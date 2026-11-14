-- Migration 021: W4 C5 Confirmed-Source Fallback (Checkpoints 1 & 2)
-- Implements atomic fallback writer and authoritative read-back contract
-- Dependency: 015 (W2 integration), 016 (Original Clone), 017 (Recovery), 018 (Review snapshot)

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Extend generation_result_kind CHECK Constraint
-- ----------------------------------------------------------------------------
ALTER TABLE public.generation_target_results DROP CONSTRAINT IF EXISTS generation_result_kind;
ALTER TABLE public.generation_target_results ADD CONSTRAINT generation_result_kind CHECK (
  (result_kind = 'AI_RESULT' AND request_fingerprint IS NOT NULL AND clone_fingerprint IS NULL)
  OR (result_kind = 'ORIGINAL_CLONE' AND request_fingerprint IS NULL
      AND clone_fingerprint ~ '^[a-f0-9]{64}$' AND clone_fingerprint IS NOT NULL
      AND is_success AND error_code IS NULL AND attempts = 0)
  OR (result_kind = 'CONFIRMED_SOURCE_FALLBACK' AND request_fingerprint ~ '^[a-f0-9]{64}$'
      AND request_fingerprint IS NOT NULL AND clone_fingerprint IS NULL
      AND is_success AND error_code = 'GENERATION_RETRIES_EXHAUSTED'
      AND attempts = 4 AND version_question_id IS NOT NULL)
);

-- ----------------------------------------------------------------------------
-- 2. Extend _generation_assert_result_kind (Accept fallback only for AI jobs)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public._generation_assert_result_kind(p_session_id uuid, p_snapshot_id uuid)
RETURNS void LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.generation_target_results r
    JOIN public.generation_job_snapshots j ON j.id = r.snapshot_id AND j.session_id = r.session_id
    WHERE r.session_id = p_session_id AND r.snapshot_id = p_snapshot_id
      AND (
        (j.public_modes = '[]'::jsonb AND j.canonical_dimensions = '[]'::jsonb AND r.result_kind IS DISTINCT FROM 'ORIGINAL_CLONE')
        OR
        ((j.public_modes IS DISTINCT FROM '[]'::jsonb OR j.canonical_dimensions IS DISTINCT FROM '[]'::jsonb)
         AND r.result_kind NOT IN ('AI_RESULT', 'CONFIRMED_SOURCE_FALLBACK'))
      )
  ) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result kind differs from frozen job; explicit reconciliation required' USING ERRCODE = '55006';
  END IF;
END $$;
REVOKE ALL ON FUNCTION public._generation_assert_result_kind(uuid, uuid) FROM PUBLIC, anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 3. Private Helper: _generation_fallback_record
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public._generation_fallback_record(
  p_job public.generation_job_snapshots,
  p_source_question_id uuid,
  p_version_index int,
  p_request_fingerprint text,
  p_last_error_code text
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  src jsonb;
  idx int;
  conf_rec public.source_artifact_confirmations%ROWTYPE;
  rev_rec public.source_artifact_revisions%ROWTYPE;
  input jsonb;
  item jsonb;
  src_fp text;
  all_items jsonb;
  all_hash text;
  spaces text := U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
BEGIN
  IF p_job.id IS NULL OR p_job.snapshot_payload IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing job snapshot payload' USING ERRCODE = '22023';
  END IF;
  IF p_version_index IS NULL OR p_version_index NOT BETWEEN 1 AND p_job.n_versions THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: version_index out of bounds' USING ERRCODE = '22023';
  END IF;
  IF p_request_fingerprint IS NULL OR p_request_fingerprint !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid request_fingerprint' USING ERRCODE = '22023';
  END IF;
  IF p_last_error_code IS NULL OR p_last_error_code !~ '^[A-Z0-9_]{3,64}$' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid last_error_code' USING ERRCODE = '22023';
  END IF;

  SELECT x, ord::int - 1 INTO src, idx
  FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord)
  WHERE (x->>'source_question_id')::uuid = p_source_question_id;

  IF src IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source_question_id not found in frozen snapshot' USING ERRCODE = '22023';
  END IF;
  IF (SELECT count(*) FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') x
      WHERE (x->>'source_question_id')::uuid = p_source_question_id) <> 1 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: non-unique source in frozen snapshot' USING ERRCODE = '22023';
  END IF;

  -- Bind snapshot confirmation to the same session
  SELECT * INTO conf_rec FROM public.source_artifact_confirmations
  WHERE confirmation_id = p_job.confirmation_id AND session_id = p_job.session_id;
  IF conf_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmation missing or mismatched' USING ERRCODE = '22023';
  END IF;

  -- Bind source revision to that confirmation/source
  SELECT * INTO rev_rec FROM public.source_artifact_revisions
  WHERE confirmation_id = p_job.confirmation_id
    AND source_question_id = p_source_question_id
    AND source_revision_id = (src->>'source_revision_id')::uuid;
  IF rev_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source revision not bound to confirmation' USING ERRCODE = '22023';
  END IF;

  -- Frozen confirmed_input must equal stored revision input
  IF rev_rec.confirmed_input IS DISTINCT FROM src->'confirmed_input' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmed_input mismatch with stored revision' USING ERRCODE = '22023';
  END IF;

  -- Check blueprint revision binding
  IF src->>'blueprint_revision_id' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing blueprint_revision_id' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.canonical_blueprint_revisions b
    WHERE b.blueprint_revision_id = (src->>'blueprint_revision_id')::uuid
      AND b.source_revision_id = (src->>'source_revision_id')::uuid
      AND b.source_question_id = p_source_question_id
  ) THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: blueprint revision not bound to source' USING ERRCODE = '22023';
  END IF;

  -- Check source order if present
  IF p_job.source_order IS NOT NULL AND jsonb_typeof(p_job.source_order) = 'array' THEN
    IF (SELECT jsonb_agg((x->>'source_question_id')::text ORDER BY ord)
        FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord))
       IS DISTINCT FROM p_job.source_order THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source order mismatch' USING ERRCODE = '22023';
    END IF;
  END IF;

  -- Recompute source fingerprint
  item := public._generation_source_item(src->'confirmed_input');
  src_fp := encode(sha256(convert_to(public._generation_json(jsonb_build_array(item)), 'UTF8')), 'hex');
  IF src_fp IS DISTINCT FROM src->>'source_fingerprint' OR src_fp IS DISTINCT FROM rev_rec.source_fingerprint THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source fingerprint mismatch' USING ERRCODE = '22023';
  END IF;

  -- Recompute confirmed_source_hash across all confirmed sources
  SELECT coalesce(jsonb_agg(public._generation_source_item(x->'confirmed_input') ORDER BY ord), '[]'::jsonb)
  INTO all_items
  FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord);

  all_hash := encode(sha256(convert_to(public._generation_json(all_items), 'UTF8')), 'hex');
  IF all_hash IS DISTINCT FROM p_job.confirmed_source_hash THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmed source hash mismatch' USING ERRCODE = '22023';
  END IF;

  -- Validate confirmed_input content
  input := src->'confirmed_input';
  IF input IS NULL OR jsonb_typeof(input) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or invalid confirmed_input' USING ERRCODE = '22023';
  END IF;

  -- Non-whitespace stem
  IF jsonb_typeof(input->'question_text') IS DISTINCT FROM 'string'
     OR coalesce(input->>'question_text', '') !~ ('[^' || spaces || ']') THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or whitespace question_text' USING ERRCODE = '22023';
  END IF;

  -- Four non-whitespace string options
  IF jsonb_typeof(input->'options') IS DISTINCT FROM 'array'
     OR jsonb_array_length(input->'options') <> 4
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(input->'options') opt
       WHERE jsonb_typeof(opt) IS DISTINCT FROM 'string'
          OR coalesce(opt#>>'{}', '') !~ ('[^' || spaces || ']')
     ) THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid options array' USING ERRCODE = '22023';
  END IF;

  -- A-D key
  IF input->>'correct_answer' NOT IN ('A', 'B', 'C', 'D') OR input->>'correct_answer' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid correct_answer' USING ERRCODE = '22023';
  END IF;

  -- Non-whitespace solution (mandatory for fallback)
  IF jsonb_typeof(input->'solution') IS DISTINCT FROM 'string'
     OR coalesce(input->>'solution', '') !~ ('[^' || spaces || ']') THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or whitespace solution' USING ERRCODE = '22023';
  END IF;

  RETURN jsonb_build_object(
    'result_kind', 'CONFIRMED_SOURCE_FALLBACK',
    'snapshot_id', lower(p_job.id::text),
    'confirmation_id', lower(p_job.confirmation_id::text),
    'version_index', p_version_index,
    'source_question_id', lower(p_source_question_id::text),
    'question_no', (src->>'question_no')::int,
    'source_revision_id', lower((src->>'source_revision_id')::uuid::text),
    'blueprint_revision_id', lower((src->>'blueprint_revision_id')::uuid::text),
    'source_fingerprint', src->>'source_fingerprint',
    'confirmed_source_hash', p_job.confirmed_source_hash,
    'seed', p_job.base_seed + p_version_index * 1000 + idx,
    'request_fingerprint', p_request_fingerprint,
    'attempts', 4,
    'error_code', 'GENERATION_RETRIES_EXHAUSTED',
    'last_error_code', p_last_error_code,
    'content', input->>'question_text',
    'options', input->'options',
    'correct_key', input->>'correct_answer',
    'solution_md', input->>'solution',
    'has_warning', true
  );
END;
$$;
REVOKE ALL ON FUNCTION public._generation_fallback_record(public.generation_job_snapshots, uuid, int, text, text)
FROM PUBLIC, anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. Replace persist_generation_result Wrapper (Checkpoint 1)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.persist_generation_result(
  p_session_id uuid,
  p_job_token uuid,
  p_version_index int,
  p_source_question_id uuid,
  p_question_no int,
  p_is_success boolean,
  p_error_code text,
  p_attempts int,
  p_seed int,
  p_request_fingerprint text,
  p_raw_result jsonb,
  p_content text,
  p_options jsonb,
  p_correct_key text,
  p_solution_md text,
  p_has_warning boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  s public.exam_sessions;
  job public.generation_job_snapshots;
  prior public.generation_target_results;
  kind text;
  expected jsonb;
  v_id uuid;
  q_id uuid;
  q_rec public.version_questions%ROWTYPE;
  val_report jsonb;
BEGIN
  -- 1. Require actual service_role; lock exam_sessions FOR UPDATE
  IF public.current_role() <> 'service_role' THEN
    RAISE EXCEPTION 'Worker only' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;

  -- 2. Check session existence, status='generating', non-null job token, and absence of approval BEFORE replay lookup
  IF s.status <> 'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
    RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE = '55006';
  END IF;
  IF s.approved_at IS NOT NULL OR s.status IN ('approved', 'exported') THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: session already approved' USING ERRCODE = '55006';
  END IF;

  -- 3. Load and validate the frozen job; reject Original Clone jobs
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing generation snapshot' USING ERRCODE = '55006';
  END IF;
  IF job.public_modes = '[]'::jsonb AND job.canonical_dimensions = '[]'::jsonb THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone job requires ORIGINAL_CLONE result kind' USING ERRCODE = '22023';
  END IF;

  -- 4. Validate existing result kinds and inspect the slot's prior result
  PERFORM public._generation_assert_result_kind(s.id, job.id);

  IF jsonb_typeof(p_raw_result) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: raw_result must be a json object' USING ERRCODE = '22023';
  END IF;

  SELECT * INTO prior FROM public.generation_target_results
  WHERE session_id = s.id AND version_index = p_version_index AND source_question_id = p_source_question_id;

  -- 5. Dispatch based on result_kind discriminator
  IF p_raw_result ? 'result_kind' THEN
    IF p_raw_result->'result_kind' = 'null'::jsonb THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result_kind cannot be null' USING ERRCODE = '22023';
    END IF;
    kind := p_raw_result->>'result_kind';
    IF kind NOT IN ('CONFIRMED_SOURCE_FALLBACK', 'AI_RESULT') THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unsupported result_kind %', kind USING ERRCODE = '22023';
    END IF;
  ELSE
    kind := 'AI_RESULT';
  END IF;

  IF kind = 'AI_RESULT' THEN
    -- AI dispatch: reject attempts to replace an existing fallback first
    IF prior.id IS NOT NULL AND prior.result_kind = 'CONFIRMED_SOURCE_FALLBACK' THEN
      RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: cannot overwrite fallback with AI result' USING ERRCODE = '23505';
    END IF;

    RETURN public._generation_persist_010(
      p_session_id, p_job_token, p_version_index, p_source_question_id,
      p_question_no, p_is_success, p_error_code, p_attempts, p_seed,
      p_request_fingerprint, p_raw_result, p_content, p_options,
      p_correct_key, p_solution_md, p_has_warning
    );
  END IF;

  -- --------------------------------------------------------------------------
  -- CONFIRMED_SOURCE_FALLBACK branch
  -- --------------------------------------------------------------------------
  IF p_is_success IS NOT TRUE THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires is_success=true' USING ERRCODE = '22023';
  END IF;
  IF p_attempts IS DISTINCT FROM 4 THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires attempts=4' USING ERRCODE = '22023';
  END IF;
  IF p_error_code IS DISTINCT FROM 'GENERATION_RETRIES_EXHAUSTED' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires error_code=GENERATION_RETRIES_EXHAUSTED' USING ERRCODE = '22023';
  END IF;
  IF p_has_warning IS NOT TRUE THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires has_warning=true' USING ERRCODE = '22023';
  END IF;
  IF p_raw_result ? 'candidate' OR p_raw_result ? 'validation' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback cannot contain AI candidate or validation' USING ERRCODE = '22023';
  END IF;

  -- Check caller projection matches raw result fields
  IF p_raw_result->>'source_question_id' IS DISTINCT FROM p_source_question_id::text
     OR p_raw_result->'version_index' IS DISTINCT FROM to_jsonb(p_version_index)
     OR p_raw_result->'question_no' IS DISTINCT FROM to_jsonb(p_question_no)
     OR p_raw_result->'seed' IS DISTINCT FROM to_jsonb(p_seed)
     OR p_raw_result->>'request_fingerprint' IS DISTINCT FROM p_request_fingerprint
     OR p_raw_result->>'content' IS DISTINCT FROM p_content
     OR p_raw_result->'options' IS DISTINCT FROM p_options
     OR p_raw_result->>'correct_key' IS DISTINCT FROM p_correct_key
     OR p_raw_result->>'solution_md' IS DISTINCT FROM p_solution_md THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: caller projection mismatch' USING ERRCODE = '22023';
  END IF;

  -- Verify and independently construct expected fallback record
  expected := public._generation_fallback_record(
    job, p_source_question_id, p_version_index, p_request_fingerprint, p_raw_result->>'last_error_code'
  );

  IF p_raw_result IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: raw_result does not match verified fallback record' USING ERRCODE = '22023';
  END IF;

  -- Check prior result state transitions
  IF prior.id IS NOT NULL THEN
    IF prior.is_success THEN
      IF prior.result_kind = 'CONFIRMED_SOURCE_FALLBACK' THEN
        -- Active replay verification
        IF prior.snapshot_id IS DISTINCT FROM job.id
           OR prior.raw_result IS DISTINCT FROM expected
           OR prior.seed IS DISTINCT FROM p_seed
           OR prior.question_no IS DISTINCT FROM p_question_no THEN
          RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: fallback record conflict' USING ERRCODE = '23505';
        END IF;

        -- Verify intact pending/current projection and report
        SELECT * INTO q_rec FROM public.version_questions WHERE id = prior.version_question_id;
        IF q_rec.id IS NULL OR NOT q_rec.is_current OR q_rec.status <> 'pending_review'
           OR q_rec.content IS DISTINCT FROM expected->>'content'
           OR q_rec.canonical_options IS DISTINCT FROM expected->'options'
           OR q_rec.canonical_correct_key IS DISTINCT FROM expected->>'correct_key'
           OR q_rec.canonical_solution_md IS DISTINCT FROM expected->>'solution_md'
           OR NOT q_rec.has_warning THEN
          RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: committed fallback projection changed' USING ERRCODE = '23505';
        END IF;

        -- Return replay receipt without modifying state
        RETURN jsonb_build_object(
          'success', true,
          'replayed', true,
          'session_id', s.id,
          'snapshot_id', job.id,
          'version_index', p_version_index,
          'source_question_id', p_source_question_id,
          'version_question_id', prior.version_question_id,
          'result_kind', 'CONFIRMED_SOURCE_FALLBACK',
          'candidate_status', 'pending_review',
          'attempts', 4,
          'error_code', 'GENERATION_RETRIES_EXHAUSTED',
          'source_revision_id', (expected->>'source_revision_id')::uuid,
          'confirmed_source_hash', expected->>'confirmed_source_hash'
        );
      ELSE
        RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: cannot overwrite committed result' USING ERRCODE = '23505';
      END IF;
    ELSE
      -- Prior failure: must be same snapshot and have no candidate ID
      IF prior.snapshot_id IS DISTINCT FROM job.id OR prior.version_question_id IS NOT NULL THEN
        RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: invalid prior failure state' USING ERRCODE = '23505';
      END IF;
    END IF;
  END IF;

  -- Ensure exam_versions row exists
  INSERT INTO public.exam_versions(session_id, version_code)
  VALUES(s.id, (100 + p_version_index)::text)
  ON CONFLICT(session_id, version_code) DO NOTHING;

  SELECT id INTO v_id FROM public.exam_versions
  WHERE session_id = s.id AND version_code = (100 + p_version_index)::text;

  -- Check no current candidate exists on this slot
  IF EXISTS (
    SELECT 1 FROM public.version_questions
    WHERE version_id = v_id AND source_question_id = p_source_question_id AND is_current
  ) THEN
    RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: display-only target requires explicit reconciliation' USING ERRCODE = '23505';
  END IF;

  -- Construct canonical fallback validation report
  val_report := jsonb_build_object(
    'fallback_source', true,
    'reason', 'GENERATION_RETRIES_EXHAUSTED',
    'attempts', 4,
    'validation_status', 'not_validated',
    'source_revision_id', (expected->>'source_revision_id')::uuid,
    'source_fingerprint', expected->>'source_fingerprint',
    'confirmed_source_hash', expected->>'confirmed_source_hash'
  );

  -- Atomic candidate insertion
  INSERT INTO public.version_questions(
    version_id, source_question_id, question_no, content, options, correct_key, solution_md,
    canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
    has_warning, status, is_current, validation_report
  ) VALUES (
    v_id, p_source_question_id, (expected->>'question_no')::int,
    expected->>'content', expected->'options', expected->>'correct_key', expected->>'solution_md',
    (expected->>'question_no')::int, expected->'options', expected->>'correct_key', expected->>'solution_md',
    true, 'pending_review', true, val_report
  ) RETURNING id INTO q_id;

  -- Atomic ledger insertion / replacement of prior failure
  INSERT INTO public.generation_target_results(
    session_id, snapshot_id, job_token, version_index, source_question_id, question_no,
    is_success, error_code, attempts, seed, request_fingerprint, raw_result,
    version_question_id, result_kind, clone_fingerprint
  ) VALUES (
    s.id, job.id, p_job_token, p_version_index, p_source_question_id, (expected->>'question_no')::int,
    true, 'GENERATION_RETRIES_EXHAUSTED', 4, (expected->>'seed')::int, p_request_fingerprint, expected,
    q_id, 'CONFIRMED_SOURCE_FALLBACK', NULL
  ) ON CONFLICT (session_id, version_index, source_question_id) DO UPDATE SET
    snapshot_id = EXCLUDED.snapshot_id,
    job_token = EXCLUDED.job_token,
    question_no = EXCLUDED.question_no,
    is_success = true,
    error_code = 'GENERATION_RETRIES_EXHAUSTED',
    attempts = 4,
    seed = EXCLUDED.seed,
    request_fingerprint = EXCLUDED.request_fingerprint,
    raw_result = EXCLUDED.raw_result,
    version_question_id = EXCLUDED.version_question_id,
    result_kind = 'CONFIRMED_SOURCE_FALLBACK',
    clone_fingerprint = NULL,
    created_at = now();

  UPDATE public.exam_sessions SET updated_at = clock_timestamp() WHERE id = s.id;

  RETURN jsonb_build_object(
    'success', true,
    'replayed', false,
    'session_id', s.id,
    'snapshot_id', job.id,
    'version_index', p_version_index,
    'source_question_id', p_source_question_id,
    'version_question_id', q_id,
    'result_kind', 'CONFIRMED_SOURCE_FALLBACK',
    'candidate_status', 'pending_review',
    'attempts', 4,
    'error_code', 'GENERATION_RETRIES_EXHAUSTED',
    'source_revision_id', (expected->>'source_revision_id')::uuid,
    'confirmed_source_hash', expected->>'confirmed_source_hash'
  );
END;
$$;
REVOKE ALL ON FUNCTION public.persist_generation_result(uuid, uuid, int, uuid, int, boolean, text, int, int, text, jsonb, text, jsonb, text, text, boolean)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.persist_generation_result(uuid, uuid, int, uuid, int, boolean, text, int, int, text, jsonb, text, jsonb, text, text, boolean)
TO service_role;

-- ----------------------------------------------------------------------------
-- 5. Replace _generation_committed (Checkpoint 2)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public._generation_committed(p_session_id uuid, p_snapshot_id uuid)
RETURNS SETOF public.generation_target_results
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
  SELECT r.* FROM public.generation_target_results r
  JOIN public.generation_job_snapshots j ON j.id = r.snapshot_id AND j.session_id = r.session_id
  JOIN public.version_questions q ON q.id = r.version_question_id AND q.is_current
  JOIN public.exam_versions v ON v.id = q.version_id AND v.session_id = r.session_id AND v.version_code = (100 + r.version_index)::text
  CROSS JOIN LATERAL jsonb_array_elements(j.snapshot_payload->'confirmed_sources') src
  CROSS JOIN LATERAL (SELECT CASE r.result_kind
    WHEN 'ORIGINAL_CLONE' THEN
      jsonb_build_object('question_text', r.raw_result->'content', 'options', r.raw_result->'options',
        'correct_key', r.raw_result->'correct_key', 'solution_md', r.raw_result->'solution_md', 'has_warning', false)
    WHEN 'CONFIRMED_SOURCE_FALLBACK' THEN
      jsonb_build_object('question_text', r.raw_result->'content', 'options', r.raw_result->'options',
        'correct_key', r.raw_result->'correct_key', 'solution_md', r.raw_result->'solution_md', 'has_warning', true)
    ELSE r.raw_result->'candidate' END c) payload
  WHERE r.session_id = p_session_id AND r.snapshot_id = p_snapshot_id AND r.is_success
  AND r.version_index BETWEEN 1 AND j.n_versions AND src->>'source_question_id' = r.source_question_id::text
  AND r.question_no = (src->>'question_no')::int AND q.source_question_id = r.source_question_id
  AND q.question_no = r.question_no AND q.canonical_question_no = r.question_no
  AND q.content IS NOT DISTINCT FROM payload.c->>'question_text'
  AND q.options IS NOT DISTINCT FROM payload.c->'options' AND q.canonical_options IS NOT DISTINCT FROM q.options
  AND q.correct_key IS NOT DISTINCT FROM payload.c->>'correct_key' AND q.canonical_correct_key IS NOT DISTINCT FROM q.correct_key
  AND q.solution_md IS NOT DISTINCT FROM payload.c->>'solution_md' AND q.canonical_solution_md IS NOT DISTINCT FROM q.solution_md
  AND q.has_warning IS NOT DISTINCT FROM (payload.c->>'has_warning')::boolean
  AND (
    -- Original Clone branch
    (j.public_modes = '[]'::jsonb AND j.canonical_dimensions = '[]'::jsonb AND r.result_kind = 'ORIGINAL_CLONE'
     AND r.error_code IS NULL AND r.attempts = 0 AND r.clone_fingerprint IS NOT NULL AND r.request_fingerprint IS NULL)
    OR
    -- AI job branch
    ((j.public_modes IS DISTINCT FROM '[]'::jsonb OR j.canonical_dimensions IS DISTINCT FROM '[]'::jsonb) AND (
      (r.result_kind = 'AI_RESULT' AND r.error_code IS NULL AND r.clone_fingerprint IS NULL AND r.request_fingerprint IS NOT NULL)
      OR
      (r.result_kind = 'CONFIRMED_SOURCE_FALLBACK'
       AND r.error_code = 'GENERATION_RETRIES_EXHAUSTED' AND r.attempts = 4
       AND r.clone_fingerprint IS NULL AND r.request_fingerprint IS NOT NULL
       AND q.status = 'pending_review'
       AND q.validation_report = jsonb_build_object(
         'fallback_source', true,
         'reason', 'GENERATION_RETRIES_EXHAUSTED',
         'attempts', 4,
         'validation_status', 'not_validated',
         'source_revision_id', (src->>'source_revision_id')::uuid,
         'source_fingerprint', src->>'source_fingerprint',
         'confirmed_source_hash', j.confirmed_source_hash
       )
       AND r.raw_result = public._generation_fallback_record(j, r.source_question_id, r.version_index, r.request_fingerprint, r.raw_result->>'last_error_code')
      )
    ))
  );
$$;
REVOKE ALL ON FUNCTION public._generation_committed(uuid, uuid) FROM PUBLIC, anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 6. Replace load_generation_completed_results (Checkpoint 2: Historical fallback_receipts)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.load_generation_completed_results(p_session_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  s public.exam_sessions;
  job public.generation_job_snapshots;
  completed jsonb;
  failures jsonb;
  fallback_receipts jsonb;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;

  IF public.current_role() != 'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
    RAISE EXCEPTION 'Access denied' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing resume snapshot' USING ERRCODE = '55006';
  END IF;

  PERFORM public._generation_assert_result_kind(s.id, job.id);

  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'snapshot_id', r.snapshot_id,
    'version_index', r.version_index,
    'source_question_id', r.source_question_id,
    'question_no', r.question_no,
    'is_success', true,
    'seed', r.seed,
    'request_fingerprint', r.request_fingerprint,
    'raw_result', r.raw_result,
    'result_kind', r.result_kind,
    'clone_fingerprint', r.clone_fingerprint
  ) ORDER BY r.version_index, r.question_no), '[]')
  INTO completed
  FROM public._generation_committed(s.id, job.id) r;

  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'snapshot_id', r.snapshot_id,
    'version_index', r.version_index,
    'source_question_id', r.source_question_id,
    'question_no', r.question_no,
    'is_success', false,
    'seed', r.seed,
    'request_fingerprint', r.request_fingerprint,
    'raw_result', r.raw_result,
    'result_kind', r.result_kind,
    'clone_fingerprint', r.clone_fingerprint
  ) ORDER BY r.version_index, r.question_no), '[]')
  INTO failures
  FROM public.generation_target_results r
  WHERE r.session_id = s.id AND r.snapshot_id = job.id AND NOT r.is_success;

  -- Verified historical fallback receipts (immutable ledger records for the frozen snapshot)
  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'snapshot_id', r.snapshot_id,
    'version_index', r.version_index,
    'source_question_id', r.source_question_id,
    'question_no', r.question_no,
    'version_question_id', r.version_question_id,
    'result_kind', r.result_kind,
    'raw_result', r.raw_result
  ) ORDER BY r.version_index, r.question_no), '[]')
  INTO fallback_receipts
  FROM public.generation_target_results r
  JOIN public.version_questions q ON q.id = r.version_question_id
  JOIN public.exam_versions v ON v.id = q.version_id AND v.session_id = s.id AND v.version_code = (100 + r.version_index)::text
  WHERE r.session_id = s.id AND r.snapshot_id = job.id
    AND r.result_kind = 'CONFIRMED_SOURCE_FALLBACK'
    AND r.is_success = true
    AND r.error_code = 'GENERATION_RETRIES_EXHAUSTED'
    AND r.attempts = 4
    AND q.source_question_id = r.source_question_id
    AND r.raw_result = public._generation_fallback_record(job, r.source_question_id, r.version_index, r.request_fingerprint, r.raw_result->>'last_error_code');

  RETURN jsonb_build_object(
    'session_id', s.id,
    'snapshot_id', job.id,
    'context', job.snapshot_payload,
    'completed', completed,
    'failures', failures,
    'fallback_receipts', fallback_receipts,
    'generation_error_code', s.generation_error_code
  );
END;
$$;
REVOKE ALL ON FUNCTION public.load_generation_completed_results(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.load_generation_completed_results(uuid) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 7. Replace get_review_current_snapshot (Checkpoint 2: Authoritative Fallback Origin & Report)
-- ----------------------------------------------------------------------------
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
  -- 1. Owner Authorization: Lock-free owner filtered query
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

  -- Validate confirmed_input presence and object type
  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') cs
    WHERE cs->'confirmed_input' IS NULL OR jsonb_typeof(cs->'confirmed_input') IS DISTINCT FROM 'object'
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: missing or invalid confirmed_input in frozen sources' USING ERRCODE = '22023';
  END IF;

  -- Validate confirmed_input matches persisted revision exactly
  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') cs
    JOIN public.source_artifact_revisions sr
      ON sr.confirmation_id = job.confirmation_id
     AND sr.source_question_id = (cs->>'source_question_id')::uuid
     AND sr.source_revision_id = (cs->>'source_revision_id')::uuid
    WHERE sr.confirmed_input IS DISTINCT FROM cs->'confirmed_input'
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: frozen source revision not bound or confirmed_input mismatched' USING ERRCODE = '22023';
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

    IF src.confirmed_input IS NULL OR jsonb_typeof(src.confirmed_input) IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: missing or invalid confirmed_input in frozen sources' USING ERRCODE = '22023';
    END IF;

    IF src.confirmed_input->>'id' IS NULL
       OR src.confirmed_input->>'question_text' IS NULL
       OR jsonb_typeof(src.confirmed_input->'options') IS DISTINCT FROM 'array'
       OR src.confirmed_input->>'correct_answer' IS NULL THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: malformed confirmed_input fields' USING ERRCODE = '22023';
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

    items_canonical := items_canonical || jsonb_build_array(public._generation_source_item(src.confirmed_input));

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

  IF jsonb_array_length(items_canonical) <> n_sources THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: canonical items count mismatch' USING ERRCODE = '22023';
  END IF;

  computed_hash := encode(sha256(convert_to(public._generation_json(items_canonical), 'UTF8')), 'hex');
  IF computed_hash IS DISTINCT FROM job.confirmed_source_hash THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: confirmed source hash mismatch' USING ERRCODE = '22023';
  END IF;

  expected_slots := job.n_versions * n_sources;
  is_read_only := (s.status IN ('partial_generated', 'failed'));

  -- 6. Invariant candidate checks (fail-closed)
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

  -- 7. Build Version Matrix & Slots
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
        (x->>'question_no')::int AS question_no,
        (x->>'source_revision_id')::uuid AS source_revision_id,
        x->>'source_fingerprint' AS source_fingerprint
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

          -- Look up target generation result by unique slot
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

          -- Fallback evidence validation
          IF v_valid_result AND r_rec.result_kind = 'CONFIRMED_SOURCE_FALLBACK' THEN
            IF r_rec.raw_result IS DISTINCT FROM public._generation_fallback_record(
                 job, src.source_question_id, v_rec.version_index, r_rec.request_fingerprint, r_rec.raw_result->>'last_error_code'
               ) THEN
              RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid fallback generation result evidence' USING ERRCODE = '22023';
            END IF;
            IF q_rec.validation_report IS DISTINCT FROM jsonb_build_object(
                 'fallback_source', true,
                 'reason', 'GENERATION_RETRIES_EXHAUSTED',
                 'attempts', 4,
                 'validation_status', 'not_validated',
                 'source_revision_id', src.source_revision_id,
                 'source_fingerprint', src.source_fingerprint,
                 'confirmed_source_hash', job.confirmed_source_hash
               ) THEN
              RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid fallback validation report' USING ERRCODE = '22023';
            END IF;
            IF q_rec.content IS DISTINCT FROM r_rec.raw_result->>'content'
               OR q_rec.canonical_options IS DISTINCT FROM r_rec.raw_result->'options'
               OR q_rec.canonical_correct_key IS DISTINCT FROM r_rec.raw_result->>'correct_key'
               OR q_rec.canonical_solution_md IS DISTINCT FROM r_rec.raw_result->>'solution_md'
               OR NOT coalesce(q_rec.has_warning, false) THEN
              RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: invalid fallback candidate content' USING ERRCODE = '22023';
            END IF;
          END IF;

          -- Read immutable canonical options
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

          -- Provenance Origin Precedence (with authoritative confirmed_source_fallback)
          IF q_rec.regenerated_from_id IS NOT NULL THEN
            v_origin := 'regenerated';
          ELSIF coalesce(q_rec.is_reverted, false) THEN
            v_origin := 'reverted';
          ELSIF v_valid_result THEN
            IF r_rec.result_kind = 'ORIGINAL_CLONE' THEN
              v_origin := 'original_clone';
            ELSIF r_rec.result_kind = 'AI_RESULT' THEN
              v_origin := 'ai_generated';
            ELSIF r_rec.result_kind = 'CONFIRMED_SOURCE_FALLBACK' THEN
              v_origin := 'confirmed_source_fallback';
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

  -- 8. Authoritative review progress consensus
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

  -- 10. Deterministic Freshness Token
  freshness_token := encode(sha256(convert_to(response_without_token::text, 'UTF8')), 'hex');

  RETURN response_without_token || jsonb_build_object('freshness_token', freshness_token);
END;
$$;

REVOKE ALL ON FUNCTION public.get_review_current_snapshot(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_review_current_snapshot(uuid) TO authenticated;

COMMIT;

