-- ============================================================================
-- Verification Test Script: Migration 002 RPC Permissions & State Machine
-- Tests public.replace_source_questions(p_session_id, p_questions)
--
-- Tests 7 scenarios:
-- [PostgREST Caller Matrix (simulated via authenticator role switching)]
-- 1. anon caller: rejected (42501: permission denied for function / Least Privilege SEC-04)
-- 2. authenticated non-owner caller: rejected (42501: Access denied: not session owner)
-- 3. authenticated caller with NULL/empty UID: rejected (42501: Unauthorized: caller must be authenticated)
-- 4. valid owner caller on non-draft session: rejected (22023: session not in draft status)
-- 5. valid owner caller on draft session: SUCCESS (atomically replaced 2 questions, updated_at refreshed)
-- 6. service_role caller: SUCCESS (trusted internal role with bypass sub check)
--
-- [Direct Database Administrator]
-- 7. postgres / supabase_admin direct caller: SUCCESS (explicitly trusted session_user without JWT)
--
-- Enclosed in a transaction with ROLLBACK to leave zero dirty test data.
-- ============================================================================

-- Preflight setup (outside transaction if roles need creation):
-- In Supabase, anon, authenticated, service_role, authenticator exist by default.
-- When running in standalone PostgreSQL, ensure roles exist.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'CREATE ROLE anon NOLOGIN';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'CREATE ROLE authenticated NOLOGIN';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'CREATE ROLE service_role NOLOGIN';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
    EXECUTE 'CREATE ROLE authenticator NOINHERIT';
  END IF;

  -- Ensure authenticator can impersonate caller roles as in PostgREST
  GRANT anon TO authenticator;
  GRANT authenticated TO authenticator;
  GRANT service_role TO authenticator;

  -- Ensure PL/pgSQL language privilege
  GRANT USAGE ON LANGUAGE plpgsql TO PUBLIC;

  -- Ensure schema usage
  GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role, authenticator;
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
    GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role, authenticator;
    GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA auth TO anon, authenticated, service_role, authenticator;
  END IF;
EXCEPTION WHEN OTHERS THEN
  NULL;
END $$;

BEGIN;

DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'Starting Migration 002 Permissions & Security Test Suite...';
  RAISE NOTICE '============================================================';
END $$;

-- ----------------------------------------------------------------------------
-- 0. Fixtures Setup: Create prerequisite mock users and test sessions
-- Prevents Foreign Key violation (exam_sessions_user_id_fkey) on empty DB.
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_owner_id UUID := '11111111-1111-1111-1111-111111111111';
  v_attacker_id UUID := '22222222-2222-2222-2222-222222222222';
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_locked_session_id UUID := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
BEGIN
  -- Insert into auth.users if auth schema and table exist (Supabase GoTrue)
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
    INSERT INTO auth.users (id, email)
    VALUES 
      (v_owner_id, 'test_owner_002@example.com'),
      (v_attacker_id, 'test_attacker_002@example.com')
    ON CONFLICT (id) DO NOTHING;
  END IF;

  -- Insert into public.users (mirrors auth.users)
  INSERT INTO public.users (id, email, name)
  VALUES 
    (v_owner_id, 'test_owner_002@example.com', 'Test Owner 002'),
    (v_attacker_id, 'test_attacker_002@example.com', 'Test Attacker 002')
  ON CONFLICT (id) DO UPDATE 
    SET email = EXCLUDED.email, name = EXCLUDED.name;

  -- Insert dummy sessions
  INSERT INTO public.exam_sessions (id, user_id, title, status, created_at, updated_at)
  VALUES 
    (v_draft_session_id, v_owner_id, 'Draft Session for Test', 'draft', now() - interval '1 hour', now() - interval '1 hour'),
    (v_locked_session_id, v_owner_id, 'Locked Session for Test', 'generating', now() - interval '1 hour', now() - interval '1 hour')
  ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at;

  -- Insert existing source question in draft session to test replacement
  INSERT INTO public.source_questions (session_id, question_no, raw_content, options, correct_key)
  VALUES (v_draft_session_id, 1, 'Old Question Before Replace', '{"A": "1", "B": "2", "C": "3", "D": "4"}'::jsonb, 'A')
  ON CONFLICT DO NOTHING;

  -- Insert existing source question in locked session to test protection
  INSERT INTO public.source_questions (session_id, question_no, raw_content, options, correct_key)
  VALUES (v_locked_session_id, 1, 'Locked Question Must Not Change', '{"A": "1", "B": "2", "C": "3", "D": "4"}'::jsonb, 'A')
  ON CONFLICT DO NOTHING;
END $$;

-- ----------------------------------------------------------------------------
-- Scenario 1: Anon caller (Unauthenticated PostgREST Request)
-- Must be rejected with 42501 (insufficient_privilege) because EXECUTE privilege
-- was explicitly revoked from public and anon (SEC-04 Least Privilege).
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'anon', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '{"role": "anon"}'::text, true);

-- Switch session authorization to authenticator then impersonate anon role
SET SESSION AUTHORIZATION authenticator;
SET ROLE anon;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
  v_has_priv BOOLEAN;
BEGIN
  -- Verify Least Privilege metadata
  SELECT has_function_privilege('anon', 'public.replace_source_questions(UUID, JSONB)', 'EXECUTE')
  INTO v_has_priv;

  IF v_has_priv THEN
    RAISE EXCEPTION 'Scenario 1 Security Violation: anon role has EXECUTE privilege on replace_source_questions!';
  END IF;

  BEGIN
    PERFORM public.replace_source_questions(
      v_draft_session_id,
      '[{"question_no": 1, "raw_content": "Hacked", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '42501' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 1 (anon caller): Correctly rejected with 42501 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 1 (anon caller): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 1 FAILED: anon caller was not rejected!';
  END IF;
END $$;

RESET ROLE;
RESET SESSION AUTHORIZATION;

-- ----------------------------------------------------------------------------
-- Scenario 2: Authenticated non-owner caller (Attacker trying to modify victim's session)
-- Must be rejected with 42501 ("Access denied: not session owner").
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "22222222-2222-2222-2222-222222222222"}'::text, true);

SET SESSION AUTHORIZATION authenticator;
SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM public.replace_source_questions(
      v_draft_session_id,
      '[{"question_no": 1, "raw_content": "Attacker replaced", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '42501' AND v_err_msg LIKE '%Access denied%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 2 (non-owner caller): Correctly rejected with 42501 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 2 (non-owner caller): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 2 FAILED: non-owner caller was not rejected!';
  END IF;
END $$;

RESET ROLE;
RESET SESSION AUTHORIZATION;

-- ----------------------------------------------------------------------------
-- Scenario 3: Authenticated caller but missing UID (NULL/empty claim)
-- Must be rejected with 42501 ("Unauthorized: caller must be authenticated or have service role").
-- Under authenticator session_user, session_user IN ('postgres', 'supabase_admin') is FALSE.
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated"}'::text, true);

SET SESSION AUTHORIZATION authenticator;
SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM public.replace_source_questions(
      v_draft_session_id,
      '[{"question_no": 1, "raw_content": "UID-less replace", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '42501' AND v_err_msg LIKE '%Unauthorized%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 3 (UID-less authenticated caller): Correctly rejected with 42501 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 3 (UID-less authenticated caller): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 3 FAILED: UID-less caller was not rejected!';
  END IF;
END $$;

RESET ROLE;
RESET SESSION AUTHORIZATION;

-- ----------------------------------------------------------------------------
-- Scenario 4: Valid owner calling on non-draft (locked) session
-- Must be rejected with 22023 ("Cannot ingest questions: session is not in draft status").
-- Locked session questions must NOT be modified.
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET SESSION AUTHORIZATION authenticator;
SET ROLE authenticated;

DO $$
DECLARE
  v_locked_session_id UUID := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
  v_check_content TEXT;
BEGIN
  BEGIN
    PERFORM public.replace_source_questions(
      v_locked_session_id,
      '[{"question_no": 1, "raw_content": "Should Fail", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '22023' AND v_err_msg LIKE '%draft%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 4 (non-draft session): Correctly rejected with 22023 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 4 (non-draft session): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  -- Verify data was NOT changed
  SELECT raw_content INTO v_check_content FROM public.source_questions WHERE session_id = v_locked_session_id;
  IF v_check_content != 'Locked Question Must Not Change' THEN
    RAISE EXCEPTION 'Scenario 4 FAILED: locked session data was modified!';
  END IF;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 4 FAILED: non-draft session update was not rejected!';
  END IF;
END $$;

RESET ROLE;
RESET SESSION AUTHORIZATION;

-- ----------------------------------------------------------------------------
-- Scenario 5: Valid owner calling on draft session (Successful Replacement)
-- Must atomically replace existing questions with 2 new questions and update updated_at.
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET SESSION AUTHORIZATION authenticator;
SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
  v_count INT;
  v_q1_content TEXT;
  v_updated_at TIMESTAMPTZ;
BEGIN
  v_res := public.replace_source_questions(
    v_draft_session_id,
    '[
      {"question_no": 1, "raw_content": "New Question 1", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"},
      {"question_no": 2, "raw_content": "New Question 2", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "B"}
    ]'::jsonb
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'count')::INT != 2 THEN
    RAISE EXCEPTION 'Scenario 5 FAILED: unexpected return payload: %', v_res;
  END IF;

  SELECT COUNT(*) INTO v_count FROM public.source_questions WHERE session_id = v_draft_session_id;
  IF v_count != 2 THEN
    RAISE EXCEPTION 'Scenario 5 FAILED: expected 2 questions in DB, got %', v_count;
  END IF;

  SELECT raw_content INTO v_q1_content FROM public.source_questions WHERE session_id = v_draft_session_id AND question_no = 1;
  IF v_q1_content != 'New Question 1' THEN
    RAISE EXCEPTION 'Scenario 5 FAILED: question content mismatch: %', v_q1_content;
  END IF;

  SELECT updated_at INTO v_updated_at FROM public.exam_sessions WHERE id = v_draft_session_id;
  IF v_updated_at < (now() - interval '1 minute') THEN
    RAISE EXCEPTION 'Scenario 5 FAILED: updated_at was not refreshed!';
  END IF;

  RAISE NOTICE '[PASS] Scenario 5 (valid owner on draft): Successfully replaced 2 questions atomically and refreshed updated_at.';
END $$;

RESET ROLE;
RESET SESSION AUTHORIZATION;

-- ----------------------------------------------------------------------------
-- Scenario 6: Service role caller (Backend Service Role Key)
-- Authorized internal backend service role bypassing sub/ownership check.
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'service_role', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '{"role": "service_role"}'::text, true);

SET SESSION AUTHORIZATION authenticator;
SET ROLE service_role;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
  v_count INT;
BEGIN
  v_res := public.replace_source_questions(
    v_draft_session_id,
    '[{"question_no": 1, "raw_content": "Service Role Ingested", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'count')::INT != 1 THEN
    RAISE EXCEPTION 'Scenario 6 FAILED: unexpected service_role payload: %', v_res;
  END IF;

  SELECT COUNT(*) INTO v_count FROM public.source_questions WHERE session_id = v_draft_session_id;
  IF v_count != 1 THEN
    RAISE EXCEPTION 'Scenario 6 FAILED: expected 1 question in DB, got %', v_count;
  END IF;

  RAISE NOTICE '[PASS] Scenario 6 (service_role caller): Successfully authorized and replaced questions.';
END $$;

RESET ROLE;
RESET SESSION AUTHORIZATION;

-- ----------------------------------------------------------------------------
-- Scenario 7: Direct Database Administrator (postgres / supabase_admin)
-- RPC explicitly trusts session_user IN ('postgres', 'supabase_admin')
-- Direct DB administrator maintenance call without any JWT claims must succeed.
-- ----------------------------------------------------------------------------
RESET ROLE;
RESET SESSION AUTHORIZATION;

-- Explicitly clear all JWT claims
SELECT set_config('request.jwt.claim.role', '', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '', true);

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
  v_count INT;
  v_current_session_user TEXT := session_user;
BEGIN
  -- Validate that current session_user is an administrator
  IF v_current_session_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE WARNING 'Scenario 7 Notice: current session_user is %, expected postgres or supabase_admin', v_current_session_user;
  END IF;

  v_res := public.replace_source_questions(
    v_draft_session_id,
    '[{"question_no": 1, "raw_content": "Direct Admin Maintenance Ingest", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'count')::INT != 1 THEN
    RAISE EXCEPTION 'Scenario 7 FAILED: unexpected admin payload: %', v_res;
  END IF;

  SELECT COUNT(*) INTO v_count FROM public.source_questions WHERE session_id = v_draft_session_id;
  IF v_count != 1 THEN
    RAISE EXCEPTION 'Scenario 7 FAILED: expected 1 question in DB, got %', v_count;
  END IF;

  RAISE NOTICE '[PASS] Scenario 7 (direct db admin): Successfully authorized via session_user trust (%) without JWT claims.', v_current_session_user;
END $$;

-- ----------------------------------------------------------------------------
-- Summary Banner
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'ALL MIGRATION 002 SECURITY SCENARIOS PASSED (7/7)!';
  RAISE NOTICE '  - Scenarios 1-6: Simulated PostgREST callers (authenticator -> anon/auth/service_role)';
  RAISE NOTICE '  - Scenario 7: Direct DB Admin caller (session_user = postgres/supabase_admin)';
  RAISE NOTICE '============================================================';
END $$;

-- Always rollback so test suite leaves zero dirty state in DB
ROLLBACK;
