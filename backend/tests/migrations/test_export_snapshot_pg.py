"""W4-MVP-07 against disposable PostgreSQL 15, with the full migration chain.

Requires backend Python dependencies and RUN_POSTGRES_MIGRATION_TESTS=1.
SqlReadClient replaces HTTP transport only: every SELECT runs as authenticated
with real RLS on a separate connection, like separate PostgREST transactions.
The seed represents a historical reviewed exam (legacy confirmed blueprints),
not a test of the W2 producer. Shuffle and approval use the actual RPCs.
"""

import asyncio
import json
import re
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from test_stage3_schema import BOOTSTRAP, ROOT, PostgresCase

from app.models.schemas import ReviewDomainException
from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
from app.services.finalize.repository import FinalizeRepository
from app.services.finalize.shuffle_input import prepare_shuffle

OWNER = "00000000-0000-0000-0000-000000000011"
OTHER = "00000000-0000-0000-0000-000000000012"
FIXTURE = Path(__file__).parents[1] / "fixtures/export_preview_off_off.json"


def literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return "'" + str(value).replace("'", "''") + "'"


def auth(actor=OWNER, role="authenticated"):
    return (
        f"SET ROLE {role}; SET request.jwt.claim.role={literal(role)}; "
        f"SET request.jwt.claim.sub={literal(actor)}; "
    )


def identifier(value):
    assert re.fullmatch(r"[a-z_]+", value), value
    return value


class SqlQuery:
    def __init__(self, client, name):
        self.client, self.name = client, identifier(name)
        self.columns, self.filters, self.row_limit = "*", [], None

    def select(self, columns="*", **_):
        if columns != "*":
            self.columns = ",".join(identifier(c.strip()) for c in columns.split(","))
        return self

    def eq(self, field, value):
        self.filters.append(f"{identifier(field)}={literal(value)}")
        return self

    def in_(self, field, values):
        self.filters.append(f"{identifier(field)} IN ({','.join(literal(v) for v in values)})")
        return self

    def order(self, *_args, **_kwargs):
        # Consumers sort their output; the fixture intentionally inserts reversed versions.
        return self

    def limit(self, number):
        assert type(number) is int and number > 0
        self.row_limit = number
        return self

    def execute(self):
        self.client.calls.append(self.name)
        where = " AND ".join(self.filters) or "true"
        limit = f" LIMIT {self.row_limit}" if self.row_limit else ""
        result = self.client.case.value(
            auth(self.client.actor)
            + "SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') FROM "
            + f"(SELECT {self.columns} FROM public.{self.name} WHERE {where}{limit}) t;"
        )
        return SimpleNamespace(data=json.loads(result.splitlines()[-1]))


class SqlReadClient:
    def __init__(self, case, actor=OWNER):
        self.case, self.actor, self.calls = case, actor, []

    def table(self, name):
        return SqlQuery(self, name)


class ExportSnapshotPostgresFixture(PostgresCase):
    def setUp(self):
        type(self).db = "export_" + uuid4().hex
        self.run_docker("exec", self.container, "createdb", "-U", "postgres", self.db)
        self.sql(BOOTSTRAP + (ROOT / "backend/scripts/schema.sql").read_text(encoding="utf-8"))
        # Supabase supplies these base grants; migrations subsequently narrow them.
        self.sql("""
            GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
            GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated,service_role;
        """)
        for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
            self.sql(migration.read_text(encoding="utf-8"))
        self.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.sid = self.expected["session_id"]
        self.seed()
        self.shuffle()

    def seed(self):
        self.sql(f"""
            INSERT INTO auth.users(id,email) VALUES ('{OWNER}','owner@example.invalid'),
                ('{OTHER}','other@example.invalid');
            INSERT INTO public.users(id,email) VALUES ('{OWNER}','owner@example.invalid'),
                ('{OTHER}','other@example.invalid') ON CONFLICT DO NOTHING;
            INSERT INTO exam_sessions(id,user_id,title) VALUES ('{self.sid}','{OWNER}','Golden export');
            INSERT INTO generation_configs(session_id,n_versions,ordering_preferences)
                VALUES ('{self.sid}',2,'{{"shuffle_questions":false,"shuffle_options":false}}');
        """)
        for question in self.expected["versions"][0]["questions"]:
            source, number = question["source_question_id"], question["question_no"]
            self.sql(f"""
                INSERT INTO source_questions(id,session_id,question_no,raw_content,options,correct_key)
                    VALUES ('{source}','{self.sid}',{number},'source','["a","b","c","d"]','A');
                INSERT INTO question_blueprints(source_question_id,confirmed_at) VALUES ('{source}',now());
            """)
        for version in reversed(self.expected["versions"]):
            vid = version["id"]
            self.sql(
                f"INSERT INTO exam_versions(id,session_id,version_code) VALUES ('{vid}','{self.sid}',{literal(version['version_code'])});"
            )
            for q in version["questions"]:
                options, solution = literal(json.dumps(q["options"])), literal(q["solution_md"])
                self.sql(f"""
                    INSERT INTO version_questions(id,version_id,source_question_id,question_no,
                        content,options,correct_key,solution_md,canonical_question_no,
                        canonical_options,canonical_correct_key,canonical_solution_md,status)
                    VALUES ('{q["id"]}','{vid}','{q["source_question_id"]}',{q["question_no"]},
                        {literal(q["content"])},{options},{literal(q["correct_key"])},{solution},
                        {q["canonical_question_no"]},{options},{literal(q["correct_key"])},{solution},'approved');
                """)
        self.sql(f"UPDATE exam_sessions SET status='reviewed' WHERE id='{self.sid}';")

    def shuffle(self):
        client = SqlReadClient(self)
        selections = (
            ("generation_configs", "id,session_id,n_versions,ordering_preferences"),
            ("exam_versions", "id,session_id,version_code"),
            ("source_questions", "id,session_id,question_no"),
            (
                "version_questions",
                "id,version_id,source_question_id,content,canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status,is_current",
            ),
        )
        config, versions, sources, questions = [
            client.table(table).select(columns).execute().data for table, columns in selections
        ]
        snap = {
            "config": config[0],
            "versions": versions,
            "sources": sources,
            "questions": questions,
        }
        results = prepare_shuffle(self.sid, config[0], versions, sources, questions)
        data = {
            "actor_id": OWNER,
            "snapshot": snap,
            "versions": [v.model_dump(mode="json") for v in results],
        }
        self.shuffle_payload = data
        self.sql(
            auth(role="service_role")
            + f"SELECT finalize_persist_shuffle('{self.sid}',{literal(json.dumps(data))});"
        )

    def approve(self):
        return self.sql(auth() + f"SELECT finalize_approve_session('{self.sid}',NULL,NULL);")

    def load(self, actor=OWNER, supplied_actor=None):
        return asyncio.run(
            load_approved_export_snapshot(
                SqlReadClient(self, actor), self.sid, supplied_actor or actor
            )
        )


class ExportSnapshotPostgresTests(ExportSnapshotPostgresFixture):
    def test_approval_then_export_matches_all_six_preview_slots(self):
        with self.assertRaises(ReviewDomainException) as caught:
            self.load()
        self.assertEqual(caught.exception.error_code, "ERR_INVALID_SESSION_STATE")
        self.approve()
        snapshot = self.load()
        checked = 0
        for actual, expected in zip(snapshot.versions, self.expected["versions"], strict=True):
            self.assertEqual(actual.code, expected["version_code"])
            for question, preview in zip(actual.questions, expected["questions"], strict=True):
                # Compare every exported question field; no substitution/answer re-derivation.
                self.assertEqual(
                    question.model_dump(mode="json"),
                    {key: preview[key] for key in type(question).model_fields},
                )
                self.assertEqual(
                    question.correct_key, expected["answer_keys"][str(question.question_no)]
                )
                checked += 1
        self.assertEqual(checked, 6)
        self.assertEqual(self.load().revision, snapshot.revision)

    def test_real_rls_hides_session_and_every_content_table_from_foreign_owner(self):
        self.approve()
        client = SqlReadClient(self, OTHER)
        for table in (
            "exam_sessions",
            "generation_configs",
            "source_questions",
            "exam_versions",
            "version_questions",
            "answer_keys",
        ):
            self.assertEqual(client.table(table).select("*").execute().data, [], table)
        # Even a forged supplied actor cannot grant visibility under the peer JWT.
        with self.assertRaises(ReviewDomainException) as caught:
            self.load(OTHER, OWNER)
        self.assertEqual(
            (caught.exception.status_code, caught.exception.error_code),
            (404, "ERR_SESSION_NOT_FOUND"),
        )

    @unittest.skipUnless(
        hasattr(FinalizeRepository, "fetch_preview_snapshot"), "task05 preview is not merged"
    )
    def test_real_preview_projection_before_approval_equals_export_after_approval(self):
        preview = asyncio.run(
            FinalizeRepository(SqlReadClient(self)).fetch_preview_snapshot(self.sid)
        )
        self.approve()
        exported = self.load()
        for version, expected in zip(exported.versions, preview["versions"], strict=True):
            self.assertEqual(version.code, expected["version_code"])
            for question, projected in zip(version.questions, expected["questions"], strict=True):
                self.assertEqual(
                    question.model_dump(mode="json"),
                    {key: projected[key] for key in type(question).model_fields},
                )
                self.assertEqual(
                    question.correct_key,
                    preview["matrix"][question.question_no - 1]["answers"][version.code],
                )

    def test_uncommitted_approval_never_exposes_partial_snapshot(self):
        # Hold actual approval uncommitted on an independent connection; a table
        # reader must see the prior reviewed row and reject before reading content.
        process = subprocess.Popen(
            [
                self.docker,
                "exec",
                "-i",
                self.container,
                "psql",
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                self.db,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            process.stdin.write(
                "BEGIN; " + auth() + f"SELECT finalize_approve_session('{self.sid}',NULL,NULL);\n"
            )
            process.stdin.flush()
            receipt = json.loads(executor.submit(process.stdout.readline).result(timeout=10))
            self.assertEqual(receipt["status"], "approved")
            with self.assertRaises(ReviewDomainException) as caught:
                self.load()
            self.assertEqual(caught.exception.error_code, "ERR_INVALID_SESSION_STATE")
            process.stdin.write("COMMIT;\n")
            process.stdin.flush()
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(self.load().status, "approved")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
            executor.shutdown(wait=True, cancel_futures=True)

    def test_invalid_persisted_title_is_a_data_conflict(self):
        self.sql(f"UPDATE exam_sessions SET title='  ' WHERE id='{self.sid}';")
        self.approve()
        with self.assertRaises(ReviewDomainException) as caught:
            self.load()
        self.assertEqual(
            (caught.exception.status_code, caught.exception.error_code),
            (409, "ERR_EXPORT_SNAPSHOT_INVALID"),
        )

    def test_late_generation_workers_are_fenced_after_approval(self):
        self.approve()
        before = self.load()
        source = self.expected["versions"][0]["questions"][0]["source_question_id"]
        token = str(uuid4())
        cases = [
            (
                f"persist_version_question('{self.sid}','{token}',1,'{source}',1,'late','[\"a\",\"b\",\"c\",\"d\"]','A','late',false)",
                "not generating",
            ),
            (
                f"persist_generation_result('{self.sid}','{token}',1,'{source}',1,true,NULL,1,1,'late','{{}}','late','[\"a\",\"b\",\"c\",\"d\"]','A','late',false)",
                "Fencing token mismatch",
            ),
        ]
        for expression, expected in cases:
            result = self.sql(auth(role="service_role") + "SELECT " + expression + ";", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertEqual(self.load(), before)

    def test_locked_tables_and_rpc_writers_cannot_change_export_content(self):
        self.approve()
        before = self.load()
        qid = self.expected["versions"][0]["questions"][0]["id"]
        operations = [
            "UPDATE exam_sessions SET title='tampered'",
            "UPDATE exam_sessions SET status='reviewed',approved_at=NULL",
            "UPDATE generation_configs SET n_versions=1",
            "UPDATE source_questions SET raw_content='tampered'",
            "UPDATE question_blueprints SET confirmed_at=NULL",
            "UPDATE exam_versions SET is_finalized=false",
            "UPDATE version_questions SET content='tampered'",
            "DELETE FROM answer_keys",
            "DELETE FROM exam_sessions",
            f"SELECT review_accept_question('{self.sid}','{qid}','{uuid4()}')",
            f"SELECT review_revert_question('{self.sid}','{qid}','{uuid4()}')",
            f"SELECT review_reserve_regeneration('{self.sid}','{qid}','{uuid4()}')",
        ]
        for operation in operations:
            with self.subTest(operation=operation):
                result = self.sql(auth() + operation + ";", check=False)
                self.assertNotEqual(result.returncode, 0, operation)
                self.assertEqual(self.load(), before)
        result = self.sql(
            auth(role="service_role")
            + f"SELECT finalize_persist_shuffle('{self.sid}',{literal(json.dumps(self.shuffle_payload))});",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.load(), before)

    def test_concurrent_owner_reads_and_rejected_writes_preserve_snapshot(self):
        self.approve()
        before = self.load()
        barrier = Barrier(6)

        def operation(index):
            barrier.wait(timeout=10)
            if index % 2:
                result = self.sql(
                    auth() + "UPDATE version_questions SET content='race';", check=False
                )
                self.assertNotEqual(result.returncode, 0)
                return None
            return self.load()

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(operation, range(6)))
        self.assertEqual([r for r in results if r is not None], [before] * 3)
        self.assertEqual(self.load(), before)


class NonContiguousExportSnapshotPostgresTests(ExportSnapshotPostgresFixture):
    def seed(self):
        # Preserve original source labels before any shuffle/approval, without
        # bypassing canonical immutability or changing a guard/schema.
        labels = {1: 3, 2: 8, 3: 9}
        for version in self.expected["versions"]:
            for question in version["questions"]:
                question["question_no"] = labels[question["question_no"]]
                question["canonical_question_no"] = labels[question["canonical_question_no"]]
        super().seed()

    def test_f01_approved_gapped_source_labels_export_all_six_display_slots(self):
        self.approve()
        snapshot = self.load()
        self.assertEqual(snapshot.status, "approved")
        self.assertEqual(
            json.loads(
                self.value(
                    "SELECT json_agg(question_no ORDER BY question_no) FROM source_questions;"
                )
            ),
            [3, 8, 9],
        )
        for version, expected in zip(snapshot.versions, self.expected["versions"], strict=True):
            self.assertEqual([q.question_no for q in version.questions], [1, 2, 3])
            for display_no, (question, source) in enumerate(
                zip(version.questions, expected["questions"], strict=True), start=1
            ):
                projected = {key: source[key] for key in type(question).model_fields}
                projected["question_no"] = display_no
                self.assertEqual(question.model_dump(mode="json"), projected)

    def test_f01_wrong_canonical_answer_mapping_still_blocks_approval(self):
        self.sql("""
            UPDATE answer_keys SET canonical_question_no=CASE canonical_question_no
                WHEN 3 THEN 8 WHEN 8 THEN 3 ELSE canonical_question_no END;
        """)
        result = self.sql(
            auth() + f"SELECT finalize_approve_session('{self.sid}',NULL,NULL);", check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_INCONSISTENT_ANSWER_KEYS", result.stderr)
        self.assertEqual(self.value("SELECT status FROM exam_sessions;"), "reviewed")
