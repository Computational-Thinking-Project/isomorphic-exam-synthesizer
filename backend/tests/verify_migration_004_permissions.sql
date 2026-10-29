-- ============================================================================
-- Verification Suite for Migration 004 & 005 (v6-lite) [TASK-207a/b]
-- Tests:
-- 1. Schema invariants (columns, constraints, triggers, indexes, functions)
-- 2. NULL-Semantics & current_role() non-NULL guarantee
-- 3. is_valid_variation_modes validation
-- 4. Service-role-only isolation for worker RPCs (reserve, persist, finish, fail_stale)
-- 5. Client authorization for claim & save_generation_config
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Verify schema elements
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- Columns on exam_sessions
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'exam_sessions' AND column_name = 'active_job_id'
  ) THEN
    RAISE EXCEPTION 'Missing active_job_id column on exam_sessions';
  END IF;

  -- Columns on generation_configs
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'generation_configs' AND column_name = 'updated_at'
  ) THEN
    RAISE EXCEPTION 'Missing updated_at column on generation_configs';
  END IF;

  -- Constraints on exam_sessions
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.exam_sessions'::regclass AND conname = 'chk_quota_range') THEN
    RAISE EXCEPTION 'Missing constraint chk_quota_range on exam_sessions';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.exam_sessions'::regclass AND conname = 'chk_generating_has_job') THEN
    RAISE EXCEPTION 'Missing constraint chk_generating_has_job on exam_sessions';
  END IF;

  -- Constraints on exam_versions
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.exam_versions'::regclass AND conname = 'uq_exam_versions_session_code') THEN
    RAISE EXCEPTION 'Missing constraint uq_exam_versions_session_code on exam_versions';
  END IF;

  -- Partial unique index on version_questions
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes 
    WHERE schemaname = 'public' AND tablename = 'version_questions' AND indexname = 'idx_single_current_version_question'
  ) THEN
    RAISE EXCEPTION 'Missing unique index idx_single_current_version_question on version_questions';
  END IF;

  -- Unique constraint on generation_configs(session_id)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid = 'public.generation_configs'::regclass AND conname = 'uq_generation_configs_session_id'
  ) THEN
    RAISE EXCEPTION 'Missing constraint uq_generation_configs_session_id on generation_configs';
  END IF;

  -- Triggers
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_exam_sessions_updated_at'
  ) THEN
    RAISE EXCEPTION 'Missing trigger trg_exam_sessions_updated_at';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_generation_configs_updated_at'
  ) THEN
    RAISE EXCEPTION 'Missing trigger trg_generation_configs_updated_at';
  END IF;

  RAISE NOTICE 'Step 1: All schema elements, columns, constraints, indexes, and triggers verified.';
END $$;

-- ----------------------------------------------------------------------------
-- 2. Verify Least-Privilege Permissions
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_has_auth BOOLEAN;
  v_has_service BOOLEAN;
BEGIN
  -- 2.1 finish_generation_job: service_role ONLY
  SELECT has_function_privilege('authenticated', 'public.finish_generation_job(UUID, TEXT, UUID)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on finish_generation_job!';
  END IF;
  SELECT has_function_privilege('service_role', 'public.finish_generation_job(UUID, TEXT, UUID)', 'EXECUTE') INTO v_has_service;
  IF v_has_service = FALSE THEN
    RAISE EXCEPTION 'Permission failure: service_role must have EXECUTE on finish_generation_job!';
  END IF;

  -- 2.2 fail_stale_generation_job: service_role ONLY
  SELECT has_function_privilege('authenticated', 'public.fail_stale_generation_job(UUID, INT)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on fail_stale_generation_job!';
  END IF;
  SELECT has_function_privilege('service_role', 'public.fail_stale_generation_job(UUID, INT)', 'EXECUTE') INTO v_has_service;
  IF v_has_service = FALSE THEN
    RAISE EXCEPTION 'Permission failure: service_role must have EXECUTE on fail_stale_generation_job!';
  END IF;

  -- 2.3 reserve_generation_quota: service_role ONLY
  SELECT has_function_privilege('authenticated', 'public.reserve_generation_quota(UUID, INT, UUID)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on reserve_generation_quota!';
  END IF;
  SELECT has_function_privilege('service_role', 'public.reserve_generation_quota(UUID, INT, UUID)', 'EXECUTE') INTO v_has_service;
  IF v_has_service = FALSE THEN
    RAISE EXCEPTION 'Permission failure: service_role must have EXECUTE on reserve_generation_quota!';
  END IF;

  -- 2.4 persist_version_question: service_role ONLY
  SELECT has_function_privilege('authenticated', 'public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on persist_version_question!';
  END IF;
  SELECT has_function_privilege('service_role', 'public.persist_version_question(UUID, UUID, INT, UUID, INT, TEXT, JSONB, TEXT, TEXT, BOOLEAN)', 'EXECUTE') INTO v_has_service;
  IF v_has_service = FALSE THEN
    RAISE EXCEPTION 'Permission failure: service_role must have EXECUTE on persist_version_question!';
  END IF;

  -- 2.5 is_valid_variation_modes: internal only
  SELECT has_function_privilege('authenticated', 'public.is_valid_variation_modes(JSONB)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on is_valid_variation_modes!';
  END IF;

  -- 2.6 Client functions: save_generation_config & claim_generation_job
  SELECT has_function_privilege('authenticated', 'public.save_generation_config(UUID, INT, JSONB, JSONB)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = FALSE THEN
    RAISE EXCEPTION 'Permission failure: authenticated role must have EXECUTE on save_generation_config!';
  END IF;

  SELECT has_function_privilege('authenticated', 'public.claim_generation_job(UUID, BOOLEAN)', 'EXECUTE') INTO v_has_auth;
  IF v_has_auth = FALSE THEN
    RAISE EXCEPTION 'Permission failure: authenticated role must have EXECUTE on claim_generation_job!';
  END IF;

  RAISE NOTICE 'Step 2: Least privilege permissions for all RPCs and helpers verified.';
END $$;

-- ----------------------------------------------------------------------------
-- 3. Functional & NULL-Semantics Unit Checks
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- current_role() must never return NULL
  IF public.current_role() IS NULL THEN
    RAISE EXCEPTION 'current_role() returned NULL! Must return anon when unset.';
  END IF;

  -- Variation modes validation with CASE protection
  IF NOT public.is_valid_variation_modes('["NUMERICAL"]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes failed for valid mode NUMERICAL';
  END IF;

  IF NOT public.is_valid_variation_modes('["  numerical  "]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes failed for padded lowercase numerical';
  END IF;

  IF NOT public.is_valid_variation_modes('[]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes failed for empty array []';
  END IF;

  -- NULL array input must return FALSE
  IF public.is_valid_variation_modes(NULL) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes(NULL) must evaluate to FALSE';
  END IF;

  -- Scalar/object must safely return FALSE via CASE without throw
  IF public.is_valid_variation_modes('{"not": "array"}'::jsonb) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes object must evaluate to FALSE';
  END IF;

  IF public.is_valid_variation_modes('"scalar_string"'::jsonb) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes scalar string must evaluate to FALSE';
  END IF;

  IF public.is_valid_variation_modes('123'::jsonb) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes scalar number must evaluate to FALSE';
  END IF;

  -- Array containing null element must return FALSE
  IF public.is_valid_variation_modes('["numerical", null]'::jsonb) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes with null element must evaluate to FALSE';
  END IF;

  RAISE NOTICE 'Step 3: All functional, domain, and NULL-semantics tests passed.';
END $$;

ROLLBACK;
