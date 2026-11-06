-- TASK-204 Q01. 010 is retained unchanged: remote deployment history is unknown.
BEGIN;
ALTER TABLE public.exam_sessions ADD COLUMN source_content_revision UUID
  NOT NULL DEFAULT gen_random_uuid();

CREATE FUNCTION public._bump_source_content_revision()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
  UPDATE public.exam_sessions SET source_content_revision=gen_random_uuid()
    WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.session_id ELSE NEW.session_id END;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_source_content_revision AFTER INSERT OR UPDATE OR DELETE
  ON public.source_questions FOR EACH ROW
  EXECUTE FUNCTION public._bump_source_content_revision();
REVOKE ALL ON FUNCTION public._bump_source_content_revision()
  FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.get_session_source_preview(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; questions JSONB;
BEGIN
  -- SHARE conflicts with every parent UPDATE held until the source write commits.
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR SHARE;
  IF NOT FOUND OR (auth.role() IS DISTINCT FROM 'service_role'
      AND (auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid())) THEN
    RAISE EXCEPTION 'ARTIFACT_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY q.question_no,q.id),'[]'::jsonb)
    INTO questions FROM public.source_questions q WHERE q.session_id=s.id;
  RETURN jsonb_build_object('session',to_jsonb(s),
    'source_revision',s.source_content_revision,'source_questions',questions);
END $$;
REVOKE ALL ON FUNCTION public.get_session_source_preview(UUID)
  FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.get_session_source_preview(UUID) TO authenticated,service_role;

CREATE FUNCTION public.confirm_source_artifacts(
  p_session_id UUID,p_actor_id UUID,p_confirmation_id UUID,
  p_expected_source_revision UUID,p_sources JSONB
)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'ARTIFACT_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  IF p_actor_id IS NULL OR s.user_id IS DISTINCT FROM p_actor_id THEN
    RAISE EXCEPTION 'ARTIFACT_OWNER_MISMATCH' USING ERRCODE='42501';
  END IF;
  -- Serialize key lookup with the original receipt writer, including cross-session keys.
  PERFORM pg_advisory_xact_lock(hashtextextended('source_confirmation:'||p_confirmation_id::text,0));
  IF NOT EXISTS (SELECT 1 FROM public.source_artifact_confirmations
      WHERE confirmation_id=p_confirmation_id) AND
      (p_expected_source_revision IS NULL OR
       p_expected_source_revision IS DISTINCT FROM s.source_content_revision) THEN
    RAISE EXCEPTION 'ARTIFACT_STALE' USING ERRCODE='55000';
  END IF;
  -- Explicit TIMESTAMPTZ dispatch preserves receipt binding, audit and validation.
  RETURN public.confirm_source_artifacts(p_session_id,p_actor_id,p_confirmation_id,
    s.updated_at::TIMESTAMPTZ,p_sources);
END $$;
REVOKE ALL ON FUNCTION public.confirm_source_artifacts(UUID,UUID,UUID,UUID,JSONB)
  FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.confirm_source_artifacts(UUID,UUID,UUID,UUID,JSONB) TO service_role;
REVOKE EXECUTE ON FUNCTION public.confirm_source_artifacts(UUID,UUID,UUID,TIMESTAMPTZ,JSONB)
  FROM service_role;
COMMIT;
