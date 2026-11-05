import traceback
from fastapi.testclient import TestClient
from app.main import app
from tests.api.test_confirm_source import flow
import pytest

class Runner:
    pass

gen = flow(pytest.MonkeyPatch())
state, client = next(gen)

try:
    res = client.post(f"/api/sessions/{state.sid}/confirm-source", json={})
    print("STATUS:", res.status_code)
    print("BODY:", res.text)
except Exception:
    traceback.print_exc()

