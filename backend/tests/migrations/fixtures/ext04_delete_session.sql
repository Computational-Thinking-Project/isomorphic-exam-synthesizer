-- Q07 rehearsal only. Apply after the pinned EXT-01 and EXT-02 migrations.
BEGIN;

CREATE FUNCTION public.delete_draft_session(p_session_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_actor uuid := auth.uid();
    v_session public.exam_sessions%ROWTYPE;
BEGIN
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'ERR_AUTH_REQUIRED' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_session
    FROM public.exam_sessions
    WHERE id = p_session_id AND user_id = v_actor
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ERR_SESSION_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_session.status IN ('approved', 'exported') OR v_session.approved_at IS NOT NULL THEN
        RAISE EXCEPTION 'ERR_SESSION_LOCKED' USING ERRCODE = '55000';
    END IF;
    IF v_session.status = 'generating' OR v_session.active_job_id IS NOT NULL THEN
        RAISE EXCEPTION 'ERR_SESSION_BUSY_GENERATING' USING ERRCODE = '55006';
    END IF;

    -- Recovery may recalculate session readiness. The parent lock stays held.
    PERFORM public._review_recover_expired_locked(v_session.id);

    SELECT * INTO STRICT v_session
    FROM public.exam_sessions
    WHERE id = p_session_id AND user_id = v_actor;

    IF v_session.status IN ('approved', 'exported') OR v_session.approved_at IS NOT NULL THEN
        RAISE EXCEPTION 'ERR_SESSION_LOCKED' USING ERRCODE = '55000';
    END IF;
    IF v_session.status = 'generating' OR v_session.active_job_id IS NOT NULL THEN
        RAISE EXCEPTION 'ERR_SESSION_BUSY_GENERATING' USING ERRCODE = '55006';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.review_operations
        WHERE session_id = v_session.id AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'ERR_REVIEW_OPERATION_ACTIVE' USING ERRCODE = '55006';
    END IF;

    DELETE FROM public.exam_sessions WHERE id = v_session.id;
END;
$$;

REVOKE ALL ON FUNCTION public.delete_draft_session(uuid) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.delete_draft_session(uuid) TO authenticated;
REVOKE DELETE ON TABLE public.exam_sessions FROM PUBLIC, anon, authenticated, service_role;

COMMIT;
