from typing import List, Optional

from pydantic import BaseModel, Field


class SourceQuestion(BaseModel):
    """Đại diện cho 1 câu hỏi nguồn được trích xuất từ đề thi gốc."""
    id: str = Field(..., description="Mã định danh câu hỏi gốc")
    question_text: str = Field(..., description="Nội dung câu hỏi (chứa LaTeX)")
    options: List[str] = Field(default_factory=list, description="Danh sách các lựa chọn trả lời")
    correct_answer: str = Field(..., description="Đáp án đúng (ví dụ: 'A' hoặc nội dung đáp án)")
    solution: str = Field("", description="Lời giải chi tiết gốc")
    topic: Optional[str] = Field(None, description="Chủ đề toán học (nếu có)")
    has_security_warning: bool = Field(False, description="Cảnh báo chuỗi khả nghi/prompt injection (SEC-02)")


class GeneratedVariant(BaseModel):
    """Một biến thể câu hỏi toán đẳng cấu được sinh tự động bởi AI."""
    variant_id: str = Field(..., description="Mã định danh duy nhất của biến thể")
    source_question_id: str = Field(..., description="Mã câu hỏi gốc tương ứng")
    question_text: str = Field(..., description="Nội dung câu hỏi biến thể với các số liệu mới (LaTeX)")
    options: List[str] = Field(..., min_length=4, max_length=4, description="Chính xác 4 lựa chọn không trùng lặp")
    correct_answer: str = Field(..., description="Đáp án đúng, bắt buộc khớp với 1 trong 4 options")
    solution_steps: str = Field(..., description="Các bước giải chi tiết tương ứng với số liệu mới (LaTeX)")
    seed: Optional[int] = Field(None, description="Seed ngẫu nhiên dùng để tái tạo kết quả")


class GenerateRequest(BaseModel):
    """Payload từ người dùng ở Stage 02: Chỉ cần chọn số lượng N đề cần sinh."""
    source_exam_id: str = Field(..., description="Mã đề thi gốc")
    n_versions: int = Field(default=4, ge=1, le=20, description="Số lượng phiên bản đề cần sinh")


class RegenerateQuestionRequest(BaseModel):
    """Payload khi người dùng bấm 'Sinh lại câu này' ở Stage 03."""
    question_id: str = Field(..., description="Mã câu hỏi cần sinh lại")
    seed: Optional[int] = Field(None, description="Seed mới (nếu muốn chỉ định trước)")


class ExamDraftPackage(BaseModel):
    """Một gói đề thi bản thảo (1 trong N phiên bản) ở Stage 02 Deliverable."""
    version_id: str = Field(..., description="Mã định danh phiên bản đề")
    version_index: int = Field(..., description="Số thứ tự phiên bản (1, 2, ... N)")
    variants: List[GeneratedVariant] = Field(default_factory=list, description="Danh sách các câu hỏi biến thể")
