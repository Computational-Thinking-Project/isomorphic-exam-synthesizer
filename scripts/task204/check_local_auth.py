"""Real local GoTrue/PostgREST smoke checks; never print keys, JWTs or passwords.

Input: private JSON from `supabase status -o json`. Creates synthetic users only.
Browser acceptance and Docker egress isolation are recorded separately.
"""
import argparse
import json
import secrets
import os
import sys
import tempfile
import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from local_transport import LoopbackGuard, assert_local_url


def check_backend(status, tokens, sid, assertions, values=False):
    """Real app dependencies, followed by explicitly controlled fake production."""
    backend = Path(__file__).resolve().parents[2] / "backend"
    sys.path.insert(0, str(backend))
    # Do not let application settings discover the checkout's cloud .env.
    old_cwd = Path.cwd()
    runtime_dir = tempfile.TemporaryDirectory(prefix="task204-runtime-")
    os.chdir(runtime_dir.name)
    os.environ.update(SUPABASE_URL=status["API_URL"], SUPABASE_ANON_KEY=status["ANON_KEY"],
                      SUPABASE_SERVICE_ROLE_KEY=status["SERVICE_ROLE_KEY"],
                      GEMINI_API_KEY="", GEMINI_API_KEY_1="", GEMINI_API_KEY_2="", GEMINI_API_KEY_3="")
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.core.config import settings
        assert not settings.get_gemini_api_keys()
        assert not app.dependency_overrides
        with TestClient(app) as api:
            a = {"Authorization": f"Bearer {tokens[0]}"}
            b = {"Authorization": f"Bearer {tokens[1]}"}
            base = f"/api/sessions/{sid}"
            assert api.get(base).status_code == 401
            assert api.get(base, headers=b).status_code in (403, 404)
            preview = api.get(base, headers=a)
            assert preview.status_code == 200, "Backend real preview failed"
            revision = str(__import__("uuid").UUID(preview.json()["source_revision"]))
            assert api.post(base + "/confirm-source", headers=a, json={"source_revision": revision}).status_code == 422
            headers = {**a, "Idempotency-Key": str(uuid4())}
            assert api.post(base + "/confirm-source", headers=headers, json={}).status_code == 422
            assert api.post(base + "/confirm-source", headers={**b, "Idempotency-Key": str(uuid4())},
                json={"source_revision": revision}).status_code in (403, 404)
            assert api.post(base + "/confirm-source", headers=headers,
                            json={"source_revision": str(uuid4())}).status_code == 409
            result = api.post(base + "/confirm-source", headers=headers, json={"source_revision": revision})
            assert result.status_code == 200, "Backend real confirmation failed"
            replay = api.post(base + "/confirm-source", headers=headers, json={"source_revision": revision})
            assert replay.status_code == 200
            assert replay.json()["confirmation_id"] == result.json()["confirmation_id"]
            artifacts = api.get(base + "/source-artifacts", headers=a)
            assert artifacts.status_code == 200 and artifacts.json()["canonical_status"] == "pending"
            from app.core.database import get_service_role_client
            from app.services.blueprint.producer import SourceArtifactRepository
            from uuid import UUID
            worker = get_service_role_client()
            repository = SourceArtifactRepository(worker)
            state = asyncio.run(repository.load(sid))
            job_id = uuid4()
            claim = asyncio.run(repository.claim(UUID(sid), state.confirmation.sources[0], job_id))
            assert claim.status == "claimed"
            running = api.get(base + "/source-artifacts", headers=a)
            assert running.status_code == 200 and running.json()["canonical_status"] == "running"
            asyncio.run(repository.fail(UUID(sid), state.confirmation.sources[0].source_revision_id,
                                        job_id, "TASK204_FAKE_FAILURE"))
            failed = api.get(base + "/source-artifacts", headers=a)
            assert failed.status_code == 200 and failed.json()["canonical_status"] == "failed"
            assertions.append("real worker RPC claim/fail and HTTP pending/running/failed")
            from fake_algebra import FakeAlgebra
            from app.services.blueprint.producer import ConfirmedArtifactProducer
            from app.services.ai.gateway import RequestContext
            import time
            producer = ConfirmedArtifactProducer(repository, FakeAlgebra(values=values))
            asyncio.run(producer.resume(sid, RequestContext(time.monotonic() + 60, lambda: None)))
            ready = api.get(base + "/source-artifacts", headers=a)
            assert ready.status_code == 200 and ready.json()["ready"] is True
            assert bool(ready.json()["supported_modes"]) == values
            detail = api.get(base, headers=a)
            assert detail.status_code == 200 and detail.json()["blueprint_summary"]["is_ready"] is True
            assertions.append("fake algebra producer / GET ready summary / " + ("nonempty modes" if values else "modes=[]"))
            assert api.get(base + "/source-artifacts", headers=b).status_code in (403, 404)
            preflight = api.options(base + "/confirm-source", headers={"Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type,idempotency-key"})
            assert preflight.status_code == 200
            assert "idempotency-key" in preflight.headers.get("access-control-allow-headers", "").lower()
            assertions.extend(["real backend JWT ownership", "UUID preview / 422 key / 409 revision",
                               "real confirm + same-key receipt replay", "pending artifacts / foreign-owner denial",
                               "CORS Idempotency-Key preflight"])
    finally:
        os.chdir(old_cwd)
        runtime_dir.cleanup()


def run(status):
    url = status["API_URL"].rstrip("/")
    assert_local_url(url)
    anon, service = status["ANON_KEY"], status["SERVICE_ROLE_KEY"]
    assertions = []
    with LoopbackGuard() as guard, httpx.Client(base_url=url, trust_env=False, timeout=30) as client:
        tokens, identities, accounts = [], [], []
        for label in ("a", "b"):
            email = f"task204-{label}-{uuid4().hex}@example.invalid"
            password = secrets.token_urlsafe(24)
            created = client.post("/auth/v1/admin/users", headers={"apikey": service,
                "Authorization": f"Bearer {service}"}, json={"email": email,
                "password": password, "email_confirm": True})
            assert created.status_code in (200, 201), "Local Auth user creation failed"
            login = client.post("/auth/v1/token?grant_type=password", headers={"apikey": anon},
                                json={"email": email, "password": password})
            assert login.status_code == 200, "Local Auth login failed"
            tokens.append(login.json()["access_token"])
            identities.append(login.json()["user"]["id"])
            accounts.append({"email": email, "password": password,
                             "access_token": login.json()["access_token"],
                             "refresh_token": login.json()["refresh_token"]})
        assertions.append("two real Auth logins")
        headers = [{"apikey": anon, "Authorization": f"Bearer {token}"} for token in tokens]
        response = client.post("/rest/v1/exam_sessions", headers={**headers[0],
            "Prefer": "return=representation"}, json={"user_id": identities[0],
            "title": "TASK-204 synthetic algebra"})
        assert response.status_code == 201, "Owner session creation failed"
        sid = response.json()[0]["id"]
        for index, expected in ((0, 1), (1, 0)):
            response = client.get(f"/rest/v1/exam_sessions?id=eq.{sid}&select=id", headers=headers[index])
            assert response.status_code == 200 and len(response.json()) == expected, "RLS visibility failed"
        assertions.append("real PostgREST owner visibility / foreign-owner RLS denial")
        denied = client.patch(f"/rest/v1/exam_sessions?id=eq.{sid}",
            headers={**headers[1], "Prefer": "return=representation"}, json={"title": "foreign write"})
        assert denied.status_code == 200 and denied.json() == [], "Foreign RLS write affected session"
        legacy = client.post("/rest/v1/rpc/confirm_exam_source", headers=headers[0],
            json={"p_session_id": sid, "p_expected_question_count": 1,
                  "p_acknowledged_security_warnings": False, "p_expected_updated_at": None})
        assert legacy.status_code in (401, 403, 404), "Legacy RPC not denied"
        assertions.append("foreign-owner UPDATE blocked / legacy confirmation RPC denied")
        question = {"question_no": 1, "raw_content": "Giải phương trình 2x + 1 = 5.",
                    "options": ["2", "1", "3", "4"], "correct_key": "A",
                    "solution_md": "2x = 4 nên x = 2.", "has_missing_answer": False,
                    "has_security_warning": False}
        seeded = client.post("/rest/v1/rpc/replace_source_questions", headers=headers[0],
                             json={"p_session_id": sid, "p_questions": [question]})
        assert seeded.status_code == 200, "Local source seeding failed"
        forbidden_seed = client.post("/rest/v1/rpc/replace_source_questions", headers=headers[1],
            json={"p_session_id": sid, "p_questions": [question]})
        assert forbidden_seed.status_code == 403, "Foreign owner source RPC accepted"
        assertions.append("foreign-owner source replacement RPC denied")
        browser_session = client.post("/rest/v1/exam_sessions", headers={**headers[0],
            "Prefer": "return=representation"}, json={"user_id": identities[0], "title": "TASK204 browser algebra"})
        assert browser_session.status_code == 201
        browser_sid = browser_session.json()[0]["id"]
        assert client.post("/rest/v1/rpc/replace_source_questions", headers=headers[0],
            json={"p_session_id": browser_sid, "p_questions": [question]}).status_code == 200
        if status.get("_private_file"):
            Path(status["_private_file"]).write_text(json.dumps({"accounts": accounts,
                "session_id": browser_sid}), encoding="utf-8")
        check_backend(status, tokens, sid, assertions)
        extra = client.post("/rest/v1/exam_sessions", headers={**headers[0],
            "Prefer": "return=representation"}, json={"user_id": identities[0], "title": "TASK204 modes algebra"})
        assert extra.status_code == 201
        extra_sid = extra.json()[0]["id"]
        assert client.post("/rest/v1/rpc/replace_source_questions", headers=headers[0],
            json={"p_session_id": extra_sid, "p_questions": [question]}).status_code == 200
        check_backend(status, tokens, extra_sid, assertions, values=True)
        response = client.get("/auth/v1/user", headers={"apikey": anon, "Authorization": "Bearer invalid"})
        assert response.status_code in (401, 403), "Invalid JWT accepted"
        assertions.append("invalid JWT rejected")
    return {"assertions": assertions, "blocked_external_connects": guard.blocked,
            "scope": "Real Auth/PostgREST/backend confirm/readiness including ready modes and []; browser evidence reported separately"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--api-url", help="Loopback gateway URL inside the local Docker network namespace")
    args = parser.parse_args()
    status = json.loads(args.status.read_text(encoding="utf-8-sig"))
    if args.api_url:
        assert_local_url(args.api_url)
        status["API_URL"] = args.api_url
    status["_private_file"] = str(args.output.with_name("browser.private.local.json"))
    result = run(status)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("PASS: local Auth/PostgREST smoke; sanitized report saved")
