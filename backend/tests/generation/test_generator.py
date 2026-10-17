import pytest
from app.models.schemas import SourceQuestion, ExamDraftPackage, GeneratedVariant
from app.services.ai.mock_client import MockGeminiClient
from app.services.generation.generator import (
    VariantGenerator,
    generate_n_exam_drafts,
    regenerate_single_variant,
)


@pytest.fixture
def sample_questions():
    """Tạo 2 câu hỏi nguồn mẫu."""
    q1 = SourceQuestion(
        id="q1",
        question_text="Giải phương trình $x^2 - 4x + 3 = 0$?",
        options=["$x=1; x=3$", "$x=2; x=4$", "$x=-1; x=-3$", "$x=0$"],
        correct_answer="$x=1; x=3$",
        solution="Ta có $(x-1)(x-3)=0 \\implies x=1$ hoặc $x=3$."
    )
    q2 = SourceQuestion(
        id="q2",
        question_text="Tìm giá trị nhỏ nhất của hàm số $y = x^2 - 2x + 5$?",
        options=["$4$", "$5$", "$1$", "$2$"],
        correct_answer="$4$",
        solution="Ta có $y = (x-1)^2 + 4 \\ge 4$. Dấu bằng xảy ra khi $x = 1$."
    )
    return [q1, q2]


def test_generate_n_exam_drafts_with_mock(sample_questions):
    """Kiểm tra sinh N=3 phiên bản đề thi độc lập với MockClient."""
    mock_client = MockGeminiClient()
    n_versions = 3

    packages = generate_n_exam_drafts(
        source_questions=sample_questions,
        n_versions=n_versions,
        ai_client=mock_client,
        base_seed=100
    )

    # 1. Đủ N phiên bản đề
    assert len(packages) == n_versions
    for idx, pkg in enumerate(packages, start=1):
        assert isinstance(pkg, ExamDraftPackage)
        assert pkg.version_index == idx
        assert pkg.version_id == f"draft_v{idx:02d}"

        # 2. Mỗi đề có đúng 2 câu hỏi biến thể
        assert len(pkg.variants) == 2
        for var in pkg.variants:
            assert isinstance(var, GeneratedVariant)
            assert len(var.options) == 4
            assert var.correct_answer in var.options
            assert len(set(var.options)) == 4  # Không trùng lặp


def test_regenerate_single_variant_with_mock(sample_questions):
    """Kiểm tra hàm tái sinh 1 câu hỏi khi giảng viên không ưng ý (Stage 03)."""
    mock_client = MockGeminiClient()
    q = sample_questions[0]

    var1 = regenerate_single_variant(source_question=q, seed=10, ai_client=mock_client)
    var2 = regenerate_single_variant(source_question=q, seed=20, ai_client=mock_client)

    assert isinstance(var1, GeneratedVariant)
    assert isinstance(var2, GeneratedVariant)
    assert var1.seed == 10
    assert var2.seed == 20
    assert var1.source_question_id == q.id
    assert var2.source_question_id == q.id


def test_generator_detects_duplicate_options():
    """Kiểm tra generator phát hiện và xử lý khi options bị trùng lặp."""
    class BadOptionsClient(MockGeminiClient):
        def generate_variant(self, source, seed=None, system_instruction=None, feedback=None):
            return GeneratedVariant(
                variant_id="bad_var",
                source_question_id=source.id,
                question_text="Câu hỏi lỗi trùng options",
                options=["1", "1", "2", "3"],  # Trùng số 1
                correct_answer="1",
                solution_steps="Lời giải"
            )

    gen = VariantGenerator(ai_client=BadOptionsClient())
    with pytest.raises(ValueError) as exc:
        gen.generate_single_variant(
            source=SourceQuestion(id="q", question_text="Test", correct_answer="1"),
            max_retries=1
        )
    assert "trùng lặp" in str(exc.value)


def test_feedback_guided_regeneration_passed_to_client(sample_questions):
    """Kiểm tra feedback được truyền đầy đủ tới AI client khi tái sinh."""
    captured_calls = []

    class FeedbackTrackingClient(MockGeminiClient):
        def generate_variant(self, source, seed=None, system_instruction=None, feedback=None):
            captured_calls.append({"seed": seed, "feedback": feedback})
            return super().generate_variant(source=source, seed=seed)

    client = FeedbackTrackingClient()
    q = sample_questions[0]
    prompt_feedback = "Học sinh THPT hay nhầm công thức delta phẩy, hãy tạo distractor cho lỗi này."

    var = regenerate_single_variant(
        source_question=q,
        seed=777,
        feedback=prompt_feedback,
        ai_client=client
    )

    assert len(captured_calls) == 1
    assert captured_calls[0]["feedback"] == prompt_feedback
    assert captured_calls[0]["seed"] == 777
    assert var.seed == 777


def test_generator_retry_recovery_with_feedback(sample_questions):
    """Kiểm tra generator tự động thử lại với feedback khi lần 1 trả về dữ liệu lỗi."""
    calls = []

    class SelfHealingClient(MockGeminiClient):
        def generate_variant(self, source, seed=None, system_instruction=None, feedback=None):
            calls.append({"feedback": feedback})
            if len(calls) == 1:
                # Lần 1: trả về options có 2 lựa chọn trùng nhau
                return GeneratedVariant(
                    variant_id="var_err",
                    source_question_id=source.id,
                    question_text="Phương trình bậc hai",
                    options=["$x=1$", "$x=1$", "$x=2$", "$x=3$"],
                    correct_answer="$x=1$",
                    solution_steps="Các bước giải"
                )
            # Lần 2: trả về đúng
            return GeneratedVariant(
                variant_id="var_ok",
                source_question_id=source.id,
                question_text="Phương trình bậc hai",
                options=["$x=1$", "$x=4$", "$x=2$", "$x=3$"],
                correct_answer="$x=1$",
                solution_steps="Các bước giải"
            )

    gen = VariantGenerator(ai_client=SelfHealingClient())
    variant = gen.generate_single_variant(source=sample_questions[0], max_retries=2)

    assert len(calls) == 2
    assert calls[0]["feedback"] is None  # Lần 1 chưa có feedback
    assert "trùng lặp" in calls[1]["feedback"]  # Lần 2 nhận được feedback lỗi từ lần 1
    assert len(set(variant.options)) == 4

