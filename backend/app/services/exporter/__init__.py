"""
Typst Exporter Package (TASK-306).

Exports Typst PDF compiler service, document rendering functions,
LaTeX/Markdown content converters, and custom exporter exceptions.
"""

from app.services.exporter.exceptions import (
    ExporterError,
    TypstCompilationError,
    TypstNotFoundError,
    TypstTimeoutError,
)
from app.services.exporter.typst_compiler import (
    DEFAULT_TIMEOUT_SECONDS,
    PDF_MAGIC_BYTES,
    TypstCompiler,
    generate_pdf_filename,
    sanitize_compiler_error,
)
from app.services.exporter.typst_converter import (
    convert_markdown_to_typst,
    escape_typst_text,
    latex_math_to_typst,
)

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "ExporterError",
    "PDF_MAGIC_BYTES",
    "TypstCompilationError",
    "TypstCompiler",
    "TypstNotFoundError",
    "TypstTimeoutError",
    "convert_markdown_to_typst",
    "escape_typst_text",
    "generate_pdf_filename",
    "latex_math_to_typst",
    "sanitize_compiler_error",
]
