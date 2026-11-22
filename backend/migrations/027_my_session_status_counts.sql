BEGIN;

CREATE FUNCTION public.get_my_session_status_counts()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
    SELECT coalesce(jsonb_agg(to_jsonb(counts)), '[]'::jsonb)
    FROM (
        SELECT s.status::text AS status, count(*) AS count
        FROM public.exam_sessions AS s
        WHERE s.user_id = (SELECT auth.uid())
        GROUP BY s.status
    ) AS counts;
$$;

REVOKE ALL ON FUNCTION public.get_my_session_status_counts()
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_my_session_status_counts() TO authenticated;

NOTIFY pgrst, 'reload schema';

COMMIT;
