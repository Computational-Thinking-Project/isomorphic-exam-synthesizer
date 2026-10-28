-- ============================================================================
-- Verification Test Script: Migration 003 RPC Permissions, Concurrency & State Machine
-- Tests public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ)
--
-- Scenarios tested:
-- [PostgREST Caller Matrix (simulated via authenticator role switching)]
-- 1. anon caller: rejected (42501: permission denied for function / Least Privilege SEC-04)
-- 2. authenticated non-owner caller: rejected (42501: Access denied: not session owner)
-- 3. authenticated caller with NULL/empty UID: rejected (42501: Unauthorized: caller must be authenticated)
-- 4. valid owner on non-draft session: rejected (22023: session not in draft status)
-- 5. valid owner with outdated p_expected_updated_at (concurrent edit): rejected (22023)
-- 6. valid owner on session with security warnings: SUCCESS (ADR-004 Silent Audit)
-- 7. valid owner on session with missing blueprints: rejected (22023)
-- 8. valid owner with question count mismatch: rejected (22023)
-- 9. valid owner on valid draft session with all blueprints: SUCCESS (200 equivalent)
-- 10. service_role caller on valid draft session: SUCCESS
--
-- [Direct Database Administrator]
-- 11. postgres / supabase_admin direct caller: SUCCESS (trusted session_user without JWT claims)
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

  -- Ensure current session user (e.g. postgres in Supabase Cloud SQL Editor) can switch roles
  BEGIN
    EXECUTE format('GRANT anon, authenticated, service_role TO %I', session_user);
  EXCEPTION WHEN OTHERS THEN
    NULL;
  END;

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
  RAISE NOTICE 'Starting Migration 003 Permissions & Integrity Test Suite...';
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
  v_warning_session_id UUID := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
  v_missing_bp_session_id UUID := 'dddddddd-dddd-dddd-dddd-dddddddddddd';
  v_sq_id1 UUID := '10000000-0000-0000-0000-000000000001';
  v_sq_id2 UUID := '10000000-0000-0000-0000-000000000002';
  v_sq_w1 UUID := '20000000-0000-0000-0000-000000000001';
  v_sq_mbp1 UUID := '30000000-0000-0000-0000-000000000001';
BEGIN
  -- Insert into auth.users if auth schema and table exist (Supabase GoTrue)
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
    INSERT INTO auth.users (id, email)
    VALUES 
      (v_owner_id, 'test_owner_003@example.com'),
      (v_attacker_id, 'test_attacker_003@example.com')
    ON CONFLICT (id) DO NOTHING;
  END IF;

  -- Insert into public.users (mirrors auth.users)
  INSERT INTO public.users (id, email, name)
  VALUES 
    (v_owner_id, 'test_owner_003@example.com', 'Test Owner 003'),
    (v_attacker_id, 'test_attacker_003@example.com', 'Test Attacker 003')
  ON CONFLICT (id) DO UPDATE 
    SET email = EXCLUDED.email, name = EXCLUDED.name;

  -- Insert dummy sessions
  INSERT INTO public.exam_sessions (id, user_id, title, status, created_at, updated_at)
  VALUES 
    (v_draft_session_id, v_owner_id, 'Draft Session for Test', 'draft', now() - interval '1 hour', '2026-10-26 00:00:00+00'),
    (v_locked_session_id, v_owner_id, 'Locked Session for Test', 'blueprinted', now() - interval '1 hour', now() - interval '1 hour'),
    (v_warning_session_id, v_owner_id, 'Warning Session for Test', 'draft', now() - interval '1 hour', now() - interval '1 hour'),
    (v_missing_bp_session_id, v_owner_id, 'Missing BP Session', 'draft', now() - interval '1 hour', now() - interval '1 hour')
  ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at;

  -- 1a. Questions and blueprints for v_draft_session_id (2 questions, 2 blueprints)
  INSERT INTO public.source_questions (id, session_id, question_no, raw_content, options, correct_key, has_missing_answer, has_security_warning)
  VALUES 
    (v_sq_id1, v_draft_session_id, 1, 'Question 1: Cho x = 5', '{"A": "1", "B": "2", "C": "3", "D": "4"}'::jsonb, 'A', FALSE, FALSE),
    (v_sq_id2, v_draft_session_id, 2, 'Question 2: Cho y = 10', '{"A": "1", "B": "2", "C": "3", "D": "4"}'::jsonb, 'B', FALSE, FALSE)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.question_blueprints (source_question_id, variables, domains, invariants, variation_modes, is_fallback, extraction_source)
  VALUES 
    (v_sq_id1, '{"param_1": 5}'::jsonb, '{"param_1": {"min": 0, "max": 10}}'::jsonb, '["PRESERVE_SOLVABILITY"]'::jsonb, '["NUMERICAL"]'::jsonb, TRUE, 'FALLBACK_DETERMINISTIC'),
    (v_sq_id2, '{"param_1": 10}'::jsonb, '{"param_1": {"min": 5, "max": 15}}'::jsonb, '["PRESERVE_SOLVABILITY"]'::jsonb, '["NUMERICAL"]'::jsonb, TRUE, 'FALLBACK_DETERMINISTIC')
  ON CONFLICT (source_question_id) DO NOTHING;

  -- 1b. Questions with security warning
  INSERT INTO public.source_questions (id, session_id, question_no, raw_content, options, correct_key, has_missing_answer, has_security_warning)
  VALUES (v_sq_w1, v_warning_session_id, 1, 'Question with Warning', '{"A": "1", "B": "2", "C": "3", "D": "4"}'::jsonb, 'A', FALSE, TRUE)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.question_blueprints (source_question_id, variables, domains, invariants, variation_modes, is_fallback, extraction_source)
  VALUES (v_sq_w1, '{}'::jsonb, '{}'::jsonb, '["PRESERVE_SOLVABILITY"]'::jsonb, '["NONE"]'::jsonb, TRUE, 'FALLBACK_DETERMINISTIC')
  ON CONFLICT (source_question_id) DO NOTHING;

  -- 1c. Question without blueprint
  INSERT INTO public.source_questions (id, session_id, question_no, raw_content, options, correct_key, has_missing_answer, has_security_warning)
  VALUES (v_sq_mbp1, v_missing_bp_session_id, 1, 'Question without Blueprint', '{"A": "1", "B": "2", "C": "3", "D": "4"}'::jsonb, 'A', FALSE, FALSE)
  ON CONFLICT (id) DO NOTHING;
END $$;

-- ----------------------------------------------------------------------------
-- Scenario 1: Anon caller (Unauthenticated PostgREST Request)
-- Must be rejected with 42501 (insufficient_privilege) because EXECUTE privilege
-- was explicitly revoked from public and anon (SEC-04 Least Privilege).
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'anon', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '{"role": "anon"}'::text, true);

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
  SELECT has_function_privilege('anon', 'public.confirm_exam_source(UUID, INT, BOOLEAN, TIMESTAMPTZ)', 'EXECUTE')
  INTO v_has_priv;

  IF v_has_priv THEN
    RAISE EXCEPTION 'Scenario 1 Security Violation: anon role has EXECUTE privilege on confirm_exam_source!';
  END IF;

  BEGIN
    PERFORM public.confirm_exam_source(v_draft_session_id, 2);
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

-- ----------------------------------------------------------------------------
-- Scenario 2: Authenticated non-owner caller (Attacker trying to confirm victim's session)
-- Must be rejected with 42501 ("Access denied: not session owner").
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "22222222-2222-2222-2222-222222222222"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM public.confirm_exam_source(v_draft_session_id, 2);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '42501' AND v_err_msg LIKE '%Access denied%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 2 (non-owner): Correctly rejected with 42501 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 2 (non-owner): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 2 FAILED: non-owner caller was not rejected!';
  END IF;
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 3: Authenticated with NULL/empty UID claim (rejected with 42501)
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM public.confirm_exam_source(v_draft_session_id, 2);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '42501' AND v_err_msg LIKE '%Unauthorized%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 3 (UID-less authenticated): Correctly rejected with 42501 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 3 (UID-less authenticated): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 3 FAILED: UID-less caller was not rejected!';
  END IF;
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 4: Valid owner on non-draft session (rejected with 22023)
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_locked_session_id UUID := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM public.confirm_exam_source(v_locked_session_id, 1);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '22023' AND v_err_msg LIKE '%draft%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 4 (non-draft session): Correctly rejected with 22023 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 4 (non-draft session): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 4 FAILED: non-draft session confirmation was not rejected!';
  END IF;
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 5: Valid owner with outdated expected updated_at (concurrent edit)
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_stale_updated_at TIMESTAMPTZ := '2026-10-25 00:00:00+00';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM public.confirm_exam_source(
      v_draft_session_id,
      2,
      FALSE,
      v_stale_updated_at
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '22023' AND v_err_msg LIKE '%concurrently%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 5 (concurrent update mismatch): Correctly rejected with 22023 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 5 (concurrent update mismatch): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 5 FAILED: concurrent modification was not detected!';
  END IF;
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 6: Valid owner on session with security warnings (ADR-004: SUCCESS via Silent Audit)
-- Per ADR-004, security warnings are logged silently and do NOT block confirmation in RPC.
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_warning_session_id UUID := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
  v_res JSONB;
BEGIN
  v_res := public.confirm_exam_source(
    v_warning_session_id,
    1,
    FALSE
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'status') != 'blueprinted' THEN
    RAISE EXCEPTION 'Scenario 6 FAILED: ADR-004 confirmation with security warnings should succeed, got: %', v_res;
  END IF;

  -- Verify persistent audit entry in public.security_events (ADR-004 & F02 requirement)
  IF NOT EXISTS (
    SELECT 1 FROM public.security_events
    WHERE session_id = v_warning_session_id
      AND event_type = 'PROMPT_INJECTION_DETECTED'
  ) THEN
    RAISE EXCEPTION 'Scenario 6 FAILED: ADR-004 persistent audit record not created in security_events table';
  END IF;

  RAISE NOTICE '[PASS] Scenario 6 (ADR-004 security warning silent audit): Successfully confirmed session and verified persistent security_events record.';
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 7: Question without blueprint (rejected with 22023, session remains draft)
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_missing_bp_session_id UUID := 'dddddddd-dddd-dddd-dddd-dddddddddddd';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
  v_status public.session_status;
BEGIN
  BEGIN
    PERFORM public.confirm_exam_source(
      v_missing_bp_session_id,
      1,
      FALSE
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '22023' AND v_err_msg LIKE '%missing blueprints%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 7 (missing blueprint): Correctly rejected with 22023 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 7 (missing blueprint): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  -- Ensure session state was NOT modified
  SELECT status INTO v_status FROM public.exam_sessions WHERE id = v_missing_bp_session_id;
  IF v_status != 'draft' THEN
    RAISE EXCEPTION 'Scenario 7 FAILED: session status was corrupted to %', v_status;
  END IF;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 7 FAILED: missing blueprint was not rejected!';
  END IF;
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 8: Question count mismatch (rejected with 22023)
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    -- Expected count is 99, but session only has 2
    PERFORM public.confirm_exam_source(v_draft_session_id, 99);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '22023' AND v_err_msg LIKE '%mismatch%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 8 (count mismatch): Correctly rejected with 22023 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 8 (count mismatch): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 8 FAILED: count mismatch was not rejected!';
  END IF;
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 9: Valid owner confirmation (SUCCESS)
-- ----------------------------------------------------------------------------
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
SELECT set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
SELECT set_config('request.jwt.claims', '{"role": "authenticated", "sub": "11111111-1111-1111-1111-111111111111"}'::text, true);

SET ROLE authenticated;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
  v_status public.session_status;
  v_confirmed_count INT;
BEGIN
  v_res := public.confirm_exam_source(
    v_draft_session_id,
    2,
    FALSE,
    '2026-10-26 00:00:00+00'::timestamptz
  );

  IF (v_res->>'success')::BOOLEAN != TRUE 
     OR (v_res->>'status') != 'blueprinted' 
     OR (v_res->>'total_questions')::INT != 2 
     OR (v_res->>'total_blueprints')::INT != 2 THEN
    RAISE EXCEPTION 'Scenario 9 FAILED: unexpected return payload: %', v_res;
  END IF;

  SELECT status INTO v_status FROM public.exam_sessions WHERE id = v_draft_session_id;
  IF v_status != 'blueprinted' THEN
    RAISE EXCEPTION 'Scenario 9 FAILED: session status is %, expected blueprinted', v_status;
  END IF;

  SELECT COUNT(*) INTO v_confirmed_count 
  FROM public.question_blueprints 
  WHERE source_question_id IN (SELECT id FROM public.source_questions WHERE session_id = v_draft_session_id)
    AND confirmed_at IS NOT NULL;

  IF v_confirmed_count != 2 THEN
    RAISE EXCEPTION 'Scenario 9 FAILED: expected 2 confirmed blueprints, found %', v_confirmed_count;
  END IF;

  RAISE NOTICE '[PASS] Scenario 9 (valid owner): Successfully confirmed session, stamped 2 blueprints, status=blueprinted.';
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 10: Service role caller (SUCCESS)
-- ----------------------------------------------------------------------------
-- Reset session back to draft for service_role test
UPDATE public.exam_sessions SET status = 'draft', updated_at = '2026-10-26 00:00:00+00' WHERE id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

SELECT set_config('request.jwt.claim.role', 'service_role', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '{"role": "service_role"}'::text, true);

SET ROLE service_role;

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
BEGIN
  v_res := public.confirm_exam_source(
    v_draft_session_id,
    2,
    FALSE,
    '2026-10-26 00:00:00+00'::timestamptz
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'total_blueprints')::INT != 2 THEN
    RAISE EXCEPTION 'Scenario 10 FAILED: service_role execution failed: %', v_res;
  END IF;

  RAISE NOTICE '[PASS] Scenario 10 (service_role): Successfully authorized and confirmed exam source.';
END $$;

RESET ROLE;

-- ----------------------------------------------------------------------------
-- Scenario 11: Direct Database Administrator (postgres / supabase_admin)
-- RPC explicitly trusts session_user IN ('postgres', 'supabase_admin')
-- Direct DB administrator maintenance call without any JWT claims must succeed.
-- ----------------------------------------------------------------------------
RESET ROLE;

-- Explicitly clear all JWT claims
SELECT set_config('request.jwt.claim.role', '', true);
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT set_config('request.jwt.claims', '', true);

-- Reset session back to draft for direct admin test
UPDATE public.exam_sessions SET status = 'draft', updated_at = '2026-10-26 00:00:00+00' WHERE id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
  v_current_session_user TEXT := session_user;
BEGIN
  -- Validate that current session_user is an administrator
  IF v_current_session_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE WARNING 'Scenario 11 Notice: current session_user is %, expected postgres or supabase_admin', v_current_session_user;
  END IF;

  v_res := public.confirm_exam_source(
    v_draft_session_id,
    2,
    FALSE,
    '2026-10-26 00:00:00+00'::timestamptz
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'status') != 'blueprinted' THEN
    RAISE EXCEPTION 'Scenario 11 FAILED: unexpected admin payload: %', v_res;
  END IF;

  RAISE NOTICE '[PASS] Scenario 11 (direct db admin): Successfully authorized via session_user trust (%) without JWT claims.', v_current_session_user;
END $$;

-- ----------------------------------------------------------------------------
-- Summary Banner
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'ALL MIGRATION 003 SECURITY SCENARIOS PASSED (11/11)!';
  RAISE NOTICE '  - Scenarios 1-10: Simulated PostgREST callers (authenticator -> anon/auth/service_role)';
  RAISE NOTICE '  - Scenario 11: Direct DB Admin caller (session_user = postgres/supabase_admin)';
  RAISE NOTICE '============================================================';
END $$;

-- Always rollback so test suite leaves zero dirty state in DB
ROLLBACK;
