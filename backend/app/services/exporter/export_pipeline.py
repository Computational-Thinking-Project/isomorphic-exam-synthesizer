"""Compile and package one locked display snapshot, without database or cloud access."""

from .bundle_builder import build_bundle
from .bundle_models import ApprovedExportSnapshot, BundleArtifact, revalidate_snapshot
from .typst_compiler import TypstCompiler, generate_pdf_filename


def build_compiled_bundle(
    snapshot: ApprovedExportSnapshot,
    *,
    compiler: TypstCompiler | None = None,
) -> BundleArtifact:
    """Build one combined PDF and source pair per validated display version.

    This synchronous function runs subprocesses; async API callers should use
    asyncio.to_thread. The caller owns authorization and the locked DB snapshot.
    Compiler/bundler errors propagate; no partial archive is returned or uploaded.
    """
    snapshot = revalidate_snapshot(snapshot)
    compiler = compiler if compiler is not None else TypstCompiler()
    pdfs: dict[str, bytes] = {}

    for version in snapshot.versions:
        # Only validated display fields enter the compiler, never canonical fallbacks.
        questions = [question.model_dump(mode="json") for question in version.questions]
        exam_name = generate_pdf_filename("exam", version.code)
        pdfs[exam_name] = compiler.compile_document(
            compiler.render_combined_document(version.code, questions, exam_title=snapshot.title),
            exam_name,
        )
    return build_bundle(snapshot, pdfs)
