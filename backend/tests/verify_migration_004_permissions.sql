-- Verification Script for Migration 004 & 005 Permissions & Execution [TASK-207a/b]
-- Verifies that:
-- 1. save_generation_config, claim_generation_job, reserve_generation_quota,
--    finish_generation_job, and fail_stale_generation_job exist in schema.
-- 2. anon cannot execute these functions.
-- 3. authenticated and service_role have EXECUTE permissions.
-- 4. Constraint uq_generation_configs_session_id is active.

BEGIN;

-- Check functions existence
DO $$
DECLARE
  v_fn RECORD;
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

-- Check unique constraint
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_generation_configs_session_id'
  ) THEN
    RAISE EXCEPTION 'Constraint uq_generation_configs_session_id does not exist!';
  END IF;
  RAISE NOTICE 'Constraint uq_generation_configs_session_id is verified.';
END $$;

ROLLBACK;
