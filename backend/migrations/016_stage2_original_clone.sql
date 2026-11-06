-- TASK-207 / PR #32: Original Clone persistence. Apply after 015.
BEGIN;
ALTER TABLE public.generation_target_results
 ADD COLUMN IF NOT EXISTS result_kind text NOT NULL DEFAULT 'AI_RESULT',
 ADD COLUMN IF NOT EXISTS clone_fingerprint text;
ALTER TABLE public.generation_target_results ALTER COLUMN request_fingerprint DROP NOT NULL;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.generation_target_results'::regclass
  AND conname='generation_result_kind') THEN
  ALTER TABLE public.generation_target_results ADD CONSTRAINT generation_result_kind CHECK (
   (result_kind='AI_RESULT' AND request_fingerprint IS NOT NULL AND clone_fingerprint IS NULL)
   OR (result_kind='ORIGINAL_CLONE' AND request_fingerprint IS NULL
    AND clone_fingerprint ~ '^[a-f0-9]{64}$' AND clone_fingerprint IS NOT NULL
    AND is_success AND error_code IS NULL AND attempts=0));
 END IF;
END $$;

-- Historical wrong-kind rows require reconciliation, including failed results.
-- Never hide them as missing slots or mutate them while recovering a job.
CREATE OR REPLACE FUNCTION public._generation_assert_result_kind(p_session_id uuid,p_snapshot_id uuid)
RETURNS void LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.generation_target_results r
  JOIN public.generation_job_snapshots j ON j.id=r.snapshot_id AND j.session_id=r.session_id
  WHERE r.session_id=p_session_id AND r.snapshot_id=p_snapshot_id
   AND r.result_kind IS DISTINCT FROM CASE
    WHEN j.public_modes='[]'::jsonb AND j.canonical_dimensions='[]'::jsonb THEN 'ORIGINAL_CLONE'
    ELSE 'AI_RESULT' END) THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result kind differs from frozen job; explicit reconciliation required' USING ERRCODE='55006';
 END IF;
END $$;
REVOKE ALL ON FUNCTION public._generation_assert_result_kind(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

-- Only exact snapshot slots with an intact generation projection are resumable.
-- Review/shuffle may change the projection after generation; those lifecycle
-- changes are not an invitation to regenerate/overwrite an already committed slot.
CREATE OR REPLACE FUNCTION public._generation_committed(p_session_id uuid,p_snapshot_id uuid)
RETURNS SETOF public.generation_target_results
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT r.* FROM public.generation_target_results r
 JOIN public.generation_job_snapshots j ON j.id=r.snapshot_id AND j.session_id=r.session_id
 JOIN public.version_questions q ON q.id=r.version_question_id AND q.is_current
 JOIN public.exam_versions v ON v.id=q.version_id AND v.session_id=r.session_id AND v.version_code=(100+r.version_index)::text
 CROSS JOIN LATERAL jsonb_array_elements(j.snapshot_payload->'confirmed_sources') src
 CROSS JOIN LATERAL (SELECT CASE r.result_kind WHEN 'ORIGINAL_CLONE' THEN
  jsonb_build_object('question_text',r.raw_result->'content','options',r.raw_result->'options',
   'correct_key',r.raw_result->'correct_key','solution_md',r.raw_result->'solution_md','has_warning',false)
  ELSE r.raw_result->'candidate' END c) payload
 WHERE r.session_id=p_session_id AND r.snapshot_id=p_snapshot_id AND r.is_success
 AND r.result_kind=CASE WHEN j.public_modes='[]'::jsonb AND j.canonical_dimensions='[]'::jsonb
  THEN 'ORIGINAL_CLONE' ELSE 'AI_RESULT' END
 AND r.version_index BETWEEN 1 AND j.n_versions AND src->>'source_question_id'=r.source_question_id::text
 AND r.question_no=(src->>'question_no')::int AND q.source_question_id=r.source_question_id
 AND q.question_no=r.question_no AND q.canonical_question_no=r.question_no
 AND q.content IS NOT DISTINCT FROM payload.c->>'question_text'
 AND q.options IS NOT DISTINCT FROM payload.c->'options' AND q.canonical_options IS NOT DISTINCT FROM q.options
 AND q.correct_key IS NOT DISTINCT FROM payload.c->>'correct_key' AND q.canonical_correct_key IS NOT DISTINCT FROM q.correct_key
 AND q.solution_md IS NOT DISTINCT FROM payload.c->>'solution_md' AND q.canonical_solution_md IS NOT DISTINCT FROM q.solution_md
 AND q.has_warning IS NOT DISTINCT FROM (payload.c->>'has_warning')::boolean
$$;
REVOKE ALL ON FUNCTION public._generation_committed(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.persist_generation_clone(p_session_id uuid,p_job_token uuid,p_clone_record jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots; src jsonb; input jsonb;
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
 expected:=jsonb_build_object('result_kind','ORIGINAL_CLONE','snapshot_id',job.id,
  'version_index',ver,'source_question_id',src->'source_question_id','question_no',src->'question_no',
  'source_revision_id',src->'source_revision_id','source_fingerprint',src->'source_fingerprint',
  'blueprint_revision_id',src->'blueprint_revision_id','confirmed_source_hash',job.confirmed_source_hash,
  'seed',job.base_seed+ver*1000+idx,'content',input->'question_text','options',input->'options',
  'correct_key',input->'correct_answer','solution_md',input->'solution');
 IF p_clone_record IS DISTINCT FROM expected
  OR p_clone_record->>'question_no' IS DISTINCT FROM expected->>'question_no'
  OR p_clone_record->>'seed' IS DISTINCT FROM expected->>'seed' THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone record differs from frozen source/slot' USING ERRCODE='22023'; END IF;
 digest:=encode(sha256(convert_to(public._generation_json(expected),'UTF8')),'hex');
 SELECT * INTO prior FROM public.generation_target_results WHERE session_id=s.id AND version_index=ver
  AND source_question_id=(src->>'source_question_id')::uuid;
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
   input->>'correct_answer',input->>'solution',(src->>'question_no')::int,input->'options',input->>'correct_answer',input->>'solution',
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

-- Retain 010's AI signature and validation, but disallow both AI success and
-- failure for clone snapshots before delegating any target/projection writes.
DO $$ BEGIN
 IF to_regprocedure('public._generation_persist_010(uuid,uuid,integer,uuid,integer,boolean,text,integer,integer,text,jsonb,text,jsonb,text,text,boolean)') IS NULL THEN
  ALTER FUNCTION public.persist_generation_result(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean)
   RENAME TO _generation_persist_010;
 END IF;
END $$;
REVOKE ALL ON FUNCTION public._generation_persist_010(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean)
 FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION public.persist_generation_result(p_session_id uuid,p_job_token uuid,p_version_index int,p_source_question_id uuid,
 p_question_no int,p_is_success boolean,p_error_code text,p_attempts int,p_seed int,p_request_fingerprint text,p_raw_result jsonb,
 p_content text,p_options jsonb,p_correct_key text,p_solution_md text,p_has_warning boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots;
BEGIN
 IF public.current_role()<>'service_role' THEN RAISE EXCEPTION 'Worker only' USING ERRCODE='42501'; END IF;
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF s.status<>'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
  RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE='55006'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 IF job.public_modes='[]'::jsonb AND job.canonical_dimensions='[]'::jsonb THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone job requires ORIGINAL_CLONE result kind' USING ERRCODE='22023'; END IF;
 PERFORM public._generation_assert_result_kind(s.id,job.id);
 RETURN public._generation_persist_010(p_session_id,p_job_token,p_version_index,p_source_question_id,
  p_question_no,p_is_success,p_error_code,p_attempts,p_seed,p_request_fingerprint,p_raw_result,
  p_content,p_options,p_correct_key,p_solution_md,p_has_warning);
END $$;
REVOKE ALL ON FUNCTION public.persist_generation_result(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.persist_generation_result(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean) TO service_role;

-- Keep 010's state, manifest, retry and legacy behavior behind private wrappers.
DO $$ BEGIN
 IF to_regprocedure('public._generation_claim_010(uuid,boolean)') IS NULL THEN
  ALTER FUNCTION public.claim_generation_job(uuid,boolean) RENAME TO _generation_claim_010;
  ALTER FUNCTION public.finish_generation_job(uuid,text,uuid) RENAME TO _generation_finish_010;
 END IF;
END $$;
REVOKE ALL ON FUNCTION public._generation_claim_010(uuid,boolean),public._generation_finish_010(uuid,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION public.claim_generation_job(p_session_id uuid,p_is_retry boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE result jsonb; completed jsonb;
BEGIN
 result:=public._generation_claim_010(p_session_id,p_is_retry);
 IF result->>'snapshot_id' IS NULL THEN RETURN result; END IF;
 PERFORM public._generation_assert_result_kind(p_session_id,(result->>'snapshot_id')::uuid);
 SELECT coalesce(jsonb_agg(jsonb_build_object('version_code',(100+r.version_index)::text,'version_index',r.version_index,
  'source_question_id',r.source_question_id,'question_no',r.question_no,'result_kind',r.result_kind)
  ORDER BY r.version_index,r.question_no),'[]') INTO completed
 FROM public._generation_committed(p_session_id,(result->>'snapshot_id')::uuid) r;
 RETURN result||jsonb_build_object('committed_targets',completed);
END $$;
REVOKE ALL ON FUNCTION public.claim_generation_job(uuid,boolean) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.claim_generation_job(uuid,boolean) TO authenticated,service_role;

CREATE OR REPLACE FUNCTION public.load_generation_completed_results(p_session_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots; completed jsonb; failures jsonb;
BEGIN
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF public.current_role()<>'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 IF job.id IS NULL THEN RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing resume snapshot' USING ERRCODE='55006'; END IF;
 PERFORM public._generation_assert_result_kind(s.id,job.id);
 SELECT coalesce(jsonb_agg(jsonb_build_object('snapshot_id',r.snapshot_id,'version_index',r.version_index,'source_question_id',r.source_question_id,
  'question_no',r.question_no,'is_success',true,'seed',r.seed,'request_fingerprint',r.request_fingerprint,'raw_result',r.raw_result,
  'result_kind',r.result_kind,'clone_fingerprint',r.clone_fingerprint) ORDER BY r.version_index,r.question_no),'[]') INTO completed
 FROM public._generation_committed(s.id,job.id) r;
 SELECT coalesce(jsonb_agg(jsonb_build_object('snapshot_id',r.snapshot_id,'version_index',r.version_index,'source_question_id',r.source_question_id,
  'question_no',r.question_no,'is_success',false,'seed',r.seed,'request_fingerprint',r.request_fingerprint,'raw_result',r.raw_result,
  'result_kind',r.result_kind,'clone_fingerprint',r.clone_fingerprint) ORDER BY r.version_index,r.question_no),'[]') INTO failures
 FROM public.generation_target_results r WHERE r.session_id=s.id AND r.snapshot_id=job.id AND NOT r.is_success;
 RETURN jsonb_build_object('session_id',s.id,'snapshot_id',job.id,'context',job.snapshot_payload,'completed',completed,'failures',failures);
END $$;
REVOKE ALL ON FUNCTION public.load_generation_completed_results(uuid) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.load_generation_completed_results(uuid) TO authenticated,service_role;

CREATE OR REPLACE FUNCTION public.finish_generation_job(p_session_id uuid,p_outcome text,p_job_token uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots;
BEGIN
 IF public.current_role()<>'service_role' THEN RAISE EXCEPTION 'Worker only' USING ERRCODE='42501'; END IF;
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF s.status<>'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
  RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE='55006'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 PERFORM public._generation_assert_result_kind(s.id,job.id);
 IF job.id IS NOT NULL AND p_outcome='generated' AND EXISTS(
  SELECT 1 FROM generate_series(1,job.n_versions) ver(idx) CROSS JOIN jsonb_array_elements(job.snapshot_payload->'confirmed_sources') src
  WHERE NOT EXISTS(SELECT 1 FROM public._generation_committed(s.id,job.id) r
   WHERE r.version_index=ver.idx AND r.source_question_id::text=src->>'source_question_id'
    AND r.question_no=(src->>'question_no')::int)) THEN
  RAISE EXCEPTION 'Cannot finish as generated: successful targets incomplete' USING ERRCODE='22023'; END IF;
 RETURN public._generation_finish_010(p_session_id,p_outcome,p_job_token);
END $$;
REVOKE ALL ON FUNCTION public.finish_generation_job(uuid,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_generation_job(uuid,text,uuid) TO service_role;
COMMIT;
