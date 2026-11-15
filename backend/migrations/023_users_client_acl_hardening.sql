-- Issue #75: remove unsafe client privileges without changing Auth/RLS.
-- Run only as part of the reviewed manifest after DB-owner GO.
BEGIN;
REVOKE TRUNCATE, TRIGGER, REFERENCES ON TABLE public.users FROM anon, authenticated;

DO $$
DECLARE
  client_role text;
  forbidden text;
BEGIN
  IF current_setting('server_version_num')::integer >= 170000 THEN
    EXECUTE 'REVOKE MAINTAIN ON TABLE public.users FROM anon, authenticated';
  END IF;
  FOREACH client_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    FOREACH forbidden IN ARRAY ARRAY['TRUNCATE', 'TRIGGER', 'REFERENCES'] LOOP
      IF has_table_privilege(client_role, 'public.users', forbidden) THEN
        RAISE EXCEPTION '023: % retains effective % on public.users; review PUBLIC/inherited grants',
          client_role, forbidden;
      END IF;
    END LOOP;
    IF has_any_column_privilege(client_role, 'public.users', 'REFERENCES') THEN
      RAISE EXCEPTION '023: % retains column REFERENCES on public.users; review column grants', client_role;
    END IF;
    IF current_setting('server_version_num')::integer >= 170000 THEN
      IF has_table_privilege(client_role, 'public.users', 'MAINTAIN') THEN
        RAISE EXCEPTION '023: % retains effective MAINTAIN on public.users; review inherited grants', client_role;
      END IF;
    END IF;
  END LOOP;
  IF NOT has_table_privilege('authenticated', 'public.users', 'SELECT') THEN
    RAISE EXCEPTION '023: required authenticated SELECT on public.users is missing';
  END IF;
END $$;
COMMIT;
