-- TASK-302: schema foundation and atomic review operation/attempt RPCs.
-- Run with psql -v ON_ERROR_STOP=1. Any ambiguous legacy data rolls back the upgrade.
BEGIN;

-- TASK-302 owns this ledger. A competing migration must not be silently accepted
-- by CREATE TABLE IF NOT EXISTS: its receipts may represent already charged calls.
-- In particular, PR #28's 008 used session_id/status instead of these fields.
-- Preserve that data and require an owner-reviewed transition if it was deployed.
DO $$ BEGIN
  IF to_regclass('public.review_attempts') IS NOT NULL AND EXISTS (
    SELECT 1 FROM (VALUES ('attempt_id'),('operation_id'),('dispatch_permitted'),
      ('calls_used'),('remaining_calls'),('created_at')) required(name)
    WHERE NOT EXISTS (
      SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass('public.review_attempts')
        AND attname=required.name AND attnum>0 AND NOT attisdropped
    )
  ) THEN
    RAISE EXCEPTION 'TASK302: incompatible review_attempts ledger; preserve receipts/quota and request a migration transition before retrying';
  END IF;
END $$;

LOCK TABLE public.exam_sessions, public.exam_versions, public.version_questions,
  public.review_logs, public.answer_keys IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.exam_sessions
  ADD COLUMN IF NOT EXISTS gemini_review_calls INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

ALTER TABLE public.version_questions
  ADD COLUMN IF NOT EXISTS canonical_question_no INT,
  ADD COLUMN IF NOT EXISTS canonical_options JSONB,
  ADD COLUMN IF NOT EXISTS canonical_correct_key TEXT,
  ADD COLUMN IF NOT EXISTS canonical_solution_md TEXT,
  ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS regenerated_from_id UUID REFERENCES public.version_questions(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS is_reverted BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS regeneration_id UUID,
  ADD COLUMN IF NOT EXISTS validation_report JSONB NOT NULL DEFAULT '{}'::jsonb;

-- A legacy display value cannot establish a missing canonical snapshot, even if
-- is_finalized is now false (e.g. a previous shuffle was invalidated).
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM public.version_questions q
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE (
      q.canonical_question_no IS NULL OR q.canonical_options IS NULL
      OR q.canonical_correct_key IS NULL
    )
  ) THEN
    RAISE EXCEPTION 'TASK302: missing canonical data; restore verified canonical snapshot before retrying';
  END IF;
END $$;

ALTER TABLE public.version_questions
  ALTER COLUMN canonical_question_no SET NOT NULL,
  ALTER COLUMN canonical_options SET NOT NULL,
  ALTER COLUMN canonical_correct_key SET NOT NULL;

-- This index enforces AT MOST one current row. Atomic replacement RPCs must also
-- ensure that a slot never loses its current row (implemented below).
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_current_version_question
  ON public.version_questions (version_id, source_question_id) WHERE is_current = TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_version_questions_regeneration
  ON public.version_questions (regeneration_id) WHERE regeneration_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_version_questions_stale_guard
  ON public.version_questions (updated_at) WHERE status = 'regenerating';

-- The table already exists on dev: CREATE TABLE IF NOT EXISTS is not an upgrade.
ALTER TABLE public.review_logs
  ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES public.users(id),
  ADD COLUMN IF NOT EXISTS api_calls_used INT,
  ADD COLUMN IF NOT EXISTS regenerated_from_id UUID REFERENCES public.version_questions(id);

-- Also cover partially prepared databases where the column exists without its FK.
DO $$
DECLARE fk RECORD;
BEGIN
  FOR fk IN SELECT * FROM (VALUES
    ('review_logs_session_id_fkey', 'FOREIGN KEY (session_id) REFERENCES public.exam_sessions(id) ON DELETE CASCADE'),
    ('review_logs_user_id_fkey', 'FOREIGN KEY (user_id) REFERENCES public.users(id)'),
    ('review_logs_regenerated_from_id_fkey', 'FOREIGN KEY (regenerated_from_id) REFERENCES public.version_questions(id)')
  ) AS required(name, definition)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conrelid = 'public.review_logs'::regclass AND conname = fk.name) THEN
      EXECUTE format('ALTER TABLE public.review_logs ADD CONSTRAINT %I %s', fk.name, fk.definition);
    END IF;
  END LOOP;
END $$;

UPDATE public.review_logs l
SET session_id = v.session_id
FROM public.version_questions q JOIN public.exam_versions v ON v.id = q.version_id
WHERE l.version_question_id = q.id AND l.session_id IS NULL;

DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM public.review_logs l
    JOIN public.version_questions q ON q.id = l.version_question_id
    JOIN public.exam_versions v ON v.id = q.version_id
    WHERE l.session_id IS DISTINCT FROM v.session_id
  ) THEN
    RAISE EXCEPTION 'TASK302: review log/session mismatch; inspect legacy data before retrying';
  END IF;
END $$;
ALTER TABLE public.review_logs ALTER COLUMN session_id SET NOT NULL;
-- Decision by TASK-302 owner (2026-10-31): keep NULL for unknown historical
-- actors; never fabricate them from the session owner or use a sentinel UUID.
-- NOT VALID intentionally exempts existing rows from the initial scan, while
-- PostgreSQL still checks EVERY future INSERT and UPDATE. Backdating created_at
-- cannot bypass this rule. Updating an unknown-actor historical row also requires
-- a verified actor; leave that row untouched when no such evidence exists.
-- Do not SET NOT NULL or VALIDATE this constraint until every historical NULL
-- has been resolved using verified evidence. Replay must not validate it either.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.review_logs'::regclass
      AND conname = 'ck_review_logs_actor_required') THEN
    ALTER TABLE public.review_logs ADD CONSTRAINT ck_review_logs_actor_required
      CHECK (user_id IS NOT NULL) NOT VALID;
  END IF;
END $$;
COMMENT ON COLUMN public.review_logs.user_id IS
  'Verified review actor. NULL means unknown pre-006 historical actor, not session owner or system actor. New writes require an actor.';
COMMENT ON CONSTRAINT ck_review_logs_actor_required ON public.review_logs IS
  'Preserves existing unknown actors; rejects new/updated rows with NULL actor, regardless of created_at. Do not validate until verified historical backfill is complete.';
CREATE INDEX IF NOT EXISTS idx_review_logs_session_created
  ON public.review_logs (session_id, created_at DESC);

ALTER TABLE public.answer_keys
  ADD COLUMN IF NOT EXISTS display_no INT,
  ADD COLUMN IF NOT EXISTS display_correct_key TEXT,
  ADD COLUMN IF NOT EXISTS canonical_question_no INT;

DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM public.answer_keys
    WHERE (display_no IS NOT NULL AND display_no IS DISTINCT FROM question_no)
       OR (display_correct_key IS NOT NULL AND display_correct_key IS DISTINCT FROM correct_option)
  ) THEN
    RAISE EXCEPTION 'TASK302: conflicting legacy/display answer key values; no value was selected automatically';
  END IF;
END $$;

UPDATE public.answer_keys
SET display_no = question_no, display_correct_key = correct_option
WHERE display_no IS NULL OR display_correct_key IS NULL;

-- Never guess a canonical slot from display order. Only a unique current candidate
-- with the same version/display number establishes the mapping.
WITH mappings AS (
  SELECT version_id, question_no, min(canonical_question_no) AS canonical_no
  FROM public.version_questions WHERE is_current
  GROUP BY version_id, question_no HAVING count(*) = 1
)
UPDATE public.answer_keys a SET canonical_question_no = m.canonical_no
FROM mappings m
WHERE a.version_id = m.version_id AND a.display_no = m.question_no
  AND a.canonical_question_no IS NULL;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.answer_keys WHERE canonical_question_no IS NULL) THEN
    RAISE EXCEPTION 'TASK302: answer key canonical mapping is missing or ambiguous; supply verified mapping before retrying';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.answer_keys a
    JOIN (
      SELECT version_id, question_no, min(canonical_question_no) AS canonical_no
      FROM public.version_questions WHERE is_current
      GROUP BY version_id, question_no HAVING count(*) = 1
    ) q ON q.version_id = a.version_id AND q.question_no = a.display_no
    WHERE a.canonical_question_no IS DISTINCT FROM q.canonical_no
  ) THEN
    RAISE EXCEPTION 'TASK302: conflicting answer key canonical mapping; inspect legacy data before retrying';
  END IF;
END $$;
ALTER TABLE public.answer_keys
  ALTER COLUMN display_no SET NOT NULL,
  ALTER COLUMN display_correct_key SET NOT NULL,
  ALTER COLUMN canonical_question_no SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_answer_keys_version_display
  ON public.answer_keys (version_id, display_no);

-- Preserve canonical values per candidate while permitting display-only shuffle.
-- A different candidate must be inserted as a new row with its own snapshot.
CREATE OR REPLACE FUNCTION public.guard_candidate_canonical()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF ROW(NEW.canonical_question_no, NEW.canonical_options,
         NEW.canonical_correct_key, NEW.canonical_solution_md)
     IS DISTINCT FROM
     ROW(OLD.canonical_question_no, OLD.canonical_options,
         OLD.canonical_correct_key, OLD.canonical_solution_md) THEN
    RAISE EXCEPTION 'TASK302: canonical snapshot is immutable; insert a new candidate'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_candidate_canonical_immutable ON public.version_questions;
CREATE TRIGGER trg_candidate_canonical_immutable
  BEFORE UPDATE ON public.version_questions
  FOR EACH ROW EXECUTE FUNCTION public.guard_candidate_canonical();

-- Bridge the existing DB field names and the Week 3 display field names. UPDATE
-- detects which representation changed, allowing either client during handoff.
CREATE OR REPLACE FUNCTION public.sync_answer_key_display_aliases()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.question_no IS DISTINCT FROM OLD.question_no AND NEW.display_no IS NOT DISTINCT FROM OLD.display_no THEN
      NEW.display_no := NEW.question_no;
    ELSIF NEW.display_no IS DISTINCT FROM OLD.display_no AND NEW.question_no IS NOT DISTINCT FROM OLD.question_no THEN
      NEW.question_no := NEW.display_no;
    END IF;
    IF NEW.correct_option IS DISTINCT FROM OLD.correct_option AND NEW.display_correct_key IS NOT DISTINCT FROM OLD.display_correct_key THEN
      NEW.display_correct_key := NEW.correct_option;
    ELSIF NEW.display_correct_key IS DISTINCT FROM OLD.display_correct_key AND NEW.correct_option IS NOT DISTINCT FROM OLD.correct_option THEN
      NEW.correct_option := NEW.display_correct_key;
    END IF;
  END IF;
  NEW.question_no := COALESCE(NEW.question_no, NEW.display_no);
  NEW.display_no := COALESCE(NEW.display_no, NEW.question_no);
  NEW.correct_option := COALESCE(NEW.correct_option, NEW.display_correct_key);
  NEW.display_correct_key := COALESCE(NEW.display_correct_key, NEW.correct_option);
  IF NEW.question_no IS DISTINCT FROM NEW.display_no
     OR NEW.correct_option IS DISTINCT FROM NEW.display_correct_key THEN
    RAISE EXCEPTION 'TASK302: conflicting legacy/display answer key values' USING ERRCODE = '23514';
  END IF;
  IF NEW.canonical_question_no IS NULL THEN
    SELECT min(q.canonical_question_no) INTO NEW.canonical_question_no
    FROM public.version_questions q
    WHERE q.version_id = NEW.version_id AND q.question_no = NEW.display_no AND q.is_current
    HAVING count(*) = 1;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_answer_key_display_aliases ON public.answer_keys;
CREATE TRIGGER trg_answer_key_display_aliases
  BEFORE INSERT OR UPDATE ON public.answer_keys
  FOR EACH ROW EXECUTE FUNCTION public.sync_answer_key_display_aliases();

-- Durable receipts contain only committed outcomes. No provider request runs in
-- these transactions; a committed permit is charged even if its response is lost.
CREATE TABLE IF NOT EXISTS public.review_operations (
  operation_id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  question_id UUID NOT NULL REFERENCES public.version_questions(id),
  actor_id UUID NOT NULL REFERENCES public.users(id),
  prior_status public.question_status NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','failed','recovered')),
  snapshot JSONB NOT NULL,
  reservation_result JSONB NOT NULL,
  settlement_result JSONB,
  completion_candidate JSONB,
  error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (clock_timestamp() + interval '180 seconds')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_active_session
  ON public.review_operations(session_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_review_operation_expiry
  ON public.review_operations(expires_at) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS public.review_attempts (
  attempt_id UUID PRIMARY KEY,
  operation_id UUID NOT NULL REFERENCES public.review_operations(operation_id) ON DELETE CASCADE,
  dispatch_permitted BOOLEAN NOT NULL,
  calls_used INT NOT NULL CHECK (calls_used BETWEEN 0 AND 30),
  remaining_calls INT NOT NULL CHECK (remaining_calls BETWEEN 0 AND 30),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (calls_used + remaining_calls = 30)
);
CREATE INDEX IF NOT EXISTS idx_review_attempt_operation ON public.review_attempts(operation_id);

CREATE TABLE IF NOT EXISTS public.review_action_receipts (
  action_id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  question_id UUID NOT NULL REFERENCES public.version_questions(id),
  actor_id UUID NOT NULL REFERENCES public.users(id),
  action_type TEXT NOT NULL CHECK (action_type IN ('ACCEPT','REVERT')),
  result JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE public.review_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_action_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.review_operations, public.review_attempts, public.review_action_receipts
  FROM PUBLIC, anon, authenticated, service_role;

-- Helpers are not callable by API roles. All mutating RPCs acquire the parent
-- session lock FIRST, then operation/candidate locks, including worker settlement.
CREATE OR REPLACE FUNCTION public._review_lock_session(p_session_id UUID, p_owner BOOLEAN)
RETURNS public.exam_sessions LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE;
  IF NOT FOUND OR (p_owner AND (auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid())) THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  RETURN s;
END $$;

CREATE OR REPLACE FUNCTION public._review_assert_editable(p_session_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions;
BEGIN
  SELECT * INTO STRICT s FROM public.exam_sessions WHERE id=p_session_id;
  IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'REVIEW_LOCKED' USING ERRCODE='55000';
  END IF;
  IF s.status NOT IN ('generated','reviewed') THEN
    RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE='55000';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public._review_worker_operation(p_operation_id UUID)
RETURNS public.review_operations LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations; sid UUID;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'REVIEW_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  SELECT session_id INTO sid FROM public.review_operations WHERE operation_id=p_operation_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002'; END IF;
  PERFORM public._review_lock_session(sid, false);
  SELECT * INTO o FROM public.review_operations WHERE operation_id=p_operation_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002'; END IF;
  RETURN o;
END $$;

CREATE OR REPLACE FUNCTION public._review_assert_operation(p_operation_id UUID, p_check_expiry BOOLEAN)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations;
BEGIN
  SELECT * INTO STRICT o FROM public.review_operations WHERE operation_id=p_operation_id;
  PERFORM public._review_assert_editable(o.session_id);
  IF o.status <> 'active' OR (p_check_expiry AND o.expires_at <= clock_timestamp()) OR NOT EXISTS (
    SELECT 1 FROM public.version_questions q JOIN public.exam_versions v ON v.id=q.version_id
    WHERE q.id=o.question_id AND q.is_current AND q.status='regenerating' AND v.session_id=o.session_id
  ) THEN RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE='55000'; END IF;
  IF p_check_expiry THEN
    IF o.snapshot IS DISTINCT FROM public._review_artifact_snapshot(o.question_id) THEN
      RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023';
    END IF;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public._review_progress(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE nv INT; ns INT; config_count INT; versions_count INT; codes_count INT;
  currents INT; approved INT; regenerating INT; missing INT; duplicates INT; extras INT; expected INT; ready BOOLEAN;
  unapproved JSONB; source_ready BOOLEAN;
BEGIN
  SELECT count(*),min(n_versions) INTO config_count,nv FROM public.generation_configs WHERE session_id=p_session_id;
  SELECT count(*) INTO ns FROM public.source_questions WHERE session_id=p_session_id;
  IF config_count <> 1 OR ns=0 OR EXISTS (
    SELECT question_no FROM public.source_questions WHERE session_id=p_session_id GROUP BY question_no HAVING count(*)>1
  ) THEN RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023'; END IF;
  SELECT NOT EXISTS (
    SELECT 1 FROM public.source_questions s WHERE s.session_id=p_session_id AND NOT EXISTS (
      SELECT 1 FROM public.source_artifact_heads h
      JOIN public.source_artifact_revisions r ON r.source_revision_id=h.source_revision_id
      JOIN public.canonical_blueprint_revisions b ON b.blueprint_revision_id=h.blueprint_revision_id
        AND b.source_revision_id=h.source_revision_id AND b.source_question_id=h.source_question_id
      WHERE h.source_question_id=s.id AND public._artifact_source_input(s)=r.confirmed_input
    )
  ) INTO source_ready;
  expected := nv * ns;
  SELECT count(*),count(DISTINCT version_code) INTO versions_count,codes_count
    FROM public.exam_versions WHERE session_id=p_session_id;
  SELECT count(*),count(*) FILTER (WHERE q.status='approved'),count(*) FILTER (WHERE q.status='regenerating'),
    count(*) FILTER (WHERE s.id IS NULL OR q.canonical_question_no IS DISTINCT FROM s.question_no)
    INTO currents,approved,regenerating,extras
  FROM public.exam_versions v JOIN public.version_questions q ON q.version_id=v.id AND q.is_current
    LEFT JOIN public.source_questions s ON s.id=q.source_question_id AND s.session_id=p_session_id
  WHERE v.session_id=p_session_id;
  SELECT count(*) FILTER (WHERE n=0),count(*) FILTER (WHERE n>1) INTO missing,duplicates FROM (
    SELECT v.id,s.id AS source_id,count(q.id) AS n FROM public.exam_versions v
    CROSS JOIN public.source_questions s LEFT JOIN public.version_questions q
      ON q.version_id=v.id AND q.source_question_id=s.id AND q.is_current
    WHERE v.session_id=p_session_id AND s.session_id=p_session_id GROUP BY v.id,s.id
  ) slots;
  missing := missing + greatest(nv-versions_count,0)*ns;
  ready := source_ready AND versions_count=nv AND codes_count=nv AND missing=0 AND duplicates=0 AND extras=0
    AND currents=expected AND approved=expected AND regenerating=0
    AND NOT EXISTS (SELECT 1 FROM public.review_operations WHERE session_id=p_session_id AND status='active');
  SELECT coalesce(jsonb_agg(q.id ORDER BY q.id),'[]'::jsonb) INTO unapproved
    FROM public.version_questions q JOIN public.exam_versions v ON v.id=q.version_id
    WHERE v.session_id=p_session_id AND q.is_current AND q.status<>'approved';
  RETURN jsonb_build_object('expected_slots',expected,'current_slots',currents,'approved_slots',approved,
    'regenerating_slots',regenerating,'missing_slots',missing,'duplicate_slots',duplicates,'ready',ready,
    'unapproved_question_ids',unapproved);
END $$;

CREATE OR REPLACE FUNCTION public._review_recalculate(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE progress JSONB;
BEGIN
  progress := public._review_progress(p_session_id);
  UPDATE public.exam_sessions SET status=CASE WHEN (progress->>'ready')::boolean
    THEN 'reviewed'::public.session_status ELSE 'generated'::public.session_status END,
    updated_at=clock_timestamp() WHERE id=p_session_id;
  RETURN progress;
END $$;

CREATE OR REPLACE FUNCTION public._review_invalidate(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE ids JSONB;
BEGIN
  SELECT coalesce(jsonb_agg(id ORDER BY id),'[]'::jsonb) INTO ids FROM public.exam_versions WHERE session_id=p_session_id;
  DELETE FROM public.answer_keys a USING public.exam_versions v WHERE a.version_id=v.id AND v.session_id=p_session_id;
  UPDATE public.exam_versions SET is_finalized=false,shuffle_seed=NULL,permutations=NULL WHERE session_id=p_session_id;
  RETURN ids;
END $$;

CREATE OR REPLACE FUNCTION public.review_get_progress(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR SHARE;
  IF NOT FOUND OR auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  RETURN jsonb_build_object('session_id',s.id,'session_status',s.status,'replayed',false,
    'progress',public._review_progress(s.id));
END $$;

CREATE OR REPLACE FUNCTION public.review_lookup_regeneration(p_session_id UUID,p_question_id UUID,p_operation_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; o public.review_operations;
BEGIN
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id FOR SHARE;
  IF NOT FOUND OR auth.uid() IS NULL OR s.user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  IF p_operation_id IS NULL THEN RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.version_questions q JOIN public.exam_versions v ON v.id=q.version_id
    WHERE q.id=p_question_id AND v.session_id=s.id) THEN
    RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002';
  END IF;
  SELECT * INTO o FROM public.review_operations WHERE operation_id=p_operation_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('found',false); END IF;
  IF o.session_id IS DISTINCT FROM s.id OR o.question_id IS DISTINCT FROM p_question_id
    OR o.actor_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
  END IF;
  RETURN jsonb_build_object('found',true,'reservation',o.reservation_result ||
    jsonb_build_object('replayed',true,'operation_status',o.status,'settlement',o.settlement_result));
END $$;
REVOKE ALL ON FUNCTION public.review_lookup_regeneration(UUID,UUID,UUID) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.review_lookup_regeneration(UUID,UUID,UUID) TO authenticated;

CREATE OR REPLACE FUNCTION public.review_reserve_regeneration(p_session_id UUID, p_question_id UUID, p_operation_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; q public.version_questions; o public.review_operations;
  snapshot JSONB; result JSONB; expiry TIMESTAMPTZ;
BEGIN
  s := public._review_lock_session(p_session_id,true);
  IF p_operation_id IS NULL THEN RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  -- IDs are global receipts. Serialize their first use even across two different
  -- sessions, so concurrent rebinding returns the domain conflict, not a raw 23505.
  PERFORM pg_advisory_xact_lock(hashtextextended('review_operation:'||p_operation_id::text,0));
  SELECT * INTO o FROM public.review_operations WHERE operation_id=p_operation_id;
  IF FOUND THEN
    IF o.session_id IS DISTINCT FROM s.id OR o.question_id IS DISTINCT FROM p_question_id OR o.actor_id IS DISTINCT FROM auth.uid() THEN
      RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
    END IF;
    RETURN o.reservation_result || jsonb_build_object('replayed',true,'operation_status',o.status,'settlement',o.settlement_result);
  END IF;
  PERFORM public._review_assert_editable(s.id);
  SELECT q0.* INTO q FROM public.version_questions q0 JOIN public.exam_versions v ON v.id=q0.version_id
    WHERE q0.id=p_question_id AND v.session_id=s.id FOR UPDATE OF q0;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002'; END IF;
  IF NOT q.is_current THEN RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE='55000'; END IF;
  IF q.status='regenerating' OR EXISTS (SELECT 1 FROM public.review_operations WHERE session_id=s.id AND status='active') THEN
    RAISE EXCEPTION 'REVIEW_BUSY' USING ERRCODE='55000';
  END IF;
  IF s.gemini_review_calls NOT BETWEEN 0 AND 29 THEN
    RAISE EXCEPTION 'REVIEW_QUOTA_EXHAUSTED' USING ERRCODE='54000';
  END IF;
  PERFORM public._review_progress(s.id);
  snapshot := public._review_artifact_snapshot(q.id);
  expiry := clock_timestamp()+interval '180 seconds';
  result := jsonb_build_object('session_id',s.id,'session_status','generated','replayed',false,
    'operation_id',p_operation_id,'question_id',q.id,'expires_at',expiry,'max_attempts',4,'snapshot',snapshot,'operation_status','active');
  INSERT INTO public.review_operations(operation_id,session_id,question_id,actor_id,prior_status,snapshot,reservation_result,expires_at)
    VALUES(p_operation_id,s.id,q.id,auth.uid(),q.status,snapshot,result,expiry);
  UPDATE public.version_questions SET status='regenerating',updated_at=clock_timestamp() WHERE id=q.id;
  UPDATE public.exam_sessions SET status='generated',updated_at=clock_timestamp() WHERE id=s.id;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.review_acquire_attempt(p_operation_id UUID, p_attempt_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations; a public.review_attempts; used INT; granted INT; allowed BOOLEAN;
BEGIN
  o := public._review_worker_operation(p_operation_id);
  IF p_attempt_id IS NULL THEN RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('review_attempt:'||p_attempt_id::text,0));
  SELECT * INTO a FROM public.review_attempts WHERE attempt_id=p_attempt_id;
  IF FOUND THEN
    IF a.operation_id<>o.operation_id THEN RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
    RETURN jsonb_build_object('operation_id',o.operation_id,'attempt_id',a.attempt_id,'dispatch_permitted',false,
      'calls_used',a.calls_used,'remaining_calls',a.remaining_calls,'replayed',true);
  END IF;
  PERFORM public._review_assert_operation(o.operation_id,true);
  SELECT gemini_review_calls INTO used FROM public.exam_sessions WHERE id=o.session_id;
  IF used NOT BETWEEN 0 AND 30 THEN RAISE EXCEPTION 'REVIEW_QUOTA_EXHAUSTED' USING ERRCODE='54000'; END IF;
  SELECT count(*) INTO granted FROM public.review_attempts WHERE operation_id=o.operation_id AND dispatch_permitted;
  allowed := used<30 AND granted<4;
  IF allowed THEN
    used := used+1;
    UPDATE public.exam_sessions SET gemini_review_calls=used,updated_at=clock_timestamp() WHERE id=o.session_id;
  END IF;
  INSERT INTO public.review_attempts(attempt_id,operation_id,dispatch_permitted,calls_used,remaining_calls)
    VALUES(p_attempt_id,o.operation_id,allowed,used,30-used);
  RETURN jsonb_build_object('operation_id',o.operation_id,'attempt_id',p_attempt_id,'dispatch_permitted',allowed,
    'calls_used',used,'remaining_calls',30-used,'replayed',false);
END $$;

CREATE OR REPLACE FUNCTION public.review_complete_regeneration(p_operation_id UUID, p_candidate JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations; q public.version_questions; new_id UUID; used INT;
  invalidated JSONB; progress JSONB; result JSONB; distinct_options INT;
BEGIN
  o := public._review_worker_operation(p_operation_id);
  IF o.status='completed' THEN
    IF o.completion_candidate IS DISTINCT FROM p_candidate THEN
      RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
    END IF;
    RETURN o.settlement_result || jsonb_build_object('replayed',true);
  END IF;
  PERFORM public._review_assert_operation(o.operation_id,true);
  IF p_candidate IS NULL OR jsonb_typeof(p_candidate) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_candidate->'stem_latex') IS DISTINCT FROM 'string'
    OR length(btrim(p_candidate->>'stem_latex')) NOT BETWEEN 1 AND 12000
    OR jsonb_typeof(p_candidate->'solution_md') IS DISTINCT FROM 'string' OR length(btrim(p_candidate->>'solution_md'))=0
    OR jsonb_typeof(p_candidate->'correct_key') IS DISTINCT FROM 'string' OR (p_candidate->>'correct_key') !~ '^[ABCD]$'
    OR jsonb_typeof(p_candidate->'options') IS DISTINCT FROM 'array'
    OR jsonb_typeof(p_candidate->'api_calls_count') IS DISTINCT FROM 'number' OR (p_candidate->>'api_calls_count') !~ '^[0-4]$'
    OR jsonb_typeof(p_candidate->'validation_report') IS DISTINCT FROM 'object'
    OR p_candidate->'validation_report'->'is_valid' IS DISTINCT FROM 'true'::jsonb
    OR jsonb_typeof(p_candidate->'validation_report'->'math_verified') IS DISTINCT FROM 'boolean'
    OR p_candidate->'validation_report'->'requires_teacher_review' IS DISTINCT FROM 'true'::jsonb
    OR jsonb_typeof(p_candidate->'validation_report'->'warnings') IS DISTINCT FROM 'array'
    OR jsonb_typeof(p_candidate->'validation_report'->'checks') IS DISTINCT FROM 'array'
    OR (p_candidate ? 'content' AND p_candidate->'content' IS DISTINCT FROM p_candidate->'stem_latex') THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(p_candidate->'options')<>4 OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_candidate->'options') x
    WHERE jsonb_typeof(x) <> 'string' OR length(btrim(x#>>'{}')) NOT BETWEEN 1 AND 4000
  ) THEN RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  SELECT count(DISTINCT lower(btrim(x))) INTO distinct_options FROM jsonb_array_elements_text(p_candidate->'options') x;
  SELECT count(*) INTO used FROM public.review_attempts WHERE operation_id=o.operation_id AND dispatch_permitted;
  IF distinct_options<>4 OR (p_candidate->>'api_calls_count')::int<>used THEN
    RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  SELECT * INTO STRICT q FROM public.version_questions WHERE id=o.question_id FOR UPDATE;
  UPDATE public.version_questions SET is_current=false,status='rejected',updated_at=clock_timestamp() WHERE id=q.id;
  INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,solution_md,
    canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status,is_current,
    regenerated_from_id,regeneration_id,validation_report,has_warning)
  VALUES(q.version_id,q.source_question_id,q.question_no,p_candidate->>'stem_latex',p_candidate->'options',
    p_candidate->>'correct_key',p_candidate->>'solution_md',q.canonical_question_no,p_candidate->'options',
    p_candidate->>'correct_key',p_candidate->>'solution_md','pending_review',true,q.id,o.operation_id,
    p_candidate->'validation_report',NOT (p_candidate->'validation_report'->>'math_verified')::boolean
      OR jsonb_array_length(p_candidate->'validation_report'->'warnings')>0) RETURNING id INTO new_id;
  INSERT INTO public.review_logs(version_question_id,session_id,user_id,action_type,reason,api_calls_used,regenerated_from_id)
    VALUES(new_id,o.session_id,o.actor_id,'REJECT','REGENERATED',used,q.id);
  invalidated := public._review_invalidate(o.session_id);
  UPDATE public.review_operations SET status='completed',completion_candidate=p_candidate WHERE operation_id=o.operation_id;
  progress := public._review_recalculate(o.session_id);
  result := jsonb_build_object('session_id',o.session_id,'session_status','generated','replayed',false,'operation_id',o.operation_id,
    'previous_question_id',q.id,'question_id',new_id,'api_calls_used',used,'invalidated_version_ids',invalidated,'progress',progress);
  UPDATE public.review_operations SET settlement_result=result WHERE operation_id=o.operation_id;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public._review_finish_failure(p_operation_id UUID, p_error_code TEXT, p_recovery BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE o public.review_operations; used INT; progress JSONB; result JSONB; session_status TEXT;
BEGIN
  o := public._review_worker_operation(p_operation_id);
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

CREATE OR REPLACE FUNCTION public.review_fail_regeneration(p_operation_id UUID, p_error_code TEXT)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
  SELECT public._review_finish_failure(p_operation_id,p_error_code,false)
$$;
CREATE OR REPLACE FUNCTION public.review_recover_regeneration(p_operation_id UUID)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
  SELECT public._review_finish_failure(p_operation_id,'STALE_RECOVERY',true)
$$;

-- Restart-safe recovery discovery: workers know the session, not necessarily the
-- reservation UUID. Keep ledger SELECT private and run discovery + settlement
-- under the same parent lock. Model A permits at most one active operation here.
CREATE OR REPLACE FUNCTION public.review_recover_session(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; op UUID; outcome JSONB; outcomes JSONB := '[]'::jsonb;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'REVIEW_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  SELECT operation_id INTO op FROM public.review_operations
    WHERE session_id=s.id AND status='active' AND expires_at<=clock_timestamp()
    FOR UPDATE;
  IF FOUND THEN
    outcome := public._review_finish_failure(op,'STALE_RECOVERY',true);
    IF outcome->'recovered'='true'::jsonb AND outcome->'replayed'='false'::jsonb THEN
      outcomes := jsonb_build_array(outcome);
    END IF;
  END IF;
  SELECT * INTO s FROM public.exam_sessions WHERE id=p_session_id;
  RETURN jsonb_build_object('session_id',s.id,'session_status',s.status,
    'recovered_count',jsonb_array_length(outcomes),'recoveries',outcomes);
END $$;

CREATE OR REPLACE FUNCTION public._review_apply_action(p_session_id UUID, p_question_id UUID, p_action_id UUID, p_revert BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.exam_sessions; q public.version_questions; root public.version_questions; receipt public.review_action_receipts;
  kind TEXT; invalidated JSONB := '[]'::jsonb; progress JSONB; result JSONB; changed BOOLEAN;
BEGIN
  s := public._review_lock_session(p_session_id,true);
  IF p_action_id IS NULL THEN RAISE EXCEPTION 'REVIEW_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('review_action:'||p_action_id::text,0));
  kind := CASE WHEN p_revert THEN 'REVERT' ELSE 'ACCEPT' END;
  SELECT * INTO receipt FROM public.review_action_receipts WHERE action_id=p_action_id;
  IF FOUND THEN
    IF receipt.session_id IS DISTINCT FROM s.id OR receipt.question_id IS DISTINCT FROM p_question_id
      OR receipt.actor_id IS DISTINCT FROM auth.uid() OR receipt.action_type IS DISTINCT FROM kind THEN
      RAISE EXCEPTION 'REVIEW_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
    END IF;
    RETURN receipt.result || jsonb_build_object('replayed',true);
  END IF;
  PERFORM public._review_assert_editable(s.id);
  SELECT q0.* INTO q FROM public.version_questions q0 JOIN public.exam_versions v ON v.id=q0.version_id
    WHERE q0.id=p_question_id AND v.session_id=s.id FOR UPDATE OF q0;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_NOT_FOUND' USING ERRCODE='P0002'; END IF;
  IF NOT q.is_current THEN RAISE EXCEPTION 'REVIEW_STALE' USING ERRCODE='55000'; END IF;
  IF q.status='regenerating' THEN RAISE EXCEPTION 'REVIEW_BUSY' USING ERRCODE='55000'; END IF;
  root := q;
  IF p_revert THEN
    WITH RECURSIVE lineage AS (
      SELECT id,regenerated_from_id,ARRAY[id] AS visited FROM public.version_questions WHERE id=q.id
      UNION ALL
      SELECT parent.id,parent.regenerated_from_id,l.visited||parent.id FROM lineage l
      JOIN public.version_questions parent ON parent.id=l.regenerated_from_id
      WHERE parent.version_id=q.version_id AND parent.source_question_id=q.source_question_id AND NOT parent.id=ANY(l.visited)
    ) SELECT vq.* INTO root FROM lineage l JOIN public.version_questions vq ON vq.id=l.id WHERE l.regenerated_from_id IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023'; END IF;
    PERFORM 1 FROM public.version_questions WHERE id=root.id FOR UPDATE;
  END IF;
  changed := root.id<>q.id OR q.status<>'approved' OR (p_revert AND NOT q.is_reverted);
  IF root.id<>q.id THEN
    UPDATE public.version_questions SET is_current=false,updated_at=clock_timestamp() WHERE id=q.id;
    UPDATE public.version_questions SET is_current=true,status='approved',is_reverted=true,
      question_no=q.question_no,updated_at=clock_timestamp() WHERE id=root.id;
    invalidated := public._review_invalidate(s.id);
  ELSE
    UPDATE public.version_questions SET status='approved',is_reverted=(is_reverted OR p_revert),updated_at=clock_timestamp()
      WHERE id=q.id AND changed;
  END IF;
  IF changed THEN
    INSERT INTO public.review_logs(version_question_id,session_id,user_id,action_type,reason,regenerated_from_id)
      VALUES(root.id,s.id,auth.uid(),kind::public.review_action_type,kind,
        CASE WHEN root.id<>q.id THEN q.id ELSE NULL END);
  END IF;
  progress := public._review_recalculate(s.id);
  SELECT * INTO s FROM public.exam_sessions WHERE id=s.id;
  result := jsonb_build_object('session_id',s.id,'session_status',s.status,'replayed',false,'previous_question_id',q.id,
    'question_id',root.id,'question_status','approved','invalidated_version_ids',invalidated,'progress',progress);
  INSERT INTO public.review_action_receipts(action_id,session_id,question_id,actor_id,action_type,result)
    VALUES(p_action_id,s.id,q.id,auth.uid(),kind,result);
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.review_accept_question(p_session_id UUID, p_question_id UUID, p_action_id UUID)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
  SELECT public._review_apply_action(p_session_id,p_question_id,p_action_id,false)
$$;
CREATE OR REPLACE FUNCTION public.review_revert_question(p_session_id UUID, p_question_id UUID, p_action_id UUID)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
  SELECT public._review_apply_action(p_session_id,p_question_id,p_action_id,true)
$$;

-- SECURITY DEFINER is needed for the private ledger and atomic cross-table writes.
-- Public helpers must never be directly executable by a client (including worker).
DO $$ DECLARE f RECORD;
BEGIN
  FOR f IN SELECT oid::regprocedure AS signature FROM pg_proc
    WHERE pronamespace='public'::regnamespace AND proname IN (
      '_review_lock_session','_review_assert_editable','_review_worker_operation','_review_assert_operation','_review_progress',
      '_review_recalculate','_review_invalidate','_review_finish_failure','_review_apply_action',
      'review_get_progress','review_reserve_regeneration','review_acquire_attempt','review_complete_regeneration',
      'review_fail_regeneration','review_recover_regeneration','review_recover_session','review_accept_question','review_revert_question')
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated, service_role',f.signature);
  END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION public.review_get_progress(UUID),public.review_reserve_regeneration(UUID,UUID,UUID),
  public.review_accept_question(UUID,UUID,UUID),public.review_revert_question(UUID,UUID,UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.review_acquire_attempt(UUID,UUID),public.review_complete_regeneration(UUID,JSONB),
  public.review_fail_regeneration(UUID,TEXT),public.review_recover_regeneration(UUID),
  public.review_recover_session(UUID) TO service_role;

-- TASK-301 producer extension, proposed for integration with TASK-302 authority.
-- No legacy confirmation or canonical document is fabricated/backfilled.
CREATE TABLE IF NOT EXISTS public.source_artifact_confirmations (
  confirmation_id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  actor_id UUID NOT NULL REFERENCES public.users(id),
  confirmed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  result JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS public.source_artifact_revisions (
  source_revision_id UUID PRIMARY KEY,
  confirmation_id UUID NOT NULL REFERENCES public.source_artifact_confirmations(confirmation_id) ON DELETE CASCADE,
  -- Historical identity survives removal/re-ingestion of a source row. Session
  -- deletion still cascades through its confirmation, not through live sources.
  source_question_id UUID NOT NULL,
  confirmed_input JSONB NOT NULL CHECK (jsonb_typeof(confirmed_input)='object'),
  source_fingerprint TEXT NOT NULL CHECK (source_fingerprint ~ '^[a-f0-9]{64}$'),
  UNIQUE(source_revision_id,source_question_id)
);
ALTER TABLE public.source_artifact_revisions
  DROP CONSTRAINT IF EXISTS source_artifact_revisions_source_question_id_fkey;
CREATE TABLE IF NOT EXISTS public.canonical_blueprint_revisions (
  blueprint_revision_id UUID PRIMARY KEY,
  source_revision_id UUID NOT NULL,
  source_question_id UUID NOT NULL,
  canonical_blueprint JSONB NOT NULL CHECK (jsonb_typeof(canonical_blueprint)='object'),
  schema_version TEXT NOT NULL CHECK (schema_version='0.4.0'),
  published_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY(source_revision_id,source_question_id)
    REFERENCES public.source_artifact_revisions(source_revision_id,source_question_id) ON DELETE CASCADE,
  UNIQUE(blueprint_revision_id,source_revision_id,source_question_id)
);
CREATE TABLE IF NOT EXISTS public.source_artifact_heads (
  source_question_id UUID PRIMARY KEY REFERENCES public.source_questions(id) ON DELETE CASCADE,
  source_revision_id UUID NOT NULL,
  blueprint_revision_id UUID,
  FOREIGN KEY(source_revision_id,source_question_id)
    REFERENCES public.source_artifact_revisions(source_revision_id,source_question_id),
  FOREIGN KEY(blueprint_revision_id,source_revision_id,source_question_id)
    REFERENCES public.canonical_blueprint_revisions(blueprint_revision_id,source_revision_id,source_question_id)
);
ALTER TABLE public.source_artifact_heads
  ADD COLUMN IF NOT EXISTS producer_job_id UUID,
  ADD COLUMN IF NOT EXISTS producer_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS producer_error_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_producer_job ON public.source_artifact_heads(producer_job_id)
  WHERE producer_job_id IS NOT NULL;
ALTER TABLE public.source_artifact_confirmations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_artifact_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.canonical_blueprint_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_artifact_heads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.source_artifact_confirmations,public.source_artifact_revisions,
  public.canonical_blueprint_revisions,public.source_artifact_heads
  FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public._artifact_source_input(p_row public.source_questions)
RETURNS JSONB LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public AS $$
  SELECT jsonb_build_object('id',p_row.id,'question_text',p_row.raw_content,
    'options',CASE WHEN jsonb_typeof(p_row.options)='object'
      THEN jsonb_build_array(p_row.options->'A',p_row.options->'B',p_row.options->'C',p_row.options->'D')
      ELSE p_row.options END,
    'correct_answer',p_row.correct_key,'solution',coalesce(p_row.solution_md,''))
$$;

CREATE OR REPLACE FUNCTION public.confirm_source_artifacts(
  p_session_id UUID,p_actor_id UUID,p_confirmation_id UUID,
  p_expected_updated_at TIMESTAMPTZ,p_sources JSONB
)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; saved public.source_artifact_confirmations;
  element JSONB; result JSONB; receipt JSONB; comparison JSONB; prior_comparison JSONB;
  revision UUID; source_id UUID; n INT; confirmed TIMESTAMPTZ;
BEGIN
  -- Only the backend worker can supply Python-computed hashes. Actor comes from
  -- the verified HTTP identity, never an actor/hash field in the public request.
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'ARTIFACT_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  IF p_actor_id IS NULL OR s.user_id IS DISTINCT FROM p_actor_id THEN
    RAISE EXCEPTION 'ARTIFACT_OWNER_MISMATCH' USING ERRCODE='42501';
  END IF;
  IF p_confirmation_id IS NULL OR jsonb_typeof(p_sources) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'ARTIFACT_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  n := jsonb_array_length(p_sources);
  IF n NOT BETWEEN 1 AND 20 OR n<>(SELECT count(DISTINCT value->>'source_question_id') FROM jsonb_array_elements(p_sources)) THEN
    RAISE EXCEPTION 'ARTIFACT_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  SELECT jsonb_object_agg(value->>'source_question_id',jsonb_build_object(
    'input',value->'confirmed_input','fingerprint',value->'source_fingerprint'))
    INTO comparison FROM jsonb_array_elements(p_sources);
  PERFORM pg_advisory_xact_lock(hashtextextended('source_confirmation:'||p_confirmation_id::text,0));
  SELECT * INTO saved FROM public.source_artifact_confirmations WHERE confirmation_id=p_confirmation_id;
  IF FOUND THEN
    SELECT jsonb_object_agg(value->>'source_question_id',jsonb_build_object(
      'input',value->'confirmed_input','fingerprint',value->'source_fingerprint'))
      INTO prior_comparison FROM jsonb_array_elements(saved.result->'sources');
    IF saved.session_id IS DISTINCT FROM s.id OR saved.actor_id IS DISTINCT FROM p_actor_id
      OR comparison IS DISTINCT FROM prior_comparison THEN
      RAISE EXCEPTION 'ARTIFACT_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
    END IF;
    RETURN saved.result || jsonb_build_object('replayed',true);
  END IF;
  IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'ARTIFACT_LOCKED' USING ERRCODE='55000';
  END IF;
  IF s.status<>'draft' OR p_expected_updated_at IS NULL
      OR s.updated_at IS DISTINCT FROM p_expected_updated_at THEN
    RAISE EXCEPTION 'ARTIFACT_STALE' USING ERRCODE='55000';
  END IF;
  IF n<>(SELECT count(*) FROM public.source_questions WHERE session_id=s.id) THEN
    RAISE EXCEPTION 'ARTIFACT_SOURCE_MISMATCH' USING ERRCODE='22023';
  END IF;
  -- Compare exact content under the parent-session lock before recording any
  -- revision. Python's fingerprint algorithm is not reimplemented in SQL.
  FOR element IN SELECT value FROM jsonb_array_elements(p_sources) LOOP
    source_id := (element->>'source_question_id')::uuid;
    revision := (element->>'source_revision_id')::uuid;
    IF revision IS NULL OR coalesce(element->>'source_fingerprint','') !~ '^[a-f0-9]{64}$'
      OR NOT EXISTS (SELECT 1 FROM public.source_questions q WHERE q.id=source_id
        AND q.session_id=s.id AND public._artifact_source_input(q)=element->'confirmed_input'
        AND NOT q.has_missing_answer) THEN
      RAISE EXCEPTION 'ARTIFACT_SOURCE_MISMATCH' USING ERRCODE='22023';
    END IF;
  END LOOP;
  -- Confirm SOURCE before canonical extraction. No legacy Blueprint prerequisite
  -- or fallback row is used as confirmation evidence. Retain ADR004 silent audit.
  IF EXISTS (SELECT 1 FROM public.source_questions WHERE session_id=s.id AND has_security_warning) THEN
    INSERT INTO public.security_events(session_id,user_id,event_type,severity,sanitized_detail)
      SELECT s.id,p_actor_id,'PROMPT_INJECTION_DETECTED','WARN',jsonb_build_object(
        'action','confirm_source','warning_questions_count',count(*),
        'flagged_questions',jsonb_agg(jsonb_build_object('id',q.id,'question_no',q.question_no)),
        'silent_audit',true,'adr_version','ADR-004')
      FROM public.source_questions q WHERE q.session_id=s.id AND q.has_security_warning;
  END IF;
  confirmed := clock_timestamp();
  UPDATE public.exam_sessions SET status='blueprinted',updated_at=confirmed WHERE id=s.id;
  receipt := jsonb_build_object('confirmation_id',p_confirmation_id,'session_id',s.id,
    'actor_id',p_actor_id,'confirmed_at',confirmed,'status','blueprinted','canonical_status','pending',
    'total_questions',n,'total_blueprints',0,'replayed',false,'sources',p_sources);
  INSERT INTO public.source_artifact_confirmations(confirmation_id,session_id,actor_id,confirmed_at,result)
    VALUES(p_confirmation_id,s.id,p_actor_id,confirmed,receipt);
  FOR element IN SELECT value FROM jsonb_array_elements(p_sources) LOOP
    source_id := (element->>'source_question_id')::uuid;
    revision := (element->>'source_revision_id')::uuid;
    INSERT INTO public.source_artifact_revisions(source_revision_id,confirmation_id,source_question_id,
      confirmed_input,source_fingerprint)
      VALUES(revision,p_confirmation_id,source_id,element->'confirmed_input',element->>'source_fingerprint');
    INSERT INTO public.source_artifact_heads(source_question_id,source_revision_id)
      VALUES(source_id,revision) ON CONFLICT(source_question_id) DO UPDATE
      SET source_revision_id=excluded.source_revision_id,blueprint_revision_id=NULL,
        producer_job_id=NULL,producer_expires_at=NULL,producer_error_code=NULL;
  END LOOP;
  RETURN receipt;
END $$;

CREATE OR REPLACE FUNCTION public.claim_source_production(p_session_id UUID,p_source_revision_id UUID,p_job_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; h public.source_artifact_heads; result JSONB;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'ARTIFACT_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  IF p_job_id IS NULL THEN RAISE EXCEPTION 'ARTIFACT_INVALID_PAYLOAD' USING ERRCODE='22023'; END IF;
  SELECT head.* INTO h FROM public.source_artifact_heads head
    JOIN public.source_artifact_revisions r ON r.source_revision_id=head.source_revision_id
    JOIN public.source_questions q ON q.id=head.source_question_id
    WHERE r.source_revision_id=p_source_revision_id AND q.session_id=s.id
      AND public._artifact_source_input(q)=r.confirmed_input;
  IF NOT FOUND THEN RAISE EXCEPTION 'ARTIFACT_STALE' USING ERRCODE='55000'; END IF;
  result := jsonb_build_object('session_id',s.id,'source_question_id',h.source_question_id,
    'source_revision_id',h.source_revision_id,'producer_job_id',p_job_id);
  IF h.blueprint_revision_id IS NOT NULL THEN
    RETURN result || jsonb_build_object('status','ready','expires_at',NULL);
  END IF;
  IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'ARTIFACT_LOCKED' USING ERRCODE='55000';
  END IF;
  IF h.producer_expires_at>clock_timestamp() THEN
    RETURN result || jsonb_build_object('status',CASE WHEN h.producer_job_id=p_job_id THEN 'claimed' ELSE 'busy' END,
      'expires_at',h.producer_expires_at);
  END IF;
  -- Extraction deadline is bounded to360s in the producer; this DB-clock lease
  -- leaves60s for transport/validation/publication. Review's180s is unrelated.
  UPDATE public.source_artifact_heads SET producer_job_id=p_job_id,
    producer_expires_at=clock_timestamp()+interval '420 seconds',producer_error_code=NULL
    WHERE source_question_id=h.source_question_id RETURNING * INTO h;
  RETURN result || jsonb_build_object('status','claimed','expires_at',h.producer_expires_at);
END $$;

CREATE OR REPLACE FUNCTION public.fail_source_production(p_session_id UUID,p_source_revision_id UUID,p_job_id UUID,p_error_code TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; changed INT;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'ARTIFACT_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  IF p_error_code IS NULL OR p_error_code !~ '^[A-Z][A-Z0-9_]{0,79}$' THEN
    RAISE EXCEPTION 'ARTIFACT_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  UPDATE public.source_artifact_heads h SET producer_error_code=p_error_code,producer_expires_at=NULL
    WHERE source_revision_id=p_source_revision_id AND producer_job_id=p_job_id
      AND blueprint_revision_id IS NULL AND s.status NOT IN ('approved','exported') AND s.approved_at IS NULL
      AND EXISTS (SELECT 1 FROM public.source_questions q WHERE q.id=h.source_question_id AND q.session_id=s.id);
  GET DIAGNOSTICS changed=ROW_COUNT;
  RETURN jsonb_build_object('settled',changed=1);
END $$;
REVOKE ALL ON FUNCTION public.claim_source_production(UUID,UUID,UUID),
  public.fail_source_production(UUID,UUID,UUID,TEXT) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.claim_source_production(UUID,UUID,UUID),
  public.fail_source_production(UUID,UUID,UUID,TEXT) TO service_role;

CREATE OR REPLACE FUNCTION public.publish_canonical_blueprint(p_session_id UUID,p_publication JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; source public.source_artifact_revisions;
  prior public.canonical_blueprint_revisions; bp UUID; source_id UUID; revision UUID; body JSONB;
BEGIN
  IF auth.role() IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'ARTIFACT_WORKER_REQUIRED' USING ERRCODE='42501';
  END IF;
  s := public._review_lock_session(p_session_id,false);
  bp := (p_publication->>'blueprint_revision_id')::uuid;
  source_id := (p_publication->>'source_question_id')::uuid;
  revision := (p_publication->>'source_revision_id')::uuid;
  body := p_publication->'canonical_blueprint';
  IF bp IS NULL OR source_id IS NULL OR revision IS NULL
    OR p_publication->>'schema_version' IS DISTINCT FROM '0.4.0'
    OR body->'requirement'->>'schema_version' IS DISTINCT FROM '0.4.0' THEN
    RAISE EXCEPTION 'ARTIFACT_INVALID_PAYLOAD' USING ERRCODE='22023';
  END IF;
  SELECT r.* INTO source FROM public.source_artifact_revisions r
    JOIN public.source_questions q ON q.id=r.source_question_id
    WHERE r.source_revision_id=revision AND r.source_question_id=source_id AND q.session_id=s.id;
  IF NOT FOUND OR source.source_fingerprint IS DISTINCT FROM p_publication->>'source_fingerprint' THEN
    RAISE EXCEPTION 'ARTIFACT_SOURCE_MISMATCH' USING ERRCODE='22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('canonical_blueprint:'||bp::text,0));
  SELECT * INTO prior FROM public.canonical_blueprint_revisions WHERE blueprint_revision_id=bp;
  IF FOUND THEN
    IF prior.source_revision_id IS DISTINCT FROM revision OR prior.canonical_blueprint IS DISTINCT FROM body THEN
      RAISE EXCEPTION 'ARTIFACT_IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';
    END IF;
    RETURN jsonb_build_object('session_id',s.id,'source_question_id',source_id,'source_revision_id',revision,
      'blueprint_revision_id',bp,'replayed',true);
  END IF;
  IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'ARTIFACT_LOCKED' USING ERRCODE='55000';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.source_artifact_heads h JOIN public.source_questions q ON q.id=h.source_question_id
    WHERE h.source_question_id=source_id AND h.source_revision_id=revision
      AND h.producer_job_id=(p_publication->>'producer_job_id')::uuid
      AND h.producer_expires_at>clock_timestamp()
      AND public._artifact_source_input(q)=source.confirmed_input) THEN
    RAISE EXCEPTION 'ARTIFACT_STALE' USING ERRCODE='55000';
  END IF;
  INSERT INTO public.canonical_blueprint_revisions(blueprint_revision_id,source_revision_id,source_question_id,
    canonical_blueprint,schema_version) VALUES(bp,revision,source_id,body,'0.4.0');
  UPDATE public.source_artifact_heads SET blueprint_revision_id=bp,producer_expires_at=NULL,producer_error_code=NULL
    WHERE source_question_id=source_id;
  RETURN jsonb_build_object('session_id',s.id,'source_question_id',source_id,'source_revision_id',revision,
    'blueprint_revision_id',bp,'replayed',false);
END $$;

-- Edits invalidate the binding while retaining revision history. Parent locking
-- serializes with reservation, permit, completion and publication. A parent
-- already removed by session cascade needs no lifecycle write/check.
CREATE OR REPLACE FUNCTION public._artifact_invalidate_source()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions;
BEGIN
  IF TG_OP='UPDATE' AND NEW.id=OLD.id AND NEW.session_id=OLD.session_id
    AND ROW(NEW.raw_content,NEW.options,NEW.correct_key,NEW.solution_md,NEW.question_no)
      IS NOT DISTINCT FROM ROW(OLD.raw_content,OLD.options,OLD.correct_key,OLD.solution_md,OLD.question_no) THEN
    RETURN NEW;
  END IF;
  IF TG_OP='UPDATE' AND (NEW.id<>OLD.id OR NEW.session_id<>OLD.session_id) THEN
    RAISE EXCEPTION 'ARTIFACT_SOURCE_MISMATCH' USING ERRCODE='22023';
  END IF;
  SELECT * INTO s FROM public.exam_sessions WHERE id=OLD.session_id FOR UPDATE;
  IF FOUND THEN
    IF s.status IN ('approved','exported') OR s.approved_at IS NOT NULL THEN
      RAISE EXCEPTION 'ARTIFACT_LOCKED' USING ERRCODE='55000';
    END IF;
    IF EXISTS (SELECT 1 FROM public.source_artifact_heads WHERE source_question_id=OLD.id) THEN
      DELETE FROM public.source_artifact_heads WHERE source_question_id=OLD.id;
      UPDATE public.question_blueprints SET confirmed_at=NULL WHERE source_question_id=OLD.id;
    END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_source_artifact_invalidation ON public.source_questions;
CREATE TRIGGER trg_source_artifact_invalidation BEFORE UPDATE OR DELETE ON public.source_questions
  FOR EACH ROW EXECUTE FUNCTION public._artifact_invalidate_source();
REVOKE ALL ON FUNCTION public._artifact_source_input(public.source_questions),public._artifact_invalidate_source()
  FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.confirm_source_artifacts(UUID,UUID,UUID,TIMESTAMPTZ,JSONB),
  public.publish_canonical_blueprint(UUID,JSONB) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.confirm_source_artifacts(UUID,UUID,UUID,TIMESTAMPTZ,JSONB),
  public.publish_canonical_blueprint(UUID,JSONB) TO service_role;

CREATE OR REPLACE FUNCTION public.get_source_artifacts(p_session_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.exam_sessions; c public.source_artifact_confirmations; pending JSONB; states JSONB;
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
  RETURN jsonb_build_object('confirmation',c.result,'pending_source_question_ids',pending,'production',states,
    'ready',jsonb_array_length(pending)=0);
END $$;
REVOKE ALL ON FUNCTION public.get_source_artifacts(UUID) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.get_source_artifacts(UUID) TO authenticated,service_role;

-- One canonical representation for the target and all peers. Display permutations
-- never travel with canonical keys/solutions. The caller already holds the parent
-- session lock, shared with source invalidation, publication and approval.
CREATE OR REPLACE FUNCTION public._review_canonical_variant(p_question_id UUID)
RETURNS JSONB LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT jsonb_build_object('id',q.id,'version_id',q.version_id,
    'source_question_id',q.source_question_id,'content',q.content,
    'options',q.canonical_options,'correct_key',q.canonical_correct_key,
    'solution_md',q.canonical_solution_md)
  FROM public.version_questions q WHERE q.id=p_question_id
$$;

CREATE OR REPLACE FUNCTION public._review_artifact_snapshot(p_question_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE q public.version_questions; src public.source_questions;
  r public.source_artifact_revisions; b public.canonical_blueprint_revisions;
  peers JSONB;
BEGIN
  SELECT * INTO STRICT q FROM public.version_questions WHERE id=p_question_id;
  SELECT s.* INTO src FROM public.source_questions s JOIN public.exam_versions v ON v.session_id=s.session_id
    WHERE s.id=q.source_question_id AND v.id=q.version_id AND s.question_no=q.canonical_question_no FOR SHARE OF s;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023'; END IF;
  SELECT rev.* INTO r FROM public.source_artifact_heads h
    JOIN public.source_artifact_revisions rev ON rev.source_revision_id=h.source_revision_id
    WHERE h.source_question_id=src.id FOR SHARE OF h,rev;
  IF NOT FOUND OR r.confirmed_input IS DISTINCT FROM public._artifact_source_input(src) THEN
    RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023';
  END IF;
  SELECT bp.* INTO b FROM public.source_artifact_heads h
    JOIN public.canonical_blueprint_revisions bp ON bp.blueprint_revision_id=h.blueprint_revision_id
      AND bp.source_revision_id=h.source_revision_id AND bp.source_question_id=h.source_question_id
    WHERE h.source_question_id=src.id FOR SHARE OF h,bp;
  IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023'; END IF;
  IF EXISTS (SELECT 1 FROM public.version_questions peer JOIN public.exam_versions v ON v.id=peer.version_id
    WHERE v.session_id=src.session_id AND peer.source_question_id=src.id AND peer.is_current
      AND (jsonb_typeof(peer.canonical_options) IS DISTINCT FROM 'array'
        OR jsonb_array_length(peer.canonical_options)<>4 OR peer.canonical_correct_key IS NULL OR peer.canonical_correct_key NOT IN ('A','B','C','D'))) THEN
    RAISE EXCEPTION 'REVIEW_SOURCE_MISMATCH' USING ERRCODE='22023';
  END IF;
  SELECT coalesce(jsonb_agg(public._review_canonical_variant(peer.id) ORDER BY peer.id),'[]'::jsonb) INTO peers
    FROM public.version_questions peer JOIN public.exam_versions v ON v.id=peer.version_id
    WHERE v.session_id=src.session_id AND peer.source_question_id=src.id AND peer.is_current AND peer.id<>q.id;
  RETURN jsonb_build_object('format','confirmed_artifacts_v1',
    'source_revision_id',r.source_revision_id,'blueprint_revision_id',b.blueprint_revision_id,
    'blueprint_source_revision_id',b.source_revision_id,'blueprint_source_fingerprint',r.source_fingerprint,
    'source_snapshot',r.confirmed_input||jsonb_build_object('content_hash',r.source_fingerprint),
    'blueprint',b.canonical_blueprint,'current_variant',public._review_canonical_variant(q.id),'peer_variants',peers);
END $$;
REVOKE ALL ON FUNCTION public._review_canonical_variant(UUID),public._review_artifact_snapshot(UUID)
  FROM PUBLIC,anon,authenticated,service_role;

COMMIT;
