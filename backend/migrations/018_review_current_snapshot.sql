-- Migration 018: Owner-authenticated atomic Review Snapshot read RPC (W4-MVP-03)
-- Reads current review candidate matrix, frozen confirmed sources, progress and freshness token.

BEGIN;

CREATE OR REPLACE FUNCTION public.get_review_current_snapshot(p_session_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  s public.exam_sessions%ROWTYPE;
  job public.generation_job_snapshots%ROWTYPE;
  v_rec RECORD;
  src RECORD;
  q_rec RECORD;
  r_rec RECORD;
  
  sources_json jsonb := '[]'::jsonb;
  versions_json jsonb := '[]'::jsonb;
  slots_json jsonb;
  candidate_json jsonb;
  
  v_norm_options jsonb;
  v_val_report jsonb;
  v_val_source text;
  v_origin text;
  
  n_sources int := 0;
  expected_slots int := 0;
  current_slots int := 0;
  approved_slots int := 0;
  missing_slots int := 0;
  is_read_only boolean := false;
  
  freshness_buf text := '';
  freshness_token text := '';
  
  v_code text;
  v_id uuid;
  has_post_shuffle boolean := false;
BEGIN
  -- 1. Owner Authorization & Locking (FOR SHARE)
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND OR auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  -- 2. State validation & guards
  IF s.status IN ('draft', 'blueprinted', 'configured', 'generating') THEN
    RAISE EXCEPTION 'REVIEW_NOT_READY' USING ERRCODE = '55000';
  END IF;

  IF s.status IN ('approved', 'exported') THEN
    RAISE EXCEPTION 'REVIEW_LOCKED' USING ERRCODE = '55000';
  END IF;

  -- Check if shuffle has already been persisted
  SELECT EXISTS(
    SELECT 1 FROM public.exam_versions 
    WHERE session_id = s.id AND is_finalized = true
  ) INTO has_post_shuffle;

  IF s.status = 'reviewed' AND has_post_shuffle THEN
    RAISE EXCEPTION 'REVIEW_POST_SHUFFLE_LOCKED' USING ERRCODE = '55000';
  END IF;

  -- 3. Load frozen generation job snapshot
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL OR job.snapshot_payload IS NULL THEN
    RAISE EXCEPTION 'REVIEW_NO_SNAPSHOT' USING ERRCODE = '55000';
  END IF;

  IF jsonb_typeof(job.snapshot_payload->'confirmed_sources') IS DISTINCT FROM 'array'
     OR jsonb_array_length(job.snapshot_payload->'confirmed_sources') = 0 THEN
    RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE = '22023';
  END IF;

  -- 4. Invariant checks: Fail-closed on corrupted candidate state
  -- a) Check for duplicate current candidates on any slot
  IF EXISTS (
    SELECT q.version_id, q.source_question_id
    FROM public.version_questions q
    JOIN public.exam_versions ev ON ev.id = q.version_id
    WHERE ev.session_id = s.id AND q.is_current = true
    GROUP BY q.version_id, q.source_question_id
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: duplicate current candidate' USING ERRCODE = '22023';
  END IF;

  -- b) Check for orphan/foreign current candidates not matching confirmed sources
  IF EXISTS (
    SELECT 1
    FROM public.version_questions q
    JOIN public.exam_versions ev ON ev.id = q.version_id
    WHERE ev.session_id = s.id AND q.is_current = true
      AND NOT EXISTS (
        SELECT 1 
        FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') cs
        WHERE (cs->>'source_question_id')::uuid = q.source_question_id
      )
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: foreign or orphan candidate' USING ERRCODE = '22023';
  END IF;

  -- 5. Build canonical sources list from frozen snapshot payload
  FOR src IN 
    SELECT 
      (x->>'source_question_id')::uuid AS source_question_id,
      (x->>'question_no')::int AS question_no,
      (x->>'source_revision_id')::uuid AS source_revision_id,
      coalesce(x->'confirmed_input'->>'question_text', x->>'content', x->>'raw_content') AS content,
      coalesce(x->'confirmed_input'->'options', x->'options') AS options,
      coalesce(x->'confirmed_input'->>'correct_answer', x->>'correct_key') AS correct_key,
      nullif(coalesce(x->'confirmed_input'->>'solution', x->>'solution_md', ''), '') AS solution_md
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') x
    ORDER BY (x->>'question_no')::int, (x->>'source_question_id')::uuid
  LOOP
    n_sources := n_sources + 1;
    
    -- Normalize options into 4-array [A, B, C, D]
    IF jsonb_typeof(src.options) = 'object' AND src.options ? 'A' AND src.options ? 'B' AND src.options ? 'C' AND src.options ? 'D' THEN
      v_norm_options := jsonb_build_array(src.options->'A', src.options->'B', src.options->'C', src.options->'D');
    ELSIF jsonb_typeof(src.options) = 'array' AND jsonb_array_length(src.options) = 4 THEN
      v_norm_options := src.options;
    ELSE
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid source options' USING ERRCODE = '22023';
    END IF;

    sources_json := sources_json || jsonb_build_array(
      jsonb_build_object(
        'source_question_id', src.source_question_id,
        'question_no', src.question_no,
        'source_revision_id', src.source_revision_id,
        'content', src.content,
        'options', v_norm_options,
        'correct_key', src.correct_key,
        'solution_md', src.solution_md
      )
    );
  END LOOP;

  expected_slots := job.n_versions * n_sources;
  is_read_only := (s.status IN ('partial_generated', 'failed'));

  freshness_buf := coalesce(job.confirmed_source_hash, '') || ':' || job.id::text || ':' || job.confirmation_id::text;

  -- 6. Build Version Matrix & Slots
  FOR v_rec IN 
    SELECT idx AS version_index
    FROM generate_series(1, job.n_versions) AS idx
    ORDER BY idx
  LOOP
    v_code := (100 + v_rec.version_index)::text;
    
    -- Lookup persisted version_id if available
    SELECT id INTO v_id 
    FROM public.exam_versions 
    WHERE session_id = s.id AND version_code = v_code;

    slots_json := '[]'::jsonb;

    -- Iterate each source in exact frozen order
    FOR src IN 
      SELECT 
        (x->>'source_question_id')::uuid AS source_question_id,
        (x->>'question_no')::int AS question_no
      FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') x
      ORDER BY (x->>'question_no')::int, (x->>'source_question_id')::uuid
    LOOP
      candidate_json := 'null'::jsonb;
      
      IF v_id IS NOT NULL THEN
        -- Find single current candidate
        SELECT * INTO q_rec
        FROM public.version_questions
        WHERE version_id = v_id 
          AND source_question_id = src.source_question_id
          AND is_current = true;

        IF q_rec.id IS NOT NULL THEN
          current_slots := current_slots + 1;
          IF q_rec.status = 'approved' THEN
            approved_slots := approved_slots + 1;
          END IF;

          -- Look up target generation result for validation & provenance
          SELECT * INTO r_rec
          FROM public.generation_target_results
          WHERE version_question_id = q_rec.id
            AND session_id = s.id
            AND snapshot_id = job.id
            AND is_success = true
          LIMIT 1;

          -- Normalize candidate options
          IF jsonb_typeof(q_rec.options) = 'object' AND q_rec.options ? 'A' AND q_rec.options ? 'B' AND q_rec.options ? 'C' AND q_rec.options ? 'D' THEN
            v_norm_options := jsonb_build_array(q_rec.options->'A', q_rec.options->'B', q_rec.options->'C', q_rec.options->'D');
          ELSIF jsonb_typeof(q_rec.options) = 'array' AND jsonb_array_length(q_rec.options) = 4 THEN
            v_norm_options := q_rec.options;
          ELSE
            RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid candidate options' USING ERRCODE = '22023';
          END IF;

          -- Determine Validation Report & Source
          IF q_rec.validation_report IS NOT NULL AND q_rec.validation_report <> '{}'::jsonb THEN
            v_val_report := q_rec.validation_report;
            v_val_source := 'version_question';
          ELSIF r_rec.id IS NOT NULL 
                AND r_rec.raw_result->'validation' IS NOT NULL 
                AND r_rec.raw_result->'validation' <> '{}'::jsonb 
                AND r_rec.raw_result->'validation' <> 'null'::jsonb THEN
            v_val_report := r_rec.raw_result->'validation';
            v_val_source := 'generation_result';
          ELSE
            v_val_report := NULL;
            v_val_source := 'unavailable';
          END IF;

          -- Determine Provenance Origin
          IF q_rec.regenerated_from_id IS NOT NULL THEN
            v_origin := 'regenerated';
          ELSIF q_rec.is_reverted THEN
            v_origin := 'reverted';
          ELSIF r_rec.id IS NOT NULL AND r_rec.result_kind = 'ORIGINAL_CLONE' THEN
            v_origin := 'original_clone';
          ELSIF (r_rec.id IS NOT NULL AND (r_rec.result_kind = 'AI_RESULT' OR r_rec.is_success)) THEN
            v_origin := 'ai_generated';
          ELSE
            v_origin := 'unknown';
          END IF;

          candidate_json := jsonb_build_object(
            'candidate_id', q_rec.id,
            'status', q_rec.status,
            'content', q_rec.content,
            'options', v_norm_options,
            'correct_key', q_rec.correct_key,
            'solution_md', nullif(coalesce(q_rec.solution_md, ''), ''),
            'has_warning', coalesce(q_rec.has_warning, false),
            'validation_report', CASE WHEN v_val_report IS NULL THEN 'null'::jsonb ELSE v_val_report END,
            'validation_source', v_val_source,
            'origin', v_origin,
            'is_reverted', coalesce(q_rec.is_reverted, false),
            'updated_at', to_char(q_rec.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
          );

          freshness_buf := freshness_buf || '|' || v_rec.version_index::text || ':' || src.source_question_id::text
                           || ':' || q_rec.id::text || ':' || q_rec.status::text || ':' 
                           || coalesce(q_rec.has_warning::text, 'f') || ':' || coalesce(q_rec.is_reverted::text, 'f')
                           || ':' || to_char(q_rec.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"');
        ELSE
          freshness_buf := freshness_buf || '|' || v_rec.version_index::text || ':' || src.source_question_id::text || ':null';
        END IF;
      ELSE
        freshness_buf := freshness_buf || '|' || v_rec.version_index::text || ':' || src.source_question_id::text || ':no_version';
      END IF;

      slots_json := slots_json || jsonb_build_array(
        jsonb_build_object(
          'source_question_id', src.source_question_id,
          'question_no', src.question_no,
          'candidate', candidate_json
        )
      );
    END LOOP;

    versions_json := versions_json || jsonb_build_array(
      jsonb_build_object(
        'version_index', v_rec.version_index,
        'version_code', v_code,
        'version_id', v_id,
        'slots', slots_json
      )
    );
  END LOOP;

  missing_slots := expected_slots - current_slots;
  freshness_token := encode(sha256(convert_to(freshness_buf, 'UTF8')), 'hex');

  -- 7. Assemble final response
  RETURN jsonb_build_object(
    'session_id', s.id,
    'session_status', s.status,
    'read_only', is_read_only,
    'confirmation_id', job.confirmation_id,
    'job_snapshot_id', job.id,
    'confirmed_source_hash', job.confirmed_source_hash,
    'freshness_token', freshness_token,
    'progress', jsonb_build_object(
      'expected_slots', expected_slots,
      'current_slots', current_slots,
      'approved_slots', approved_slots,
      'missing_slots', missing_slots,
      'ready', (expected_slots > 0 AND current_slots = expected_slots AND approved_slots = expected_slots)
    ),
    'sources', sources_json,
    'versions', versions_json
  );
END;
$$;

-- Security & ACL
REVOKE ALL ON FUNCTION public.get_review_current_snapshot(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_review_current_snapshot(uuid) TO authenticated;

COMMIT;
