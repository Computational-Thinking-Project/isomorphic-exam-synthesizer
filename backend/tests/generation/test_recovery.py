"""Offline checks for the migration 017 scanner contract."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.generation.recovery import GenerationRecoveryScanner, StaleJobRepository


class FakeRPCClient:
    def __init__(self, pages, receipts):
        self.pages = list(pages)
        self.receipts = list(receipts)
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        values = self.pages if name == "list_stale_generation_jobs" else self.receipts
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=value))


@pytest.mark.asyncio
async def test_scanner_paginates_and_fences_every_candidate():
    jobs = [(str(uuid4()), str(uuid4())) for _ in range(101)]
    stamp = datetime.now(timezone.utc).isoformat()
    first = [
        {"session_id": sid, "job_token": token, "last_activity_at": stamp}
        for sid, token in jobs[:100]
    ]
    last = [{"session_id": jobs[-1][0], "job_token": jobs[-1][1], "last_activity_at": stamp}]
    client = FakeRPCClient(
        [
            {
                "scan_as_of": stamp,
                "cutoff_seconds": 720,
                "items": first,
                "next_cursor": {"last_activity_at": stamp, "session_id": jobs[99][0]},
                "has_more": True,
            },
            {
                "scan_as_of": stamp,
                "cutoff_seconds": 720,
                "items": last,
                "next_cursor": None,
                "has_more": False,
            },
        ],
        [
            {
                "session_id": sid,
                "recovered": True,
                "previous_job_id": token,
                "status": "failed",
                "error_code": "ERR_GENERATION_INTERRUPTED",
            }
            for sid, token in jobs
        ],
    )
    scanner = GenerationRecoveryScanner(StaleJobRepository(client))
    assert await scanner.scan_once() == 100
    assert await scanner.scan_once() == 1
    assert client.calls[0][1] == {"p_cutoff_seconds": 720, "p_limit": 100}
    assert client.calls[101][1]["p_after_session_id"] == jobs[99][0]
    assert client.calls[1][1]["p_expected_job_token"] == jobs[0][1]


@pytest.mark.asyncio
async def test_recovery_race_noop_does_not_count():
    sid, token = str(uuid4()), str(uuid4())
    client = FakeRPCClient(
        [
            {
                "scan_as_of": datetime.now(timezone.utc).isoformat(),
                "cutoff_seconds": 720,
                "items": [
                    {
                        "session_id": sid,
                        "job_token": token,
                        "last_activity_at": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "next_cursor": None,
                "has_more": False,
            }
        ],
        [
            {
                "session_id": sid,
                "recovered": False,
                "current_status": "generated",
                "current_job_id": None,
                "reason": "status_not_generating",
            }
        ],
    )
    assert await GenerationRecoveryScanner(StaleJobRepository(client)).scan_once() == 0


@pytest.mark.asyncio
async def test_scanner_resets_cursor_after_rpc_failure():
    sid, token = str(uuid4()), str(uuid4())
    stamp = datetime.now(timezone.utc).isoformat()
    page = {
        "scan_as_of": stamp,
        "cutoff_seconds": 720,
        "items": [{"session_id": sid, "job_token": token, "last_activity_at": stamp}],
        "next_cursor": {"last_activity_at": stamp, "session_id": sid},
        "has_more": True,
    }
    client = FakeRPCClient(
        [page, RuntimeError("temporary"), page],
        [
            {"session_id": sid, "recovered": False, "reason": "activity_not_stale"},
            {"session_id": sid, "recovered": False, "reason": "token_mismatch"},
        ],
    )
    scanner = GenerationRecoveryScanner(StaleJobRepository(client))
    assert await scanner.scan_once() == 0
    with pytest.raises(RuntimeError):
        await scanner.scan_once()
    assert await scanner.scan_once() == 0
    list_calls = [params for name, params in client.calls if name == "list_stale_generation_jobs"]
    assert "p_after_session_id" in list_calls[1]
    assert "p_after_session_id" not in list_calls[2]
