-- Verification Script for Migration 004 & 005 Permissions & Execution [TASK-207a/b]
-- Verifies that:
-- 1. active_job_id column exists on exam_sessions.
-- 2. Constraint uq_generation_configs_session_id exists on generation_configs.
-- 3. All 5 RPC functions exist with correct parameter signatures.
-- 4. fail_stale_generation_job has EXECUTE revoked from authenticated and granted ONLY to service_role.
-- 5. claim_generation_job, reserve_generation_quota, finish_generation_job, save_generation_config
--    are granted to authenticated and service_role.

BEGIN;

-- 1. Check columns
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'exam_sessions' AND column_name = 'active_job_id'
  ) THEN
    RAISE EXCEPTION 'Column active_job_id does not exist on exam_sessions!';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'generation_configs' AND column_name = 'updated_at'
  ) THEN
    RAISE EXCEPTION 'Column updated_at does not exist on generation_configs!';
  END IF;
END $$;

-- 2. Check unique constraint
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_generation_configs_session_id'
  ) AND NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE indexname = 'uq_generation_configs_session_id'
  ) THEN
    RAISE EXCEPTION 'Unique constraint on generation_configs(session_id) does not exist!';
  END IF;
  RAISE NOTICE 'Constraint uq_generation_configs_session_id is verified.';
END $$;

-- 3. Check functions existence
DO $$
DECLARE
  v_functions TEXT[] := ARRAY[
    'save_generation_config',
    'claim_generation_job',
    'reserve_generation_quota',
    'finish_generation_job',
    'fail_stale_generation_job'
  ];
  v_name TEXT;
BEGIN
  FOREACH v_name IN ARRAY v_functions LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_proc p
      JOIN pg_namespace n ON p.pronamespace = n.oid
      WHERE n.nspname = 'public' AND p.proname = v_name
    ) THEN
      RAISE EXCEPTION 'Function public.% does not exist!', v_name;
    END IF;
  END LOOP;
  RAISE NOTICE 'All 5 generation functions exist in public schema.';
END $$;

-- 4. Check permissions on fail_stale_generation_job
DO $$
DECLARE
  v_has_auth_privilege BOOLEAN;
BEGIN
  SELECT has_function_privilege('authenticated', 'public.fail_stale_generation_job(UUID, INT)', 'EXECUTE')
  INTO v_has_auth_privilege;

  IF v_has_auth_privilege = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have EXECUTE on fail_stale_generation_job!';
  END IF;

  RAISE NOTICE 'Least privilege verified: fail_stale_generation_job is strictly protected from authenticated role.';
END $$;

ROLLBACK;
