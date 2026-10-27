import { api } from './api.js';

/**
 * Service giao tiếp API cho Stage 2: Cấu hình và Sinh đề bất đồng bộ.
 */

export async function fetchSessionDetail(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.get(`/sessions/${encodeURIComponent(sessionId)}`);
  const data = response.data;

  // Chuẩn hóa cấu trúc blueprint_summary nếu backend trả về dạng thô
  const totalQuestions = data.source_questions?.length ?? 0;
  const blueprintSummary = data.blueprint_summary || {
    total_questions: totalQuestions,
    supported_modes: [
      {
        id: 'parameter_variation',
        label: 'Thay đổi số liệu / tham số',
        description: 'Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.',
        question_count: totalQuestions,
        is_available: true,
      },
      {
        id: 'context_swap',
        label: 'Đổi ngữ cảnh thực tế',
        description: 'Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.',
        question_count: totalQuestions,
        is_available: true,
      },
      {
        id: 'variable_inversion',
        label: 'Hoán đổi ẩn số',
        description: 'Đổi vị trí đại lượng đã cho và đại lượng cần tìm trong bài toán.',
        question_count: Math.max(0, Math.floor(totalQuestions / 2)),
        is_available: false,
        unavailable_reason: 'Chưa đủ điều kiện biến đổi hai chiều cho toàn bộ câu hỏi trong đề.',
      },
    ],
  };

  return {
    ...data,
    blueprint_summary: blueprintSummary,
  };
}

export async function saveSessionConfig(sessionId, configPayload) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/config`,
    configPayload,
  );
  return response.data;
}

export async function startGeneration(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/generate`,
  );
  return response.data;
}

export async function requestEventTicket(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/events/ticket`,
  );
  return response.data;
}
