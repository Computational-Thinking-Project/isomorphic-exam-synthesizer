"""Current Q01/Q02 HTTP + producer + real SQL, with zero external AI requests."""

import os
import socket
import unittest
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import httpx
import test_source_confirmation_revision as revision_fixtures
from test_review_rpcs import OWNER, SID


class NoAIIntegrationTests(revision_fixtures.SourceRevisionTests):
    def test_http_pending_running_failed_retry_ready_replay_no_outbound(self):
        from fastapi.testclient import TestClient
        from sql_client_fixture import SqlClient

        from app.api.dependencies import get_current_user, get_service_db, get_user_db
        from app.api.routes import source_artifacts
        from app.main import app
        from app.models.schemas import CurrentUser
        from app.services.ai.gateway import GeminiGateway

        case, extracts, outbound = self, [], []
        owner, worker = SqlClient(self), SqlClient(self, True)
        rpc = worker.rpc
        lost_read = [True]

        def worker_rpc(name, params):
            if name == "get_source_artifacts" and lost_read[0]:
                lost_read[0] = False

                def lost():
                    raise ConnectionError("Injected postcommit response loss")

                from types import SimpleNamespace

                return SimpleNamespace(execute=lost)
            return rpc(name, params)

        worker.rpc = worker_rpc

        class Extractor:
            async def extract_confirmed(self, items, **kwargs):
                extracts.append(deepcopy(items))
                return [{"blueprint": deepcopy(case.blueprint)}], []

        def blocked(*args, **kwargs):
            outbound.append("blocked")
            raise AssertionError("External AI/network transport is forbidden")

        async def blocked_async(*args, **kwargs):
            blocked(*args, **kwargs)

        connect = socket.socket.connect

        def guarded_connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                blocked()
            return connect(sock, address)

        previous = app.dependency_overrides.copy()
        app.dependency_overrides.update(
            {
                get_current_user: lambda: CurrentUser(
                    id=OWNER,
                    email="fixture@example.invalid",
                    name="Fixture",
                    access_token="fixture",
                ),
                get_user_db: lambda: owner,
                get_service_db: lambda: worker,
            }
        )
        try:
            with (
                patch.dict(os.environ, {"GEMINI_API_KEY": "", "GEMINI_API_KEYS": ""}),
                patch.object(GeminiGateway, "generate_content", blocked_async),
                patch.object(httpx.HTTPTransport, "handle_request", blocked),
                patch.object(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async),
                patch.object(socket.socket, "connect", guarded_connect),
                patch.object(source_artifacts, "blueprint_service", return_value=None) as provider,
                TestClient(app) as client,
            ):
                if hasattr(app.state, "limiter"):
                    app.state.limiter._storage.reset()
                base = f"/api/sessions/{SID}"
                preview = client.get(base)
                self.assertEqual(preview.status_code, 200, preview.text)
                body = {"source_revision": preview.json()["source_revision"]}
                key = {"Idempotency-Key": str(uuid4())}
                self.sql("UPDATE source_questions SET has_security_warning=true;")
                stale = client.post(base + "/confirm-source", json=body, headers=key)
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertEqual(stale.json()["error_code"], "ERR_SOURCE_REVISION_CONFLICT")
                self.assertEqual(
                    self.value("SELECT count(*) FROM source_artifact_confirmations;"), "0"
                )
                body = {"source_revision": client.get(base).json()["source_revision"]}
                uncertain = client.post(base + "/confirm-source", json=body, headers=key)
                self.assertEqual(uncertain.status_code, 503, uncertain.text)
                self.assertEqual(
                    self.value("SELECT count(*) FROM source_artifact_confirmations;"), "1"
                )
                response = client.post(base + "/confirm-source", json=body, headers=key)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["canonical_status"], "pending")
                self.assertEqual(extracts, [])
                state = client.get(base + "/source-artifacts").json()
                self.assertFalse(state["ready"])
                self.assertIsNone(state["supported_modes"])
                revision = self.value("SELECT source_revision_id FROM source_artifact_heads;")
                job = str(uuid4())
                self.call("claim_source_production", SID, revision, job)
                self.assertEqual(
                    client.get(base + "/source-artifacts").json()["canonical_status"], "running"
                )
                self.call("fail_source_production", SID, revision, job, "FIXTURE_FAILURE")
                self.assertEqual(
                    client.get(base + "/source-artifacts").json()["canonical_status"], "failed"
                )
                provider.return_value = Extractor()
                retry = client.post(base + "/source-artifacts/retry")
                self.assertEqual(retry.status_code, 202, retry.text)
                ready = client.get(base + "/source-artifacts")
                self.assertEqual(ready.status_code, 200, ready.text)
                self.assertTrue(ready.json()["ready"])
                self.assertEqual(
                    [m["id"] for m in ready.json()["supported_modes"]],
                    ["NUMERICAL", "context_swap", "parameter_variation"],
                )
                self.assertEqual(len(extracts), 1)
                replay = client.post(base + "/confirm-source", json=body, headers=key)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(
                    replay.json()["confirmation_id"], response.json()["confirmation_id"]
                )
                self.assertEqual(len(extracts), 1)
                self.assertEqual(outbound, [])
                self.assertEqual(
                    self.value("SELECT count(*) FROM canonical_blueprint_revisions;"), "1"
                )
                self.assertEqual(self.value("SELECT count(*) FROM security_events;"), "1")
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        NoAIIntegrationTests(name)
        for name in sorted(NoAIIntegrationTests.__dict__)
        if name.startswith("test_")
    )
