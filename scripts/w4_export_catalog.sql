-- Read-only OPS observation, NOT deployment approval or an applied migration ledger.
-- Run with an operator role able to read pg_catalog and storage.buckets.
-- Empty arrays mean missing dependencies; permission errors are not PASS.
SELECT
 to_regclass('public.private_export_ledger') IS NOT NULL AS export_ledger_exists,
 to_regclass('supabase_migrations.schema_migrations') IS NOT NULL AS standard_migration_history_exists,
 COALESCE((SELECT jsonb_agg(jsonb_build_object(
 'signature',p.oid::regprocedure::text,
 'security_definer',p.prosecdef,
 'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),
 'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
 'service_role_execute',has_function_privilege('service_role',p.oid,'EXECUTE')))
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='private_export_ledger_command'),'[]'::jsonb) AS export_rpc,
 COALESCE((SELECT jsonb_agg(jsonb_build_object('id',id,'public',public,'file_size_limit',file_size_limit,'allowed_mime_types',allowed_mime_types))
 FROM storage.buckets WHERE id='exam-export-bundles'),'[]'::jsonb) AS export_bucket;
