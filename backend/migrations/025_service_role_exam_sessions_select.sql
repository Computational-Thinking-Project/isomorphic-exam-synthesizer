-- Migration 025: Grant SELECT on public.exam_sessions to service_role (PR #78)
-- Fixes PostgreSQL SQLSTATE 42501 when backend reads session ownership and terminal generation state

BEGIN;

GRANT SELECT ON TABLE public.exam_sessions TO service_role;

DO $$
BEGIN
  IF NOT has_table_privilege('service_role', 'public.exam_sessions', 'SELECT') THEN
    RAISE EXCEPTION '025: required service_role SELECT on public.exam_sessions is missing';
  END IF;
END $$;

COMMIT;
