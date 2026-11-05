"""Disposable PostgreSQL cluster for the opt-in TASK-305 integration tests."""

import os
import shutil
import subprocess
import time
from uuid import uuid4

import pytest


async def assert_disposable_database(conn, expected_database):
    """Fail before destructive DDL unless this is the provisioned test database."""
    if os.environ.get("EXAM_TEST_DB_DESTRUCTIVE") != "1":
        raise RuntimeError("EXAM_TEST_DB_DESTRUCTIVE=1 is required for destructive test setup")
    actual = await conn.fetchval("SELECT current_database()")
    if not expected_database.startswith("task305_test_") or actual != expected_database:
        raise RuntimeError("refusing to initialize an unexpected database")


@pytest.fixture(scope="module")
def isolated_pg_dsn():
    if os.environ.get("RUN_TASK305_REAL_DB_TESTS") != "1":
        pytest.skip("Set RUN_TASK305_REAL_DB_TESTS=1 to run isolated PostgreSQL tests")
    if os.environ.get("EXAM_TEST_DB_DESTRUCTIVE") != "1":
        pytest.skip("Set EXAM_TEST_DB_DESTRUCTIVE=1 to allow disposable database setup")
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI unavailable; no external database will be used")
    token = uuid4().hex
    name = f"task305-test-{token}"
    database = f"task305_test_{token}"

    def run(*args, check=True):
        return subprocess.run(
            [docker, *args], capture_output=True, text=True, check=check, timeout=60
        )

    try:
        run(
            "run",
            "--detach",
            "--name",
            name,
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            f"POSTGRES_DB={database}",
            "postgres:15-alpine",
        )
        for _ in range(60):
            if (
                run(
                    "exec", name, "pg_isready", "-U", "postgres", "-d", database, check=False
                ).returncode
                == 0
            ):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("isolated PostgreSQL container did not become ready")
        port = run("port", name, "5432/tcp").stdout.strip().rsplit(":", 1)[-1]
        if not port.isdigit():
            raise RuntimeError("cannot determine isolated PostgreSQL port")
        yield f"postgresql://postgres@127.0.0.1:{port}/{database}", database
    finally:
        run("rm", "--force", name, check=False)
