-- EXT-01 / Package 02 (Local-only migration; shared DB deploy gated by G3 / Q05):
-- Durable rejection reasons stored in review_operations.reservation_result.reasons
-- with single 4-arg NO-DEFAULT signatures for review_lookup_regeneration and
-- review_reserve_regeneration (old 3-arg overloads dropped).

BEGIN;

DROP FUNCTION IF EXISTS public.review_lookup_regeneration(UUID, UUID, UUID);
DROP FUNCTION IF EXISTS public.review_reserve_regeneration(UUID, UUID, UUID);

CREATE OR REPLACE FUNCTION public._review_canonical_reasons(p_reasons JSONB)
RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  normalized JSONB;
BEGIN
  IF p_reasons IS NULL OR jsonb_typeof(p_reasons) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(p_reasons) AS elem
    WHERE jsonb_typeof(elem) IS DISTINCT FROM 'string'
      OR (elem #>> '{}') NOT IN (
        'INCORRECT_ANSWER',
        'NO_CORRECT_ANSWER',
        'MULTIPLE_CORRECT_ANSWERS',
        'EQUIVALENT_OPTIONS',
        'INVALID_QUESTION',
        'ISOMORPHISM_MISMATCH',
        'DIFFICULTY_MISMATCH',
        'INCORRECT_SOLUTION'
      )
  ) THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE = '22023';
  END IF;

  SELECT coalesce(jsonb_agg(code ORDER BY code COLLATE "C"), '[]'::jsonb)
  INTO normalized
  FROM (
    SELECT DISTINCT (elem #>> '{}') AS code
    FROM jsonb_array_elements(p_reasons) AS elem
  ) AS dedup;

  RETURN normalized;
END $$;

CREATE OR REPLACE FUNCTION public._review_stored_reasons(p_reservation_result JSONB)
RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
  IF p_reservation_result IS NULL OR jsonb_typeof(p_reservation_result) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: malformed reservation receipt' USING ERRCODE = '55000';
  END IF;

  IF NOT (p_reservation_result ? 'reasons') THEN
    RETURN '[]'::jsonb;
  END IF;

  BEGIN
    RETURN public._review_canonical_reasons(p_reservation_result->'reasons');
  EXCEPTION
    WHEN SQLSTATE '22023' THEN
      RAISE EXCEPTION 'REVIEW_INVARIANT_VIOLATION: malformed reservation reasons' USING ERRCODE = '55000';
  END;
END $$;

CREATE OR REPLACE FUNCTION public.review_lookup_regeneration(
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
  o public.review_operations;
  canonical_reasons JSONB;
  stored_reasons JSONB;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id = p_session_id FOR SHARE;
  IF NOT FOUND OR auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  IF p_operation_id IS NULL THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE = '22023';
  END IF;

  canonical_reasons := public._review_canonical_reasons(p_reasons);

  IF NOT EXISTS (
    SELECT 1
    FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE q.id = p_question_id AND v.session_id = s.id
  ) THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE = 'P0002';
  END IF;

  SELECT * INTO o FROM public.review_operations WHERE operation_id = p_operation_id;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('found', false);
  END IF;

  IF o.session_id IS DISTINCT FROM s.id
    OR o.question_id IS DISTINCT FROM p_question_id
    OR o.actor_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE = '22023';
  END IF;

  stored_reasons := public._review_stored_reasons(o.reservation_result);
  IF stored_reasons IS DISTINCT FROM canonical_reasons THEN
    RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE = '22023';
  END IF;

  RETURN jsonb_build_object(
    'found', true,
    'reservation', o.reservation_result || jsonb_build_object(
      'reasons', stored_reasons,
      'replayed', true,
      'operation_status', o.status,
      'completion_candidate', CASE WHEN o.status = 'completed' THEN o.completion_candidate END,
      'settlement', o.settlement_result
    )
  );
END $$;

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

REVOKE ALL ON FUNCTION
  public._review_canonical_reasons(JSONB),
  public._review_stored_reasons(JSONB),
  public.review_lookup_regeneration(UUID, UUID, UUID, JSONB),
  public.review_reserve_regeneration(UUID, UUID, UUID, JSONB)
  FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION
  public.review_lookup_regeneration(UUID, UUID, UUID, JSONB),
  public.review_reserve_regeneration(UUID, UUID, UUID, JSONB)
  TO authenticated;

-- Internal primitives run as the trusted caller. The caller already holds the
-- session lock and, for settlement, has locked the operation after its parent.
CREATE OR REPLACE FUNCTION public._review_finish_failure_locked(o public.review_operations, p_error_code TEXT, p_recovery BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE used INT; progress JSONB; result JSONB; session_status TEXT;
BEGIN
  IF p_recovery AND o.status='recovered' THEN RETURN o.settlement_result || jsonb_build_object('replayed',true); END IF;
  IF NOT p_recovery AND o.status='failed' THEN
    IF o.error_code IS DISTINCT FROM p_error_code THEN RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
    RETURN o.settlement_result || jsonb_build_object('replayed',true);
  END IF;
  IF p_recovery AND (o.status<>'active' OR o.expires_at>clock_timestamp()) THEN
    SELECT status::text INTO session_status FROM public.exam_sessions WHERE id=o.session_id;
    SELECT count(*) INTO used FROM public.review_attempts WHERE operation_id=o.operation_id AND dispatch_permitted;
    RETURN jsonb_build_object('session_id',o.session_id,'session_status',session_status,'replayed',false,'operation_id',o.operation_id,
      'question_id',o.question_id,'operation_status',o.status,'recovered',false,'api_calls_used',used);
  END IF;
  IF p_error_code IS NULL OR p_error_code !~ '^[A-Z][A-Z0-9_]{0,79}$' THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  PERFORM public._review_assert_operation(o.operation_id,false);
  SELECT count(*) INTO used FROM public.review_attempts WHERE operation_id=o.operation_id AND dispatch_permitted;
  UPDATE public.version_questions SET status=o.prior_status,updated_at=clock_timestamp() WHERE id=o.question_id;
  INSERT INTO public.review_logs(version_question_id,session_id,user_id,action_type,reason,api_calls_used)
    VALUES(o.question_id,o.session_id,o.actor_id,'REJECT_FAILED',p_error_code,used);
  UPDATE public.review_operations SET status=CASE WHEN p_recovery THEN 'recovered' ELSE 'failed' END,error_code=p_error_code
    WHERE operation_id=o.operation_id;
  progress := public._review_recalculate(o.session_id);
  SELECT status::text INTO session_status FROM public.exam_sessions WHERE id=o.session_id;
  result := jsonb_build_object('session_id',o.session_id,'session_status',session_status,'replayed',false,
    'operation_id',o.operation_id,'question_id',o.question_id,'api_calls_used',used,'operation_status',
    CASE WHEN p_recovery THEN 'recovered' ELSE 'failed' END,'recovered',p_recovery,'progress',progress);
  UPDATE public.review_operations SET settlement_result=result WHERE operation_id=o.operation_id;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public._review_finish_failure(p_operation_id UUID, p_error_code TEXT, p_recovery BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations;
BEGIN
  o := public._review_worker_operation(p_operation_id);
  RETURN public._review_finish_failure_locked(o,p_error_code,p_recovery);
END $$;

CREATE OR REPLACE FUNCTION public._review_recover_expired_locked(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations; outcome JSONB; outcomes JSONB := '[]'::jsonb;
BEGIN
  SELECT * INTO o FROM public.review_operations
    WHERE session_id=p_session_id AND status='active' AND expires_at<=clock_timestamp()
    FOR UPDATE;
  IF FOUND THEN
    outcome := public._review_finish_failure_locked(o,'STALE_RECOVERY',true);
    IF outcome->'recovered'='true'::jsonb AND outcome->'replayed'='false'::jsonb THEN
      outcomes := jsonb_build_array(outcome);
    END IF;
  END IF;
  RETURN outcomes;
END $$;

REVOKE ALL ON FUNCTION
  public._review_finish_failure_locked(public.review_operations,TEXT,BOOLEAN),
  public._review_recover_expired_locked(UUID)
  FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.review_recover_session(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; outcomes JSONB;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'REVIEW_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'REVIEW_LOCKED' USING ERRCODE='55000';
  END IF;
  IF s.status IN ('draft','blueprinted','configured','generating') THEN
    RAISE EXCEPTION 'REVIEW_NOT_READY' USING ERRCODE='55000';
  END IF;
  IF s.status='reviewed' AND EXISTS (
    SELECT 1 FROM public.exam_versions v WHERE v.session_id=s.id
    AND (v.is_finalized OR EXISTS (SELECT 1 FROM public.answer_keys k WHERE k.version_id=v.id))
  ) THEN
    RAISE EXCEPTION 'REVIEW_POST_SHUFFLE_LOCKED' USING ERRCODE='55000';
  END IF;
  outcomes := public._review_recover_expired_locked(s.id);
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id;
  RETURN jsonb_build_object('session_id',s.id,'session_status',s.status,
    'recovered_count',jsonb_array_length(outcomes),'recoveries',outcomes);
END $$;

NOTIFY pgrst, 'reload schema';

COMMIT;
