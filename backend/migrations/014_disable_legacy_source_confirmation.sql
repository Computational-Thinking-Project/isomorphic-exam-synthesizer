BEGIN;

-- Revoke every installed legacy signature, including the pre-003 overload
-- on older upgrades. Default-argument calls share the same function ACL.
DO $$
DECLARE legacy_signature text;
BEGIN
  FOR legacy_signature IN
    SELECT pg_get_function_identity_arguments(p.oid)
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'confirm_exam_source' AND p.prokind = 'f'
  LOOP
    EXECUTE format(
      'REVOKE EXECUTE ON FUNCTION public.confirm_exam_source(%s) FROM PUBLIC, anon, authenticated, service_role',
      legacy_signature
    );
  END LOOP;
END $$;

COMMIT;
