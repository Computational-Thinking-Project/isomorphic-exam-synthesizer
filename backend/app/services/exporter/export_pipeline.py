"""Compile and package one locked display snapshot, without database or cloud access."""

from .bundle_builder import build_bundle
from .bundle_models import ApprovedExportSnapshot, BundleArtifact
from .typst_compiler import TypstCompiler, generate_pdf_filename


def build_compiled_bundle(
    snapshot: ApprovedExportSnapshot,
    *,
    compiler: TypstCompiler | None = None,
) -> BundleArtifact:
    """Build all 2*N+1 PDFs and source files from the same validated snapshot.

    This synchronous function runs subprocesses; async API callers should use
    asyncio.to_thread. The caller owns authorization and the locked DB snapshot.
    Compiler/bundler errors propagate; no partial archive is returned or uploaded.
    """
    snapshot = ApprovedExportSnapshot.model_validate(snapshot.model_dump())
    compiler = compiler if compiler is not None else TypstCompiler()
    pdfs: dict[str, bytes] = {}
    matrix: list[dict[str, object]] = []

    for version in snapshot.versions:
        # Only validated display fields enter the compiler, never canonical fallbacks.
        questions = [question.model_dump(mode="json") for question in version.questions]
        exam_name = generate_pdf_filename("exam", version.code)
        pdfs[exam_name] = compiler.compile_document(
            compiler.render_exam_document(version.code, questions, exam_title=snapshot.title),
            exam_name,
        )
        solutions_name = generate_pdf_filename("solutions", version.code)
        pdfs[solutions_name] = compiler.compile_document(
            compiler.render_solution_document(version.code, questions, exam_title=snapshot.title),
            solutions_name,
        )
        matrix.append(
            {
                "version_code": version.code,
                "answer_keys": {
                    question.question_no: question.correct_key for question in version.questions
                },
            }
        )

    matrix_name = generate_pdf_filename("matrix")
    pdfs[matrix_name] = compiler.compile_document(
        compiler.render_answers_matrix_document(matrix, exam_title=snapshot.title), matrix_name
    )
    return build_bundle(snapshot, pdfs)
