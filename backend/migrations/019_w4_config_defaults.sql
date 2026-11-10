-- W4-MVP-01: OFF/OFF for omitted ordering preferences; existing rows unchanged.
-- Requires merged migrations 002-016. 017 (stale jobs) and 018 (review read)
-- are separate pending work; this migration does not define or depend on them.
-- Keep the five-argument RPC, ownership, root lock and canonical/legacy policy.
BEGIN;
ALTER TABLE public.generation_configs ALTER COLUMN ordering_preferences
 SET DEFAULT '{"shuffle_questions":false,"shuffle_options":false}'::jsonb;

CREATE OR REPLACE FUNCTION public.save_generation_config(
 p_session_id uuid,p_n_versions int,p_active_variation_modes jsonb DEFAULT '[]',
 p_ordering_preferences jsonb DEFAULT '{"shuffle_questions":false,"shuffle_options":false}',p_expected_snapshot jsonb DEFAULT NULL
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

COMMIT;
