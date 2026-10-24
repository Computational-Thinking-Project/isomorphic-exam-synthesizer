-- Migration 002: Hardened Atomic Replace Source Questions RPC (TASK-202 Fix)
-- Purpose: Enforce strict auth, draft state machine, and atomic replace in single transaction.
-- Safe and idempotent: can be applied directly to databases with existing data.

CREATE OR REPLACE FUNCTION public.replace_source_questions(
  p_session_id UUID,
  p_questions JSONB
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
  v_q JSONB;
  v_count INT := 0;
BEGIN
  -- 1. Atomic row lock and session lookup
  SELECT user_id, status INTO v_session_user_id, v_session_status
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Strict caller authorization
  IF auth.uid() IS NOT NULL THEN
    IF v_session_user_id != auth.uid() THEN
      RAISE EXCEPTION 'Access denied: not session owner' USING ERRCODE = '42501';
    END IF;
  ELSIF v_role = 'service_role' OR current_user IN ('postgres', 'supabase_admin') THEN
    NULL; -- Trusted internal backend or database admin
  ELSE
    RAISE EXCEPTION 'Unauthorized: caller must be authenticated' USING ERRCODE = '42501';
  END IF;

  -- 3. State machine validation
  IF v_session_status != 'draft' THEN
    RAISE EXCEPTION 'Cannot ingest questions: session is not in draft status' USING ERRCODE = '22023';
  END IF;

  -- 4. Atomic cascade cleanup of existing blueprints and questions
  DELETE FROM public.question_blueprints
  WHERE source_question_id IN (
    SELECT id FROM public.source_questions WHERE session_id = p_session_id
  );

  DELETE FROM public.source_questions
  WHERE session_id = p_session_id;

  -- 5. Bulk insert validated questions
  FOR v_q IN SELECT * FROM jsonb_array_elements(p_questions)
  LOOP
    INSERT INTO public.source_questions (
      session_id,
      question_no,
      raw_content,
      options,
      correct_key,
      solution_md,
      has_missing_answer,
      has_security_warning
    ) VALUES (
      p_session_id,
      (v_q->>'question_no')::INT,
      v_q->>'raw_content',
      v_q->'options',
      v_q->>'correct_key',
      v_q->>'solution_md',
      COALESCE((v_q->>'has_missing_answer')::BOOLEAN, FALSE),
      COALESCE((v_q->>'has_security_warning')::BOOLEAN, FALSE)
    );
    v_count := v_count + 1;
  END LOOP;

  -- 6. Update session metadata timestamp
  UPDATE public.exam_sessions
  SET updated_at = now()
  WHERE id = p_session_id;

  RETURN jsonb_build_object('success', TRUE, 'count', v_count);
END;
$$;

-- Enforce Least Privilege (SEC-04)
REVOKE EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) FROM anon;
GRANT EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION public.replace_source_questions(UUID, JSONB) TO service_role;
