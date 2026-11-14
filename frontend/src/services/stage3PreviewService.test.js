import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api } from './api.js';
import {
  fetchFinalizePreview,
  updateOrderingPreferences,
  triggerFinalizeShuffle,
  executeFullShuffle,
  triggerFinalizeApprove,
  adaptPreviewSnapshot,
  GOLDEN_PREVIEW_FIXTURE,
} from './stage3PreviewService.js';

test('fetchFinalizePreview: ném lỗi nếu không truyền sessionId', async () => {
  await assert.rejects(
    async () => {
      await fetchFinalizePreview('');
    },
    {
      message: 'Cần cung cấp sessionId hợp lệ.',
    }
  );
});

test('fetchFinalizePreview: gọi đúng GET /sessions/:id/finalize/preview kèm Cache-Control no-store', async () => {
  let capturedGet = null;
  const originalGet = api.get;

  api.get = async (url, options) => {
    capturedGet = { url, options };
    return {
      data: GOLDEN_PREVIEW_FIXTURE,
    };
  };

  try {
    const res = await fetchFinalizePreview('session-123');
    assert.ok(capturedGet);
    assert.equal(capturedGet.url, '/sessions/session-123/finalize/preview');
    assert.equal(capturedGet.options.headers['Cache-Control'], 'no-store');
    assert.equal(res.session_id, '00000000-0000-0000-0000-000000000001');
    assert.equal(res.n_versions, 2);
    assert.equal(res.versions.length, 2);
    assert.equal(res.matrix.length, 3);
  } finally {
    api.get = originalGet;
  }
});

test('fetchFinalizePreview: xử lý lỗi 409 ERR_SHUFFLE_REQUIRED có gán status và errorCode', async () => {
  const originalGet = api.get;

  api.get = async () => {
    const error = new Error('Phiên đề thi chưa chạy xáo trộn');
    error.response = {
      status: 409,
      data: {
        error_code: 'ERR_SHUFFLE_REQUIRED',
        detail: 'Cần thực hiện xáo trộn đề trước khi xem bản chiếu',
      },
    };
    throw error;
  };

  try {
    await assert.rejects(
      async () => {
        await fetchFinalizePreview('session-123');
      },
      (err) => {
        assert.equal(err.status, 409);
        assert.equal(err.errorCode, 'ERR_SHUFFLE_REQUIRED');
        assert.match(err.message, /Cần thực hiện xáo trộn đề/);
        return true;
      }
    );
  } finally {
    api.get = originalGet;
  }
});

test('fetchFinalizePreview: xử lý lỗi 423 ERR_SESSION_LOCKED khi phiên đã được phê duyệt', async () => {
  const originalGet = api.get;

  api.get = async () => {
    const error = new Error('Phiên đề đã bị khóa');
    error.response = {
      status: 423,
      data: {
        error_code: 'ERR_SESSION_LOCKED',
        detail: 'Phiên làm việc đã phê duyệt và khóa nội dung',
      },
    };
    throw error;
  };

  try {
    await assert.rejects(
      async () => {
        await fetchFinalizePreview('session-123');
      },
      (err) => {
        assert.equal(err.status, 423);
        assert.equal(err.errorCode, 'ERR_SESSION_LOCKED');
        return true;
      }
    );
  } finally {
    api.get = originalGet;
  }
});

test('updateOrderingPreferences: gọi đúng PATCH /sessions/:id/ordering-preferences với strict boolean', async () => {
  let capturedPatch = null;
  const originalPatch = api.patch;

  api.patch = async (url, payload, options) => {
    capturedPatch = { url, payload, options };
    return {
      data: {
        success: true,
        session_id: 'session-123',
        status: 'reviewed',
        ordering_preferences: payload,
      },
    };
  };

  try {
    const res = await updateOrderingPreferences('session-123', {
      shuffle_questions: 1, // truthy, phải được ép sang true boolean
      shuffle_options: false,
    });

    assert.ok(capturedPatch);
    assert.equal(capturedPatch.url, '/sessions/session-123/ordering-preferences');
    assert.strictEqual(capturedPatch.payload.shuffle_questions, true);
    assert.strictEqual(capturedPatch.payload.shuffle_options, false);
    assert.equal(res.success, true);
  } finally {
    api.patch = originalPatch;
  }
});

test('updateOrderingPreferences: ném lỗi nếu không truyền sessionId', async () => {
  await assert.rejects(
    async () => {
      await updateOrderingPreferences('');
    },
    {
      message: 'Cần cung cấp sessionId hợp lệ.',
    }
  );
});

test('triggerFinalizeShuffle: gọi đúng POST /sessions/:id/finalize/shuffle với body null', async () => {
  let capturedPost = null;
  const originalPost = api.post;

  api.post = async (url, payload, options) => {
    capturedPost = { url, payload, options };
    return {
      data: {
        session_id: 'session-123',
        status: 'reviewed',
        is_finalized: true,
        versions: [{ version_code: '101' }],
      },
    };
  };

  try {
    const res = await triggerFinalizeShuffle('session-123');
    assert.ok(capturedPost);
    assert.equal(capturedPost.url, '/sessions/session-123/finalize/shuffle');
    assert.equal(capturedPost.payload, null);
    assert.equal(res.is_finalized, true);
  } finally {
    api.post = originalPost;
  }
});

test('executeFullShuffle: gọi PATCH preferences true/true trước rồi gọi POST shuffle', async () => {
  const callSequence = [];
  const originalPatch = api.patch;
  const originalPost = api.post;

  api.patch = async (url, payload) => {
    callSequence.push({ type: 'patch', url, payload });
    return { data: { success: true } };
  };

  api.post = async (url, payload) => {
    callSequence.push({ type: 'post', url, payload });
    return { data: { session_id: 'session-123', is_finalized: true } };
  };

  try {
    const res = await executeFullShuffle('session-123');
    assert.equal(callSequence.length, 2);
    assert.equal(callSequence[0].type, 'patch');
    assert.equal(callSequence[0].url, '/sessions/session-123/ordering-preferences');
    assert.deepEqual(callSequence[0].payload, {
      shuffle_questions: true,
      shuffle_options: true,
    });
    assert.equal(callSequence[1].type, 'post');
    assert.equal(callSequence[1].url, '/sessions/session-123/finalize/shuffle');
    assert.equal(res.is_finalized, true);
  } finally {
    api.patch = originalPatch;
    api.post = originalPost;
  }
});

test('triggerFinalizeApprove: gọi đúng POST /sessions/:id/finalize/approve', async () => {
  let capturedPost = null;
  const originalPost = api.post;

  api.post = async (url, payload, options) => {
    capturedPost = { url, payload, options };
    return {
      data: {
        session_id: 'session-123',
        status: 'approved',
        approved_at: '2026-11-14T20:00:00Z',
        message: 'Phiên làm việc đã được phê duyệt và khóa nội dung thành công.',
      },
    };
  };

  try {
    const res = await triggerFinalizeApprove('session-123');
    assert.ok(capturedPost);
    assert.equal(capturedPost.url, '/sessions/session-123/finalize/approve');
    assert.equal(capturedPost.payload, null);
    assert.equal(res.status, 'approved');
  } finally {
    api.post = originalPost;
  }
});

test('adaptPreviewSnapshot: sắp xếp questions theo question_no và chuẩn hóa answer_keys', () => {
  const raw = {
    session_id: 'test-session',
    status: 'reviewed',
    is_finalized: true,
    versions: [
      {
        version_code: '101',
        questions: [
          { question_no: 3, content: 'Câu 3' },
          { question_no: 1, content: 'Câu 1' },
          { question_no: 2, content: 'Câu 2' },
        ],
        answer_keys: [
          { display_no: 1, display_correct_key: 'A' },
          { display_no: 2, display_correct_key: 'C' },
          { display_no: 3, display_correct_key: 'B' },
        ],
      },
    ],
    matrix: [{ question_no: 1, answers: { '101': 'A' } }],
  };

  const adapted = adaptPreviewSnapshot(raw);
  assert.equal(adapted.session_id, 'test-session');
  assert.equal(adapted.versions[0].questions[0].question_no, 1);
  assert.equal(adapted.versions[0].questions[1].question_no, 2);
  assert.equal(adapted.versions[0].questions[2].question_no, 3);
  assert.deepEqual(adapted.versions[0].answer_keys, {
    '1': 'A',
    '2': 'C',
    '3': 'B',
  });
  assert.equal(adapted.matrix.length, 1);
});

test('adaptPreviewSnapshot: trả về null khi input rỗng', () => {
  assert.equal(adaptPreviewSnapshot(null), null);
  assert.equal(adaptPreviewSnapshot(undefined), null);
});
