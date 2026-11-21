"""Isolated OPS checks; these tests do not certify a deployment."""

import argparse
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import w4_ops as ops


class OpsTests(unittest.TestCase):
    def test_missing_docker_blocks_config(self):
        with patch.object(ops.shutil, "which", return_value=None):
            checks = ops.preflight()
        self.assertEqual(checks[0]["result"], "BLOCKED")
        self.assertEqual(checks[-1]["result"], "BLOCKED")

    def test_urls_cannot_contain_credentials_or_signed_query(self):
        for url in ["https://user:secret@example.com", "https://example.com?token=secret",
                    "https://example.com/#secret", "file:///tmp/a", "https://example.com/api"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                ops.origin(url)

    def test_health_rejects_html_even_when_http_200(self):
        response = MagicMock(status=200)
        response.read.return_value = b"<html>login</html>"
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch.object(ops, "build_opener", return_value=opener):
            self.assertEqual(ops.probe("health", "http://localhost/health", True)["result"], "FAIL")

    def test_redirect_fails_without_recording_location_or_body(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError("http://localhost", 302, "secret", {"Location": "secret"}, None)
        with patch.object(ops, "build_opener", return_value=opener):
            result = ops.probe("html", "http://localhost")
        self.assertEqual(result, {"name": "html", "result": "FAIL", "http_status": 302})

    def test_proxy_requires_backend_openapi_instead_of_spa_fallback(self):
        schema = {"openapi": "3.1.0", "paths": {
            "/health": {"get": {}}, "/api/sessions": {"get": {}}}}
        cases = [
            ("text/html", b"<html>frontend SPA</html>", "FAIL"),
            ("application/json", b"{}", "FAIL"),
            ("application/json", b"[]", "FAIL"),
            ("application/json", b"not json", "FAIL"),
            ("application/json", json.dumps({**schema, "paths": {}}).encode(), "FAIL"),
            ("application/json", json.dumps(schema).encode(), "PASS"),
        ]
        for content_type, body, expected in cases:
            with self.subTest(body=body):
                response = MagicMock(status=200)
                response.headers = {"Content-Type": content_type}
                response.read.return_value = body
                opener = MagicMock()
                opener.open.return_value.__enter__.return_value = response
                with patch.object(ops, "build_opener", return_value=opener):
                    result = ops.probe("backend_proxy_openapi", "http://frontend/openapi.json",
                                       openapi=True)
                self.assertEqual(result["result"], expected)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, "http://frontend/openapi.json")
                self.assertNotIn("body", result)

    def test_anonymous_auth_requires_401_and_bearer_challenge(self):
        for status, challenge, expected in [
            (401, "Bearer", "PASS"),
            (401, 'Basic realm="local", Bearer realm="api"', "PASS"),
            (401, "bearer", "PASS"),
            (401, "", "FAIL"),
            (401, "BearerInvalid", "FAIL"),
            (401, 'Basic realm="Bearer"', "FAIL"),
            (403, "Bearer", "FAIL"),
            (302, "Bearer", "FAIL"),
        ]:
            with self.subTest(status=status, challenge=challenge):
                headers = Message()
                headers["WWW-Authenticate"] = challenge
                headers["Location"] = "secret-location"
                opener = MagicMock()
                opener.open.side_effect = HTTPError("http://localhost", status, "secret", headers, None)
                with patch.object(ops, "build_opener", return_value=opener):
                    result = ops.anonymous_auth_probe("auth", "http://localhost/api/sessions")
                self.assertEqual(result, {"name": "auth", "result": expected, "http_status": status})

    def test_anonymous_auth_rejects_success_and_connection_failure(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = MagicMock(status=200)
        with patch.object(ops, "build_opener", return_value=opener):
            self.assertEqual(ops.anonymous_auth_probe("auth", "http://localhost")["result"], "FAIL")
        opener.open.side_effect = OSError("secret connection diagnostics")
        with patch.object(ops, "build_opener", return_value=opener):
            self.assertEqual(ops.anonymous_auth_probe("auth", "http://localhost"),
                             {"name": "auth", "result": "FAIL"})

    def test_smoke_checks_auth_on_backend_and_proxy(self):
        with patch.object(ops, "probe", return_value={"result": "PASS"}), patch.object(
            ops, "anonymous_auth_probe", return_value={"result": "PASS"}
        ) as auth:
            self.assertEqual(len(ops.smoke("http://backend", "http://frontend")), 8)
        self.assertEqual([call.args[1] for call in auth.call_args_list], [
            "http://backend/api/sessions", "http://frontend/api/sessions",
            "http://backend/api/health/metrics", "http://frontend/api/health/metrics",
        ])

    def test_report_never_equates_checkout_or_checksum_with_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "sample.zip"
            artifact.write_bytes(b"not even a zip")
            with patch.object(ops, "command", return_value=(True, "a" * 40)):
                result = ops.report("smoke", [{"name": "http", "result": "PASS"}], zip_path=artifact)
        self.assertEqual(result["result"], "PASS")
        self.assertIsNone(result["operator_supplied_deployed_sha"])
        self.assertEqual(result["integrated_acceptance"], "NOT_VERIFIED")
        self.assertEqual(result["artifact"]["contents_and_six_slots"], "NOT_VERIFIED")
        self.assertNotIn("not even", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
