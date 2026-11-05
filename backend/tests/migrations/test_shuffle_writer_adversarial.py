"""Real SQL authority tests; run only in the provisioned disposable writer DB.

No mocks implement transactions. Each case seeds its own 2 x 3 session and
compares complete rows (including history, timestamps and key identities).
"""

import asyncio
import json
import os
from copy import deepcopy
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.services.finalize.shuffle_input import prepare_shuffle
from app.services.shuffler.service import sync_solution_text

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.asyncio
OWNER = "00000000-0000-0000-0000-000000000001"


async def state(conn):
    # Include the other session too: catches accidental unscoped writes.
    result = {}
    for table in (
        "exam_sessions",
        "generation_configs",
        "exam_versions",
        "source_questions",
        "version_questions",
        "answer_keys",
        "review_logs",
        "review_operations",
    ):
        result[table] = await conn.fetchval(
            f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]')::text FROM public.{table} t"
        )
    return result


async def snapshot(conn, session):
    async def rows(table, columns, where="session_id=$1::uuid"):
        return json.loads(
            await conn.fetchval(
                f"SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]')::text FROM (SELECT {columns} FROM public.{table} WHERE {where}) t",
                session,
            )
        )

    return {
        "config": (
            await rows("generation_configs", "id,session_id,n_versions,ordering_preferences")
        )[0],
        "versions": await rows("exam_versions", "id,session_id,version_code"),
        "sources": await rows("source_questions", "id,session_id,question_no"),
        "questions": await rows(
            "version_questions",
            "id,version_id,source_question_id,content,canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status,is_current",
            "is_current AND version_id IN (SELECT id FROM public.exam_versions WHERE session_id=$1::uuid)",
        ),
    }


def payload(sid, snap):
    results = prepare_shuffle(
        sid, snap["config"], snap["versions"], snap["sources"], snap["questions"]
    )
    return {"snapshot": snap, "versions": [r.model_dump(mode="json") for r in results]}


async def persist(conn, sid, data):
    return json.loads(
        await conn.fetchval(
            "SELECT public.finalize_persist_shuffle($1::uuid,$2::jsonb)", sid, json.dumps(data)
        )
    )


@pytest.fixture
async def db():
    if os.environ.get("RUN_TASK305_WRITER_DB_TEST") != "1":
        pytest.skip("explicit disposable PostgreSQL opt-in required")
    dsn = os.environ["TASK305_WRITER_TEST_DSN"]
    parsed = urlparse(dsn)
    assert parsed.hostname == "127.0.0.1" and parsed.path == "/task305_isolated"
    admin, owner, peer = [await asyncpg.connect(dsn) for _ in range(3)]
    assert await admin.fetchval("SELECT current_database()") == "task305_isolated"
    sid = str(uuid4())
    try:
        await admin.execute(
            "INSERT INTO public.exam_sessions(id,user_id,title) VALUES($1::uuid,$2::uuid,'adversarial')",
            sid,
            OWNER,
        )
        await admin.execute(
            'INSERT INTO public.generation_configs(session_id,n_versions,ordering_preferences) VALUES($1::uuid,2,\'{"shuffle_questions":true,"shuffle_options":true}\')',
            sid,
        )
        sources = [str(uuid4()) for _ in range(3)]
        for i, source in enumerate(sources, 1):
            await admin.execute(
                "INSERT INTO public.source_questions(id,session_id,question_no,raw_content,options,correct_key) VALUES($1::uuid,$2::uuid,$3,'source','[]','C')",
                source,
                sid,
                i,
            )
            await admin.execute(
                "INSERT INTO public.question_blueprints(source_question_id,confirmed_at) VALUES($1::uuid,now())",
                source,
            )
        for code in ("102", "101"):
            vid = str(uuid4())
            await admin.execute(
                "INSERT INTO public.exam_versions(id,session_id,version_code) VALUES($1::uuid,$2::uuid,$3)",
                vid,
                sid,
                code,
            )
            for i, source in enumerate(sources, 1):
                # Repeated option VALUES still have distinct index identities.
                await admin.execute(
                    'INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status) VALUES($1::uuid,$2::uuid,$3,$4,\'["same","same","c","d"]\',\'C\',$3,\'["same","same","c","d"]\',\'C\',$5,\'approved\')',
                    vid,
                    source,
                    i,
                    "stem " + code,
                    "Đáp án C: đúng. Vậy: C + A = 5",
                )
            await admin.execute(
                'INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,canonical_question_no,canonical_options,canonical_correct_key,status,is_current) VALUES($1::uuid,$2::uuid,1,\'history\',\'["a","b","c","d"]\',\'D\',1,\'["a","b","c","d"]\',\'D\',\'rejected\',false)',
                vid,
                sources[0],
            )
        await admin.execute(
            "UPDATE public.exam_sessions SET status='reviewed' WHERE id=$1::uuid", sid
        )
        for conn in (owner, peer):
            await conn.execute("SET ROLE authenticated")
            await conn.execute("SELECT set_config('request.jwt.claim.sub',$1,false)", OWNER)
            await conn.execute("SET lock_timeout='4s'; SET statement_timeout='8s'")
        snap = await snapshot(admin, sid)
        yield admin, owner, peer, sid, payload(sid, snap)
    finally:
        for conn in (owner, peer):
            if conn.is_in_transaction():
                await conn.execute("ROLLBACK")
        await admin.execute("DELETE FROM public.exam_sessions WHERE id=$1::uuid", sid)
        await asyncio.gather(admin.close(), owner.close(), peer.close())


@pytest.mark.parametrize(
    "case",
    [
        "null",
        "scalar",
        "array",
        "snapshot",
        "sources_shape",
        "versions_shape",
        "questions_shape",
        "uuid",
        "overflow",
        "bool_count",
        "string_count",
        "string_display",
        "fraction_display",
        "missing_version",
        "duplicate_version",
        "foreign_version",
        "wrong_code",
        "seed",
        "missing_question",
        "duplicate_question",
        "foreign_source",
        "canonical_number",
        "canonical_options",
        "canonical_key",
        "canonical_solution",
        "content",
        "current",
        "options",
        "mapping_missing",
        "mapping_duplicate",
        "mapping_outside",
        "key",
        "solution",
        "answer_key",
        "answer_alias",
        "question_order",
        "display_to_canonical",
        "canonical_to_display",
        "option_permutations",
    ],
)
async def test_direct_rpc_rejects_corrupt_payload_without_writes(db, case):
    admin, owner, _, sid, data = db
    before = await state(admin)
    version = data["versions"][0]
    q = version["questions"][0]
    if case in ("null", "scalar", "array"):
        data = {"null": None, "scalar": 7, "array": []}[case]
    elif case == "snapshot":
        data["snapshot"] = None
    elif case.endswith("_shape"):
        data["snapshot"][case.removesuffix("_shape")] = {}
    elif case == "uuid":
        version["version_id"] = "invalid"
    elif case == "overflow":
        q["display_no"] = 10**100
    elif case in ("bool_count", "string_count"):
        version["total_questions"] = True if case == "bool_count" else "3"
    elif case in ("string_display", "fraction_display"):
        q["display_no"] = "1" if case == "string_display" else 1.5
    elif case == "missing_version":
        data["versions"].pop()
    elif case == "duplicate_version":
        data["versions"][1] = deepcopy(version)
    elif case == "foreign_version":
        version["version_id"] = str(uuid4())
    elif case == "wrong_code":
        version["version_code"] = "999"
    elif case == "seed":
        version["shuffle_seed"] = "wrong"
    elif case == "missing_question":
        version["questions"].pop()
    elif case == "duplicate_question":
        version["questions"][1] = deepcopy(q)
    elif case == "foreign_source":
        q["source_question_id"] = str(uuid4())
    elif case.startswith("canonical_") and case not in ("canonical_to_display",):
        field = {
            "canonical_number": "canonical_question_no",
            "canonical_key": "canonical_correct_key",
            "canonical_solution": "canonical_solution_md",
        }.get(case, case)
        q[field] = {
            "canonical_number": 9,
            "canonical_options": ["x"] * 4,
            "canonical_key": "D",
            "canonical_solution": "tampered",
        }[case]
    elif case == "content":
        q["content"] = "other"
    elif case == "current":
        q["is_current"] = False
    elif case == "options":
        q["options"][0] = "tampered"
    elif case.startswith("mapping_"):
        q["permutation_map"] = {"A": "A", "B": "B", "C": "C", "D": "D"}
        if case == "mapping_missing":
            q["permutation_map"].pop("A")
        else:
            q["permutation_map"]["A"] = "B" if case == "mapping_duplicate" else "E"
    elif case == "key":
        q["display_correct_key"] = "Z"
    elif case == "solution":
        q["solution_md"] = "tampered"
    elif case.startswith("answer_"):
        version["answer_keys"][0][
            "display_correct_key" if case == "answer_key" else "canonical_question_no"
        ] = "Z"
    else:
        version["permutations"][case] = []
    with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_(INPUT_INCOMPLETE|STALE_INPUT)"):
        await persist(owner, sid, data)
    assert await state(admin) == before


@pytest.mark.parametrize(
    "case",
    [
        "missing_sub",
        "other_owner",
        "anon",
        "service_role",
        "missing_session",
        "generated",
        "approved",
        "exported",
        "approved_at",
        "active",
    ],
)
async def test_sql_authorization_and_state(db, case):
    admin, owner, _, sid, data = db
    expected = "ERR_UNAUTHORIZED"
    if case in ("missing_sub", "other_owner"):
        await owner.execute(
            "SELECT set_config('request.jwt.claim.sub',$1,false)",
            "" if case == "missing_sub" else str(uuid4()),
        )
    elif case in ("anon", "service_role"):
        await owner.execute("RESET ROLE")
        await owner.execute(f"SET ROLE {case}")
        expected = "permission denied"
    elif case == "missing_session":
        sid = str(uuid4())
    elif case == "approved_at":
        await admin.execute(
            "UPDATE public.exam_sessions SET approved_at=now() WHERE id=$1::uuid", sid
        )
        expected = "ERR_SESSION_LOCKED"
    elif case == "active":
        q = data["snapshot"]["questions"][0]
        await admin.execute(
            "INSERT INTO public.review_operations(operation_id,session_id,question_id,actor_id,prior_status,snapshot,reservation_result,expires_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'approved','{}','{}',now()+interval '1 minute')",
            str(uuid4()),
            sid,
            q["id"],
            OWNER,
        )
        expected = "ERR_SHUFFLE_NOT_READY"
    else:
        await admin.execute(
            "UPDATE public.exam_sessions SET status=$2::public.session_status WHERE id=$1::uuid",
            sid,
            case,
        )
        expected = "ERR_SHUFFLE_NOT_READY" if case == "generated" else "ERR_SESSION_LOCKED"
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match=expected):
        await persist(owner, sid, data)
    assert await state(admin) == before


async def test_all_columns_history_aliases_metadata_noop_and_repair(db):
    admin, owner, _, sid, data = db
    before = await state(admin)
    first = await persist(owner, sid, data)
    after = await state(admin)
    for v in data["versions"]:
        stored = await admin.fetchrow(
            "SELECT * FROM public.exam_versions WHERE id=$1::uuid", v["version_id"]
        )
        assert stored["is_finalized"] is True
        assert stored["shuffle_seed"] == v["shuffle_seed"]
        assert json.loads(stored["permutations"]) == v["permutations"]
        for q in v["questions"]:
            row = await admin.fetchrow(
                "SELECT * FROM public.version_questions WHERE id=$1::uuid", q["id"]
            )
            assert (
                row["question_no"],
                json.loads(row["options"]),
                row["correct_key"],
                row["solution_md"],
            ) == (q["display_no"], q["options"], q["display_correct_key"], q["solution_md"])
            key = await admin.fetchrow(
                "SELECT * FROM public.answer_keys WHERE version_id=$1::uuid AND display_no=$2",
                v["version_id"],
                q["display_no"],
            )
            assert key["question_no"] == key["display_no"] == q["display_no"]
            assert key["correct_option"] == key["display_correct_key"] == q["display_correct_key"]
            assert key["canonical_question_no"] == q["canonical_question_no"]
    old_rows = {r["id"]: r for r in json.loads(before["version_questions"])}
    for row in json.loads(after["version_questions"]):
        old = old_rows[row["id"]]
        if row["is_current"] and row["id"] in {q["id"] for q in data["snapshot"]["questions"]}:
            assert {
                k: v
                for k, v in row.items()
                if k not in ("question_no", "options", "correct_key", "solution_md", "updated_at")
            } == {
                k: v
                for k, v in old.items()
                if k not in ("question_no", "options", "correct_key", "solution_md", "updated_at")
            }
        else:
            assert row == old
    assert await persist(owner, sid, data) == first
    assert await state(admin) == after  # includes every key ID and timestamp
    await admin.execute(
        "DELETE FROM public.answer_keys WHERE version_id=$1::uuid",
        data["versions"][0]["version_id"],
    )
    await admin.execute(
        "UPDATE public.version_questions SET correct_key='Z',options='[]' WHERE id=$1::uuid",
        data["versions"][0]["questions"][0]["id"],
    )
    await admin.execute(
        "UPDATE public.exam_versions SET permutations='{}',shuffle_seed='wrong' WHERE id=$1::uuid",
        data["versions"][0]["version_id"],
    )
    assert await persist(owner, sid, data) == first
    repaired = await state(admin)

    def business_rows(raw, table):
        ignored = {"version_questions": {"updated_at"}, "answer_keys": {"id", "created_at"}}.get(
            table, set()
        )
        return sorted(
            json.dumps({k: v for k, v in row.items() if k not in ignored}, sort_keys=True)
            for row in json.loads(raw)
        )

    for table in after:
        assert business_rows(repaired[table], table) == business_rows(after[table], table)
    # New keys/timestamps are expected on repair; canonical/history must stay fixed.
    assert await persist(owner, sid, data) == first
    assert await state(admin) == repaired
    assert (
        len(
            [
                k
                for k in json.loads(repaired["answer_keys"])
                if k["version_id"] in {v["version_id"] for v in data["versions"]}
            ]
        )
        == 6
    )


@pytest.mark.parametrize(
    "point",
    [
        "display",
        "delete",
        "insert_first",
        "insert_middle",
        "insert_last",
        "finalized",
        "rowcount",
        "integrity",
        "timeout",
        "disconnect",
        "display_silent",
        "metadata_silent",
        "metadata_rowcount",
        "finalized_silent",
    ],
)
async def test_real_faults_rollback_every_row(db, point):
    admin, owner, _, sid, data = db
    await persist(owner, sid, data)
    await admin.execute(
        "UPDATE public.exam_versions SET is_finalized=false WHERE session_id=$1::uuid", sid
    )
    before = await state(admin)
    if point in ("display", "rowcount", "display_silent"):
        table, timing, event = "version_questions", "BEFORE", "UPDATE"
    elif point == "delete":
        table, timing, event = "answer_keys", "AFTER", "DELETE"
    elif point in ("finalized", "finalized_silent"):
        table, timing, event = "exam_versions", "BEFORE", "UPDATE OF is_finalized"
    elif point in ("metadata_silent", "metadata_rowcount"):
        table, timing, event = "exam_versions", "BEFORE", "UPDATE OF shuffle_seed"
    else:
        table, timing, event = "answer_keys", "BEFORE", "INSERT"
    action = "RAISE EXCEPTION 'AB_FAULT';"
    if point.startswith("insert_"):
        index = {"insert_first": 0, "insert_middle": 1, "insert_last": 2}[point]
        action = f"IF (SELECT count(*) FROM public.answer_keys WHERE version_id=NEW.version_id)={index} THEN RAISE EXCEPTION 'AB_FAULT'; END IF;"
    elif point in ("rowcount", "metadata_rowcount"):
        action = "RETURN NULL;"
    elif point == "display_silent":
        action = "NEW.options := '[]'::jsonb;"
    elif point == "metadata_silent":
        action = "NEW.permutations := '{}'::jsonb;"
    elif point == "finalized_silent":
        action = "NEW.is_finalized := false;"
    elif point == "integrity":
        action = "NEW.correct_option := 'Z'; NEW.display_correct_key := 'Z';"
    elif point == "timeout":
        await owner.execute("SET statement_timeout='150ms'")
        action = "PERFORM pg_sleep(5);"
    elif point == "disconnect":
        action = "PERFORM pg_terminate_backend(pg_backend_pid());"
    await admin.execute(
        f"CREATE FUNCTION public.ab_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {action} RETURN COALESCE(NEW,OLD); END $$; CREATE TRIGGER ab_fault {timing} {event} ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.ab_fault()"
    )
    try:
        with pytest.raises((asyncpg.PostgresError, asyncpg.InterfaceError, ConnectionError)) as exc:
            await persist(owner, sid, data)
        if point in ("rowcount", "metadata_rowcount"):
            assert "ERR_SHUFFLE_STALE_INPUT" in str(exc.value)
        elif point in ("integrity", "display_silent", "metadata_silent", "finalized_silent"):
            assert "ERR_SHUFFLE_INPUT_INCOMPLETE" in str(exc.value)
        elif point == "timeout":
            assert isinstance(exc.value, asyncpg.QueryCanceledError)
        elif point != "disconnect":
            assert "AB_FAULT" in str(exc.value)
        assert await state(admin) == before
    finally:
        await admin.execute(
            f"DROP TRIGGER ab_fault ON public.{table}; DROP FUNCTION public.ab_fault()"
        )


async def wait_blocked(observer, waiter, blocker):
    async def poll():
        while True:
            if await observer.fetchval(
                "SELECT $1::int=ANY(pg_blocking_pids($2::int))",
                blocker.get_server_pid(),
                waiter.get_server_pid(),
            ):
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), 3)


@pytest.mark.parametrize("repeat", range(3))
@pytest.mark.parametrize("winner", ["shuffle", "approval", "review", "revert"])
async def test_real_parent_lock_serializes_competing_rpc(db, winner, repeat):
    admin, owner, peer, sid, data = db
    target = data["snapshot"]["questions"][0]["id"]
    if winner == "revert":
        lineage = await admin.fetchrow(
            "SELECT c.id,h.id AS parent FROM public.version_questions c JOIN public.version_questions h ON h.version_id=c.version_id AND h.source_question_id=c.source_question_id JOIN public.exam_versions v ON v.id=c.version_id WHERE v.session_id=$1::uuid AND c.is_current AND NOT h.is_current LIMIT 1",
            sid,
        )
        target = str(lineage["id"])
        await admin.execute(
            "UPDATE public.version_questions SET regenerated_from_id=$2 WHERE id=$1",
            lineage["id"],
            lineage["parent"],
        )
    await persist(owner, sid, data)
    tx = owner.transaction()
    await tx.start()
    pending = None
    try:
        if winner == "approval":
            await owner.fetchval("SELECT public.finalize_approve_session($1::uuid,NULL,NULL)", sid)
        elif winner in ("review", "revert"):
            await owner.fetchval(
                "SELECT public.review_accept_question($1::uuid,$2::uuid,$3::uuid)"
                if winner == "review"
                else "SELECT public.review_revert_question($1::uuid,$2::uuid,$3::uuid)",
                sid,
                target,
                str(uuid4()),
            )
        else:
            await persist(owner, sid, data)
        if winner == "shuffle":
            pending = asyncio.create_task(
                peer.fetchval("SELECT public.finalize_approve_session($1::uuid,NULL,NULL)", sid)
            )
        else:
            pending = asyncio.create_task(persist(peer, sid, data))
        await wait_blocked(admin, peer, owner)
        await tx.commit()
        if winner in ("approval", "revert"):
            before = await state(admin)
            with pytest.raises(
                asyncpg.PostgresError,
                match="ERR_SESSION_LOCKED" if winner == "approval" else "ERR_SHUFFLE_STALE_INPUT",
            ):
                await asyncio.wait_for(pending, 5)
            assert await state(admin) == before
        else:
            result = await asyncio.wait_for(pending, 5)
            assert (
                (json.loads(result)["status"] == "approved")
                if winner == "shuffle"
                else result["is_finalized"]
            )
    finally:
        if owner.is_in_transaction():
            await tx.rollback()
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_solution_parity_unicode_markdown_math_corpus(db):
    admin = db[0]
    for canonical in "ABCD":
        for target in "ABCD":
            for prefix in (
                "Chọn ",
                "Đáp án: ",
                "Phương án đúng là ",
                "Kết luận: ",
                "Suy ra: ",
                "Vậy: ",
                "xChọn ",
                "🙂Chọn ",
            ):
                for wrap in ("{}", "**{}**", "({})", "[{}]", r"\textbf{{{}}}"):
                    for suffix in ("", ".", ": đúng", " = 3", r" \in X", " + A", "\nChọn A"):
                        text = prefix + wrap.format(canonical) + suffix
                        actual = await admin.fetchval(
                            "SELECT public._finalize_sync_solution($1,$2,$3)",
                            text,
                            canonical,
                            target,
                        )
                        assert actual == sync_solution_text(text, canonical, target), (
                            text,
                            canonical,
                            target,
                            actual,
                        )
    for whitespace in ("\t", "\r\n", "\u00a0", "\u2003", "\u202f", "\x1c", "\x85"):
        for text in (f"Chọn{whitespace}A", f"Chọn A{whitespace}= 2", f"Vậy:{whitespace}A."):
            assert await admin.fetchval(
                "SELECT public._finalize_sync_solution($1,'A','B')", text
            ) == sync_solution_text(text, "A", "B"), repr(text)


@pytest.mark.parametrize(
    "case",
    [
        "missing_current",
        "unapproved",
        "foreign_source",
        "canonical_number",
        "bad_key",
        "options_short",
        "options_long",
        "options_nonstring",
        "config_missing",
        "config_extra",
        "config_changed",
        "unknown_pref",
        "version_missing",
        "version_extra",
        "source_number_duplicate",
    ],
)
async def test_sql_revalidates_live_database_inputs(db, case):
    admin, owner, _, sid, old = db
    q = old["snapshot"]["questions"][0]
    if case == "missing_current":
        await admin.execute(
            "UPDATE public.version_questions SET is_current=false WHERE id=$1::uuid", q["id"]
        )
    elif case == "unapproved":
        await admin.execute(
            "UPDATE public.version_questions SET status='pending_review' WHERE id=$1::uuid", q["id"]
        )
    elif case in ("config_missing", "config_extra", "config_changed", "unknown_pref"):
        if case == "config_missing":
            await admin.execute(
                "DELETE FROM public.generation_configs WHERE session_id=$1::uuid", sid
            )
        elif case == "config_extra":
            await admin.execute(
                "INSERT INTO public.generation_configs(session_id,n_versions) VALUES($1::uuid,2)",
                sid,
            )
        else:
            prefs = {"shuffle_options": False} if case == "config_changed" else {"unexpected": True}
            await admin.execute(
                "UPDATE public.generation_configs SET ordering_preferences=$2::jsonb WHERE session_id=$1::uuid",
                sid,
                json.dumps(prefs),
            )
    elif case.startswith("version_"):
        if case == "version_missing":
            await admin.execute(
                "DELETE FROM public.exam_versions WHERE id=$1::uuid", q["version_id"]
            )
        else:
            await admin.execute(
                "INSERT INTO public.exam_versions(session_id,version_code) VALUES($1::uuid,'103')",
                sid,
            )
    elif case == "source_number_duplicate":
        await admin.execute(
            "UPDATE public.source_questions SET question_no=1 WHERE session_id=$1::uuid", sid
        )
    else:
        # New candidate snapshots may be malformed even though immutable on UPDATE.
        await admin.execute(
            "UPDATE public.version_questions SET is_current=false WHERE id=$1::uuid", q["id"]
        )
        source = (
            q["source_question_id"]
            if case != "foreign_source"
            else "20000000-0000-0000-0000-000000000001"
        )
        options = {
            "options_short": ["a"],
            "options_long": ["a"] * 5,
            "options_nonstring": [1, 2, 3, 4],
        }.get(case, ["a", "b", "c", "d"])
        await admin.execute(
            "INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,canonical_question_no,canonical_options,canonical_correct_key,status) VALUES($1::uuid,$2::uuid,1,'new','[]','A',$3,$4::jsonb,$5,'approved')",
            q["version_id"],
            source,
            99 if case == "canonical_number" else q["canonical_question_no"],
            json.dumps(options),
            "Z" if case == "bad_key" else "A",
        )
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError):
        await persist(owner, sid, old)
    assert await state(admin) == before
    # With malformed canonical values, match the LIVE snapshot too: rejection
    # must come from SQL canonical validation rather than just stale detection.
    if case in ("bad_key", "options_short", "options_long", "options_nonstring"):
        data = deepcopy(old)
        data["snapshot"] = await snapshot(admin, sid)
        new_q = next(
            x
            for x in data["snapshot"]["questions"]
            if x["source_question_id"] == q["source_question_id"]
            and x["version_id"] == q["version_id"]
        )
        for v in data["versions"]:
            for output in v["questions"]:
                if output["id"] == q["id"]:
                    output.update(
                        {
                            k: new_q[k]
                            for k in (
                                "id",
                                "content",
                                "canonical_options",
                                "canonical_correct_key",
                                "canonical_solution_md",
                            )
                        }
                    )
        with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_INPUT_INCOMPLETE"):
            await persist(owner, sid, data)
        assert await state(admin) == before


async def test_unknown_commit_outcome_retries_without_writes(db):
    from app.models.schemas import ReviewDomainException
    from app.services.finalize.repository import FinalizeRepository
    from tests.services.test_finalize_real_db_integration import AsyncpgSupabaseAdapter

    admin, _, _, sid, data = db
    dsn = os.environ["TASK305_WRITER_TEST_DSN"]
    adapter = AsyncpgSupabaseAdapter(dsn, actor=OWNER)

    class LostReceipt:
        def rpc(self, name, params):
            rpc = adapter.rpc(name, params)

            class Request:
                def execute(self):
                    rpc.execute()  # actual committed PostgreSQL RPC
                    raise TimeoutError("receipt lost after commit")

            return Request()

        def table(self, name):
            raise AssertionError("no fallback writes")

    with pytest.raises(ReviewDomainException) as exc:
        await FinalizeRepository(LostReceipt()).persist_shuffle_rpc(
            sid, data, data["snapshot"]["versions"], 3
        )
    assert exc.value.error_code == "ERR_UPSTREAM_TIMEOUT"
    committed = await state(admin)
    receipt = await FinalizeRepository(adapter).persist_shuffle_rpc(
        sid, data, data["snapshot"]["versions"], 3
    )
    assert receipt["is_finalized"] is True
    assert await state(admin) == committed


async def test_changed_preferences_reject_old_snapshot_then_recompute(db):
    admin, owner, _, sid, old = db
    await persist(owner, sid, old)
    await admin.execute(
        'UPDATE public.generation_configs SET ordering_preferences=\'{"shuffle_questions":false,"shuffle_options":false}\' WHERE session_id=$1::uuid',
        sid,
    )
    before = await state(admin)
    with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_STALE_INPUT"):
        await persist(owner, sid, old)
    assert await state(admin) == before
    fresh = payload(sid, await snapshot(admin, sid))
    await persist(owner, sid, fresh)
    for v in fresh["versions"]:
        assert v["permutations"]["question_order"] == [1, 2, 3]
        assert all(q["permutation_map"] == {c: c for c in "ABCD"} for q in v["questions"])
    committed = await state(admin)
    await persist(owner, sid, fresh)
    assert await state(admin) == committed


async def test_http_uppercase_uuid_and_committed_response(db):
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_current_user, get_user_db
    from app.main import app
    from app.models.schemas import CurrentUser
    from tests.services.test_finalize_real_db_integration import AsyncpgSupabaseAdapter

    admin, _, _, sid, data = db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=OWNER, email="test@example.invalid", name="Teacher", access_token="test"
    )
    app.dependency_overrides[get_user_db] = lambda: AsyncpgSupabaseAdapter(
        os.environ["TASK305_WRITER_TEST_DSN"], actor=OWNER
    )
    try:
        response = TestClient(app).post(f"/api/sessions/{sid.upper()}/finalize/shuffle")
        assert response.status_code == 200, response.text
        assert response.json()["session_id"] == sid
        assert response.json()["versions"] == [
            {"version_id": v["version_id"], "version_code": v["version_code"], "total_questions": 3}
            for v in data["versions"]
        ]
        assert all(v["is_finalized"] for v in json.loads((await state(admin))["exam_versions"]))
        for status in ("approved", "exported", "generated"):
            await admin.execute(
                "UPDATE public.exam_sessions SET status=$2::public.session_status WHERE id=$1::uuid",
                sid,
                status,
            )
            before = await state(admin)
            denied = TestClient(app).post(f"/api/sessions/{sid}/finalize/shuffle")
            assert denied.status_code == (409 if status == "generated" else 423), denied.text
            assert await state(admin) == before
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "constraint", ["duplicate_current", "duplicate_key", "wrong_alias", "canonical_update"]
)
async def test_schema_guards_are_real_constraints(db, constraint):
    admin, owner, _, sid, data = db
    await persist(owner, sid, data)
    before = await state(admin)
    q = data["versions"][0]["questions"][0]
    with pytest.raises(asyncpg.PostgresError):
        if constraint == "duplicate_current":
            await admin.execute(
                "INSERT INTO public.version_questions(version_id,source_question_id,question_no,content,options,correct_key,canonical_question_no,canonical_options,canonical_correct_key) SELECT version_id,source_question_id,question_no,content,options,correct_key,canonical_question_no,canonical_options,canonical_correct_key FROM public.version_questions WHERE id=$1::uuid",
                q["id"],
            )
        elif constraint == "duplicate_key":
            await admin.execute(
                "INSERT INTO public.answer_keys(version_id,question_no,display_no,correct_option,display_correct_key,canonical_question_no) SELECT version_id,question_no,display_no,correct_option,display_correct_key,canonical_question_no FROM public.answer_keys WHERE version_id=$1::uuid",
                data["versions"][0]["version_id"],
            )
        elif constraint == "wrong_alias":
            await admin.execute(
                "INSERT INTO public.answer_keys(version_id,question_no,display_no,correct_option,display_correct_key,canonical_question_no) VALUES($1::uuid,99,98,'A','B',1)",
                data["versions"][0]["version_id"],
            )
        else:
            await admin.execute(
                "UPDATE public.version_questions SET canonical_correct_key='D' WHERE id=$1::uuid",
                q["id"],
            )
    assert await state(admin) == before
