import logging
import time
from pathlib import Path
from typing import List, Optional

from app.models.schemas import (
    ExamDraftPackage,
    GeneratedVariant,
    SourceQuestion,
)
from app.services.ai.client import GeminiClient
from app.services.ai.mock_client import BaseAIClient

logger = logging.getLogger(__name__)

# Đọc prompt template từ file text nếu có
PROMPT_FILE = Path(__file__).resolve().parents[1] / "ai" / "prompts" / "variant_generation.txt"


def load_system_prompt() -> str:
    """Đọc system prompt từ file variant_generation.txt."""
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return "Bạn là chuyên gia sinh đề toán đẳng cấu (IMPG)."


class VariantGenerator:
    """
    Bộ điều phối sinh đề thi đẳng cấu (Isomorphic Variant Generator) - Hộp đen Stage 02.
    Nhận số lượng N và đề gốc -> Tự động sinh ra N phiên bản đề thi độc lập.
    """

    def __init__(self, ai_client: Optional[BaseAIClient] = None):
        """
        :param ai_client: Client AI (GeminiClient hoặc MockGeminiClient).
                          Nếu không truyền, mặc định khởi tạo GeminiClient.
        """
        self.ai_client = ai_client
        self.system_prompt = load_system_prompt()

    def _get_client(self) -> BaseAIClient:
        """Lấy client khả dụng hoặc tạo mới GeminiClient."""
        if self.ai_client is None:
            self.ai_client = GeminiClient()
        return self.ai_client

    def generate_single_variant(
        self,
        source: SourceQuestion,
        seed: Optional[int] = None,
        feedback: Optional[str] = None,
        max_retries: int = 2
    ) -> GeneratedVariant:
        """
        Sinh 1 biến thể duy nhất cho một câu hỏi nguồn.
        Hỗ trợ Feedback-guided Regeneration (TASK-106c): tiếp nhận góp ý hoặc lý do từ chối
        từ vòng validation / người dùng để điều hướng AI tránh lặp lại lỗi cũ.
        Bảo đảm tính toàn vẹn: 4 options không trùng lặp, đáp án đúng nằm trong options.
        """
        client = self._get_client()
        used_seed = seed if seed is not None else int(time.time())
        current_feedback = feedback

        for attempt in range(1, max_retries + 1):
            try:
                variant = client.generate_variant(
                    source=source,
                    seed=used_seed,
                    system_instruction=self.system_prompt,
                    feedback=current_feedback
                )

                # Kiểm tra tính toàn vẹn cơ bản của trắc nghiệm
                # 1. Bắt buộc đúng 4 options
                if len(variant.options) != 4:
                    raise ValueError(f"Số lượng options không đúng: {len(variant.options)} (yêu cầu 4)")

                # 2. Không có 2 lựa chọn trùng lặp hoàn toàn
                if len(set(variant.options)) != 4:
                    raise ValueError("Tồn tại các lựa chọn bị trùng lặp trong options")

                # 3. Đáp án đúng phải nằm trong danh sách options
                if variant.correct_answer not in variant.options:
                    # Tự động khắc phục nhẹ: nếu đáp án đúng bị lệch khoảng trắng, chuẩn hóa lại
                    normalized_correct = variant.correct_answer.strip()
                    matched = False
                    for idx, opt in enumerate(variant.options):
                        if opt.strip() == normalized_correct:
                            variant.correct_answer = opt
                            matched = True
                            break
                    if not matched:
                        raise ValueError(f"Đáp án đúng '{variant.correct_answer}' không có trong options: {variant.options}")

                return variant

            except Exception as e:
                logger.warning(
                    "Lần thử %d sinh câu hỏi %s thất bại: %s",
                    attempt, source.id, e
                )
                if attempt == max_retries:
                    raise

                # Đổi seed và bổ sung feedback hướng dẫn cho lần thử tiếp theo
                used_seed += 1
                current_feedback = (
                    f"Lần sinh trước thất bại với lỗi: {e}. "
                    f"Vui lòng tạo chính xác 4 lựa chọn khác nhau hoàn toàn và đảm bảo correct_answer nằm trong 4 lựa chọn."
                )

        raise RuntimeError(f"Không thể sinh biến thể cho câu hỏi {source.id}")

    def generate_n_exam_drafts(
        self,
        source_questions: List[SourceQuestion],
        n_versions: int = 4,
        base_seed: int = 100
    ) -> List[ExamDraftPackage]:
        """
        Sinh N phiên bản đề thi hoàn chỉnh độc lập nhau (Stage 02 Deliverable).
        :param source_questions: Danh sách câu hỏi của đề thi gốc.
        :param n_versions: Số lượng phiên bản đề cần sinh (ví dụ: N=4).
        :param base_seed: Seed cơ sở để bảo đảm tính tái lập kết quả.
        :return: Danh sách N gói đề thi (ExamDraftPackage).
        """
        exam_packages: List[ExamDraftPackage] = []

        for v_idx in range(1, n_versions + 1):
            version_id = f"draft_v{v_idx:02d}"
            version_variants: List[GeneratedVariant] = []

            for q_idx, source_q in enumerate(source_questions, start=1):
                # Mỗi câu hỏi ở mỗi phiên bản có một seed duy nhất
                item_seed = base_seed + (v_idx * 1000) + q_idx
                variant = self.generate_single_variant(
                    source=source_q,
                    seed=item_seed
                )
                # Đổi variant_id để phản ánh đúng phiên bản đề
                variant.variant_id = f"var_{source_q.id}_v{v_idx:02d}"
                version_variants.append(variant)

            package = ExamDraftPackage(
                version_id=version_id,
                version_index=v_idx,
                variants=version_variants
            )
            exam_packages.append(package)

        return exam_packages


# --- Các hàm tiện ích cấp module (Standalone APIs) ---

def generate_n_exam_drafts(
    source_questions: List[SourceQuestion],
    n_versions: int = 4,
    ai_client: Optional[BaseAIClient] = None,
    base_seed: int = 100
) -> List[ExamDraftPackage]:
    """Hàm nhanh sinh N đề thi hoàn chỉnh (Stage 02)."""
    generator = VariantGenerator(ai_client=ai_client)
    return generator.generate_n_exam_drafts(
        source_questions=source_questions,
        n_versions=n_versions,
        base_seed=base_seed
    )


def regenerate_single_variant(
    source_question: SourceQuestion,
    seed: Optional[int] = None,
    feedback: Optional[str] = None,
    ai_client: Optional[BaseAIClient] = None
) -> GeneratedVariant:
    """Hàm nhanh tái sinh 1 câu hỏi khi giảng viên không ưng ý ở Stage 03 hoặc bị từ chối ở tầng validation."""
    generator = VariantGenerator(ai_client=ai_client)
    return generator.generate_single_variant(
        source=source_question,
        seed=seed,
        feedback=feedback
    )
