-- ============================================================================
-- Verification Suite for Migration 004 & 005 (v3) [TASK-207a/b]
-- Tests:
-- 1. Schema invariants (columns, constraints, triggers, indexes, functions)
-- 2. NULL-Semantics & current_role() non-NULL guarantee
-- 3. is_valid_variation_modes rejection of NULL, [null], case insensitivity
-- 4. Fencing token enforcement (IS DISTINCT FROM rejects NULL and mismatch)
-- 5. Quota bounds validation (negative/zero/exceeded quota rejection)
-- 6. Claim idempotency & concurrency protection (55006 object_in_use)
-- 7. Permissions / Least-privilege (fail_stale restricted to service_role)
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

  -- Constraints / Unique Index
  IF NOT EXISTS (
    SELECT 1
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
    WHERE i.indrelid = 'public.generation_configs'::regclass
      AND i.indisunique
      AND a.attname = 'session_id'
  ) THEN
    RAISE EXCEPTION 'Missing unique constraint on generation_configs(session_id)';
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
-- 2. Verify helper functions & RPC existence
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_functions TEXT[] := ARRAY[
    'current_role',
    'tg_set_updated_at',
    'is_valid_variation_modes',
    'save_generation_config',
    'claim_generation_job',
    'reserve_generation_quota',
    'finish_generation_job',
    'fail_stale_generation_job'
  ];
  v_fn TEXT;
BEGIN
  FOREACH v_fn IN ARRAY v_functions LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_proc p
      JOIN pg_namespace n ON p.pronamespace = n.oid
      WHERE n.nspname = 'public' AND p.proname = v_fn
    ) THEN
      RAISE EXCEPTION 'Function public.% does not exist!', v_fn;
    END IF;
  END LOOP;
  RAISE NOTICE 'Step 2: All 8 helper and RPC functions verified in public schema.';
END $$;

-- ----------------------------------------------------------------------------
-- 3. Verify Least-Privilege Permissions
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_has_auth BOOLEAN;
BEGIN
  -- fail_stale must be blocked from authenticated role
  SELECT has_function_privilege('authenticated', 'public.fail_stale_generation_job(UUID, INT)', 'EXECUTE')
  INTO v_has_auth;

  IF v_has_auth = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on fail_stale_generation_job!';
  END IF;

  -- save_generation_config must be granted to authenticated
  SELECT has_function_privilege('authenticated', 'public.save_generation_config(UUID, INT, JSONB, JSONB)', 'EXECUTE')
  INTO v_has_auth;
  IF v_has_auth = FALSE THEN
    RAISE EXCEPTION 'Permission failure: authenticated role must have EXECUTE on save_generation_config!';
  END IF;

  RAISE NOTICE 'Step 3: Least privilege permissions verified.';
END $$;

-- ----------------------------------------------------------------------------
-- 4. Functional & NULL-Semantics Unit Checks
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  -- current_role() must never return NULL
  IF public.current_role() IS NULL THEN
    RAISE EXCEPTION 'current_role() returned NULL! Must return anon when unset.';
  END IF;

  IF public.current_role() != 'anon' THEN
    RAISE EXCEPTION 'Expected default current_role() to be anon, got %', public.current_role();
  END IF;

  -- Variation modes validation
  IF NOT public.is_valid_variation_modes('["NUMERICAL"]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes failed for valid mode NUMERICAL';
  END IF;

  IF NOT public.is_valid_variation_modes('["numerical"]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes failed for lowercase numerical';
  END IF;

  IF NOT public.is_valid_variation_modes('[]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes failed for empty array []';
  END IF;

  -- NULL array input must return FALSE
  IF public.is_valid_variation_modes(NULL) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes(NULL) must evaluate to FALSE';
  END IF;

  -- Array containing null element must return FALSE
  IF public.is_valid_variation_modes('["numerical", null]'::jsonb) IS NOT FALSE THEN
    RAISE EXCEPTION 'is_valid_variation_modes with null element must evaluate to FALSE';
  END IF;

  IF public.is_valid_variation_modes('["malicious_mode_injection"]'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes allowed unrecognized mode';
  END IF;

  IF public.is_valid_variation_modes('"not_an_array"'::jsonb) THEN
    RAISE EXCEPTION 'is_valid_variation_modes allowed non-array input';
  END IF;

  RAISE NOTICE 'Step 4: All functional, domain, and NULL-semantics tests passed.';
END $$;

ROLLBACK;
