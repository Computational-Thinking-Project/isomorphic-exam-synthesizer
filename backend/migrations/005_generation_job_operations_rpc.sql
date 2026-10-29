-- ============================================================================
-- Migration 005 (v4): Hardened Generation Job Operations RPC [TASK-207b]
-- Prerequisites: PostgreSQL 13+ (built-in gen_random_uuid) or pgcrypto extension.
-- Note: Background workers run under service_role. finish_generation_job is strictly
-- restricted to service_role to prevent unverified client completion.
--
-- Security & Concurrency Enhancements:
--   - NULL-Safe Authorization: current_role() is guaranteed non-NULL ('anon' fallback).
--   - Strict Outcome Validation: p_outcome IS NULL checked before enum cast.
--   - Strict Retry Validation: p_is_retry IS NULL rejected, retry allowed only from
--     'partial_generated' or 'failed'.
--   - Service-Role Only Finish: finish_generation_job revoked from authenticated.
--   - Strict Fencing Token: p_job_token IS DISTINCT FROM v_active_job_id (NULL rejected).
--   - Invariant Check: status = 'generating' => active_job_id NOT NULL (55000).
--   - Anti-race Claim Lock: returns standard 55006 (object_in_use) if already generating.
--   - fail_stale: strictly restricted to service_role, validates p_cutoff_seconds > 0.
-- ============================================================================

-- 1. Ensure active_job_id column exists on exam_sessions
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'active_job_id'
  ) THEN
    ALTER TABLE public.exam_sessions ADD COLUMN active_job_id UUID NULL;
  END IF;
END $$;

-- 2. Drop existing signatures to avoid overload mismatch
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN);
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN, UUID);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT, UUID);
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
BEGIN
  -- 1. Validate p_is_retry explicitly
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

  -- 8. Transition status and set active_job_id (trigger trg_exam_sessions_updated_at updates updated_at)
  UPDATE public.exam_sessions
  SET status = 'generating',
      active_job_id = v_job_id
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
    'gemini_call_count', v_current_quota,
    'config', v_config,
    'committed_targets', v_committed_targets
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 4. reserve_generation_quota
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
BEGIN
  -- 1. Validate input bounds
  IF p_calls_requested IS NULL OR p_calls_requested < 1 OR p_calls_requested > 250 THEN
    RAISE EXCEPTION 'p_calls_requested must be between 1 and 250 (got %)', p_calls_requested
      USING ERRCODE = '22023';
  END IF;

  -- 2. Lock session row
  SELECT user_id, status, gemini_call_count, active_job_id
    INTO v_session_user_id, v_session_status, v_current_quota, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 3. Enforce ownership (NULL-safe)
  IF public.current_role() != 'service_role'
     AND (v_session_user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id
      USING ERRCODE = '42501';
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

  -- 7. Quota cap check
  IF (v_current_quota + p_calls_requested) > 250 THEN
    RAISE EXCEPTION 'Quota exceeded: reserve % (current %, cap 250)',
      p_calls_requested, v_current_quota USING ERRCODE = '22023';
  END IF;

  v_new_quota := v_current_quota + p_calls_requested;

  UPDATE public.exam_sessions
  SET gemini_call_count = v_new_quota
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
-- 5. finish_generation_job (Restricted to service_role)
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
  v_now TIMESTAMPTZ := now();
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

  -- 7. Transition status and clear active_job_id
  UPDATE public.exam_sessions
  SET status = v_target_status,
      active_job_id = NULL
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'previous_job_id', v_active_job_id,
    'status', p_outcome,
    'finished_at', v_now
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 6. fail_stale_generation_job (Restricted to service_role)
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
  -- 1. Validate cutoff seconds
  IF p_cutoff_seconds IS NULL OR p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds
      USING ERRCODE = '22023';
  END IF;

  -- 2. Restrict to service_role (NULL-safe)
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: fail_stale_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 3. Lock session row
  SELECT status, updated_at, active_job_id
    INTO v_current_status, v_updated_at, v_old_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_current_status IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 4. Recover if stale
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
-- 7. Least privilege (SEC-04)
-- ----------------------------------------------------------------------------
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO authenticated, service_role;

-- finish_generation_job is strictly restricted to service_role (Background Worker)
REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) TO service_role;

-- fail_stale_generation_job is strictly restricted to service_role (Recovery cleaner)
REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;
