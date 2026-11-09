import json
import sys
from pathlib import Path
from local_transport import assert_local_url
if len(sys.argv) != 2:
    raise SystemExit('Usage: prepare_app.py <local-evidence-directory>')
root = Path(sys.argv[1]).resolve()
status = json.loads((root / "status.private.local.json").read_text(encoding="utf-8-sig"))
assert_local_url(status["API_URL"])
config = {"services": {
    "backend": {"networks": ["p4"], "environment": {"SUPABASE_URL": "http://supabase-local:8000",
        "SUPABASE_ANON_KEY": status["ANON_KEY"], "SUPABASE_SERVICE_ROLE_KEY": status["SERVICE_ROLE_KEY"]}},
    "frontend": {"networks": ["default", "p4"], "environment": {"VITE_SUPABASE_URL": "http://127.0.0.1:55421",
        "VITE_SUPABASE_PUBLISHABLE_KEY": status["ANON_KEY"]}}
}, "networks": {"p4": {"external": True, "name": "exam-tv1-p4-isolated"}}}
(root / "app-p4.private.local.json").write_text(json.dumps(config), encoding="utf-8")
print("Local-only app override prepared; no credentials printed")
