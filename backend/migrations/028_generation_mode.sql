-- EXT-02 (PR #112): explicit generation mode, frozen per job.
-- The number 028 is tentative: Q05 on PR #111 may renumber this file. It must stay
-- before the EXT-01 Review guard, which reads public._generation_job_mode(job).
-- Forward-only after 027. Historical snapshots are NOT rewritten: mapping_version
-- 1.0/1.1 jobs resolve to ai_generation. New claims freeze mapping_version 1.2.
BEGIN;

ALTER TABLE public.generation_configs
  ADD COLUMN IF NOT EXISTS generation_mode text NOT NULL DEFAULT 'ai_generation'
  CONSTRAINT generation_configs_generation_mode_check
  CHECK (generation_mode IN ('ai_generation','shuffle_only'));
ALTER TABLE public.generation_job_snapshots
  ADD COLUMN IF NOT EXISTS generation_mode text
  CONSTRAINT generation_job_snapshots_generation_mode_check
  CHECK (generation_mode IS NULL OR generation_mode IN ('ai_generation','shuffle_only'));

-- The only reader of a job's mode. Never read the live config and never COALESCE.
CREATE OR REPLACE FUNCTION public._generation_job_mode(p_job public.generation_job_snapshots)
RETURNS text LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF p_job.mapping_version IN ('1.0','1.1') THEN
    RETURN 'ai_generation';
  END IF;
  IF p_job.mapping_version IS DISTINCT FROM '1.2'
     OR p_job.generation_mode IS NULL
     OR p_job.generation_mode NOT IN ('ai_generation','shuffle_only')
     OR p_job.snapshot_payload->>'generation_mode' IS DISTINCT FROM p_job.generation_mode THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unknown or inconsistent generation mode' USING ERRCODE='55006';
  END IF;
  RETURN p_job.generation_mode;
END $$;
REVOKE ALL ON FUNCTION public._generation_job_mode(public.generation_job_snapshots) FROM PUBLIC,anon,authenticated,service_role;

-- Per-question policy a job must have frozen. shuffle_only ignores AI-capable Blueprints.
CREATE OR REPLACE FUNCTION public._generation_mode_policy(p_mode text, p_blueprint jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF p_mode='shuffle_only' THEN
    RETURN jsonb_build_object('canonical_dimensions','[]'::jsonb,'result_kind','ORIGINAL_CLONE');
  END IF;
  IF p_mode IS DISTINCT FROM 'ai_generation' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unknown generation mode' USING ERRCODE='55006';
  END IF;
  RETURN public._generation_question_policy(p_blueprint);
END $$;
REVOKE ALL ON FUNCTION public._generation_mode_policy(text,jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public._generation_is_clone(p_job public.generation_job_snapshots,p_source_id uuid)
RETURNS boolean LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE src jsonb; expected jsonb;
BEGIN
  IF p_job.mapping_version='1.0' THEN
    RETURN p_job.public_modes='[]'::jsonb AND p_job.canonical_dimensions='[]'::jsonb;
  END IF;
  IF p_job.mapping_version IS DISTINCT FROM '1.1' AND p_job.mapping_version IS DISTINCT FROM '1.2' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unknown mapping version' USING ERRCODE='55006';
  END IF;
  SELECT value INTO src FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources')
    WHERE value->>'source_question_id'=p_source_id::text;
  expected := public._generation_mode_policy(public._generation_job_mode(p_job),src->'canonical_blueprint');
  IF p_job.snapshot_payload#>ARRAY['question_policies',p_source_id::text] IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen question policy changed' USING ERRCODE='55006';
  END IF;
  RETURN expected->>'result_kind'='ORIGINAL_CLONE';
END $$;
REVOKE ALL ON FUNCTION public._generation_is_clone(public.generation_job_snapshots,uuid) FROM PUBLIC,anon,authenticated,service_role;

-- One added argument: drop the 5-argument signature so PostgREST sees a single function.
-- Callers that omit p_generation_mode keep the previous behaviour (ai_generation).
DROP FUNCTION IF EXISTS public.save_generation_config(uuid,int,jsonb,jsonb,jsonb);
CREATE OR REPLACE FUNCTION public.save_generation_config(
  p_session_id uuid,
  p_n_versions int,
  p_active_variation_modes jsonb DEFAULT '[]',
  p_ordering_preferences jsonb DEFAULT '{"shuffle_questions":false,"shuffle_options":false}',
  p_expected_snapshot jsonb DEFAULT NULL,
  p_generation_mode text DEFAULT 'ai_generation'
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
     OR jsonb_typeof(p_ordering_preferences) IS DISTINCT FROM 'object'
     OR p_generation_mode IS NULL OR p_generation_mode NOT IN ('ai_generation','shuffle_only') THEN
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
  IF jsonb_array_length(snap->'confirmed_sources') NOT BETWEEN 1 AND 20 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source must have 1-20 questions' USING ERRCODE='22023';
  END IF;
  FOR src IN SELECT value FROM jsonb_array_elements(snap->'confirmed_sources') LOOP
    -- Malformed policies are rejected in both modes; shuffle_only then ignores AI dimensions.
    PERFORM public._generation_question_policy(src->'canonical_blueprint');
    policy := public._generation_mode_policy(p_generation_mode,src->'canonical_blueprint');
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
    ordering_preferences,source_manifest,canonical_dimensions,mapping_version,generation_mode)
  VALUES(s.id,p_n_versions,modes,p_ordering_preferences,snap->'manifest',dims,'1.2',p_generation_mode)
  ON CONFLICT(session_id) DO UPDATE SET n_versions=EXCLUDED.n_versions,
    active_variation_modes=EXCLUDED.active_variation_modes,
    ordering_preferences=EXCLUDED.ordering_preferences,source_manifest=EXCLUDED.source_manifest,
    canonical_dimensions=EXCLUDED.canonical_dimensions,mapping_version=EXCLUDED.mapping_version,
    generation_mode=EXCLUDED.generation_mode
  RETURNING id INTO cfg;
  UPDATE public.exam_sessions SET status='configured' WHERE id=s.id;
  RETURN jsonb_build_object('success',true,'session_id',s.id,'config_id',cfg,'status','configured',
    'config',jsonb_build_object('n_versions',p_n_versions,'active_variation_modes',modes,
      'ordering_preferences',p_ordering_preferences,'source_manifest',snap->'manifest',
      'canonical_dimensions',dims,'mapping_version','1.2','generation_mode',p_generation_mode));
END $$;
REVOKE ALL ON FUNCTION public.save_generation_config(uuid,int,jsonb,jsonb,jsonb,text) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.save_generation_config(uuid,int,jsonb,jsonb,jsonb,text) TO authenticated,service_role;

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
  SELECT * INTO cfg FROM public.generation_configs WHERE session_id = s.id;
  IF NOT EXISTS (SELECT 1 FROM public.source_artifact_confirmations WHERE session_id = s.id) THEN
    -- Pre-confirmation sessions have no frozen per-question policy; they cannot be shuffle_only.
    IF cfg.generation_mode = 'shuffle_only' THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: shuffle_only requires confirmed sources' USING ERRCODE = '55006';
    END IF;
    -- The legacy path never counted sources; 0 or 21+ must not start a job.
    IF (SELECT count(*) FROM public.source_questions WHERE session_id = s.id) NOT BETWEEN 1 AND 20 THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source must have 1-20 questions' USING ERRCODE = '22023';
    END IF;
    RETURN public._generation_legacy_claim(s.id, p_is_retry);
  END IF;
  IF p_is_retry IS NULL OR s.approved_at IS NOT NULL
     OR (NOT p_is_retry AND s.status <> 'configured')
     OR (p_is_retry AND s.status NOT IN ('failed', 'partial_generated')) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: cannot claim current state' USING ERRCODE = '55006';
  END IF;
  IF cfg.id IS NULL THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: missing config' USING ERRCODE = '55006';
  END IF;
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;

  IF p_is_retry THEN
    -- Retry/resume uses the frozen job only; a changed live mode is a conflict.
    IF job.id IS NULL OR job.n_versions IS DISTINCT FROM cfg.n_versions
       OR job.public_modes IS DISTINCT FROM cfg.active_variation_modes
       OR job.canonical_dimensions IS DISTINCT FROM cfg.canonical_dimensions
       OR job.mapping_version IS DISTINCT FROM cfg.mapping_version
       OR job.snapshot_payload->'manifest' IS DISTINCT FROM cfg.source_manifest
       OR job.snapshot_payload->'ordering_preferences' IS DISTINCT FROM cfg.ordering_preferences
       OR public._generation_job_mode(job) IS DISTINCT FROM cfg.generation_mode THEN
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
    -- 1-20 questions on the canonical revision, before any job, quota or AI call.
    IF jsonb_typeof(snap->'confirmed_sources') IS DISTINCT FROM 'array'
       OR jsonb_array_length(snap->'confirmed_sources') NOT BETWEEN 1 AND 20 THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source must have 1-20 questions' USING ERRCODE = '22023';
    END IF;
    IF cfg.source_manifest IS DISTINCT FROM snap->'manifest' THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: configured source changed' USING ERRCODE = '55006';
    END IF;
    IF cfg.generation_mode NOT IN ('ai_generation','shuffle_only') THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unknown generation mode' USING ERRCODE = '55006';
    END IF;
  END IF;

  -- New claims freeze mode, per-question policy and mapping 1.2 under the session lock.
  -- Retry NEVER reads current Blueprints or recalculates its frozen decisions.
  IF NOT p_is_retry THEN
    SELECT jsonb_object_agg(src->>'source_question_id',
        public._generation_mode_policy(cfg.generation_mode,src->'canonical_blueprint'))
      INTO policies FROM jsonb_array_elements(snap->'confirmed_sources') src;
    SELECT coalesce(jsonb_agg(d ORDER BY d DESC),'[]'::jsonb) INTO dims FROM (
      SELECT DISTINCT jsonb_array_elements_text(value->'canonical_dimensions') d FROM jsonb_each(policies)
    ) dimensions;
    modes := '[]'::jsonb;
    IF dims ? 'values' THEN modes := modes || '["NUMERICAL","parameter_variation"]'::jsonb; END IF;
    IF dims ? 'context' THEN modes := modes || '["context_swap"]'::jsonb; END IF;
    UPDATE public.generation_configs SET active_variation_modes=modes,canonical_dimensions=dims,mapping_version='1.2'
      WHERE session_id=s.id RETURNING * INTO cfg;
    snap := snap || jsonb_build_object('question_policies',policies,'generation_mode',cfg.generation_mode);
  END IF;

  token := gen_random_uuid();
  IF NOT p_is_retry THEN
    INSERT INTO public.generation_job_snapshots(
      session_id, job_token, confirmation_id, source_order, confirmed_source_hash, base_seed,
      n_versions, public_modes, canonical_dimensions, mapping_version, snapshot_payload, generation_mode
    ) VALUES (
      s.id, token, (snap->>'confirmation_id')::uuid, snap->'source_order', snap->>'confirmed_source_hash', 100,
      cfg.n_versions, cfg.active_variation_modes, cfg.canonical_dimensions, cfg.mapping_version,
      snap || jsonb_build_object('base_seed', 100, 'n_versions', cfg.n_versions, 'public_modes', cfg.active_variation_modes,
        'canonical_dimensions', cfg.canonical_dimensions, 'mapping_version', cfg.mapping_version,
        'ordering_preferences', cfg.ordering_preferences),
      cfg.generation_mode
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
      'ordering_preferences', job.snapshot_payload->'ordering_preferences',
      'generation_mode', public._generation_job_mode(job)),
    'committed_targets', completed, 'snapshot_id', job.id, 'context', job.snapshot_payload);
END $$;
REVOKE ALL ON FUNCTION public._generation_claim_010(uuid,boolean) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public._generation_assert_result_kind(p_session_id uuid, p_snapshot_id uuid)
RETURNS void LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE job public.generation_job_snapshots; expected jsonb; mode text;
BEGIN
  SELECT * INTO job FROM public.generation_job_snapshots
    WHERE id=p_snapshot_id AND session_id=p_session_id;
  IF job.mapping_version IN ('1.1','1.2') THEN
    mode := public._generation_job_mode(job);
    SELECT jsonb_object_agg(src->>'source_question_id',public._generation_mode_policy(mode,src->'canonical_blueprint'))
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

-- Quota is AI-only: a shuffle_only job can never reserve Gemini calls, even if a
-- worker bug asks for it. Body otherwise identical to migration 005.
CREATE OR REPLACE FUNCTION public.reserve_generation_quota(
  p_session_id UUID,
  p_calls_requested INT,
  p_job_token UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_session_user_id UUID;
  v_session_status public.session_status;
  v_active_job_id UUID;
  v_current_quota INT;
  v_new_quota INT;
  v_job public.generation_job_snapshots;
BEGIN
  IF public.current_role() != 'service_role' THEN
    RAISE EXCEPTION 'Access denied: reserve_generation_quota is restricted to service_role'
      USING ERRCODE = '42501';
  END IF;

  IF p_calls_requested IS NULL OR p_calls_requested < 1 OR p_calls_requested > 250 THEN
    RAISE EXCEPTION 'p_calls_requested must be between 1 and 250 (got %)', p_calls_requested
      USING ERRCODE = '22023';
  END IF;

  -- 1. Lock session row
  SELECT user_id, status, active_job_id, gemini_call_count
    INTO v_session_user_id, v_session_status, v_active_job_id, v_current_quota
  FROM public.exam_sessions
  WHERE id = p_session_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found: %', p_session_id USING ERRCODE = 'P0002';
  END IF;

  IF v_session_status != 'generating' THEN
    RAISE EXCEPTION 'Cannot reserve quota: session % is not generating (current: %)',
      p_session_id, v_session_status USING ERRCODE = '22023';
  END IF;

  -- 2. Fencing token check
  IF p_job_token IS DISTINCT FROM v_active_job_id THEN
    RAISE EXCEPTION 'Fencing token mismatch: job % is stale for session % (active: %)',
      p_job_token, p_session_id, v_active_job_id USING ERRCODE = '55006';
  END IF;

  -- 3. EXT-02: no AI quota for a frozen shuffle_only job
  SELECT * INTO v_job FROM public.generation_job_snapshots WHERE session_id = p_session_id;
  IF v_job.id IS NOT NULL AND public._generation_job_mode(v_job) = 'shuffle_only' THEN
    RAISE EXCEPTION 'ERR_MODE_SHUFFLE_ONLY: shuffle_only jobs never reserve AI quota'
      USING ERRCODE = '55006';
  END IF;

  -- 4. Enforce durable hard-cap of 250 calls
  v_new_quota := v_current_quota + p_calls_requested;
  IF v_new_quota > 250 THEN
    RAISE EXCEPTION 'Gemini quota hard-cap exceeded for session %: requested %, current %, cap 250',
      p_session_id, p_calls_requested, v_current_quota USING ERRCODE = '54000';
  END IF;

  UPDATE public.exam_sessions
  SET gemini_call_count = v_new_quota
  WHERE id = p_session_id;

  RETURN jsonb_build_object(
    'session_id', p_session_id,
    'job_id', p_job_token,
    'reserved_calls', p_calls_requested,
    'new_total_calls', v_new_quota,
    'remaining_quota', (250 - v_new_quota)
  );
END;
$$;
REVOKE EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.reserve_generation_quota(UUID, INT, UUID) TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
