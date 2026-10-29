-- ============================================================================
-- Migration 005 (v6-lite): Generation Job Operations & Persistence RPC [TASK-207b]
-- Architecture:
--   1. Concurrency control with row-level locks (FOR UPDATE)
--   2. Fencing tokens (active_job_id) to eliminate stale worker races
--   3. Hard-cap Gemini quota protection (0-250)
--   4. Idempotent persistence for version questions across network retries
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Schema Setup, Invariants & Constraints
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- Add active_job_id column if not present
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'active_job_id'
  ) THEN
    ALTER TABLE public.exam_sessions ADD COLUMN active_job_id UUID NULL;
  END IF;

  -- Backfill any unexpected NULLs before enforcing NOT NULL
  UPDATE public.exam_sessions SET status = 'draft' WHERE status IS NULL;
  UPDATE public.exam_sessions SET gemini_call_count = 0 WHERE gemini_call_count IS NULL;
  UPDATE public.exam_sessions SET active_job_id = NULL WHERE status <> 'generating' AND active_job_id IS NOT NULL;
  UPDATE public.exam_sessions SET status = 'failed' WHERE status = 'generating' AND active_job_id IS NULL;

  -- Enforce NOT NULL on status and gemini_call_count
  ALTER TABLE public.exam_sessions
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN gemini_call_count SET NOT NULL,
    ALTER COLUMN gemini_call_count SET DEFAULT 0;

  -- Add CHECK constraints
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conrelid = 'public.exam_sessions'::regclass 
      AND conname = 'chk_quota_range'
  ) THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_quota_range CHECK (gemini_call_count BETWEEN 0 AND 250);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conrelid = 'public.exam_sessions'::regclass 
      AND conname = 'chk_generating_has_job'
  ) THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_generating_has_job CHECK (status <> 'generating' OR active_job_id IS NOT NULL);
  END IF;

  -- Ensure unique constraint on exam_versions(session_id, version_code)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conrelid = 'public.exam_versions'::regclass 
      AND conname = 'uq_exam_versions_session_code'
  ) THEN
    ALTER TABLE public.exam_versions
      ADD CONSTRAINT uq_exam_versions_session_code UNIQUE (session_id, version_code);
  END IF;

  -- Ensure partial unique index on version_questions(version_id, source_question_id) for current questions
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes 
    WHERE schemaname = 'public' 
      AND tablename = 'version_questions'
      AND indexname = 'idx_single_current_version_question'
  ) THEN
    CREATE UNIQUE INDEX idx_single_current_version_question
      ON public.version_questions (version_id, source_question_id)
      WHERE is_current = TRUE;
  END IF;
END $$;

-- 2. Drop existing signatures to avoid overload mismatch
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN);
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN, UUID);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT, UUID);
DROP FUNCTION IF EXISTS public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN);
DROP FUNCTION IF EXISTS public.heartbeat_generation_job(UUID, UUID);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT, UUID);
DROP FUNCTION IF EXISTS public.fail_stale_generation_job(UUID);
DROP FUNCTION IF EXISTS public.fail_stale_generation_job(UUID, INT);

-- ----------------------------------------------------------------------------
-- 3. claim_generation_job
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_generation_job(
  p_session_id UUID,
  p_is_retry BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_current_quota INT;
  v_config JSONB;
  v_committed_targets JSONB;
  v_job_id UUID;
BEGIN
  IF p_is_retry IS NULL THEN
    RAISE EXCEPTION 'p_is_retry cannot be NULL' USING ERRCODE = '22023';
  END IF;

  -- 1. Lock session row
  SELECT user_id, status, active_job_id, gemini_call_count
    INTO v_session_user_id, v_session_status, v_active_job_id, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Authorization (caller must be owner or service_role)
  IF public.current_role() != 'service_role'
     AND (v_session_user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id
      USING ERRCODE = '42501';
  END IF;

  -- 3. Concurrency check: Reject if already actively generating
  IF v_session_status = 'generating' THEN
    RAISE EXCEPTION 'Session % is already being generated by job %',
      p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 4. State validation
  IF NOT p_is_retry THEN
    IF v_session_status != 'configured' THEN
      RAISE EXCEPTION 'Cannot claim generation: session must be configured (current: %)',
        v_session_status USING ERRCODE = '22023';
    END IF;
  ELSE
    IF v_session_status NOT IN ('partial_generated', 'failed') THEN
      RAISE EXCEPTION 'Cannot retry generation: session status must be partial_generated or failed (current: %)',
        v_session_status USING ERRCODE = '22023';
    END IF;
  END IF;

  -- 5. Read generation config
  SELECT jsonb_build_object(
    'n_versions', n_versions,
    'active_variation_modes', active_variation_modes,
    'ordering_preferences', ordering_preferences
  ) INTO v_config
  FROM public.generation_configs
  WHERE session_id = p_session_id;

  IF v_config IS NULL THEN
    RAISE EXCEPTION 'Generation config not found for session %', p_session_id
      USING ERRCODE = '55000';
  END IF;

  -- 6. Read committed targets (for incremental retry resume)
  SELECT COALESCE(
    jsonb_agg(jsonb_build_object(
      'version_code', ev.version_code,
      'source_question_id', vq.source_question_id,
      'question_no', vq.question_no
    )),
    '[]'::jsonb
  ) INTO v_committed_targets
  FROM public.exam_versions ev
  JOIN public.version_questions vq ON vq.version_id = ev.id
  WHERE ev.session_id = p_session_id AND vq.is_current = TRUE;

  -- 7. Transition to generating and set active fencing token
  v_job_id := gen_random_uuid();

  UPDATE public.exam_sessions
  SET status = 'generating',
      active_job_id = v_job_id
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'job_id', v_job_id,
    'status', 'generating',
    'starting_quota', v_current_quota,
    'gemini_call_count', v_current_quota,
    'config', v_config,
    'committed_targets', v_committed_targets
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 4. reserve_generation_quota (Restricted to service_role)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.reserve_generation_quota(
  p_session_id UUID,
  p_calls_requested INT,
  p_job_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_current_quota INT;
  v_new_quota INT;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: reserve_generation_quota is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  IF p_calls_requested IS NULL OR p_calls_requested < 1 OR p_calls_requested > 250 THEN
    RAISE EXCEPTION 'p_calls_requested must be between 1 and 250 (got %)', p_calls_requested
      USING ERRCODE = '22023';
  END IF;

  -- 1. Lock session row
  SELECT user_id, status, active_job_id, gemini_call_count
    INTO v_session_user_id, v_session_status, v_active_job_id, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot reserve quota: session % is not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 2. Fencing token check
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 3. Enforce durable hard-cap of 250 calls
  v_new_quota := v_current_quota + p_calls_requested;
  IF v_new_quota > 250 THEN
    RAISE EXCEPTION 'Gemini quota hard-cap exceeded for session %: requested %, current %, cap 250',
      p_session_id, p_calls_requested, v_current_quota USING ERRCODE = '54000';
  END IF;

  UPDATE public.exam_sessions
  SET gemini_call_count = v_new_quota
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'job_id', p_job_token,
    'reserved_calls', p_calls_requested,
    'new_total_calls', v_new_quota,
    'remaining_quota', (250 - v_new_quota)
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 5. persist_version_question (Fenced & Idempotent Question Persistence)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.persist_version_question(
  p_session_id UUID,
  p_job_token UUID,
  p_version_index INT,
  p_source_question_id UUID,
  p_question_no INT,
  p_content TEXT,
  p_options JSONB,
  p_correct_key TEXT,
  p_solution_md TEXT,
  p_has_warning BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_version_id UUID;
  v_question_id UUID;
  v_version_code TEXT;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: persist_version_question is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  IF p_version_index IS NULL OR p_version_index < 1 OR p_version_index > 4 THEN
    RAISE EXCEPTION 'p_version_index must be between 1 and 4 (got %)', p_version_index
      USING ERRCODE = '22023';
  END IF;

  IF p_question_no IS NULL OR p_question_no < 1 THEN
    RAISE EXCEPTION 'p_question_no must be positive (got %)', p_question_no
      USING ERRCODE = '22023';
  END IF;
  v_version_code := (100 + p_version_index)::TEXT;

  -- 1. Lock session row to verify active fencing token
  SELECT status, active_job_id
    INTO v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot persist question: session % is not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 2. Fencing token check: Stale worker is completely blocked from writing rows
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 3. Verify source_question belongs to session
  IF NOT EXISTS (
    SELECT 1 FROM public.source_questions
    WHERE id = p_source_question_id AND session_id = p_session_id
  ) THEN
    RAISE EXCEPTION 'source_question % does not belong to session %',
      p_source_question_id, p_session_id USING ERRCODE = '22023';
  END IF;

  -- 4. Ensure target exam_version exists (idempotent upsert)
  INSERT INTO public.exam_versions (session_id, version_code)
  VALUES (p_session_id, v_version_code)
  ON CONFLICT (session_id, version_code) DO NOTHING;

  SELECT id INTO v_version_id
  FROM public.exam_versions
  WHERE session_id = p_session_id AND version_code = v_version_code;

  -- 5. Atomic upsert into version_questions
  INSERT INTO public.version_questions (
    version_id,
    source_question_id,
    question_no,
    content,
    options,
    correct_key,
    solution_md,
    canonical_question_no,
    canonical_options,
    canonical_correct_key,
    canonical_solution_md,
    has_warning,
    status,
    is_current
  ) VALUES (
    v_version_id,
    p_source_question_id,
    p_question_no,
    p_content,
    p_options,
    p_correct_key,
    p_solution_md,
    p_question_no,
    p_options,
    p_correct_key,
    p_solution_md,
    COALESCE(p_has_warning, FALSE),
    'pending_review',
    TRUE
  )
  ON CONFLICT (version_id, source_question_id) WHERE is_current = TRUE DO UPDATE SET
    question_no = EXCLUDED.question_no,
    content = EXCLUDED.content,
    options = EXCLUDED.options,
    correct_key = EXCLUDED.correct_key,
    solution_md = EXCLUDED.solution_md,
    canonical_question_no = EXCLUDED.canonical_question_no,
    canonical_options = EXCLUDED.canonical_options,
    canonical_correct_key = EXCLUDED.canonical_correct_key,
    canonical_solution_md = EXCLUDED.canonical_solution_md,
    has_warning = EXCLUDED.has_warning,
    updated_at = now()
  RETURNING id INTO v_question_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'question_id', v_question_id,
    'version_id', v_version_id,
    'question_no', p_question_no
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 6. finish_generation_job (Restricted to service_role)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.finish_generation_job(
  p_session_id UUID,
  p_outcome TEXT,
  p_job_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_active_job_id UUID;
BEGIN
  IF p_outcome IS NULL OR p_outcome NOT IN ('generated', 'partial_generated', 'failed') THEN
    RAISE EXCEPTION 'Invalid outcome status: % (must be generated, partial_generated, or failed)', p_outcome
      USING ERRCODE = '22023';
  END IF;

  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: finish_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 1. Lock session row
  SELECT user_id, status, active_job_id
    INTO v_session_user_id, v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot finish: session % not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 2. Fencing token check
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 3. Transition status and release active_job_id
  UPDATE public.exam_sessions
  SET status = p_outcome::public.session_status,
      active_job_id = NULL
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'previous_job_id', v_active_job_id,
    'status', p_outcome
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 7. fail_stale_generation_job (Restricted to service_role)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fail_stale_generation_job(
  p_session_id UUID,
  p_cutoff_seconds INT DEFAULT 720
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_current_status public.session_status;
  v_updated_at TIMESTAMPTZ;
  v_old_job_id UUID;
  v_recovered BOOLEAN := FALSE;
  v_now TIMESTAMPTZ := now();
BEGIN
  IF p_cutoff_seconds IS NULL OR p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds
      USING ERRCODE = '22023';
  END IF;

  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'fail_stale_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 1. Lock session row
  SELECT status, updated_at, active_job_id
    INTO v_current_status, v_updated_at, v_old_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Recover if stale
  IF v_current_status = 'generating'
     AND v_updated_at < (v_now - make_interval(secs => p_cutoff_seconds)) THEN
    UPDATE public.exam_sessions
    SET status = 'failed', active_job_id = NULL
    WHERE id = p_session_id;
    v_recovered := TRUE;
  END IF;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'stale_job_recovered', v_recovered,
    'old_active_job_id', v_old_job_id,
    'current_status', CASE WHEN v_recovered THEN 'failed' ELSE v_current_status::text END
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 8. Least privilege (SEC-04)
-- ----------------------------------------------------------------------------
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN) TO service_role;

REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;
