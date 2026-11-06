-- TASK-204 P1/P2: confirmation freezes all source rows, including warning flags.
BEGIN;
CREATE FUNCTION public._guard_source_freeze()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE sid UUID; s public.exam_sessions;
BEGIN
  IF TG_OP='UPDATE' AND
      (NEW.id IS DISTINCT FROM OLD.id OR NEW.session_id IS DISTINCT FROM OLD.session_id) THEN
    RAISE EXCEPTION 'ARTIFACT_SOURCE_MISMATCH' USING ERRCODE='22023';
  END IF;
  sid := CASE WHEN TG_OP='INSERT' THEN NEW.session_id ELSE OLD.session_id END;
  SELECT * INTO s FROM public.exam_sessions WHERE id=sid FOR UPDATE;
  -- Parent DELETE has already removed its tuple before the FK cascade visits us.
  -- Other missing-parent writes still face the existing FK constraint.
  IF FOUND AND (s.status IS DISTINCT FROM 'draft' OR s.approved_at IS NOT NULL) THEN
    RAISE EXCEPTION 'ARTIFACT_SOURCE_LOCKED' USING ERRCODE='55000';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public._guard_source_freeze()
  FROM PUBLIC,anon,authenticated,service_role;
-- Run before both existing BEFORE triggers; no invalidation occurs on refusal.
CREATE TRIGGER trg_00_source_freeze_guard BEFORE INSERT OR UPDATE OR DELETE
  ON public.source_questions FOR EACH ROW EXECUTE FUNCTION public._guard_source_freeze();
COMMIT;
