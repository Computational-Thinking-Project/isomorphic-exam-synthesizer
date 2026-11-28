-- EXT-04 rehearsal. Promote after Q05; this file is outside the migration chain.
BEGIN;

DO $$ BEGIN
CREATE DOMAIN public.exam_bank_metadata AS jsonb
DEFAULT '{"school":null,"subject":null,"exam_type":null,"grade":null,"semester":null,"academic_year":null,"exam_date":null,"duration_minutes":null}'
CHECK (
    jsonb_typeof(VALUE) = 'object'
    AND VALUE ?& ARRAY['school','subject','exam_type','grade','semester',
                        'academic_year','exam_date','duration_minutes']
    AND VALUE - ARRAY['school','subject','exam_type','grade','semester',
                       'academic_year','exam_date','duration_minutes'] = '{}'::jsonb
);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ext04_exam_sessions_id_owner
    ON public.exam_sessions(id, user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ext04_exam_versions_id_session
    ON public.exam_versions(id, session_id);

CREATE TABLE IF NOT EXISTS public.exam_bank_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL,
    first_session_id uuid NOT NULL UNIQUE,
    display_name text NOT NULL CHECK (
        char_length(display_name) BETWEEN 1 AND 255 AND display_name = btrim(normalize(display_name))
    ),
    metadata public.exam_bank_metadata NOT NULL,
    tags text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_id),
    FOREIGN KEY (first_session_id, owner_id)
        REFERENCES public.exam_sessions(id, user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.exam_bank_rounds (
    session_id uuid PRIMARY KEY,
    bank_item_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    is_legacy boolean NOT NULL DEFAULT false,
    UNIQUE (session_id, bank_item_id),
    UNIQUE (session_id, bank_item_id, owner_id),
    FOREIGN KEY (session_id, owner_id)
        REFERENCES public.exam_sessions(id, user_id) ON DELETE CASCADE,
    FOREIGN KEY (bank_item_id, owner_id)
        REFERENCES public.exam_bank_items(id, owner_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.exam_bank_version_codes (
    version_id uuid PRIMARY KEY,
    session_id uuid NOT NULL,
    bank_item_id uuid NOT NULL,
    public_version_code text NOT NULL,
    UNIQUE (bank_item_id, public_version_code),
    FOREIGN KEY (version_id, session_id)
        REFERENCES public.exam_versions(id, session_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id, bank_item_id)
        REFERENCES public.exam_bank_rounds(session_id, bank_item_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.exam_bank_drafts (
    session_id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    metadata public.exam_bank_metadata NOT NULL,
    source_type text CHECK (source_type IN ('original', 'version')),
    source_bank_item_id uuid,
    source_session_id uuid,
    source_version_id uuid,
    save_action text CHECK (save_action IN ('append_existing', 'create_new')),
    new_display_name text CHECK (
        char_length(new_display_name) BETWEEN 1 AND 255
        AND new_display_name = btrim(normalize(new_display_name))
    ),
    new_tags text[] NOT NULL DEFAULT '{}',
    CHECK (
        (source_type IS NULL AND source_bank_item_id IS NULL
            AND source_session_id IS NULL AND source_version_id IS NULL)
        OR (source_type IS NOT NULL AND source_bank_item_id IS NOT NULL
            AND source_session_id IS NOT NULL AND source_session_id <> session_id
            AND (source_version_id IS NOT NULL) = (source_type = 'version'))
    ),
    CHECK (save_action IS DISTINCT FROM 'append_existing' OR source_bank_item_id IS NOT NULL),
    FOREIGN KEY (session_id, owner_id)
        REFERENCES public.exam_sessions(id, user_id) ON DELETE CASCADE,
    FOREIGN KEY (source_session_id, source_bank_item_id, owner_id)
        REFERENCES public.exam_bank_rounds(session_id, bank_item_id, owner_id),
    FOREIGN KEY (source_version_id, source_session_id)
        REFERENCES public.exam_versions(id, session_id)
);

ALTER TABLE public.exam_bank_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_bank_rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_bank_version_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_bank_drafts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS exam_bank_items_owner ON public.exam_bank_items;
DROP POLICY IF EXISTS exam_bank_rounds_owner ON public.exam_bank_rounds;
DROP POLICY IF EXISTS exam_bank_version_codes_owner ON public.exam_bank_version_codes;
DROP POLICY IF EXISTS exam_bank_drafts_owner ON public.exam_bank_drafts;
CREATE POLICY exam_bank_items_owner ON public.exam_bank_items
    FOR SELECT TO authenticated USING (owner_id = (SELECT auth.uid()));
CREATE POLICY exam_bank_rounds_owner ON public.exam_bank_rounds
    FOR SELECT TO authenticated USING (owner_id = (SELECT auth.uid()));
CREATE POLICY exam_bank_version_codes_owner ON public.exam_bank_version_codes
    FOR SELECT TO authenticated USING (EXISTS (
        SELECT 1 FROM public.exam_bank_rounds r
        WHERE r.session_id = exam_bank_version_codes.session_id AND r.owner_id = (SELECT auth.uid())
    ));
CREATE POLICY exam_bank_drafts_owner ON public.exam_bank_drafts
    FOR SELECT TO authenticated USING (owner_id = (SELECT auth.uid()));
REVOKE ALL ON TABLE public.exam_bank_items, public.exam_bank_rounds,
    public.exam_bank_version_codes, public.exam_bank_drafts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.exam_bank_items, public.exam_bank_rounds,
    public.exam_bank_version_codes, public.exam_bank_drafts TO authenticated;

CREATE OR REPLACE FUNCTION public._bank_capacity_check(p_session_id uuid, p_n_versions int)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_owner uuid := auth.uid();
    v_target uuid;
    v_used int;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.exam_sessions s WHERE s.id = p_session_id AND s.user_id = v_owner
    ) THEN
        RAISE EXCEPTION 'ERR_SESSION_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF p_n_versions IS NULL OR p_n_versions NOT BETWEEN 1 AND 4 THEN
        RAISE EXCEPTION 'ERR_CONFIG_CONFLICT' USING ERRCODE = '22023';
    END IF;

    SELECT b.id INTO v_target
    FROM public.exam_bank_drafts d
    JOIN public.exam_bank_items b ON b.id = d.source_bank_item_id AND b.owner_id = d.owner_id
    WHERE d.session_id = p_session_id AND d.owner_id = v_owner
        AND d.save_action IS DISTINCT FROM 'create_new'
        AND d.metadata = b.metadata;
    IF NOT FOUND THEN RETURN; END IF;

    SELECT count(*) INTO v_used FROM public.exam_bank_version_codes
    WHERE bank_item_id = v_target AND public_version_code COLLATE "C" ~ '^[0-9]{3}$'
        AND public_version_code COLLATE "C" BETWEEN '101' AND '999';

    IF 899 - v_used < p_n_versions THEN
        RAISE EXCEPTION 'ERR_BANK_CAPACITY_EXCEEDED' USING ERRCODE = '55006';
    END IF;
END;
$$;
REVOKE ALL ON FUNCTION public._bank_capacity_check(uuid, int) FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public._backfill_legacy_exam_bank()
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    INSERT INTO public.exam_bank_items (owner_id, first_session_id, display_name, created_at)
    SELECT s.user_id, s.id, coalesce(nullif(btrim(left(btrim(normalize(s.title)), 255)), ''), 'Phiên đề'), s.created_at
    FROM public.exam_sessions s
    WHERE s.status IN ('approved', 'exported')
        AND NOT EXISTS (SELECT 1 FROM public.exam_bank_rounds r WHERE r.session_id = s.id)
    ON CONFLICT (first_session_id) DO NOTHING;

    INSERT INTO public.exam_bank_rounds (session_id, bank_item_id, owner_id, is_legacy)
    SELECT b.first_session_id, b.id, b.owner_id, true
    FROM public.exam_bank_items b
    JOIN public.exam_sessions s ON s.id = b.first_session_id
    WHERE s.status IN ('approved', 'exported')
    ON CONFLICT (session_id) DO NOTHING;

    INSERT INTO public.exam_bank_version_codes (version_id, session_id, bank_item_id, public_version_code)
    SELECT v.id, r.session_id, r.bank_item_id, v.version_code
    FROM public.exam_bank_rounds r JOIN public.exam_versions v ON v.session_id = r.session_id
    WHERE r.is_legacy
    ON CONFLICT (version_id) DO NOTHING;
END;
$$;
REVOKE ALL ON FUNCTION public._backfill_legacy_exam_bank() FROM PUBLIC, anon, authenticated, service_role;

SELECT public._backfill_legacy_exam_bank();

COMMIT;
