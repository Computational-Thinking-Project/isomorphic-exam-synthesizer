-- Issue #70: per-question policy for NEW frozen jobs; historical snapshots stay unchanged.
-- Forward-only after 025. No table rewrite, new role grant, or historical data migration.
BEGIN;

CREATE OR REPLACE FUNCTION public._generation_question_policy(p_blueprint jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE transforms jsonb; t jsonb; dims jsonb;
BEGIN
  transforms := p_blueprint#>'{requirement,variation_policy,allowed_transformations}';
  IF jsonb_typeof(transforms) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed policy' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(transforms)=0 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: empty policy' USING ERRCODE='22023';
  END IF;
  FOR t IN SELECT value FROM jsonb_array_elements(transforms) LOOP
    IF jsonb_typeof(t) IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed transformation' USING ERRCODE='22023';
    END IF;
    IF coalesce(t->>'dimension','') NOT IN ('values','context','wording','names','representation','option_order')
      OR jsonb_typeof(t->'id') IS DISTINCT FROM 'string' OR length(btrim(t->>'id'))=0
      OR jsonb_typeof(t->'description') IS DISTINCT FROM 'string' OR length(btrim(t->>'description'))=0
      OR jsonb_typeof(t->'target_refs') IS DISTINCT FROM 'array'
      OR jsonb_typeof(t->'preconditions') IS DISTINCT FROM 'array'
      OR jsonb_typeof(t->'limits') IS DISTINCT FROM 'array'
      OR t - ARRAY['id','dimension','description','target_refs','preconditions','limits'] <> '{}'::jsonb THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed transformation' USING ERRCODE='22023';
    END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements((t->'target_refs')||(t->'preconditions')||(t->'limits')) x
      WHERE jsonb_typeof(x) IS DISTINCT FROM 'string' OR length(btrim(x#>>'{}'))=0) THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: malformed transformation references' USING ERRCODE='22023';
    END IF;
  END LOOP;
  SELECT coalesce(jsonb_agg(d ORDER BY ord),'[]'::jsonb) INTO dims
  FROM (VALUES ('values',1),('context',2)) allowed(d,ord)
  WHERE EXISTS(SELECT 1 FROM jsonb_array_elements(transforms) transform WHERE transform->>'dimension'=d);
  RETURN jsonb_build_object('canonical_dimensions',dims,'result_kind',
    CASE WHEN dims='[]'::jsonb THEN 'ORIGINAL_CLONE' ELSE 'AI_RESULT' END);
END $$;
REVOKE ALL ON FUNCTION public._generation_question_policy(jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public._generation_is_clone(p_job public.generation_job_snapshots,p_source_id uuid)
RETURNS boolean LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE src jsonb; expected jsonb;
BEGIN
  IF p_job.mapping_version='1.0' THEN
    RETURN p_job.public_modes='[]'::jsonb AND p_job.canonical_dimensions='[]'::jsonb;
  END IF;
  IF p_job.mapping_version IS DISTINCT FROM '1.1' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unknown mapping version' USING ERRCODE='55006';
  END IF;
  SELECT value INTO src FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources')
    WHERE value->>'source_question_id'=p_source_id::text;
  expected := public._generation_question_policy(src->'canonical_blueprint');
  IF p_job.snapshot_payload#>ARRAY['question_policies',p_source_id::text] IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen question policy changed' USING ERRCODE='55006';
  END IF;
  RETURN expected->>'result_kind'='ORIGINAL_CLONE';
END $$;
REVOKE ALL ON FUNCTION public._generation_is_clone(public.generation_job_snapshots,uuid) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION public.save_generation_config(
  p_session_id uuid,
  p_n_versions int,
  p_active_variation_modes jsonb DEFAULT '[]',
  p_ordering_preferences jsonb DEFAULT '{"shuffle_questions":false,"shuffle_options":false}',
  p_expected_snapshot jsonb DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  s public.exam_sessions; snap jsonb; src jsonb; policy jsonb;
  has_values boolean := false; has_context boolean := false;
  modes jsonb := '[]'; dims jsonb := '[]'; cfg uuid;
BEGIN
  -- Same parent-first lock order as claim and trusted final shuffle.
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE='P0002';
  END IF;
  IF public.current_role()<>'service_role'
     AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
    RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
  END IF;
  IF s.status NOT IN ('blueprinted','configured') OR s.approved_at IS NOT NULL
     OR EXISTS(SELECT 1 FROM public.generation_job_snapshots WHERE session_id=s.id)
     OR EXISTS(SELECT 1 FROM public.exam_versions WHERE session_id=s.id AND is_finalized) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: configuration locked' USING ERRCODE='55006';
  END IF;
  IF p_n_versions IS NULL OR p_n_versions NOT BETWEEN 1 AND 4
     OR p_active_variation_modes IS DISTINCT FROM '[]'::jsonb
     OR jsonb_typeof(p_ordering_preferences) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid configuration' USING ERRCODE='22023';
  END IF;
  IF jsonb_typeof(p_ordering_preferences->'shuffle_questions') IS DISTINCT FROM 'boolean'
     OR jsonb_typeof(p_ordering_preferences->'shuffle_options') IS DISTINCT FROM 'boolean'
     OR p_ordering_preferences - ARRAY['shuffle_questions','shuffle_options'] <> '{}'::jsonb THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid ordering preferences' USING ERRCODE='22023';
  END IF;

  snap := public.get_generation_source_snapshot(s.id);
  IF (snap->>'ready')::boolean IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: %', coalesce(snap->>'reason', 'not ready') USING ERRCODE='22023';
  END IF;
  IF jsonb_typeof(snap->'manifest') IS DISTINCT FROM 'object'
     OR jsonb_typeof(p_expected_snapshot) IS DISTINCT FROM 'object'
     OR p_expected_snapshot IS DISTINCT FROM snap->'manifest' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: snapshot changed or missing' USING ERRCODE='55006';
  END IF;
  IF jsonb_typeof(snap->'confirmed_sources') IS DISTINCT FROM 'array'
     OR snap->>'confirmation_id' IS NULL OR snap->>'confirmed_source_hash' IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: invalid source evidence' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(snap->'confirmed_sources')=0 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: empty source evidence' USING ERRCODE='22023';
  END IF;
  FOR src IN SELECT value FROM jsonb_array_elements(snap->'confirmed_sources') LOOP
    policy := public._generation_question_policy(src->'canonical_blueprint');
    has_values := has_values OR (policy->'canonical_dimensions' ? 'values');
    has_context := has_context OR (policy->'canonical_dimensions' ? 'context');
  END LOOP;
  -- Retain both published aliases for compatibility; only one semantic dimension.
  IF has_values THEN
    modes := modes || '["NUMERICAL","parameter_variation"]'::jsonb;
    dims := dims || '["values"]'::jsonb;
  END IF;
  IF has_context THEN
    modes := modes || '["context_swap"]'::jsonb;
    dims := dims || '["context"]'::jsonb;
  END IF;
  INSERT INTO public.generation_configs(session_id,n_versions,active_variation_modes,
    ordering_preferences,source_manifest,canonical_dimensions,mapping_version)
  VALUES(s.id,p_n_versions,modes,p_ordering_preferences,snap->'manifest',dims,'1.1')
  ON CONFLICT(session_id) DO UPDATE SET n_versions=EXCLUDED.n_versions,
    active_variation_modes=EXCLUDED.active_variation_modes,
    ordering_preferences=EXCLUDED.ordering_preferences,source_manifest=EXCLUDED.source_manifest,
    canonical_dimensions=EXCLUDED.canonical_dimensions,mapping_version=EXCLUDED.mapping_version
  RETURNING id INTO cfg;
  UPDATE public.exam_sessions SET status='configured' WHERE id=s.id;
  RETURN jsonb_build_object('success',true,'session_id',s.id,'config_id',cfg,'status','configured',
    'config',jsonb_build_object('n_versions',p_n_versions,'active_variation_modes',modes,
      'ordering_preferences',p_ordering_preferences,'source_manifest',snap->'manifest',
      'canonical_dimensions',dims,'mapping_version','1.1'));
END $$;

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
  completed jsonb; policies jsonb; dims jsonb; modes jsonb;

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

  -- New claims upgrade an unfrozen legacy config under the same session lock.
  -- Retry NEVER reads current Blueprints or recalculates its frozen decisions.
  IF NOT p_is_retry THEN
    SELECT jsonb_object_agg(src->>'source_question_id',public._generation_question_policy(src->'canonical_blueprint'))
      INTO policies FROM jsonb_array_elements(snap->'confirmed_sources') src;
    SELECT coalesce(jsonb_agg(d ORDER BY d DESC),'[]'::jsonb) INTO dims FROM (
      SELECT DISTINCT jsonb_array_elements_text(value->'canonical_dimensions') d FROM jsonb_each(policies)
    ) dimensions;
    modes := '[]'::jsonb;
    IF dims ? 'values' THEN modes := modes || '["NUMERICAL","parameter_variation"]'::jsonb; END IF;
    IF dims ? 'context' THEN modes := modes || '["context_swap"]'::jsonb; END IF;
    UPDATE public.generation_configs SET active_variation_modes=modes,canonical_dimensions=dims,mapping_version='1.1'
      WHERE session_id=s.id RETURNING * INTO cfg;
    snap := snap || jsonb_build_object('question_policies',policies);
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

CREATE OR REPLACE FUNCTION public._generation_assert_result_kind(p_session_id uuid, p_snapshot_id uuid)
RETURNS void LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE job public.generation_job_snapshots; expected jsonb;
BEGIN
  SELECT * INTO job FROM public.generation_job_snapshots
    WHERE id=p_snapshot_id AND session_id=p_session_id;
  IF job.mapping_version='1.1' THEN
    SELECT jsonb_object_agg(src->>'source_question_id',public._generation_question_policy(src->'canonical_blueprint'))
      INTO expected FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') src;
    IF job.snapshot_payload->'question_policies' IS DISTINCT FROM expected THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen question policy changed' USING ERRCODE='55006';
    END IF;
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.generation_target_results r
    JOIN public.generation_job_snapshots j ON j.id = r.snapshot_id AND j.session_id = r.session_id
    WHERE r.session_id = p_session_id AND r.snapshot_id = p_snapshot_id
      AND (
        (public._generation_is_clone(j,r.source_question_id) AND r.result_kind IS DISTINCT FROM 'ORIGINAL_CLONE')
        OR
        (NOT public._generation_is_clone(j,r.source_question_id)
         AND r.result_kind NOT IN ('AI_RESULT', 'CONFIRMED_SOURCE_FALLBACK'))
      )
  ) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result kind differs from frozen job; explicit reconciliation required' USING ERRCODE = '55006';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public._generation_committed(p_session_id uuid, p_snapshot_id uuid)
RETURNS SETOF public.generation_target_results
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
  SELECT r.* FROM public.generation_target_results r
  JOIN public.generation_job_snapshots j ON j.id = r.snapshot_id AND j.session_id = r.session_id
  JOIN public.version_questions q ON q.id = r.version_question_id AND q.is_current
  JOIN public.exam_versions v ON v.id = q.version_id AND v.session_id = r.session_id AND v.version_code = (100 + r.version_index)::text
  CROSS JOIN LATERAL jsonb_array_elements(j.snapshot_payload->'confirmed_sources') src
  CROSS JOIN LATERAL (SELECT CASE r.result_kind
    WHEN 'ORIGINAL_CLONE' THEN
      jsonb_build_object('question_text', r.raw_result->'content', 'options', r.raw_result->'options',
        'correct_key', r.raw_result->'correct_key', 'solution_md', r.raw_result->'solution_md', 'has_warning', false)
    WHEN 'CONFIRMED_SOURCE_FALLBACK' THEN
      jsonb_build_object('question_text', r.raw_result->'content', 'options', r.raw_result->'options',
        'correct_key', r.raw_result->'correct_key', 'solution_md', r.raw_result->'solution_md', 'has_warning', true)
    ELSE r.raw_result->'candidate' END c) payload
  WHERE r.session_id = p_session_id AND r.snapshot_id = p_snapshot_id AND r.is_success
  AND r.version_index BETWEEN 1 AND j.n_versions AND src->>'source_question_id' = r.source_question_id::text
  AND r.question_no = (src->>'question_no')::int AND q.source_question_id = r.source_question_id
  AND q.question_no = r.question_no AND q.canonical_question_no = r.question_no
  AND q.content IS NOT DISTINCT FROM payload.c->>'question_text'
  AND q.options IS NOT DISTINCT FROM payload.c->'options' AND q.canonical_options IS NOT DISTINCT FROM q.options
  AND q.correct_key IS NOT DISTINCT FROM payload.c->>'correct_key' AND q.canonical_correct_key IS NOT DISTINCT FROM q.correct_key
  AND q.solution_md IS NOT DISTINCT FROM payload.c->>'solution_md' AND q.canonical_solution_md IS NOT DISTINCT FROM q.solution_md
  AND q.has_warning IS NOT DISTINCT FROM (payload.c->>'has_warning')::boolean
  AND (
    -- Original Clone branch
    (public._generation_is_clone(j,r.source_question_id) AND r.result_kind = 'ORIGINAL_CLONE'
     AND r.error_code IS NULL AND r.attempts = 0 AND r.clone_fingerprint IS NOT NULL AND r.request_fingerprint IS NULL)
    OR
    -- AI job branch
    (NOT public._generation_is_clone(j,r.source_question_id) AND (
      (r.result_kind = 'AI_RESULT' AND r.error_code IS NULL AND r.clone_fingerprint IS NULL AND r.request_fingerprint IS NOT NULL)
      OR
      (r.result_kind = 'CONFIRMED_SOURCE_FALLBACK'
       AND r.error_code = 'GENERATION_RETRIES_EXHAUSTED' AND r.attempts = 4
       AND r.clone_fingerprint IS NULL AND r.request_fingerprint IS NOT NULL
       AND q.status IN ('pending_review', 'approved')
       AND q.validation_report = jsonb_build_object(
         'fallback_source', true,
         'reason', 'GENERATION_RETRIES_EXHAUSTED',
         'attempts', 4,
         'validation_status', 'not_validated',
         'source_revision_id', (src->>'source_revision_id')::uuid,
         'source_fingerprint', src->>'source_fingerprint',
         'confirmed_source_hash', j.confirmed_source_hash
       )
       AND r.raw_result = public._generation_fallback_record(j, r.source_question_id, r.version_index, r.request_fingerprint, r.raw_result->>'last_error_code')
      )
    ))
  );
$$;

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
 IF NOT public._generation_is_clone(job,(src->>'source_question_id')::uuid) THEN
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone requires ORIGINAL_CLONE question policy' USING ERRCODE='22023'; END IF;
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

CREATE OR REPLACE FUNCTION public.persist_generation_result(
  p_session_id uuid,
  p_job_token uuid,
  p_version_index int,
  p_source_question_id uuid,
  p_question_no int,
  p_is_success boolean,
  p_error_code text,
  p_attempts int,
  p_seed int,
  p_request_fingerprint text,
  p_raw_result jsonb,
  p_content text,
  p_options jsonb,
  p_correct_key text,
  p_solution_md text,
  p_has_warning boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  s public.exam_sessions;
  job public.generation_job_snapshots;
  prior public.generation_target_results;
  kind text;
  expected jsonb;
  v_id uuid;
  q_id uuid;
  q_rec public.version_questions%ROWTYPE;
  val_report jsonb;
BEGIN
  -- 1. Require actual service_role; lock exam_sessions FOR UPDATE
  IF public.current_role() <> 'service_role' THEN
    RAISE EXCEPTION 'Worker only' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;

  -- 2. Check session existence, status='generating', non-null job token, and absence of approval BEFORE replay lookup
  IF s.status <> 'generating' OR p_job_token IS NULL OR s.active_job_id IS DISTINCT FROM p_job_token THEN
    RAISE EXCEPTION 'Fencing token mismatch' USING ERRCODE = '55006';
  END IF;
  IF s.approved_at IS NOT NULL OR s.status IN ('approved', 'exported') THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: session already approved' USING ERRCODE = '55006';
  END IF;

  -- 3. Load and validate the frozen job; reject Original Clone jobs
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing generation snapshot' USING ERRCODE = '55006';
  END IF;
  IF public._generation_is_clone(job,p_source_question_id) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: clone job requires ORIGINAL_CLONE result kind' USING ERRCODE = '22023';
  END IF;

  -- 4. Validate existing result kinds and inspect the slot's prior result
  PERFORM public._generation_assert_result_kind(s.id, job.id);

  IF jsonb_typeof(p_raw_result) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: raw_result must be a json object' USING ERRCODE = '22023';
  END IF;

  SELECT * INTO prior FROM public.generation_target_results
  WHERE session_id = s.id AND version_index = p_version_index AND source_question_id = p_source_question_id;

  -- 5. Dispatch based on result_kind discriminator
  IF p_raw_result ? 'result_kind' THEN
    IF p_raw_result->'result_kind' = 'null'::jsonb THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: result_kind cannot be null' USING ERRCODE = '22023';
    END IF;
    kind := p_raw_result->>'result_kind';
    IF kind NOT IN ('CONFIRMED_SOURCE_FALLBACK', 'AI_RESULT') THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unsupported result_kind %', kind USING ERRCODE = '22023';
    END IF;
  ELSE
    kind := 'AI_RESULT';
  END IF;

  IF kind = 'AI_RESULT' THEN
    -- AI dispatch: reject attempts to replace an existing fallback first
    IF prior.id IS NOT NULL AND prior.result_kind = 'CONFIRMED_SOURCE_FALLBACK' THEN
      RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: cannot overwrite fallback with AI result' USING ERRCODE = '23505';
    END IF;

    RETURN public._generation_persist_010(
      p_session_id, p_job_token, p_version_index, p_source_question_id,
      p_question_no, p_is_success, p_error_code, p_attempts, p_seed,
      p_request_fingerprint, p_raw_result, p_content, p_options,
      p_correct_key, p_solution_md, p_has_warning
    );
  END IF;

  -- --------------------------------------------------------------------------
  -- CONFIRMED_SOURCE_FALLBACK branch
  -- --------------------------------------------------------------------------
  IF p_is_success IS NOT TRUE THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires is_success=true' USING ERRCODE = '22023';
  END IF;
  IF p_attempts IS DISTINCT FROM 4 THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires attempts=4' USING ERRCODE = '22023';
  END IF;
  IF p_error_code IS DISTINCT FROM 'GENERATION_RETRIES_EXHAUSTED' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires error_code=GENERATION_RETRIES_EXHAUSTED' USING ERRCODE = '22023';
  END IF;
  IF p_has_warning IS NOT TRUE THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback requires has_warning=true' USING ERRCODE = '22023';
  END IF;
  IF p_raw_result ? 'candidate' OR p_raw_result ? 'validation' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: fallback cannot contain AI candidate or validation' USING ERRCODE = '22023';
  END IF;

  -- Check caller projection matches raw result fields
  IF p_raw_result->>'source_question_id' IS DISTINCT FROM p_source_question_id::text
     OR p_raw_result->'version_index' IS DISTINCT FROM to_jsonb(p_version_index)
     OR p_raw_result->'question_no' IS DISTINCT FROM to_jsonb(p_question_no)
     OR p_raw_result->'seed' IS DISTINCT FROM to_jsonb(p_seed)
     OR p_raw_result->>'request_fingerprint' IS DISTINCT FROM p_request_fingerprint
     OR p_raw_result->>'content' IS DISTINCT FROM p_content
     OR p_raw_result->'options' IS DISTINCT FROM p_options
     OR p_raw_result->>'correct_key' IS DISTINCT FROM p_correct_key
     OR p_raw_result->>'solution_md' IS DISTINCT FROM p_solution_md THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: caller projection mismatch' USING ERRCODE = '22023';
  END IF;

  -- Verify and independently construct expected fallback record
  expected := public._generation_fallback_record(
    job, p_source_question_id, p_version_index, p_request_fingerprint, p_raw_result->>'last_error_code'
  );

  IF p_raw_result IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: raw_result does not match verified fallback record' USING ERRCODE = '22023';
  END IF;

  -- Check prior result state transitions
  IF prior.id IS NOT NULL THEN
    IF prior.is_success THEN
      IF prior.result_kind = 'CONFIRMED_SOURCE_FALLBACK' THEN
        -- Active replay verification
        IF prior.snapshot_id IS DISTINCT FROM job.id
           OR prior.raw_result IS DISTINCT FROM expected
           OR prior.seed IS DISTINCT FROM p_seed
           OR prior.question_no IS DISTINCT FROM p_question_no THEN
          RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: fallback record conflict' USING ERRCODE = '23505';
        END IF;

        -- Verify intact pending/current projection and report
        SELECT * INTO q_rec FROM public.version_questions WHERE id = prior.version_question_id;
        IF q_rec.id IS NULL OR NOT q_rec.is_current OR q_rec.status <> 'pending_review'
           OR q_rec.content IS DISTINCT FROM expected->>'content'
           OR q_rec.canonical_options IS DISTINCT FROM expected->'options'
           OR q_rec.canonical_correct_key IS DISTINCT FROM expected->>'correct_key'
           OR q_rec.canonical_solution_md IS DISTINCT FROM expected->>'solution_md'
           OR NOT q_rec.has_warning THEN
          RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: committed fallback projection changed' USING ERRCODE = '23505';
        END IF;

        -- Return replay receipt without modifying state
        RETURN jsonb_build_object(
          'success', true,
          'replayed', true,
          'session_id', s.id,
          'snapshot_id', job.id,
          'version_index', p_version_index,
          'source_question_id', p_source_question_id,
          'version_question_id', prior.version_question_id,
          'result_kind', 'CONFIRMED_SOURCE_FALLBACK',
          'candidate_status', 'pending_review',
          'attempts', 4,
          'error_code', 'GENERATION_RETRIES_EXHAUSTED',
          'source_revision_id', (expected->>'source_revision_id')::uuid,
          'confirmed_source_hash', expected->>'confirmed_source_hash'
        );
      ELSE
        RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: cannot overwrite committed result' USING ERRCODE = '23505';
      END IF;
    ELSE
      -- Prior failure: must be same snapshot and have no candidate ID
      IF prior.snapshot_id IS DISTINCT FROM job.id OR prior.version_question_id IS NOT NULL THEN
        RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: invalid prior failure state' USING ERRCODE = '23505';
      END IF;
    END IF;
  END IF;

  -- Ensure exam_versions row exists
  INSERT INTO public.exam_versions(session_id, version_code)
  VALUES(s.id, (100 + p_version_index)::text)
  ON CONFLICT(session_id, version_code) DO NOTHING;

  SELECT id INTO v_id FROM public.exam_versions
  WHERE session_id = s.id AND version_code = (100 + p_version_index)::text;

  -- Check no current candidate exists on this slot
  IF EXISTS (
    SELECT 1 FROM public.version_questions
    WHERE version_id = v_id AND source_question_id = p_source_question_id AND is_current
  ) THEN
    RAISE EXCEPTION 'ERR_GENERATION_RESULT_CONFLICT: display-only target requires explicit reconciliation' USING ERRCODE = '23505';
  END IF;

  -- Construct canonical fallback validation report
  val_report := jsonb_build_object(
    'fallback_source', true,
    'reason', 'GENERATION_RETRIES_EXHAUSTED',
    'attempts', 4,
    'validation_status', 'not_validated',
    'source_revision_id', (expected->>'source_revision_id')::uuid,
    'source_fingerprint', expected->>'source_fingerprint',
    'confirmed_source_hash', expected->>'confirmed_source_hash'
  );

  -- Atomic candidate insertion
  INSERT INTO public.version_questions(
    version_id, source_question_id, question_no, content, options, correct_key, solution_md,
    canonical_question_no, canonical_options, canonical_correct_key, canonical_solution_md,
    has_warning, status, is_current, validation_report
  ) VALUES (
    v_id, p_source_question_id, (expected->>'question_no')::int,
    expected->>'content', expected->'options', expected->>'correct_key', expected->>'solution_md',
    (expected->>'question_no')::int, expected->'options', expected->>'correct_key', expected->>'solution_md',
    true, 'pending_review', true, val_report
  ) RETURNING id INTO q_id;

  -- Atomic ledger insertion / replacement of prior failure
  INSERT INTO public.generation_target_results(
    session_id, snapshot_id, job_token, version_index, source_question_id, question_no,
    is_success, error_code, attempts, seed, request_fingerprint, raw_result,
    version_question_id, result_kind, clone_fingerprint
  ) VALUES (
    s.id, job.id, p_job_token, p_version_index, p_source_question_id, (expected->>'question_no')::int,
    true, 'GENERATION_RETRIES_EXHAUSTED', 4, (expected->>'seed')::int, p_request_fingerprint, expected,
    q_id, 'CONFIRMED_SOURCE_FALLBACK', NULL
  ) ON CONFLICT (session_id, version_index, source_question_id) DO UPDATE SET
    snapshot_id = EXCLUDED.snapshot_id,
    job_token = EXCLUDED.job_token,
    question_no = EXCLUDED.question_no,
    is_success = true,
    error_code = 'GENERATION_RETRIES_EXHAUSTED',
    attempts = 4,
    seed = EXCLUDED.seed,
    request_fingerprint = EXCLUDED.request_fingerprint,
    raw_result = EXCLUDED.raw_result,
    version_question_id = EXCLUDED.version_question_id,
    result_kind = 'CONFIRMED_SOURCE_FALLBACK',
    clone_fingerprint = NULL,
    created_at = now();

  UPDATE public.exam_sessions SET updated_at = clock_timestamp() WHERE id = s.id;

  RETURN jsonb_build_object(
    'success', true,
    'replayed', false,
    'session_id', s.id,
    'snapshot_id', job.id,
    'version_index', p_version_index,
    'source_question_id', p_source_question_id,
    'version_question_id', q_id,
    'result_kind', 'CONFIRMED_SOURCE_FALLBACK',
    'candidate_status', 'pending_review',
    'attempts', 4,
    'error_code', 'GENERATION_RETRIES_EXHAUSTED',
    'source_revision_id', (expected->>'source_revision_id')::uuid,
    'confirmed_source_hash', expected->>'confirmed_source_hash'
  );
END;
$$;
COMMIT;
