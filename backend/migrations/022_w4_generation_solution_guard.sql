BEGIN;

-- Q01. The public 016 wrapper and its grants stay in place. Check the exact
-- canonical snapshot selected by this locked claim before inserting or updating.
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
  committed_counts jsonb := '{}'::jsonb;
  completed jsonb;
  question_numbers jsonb;
  spaces constant text := U&'\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000';
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
    SELECT coalesce(jsonb_object_agg(source_question_id, slot_count), '{}'::jsonb)
      INTO committed_counts
      FROM (
        SELECT r.source_question_id, count(DISTINCT r.version_index) AS slot_count
        FROM public._generation_committed(s.id, job.id) r
        GROUP BY r.source_question_id
      ) AS counts;
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

  SELECT jsonb_agg(DISTINCT question_no ORDER BY question_no) INTO question_numbers
  FROM (
    SELECT (source->>'question_no')::int AS question_no
    FROM jsonb_array_elements(snap->'confirmed_sources') AS sources(source)
    WHERE (NOT p_is_retry OR coalesce((committed_counts->>(source->>'source_question_id'))::int, 0) < job.n_versions)
      AND (jsonb_typeof(source#>'{confirmed_input,solution}') IS DISTINCT FROM 'string'
           OR coalesce(source#>>'{confirmed_input,solution}', '') !~ ('[^' || spaces || ']'))
  ) AS blocked;
  IF question_numbers IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'ERR_SOURCE_SOLUTION_REQUIRED',
      DETAIL = jsonb_build_object('question_numbers', question_numbers)::text;
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

COMMIT;
