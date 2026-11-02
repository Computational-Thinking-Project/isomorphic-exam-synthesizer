-- Migration 008: Stage 3 Review Lifecycle Stored Procedures & Attempt Ledger
-- Conforms strictly to review-rpc-contract.md (TASK-301 / TASK-302 Phase B).
-- Provides single-transaction atomic permit acquisition, replay prevention, operation binding,
-- state transition guards, session-wide reshuffle invalidation, and quota accounting.

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

-- Enable Row Level Security on review_attempts ledger
ALTER TABLE public.review_attempts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'review_attempts' AND policyname = 'review_attempts_owner_read'
    ) THEN
        CREATE POLICY review_attempts_owner_read ON public.review_attempts
            FOR SELECT TO authenticated
            USING (session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'review_attempts' AND policyname = 'review_attempts_service_write'
    ) THEN
        CREATE POLICY review_attempts_service_write ON public.review_attempts
            FOR ALL TO service_role
            USING (TRUE) WITH CHECK (TRUE);
    END IF;
END $$;


-- ============================================================================
-- 2. Stored Procedure: review_reserve_regeneration (Owner JWT / Service Role)
-- Atomic TX1: Locks session FOR UPDATE, enforces Model A concurrency, and marks question
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_reserve_regeneration(
    p_session_id UUID,
    p_question_id UUID,
    p_operation_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_status TEXT;
    v_current_calls INT;
    v_session_owner UUID;
    v_active_regen_id UUID;
    v_qid UUID;
    v_qstatus TEXT;
    v_is_current BOOLEAN;
    v_src_qid UUID;
    v_vid UUID;
    v_qno INT;
    v_can_qno INT;
    v_can_opts JSONB;
    v_can_key TEXT;
    v_can_sol TEXT;
    v_content TEXT;
    v_opts JSONB;
    v_key TEXT;
    v_sol TEXT;
BEGIN
    -- 1. Lock session row atomically to enforce concurrency and check quota
    SELECT status, gemini_review_calls, user_id
    INTO v_session_status, v_current_calls, v_session_owner
    FROM public.exam_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_NOT_FOUND');
    END IF;

    -- Verify caller ownership if called via authenticated JWT
    IF auth.uid() IS NOT NULL AND auth.role() = 'authenticated' AND v_session_owner != auth.uid() THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'FORBIDDEN');
    END IF;

    -- Guard session status: locked when approved or exported
    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_LOCKED');
    END IF;

    -- Guard session busy when generating
    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- Guard session quota ceiling (30)
    IF v_current_calls >= 30 THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUOTA_EXHAUSTED');
    END IF;

    -- 2. Concurrency Model A: Max 1 active regenerating question per session
    SELECT q.id INTO v_active_regen_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE v.session_id = p_session_id
      AND q.status = 'regenerating'
      AND q.is_current = TRUE
    LIMIT 1;

    IF FOUND AND v_active_regen_id != p_question_id THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- 3. Check question state and lock question row
    SELECT q.id, q.status, q.is_current, q.source_question_id, q.version_id, q.question_no,
           q.canonical_question_no, q.canonical_options, q.canonical_correct_key, q.canonical_solution_md,
           q.content, q.options, q.correct_key, q.solution_md
    INTO v_qid, v_qstatus, v_is_current, v_src_qid, v_vid, v_qno,
         v_can_qno, v_can_opts, v_can_key, v_can_sol,
         v_content, v_opts, v_key, v_sol
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_FOUND');
    END IF;

    IF NOT v_is_current THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_CURRENT');
    END IF;

    IF v_qstatus = 'regenerating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_BUSY');
    END IF;

    -- 4. Atomic lock & durable operation binding
    UPDATE public.version_questions
    SET status = 'regenerating',
        regeneration_id = p_operation_id,
        updated_at = NOW()
    WHERE id = p_question_id;

    UPDATE public.exam_sessions
    SET updated_at = NOW()
    WHERE id = p_session_id;

    RETURN jsonb_build_object(
        'success', true,
        'session_id', p_session_id,
        'question_id', p_question_id,
        'operation_id', p_operation_id,
        'source_question_id', v_src_qid,
        'version_id', v_vid,
        'question_no', v_qno,
        'canonical_question_no', v_can_qno,
        'current_calls', v_current_calls,
        'status', 'regenerating'
    );
END;
$$;


-- ============================================================================
-- 3. Stored Procedure: review_acquire_attempt (Worker / service_role)
-- Single-transaction permit acquisition with strict binding, replay protection, and quota ceiling
-- ============================================================================
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
    v_question_id UUID;
    v_question_status TEXT;
    v_question_updated_at TIMESTAMPTZ;
    v_session_status TEXT;
    v_current_calls INT;
    v_attempt_status TEXT;
    v_op_attempts INT;
BEGIN
    -- Strict Operation Identity & Session Binding (TASK-302 contract)
    SELECT v.session_id, q.id, q.status, q.updated_at
    INTO v_session_id, v_question_id, v_question_status, v_question_updated_at
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.regeneration_id = p_operation_id
      AND q.is_current = TRUE
    LIMIT 1;

    -- If not found on version_questions, check review_attempts ledger for prior acquired attempts
    IF v_session_id IS NULL THEN
        SELECT session_id INTO v_session_id
        FROM public.review_attempts
        WHERE operation_id = p_operation_id
        LIMIT 1;
    END IF;

    -- Reject if operation does not exist or cannot be bound (Fail-closed)
    IF v_session_id IS NULL THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', NULL,
            'session_status', 'not_found',
            'replayed', false,
            'rejection_reason', 'OPERATION_NOT_FOUND'
        );
    END IF;

    -- Verify question is in active regenerating status
    IF v_question_status IS NOT NULL AND v_question_status != 'regenerating' THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', 'invalid_state',
            'replayed', false,
            'rejection_reason', 'OPERATION_INACTIVE'
        );
    END IF;

    -- Check lease expiration (180-second stale timeout per TASK-302 contract)
    IF v_question_updated_at IS NOT NULL AND v_question_updated_at < (NOW() - INTERVAL '180 seconds') THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', 'expired',
            'replayed', false,
            'rejection_reason', 'OPERATION_EXPIRED'
        );
    END IF;

    -- Lock session row atomically to prevent concurrent quota races across workers
    SELECT status, gemini_review_calls
    INTO v_session_status, v_current_calls
    FROM public.exam_sessions
    WHERE id = v_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', 0,
            'remaining_calls', 0,
            'session_id', v_session_id,
            'session_status', 'not_found',
            'replayed', false,
            'rejection_reason', 'SESSION_NOT_FOUND'
        );
    END IF;

    -- Enforce session lock guard: reject approved or exported sessions
    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false,
            'rejection_reason', 'SESSION_LOCKED'
        );
    END IF;

    -- Enforce session busy guard: reject if session is actively generating
    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object(
            'operation_id', p_operation_id,
            'attempt_id', p_attempt_id,
            'dispatch_permitted', false,
            'calls_used', LEAST(30, GREATEST(0, v_current_calls)),
            'remaining_calls', GREATEST(0, 30 - v_current_calls),
            'session_id', v_session_id,
            'session_status', v_session_status,
            'replayed', false,
            'rejection_reason', 'SESSION_BUSY'
        );
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
            'replayed', true,
            'rejection_reason', 'ATTEMPT_REPLAYED'
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
            'replayed', false,
            'rejection_reason', 'OPERATION_EXHAUSTED'
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
            'replayed', false,
            'rejection_reason', 'QUOTA_EXHAUSTED'
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


-- ============================================================================
-- 4. Stored Procedure: review_complete_regeneration (Worker / service_role)
-- Atomic TX2: Deactivates old question, inserts new question, invalidates finalization, and writes audit
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_complete_regeneration(
    p_operation_id UUID,
    p_candidate JSONB,
    p_user_id UUID,
    p_actual_calls INT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_existing_id UUID;
    v_old_id UUID;
    v_version_id UUID;
    v_source_id UUID;
    v_question_no INT;
    v_canonical_no INT;
    v_session_id UUID;
    v_new_id UUID;
    v_content TEXT;
    v_options JSONB;
    v_correct_key TEXT;
    v_solution_md TEXT;
    v_validation_report JSONB;
BEGIN
    -- Idempotency check: see if a replacement was already committed with this operation_id
    SELECT id INTO v_existing_id
    FROM public.version_questions
    WHERE regeneration_id = p_operation_id
      AND status != 'rejected'
      AND status != 'regenerating'
    LIMIT 1;

    IF FOUND THEN
        SELECT v.session_id INTO v_session_id
        FROM public.version_questions q
        JOIN public.exam_versions v ON v.id = q.version_id
        WHERE q.id = v_existing_id;

        RETURN jsonb_build_object(
            'success', true,
            'replayed', true,
            'session_id', v_session_id,
            'question_id', v_existing_id,
            'operation_id', p_operation_id,
            'status', 'pending_review'
        );
    END IF;

    -- Find active regenerating question bound to this operation
    SELECT q.id, q.version_id, q.source_question_id, q.question_no,
           COALESCE(q.canonical_question_no, q.question_no), v.session_id
    INTO v_old_id, v_version_id, v_source_id, v_question_no,
         v_canonical_no, v_session_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.regeneration_id = p_operation_id
      AND q.status = 'regenerating'
      AND q.is_current = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'rejection_reason', 'OPERATION_NOT_FOUND'
        );
    END IF;

    -- 1. Deactivate old candidate
    UPDATE public.version_questions
    SET is_current = FALSE,
        status = 'rejected',
        regeneration_id = NULL,
        updated_at = NOW()
    WHERE id = v_old_id;

    -- 2. Extract candidate payload fields
    v_content := COALESCE(p_candidate->>'content', p_candidate->>'stem_latex');
    v_options := p_candidate->'options';
    v_correct_key := UPPER(TRIM(COALESCE(p_candidate->>'correct_key', 'A')));
    v_solution_md := p_candidate->>'solution_md';
    v_validation_report := COALESCE(p_candidate->'validation_report', '{}'::jsonb);

    -- 3. Insert new candidate with fresh canonical snapshot
    v_new_id := gen_random_uuid();
    INSERT INTO public.version_questions (
        id, version_id, source_question_id, question_no,
        content, options, correct_key, solution_md,
        canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
        status, is_current, is_reverted, regenerated_from_id, regeneration_id,
        validation_report, created_at, updated_at
    ) VALUES (
        v_new_id,
        v_version_id,
        v_source_id,
        v_question_no,
        v_content,
        v_options,
        v_correct_key,
        v_solution_md,
        v_canonical_no,
        v_options,
        v_correct_key,
        v_solution_md,
        'pending_review',
        TRUE,
        FALSE,
        v_old_id,
        p_operation_id,
        v_validation_report,
        NOW(),
        NOW()
    );

    -- 4. Session-wide reshuffle invalidation
    DELETE FROM public.answer_keys
    WHERE version_id IN (
        SELECT id FROM public.exam_versions WHERE session_id = v_session_id
    );

    UPDATE public.exam_versions
    SET is_finalized = FALSE,
        shuffle_seed = NULL,
        permutations = NULL,
        updated_at = NOW()
    WHERE session_id = v_session_id;

    UPDATE public.exam_sessions
    SET status = 'generated',
        updated_at = NOW()
    WHERE id = v_session_id AND status = 'reviewed';

    -- 5. Audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, api_calls_used, regenerated_from_id, created_at
    ) VALUES (
        v_session_id,
        v_new_id,
        p_user_id,
        'REJECT',
        'USER_REJECTED',
        p_actual_calls,
        v_old_id,
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'replayed', false,
        'session_id', v_session_id,
        'question_id', v_new_id,
        'previous_question_id', v_old_id,
        'operation_id', p_operation_id,
        'status', 'pending_review',
        'api_calls_used', p_actual_calls
    );
END;
$$;


-- ============================================================================
-- 5. Stored Procedure: review_fail_regeneration (Worker / service_role)
-- Emergency Rollback: restores old question to pending_review without quota refund
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_fail_regeneration(
    p_operation_id UUID,
    p_error_code TEXT,
    p_user_id UUID,
    p_actual_calls INT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_old_id UUID;
    v_session_id UUID;
BEGIN
    SELECT q.id, v.session_id
    INTO v_old_id, v_session_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.regeneration_id = p_operation_id
      AND q.status = 'regenerating'
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'replayed', true,
            'operation_id', p_operation_id
        );
    END IF;

    -- Restore question back to pending_review and clear lease
    UPDATE public.version_questions
    SET status = 'pending_review',
        regeneration_id = NULL,
        updated_at = NOW()
    WHERE id = v_old_id;

    -- Record failed attempt in audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, api_calls_used, created_at
    ) VALUES (
        v_session_id,
        v_old_id,
        p_user_id,
        'REJECT_FAILED',
        p_error_code,
        p_actual_calls,
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'operation_id', p_operation_id,
        'question_id', v_old_id,
        'status', 'pending_review',
        'api_calls_used', p_actual_calls
    );
END;
$$;


-- ============================================================================
-- 6. Stored Procedure: review_revert_question (Owner JWT / Service Role)
-- Atomic Revert: Copies original source question, invalidates finalization, and audits
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_revert_question(
    p_session_id UUID,
    p_question_id UUID,
    p_action_id UUID,
    p_user_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_status TEXT;
    v_session_owner UUID;
    v_old_id UUID;
    v_version_id UUID;
    v_source_id UUID;
    v_is_current BOOLEAN;
    v_qstatus TEXT;
    v_is_reverted BOOLEAN;
    v_regen_from_id UUID;
    v_raw_content TEXT;
    v_src_opts JSONB;
    v_src_key TEXT;
    v_src_sol TEXT;
    v_qno INT;
    v_new_id UUID;
BEGIN
    -- 1. Lock session row
    SELECT status, user_id INTO v_session_status, v_session_owner
    FROM public.exam_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_NOT_FOUND');
    END IF;

    IF auth.uid() IS NOT NULL AND auth.role() = 'authenticated' AND v_session_owner != auth.uid() THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'FORBIDDEN');
    END IF;

    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_LOCKED');
    END IF;

    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- 2. Lock candidate row
    SELECT q.id, q.version_id, q.source_question_id, q.is_current, q.status,
           q.is_reverted, q.regenerated_from_id
    INTO v_old_id, v_version_id, v_source_id, v_is_current, v_qstatus,
         v_is_reverted, v_regen_from_id
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_FOUND');
    END IF;

    IF NOT v_is_current THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_CURRENT');
    END IF;

    IF v_qstatus = 'regenerating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_BUSY');
    END IF;

    -- Cannot revert a question that was never regenerated
    IF v_regen_from_id IS NULL AND v_is_reverted IS FALSE THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_REGENERATED');
    END IF;

    -- Idempotent check
    IF v_is_reverted IS TRUE AND v_qstatus = 'approved' THEN
        RETURN jsonb_build_object(
            'success', true,
            'replayed', true,
            'session_id', p_session_id,
            'question_id', p_question_id,
            'status', 'approved'
        );
    END IF;

    -- 3. Fetch source question
    SELECT raw_content, options, correct_key, solution_md, question_no
    INTO v_raw_content, v_src_opts, v_src_key, v_src_sol, v_qno
    FROM public.source_questions
    WHERE id = v_source_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SOURCE_NOT_FOUND');
    END IF;

    -- 4. Deactivate old candidate
    UPDATE public.version_questions
    SET is_current = FALSE,
        updated_at = NOW()
    WHERE id = p_question_id;

    -- 5. Insert new candidate copied from source
    v_new_id := gen_random_uuid();
    INSERT INTO public.version_questions (
        id, version_id, source_question_id, question_no,
        content, options, correct_key, solution_md,
        canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
        status, is_current, is_reverted, regenerated_from_id, created_at, updated_at
    ) VALUES (
        v_new_id,
        v_version_id,
        v_source_id,
        v_qno,
        v_raw_content,
        v_src_opts,
        v_src_key,
        v_src_sol,
        v_qno,
        v_src_opts,
        v_src_key,
        v_src_sol,
        'approved',
        TRUE,
        TRUE,
        p_question_id,
        NOW(),
        NOW()
    );

    -- 6. Session-wide reshuffle invalidation
    DELETE FROM public.answer_keys
    WHERE version_id IN (
        SELECT id FROM public.exam_versions WHERE session_id = p_session_id
    );

    UPDATE public.exam_versions
    SET is_finalized = FALSE,
        shuffle_seed = NULL,
        permutations = NULL,
        updated_at = NOW()
    WHERE session_id = p_session_id;

    UPDATE public.exam_sessions
    SET status = 'generated',
        updated_at = NOW()
    WHERE id = p_session_id AND status = 'reviewed';

    -- 7. Audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, created_at
    ) VALUES (
        p_session_id,
        v_new_id,
        p_user_id,
        'REVERT',
        'USER_REVERTED',
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'replayed', false,
        'session_id', p_session_id,
        'question_id', v_new_id,
        'previous_question_id', p_question_id,
        'status', 'approved'
    );
END;
$$;


-- ============================================================================
-- 7. Stored Procedure: review_accept_question (Owner JWT / Service Role)
-- Atomic Accept: Marks candidate approved and writes audit log
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_accept_question(
    p_session_id UUID,
    p_question_id UUID,
    p_user_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_session_status TEXT;
    v_session_owner UUID;
    v_qid UUID;
    v_qstatus TEXT;
    v_is_current BOOLEAN;
BEGIN
    -- 1. Lock session row
    SELECT status, user_id INTO v_session_status, v_session_owner
    FROM public.exam_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_NOT_FOUND');
    END IF;

    IF auth.uid() IS NOT NULL AND auth.role() = 'authenticated' AND v_session_owner != auth.uid() THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'FORBIDDEN');
    END IF;

    IF v_session_status IN ('approved', 'exported') THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_LOCKED');
    END IF;

    IF v_session_status = 'generating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'SESSION_BUSY');
    END IF;

    -- 2. Lock candidate row
    SELECT q.id, q.status, q.is_current
    INTO v_qid, v_qstatus, v_is_current
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_FOUND');
    END IF;

    IF NOT v_is_current THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_NOT_CURRENT');
    END IF;

    IF v_qstatus = 'regenerating' THEN
        RETURN jsonb_build_object('success', false, 'rejection_reason', 'QUESTION_BUSY');
    END IF;

    IF v_qstatus = 'approved' THEN
        RETURN jsonb_build_object(
            'success', true,
            'replayed', true,
            'session_id', p_session_id,
            'question_id', p_question_id,
            'status', 'approved'
        );
    END IF;

    -- 3. Mark approved
    UPDATE public.version_questions
    SET status = 'approved',
        updated_at = NOW()
    WHERE id = p_question_id;

    -- 4. Audit log
    INSERT INTO public.review_logs (
        session_id, version_question_id, user_id, action_type,
        reason, created_at
    ) VALUES (
        p_session_id,
        p_question_id,
        p_user_id,
        'ACCEPT',
        'USER_ACCEPTED',
        NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'replayed', false,
        'session_id', p_session_id,
        'question_id', p_question_id,
        'status', 'approved'
    );
END;
$$;


-- ============================================================================
-- 8. Stored Procedure: review_recover_stale (Owner JWT / Service Role)
-- Recovers stale regenerating questions (> 180s) and writes REJECT_FAILED audit logs
-- ============================================================================
CREATE OR REPLACE FUNCTION public.review_recover_stale(
    p_session_id UUID,
    p_caller_user_id UUID
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_recovered_count INT := 0;
    r RECORD;
BEGIN
    FOR r IN (
        SELECT q.id
        FROM public.version_questions q
        JOIN public.exam_versions v ON v.id = q.version_id
        WHERE v.session_id = p_session_id
          AND q.status = 'regenerating'
          AND q.is_current = TRUE
          AND q.updated_at < (NOW() - INTERVAL '180 seconds')
        FOR UPDATE OF q
    ) LOOP
        UPDATE public.version_questions
        SET status = 'pending_review',
            regeneration_id = NULL,
            updated_at = NOW()
        WHERE id = r.id;

        INSERT INTO public.review_logs (
            session_id, version_question_id, user_id, action_type,
            reason, created_at
        ) VALUES (
            p_session_id,
            r.id,
            p_caller_user_id,
            'REJECT_FAILED',
            'STALE_TIMEOUT',
            NOW()
        );

        v_recovered_count := v_recovered_count + 1;
    END LOOP;

    RETURN jsonb_build_object(
        'success', true,
        'session_id', p_session_id,
        'recovered_count', v_recovered_count
    );
END;
$$;


-- ============================================================================
-- 9. Permissions & Access Control (TASK-302 Contract)
-- ============================================================================
-- Revoke all from PUBLIC and anon
REVOKE ALL ON FUNCTION public.review_reserve_regeneration(UUID, UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_acquire_attempt(UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_complete_regeneration(UUID, JSONB, UUID, INT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_fail_regeneration(UUID, TEXT, UUID, INT) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_revert_question(UUID, UUID, UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_accept_question(UUID, UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.review_recover_stale(UUID, UUID) FROM PUBLIC, anon;

-- Grant Owner RPCs to authenticated and service_role
GRANT EXECUTE ON FUNCTION public.review_reserve_regeneration(UUID, UUID, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.review_revert_question(UUID, UUID, UUID, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.review_accept_question(UUID, UUID, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.review_recover_stale(UUID, UUID) TO authenticated, service_role;

-- Grant Worker RPCs to service_role (and authenticated for direct API lifecycle)
GRANT EXECUTE ON FUNCTION public.review_acquire_attempt(UUID, UUID) TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.review_complete_regeneration(UUID, JSONB, UUID, INT) TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.review_fail_regeneration(UUID, TEXT, UUID, INT) TO service_role, authenticated;

COMMIT;
