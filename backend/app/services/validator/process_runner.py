"""
Isolated Process Runner with Hard Timeout and Resource Reclamation.

Executes a function in a separate, isolated OS process with a strict timeout.
Ensures thorough process cleanup (terminate -> kill -> join) upon timeout,
preventing GIL deadlocks, IPC pipe deadlocks, and orphan background tasks.
"""

import logging
import multiprocessing
import queue
import threading
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
    *,
    start_method: str | None = None,
    cancel_signal: threading.Event | None = None,
) -> ProcessResult:
    """
    Run `target_func(*args, **kwargs)` inside an isolated process with a hard timeout.

    Guarantees:
    - Reads from IPC queue before waiting on process join, preventing pipe buffer deadlocks
      on large payloads (>64-128 KiB).
    - If execution finishes within timeout, returns ProcessResult with `success=True/False`.
    - Always reaps and guarantees termination of worker processes in every branch (success,
      timeout, error), preventing orphan processes or zombie threads.
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
    ctx = multiprocessing.get_context(start_method)
    res_queue = ctx.Queue()

    process = ctx.Process(  # type: ignore[attr-defined]
        target=_worker_wrapper,
        args=(target_func, args, kwargs, res_queue),
        daemon=True,
    )

    got_result = False
    result_tuple = None
    cancelled = False
    timed_out = False
    worker_error: str | None = None
    started = False

    try:
        if cancel_signal is not None and cancel_signal.is_set():
            return ProcessResult(success=False, error="Execution cancelled before start.")
        process.start()
        started = True

        # Read before joining: a large result can block the worker on the queue.
        # Polling is opt-in so an async caller can stop the actual process promptly.
        while not got_result:
            if cancel_signal is not None and cancel_signal.is_set():
                cancelled = True
                break
            remaining = timeout - (time.perf_counter() - start_time)
            if remaining <= 0:
                timed_out = True
                break
            try:
                result_tuple = res_queue.get(
                    timeout=min(remaining, 0.05) if cancel_signal is not None else remaining
                )
                got_result = True
            except queue.Empty:
                if not process.is_alive():
                    worker_error = "Worker exited without returning a result."
                    break
            except (EOFError, OSError, ValueError) as exc:
                worker_error = f"Worker result could not be read: {exc}"
                break

        elapsed = time.perf_counter() - start_time
        if got_result and elapsed > timeout:
            timed_out = True

        # Do not report completion until the OS worker has actually stopped.
        process.join(timeout=0.5 if got_result else 0)
        if process.is_alive():
            logger.warning("Stopping validation process %s.", process.pid)
            process.terminate()
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.5)
        if process.is_alive():
            raise RuntimeError(f"Validation process {process.pid} could not be reaped.")

        exit_code = process.exitcode
        duration = time.perf_counter() - start_time
        if cancelled:
            return ProcessResult(
                success=False,
                error="Execution cancelled.",
                duration_sec=duration,
                exit_code=exit_code,
                metadata={"pid": process.pid},
            )
        if timed_out:
            return ProcessResult(
                success=False,
                timed_out=True,
                error=f"Execution timed out after {timeout:.1f}s.",
                duration_sec=duration,
                exit_code=exit_code,
                metadata={"pid": process.pid},
            )

        if result_tuple is not None:
            success, data, err = result_tuple
            return ProcessResult(
                success=success,
                data=data,
                error=err,
                timed_out=False,
                duration_sec=duration,
                exit_code=exit_code,
                metadata={"pid": process.pid},
            )

        # Fallback in case result was placed just as process exited
        try:
            success, data, err = res_queue.get(timeout=0.2)
            return ProcessResult(
                success=success,
                data=data,
                error=err,
                timed_out=False,
                duration_sec=duration,
                exit_code=exit_code,
            )
        except (queue.Empty, EOFError, OSError, ValueError) as exc:
            err_msg = (
                worker_error
                or f"Process terminated with exit code {exit_code} without returning data: {exc}"
            )
            return ProcessResult(
                success=False,
                timed_out=False,
                error=err_msg,
                duration_sec=duration,
                exit_code=exit_code,
                metadata={"pid": process.pid},
            )

    finally:
        if started and process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.5)
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
