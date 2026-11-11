-- Migration 018: Owner-authenticated Review Snapshot read RPC (W4-MVP-03)
-- Reads current review candidate matrix, frozen confirmed sources, progress and freshness token.
-- Operates in a single statement snapshot (STABLE) without row locks.

BEGIN;

-- 1. Private stable reader for source artifacts (reusable by _review_progress and public wrapper)
CREATE OR REPLACE FUNCTION public._get_source_artifacts_data(p_session_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  s public.exam_sessions;
  c public.source_artifact_confirmations;
  pending JSONB;
  states JSONB;
  modes JSONB;
  doc JSONB;
  transform JSONB;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id;
  IF NOT FOUND OR (auth.role() IS DISTINCT FROM 'service_role'
      AND (auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid())) THEN
    RAISE EXCEPTION 'ARTIFACT_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  SELECT * INTO c FROM public.source_artifact_confirmations WHERE session_id = s.id
    ORDER BY confirmed_at DESC, confirmation_id DESC LIMIT 1;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ARTIFACT_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  IF jsonb_array_length(c.result->'sources') <> (SELECT count(*) FROM public.source_questions WHERE session_id = s.id)
    OR EXISTS (
      SELECT 1 FROM jsonb_array_elements(c.result->'sources') item
      LEFT JOIN public.source_artifact_heads h ON h.source_question_id = (item->>'source_question_id')::uuid
      LEFT JOIN public.source_questions q ON q.id = h.source_question_id
      WHERE h.source_revision_id IS DISTINCT FROM (item->>'source_revision_id')::uuid
        OR public._artifact_source_input(q) IS DISTINCT FROM item->'confirmed_input'
    ) THEN
    RAISE EXCEPTION 'ARTIFACT_STALE' USING ERRCODE = '55000';
  END IF;

  SELECT coalesce(jsonb_agg(h.source_question_id ORDER BY h.source_question_id), '[]'::jsonb)
    INTO pending FROM public.source_artifact_heads h JOIN public.source_questions q ON q.id = h.source_question_id
    WHERE q.session_id = s.id AND h.blueprint_revision_id IS NULL;

  SELECT coalesce(jsonb_agg(jsonb_build_object('source_question_id', h.source_question_id,
    'source_revision_id', h.source_revision_id, 'status', CASE
      WHEN h.blueprint_revision_id IS NOT NULL THEN 'ready'
      WHEN h.producer_error_code IS NOT NULL THEN 'failed'
      WHEN h.producer_expires_at > CURRENT_TIMESTAMP THEN 'running' ELSE 'pending' END,
    'expires_at', h.producer_expires_at, 'error_code', h.producer_error_code) ORDER BY h.source_question_id), '[]'::jsonb)
    INTO states FROM public.source_artifact_heads h JOIN public.source_questions q ON q.id = h.source_question_id
    WHERE q.session_id = s.id;

  IF jsonb_array_length(pending) = 0 THEN
    FOR doc IN
      SELECT b.canonical_blueprint FROM public.source_artifact_heads h
      JOIN public.source_questions q ON q.id = h.source_question_id
      JOIN public.canonical_blueprint_revisions b ON
        (b.blueprint_revision_id, b.source_revision_id, b.source_question_id) =
        (h.blueprint_revision_id, h.source_revision_id, h.source_question_id)
      WHERE q.session_id = s.id
    LOOP
      IF doc->'requirement'->>'schema_version' IS DISTINCT FROM '0.4.0'
        OR jsonb_typeof(doc#>'{requirement,variation_policy,allowed_transformations}') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'ARTIFACT_INVALID_CANONICAL_MODES' USING ERRCODE = '22023';
      END IF;
      IF jsonb_array_length(doc#>'{requirement,variation_policy,allowed_transformations}') = 0 THEN
        RAISE EXCEPTION 'ARTIFACT_INVALID_CANONICAL_MODES' USING ERRCODE = '22023';
      END IF;
      FOR transform IN SELECT value FROM jsonb_array_elements(doc#>'{requirement,variation_policy,allowed_transformations}') LOOP
        IF jsonb_typeof(transform) IS DISTINCT FROM 'object'
          OR jsonb_typeof(transform->'dimension') IS DISTINCT FROM 'string'
          OR transform->>'dimension' NOT IN ('wording', 'names', 'context', 'values', 'representation', 'option_order') THEN
          RAISE EXCEPTION 'ARTIFACT_INVALID_CANONICAL_MODES' USING ERRCODE = '22023';
        END IF;
      END LOOP;
    END LOOP;

    WITH profile(id, dimension, label, description) AS (VALUES
      ('NUMERICAL', 'values', 'Thay đổi số liệu / tham số', 'Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.'),
      ('parameter_variation', 'values', 'Thay đổi số liệu / tham số', 'Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.'),
      ('context_swap', 'context', 'Đổi ngữ cảnh thực tế', 'Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.')
    ), dimensions AS (
      SELECT DISTINCT h.source_question_id, t->>'dimension' AS dimension
      FROM public.source_artifact_heads h
      JOIN public.source_questions q ON q.id = h.source_question_id
      JOIN public.canonical_blueprint_revisions b ON
        (b.blueprint_revision_id, b.source_revision_id, b.source_question_id) =
        (h.blueprint_revision_id, h.source_revision_id, h.source_question_id)
      CROSS JOIN LATERAL jsonb_array_elements(b.canonical_blueprint#>'{requirement,variation_policy,allowed_transformations}') t
      WHERE q.session_id = s.id
    ), counts AS (
      SELECT p.id, p.label, p.description, count(*) AS n FROM dimensions d
      JOIN profile p ON p.dimension = d.dimension GROUP BY p.id, p.label, p.description
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('id', id, 'label', label, 'description', description,
      'question_count', n, 'is_available', n = (c.result->>'total_questions')::int) ORDER BY id COLLATE "C"), '[]'::jsonb)
      INTO modes FROM counts;
  END IF;

  RETURN jsonb_build_object('confirmation', c.result, 'pending_source_question_ids', pending, 'production', states,
    'ready', jsonb_array_length(pending) = 0, 'supported_modes', modes);
END;
$$;

REVOKE ALL ON FUNCTION public._get_source_artifacts_data(UUID) FROM PUBLIC, anon, authenticated, service_role;

-- 2. Public get_source_artifacts wrapper retaining row-locking and authorization boundary
CREATE OR REPLACE FUNCTION public.get_source_artifacts(p_session_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  s public.exam_sessions;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND OR (auth.role() IS DISTINCT FROM 'service_role'
      AND (auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid())) THEN
    RAISE EXCEPTION 'ARTIFACT_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  RETURN public._get_source_artifacts_data(p_session_id);
END;
$$;

REVOKE ALL ON FUNCTION public.get_source_artifacts(UUID) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_source_artifacts(UUID) TO authenticated, service_role;

-- 3. Replace _review_progress to be STABLE and call _get_source_artifacts_data
CREATE OR REPLACE FUNCTION public._review_progress(p_session_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  nv INT;
  ns INT;
  config_count INT;
  versions_count INT;
  codes_count INT;
  currents INT;
  approved INT;
  regenerating INT;
  missing INT;
  duplicates INT;
  extras INT;
  expected INT;
  ready BOOLEAN;
  unapproved JSONB;
  source_ready BOOLEAN;
BEGIN
  SELECT count(*), min(n_versions) INTO config_count, nv FROM public.generation_configs WHERE session_id = p_session_id;
  SELECT count(*) INTO ns FROM public.source_questions WHERE session_id = p_session_id;
  IF config_count <> 1 OR ns = 0 OR EXISTS (
    SELECT question_no FROM public.source_questions WHERE session_id = p_session_id GROUP BY question_no HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (SELECT 1 FROM public.source_artifact_confirmations WHERE session_id = p_session_id) THEN
    BEGIN
      source_ready := (public._get_source_artifacts_data(p_session_id)->>'ready')::boolean;
    EXCEPTION WHEN SQLSTATE 'P0002' OR SQLSTATE '55000' THEN
      source_ready := false;
    END;
  ELSE
    SELECT NOT EXISTS (
      SELECT 1 FROM public.source_questions s LEFT JOIN public.question_blueprints b ON b.source_question_id = s.id
      WHERE s.session_id = p_session_id AND b.confirmed_at IS NULL
    ) INTO source_ready;
  END IF;

  expected := nv * ns;
  SELECT count(*), count(DISTINCT version_code) INTO versions_count, codes_count
    FROM public.exam_versions WHERE session_id = p_session_id;
  SELECT count(*), count(*) FILTER (WHERE q.status = 'approved'), count(*) FILTER (WHERE q.status = 'regenerating'),
    count(*) FILTER (WHERE s.id IS NULL OR q.canonical_question_no IS DISTINCT FROM s.question_no)
    INTO currents, approved, regenerating, extras
  FROM public.exam_versions v JOIN public.version_questions q ON q.version_id = v.id AND q.is_current
    LEFT JOIN public.source_questions s ON s.id = q.source_question_id AND s.session_id = p_session_id
  WHERE v.session_id = p_session_id;

  SELECT count(*) FILTER (WHERE n = 0), count(*) FILTER (WHERE n > 1) INTO missing, duplicates FROM (
    SELECT v.id, s.id AS source_id, count(q.id) AS n FROM public.exam_versions v
    CROSS JOIN public.source_questions s LEFT JOIN public.version_questions q
      ON q.version_id = v.id AND q.source_question_id = s.id AND q.is_current
    WHERE v.session_id = p_session_id AND s.session_id = p_session_id GROUP BY v.id, s.id
  ) slots;

  missing := missing + greatest(nv - versions_count, 0) * ns;
  ready := source_ready AND versions_count = nv AND codes_count = nv AND missing = 0 AND duplicates = 0 AND extras = 0
    AND currents = expected AND approved = expected AND regenerating = 0
    AND NOT EXISTS (SELECT 1 FROM public.review_operations WHERE session_id = p_session_id AND status = 'active');

  SELECT coalesce(jsonb_agg(q.id ORDER BY q.id), '[]'::jsonb) INTO unapproved
    FROM public.version_questions q JOIN public.exam_versions v ON v.id = q.version_id
    WHERE v.session_id = p_session_id AND q.is_current AND q.status <> 'approved';

  RETURN jsonb_build_object(
    'expected_slots', expected,
    'current_slots', currents,
    'approved_slots', approved,
    'regenerating_slots', regenerating,
    'missing_slots', missing,
    'duplicate_slots', duplicates,
    'ready', ready,
    'unapproved_question_ids', unapproved
  );
END;
$$;

REVOKE ALL ON FUNCTION public._review_progress(UUID) FROM PUBLIC, anon, authenticated, service_role;

-- 4. Review Snapshot Read RPC: STABLE statement snapshot without row locks
CREATE OR REPLACE FUNCTION public.get_review_current_snapshot(p_session_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  s public.exam_sessions%ROWTYPE;
  job public.generation_job_snapshots%ROWTYPE;
  conf_rec public.source_artifact_confirmations%ROWTYPE;
  v_rec RECORD;
  src RECORD;
  q_rec RECORD;
  r_rec RECORD;
  auth_prog jsonb;

  sources_json jsonb := '[]'::jsonb;
  versions_json jsonb := '[]'::jsonb;
  slots_json jsonb;
  candidate_json jsonb;
  response_without_token jsonb;

  v_norm_options jsonb;
  v_val_report jsonb;
  v_val_source text;
  v_origin text;
  v_valid_result boolean;

  n_sources int := 0;
  expected_slots int := 0;
  current_slots int := 0;
  approved_slots int := 0;
  missing_slots int := 0;
  is_read_only boolean := false;
  is_ready boolean := false;

  freshness_token text := '';
  v_code text;
  v_id uuid;
  has_post_shuffle boolean := false;

  items_canonical jsonb := '[]'::jsonb;
  computed_hash text;
  idx_seq int := 0;
BEGIN
  -- 1. Owner Authorization: Lock-free owner filtered query (prevents foreign lock contention & existence leakage)
  IF auth.uid() IS NULL THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id AND user_id = auth.uid();
  IF NOT FOUND THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  -- 2. State validation & guards
  IF s.status IN ('draft', 'blueprinted', 'configured', 'generating') THEN
    RAISE EXCEPTION 'REVIEW_NOT_READY' USING ERRCODE = '55000';
  END IF;

  IF s.status IN ('approved', 'exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'REVIEW_LOCKED' USING ERRCODE = '55000';
  END IF;

  -- Check if shuffle has already been persisted
  SELECT EXISTS(
    SELECT 1 FROM public.exam_versions
    WHERE session_id = s.id AND is_finalized = true
  ) INTO has_post_shuffle;

  IF s.status = 'reviewed' AND (has_post_shuffle OR EXISTS (
    SELECT 1 FROM public.answer_keys ak
    JOIN public.exam_versions ev ON ev.id = ak.version_id
    WHERE ev.session_id = s.id
  )) THEN
    RAISE EXCEPTION 'REVIEW_POST_SHUFFLE_LOCKED' USING ERRCODE = '55000';
  END IF;

  -- 3. Load frozen generation job snapshot
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL OR job.snapshot_payload IS NULL THEN
    RAISE EXCEPTION 'REVIEW_NO_SNAPSHOT' USING ERRCODE = '55000';
  END IF;

  IF job.n_versions NOT BETWEEN 1 AND 4 THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid n_versions scope' USING ERRCODE = '22023';
  END IF;

  IF jsonb_typeof(job.snapshot_payload->'confirmed_sources') IS DISTINCT FROM 'array'
     OR jsonb_array_length(job.snapshot_payload->'confirmed_sources') = 0 THEN
    RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE = '22023';
  END IF;

  n_sources := jsonb_array_length(job.snapshot_payload->'confirmed_sources');
  IF n_sources NOT BETWEEN 1 AND 20 THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid source count in snapshot' USING ERRCODE = '22023';
  END IF;

  -- 4. Verify confirmation existence & binding
  SELECT * INTO conf_rec FROM public.source_artifact_confirmations
  WHERE confirmation_id = job.confirmation_id AND session_id = s.id;
  IF conf_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: confirmation missing or mismatched' USING ERRCODE = '22023';
  END IF;

  -- Validate frozen source revisions bound to confirmation
  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') cs
    WHERE NOT EXISTS (
      SELECT 1 FROM public.source_artifact_revisions sr
      WHERE sr.confirmation_id = job.confirmation_id
        AND sr.source_question_id = (cs->>'source_question_id')::uuid
        AND sr.source_revision_id = (cs->>'source_revision_id')::uuid
    )
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: frozen source revision not bound to confirmation' USING ERRCODE = '22023';
  END IF;

  -- Verify source order correspondence if present
  IF job.source_order IS NOT NULL AND jsonb_typeof(job.source_order) = 'array' THEN
    IF (SELECT jsonb_agg((x->>'source_question_id')::text ORDER BY ord)
        FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord))
       IS DISTINCT FROM job.source_order THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: source order mismatch' USING ERRCODE = '22023';
    END IF;
  END IF;

  -- Verify unique source IDs and sequential question numbers
  IF EXISTS (
    SELECT (x->>'source_question_id')::uuid
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') x
    GROUP BY (x->>'source_question_id')::uuid
    HAVING count(*) > 1
  ) OR EXISTS (
    SELECT (x->>'question_no')::int
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') x
    GROUP BY (x->>'question_no')::int
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: duplicate source ID or question_no in frozen sources' USING ERRCODE = '22023';
  END IF;

  -- 5. Build canonical sources list and verify canonical source hash
  FOR src IN
    SELECT
      (x->>'source_question_id')::uuid AS source_question_id,
      (x->>'question_no')::int AS question_no,
      (x->>'source_revision_id')::uuid AS source_revision_id,
      coalesce(x->'confirmed_input'->>'question_text', x->>'content', x->>'raw_content') AS content,
      coalesce(x->'confirmed_input'->'options', x->'options') AS options,
      coalesce(x->'confirmed_input'->>'correct_answer', x->>'correct_key') AS correct_key,
      nullif(coalesce(x->'confirmed_input'->>'solution', x->>'solution_md', ''), '') AS solution_md,
      x->'confirmed_input' AS confirmed_input,
      ord
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord)
    ORDER BY (x->>'question_no')::int, (x->>'source_question_id')::uuid
  LOOP
    idx_seq := idx_seq + 1;
    IF src.question_no IS DISTINCT FROM idx_seq THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: non-sequential question_no in frozen sources' USING ERRCODE = '22023';
    END IF;

    -- Normalize options into 4-array [A, B, C, D]
    IF jsonb_typeof(src.options) = 'object' AND src.options ? 'A' AND src.options ? 'B' AND src.options ? 'C' AND src.options ? 'D' THEN
      v_norm_options := jsonb_build_array(src.options->'A', src.options->'B', src.options->'C', src.options->'D');
    ELSIF jsonb_typeof(src.options) = 'array' AND jsonb_array_length(src.options) = 4 THEN
      v_norm_options := src.options;
    ELSE
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid source options' USING ERRCODE = '22023';
    END IF;

    IF src.correct_key NOT IN ('A', 'B', 'C', 'D') THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid source correct_key' USING ERRCODE = '22023';
    END IF;

    -- Hash canonicalization using migration 015 helpers
    IF src.confirmed_input IS NOT NULL THEN
      items_canonical := items_canonical || jsonb_build_array(public._generation_source_item(src.confirmed_input));
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

  -- Recompute and verify confirmed source hash if confirmed_input is available
  IF jsonb_array_length(items_canonical) = n_sources THEN
    computed_hash := encode(sha256(convert_to(public._generation_json(items_canonical), 'UTF8')), 'hex');
    IF computed_hash IS DISTINCT FROM job.confirmed_source_hash THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: confirmed source hash mismatch' USING ERRCODE = '22023';
    END IF;
  END IF;

  expected_slots := job.n_versions * n_sources;
  is_read_only := (s.status IN ('partial_generated', 'failed'));

  -- 6. Invariant candidate checks (fail-closed)
  -- a) Duplicate current candidate on any slot
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

  -- b) Orphan/foreign current candidate
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

  -- c) Current candidate in version outside frozen N scope
  IF EXISTS (
    SELECT 1
    FROM public.version_questions q
    JOIN public.exam_versions ev ON ev.id = q.version_id
    WHERE ev.session_id = s.id AND q.is_current = true
      AND ev.version_code NOT IN (
        SELECT (100 + i)::text FROM generate_series(1, job.n_versions) i
      )
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: current candidate in extra version outside frozen scope' USING ERRCODE = '22023';
  END IF;

  -- d) Canonical mapping: canonical_question_no matches frozen source question_no
  IF EXISTS (
    SELECT 1
    FROM public.version_questions q
    JOIN public.exam_versions ev ON ev.id = q.version_id
    JOIN jsonb_array_elements(job.snapshot_payload->'confirmed_sources') cs
      ON (cs->>'source_question_id')::uuid = q.source_question_id
    WHERE ev.session_id = s.id AND q.is_current = true
      AND q.canonical_question_no IS DISTINCT FROM (cs->>'question_no')::int
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: canonical_question_no mismatch with frozen source question_no' USING ERRCODE = '22023';
  END IF;

  -- 7. Build Version Matrix & Slots (always using immutable canonical candidate fields)
  FOR v_rec IN
    SELECT idx AS version_index
    FROM generate_series(1, job.n_versions) AS idx
    ORDER BY idx
  LOOP
    v_code := (100 + v_rec.version_index)::text;

    SELECT id INTO v_id
    FROM public.exam_versions
    WHERE session_id = s.id AND version_code = v_code;

    slots_json := '[]'::jsonb;

    FOR src IN
      SELECT
        (x->>'source_question_id')::uuid AS source_question_id,
        (x->>'question_no')::int AS question_no
      FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') x
      ORDER BY (x->>'question_no')::int, (x->>'source_question_id')::uuid
    LOOP
      candidate_json := 'null'::jsonb;

      IF v_id IS NOT NULL THEN
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

          -- Look up target generation result by unique slot (session_id, version_index, source_question_id)
          SELECT * INTO r_rec
          FROM public.generation_target_results
          WHERE session_id = s.id
            AND snapshot_id = job.id
            AND version_index = v_rec.version_index
            AND source_question_id = src.source_question_id;

          -- Evidence linkage check: verify candidate ID and question number
          v_valid_result := (r_rec.id IS NOT NULL
                             AND r_rec.is_success = true
                             AND r_rec.version_question_id = q_rec.id
                             AND r_rec.question_no = src.question_no);

          -- Read immutable canonical options (prevents presentation of shuffled display options)
          IF jsonb_typeof(q_rec.canonical_options) = 'object'
             AND q_rec.canonical_options ? 'A' AND q_rec.canonical_options ? 'B'
             AND q_rec.canonical_options ? 'C' AND q_rec.canonical_options ? 'D' THEN
            v_norm_options := jsonb_build_array(
              q_rec.canonical_options->'A',
              q_rec.canonical_options->'B',
              q_rec.canonical_options->'C',
              q_rec.canonical_options->'D'
            );
          ELSIF jsonb_typeof(q_rec.canonical_options) = 'array' AND jsonb_array_length(q_rec.canonical_options) = 4 THEN
            v_norm_options := q_rec.canonical_options;
          ELSE
            RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid candidate canonical options' USING ERRCODE = '22023';
          END IF;

          -- Validation Report & Source Precedence
          IF q_rec.validation_report IS NOT NULL
             AND jsonb_typeof(q_rec.validation_report) = 'object'
             AND q_rec.validation_report <> '{}'::jsonb THEN
            v_val_report := q_rec.validation_report;
            v_val_source := 'version_question';
          ELSIF v_valid_result
                AND r_rec.raw_result->'validation' IS NOT NULL
                AND jsonb_typeof(r_rec.raw_result->'validation') = 'object'
                AND r_rec.raw_result->'validation' <> '{}'::jsonb THEN
            v_val_report := r_rec.raw_result->'validation';
            v_val_source := 'generation_result';
          ELSE
            v_val_report := NULL;
            v_val_source := 'unavailable';
          END IF;

          -- Provenance Origin Precedence
          IF q_rec.regenerated_from_id IS NOT NULL THEN
            v_origin := 'regenerated';
          ELSIF coalesce(q_rec.is_reverted, false) THEN
            v_origin := 'reverted';
          ELSIF v_valid_result THEN
            IF r_rec.result_kind = 'ORIGINAL_CLONE' THEN
              v_origin := 'original_clone';
            ELSIF r_rec.result_kind = 'AI_RESULT' THEN
              v_origin := 'ai_generated';
            ELSE
              v_origin := 'unknown';
            END IF;
          ELSE
            v_origin := 'unknown';
          END IF;

          candidate_json := jsonb_build_object(
            'candidate_id', q_rec.id,
            'status', q_rec.status,
            'content', q_rec.content,
            'options', v_norm_options,
            'correct_key', q_rec.canonical_correct_key,
            'solution_md', nullif(coalesce(q_rec.canonical_solution_md, ''), ''),
            'has_warning', coalesce(q_rec.has_warning, false),
            'validation_report', CASE WHEN v_val_report IS NULL THEN 'null'::jsonb ELSE v_val_report END,
            'validation_source', v_val_source,
            'origin', v_origin,
            'is_reverted', coalesce(q_rec.is_reverted, false),
            'updated_at', to_char(q_rec.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
          );
        END IF;
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

  -- 8. Authoritative review progress consensus (fail-closed, no permissive fallback)
  BEGIN
    auth_prog := public._review_progress(s.id);
  EXCEPTION
    WHEN SQLSTATE '22023' THEN
      RAISE;
    WHEN OTHERS THEN
      RAISE EXCEPTION 'REVIEW_PROGRESS_UNAVAILABLE' USING ERRCODE = '55000';
  END;

  IF auth_prog IS NULL
     OR (auth_prog->>'expected_slots')::int <> expected_slots
     OR (auth_prog->>'current_slots')::int <> current_slots
     OR (auth_prog->>'approved_slots')::int <> approved_slots
     OR (auth_prog->>'missing_slots')::int <> missing_slots THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: progress mismatch with authoritative review state' USING ERRCODE = '22023';
  END IF;

  is_ready := coalesce((auth_prog->>'ready')::boolean, false);

  -- 9. Canonical response payload
  response_without_token := jsonb_build_object(
    'session_id', s.id,
    'session_status', s.status,
    'read_only', is_read_only,
    'confirmation_id', job.confirmation_id,
    'job_snapshot_id', job.id,
    'confirmed_source_hash', job.confirmed_source_hash,
    'progress', jsonb_build_object(
      'expected_slots', expected_slots,
      'current_slots', current_slots,
      'approved_slots', approved_slots,
      'missing_slots', missing_slots,
      'ready', is_ready
    ),
    'sources', sources_json,
    'versions', versions_json
  );

  -- 10. Deterministic Freshness Token: SHA-256 of canonical response without token
  freshness_token := encode(sha256(convert_to(response_without_token::text, 'UTF8')), 'hex');

  RETURN response_without_token || jsonb_build_object('freshness_token', freshness_token);
END;
$$;

-- Security & ACL
REVOKE ALL ON FUNCTION public.get_review_current_snapshot(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_review_current_snapshot(uuid) TO authenticated;

COMMIT;
