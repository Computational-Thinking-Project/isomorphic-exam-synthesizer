import math
import sys
from pathlib import Path
from typing import cast

import pytest

from app.services.observability.process_memory import (
    ProcessMemoryUnavailableError,
    read_process_memory_mb,
)


@pytest.mark.parametrize("kib,expected", [(0, 0.0), (512, 0.5), (2048, 2.0), (123456, 120.5625)])
def test_reads_current_rss_and_converts_kib_to_mib(kib: int, expected: float) -> None:
    status = f"Name:\tpython\nVmPeak:\t999999 kB\nVmHWM:\t888888 kB\nVmRSS:\t{kib} kB\n"
    assert read_process_memory_mb(read_status=lambda: status) == expected


def test_every_sample_reads_current_data_without_reusing_a_cached_peak() -> None:
    samples = iter(["VmRSS: 4096 kB", "VmRSS: 1024 kB"])
    assert read_process_memory_mb(read_status=lambda: next(samples)) == 4.0
    assert read_process_memory_mb(read_status=lambda: next(samples)) == 1.0


@pytest.mark.parametrize(
    "status",
    [
        "",
        "VmHWM: 2048 kB\nVmSize: 4096 kB",
        "VmRSS: -1024 kB",
        "VmRSS: 1.5 kB",
        "VmRSS: nan kB",
        "VmRSS: inf kB",
        "VmRSS: 1024 MB",
        "VmRSS: 1024",
        "VmRSS: 1024kB",
        "VmRSS: 1024 kB extra",
        "VmRSS: 1024 kB\nVmRSS: 2048 kB",
        "VmRSS: bad\nVmRSS: 2048 kB",
        "VmRSS: " + "9" * 400 + " kB",
    ],
)
def test_invalid_or_missing_current_rss_fails_instead_of_fabricating_zero(status: str) -> None:
    with pytest.raises(
        ProcessMemoryUnavailableError, match="^Current process memory is unavailable.$"
    ):
        read_process_memory_mb(read_status=lambda: status)


@pytest.mark.parametrize("status", [None, 123, True, b"VmRSS: 1024 kB"])
def test_nontext_status_is_unavailable(status: object) -> None:
    with pytest.raises(ProcessMemoryUnavailableError):
        read_process_memory_mb(read_status=lambda: cast(str, status))


@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError, UnicodeError, RuntimeError])
def test_read_failures_have_a_safe_message_without_raw_paths_or_details(
    error: type[Exception],
) -> None:
    def fail() -> str:
        raise error("fixture-private-path-or-provider-detail")

    with pytest.raises(ProcessMemoryUnavailableError) as caught:
        read_process_memory_mb(read_status=fail)
    assert str(caught.value) == "Current process memory is unavailable."
    assert "fixture-private" not in str(caught.value)


def test_default_reader_reads_only_self_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, str]] = []

    def read_text(path: Path, *, encoding: str) -> str:
        calls.append((path, encoding))
        return "VmRSS:\t2048 kB\n"

    monkeypatch.setattr(Path, "read_text", read_text)
    assert read_process_memory_mb() == 2.0
    assert calls == [(Path("/proc/self/status"), "ascii")]


@pytest.mark.skipif(sys.platform != "linux", reason="The initial provider targets Linux Docker.")
def test_linux_reader_smoke_returns_finite_positive_current_rss() -> None:
    result = read_process_memory_mb()
    assert isinstance(result, float)
    assert math.isfinite(result) and result > 0
