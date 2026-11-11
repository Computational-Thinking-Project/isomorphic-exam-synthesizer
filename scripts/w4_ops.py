"""Read-only W4 preflight/smoke; reports are observations, never G0/G1/G2 acceptance."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def command(args):
    """Do not expose command output: Compose diagnostics may contain env values."""
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
        return result.returncode == 0, result.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def preflight():
    checks = []
    docker = shutil.which("docker")
    checks.append({"name": "docker_cli", "result": "PASS" if docker else "BLOCKED"})
    if docker:
        for name, args in [
            ("linux_engine", [docker, "info", "--format", "{{.OSType}}"]),
            ("compose", [docker, "compose", "version", "--short"]),
        ]:
            ok, output = command(args)
            version = re.search(r"(\d+)\.(\d+)\.(\d+)", output)
            ok = ok and (output == "linux" if name == "linux_engine" else
                         version is not None and tuple(map(int, version.groups())) >= (2, 24, 4))
            checks.append({"name": name, "result": "PASS" if ok else "BLOCKED"})
    env_exists = (ROOT / ".env").is_file()
    checks.append({"name": "env_file_exists_not_validated", "result": "PASS" if env_exists else "BLOCKED"})
    if docker and env_exists:
        ok, _ = command([docker, "compose", "config", "--quiet"])
        checks.append({"name": "static_compose_config", "result": "PASS" if ok else "FAIL"})
    else:
        checks.append({"name": "static_compose_config", "result": "BLOCKED"})
    return checks


def origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise argparse.ArgumentTypeError("Use an HTTP(S) origin without credentials, path, query or fragment")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(name, url, health=False, openapi=False):
    try:
        # Never follow redirects to OAuth or retain response bodies/headers in reports.
        with build_opener(NoRedirect).open(Request(url), timeout=10) as response:
            body = response.read(1024 * 1024).decode("utf-8", errors="replace")
            content_type = response.headers.get("Content-Type", "").lower()
            if openapi:
                schema = json.loads(body)
                paths = schema.get("paths", {})
                valid = ("application/json" in content_type
                         and isinstance(schema.get("openapi"), str)
                         and schema["openapi"].startswith("3.")
                         and isinstance(paths, dict)
                         and all(isinstance(paths.get(path), dict)
                                 and isinstance(paths[path].get("get"), dict)
                                 for path in ("/health", "/api/sessions")))
            else:
                valid = (json.loads(body).get("status") == "healthy" if health
                         else "text/html" in content_type and "<html" in body.lower())
            return {"name": name, "result": "PASS" if response.status == 200 and valid else "FAIL",
                    "http_status": response.status}
    except HTTPError as error:
        return {"name": name, "result": "FAIL", "http_status": error.code}
    except (OSError, URLError, ValueError, AttributeError):
        return {"name": name, "result": "FAIL"}


def smoke(backend, frontend):
    return [probe("backend_health", backend + "/health", health=True),
            probe("frontend_html", frontend + "/"),
            probe("spa_login_deep_link", frontend + "/login"),
            probe("backend_proxy_openapi", frontend + "/openapi.json", openapi=True)]


def report(action, checks, deployed_sha=None, zip_path=None):
    ok, sha = command(["git", "rev-parse", "HEAD"])
    artifact = None
    if zip_path:
        digest = hashlib.sha256()
        with zip_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        artifact = {"sha256": digest.hexdigest(), "bytes": zip_path.stat().st_size,
                    "contents_and_six_slots": "NOT_VERIFIED"}
    result = "FAIL" if any(c["result"] == "FAIL" for c in checks) else (
        "BLOCKED" if any(c["result"] == "BLOCKED" for c in checks) else "PASS")
    return {"schema_version": 1, "action": action, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "checkout_sha": sha if ok else None, "operator_supplied_deployed_sha": deployed_sha,
            "result": result, "checks": checks, "artifact": artifact,
            "integrated_acceptance": "NOT_VERIFIED",
            "manual_evidence_required": ["DB ledger", "prompt/model/config versions", "OAuth/ownership",
                                         "SSE/restart", "8 demo steps", "6-slot key/solution comparison",
                                         "Storage/download", "Duy acceptance"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "smoke"])
    parser.add_argument("--backend", type=origin, default="http://localhost:8000")
    parser.add_argument("--frontend", type=origin, default="http://localhost:3000")
    parser.add_argument("--deployed-sha", help="Operator supplied; not inferred from checkout")
    parser.add_argument("--zip", type=Path, dest="zip_path", help="Hash an existing export; does not validate contents")
    parser.add_argument("--output", type=Path, required=True, help="New JSON report; existing files are never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    if args.deployed_sha and (len(args.deployed_sha) != 40 or any(c not in "0123456789abcdef" for c in args.deployed_sha)):
        parser.error("deployed-sha must be a full lowercase Git SHA")
    if args.zip_path and not args.zip_path.is_file():
        parser.error("ZIP artifact does not exist")
    checks = preflight() if args.action == "preflight" else smoke(args.backend, args.frontend)
    data = report(args.action, checks, args.deployed_sha, args.zip_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    print(f"{args.action}: {data['result']}; integrated acceptance: NOT_VERIFIED")
    return 0 if data["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
