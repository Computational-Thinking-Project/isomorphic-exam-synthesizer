import { api } from './api.js';

/**
 * Phê duyệt một câu hỏi biến thể (TASK-301 / Stage 3 Review)
 * POST /api/sessions/{session_id}/questions/{version_question_id}/accept
 *
 * @param {string} sessionId
 * @param {string} questionId
 * @param {string|null} idempotencyKey
 * @returns {Promise<object>}
 */
export async function acceptQuestion(sessionId, questionId, idempotencyKey = null, config = {}) {
  if (!sessionId || !questionId) {
    throw new Error('Cần cung cấp sessionId và questionId hợp lệ.');
  }

  const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey, ...config.headers } : { ...config.headers };
  const response = await api.post(
    `/sessions/${sessionId}/questions/${questionId}/accept`,
    null,
    {
      ...config,
      headers,
    }
  );
  return response.data;
}

/**
 * Từ chối câu hỏi biến thể và kích hoạt AI sinh lại câu mới (Reject & Targeted Regeneration)
 * POST /api/sessions/{session_id}/questions/{version_question_id}/reject
 *
 * Lưu ý: backend ReviewService có timeout sinh lại câu hỏi 45s, nên client cấu hình timeout 60s
 * để tránh Axios ngắt sớm khi backend đang hoàn tất tạo biến thể.
 *
 * @param {string} sessionId
 * @param {string} questionId
 * @param {string|null} idempotencyKey
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function rejectAndRegenerateQuestion(sessionId, questionId, idempotencyKey = null, config = {}) {
  if (!sessionId || !questionId) {
    throw new Error('Cần cung cấp sessionId và questionId hợp lệ.');
  }

  const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey, ...config.headers } : { ...config.headers };
  const response = await api.post(
    `/sessions/${sessionId}/questions/${questionId}/reject`,
    null,
    {
      timeout: 60000,
      ...config,
      headers,
    }
  );
  return response.data;
}

/**
 * Lấy số liệu tiến độ duyệt bài của toàn phiên
 * GET /api/sessions/{session_id}/review/progress
 *
 * @param {string} sessionId
 * @returns {Promise<object>}
 */
export async function fetchReviewProgress(sessionId) {
  if (!sessionId) {
    throw new Error('Cần cung cấp sessionId hợp lệ.');
  }

  const response = await api.get(`/sessions/${sessionId}/review/progress`);
  return response.data;
}
