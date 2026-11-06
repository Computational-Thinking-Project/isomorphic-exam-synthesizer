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
  IF NOT FOUND OR auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid() THEN
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

REVOKE ALL ON FUNCTION public.finalize_persist_shuffle(uuid,jsonb) FROM PUBLIC, anon, service_role;
GRANT EXECUTE ON FUNCTION public.finalize_persist_shuffle(uuid,jsonb) TO authenticated;
