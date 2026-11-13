"""Thread-safe counters with explicit startup and bounded active-handle storage."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RuntimeActivitySnapshot:
    uptime_seconds: float
    active_sse_connections: int
    gemini_call_count: int
    gemini_error_rate: float
    background_jobs_running: int


@dataclass(frozen=True, slots=True)
class RuntimeActivityHandle:
    _release: Callable[[], None]

    def close(self) -> None:
        """Release in finally; repeated/concurrent cleanup is harmless."""
        self._release()


@dataclass(frozen=True, slots=True)
class GeminiAttemptHandle:
    _complete: Callable[[bool | None], None]

    def finish(self, *, failed: bool) -> None:
        """Record a known provider outcome once, independently of local validation."""
        if type(failed) is not bool:
            raise TypeError("A provider outcome must be an explicit boolean.")
        self._complete(failed)

    def abandon(self) -> None:
        """Release an unknown outcome without inventing a completed provider result."""
        self._complete(None)


class RuntimeRegistry:
    """Create once per app/worker and start from its lifespan, never on each request.

    Methods use short synchronous locks and can be called from threads or async
    code. Producers retain handles across their I/O and release them in finally;
    no lock is retained by those handles. This class does not prevent duplicate
    generation jobs or decide which SDK outcomes/retries belong to an attempt.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._started_at: float | None = None
        self._connections: set[object] = set()
        self._jobs: dict[UUID, set[object]] = {}
        self._attempts: set[object] = set()
        self._attempt_count = 0
        self._completed_count = 0
        self._failed_count = 0

    def _read_clock(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("The runtime clock must return a finite number.")
        return float(value)

    def _require_started(self) -> float:
        # The caller holds _lock. None distinguishes not-started from a valid zero.
        if self._started_at is None:
            raise RuntimeError("The runtime registry has not been started.")
        return self._started_at

    def start(self) -> None:
        with self._lock:
            if self._started_at is not None:
                return
        started_at = self._read_clock()
        with self._lock:
            if self._started_at is None:
                self._started_at = started_at

    def begin_sse_connection(self) -> RuntimeActivityHandle:
        token = object()
        with self._lock:
            self._require_started()
            self._connections.add(token)
        return RuntimeActivityHandle(lambda: self._close_connection(token))

    def _close_connection(self, token: object) -> None:
        with self._lock:
            self._connections.discard(token)

    def begin_job(self, session_id: UUID) -> RuntimeActivityHandle:
        if not isinstance(session_id, UUID):
            raise TypeError("A job session must be identified by a UUID.")
        token = object()
        with self._lock:
            self._require_started()
            self._jobs.setdefault(session_id, set()).add(token)
        return RuntimeActivityHandle(lambda: self._close_job(session_id, token))

    def _close_job(self, session_id: UUID, token: object) -> None:
        with self._lock:
            handles = self._jobs.get(session_id)
            if handles is None:
                return
            handles.discard(token)
            if not handles:
                del self._jobs[session_id]

    def begin_gemini_attempt(self) -> GeminiAttemptHandle:
        token = object()
        with self._lock:
            self._require_started()
            self._attempts.add(token)
            self._attempt_count += 1
        return GeminiAttemptHandle(lambda failed: self._finish_attempt(token, failed))

    def _finish_attempt(self, token: object, failed: bool | None) -> None:
        with self._lock:
            if token not in self._attempts:
                return
            self._attempts.remove(token)
            if failed is not None:
                self._completed_count += 1
                self._failed_count += int(failed)

    def snapshot(self) -> RuntimeActivitySnapshot:
        with self._lock:
            started_at = self._require_started()
        # The injectable clock is called outside the lock, as are all producer I/O.
        elapsed = self._read_clock() - started_at
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("The runtime clock produced an invalid elapsed time.")
        with self._lock:
            return RuntimeActivitySnapshot(
                uptime_seconds=elapsed,
                active_sse_connections=len(self._connections),
                gemini_call_count=self._attempt_count,
                gemini_error_rate=(
                    self._failed_count / self._completed_count if self._completed_count else 0.0
                ),
                background_jobs_running=len(self._jobs),
            )
