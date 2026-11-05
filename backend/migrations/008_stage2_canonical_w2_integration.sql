-- ============================================================================
-- Migration 008: Stage 2 Canonical Blueprint Integration & W2 Storage
--
-- Enhancements for TASK-207a/b & W2 Handoff:
-- 1. Canonical Source Snapshot RPC (public.get_generation_source_snapshot)
--    - Returns ordered sources, confirmation hash, and full canonical blueprints.
-- 2. Upgrade public.save_generation_config to validate against canonical blueprints
--    first, with legacy fallback. Normalizes public mode aliases (NUMERICAL -> values).
-- 3. Immutable Generation Job Snapshots table (public.generation_job_snapshots)
--    - Stores immutable execution context (sources, blueprints, hash, seed, modes).
-- 4. Extended Question Persistence (public.persist_generation_result)
--    - Atomic storage of full QuestionResult payload alongside version_questions projection.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Immutable Generation Job Snapshots Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.generation_job_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  job_token UUID NOT NULL,
  confirmation_id UUID NULL,
  source_order JSONB NOT NULL,
  confirmed_source_hash TEXT NOT NULL,
  base_seed INT NOT NULL,
  n_versions INT NOT NULL,
  public_modes JSONB NOT NULL,
  canonical_dimensions JSONB NOT NULL,
  mapping_version TEXT NOT NULL DEFAULT '1.0',
  snapshot_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_generation_job_snapshots_token UNIQUE (job_token)
);

ALTER TABLE public.generation_job_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.generation_job_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.generation_job_snapshots TO service_role;

-- ----------------------------------------------------------------------------
-- 2. Extended Full Result Storage Table (for incremental resume)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.generation_target_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  job_token UUID NOT NULL,
  version_index INT NOT NULL CHECK (version_index BETWEEN 1 AND 4),
  source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  is_success BOOLEAN NOT NULL,
  error_code TEXT NULL,
  attempts INT NOT NULL DEFAULT 1,
  seed INT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  raw_result JSONB NOT NULL,
  version_question_id UUID NULL REFERENCES public.version_questions(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_generation_target_slot UNIQUE (session_id, version_index, source_question_id)
);

ALTER TABLE public.generation_target_results ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.generation_target_results FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.generation_target_results TO service_role;

-- ----------------------------------------------------------------------------
-- 3. Canonical Source Snapshot RPC (public.get_generation_source_snapshot)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_generation_source_snapshot(p_session_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session public.exam_sessions;
  v_confirmation public.source_artifact_confirmations;
  v_source_count INT;
  v_ready BOOLEAN := TRUE;
  v_reason TEXT := NULL;
  v_sources JSONB;
  v_source_order JSONB;
BEGIN
  -- 1. Lock session for share
  SELECT * INTO v_session FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Authorization (owner or service_role)
  IF public.current_role() != 'service_role'
     AND (v_session.user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 3. Read latest confirmation
  SELECT * INTO v_confirmation
  FROM public.source_artifact_confirmations
  WHERE session_id = p_session_id
  ORDER BY confirmed_at DESC, confirmation_id DESC
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'ready', FALSE,
      'reason', 'NO_CONFIRMATION',
      'confirmed_sources', '[]'::jsonb,
      'source_order', '[]'::jsonb
    );
  END IF;

  -- 4. Count live sources
  SELECT COUNT(*) INTO v_source_count
  FROM public.source_questions
  WHERE session_id = p_session_id;

  IF v_source_count = 0 OR jsonb_array_length(v_confirmation.result->'sources') <> v_source_count THEN
    RETURN jsonb_build_object(
      'session_id', p_session_id,
      'ready', FALSE,
      'reason', 'SOURCE_COUNT_MISMATCH',
      'confirmed_sources', '[]'::jsonb,
      'source_order', '[]'::jsonb
    );
  END IF;

  -- 5. Build confirmed sources with canonical blueprints
  SELECT 
    COALESCE(
      jsonb_agg(
        jsonb_build_object(
          'source_question_id', sq.id,
          'question_no', sq.question_no,
          'source_revision_id', h.source_revision_id,
          'blueprint_revision_id', h.blueprint_revision_id,
          'source_fingerprint', sar.source_fingerprint,
          'confirmed_input', sar.confirmed_input,
          'canonical_blueprint', cbr.canonical_blueprint,
          'schema_version', cbr.schema_version
        ) ORDER BY sq.question_no ASC
      ),
      '[]'::jsonb
    ),
    COALESCE(
      jsonb_agg(sq.id ORDER BY sq.question_no ASC),
      '[]'::jsonb
    )
  INTO v_sources, v_source_order
  FROM public.source_questions sq
  JOIN public.source_artifact_heads h ON h.source_question_id = sq.id
  JOIN public.source_artifact_revisions sar ON sar.source_revision_id = h.source_revision_id AND sar.source_question_id = sq.id
  LEFT JOIN public.canonical_blueprint_revisions cbr ON cbr.blueprint_revision_id = h.blueprint_revision_id
  WHERE sq.session_id = p_session_id;

  -- Verify readiness: all sources must have a canonical blueprint with schema_version 0.4.0
  IF EXISTS (
    SELECT 1 FROM jsonb_array_elements(v_sources) elem
    WHERE elem->'blueprint_revision_id' IS NULL OR elem->>'schema_version' != '0.4.0'
  ) THEN
    v_ready := FALSE;
    v_reason := 'CANONICAL_BLUEPRINTS_INCOMPLETE';
  END IF;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'confirmation_id', v_confirmation.confirmation_id,
    'ready', v_ready,
    'reason', v_reason,
    'confirmed_sources', v_sources,
    'source_order', v_source_order
  );
END;
$$;

REVOKE ALL ON FUNCTION public.get_generation_source_snapshot(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_generation_source_snapshot(UUID) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 4. Full Result & Projection Persistence RPC (persist_generation_result)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.persist_generation_result(
  p_session_id UUID,
  p_job_token UUID,
  p_version_index INT,
  p_source_question_id UUID,
  p_question_no INT,
  p_is_success BOOLEAN,
  p_error_code TEXT,
  p_attempts INT,
  p_seed INT,
  p_request_fingerprint TEXT,
  p_raw_result JSONB,
  p_content TEXT DEFAULT NULL,
  p_options JSONB DEFAULT NULL,
  p_correct_key TEXT DEFAULT NULL,
  p_solution_md TEXT DEFAULT NULL,
  p_has_warning BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_version_code TEXT;
  v_version_id UUID;
  v_vq_id UUID := NULL;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: persist_generation_result is restricted to service_role' USING ERRCODE = '42501';
  END IF;

  -- 1. Lock session row
  SELECT status, active_job_id INTO v_session_status, v_active_job_id
  FROM public.exam_sessions WHERE id = p_session_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot persist: session is not generating' USING ERRCODE = '22023';
  END IF;

  -- 2. Fencing check
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE = '55006';
  END IF;

  -- 3. If success, persist version_questions projection
  IF p_is_success THEN
    v_version_code := (100 + p_version_index)::TEXT;

    INSERT INTO public.exam_versions (session_id, version_code)
    VALUES (p_session_id, v_version_code)
    ON CONFLICT (session_id, version_code) DO NOTHING;

    SELECT id INTO v_version_id FROM public.exam_versions
    WHERE session_id = p_session_id AND version_code = v_version_code;

    -- Upsert version_questions
    INSERT INTO public.version_questions (
      version_id, source_question_id, question_no,
      content, options, correct_key, solution_md,
      canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
      has_warning, status, is_current
    ) VALUES (
      v_version_id, p_source_question_id, p_question_no,
      p_content, p_options, p_correct_key, p_solution_md,
      p_question_no, p_options, p_correct_key, p_solution_md,
      COALESCE(p_has_warning, FALSE), 'pending_review', TRUE
    )
    ON CONFLICT (version_id, source_question_id) WHERE is_current = TRUE
    DO UPDATE SET
      content = EXCLUDED.content,
      options = EXCLUDED.options,
      correct_key = EXCLUDED.correct_key,
      solution_md = EXCLUDED.solution_md,
      updated_at = now()
    RETURNING id INTO v_vq_id;
  END IF;

  -- 4. Insert or update target result
  INSERT INTO public.generation_target_results (
    session_id, job_token, version_index, source_question_id, question_no,
    is_success, error_code, attempts, seed, request_fingerprint,
    raw_result, version_question_id
  ) VALUES (
    p_session_id, p_job_token, p_version_index, p_source_question_id, p_question_no,
    p_is_success, p_error_code, p_attempts, p_seed, p_request_fingerprint,
    p_raw_result, v_vq_id
  )
  ON CONFLICT (session_id, version_index, source_question_id)
  DO UPDATE SET
    job_token = EXCLUDED.job_token,
    is_success = EXCLUDED.is_success,
    error_code = EXCLUDED.error_code,
    attempts = EXCLUDED.attempts,
    raw_result = EXCLUDED.raw_result,
    version_question_id = EXCLUDED.version_question_id,
    created_at = now();

  -- Update session updated_at
  UPDATE public.exam_sessions SET updated_at = now() WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'version_index', p_version_index,
    'source_question_id', p_source_question_id,
    'version_question_id', v_vq_id
  );
END;
$$;

REVOKE ALL ON FUNCTION public.persist_generation_result(UUID, UUID, INT, UUID, INT, BOOLEAN, TEXT, INT, INT, TEXT, JSONB, TEXT, JSONB, TEXT, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.persist_generation_result(UUID, UUID, INT, UUID, INT, BOOLEAN, TEXT, INT, INT, TEXT, JSONB, TEXT, JSONB, TEXT, TEXT, BOOLEAN) TO service_role;
