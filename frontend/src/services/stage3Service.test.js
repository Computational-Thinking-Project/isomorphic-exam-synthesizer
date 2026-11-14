import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api } from './api.js';
import {
  acceptQuestion,
  rejectAndRegenerateQuestion,
  fetchReviewProgress,
  fetchReviewSnapshot,
  adaptReviewSnapshot,
  normalizeOptions,
} from './stage3Service.js';

test('acceptQuestion gọi đúng POST /sessions/:id/questions/:qid/accept với Idempotency-Key', async () => {
  let capturedPost = null;
  const originalPost = api.post;

  api.post = async (url, payload, options) => {
    capturedPost = { url, payload, options };
    return {
      data: {
        question_id: 'q-var-1',
        question_status: 'approved',
      },
    };
  };

  try {
    const res = await acceptQuestion('sess-123', 'q-var-1', 'idem-key-abc');
    assert.ok(capturedPost);
    assert.equal(capturedPost.url, '/sessions/sess-123/questions/q-var-1/accept');
    assert.equal(capturedPost.options.headers['Idempotency-Key'], 'idem-key-abc');
    assert.equal(res.question_status, 'approved');
  } finally {
    api.post = originalPost;
  }
});

test('rejectAndRegenerateQuestion gọi đúng POST /sessions/:id/questions/:qid/reject và nhận biến thể mới', async () => {
  let capturedPost = null;
  const originalPost = api.post;

  api.post = async (url, payload, options) => {
    capturedPost = { url, payload, options };
    return {
      data: {
        question_id: 'q-var-new',
        regenerated_from_id: 'q-var-old',
        status: 'pending_review',
        content: 'Cho hàm số $y = 2x + 1$',
        options: ['1', '2', '3', '4'],
        correct_key: 'A',
        solution_md: 'Đạo hàm là $y\' = 2$.',
      },
    };
  };

  try {
    const res = await rejectAndRegenerateQuestion('sess-123', 'q-var-old');
    assert.ok(capturedPost);
    assert.equal(capturedPost.url, '/sessions/sess-123/questions/q-var-old/reject');
    assert.equal(capturedPost.options.timeout, 60000);
    assert.equal(res.question_id, 'q-var-new');
    assert.equal(res.status, 'pending_review');
    assert.equal(res.content, 'Cho hàm số $y = 2x + 1$');
  } finally {
    api.post = originalPost;
  }
});

test('fetchReviewProgress gọi đúng GET /sessions/:id/review/progress', async () => {
  let capturedGet = null;
  const originalGet = api.get;

  api.get = async (url) => {
    capturedGet = { url };
    return {
      data: {
        session_id: 'sess-123',
        expected_slots: 10,
        approved_slots: 4,
        ready: false,
      },
    };
  };

  try {
    const res = await fetchReviewProgress('sess-123');
    assert.ok(capturedGet);
    assert.equal(capturedGet.url, '/sessions/sess-123/review/progress');
    assert.equal(res.expected_slots, 10);
    assert.equal(res.approved_slots, 4);
    assert.equal(res.ready, false);
  } finally {
    api.get = originalGet;
  }
});

test('fetchReviewSnapshot gọi đúng GET /sessions/:id/review/snapshot với Cache-Control: no-store', async () => {
  let capturedGet = null;
  const originalGet = api.get;

  api.get = async (url, options) => {
    capturedGet = { url, options };
    return {
      data: {
        session_id: 'sess-snap-1',
        session_status: 'generated',
        sources: [],
        versions: [],
      },
    };
  };

  try {
    const res = await fetchReviewSnapshot('sess-snap-1');
    assert.ok(capturedGet);
    assert.equal(capturedGet.url, '/sessions/sess-snap-1/review/snapshot');
    assert.equal(capturedGet.options.headers['Cache-Control'], 'no-store');
    assert.equal(res.session_id, 'sess-snap-1');
  } finally {
    api.get = originalGet;
  }
});

test('fetchReviewSnapshot ném lỗi nếu không truyền sessionId', async () => {
  await assert.rejects(
    async () => fetchReviewSnapshot(''),
    /Cần cung cấp sessionId hợp lệ/
  );
});

test('normalizeOptions chuẩn hóa mảng options sang dạng { A, B, C, D }', () => {
  const arr = ['Option 1', 'Option 2', 'Option 3', 'Option 4'];
  const res = normalizeOptions(arr);
  assert.deepEqual(res, {
    A: 'Option 1',
    B: 'Option 2',
    C: 'Option 3',
    D: 'Option 4',
  });

  const obj = { A: '1', B: '2' };
  assert.deepEqual(normalizeOptions(obj), obj);
  assert.deepEqual(normalizeOptions(null), {});
});

test('adaptReviewSnapshot ánh xạ chính xác PR #54 Review Snapshot contract', () => {
  const snapshotData = {
    session_id: 'sess-snap-01',
    session_status: 'generated',
    read_only: false,
    confirmation_id: 'conf-123',
    job_snapshot_id: 'job-456',
    confirmed_source_hash: 'hash-abc',
    freshness_token: 'fresh-789',
    progress: {
      expected_slots: 2,
      current_slots: 2,
      approved_slots: 1,
      missing_slots: 0,
    },
    sources: [
      {
        source_question_id: 'sq-1',
        question_no: 1,
        content: 'Nguồn 1: Tìm đạo hàm $y = x^2$',
        options: ['2x', 'x', '2', '0'],
        correct_key: 'A',
        solution_md: 'Đạo hàm là $2x$.',
      },
    ],
    versions: [
      {
        version_index: 1,
        version_code: '101',
        version_id: 'ver-101',
        slots: [
          {
            source_question_id: 'sq-1',
            question_no: 1,
            candidate: {
              candidate_id: 'cand-101-1',
              status: 'approved',
              content: 'Biến thể: Tìm đạo hàm $y = 3x^2$',
              options: ['6x', '3x', '6', '0'],
              correct_key: 'A',
              solution_md: 'Đạo hàm là $6x$.',
              has_warning: false,
              validation_report: { is_valid: true },
              validation_source: 'version_question',
              origin: 'ai_generated',
              is_reverted: false,
              updated_at: '2026-11-14T10:00:00Z',
            },
          },
          {
            source_question_id: 'sq-2',
            question_no: 2,
            candidate: null, // missing slot!
          },
        ],
      },
    ],
  };

  const adapted = adaptReviewSnapshot(snapshotData, { title: 'Đề Toán 12 Tự Nhiên' });

  assert.equal(adapted.id, 'sess-snap-01');
  assert.equal(adapted.title, 'Đề Toán 12 Tự Nhiên');
  assert.equal(adapted.status, 'generated');
  assert.equal(adapted.source_questions.length, 1);
  assert.equal(adapted.source_questions[0].id, 'sq-1');
  assert.equal(adapted.source_questions[0].correct_key, 'A');

  assert.equal(adapted.exam_versions.length, 1);
  const v1 = adapted.exam_versions[0];
  assert.equal(v1.version_index, 1);
  assert.equal(v1.version_code, '101');
  // Slot 2 có candidate: null nên v1.questions CHỈ chứa 1 câu
  assert.equal(v1.questions.length, 1);
  const q1 = v1.questions[0];
  assert.equal(q1.id, 'cand-101-1');
  assert.equal(q1.candidate_id, 'cand-101-1');
  assert.equal(q1.status, 'approved');
  assert.equal(q1.correct_key, 'A');
  assert.equal(q1.solution_md, 'Đạo hàm là $6x$.');
  assert.equal(q1.options.A, '6x');
  assert.equal(q1.has_warning, false);
});

test('adaptReviewSnapshot giữ nguyên format cũ nếu đã có exam_versions mà không có versions', () => {
  const legacyData = {
    id: 'legacy-sess',
    exam_versions: [{ version_index: 1, questions: [] }],
    source_questions: [{ id: 'sq-1' }],
  };
  const res = adaptReviewSnapshot(legacyData);
  assert.equal(res, legacyData);
  assert.equal(adaptReviewSnapshot(null), null);
});
