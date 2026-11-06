-- TASK-204 Q02: public profile 1.0 pinned to BE2 7e9377f; retain readiness/ACL.
BEGIN;
CREATE OR REPLACE FUNCTION public.get_source_artifacts(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; c public.source_artifact_confirmations; pending JSONB; states JSONB; modes JSONB; doc JSONB; transform JSONB;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR SHARE;
  IF NOT FOUND OR (auth.role() IS DISTINCT FROM 'service_role'
      AND (auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid())) THEN
    RAISE EXCEPTION 'ARTIFACT_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  SELECT * INTO c FROM public.source_artifact_confirmations WHERE session_id=s.id
    ORDER BY confirmed_at DESC,confirmation_id DESC LIMIT 1;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ARTIFACT_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  IF jsonb_array_length(c.result->'sources')<>(SELECT count(*) FROM public.source_questions WHERE session_id=s.id)
    OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(c.result->'sources') item
    LEFT JOIN public.source_artifact_heads h ON h.source_question_id=(item->>'source_question_id')::uuid
    LEFT JOIN public.source_questions q ON q.id=h.source_question_id
    WHERE h.source_revision_id IS DISTINCT FROM (item->>'source_revision_id')::uuid
      OR public._artifact_source_input(q) IS DISTINCT FROM item->'confirmed_input'
  ) THEN RAISE EXCEPTION 'ARTIFACT_STALE' USING ERRCODE='55000'; END IF;
  SELECT coalesce(jsonb_agg(h.source_question_id ORDER BY h.source_question_id),'[]'::jsonb)
    INTO pending FROM public.source_artifact_heads h JOIN public.source_questions q ON q.id=h.source_question_id
    WHERE q.session_id=s.id AND h.blueprint_revision_id IS NULL;
  SELECT coalesce(jsonb_agg(jsonb_build_object('source_question_id',h.source_question_id,
    'source_revision_id',h.source_revision_id,'status',CASE
      WHEN h.blueprint_revision_id IS NOT NULL THEN 'ready'
      WHEN h.producer_error_code IS NOT NULL THEN 'failed'
      WHEN h.producer_expires_at>clock_timestamp() THEN 'running' ELSE 'pending' END,
    'expires_at',h.producer_expires_at,'error_code',h.producer_error_code) ORDER BY h.source_question_id),'[]'::jsonb)
    INTO states FROM public.source_artifact_heads h JOIN public.source_questions q ON q.id=h.source_question_id
    WHERE q.session_id=s.id;
  IF jsonb_array_length(pending)=0 THEN
    FOR doc IN
      SELECT b.canonical_blueprint FROM public.source_artifact_heads h
      JOIN public.source_questions q ON q.id=h.source_question_id
      JOIN public.canonical_blueprint_revisions b ON
        (b.blueprint_revision_id,b.source_revision_id,b.source_question_id)=
        (h.blueprint_revision_id,h.source_revision_id,h.source_question_id)
      WHERE q.session_id=s.id
    LOOP
      IF doc->'requirement'->>'schema_version' IS DISTINCT FROM '0.4.0'
        OR jsonb_typeof(doc#>'{requirement,variation_policy,allowed_transformations}') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'ARTIFACT_INVALID_CANONICAL_MODES' USING ERRCODE='22023';
      END IF;
      IF jsonb_array_length(doc#>'{requirement,variation_policy,allowed_transformations}')=0 THEN
        RAISE EXCEPTION 'ARTIFACT_INVALID_CANONICAL_MODES' USING ERRCODE='22023';
      END IF;
      FOR transform IN SELECT value FROM jsonb_array_elements(doc#>'{requirement,variation_policy,allowed_transformations}') LOOP
        IF jsonb_typeof(transform) IS DISTINCT FROM 'object'
          OR jsonb_typeof(transform->'dimension') IS DISTINCT FROM 'string'
          OR transform->>'dimension' NOT IN ('wording','names','context','values','representation','option_order') THEN
          RAISE EXCEPTION 'ARTIFACT_INVALID_CANONICAL_MODES' USING ERRCODE='22023';
        END IF;
      END LOOP;
    END LOOP;
    WITH profile(id,dimension,label,description) AS (VALUES
      ('NUMERICAL','values','Thay đổi số liệu / tham số','Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.'),
      ('parameter_variation','values','Thay đổi số liệu / tham số','Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.'),
      ('context_swap','context','Đổi ngữ cảnh thực tế','Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.')
    ), dimensions AS (
      SELECT DISTINCT h.source_question_id,t->>'dimension' AS dimension
      FROM public.source_artifact_heads h
      JOIN public.source_questions q ON q.id=h.source_question_id
      JOIN public.canonical_blueprint_revisions b ON
        (b.blueprint_revision_id,b.source_revision_id,b.source_question_id)=
        (h.blueprint_revision_id,h.source_revision_id,h.source_question_id)
      CROSS JOIN LATERAL jsonb_array_elements(b.canonical_blueprint#>'{requirement,variation_policy,allowed_transformations}') t
      WHERE q.session_id=s.id
    ), counts AS (
      SELECT p.id,p.label,p.description,count(*) AS n FROM dimensions d
      JOIN profile p ON p.dimension=d.dimension GROUP BY p.id,p.label,p.description
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'label',label,'description',description,
      'question_count',n,'is_available',n=(c.result->>'total_questions')::int) ORDER BY id COLLATE "C"),'[]'::jsonb)
      INTO modes FROM counts;
  END IF;
  RETURN jsonb_build_object('confirmation',c.result,'pending_source_question_ids',pending,'production',states,
    'ready',jsonb_array_length(pending)=0,'supported_modes',modes);
END $$;
REVOKE ALL ON FUNCTION public.get_source_artifacts(UUID) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.get_source_artifacts(UUID) TO authenticated,service_role;
COMMIT;
