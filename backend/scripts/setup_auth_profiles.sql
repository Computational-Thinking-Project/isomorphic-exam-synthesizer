-- Auth-only setup derived from backend/scripts/schema.sql.
-- Run once in the shared Supabase SQL Editor with the postgres role.
-- Preflight: public.users, public.handle_new_user() and custom auth.users
-- triggers are absent (TV1 checked 23/10/2026).
-- All changes below are in one transaction. Existing objects are not replaced.
-- Record this setup before applying the remaining sections of schema.sql:
-- that file also defines these objects and its policies are not rerunnable.

BEGIN;

-- 1. Application profile, using the same columns/FK as the team schema.
CREATE TABLE public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Preserve the team ownership policy. The current profile API needs SELECT.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own profile" ON public.users
  FOR ALL USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT ON TABLE public.users TO authenticated;

-- 3. New Google accounts automatically receive their application profile.
CREATE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.users (id, email, name)
  VALUES (
    new.id,
    new.email,
    COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email)
  )
  ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        name = EXCLUDED.name;
  RETURN new;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 4. Existing Google users predate the trigger. Copy their real Auth records.
-- The team schema requires an email; accounts without email are not copied.
INSERT INTO public.users (id, email, name, created_at)
SELECT
  id,
  email,
  COALESCE(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', email),
  COALESCE(created_at, now())
FROM auth.users
WHERE email IS NOT NULL
ON CONFLICT (id) DO NOTHING;

-- 5. Publish the new table metadata to the Data API after commit.
NOTIFY pgrst, 'reload schema';

COMMIT;

-- Verification returns metadata/count only, not account identities.
SELECT
  to_regclass('public.users') IS NOT NULL AS users_exists,
  to_regprocedure('public.handle_new_user()') IS NOT NULL AS sync_function_exists,
  EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'auth.users'::regclass
      AND tgname = 'on_auth_user_created'
      AND NOT tgisinternal
  ) AS sync_trigger_exists,
  (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.users'::regclass) AS rls_enabled,
  has_table_privilege('authenticated', 'public.users', 'SELECT') AS authenticated_can_select,
  (SELECT count(*) FROM public.users) AS profile_count;
