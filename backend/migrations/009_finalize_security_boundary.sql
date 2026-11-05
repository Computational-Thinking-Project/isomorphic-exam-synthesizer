-- TASK-305 review F01-F03: forward upgrade after 006,007,008.
BEGIN;

CREATE OR REPLACE FUNCTION public.finalize_approve_session(
  p_session_id UUID,
  p_user_id UUID DEFAULT NULL,
  p_expected_updated_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session RECORD;
  v_caller_id UUID;
  -- JWT claim GUCs can be set by a SQL caller; they must not elevate the
  -- database principal. SECURITY DEFINER changes current_user, so retain the
  -- role selected by the connection, falling back to the login role.
  v_role TEXT := COALESCE(NULLIF(current_setting('role', true), 'none'), session_user);
  v_config_count INT := 0;
  v_min_n_versions INT;
  v_max_n_versions INT;
  v_expected_versions INT;
  v_total_versions INT := 0;
  v_finalized_versions INT := 0;
  v_regenerating_count INT := 0;
  v_total_current_q INT := 0;
  v_approved_current_q INT := 0;
  v_progress JSONB;
  v_source_count INT;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  -- 1. Resolve authenticated caller ID (F16 Actor Spoofing Fix)
  -- For service_role: trust p_user_id or fallback to auth.uid() / JWT claims
  -- For authenticated / client role: strictly resolve from auth.uid() or JWT sub, NEVER trust p_user_id
  IF v_role = 'service_role' THEN
    v_caller_id := COALESCE(
      p_user_id,
      auth.uid(),
      CASE
        WHEN NULLIF(current_setting('request.jwt.claim.sub', true), '') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN NULLIF(current_setting('request.jwt.claim.sub', true), '')::UUID
        WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL
             AND (current_setting('request.jwt.claims', true)::jsonb ? 'sub')
             AND (current_setting('request.jwt.claims', true)::jsonb->>'sub') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN (current_setting('request.jwt.claims', true)::jsonb->>'sub')::UUID
        ELSE NULL
      END
    );
  ELSE
    v_caller_id := COALESCE(
      auth.uid(),
      CASE
        WHEN NULLIF(current_setting('request.jwt.claim.sub', true), '') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN NULLIF(current_setting('request.jwt.claim.sub', true), '')::UUID
        WHEN NULLIF(current_setting('request.jwt.claims', true), '') IS NOT NULL
             AND (current_setting('request.jwt.claims', true)::jsonb ? 'sub')
             AND (current_setting('request.jwt.claims', true)::jsonb->>'sub') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN (current_setting('request.jwt.claims', true)::jsonb->>'sub')::UUID
        ELSE NULL
      END
    );
  END IF;

  -- 2. Lock root tuple on exam_sessions exclusively
  SELECT id, user_id, status, approved_at, updated_at
  INTO v_session
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ERR_SESSION_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  -- 3. Verify user ownership authorization (unless service_role) (F14 & F16)
  IF v_role != 'service_role' AND (v_caller_id IS NULL OR v_session.user_id IS DISTINCT FROM v_caller_id) THEN
    RAISE EXCEPTION 'ERR_UNAUTHORIZED' USING ERRCODE = '42501';
  END IF;

  -- 4. Idempotency Guard: if already approved, return stored timestamp without mutation
  IF v_session.status = 'approved' THEN
    IF v_session.approved_at IS NULL THEN
      RAISE EXCEPTION 'ERR_INVALID_SESSION_STATE' USING ERRCODE = 'P0001';
    END IF;
    RETURN jsonb_build_object(
      'session_id', v_session.id,
      'status', 'approved',
      'approved_at', v_session.approved_at,
      'updated_at', v_session.updated_at,
      'message', 'Phiên đề đã được phê duyệt trước đó'
    );
  END IF;

  -- 5. Session State Machine Guard: only 'reviewed' or 'generated' allowed
  IF v_session.status != 'reviewed' THEN
    RAISE EXCEPTION 'ERR_INVALID_SESSION_STATE' USING ERRCODE = 'P0001';
  END IF;

  -- 6. Optimistic Locking Guard: detect concurrent mutations
  IF p_expected_updated_at IS NOT NULL
     AND v_session.updated_at IS DISTINCT FROM p_expected_updated_at THEN
    RAISE EXCEPTION 'ERR_INVALID_SESSION_STATE' USING ERRCODE = 'P0001';
  END IF;

  -- 7. Exam Versions Invariant Guard (TASK-303 & F19 Fail-Closed):
  -- 7a. Query configured expected n_versions from generation_configs
  SELECT count(*), min(n_versions), max(n_versions)
  INTO v_config_count, v_min_n_versions, v_max_n_versions
  FROM public.generation_configs
  WHERE session_id = p_session_id;

  IF v_config_count = 0 THEN
    RAISE EXCEPTION 'ERR_CONFIG_NOT_FOUND' USING ERRCODE = '22023';
  END IF;

  IF v_config_count <> 1 THEN
    RAISE EXCEPTION 'ERR_CONFIG_AMBIGUOUS' USING ERRCODE = '22023';
  END IF;

  v_expected_versions := v_min_n_versions;

  -- 7b. Total versions must match configured n_versions and 100% of versions must have is_finalized = TRUE
  SELECT count(*), count(*) FILTER (WHERE is_finalized IS TRUE)
  INTO v_total_versions, v_finalized_versions
  FROM public.exam_versions
  WHERE session_id = p_session_id;

  IF v_total_versions != v_expected_versions THEN
    RAISE EXCEPTION 'ERR_VERSIONS_NOT_FINALIZED' USING ERRCODE = 'P0001';
  END IF;

  IF v_total_versions = 0 OR v_finalized_versions < v_total_versions THEN
    RAISE EXCEPTION 'ERR_VERSIONS_NOT_FINALIZED' USING ERRCODE = 'P0001';
  END IF;

  -- 8. Questions Invariant Guard (TASK-301):
  -- 8a. No question may be actively regenerating
  SELECT count(*)
  INTO v_regenerating_count
  FROM public.version_questions q
  JOIN public.exam_versions v ON v.id = q.version_id
  WHERE v.session_id = p_session_id
    AND q.is_current IS TRUE
    AND q.status = 'regenerating';

  IF v_regenerating_count > 0 THEN
    RAISE EXCEPTION 'ERR_QUESTION_REGENERATING' USING ERRCODE = 'P0001';
  END IF;

  -- 8b. 100% of active questions must have status = 'approved'
  SELECT count(*), count(*) FILTER (WHERE q.status = 'approved')
  INTO v_total_current_q, v_approved_current_q
  FROM public.version_questions q
  JOIN public.exam_versions v ON v.id = q.version_id
  WHERE v.session_id = p_session_id
    AND q.is_current IS TRUE;

  IF v_total_current_q = 0 OR v_approved_current_q < v_total_current_q THEN
    RAISE EXCEPTION 'ERR_NOT_ALL_QUESTIONS_APPROVED' USING ERRCODE = 'P0001';
  END IF;

  -- 8c. Cartesian Completeness Guard (F02):
  -- Every (version, source_question) pair must have an active approved variant
  IF EXISTS (
    SELECT 1
    FROM public.exam_versions v
    CROSS JOIN public.source_questions s
    WHERE v.session_id = p_session_id
      AND s.session_id = p_session_id
      AND NOT EXISTS (
        SELECT 1
        FROM public.version_questions q
        WHERE q.version_id = v.id
          AND q.source_question_id = s.id
          AND q.is_current IS TRUE
          AND q.status = 'approved'
      )
  ) THEN
    RAISE EXCEPTION 'ERR_NOT_ALL_QUESTIONS_APPROVED' USING ERRCODE = 'P0001';
  END IF;

  -- The review owner defines readiness, including source evidence and active
  -- operations. Re-evaluate it under the same parent lock as review writers.
  v_progress := public._review_progress(p_session_id);
  IF (v_progress->>'ready')::boolean IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'ERR_NOT_ALL_QUESTIONS_APPROVED' USING ERRCODE = 'P0001';
  END IF;

  -- Retain structural checks, then bind keys to the actual current display rows.
  SELECT count(*) INTO v_source_count FROM public.source_questions
    WHERE session_id = p_session_id;
  IF EXISTS (
    SELECT 1 FROM public.exam_versions v
    CROSS JOIN generate_series(1, v_source_count) slot(display_no)
    LEFT JOIN public.answer_keys k ON k.version_id = v.id AND k.display_no = slot.display_no
    WHERE v.session_id = p_session_id
    GROUP BY v.id, slot.display_no HAVING count(k.id) <> 1
  ) OR EXISTS (
    SELECT 1 FROM public.answer_keys k
    JOIN public.exam_versions v ON v.id = k.version_id
    WHERE v.session_id = p_session_id AND (
      k.question_no IS DISTINCT FROM k.display_no
      OR k.display_no IS NULL OR k.display_no NOT BETWEEN 1 AND v_source_count
      OR k.correct_option IS DISTINCT FROM k.display_correct_key
      OR k.display_correct_key IS NULL OR k.display_correct_key NOT IN ('A','B','C','D')
      OR NOT EXISTS (
        SELECT 1 FROM public.source_questions s
        WHERE s.session_id = p_session_id AND s.question_no = k.canonical_question_no
      )
    )
  ) OR EXISTS (
    SELECT 1 FROM public.answer_keys k JOIN public.exam_versions v ON v.id = k.version_id
    WHERE v.session_id = p_session_id
    GROUP BY k.version_id, k.canonical_question_no HAVING count(*) <> 1
  ) THEN
    RAISE EXCEPTION 'ERR_INCONSISTENT_ANSWER_KEYS' USING ERRCODE = 'P0001';
  END IF;

  -- F02: exact current display slot, answer and canonical source mapping.
  -- Runs under the parent lock shared by every supported content writer.
  IF EXISTS (
    SELECT 1 FROM public.exam_versions v
    CROSS JOIN generate_series(1,v_source_count) slot(display_no)
    LEFT JOIN public.version_questions q ON q.version_id=v.id
      AND q.is_current AND q.question_no=slot.display_no
    LEFT JOIN public.answer_keys k ON k.version_id=v.id AND k.display_no=slot.display_no
    WHERE v.session_id=p_session_id
    GROUP BY v.id,slot.display_no
    HAVING count(q.id)<>1 OR count(k.id)<>1
       OR bool_or(k.correct_option IS DISTINCT FROM q.correct_key
         OR k.display_correct_key IS DISTINCT FROM q.correct_key
         OR k.canonical_question_no IS DISTINCT FROM q.canonical_question_no)
  ) THEN RAISE EXCEPTION 'ERR_INCONSISTENT_ANSWER_KEYS'; END IF;

  -- 9. Atomic State Transition
  UPDATE public.exam_sessions
  SET status = 'approved',
      approved_at = v_now,
      updated_at = v_now
  WHERE id = p_session_id;

  -- 10. Record APPROVE_ALL audit log entry
  INSERT INTO public.review_logs (
    session_id,
    user_id,
    action_type,
    reason,
    created_at
  ) VALUES (
    p_session_id,
    COALESCE(v_caller_id, v_session.user_id),
    'APPROVE_ALL',
    'Phiên đề được phê duyệt chính thức và khóa nội dung bất biến vĩnh viễn (TASK-305)',
    v_now
  );

  -- 11. Return approved response payload
  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'status', 'approved',
    'approved_at', v_now,
    'updated_at', v_now,
    'message', 'Phê duyệt phiên thi thành công và đã khóa nội dung'
  );
END;
$$;

-- Grant permissions for authenticated users and backend service role
REVOKE EXECUTE ON FUNCTION public.finalize_approve_session(UUID, UUID, TIMESTAMPTZ) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.finalize_approve_session(UUID, UUID, TIMESTAMPTZ) TO authenticated, service_role;

-- TASK-305: persist shuffle in one owner-authorized transaction.
-- Input was computed outside the transaction and is compared again under lock.
CREATE OR REPLACE FUNCTION public._finalize_sync_solution(p_text text, p_canonical text, p_display text)
RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  result text := coalesce(p_text, '');
  suffix text := $re$((?:\})?[\*_\]\)]*)(?=[\s\.,;:\n\)]|$)(?!\s*(?:[=!<>]|<=|>=|!=|==|\\le|\\ge|\\in|\\notin|[\+\-\*/\\~]))$re$;
  wrapper text := $re$([\*_\[\(]*(?:\\textbf\{)?)$re$;
  -- Python re uses Unicode whitespace, including NBSP and C0 separators;
  -- PostgreSQL's locale-dependent \s does not. Keep the shuffler contract.
  spaces text := U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
BEGIN
  IF p_canonical = p_display OR result = '' THEN RETURN result; END IF;
  suffix := replace(suffix, $re$[\s$re$, '[' || spaces);
  result := regexp_replace(result,
    replace($re$(\m(?:đáp\s+án|phương\s+án|câu\s+trả\s+lời|chọn(?:\s+đáp\s+án|\s+phương\s+án)?)(?:\s+đúng|\s+cần\s+chọn)?(?:\s+là)?\s*[:\.]?\s*)$re$
      || wrapper || '(' || p_canonical || ')' || suffix, $re$\s$re$, '[' || spaces || ']'),
    E'\\1\\2' || p_display || E'\\4', 'gi');
  result := regexp_replace(result,
    replace($re$(\m(?:kết\s+luận|suy\s+ra|do\s+đó|vậy)\s*[:]\s*)$re$
      || wrapper || '(' || p_canonical || ')' || suffix, $re$\s$re$, '[' || spaces || ']'),
    E'\\1\\2' || p_display || E'\\4', 'gi');
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION public._finalize_sync_solution(text,text,text) FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.finalize_persist_shuffle(p_session_id uuid, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  s public.exam_sessions%ROWTYPE;
  cfg public.generation_configs%ROWTYPE;
  v public.exam_versions%ROWTYPE;
  q public.version_questions%ROWTYPE;
  snap jsonb := p_payload->'snapshot';
  actual jsonb;
  supplied jsonb;
  vr jsonb;
  qr jsonb;
  ak jsonb;
  label text;
  mapped text;
  receipt jsonb := '[]'::jsonb;
  n integer;
  m integer;
  cnt integer;
  expected_permutations jsonb;
  no_change boolean := true;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
  -- Only the backend service principal may attest computed shuffle output.
  -- JWT role claims do not elevate the actual PostgreSQL connection role.
  IF coalesce(nullif(current_setting('role',true),'none'),session_user) <> 'service_role'
     OR NOT FOUND OR jsonb_typeof(p_payload->'actor_id') IS DISTINCT FROM 'string'
     OR s.user_id IS DISTINCT FROM (p_payload->>'actor_id')::uuid THEN
    RAISE EXCEPTION 'ERR_UNAUTHORIZED' USING ERRCODE='42501';
  END IF;
  IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'ERR_SESSION_LOCKED';
  END IF;
  IF s.status <> 'reviewed' OR (public._review_progress(p_session_id)->>'ready')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_NOT_READY';
  END IF;
  IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
     OR jsonb_typeof(snap) IS DISTINCT FROM 'object'
     OR jsonb_typeof(snap->'config') IS DISTINCT FROM 'object'
     OR jsonb_typeof(snap->'versions') IS DISTINCT FROM 'array'
     OR jsonb_typeof(snap->'sources') IS DISTINCT FROM 'array'
     OR jsonb_typeof(snap->'questions') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  SELECT count(*) INTO cnt FROM public.generation_configs WHERE session_id=p_session_id;
  IF cnt <> 1 THEN RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE'; END IF;
  SELECT * INTO cfg FROM public.generation_configs WHERE session_id=p_session_id FOR UPDATE;
  n := cfg.n_versions;
  IF n NOT BETWEEN 1 AND 4 OR jsonb_typeof(cfg.ordering_preferences) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_each(cfg.ordering_preferences) e
                WHERE e.key NOT IN ('shuffle_questions','shuffle_options') OR jsonb_typeof(e.value) <> 'boolean') THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  PERFORM 1 FROM public.exam_versions WHERE session_id=p_session_id ORDER BY id FOR UPDATE;
  PERFORM 1 FROM public.source_questions WHERE session_id=p_session_id ORDER BY id FOR UPDATE;
  PERFORM 1 FROM public.version_questions q0 JOIN public.exam_versions v0 ON v0.id=q0.version_id
    WHERE v0.session_id=p_session_id AND q0.is_current ORDER BY q0.id FOR UPDATE OF q0;

  IF snap->'config' IS DISTINCT FROM jsonb_build_object('id',cfg.id,'session_id',cfg.session_id,
      'n_versions',cfg.n_versions,'ordering_preferences',cfg.ordering_preferences) THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT';
  END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'session_id',session_id,'version_code',version_code)
                            ORDER BY id),'[]'::jsonb) INTO actual
    FROM public.exam_versions WHERE session_id=p_session_id;
  SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]'::jsonb) INTO supplied
    FROM jsonb_array_elements(snap->'versions') x;
  IF actual IS DISTINCT FROM supplied OR jsonb_array_length(actual) <> n THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT';
  END IF;
  IF EXISTS (SELECT 1 FROM public.exam_versions WHERE session_id=p_session_id AND version_code='') THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'session_id',session_id,'question_no',question_no)
                            ORDER BY id),'[]'::jsonb), count(*) INTO actual,m
    FROM public.source_questions WHERE session_id=p_session_id;
  SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]'::jsonb) INTO supplied
    FROM jsonb_array_elements(snap->'sources') x;
  IF actual IS DISTINCT FROM supplied OR m=0 THEN RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT'; END IF;
  IF EXISTS (SELECT 1 FROM public.source_questions WHERE session_id=p_session_id AND question_no < 1) THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',q0.id,'version_id',q0.version_id,
    'source_question_id',q0.source_question_id,'content',q0.content,
    'canonical_question_no',q0.canonical_question_no,'canonical_options',q0.canonical_options,
    'canonical_correct_key',q0.canonical_correct_key,'canonical_solution_md',q0.canonical_solution_md,
    'status',q0.status,'is_current',q0.is_current) ORDER BY q0.id),'[]'::jsonb) INTO actual
    FROM public.version_questions q0 JOIN public.exam_versions v0 ON v0.id=q0.version_id
    WHERE v0.session_id=p_session_id AND q0.is_current;
  SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]'::jsonb) INTO supplied
    FROM jsonb_array_elements(snap->'questions') x;
  IF actual IS DISTINCT FROM supplied OR jsonb_array_length(actual) <> n*m THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT';
  END IF;

  IF jsonb_typeof(p_payload->'versions') IS DISTINCT FROM 'array' OR jsonb_array_length(p_payload->'versions') <> n
     OR (SELECT count(DISTINCT x->>'version_id') FROM jsonb_array_elements(p_payload->'versions') x) <> n THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  -- Validate every row before the first write. SQL never trusts client-side checks.
  FOR vr IN SELECT value FROM jsonb_array_elements(p_payload->'versions') LOOP
    SELECT * INTO v FROM public.exam_versions WHERE id=(vr->>'version_id')::uuid AND session_id=p_session_id;
    IF NOT FOUND OR vr->>'version_code' IS DISTINCT FROM v.version_code
       OR vr->>'shuffle_seed' IS DISTINCT FROM encode(sha256(convert_to(p_session_id::text || '_' || v.version_code,'UTF8')),'hex')
       OR vr->'total_questions' IS DISTINCT FROM to_jsonb(m)
       OR jsonb_typeof(vr->'questions') IS DISTINCT FROM 'array'
       OR jsonb_typeof(vr->'answer_keys') IS DISTINCT FROM 'array'
       OR jsonb_array_length(vr->'questions') <> m OR jsonb_array_length(vr->'answer_keys') <> m THEN
      RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
    END IF;
    IF v.is_finalized IS NOT TRUE OR v.shuffle_seed IS DISTINCT FROM vr->>'shuffle_seed'
       OR v.permutations IS DISTINCT FROM vr->'permutations'
       OR (SELECT count(*) FROM public.answer_keys WHERE version_id=v.id) <> m THEN
      no_change := false;
    END IF;
    IF (SELECT count(DISTINCT x->>'id') FROM jsonb_array_elements(vr->'questions') x) <> m
       OR (SELECT count(DISTINCT (x->>'display_no')::int) FROM jsonb_array_elements(vr->'questions') x) <> m THEN
      RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
    END IF;
    FOR qr IN SELECT value FROM jsonb_array_elements(vr->'questions') LOOP
      SELECT * INTO q FROM public.version_questions WHERE id=(qr->>'id')::uuid AND version_id=v.id
        AND is_current AND status='approved';
      IF NOT FOUND OR qr->>'source_question_id' IS DISTINCT FROM q.source_question_id::text
         OR qr->'is_current' IS DISTINCT FROM 'true'::jsonb
         OR jsonb_typeof(qr->'display_no') IS DISTINCT FROM 'number'
         OR (qr->>'display_no') !~ '^[1-9][0-9]*$'
         OR qr->'canonical_question_no' IS DISTINCT FROM to_jsonb(q.canonical_question_no)
         OR (qr->>'canonical_question_no')::int IS DISTINCT FROM q.canonical_question_no
         OR qr->'canonical_options' IS DISTINCT FROM q.canonical_options
         OR qr->>'canonical_correct_key' IS DISTINCT FROM q.canonical_correct_key
         OR qr->'canonical_solution_md' IS DISTINCT FROM coalesce(to_jsonb(q.canonical_solution_md),'null'::jsonb)
         OR qr->>'content' IS DISTINCT FROM q.content OR (qr->>'display_no') IS NULL
         OR (qr->>'display_no')::int NOT BETWEEN 1 AND m
         OR q.canonical_correct_key NOT IN ('A','B','C','D')
         OR jsonb_typeof(q.canonical_options) IS DISTINCT FROM 'array'
         OR jsonb_array_length(q.canonical_options) <> 4
         OR EXISTS (SELECT 1 FROM jsonb_array_elements(q.canonical_options) o WHERE jsonb_typeof(o) <> 'string')
         OR jsonb_typeof(qr->'options') IS DISTINCT FROM 'array' OR jsonb_array_length(qr->'options') <> 4
         OR jsonb_typeof(qr->'permutation_map') IS DISTINCT FROM 'object'
         OR (SELECT count(*) FROM jsonb_object_keys(qr->'permutation_map')) <> 4
         OR (SELECT count(DISTINCT value) FROM jsonb_each_text(qr->'permutation_map')) <> 4 THEN
        RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
      END IF;
      FOREACH label IN ARRAY ARRAY['A','B','C','D'] LOOP
        mapped := qr->'permutation_map'->>label;
        IF mapped IS NULL OR mapped NOT IN ('A','B','C','D') OR
           (coalesce((cfg.ordering_preferences->>'shuffle_options')::boolean,true) IS FALSE AND mapped <> label) OR
           qr->'options'->(strpos('ABCD',mapped)-1) IS DISTINCT FROM q.canonical_options->(strpos('ABCD',label)-1) THEN
          RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
        END IF;
      END LOOP;
      IF qr->>'display_correct_key' IS DISTINCT FROM qr->'permutation_map'->>q.canonical_correct_key THEN
        RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
      END IF;
      SELECT x INTO ak FROM jsonb_array_elements(vr->'answer_keys') x
        WHERE (x->>'display_no')::int=(qr->>'display_no')::int;
      IF NOT FOUND OR ak->>'version_id' IS DISTINCT FROM v.id::text
         OR ak->>'display_correct_key' IS DISTINCT FROM qr->>'display_correct_key'
         OR ak->'display_no' IS DISTINCT FROM qr->'display_no'
         OR ak->'canonical_question_no' IS DISTINCT FROM to_jsonb(q.canonical_question_no) THEN
        RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
      END IF;
      IF qr->>'solution_md' IS DISTINCT FROM public._finalize_sync_solution(
          q.canonical_solution_md,q.canonical_correct_key,qr->>'display_correct_key') THEN
        RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
      END IF;
      IF q.question_no IS DISTINCT FROM (qr->>'display_no')::int OR q.options IS DISTINCT FROM qr->'options'
         OR q.correct_key IS DISTINCT FROM qr->>'display_correct_key' OR q.solution_md IS DISTINCT FROM qr->>'solution_md'
         OR NOT EXISTS (SELECT 1 FROM public.answer_keys a WHERE a.version_id=v.id
           AND a.question_no=(qr->>'display_no')::int AND a.display_no=a.question_no
           AND a.correct_option=qr->>'display_correct_key' AND a.display_correct_key=a.correct_option
           AND a.canonical_question_no=q.canonical_question_no) THEN
        no_change := false;
      END IF;
    END LOOP;
    SELECT jsonb_build_object(
      'question_order',jsonb_agg((x->>'canonical_question_no')::int ORDER BY (x->>'display_no')::int),
      'display_to_canonical',jsonb_object_agg(x->>'display_no',(x->>'canonical_question_no')::int),
      'canonical_to_display',jsonb_object_agg(x->>'canonical_question_no',(x->>'display_no')::int),
      'option_permutations',jsonb_object_agg(x->>'display_no',x->'permutation_map'))
      INTO expected_permutations FROM jsonb_array_elements(vr->'questions') x;
    IF vr->'permutations' IS DISTINCT FROM expected_permutations THEN
      RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
    END IF;
    IF coalesce((cfg.ordering_preferences->>'shuffle_questions')::boolean,true) IS FALSE AND
       EXISTS (SELECT 1 FROM jsonb_array_elements(vr->'questions') x
         WHERE (x->>'display_no')::int <> (SELECT count(*) FROM public.version_questions q0
           WHERE q0.version_id=v.id AND q0.is_current AND q0.canonical_question_no <= (x->>'canonical_question_no')::int)) THEN
      RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
    END IF;
  END LOOP;

  IF no_change THEN
    SELECT jsonb_agg(jsonb_build_object('version_id',x->>'version_id',
      'version_code',x->>'version_code','total_questions',m)) INTO receipt
      FROM jsonb_array_elements(p_payload->'versions') x;
    RETURN jsonb_build_object('session_id',p_session_id,'status','reviewed','is_finalized',true,'versions',receipt);
  END IF;
  FOR vr IN SELECT value FROM jsonb_array_elements(p_payload->'versions') LOOP
    UPDATE public.exam_versions SET shuffle_seed=vr->>'shuffle_seed', permutations=vr->'permutations'
      WHERE id=(vr->>'version_id')::uuid AND session_id=p_session_id;
    GET DIAGNOSTICS cnt = ROW_COUNT;
    IF cnt <> 1 THEN RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT'; END IF;
    DELETE FROM public.answer_keys WHERE version_id=(vr->>'version_id')::uuid;
    FOR qr IN SELECT value FROM jsonb_array_elements(vr->'questions') LOOP
      UPDATE public.version_questions SET question_no=(qr->>'display_no')::int, options=qr->'options',
        correct_key=qr->>'display_correct_key', solution_md=qr->>'solution_md', updated_at=clock_timestamp()
        WHERE id=(qr->>'id')::uuid AND version_id=(vr->>'version_id')::uuid
          AND source_question_id=(qr->>'source_question_id')::uuid AND is_current AND status='approved';
      GET DIAGNOSTICS cnt = ROW_COUNT;
      IF cnt <> 1 THEN RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT'; END IF;
      INSERT INTO public.answer_keys(version_id,question_no,correct_option,display_no,display_correct_key,canonical_question_no)
        VALUES ((vr->>'version_id')::uuid,(qr->>'display_no')::int,qr->>'display_correct_key',
                (qr->>'display_no')::int,qr->>'display_correct_key',(qr->>'canonical_question_no')::int);
    END LOOP;
    receipt := receipt || jsonb_build_array(jsonb_build_object('version_id',vr->>'version_id',
      'version_code',vr->>'version_code','total_questions',m));
  END LOOP;
  -- Re-read persisted output too: an UPDATE trigger may silently change or
  -- suppress a row. A valid request alone must never authorize finalized=true.
  FOR vr IN SELECT value FROM jsonb_array_elements(p_payload->'versions') LOOP
    SELECT * INTO v FROM public.exam_versions WHERE id=(vr->>'version_id')::uuid AND session_id=p_session_id;
    IF NOT FOUND OR v.shuffle_seed IS DISTINCT FROM vr->>'shuffle_seed'
       OR v.permutations IS DISTINCT FROM vr->'permutations' THEN
      RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
    END IF;
    FOR qr IN SELECT value FROM jsonb_array_elements(vr->'questions') LOOP
      SELECT * INTO q FROM public.version_questions WHERE id=(qr->>'id')::uuid AND version_id=v.id;
      IF NOT FOUND OR q.is_current IS NOT TRUE OR q.status <> 'approved'
         OR q.source_question_id::text IS DISTINCT FROM qr->>'source_question_id'
         OR q.content IS DISTINCT FROM qr->>'content'
         OR q.canonical_question_no IS DISTINCT FROM (qr->>'canonical_question_no')::int
         OR q.canonical_options IS DISTINCT FROM qr->'canonical_options'
         OR q.canonical_correct_key IS DISTINCT FROM qr->>'canonical_correct_key'
         OR q.canonical_solution_md IS DISTINCT FROM qr->>'canonical_solution_md'
         OR q.question_no IS DISTINCT FROM (qr->>'display_no')::int
         OR q.options IS DISTINCT FROM qr->'options'
         OR q.correct_key IS DISTINCT FROM qr->>'display_correct_key'
         OR q.solution_md IS DISTINCT FROM qr->>'solution_md' THEN
        RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
      END IF;
    END LOOP;
  END LOOP;
  IF (SELECT count(*) FROM public.answer_keys a JOIN public.exam_versions v0 ON v0.id=a.version_id
      WHERE v0.session_id=p_session_id) <> n*m OR EXISTS (
    SELECT 1 FROM public.version_questions q0 JOIN public.exam_versions v0 ON v0.id=q0.version_id
    LEFT JOIN public.answer_keys a ON a.version_id=q0.version_id AND a.display_no=q0.question_no
    WHERE v0.session_id=p_session_id AND q0.is_current AND
      (a.id IS NULL OR a.question_no IS DISTINCT FROM q0.question_no
       OR a.correct_option IS DISTINCT FROM q0.correct_key
       OR a.display_correct_key IS DISTINCT FROM q0.correct_key
       OR a.canonical_question_no IS DISTINCT FROM q0.canonical_question_no)
  ) THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  UPDATE public.exam_versions SET is_finalized=true WHERE session_id=p_session_id;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  IF cnt <> n THEN RAISE EXCEPTION 'ERR_SHUFFLE_STALE_INPUT'; END IF;
  IF (SELECT count(*) FROM public.exam_versions WHERE session_id=p_session_id AND is_finalized) <> n THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE';
  END IF;
  RETURN jsonb_build_object('session_id',p_session_id,'status','reviewed','is_finalized',true,'versions',receipt);
EXCEPTION
  -- Malformed JSON/UUID/integer inputs remain domain errors. This block also
  -- rolls back every write in the function; never translate an error to success.
  WHEN invalid_text_representation OR numeric_value_out_of_range
       OR invalid_parameter_value OR datatype_mismatch THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_INPUT_INCOMPLETE' USING ERRCODE='22023';
END $$;

REVOKE ALL ON FUNCTION public.finalize_persist_shuffle(uuid,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finalize_persist_shuffle(uuid,jsonb) TO service_role;


-- Direct client writes must not replace review/shuffle/approval transactions.
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES ON public.exam_versions,
  public.version_questions,public.answer_keys,public.review_logs FROM PUBLIC,anon,authenticated;
-- Table-level REVOKE does not remove independently granted column privileges.
DO $$ DECLARE t text; cols text; BEGIN
  FOREACH t IN ARRAY ARRAY['exam_versions','version_questions','answer_keys','review_logs'] LOOP
    SELECT string_agg(quote_ident(attname),',') INTO cols FROM pg_attribute
      WHERE attrelid=('public.'||t)::regclass AND attnum>0 AND NOT attisdropped;
    EXECUTE format('REVOKE INSERT (%s),UPDATE (%s),REFERENCES (%s) ON public.%I FROM PUBLIC,anon,authenticated',cols,cols,cols,t);
  END LOOP;
END $$;
REVOKE TRUNCATE,TRIGGER,REFERENCES ON public.users,public.exam_sessions,
  public.source_questions,public.question_blueprints,public.generation_configs
  FROM PUBLIC,anon,authenticated;
-- Deleting the profile can cascade through sessions as the RI trigger owner.
-- Account removal is an administrative retention workflow, never client DML.
REVOKE DELETE ON public.users FROM PUBLIC,anon,authenticated;

DROP POLICY IF EXISTS "Users can manage exam versions in their sessions" ON public.exam_versions;
CREATE POLICY "Users can manage exam versions in their sessions" ON public.exam_versions FOR SELECT
  USING (session_id IN (SELECT id FROM public.exam_sessions WHERE user_id=auth.uid()));
DROP POLICY IF EXISTS "Users can manage version questions in their versions" ON public.version_questions;
CREATE POLICY "Users can manage version questions in their versions" ON public.version_questions FOR SELECT
  USING (version_id IN (SELECT v.id FROM public.exam_versions v JOIN public.exam_sessions s ON s.id=v.session_id WHERE s.user_id=auth.uid()));
DROP POLICY IF EXISTS "Users can manage answer keys in their versions" ON public.answer_keys;
CREATE POLICY "Users can manage answer keys in their versions" ON public.answer_keys FOR SELECT
  USING (version_id IN (SELECT v.id FROM public.exam_versions v JOIN public.exam_sessions s ON s.id=v.session_id WHERE s.user_id=auth.uid()));
DROP POLICY IF EXISTS "Users can view review logs of their version questions" ON public.review_logs;
CREATE POLICY "Users can view review logs of their version questions" ON public.review_logs FOR SELECT
  USING (session_id IN (SELECT id FROM public.exam_sessions WHERE user_id=auth.uid()));

-- Invoker trigger: current_user distinguishes direct API DML from the existing
-- SECURITY DEFINER RPCs. No user-set GUC can authorize lifecycle state writes.
CREATE OR REPLACE FUNCTION public.finalize_guard_direct_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE sid uuid; locked boolean;
BEGIN
  IF current_user NOT IN ('authenticated','anon','service_role') THEN
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
  END IF;
  IF TG_TABLE_NAME='exam_sessions' THEN
    IF TG_OP<>'INSERT' AND (OLD.status IN ('approved','exported') OR OLD.approved_at IS NOT NULL) THEN
      RAISE EXCEPTION 'ERR_SESSION_LOCKED' USING ERRCODE='55000';
    END IF;
    IF current_user IN ('authenticated','anon') THEN
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'draft' OR NEW.approved_at IS NOT NULL OR NEW.gemini_review_calls<>0
          OR NEW.gemini_call_count<>0 OR NEW.retry_count<>0 THEN
          RAISE EXCEPTION 'ERR_DIRECT_LIFECYCLE_MUTATION' USING ERRCODE='42501';
        END IF;
      ELSIF TG_OP='UPDATE' AND
        (to_jsonb(NEW)-ARRAY['title','subject','grade','updated_at']) IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['title','subject','grade','updated_at']) THEN
        RAISE EXCEPTION 'ERR_DIRECT_LIFECYCLE_MUTATION' USING ERRCODE='42501';
      END IF;
    END IF;
  ELSE
    IF TG_TABLE_NAME='question_blueprints' THEN
      IF TG_OP='UPDATE' AND NEW.source_question_id IS DISTINCT FROM OLD.source_question_id THEN
        RAISE EXCEPTION 'ERR_DIRECT_LIFECYCLE_MUTATION' USING ERRCODE='42501';
      END IF;
      SELECT session_id INTO sid FROM public.source_questions
        WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.source_question_id ELSE NEW.source_question_id END;
    ELSIF TG_TABLE_NAME IN ('version_questions','answer_keys') THEN
      IF TG_OP='UPDATE' AND NEW.version_id IS DISTINCT FROM OLD.version_id THEN
        RAISE EXCEPTION 'ERR_DIRECT_LIFECYCLE_MUTATION' USING ERRCODE='42501';
      END IF;
      SELECT session_id INTO sid FROM public.exam_versions
        WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.version_id ELSE NEW.version_id END;
    ELSE
      IF TG_OP='UPDATE' AND NEW.session_id IS DISTINCT FROM OLD.session_id THEN
        RAISE EXCEPTION 'ERR_DIRECT_LIFECYCLE_MUTATION' USING ERRCODE='42501';
      END IF;
      sid := CASE WHEN TG_OP='DELETE' THEN OLD.session_id ELSE NEW.session_id END;
    END IF;
    SELECT status IN ('approved','exported') OR approved_at IS NOT NULL INTO locked
      FROM public.exam_sessions WHERE id=sid FOR UPDATE;
    IF locked THEN RAISE EXCEPTION 'ERR_SESSION_LOCKED' USING ERRCODE='55000'; END IF;
    IF TG_TABLE_NAME='generation_configs' THEN
      IF (TG_OP<>'UPDATE'
       OR ROW(NEW.n_versions,NEW.ordering_preferences) IS DISTINCT FROM ROW(OLD.n_versions,OLD.ordering_preferences))
       AND EXISTS (SELECT 1 FROM public.exam_versions WHERE session_id=sid AND is_finalized) THEN
      -- A client cannot change the seed's input policy behind a trusted receipt.
      -- Reconfiguration of finalized output needs an explicit invalidating RPC.
      RAISE EXCEPTION 'ERR_SHUFFLE_CONFIGURATION_LOCKED' USING ERRCODE='55000';
      END IF;
    END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
REVOKE ALL ON FUNCTION public.finalize_guard_direct_mutation() FROM PUBLIC,anon,authenticated,service_role;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['exam_sessions','source_questions','question_blueprints','generation_configs','exam_versions','version_questions','answer_keys'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_finalize_direct_guard ON public.%I',t);
    EXECUTE format('CREATE TRIGGER trg_finalize_direct_guard BEFORE INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.finalize_guard_direct_mutation()',t);
  END LOOP;
END $$;

COMMIT;
