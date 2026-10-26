-- Migration 003: Atomic Confirm Exam Source RPC & Blueprint Hardening (TASK-205 Fix)
-- Purpose: Atomically lock exam session, prevent race conditions during confirmation,
-- verify session update timestamp/fingerprint, enforce 1-to-1 relationship and schema columns 
-- (is_fallback, extraction_source) on question_blueprints, require SEC-02 acknowledgment,
-- ensure every question has a confirmed blueprint, and safely stamp confirmed_at.

-- 1. Ensure 1-to-1 unique relationship and metadata columns on question_blueprints
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_question_blueprints_source_question'
  ) THEN
    ALTER TABLE public.question_blueprints 
      ADD CONSTRAINT uq_question_blueprints_source_question UNIQUE (source_question_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'question_blueprints' 
      AND column_name = 'is_fallback'
  ) THEN
    ALTER TABLE public.question_blueprints 
      ADD COLUMN is_fallback BOOLEAN NOT NULL DEFAULT FALSE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'question_blueprints' 
      AND column_name = 'extraction_source'
  ) THEN
    ALTER TABLE public.question_blueprints 
      ADD COLUMN extraction_source TEXT NOT NULL DEFAULT 'AI_PIPELINE';
  END IF;
END $$;

-- 2. Drop older 2-argument signature to prevent ambiguous overload
DROP FUNCTION IF EXISTS public.confirm_exam_source(UUID, INT);

-- 3. Create hardened atomic confirm_exam_source RPC
CREATE OR REPLACE FUNCTION public.confirm_exam_source(
  p_session_id UUID,
  p_expected_question_count INT,
  p_acknowledged_security_warnings BOOLEAN DEFAULT FALSE,
  p_expected_updated_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_session_updated_at TIMESTAMPTZ;
  v_role TEXT := COALESCE(
    current_setting('request.jwt.claim.role', true),
    (current_setting('request.jwt.claims', true)::jsonb ->> 'role')
  );
  v_current_count INT;
  v_missing_count INT;
  v_security_warning_count INT;
  v_now TIMESTAMPTZ := now();
  v_bp_count INT := 0;
BEGIN
  -- 1. Row lock session to prevent race conditions (e.g. concurrent confirm or re-ingest)
  SELECT user_id, status, updated_at INTO v_session_user_id, v_session_status, v_session_updated_at
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Strict caller authorization (session owner, service_role, or direct DBA)
  -- Uses session_user to prevent UID-less callers bypassing auth in SECURITY DEFINER
  IF auth.uid() IS NOT NULL THEN
    IF v_session_user_id != auth.uid() THEN
      RAISE EXCEPTION 'Access denied: not session owner' USING ERRCODE = '42501';
    END IF;
  ELSIF v_role = 'service_role' OR session_user IN ('postgres', 'supabase_admin') THEN
    NULL; -- Trusted internal backend service role or direct database administrator
  ELSE
    RAISE EXCEPTION 'Unauthorized: caller must be authenticated or have service role' USING ERRCODE = '42501';
  END IF;

  -- 3. State machine precondition: session must be in 'draft' status
  IF v_session_status != 'draft' THEN
    RAISE EXCEPTION 'Cannot confirm source: session is not in draft status (current: %)', v_session_status USING ERRCODE = '22023';
  END IF;

  -- 4. Concurrency check: session must not have been modified since read
  IF p_expected_updated_at IS NOT NULL AND v_session_updated_at != p_expected_updated_at THEN
    RAISE EXCEPTION 'Cannot confirm source: Session or source questions were modified concurrently (expected updated_at %, got %)', 
      p_expected_updated_at, v_session_updated_at USING ERRCODE = '22023';
  END IF;

  -- 5. Check question count, missing answers, and security warnings
  SELECT 
    COUNT(*), 
    COUNT(*) FILTER (WHERE has_missing_answer = TRUE),
    COUNT(*) FILTER (WHERE has_security_warning = TRUE)
  INTO v_current_count, v_missing_count, v_security_warning_count
  FROM public.source_questions
  WHERE session_id = p_session_id;

  IF v_current_count = 0 THEN
    RAISE EXCEPTION 'Cannot confirm source: session has no source questions' USING ERRCODE = '22023';
  END IF;

  IF p_expected_question_count IS NOT NULL AND v_current_count != p_expected_question_count THEN
    RAISE EXCEPTION 'Question count mismatch: expected %, found %', p_expected_question_count, v_current_count USING ERRCODE = '22023';
  END IF;

  IF v_missing_count > 0 THEN
    RAISE EXCEPTION 'Cannot confirm source: session has % questions with missing answers', v_missing_count USING ERRCODE = '22023';
  END IF;

  IF v_security_warning_count > 0 AND NOT COALESCE(p_acknowledged_security_warnings, FALSE) THEN
    RAISE EXCEPTION 'Cannot confirm source: session has % question(s) with security warnings (SEC-02) that must be explicitly acknowledged', 
      v_security_warning_count USING ERRCODE = '22023';
  END IF;

  -- 6. Lock blueprints: stamp confirmed_at and verify 100% of questions have an active blueprint
  WITH updated_bp AS (
    UPDATE public.question_blueprints
    SET confirmed_at = v_now, updated_at = v_now
    WHERE source_question_id IN (
      SELECT id FROM public.source_questions WHERE session_id = p_session_id
    )
    RETURNING id
  )
  SELECT COUNT(*) INTO v_bp_count FROM updated_bp;

  IF v_bp_count < v_current_count THEN
    RAISE EXCEPTION 'Cannot confirm source: missing blueprints for session questions (expected %, confirmed %)', 
      v_current_count, v_bp_count USING ERRCODE = '22023';
  END IF;

  -- 7. Transition session status to 'blueprinted'
  UPDATE public.exam_sessions
  SET status = 'blueprinted', updated_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'status', 'blueprinted',
    'confirmed_at', v_now,
    'total_questions', v_current_count,
    'total_blueprints', v_bp_count
  );
END;
$$;

-- 4. Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) FROM anon;
GRANT EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) TO authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ) TO service_role;
