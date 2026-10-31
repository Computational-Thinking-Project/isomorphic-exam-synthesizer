-- TASK-302, phase A: schema foundation only; no lifecycle/quota RPCs.
-- Run with psql -v ON_ERROR_STOP=1. Any ambiguous legacy data rolls back the upgrade.
BEGIN;
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
-- ensure that a slot never loses its current row; they are not part of phase A.
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

COMMIT;
