"""
Custom Exceptions for Typst PDF Exporter Service (TASK-306).
"""

from typing import Optional


class ExporterError(Exception):
    """Base exception for all document export and compilation errors."""


class TypstNotFoundError(ExporterError):
    """Raised when the Typst CLI binary is not installed or not found on PATH."""

    def __init__(
        self,
        binary_path: str = "typst",
        message: Optional[str] = None,
    ) -> None:
        self.binary_path = binary_path
        msg = (
            message
            or f"Typst CLI binary '{binary_path}' not found. Please ensure Typst v0.11.1+ is installed."
        )
        super().__init__(msg)


class TypstCompilationError(ExporterError):
    """Raised when Typst compilation fails with non-zero exit code."""

    def __init__(
        self,
        message: str,
        exit_code: int = 1,
        raw_stderr: Optional[str] = None,
    ) -> None:
        self.exit_code = exit_code
        self.raw_stderr = raw_stderr
        super().__init__(message)


class TypstTimeoutError(ExporterError):
    """Raised when Typst compilation exceeds the maximum execution timeout budget."""

    def __init__(
        self,
        timeout_seconds: float,
        message: Optional[str] = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        msg = message or f"Typst compilation timed out after {timeout_seconds} seconds."
        super().__init__(msg)
