-- Migration 005: Atomic Generation Job Durable Operations & Quota RPC [TASK-207b]
-- Hardened Version:
-- 1. Adds active_job_id column to exam_sessions for fencing tokens.
-- 2. claim_generation_job: atomic lock, ownership, config validation, 55006 for concurrent runs, generates job_id fencing token.
-- 3. reserve_generation_quota: strict ownership check, validates p_calls_requested (1-250), state check ('generating'), fencing token verification.
-- 4. finish_generation_job: strict ownership check, state check ('generating'), row lock, fencing token verification, clears active_job_id.
-- 5. fail_stale_generation_job: restricted to service_role, validates p_cutoff_seconds > 0, clears active_job_id upon recovery.

-- 1. Ensure active_job_id column on exam_sessions for fencing tokens
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'active_job_id'
  ) THEN
    ALTER TABLE public.exam_sessions 
      ADD COLUMN active_job_id UUID NULL;
  END IF;
END $$;

-- 2. Drop existing function signatures to avoid overload mismatch
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN);
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN, UUID);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT, UUID);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT, UUID);
DROP FUNCTION IF EXISTS public.fail_stale_generation_job(UUID, INT);

-- ------------------------------------------------------------------------------
-- 3. RPC: claim_generation_job
-- ------------------------------------------------------------------------------
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
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END
  );
  v_now TIMESTAMPTZ := now();
  v_config JSONB;
  v_committed_targets JSONB;
  v_job_id UUID := COALESCE(p_job_token, gen_random_uuid());
BEGIN
  -- 1. Lock session row
  SELECT user_id, status, gemini_call_count INTO v_session_user_id, v_session_status, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Enforce ownership (authenticated user or service_role)
  IF v_role != 'service_role' AND (v_session_user_id != auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 3. Check duplicate active job: 55006 (object_in_use)
  IF v_session_status = 'generating' THEN
    RAISE EXCEPTION 'Session % is already generating', p_session_id USING ERRCODE = '55006';
  END IF;

  -- 4. Enforce valid state machine transition
  IF p_is_retry = FALSE THEN
    IF v_session_status != 'configured' THEN
      RAISE EXCEPTION 'Cannot start generation: session status must be configured (current: %)', 
        v_session_status USING ERRCODE = '22023';
    END IF;
  ELSE
    IF v_session_status NOT IN ('configured', 'partial_generated', 'failed') THEN
      RAISE EXCEPTION 'Cannot retry generation from status %', v_session_status USING ERRCODE = '22023';
    END IF;
  END IF;

  -- 5. Validate configuration exists
  SELECT row_to_json(c)::jsonb INTO v_config
  FROM public.generation_configs c
  WHERE c.session_id = p_session_id;

  IF v_config IS NULL THEN
    RAISE EXCEPTION 'Cannot start generation: session % has no saved generation config', 
      p_session_id USING ERRCODE = '22023';
  END IF;

  -- 6. Check quota limit (cap: 250)
  IF v_current_quota >= 250 THEN
    RAISE EXCEPTION 'Quota exceeded: session has already utilized % of 250 Gemini calls', 
      v_current_quota USING ERRCODE = '22023';
  END IF;

  -- 7. Transition status to 'generating' and record active_job_id fencing token
  UPDATE public.exam_sessions
  SET status = 'generating', active_job_id = v_job_id, updated_at = v_now
  WHERE id = p_session_id;

  -- 8. Fetch already committed targets (for incremental retry resume)
  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'version_id', vq.version_id,
      'source_question_id', vq.source_question_id,
      'question_no', vq.question_no
    )
  ), '[]'::jsonb) INTO v_committed_targets
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

-- ------------------------------------------------------------------------------
-- 4. RPC: reserve_generation_quota
-- ------------------------------------------------------------------------------
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
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END
  );
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Validate p_calls_requested upper & lower bounds
  IF p_calls_requested < 1 OR p_calls_requested > 250 THEN
    RAISE EXCEPTION 'p_calls_requested must be between 1 and 250 (got %)', p_calls_requested USING ERRCODE = '22023';
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

  -- 3. Enforce ownership
  IF v_role != 'service_role' AND (v_session_user_id != auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 4. Enforce state: only active 'generating' session can reserve quota
  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot reserve quota: session % is not generating (current status: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 5. Validate fencing token (if active job is set)
  IF p_job_token IS NOT NULL AND v_active_job_id IS NOT NULL AND p_job_token != v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session %',
      p_job_token, p_session_id USING ERRCODE = '55006';
  END IF;

  -- 6. Enforce quota ceiling
  IF (v_current_quota + p_calls_requested) > 250 THEN
    RAISE EXCEPTION 'Quota exceeded: cannot reserve % calls (current %, cap 250)', 
      p_calls_requested, v_current_quota USING ERRCODE = '22023';
  END IF;

  v_new_quota := v_current_quota + p_calls_requested;

  UPDATE public.exam_sessions
  SET gemini_call_count = v_new_quota, updated_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'gemini_call_count', v_new_quota,
    'remaining_quota', (250 - v_new_quota)
  );
END;
$$;

-- ------------------------------------------------------------------------------
-- 5. RPC: finish_generation_job
-- ------------------------------------------------------------------------------
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
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END
  );
  v_now TIMESTAMPTZ := now();
  v_target_status public.session_status;
BEGIN
  -- 1. Validate outcome status enum
  IF p_outcome NOT IN ('generated', 'partial_generated', 'failed') THEN
    RAISE EXCEPTION 'Invalid outcome status: %', p_outcome USING ERRCODE = '22023';
  END IF;

  v_target_status := p_outcome::public.session_status;

  -- 2. Lock session row
  SELECT user_id, status, active_job_id
  INTO v_session_user_id, v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 3. Enforce ownership
  IF v_role != 'service_role' AND (v_session_user_id != auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id USING ERRCODE = '42501';
  END IF;

  -- 4. Enforce state machine: only 'generating' sessions can be finished
  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot finish job: session % is not in generating status (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 5. Validate fencing token (prevents stale worker overriding recovered session)
  IF p_job_token IS NOT NULL AND v_active_job_id IS NOT NULL AND p_job_token != v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session %',
      p_job_token, p_session_id USING ERRCODE = '55006';
  END IF;

  -- 6. Transition status and clear active_job_id
  UPDATE public.exam_sessions
  SET status = v_target_status, active_job_id = NULL, updated_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'status', p_outcome,
    'finished_at', v_now
  );
END;
$$;

-- ------------------------------------------------------------------------------
-- 6. RPC: fail_stale_generation_job (Restricted to service_role)
-- ------------------------------------------------------------------------------
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
  v_now TIMESTAMPTZ := now();
  v_recovered BOOLEAN := FALSE;
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
      THEN NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'role'), '')
      ELSE NULL 
    END
  );
BEGIN
  -- 1. Strictly validate cutoff seconds > 0
  IF p_cutoff_seconds <= 0 THEN
    RAISE EXCEPTION 'p_cutoff_seconds must be positive (got %)', p_cutoff_seconds USING ERRCODE = '22023';
  END IF;

  -- 2. Restrict to service_role (background administrative cleaner)
  IF v_role != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: fail_stale_generation_job is restricted to service_role' USING ERRCODE = '42501';
  END IF;

  SELECT status, updated_at INTO v_current_status, v_updated_at
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_current_status IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_current_status = 'generating' AND (v_updated_at < (v_now - (p_cutoff_seconds || ' seconds')::interval)) THEN
    UPDATE public.exam_sessions
    SET status = 'failed', active_job_id = NULL, updated_at = v_now
    WHERE id = p_session_id;
    v_recovered := TRUE;
  END IF;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'stale_job_recovered', v_recovered,
    'current_status', CASE WHEN v_recovered THEN 'failed' ELSE v_current_status::text END
  );
END;
$$;

-- ------------------------------------------------------------------------------
-- 7. Enforce Least Privilege (SEC-04)
-- ------------------------------------------------------------------------------
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) FROM anon;
GRANT EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM anon;
GRANT EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) FROM anon;
GRANT EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) TO service_role;

-- fail_stale_generation_job is strictly restricted to service_role (Recovery cleaner)
REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;
