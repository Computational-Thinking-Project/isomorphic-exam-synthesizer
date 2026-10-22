"""
Unit tests for Isolated Process Runner with Hard Timeout.
"""

import time

from app.services.validator.process_runner import ProcessResult, run_with_timeout


def _fast_add(a: int, b: int) -> int:
    return a + b


def _slow_task(sleep_sec: float) -> str:
    time.sleep(sleep_sec)
    return "done"


def _failing_task():
    raise ValueError("Explicit test failure.")


def _infinite_loop():
    while True:
        time.sleep(0.05)


class TestProcessRunner:
    def test_fast_execution_success(self):
        result: ProcessResult = run_with_timeout(_fast_add, args=(10, 20), timeout=3.0)
        assert result.success is True
        assert result.data == 30
        assert result.timed_out is False
        assert result.error is None
        assert result.duration_sec >= 0.0

    def test_function_exception_handling(self):
        result: ProcessResult = run_with_timeout(_failing_task, timeout=3.0)
        assert result.success is False
        assert result.timed_out is False
        assert "ValueError" in str(result.error)
        assert "Explicit test failure" in str(result.error)

    def test_hard_timeout_reclamation(self):
        # Set a short timeout (0.3s) on an infinite loop
        start = time.perf_counter()
        result: ProcessResult = run_with_timeout(_infinite_loop, timeout=0.3)
        duration = time.perf_counter() - start

        assert result.success is False
        assert result.timed_out is True
        assert "timed out" in str(result.error).lower()
        # Ensure timeout didn't hang indefinitely (should terminate within ~1s)
        assert duration < 2.0

    def test_slow_task_killed_and_reaped(self):
        # 2-second task with 0.2-second timeout
        result: ProcessResult = run_with_timeout(_slow_task, args=(2.0,), timeout=0.2)
        assert result.timed_out is True
        assert result.success is False
        assert result.exit_code is not None


def _generate_large_payload(size_bytes: int) -> str:
    return "X" * size_bytes


def test_large_payload_no_pipe_buffer_deadlock():
    """Regression test for pipe buffer deadlock when returning large payloads (>128 KiB)."""
    large_size = 256 * 1024  # 256 KiB
    result: ProcessResult = run_with_timeout(_generate_large_payload, args=(large_size,), timeout=5.0)
    assert result.success is True
    assert result.timed_out is False
    assert len(result.data) == large_size
