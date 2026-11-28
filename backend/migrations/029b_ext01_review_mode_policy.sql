-- Q04 Review policy follows EXT-02's frozen generation job.
BEGIN;

CREATE OR REPLACE FUNCTION public._review_job_mode(p_job public.generation_job_snapshots)
RETURNS text LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
  IF to_regprocedure('public._generation_job_mode(public.generation_job_snapshots)') IS NOT NULL THEN
    RETURN public._generation_job_mode(p_job);
  END IF;
  -- A checkout without migration 028 can only interpret historical jobs.
  IF p_job.mapping_version IN ('1.0', '1.1') THEN
    RETURN 'ai_generation';
  END IF;
  RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: unsupported frozen job mapping' USING ERRCODE = '55006';
END $$;

CREATE OR REPLACE FUNCTION public._review_slot_policy(
  p_job public.generation_job_snapshots, p_source_id uuid
) RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE source_artifact jsonb; dims jsonb; clone boolean;
BEGIN
  IF jsonb_typeof(p_job.snapshot_payload->'confirmed_sources') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen sources missing' USING ERRCODE = '55006';
  END IF;
  BEGIN
    SELECT value INTO STRICT source_artifact
    FROM jsonb_array_elements(p_job.snapshot_payload->'confirmed_sources')
    WHERE value->>'source_question_id' = p_source_id::text;
  EXCEPTION WHEN no_data_found OR too_many_rows THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid frozen source binding' USING ERRCODE = '55006';
  END;

  BEGIN
    clone := public._generation_is_clone(p_job, p_source_id);
  EXCEPTION WHEN invalid_parameter_value THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: malformed frozen question policy' USING ERRCODE = '55006';
  END;
  IF p_job.mapping_version = '1.0' THEN
    dims := p_job.canonical_dimensions;
    IF dims NOT IN ('[]'::jsonb, '["values"]'::jsonb, '["context"]'::jsonb, '["values","context"]'::jsonb, '["context","values"]'::jsonb)
       OR (dims = '[]'::jsonb) IS DISTINCT FROM clone THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: invalid legacy variation dimensions' USING ERRCODE = '55006';
    END IF;
  ELSE
    dims := p_job.snapshot_payload#>ARRAY['question_policies',p_source_id::text,'canonical_dimensions'];
  END IF;
  RETURN jsonb_build_object(
    'result_kind', CASE WHEN clone THEN 'ORIGINAL_CLONE' ELSE 'AI_RESULT' END,
    'canonical_dimensions', dims
  );
END $$;

REVOKE ALL ON FUNCTION
  public._review_job_mode(public.generation_job_snapshots),
  public._review_slot_policy(public.generation_job_snapshots, uuid)
  FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.review_reserve_regeneration(
  p_session_id UUID,
  p_question_id UUID,
  p_operation_id UUID,
  p_reasons JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  s public.exam_sessions;
  q public.version_questions;
  o public.review_operations;
  snapshot JSONB;
  job public.generation_job_snapshots;
  policy JSONB;
  source_artifact JSONB;
  result JSONB;
  expiry TIMESTAMPTZ;
  canonical_reasons JSONB;
  stored_reasons JSONB;
BEGIN
  s := public._review_lock_session(p_session_id, true);
  IF p_operation_id IS NULL THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE = '22023';
  END IF;

  canonical_reasons := public._review_canonical_reasons(p_reasons);

  -- IDs are global receipts. Serialize their first use even across two different
  -- sessions, so concurrent rebinding returns the domain conflict, not a raw 23505.
  PERFORM pg_advisory_xact_lock(hashtextextended('review_operation:' || p_operation_id::text, 0));
  SELECT * INTO o FROM public.review_operations WHERE operation_id = p_operation_id;
  IF FOUND THEN
    IF o.session_id IS DISTINCT FROM s.id
      OR o.question_id IS DISTINCT FROM p_question_id
      OR o.actor_id IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE = '22023';
    END IF;

    stored_reasons := public._review_stored_reasons(o.reservation_result);
    IF stored_reasons IS DISTINCT FROM canonical_reasons THEN
      RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE = '22023';
    END IF;

    RETURN o.reservation_result || jsonb_build_object(
      'reasons', stored_reasons,
      'replayed', true,
      'operation_status', o.status,
      'completion_candidate', CASE WHEN o.status = 'completed' THEN o.completion_candidate END,
      'settlement', o.settlement_result
    );
  END IF;

  PERFORM public._review_assert_editable(s.id);
  SELECT q0.* INTO q
  FROM public.version_questions q0
  JOIN public.exam_versions v ON v.id = q0.version_id
  WHERE q0.id = p_question_id AND v.session_id = s.id
  FOR UPDATE OF q0;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;
  IF NOT q.is_current THEN
    RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE = '55000';
  END IF;
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF FOUND THEN
    IF public._review_job_mode(job) = 'shuffle_only' THEN
      RAISE EXCEPTION 'ERR_MODE_SHUFFLE_ONLY' USING ERRCODE = '55006';
    END IF;
    policy := public._review_slot_policy(job, q.source_question_id);
    IF policy->>'result_kind' = 'ORIGINAL_CLONE' THEN
      RAISE EXCEPTION 'ERR_SLOT_POLICY_CLONE_ONLY' USING ERRCODE = '55006';
    END IF;
    SELECT value INTO STRICT source_artifact
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources')
    WHERE value->>'source_question_id' = q.source_question_id::text;
  ELSIF EXISTS (
    SELECT 1 FROM public.generation_configs
    WHERE session_id = s.id AND mapping_version IS NOT NULL AND mapping_version NOT IN ('1.0','1.1')
  ) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen job missing' USING ERRCODE = '55006';
  END IF;
  IF q.status = 'regenerating'
    OR EXISTS (SELECT 1 FROM public.review_operations WHERE session_id = s.id AND status = 'active') THEN
    RAISE EXCEPTION 'REVIEW_BUSY' USING ERRCODE = '55000';
  END IF;
  IF s.gemini_review_calls NOT BETWEEN 0 AND 29 THEN
    RAISE EXCEPTION 'REVIEW_QUOTA_EXHAUSTED' USING ERRCODE = '54000';
  END IF;

  PERFORM public._review_progress(s.id);
  -- Read only durably confirmed artifacts. No legacy/hash/blueprint fallback.
  snapshot := public._review_frozen_artifacts(s.id, q.id);
  IF policy IS NOT NULL AND (
    source_artifact->'source_revision_id' IS DISTINCT FROM snapshot->'source_revision_id'
    OR source_artifact->'blueprint_revision_id' IS DISTINCT FROM snapshot->'blueprint_revision_id'
    OR source_artifact->'canonical_blueprint' IS DISTINCT FROM snapshot->'blueprint'
    OR source_artifact->'source_fingerprint' IS DISTINCT FROM snapshot->'blueprint_source_fingerprint'
    OR NOT (public._generation_question_policy(snapshot->'blueprint')->'canonical_dimensions')
      @> (policy->'canonical_dimensions')
  ) THEN
    RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen job and confirmed artifacts differ' USING ERRCODE = '55006';
  END IF;
  expiry := clock_timestamp() + interval '180 seconds';
  result := jsonb_build_object(
    'session_id', s.id,
    'session_status', 'generated',
    'replayed', false,
    'operation_id', p_operation_id,
    'question_id', q.id,
    'expires_at', expiry,
    'max_attempts', 4,
    'reasons', canonical_reasons,
    'snapshot', snapshot,
    'operation_status', 'active'
  );
  IF policy IS NOT NULL THEN
    result := result || jsonb_build_object('variation_dimensions', policy->'canonical_dimensions');
  END IF;
  INSERT INTO public.review_operations(
    operation_id, session_id, question_id, actor_id, prior_status, snapshot, reservation_result, expires_at
  )
  VALUES(p_operation_id, s.id, q.id, auth.uid(), q.status, snapshot, result, expiry);
  UPDATE public.version_questions
  SET status = 'regenerating', updated_at = clock_timestamp()
  WHERE id = q.id;
  UPDATE public.exam_sessions
  SET status = 'generated', updated_at = clock_timestamp()
  WHERE id = s.id;
  RETURN result;
END $$;

-- The public Revert wrapper checks policy before entering the existing action.
-- Use the same session/advisory lock order and let the action validate replays.
CREATE OR REPLACE FUNCTION public.review_revert_question(
  p_session_id uuid, p_question_id uuid, p_action_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; q public.version_questions; job public.generation_job_snapshots;
BEGIN
  s := public._review_lock_session(p_session_id, true);
  IF p_action_id IS NULL THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('review_action:' || p_action_id::text, 0));
  IF NOT EXISTS (SELECT 1 FROM public.review_action_receipts WHERE action_id = p_action_id) THEN
    PERFORM public._review_assert_editable(s.id);
    SELECT q0.* INTO q FROM public.version_questions q0
      JOIN public.exam_versions v ON v.id = q0.version_id
    WHERE q0.id = p_question_id AND v.session_id = s.id FOR UPDATE OF q0;
    IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002'; END IF;
    IF NOT q.is_current THEN RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE = '55000'; END IF;

    SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
    IF FOUND THEN
      IF public._review_job_mode(job) = 'shuffle_only' THEN
        RAISE EXCEPTION 'ERR_MODE_SHUFFLE_ONLY' USING ERRCODE = '55006';
      END IF;
      PERFORM public._review_slot_policy(job, q.source_question_id);
    ELSIF EXISTS (
      SELECT 1 FROM public.generation_configs
      WHERE session_id = s.id AND mapping_version IS NOT NULL AND mapping_version NOT IN ('1.0','1.1')
    ) THEN
      RAISE EXCEPTION 'ERR_CONFIG_CONFLICT: frozen job missing' USING ERRCODE = '55006';
    END IF;
  END IF;
  RETURN public._review_apply_action(p_session_id, p_question_id, p_action_id, true);
END $$;

-- Reuse the existing owner-checked snapshot and add capabilities under the same
-- read snapshot. Keep the base implementation private and rehash the final DTO.
DO $$
BEGIN
  IF to_regprocedure('public._review_current_snapshot_base(uuid)') IS NULL THEN
    ALTER FUNCTION public.get_review_current_snapshot(uuid) RENAME TO _review_current_snapshot_base;
  END IF;
END $$;
REVOKE ALL ON FUNCTION public._review_current_snapshot_base(uuid)
  FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.get_review_current_snapshot(p_session_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE snapshot jsonb; job public.generation_job_snapshots; mode text; policies jsonb; versions jsonb;
BEGIN
  snapshot := public._review_current_snapshot_base(p_session_id) - 'freshness_token';
  SELECT * INTO STRICT job FROM public.generation_job_snapshots
    WHERE session_id = p_session_id AND id = (snapshot->>'job_snapshot_id')::uuid;
  mode := public._review_job_mode(job);
  SELECT jsonb_object_agg(source->>'source_question_id',
    public._review_slot_policy(job, (source->>'source_question_id')::uuid)->'result_kind')
  INTO policies FROM jsonb_array_elements(snapshot->'sources') AS src(source);

  SELECT jsonb_agg(version || jsonb_build_object('slots', (
    SELECT jsonb_agg(slot || jsonb_build_object('result_kind', policies->(slot->>'source_question_id')) ORDER BY si)
    FROM jsonb_array_elements(version->'slots') WITH ORDINALITY AS s(slot, si)
  )) ORDER BY vi) INTO versions
  FROM jsonb_array_elements(snapshot->'versions') WITH ORDINALITY AS v(version, vi);

  snapshot := snapshot || jsonb_build_object('generation_mode', mode, 'versions', versions);
  RETURN snapshot || jsonb_build_object('freshness_token',
    encode(sha256(convert_to(snapshot::text, 'UTF8')), 'hex'));
END $$;
REVOKE ALL ON FUNCTION public.get_review_current_snapshot(uuid)
  FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_review_current_snapshot(uuid) TO authenticated;

NOTIFY pgrst, 'reload schema';
COMMIT;
