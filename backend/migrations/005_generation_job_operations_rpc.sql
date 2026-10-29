-- ============================================================================
-- Migration 005 (v5): Hardened Generation Job Operations & Persistence RPC [TASK-207b]
-- Prerequisites: PostgreSQL 13+ (built-in gen_random_uuid) or pgcrypto extension.
-- Note: Background workers run under service_role.
--
-- Security, Fencing & Consistency Hardening (Review v4 Resolution):
--   - P1 FIX: persist_version_question RPC enforces active_job_id fencing token
--     on all data writes into version_questions (prevents zombie worker pollution).
--   - P1 FIX: DB NOT NULL and CHECK constraints on exam_sessions enforce invariants:
--     chk_quota_range, chk_generating_has_job, chk_not_generating_has_no_job.
--   - P2 FIX: last_progress_at heartbeat tracking and heartbeat_generation_job RPC.
--   - P2 FIX: reserve_generation_quota REVOKED from authenticated, restricted to service_role.
--   - P2 FIX: fail_stale_generation_job checks COALESCE(last_progress_at, updated_at).
--   - P3 FIX: Outcome status and p_is_retry strictly validated against NULL.
--   - P3 FIX: Response returns true committed finished_at timestamp from RETURNING updated_at.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Schema Invariants & Column Setup on exam_sessions
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- Add active_job_id if not present
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'active_job_id'
  ) THEN
    ALTER TABLE public.exam_sessions ADD COLUMN active_job_id UUID NULL;
  END IF;

  -- Add last_progress_at heartbeat column if not present
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'last_progress_at'
  ) THEN
    ALTER TABLE public.exam_sessions ADD COLUMN last_progress_at TIMESTAMPTZ NULL;
  END IF;

  -- Backfill any unexpected NULLs before setting NOT NULL
  UPDATE public.exam_sessions SET gemini_call_count = 0 WHERE gemini_call_count IS NULL;
  UPDATE public.exam_sessions SET active_job_id = NULL WHERE status <> 'generating' AND active_job_id IS NOT NULL;

  -- Enforce NOT NULL on status and gemini_call_count
  ALTER TABLE public.exam_sessions
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN gemini_call_count SET NOT NULL,
    ALTER COLUMN gemini_call_count SET DEFAULT 0;

  -- Add CHECK constraints if not exist
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_quota_range') THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_quota_range CHECK (gemini_call_count BETWEEN 0 AND 250);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_generating_has_job') THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_generating_has_job CHECK (status <> 'generating' OR active_job_id IS NOT NULL);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_not_generating_has_no_job') THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_not_generating_has_no_job CHECK (status = 'generating' OR active_job_id IS NULL);
  END IF;
END $$;

-- 2. Drop existing signatures to avoid overload mismatch
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN);
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN, UUID);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT, UUID);
DROP FUNCTION IF EXISTS public.heartbeat_generation_job(UUID, UUID);
DROP FUNCTION IF EXISTS public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT, UUID);
DROP FUNCTION IF EXISTS public.fail_stale_generation_job(UUID, INT);

-- ----------------------------------------------------------------------------
-- 3. claim_generation_job
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_generation_job(
  p_session_id UUID,
  p_is_retry BOOLEAN DEFAULT FALSE,
  p_job_token UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_current_quota INT;
  v_config JSONB;
  v_committed_targets JSONB;
  v_job_id UUID := COALESCE(p_job_token, gen_random_uuid());
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Validate p_is_retry explicitly against NULL
  IF p_is_retry IS NULL THEN
    RAISE EXCEPTION 'p_is_retry cannot be NULL' USING ERRCODE = '22023';
  END IF;

  -- 2. Lock session row
  SELECT user_id, status, gemini_call_count
    INTO v_session_user_id, v_session_status, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 3. Enforce ownership (NULL-safe: current_role() is guaranteed non-NULL)
  IF public.current_role() != 'service_role'
     AND (v_session_user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id
      USING ERRCODE = '42501';
  END IF;

  -- 4. Anti-concurrency check: 55006 (object_in_use)
  IF v_session_status = 'generating' THEN
    RAISE EXCEPTION 'Session % is already generating', p_session_id USING ERRCODE = '55006';
  END IF;

  -- 5. State machine transition check
  IF NOT p_is_retry THEN
    IF v_session_status != 'configured' THEN
      RAISE EXCEPTION 'Cannot start generation: session must be configured (current: %)',
        v_session_status USING ERRCODE = '22023';
    END IF;
  ELSE
    IF v_session_status NOT IN ('partial_generated', 'failed') THEN
      RAISE EXCEPTION 'Cannot retry from status % (only partial_generated or failed)',
        v_session_status USING ERRCODE = '22023';
    END IF;
  END IF;

  -- 6. Config must exist (fail-closed)
  SELECT row_to_json(c)::jsonb INTO v_config
  FROM public.generation_configs c
  WHERE c.session_id = p_session_id;

  IF v_config IS NULL THEN
    RAISE EXCEPTION 'Session % has no saved generation config', p_session_id
      USING ERRCODE = '22023';
  END IF;

  -- 7. Quota ceiling check (250 calls limit)
  IF v_current_quota >= 250 THEN
    RAISE EXCEPTION 'Quota exceeded: % of 250 calls already used', v_current_quota
      USING ERRCODE = '22023';
  END IF;

  -- 8. Transition status, record active_job_id fencing token, and init last_progress_at
  UPDATE public.exam_sessions
  SET status = 'generating',
      active_job_id = v_job_id,
      last_progress_at = v_now
  WHERE id = p_session_id;

  -- 9. Fetch committed targets for incremental resume
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'version_id', vq.version_id,
    'source_question_id', vq.source_question_id,
    'question_no', vq.question_no
  )), '[]'::jsonb) INTO v_committed_targets
  FROM public.version_questions vq
  JOIN public.exam_versions ev ON vq.version_id = ev.id
  WHERE ev.session_id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
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
  p_calls_requested INT DEFAULT 1,
  p_job_token UUID DEFAULT NULL
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
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Validate input bounds
  IF p_calls_requested IS NULL OR p_calls_requested < 1 OR p_calls_requested > 250 THEN
    RAISE EXCEPTION 'p_calls_requested must be between 1 and 250 (got %)', p_calls_requested
      USING ERRCODE = '22023';
  END IF;

  -- 2. Restrict to service_role (background worker)
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: reserve_generation_quota is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 3. Lock session row
  SELECT user_id, status, gemini_call_count, active_job_id
    INTO v_session_user_id, v_session_status, v_current_quota, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 4. State validation: only generating session can reserve quota
  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot reserve quota: session % not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 5. Invariant check: status = 'generating' => active_job_id NOT NULL
  IF v_active_job_id IS NULL THEN
    RAISE EXCEPTION 'Invariant violated: session % is generating but has no active_job_id',
      p_session_id USING ERRCODE = '55000';
  END IF;

  -- 6. Fencing token check: NULL cannot bypass (IS DISTINCT FROM)
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: supplied token does not match active job % for session %',
      v_active_job_id, p_session_id USING ERRCODE = '55006';
  END IF;

  -- 7. Quota ceiling check
  IF (v_current_quota + p_calls_requested) > 250 THEN
    RAISE EXCEPTION 'Quota exceeded: reserve % (current %, cap 250)',
      p_calls_requested, v_current_quota USING ERRCODE = '22023';
  END IF;

  v_new_quota := v_current_quota + p_calls_requested;

  UPDATE public.exam_sessions
  SET gemini_call_count = v_new_quota,
      last_progress_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'gemini_call_count', v_new_quota,
    'previous_quota', v_current_quota,
    'reserved_this_call', p_calls_requested,
    'remaining_quota', (250 - v_new_quota)
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 5. persist_version_question (Fencing Token Protection on Data Writes)
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
  v_version_code TEXT := (100 + p_version_index)::TEXT;
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Restrict to service_role
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: persist_version_question is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 2. Lock session row to verify active fencing token
  SELECT status, active_job_id
    INTO v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_status IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot persist question: session % is not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- Critical Fencing Token Check: Stale worker is completely blocked from writing rows!
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 3. Ensure target exam_version exists
  SELECT id INTO v_version_id
  FROM public.exam_versions
  WHERE session_id = p_session_id AND version_code = v_version_code;

  IF v_version_id IS NULL THEN
    INSERT INTO public.exam_versions (session_id, version_code, created_at)
    VALUES (p_session_id, v_version_code, v_now)
    RETURNING id INTO v_version_id;
  END IF;

  -- 4. Upsert row into version_questions
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
    p_has_warning,
    'pending_review',
    TRUE
  )
  RETURNING id INTO v_question_id;

  -- 5. Touch last_progress_at to prevent false-positive stale timeout
  UPDATE public.exam_sessions
  SET last_progress_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'question_id', v_question_id,
    'version_id', v_version_id,
    'question_no', p_question_no
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 6. heartbeat_generation_job (Worker Liveness Reporting)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.heartbeat_generation_job(
  p_session_id UUID,
  p_job_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_now TIMESTAMPTZ := now();
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: heartbeat_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  SELECT status, active_job_id
    INTO v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot heartbeat: session % is not generating', p_session_id USING ERRCODE = '22023';
  END IF;

  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session %',
      p_job_token, p_session_id USING ERRCODE = '55006';
  END IF;

  UPDATE public.exam_sessions
  SET last_progress_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'heartbeat_at', v_now
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 7. finish_generation_job (Restricted to service_role)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.finish_generation_job(
  p_session_id UUID,
  p_outcome TEXT,
  p_job_token UUID DEFAULT NULL
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
  v_target_status public.session_status;
  v_finished_at TIMESTAMPTZ;
BEGIN
  -- 1. Validate outcome (strict NULL check before enum cast)
  IF p_outcome IS NULL OR p_outcome NOT IN ('generated', 'partial_generated', 'failed') THEN
    RAISE EXCEPTION 'Invalid outcome status: must be generated, partial_generated, or failed (got %)', 
      p_outcome USING ERRCODE = '22023';
  END IF;
  v_target_status := p_outcome::public.session_status;

  -- 2. Restrict execution to service_role (background worker)
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: finish_generation_job is strictly restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 3. Lock session row
  SELECT user_id, status, active_job_id
    INTO v_session_user_id, v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 4. State validation: only generating session can finish
  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot finish: session % not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 5. Invariant check: status = 'generating' => active_job_id NOT NULL
  IF v_active_job_id IS NULL THEN
    RAISE EXCEPTION 'Invariant violated: session % generating but active_job_id is NULL',
      p_session_id USING ERRCODE = '55000';
  END IF;

  -- 6. Fencing token check: NULL cannot bypass (IS DISTINCT FROM)
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 7. Transition status and clear active_job_id (RETURNING true updated_at)
  UPDATE public.exam_sessions
  SET status = v_target_status,
      active_job_id = NULL
  WHERE id = p_session_id
  RETURNING updated_at INTO v_finished_at;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'previous_job_id', v_active_job_id,
    'status', p_outcome,
    'finished_at', v_finished_at
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 8. fail_stale_generation_job (Restricted to service_role)
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
  v_last_progress TIMESTAMPTZ;
  v_effective_activity TIMESTAMPTZ;
  v_old_job_id UUID;
  v_recovered BOOLEAN := FALSE;
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Validate cutoff seconds
  IF p_cutoff_seconds IS NULL OR p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds
      USING ERRCODE = '22023';
  END IF;

  -- 2. Restrict to service_role (NULL-safe)
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'fail_stale_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 3. Lock session row
  SELECT status, updated_at, last_progress_at, active_job_id
    INTO v_current_status, v_updated_at, v_last_progress, v_old_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_current_status IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- Effective activity timestamp: prefers last_progress_at, falls back to updated_at
  v_effective_activity := COALESCE(v_last_progress, v_updated_at);

  -- 4. Recover if stale
  IF v_current_status = 'generating'
     AND v_effective_activity < (v_now - make_interval(secs => p_cutoff_seconds)) THEN
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
-- 9. Least privilege (SEC-04)
-- ----------------------------------------------------------------------------
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) TO authenticated, service_role;

-- reserve, persist, heartbeat, finish, and fail_stale are strictly for service_role
REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN) TO service_role;

REVOKE EXECUTE ON FUNCTION public.heartbeat_generation_job(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.heartbeat_generation_job(UUID, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;
