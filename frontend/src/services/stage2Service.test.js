import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api } from './api.js';
import {
  fetchSessionDetail,
  saveSessionConfig,
  startGeneration,
  retryGeneration,
  requestEventTicket,
} from './stage2Service.js';

test('saveSessionConfig CHỈ gửi đúng tên trường theo contract 207a (không gửi num_versions/variation_modes)', async () => {
  let capturedPost = null;
  const originalPost = api.post;

  api.post = async (url, payload) => {
    capturedPost = { url, payload };
    return { data: { success: true } };
  };

  try {
    await saveSessionConfig('session-contract-1', {
      n_versions: 3,
      num_versions: 3,
      active_variation_modes: ['parameter_variation'],
      variation_modes: ['parameter_variation'],
      ordering_preferences: { shuffle_questions: true },
    });

    assert.ok(capturedPost);
    assert.equal(capturedPost.url, '/sessions/session-contract-1/config');
    assert.deepEqual(Object.keys(capturedPost.payload).sort(), [
      'active_variation_modes',
      'n_versions',
      'ordering_preferences',
    ]);
    assert.equal(capturedPost.payload.n_versions, 3);
    assert.deepEqual(capturedPost.payload.active_variation_modes, ['parameter_variation']);
    assert.deepEqual(capturedPost.payload.ordering_preferences, {
      shuffle_questions: true,
      shuffle_options: false,
    });
    assert.equal(capturedPost.payload.num_versions, undefined, 'Không được chứa num_versions');
    assert.equal(capturedPost.payload.variation_modes, undefined, 'Không được chứa variation_modes');
  } finally {
    api.post = originalPost;
  }
});

test('fetchSessionDetail tính phần giao các chế độ Blueprint: chỉ bật is_available khi toàn bộ câu hỏi hỗ trợ', async () => {
  const originalGet = api.get;

  // Q1 hỗ trợ [NUMERICAL, NONE], Q2 chỉ hỗ trợ [NONE]
  api.get = async () => ({
    data: {
      id: 'session-intersection',
      title: 'Đề kiểm tra phần giao',
      status: 'blueprinted',
      source_questions: [
        { id: 'q1', variation_modes: ['NUMERICAL', 'NONE'] },
        { id: 'q2', variation_modes: ['NONE'] },
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-intersection');
    assert.ok(detail.blueprint_summary);
    assert.equal(detail.blueprint_summary.total_questions, 2);

    const paramMode = detail.blueprint_summary.supported_modes.find(
      (m) => m.id === 'NUMERICAL',
    );
    assert.ok(paramMode, 'Phải có chế độ NUMERICAL (giữ nguyên ID gốc)');
    assert.equal(paramMode.label, 'Thay đổi số liệu / tham số');
    assert.equal(paramMode.question_count, 1);
    assert.equal(
      paramMode.is_available,
      false,
      'Vì chỉ 1/2 câu hỏi hỗ trợ nên mode không được coi là is_available',
    );
    assert.ok(paramMode.unavailable_reason.includes('1/2 câu'));
  } finally {
    api.get = originalGet;
  }
});

test('fetchSessionDetail bật is_available khi 100% câu hỏi trong đề đều hỗ trợ chế độ đó và giữ nguyên ID gốc NUMERICAL', async () => {
  const originalGet = api.get;

  // Cả Q1 và Q2 đều hỗ trợ NUMERICAL (giữ nguyên ID gốc để không xung đột ERR_CONFIG_CONFLICT với policy backend)
  api.get = async () => ({
    data: {
      id: 'session-full-support',
      title: 'Đề 100% hỗ trợ NUMERICAL',
      status: 'blueprinted',
      source_questions: [
        { id: 'q1', variation_modes: ['NUMERICAL'] },
        { id: 'q2', variation_modes: ['NUMERICAL'] },
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-full-support');
    const numericalMode = detail.blueprint_summary.supported_modes.find(
      (m) => m.id === 'NUMERICAL',
    );
    assert.ok(numericalMode, 'Phải giữ nguyên ID gốc NUMERICAL từ Blueprint');
    assert.equal(numericalMode.label, 'Thay đổi số liệu / tham số');
    assert.equal(numericalMode.question_count, 2);
    assert.equal(numericalMode.is_available, true, '100% câu hỏi hỗ trợ thì is_available phải là true');
  } finally {
    api.get = originalGet;
  }
});

test('startGeneration và requestEventTicket gọi đúng endpoint POST tương ứng', async () => {
  const calls = [];
  const originalPost = api.post;

  api.post = async (url) => {
    calls.push(url);
    return { data: { ticket: 'ticket-ok' } };
  };

  try {
    await startGeneration('sess-100');
    await requestEventTicket('sess-100');

    assert.equal(calls[0], '/sessions/sess-100/generate');
    assert.equal(calls[1], '/sessions/sess-100/events/ticket');
  } finally {
    api.post = originalPost;
  }
});

test('retryGeneration gọi đúng endpoint POST /sessions/:id/retry-generation theo contract W2', async () => {
  let calledUrl = null;
  const originalPost = api.post;

  api.post = async (url) => {
    calledUrl = url;
    return { data: { success: true } };
  };

  try {
    await retryGeneration('sess-retry-99');
    assert.equal(calledUrl, '/sessions/sess-retry-99/retry-generation');
  } finally {
    api.post = originalPost;
  }
});

test('fetchSessionDetail phân biệt hoa/thường (case-sensitive) chính xác theo Policy 207a: NUMERICAL khác numerical', async () => {
  const originalGet = api.get;

  // Q1 hỗ trợ NUMERICAL, Q2 hỗ trợ numerical (hai chuỗi khác nhau về case)
  api.get = async () => ({
    data: {
      id: 'session-case-sensitive',
      title: 'Đề kiểm tra case sensitivity',
      status: 'blueprinted',
      source_questions: [
        { id: 'q1', variation_modes: ['NUMERICAL'] },
        { id: 'q2', variation_modes: ['numerical'] },
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-case-sensitive');
    const upperMode = detail.blueprint_summary.supported_modes.find((m) => m.id === 'NUMERICAL');
    const lowerMode = detail.blueprint_summary.supported_modes.find((m) => m.id === 'numerical');

    assert.ok(upperMode, 'Phải có mục NUMERICAL riêng');
    assert.ok(lowerMode, 'Phải có mục numerical riêng');
    assert.equal(upperMode.question_count, 1);
    assert.equal(lowerMode.question_count, 1);
    assert.equal(upperMode.is_available, false, 'Chỉ 1/2 câu hỗ trợ NUMERICAL nên is_available phải false');
    assert.equal(lowerMode.is_available, false, 'Chỉ 1/2 câu hỗ trợ numerical nên is_available phải false');
  } finally {
    api.get = originalGet;
  }
});

test('saveSessionConfig gửi shuffle_options: true khi người dùng chọn xáo đáp án', async () => {
  let capturedPost = null;
  const originalPost = api.post;

  api.post = async (url, payload) => {
    capturedPost = payload;
    return { data: { success: true } };
  };

  try {
    await saveSessionConfig('session-shuffle-opt', {
      n_versions: 2,
      active_variation_modes: ['parameter_variation'],
      ordering_preferences: {
        shuffle_questions: true,
        shuffle_options: true,
      },
    });

    assert.ok(capturedPost);
    assert.deepEqual(capturedPost.ordering_preferences, {
      shuffle_questions: true,
      shuffle_options: true,
    });
  } finally {
    api.post = originalPost;
  }
});

test('fetchSessionDetail đánh dấu is_ready: true và supported_modes: [] khi tất cả câu hỏi chỉ hỗ trợ NONE', async () => {
  const originalGet = api.get;
  api.get = async () => ({
    data: {
      id: 'session-none-only',
      status: 'blueprinted',
      source_questions: [
        { id: 'q1', variation_modes: ['NONE'] },
        { id: 'q2', variation_modes: ['none'] },
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-none-only');
    assert.ok(detail.blueprint_summary, 'Phải có blueprint_summary');
    assert.equal(detail.blueprint_summary.is_ready, true, 'Blueprint phải sẵn sàng');
    assert.equal(detail.blueprint_summary.total_questions, 2);
    assert.deepEqual(detail.blueprint_summary.supported_modes, [], 'supported_modes phải là mảng rỗng');
  } finally {
    api.get = originalGet;
  }
});

test('fetchSessionDetail trả blueprint_summary: null khi có câu hỏi nguồn thiếu dữ liệu Blueprint', async () => {
  const originalGet = api.get;
  api.get = async () => ({
    data: {
      id: 'session-incomplete-blueprint',
      status: 'blueprinted',
      source_questions: [
        { id: 'q1', variation_modes: ['parameter_variation'] },
        { id: 'q2' }, // q2 không có question_blueprints, blueprint, variation_modes
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-incomplete-blueprint');
    assert.equal(detail.blueprint_summary, null, 'Blueprint chưa hoàn thiện thì blueprint_summary phải là null');
  } finally {
    api.get = originalGet;
  }
});

test('fetchSessionDetail tính fallback supported_modes từ source_questions nếu backend trả summary thiếu supported_modes (F02/PR32)', async () => {
  const originalGet = api.get;
  api.get = async () => ({
    data: {
      id: 'session-pr32-summary',
      status: 'blueprinted',
      blueprint_summary: {
        is_ready: true,
        counts: { total: 2, blueprinted: 2 },
        // supported_modes bị thiếu từ PR #32
      },
      source_questions: [
        { id: 'q1', variation_modes: ['NUMERICAL', 'context_swap'] },
        { id: 'q2', variation_modes: ['NUMERICAL'] },
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-pr32-summary');
    assert.ok(detail.blueprint_summary);
    assert.equal(detail.blueprint_summary.is_ready, true);
    assert.ok(Array.isArray(detail.blueprint_summary.supported_modes));

    const numMode = detail.blueprint_summary.supported_modes.find((m) => m.id === 'NUMERICAL');
    assert.ok(numMode, 'Phải có NUMERICAL được bóc tách từ source_questions');
    assert.equal(numMode.is_available, true, '100% câu hỗ trợ NUMERICAL');

    const ctxMode = detail.blueprint_summary.supported_modes.find((m) => m.id === 'context_swap');
    assert.ok(ctxMode);
    assert.equal(ctxMode.is_available, false, 'Chỉ 1/2 câu hỗ trợ context_swap');
  } finally {
    api.get = originalGet;
  }
});

test('fetchSessionDetail khôi phục snapshot tiến độ và bản đồ câu hỏi khi F5/reload phiên partial_generated', async () => {
  const originalGet = api.get;
  api.get = async () => ({
    data: {
      id: 'session-reload-partial',
      status: 'partial_generated',
      generation_config: {
        n_versions: 2,
        active_variation_modes: ['parameter_variation'],
        ordering_preferences: { shuffle_questions: true, shuffle_options: false },
      },
      source_questions: [{ id: 'q1' }, { id: 'q2' }],
      exam_versions: [
        {
          version_index: 1,
          version_code: '101',
          questions: [
            { question_no: 1, status: 'done' },
            { question_no: 2, status: 'done' },
          ],
        },
        {
          version_index: 2,
          version_code: '102',
          questions: [
            { question_no: 1, status: 'done' },
            // question_no: 2 bị thiếu
          ],
        },
      ],
    },
  });

  try {
    const detail = await fetchSessionDetail('session-reload-partial');
    assert.ok(detail.progress, 'Phải có progress snapshot khôi phục');
    assert.equal(detail.progress.completedCount, 3);
    assert.equal(detail.progress.totalCount, 4);
    assert.equal(detail.progress.percent, 75);
    assert.equal(detail.progress.is_partial, true);

    assert.equal(detail.question_statuses['1-1']?.status, 'done');
    assert.equal(detail.question_statuses['1-2']?.status, 'done');
    assert.equal(detail.question_statuses['2-1']?.status, 'done');
    assert.equal(detail.question_statuses['2-2'], undefined, 'Câu 2 mã 2 chưa sinh');
  } finally {
    api.get = originalGet;
  }
});
