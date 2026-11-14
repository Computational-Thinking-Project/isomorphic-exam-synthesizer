from enum import Enum, StrEnum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


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
    source_revision: str = Field(
        ...,
        min_length=1,
        description="Revision of the source preview being confirmed.",
    )
    source_questions: List[dict] = Field(default_factory=list, description="Danh sách câu hỏi gốc")
    exam_versions: List[dict] = Field(default_factory=list, description="Danh sách các mã đề")
    generation_config: Optional[dict] = Field(
        default=None, description="Cấu hình sinh đề Stage 2 nếu có"
    )
    blueprint_summary: Optional[dict] = Field(
        default=None, description="Tóm tắt trạng thái Blueprint"
    )


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

    `source_revision` is required (Q01): the client must echo back the opaque revision
    token received from `GET /sessions/{id}` together with the preview snapshot.  The
    backend compares this token atomically under the session lock and returns HTTP 409
    ERR_SOURCE_REVISION_CONFLICT when the source has been replaced since the preview.
    """

    acknowledged_security_warnings: bool = Field(
        default=False,
        description=(
            "[DEPRECATED per ADR-004] Previously required to acknowledge SEC-02 security warnings. "
            "Now ignored — security events are logged silently for admin audit. "
            "Field kept for backward compatibility; any value sent has no effect."
        ),
    )
    source_revision: UUID = Field(
        ...,
        description="UUID revision token received with the source preview.",
    )


class ConfirmSourceResponse(BaseModel):
    """Phản hồi thành công từ endpoint confirm-source (TASK-205)."""

    session_id: str = Field(..., description="Mã phiên làm việc")
    status: Literal["blueprinted"] = "blueprinted"
    confirmed_at: str = Field(..., description="Thời điểm xác nhận (ISO8601)")
    total_questions: int = Field(..., description="Tổng câu nguồn đã khóa")
    total_blueprints: int = Field(..., description="Tổng blueprints tương ứng")
    confirmation_id: str | None = None
    canonical_status: Literal["pending", "running", "ready", "failed"] = "pending"
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


class RollbackErrorCode(StrEnum):
    """Sanitized failure/rollback error codes for failure settlement (TASK-301/TASK-302)."""

    AI_TIMEOUT = "AI_TIMEOUT"
    AI_INVALID_OUTPUT = "AI_INVALID_OUTPUT"
    MATH_VALIDATION_FAILED = "MATH_VALIDATION_FAILED"
    PERMIT_UNAVAILABLE = "PERMIT_UNAVAILABLE"
    PERMIT_UNCERTAIN = "PERMIT_UNCERTAIN"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    OPERATION_EXHAUSTED = "OPERATION_EXHAUSTED"
    ATTEMPT_REPLAYED = "ATTEMPT_REPLAYED"
    GENERATION_FAILED = "GENERATION_FAILED"
    CLIENT_CANCELLED = "CLIENT_CANCELLED"
    SOURCE_NOT_CONFIRMED = "SOURCE_NOT_CONFIRMED"
    AMBIGUOUS_STATE = "AMBIGUOUS_STATE"


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


class ReviewAcquireUnavailableError(ConnectionError):
    """Raised when atomic permit acquisition via review_acquire_attempt RPC fails or is unavailable.

    Enforces fail-closed semantics in production: no permit is granted and no AI call is dispatched.
    Inherits from ConnectionError so transport error catchers also recognize unavailable state.
    """

    def __init__(
        self,
        message: str,
        operation_id: Optional[UUID] = None,
        attempt_id: Optional[UUID] = None,
        error_code: str = "ERR_AI_GATEWAY_PERMIT_FAILURE",
        status_code: int = 503,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.operation_id = operation_id
        self.attempt_id = attempt_id
        self.error_code = error_code
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Finalize & Content Lock Schemas (TASK-305)
# ---------------------------------------------------------------------------


class FinalizeApproveResponse(BaseModel):
    """Phản hồi phê duyệt phiên làm việc thành công (TASK-305)."""

    session_id: str = Field(..., description="Mã phiên làm việc (UUID)")
    status: str = Field("approved", description="Trạng thái phiên làm việc sau khi duyệt")
    approved_at: str = Field(..., description="Thời điểm phê duyệt phiên làm việc (ISO8601)")
    message: str = Field(..., description="Thông báo kết quả phê duyệt")


class MatrixItem(BaseModel):
    """Một dòng trong ma trận đáp án tương ứng với số thứ tự câu hỏi sau hoán vị."""

    question_no: int = Field(..., ge=1, description="Số thứ tự câu hỏi trong đề thi (1..N)")
    answers: Dict[str, str] = Field(
        ...,
        description="Bảng tra đáp án của câu hỏi theo từng mã đề (ví dụ: {'101': 'A', '102': 'C'})",
    )


class AnswersMatrixResponse(BaseModel):
    """Ma trận đối soát đáp án của toàn bộ phiên đề (TASK-305)."""

    session_id: str = Field(..., description="Mã phiên làm việc (UUID)")
    total_questions: int = Field(..., ge=0, description="Tổng số câu hỏi trong ma trận")
    version_codes: List[str] = Field(
        ...,
        description="Danh sách các mã đề thi đã được sắp xếp (ví dụ: ['101', '102', '103', '104'])",
    )
    matrix: List[MatrixItem] = Field(
        ..., description="Danh sách đáp án từng câu hỏi cho tất cả mã đề"
    )


class PreviewQuestionItem(BaseModel):
    """Chi tiết một câu hỏi sau hoán vị trong đề xem trước (W4-MVP-05)."""

    id: str = Field(..., description="Mã định danh duy nhất của câu hỏi phiên bản (UUID)")
    source_question_id: str = Field(..., description="Mã định danh câu hỏi nguồn tương ứng (UUID)")
    question_no: int = Field(
        ..., ge=1, le=20, description="Thứ tự hiển thị của câu hỏi sau hoán vị (1..N)"
    )
    canonical_question_no: int = Field(
        ..., ge=1, description="Thứ tự gốc của câu hỏi trong đề nguồn"
    )
    content: str = Field(..., description="Nội dung đề bài câu hỏi")
    options: List[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Danh sách 4 phương án hiển thị theo thứ tự [A, B, C, D]",
    )
    correct_key: Literal["A", "B", "C", "D"] = Field(
        ..., description="Đáp án đúng hiển thị tương ứng với thứ tự options mới ('A'..'D')"
    )
    solution_md: str = Field(..., description="Lời giải chi tiết đã đồng bộ nhãn đáp án hiển thị")
    status: str = Field(..., description="Trạng thái thẩm định của câu hỏi (thường là 'approved')")


class PreviewVersionItem(BaseModel):
    """Chi tiết một phiên bản đề thi sau hoán vị trong bản xem trước (W4-MVP-05)."""

    id: str = Field(..., description="Mã phiên bản đề thi (UUID)")
    version_code: str = Field(..., description="Mã đề thi (ví dụ: '101', '102')")
    is_finalized: bool = Field(..., description="Đánh dấu phiên bản đã hoàn tất hoán vị chốt đề")
    shuffle_seed: Optional[str] = Field(
        None, description="Seed ngẫu nhiên xác định dùng cho hoán vị"
    )
    total_questions: int = Field(..., ge=1, le=20, description="Tổng số câu hỏi trong phiên bản đề")
    questions: List[PreviewQuestionItem] = Field(
        ...,
        description="Danh sách câu hỏi theo đúng thứ tự in đề (question_no 1..N)",
    )
    answer_keys: Dict[str, str] = Field(
        ...,
        description="Bảng tra nhanh đáp án của phiên bản theo số thứ tự câu hiển thị (ví dụ: {'1': 'B', '2': 'A'})",
    )


class PreviewSnapshotResponse(BaseModel):
    """Ảnh chiếu xem trước đề thi sau hoán vị trước khi phê duyệt khóa nội dung (W4-MVP-05)."""

    session_id: str = Field(..., description="Mã phiên làm việc (UUID)")
    status: str = Field(
        ...,
        description="Trạng thái hiện tại của phiên làm việc ('reviewed', 'approved', 'exported')",
    )
    is_finalized: bool = Field(
        ..., description="Đánh dấu toàn bộ các phiên bản đề đã hoàn tất hoán vị"
    )
    n_versions: int = Field(..., ge=1, le=4, description="Số lượng mã đề thi được tạo")
    total_questions: int = Field(..., ge=1, le=20, description="Số lượng câu hỏi trên mỗi đề")
    versions: List[PreviewVersionItem] = Field(
        ..., description="Danh sách chi tiết từng phiên bản đề đã sắp xếp theo mã đề"
    )
    matrix: List[MatrixItem] = Field(
        ...,
        description="Ma trận đối soát đáp án chéo giữa các mã đề theo thứ tự câu 1..N",
    )


class OrderingPreferencesPayload(BaseModel):
    shuffle_questions: StrictBool
    shuffle_options: StrictBool

    model_config = ConfigDict(extra="forbid")


class OrderingPreferencesResponse(BaseModel):
    success: bool
    session_id: str
    status: str
    ordering_preferences: Dict[str, bool]


class ReviewSnapshotSource(BaseModel):
    """Câu hỏi nguồn đã xác nhận và đóng băng trong snapshot (W4-MVP-03)."""

    source_question_id: UUID = Field(..., description="Mã định danh câu nguồn (UUID)")
    question_no: int = Field(..., ge=1, description="Số thứ tự câu nguồn (1..M)")
    source_revision_id: UUID = Field(..., description="Mã phiên bản nguồn đã xác nhận (UUID)")
    content: str = Field(..., description="Nội dung câu hỏi nguồn")
    options: List[str] = Field(..., description="Danh sách 4 phương án [A, B, C, D]")
    correct_key: Literal["A", "B", "C", "D"] = Field(..., description="Đáp án đúng của câu nguồn")
    solution_md: Optional[str] = Field(None, description="Lời giải chi tiết câu nguồn (Markdown)")

    @field_validator("options")
    @classmethod
    def validate_options_length(cls, v: List[str]) -> List[str]:
        if len(v) != 4:
            raise ValueError("options must contain exactly 4 elements")
        return [str(opt) for opt in v]


class ReviewSnapshotCandidate(BaseModel):
    """Biến thể câu hỏi hiện hành hiển thị tại một slot thẩm định (W4-MVP-03)."""

    candidate_id: UUID = Field(..., description="Mã biến thể câu hỏi (version_questions.id)")
    status: Literal["pending_review", "approved", "rejected", "regenerating"] = Field(
        ..., description="Trạng thái thẩm định của biến thể"
    )
    content: str = Field(..., description="Nội dung câu hỏi biến thể")
    options: List[str] = Field(..., description="Danh sách 4 phương án [A, B, C, D]")
    correct_key: Literal["A", "B", "C", "D"] = Field(..., description="Đáp án đúng biến thể")
    solution_md: Optional[str] = Field(None, description="Lời giải chi tiết biến thể")
    has_warning: bool = Field(False, description="Cờ cảnh báo kiểm định toán học hoặc định dạng")
    validation_report: Optional[Dict[str, Any]] = Field(
        None, description="Báo cáo kiểm định toán học on-the-fly"
    )
    validation_source: Literal["version_question", "generation_result", "unavailable"] = Field(
        ..., description="Nguồn xuất xứ của báo cáo kiểm định"
    )
    origin: Literal[
        "ai_generated",
        "original_clone",
        "regenerated",
        "reverted",
        "confirmed_source_fallback",
        "unknown",
    ] = Field(..., description="Nguồn gốc sinh của ứng viên biến thể")
    is_reverted: bool = Field(False, description="Biến thể đã từng bị hoàn nguyên về câu nguồn")
    updated_at: str = Field(..., description="Thời điểm cập nhật bản ghi gần nhất (ISO 8601)")

    @field_validator("options")
    @classmethod
    def validate_options_length(cls, v: List[str]) -> List[str]:
        if len(v) != 4:
            raise ValueError("options must contain exactly 4 elements")
        return [str(opt) for opt in v]


class ReviewSnapshotSlot(BaseModel):
    """Một vị trí câu hỏi trong ma trận phiên bản đề (W4-MVP-03)."""

    source_question_id: UUID = Field(..., description="Mã câu nguồn đối chiếu")
    question_no: int = Field(..., ge=1, description="Số thứ tự câu hỏi đối chiếu")
    candidate: Optional[ReviewSnapshotCandidate] = Field(
        None, description="Ứng viên hiện hành duy nhất hoặc null nếu slot còn thiếu"
    )


class ReviewSnapshotVersion(BaseModel):
    """Một phiên bản đề thi trong ma trận thẩm định (W4-MVP-03)."""

    version_index: int = Field(..., ge=1, le=4, description="Chỉ số phiên bản (1..4)")
    version_code: str = Field(..., description="Mã đề thi hiển thị (ví dụ '101')")
    version_id: Optional[UUID] = Field(
        None, description="Mã phiên bản (UUID) nếu đã được lưu CSDL"
    )
    slots: List[ReviewSnapshotSlot] = Field(
        ..., description="Danh sách các slot câu hỏi của phiên bản này"
    )


class ReviewSnapshotProgress(BaseModel):
    """Tiến độ thẩm định tính toán đồng thời trong snapshot (W4-MVP-03)."""

    expected_slots: int = Field(..., ge=0, description="Tổng số slot cần có (N x M)")
    current_slots: int = Field(..., ge=0, description="Số slot hiện đã có candidate")
    approved_slots: int = Field(..., ge=0, description="Số candidate đã được duyệt")
    missing_slots: int = Field(..., ge=0, description="Số slot còn thiếu chưa sinh")
    ready: bool = Field(False, description="Đã duyệt đủ toàn bộ ma trận câu hỏi")


class ReviewSnapshotResponse(BaseModel):
    """Snapshot hiện hành của quy trình thẩm định Stage 3 (W4-MVP-03)."""

    session_id: UUID = Field(..., description="Mã phiên làm việc")
    session_status: str = Field(..., description="Trạng thái phiên làm việc")
    read_only: bool = Field(..., description="Cờ giao diện chỉ đọc")
    confirmation_id: UUID = Field(..., description="Mã xác nhận nguồn")
    job_snapshot_id: UUID = Field(..., description="Mã snapshot công việc sinh")
    confirmed_source_hash: str = Field(..., description="Mã băm SHA-256 nguồn đóng băng")
    freshness_token: str = Field(..., description="Token kiểm tra tính tươi mới của trạng thái")
    progress: ReviewSnapshotProgress = Field(..., description="Thống kê tiến độ thẩm định")
    sources: List[ReviewSnapshotSource] = Field(
        ..., description="Danh sách câu nguồn đã đóng băng"
    )
    versions: List[ReviewSnapshotVersion] = Field(
        ..., description="Ma trận các phiên bản đề và slot ứng viên"
    )


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
    "RollbackErrorCode",
    "ReviewActionResponse",
    "RegeneratedQuestionResponse",
    "ReviewProgressResponse",
    "ErrorDetailResponse",
    "ReviewDomainException",
    "ReviewAcquireUnavailableError",
    "FinalizeApproveResponse",
    "MatrixItem",
    "AnswersMatrixResponse",
    "PreviewQuestionItem",
    "PreviewVersionItem",
    "PreviewSnapshotResponse",
    "OrderingPreferencesPayload",
    "OrderingPreferencesResponse",
    "CheckResult",
    "ValidationReport",
    "ReviewSnapshotSource",
    "ReviewSnapshotCandidate",
    "ReviewSnapshotSlot",
    "ReviewSnapshotVersion",
    "ReviewSnapshotProgress",
    "ReviewSnapshotResponse",
]
