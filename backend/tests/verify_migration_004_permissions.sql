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

  -- Worker columns guard trigger (F07)
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_guard_exam_sessions_worker_columns'
  ) THEN
    RAISE EXCEPTION 'Missing trigger trg_guard_exam_sessions_worker_columns';
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

  -- 2.7 Column-level security (F07):
  -- authenticated role must NOT have table-level UPDATE or INSERT
  IF has_table_privilege('authenticated', 'public.exam_sessions', 'UPDATE') = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have table-level UPDATE on exam_sessions!';
  END IF;

  IF has_table_privilege('authenticated', 'public.exam_sessions', 'INSERT') = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have table-level INSERT on exam_sessions!';
  END IF;

  -- authenticated role must NOT have column-level UPDATE on protected worker/lifecycle columns
  IF has_column_privilege('authenticated', 'public.exam_sessions', 'active_job_id', 'UPDATE') = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have direct UPDATE on exam_sessions.active_job_id!';
  END IF;

  IF has_column_privilege('authenticated', 'public.exam_sessions', 'gemini_call_count', 'UPDATE') = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have direct UPDATE on exam_sessions.gemini_call_count!';
  END IF;

  IF has_column_privilege('authenticated', 'public.exam_sessions', 'status', 'UPDATE') = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have direct UPDATE on exam_sessions.status!';
  END IF;

  IF has_column_privilege('authenticated', 'public.exam_sessions', 'status', 'INSERT') = TRUE THEN
    RAISE EXCEPTION 'Security failure: authenticated role must NOT have direct INSERT on exam_sessions.status!';
  END IF;

  -- authenticated role MUST have UPDATE & INSERT only on allowed metadata columns
  IF has_column_privilege('authenticated', 'public.exam_sessions', 'title', 'UPDATE') = FALSE THEN
    RAISE EXCEPTION 'Permission failure: authenticated role must have column UPDATE on exam_sessions.title!';
  END IF;

  IF has_column_privilege('authenticated', 'public.exam_sessions', 'title', 'INSERT') = FALSE THEN
    RAISE EXCEPTION 'Permission failure: authenticated role must have column INSERT on exam_sessions.title!';
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

-- ----------------------------------------------------------------------------
-- 4. Functional Attack Simulation & Defense-in-Depth Verification (F07)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_test_session_id UUID := '22222222-2222-2222-2222-222222222222'::uuid;
  v_test_user_id UUID := '00000000-0000-0000-0000-000000000001'::uuid;
  v_claim_res JSONB;
  v_quota_val INT;
  v_attack_succeeded BOOLEAN := FALSE;
BEGIN
  -- Ensure test user exists in auth.users & public.users
  INSERT INTO auth.users (id, email) VALUES (v_test_user_id, 'f07_test@example.com') ON CONFLICT DO NOTHING;
  INSERT INTO public.users (id, email, name) VALUES (v_test_user_id, 'f07_test@example.com', 'F07 Test User') ON CONFLICT DO NOTHING;

  -- Setup test session owned by v_test_user_id in configured state with quota=250
  INSERT INTO public.exam_sessions (id, user_id, title, status, gemini_call_count, active_job_id)
  VALUES (v_test_session_id, v_test_user_id, 'F07 Guard Test Exam', 'configured', 250, NULL)
  ON CONFLICT (id) DO UPDATE SET status='configured', gemini_call_count=250, active_job_id=NULL;

  INSERT INTO public.generation_configs (session_id, n_versions, active_variation_modes)
  VALUES (v_test_session_id, 2, '[]'::jsonb)
  ON CONFLICT (session_id) DO NOTHING;

  -- 4.1 Probe 1: Same-transaction claim followed by direct UPDATE under authenticated role
  -- Must be rejected by Column-level permissions
  PERFORM set_config('role', 'authenticated', true);
  PERFORM set_config('request.jwt.claim.sub', v_test_user_id::text, true);
  PERFORM set_config('request.jwt.claim.role', 'authenticated', true);

  -- Claim job legitimately
  v_claim_res := public.claim_generation_job(v_test_session_id, false);
  IF v_claim_res->>'status' != 'generating' THEN
    RAISE EXCEPTION 'claim_generation_job failed during test setup';
  END IF;

  -- Attempt direct UPDATE in same transaction
  BEGIN
    UPDATE public.exam_sessions SET gemini_call_count = 0 WHERE id = v_test_session_id;
    v_attack_succeeded := TRUE;
  EXCEPTION
    WHEN insufficient_privilege THEN
      v_attack_succeeded := FALSE;
  END;

  IF v_attack_succeeded THEN
    RAISE EXCEPTION 'Security failure (F07): direct UPDATE succeeded after claim in same transaction!';
  END IF;

  -- Reset role to test defense-in-depth trigger
  PERFORM set_config('role', 'postgres', true);

  -- 4.2 Probe 2: Defense-in-depth trigger under simulated table-level grant and manual GUC flag
  -- Even if table-level UPDATE is accidentally granted and client sets custom GUC, trigger must reject!
  EXECUTE 'GRANT UPDATE ON TABLE public.exam_sessions TO authenticated';
  PERFORM set_config('role', 'authenticated', true);
  PERFORM set_config('app.internal_worker_rpc', 'true', true);

  BEGIN
    UPDATE public.exam_sessions SET gemini_call_count = 0 WHERE id = v_test_session_id;
    v_attack_succeeded := TRUE;
  EXCEPTION
    WHEN insufficient_privilege THEN
      v_attack_succeeded := FALSE;
  END;

  IF v_attack_succeeded THEN
    RAISE EXCEPTION 'Security failure (F07): trigger failed to block worker column update under table grant / GUC!';
  END IF;

  -- Cleanup temporary grant
  PERFORM set_config('role', 'postgres', true);
  EXECUTE 'REVOKE UPDATE ON TABLE public.exam_sessions FROM authenticated';
  EXECUTE 'GRANT UPDATE (title, subject, grade) ON TABLE public.exam_sessions TO authenticated';

  -- Verify DB value remained 250
  SELECT gemini_call_count INTO v_quota_val FROM public.exam_sessions WHERE id = v_test_session_id;
  IF v_quota_val != 250 THEN
    RAISE EXCEPTION 'Security failure (F07): quota value was corrupted to %', v_quota_val;
  END IF;

  RAISE NOTICE 'Step 4: All F07 attack probes and defense-in-depth tests passed.';
END $$;

ROLLBACK;
