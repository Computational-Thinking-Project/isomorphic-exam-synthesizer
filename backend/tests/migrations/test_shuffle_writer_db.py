"""Opt-in tests against the disposable, pre-seeded TASK-305 PostgreSQL container."""

import asyncio
import json
import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_service_db, get_user_db
from app.main import app
from app.models.schemas import CurrentUser
from app.services.finalize.repository import FinalizeRepository
from app.services.finalize.service import FinalizeService
from app.services.finalize.shuffle_input import prepare_shuffle
from app.services.shuffler.service import sync_solution_text
from tests.migrations.test_shuffle_writer_adversarial import persist as trusted_persist
from tests.migrations.test_shuffle_writer_adversarial import wait_blocked
from tests.services.test_finalize_real_db_integration import AsyncpgSupabaseAdapter

asyncpg = pytest.importorskip("asyncpg")
SESSION = "10000000-0000-0000-0000-000000000001"
OWNER = "00000000-0000-0000-0000-000000000001"


def test_shuffle_writer_atomicity_and_locking():
    if os.environ.get("RUN_TASK305_WRITER_DB_TEST") != "1":
        pytest.skip("requires explicitly provisioned disposable PostgreSQL")
    dsn = os.environ["TASK305_WRITER_TEST_DSN"]
    parsed = urlparse(dsn)
    if parsed.hostname != "127.0.0.1" or parsed.path != "/task305_isolated":
        pytest.fail("refusing a non-disposable test DSN")
    asyncio.run(_exercise(dsn))


async def _exercise(dsn):
    admin = await asyncpg.connect(dsn)
    a = await asyncpg.connect(dsn)
    b = await asyncpg.connect(dsn)
    anon = await asyncpg.connect(dsn)
    try:
        assert await admin.fetchval("SELECT current_database()") == "task305_isolated"
        await admin.execute(
            "UPDATE public.exam_sessions SET status='reviewed',approved_at=NULL WHERE id=$1::uuid",
            SESSION,
        )
        for text in (
            "Chọn A",
            "Đáp án: **A**.",
            "Kết luận: A",
            "Vậy: \\textbf{A}",
            "Chọn A = 1",
            "Đáp án đúng là A. Chọn A",
            "không có kết luận",
            None,
            "Đáp án A: 5",
            "Do đó ta chọn A.",
            "Vậy phương án đúng là A.",
            "Chọn **A** vì nghiệm là 2.",
            "Kết luận: \\textbf{A}",
            "Đáp án: A",
            "Suy ra: A > 0",
            r"Do đó: A \in (0, 1)",
            "Vậy: A + B = 10",
            "Vậy: A.",
        ):
            for target in ("A", "B", "C", "D"):
                actual = await admin.fetchval(
                    "SELECT public._finalize_sync_solution($1,'A',$2)", text, target
                )
                assert actual == sync_solution_text(text, "A", target), (text, target, actual)
        payload_data = json.loads(await admin.fetchval("SELECT public.test_shuffle_payload()"))
        payload_data["versions"][0]["questions"][0]["is_current"] = True
        payload = json.dumps(payload_data)
        await a.execute("SET ROLE authenticated")
        await b.execute("SET ROLE authenticated")
        for conn in (a, b):
            await conn.execute("SELECT set_config('request.jwt.claim.sub',$1,false)", OWNER)

        async def persist(conn, value=payload):
            return await trusted_persist(conn, SESSION, json.loads(value))

        await anon.execute("SET ROLE anon")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await anon.fetchval(
                "SELECT public.finalize_persist_shuffle($1::uuid,$2::jsonb)", SESSION, payload
            )

        # Stale pre-read config is rejected and no writer state changes.
        before = await admin.fetchval(
            "SELECT row_to_json(v)::text FROM public.exam_versions v LIMIT 1"
        )
        await admin.execute("UPDATE public.generation_configs SET ordering_preferences='{}'::jsonb")
        with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_STALE_INPUT"):
            await persist(a)
        assert (
            await admin.fetchval("SELECT row_to_json(v)::text FROM public.exam_versions v LIMIT 1")
            == before
        )
        await admin.execute(
            "UPDATE public.generation_configs SET ordering_preferences=$1::jsonb",
            json.dumps({"shuffle_questions": False, "shuffle_options": False}),
        )
        await admin.execute(
            "UPDATE public.version_questions SET content='changed' WHERE version_id='30000000-0000-0000-0000-000000000001'"
        )
        with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_STALE_INPUT"):
            await persist(a)
        await admin.execute(
            "UPDATE public.version_questions SET content='stem' WHERE version_id='30000000-0000-0000-0000-000000000001'"
        )
        await b.execute(
            "SELECT set_config('request.jwt.claim.sub',$1,false)",
            "00000000-0000-0000-0000-000000000002",
        )
        with pytest.raises(asyncpg.PostgresError, match="ERR_UNAUTHORIZED"):
            await persist(
                b,
                json.dumps(
                    {**json.loads(payload), "actor_id": "00000000-0000-0000-0000-000000000002"}
                ),
            )
        await b.execute("SELECT set_config('request.jwt.claim.sub',$1,false)", OWNER)
        corrupt = json.loads(payload)
        corrupt["versions"][0]["questions"][0]["display_correct_key"] = "B"
        with pytest.raises(asyncpg.PostgresError, match="ERR_SHUFFLE_INPUT_INCOMPLETE"):
            await persist(a, json.dumps(corrupt))
        assert (
            await admin.fetchval("SELECT row_to_json(v)::text FROM public.exam_versions v LIMIT 1")
            == before
        )

        # Send the actual Python shuffler output, including synchronized solution text.
        await admin.execute(
            "UPDATE public.generation_configs SET ordering_preferences=$1::jsonb",
            json.dumps({"shuffle_questions": False, "shuffle_options": True}),
        )
        generated = json.loads(await admin.fetchval("SELECT public.test_shuffle_payload()"))
        snap = generated["snapshot"]
        generated["versions"] = [
            x.model_dump(mode="json")
            for x in prepare_shuffle(
                SESSION, snap["config"], snap["versions"], snap["sources"], snap["questions"]
            )
        ]
        assert (await persist(a, json.dumps(generated)))["is_finalized"] is True
        row = await admin.fetchrow(
            "SELECT correct_key,options,solution_md FROM public.version_questions LIMIT 1"
        )
        question = generated["versions"][0]["questions"][0]
        assert row["correct_key"] == question["display_correct_key"]
        assert json.loads(row["options"]) == question["options"]
        assert row["solution_md"] == question["solution_md"]
        await admin.execute(
            "UPDATE public.generation_configs SET ordering_preferences=$1::jsonb",
            json.dumps({"shuffle_questions": False, "shuffle_options": False}),
        )

        # Force an error after DELETE and display UPDATE, and compare all rows.
        await admin.execute("UPDATE public.exam_versions SET is_finalized=false")
        before = await admin.fetchval(
            "SELECT jsonb_build_object('v',(SELECT jsonb_agg(to_jsonb(v)) FROM public.exam_versions v),'q',(SELECT jsonb_agg(to_jsonb(q)) FROM public.version_questions q),'k',(SELECT jsonb_agg(to_jsonb(k)) FROM public.answer_keys k))::text"
        )
        await admin.execute(
            "CREATE FUNCTION public.task305_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TASK305_INJECTED'; END $$; CREATE TRIGGER task305_test_fail BEFORE INSERT ON public.answer_keys FOR EACH ROW EXECUTE FUNCTION public.task305_test_fail()"
        )
        try:
            with pytest.raises(asyncpg.PostgresError, match="TASK305_INJECTED"):
                await persist(a)
            after = await admin.fetchval(
                "SELECT jsonb_build_object('v',(SELECT jsonb_agg(to_jsonb(v)) FROM public.exam_versions v),'q',(SELECT jsonb_agg(to_jsonb(q)) FROM public.version_questions q),'k',(SELECT jsonb_agg(to_jsonb(k)) FROM public.answer_keys k))::text"
            )
            assert after == before
        finally:
            await admin.execute(
                "DROP TRIGGER task305_test_fail ON public.answer_keys; DROP FUNCTION public.task305_test_fail()"
            )

        # Writer B must wait for writer A's parent lock, then safely retry.
        lock = a.transaction()
        await lock.start()
        assert (await persist(a))["is_finalized"] is True
        waiting = asyncio.create_task(persist(b))
        await wait_blocked(admin, b, a)
        await lock.commit()
        assert (await asyncio.wait_for(waiting, 5))["is_finalized"] is True
        timestamp = await admin.fetchval("SELECT updated_at FROM public.version_questions LIMIT 1")
        assert (await persist(a))["is_finalized"] is True
        assert (
            await admin.fetchval("SELECT updated_at FROM public.version_questions LIMIT 1")
            == timestamp
        )

        lock = a.transaction()
        await lock.start()
        assert (await persist(a))["is_finalized"] is True
        approval = asyncio.create_task(
            b.fetchval("SELECT public.finalize_approve_session($1::uuid,NULL,NULL)", SESSION)
        )
        await wait_blocked(admin, b, a)
        await lock.commit()
        assert json.loads(await asyncio.wait_for(approval, 5))["status"] == "approved"
        await admin.execute(
            "UPDATE public.exam_sessions SET status='reviewed',approved_at=NULL WHERE id=$1::uuid",
            SESSION,
        )

        # An approval holding the shared parent lock wins over precomputed shuffle.
        lock = admin.transaction()
        await lock.start()
        await admin.execute(
            "SELECT id FROM public.exam_sessions WHERE id=$1::uuid FOR UPDATE", SESSION
        )
        waiting = asyncio.create_task(persist(b))
        await wait_blocked(a, b, admin)
        await admin.execute("SET LOCAL ROLE authenticated")
        await admin.execute("SELECT set_config('request.jwt.claim.sub',$1,true)", OWNER)
        await admin.fetchval("SELECT public.finalize_approve_session($1::uuid,NULL,NULL)", SESSION)
        await lock.commit()
        with pytest.raises(asyncpg.PostgresError, match="ERR_SESSION_LOCKED"):
            await asyncio.wait_for(waiting, 5)
        await _multi_version(admin, a, dsn)
    finally:
        await admin.close()
        await a.close()
        await b.close()
        await anon.close()


async def _multi_version(admin, owner, dsn):
    session = str(uuid4())
    other_keys = await admin.fetchval(
        "SELECT jsonb_agg(to_jsonb(k) ORDER BY k.id)::text FROM public.answer_keys k "
        "JOIN public.exam_versions v ON v.id=k.version_id WHERE v.session_id=$1::uuid",
        SESSION,
    )
    config = {
        "id": str(uuid4()),
        "session_id": session,
        "n_versions": 2,
        "ordering_preferences": {"shuffle_questions": True, "shuffle_options": True},
    }
    await admin.execute(
        "INSERT INTO public.exam_sessions(id,user_id,title) VALUES ($1::uuid,$2::uuid,'multi')",
        session,
        OWNER,
    )
    await admin.execute(
        "INSERT INTO public.generation_configs(id,session_id,n_versions,ordering_preferences) VALUES ($1::uuid,$2::uuid,2,$3::jsonb)",
        config["id"],
        session,
        json.dumps(config["ordering_preferences"]),
    )
    versions = [
        {"id": str(uuid4()), "session_id": session, "version_code": code} for code in ("101", "102")
    ]
    sources = [{"id": str(uuid4()), "session_id": session, "question_no": i} for i in (1, 2, 3)]
    for source in sources:
        await admin.execute(
            "INSERT INTO public.source_questions(id,session_id,question_no,raw_content,options,correct_key) VALUES ($1::uuid,$2::uuid,$3,'source','{}','A')",
            source["id"],
            session,
            source["question_no"],
        )
        await admin.execute(
            "INSERT INTO public.question_blueprints(source_question_id,confirmed_at) VALUES ($1::uuid,now())",
            source["id"],
        )
    for version in versions:
        await admin.execute(
            "INSERT INTO public.exam_versions(id,session_id,version_code) VALUES ($1::uuid,$2::uuid,$3)",
            version["id"],
            session,
            version["version_code"],
        )
    questions = []
    for version in versions:
        for source in sources:
            question = {
                "id": str(uuid4()),
                "version_id": version["id"],
                "source_question_id": source["id"],
                "content": "stem " + version["version_code"],
                "canonical_question_no": source["question_no"],
                "canonical_options": ["a", "b", "c", "d"],
                "canonical_correct_key": "A",
                "canonical_solution_md": "Đáp án A: đúng",
                "status": "approved",
                "is_current": True,
            }
            questions.append(question)
            await admin.execute(
                "INSERT INTO public.version_questions(id,version_id,source_question_id,question_no,content,options,correct_key,canonical_question_no,canonical_options,canonical_correct_key,canonical_solution_md,status,is_current) VALUES ($1::uuid,$2::uuid,$3::uuid,$4,$5,$6::jsonb,'A',$4,$6::jsonb,'A',$7,'approved',true)",
                question["id"],
                version["id"],
                source["id"],
                source["question_no"],
                question["content"],
                json.dumps(question["canonical_options"]),
                question["canonical_solution_md"],
            )
    await admin.execute(
        "UPDATE public.exam_sessions SET status='reviewed' WHERE id=$1::uuid", session
    )
    snapshot = {"config": config, "versions": versions, "sources": sources, "questions": questions}
    results = prepare_shuffle(session, config, versions, sources, questions)
    payload = json.dumps(
        {"snapshot": snapshot, "versions": [r.model_dump(mode="json") for r in results]}
    )
    state_sql = "SELECT jsonb_build_object('v',(SELECT jsonb_agg(to_jsonb(v) ORDER BY v.id) FROM public.exam_versions v WHERE v.session_id=$1::uuid),'q',(SELECT jsonb_agg(to_jsonb(q) ORDER BY q.id) FROM public.version_questions q JOIN public.exam_versions v ON v.id=q.version_id WHERE v.session_id=$1::uuid),'k',(SELECT jsonb_agg(to_jsonb(k) ORDER BY k.id) FROM public.answer_keys k JOIN public.exam_versions v ON v.id=k.version_id WHERE v.session_id=$1::uuid))::text"
    before = await admin.fetchval(state_sql, session)
    await admin.execute(
        "CREATE FUNCTION public.task305_test_fail_later() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (SELECT count(*) FROM public.answer_keys WHERE version_id=NEW.version_id)>=2 THEN RAISE EXCEPTION 'TASK305_INSERT_FAILURE'; END IF; RETURN NEW; END $$; CREATE TRIGGER task305_test_fail_later BEFORE INSERT ON public.answer_keys FOR EACH ROW EXECUTE FUNCTION public.task305_test_fail_later()"
    )
    try:
        with pytest.raises(asyncpg.PostgresError, match="TASK305_INSERT_FAILURE"):
            await trusted_persist(owner, session, json.loads(payload))
        assert await admin.fetchval(state_sql, session) == before
    finally:
        await admin.execute(
            "DROP TRIGGER task305_test_fail_later ON public.answer_keys; DROP FUNCTION public.task305_test_fail_later()"
        )
    receipt = await trusted_persist(owner, session, json.loads(payload))
    assert receipt["is_finalized"] and len(receipt["versions"]) == 2
    writer = FinalizeRepository(AsyncpgSupabaseAdapter(dsn, role="service_role", actor=OWNER))
    via_service = await FinalizeService(
        AsyncpgSupabaseAdapter(dsn, actor=OWNER), writer_repo=writer
    ).shuffle_session(session, OWNER)
    assert via_service.is_finalized is True and len(via_service.versions) == 2
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=OWNER, email="teacher@example.invalid", name="Teacher", access_token="test"
    )
    app.dependency_overrides[get_user_db] = lambda: AsyncpgSupabaseAdapter(dsn, actor=OWNER)
    app.dependency_overrides[get_service_db] = lambda: AsyncpgSupabaseAdapter(
        dsn, role="service_role", actor=OWNER
    )
    try:
        response = TestClient(app).post(f"/api/sessions/{session}/finalize/shuffle")
        assert response.status_code == 200, response.text
        assert response.json()["is_finalized"] is True
    finally:
        app.dependency_overrides.clear()
    assert (
        await admin.fetchval(
            "SELECT count(*) FROM public.answer_keys k JOIN public.exam_versions v ON v.id=k.version_id WHERE v.session_id=$1::uuid",
            session,
        )
        == 6
    )
    assert (
        await admin.fetchval(
            "SELECT jsonb_agg(to_jsonb(k) ORDER BY k.id)::text FROM public.answer_keys k "
            "JOIN public.exam_versions v ON v.id=k.version_id WHERE v.session_id=$1::uuid",
            SESSION,
        )
        == other_keys
    )
    for result in results:
        for question in result.questions:
            row = await admin.fetchrow(
                "SELECT question_no,options,correct_key,solution_md,canonical_options FROM public.version_questions WHERE id=$1::uuid",
                question.id,
            )
            assert row["question_no"] == question.display_no
            assert json.loads(row["options"]) == question.options
            assert row["correct_key"] == question.display_correct_key
            assert row["solution_md"] == question.solution_md
            assert json.loads(row["canonical_options"]) == question.canonical_options
    await admin.execute("DELETE FROM public.exam_sessions WHERE id=$1::uuid", session)
