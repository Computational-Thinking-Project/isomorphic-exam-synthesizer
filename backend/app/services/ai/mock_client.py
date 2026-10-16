import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.models.schemas import GeneratedVariant, SourceQuestion


class BaseAIClient(ABC):
    """Giao diện trừu tượng cho AI Client (hỗ trợ cả Real và Mock client)."""

    @abstractmethod
    def generate_variant(
        self,
        source: SourceQuestion,
        seed: Optional[int] = None,
        system_instruction: Optional[str] = None,
        feedback: Optional[str] = None
    ) -> GeneratedVariant:
        """Sinh một biến thể câu hỏi từ câu hỏi nguồn."""
        pass


class MockGeminiClient(BaseAIClient):
    """
    Mock AI Client phục vụ Unit Test và môi trường CI/CD.
    Không gọi mạng, không tốn quota, trả về dữ liệu nhanh chóng và có thể mô phỏng lỗi.
    """

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
        simulate_error: Optional[str] = None
    ):
        """
        :param fixture_path: Đường dẫn tới file JSON fixture mẫu (mặc định tìm contracts/fixtures/variant.json)
        :param simulate_error: Tùy chọn mô phỏng lỗi: 'quota_exceeded', 'rate_limit', 'server_error'
        """
        self.simulate_error = simulate_error
        if fixture_path is None:
            # Tìm fixture tương đối từ backend/app/services/ai/
            root_dir = Path(__file__).resolve().parents[4]
            fixture_path = root_dir / "contracts" / "fixtures" / "variant.json"
        self.fixture_path = fixture_path

    def generate_variant(
        self,
        source: SourceQuestion,
        seed: Optional[int] = None,
        system_instruction: Optional[str] = None,
        feedback: Optional[str] = None
    ) -> GeneratedVariant:
        # 1. Mô phỏng lỗi nếu được cấu hình
        if self.simulate_error == "quota_exceeded":
            raise RuntimeError("ResourceExhausted: 429 You have exhausted your Gemini API quota.")
        elif self.simulate_error == "server_error":
            raise RuntimeError("InternalServerError: 503 Service Temporarily Unavailable.")

        # 2. Đọc fixture JSON nếu file tồn tại
        if self.fixture_path.exists():
            data = json.loads(self.fixture_path.read_text(encoding="utf-8"))
            # Gắn id câu hỏi gốc vào fixture để nhất quán
            data["source_question_id"] = source.id
            if seed is not None:
                data["seed"] = seed
                data["variant_id"] = f"var_{source.id}_s{seed}"
            return GeneratedVariant(**data)

        # 3. Fallback mặc định nếu không tìm thấy file fixture
        used_seed = seed if seed is not None else 42
        return GeneratedVariant(
            variant_id=f"var_{source.id}_s{used_seed}",
            source_question_id=source.id,
            question_text=f"{source.question_text} (Biến thể số học seed={used_seed})",
            options=[
                source.correct_answer,
                "Phương án nhiễu 1",
                "Phương án nhiễu 2",
                "Phương án nhiễu 3"
            ],
            correct_answer=source.correct_answer,
            solution_steps=source.solution or "Các bước giải chi tiết mẫu.",
            seed=used_seed
        )
