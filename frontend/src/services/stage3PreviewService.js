import { api } from './api.js';

/**
 * Fixture chuẩn của bản xem trước sau khi hoán vị (Golden Fixture PR #49 / W4-MVP-05).
 * Dùng làm mock fallback khi chạy trong môi trường kiểm thử hoặc dev standalone.
 */
export const GOLDEN_PREVIEW_FIXTURE = {
  session_id: '00000000-0000-0000-0000-000000000001',
  status: 'reviewed',
  is_finalized: true,
  n_versions: 2,
  total_questions: 3,
  versions: [
    {
      id: '10100000-0000-0000-0000-000000000101',
      version_code: '101',
      is_finalized: true,
      shuffle_seed: 'golden-seed-w4-101',
      total_questions: 3,
      questions: [
        {
          id: '11111111-0000-0000-0000-000000000101',
          source_question_id: '00000000-0000-0000-0000-000000000001',
          question_no: 1,
          canonical_question_no: 1,
          content: 'Cho hàm số $y = x^3 - 3x + 2$. Điểm cực đại của hàm số đã cho là:',
          options: ['$x = -1$', '$x = 1$', '$x = 2$', '$x = 0$'],
          correct_key: 'A',
          solution_md: 'Đạo hàm $y\' = 3x^2 - 3 = 0 \\iff x = \\pm 1$. Vì $y\'\'(-1) = -6 < 0$ nên điểm cực đại là $x = -1$. Do đó đáp án đúng là A.',
          status: 'approved',
        },
        {
          id: '11111111-0000-0000-0000-000000000102',
          source_question_id: '00000000-0000-0000-0000-000000000002',
          question_no: 2,
          canonical_question_no: 2,
          content: 'Tính tích phân $I = \\int_{0}^{1} (3x^2 + 2x) dx$.',
          options: ['$I = 1$', '$I = 3$', '$I = 2$', '$I = 4$'],
          correct_key: 'C',
          solution_md: 'Ta có nguyên hàm $F(x) = x^3 + x^2$. Khi đó $I = F(1) - F(0) = (1 + 1) - 0 = 2$. Do đó đáp án đúng là C.',
          status: 'approved',
        },
        {
          id: '11111111-0000-0000-0000-000000000103',
          source_question_id: '00000000-0000-0000-0000-000000000003',
          question_no: 3,
          canonical_question_no: 3,
          content: 'Trong không gian $Oxyz$, cho mặt cầu $(S): (x-1)^2 + (y+2)^2 + z^2 = 9$. Bán kính của mặt cầu $(S)$ là:',
          options: ['$R = 9$', '$R = 81$', '$R = \\sqrt{3}$', '$R = 3$'],
          correct_key: 'D',
          solution_md: 'Phương trình mặt cầu có dạng $(x-a)^2 + (y-b)^2 + (z-c)^2 = R^2$. Suy ra $R^2 = 9 \\implies R = 3$. Do đó đáp án đúng là D.',
          status: 'approved',
        },
      ],
      answer_keys: {
        '1': 'A',
        '2': 'C',
        '3': 'D',
      },
    },
    {
      id: '10200000-0000-0000-0000-000000000102',
      version_code: '102',
      is_finalized: true,
      shuffle_seed: 'golden-seed-w4-102',
      total_questions: 3,
      questions: [
        {
          id: '22222222-0000-0000-0000-000000000101',
          source_question_id: '00000000-0000-0000-0000-000000000001',
          question_no: 1,
          canonical_question_no: 1,
          content: 'Cho hàm số $y = x^3 - 3x + 2$. Điểm cực đại của hàm số đã cho là:',
          options: ['$x = -1$', '$x = 1$', '$x = 2$', '$x = 0$'],
          correct_key: 'A',
          solution_md: 'Đạo hàm $y\' = 3x^2 - 3 = 0 \\iff x = \\pm 1$. Vì $y\'\'(-1) = -6 < 0$ nên điểm cực đại là $x = -1$. Do đó đáp án đúng là A.',
          status: 'approved',
        },
        {
          id: '22222222-0000-0000-0000-000000000102',
          source_question_id: '00000000-0000-0000-0000-000000000002',
          question_no: 2,
          canonical_question_no: 2,
          content: 'Tính tích phân $I = \\int_{0}^{1} (3x^2 + 2x) dx$.',
          options: ['$I = 1$', '$I = 3$', '$I = 2$', '$I = 4$'],
          correct_key: 'C',
          solution_md: 'Ta có nguyên hàm $F(x) = x^3 + x^2$. Khi đó $I = F(1) - F(0) = (1 + 1) - 0 = 2$. Do đó đáp án đúng là C.',
          status: 'approved',
        },
        {
          id: '22222222-0000-0000-0000-000000000103',
          source_question_id: '00000000-0000-0000-0000-000000000003',
          question_no: 3,
          canonical_question_no: 3,
          content: 'Trong không gian $Oxyz$, cho mặt cầu $(S): (x-1)^2 + (y+2)^2 + z^2 = 9$. Bán kính của mặt cầu $(S)$ là:',
          options: ['$R = 9$', '$R = 81$', '$R = \\sqrt{3}$', '$R = 3$'],
          correct_key: 'D',
          solution_md: 'Phương trình mặt cầu có dạng $(x-a)^2 + (y-b)^2 + (z-c)^2 = R^2$. Suy ra $R^2 = 9 \\implies R = 3$. Do đó đáp án đúng là D.',
          status: 'approved',
        },
      ],
      answer_keys: {
        '1': 'A',
        '2': 'C',
        '3': 'D',
      },
    },
  ],
  matrix: [
    {
      question_no: 1,
      answers: {
        '101': 'A',
        '102': 'A',
      },
    },
    {
      question_no: 2,
      answers: {
        '101': 'C',
        '102': 'C',
      },
    },
    {
      question_no: 3,
      answers: {
        '101': 'D',
        '102': 'D',
      },
    },
  ],
};

/**
 * Chuẩn hóa đối tượng snapshot trả về từ server, đảm bảo các trường cần thiết cho UI
 * @param {object} raw
 * @returns {object}
 */
export function adaptPreviewSnapshot(raw) {
  if (!raw) return null;

  const versions = Array.isArray(raw.versions)
    ? raw.versions.map((ver) => {
        const questions = Array.isArray(ver.questions)
          ? [...ver.questions]
              .sort((a, b) => (a.question_no || 0) - (b.question_no || 0))
              .map((q) => {
                let options = q.options;
                if (options && !Array.isArray(options) && typeof options === 'object') {
                  options = ['A', 'B', 'C', 'D'].map((k) => options[k] || '');
                } else if (!Array.isArray(options)) {
                  options = [];
                }
                return {
                  ...q,
                  options,
                };
              })
          : [];

        // Đảm bảo answer_keys là map phẳng { "1": "A", ... }
        let answerKeys = ver.answer_keys || {};
        if (Array.isArray(answerKeys)) {
          const map = {};
          answerKeys.forEach((k) => {
            if (k && k.display_no) {
              map[String(k.display_no)] = k.display_correct_key || k.correct_option;
            }
          });
          answerKeys = map;
        }

        return {
          ...ver,
          questions,
          answer_keys: answerKeys,
        };
      })
    : [];

  return {
    session_id: raw.session_id,
    status: raw.status || 'reviewed',
    is_finalized: Boolean(raw.is_finalized),
    n_versions: raw.n_versions || versions.length,
    total_questions: raw.total_questions || (versions[0]?.questions?.length ?? 0),
    versions,
    matrix: Array.isArray(raw.matrix) ? raw.matrix : [],
  };
}

/**
 * Lấy dữ liệu xem trước toàn diện sau hoán vị (W4-MVP-05 / Q06)
 * GET /api/sessions/{session_id}/finalize/preview
 *
 * @param {string} sessionId
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function fetchFinalizePreview(sessionId, config = {}) {
  if (!sessionId) {
    throw new Error('Cần cung cấp sessionId hợp lệ.');
  }

  try {
    const response = await api.get(`/sessions/${sessionId}/finalize/preview`, {
      ...config,
      headers: {
        'Cache-Control': 'no-store',
        ...config.headers,
      },
    });

    return adaptPreviewSnapshot(response.data);
  } catch (err) {
    const status = err.response?.status;
    const data = err.response?.data;
    const errorCode = data?.error_code || (typeof data?.detail === 'string' ? data.detail : null);
    const detail = typeof data?.detail === 'string' ? data.detail : data?.message || err.message;

    const error = new Error(detail || 'Không thể tải bản xem trước đề thi.');
    error.status = status;
    error.errorCode = errorCode;
    error.detail = detail;
    error.response = err.response;
    throw error;
  }
}

/**
 * Cập nhật cấu hình xáo trộn trước khi kích hoạt (PR #61)
 * PATCH /api/sessions/{session_id}/ordering-preferences
 *
 * @param {string} sessionId
 * @param {object} preferences - { shuffle_questions: boolean, shuffle_options: boolean }
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function updateOrderingPreferences(sessionId, preferences = {}, config = {}) {
  if (!sessionId) {
    throw new Error('Cần cung cấp sessionId hợp lệ.');
  }

  const payload = {
    shuffle_questions: Boolean(preferences.shuffle_questions),
    shuffle_options: Boolean(preferences.shuffle_options),
  };

  const response = await api.patch(
    `/sessions/${sessionId}/ordering-preferences`,
    payload,
    config
  );

  return response.data;
}

/**
 * Kích hoạt thuật toán hoán vị Fisher-Yates trên server (TASK-305)
 * POST /api/sessions/{session_id}/finalize/shuffle
 *
 * @param {string} sessionId
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function triggerFinalizeShuffle(sessionId, config = {}) {
  if (!sessionId) {
    throw new Error('Cần cung cấp sessionId hợp lệ.');
  }

  const response = await api.post(
    `/sessions/${sessionId}/finalize/shuffle`,
    null,
    config
  );

  return response.data;
}

/**
 * Thực hiện chuỗi xáo trộn hoàn chỉnh: Tự động lưu preferences true/true và kích hoạt Shuffle
 * @param {string} sessionId
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function executeFullShuffle(sessionId, config = {}) {
  await updateOrderingPreferences(
    sessionId,
    { shuffle_questions: true, shuffle_options: true },
    config
  );

  return await triggerFinalizeShuffle(sessionId, config);
}

/**
 * Phê duyệt phiên làm việc và kích hoạt khóa vĩnh viễn nội dung HTTP 423 (TASK-305)
 * POST /api/sessions/{session_id}/finalize/approve
 *
 * @param {string} sessionId
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function triggerFinalizeApprove(sessionId, config = {}) {
  if (!sessionId) {
    throw new Error('Cần cung cấp sessionId hợp lệ.');
  }

  const response = await api.post(
    `/sessions/${sessionId}/finalize/approve`,
    null,
    config
  );

  return response.data;
}
