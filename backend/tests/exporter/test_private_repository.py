"""Adversarial receipt/SDK failures; real SQL behavior has separate PG tests."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from storage3.exceptions import StorageApiError

from app.services.exporter.private_models import ExportFailure, ExportIdentity, ReadyExport
from app.services.exporter.private_repository import SupabaseExportLedger
from app.services.exporter.private_storage import SupabasePrivateExportStore

IDENTITY = ExportIdentity(UUID(int=1), UUID(int=2), "sha256:" + "a" * 64, "b" * 64)


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {"state": "unknown"},
        {"state": "claimed"},
        {"state": "ready", "receipt": {}},
        {"state": "failed", "error_code": "secret provider exception"},
        {"state": "ready", "token": "invalid", "receipt": {}},
    ],
)
def test_malformed_rpc_receipts_do_not_become_success(response):
    client = Mock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=response)
    with pytest.raises(ExportFailure, match="ERR_EXPORT_METADATA_INVALID"):
        SupabaseExportLedger(client).claim(IDENTITY)


@pytest.mark.parametrize(
    "status,code,missing",
    [
        (404, "NoSuchKey", True),
        ("404", "NoSuchKey", True),
        (404, "NoSuchBucket", False),
        (404, "AccessDenied", False),
        (404, "not_found", False),
        (404, "InternalError", False),
        (403, "NoSuchKey", False),
        (500, "NoSuchKey", False),
    ],
)
def test_sdk_only_classifies_object_specific_404_as_missing(status, code, missing):
    client = Mock()
    client.storage.from_.return_value.download.side_effect = StorageApiError(
        "sensitive", code, status
    )
    adapter = SupabasePrivateExportStore(client, "private-test")
    artifact = ReadyExport(IDENTITY, "path.zip", "file.zip", "a" * 64, 100)
    expected = ExportFailure if missing else StorageApiError
    with pytest.raises(expected) as err:
        adapter.verify(artifact)
    if missing:
        assert str(err.value) == "ERR_EXPORT_OBJECT_NOT_FOUND"


@pytest.mark.parametrize("state", ["pending", "ready"])
@pytest.mark.parametrize("defect", ["token", "missing_token", "receipt", "missing_receipt"])
def test_checkpoint_ack_requires_matching_token_and_durable_receipt(state, defect):
    from app.services.exporter.private_repository import receipt

    token = UUID(int=3)
    artifact = ReadyExport(IDENTITY, "path.zip", "file.zip", "a" * 64, 100)
    response = {"state": state, "token": str(token), "receipt": receipt(artifact)}
    if defect == "token":
        response["token"] = str(UUID(int=4))
    elif defect == "missing_token":
        response.pop("token")
    elif defect == "receipt":
        response["receipt"] = {**receipt(artifact), "sha256": "b" * 64}
    else:
        response["receipt"] = None
    client = Mock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=response)
    with pytest.raises(ExportFailure, match="ERR_EXPORT_METADATA_INVALID"):
        SupabaseExportLedger(client).record_built(artifact, token)


@pytest.mark.parametrize("state", ["pending", "ready"])
def test_checkpoint_accepts_exact_ack(state):
    from app.services.exporter.private_repository import receipt

    token = UUID(int=3)
    artifact = ReadyExport(IDENTITY, "path.zip", "file.zip", "a" * 64, 100)
    client = Mock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"state": state, "token": str(token), "receipt": receipt(artifact)}
    )
    SupabaseExportLedger(client).record_built(artifact, token)
