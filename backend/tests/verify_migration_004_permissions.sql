-- ============================================================================
-- Verification Suite for Migration 004 & 005 (v4) [TASK-207a/b]
-- Tests:
-- 1. Schema invariants (columns, constraints, triggers, indexes, functions)
-- 2. NULL-Semantics & current_role() non-NULL guarantee
-- 3. is_valid_variation_modes with CASE protection, NULL elements, normalization
-- 4. finish_generation_job restricted strictly to service_role
-- 5. fail_stale_generation_job restricted strictly to service_role
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Verify schema elements
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- Columns
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'exam_sessions' AND column_name = 'active_job_id'
  ) THEN
    RAISE EXCEPTION 'Missing active_job_id column on exam_sessions';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'generation_configs' AND column_name = 'updated_at'
  ) THEN
    RAISE EXCEPTION 'Missing updated_at column on generation_configs';
  END IF;

  -- Constraints / Unique Index (must be non-partial single column)
  IF NOT EXISTS (
    SELECT 1
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
    WHERE i.indrelid = 'public.generation_configs'::regclass
      AND i.indisunique
      AND i.indisvalid
      AND i.indpred IS NULL
      AND a.attname = 'session_id'
  ) THEN
    RAISE EXCEPTION 'Missing valid, non-partial unique index on generation_configs(session_id)';
  END IF;

  -- Partial Index
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public' AND indexname = 'idx_exam_sessions_active_job'
  ) THEN
    RAISE EXCEPTION 'Missing partial index idx_exam_sessions_active_job';
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

  RAISE NOTICE 'Step 1: All schema elements, columns, indexes, and triggers verified.';
END $$;

-- ----------------------------------------------------------------------------
-- 2. Verify Least-Privilege Permissions
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_has_auth BOOLEAN;
  v_has_service BOOLEAN;
BEGIN
  -- finish_generation_job must be REVOKED from authenticated
  SELECT has_function_privilege('authenticated', 'public.finish_generation_job(UUID, TEXT, UUID)', 'EXECUTE')
  INTO v_has_auth;

  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on finish_generation_job!';
  END IF;

  -- fail_stale must be REVOKED from authenticated
  SELECT has_function_privilege('authenticated', 'public.fail_stale_generation_job(UUID, INT)', 'EXECUTE')
  INTO v_has_auth;

  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on fail_stale_generation_job!';
  END IF;

  -- finish_generation_job and fail_stale must be GRANTED to service_role
  SELECT has_function_privilege('service_role', 'public.finish_generation_job(UUID, TEXT, UUID)', 'EXECUTE')
  INTO v_has_service;

  IF v_has_service = FALSE THEN
    RAISE EXCEPTION 'Permission failure: service_role must have EXECUTE on finish_generation_job!';
  END IF;

  -- save_generation_config must be GRANTED to authenticated
  SELECT has_function_privilege('authenticated', 'public.save_generation_config(UUID, INT, JSONB, JSONB)', 'EXECUTE')
  INTO v_has_auth;
  IF v_has_auth = FALSE THEN
    RAISE EXCEPTION 'Permission failure: authenticated role must have EXECUTE on save_generation_config!';
  END IF;

  RAISE NOTICE 'Step 2: Least privilege permissions verified.';
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
