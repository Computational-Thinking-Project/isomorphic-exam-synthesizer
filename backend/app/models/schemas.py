from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class SourceQuestion(BaseModel):
    """Đại diện cho 1 câu hỏi nguồn được trích xuất từ đề thi gốc."""

    id: str = Field(..., description="Mã định danh câu hỏi gốc")
    question_text: str = Field(..., description="Nội dung câu hỏi (chứa LaTeX)")
    options: List[str] = Field(default_factory=list, description="Danh sách các lựa chọn trả lời")
    correct_answer: str = Field(..., description="Đáp án đúng (ví dụ: 'A' hoặc nội dung đáp án)")
    solution: str = Field("", description="Lời giải chi tiết gốc")
    topic: Optional[str] = Field(None, description="Chủ đề toán học (nếu có)")
    has_security_warning: bool = Field(
        False, description="Cảnh báo chuỗi khả nghi/prompt injection (SEC-02)"
    )


class GeneratedVariant(BaseModel):
    """Một biến thể câu hỏi toán đẳng cấu được sinh tự động bởi AI."""

    variant_id: str = Field(..., description="Mã định danh duy nhất của biến thể")
    source_question_id: str = Field(..., description="Mã câu hỏi gốc tương ứng")
    question_text: str = Field(
        ..., description="Nội dung câu hỏi biến thể với các số liệu mới (LaTeX)"
    )
    options: List[str] = Field(
        ..., min_length=4, max_length=4, description="Chính xác 4 lựa chọn không trùng lặp"
    )
    correct_answer: str = Field(..., description="Đáp án đúng, bắt buộc khớp với 1 trong 4 options")
    solution_steps: str = Field(
        ..., description="Các bước giải chi tiết tương ứng với số liệu mới (LaTeX)"
    )
    seed: Optional[int] = Field(None, description="Seed ngẫu nhiên dùng để tái tạo kết quả")


class GenerateRequest(BaseModel):
    """Payload từ người dùng ở Stage 02: Chỉ cần chọn số lượng N đề cần sinh."""

    source_exam_id: str = Field(..., description="Mã đề thi gốc")
    n_versions: int = Field(default=4, ge=1, le=4, description="Số lượng phiên bản đề cần sinh")


class RegenerateQuestionRequest(BaseModel):
    """Payload khi người dùng bấm 'Sinh lại câu này' ở Stage 03."""

    question_id: str = Field(..., description="Mã câu hỏi cần sinh lại")
    seed: Optional[int] = Field(None, description="Seed mới (nếu muốn chỉ định trước)")


class ExamDraftPackage(BaseModel):
    """Một gói đề thi bản thảo (1 trong N phiên bản) ở Stage 02 Deliverable."""

    version_id: str = Field(..., description="Mã định danh phiên bản đề")
    version_index: int = Field(..., description="Số thứ tự phiên bản (1, 2, ... N)")
    variants: List[GeneratedVariant] = Field(
        default_factory=list, description="Danh sách các câu hỏi biến thể"
    )


class CurrentUser(BaseModel):
    """Thông tin người dùng đã xác thực từ Supabase Auth JWT."""

    id: str = Field(..., description="Supabase Auth UUID")
    email: str = Field(..., description="Email người dùng")
    name: Optional[str] = Field(None, description="Tên hiển thị người dùng")
    access_token: str = Field(..., description="JWT Bearer token")


class UserProfile(BaseModel):
    """Thông tin hồ sơ người dùng trả về từ public.users."""

    id: str = Field(..., description="UUID người dùng")
    email: str = Field(..., description="Email người dùng")
    name: Optional[str] = Field(None, description="Tên người dùng")
    created_at: Optional[str] = Field(None, description="Thời điểm tạo tài khoản")


class SessionCreate(BaseModel):
    """Payload tạo mới phiên làm việc (Stage 1)."""

    title: str = Field(..., min_length=1, max_length=255, description="Tiêu đề phiên làm việc")
    subject: str = Field(default="Toán", max_length=100, description="Môn học")
    grade: int = Field(default=12, ge=1, le=12, description="Khối lớp (mặc định 12)")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Title must not be empty or whitespace only")
        return trimmed


class SessionUpdate(BaseModel):
    """Payload cập nhật thông tin phiên làm việc."""

    title: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Tiêu đề phiên làm việc"
    )
    subject: Optional[str] = Field(None, max_length=100, description="Môn học")
    grade: Optional[int] = Field(None, ge=1, le=12, description="Khối lớp")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Title must not be empty or whitespace only")
            return trimmed
        return v


class SessionCloneRequest(BaseModel):
    """Payload nhân bản phiên làm việc (UC03 / TASK-103b)."""

    new_title: Optional[str] = Field(
        None, max_length=255, description="Tiêu đề mới cho bản sao chép"
    )

    @field_validator("new_title")
    @classmethod
    def validate_new_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("New title must not be empty or whitespace only")
            return trimmed
        return v


class SessionItem(BaseModel):
    """Thông tin tóm tắt một phiên làm việc."""

    id: str
    user_id: str
    title: str
    subject: str
    grade: int
    status: str
    gemini_call_count: int = 0
    retry_count: int = 0
    approved_at: Optional[str] = None
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """Danh sách các phiên làm việc có hỗ trợ phân trang."""

    items: List[SessionItem]
    total: int
    page: int
    page_size: int


class SessionDetailResponse(BaseModel):
    """Chi tiết phiên làm việc kèm danh sách câu hỏi nguồn và mã đề."""

    id: str
    user_id: str
    title: str
    subject: str
    grade: int
    status: str
    gemini_call_count: int = 0
    retry_count: int = 0
    approved_at: Optional[str] = None
    created_at: str
    updated_at: str
    source_questions: List[dict] = Field(default_factory=list, description="Danh sách câu hỏi gốc")
    exam_versions: List[dict] = Field(default_factory=list, description="Danh sách các mã đề")


class IngestTextRequest(BaseModel):
    """Payload cho endpoint nhập trực tiếp đề thi dạng text (TASK-202)."""

    raw_text: str = Field(..., description="Nội dung văn bản đề thi thô kèm công thức LaTeX")

    @field_validator("raw_text")
    @classmethod
    def validate_raw_text(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("raw_text must not be empty or whitespace only")
        if len(trimmed) > 100_000:
            raise ValueError("raw_text exceeds maximum allowed length of 100,000 characters")
        return trimmed


class ParserErrorItem(BaseModel):
    """Chi tiết một lỗi bóc tách trong câu hỏi nguồn (TASK-203b)."""

    question_no: int = Field(..., description="Số thứ tự câu hỏi bị lỗi (1-indexed)")
    error_type: Literal[
        "MISSING_ANSWER",
        "UNPARSED_OMML",
        "UNPARSED_IMAGE",
        "AMBIGUOUS_FORMAT",
        "EMPTY_STEM",
        "CONFLICTING_ANSWER_KEY",
        "SURPLUS_ANSWER_KEY",
        "DUPLICATE_QUESTION_NO",
        "INVALID_QUESTION_NO",
        "INVALID_FORMAT",
    ] = Field(..., description="Mã phân loại lỗi bóc tách")
    message: Optional[str] = Field(None, description="Mô tả chi tiết nguyên nhân lỗi")


class IngestValidationErrorResponse(BaseModel):
    """Payload phản hồi HTTP 422 khi phát hiện lỗi bóc tách dữ liệu đề thi."""

    detail: str = Field(
        "Exam content incomplete or unprocessable", description="Thông điệp tổng quan"
    )
    errors: List[ParserErrorItem] = Field(
        default_factory=list, description="Danh sách các câu hỏi bị lỗi"
    )


class ParsedQuestionItem(BaseModel):
    """Dữ liệu một câu hỏi sau khi bóc tách In-Memory trước khi lưu CSDL."""

    question_no: int
    raw_content: str
    options: Dict[str, str] = Field(
        ..., description="Chính xác 4 lựa chọn {'A': '...', 'B': '...', 'C': '...', 'D': '...'}"
    )
    correct_key: str = Field(..., description="'A', 'B', 'C', hoặc 'D'")
    solution_md: Optional[str] = None
    has_missing_answer: bool = False
    has_unparsed_omml: bool = False
    has_unparsed_image: bool = False
    is_empty_stem: bool = False
    has_security_warning: bool = False


class IngestSuccessResponse(BaseModel):
    """Phản hồi thành công từ endpoints Ingestion (TASK-202)."""

    session_id: str = Field(..., description="Mã định danh phiên làm việc")
    message: str = Field("Exam ingested successfully", description="Thông điệp thành công")
    total_questions: int = Field(..., description="Tổng số câu hỏi hợp lệ đã nạp")
    questions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Danh sách câu hỏi nguồn đã lưu"
    )
