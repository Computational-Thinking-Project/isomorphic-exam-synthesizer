"""
Isolated Process Runner with Hard Timeout and Resource Reclamation.

Executes a function in a separate, isolated OS process with a strict timeout.
Ensures thorough process cleanup (terminate -> kill -> join) upon timeout,
preventing GIL deadlocks, IPC pipe deadlocks, and orphan background tasks.
"""

import logging
import multiprocessing
import queue
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS: float = 5.0


@dataclass
class ProcessResult:
    """Outcome of an isolated process execution."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    timed_out: bool = False
    duration_sec: float = 0.0
    exit_code: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _worker_wrapper(
    target_func: Callable,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    result_queue: Any,
) -> None:
    """
    Top-level worker entrypoint for multiprocessing.
    Executes the target function and places the serialized result in the queue.
    """
    try:
        result = target_func(*args, **kwargs)
        result_queue.put((True, result, None))
    except Exception as exc:
        result_queue.put((False, None, f"{type(exc).__name__}: {str(exc)}"))


def run_with_timeout(
    target_func: Callable,
    args: Tuple[Any, ...] = (),
    kwargs: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProcessResult:
    """
    Run `target_func(*args, **kwargs)` inside an isolated process with a hard timeout.

    Guarantees:
    - Reads from IPC queue before waiting on process join, preventing pipe buffer deadlocks
      on large payloads (>64-128 KiB).
    - If execution finishes within timeout, returns ProcessResult with `success=True/False`.
    - If execution exceeds timeout:
        1. Calls `process.terminate()`
        2. Waits up to 0.5s
        3. Calls `process.kill()` if still running
        4. Calls `process.join()` to avoid zombie/leaked processes
        5. Returns ProcessResult with `timed_out=True`.
    """
    if kwargs is None:
        kwargs = {}

    start_time = time.perf_counter()
    ctx = multiprocessing.get_context()
    res_queue = ctx.Queue()

    process = ctx.Process(
        target=_worker_wrapper,
        args=(target_func, args, kwargs, res_queue),
        daemon=True,
    )

    got_result = False
    result_tuple = None

    try:
        process.start()

        # Step 1: Read from queue before waiting on join to avoid IPC pipe buffer deadlock.
        # If payload is large (>64-128 KiB), the worker blocks on put() until parent reads.
        try:
            result_tuple = res_queue.get(timeout=timeout)
            got_result = True
        except (queue.Empty, Exception):
            pass

        # Step 2: Join process with remaining timeout
        elapsed = time.perf_counter() - start_time
        remaining = max(0.1, timeout - elapsed)
        process.join(timeout=1.0 if got_result else remaining)
        duration = time.perf_counter() - start_time

        if process.is_alive():
            logger.warning(
                "Process %s timed out after %.2fs. Initiating termination/kill cleanup.",
                process.pid,
                timeout,
            )
            # 1. Graceful termination
            process.terminate()
            process.join(timeout=0.5)

            # 2. Forceful kill if still alive
            if process.is_alive():
                process.kill()
                process.join(timeout=0.5)

            # 3. Final join
            process.join()

            return ProcessResult(
                success=False,
                timed_out=True,
                error=f"Execution timed out after {timeout:.1f}s.",
                duration_sec=duration,
                exit_code=process.exitcode,
            )

        # Process finished within timeout
        exit_code = process.exitcode
        duration = time.perf_counter() - start_time

        if got_result and result_tuple is not None:
            success, data, err = result_tuple
            return ProcessResult(
                success=success,
                data=data,
                error=err,
                timed_out=False,
                duration_sec=duration,
                exit_code=exit_code,
            )

        # If result wasn't retrieved earlier, try reading now with short timeout
        try:
            success, data, err = res_queue.get(timeout=0.5)
            return ProcessResult(
                success=success,
                data=data,
                error=err,
                timed_out=False,
                duration_sec=duration,
                exit_code=exit_code,
            )
        except (queue.Empty, Exception) as exc:
            err_msg = f"Process terminated with exit code {exit_code} without returning data: {exc}"
            return ProcessResult(
                success=False,
                timed_out=False,
                error=err_msg,
                duration_sec=duration,
                exit_code=exit_code,
            )

    finally:
        try:
            res_queue.close()
            res_queue.cancel_join_thread()
        except Exception:
            pass

        if hasattr(process, "close"):
            try:
                process.close()
            except Exception:
                pass
