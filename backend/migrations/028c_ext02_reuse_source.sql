-- EXT-02 Step 7 core (PR #112): create a new draft session from an approved round.
-- Number 028c is tentative (Q05 on #111). It does not depend on EXT-04 tables yet:
-- the Bank item lookup and public._bank_capacity_check are TODO hook points below and
-- will be wired once EXT-04 lands them on an integration head. Forward-only.
BEGIN;

-- Idempotency receipts for reuse requests, keyed per user. Private to SECURITY DEFINER RPCs.
CREATE TABLE IF NOT EXISTS public.ext02_reuse_receipts (
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
  request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  source_session_id uuid NOT NULL,
  new_session_id uuid NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  generation_mode text NOT NULL CHECK (generation_mode IN ('ai_generation','shuffle_only')),
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (user_id, idempotency_key)
);
ALTER TABLE public.ext02_reuse_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ext02_reuse_receipts FROM PUBLIC, anon, authenticated, service_role;

-- Builds the new draft source from either
--   'original': the immutable confirmed source frozen in the first round's job snapshot, or
--   'version' : the stored post-shuffle projection of one finalized version (display order,
--               options, display key and solution as persisted; the old shuffle seed is not applied).
-- The new session starts as an unconfirmed draft (next_step 'confirm_source'): confirmation,
-- Blueprint and config then run through the normal pipeline. Same key + payload returns the
-- same session; a different payload raises ERR_IDEMPOTENCY_CONFLICT; any failure rolls back.
CREATE OR REPLACE FUNCTION public.reuse_session_source(
  p_source_session_id uuid,
  p_source_type text,
  p_source_version_id uuid,
  p_generation_mode text,
  p_idempotency_key text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
  src_session public.exam_sessions;
  job public.generation_job_snapshots;
  v public.exam_versions;
  prior public.ext02_reuse_receipts;
  uid uuid := auth.uid();
  fp text; questions jsonb; q jsonb; new_id uuid; n int; result jsonb; source_order jsonb;
  placeholder constant text := 'Không có lời giải cho câu hỏi này.';
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'Access denied' USING ERRCODE = '42501';
  END IF;
  IF p_idempotency_key IS NULL OR length(p_idempotency_key) NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION 'ERR_REUSE_INVALID: idempotency key required' USING ERRCODE = '22023';
  END IF;
  IF p_source_type IS NULL OR p_source_type NOT IN ('original', 'version')
     OR (p_source_type = 'version') IS DISTINCT FROM (p_source_version_id IS NOT NULL)
     OR p_generation_mode IS NULL OR p_generation_mode NOT IN ('ai_generation', 'shuffle_only') THEN
    RAISE EXCEPTION 'ERR_REUSE_INVALID: invalid source or mode' USING ERRCODE = '22023';
  END IF;
  fp := encode(sha256(convert_to(jsonb_build_object(
    'source_session_id', p_source_session_id, 'source_type', p_source_type,
    'source_version_id', p_source_version_id, 'generation_mode', p_generation_mode)::text, 'UTF8')), 'hex');

  -- Serialize the first use of a key, then replay or reject a different payload.
  PERFORM pg_advisory_xact_lock(hashtextextended('ext02_reuse:' || uid::text || ':' || p_idempotency_key, 0));
  SELECT * INTO prior FROM public.ext02_reuse_receipts
    WHERE user_id = uid AND idempotency_key = p_idempotency_key;
  IF FOUND THEN
    IF prior.request_fingerprint IS DISTINCT FROM fp THEN
      RAISE EXCEPTION 'ERR_IDEMPOTENCY_CONFLICT' USING ERRCODE = '22023';
    END IF;
    RETURN prior.result || jsonb_build_object('replayed', true);
  END IF;

  -- Owner only; a foreign session is reported as not found.
  SELECT * INTO src_session FROM public.exam_sessions WHERE id = p_source_session_id FOR SHARE;
  IF NOT FOUND OR src_session.user_id IS DISTINCT FROM uid THEN
    RAISE EXCEPTION 'Session not found' USING ERRCODE = 'P0002';
  END IF;
  -- TODO(EXT-04 I-EXT-02): resolve bank_item_id -> source session/version and check the
  -- bank item belongs to the caller once the bank tables exist.
  IF src_session.status NOT IN ('approved', 'exported') OR src_session.approved_at IS NULL THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_APPROVED' USING ERRCODE = '55000';
  END IF;

  IF p_source_type = 'original' THEN
    SELECT * INTO job FROM public.generation_job_snapshots WHERE session_id = src_session.id;
    IF job.id IS NULL OR jsonb_typeof(job.snapshot_payload->'confirmed_sources') IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: no frozen confirmed source' USING ERRCODE = '22023';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'content', x->'confirmed_input'->>'question_text', 'options', x->'confirmed_input'->'options',
        'correct_key', x->'confirmed_input'->>'correct_answer',
        'solution_md', nullif(btrim(coalesce(x->'confirmed_input'->>'solution', '')), ''),
        'from_question_no', (x->>'question_no')::int) ORDER BY ord), '[]'::jsonb),
      coalesce(jsonb_agg((x->>'question_no')::int ORDER BY ord), '[]'::jsonb)
      INTO questions, source_order
    FROM jsonb_array_elements(job.snapshot_payload->'confirmed_sources') WITH ORDINALITY a(x, ord);
  ELSE
    SELECT * INTO v FROM public.exam_versions
      WHERE id = p_source_version_id AND session_id = src_session.id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Version not found' USING ERRCODE = 'P0002';
    END IF;
    IF NOT v.is_finalized THEN
      RAISE EXCEPTION 'ERR_SOURCE_NOT_APPROVED: version not finalized' USING ERRCODE = '55000';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'content', q0.content, 'options', q0.options, 'correct_key', q0.correct_key,
        'solution_md', CASE WHEN q0.solution_md IS NULL OR btrim(q0.solution_md) = ''
          OR q0.solution_md = placeholder THEN NULL ELSE q0.solution_md END,
        'from_question_no', q0.question_no) ORDER BY q0.question_no), '[]'::jsonb),
      coalesce(jsonb_agg(q0.canonical_question_no ORDER BY q0.question_no), '[]'::jsonb)
      INTO questions, source_order
    FROM public.version_questions q0 WHERE q0.version_id = v.id AND q0.is_current;
  END IF;
  n := jsonb_array_length(questions);
  IF n NOT BETWEEN 1 AND 20 THEN
    RAISE EXCEPTION 'ERR_SOURCE_NOT_READY: source must have 1-20 questions' USING ERRCODE = '22023';
  END IF;
  -- TODO(EXT-04 I-EXT-02): call public._bank_capacity_check(new_id, <n_versions>) here once the
  -- append target is known at reuse time; it is also called by save_generation_config and claim.

  INSERT INTO public.exam_sessions(user_id, title, subject, grade)
  VALUES (uid, src_session.title, src_session.subject, src_session.grade)
  RETURNING id INTO new_id;
  FOR q IN SELECT value FROM jsonb_array_elements(questions) WITH ORDINALITY a(value, ord) ORDER BY ord LOOP
    INSERT INTO public.source_questions(session_id, question_no, raw_content, options, correct_key, solution_md)
    VALUES (new_id, (SELECT count(*) + 1 FROM public.source_questions WHERE session_id = new_id),
      q->>'content', q->'options', q->>'correct_key', q->>'solution_md');
  END LOOP;

  result := jsonb_build_object('success', true, 'replayed', false, 'session_id', new_id,
    'status', 'draft', 'next_step', 'confirm_source', 'generation_mode', p_generation_mode,
    'question_count', n,
    'source', jsonb_build_object('source_type', p_source_type, 'source_session_id', src_session.id,
      'source_version_id', p_source_version_id, 'new_source_order', source_order));
  INSERT INTO public.ext02_reuse_receipts(user_id, idempotency_key, request_fingerprint,
    source_session_id, new_session_id, generation_mode, result)
  VALUES (uid, p_idempotency_key, fp, src_session.id, new_id, p_generation_mode, result);
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.reuse_session_source(uuid, text, uuid, text, text) FROM PUBLIC, anon, service_role;
GRANT EXECUTE ON FUNCTION public.reuse_session_source(uuid, text, uuid, text, text) TO authenticated;

NOTIFY pgrst, 'reload schema';
COMMIT;
