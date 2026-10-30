"""Current process RSS for the existing Linux Docker runtime, without dependencies."""

import math
import re
from collections.abc import Callable
from pathlib import Path


class ProcessMemoryUnavailableError(RuntimeError):
    """The current RSS could not be sampled; callers must not substitute zero."""


def _read_self_status() -> str:
    return Path("/proc/self/status").read_text(encoding="ascii")


def read_process_memory_mb(*, read_status: Callable[[], str] = _read_self_status) -> float:
    """Read VmRSS each time, converting KiB to MiB while keeping the W2 field name.

    VmHWM/ru_maxrss are peak memory and must not stand in for the current RSS.
    Unsupported platforms and malformed/unreadable samples are unavailable.
    """
    try:
        status = read_status()
        if not isinstance(status, str):
            raise ValueError("Expected process status text.")
        entries = [line for line in status.splitlines() if line.startswith("VmRSS:")]
        if len(entries) != 1:
            raise ValueError("Expected one current RSS measurement.")
        match = re.fullmatch(r"VmRSS:[ \t]+([0-9]+)[ \t]+kB[ \t]*", entries[0])
        if match is None:
            raise ValueError("Invalid current RSS measurement.")
        memory_mb = int(match.group(1)) / 1024
        if not math.isfinite(memory_mb):
            raise ValueError("Current RSS must be finite.")
        return memory_mb
    except Exception:
        raise ProcessMemoryUnavailableError("Current process memory is unavailable.") from None
