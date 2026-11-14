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

/**
 * Chuẩn hóa đối tượng options từ mảng hoặc dictionary sang format { A: ..., B: ..., C: ..., D: ... }
 *
 * @param {Array<string>|object|null} options
 * @returns {object}
 */
export function normalizeOptions(options) {
  if (!options) return {};
  if (Array.isArray(options)) {
    const letters = ['A', 'B', 'C', 'D'];
    const res = {};
    options.forEach((opt, idx) => {
      if (idx < 4) res[letters[idx]] = opt;
    });
    return res;
  }
  return options;
}

/**
 * Lấy snapshot hiện hành của quy trình Review (Stage 3) trước khi shuffle (PR #54 contract)
 * GET /api/sessions/{session_id}/review/snapshot
 *
 * @param {string} sessionId
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function fetchReviewSnapshot(sessionId, config = {}) {
  if (!sessionId) {
    throw new Error('Cần cung cấp sessionId hợp lệ.');
  }

  const response = await api.get(`/sessions/${sessionId}/review/snapshot`, {
    ...config,
    headers: {
      'Cache-Control': 'no-store',
      ...config.headers,
    },
  });
  return response.data;
}

/**
 * Chuyển đổi dữ liệu từ Contract GET /api/sessions/{session_id}/review/snapshot (PR #54)
 * sang view model chuẩn của Stage 3 Review UI, bảo toàn khả năng tương thích ngược.
 *
 * @param {object} raw - Response từ review snapshot API hoặc session detail cũ
 * @param {object|null} detail - Dữ liệu session detail bổ trợ nếu có
 * @returns {object|null}
 */
export function adaptReviewSnapshot(raw, detail = null) {
  if (!raw) return null;

  // Tương thích ngược: nếu raw đã là format cũ (exam_versions / source_questions) và không có snapshot versions/sources
  if (!Array.isArray(raw.versions) && Array.isArray(raw.exam_versions)) {
    return raw;
  }

  const rawSources = Array.isArray(raw.sources) ? raw.sources : [];
  const sourceQuestions = rawSources.map((s, idx) => ({
    id: s.source_question_id || `sq-${s.question_no ?? idx + 1}`,
    source_question_id: s.source_question_id,
    question_no: s.question_no ?? idx + 1,
    number: s.question_no ?? idx + 1,
    content: s.content || '',
    raw_content: s.content || '',
    options: normalizeOptions(s.options),
    correct_key: s.correct_key || 'A',
    solution_md: s.solution_md || '',
  }));

  const rawVersions = Array.isArray(raw.versions) ? raw.versions : [];
  const examVersions = rawVersions.map((v, vIdx) => {
    const versionIndex = v.version_index ?? vIdx + 1;
    const versionCode = v.version_code || String(100 + versionIndex);
    const slots = Array.isArray(v.slots) ? v.slots : [];

    const questions = [];
    slots.forEach((slot, sIdx) => {
      const qNo = slot.question_no ?? sIdx + 1;
      const c = slot.candidate;
      if (!c) {
        // candidate === null là missing slot, tuyệt đối KHÔNG đưa vào questions
        return;
      }

      const isFallback =
        c.origin === 'original_clone' ||
        c.origin === 'confirmed_source_fallback' ||
        Boolean(c.is_fallback);

      questions.push({
        id: c.candidate_id,
        candidate_id: c.candidate_id,
        question_id: c.candidate_id,
        source_question_id: slot.source_question_id,
        question_no: qNo,
        number: qNo,
        version_index: versionIndex,
        version_code: versionCode,
        status: c.status || 'pending_review',
        content: c.content || '',
        raw_content: c.content || '',
        options: normalizeOptions(c.options),
        correct_key: c.correct_key || '',
        solution_md: c.solution_md || '',
        has_warning: Boolean(c.has_warning),
        validation_report: c.validation_report || null,
        validation_source: c.validation_source || 'unavailable',
        origin: c.origin || 'ai_generated',
        is_reverted: Boolean(c.is_reverted),
        updated_at: c.updated_at || null,
        is_fallback: isFallback,
        source_fallback: isFallback,
        warning_message: c.warning_message || c.validation_report?.warning || null,
      });
    });

    return {
      version_index: versionIndex,
      version_code: versionCode,
      version_id: v.version_id || null,
      questions,
      slots,
    };
  });

  const sessionStatus = raw.session_status || raw.status || detail?.status || 'generated';

  return {
    id: raw.session_id || detail?.id,
    session_id: raw.session_id || detail?.id,
    title: detail?.title || raw.title || 'Xem & Duyệt Đề Thi Đẳng Cấu',
    subject: detail?.subject || raw.subject || 'Toán',
    grade: detail?.grade || raw.grade || 12,
    status: sessionStatus,
    session_status: sessionStatus,
    read_only: Boolean(raw.read_only),
    confirmation_id: raw.confirmation_id || null,
    job_snapshot_id: raw.job_snapshot_id || null,
    confirmed_source_hash: raw.confirmed_source_hash || null,
    freshness_token: raw.freshness_token || null,
    progress: raw.progress || null,
    config: {
      n_versions: examVersions.length || detail?.config?.n_versions || 1,
      ...(detail?.config || {}),
    },
    source_questions: sourceQuestions,
    exam_versions: examVersions,
    raw_snapshot: raw,
  };
}
