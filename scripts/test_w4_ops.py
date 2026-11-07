"""Isolated OPS checks; these tests do not certify a deployment."""

import argparse
import json
import tempfile
import unittest
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
