import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from test_export_snapshot_pg import OTHER, OWNER, auth
from test_stage3_schema import BOOTSTRAP, PostgresCase

SETTINGS_SCHEMA = Path(__file__).parent / "fixtures/ext04_exam_settings.sql"


class TestExt04ExamSettings(PostgresCase):
    def setUp(self):
        type(self).db = f"ext04_settings_{uuid4().hex}"
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP)
        self.sql(f"""
            GRANT USAGE ON SCHEMA auth TO authenticated;
            INSERT INTO auth.users (id) VALUES ('{OWNER}'), ('{OTHER}');
        """)
        self.sql(SETTINGS_SCHEMA.read_text(encoding="utf-8"))

    def patch(self, actor, fields):
        payload = json.dumps(fields).replace("'", "''")
        return json.loads(self.value(auth(actor) + f"SELECT public.patch_my_exam_settings('{payload}');"))

    def test_partial_patch_preserves_unset_and_clears_null(self):
        original = self.patch(OWNER, {"school": "School A", "grade": 12, "exam_date": "2028-02-29"})
        assert len(original) == 8
        assert self.patch(OWNER, {"grade": None, "academic_year": "2026-2027"}) == (
            original | {"grade": None, "academic_year": "2026-2027"}
        )

    def test_read_and_write_are_scoped_to_the_current_owner(self):
        self.patch(OWNER, {"school": "School A"})
        assert self.patch(OTHER, {"school": "School B"})["school"] == "School B"
        assert self.value(auth(OWNER) + "SELECT school FROM public.user_exam_settings;") == "School A"
        self.assert_sql_fails(
            auth(OTHER) + f"INSERT INTO public.user_exam_settings(user_id) VALUES ('{OWNER}');",
            "row-level security policy",
        )
        self.assert_sql_fails(
            auth(OWNER, "anon") + "SELECT public.patch_my_exam_settings('{}');",
            "permission denied for function",
        )

    def test_disjoint_patches_preserve_both_fields(self):
        self.patch(OWNER, {"school": "School A"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            grade = pool.submit(self.patch, OWNER, {"grade": 12})
            semester = pool.submit(self.patch, OWNER, {"semester": 1})
            grade.result()
            semester.result()
        assert self.value(auth(OWNER) + "SELECT grade, semester FROM public.user_exam_settings;") == "12|1"
