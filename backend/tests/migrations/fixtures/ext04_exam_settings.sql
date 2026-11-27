-- EXT-04 Settings rehearsal. Promote to the ordered migration chain after Q05.
BEGIN;

CREATE TABLE public.user_exam_settings (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    school text CHECK (school = btrim(normalize(school)) AND school <> ''),
    subject text CHECK (subject = btrim(normalize(subject)) AND subject <> ''),
    exam_type text CHECK (exam_type = btrim(normalize(exam_type)) AND exam_type <> ''),
    grade smallint CHECK (grade BETWEEN 1 AND 12),
    semester smallint CHECK (semester IN (1, 2)),
    academic_year text CHECK (
        CASE WHEN academic_year ~ '^[0-9]{4}-[0-9]{4}$' THEN
            left(academic_year, 4)::int > 0
            AND right(academic_year, 4)::int = left(academic_year, 4)::int + 1
        ELSE academic_year IS NULL END
    ),
    exam_date date CHECK (exam_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'),
    duration_minutes numeric CHECK (duration_minutes > 0 AND scale(duration_minutes) = 0)
);

ALTER TABLE public.user_exam_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY exam_settings_owner ON public.user_exam_settings
    FOR ALL TO authenticated USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));
REVOKE ALL ON TABLE public.user_exam_settings FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.user_exam_settings TO authenticated;

CREATE FUNCTION public.patch_my_exam_settings(p_patch jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    v_owner uuid := auth.uid();
    v_result jsonb;
BEGIN
    IF v_owner IS NULL THEN
        RAISE EXCEPTION 'EXAM_SETTINGS_AUTH_REQUIRED' USING ERRCODE = '42501';
    END IF;
    IF jsonb_typeof(p_patch) IS DISTINCT FROM 'object'
       OR p_patch - ARRAY['school','subject','exam_type','grade','semester',
                           'academic_year','exam_date','duration_minutes'] <> '{}'::jsonb THEN
        RAISE EXCEPTION 'EXAM_SETTINGS_INVALID_PATCH' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_each(p_patch) AS field(key, value)
        WHERE jsonb_typeof(field.value) NOT IN (
            'null', CASE WHEN field.key IN ('grade', 'semester', 'duration_minutes')
                         THEN 'number' ELSE 'string' END
        )
    ) THEN
        RAISE EXCEPTION 'EXAM_SETTINGS_INVALID_PATCH' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.user_exam_settings AS settings (
        user_id, school, subject, exam_type, grade, semester, academic_year, exam_date, duration_minutes
    )
    SELECT v_owner, p.school, p.subject, p.exam_type, p.grade, p.semester,
        p.academic_year, p.exam_date, p.duration_minutes
    FROM jsonb_populate_record(NULL::public.user_exam_settings, p_patch) AS p
    ON CONFLICT (user_id) DO UPDATE SET
        school = CASE WHEN p_patch ? 'school' THEN excluded.school ELSE settings.school END,
        subject = CASE WHEN p_patch ? 'subject' THEN excluded.subject ELSE settings.subject END,
        exam_type = CASE WHEN p_patch ? 'exam_type' THEN excluded.exam_type ELSE settings.exam_type END,
        grade = CASE WHEN p_patch ? 'grade' THEN excluded.grade ELSE settings.grade END,
        semester = CASE WHEN p_patch ? 'semester' THEN excluded.semester ELSE settings.semester END,
        academic_year = CASE WHEN p_patch ? 'academic_year' THEN excluded.academic_year ELSE settings.academic_year END,
        exam_date = CASE WHEN p_patch ? 'exam_date' THEN excluded.exam_date ELSE settings.exam_date END,
        duration_minutes = CASE WHEN p_patch ? 'duration_minutes' THEN excluded.duration_minutes ELSE settings.duration_minutes END
    RETURNING to_jsonb(settings) - 'user_id' INTO v_result;

    RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION public.patch_my_exam_settings(jsonb) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.patch_my_exam_settings(jsonb) TO authenticated;

COMMIT;
