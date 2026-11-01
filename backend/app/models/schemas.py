from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator


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


class ConfirmSourceRequest(BaseModel):
    """Payload xác nhận đề nguồn và chuyển sang Stage 2 (TASK-205).

    Per ADR-004 (Silent Security Audit): The `acknowledged_security_warnings` field is
    deprecated and IGNORED. Security warnings are logged silently on the backend for
    admin audit. The UI no longer exposes a security acknowledgment checkbox. Clients
    may omit this field or send any value without affecting the outcome.
    """

    acknowledged_security_warnings: bool = Field(
        default=False,
        description=(
            "[DEPRECATED per ADR-004] Previously required to acknowledge SEC-02 security warnings. "
            "Now ignored — security events are logged silently for admin audit. "
            "Field kept for backward compatibility; any value sent has no effect."
        ),
    )


class ConfirmSourceResponse(BaseModel):
    """Phản hồi thành công từ endpoint confirm-source (TASK-205)."""

    session_id: str = Field(..., description="Mã phiên làm việc")
    status: Literal["blueprinted"] = "blueprinted"
    confirmed_at: str = Field(..., description="Thời điểm xác nhận (ISO8601)")
    total_questions: int = Field(..., description="Tổng câu nguồn đã khóa")
    total_blueprints: int = Field(..., description="Tổng blueprints tương ứng")
    message: str = "Source confirmed and blueprints locked successfully"


# ------------------------------------------------------------------------------
# Stage 3: Review Lifecycle & Invariants Models (TASK-301)
# ------------------------------------------------------------------------------


class ReserveResult(str, Enum):
    """Kết quả dự trữ hạn mức và khóa trạng thái câu hỏi khi reject."""

    OK = "OK"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    QUESTION_BUSY = "QUESTION_BUSY"
    SESSION_BUSY = "SESSION_BUSY"
    QUESTION_NOT_FOUND = "QUESTION_NOT_FOUND"
    QUESTION_NOT_CURRENT = "QUESTION_NOT_CURRENT"


class ReviewErrorCode:
    """Standard domain error codes conforming to Stage 3 review RPC contract."""

    REVIEW_NOT_FOUND = "REVIEW_NOT_FOUND"
    REVIEW_BUSY = "REVIEW_BUSY"
    REVIEW_STALE = "REVIEW_STALE"
    REVIEW_IDEMPOTENCY_CONFLICT = "REVIEW_IDEMPOTENCY_CONFLICT"
    REVIEW_LOCKED = "REVIEW_LOCKED"
    REVIEW_QUOTA_EXHAUSTED = "REVIEW_QUOTA_EXHAUSTED"
    REVIEW_INVALID_PAYLOAD = "REVIEW_INVALID_PAYLOAD"
    REVIEW_SOURCE_MISMATCH = "REVIEW_SOURCE_MISMATCH"
    REVIEW_AI_UNAVAILABLE = "REVIEW_AI_UNAVAILABLE"
    REVIEW_PERMIT_REQUIRED = "REVIEW_PERMIT_REQUIRED"
    REVIEW_PERMIT_INVALID = "REVIEW_PERMIT_INVALID"
    REVIEW_PERMIT_UNCERTAIN = "REVIEW_PERMIT_UNCERTAIN"
    REVIEW_ATTEMPT_REPLAYED = "REVIEW_ATTEMPT_REPLAYED"


class ReviewActionResponse(BaseModel):
    """Phản hồi sau thao tác Accept hoặc Revert trên một câu hỏi (TASK-301)."""

    question_id: str = Field(..., description="Mã định danh câu hỏi hiện hành")
    session_id: str = Field(..., description="Mã phiên làm việc")
    status: str = Field(..., description="Trạng thái câu hỏi ('approved', 'pending_review', v.v.)")
    is_current: bool = Field(True, description="Đánh dấu câu hỏi là bản ghi hiện hành")
    is_reverted: bool = Field(False, description="Đánh dấu câu hỏi đã được hoàn nguyên về gốc")
    updated_at: str = Field(..., description="Thời điểm cập nhật trạng thái (ISO8601)")


class RegeneratedQuestionResponse(BaseModel):
    """Phản hồi câu hỏi biến thể mới sau khi từ chối (Reject & Regenerate)."""

    question_id: str = Field(..., description="Mã định danh của biến thể mới")
    regenerated_from_id: str = Field(..., description="Mã định danh câu cũ bị thay thế")
    status: str = Field("pending_review", description="Trạng thái của biến thể mới")
    content: str = Field(..., description="Nội dung câu hỏi biến thể mới (LaTeX)")
    options: List[str] = Field(
        ..., min_length=4, max_length=4, description="4 phương án A, B, C, D"
    )
    correct_key: str = Field(..., description="Chữ cái đáp án đúng ('A', 'B', 'C', 'D')")
    solution_md: Optional[str] = Field(None, description="Lời giải chi tiết mới")
    validation_report: Optional[Dict[str, Any]] = Field(
        default=None, description="Báo cáo kiểm định toán học on-the-fly"
    )


class ReviewProgressResponse(BaseModel):
    """Thống kê tiến độ thẩm định của phiên làm việc (TASK-301 & TASK-302 Contract)."""

    session_id: str = Field(..., description="Mã phiên làm việc")

    # Contract fields aligned with TASK-302 RPC contract & Migration 006
    expected_slots: int = Field(0, description="Tổng số vị trí câu hỏi cần có (N mã đề x M câu)")
    current_slots: int = Field(
        0, description="Tổng số câu hiện hành đang hiển thị (is_current=True)"
    )
    approved_slots: int = Field(0, description="Số câu hiện hành đã được duyệt (status='approved')")
    regenerating_slots: int = Field(0, description="Số câu đang trong tiến trình sinh lại")
    missing_slots: int = Field(0, description="Số vị trí câu hỏi còn thiếu chưa được sinh")
    duplicate_slots: int = Field(0, description="Số vị trí câu hỏi bị dư hoặc trùng lặp")
    ready: bool = Field(False, description="Đủ điều kiện sẵn sàng shuffle và finalize")

    # Backward-compatible fields for existing frontend and test callers
    required_count: int = Field(0, description="Alias tương thích ngược của expected_slots")
    current_count: int = Field(0, description="Alias tương thích ngược của current_slots")
    approved_count: int = Field(0, description="Alias tương thích ngược của approved_slots")
    regenerating_count: int = Field(0, description="Alias tương thích ngược của regenerating_slots")
    unapproved_question_ids: List[str] = Field(
        default_factory=list, description="Danh sách mã câu hỏi hiện hành chưa được duyệt"
    )
    is_complete: bool = Field(False, description="Đã duyệt đủ 100% câu hỏi hiện hành")
    can_finalize: bool = Field(False, description="Alias tương thích ngược của ready")

    @model_validator(mode="before")
    @classmethod
    def sync_contract_and_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync expected_slots <-> required_count
            if "expected_slots" not in data and "required_count" in data:
                data["expected_slots"] = data["required_count"]
            elif "required_count" not in data and "expected_slots" in data:
                data["required_count"] = data["expected_slots"]

            # Sync current_slots <-> current_count
            if "current_slots" not in data and "current_count" in data:
                data["current_slots"] = data["current_count"]
            elif "current_count" not in data and "current_slots" in data:
                data["current_count"] = data["current_slots"]

            # Sync approved_slots <-> approved_count
            if "approved_slots" not in data and "approved_count" in data:
                data["approved_slots"] = data["approved_count"]
            elif "approved_count" not in data and "approved_slots" in data:
                data["approved_count"] = data["approved_slots"]

            # Sync regenerating_slots <-> regenerating_count
            if "regenerating_slots" not in data and "regenerating_count" in data:
                data["regenerating_slots"] = data["regenerating_count"]
            elif "regenerating_count" not in data and "regenerating_slots" in data:
                data["regenerating_count"] = data["regenerating_slots"]

            # Sync ready <-> can_finalize
            if "ready" not in data and "can_finalize" in data:
                data["ready"] = data["can_finalize"]
            elif "can_finalize" not in data and "ready" in data:
                data["can_finalize"] = data["ready"]

            if "missing_slots" not in data:
                exp = int(data.get("expected_slots", 0) or 0)
                cur = int(data.get("current_slots", 0) or 0)
                data["missing_slots"] = max(0, exp - cur)

            if "duplicate_slots" not in data:
                exp = int(data.get("expected_slots", 0) or 0)
                cur = int(data.get("current_slots", 0) or 0)
                data["duplicate_slots"] = max(0, cur - exp)

            if "is_complete" not in data:
                exp = int(data.get("expected_slots", 0) or 0)
                cur = int(data.get("current_slots", 0) or 0)
                app = int(data.get("approved_slots", 0) or 0)
                data["is_complete"] = bool(exp > 0 and cur == exp and app == exp)
        return data


class ErrorDetailResponse(BaseModel):
    """Cấu trúc lỗi chuẩn hóa của hệ thống."""

    error_code: str = Field(..., description="Mã lỗi hệ thống định danh")
    detail: str = Field(..., description="Mô tả chi tiết lỗi")


class ReviewDomainException(HTTPException):
    """Ngoại lệ nghiệp vụ riêng cho Review Lifecycle."""

    def __init__(self, status_code: int, error_code: str, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


# Re-export validator schemas for convenient consumption across services and routes
from app.services.validator.base import CheckResult, ValidationReport  # noqa: E402

__all__ = [
    "SourceQuestion",
    "GeneratedVariant",
    "GenerateRequest",
    "RegenerateQuestionRequest",
    "ExamDraftPackage",
    "CurrentUser",
    "UserProfile",
    "SessionCreate",
    "SessionUpdate",
    "SessionCloneRequest",
    "SessionItem",
    "SessionListResponse",
    "SessionDetailResponse",
    "IngestTextRequest",
    "ParserErrorItem",
    "IngestValidationErrorResponse",
    "ParsedQuestionItem",
    "IngestSuccessResponse",
    "ConfirmSourceRequest",
    "ConfirmSourceResponse",
    "ReserveResult",
    "ReviewErrorCode",
    "ReviewActionResponse",
    "RegeneratedQuestionResponse",
    "ReviewProgressResponse",
    "ErrorDetailResponse",
    "ReviewDomainException",
    "CheckResult",
    "ValidationReport",
]
