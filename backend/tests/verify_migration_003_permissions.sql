-- ============================================================================
-- Verification Test Script: Migration 003 RPC Permissions, Concurrency & State Machine
-- Tests confirm_exam_source(p_session_id, p_expected_question_count, p_acknowledged_security_warnings, p_expected_updated_at)
--
-- Scenarios tested:
-- 1. anon caller: rejected (42501)
-- 2. authenticated non-owner caller: rejected (42501)
-- 3. authenticated caller with NULL/empty UID: rejected (42501)
-- 4. valid owner on non-draft session: rejected (22023)
-- 5. valid owner with outdated p_expected_updated_at (concurrent edit): rejected (22023)
-- 6. valid owner on session with unacknowledged security warnings: rejected (22023)
-- 7. valid owner on session with missing blueprints: rejected (22023)
-- 8. valid owner with question count mismatch: rejected (22023)
-- 9. valid owner on valid draft session with all blueprints: SUCCESS (200 equivalent)
-- 10. service_role caller on valid draft session: SUCCESS
--
-- Enclosed in a transaction with ROLLBACK to leave zero dirty test data.
-- ============================================================================

BEGIN;

DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'Starting Migration 003 Permissions & Integrity Test Suite...';
  RAISE NOTICE '============================================================';
END $$;

-- 1. Set up test sessions, questions, and blueprints
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
-- Scenario 1: Anon caller (rejected with 42501)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'anon', true);
    PERFORM set_config('request.jwt.claim.sub', '', true);
    PERFORM set_config('request.jwt.claims', '{"role": "anon"}'::text, true);

    PERFORM public.confirm_exam_source(v_draft_session_id, 2);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '42501' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 1 (anon): Correctly rejected with 42501 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 1 (anon): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 1 FAILED: anon caller was not rejected!';
  END IF;
END $$;

-- ----------------------------------------------------------------------------
-- Scenario 2: Authenticated non-owner (rejected with 42501)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_attacker_id TEXT := '22222222-2222-2222-2222-222222222222';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_attacker_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_attacker_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 3: Authenticated with NULL/empty UID claim (rejected with 42501)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', '', true);
    PERFORM set_config('request.jwt.claims', '{"role": "authenticated"}'::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 4: Valid owner on non-draft session (rejected with 22023)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_locked_session_id UUID := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 5: Valid owner with outdated expected updated_at (concurrent edit)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_stale_updated_at TIMESTAMPTZ := '2026-10-25 00:00:00+00';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 6: Unacknowledged security warnings (rejected with 22023)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_warning_session_id UUID := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

    PERFORM public.confirm_exam_source(
      v_warning_session_id,
      1,
      FALSE
    );
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_err_code = RETURNED_SQLSTATE, v_err_msg = MESSAGE_TEXT;
    IF v_err_code = '22023' AND v_err_msg LIKE '%security warnings%' THEN
      v_test_passed := TRUE;
      RAISE NOTICE '[PASS] Scenario 6 (unacknowledged warning): Correctly rejected with 22023 (%: %)', v_err_code, v_err_msg;
    ELSE
      RAISE WARNING '[FAIL] Scenario 6 (unacknowledged warning): Unexpected error code %: %', v_err_code, v_err_msg;
    END IF;
  END;

  IF NOT v_test_passed THEN
    RAISE EXCEPTION 'Scenario 6 FAILED: unacknowledged security warning was not rejected!';
  END IF;
END $$;

-- ----------------------------------------------------------------------------
-- Scenario 7: Question without blueprint (rejected with 22023, session remains draft)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_missing_bp_session_id UUID := 'dddddddd-dddd-dddd-dddd-dddddddddddd';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
  v_status public.session_status;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 8: Question count mismatch (rejected with 22023)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 9: Valid owner confirmation (SUCCESS)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_res JSONB;
  v_status public.session_status;
  v_confirmed_count INT;
BEGIN
  PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
  PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
  PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 10: Service role caller (SUCCESS)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
BEGIN
  -- Reset session back to draft for service_role test
  UPDATE public.exam_sessions SET status = 'draft', updated_at = '2026-10-26 00:00:00+00' WHERE id = v_draft_session_id;

  PERFORM set_config('request.jwt.claim.role', 'service_role', true);
  PERFORM set_config('request.jwt.claim.sub', '', true);
  PERFORM set_config('request.jwt.claims', '{"role": "service_role"}'::text, true);

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

DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'ALL MIGRATION 003 SCENARIOS PASSED (10/10)!';
  RAISE NOTICE '============================================================';
END $$;

-- Always rollback so test suite leaves zero dirty state in DB
ROLLBACK;
