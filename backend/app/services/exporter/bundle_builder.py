"""Build a bounded in-memory archive; no database, Gemini, cloud or subprocesses."""

import hashlib
from collections.abc import Mapping
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .bundle_models import ApprovedExportSnapshot, BundleArtifact, BundleBuildError
from .source_renderer import render_markdown, render_tex

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_BUNDLE_BYTES = 100 * 1024 * 1024

COMPILE_README = """Hướng dẫn biên dịch
===================
Các file exam_*.tex dùng XeLaTeX, UTF-8 không BOM.
TeX Live đầy đủ hoặc Overleaf: chọn compiler XeLaTeX.
Font: TeX Gyre Termes. Packages: fontspec, amsmath, amssymb, geometry, enumitem.
Lệnh: xelatex -no-shell-escape -interaction=nonstopmode exam_101.tex
Đổi 101 theo mã đề cần biên dịch. Không dùng pdfLaTeX.
Mỗi file gồm đề ở đầu, đáp án và lời giải ở phần sau.
"""


def required_pdf_names(snapshot: ApprovedExportSnapshot) -> set[str]:
    return {"answers_matrix.pdf"} | {
        f"{kind}_{version.code}.pdf" for version in snapshot.versions for kind in ("exam", "solutions")
    }


def build_bundle(snapshot: ApprovedExportSnapshot, pdf_artifacts: Mapping[str, bytes]) -> BundleArtifact:
    """PDF mapping uses basenames, not paths. Input bytes remain caller-owned.

    Returns immutable bytes with no temporary file cleanup needed by the caller.
    PDF checks screen structure, not layout/content correctness.
    """
    snapshot = ApprovedExportSnapshot.model_validate(snapshot.model_dump())
    expected = required_pdf_names(snapshot)
    if set(pdf_artifacts) != expected:
        raise BundleBuildError("EXPORT_PDF_MANIFEST_MISMATCH")
    entries: dict[str, bytes] = {}
    size = 0

    def add(name: str, data: bytes) -> None:
        nonlocal size
        size += len(data)
        if size > MAX_BUNDLE_BYTES:
            raise BundleBuildError("EXPORT_BUNDLE_TOO_LARGE")
        entries[name] = data

    for name in sorted(expected):
        pdf = pdf_artifacts[name]
        if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-1024:]:
            raise BundleBuildError("EXPORT_PDF_INVALID")
        if len(pdf) > MAX_PDF_BYTES:
            raise BundleBuildError("EXPORT_PDF_TOO_LARGE")
        add(f"pdf/{name}", pdf)
    for version in snapshot.versions:
        add(f"latex/exam_{version.code}.tex", render_tex(snapshot, version).encode("utf-8"))
        add(f"markdown/exam_{version.code}.md", render_markdown(snapshot, version).encode("utf-8"))
    add("latex/README_huong_dan_bien_dich.txt", COMPILE_README.encode("utf-8"))
    add("README.txt", (
        f"{snapshot.title}\nSession: {snapshot.session_id}\nRevision: {snapshot.revision}\n"
        "pdf/: đề, ma trận đáp án và lời giải PDF.\n"
        "latex/: nguồn XeLaTeX độc lập. markdown/: đề, đáp án và lời giải Markdown.\n"
        "Nội dung theo thứ tự câu/options/key/lời giải đã duyệt sau shuffle.\n"
    ).encode("utf-8"))
    root = f"exam_bundle_{snapshot.session_id}"
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = ZipInfo(f"{root}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    payload = output.getvalue()
    if len(payload) > MAX_BUNDLE_BYTES:
        raise BundleBuildError("EXPORT_BUNDLE_TOO_LARGE")
    return BundleArtifact(filename=f"{root}.zip", data=payload, sha256=hashlib.sha256(payload).hexdigest())
