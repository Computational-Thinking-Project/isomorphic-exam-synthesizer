-- TASK-103 list/clone setup, derived from backend/scripts/schema.sql.
-- Run ONCE as postgres in the existing shared Supabase project's SQL Editor.
-- Preflight reported by TV1 on 24/10/2026: users exists; exam_sessions,
-- source_questions, question_blueprints and session_status are absent.
-- Existing objects are not replaced: a concurrent setup causes a rollback.
-- Does not recreate users, Auth functions/triggers/policies or storage.
-- question_status is not needed by these three tables; leave it for the
-- version-question migration. Session detail also needs exam_versions later.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.users') IS NULL THEN
    RAISE EXCEPTION 'Missing public.users: finish the existing Auth setup first.';
  END IF;
END;
$$;

CREATE TYPE public.session_status AS ENUM (
  'draft',
  'blueprinted',
  'configured',
  'generating',
  'partial_generated',
  'generated',
  'reviewed',
  'approved',
  'exported',
  'failed'
);

CREATE TABLE public.exam_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT 'Toán',
  grade INT NOT NULL DEFAULT 12,
  status public.session_status NOT NULL DEFAULT 'draft',
  gemini_call_count INT NOT NULL DEFAULT 0,
  retry_count INT NOT NULL DEFAULT 0,
  gemini_review_calls INT NOT NULL DEFAULT 0,
  approved_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.source_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  question_no INT NOT NULL,
  raw_content TEXT NOT NULL,
  options JSONB NOT NULL,
  correct_key TEXT NOT NULL,
  solution_md TEXT,
  has_missing_answer BOOLEAN NOT NULL DEFAULT FALSE,
  has_security_warning BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.question_blueprints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_question_id UUID NOT NULL REFERENCES public.source_questions(id) ON DELETE CASCADE,
  variables JSONB NOT NULL DEFAULT '{}'::jsonb,
  domains JSONB NOT NULL DEFAULT '{}'::jsonb,
  invariants JSONB NOT NULL DEFAULT '[]'::jsonb,
  variation_modes JSONB NOT NULL DEFAULT '[]'::jsonb,
  rule_summary TEXT,
  confirmed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.exam_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.question_blueprints ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own exam sessions" ON public.exam_sessions
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can manage source questions in their sessions" ON public.source_questions
  FOR ALL USING (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  ) WITH CHECK (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  );

CREATE POLICY "Users can manage blueprints in their questions" ON public.question_blueprints
  FOR ALL USING (
    source_question_id IN (
      SELECT sq.id FROM public.source_questions sq
      JOIN public.exam_sessions s ON sq.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  ) WITH CHECK (
    source_question_id IN (
      SELECT sq.id FROM public.source_questions sq
      JOIN public.exam_sessions s ON sq.session_id = s.id
      WHERE s.user_id = auth.uid()
    )
  );

-- Set explicit privileges on these NEW tables, independent of default grants.
-- RLS still limits every authenticated query/insert to the user's ownership.
REVOKE ALL ON TABLE
  public.exam_sessions, public.source_questions, public.question_blueprints
  FROM PUBLIC, anon, authenticated;

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON TYPE public.session_status TO authenticated;
GRANT SELECT, INSERT, DELETE ON TABLE public.exam_sessions TO authenticated;
GRANT SELECT, INSERT ON TABLE
  public.source_questions, public.question_blueprints TO authenticated;
-- DELETE on the parent permits backend clone-error cleanup; FK cascades clean
-- child rows. UPDATE and other CRUD permissions are not added by this setup.

NOTIFY pgrst, 'reload schema';

COMMIT;

-- Metadata only: these checks do not prove API success or account isolation.
WITH expected(table_name, policy_name) AS (
  VALUES
    ('exam_sessions', 'Users can manage own exam sessions'),
    ('source_questions', 'Users can manage source questions in their sessions'),
    ('question_blueprints', 'Users can manage blueprints in their questions')
)
SELECT
  e.table_name,
  c.oid IS NOT NULL AS table_exists,
  COALESCE(c.relrowsecurity, FALSE) AS rls_enabled,
  EXISTS (
    SELECT 1 FROM pg_policy p
    WHERE p.polrelid = c.oid AND p.polname = e.policy_name
  ) AS ownership_policy_exists,
  has_table_privilege('authenticated', c.oid, 'SELECT') AS authenticated_can_select,
  has_table_privilege('authenticated', c.oid, 'INSERT') AS authenticated_can_insert,
  CASE WHEN e.table_name = 'exam_sessions'
    THEN has_table_privilege('authenticated', c.oid, 'DELETE')
    ELSE TRUE
  END AS clone_cleanup_grant_ok,
  NOT has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE') AS anon_has_no_access
FROM expected e
LEFT JOIN pg_class c ON c.oid = to_regclass('public.' || e.table_name)
ORDER BY e.table_name;
