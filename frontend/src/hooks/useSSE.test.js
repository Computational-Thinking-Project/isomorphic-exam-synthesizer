import { test } from 'node:test';
import assert from 'node:assert/strict';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ensureDomEnvironment } from '../test-support/domHarness.js';
import { useSSE } from './useSSE.js';

ensureDomEnvironment();

/**
 * Mock EventSource để kiểm soát việc phát event và mô phỏng lỗi mạng.
 */
class MockEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.readyState = 0; // CONNECTING
    this.closed = false;
    MockEventSource.instances.push(this);
  }

  addEventListener(type, listener) {
    (this.listeners[type] = this.listeners[type] || []).push(listener);
  }

  removeEventListener(type, listener) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
    }
  }

  emit(type, data, lastEventId = null) {
    const event = {
      type,
      data: typeof data === 'string' ? data : JSON.stringify(data),
      lastEventId,
    };
    if (this.listeners[type]) {
      for (const listener of this.listeners[type]) {
        listener(event);
      }
    }
  }

  simulateOpen() {
    this.readyState = 1; // OPEN
    this.onopen?.({ type: 'open' });
  }

  simulateError(error = new Error('Network error')) {
    this.onerror?.(error);
  }

  close() {
    this.readyState = 2; // CLOSED
    this.closed = true;
  }
}
MockEventSource.instances = [];

function renderHookHarness(renderCallback) {
  const container = document.createElement('div');
  const root = createRoot(container);
  let latestResult = null;

  function TestComponent(props) {
    latestResult = renderCallback(props);
    return null;
  }

  return {
    get result() {
      return latestResult;
    },
    async render(props = {}) {
      await act(async () => {
        root.render(React.createElement(TestComponent, props));
      });
    },
    async unmount() {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

test('useSSE thực hiện ticket handshake và khởi tạo kết nối EventSource an toàn', async () => {
  MockEventSource.instances = [];
  let requestedSessionId = null;

  const mockRequestTicket = async (sessionId) => {
    requestedSessionId = sessionId;
    return { ticket: 'ticket-test-abc' };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-101', {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();

  assert.equal(requestedSessionId, 'session-101');
  assert.equal(MockEventSource.instances.length, 1);
  const es = MockEventSource.instances[0];
  assert.ok(es.url.includes('/api/sessions/session-101/events?ticket=ticket-test-abc'));
  assert.equal(harness.result.connectionState, 'connecting');

  // Mô phỏng kết nối thành công
  await act(async () => {
    es.simulateOpen();
  });
  assert.equal(harness.result.connectionState, 'connected');
  assert.equal(harness.result.error, null);

  await harness.unmount();
  assert.equal(es.closed, true);
});

test('useSSE cập nhật tiến trình progress và trạng thái câu hỏi thời gian thực', async () => {
  MockEventSource.instances = [];
  const harness = renderHookHarness(() =>
    useSSE('session-102', {
      requestTicket: async () => ({ ticket: 't1' }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
  });

  // Phát event progress
  await act(async () => {
    es.emit('progress', {
      percent: 45,
      completed_count: 9,
      total_count: 20,
      message: 'Đang xử lý mã đề 2',
      estimated_seconds: 25,
    });
  });

  assert.equal(harness.result.progress.percent, 45);
  assert.equal(harness.result.progress.completedCount, 9);
  assert.equal(harness.result.progress.totalCount, 20);
  assert.equal(harness.result.progress.estimatedSeconds, 25);

  // Phát event question_status: 🔍 Đang phân tích -> ⏳ Đang soạn nội dung -> 🔍 Đang kiểm tra
  await act(async () => {
    es.emit('question_status', {
      version_index: 1,
      question_no: 3,
      status: 'analyzing',
      message: 'Đang phân tích cấu trúc bài toán',
    });
  });
  assert.deepEqual(harness.result.questionStatuses['1-3'], {
    version_index: 1,
    question_no: 3,
    status: 'analyzing',
    message: 'Đang phân tích cấu trúc bài toán',
  });

  await act(async () => {
    es.emit('question_status', {
      version_index: 1,
      question_no: 3,
      status: 'generating',
      message: 'Đang soạn nội dung câu hỏi mới',
    });
  });
  assert.equal(harness.result.questionStatuses['1-3'].status, 'generating');

  // Phát event question_done
  await act(async () => {
    es.emit('question_done', {
      version_index: 1,
      question_no: 3,
      variant_id: 'var-999',
    });
  });
  assert.equal(harness.result.questionStatuses['1-3'].status, 'done');
  assert.equal(harness.result.questionStatuses['1-3'].variant_id, 'var-999');

  await harness.unmount();
});

test('useSSE xử lý sự kiện done: chuyển trạng thái completed, 100% và đóng kết nối', async () => {
  MockEventSource.instances = [];
  let onDoneCalled = false;

  const harness = renderHookHarness(() =>
    useSSE('session-103', {
      requestTicket: async () => ({ ticket: 't1' }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onDone: () => {
        onDoneCalled = true;
      },
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
    es.emit('done', { total_generated: 20, duration_seconds: 32 });
  });

  assert.equal(harness.result.isDone, true);
  assert.equal(harness.result.connectionState, 'completed');
  assert.equal(harness.result.progress.percent, 100);
  assert.equal(onDoneCalled, true);
  assert.equal(es.closed, true);

  await harness.unmount();
});

test('useSSE tự động xin ticket mới và mang theo last_event_id khi tái kết nối (P1.6)', async () => {
  MockEventSource.instances = [];
  const ticketsGenerated = [];

  const mockRequestTicket = async () => {
    const t = `ticket-attempt-${ticketsGenerated.length + 1}`;
    ticketsGenerated.push(t);
    return { ticket: t };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-104', {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
      maxReconnectAttempts: 3,
    }),
  );

  await harness.render();
  assert.equal(MockEventSource.instances.length, 1);
  const es1 = MockEventSource.instances[0];
  await act(async () => {
    es1.simulateOpen();
  });

  // Gửi sự kiện kèm lastEventId = "evt-42"
  await act(async () => {
    es1.emit('progress', { percent: 30 }, 'evt-42');
  });

  // Giả lập rớt mạng (onerror)
  await act(async () => {
    es1.simulateError(new Error('Connection lost'));
  });

  assert.equal(es1.closed, true);
  assert.equal(harness.result.connectionState, 'reconnecting');

  // Chờ timer backoff tái kết nối
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1100));
  });

  assert.equal(MockEventSource.instances.length, 2);
  const es2 = MockEventSource.instances[1];
  assert.ok(es2.url.includes('ticket=ticket-attempt-2'));
  assert.ok(es2.url.includes('last_event_id=evt-42'), 'Phải mang theo last_event_id của sự kiện gần nhất');

  // Kết nối lại thành công
  await act(async () => {
    es2.simulateOpen();
  });
  assert.equal(harness.result.connectionState, 'connected');
  assert.equal(harness.result.reconnectCount, 0);

  await harness.unmount();
});

test('useSSE dọn dẹp tài nguyên khi unmount hoặc khi enabled = false', async () => {
  MockEventSource.instances = [];
  let enabled = true;

  const harness = renderHookHarness(() =>
    useSSE('session-105', {
      enabled,
      requestTicket: async () => ({ ticket: 't-test' }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  assert.equal(es.closed, false);

  // Tắt enabled
  enabled = false;
  await harness.render();
  assert.equal(es.closed, true);
  assert.equal(harness.result.connectionState, 'idle');

  await harness.unmount();
});
