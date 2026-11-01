-- Migration 008: Stage 3 Review Attempt Ledger & review_acquire_attempt RPC
-- Conforms strictly to review-rpc-contract.md (F07 resolution, TASK-301 / TASK-302 Phase B).
-- Provides single-transaction atomic permit acquisition, replay prevention, and quota accounting.

BEGIN;

-- 1. Create review_attempts table for durable ledger tracking
CREATE TABLE IF NOT EXISTS public.review_attempts (
    attempt_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL,
    session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('requested', 'granted', 'denied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_attempts_operation_id ON public.review_attempts(operation_id);
CREATE INDEX IF NOT EXISTS idx_review_attempts_session_id ON public.review_attempts(session_id);

-- 2. Stored Procedure for atomic attempt acquisition
CREATE OR REPLACE FUNCTION public.review_acquire_attempt(
    p_operation_id UUID,
    p_attempt_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_id UUID;
    v_session_status TEXT;
    v_current_calls INT;
    v_attempt_status TEXT;
    v_op_attempts INT;
BEGIN
    -- Resolve session_id from review_attempts or active regenerating candidate
    SELECT session_id INTO v_session_id
    FROM public.review_attempts
    WHERE operation_id = p_operation_id
    LIMIT 1;

    IF v_session_id IS NULL THEN
        SELECT v.session_id INTO v_session_id
        FROM public.version_questions q
        JOIN public.exam_versions v ON v.id = q.version_id
        WHERE q.regeneration_id = p_operation_id OR (q.status = 'regenerating' AND q.is_current)
        LIMIT 1;
    END IF;

    IF v_session_id IS NULL THEN
        RAISE EXCEPTION 'TASK301: cannot resolve session_id for operation %', p_operation_id
            USING ERRCODE = 'P0002';
    END IF;

    -- Lock session row atomically to prevent concurrent quota races across workers
    SELECT status, gemini_review_calls
    INTO v_session_status, v_current_calls
    FROM public.exam_sessions
    WHERE id = v_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'TASK301: session % not found', v_session_id
            USING ERRCODE = 'P0002';
    END IF;

    -- Check replay on review_attempts ledger
    SELECT status INTO v_attempt_status
    FROM public.review_attempts
    WHERE attempt_id = p_attempt_id;

    IF FOUND THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', true
        );
    END IF;

    -- Check operation attempt ceiling (max 4 attempts per reject operation)
    SELECT COUNT(*) INTO v_op_attempts
    FROM public.review_attempts
    WHERE operation_id = p_operation_id;

    IF v_op_attempts >= 4 THEN
        INSERT INTO public.review_attempts (attempt_id, operation_id, session_id, status, created_at)
        VALUES (p_attempt_id, p_operation_id, v_session_id, 'denied', NOW());

        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false
        );
    END IF;

    -- Check session quota ceiling (max 30 attempts per session)
    IF v_current_calls >= 30 THEN
        INSERT INTO public.review_attempts (attempt_id, operation_id, session_id, status, created_at)
        VALUES (p_attempt_id, p_operation_id, v_session_id, 'denied', NOW());

        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 30,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false
        );
    END IF;

    -- Increment session quota atomically and insert granted ledger entry
    UPDATE public.exam_sessions
    SET gemini_review_calls = v_current_calls + 1,
        updated_at = NOW()
    WHERE id = v_session_id;

    INSERT INTO public.review_attempts (attempt_id, operation_id, session_id, status, created_at)
    VALUES (p_attempt_id, p_operation_id, v_session_id, 'granted', NOW());

    RETURN jsonb_build_object(
        'operation_id', p_operation_id,
        'attempt_id', p_attempt_id,
        'dispatch_permitted', true,
        'calls_used', v_current_calls + 1,
        'remaining_calls', 30 - (v_current_calls + 1),
        'session_id', v_session_id,
        'session_status', v_session_status,
        'replayed', false
    );
END;
$$;

-- Revoke public permissions, grant to service_role and authenticated
REVOKE EXECUTE ON FUNCTION public.review_acquire_attempt(UUID, UUID) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.review_acquire_attempt(UUID, UUID) FROM anon;
GRANT EXECUTE ON FUNCTION public.review_acquire_attempt(UUID, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.review_acquire_attempt(UUID, UUID) TO service_role;

COMMIT;
