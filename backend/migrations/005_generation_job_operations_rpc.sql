-- ============================================================================
-- Migration 005 (v6): Hardened Generation Job Operations & Persistence RPC [TASK-207b]
-- Prerequisites: PostgreSQL 13+ (built-in gen_random_uuid) or pgcrypto extension.
-- Note: Background workers run under service_role.
--
-- Security, Fencing & Consistency Hardening (Review v5 Resolution):
--   - B1 FIX: Safe backfill transitions orphan generating sessions (active_job_id IS NULL)
--     to 'failed' before applying chk_generating_has_job constraint.
--   - B2 FIX: persist_version_question verifies p_source_question_id belongs to p_session_id.
--   - M1 FIX: finish_generation_job verifies questions persistence completeness
--     (outcome 'generated' requires all expected questions; 'partial_generated' requires >= 1).
--   - M2 FIX: persist_version_question is fully idempotent (ON CONFLICT on exam_versions;
--     checks existing is_current question before INSERT/UPDATE on version_questions).
--   - M3 FIX: p_version_index validated strictly between 1 and 4, and cannot exceed
--     configured n_versions from generation_configs.
--   - M4 DOC: Documented schema prerequisites for exam_versions and version_questions.
--   - Md1 DOC: canonical_* represents the immutable generated baseline variant, preserved
--     per docs/planning.md for Stage 3 side-by-side review and reversion.
--   - Md2 DOC: claim_generation_job remains GRANTED to authenticated because FastAPI's
--     generate endpoint executes runner.claim under user auth with strict ownership verification.
--   - Mi3 DOC: claim response preserves both starting_quota and gemini_call_count for
--     backwards compatibility with PR #30 GenerationPlan contract.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Schema Invariants, Indexes & Constraints Setup
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- Add active_job_id if not present
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'active_job_id'
  ) THEN
    ALTER TABLE public.exam_sessions ADD COLUMN active_job_id UUID NULL;
  END IF;

  -- Add last_progress_at heartbeat column if not present
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'exam_sessions' 
      AND column_name = 'last_progress_at'
  ) THEN
    ALTER TABLE public.exam_sessions ADD COLUMN last_progress_at TIMESTAMPTZ NULL;
  END IF;

  -- Backfill any unexpected NULLs before setting NOT NULL
  UPDATE public.exam_sessions SET gemini_call_count = 0 WHERE gemini_call_count IS NULL;
  UPDATE public.exam_sessions SET active_job_id = NULL WHERE status <> 'generating' AND active_job_id IS NOT NULL;

  -- B1 FIX: Resolve legacy orphan generating sessions BEFORE adding constraint
  UPDATE public.exam_sessions SET status = 'failed' WHERE status = 'generating' AND active_job_id IS NULL;

  -- Enforce NOT NULL on status and gemini_call_count
  ALTER TABLE public.exam_sessions
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN gemini_call_count SET NOT NULL,
    ALTER COLUMN gemini_call_count SET DEFAULT 0;

  -- Add CHECK constraints if not exist
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_quota_range') THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_quota_range CHECK (gemini_call_count BETWEEN 0 AND 250);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_generating_has_job') THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_generating_has_job CHECK (status <> 'generating' OR active_job_id IS NOT NULL);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_not_generating_has_no_job') THEN
    ALTER TABLE public.exam_sessions
      ADD CONSTRAINT chk_not_generating_has_no_job CHECK (status = 'generating' OR active_job_id IS NULL);
  END IF;

  -- Ensure unique constraint on exam_versions(session_id, version_code)
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_exam_versions_session_code') THEN
    ALTER TABLE public.exam_versions
      ADD CONSTRAINT uq_exam_versions_session_code UNIQUE (session_id, version_code);
  END IF;

  -- Ensure partial unique index on version_questions(version_id, source_question_id) for current questions
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes 
    WHERE schemaname = 'public' AND indexname = 'idx_single_current_version_question'
  ) THEN
    CREATE UNIQUE INDEX idx_single_current_version_question
      ON public.version_questions (version_id, source_question_id)
      WHERE is_current = TRUE;
  END IF;
END $$;

-- 2. Drop existing signatures to avoid overload mismatch
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN);
DROP FUNCTION IF EXISTS public.claim_generation_job(UUID, BOOLEAN, UUID);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT);
DROP FUNCTION IF EXISTS public.reserve_generation_quota(UUID, INT, UUID);
DROP FUNCTION IF EXISTS public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN);
DROP FUNCTION IF EXISTS public.heartbeat_generation_job(UUID, UUID);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT);
DROP FUNCTION IF EXISTS public.finish_generation_job(UUID, TEXT, UUID);
DROP FUNCTION IF EXISTS public.fail_stale_generation_job(UUID);
DROP FUNCTION IF EXISTS public.fail_stale_generation_job(UUID, INT);

-- ----------------------------------------------------------------------------
-- 3. claim_generation_job
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_generation_job(
  p_session_id UUID,
  p_is_retry BOOLEAN DEFAULT FALSE,
  p_worker_job_id UUID DEFAULT NULL
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
  v_config JSONB;
  v_committed_targets JSONB;
  v_job_id UUID;
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 0. Validate p_is_retry is not NULL
  IF p_is_retry IS NULL THEN
    RAISE EXCEPTION 'p_is_retry cannot be NULL' USING ERRCODE = '22023';
  END IF;

  -- 1. Lock session row
  SELECT user_id, status, active_job_id, gemini_call_count
    INTO v_session_user_id, v_session_status, v_active_job_id, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Authorization (NULL-safe: caller must be service_role or owner)
  IF public.current_role() != 'service_role'
     AND (v_session_user_id IS DISTINCT FROM auth.uid() OR auth.uid() IS NULL) THEN
    RAISE EXCEPTION 'Access denied: caller does not own session %', p_session_id
      USING ERRCODE = '42501';
  END IF;

  -- 3. Concurrency check: Reject if already actively generating
  IF v_session_status = 'generating' THEN
    RAISE EXCEPTION 'Session % is already being generated by job %',
      p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 4. State validation
  IF NOT p_is_retry THEN
    IF v_session_status != 'configured' THEN
      RAISE EXCEPTION 'Cannot claim generation: session must be configured (current: %)',
        v_session_status USING ERRCODE = '22023';
    END IF;
  ELSE
    IF v_session_status NOT IN ('partial_generated', 'failed') THEN
      RAISE EXCEPTION 'Cannot retry generation: session status must be partial_generated or failed (current: %)',
        v_session_status USING ERRCODE = '22023';
    END IF;
  END IF;

  -- 5. Read generation config
  SELECT jsonb_build_object(
    'n_versions', n_versions,
    'active_variation_modes', active_variation_modes,
    'ordering_preferences', ordering_preferences
  ) INTO v_config
  FROM public.generation_configs
  WHERE session_id = p_session_id;

  IF v_config IS NULL THEN
    RAISE EXCEPTION 'Generation config not found for session %', p_session_id
      USING ERRCODE = '55000';
  END IF;

  -- 6. Read committed targets (for incremental retry resume)
  SELECT COALESCE(
    jsonb_agg(jsonb_build_object(
      'version_code', ev.version_code,
      'source_question_id', vq.source_question_id,
      'question_no', vq.question_no
    )),
    '[]'::jsonb
  ) INTO v_committed_targets
  FROM public.exam_versions ev
  JOIN public.version_questions vq ON vq.version_id = ev.id
  WHERE ev.session_id = p_session_id AND vq.is_current = TRUE;

  -- 7. Transition to generating and set active fencing token
  v_job_id := COALESCE(p_worker_job_id, gen_random_uuid());

  UPDATE public.exam_sessions
  SET status = 'generating',
      active_job_id = v_job_id,
      last_progress_at = v_now,
      retry_count = CASE WHEN p_is_retry THEN retry_count + 1 ELSE retry_count END
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'job_id', v_job_id,
    'status', 'generating',
    'starting_quota', v_current_quota,
    'gemini_call_count', v_current_quota,
    'config', v_config,
    'committed_targets', v_committed_targets
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 4. reserve_generation_quota (Restricted to service_role)
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
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Restrict strictly to service_role (NULL-safe)
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: reserve_generation_quota is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 2. Validate requested quota increment
  IF p_calls_requested IS NULL OR p_calls_requested < 1 OR p_calls_requested > 250 THEN
    RAISE EXCEPTION 'p_calls_requested must be between 1 and 250 (got %)', p_calls_requested
      USING ERRCODE = '22023';
  END IF;

  -- 3. Lock session row
  SELECT user_id, status, active_job_id, gemini_call_count
    INTO v_session_user_id, v_session_status, v_active_job_id, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_user_id IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- 4. State validation: only generating session can consume quota
  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot reserve quota: session % is not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 5. Fencing token check: NULL cannot bypass (IS DISTINCT FROM)
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 6. Check durable quota hard-cap (250 calls across entire session lifecycle)
  v_new_quota := v_current_quota + p_calls_requested;
  IF v_new_quota > 250 THEN
    RAISE EXCEPTION 'Gemini quota hard-cap exceeded for session %: requested %, current %, cap 250',
      p_session_id, p_calls_requested, v_current_quota USING ERRCODE = '54000';
  END IF;

  -- 7. Atomically increment quota and update heartbeat
  UPDATE public.exam_sessions
  SET gemini_call_count = v_new_quota,
      last_progress_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'job_id', p_job_token,
    'reserved_calls', p_calls_requested,
    'new_total_calls', v_new_quota,
    'remaining_quota', (250 - v_new_quota)
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 5. persist_version_question (Fencing Token Protection & Idempotent Persistence)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.persist_version_question(
  p_session_id UUID,
  p_job_token UUID,
  p_version_index INT,
  p_source_question_id UUID,
  p_question_no INT,
  p_content TEXT,
  p_options JSONB,
  p_correct_key TEXT,
  p_solution_md TEXT,
  p_has_warning BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_configured_n_versions INT;
  v_version_id UUID;
  v_question_id UUID;
  v_version_code TEXT;
  v_now TIMESTAMPTZ := now();
BEGIN
  -- 1. Restrict strictly to service_role
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: persist_version_question is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 2. Validate p_version_index (M3 FIX)
  IF p_version_index IS NULL OR p_version_index < 1 OR p_version_index > 4 THEN
    RAISE EXCEPTION 'p_version_index must be between 1 and 4 (got %)', p_version_index
      USING ERRCODE = '22023';
  END IF;
  v_version_code := (100 + p_version_index)::TEXT;

  -- 3. Lock session row to verify active fencing token
  SELECT status, active_job_id
    INTO v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_status IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot persist question: session % is not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- Critical Fencing Token Check: Stale worker is completely blocked from writing rows!
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 4. Validate p_version_index does not exceed session configuration (M3 FIX)
  SELECT n_versions INTO v_configured_n_versions
  FROM public.generation_configs
  WHERE session_id = p_session_id;

  IF v_configured_n_versions IS NOT NULL AND p_version_index > v_configured_n_versions THEN
    RAISE EXCEPTION 'p_version_index % exceeds configured n_versions % for session %',
      p_version_index, v_configured_n_versions, p_session_id USING ERRCODE = '22023';
  END IF;

  -- 5. B2 FIX: Verify p_source_question_id belongs to p_session_id
  IF NOT EXISTS (
    SELECT 1 FROM public.source_questions
    WHERE id = p_source_question_id AND session_id = p_session_id
  ) THEN
    RAISE EXCEPTION 'source_question % does not belong to session %',
      p_source_question_id, p_session_id USING ERRCODE = '22023';
  END IF;

  -- 6. M2 FIX: Ensure target exam_version exists (idempotent upsert)
  SELECT id INTO v_version_id
  FROM public.exam_versions
  WHERE session_id = p_session_id AND version_code = v_version_code;

  IF v_version_id IS NULL THEN
    INSERT INTO public.exam_versions (session_id, version_code, created_at)
    VALUES (p_session_id, v_version_code, v_now)
    ON CONFLICT (session_id, version_code) DO UPDATE
      SET version_code = EXCLUDED.version_code
    RETURNING id INTO v_version_id;
  END IF;

  -- 7. M2 FIX: Idempotent upsert into version_questions
  SELECT id INTO v_question_id
  FROM public.version_questions
  WHERE version_id = v_version_id
    AND source_question_id = p_source_question_id
    AND is_current = TRUE;

  IF v_question_id IS NOT NULL THEN
    UPDATE public.version_questions
    SET question_no = p_question_no,
        content = p_content,
        options = p_options,
        correct_key = p_correct_key,
        solution_md = p_solution_md,
        canonical_question_no = p_question_no,
        canonical_options = p_options,
        canonical_correct_key = p_correct_key,
        canonical_solution_md = p_solution_md,
        has_warning = COALESCE(p_has_warning, FALSE),
        updated_at = v_now
    WHERE id = v_question_id;
  ELSE
    INSERT INTO public.version_questions (
      version_id,
      source_question_id,
      question_no,
      content,
      options,
      correct_key,
      solution_md,
      canonical_question_no,
      canonical_options,
      canonical_correct_key,
      canonical_solution_md,
      has_warning,
      status,
      is_current,
      created_at,
      updated_at
    ) VALUES (
      v_version_id,
      p_source_question_id,
      p_question_no,
      p_content,
      p_options,
      p_correct_key,
      p_solution_md,
      p_question_no,
      p_options,
      p_correct_key,
      p_solution_md,
      COALESCE(p_has_warning, FALSE),
      'pending_review',
      TRUE,
      v_now,
      v_now
    )
    RETURNING id INTO v_question_id;
  END IF;

  -- 8. Touch last_progress_at to prevent false-positive stale timeout
  UPDATE public.exam_sessions
  SET last_progress_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'question_id', v_question_id,
    'version_id', v_version_id,
    'question_no', p_question_no
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 6. heartbeat_generation_job (Worker Liveness Reporting)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.heartbeat_generation_job(
  p_session_id UUID,
  p_job_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_now TIMESTAMPTZ := now();
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: heartbeat_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  SELECT status, active_job_id
    INTO v_session_status, v_active_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot heartbeat: session % is not generating', p_session_id USING ERRCODE = '22023';
  END IF;

  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session %',
      p_job_token, p_session_id USING ERRCODE = '55006';
  END IF;

  UPDATE public.exam_sessions
  SET last_progress_at = v_now
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'heartbeat_at', v_now
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 7. finish_generation_job (Restricted to service_role)
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
  v_finished_at TIMESTAMPTZ;
BEGIN
  -- 1. Validate outcome (strict NULL check before enum cast)
  IF p_outcome IS NULL OR p_outcome NOT IN ('generated', 'partial_generated', 'failed') THEN
    RAISE EXCEPTION 'Invalid outcome status: % (must be generated, partial_generated, or failed)', p_outcome
      USING ERRCODE = '22023';
  END IF;
  v_target_status := p_outcome::public.session_status;

  -- 2. Restrict to service_role (NULL-safe)
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: finish_generation_job is restricted to service_role'
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

  -- 7. M1 FIX: Verify question persistence completeness
  IF p_outcome = 'generated' THEN
    DECLARE
      v_expected INT;
      v_actual INT;
    BEGIN
      SELECT c.n_versions * (SELECT COUNT(*) FROM public.source_questions WHERE session_id = p_session_id)
        INTO v_expected
      FROM public.generation_configs c
      WHERE c.session_id = p_session_id;

      IF v_expected IS NULL OR v_expected = 0 THEN
        RAISE EXCEPTION 'Cannot finish as generated: session % has no valid generation config or source questions',
          p_session_id USING ERRCODE = '55000';
      END IF;

      SELECT COUNT(*) INTO v_actual
      FROM public.version_questions vq
      JOIN public.exam_versions ev ON vq.version_id = ev.id
      WHERE ev.session_id = p_session_id AND vq.is_current = TRUE;

      IF v_actual < v_expected THEN
        RAISE EXCEPTION 'Cannot finish as generated: expected % questions, found % for session %',
          v_expected, v_actual, p_session_id USING ERRCODE = '22023';
      END IF;
    END;
  ELSIF p_outcome = 'partial_generated' THEN
    DECLARE
      v_actual INT;
    BEGIN
      SELECT COUNT(*) INTO v_actual
      FROM public.version_questions vq
      JOIN public.exam_versions ev ON vq.version_id = ev.id
      WHERE ev.session_id = p_session_id AND vq.is_current = TRUE;

      IF v_actual < 1 THEN
        RAISE EXCEPTION 'Cannot finish as partial_generated: 0 questions persisted for session %',
          p_session_id USING ERRCODE = '22023';
      END IF;
    END;
  END IF;

  -- 8. Transition status and clear active_job_id (RETURNING true updated_at)
  UPDATE public.exam_sessions
  SET status = v_target_status,
      active_job_id = NULL
  WHERE id = p_session_id
  RETURNING updated_at INTO v_finished_at;

  RETURN jsonb_build_object(
    'success', TRUE,
    'session_id', p_session_id,
    'previous_job_id', v_active_job_id,
    'status', p_outcome,
    'finished_at', v_finished_at
  );
END;
$$;

-- ----------------------------------------------------------------------------
-- 8. fail_stale_generation_job (Restricted to service_role)
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
  v_last_progress TIMESTAMPTZ;
  v_effective_activity TIMESTAMPTZ;
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
    RAISE EXCEPTION 'fail_stale_generation_job is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  -- 3. Lock session row
  SELECT status, updated_at, last_progress_at, active_job_id
    INTO v_current_status, v_updated_at, v_last_progress, v_old_job_id
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF v_current_status IS NULL THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  -- Effective activity timestamp: prefers last_progress_at, falls back to updated_at
  v_effective_activity := COALESCE(v_last_progress, v_updated_at);

  -- 4. Recover if stale
  IF v_current_status = 'generating'
     AND v_effective_activity < (v_now - make_interval(secs => p_cutoff_seconds)) THEN
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
-- 9. Least privilege (SEC-04)
-- ----------------------------------------------------------------------------
-- Client functions: claim_generation_job remains GRANTED to authenticated because
-- FastAPI's generate endpoint calls runner.claim under user auth (enforcing ownership)
REVOKE EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.claim_generation_job(UUID, BOOLEAN, UUID) TO authenticated, service_role;

-- Worker functions: strictly service_role only
REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN) TO service_role;

REVOKE EXECUTE ON FUNCTION public.heartbeat_generation_job(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.heartbeat_generation_job(UUID, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.finish_generation_job(UUID, TEXT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.fail_stale_generation_job(UUID, INT) TO service_role;
