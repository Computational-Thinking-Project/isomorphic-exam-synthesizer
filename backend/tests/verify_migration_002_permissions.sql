-- ============================================================================
-- Verification Test Script: Migration 002 RPC Permissions & State Machine
-- Tests replace_source_questions(p_session_id, p_questions)
--
-- Tests the 5 matrix scenarios:
-- 1. anon caller: rejected (permission denied / 42501)
-- 2. authenticated non-owner caller: rejected (Access denied: not session owner / 42501)
-- 3. authenticated caller with NULL/empty UID: rejected (Unauthorized / 42501)
-- 4. valid owner caller on non-draft session: rejected (session not in draft status / 22023)
-- 5. valid owner caller on draft session: SUCCESS (atomically replaced)
-- 6. service_role caller: SUCCESS (trusted internal role)
--
-- Enclosed in a transaction with ROLLBACK to leave zero dirty test data.
-- ============================================================================

BEGIN;

-- Helper notices
DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'Starting Migration 002 Permissions & Security Test Suite...';
  RAISE NOTICE '============================================================';
END $$;

-- 1. Create mock users and test sessions
DO $$
DECLARE
  v_owner_id UUID := '11111111-1111-1111-1111-111111111111';
  v_attacker_id UUID := '22222222-2222-2222-2222-222222222222';
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_locked_session_id UUID := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
BEGIN
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
-- Scenario 1: Anon caller (No JWT / anon role)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    -- Simulate PostgREST anon environment
    PERFORM set_config('request.jwt.claim.role', 'anon', true);
    PERFORM set_config('request.jwt.claim.sub', '', true);
    PERFORM set_config('request.jwt.claims', '{"role": "anon"}'::text, true);

    PERFORM public.replace_source_questions(
      v_draft_session_id,
      '[{"question_no": 1, "raw_content": "Hacked", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
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
-- Scenario 2: Authenticated caller attempting to modify another user session
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
    -- Simulate PostgREST authenticated as attacker
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_attacker_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_attacker_id)::text, true);

    PERFORM public.replace_source_questions(
      v_draft_session_id,
      '[{"question_no": 1, "raw_content": "Attacker replaced", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
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
-- Scenario 3: Caller authenticated but missing auth.uid() (NULL/empty claim)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
BEGIN
  BEGIN
    -- Simulate authenticated without sub
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', '', true);
    PERFORM set_config('request.jwt.claims', '{"role": "authenticated"}'::text, true);

    PERFORM public.replace_source_questions(
      v_draft_session_id,
      '[{"question_no": 1, "raw_content": "UID-less replace", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
    );
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
-- Scenario 4: Valid owner calling on non-draft (locked) session
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_locked_session_id UUID := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_test_passed BOOLEAN := FALSE;
  v_err_code TEXT;
  v_err_msg TEXT;
  v_check_content TEXT;
BEGIN
  BEGIN
    -- Simulate valid owner
    PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
    PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
    PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 5: Valid owner calling on draft session (Successful Replacement)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_owner_id TEXT := '11111111-1111-1111-1111-111111111111';
  v_res JSONB;
  v_count INT;
  v_q1_content TEXT;
  v_updated_at TIMESTAMPTZ;
BEGIN
  -- Simulate valid owner
  PERFORM set_config('request.jwt.claim.role', 'authenticated', true);
  PERFORM set_config('request.jwt.claim.sub', v_owner_id, true);
  PERFORM set_config('request.jwt.claims', json_build_object('role', 'authenticated', 'sub', v_owner_id)::text, true);

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

-- ----------------------------------------------------------------------------
-- Scenario 6: Service role caller (Backend Service Role Key)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_draft_session_id UUID := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  v_res JSONB;
BEGIN
  -- Simulate service_role (sub can be null)
  PERFORM set_config('request.jwt.claim.role', 'service_role', true);
  PERFORM set_config('request.jwt.claim.sub', '', true);
  PERFORM set_config('request.jwt.claims', '{"role": "service_role"}'::text, true);

  v_res := public.replace_source_questions(
    v_draft_session_id,
    '[{"question_no": 1, "raw_content": "Service Role Ingested", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct_key": "A"}]'::jsonb
  );

  IF (v_res->>'success')::BOOLEAN != TRUE OR (v_res->>'count')::INT != 1 THEN
    RAISE EXCEPTION 'Scenario 6 FAILED: unexpected service_role payload: %', v_res;
  END IF;

  RAISE NOTICE '[PASS] Scenario 6 (service_role): Successfully authorized and replaced questions.';
END $$;

DO $$
BEGIN
  RAISE NOTICE '============================================================';
  RAISE NOTICE 'ALL MIGRATION 002 SECURITY SCENARIOS PASSED (6/6)!';
  RAISE NOTICE '============================================================';
END $$;

-- Always rollback so test suite leaves zero dirty state in DB
ROLLBACK;
