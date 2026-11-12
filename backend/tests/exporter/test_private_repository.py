"""Adversarial receipt/SDK failures; real SQL behavior has separate PG tests."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from app.services.exporter.private_models import ExportFailure, ExportIdentity, ReadyExport
from app.services.exporter.private_repository import SupabaseExportLedger
from app.services.exporter.private_storage import SupabasePrivateExportStore
from storage3.exceptions import StorageApiError

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
    "status,missing", [(404, True), ("404", True), (403, False), (429, False), (500, False)]
)
def test_sdk_only_classifies_404_as_missing(status, missing):
    client = Mock()
    client.storage.from_.return_value.download.side_effect = StorageApiError(
        "sensitive", "not_found", status
    )
    adapter = SupabasePrivateExportStore(client, "private-test")
    artifact = ReadyExport(IDENTITY, "path.zip", "file.zip", "a" * 64, 100)
    expected = ExportFailure if missing else StorageApiError
    with pytest.raises(expected) as err:
        adapter.verify(artifact)
    if missing:
        assert str(err.value) == "ERR_EXPORT_OBJECT_NOT_FOUND"
