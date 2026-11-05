"""Provision separate random databases in the verified no-network test cluster.

Only replaces Docker container launching (CLI absent in this runner). The real
suite's assert_disposable_database guard still executes before all destructive DDL.
"""

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

BASE = "postgresql://postgres@127.0.0.1/task305_isolated"
assert os.environ.get("RUN_TASK305_REAL_DB_TESTS") == "1"
assert os.environ.get("EXAM_TEST_DB_DESTRUCTIVE") == "1"


async def ddl(database, create):
    assert database.startswith("task305_test_") and database.replace("_", "").isalnum()
    conn = await asyncpg.connect(BASE)
    try:
        assert await conn.fetchval("SELECT current_database()") == "task305_isolated"
        await conn.execute(f'{"CREATE" if create else "DROP"} DATABASE "{database}"')
    finally:
        await conn.close()


class TestClusterPlugin:
    @pytest.hookimpl(tryfirst=True)
    def pytest_fixture_setup(self, fixturedef, request):
        if fixturedef.argname != "isolated_pg_dsn":
            return None
        database = "task305_test_" + uuid4().hex
        asyncio.run(ddl(database, True))
        request.addfinalizer(lambda: asyncio.run(ddl(database, False)))
        result = BASE.rsplit("/", 1)[0] + "/" + database, database
        fixturedef.cached_result = (result, fixturedef.cache_key(request), None)
        return result


raise SystemExit(
    pytest.main(
        [
            "tests/services/test_finalize_real_db_integration.py",
            "tests/services/test_review_real_db_integration.py",
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
        ],
        plugins=[TestClusterPlugin()],
    )
)
