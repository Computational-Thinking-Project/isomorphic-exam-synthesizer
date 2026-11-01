-- Migration 007: Finalize & Content Lock Stored Procedure RPC (TASK-305)
-- Purpose: Atomically lock exam session, verify all Stage 3 invariants,
-- enforce Cartesian version x question completeness, transition session status to 'approved',
-- stamp approved_at, and record APPROVE_ALL audit log in a single ACID transaction.

-- Drop previous overload if exists
DROP FUNCTION IF EXISTS public.finalize_approve_session(UUID, UUID, TIMESTAMPTZ);
DROP FUNCTION IF EXISTS public.finalize_approve_session(UUID, TIMESTAMPTZ);

CREATE OR REPLACE FUNCTION public.finalize_approve_session(
  p_session_id UUID,
  p_user_id UUID DEFAULT NULL,
  p_expected_updated_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session RECORD;
  v_caller_id UUID;
  v_jwt_sub TEXT := NULLIF(current_setting('request.jwt.claim.sub', true), '');
  v_role TEXT := COALESCE(
    NULLIF(current_setting('request.jwt.claim.role', true), ''),
    CASE 
      WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL 
           AND (current_setting('request.jwt.claims', true)::jsonb ? 'role')
      THEN current_setting('request.jwt.claims', true)::jsonb->>'role'
      ELSE ''
    END
  );
  v_total_versions INT := 0;
  v_finalized_versions INT := 0;
  v_regenerating_count INT := 0;
  v_total_current_q INT := 0;
  v_approved_current_q INT := 0;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  -- 1. Resolve authenticated caller ID
  IF v_jwt_sub IS NOT NULL AND v_jwt_sub ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
    v_caller_id := v_jwt_sub::UUID;
  ELSE
    v_caller_id := p_user_id;
  END IF;

  -- 2. Lock root tuple on exam_sessions exclusively
  SELECT id, user_id, status, approved_at, updated_at
  INTO v_session
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ERR_SESSION_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  -- 3. Verify user ownership authorization (unless service_role)
  IF v_caller_id IS NOT NULL 
     AND v_session.user_id IS DISTINCT FROM v_caller_id 
     AND v_role != 'service_role' THEN
    RAISE EXCEPTION 'ERR_UNAUTHORIZED' USING ERRCODE = '42501';
  END IF;

  -- 4. Idempotency Guard: if already approved, return stored timestamp without mutation
  IF v_session.status = 'approved' THEN
    RETURN jsonb_build_object(
      'session_id', v_session.id,
      'status', 'approved',
      'approved_at', v_session.approved_at,
      'updated_at', v_session.updated_at,
      'message', 'Phiên đề đã được phê duyệt trước đó'
    );
  END IF;

  -- 5. Session State Machine Guard: only 'reviewed' or 'generated' allowed
  IF v_session.status NOT IN ('reviewed', 'generated') THEN
    RAISE EXCEPTION 'ERR_INVALID_SESSION_STATE' USING ERRCODE = 'P0001';
  END IF;

  -- 6. Optimistic Locking Guard: detect concurrent mutations
  IF p_expected_updated_at IS NOT NULL 
     AND v_session.updated_at IS DISTINCT FROM p_expected_updated_at THEN
    RAISE EXCEPTION 'ERR_INVALID_SESSION_STATE' USING ERRCODE = 'P0001';
  END IF;

  -- 7. Exam Versions Invariant Guard (TASK-303):
  -- Total versions must be > 0 and 100% of versions must have is_finalized = TRUE
  SELECT count(*), count(*) FILTER (WHERE is_finalized IS TRUE)
  INTO v_total_versions, v_finalized_versions
  FROM public.exam_versions
  WHERE session_id = p_session_id;

  IF v_total_versions = 0 OR v_finalized_versions < v_total_versions THEN
    RAISE EXCEPTION 'ERR_VERSIONS_NOT_FINALIZED' USING ERRCODE = 'P0001';
  END IF;

  -- 8. Questions Invariant Guard (TASK-301):
  -- 8a. No question may be actively regenerating
  SELECT count(*)
  INTO v_regenerating_count
  FROM public.version_questions q
  JOIN public.exam_versions v ON v.id = q.version_id
  WHERE v.session_id = p_session_id 
    AND q.is_current IS TRUE 
    AND q.status = 'regenerating';

  IF v_regenerating_count > 0 THEN
    RAISE EXCEPTION 'ERR_QUESTION_REGENERATING' USING ERRCODE = 'P0001';
  END IF;

  -- 8b. 100% of active questions must have status = 'approved'
  SELECT count(*), count(*) FILTER (WHERE q.status = 'approved')
  INTO v_total_current_q, v_approved_current_q
  FROM public.version_questions q
  JOIN public.exam_versions v ON v.id = q.version_id
  WHERE v.session_id = p_session_id 
    AND q.is_current IS TRUE;

  IF v_total_current_q = 0 OR v_approved_current_q < v_total_current_q THEN
    RAISE EXCEPTION 'ERR_NOT_ALL_QUESTIONS_APPROVED' USING ERRCODE = 'P0001';
  END IF;

  -- 8c. Cartesian Completeness Guard (F02):
  -- Every (version, source_question) pair must have an active approved variant
  IF EXISTS (
    SELECT 1
    FROM public.exam_versions v
    CROSS JOIN public.source_questions s
    WHERE v.session_id = p_session_id 
      AND s.session_id = p_session_id
      AND NOT EXISTS (
        SELECT 1
        FROM public.version_questions q
        WHERE q.version_id = v.id
          AND q.source_question_id = s.id
          AND q.is_current IS TRUE
          AND q.status = 'approved'
      )
  ) THEN
    RAISE EXCEPTION 'ERR_NOT_ALL_QUESTIONS_APPROVED' USING ERRCODE = 'P0001';
  END IF;

  -- 9. Atomic State Transition
  UPDATE public.exam_sessions
  SET status = 'approved',
      approved_at = v_now,
      updated_at = v_now
  WHERE id = p_session_id;

  -- 10. Record APPROVE_ALL audit log entry
  INSERT INTO public.review_logs (
    session_id,
    user_id,
    action_type,
    reason,
    created_at
  ) VALUES (
    p_session_id,
    COALESCE(v_caller_id, v_session.user_id),
    'APPROVE_ALL',
    'Phiên đề được phê duyệt chính thức và khóa nội dung bất biến vĩnh viễn (TASK-305)',
    v_now
  );

  -- 11. Return approved response payload
  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'status', 'approved',
    'approved_at', v_now,
    'updated_at', v_now,
    'message', 'Phê duyệt phiên thi thành công và đã khóa nội dung'
  );
END;
$$;

-- Grant permissions for authenticated users and backend service role
REVOKE EXECUTE ON FUNCTION public.finalize_approve_session(UUID, UUID, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.finalize_approve_session(UUID, UUID, TIMESTAMPTZ) TO authenticated, service_role;

