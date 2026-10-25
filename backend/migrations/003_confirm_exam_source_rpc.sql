-- Migration 003: Atomic Confirm Exam Source RPC & Blueprint Unique Constraint (TASK-205 Fix)
-- Purpose: Atomically lock exam session, prevent race conditions during confirmation, 
-- enforce 1-to-1 relationship on question_blueprints, and stamp confirmed_at.

-- 1. Ensure 1-to-1 unique relationship on question_blueprints
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_question_blueprints_source_question'
  ) THEN
    ALTER TABLE public.question_blueprints 
      ADD CONSTRAINT uq_question_blueprints_source_question UNIQUE (source_question_id);
  END IF;
END $$;

-- 2. Create or replace atomic confirm_exam_source RPC
CREATE OR REPLACE FUNCTION public.confirm_exam_source(
  p_session_id UUID,
  p_expected_question_count INT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_role TEXT := COALESCE(
    current_setting('request.jwt.claim.role', true),
    (current_setting('request.jwt.claims', true)::jsonb ->> 'role')
  );
  v_current_count INT;
  v_missing_count INT;
  v_now TIMESTAMPTZ := now();
  v_bp_count INT := 0;
BEGIN
  -- 1. Row lock session to prevent race conditions (e.g. concurrent confirm or re-ingest)
  SELECT user_id, status INTO v_session_user_id, v_session_status
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Strict caller authorization (session owner, service_role, or superadmin)
  IF auth.uid() IS NOT NULL THEN
    IF v_session_user_id != auth.uid() THEN
      RAISE EXCEPTION 'Access denied: not session owner' USING ERRCODE = '42501';
    END IF;
  ELSIF v_role = 'service_role' OR current_user IN ('postgres', 'supabase_admin') THEN
    NULL;
  ELSE
    RAISE EXCEPTION 'Unauthorized: caller must be authenticated' USING ERRCODE = '42501';
  END IF;

  -- 3. State machine precondition: session must be in 'draft' status
  IF v_session_status != 'draft' THEN
    RAISE EXCEPTION 'Cannot confirm source: session is not in draft status (current: %)', v_session_status USING ERRCODE = '22023';
  END IF;

  -- 4. Check question count and integrity
  SELECT COUNT(*), COUNT(*) FILTER (WHERE has_missing_answer = TRUE)
  INTO v_current_count, v_missing_count
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

  -- 5. Lock blueprints: stamp confirmed_at
  WITH updated_bp AS (
    UPDATE public.question_blueprints
    SET confirmed_at = v_now, updated_at = v_now
    WHERE source_question_id IN (
      SELECT id FROM public.source_questions WHERE session_id = p_session_id
    )
    RETURNING id
  )
  SELECT COUNT(*) INTO v_bp_count FROM updated_bp;

  -- 6. Transition session status to 'blueprinted'
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

-- 3. Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT) FROM anon;
GRANT EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_exam_source(UUID, INT) TO service_role;
