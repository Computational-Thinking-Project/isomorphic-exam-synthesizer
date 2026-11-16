-- Issue #80 supersedes blanket Q01. Frozen inputs/hashes remain immutable.
BEGIN;

CREATE OR REPLACE FUNCTION public._generation_claim_010(
  p_session_id uuid, p_is_retry boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  s public.exam_sessions;
  cfg public.generation_configs;
  job public.generation_job_snapshots;
  snap jsonb;
  token uuid;
  completed jsonb;

BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;
  IF public.current_role() <> 'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
    RAISE EXCEPTION 'Access denied' USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.source_artifact_confirmations WHERE session_id = s.id) THEN
    RETURN public._generation_legacy_claim(s.id, p_is_retry);
  END IF;
  IF p_is_retry IS NULL OR s.approved_at IS NOT NULL
     OR (NOT p_is_retry AND s.status <> 'configured')
     OR (p_is_retry AND s.status NOT IN ('failed', 'partial_generated')) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: cannot claim current state' USING ERRCODE = '55006';
  END IF;
  SELECT * INTO cfg FROM public.generation_configs WHERE session_id = s.id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing config' USING ERRCODE = '55006';
  END IF;
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;

  IF p_is_retry THEN
    IF job.id IS NULL OR job.n_versions IS DISTINCT FROM cfg.n_versions
       OR job.public_modes IS DISTINCT FROM cfg.active_variation_modes
       OR job.canonical_dimensions IS DISTINCT FROM cfg.canonical_dimensions
       OR job.mapping_version IS DISTINCT FROM cfg.mapping_version
       OR job.snapshot_payload->'manifest' IS DISTINCT FROM cfg.source_manifest
       OR job.snapshot_payload->'ordering_preferences' IS DISTINCT FROM cfg.ordering_preferences THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing or incompatible retry snapshot' USING ERRCODE = '55006';
    END IF;
    snap := job.snapshot_payload;
  ELSE
    IF job.id IS NOT NULL THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: generation already started' USING ERRCODE = '55006';
    END IF;
    snap := public.get_generation_source_snapshot(s.id);
    IF (snap->>'ready')::boolean IS DISTINCT FROM true THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY' USING ERRCODE = '22023';
    END IF;
    IF cfg.source_manifest IS DISTINCT FROM snap->'manifest' THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: configured source changed' USING ERRCODE = '55006';
    END IF;
  END IF;

  token := gen_random_uuid();
  IF NOT p_is_retry THEN
    INSERT INTO public.generation_job_snapshots(
      session_id, job_token, confirmation_id, source_order, confirmed_source_hash, base_seed,
      n_versions, public_modes, canonical_dimensions, mapping_version, snapshot_payload
    ) VALUES (
      s.id, token, (snap->>'confirmation_id')::uuid, snap->'source_order', snap->>'confirmed_source_hash', 100,
      cfg.n_versions, cfg.active_variation_modes, cfg.canonical_dimensions, cfg.mapping_version,
      snap || jsonb_build_object('base_seed', 100, 'n_versions', cfg.n_versions, 'public_modes', cfg.active_variation_modes,
        'canonical_dimensions', cfg.canonical_dimensions, 'mapping_version', cfg.mapping_version,
        'ordering_preferences', cfg.ordering_preferences)
    ) RETURNING * INTO job;
  END IF;

  SELECT coalesce(jsonb_agg(jsonb_build_object('version_code', (100 + r.version_index)::text,
    'version_index', r.version_index, 'source_question_id', r.source_question_id, 'question_no', r.question_no)
    ORDER BY r.version_index, r.question_no), '[]') INTO completed
  FROM public.generation_target_results r JOIN public.version_questions q ON q.id = r.version_question_id AND q.is_current
  WHERE r.session_id = s.id AND r.snapshot_id = job.id AND r.is_success;
  UPDATE public.exam_sessions SET status = 'generating', active_job_id = token WHERE id = s.id;
  RETURN jsonb_build_object('session_id', s.id, 'job_id', token, 'status', 'generating',
    'starting_quota', s.gemini_call_count, 'gemini_call_count', s.gemini_call_count,
    'config', jsonb_build_object('n_versions', job.n_versions, 'active_variation_modes', job.public_modes,
      'ordering_preferences', job.snapshot_payload->'ordering_preferences'),
    'committed_targets', completed, 'snapshot_id', job.id, 'context', job.snapshot_payload);
END $$;

REVOKE ALL ON FUNCTION public._generation_claim_010(uuid, boolean) FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public._generation_fallback_record(
  p_job public.generation_job_snapshots,
  p_source_question_id uuid,
  p_version_index int,
  p_request_fingerprint text,
  p_last_error_code text
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  solution text;
  src jsonb;
  idx int;
  conf_rec public.source_artifact_confirmations%ROWTYPE;
  rev_rec public.source_artifact_revisions%ROWTYPE;
  input jsonb;
  item jsonb;
  src_fp text;
  all_items jsonb;
  all_hash text;
  spaces text := U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
BEGIN
  IF p_job.id IS NULL OR p_job.snapshot_payload IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing job snapshot payload' USING ERRCODE = '22023';
  END IF;
  IF p_version_index IS NULL OR p_version_index NOT BETWEEN 1 AND p_job.n_versions THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: version_index out of bounds' USING ERRCODE = '22023';
  END IF;
  IF p_request_fingerprint IS NULL OR p_request_fingerprint !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid request_fingerprint' USING ERRCODE = '22023';
  END IF;
  IF p_last_error_code IS NULL OR p_last_error_code !~ '^[A-Z0-9_]{3,64}$' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid last_error_code' USING ERRCODE = '22023';
  END IF;

  SELECT x, ord::int - 1 INTO src, idx
  FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord)
  WHERE (x->>'source_question_id')::uuid = p_source_question_id;

  IF src IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source_question_id not found in frozen snapshot' USING ERRCODE = '22023';
  END IF;
  IF (SELECT count(*) FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') x
      WHERE (x->>'source_question_id')::uuid = p_source_question_id) <> 1 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: non-unique source in frozen snapshot' USING ERRCODE = '22023';
  END IF;

  -- Bind snapshot confirmation to the same session
  SELECT * INTO conf_rec FROM public.source_artifact_confirmations
  WHERE confirmation_id = p_job.confirmation_id AND session_id = p_job.session_id;
  IF conf_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmation missing or mismatched' USING ERRCODE = '22023';
  END IF;

  -- Bind source revision to that confirmation/source
  SELECT * INTO rev_rec FROM public.source_artifact_revisions
  WHERE confirmation_id = p_job.confirmation_id
    AND source_question_id = p_source_question_id
    AND source_revision_id = (src->>'source_revision_id')::uuid;
  IF rev_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source revision not bound to confirmation' USING ERRCODE = '22023';
  END IF;

  -- Frozen confirmed_input must equal stored revision input
  IF rev_rec.confirmed_input IS DISTINCT FROM src->'confirmed_input' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmed_input mismatch with stored revision' USING ERRCODE = '22023';
  END IF;

  -- Check blueprint revision binding
  IF src->>'blueprint_revision_id' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing blueprint_revision_id' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.canonical_blueprint_revisions b
    WHERE b.blueprint_revision_id = (src->>'blueprint_revision_id')::uuid
      AND b.source_revision_id = (src->>'source_revision_id')::uuid
      AND b.source_question_id = p_source_question_id
  ) THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: blueprint revision not bound to source' USING ERRCODE = '22023';
  END IF;

  -- Check source order if present
  IF p_job.source_order IS NOT NULL AND jsonb_typeof(p_job.source_order) = 'array' THEN
    IF (SELECT jsonb_agg((x->>'source_question_id')::text ORDER BY ord)
        FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord))
       IS DISTINCT FROM p_job.source_order THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source order mismatch' USING ERRCODE = '22023';
    END IF;
  END IF;

  -- Recompute source fingerprint
  item := public._generation_source_item(src->'confirmed_input');
  src_fp := encode(sha256(convert_to(public._generation_json(jsonb_build_array(item)), 'UTF8')), 'hex');
  IF src_fp IS DISTINCT FROM src->>'source_fingerprint' OR src_fp IS DISTINCT FROM rev_rec.source_fingerprint THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source fingerprint mismatch' USING ERRCODE = '22023';
  END IF;

  -- Recompute confirmed_source_hash across all confirmed sources
  SELECT coalesce(jsonb_agg(public._generation_source_item(x->'confirmed_input') ORDER BY ord), '[]'::jsonb)
  INTO all_items
  FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord);

  all_hash := encode(sha256(convert_to(public._generation_json(all_items), 'UTF8')), 'hex');
  IF all_hash IS DISTINCT FROM p_job.confirmed_source_hash THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmed source hash mismatch' USING ERRCODE = '22023';
  END IF;

  -- Validate confirmed_input content
  input := src->'confirmed_input';
  IF input IS NULL OR jsonb_typeof(input) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or invalid confirmed_input' USING ERRCODE = '22023';
  END IF;

  -- Non-whitespace stem
  IF jsonb_typeof(input->'question_text') IS DISTINCT FROM 'string'
     OR coalesce(input->>'question_text', '') !~ ('[^' || spaces || ']') THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or whitespace question_text' USING ERRCODE = '22023';
  END IF;

  -- Four non-whitespace string options
  IF jsonb_typeof(input->'options') IS DISTINCT FROM 'array'
     OR jsonb_array_length(input->'options') <> 4
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(input->'options') opt
       WHERE jsonb_typeof(opt) IS DISTINCT FROM 'string'
          OR coalesce(opt#>>'{}', '') !~ ('[^' || spaces || ']')
     ) THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid options array' USING ERRCODE = '22023';
  END IF;

  -- A-D key
  IF input->>'correct_answer' NOT IN ('A', 'B', 'C', 'D') OR input->>'correct_answer' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid correct_answer' USING ERRCODE = '22023';
  END IF;

  IF input->'solution' IS NOT NULL AND jsonb_typeof(input->'solution') NOT IN ('null','string') THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed solution' USING ERRCODE='22023';
  END IF;
  solution := CASE WHEN coalesce(input->>'solution','') ~ ('[^' || spaces || ']')
    THEN input->>'solution' ELSE 'Không có lời giải cho câu hỏi này.' END;

  RETURN jsonb_build_object(
    'result_kind', 'CONFIRMED_SOURCE_FALLBACK',
    'snapshot_id', lower(p_job.id::text),
    'confirmation_id', lower(p_job.confirmation_id::text),
    'version_index', p_version_index,
    'source_question_id', lower(p_source_question_id::text),
    'question_no', (src->>'question_no')::int,
    'source_revision_id', lower((src->>'source_revision_id')::uuid::text),
    'blueprint_revision_id', lower((src->>'blueprint_revision_id')::uuid::text),
    'source_fingerprint', src->>'source_fingerprint',
    'confirmed_source_hash', p_job.confirmed_source_hash,
    'seed', p_job.base_seed + p_version_index * 1000 + idx,
    'request_fingerprint', p_request_fingerprint,
    'attempts', 4,
    'error_code', 'GENERATION_RETRIES_EXHAUSTED',
    'last_error_code', p_last_error_code,
    'content', input->>'question_text',
    'options', input->'options',
    'correct_key', input->>'correct_answer',
    'solution_md', solution,
    'has_warning', true
  );
END;
$$;
REVOKE ALL ON FUNCTION public._generation_fallback_record(public.generation_job_snapshots, uuid, int, text, text)
FROM PUBLIC, anon, authenticated, service_role;
CREATE OR REPLACE FUNCTION public.persist_generation_clone(p_session_id uuid,p_job_token uuid,p_clone_record jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots; src jsonb; input jsonb;
 solution text; legacy_expected jsonb; spaces text := U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
 prior public.generation_target_results; expected jsonb; digest text; idx int; ver int; v_id uuid; q_id uuid;
BEGIN
 IF public.current_role()<>'service_role' THEN RAISE EXCEPTION 'Worker only' USING ERRCODE='42501'; END IF;
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF s.status<>'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
  RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE='55006'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 IF job.id IS NULL OR job.public_modes IS DISTINCT FROM '[]'::jsonb
  OR job.canonical_dimensions IS DISTINCT FROM '[]'::jsonb THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone requires frozen modes=[]' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(p_clone_record) IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid clone record' USING ERRCODE='22023'; END IF;
 -- Text comparison before integer conversion rejects strings, fractions and null.
 IF p_clone_record->'version_index' IS NULL OR jsonb_typeof(p_clone_record->'version_index') IS DISTINCT FROM 'number'
  OR p_clone_record->>'version_index' NOT IN ('1','2','3','4') THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid clone version' USING ERRCODE='22023'; END IF;
 ver:=(p_clone_record->>'version_index')::int;
 SELECT x,ord::int-1 INTO src,idx FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x,ord)
 WHERE x->>'source_question_id'=p_clone_record->>'source_question_id';
 IF src IS NULL OR ver>job.n_versions THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid clone slot' USING ERRCODE='22023'; END IF;
 input:=src->'confirmed_input';
 IF jsonb_typeof(input->'question_text') IS DISTINCT FROM 'string' OR btrim(input->>'question_text')=''
  OR jsonb_typeof(input->'options') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed clone source' USING ERRCODE='22023'; END IF;
 IF jsonb_array_length(input->'options')<>4 OR coalesce(input->>'correct_answer','') NOT IN ('A','B','C','D')
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(input->'options') o WHERE jsonb_typeof(o)<>'string' OR btrim(o#>>'{}')='')
  OR (input->'solution' IS NOT NULL AND jsonb_typeof(input->'solution') NOT IN ('null','string')) THEN
  RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed clone options/key/solution' USING ERRCODE='22023'; END IF;
  solution := CASE WHEN coalesce(input->>'solution','') ~ ('[^' || spaces || ']')
    THEN input->>'solution' ELSE 'Không có lời giải cho câu hỏi này.' END;
 expected:=jsonb_build_object('result_kind','ORIGINAL_CLONE','snapshot_id',job.id,
  'version_index',ver,'source_question_id',src->'source_question_id','question_no',src->'question_no',
  'source_revision_id',src->'source_revision_id','source_fingerprint',src->'source_fingerprint',
  'blueprint_revision_id',src->'blueprint_revision_id','confirmed_source_hash',job.confirmed_source_hash,
  'seed',job.base_seed+ver*1000+idx,'content',input->'question_text','options',input->'options',
  'correct_key',input->'correct_answer','solution_md',solution);
 legacy_expected := jsonb_set(expected, '{solution_md}', coalesce(input->'solution','null'::jsonb));
 SELECT * INTO prior FROM public.generation_target_results WHERE session_id=s.id AND version_index=ver
  AND source_question_id=(src->>'source_question_id')::uuid;
 IF prior.is_success AND prior.result_kind='ORIGINAL_CLONE' AND prior.snapshot_id=job.id
    AND prior.raw_result=legacy_expected AND p_clone_record IN (legacy_expected, expected) THEN
   expected := legacy_expected;
 END IF;
 IF p_clone_record IS DISTINCT FROM expected AND NOT (coalesce(prior.is_success,false) AND expected=legacy_expected
     AND p_clone_record=jsonb_set(expected,'{solution_md}',to_jsonb(solution))) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone record differs from frozen source/slot' USING ERRCODE='22023';
 END IF;
 digest:=encode(sha256(convert_to(public._generation_json(expected),'UTF8')),'hex');
 IF prior.id IS NOT NULL AND prior.result_kind IS DISTINCT FROM 'ORIGINAL_CLONE' THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result kind differs from frozen job; explicit reconciliation required' USING ERRCODE='55006'; END IF;
 IF prior.is_success THEN
  IF prior.result_kind<>'ORIGINAL_CLONE' OR prior.snapshot_id<>job.id OR prior.raw_result IS DISTINCT FROM expected
   OR prior.clone_fingerprint IS DISTINCT FROM digest THEN
   RAISE EXCEPTION 'Successful target is immutable' USING ERRCODE='23505'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public._generation_committed(s.id,job.id) r WHERE r.id=prior.id) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: committed clone projection changed' USING ERRCODE='55006'; END IF;
  q_id:=prior.version_question_id;
 ELSE
  INSERT INTO public.exam_versions(session_id,version_code) VALUES(s.id,(100+ver)::text) ON CONFLICT(session_id,version_code) DO NOTHING;
  SELECT id INTO v_id FROM public.exam_versions WHERE session_id=s.id AND version_code=(100+ver)::text;
  IF EXISTS(SELECT 1 FROM public.version_questions WHERE version_id=v_id AND source_question_id=(src->>'source_question_id')::uuid AND is_current) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: display-only target requires explicit reconciliation' USING ERRCODE='23505'; END IF;
  INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,solution_md,
   canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,has_warning,status,is_current)
  VALUES(v_id,(src->>'source_question_id')::uuid,(src->>'question_no')::int,input->>'question_text',input->'options',
   input->>'correct_answer',solution,(src->>'question_no')::int,input->'options',input->>'correct_answer',solution,
   false,'pending_review',true) RETURNING id INTO q_id;
  INSERT INTO public.generation_target_results(session_id,snapshot_id,job_token,version_index,source_question_id,question_no,
   is_success,error_code,attempts,seed,request_fingerprint,raw_result,version_question_id,result_kind,clone_fingerprint)
  VALUES(s.id,job.id,p_job_token,ver,(src->>'source_question_id')::uuid,(src->>'question_no')::int,true,NULL,0,
   job.base_seed+ver*1000+idx,NULL,expected,q_id,'ORIGINAL_CLONE',digest)
  ON CONFLICT(session_id,version_index,source_question_id) DO UPDATE SET snapshot_id=EXCLUDED.snapshot_id,job_token=EXCLUDED.job_token,
   question_no=EXCLUDED.question_no,is_success=true,error_code=NULL,attempts=0,seed=EXCLUDED.seed,request_fingerprint=NULL,
   raw_result=EXCLUDED.raw_result,version_question_id=EXCLUDED.version_question_id,result_kind=EXCLUDED.result_kind,
   clone_fingerprint=EXCLUDED.clone_fingerprint,created_at=now();
  UPDATE public.exam_sessions SET updated_at=clock_timestamp() WHERE id=s.id;
 END IF;
 RETURN jsonb_build_object('success',true,'replayed',coalesce(prior.is_success,false),'session_id',s.id,'snapshot_id',job.id,
  'version_index',ver,'source_question_id',src->'source_question_id','version_question_id',q_id,
  'result_kind','ORIGINAL_CLONE','clone_fingerprint',digest);
END $$;
REVOKE ALL ON FUNCTION public.persist_generation_clone(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.persist_generation_clone(uuid,uuid,jsonb) TO service_role;
CREATE OR REPLACE FUNCTION public._review_apply_action(p_session_id UUID, p_question_id UUID, p_action_id UUID, p_revert BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; q public.version_questions; root public.version_questions; receipt public.review_action_receipts;
  job public.generation_job_snapshots; src jsonb; idx int; input jsonb; item jsonb; src_fp text;
  conf_rec public.source_artifact_confirmations%ROWTYPE; rev_rec public.source_artifact_revisions%ROWTYPE;
  all_items jsonb; all_hash text; solution text;
 spaces text := U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
  kind TEXT; invalidated JSONB := '[]'::jsonb; progress JSONB; result JSONB; changed BOOLEAN;
BEGIN
  s := public._review_lock_session(p_session_id,true);
  IF p_action_id IS NULL THEN RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('review_action:'||p_action_id::text,0));
  kind := CASE WHEN p_revert THEN 'REVERT' ELSE 'ACCEPT' END;
  SELECT * INTO receipt FROM public.review_action_receipts WHERE action_id=p_action_id;
  IF FOUND THEN
    IF receipt.session_id IS DISTINCT FROM s.id OR receipt.question_id IS DISTINCT FROM p_question_id
      OR receipt.actor_id IS DISTINCT FROM auth.uid() OR receipt.action_type IS DISTINCT FROM kind THEN
      RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
    END IF;
    RETURN receipt.result || jsonb_build_object('replayed',true);
  END IF;
  PERFORM public._review_assert_editable(s.id);
  SELECT q0.* INTO q FROM public.version_questions q0 JOIN public.exam_versions v ON v.id=q0.version_id
    WHERE q0.id=p_question_id AND v.session_id=s.id FOR UPDATE OF q0;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002'; END IF;
  IF NOT q.is_current THEN RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE='55000'; END IF;
  IF q.status='regenerating' THEN RAISE EXCEPTION 'REVIEW_BUSY' USING ERRCODE='55000'; END IF;
  root := q;
  IF p_revert THEN
    SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
    IF job.id IS NULL THEN RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023'; END IF;
  SELECT x, ord::int - 1 INTO src, idx
  FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord)
  WHERE (x->>'source_question_id')::uuid = q.source_question_id;

  IF src IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source_question_id not found in frozen snapshot' USING ERRCODE = '22023';
  END IF;
  IF (SELECT count(*) FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') x
      WHERE (x->>'source_question_id')::uuid = q.source_question_id) <> 1 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: non-unique source in frozen snapshot' USING ERRCODE = '22023';
  END IF;

  -- Bind snapshot confirmation to the same session
  SELECT * INTO conf_rec FROM public.source_artifact_confirmations
  WHERE confirmation_id = job.confirmation_id AND session_id = job.session_id;
  IF conf_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmation missing or mismatched' USING ERRCODE = '22023';
  END IF;

  -- Bind source revision to that confirmation/source
  SELECT * INTO rev_rec FROM public.source_artifact_revisions
  WHERE confirmation_id = job.confirmation_id
    AND source_question_id = q.source_question_id
    AND source_revision_id = (src->>'source_revision_id')::uuid;
  IF rev_rec.confirmation_id IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source revision not bound to confirmation' USING ERRCODE = '22023';
  END IF;

  -- Frozen confirmed_input must equal stored revision input
  IF rev_rec.confirmed_input IS DISTINCT FROM src->'confirmed_input' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmed_input mismatch with stored revision' USING ERRCODE = '22023';
  END IF;

  -- Check blueprint revision binding
  IF src->>'blueprint_revision_id' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing blueprint_revision_id' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.canonical_blueprint_revisions b
    WHERE b.blueprint_revision_id = (src->>'blueprint_revision_id')::uuid
      AND b.source_revision_id = (src->>'source_revision_id')::uuid
      AND b.source_question_id = q.source_question_id
  ) THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: blueprint revision not bound to source' USING ERRCODE = '22023';
  END IF;

  -- Check source order if present
  IF job.source_order IS NOT NULL AND jsonb_typeof(job.source_order) = 'array' THEN
    IF (SELECT jsonb_agg((x->>'source_question_id')::text ORDER BY ord)
        FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord))
       IS DISTINCT FROM job.source_order THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source order mismatch' USING ERRCODE = '22023';
    END IF;
  END IF;

  -- Recompute source fingerprint
  item := public._generation_source_item(src->'confirmed_input');
  src_fp := encode(sha256(convert_to(public._generation_json(jsonb_build_array(item)), 'UTF8')), 'hex');
  IF src_fp IS DISTINCT FROM src->>'source_fingerprint' OR src_fp IS DISTINCT FROM rev_rec.source_fingerprint THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source fingerprint mismatch' USING ERRCODE = '22023';
  END IF;

  -- Recompute confirmed_source_hash across all confirmed sources
  SELECT coalesce(jsonb_agg(public._generation_source_item(x->'confirmed_input') ORDER BY ord), '[]'::jsonb)
  INTO all_items
  FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord);

  all_hash := encode(sha256(convert_to(public._generation_json(all_items), 'UTF8')), 'hex');
  IF all_hash IS DISTINCT FROM job.confirmed_source_hash THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: confirmed source hash mismatch' USING ERRCODE = '22023';
  END IF;

  -- Validate confirmed_input content
  input := src->'confirmed_input';
  IF input IS NULL OR jsonb_typeof(input) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or invalid confirmed_input' USING ERRCODE = '22023';
  END IF;

  -- Non-whitespace stem
  IF jsonb_typeof(input->'question_text') IS DISTINCT FROM 'string'
     OR coalesce(input->>'question_text', '') !~ ('[^' || spaces || ']') THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: missing or whitespace question_text' USING ERRCODE = '22023';
  END IF;

  -- Four non-whitespace string options
  IF jsonb_typeof(input->'options') IS DISTINCT FROM 'array'
     OR jsonb_array_length(input->'options') <> 4
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(input->'options') opt
       WHERE jsonb_typeof(opt) IS DISTINCT FROM 'string'
          OR coalesce(opt#>>'{}', '') !~ ('[^' || spaces || ']')
     ) THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid options array' USING ERRCODE = '22023';
  END IF;

  -- A-D key
  IF input->>'correct_answer' NOT IN ('A', 'B', 'C', 'D') OR input->>'correct_answer' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid correct_answer' USING ERRCODE = '22023';
  END IF;

  IF input->'solution' IS NOT NULL AND jsonb_typeof(input->'solution') NOT IN ('null','string') THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed solution' USING ERRCODE='22023';
  END IF;
  solution := CASE WHEN coalesce(input->>'solution','') ~ ('[^' || spaces || ']')
    THEN input->>'solution' ELSE 'Không có lời giải cho câu hỏi này.' END;
    UPDATE public.version_questions SET is_current=false,updated_at=clock_timestamp() WHERE id=q.id;
    INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,solution_md,
      canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status,is_current,is_reverted,has_warning,validation_report)
    VALUES(q.version_id,q.source_question_id,q.question_no,input->>'question_text',input->'options',input->>'correct_answer',solution,
      (src->>'question_no')::int,input->'options',input->>'correct_answer',solution,'pending_review',true,true,true,
      jsonb_build_object('reason','REVERT','validation_status','not_validated','source_revision_id',src->>'source_revision_id',
        'source_fingerprint',src->>'source_fingerprint','confirmed_source_hash',job.confirmed_source_hash)) RETURNING * INTO root;
    invalidated := public._review_invalidate(s.id);
    changed := true;
  ELSE
    changed := q.status<>'approved';
    UPDATE public.version_questions SET status='approved',updated_at=clock_timestamp() WHERE id=q.id AND changed;
  END IF;
  IF changed THEN
    INSERT INTO public.review_logs(version_question_id,session_id,user_id,action_type,reason,regenerated_from_id)
      VALUES(root.id,s.id,auth.uid(),kind::public.review_action_type,kind,
        CASE WHEN root.id<>q.id THEN q.id ELSE NULL END);
  END IF;
  progress := public._review_recalculate(s.id);
  SELECT * INTO s FROM public.exam_sessions WHERE id=s.id;
  result := jsonb_build_object('session_id',s.id,'session_status',s.status,'replayed',false,'previous_question_id',q.id,
    'question_id',root.id,'question_status',CASE WHEN p_revert THEN 'pending_review' ELSE 'approved' END,'invalidated_version_ids',invalidated,'progress',progress);
  INSERT INTO public.review_action_receipts(action_id,session_id,question_id,actor_id,action_type,result)
    VALUES(p_action_id,s.id,q.id,auth.uid(),kind,result);
  RETURN result;
END $$;

COMMIT;
