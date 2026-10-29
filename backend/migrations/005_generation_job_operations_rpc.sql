-- Migration 005: Atomic Generation Job Durable Operations & Quota RPC [TASK-207b]
-- Purpose: Implement durable job operations for background worker orchestration:
-- 1. claim_generation_job: atomically lock session, verify ownership/configured state, check & fence duplicate runs.
-- 2. reserve_generation_quota: atomically verify and increment session Gemini call quota up to 250 limit.
-- 3. finish_generation_job: atomically transition status to 'generated' or 'partial_generated' or 'failed'.
-- 4. fail_stale_generation_job: recover from interrupted/abandoned worker executions (> 12 minutes).

-- 1. Create claim_generation_job RPC
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

  -- 3. Check duplicate active job
  IF v_session_status = 'generating' THEN
    RAISE EXCEPTION 'Session % is already generating', p_session_id USING ERRCODE = '23505';
  END IF;

  -- 4. Enforce valid state for generation
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

  -- 5. Check quota limit
  IF v_current_quota >= 250 THEN
    RAISE EXCEPTION 'Quota exceeded: session has already utilized % of 250 Gemini calls', 
      v_current_quota USING ERRCODE = '22023';
  END IF;

  -- 6. Transition status to generating
  UPDATE public.exam_sessions
  SET status = 'generating', updated_at = v_now
  WHERE id = p_session_id;

  -- 7. Fetch active configuration
  SELECT row_to_json(c)::jsonb INTO v_config
  FROM public.generation_configs c
  WHERE c.session_id = p_session_id;

  -- 8. Fetch already committed targets (if retry)
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
    'status', 'generating',
    'gemini_call_count', v_current_quota,
    'config', v_config,
    'committed_targets', v_committed_targets
  );
END;
$$;

-- 2. Create reserve_generation_quota RPC
CREATE OR REPLACE FUNCTION public.reserve_generation_quota(
  p_session_id UUID,
  p_calls_requested INT DEFAULT 1
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_current_quota INT;
  v_new_quota INT;
  v_now TIMESTAMPTZ := now();
BEGIN
  SELECT gemini_call_count INTO v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_current_quota IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

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

-- 3. Create finish_generation_job RPC
CREATE OR REPLACE FUNCTION public.finish_generation_job(
  p_session_id UUID,
  p_outcome TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_target_status public.session_status;
BEGIN
  IF p_outcome NOT IN ('generated', 'partial_generated', 'failed') THEN
    RAISE EXCEPTION 'Invalid outcome status: %', p_outcome USING ERRCODE = '22023';
  END IF;

  v_target_status := p_outcome::public.session_status;

  UPDATE public.exam_sessions
  SET status = v_target_status, updated_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'status', p_outcome,
    'finished_at', v_now
  );
END;
$$;

-- 4. Create fail_stale_generation_job RPC
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
BEGIN
  SELECT status, updated_at INTO v_current_status, v_updated_at
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_current_status = 'generating' AND (v_updated_at < (v_now - (p_cutoff_seconds || ' seconds')::interval)) THEN
    UPDATE public.exam_sessions
    SET status = 'failed', updated_at = v_now
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

-- 5. Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN) FROM anon;
GRANT EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN) TO authenticated;
GRANT EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN) TO service_role;

REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT) FROM anon;
GRANT EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT) TO service_role;

REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT) FROM anon;
GRANT EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT) TO service_role;

REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM anon;
GRANT EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;
