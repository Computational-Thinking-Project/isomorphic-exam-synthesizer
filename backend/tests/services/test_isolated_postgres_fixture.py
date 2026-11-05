"""Safety checks for the disposable PostgreSQL fixture without a database."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.services.isolated_postgres import assert_disposable_database, isolated_pg_dsn


def test_no_opt_in_never_starts_docker(monkeypatch):
    monkeypatch.delenv("RUN_TASK305_REAL_DB_TESTS", raising=False)
    monkeypatch.setenv("PG_TEST_DSN", "postgresql://example.invalid/postgres")
    with patch("tests.services.isolated_postgres.subprocess.run") as run:
        with pytest.raises(pytest.skip.Exception):
            next(isolated_pg_dsn.__wrapped__())
        run.assert_not_called()


def test_setup_failure_cleans_only_its_random_container(monkeypatch):
    monkeypatch.setenv("RUN_TASK305_REAL_DB_TESTS", "1")
    monkeypatch.setenv("EXAM_TEST_DB_DESTRUCTIVE", "1")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise RuntimeError("injected container startup failure")
        return SimpleNamespace(returncode=0, stdout="")

    with (
        patch("tests.services.isolated_postgres.shutil.which", return_value="docker"),
        patch("tests.services.isolated_postgres.subprocess.run", side_effect=run),
    ):
        with pytest.raises(RuntimeError, match="injected"):
            next(isolated_pg_dsn.__wrapped__())
    assert calls[0][calls[0].index("--name") + 1].startswith("task305-test-")
    assert calls[1] == ["docker", "rm", "--force", calls[0][calls[0].index("--name") + 1]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actual, expected, opt_in",
    [
        ("postgres", "postgres", "1"),
        ("postgres", "task305_test_abc", "1"),
        ("task305_test_abc", "task305_test_abc", "0"),
    ],
)
async def test_database_guard_rejects_unsafe_targets(monkeypatch, actual, expected, opt_in):
    monkeypatch.setenv("EXAM_TEST_DB_DESTRUCTIVE", opt_in)

    class Connection:
        async def fetchval(self, query):
            assert query == "SELECT current_database()"
            return actual

    with pytest.raises(RuntimeError):
        await assert_disposable_database(Connection(), expected)
