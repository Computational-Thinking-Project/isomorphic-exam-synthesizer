-- TASK-207a/b: forward W2 integration after the adopted 004-009 chain.
BEGIN;
ALTER TABLE public.generation_configs ADD COLUMN IF NOT EXISTS source_manifest jsonb;
ALTER TABLE public.generation_configs ADD COLUMN IF NOT EXISTS canonical_dimensions jsonb;
ALTER TABLE public.generation_configs ADD COLUMN IF NOT EXISTS mapping_version text;

CREATE TABLE IF NOT EXISTS public.generation_job_snapshots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 session_id uuid NOT NULL UNIQUE REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
 job_token uuid NOT NULL UNIQUE, confirmation_id uuid NOT NULL,
 source_order jsonb NOT NULL, confirmed_source_hash text NOT NULL,
 base_seed int NOT NULL DEFAULT 100, n_versions int NOT NULL CHECK(n_versions BETWEEN 1 AND 4),
 public_modes jsonb NOT NULL, canonical_dimensions jsonb NOT NULL, mapping_version text NOT NULL,
 snapshot_payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.generation_target_results (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 session_id uuid NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
 snapshot_id uuid NOT NULL REFERENCES public.generation_job_snapshots(id) ON DELETE CASCADE,
 job_token uuid NOT NULL, version_index int NOT NULL CHECK(version_index BETWEEN 1 AND 4),
 source_question_id uuid NOT NULL, question_no int NOT NULL, is_success boolean NOT NULL,
 error_code text, attempts int NOT NULL CHECK(attempts>=0), seed int NOT NULL,
 request_fingerprint text NOT NULL, raw_result jsonb NOT NULL,
 version_question_id uuid REFERENCES public.version_questions(id) ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(session_id,version_index,source_question_id)
);
ALTER TABLE public.generation_job_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generation_target_results ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.generation_job_snapshots,public.generation_target_results FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.generation_job_snapshots,public.generation_target_results TO service_role;

-- SECURITY DEFINER changes current_user, but not the connection's SET ROLE.
-- A JWT claim GUC must never promote authenticated to service_role.
CREATE OR REPLACE FUNCTION public.current_role() RETURNS text
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT coalesce(nullif(current_setting('role',true),'none'),session_user)
$$;

-- Match the existing Python canonical JSON contract (no jsonb::text hash).
CREATE OR REPLACE FUNCTION public._generation_json(p_value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp
SET extra_float_digits=3 AS $$
DECLARE result text; number_text text; rendered text; coefficient text; sign_prefix text;
 digits text; exponent int; decimal_position int; precision int; rounded_digits text; binary_value float8;
BEGIN
 CASE jsonb_typeof(p_value)
 WHEN 'object' THEN
  SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||public._generation_json(value),',' ORDER BY key COLLATE "C"),'')||'}'
   INTO result FROM jsonb_each(p_value);
 WHEN 'array' THEN
  SELECT '['||coalesce(string_agg(public._generation_json(value),',' ORDER BY ord),'')||']'
   INTO result FROM jsonb_array_elements(p_value) WITH ORDINALITY a(value,ord);
 WHEN 'number' THEN
  number_text:=p_value::text;
  IF strpos(number_text,'.')=0 THEN
   -- JSONB integer tokens are arbitrary-precision ints in Python, not floats.
   result:=number_text;
  ELSE
   BEGIN
    binary_value:=number_text::float8; rendered:=binary_value::text;
   EXCEPTION WHEN numeric_value_out_of_range THEN
    IF abs(number_text::numeric)>=1 THEN RAISE; END IF;
    rendered:=CASE WHEN left(number_text,1)='-' THEN '-0' ELSE '0' END;
   END;
   coefficient:=split_part(rendered,'e',1);
   sign_prefix:='';
   IF left(coefficient,1)='-' THEN sign_prefix:='-'; coefficient:=substr(coefficient,2); END IF;
   decimal_position:=strpos(coefficient,'.');
   IF decimal_position=0 THEN decimal_position:=length(coefficient)+1; END IF;
   exponent:=coalesce(nullif(split_part(rendered,'e',2),'')::int,0)+decimal_position-2;
   digits:=replace(coefficient,'.','');
   WHILE length(digits)>1 AND left(digits,1)='0' LOOP
    digits:=substr(digits,2); exponent:=exponent-1;
   END LOOP;
   -- PostgreSQL avoids midpoint representations (1e23); Python accepts them.
   -- Shorten only if rounding recovers the exact same binary64 value.
   FOR precision IN 1..(length(digits)-1) LOOP
    rounded_digits:=round(digits::numeric,precision-length(digits))::text;
    BEGIN
     IF (sign_prefix||rounded_digits||'e'||(exponent-length(digits)+1)::text)::float8=binary_value THEN
      exponent:=exponent+length(rounded_digits)-length(digits);
      digits:=rounded_digits;
      EXIT;
     END IF;
    EXCEPTION WHEN numeric_value_out_of_range THEN
     NULL;
    END;
   END LOOP;
   digits:=rtrim(digits,'0');
   IF digits='' THEN result:=sign_prefix||'0.0';
   ELSIF exponent < -4 OR exponent >= 16 THEN
    result:=sign_prefix||left(digits,1)||CASE WHEN length(digits)>1 THEN '.'||substr(digits,2) ELSE '' END
     ||'e'||CASE WHEN exponent<0 THEN '-' ELSE '+' END
     ||CASE WHEN abs(exponent)<10 THEN '0' ELSE '' END||abs(exponent)::text;
   ELSIF exponent<0 THEN
    result:=sign_prefix||'0.'||repeat('0',-exponent-1)||digits;
   ELSIF length(digits)<=exponent+1 THEN
    result:=sign_prefix||digits||repeat('0',exponent+1-length(digits))||'.0';
   ELSE result:=sign_prefix||left(digits,exponent+1)||'.'||substr(digits,exponent+2);
   END IF;
  END IF;
 ELSE result:=p_value::text;
 END CASE;
 RETURN result;
END $$;

-- Narrow confirmed-input projection of source_to_item, pinned by parity tests.
CREATE OR REPLACE FUNCTION public._generation_source_item(p_input jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE qid text; stem text:=p_input->>'question_text'; lang text:='vi'; opts jsonb; sol jsonb;
 spaces text:=U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
BEGIN
 qid:='q_'||substr(encode(sha256(convert_to(p_input->>'id','UTF8')),'hex'),1,24);
 IF stem !~ '[ăâđêôơưĂÂĐÊÔƠƯẠ-ỹ]' AND stem ~* '\m(the|find|calculate|explain|which|what|given|compute)\M' THEN lang:='en'; END IF;
 SELECT jsonb_agg(jsonb_build_object('id',qid||'.'||substr('ABCD',ord::int,1),
  'content',jsonb_build_array(jsonb_build_object('id',qid||'.'||substr('ABCD',ord::int,1)||'.text','type','text','text',value))) ORDER BY ord)
 INTO opts FROM jsonb_array_elements(p_input->'options') WITH ORDINALITY a(value,ord);
 IF coalesce(p_input->>'solution','') ~ ('[^'||spaces||']') THEN
  sol:=jsonb_build_array(jsonb_build_object('id',qid||'.solution','type','text','text',p_input->>'solution'));
 END IF;
 RETURN jsonb_build_object('source',jsonb_build_object('question_id',qid,
  'content',jsonb_build_array(jsonb_build_object('id',qid||'.stem','type','text','text',stem)),
  'options',opts,'supplied_answer',jsonb_build_object('option_ids',jsonb_build_array(qid||'.'||(p_input->>'correct_answer')),'value',null,'explanation',null),
  'supplied_solution',sol,'references','[]'::jsonb),
  'context',jsonb_build_object('subject','mathematics','language',lang));
END $$;
REVOKE ALL ON FUNCTION public._generation_json(jsonb),public._generation_source_item(jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.get_generation_source_snapshot(p_session_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; c public.source_artifact_confirmations;
 sources jsonb:='[]'; manifest jsonb:='[]'; items jsonb:='[]'; item jsonb; r record;
 reason text; total int; result jsonb;
BEGIN
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF public.current_role()<>'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO c FROM public.source_artifact_confirmations WHERE session_id=s.id ORDER BY confirmed_at DESC,confirmation_id DESC LIMIT 1;
 IF NOT FOUND THEN RETURN jsonb_build_object('session_id',s.id,'ready',false,'reason','NO_CONFIRMATION','confirmed_sources','[]'::jsonb); END IF;
 SELECT count(*) INTO total FROM public.source_questions WHERE session_id=s.id;
 IF total NOT BETWEEN 1 AND 20 OR jsonb_typeof(c.result->'sources') IS DISTINCT FROM 'array' THEN reason:='INVALID_SOURCE_COUNT';
 ELSIF jsonb_array_length(c.result->'sources')<>total THEN reason:='SOURCE_COUNT_MISMATCH'; END IF;
 IF reason IS NULL THEN
  FOR r IN SELECT q.id,q.question_no,public._artifact_source_input(q) live_input,
   h.source_revision_id,h.blueprint_revision_id,sr.confirmation_id,sr.confirmed_input,sr.source_fingerprint,
   b.canonical_blueprint,b.schema_version
   FROM public.source_questions q LEFT JOIN public.source_artifact_heads h ON h.source_question_id=q.id
   LEFT JOIN public.source_artifact_revisions sr ON sr.source_revision_id=h.source_revision_id AND sr.source_question_id=q.id
   LEFT JOIN public.canonical_blueprint_revisions b ON b.blueprint_revision_id=h.blueprint_revision_id
    AND b.source_revision_id=sr.source_revision_id AND b.source_question_id=q.id
   WHERE q.session_id=s.id ORDER BY q.question_no,q.id
  LOOP
   IF r.confirmation_id IS DISTINCT FROM c.confirmation_id OR r.confirmed_input IS NULL
    OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(c.result->'sources') x WHERE x->>'source_question_id'=r.id::text AND x->>'source_revision_id'=r.source_revision_id::text)
    OR r.confirmed_input IS DISTINCT FROM r.live_input THEN reason:='ARTIFACT_STALE'; EXIT; END IF;
   IF r.canonical_blueprint IS NULL OR r.schema_version IS DISTINCT FROM '0.4.0'
    OR jsonb_typeof(r.canonical_blueprint#>'{requirement,variation_policy,allowed_transformations}') IS DISTINCT FROM 'array' THEN
    reason:='CANONICAL_BLUEPRINTS_INCOMPLETE'; EXIT; END IF;
   IF EXISTS(SELECT 1 FROM jsonb_array_elements(r.canonical_blueprint#>'{requirement,variation_policy,allowed_transformations}') t
    WHERE jsonb_typeof(t) IS DISTINCT FROM 'object' OR coalesce(t->>'dimension','') NOT IN ('values','context','wording','names','representation','option_order')) THEN
    reason:='INVALID_BLUEPRINT_POLICY'; EXIT; END IF;
   item:=public._generation_source_item(r.confirmed_input);
   IF encode(sha256(convert_to(public._generation_json(jsonb_build_array(item)),'UTF8')),'hex') IS DISTINCT FROM r.source_fingerprint THEN
    reason:='SOURCE_FINGERPRINT_MISMATCH'; EXIT; END IF;
   items:=items||jsonb_build_array(item);
   manifest:=manifest||jsonb_build_array(jsonb_build_object('source_question_id',r.id,'question_no',r.question_no,
    'source_revision_id',r.source_revision_id,'blueprint_revision_id',r.blueprint_revision_id));
   sources:=sources||jsonb_build_array(jsonb_build_object('source_question_id',r.id,'question_no',r.question_no,
    'source_revision_id',r.source_revision_id,'blueprint_revision_id',r.blueprint_revision_id,
    'source_fingerprint',r.source_fingerprint,'confirmed_input',r.confirmed_input,'canonical_blueprint',r.canonical_blueprint,
    'blueprint_fingerprint',encode(sha256(convert_to(public._generation_json(r.canonical_blueprint),'UTF8')),'hex')));
  END LOOP;
 END IF;
 result:=jsonb_build_object('session_id',s.id,'confirmation_id',c.confirmation_id,'ready',reason IS NULL,'reason',reason);
 IF reason IS NOT NULL THEN RETURN result||jsonb_build_object('confirmed_sources','[]'::jsonb); END IF;
 RETURN result||jsonb_build_object('confirmed_sources',sources,
  'source_order',(SELECT jsonb_agg(x->'source_question_id' ORDER BY ord) FROM jsonb_array_elements(sources) WITH ORDINALITY a(x,ord)),
  'manifest',jsonb_build_object('confirmation_id',c.confirmation_id,'sources',manifest),
  'confirmed_source_hash',encode(sha256(convert_to(public._generation_json(items),'UTF8')),'hex'));
END $$;
REVOKE ALL ON FUNCTION public.get_generation_source_snapshot(uuid) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.get_generation_source_snapshot(uuid) TO authenticated,service_role;

DROP FUNCTION IF EXISTS public.save_generation_config(uuid,int,jsonb,jsonb);
CREATE OR REPLACE FUNCTION public.save_generation_config(
 p_session_id uuid,p_n_versions int,p_active_variation_modes jsonb DEFAULT '[]',
 p_ordering_preferences jsonb DEFAULT '{"shuffle_questions":true,"shuffle_options":true}',p_expected_snapshot jsonb DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; snap jsonb; modes jsonb; dims jsonb; cfg uuid; n int;
BEGIN
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF public.current_role()<>'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 IF s.status NOT IN ('blueprinted','configured') OR s.approved_at IS NOT NULL THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid session state' USING ERRCODE='55006'; END IF;
 IF p_n_versions IS NULL OR p_n_versions NOT BETWEEN 1 AND 4
  OR NOT public.is_valid_variation_modes(p_active_variation_modes)
  OR jsonb_typeof(p_ordering_preferences) IS DISTINCT FROM 'object'
  OR jsonb_typeof(p_ordering_preferences->'shuffle_questions') IS DISTINCT FROM 'boolean'
  OR jsonb_typeof(p_ordering_preferences->'shuffle_options') IS DISTINCT FROM 'boolean' THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid configuration' USING ERRCODE='22023'; END IF;
 modes:=p_active_variation_modes;
 IF modes='["NONE"]'::jsonb THEN modes:='[]'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(modes) m WHERE m NOT IN ('NUMERICAL','parameter_variation','context_swap')) THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unsupported public mode' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(mode ORDER BY first_ord),'[]') INTO modes FROM
  (SELECT mode,min(ord) first_ord FROM jsonb_array_elements_text(modes) WITH ORDINALITY a(mode,ord) GROUP BY mode) d;
 SELECT coalesce(jsonb_agg(dim ORDER BY dim),'[]') INTO dims FROM
  (SELECT DISTINCT CASE m WHEN 'context_swap' THEN 'context' ELSE 'values' END dim FROM jsonb_array_elements_text(modes) m) d;
 snap:=public.get_generation_source_snapshot(s.id);
 IF snap->>'reason'='NO_CONFIRMATION' THEN
  SELECT count(*) INTO n FROM public.source_questions WHERE session_id=s.id;
  IF n NOT BETWEEN 1 AND 20 OR EXISTS(
   SELECT 1 FROM public.source_questions q LEFT JOIN public.question_blueprints b ON b.source_question_id=q.id
   WHERE q.session_id=s.id AND (b.confirmed_at IS NULL OR NOT public.is_valid_variation_modes(b.variation_modes))) THEN
   RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid legacy blueprints' USING ERRCODE='22023'; END IF;
  IF EXISTS(SELECT 1 FROM public.source_questions q JOIN public.question_blueprints b ON b.source_question_id=q.id
   CROSS JOIN jsonb_array_elements_text(modes) m WHERE q.session_id=s.id AND NOT (b.variation_modes ? m)) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: legacy mode intersection' USING ERRCODE='22023'; END IF;
 ELSE
  IF (snap->>'ready')::boolean IS DISTINCT FROM true THEN
   RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: %',snap->>'reason' USING ERRCODE='22023'; END IF;
  IF p_expected_snapshot IS DISTINCT FROM snap->'manifest' THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: snapshot changed or missing' USING ERRCODE='55006'; END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(snap->'confirmed_sources') src CROSS JOIN jsonb_array_elements_text(dims) dim
   WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(src#>'{canonical_blueprint,requirement,variation_policy,allowed_transformations}') t WHERE t->>'dimension'=dim)) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: canonical mode intersection' USING ERRCODE='22023'; END IF;
 END IF;
 INSERT INTO public.generation_configs(session_id,n_versions,active_variation_modes,ordering_preferences,source_manifest,canonical_dimensions,mapping_version)
 VALUES(s.id,p_n_versions,modes,p_ordering_preferences,snap->'manifest',dims,'1.0')
 ON CONFLICT(session_id) DO UPDATE SET n_versions=EXCLUDED.n_versions,active_variation_modes=EXCLUDED.active_variation_modes,
 ordering_preferences=EXCLUDED.ordering_preferences,source_manifest=EXCLUDED.source_manifest,canonical_dimensions=EXCLUDED.canonical_dimensions,mapping_version=EXCLUDED.mapping_version
 RETURNING id INTO cfg;
 UPDATE public.exam_sessions SET status='configured' WHERE id=s.id;
 RETURN jsonb_build_object('success',true,'session_id',s.id,'config_id',cfg,'status','configured','config',
  jsonb_build_object('n_versions',p_n_versions,'active_variation_modes',modes,'ordering_preferences',p_ordering_preferences,
   'source_manifest',snap->'manifest','canonical_dimensions',dims,'mapping_version','1.0'));
END $$;
REVOKE ALL ON FUNCTION public.save_generation_config(uuid,int,jsonb,jsonb,jsonb) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.save_generation_config(uuid,int,jsonb,jsonb,jsonb) TO authenticated,service_role;
REVOKE INSERT,UPDATE,DELETE ON public.generation_configs FROM PUBLIC,anon,authenticated;
DO $$ DECLARE cols text; BEGIN
 SELECT string_agg(quote_ident(attname),',') INTO cols FROM pg_attribute
 WHERE attrelid='public.generation_configs'::regclass AND attnum>0 AND NOT attisdropped;
 EXECUTE format('REVOKE INSERT (%s),UPDATE (%s) ON public.generation_configs FROM PUBLIC,anon,authenticated',cols,cols);
END $$;

-- Preserve the existing legacy path; wrappers cannot be renamed on replay.
DO $$ BEGIN
 IF to_regprocedure('public._generation_legacy_claim(uuid,boolean)') IS NULL THEN
  ALTER FUNCTION public.claim_generation_job(uuid,boolean) RENAME TO _generation_legacy_claim;
  ALTER FUNCTION public.persist_version_question(uuid,uuid,int,uuid,int,text,jsonb,text,text,boolean) RENAME TO _generation_legacy_persist;
  ALTER FUNCTION public.finish_generation_job(uuid,text,uuid) RENAME TO _generation_legacy_finish;
 END IF;
END $$;
REVOKE ALL ON FUNCTION public._generation_legacy_claim(uuid,boolean),public._generation_legacy_persist(uuid,uuid,int,uuid,int,text,jsonb,text,text,boolean),public._generation_legacy_finish(uuid,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.claim_generation_job(p_session_id uuid,p_is_retry boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; cfg public.generation_configs; snap jsonb; job public.generation_job_snapshots; token uuid; completed jsonb;
BEGIN
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF public.current_role()<>'service_role' AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.source_artifact_confirmations WHERE session_id=s.id) THEN
  RETURN public._generation_legacy_claim(s.id,p_is_retry); END IF;
 IF p_is_retry IS NULL OR s.approved_at IS NOT NULL OR
  (NOT p_is_retry AND s.status<>'configured') OR (p_is_retry AND s.status NOT IN ('failed','partial_generated')) THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: cannot claim current state' USING ERRCODE='55006'; END IF;
 SELECT * INTO cfg FROM public.generation_configs WHERE session_id=s.id;
 IF NOT FOUND THEN RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing config' USING ERRCODE='55006'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 token:=gen_random_uuid();
 IF p_is_retry THEN
  IF job.id IS NULL OR job.n_versions IS DISTINCT FROM cfg.n_versions OR job.public_modes IS DISTINCT FROM cfg.active_variation_modes
   OR job.canonical_dimensions IS DISTINCT FROM cfg.canonical_dimensions OR job.mapping_version IS DISTINCT FROM cfg.mapping_version
   OR job.snapshot_payload->'manifest' IS DISTINCT FROM cfg.source_manifest
   OR job.snapshot_payload->'ordering_preferences' IS DISTINCT FROM cfg.ordering_preferences THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing or incompatible retry snapshot' USING ERRCODE='55006'; END IF;
 ELSE
  IF job.id IS NOT NULL THEN RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: generation already started' USING ERRCODE='55006'; END IF;
  snap:=public.get_generation_source_snapshot(s.id);
  IF (snap->>'ready')::boolean IS DISTINCT FROM true THEN
   RAISE EXCEPTION 'ERR_SOURCE_NOT_READY' USING ERRCODE='22023'; END IF;
  IF cfg.source_manifest IS DISTINCT FROM snap->'manifest' THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: configured source changed' USING ERRCODE='55006'; END IF;
  INSERT INTO public.generation_job_snapshots(session_id,job_token,confirmation_id,source_order,confirmed_source_hash,base_seed,
   n_versions,public_modes,canonical_dimensions,mapping_version,snapshot_payload)
  VALUES(s.id,token,(snap->>'confirmation_id')::uuid,snap->'source_order',snap->>'confirmed_source_hash',100,cfg.n_versions,
   cfg.active_variation_modes,cfg.canonical_dimensions,cfg.mapping_version,
   snap||jsonb_build_object('base_seed',100,'n_versions',cfg.n_versions,'public_modes',cfg.active_variation_modes,
    'canonical_dimensions',cfg.canonical_dimensions,'mapping_version',cfg.mapping_version,'ordering_preferences',cfg.ordering_preferences)) RETURNING * INTO job;
 END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('version_code',(100+r.version_index)::text,'version_index',r.version_index,
  'source_question_id',r.source_question_id,'question_no',r.question_no) ORDER BY r.version_index,r.question_no),'[]') INTO completed
 FROM public.generation_target_results r JOIN public.version_questions q ON q.id=r.version_question_id AND q.is_current
 WHERE r.session_id=s.id AND r.snapshot_id=job.id AND r.is_success;
 UPDATE public.exam_sessions SET status='generating',active_job_id=token WHERE id=s.id;
 RETURN jsonb_build_object('session_id',s.id,'job_id',token,'status','generating','starting_quota',s.gemini_call_count,
  'gemini_call_count',s.gemini_call_count,'config',jsonb_build_object('n_versions',job.n_versions,'active_variation_modes',job.public_modes,
  'ordering_preferences',job.snapshot_payload->'ordering_preferences'),'committed_targets',completed,
  'snapshot_id',job.id,'context',job.snapshot_payload);
END $$;
REVOKE ALL ON FUNCTION public.claim_generation_job(uuid,boolean) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.claim_generation_job(uuid,boolean) TO authenticated,service_role;

CREATE OR REPLACE FUNCTION public.persist_version_question(p_session_id uuid,p_job_token uuid,p_version_index int,p_source_question_id uuid,
 p_question_no int,p_content text,p_options jsonb,p_correct_key text,p_solution_md text,p_has_warning boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 PERFORM 1 FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM public.source_artifact_confirmations WHERE session_id=p_session_id) THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: W2 requires persist_generation_result' USING ERRCODE='55006'; END IF;
 RETURN public._generation_legacy_persist(p_session_id,p_job_token,p_version_index,p_source_question_id,p_question_no,p_content,p_options,p_correct_key,p_solution_md,p_has_warning);
END $$;
REVOKE ALL ON FUNCTION public.persist_version_question(uuid,uuid,int,uuid,int,text,jsonb,text,text,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.persist_version_question(uuid,uuid,int,uuid,int,text,jsonb,text,text,boolean) TO service_role;

CREATE OR REPLACE FUNCTION public.persist_generation_result(p_session_id uuid,p_job_token uuid,p_version_index int,p_source_question_id uuid,
 p_question_no int,p_is_success boolean,p_error_code text,p_attempts int,p_seed int,p_request_fingerprint text,p_raw_result jsonb,
 p_content text,p_options jsonb,p_correct_key text,p_solution_md text,p_has_warning boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots; src jsonb; idx int; prior public.generation_target_results;
 v_id uuid; q_id uuid; candidate jsonb;
BEGIN
 IF public.current_role()<>'service_role' THEN RAISE EXCEPTION 'Worker only' USING ERRCODE='42501'; END IF;
 SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF s.status<>'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
  RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE='55006'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 SELECT x,ord::int-1 INTO src,idx FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x,ord)
 WHERE x->>'source_question_id'=p_source_question_id::text;
 IF job.id IS NULL OR src IS NULL OR p_version_index IS NULL OR p_version_index NOT BETWEEN 1 AND job.n_versions
  OR p_question_no IS DISTINCT FROM (src->>'question_no')::int OR p_seed IS DISTINCT FROM job.base_seed+p_version_index*1000+idx THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid snapshot slot or seed' USING ERRCODE='22023'; END IF;
 IF p_is_success IS NULL OR p_attempts IS NULL OR p_attempts<0 OR p_request_fingerprint IS NULL OR p_request_fingerprint !~ '^[a-f0-9]{64}$'
  OR jsonb_typeof(p_raw_result) IS DISTINCT FROM 'object'
  OR p_raw_result->'version_index' IS DISTINCT FROM to_jsonb(p_version_index)
  OR p_raw_result->>'source_question_id' IS DISTINCT FROM p_source_question_id::text
  OR p_raw_result->>'request_fingerprint' IS DISTINCT FROM p_request_fingerprint
  OR p_raw_result->'attempts' IS DISTINCT FROM to_jsonb(p_attempts)
  OR p_raw_result->>'error_code' IS DISTINCT FROM p_error_code THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result metadata mismatch' USING ERRCODE='22023'; END IF;
 candidate:=p_raw_result->'candidate';
 IF p_is_success THEN
  IF p_error_code IS NOT NULL OR jsonb_typeof(candidate) IS DISTINCT FROM 'object'
   OR candidate->>'source_question_id' IS DISTINCT FROM p_source_question_id::text
   OR candidate->'seed' IS DISTINCT FROM to_jsonb(p_seed)
   OR candidate->>'blueprint_fingerprint' IS DISTINCT FROM src->>'blueprint_fingerprint'
   OR p_content IS NULL OR candidate->>'question_text' IS DISTINCT FROM p_content
   OR jsonb_typeof(p_options) IS DISTINCT FROM 'array' OR jsonb_array_length(p_options)<>4
   OR candidate->'options' IS DISTINCT FROM p_options OR p_correct_key NOT IN ('A','B','C','D') OR p_correct_key IS NULL
   OR candidate->>'correct_key' IS DISTINCT FROM p_correct_key OR candidate->>'solution_md' IS DISTINCT FROM p_solution_md
   OR candidate->'has_warning' IS DISTINCT FROM to_jsonb(coalesce(p_has_warning,false))
   OR jsonb_typeof(p_raw_result#>'{validation,checks}') IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid successful result or projection' USING ERRCODE='22023'; END IF;
  -- Same acceptance semantics as ValidationReport.failures; warnings are valid.
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_raw_result#>'{validation,checks}') c
   WHERE (c->>'passed')::boolean IS DISTINCT FROM true AND coalesce(c->>'status','') NOT IN ('unknown','unsupported','inconclusive','timeout')) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: hard-failed result' USING ERRCODE='22023'; END IF;
 ELSE
  IF p_error_code IS NULL THEN RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: failure needs error code' USING ERRCODE='22023'; END IF;
 END IF;
 SELECT * INTO prior FROM public.generation_target_results WHERE session_id=s.id AND version_index=p_version_index AND source_question_id=p_source_question_id;
 IF prior.is_success THEN
  IF NOT p_is_success OR prior.snapshot_id IS DISTINCT FROM job.id OR prior.raw_result IS DISTINCT FROM p_raw_result
   OR prior.seed IS DISTINCT FROM p_seed OR prior.question_no IS DISTINCT FROM p_question_no THEN
   RAISE EXCEPTION 'Successful target is immutable' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('success',true,'replayed',true,'session_id',s.id,'snapshot_id',job.id,
   'version_index',p_version_index,'source_question_id',p_source_question_id,'version_question_id',prior.version_question_id);
 END IF;
 IF p_is_success THEN
  INSERT INTO public.exam_versions(session_id,version_code) VALUES(s.id,(100+p_version_index)::text) ON CONFLICT(session_id,version_code) DO NOTHING;
  SELECT id INTO v_id FROM public.exam_versions WHERE session_id=s.id AND version_code=(100+p_version_index)::text;
  IF EXISTS(SELECT 1 FROM public.version_questions WHERE version_id=v_id AND source_question_id=p_source_question_id AND is_current) THEN
   RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: display-only target requires explicit reconciliation' USING ERRCODE='23505'; END IF;
  INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,solution_md,
   canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,has_warning,status,is_current)
  VALUES(v_id,p_source_question_id,p_question_no,p_content,p_options,p_correct_key,p_solution_md,
   p_question_no,p_options,p_correct_key,p_solution_md,coalesce(p_has_warning,false),'pending_review',true) RETURNING id INTO q_id;
 END IF;
 INSERT INTO public.generation_target_results(session_id,snapshot_id,job_token,version_index,source_question_id,question_no,is_success,error_code,
  attempts,seed,request_fingerprint,raw_result,version_question_id)
 VALUES(s.id,job.id,p_job_token,p_version_index,p_source_question_id,p_question_no,p_is_success,p_error_code,p_attempts,p_seed,p_request_fingerprint,p_raw_result,q_id)
 ON CONFLICT(session_id,version_index,source_question_id) DO UPDATE SET snapshot_id=EXCLUDED.snapshot_id,job_token=EXCLUDED.job_token,
 question_no=EXCLUDED.question_no,is_success=EXCLUDED.is_success,error_code=EXCLUDED.error_code,attempts=EXCLUDED.attempts,
 seed=EXCLUDED.seed,request_fingerprint=EXCLUDED.request_fingerprint,raw_result=EXCLUDED.raw_result,version_question_id=EXCLUDED.version_question_id,created_at=now();
 UPDATE public.exam_sessions SET updated_at=clock_timestamp() WHERE id=s.id;
 RETURN jsonb_build_object('success',true,'replayed',false,'session_id',s.id,'snapshot_id',job.id,
  'version_index',p_version_index,'source_question_id',p_source_question_id,'version_question_id',q_id);
END $$;
REVOKE ALL ON FUNCTION public.persist_generation_result(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.persist_generation_result(uuid,uuid,int,uuid,int,boolean,text,int,int,text,jsonb,text,jsonb,text,text,boolean) TO service_role;

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
 SELECT coalesce(jsonb_agg(jsonb_build_object('snapshot_id',r.snapshot_id,'version_index',r.version_index,'source_question_id',r.source_question_id,
  'question_no',r.question_no,'is_success',true,'seed',r.seed,'request_fingerprint',r.request_fingerprint,'raw_result',r.raw_result)
  ORDER BY r.version_index,r.question_no),'[]') INTO completed
 FROM public.generation_target_results r JOIN public.version_questions q ON q.id=r.version_question_id AND q.is_current
 WHERE r.session_id=s.id AND r.snapshot_id=job.id AND r.is_success;
 SELECT coalesce(jsonb_agg(jsonb_build_object('snapshot_id',r.snapshot_id,'version_index',r.version_index,'source_question_id',r.source_question_id,
  'question_no',r.question_no,'is_success',false,'seed',r.seed,'request_fingerprint',r.request_fingerprint,'raw_result',r.raw_result)
  ORDER BY r.version_index,r.question_no),'[]') INTO failures FROM public.generation_target_results r
 WHERE r.session_id=s.id AND r.snapshot_id=job.id AND NOT r.is_success;
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
 IF NOT EXISTS(SELECT 1 FROM public.source_artifact_confirmations WHERE session_id=p_session_id) THEN
  RETURN public._generation_legacy_finish(p_session_id,p_outcome,p_job_token); END IF;
 IF s.id IS NULL THEN RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002'; END IF;
 IF s.status<>'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
  RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE='55006'; END IF;
 IF p_outcome IS NULL OR p_outcome NOT IN ('generated','partial_generated','failed') THEN
  RAISE EXCEPTION 'Invalid outcome' USING ERRCODE='22023'; END IF;
 SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id=s.id;
 IF job.id IS NULL THEN RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing snapshot' USING ERRCODE='55006'; END IF;
 IF p_outcome='generated' AND EXISTS(
  SELECT 1 FROM generate_series(1,job.n_versions) ver(idx) CROSS JOIN jsonb_array_elements(job.snapshot_payload->'confirmed_sources') src
  WHERE NOT EXISTS(SELECT 1 FROM public.generation_target_results r JOIN public.version_questions q ON q.id=r.version_question_id
   JOIN public.exam_versions v ON v.id=q.version_id
   WHERE r.session_id=s.id AND r.snapshot_id=job.id AND r.version_index=ver.idx AND r.source_question_id::text=src->>'source_question_id'
   AND r.is_success AND q.is_current AND v.session_id=s.id AND v.version_code=(100+ver.idx)::text
   AND q.source_question_id=r.source_question_id AND q.canonical_question_no=r.question_no)) THEN
  RAISE EXCEPTION 'Cannot finish as generated: successful targets incomplete' USING ERRCODE='22023'; END IF;
 UPDATE public.exam_sessions SET status=p_outcome::public.session_status,active_job_id=NULL WHERE id=s.id;
 RETURN jsonb_build_object('session_id',s.id,'status',p_outcome,'snapshot_id',job.id);
END $$;
REVOKE ALL ON FUNCTION public.finish_generation_job(uuid,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_generation_job(uuid,text,uuid) TO service_role;
COMMIT;
