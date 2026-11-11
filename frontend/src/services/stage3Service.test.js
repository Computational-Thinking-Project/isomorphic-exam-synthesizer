import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api } from './api.js';
import {
  acceptQuestion,
  rejectAndRegenerateQuestion,
  fetchReviewProgress,
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
