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

NOTIFY pgrst, 'reload schema';

COMMIT;
