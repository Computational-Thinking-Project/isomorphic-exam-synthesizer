-- EXT-02 Step 3 (PR #112): backend confirmation of shuffle-only copies.
-- Number 028b is tentative (Q05 on #111). Order: 028 -> 028b -> 029 -> 029b.
-- 029/029b do not redefine review_accept_question, so the Accept guard below survives them.
-- Forward-only; no table changes and no new grants beyond the new RPC.
BEGIN;

-- Copies of a frozen shuffle_only job are verified against the ledger and the frozen
-- confirmed source, then marked approved through the existing Review data model so
-- _review_recalculate moves the session to 'reviewed' and progress.ready becomes true.
-- Owner (authenticated) or worker (service_role). Idempotent; any failure raises and
-- leaves the session unchanged.
CREATE OR REPLACE FUNCTION public.confirm_shuffle_only_copies(p_session_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  s public.exam_sessions;
  job public.generation_job_snapshots;
  n_sources int; expected int; currents int; committed int; approved_before int;
  progress jsonb; prior_status public.session_status;
BEGIN
  -- Same parent-first session lock as Review, claim and shuffle.
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;
  IF public.current_role() <> 'service_role'
     AND (auth.uid() IS NULL OR auth.uid() IS DISTINCT FROM s.user_id) THEN
    RAISE EXCEPTION 'Access denied' USING ERRCODE = '42501';
  END IF;
  prior_status := s.status;
  IF s.status IN ('approved', 'exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'REVIEW_LOCKED' USING ERRCODE = '55000';
  END IF;
  SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
  IF job.id IS NULL OR public._generation_job_mode(job) <> 'shuffle_only' THEN
    RAISE EXCEPTION 'ERR_MODE_NOT_SHUFFLE_ONLY' USING ERRCODE = '55006';
  END IF;
  IF s.status NOT IN ('generated', 'reviewed') THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_ONLY_NOT_READY: session is %', s.status USING ERRCODE = '55000';
  END IF;
  IF EXISTS (SELECT 1 FROM public.review_operations WHERE session_id = s.id AND status = 'active') THEN
    RAISE EXCEPTION 'REVIEW_BUSY' USING ERRCODE = '55000';
  END IF;

  n_sources := jsonb_array_length(job.snapshot_payload->'confirmed_sources');
  expected := job.n_versions * n_sources;
  SELECT count(*), count(*) FILTER (WHERE q.status = 'approved') INTO currents, approved_before
  FROM public.exam_versions v JOIN public.version_questions q ON q.version_id = v.id AND q.is_current
  WHERE v.session_id = s.id;
  IF currents <> expected OR EXISTS (
    SELECT 1 FROM public.exam_versions v JOIN public.version_questions q ON q.version_id = v.id AND q.is_current
    WHERE v.session_id = s.id AND q.status NOT IN ('pending_review', 'approved')
  ) THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_ONLY_NOT_READY: current candidates incomplete' USING ERRCODE = '55000';
  END IF;

  -- _generation_committed already binds each ledger row to its current candidate and
  -- checks content, options, key and solution (placeholder included) against the frozen
  -- source. Every slot must be one such ORIGINAL_CLONE row with a 64-hex fingerprint.
  SELECT count(DISTINCT (r.version_index, r.source_question_id)) INTO committed
  FROM public._generation_committed(s.id, job.id) r
  JOIN public.version_questions q ON q.id = r.version_question_id AND q.is_current
  WHERE r.result_kind = 'ORIGINAL_CLONE'
    AND r.clone_fingerprint ~ '^[0-9a-f]{64}$'
    AND public._generation_is_clone(job, r.source_question_id);
  IF committed <> expected OR EXISTS (
    SELECT 1 FROM public.generation_target_results r
    WHERE r.session_id = s.id AND r.is_success AND r.result_kind <> 'ORIGINAL_CLONE'
  ) THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_ONLY_NOT_READY: copies do not match the frozen source' USING ERRCODE = '55000';
  END IF;

  UPDATE public.version_questions q SET status = 'approved', updated_at = clock_timestamp()
  FROM public.exam_versions v
  WHERE v.id = q.version_id AND v.session_id = s.id AND q.is_current AND q.status <> 'approved';
  progress := public._review_recalculate(s.id);
  IF (progress->>'ready')::boolean IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'ERR_SHUFFLE_ONLY_NOT_READY: review progress not ready' USING ERRCODE = '55000';
  END IF;
  SELECT * INTO s FROM public.exam_sessions WHERE id = s.id;
  RETURN jsonb_build_object('success', true, 'session_id', s.id, 'session_status', s.status,
    'generation_mode', 'shuffle_only', 'confirmed_slots', expected,
    'replayed', prior_status = 'reviewed' AND approved_before = expected,
    'progress', progress);
END $$;
REVOKE ALL ON FUNCTION public.confirm_shuffle_only_copies(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.confirm_shuffle_only_copies(uuid) TO authenticated, service_role;

-- Manual Accept: new Accept operations are rejected for shuffle_only jobs; a stored
-- receipt still replays. Same lock order as Duy's 029b revert guard.
CREATE OR REPLACE FUNCTION public.review_accept_question(p_session_id uuid, p_question_id uuid, p_action_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; job public.generation_job_snapshots;
BEGIN
  s := public._review_lock_session(p_session_id, true);
  IF p_action_id IS NULL THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('review_action:' || p_action_id::text, 0));
  IF NOT EXISTS (SELECT 1 FROM public.review_action_receipts WHERE action_id = p_action_id) THEN
    SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = s.id;
    IF job.id IS NOT NULL AND public._generation_job_mode(job) = 'shuffle_only' THEN
      RAISE EXCEPTION 'ERR_MODE_SHUFFLE_ONLY' USING ERRCODE = '55006';
    END IF;
  END IF;
  RETURN public._review_apply_action(p_session_id, p_question_id, p_action_id, false);
END $$;
REVOKE ALL ON FUNCTION public.review_accept_question(uuid, uuid, uuid) FROM PUBLIC, anon, service_role;
GRANT EXECUTE ON FUNCTION public.review_accept_question(uuid, uuid, uuid) TO authenticated;

NOTIFY pgrst, 'reload schema';
COMMIT;
