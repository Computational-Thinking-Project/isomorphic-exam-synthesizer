-- TASK-103 session detail prerequisite; run ONCE as postgres in Supabase SQL Editor.
-- TV1 confirmed exam_versions absent on 26/10/2026 (PGRST205 + to_regclass=false).
-- Table columns match schema.sql. Only authenticated owner SELECT is enabled here.
-- Generation/write grants and remaining tables are outside this setup.
-- Existing objects are not replaced: a concurrent setup causes rollback.
BEGIN;

DO $$
BEGIN
  IF to_regclass('public.exam_sessions') IS NULL THEN
    RAISE EXCEPTION 'Missing public.exam_sessions: complete the Dashboard setup first.';
  END IF;
END;
$$;

CREATE TABLE public.exam_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES public.exam_sessions(id) ON DELETE CASCADE,
  version_code TEXT NOT NULL,
  shuffle_seed TEXT,
  permutations JSONB,
  is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.exam_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read exam versions in their sessions"
  ON public.exam_versions FOR SELECT TO authenticated
  USING (
    session_id IN (SELECT id FROM public.exam_sessions WHERE user_id = auth.uid())
  );

REVOKE ALL PRIVILEGES ON TABLE public.exam_versions FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.exam_versions TO authenticated;

NOTIFY pgrst, 'reload schema';
COMMIT;

-- Metadata only; real authenticated GET and cross-account checks are still needed.
SELECT
  c.relrowsecurity AS rls_enabled,
  has_table_privilege('authenticated', c.oid, 'SELECT') AS authenticated_can_select,
  NOT has_table_privilege('authenticated', c.oid, 'INSERT, UPDATE, DELETE') AS no_user_write_grant,
  NOT has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE') AS anon_has_no_access,
  EXISTS (
    SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid
      AND p.polname = 'Users can read exam versions in their sessions'
  ) AS ownership_policy_exists
FROM pg_class c
WHERE c.oid = to_regclass('public.exam_versions');
