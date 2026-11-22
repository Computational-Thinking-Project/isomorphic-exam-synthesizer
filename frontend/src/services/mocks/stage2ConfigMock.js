/**
 * Mock Service cho Stage 2: Cấu hình sinh đề và tiến trình thời gian thực SSE.
 * Phục vụ phát triển giao diện độc lập, xem trước (preview) và kiểm thử offline.
 */

export const mockStage2Session = {
  id: 'mock-session-stage2-001',
  user_id: 'mock-user-fe2',
  title: 'Đề kiểm tra Giải tích 12 — Chương 1: Đạo hàm và Khảo sát đồ thị',
  subject: 'Toán',
  grade: 12,
  status: 'blueprinted',
  created_at: '2026-10-27T08:00:00Z',
  blueprint_summary: {
    is_ready: true,
    total_questions: 10,
    supported_modes: [
      {
        id: 'parameter_variation',
        label: 'Thay đổi số liệu / tham số',
        description: 'Giữ nguyên cấu trúc đề bài toán, thay đổi tham số đảm bảo nghiệm đẹp và không suy biến.',
        question_count: 10,
        is_available: true,
      },
      {
        id: 'context_swap',
        label: 'Đổi ngữ cảnh thực tế',
        description: 'Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.',
        question_count: 7,
        is_available: true,
      },
      {
        id: 'variable_inversion',
        label: 'Hoán đổi ẩn số',
        description: 'Đổi vị trí đại lượng đã cho và đại lượng cần tìm trong câu hỏi.',
        question_count: 3,
        is_available: false,
        unavailable_reason: 'Chưa đủ điều kiện biến đổi hai chiều cho 7/10 câu hỏi trong đề.',
      },
    ],
  },
  source_questions: Array.from({ length: 10 }, (_, index) => ({
    id: `q-src-${index + 1}`,
    question_no: index + 1,
    topic: index < 5 ? 'Tính đơn điệu của hàm số' : 'Cực trị và Giá trị lớn nhất - nhỏ nhất',
    question_text: `Câu ${index + 1}: Cho hàm số $y = f(x)$ xác định trên $\\mathbb{R}$. Tìm các khoảng đơn điệu hoặc cực trị.`,
    options: [
      '$(-\\infty; 1)$',
      '$(1; +\\infty)$',
      '$(0; 2)$',
      '$\\mathbb{R} \\setminus \\{1\\}$',
    ],
    correct_answer: '$(1; +\\infty)$',
  })),
  config: null,
};

let currentMockSession = JSON.parse(JSON.stringify(mockStage2Session));

export function resetMockSession(initial = mockStage2Session) {
  currentMockSession = JSON.parse(JSON.stringify(initial));
  return currentMockSession;
}

export async function getStage2Session(sessionId, { scenario = 'success', delayMs = 150 } = {}) {
  if (delayMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  if (scenario === 'error') {
    throw new Error('Lỗi máy chủ khi tải thông tin phiên làm việc. Vui lòng thử lại.');
  }

  if (scenario === 'not_found' || !sessionId) {
    const error = new Error('Không tìm thấy phiên làm việc yêu cầu.');
    error.status = 404;
    throw error;
  }

  if (scenario === 'draft_not_ready') {
    return {
      ...currentMockSession,
      id: sessionId,
      status: 'draft',
    };
  }

  if (scenario === 'configured') {
    return {
      ...currentMockSession,
      id: sessionId,
      status: 'configured',
      config: {
        num_versions: 2,
        variation_modes: ['parameter_variation'],
        ordering_preferences: {
          shuffle_questions: true,
        },
      },
    };
  }

  return {
    ...currentMockSession,
    id: sessionId,
  };
}

export async function saveStage2Config(sessionId, configPayload, { scenario = 'success', delayMs = 200 } = {}) {
  if (delayMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  if (scenario === 'error_network') {
    throw new Error('Mất kết nối mạng khi lưu cấu hình.');
  }

  if (scenario === 'error_conflict') {
    const error = new Error('Cấu hình xung đột với Blueprint hiện hành của phiên làm việc.');
    error.code = 'ERR_CONFIG_CONFLICT';
    error.status = 400;
    error.conflicting_modes = ['variable_inversion'];
    throw error;
  }

  const nVersions = Number(configPayload?.n_versions ?? configPayload?.num_versions);

  if (!nVersions || nVersions < 1 || nVersions > 4) {
    const error = new Error('Số lượng mã đề phải nằm trong khoảng từ 1 đến 4.');
    error.status = 422;
    throw error;
  }

  const rawModes = Array.isArray(configPayload?.active_variation_modes)
    ? configPayload.active_variation_modes
    : Array.isArray(configPayload?.variation_modes)
    ? configPayload.variation_modes
    : [];

  const updatedConfig = {
    n_versions: nVersions,
    num_versions: nVersions,
    active_variation_modes: rawModes,
    ordering_preferences: {
      shuffle_questions: Boolean(configPayload?.ordering_preferences?.shuffle_questions ?? false),
      shuffle_options: Boolean(configPayload?.ordering_preferences?.shuffle_options ?? false),
    },
  };

  currentMockSession = {
    ...currentMockSession,
    id: sessionId,
    status: 'configured',
    config: updatedConfig,
  };

  return {
    ok: true,
    session: JSON.parse(JSON.stringify(currentMockSession)),
  };
}

export async function triggerGeneration(sessionId, { scenario = 'success', delayMs = 200 } = {}) {
  if (delayMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  if (scenario === 'error') {
    throw new Error('Không thể khởi động tiến trình sinh đề.');
  }

  currentMockSession.status = 'generating';

  return {
    ok: true,
    job_id: `job-${Date.now()}`,
    session_id: sessionId,
    status: 'generating',
  };
}

export async function createEventTicket(sessionId, { scenario = 'success', delayMs = 100 } = {}) {
  if (delayMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  if (scenario === 'error') {
    throw new Error('Không thể cấp ticket xác thực sự kiện.');
  }

  const ticket = `sse-ticket-${Math.random().toString(36).slice(2, 10)}`;
  const expiresAt = new Date(Date.now() + 60000).toISOString();

  return {
    ticket,
    expires_at: expiresAt,
  };
}
