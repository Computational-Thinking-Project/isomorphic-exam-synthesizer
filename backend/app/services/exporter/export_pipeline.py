"""Compile and package one locked display snapshot, without database or cloud access."""

from .bundle_builder import build_bundle
from .bundle_models import ApprovedExportSnapshot, BundleArtifact, revalidate_snapshot
from .print_layout import ExamMetadata, ExportConfig
from .typst_compiler import TypstCompiler, generate_pdf_filename


def build_compiled_bundle(
    snapshot: ApprovedExportSnapshot,
    *,
    compiler: TypstCompiler | None = None,
    config: ExportConfig | None = None,
    metadata: ExamMetadata | None = None,
) -> BundleArtifact:
    """Build one combined PDF and source pair per validated display version.

    This synchronous function runs subprocesses; async API callers should use
    asyncio.to_thread. The caller owns authorization and the locked DB snapshot.
    Compiler/bundler errors propagate; no partial archive is returned or uploaded.

    ``config=None`` is the MVP/default packager. With a config (EXT-03), only the
    chosen formats are built and PDF uses the configured header when it differs
    from the default; ``metadata`` is the set locked at Approve (null fields omitted).
    """
    snapshot = revalidate_snapshot(snapshot)
    compiler = compiler if compiler is not None else TypstCompiler()
    pdfs: dict[str, bytes] = {}
    build_pdf = config is None or "pdf" in config.formats

    for version in snapshot.versions if build_pdf else ():
        # Only validated display fields enter the compiler, never canonical fallbacks.
        questions = [question.model_dump(mode="json") for question in version.questions]
        exam_name = generate_pdf_filename("exam", version.code)
        if config is not None and config.uses_pdf_template:
            source = compiler.render_configured_document(
                version.code,
                questions,
                exam_title=snapshot.title,
                metadata=metadata if metadata is not None else ExamMetadata(),
                config=config,
            )
        else:
            source = compiler.render_combined_document(
                version.code, questions, exam_title=snapshot.title
            )
        pdfs[exam_name] = compiler.compile_document(source, exam_name)
    return build_bundle(snapshot, pdfs, config=config)
