-- W4-MVP-01 S04. Forward-only, after 016 and PR52's allocated 017.
-- Allocation and alias compatibility authorized by the task owner 2026-11-09.
-- No historical rows, job functions, source producer or table grants are changed.
BEGIN;

ALTER TABLE public.generation_configs ALTER COLUMN ordering_preferences
  SET DEFAULT '{"shuffle_questions":false,"shuffle_options":false}'::jsonb;

CREATE OR REPLACE FUNCTION public.save_generation_config(
  p_session_id uuid,
  p_n_versions int,
  p_active_variation_modes jsonb DEFAULT '[]',
  p_ordering_preferences jsonb DEFAULT '{"shuffle_questions":false,"shuffle_options":false}',
  p_expected_snapshot jsonb DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  s public.exam_sessions; snap jsonb; src jsonb; transforms jsonb; t jsonb;
  common_values boolean := true; common_context boolean := true;
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
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: %',snap->>'reason' USING ERRCODE='22023';
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
    transforms := src#>'{canonical_blueprint,requirement,variation_policy,allowed_transformations}';
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
    common_values := common_values AND EXISTS(
      SELECT 1 FROM jsonb_array_elements(transforms) x WHERE x->>'dimension'='values');
    common_context := common_context AND EXISTS(
      SELECT 1 FROM jsonb_array_elements(transforms) x WHERE x->>'dimension'='context');
  END LOOP;
  -- Retain both published aliases for compatibility; only one semantic dimension.
  IF common_values THEN
    modes := modes || '["NUMERICAL","parameter_variation"]'::jsonb;
    dims := dims || '["values"]'::jsonb;
  END IF;
  IF common_context THEN
    modes := modes || '["context_swap"]'::jsonb;
    dims := dims || '["context"]'::jsonb;
  END IF;
  INSERT INTO public.generation_configs(session_id,n_versions,active_variation_modes,
    ordering_preferences,source_manifest,canonical_dimensions,mapping_version)
  VALUES(s.id,p_n_versions,modes,p_ordering_preferences,snap->'manifest',dims,'1.0')
  ON CONFLICT(session_id) DO UPDATE SET n_versions=EXCLUDED.n_versions,
    active_variation_modes=EXCLUDED.active_variation_modes,
    ordering_preferences=EXCLUDED.ordering_preferences,source_manifest=EXCLUDED.source_manifest,
    canonical_dimensions=EXCLUDED.canonical_dimensions,mapping_version=EXCLUDED.mapping_version
  RETURNING id INTO cfg;
  UPDATE public.exam_sessions SET status='configured' WHERE id=s.id;
  RETURN jsonb_build_object('success',true,'session_id',s.id,'config_id',cfg,'status','configured',
    'config',jsonb_build_object('n_versions',p_n_versions,'active_variation_modes',modes,
      'ordering_preferences',p_ordering_preferences,'source_manifest',snap->'manifest',
      'canonical_dimensions',dims,'mapping_version','1.0'));
END $$;
REVOKE ALL ON FUNCTION public.save_generation_config(uuid,int,jsonb,jsonb,jsonb) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.save_generation_config(uuid,int,jsonb,jsonb,jsonb) TO authenticated,service_role;
COMMIT;
