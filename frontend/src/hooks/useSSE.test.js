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

test('useSSE hỗ trợ percent_complete và cập nhật trạng thái câu hỏi trực tiếp trong progress (TASK-207b)', async () => {
  MockEventSource.instances = [];
  const harness = renderHookHarness(() =>
    useSSE('session-106', {
      requestTicket: async () => ({ ticket: 't106' }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
  });

  // Gửi progress theo schema BE2 TASK-207b (percent_complete + questions)
  await act(async () => {
    es.emit('progress', {
      percent_complete: 45,
      completed_count: 9,
      total_count: 20,
      message: 'Đang xử lý mã đề 2',
      questions: [
        {
          version_index: 1,
          question_no: 1,
          status: 'done',
          message: 'Hoàn thành câu 1',
        },
        {
          version_index: 1,
          question_no: 2,
          status: 'generating',
          message: 'Đang sinh câu 2',
        },
      ],
    });
  });

  assert.equal(harness.result.progress.percent, 45, 'percent_complete phải cập nhật progress.percent');
  assert.equal(harness.result.progress.completedCount, 9);
  assert.equal(harness.result.questionStatuses['1-1'].status, 'done');
  assert.equal(harness.result.questionStatuses['1-2'].status, 'generating');

  await harness.unmount();
});

test('useSSE phân biệt lỗi job (server error) với lỗi mạng: dừng kết nối và không reconnect vô tận', async () => {
  MockEventSource.instances = [];
  let errorCallbackPayload = null;

  const harness = renderHookHarness(() =>
    useSSE('session-107', {
      requestTicket: async () => ({ ticket: 't107' }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onError: (err) => {
        errorCallbackPayload = err;
      },
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
  });

  // Máy chủ phát sự kiện error nghiệp vụ (hết quota, Gemini failed)
  await act(async () => {
    es.emit('error', {
      error: 'GEMINI_QUOTA_EXCEEDED',
      message: 'Đã vượt quá hạn mức gọi AI của Google',
    });
  });

  assert.equal(harness.result.connectionState, 'failed', 'Lỗi job phải chuyển sang failed');
  assert.equal(harness.result.error, 'Đã vượt quá hạn mức gọi AI của Google');
  assert.equal(harness.result.reconnectCount, 0, 'Tuyệt đối không tăng reconnectCount với lỗi job');
  assert.equal(es.closed, true, 'EventSource phải được đóng ngay');
  assert.ok(errorCallbackPayload, 'onError callback phải được gọi');

  // Đợi để xác nhận không có timer reconnect nào được kích hoạt
  await act(async () => {
    await new Promise((r) => setTimeout(r, 1200));
  });
  assert.equal(MockEventSource.instances.length, 1, 'Không được tạo thêm EventSource để reconnect');

  await harness.unmount();
});

test('useSSE cô lập phiên làm việc: huỷ kết nối và bỏ qua ticket trả muộn của phiên cũ khi đổi sang phiên mới', async () => {
  MockEventSource.instances = [];
  let resolveTicketA;
  const ticketAPromise = new Promise((resolve) => {
    resolveTicketA = resolve;
  });

  const mockRequestTicket = async (sessionId) => {
    if (sessionId === 'session-A') {
      return ticketAPromise;
    }
    return { ticket: 'ticket-for-session-B' };
  };

  let currentSession = 'session-A';
  const harness = renderHookHarness(() =>
    useSSE(currentSession, {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  // Ticket cho session-A đang chờ giải quyết, chưa có EventSource nào được tạo
  assert.equal(MockEventSource.instances.length, 0);

  // Người dùng chuyển sang session-B
  currentSession = 'session-B';
  await harness.render();

  // session-B nhận ticket ngay lập tức và mở EventSource
  assert.equal(MockEventSource.instances.length, 1);
  assert.ok(MockEventSource.instances[0].url.includes('session-B'));

  // Bây giờ ticket của session-A mới trả về muộn
  await act(async () => {
    resolveTicketA({ ticket: 'ticket-for-session-A' });
  });

  // Ticket muộn của session-A phải bị bỏ qua, không mở thêm stream nào
  assert.equal(MockEventSource.instances.length, 1);
  assert.ok(MockEventSource.instances[0].url.includes('session-B'));

  await harness.unmount();
});

test('useSSE reset sạch sẽ trạng thái (progress, done, questionStatuses) khi đổi session', async () => {
  MockEventSource.instances = [];
  let currentSession = 'session-X';

  const harness = renderHookHarness(() =>
    useSSE(currentSession, {
      requestTicket: async (sId) => ({ ticket: `ticket-${sId}` }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const esX = MockEventSource.instances[0];
  await act(async () => {
    esX.simulateOpen();
    esX.emit('progress', { percent: 100, completed_count: 10, total_count: 10 });
    esX.emit('done', { message: 'Xong' });
  });

  assert.equal(harness.result.isDone, true);
  assert.equal(harness.result.progress.percent, 100);

  // Đổi sang session-Y
  currentSession = 'session-Y';
  await harness.render();

  // State của session-Y phải hoàn toàn sạch sẽ, không rò rỉ 100% hay isDone từ session-X
  assert.equal(harness.result.isDone, false, 'isDone phải được reset về false');
  assert.equal(harness.result.progress.percent, 0, 'percent phải được reset về 0%');
  assert.deepEqual(harness.result.questionStatuses, {}, 'questionStatuses phải rỗng');

  await harness.unmount();
});

test('useSSE đọc trường error_message từ payload sự kiện error theo đúng schema BE2', async () => {
  MockEventSource.instances = [];
  const harness = renderHookHarness(() =>
    useSSE('session-108', {
      requestTicket: async () => ({ ticket: 't108' }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
    es.emit('error', {
      error: 'GEMINI_CALL_FAILED',
      error_message: 'Không thể kết nối đến Gemini AI Service',
    });
  });

  assert.equal(harness.result.connectionState, 'failed');
  assert.equal(harness.result.error, 'Không thể kết nối đến Gemini AI Service');
  assert.equal(es.closed, true);

  await harness.unmount();
});

test('useSSE nhận diện session_status === partial_generated từ event done, giữ nguyên phần trăm thực tế và không ép lên 100%', async () => {
  MockEventSource.instances = [];
  const harness = renderHookHarness(() =>
    useSSE('session-partial-1', {
      requestTicket: async () => ({ ticket: 't-part-1' }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
    es.emit('done', {
      session_status: 'partial_generated',
      percent: 60,
      completed_count: 3,
      total_count: 5,
      message: 'Hoàn thành một phần',
    });
  });

  assert.equal(harness.result.isDone, true);
  assert.equal(harness.result.isPartial, true);
  assert.equal(harness.result.progress.percent, 60, 'Không được ép percent thành 100% khi partial_generated');
  assert.equal(harness.result.progress.completedCount, 3);
  assert.equal(harness.result.progress.totalCount, 5);
  assert.equal(harness.result.progress.session_status, 'partial_generated');
  assert.equal(es.closed, true);

  await harness.unmount();
});

test('useSSE thông thường khi done với session_status === generated thì isPartial = false và percent = 100%', async () => {
  MockEventSource.instances = [];
  const harness = renderHookHarness(() =>
    useSSE('session-complete-1', {
      requestTicket: async () => ({ ticket: 't-comp-1' }),
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];
  await act(async () => {
    es.simulateOpen();
    es.emit('done', {
      session_status: 'generated',
      percent: 100,
      completed_count: 5,
      total_count: 5,
    });
  });

  assert.equal(harness.result.isDone, true);
  assert.equal(harness.result.isPartial, false);
  assert.equal(harness.result.progress.percent, 100);
  assert.equal(es.closed, true);

  await harness.unmount();
});

test('useSSE manualReconnect giữ nguyên last_event_id khi kết nối lại hoặc sinh bù cùng phiên (kể cả khi lịch sử vượt 50 sự kiện)', async () => {
  MockEventSource.instances = [];
  let ticketCallCount = 0;
  const harness = renderHookHarness(({ sessionId = 'session-chk-1' } = {}) =>
    useSSE(sessionId, {
      requestTicket: async () => {
        ticketCallCount += 1;
        return { ticket: `t-chk-${ticketCallCount}` };
      },
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();
  const es1 = MockEventSource.instances[0];
  assert.ok(es1, 'EventSource 1 phải được khởi tạo');
  assert.equal(es1.url.includes('last_event_id'), false, 'Kết nối ban đầu chưa có last_event_id');

  // Mô phỏng nhận 70 sự kiện liên tiếp (vượt quá dung lượng buffer 50 sự kiện của broker backend)
  await act(async () => {
    es1.simulateOpen();
    for (let i = 1; i <= 70; i++) {
      es1.emit(
        'progress',
        { percent: i, message: `Tiến độ sự kiện ${i}` },
        String(i),
      );
    }
    // Phát event done kết thúc với trạng thái partial_generated
    es1.emit('done', {
      session_status: 'partial_generated',
      percent: 70,
      completed_count: 7,
      total_count: 10,
    });
  });

  assert.equal(harness.result.isDone, true);
  assert.equal(harness.result.isPartial, true);
  assert.equal(harness.result.progress.percent, 70);

  // Kích hoạt manualReconnect (khi người dùng bấm Sinh bù hoặc Kết nối lại)
  await act(async () => {
    harness.result.manualReconnect();
  });

  // Kiểm tra: isDone phải được reset về false để đón nhận stream mới
  assert.equal(harness.result.isDone, false);
  assert.equal(harness.result.progress.session_status, 'generating');

  // Kiểm tra EventSource thứ 2: Bắt buộc phải mang theo last_event_id=70
  assert.equal(MockEventSource.instances.length, 2);
  const es2 = MockEventSource.instances[1];
  assert.ok(
    es2.url.includes('&last_event_id=70'),
    `URL của EventSource mới (${es2.url}) phải mang theo &last_event_id=70 để broker tiếp tục stream từ mốc đã đọc`,
  );

  // Chuyển sang phiên khác (session B): last_event_id phải được xóa sạch
  await harness.render({ sessionId: 'session-chk-2' });
  assert.equal(MockEventSource.instances.length, 3);
  const es3 = MockEventSource.instances[2];
  assert.equal(
    es3.url.includes('last_event_id'),
    false,
    'Chuyển sang phiên khác thì không được mang last_event_id của phiên cũ',
  );

  await harness.unmount();
});

test('F04: useSSE xóa cursor và gọi onResync trước khi mở stream mới khi nhận ERR_EVENT_HISTORY_LOST trong stream', async () => {
  MockEventSource.instances = [];
  let resyncCalled = 0;

  const mockRequestTicket = async (sessionId, lastEventId) => ({
    ticket: `ticket-${lastEventId || 'clean'}`,
  });

  const mockOnResync = async () => {
    resyncCalled += 1;
    return {
      progress: { percent: 80, completedCount: 8, totalCount: 10 },
      question_statuses: { '1-1': { status: 'done' } },
    };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-f04-stream', {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const es1 = MockEventSource.instances[0];

  // Phát một số event có event_id
  await act(async () => {
    es1.simulateOpen();
    es1.emit('progress', { percent: 50 }, 'evt-50');
  });

  // Backend phát tín hiệu mất lịch sử sự kiện ERR_EVENT_HISTORY_LOST
  await act(async () => {
    es1.emit('error', { error_code: 'ERR_EVENT_HISTORY_LOST' });
  });

  // Chờ timer reconnect 600ms
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 700));
  });

  assert.equal(resyncCalled, 1, 'onResync phải được gọi trước khi mở stream mới');
  assert.equal(harness.result.progress.percent, 80, 'Progress phải được cập nhật từ snapshot resync');

  // Stream thứ 2 mở ra phải có URL sạch không mang cursor hết hạn
  assert.equal(MockEventSource.instances.length, 2);
  const es2 = MockEventSource.instances[1];
  assert.equal(es2.url.includes('last_event_id'), false, 'Stream mới không được mang cursor hết hạn');

  await harness.unmount();
});

test('F04: useSSE xóa cursor và gọi onResync khi xin ticket gặp lỗi HTTP 409', async () => {
  MockEventSource.instances = [];
  let resyncCalled = 0;

  const mockRequestTicket = async (sessionId, lastEventId) => {
    if (lastEventId === 'evt-outdated') {
      const err = new Error('Conflict cursor outdated');
      err.status = 409;
      throw err;
    }
    return { ticket: 'ticket-after-409' };
  };

  const mockOnResync = async () => {
    resyncCalled += 1;
    return {
      progress: { percent: 90, completedCount: 9, totalCount: 10 },
    };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-f04-ticket-409', {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const es1 = MockEventSource.instances[0];

  await act(async () => {
    es1.simulateOpen();
    es1.emit('progress', { percent: 40 }, 'evt-outdated');
  });

  // Giả lập EventSource rớt mạng dẫn đến thử xin ticket lại
  await act(async () => {
    es1.simulateError(new Error('Network drop'));
  });

  // Chờ reconnect timer (1000ms delay cho lần 1)
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
  });

  assert.equal(resyncCalled, 1, 'Khi gặp 409 khi lấy ticket, onResync phải được gọi để reload snapshot');
  assert.equal(harness.result.progress.percent, 90, 'Snapshot mới được cập nhật vào state');

  await harness.unmount();
});

test('F04 Ca còn lỗi 2: EventSource báo lỗi chung trước onopen và ticket API vẫn hợp lệ thì FE thử nối lại từ mốc cũ, KHÔNG tải lại snapshot', async () => {
  MockEventSource.instances = [];
  let resyncCalled = 0;
  const ticketRequests = [];

  const mockRequestTicket = async (sessionId, lastEventId, epoch) => {
    ticketRequests.push({ sessionId, lastEventId, epoch });
    return {
      ticket: `ticket-${lastEventId || 'clean'}-${epoch || 'noepoch'}`,
    };
  };

  const mockOnResync = async () => {
    resyncCalled += 1;
    return {
      resume_after_event_id: 72,
      stream_epoch: 'epoch-v2',
      progress: { percent: 75, completedCount: 3, totalCount: 4, hasData: true },
    };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-f04-ticket-valid', {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const es1 = MockEventSource.instances[0];

  // Phát sinh event ghi nhận cursor 'cursor-10'
  await act(async () => {
    es1.simulateOpen();
    es1.emit('progress', { percent: 50 }, 'cursor-10');
  });

  // Mô phỏng rớt mạng
  await act(async () => {
    es1.simulateError(new Error('Network drop'));
  });

  // EventSource thứ hai được tạo để reconnect
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
  });

  const es2 = MockEventSource.instances[1];
  assert.ok(es2, 'Phải tạo kết nối EventSource thứ hai để thử lại');

  // Mô phỏng es2 bị lỗi chung trước khi onopen (nhưng ticket API vẫn hợp lệ)
  await act(async () => {
    es2.simulateError(new Error('Connection failed before open'));
  });

  // Chờ reconnect timer tiếp theo chạy
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 2200));
  });

  // TIÊU CHÍ ĐẠT: FE không được nhảy thẳng vào tải snapshot khi ticket API vẫn hợp lệ!
  assert.equal(resyncCalled, 0, 'Tuyệt đối KHÔNG được gọi onResync khi ticket API vẫn hợp lệ');

  // FE phải thử kết nối lại mang theo cursor cũ 'cursor-10'
  const latestEs = MockEventSource.instances[MockEventSource.instances.length - 1];
  assert.ok(
    latestEs.url.includes('last_event_id=cursor-10'),
    'Phải thử kết nối lại mang theo cursor cũ cursor-10',
  );

  await harness.unmount();
});

test('F04 Ca còn lỗi 2: Khi backend báo mất lịch sử (HTTP 409 / ERR_EVENT_HISTORY_LOST) trong ticket request, tải snapshot 1 lần và dùng mốc mới cho cả ticket và stream', async () => {
  MockEventSource.instances = [];
  let resyncCalled = 0;
  const ticketRequests = [];

  const mockRequestTicket = async (sessionId, lastEventId, epoch) => {
    ticketRequests.push({ sessionId, lastEventId, epoch });
    // Nếu gửi cursor-old đã bị trôi / mất lịch sử: backend trả HTTP 409 ERR_EVENT_HISTORY_LOST
    if (lastEventId === 'cursor-old') {
      const err = new Error('Event history lost');
      err.status = 409;
      err.code = 'ERR_EVENT_HISTORY_LOST';
      throw err;
    }
    return {
      ticket: `ticket-${lastEventId || 'clean'}-${epoch || 'noepoch'}`,
    };
  };

  const mockOnResync = async () => {
    resyncCalled += 1;
    return {
      resume_after_event_id: 72,
      stream_epoch: 'epoch-v2',
      progress: { percent: 75, completedCount: 3, totalCount: 4, hasData: true },
    };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-f04-ticket-409', {
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const es1 = MockEventSource.instances[0];

  await act(async () => {
    es1.simulateOpen();
    es1.emit('progress', { percent: 50 }, 'cursor-old');
  });

  // Giả lập rớt mạng và kích hoạt reconnect
  await act(async () => {
    es1.simulateError(new Error('Network drop'));
  });

  // Chờ timer thử lại và chạy quy trình phục hồi sau khi requestTicket bị 409
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 2000));
  });

  // TIÊU CHÍ ĐẠT:
  // 1. onResync được gọi đúng 1 lần khi backend báo mất lịch sử
  assert.equal(resyncCalled, 1, 'onResync phải được gọi đúng 1 lần khi ticket API trả 409');
  assert.equal(harness.result.progress.percent, 75, 'Progress phải đồng bộ từ snapshot mới');

  // 2. Ticket API lần tiếp theo phải dùng đúng cursor và epoch từ snapshot (72, epoch-v2)
  const lastTicketReq = ticketRequests[ticketRequests.length - 1];
  assert.equal(lastTicketReq.lastEventId, 72, 'Ticket request mới phải dùng resume_after_event_id=72 từ snapshot');
  assert.equal(lastTicketReq.epoch, 'epoch-v2', 'Ticket request mới phải dùng stream_epoch=epoch-v2 từ snapshot');

  // 3. Stream URL mới cũng phải dùng đúng cursor và epoch từ snapshot
  const latestEs = MockEventSource.instances[MockEventSource.instances.length - 1];
  assert.equal(latestEs.url.includes('cursor-old'), false, 'Không gửi lại cursor cũ đã mất');
  assert.ok(latestEs.url.includes('last_event_id=72'), 'Stream URL mới phải mang last_event_id=72');
  assert.ok(latestEs.url.includes('stream_epoch=epoch-v2'), 'Stream URL mới phải mang stream_epoch=epoch-v2');

  await harness.unmount();
});

test('F04 Ca còn lỗi 1: Khi snapshot trả resume_after_event_id=72 và stream_epoch=epoch-2, hook bảo tồn cả hai mốc cho cả ticket và stream mới, không xóa về null', async () => {
  MockEventSource.instances = [];
  const ticketRequests = [];

  const mockRequestTicket = async (sessionId, lastEventId, epoch) => {
    ticketRequests.push({ sessionId, lastEventId, epoch });
    return {
      ticket: `ticket-${lastEventId}-${epoch}`,
    };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-f04-preserve-marks', {
      initialResumeAfterEventId: 72,
      initialStreamEpoch: 'epoch-2',
      initialProgress: {
        hasData: true,
        percent: 75,
        completedCount: 3,
        totalCount: 4,
      },
      requestTicket: mockRequestTicket,
      eventSourceFactory: (url) => new MockEventSource(url),
    }),
  );

  await harness.render();

  // TIÊU CHÍ ĐẠT:
  // 1. Ticket request ban đầu phải gửi resume_after_event_id=72 và stream_epoch=epoch-2
  assert.equal(ticketRequests.length, 1);
  assert.equal(ticketRequests[0].lastEventId, 72, 'Ticket request phải nhận lastEventId=72');
  assert.equal(ticketRequests[0].epoch, 'epoch-2', 'Ticket request phải nhận stream_epoch=epoch-2');

  // 2. Stream URL phải chứa đầy đủ ticket, last_event_id=72 và stream_epoch=epoch-2
  const es = MockEventSource.instances[0];
  assert.ok(es.url.includes('last_event_id=72'), 'Stream URL phải mang last_event_id=72');
  assert.ok(es.url.includes('stream_epoch=epoch-2'), 'Stream URL phải mang stream_epoch=epoch-2');

  await harness.unmount();
});

test('F04: useSSE đảm bảo 1 sự kiện mất lịch sử có payload (ERR_EVENT_HISTORY_LOST) chỉ gọi onResync đúng 1 lần (Single-Flight)', async () => {
  MockEventSource.instances = [];
  let resyncCalled = 0;

  const mockOnResync = async () => {
    resyncCalled += 1;
    // Tạm dừng 50ms để kiểm tra single-flight lock
    await new Promise((r) => setTimeout(r, 50));
    return {
      progress: { percent: 80, completedCount: 4, totalCount: 5, hasData: true },
    };
  };

  const harness = renderHookHarness(() =>
    useSSE('session-f04-single-flight', {
      requestTicket: async () => ({ ticket: 't-sf' }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];

  await act(async () => {
    es.simulateOpen();
    // Bắn đồng thời qua cả event listener và onerror
    es.emit('error', { error_code: 'ERR_EVENT_HISTORY_LOST' });
    es.simulateError({ data: JSON.stringify({ error_code: 'ERR_EVENT_HISTORY_LOST' }) });
  });

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 800));
  });

  assert.equal(resyncCalled, 1, 'onResync chỉ được gọi chính xác 1 lần, không bị cộng đôi');

  await harness.unmount();
});

test('F06: Snapshot trả về muộn của phiên A khi đã chuyển sang phiên B bị hủy bỏ, không ghi đè tiến độ của phiên B', async () => {
  MockEventSource.instances = [];
  let resolveSessionAResync;
  const sessionAResyncPromise = new Promise((resolve) => {
    resolveSessionAResync = resolve;
  });

  const mockOnResync = async (sid) => {
    if (sid === 'session-A') {
      return await sessionAResyncPromise;
    }
    return { progress: { percent: 30, completedCount: 3, totalCount: 10, hasData: true } };
  };

  let activeId = 'session-A';
  const harness = renderHookHarness(() =>
    useSSE(activeId, {
      requestTicket: async (sid) => ({ ticket: `ticket-${sid}` }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const esA = MockEventSource.instances[0];

  // Phiên A mở stream và nhận lỗi mất lịch sử
  await act(async () => {
    esA.simulateOpen();
    esA.emit('error', { error_code: 'ERR_EVENT_HISTORY_LOST' });
  });

  // Phiên A đang chờ onResync... Ngay lúc này người dùng chuyển sang phiên B!
  activeId = 'session-B';
  await harness.render();

  const esB = MockEventSource.instances.find((inst) => inst.url.includes('session-B'));
  assert.ok(esB, 'Phiên B phải được kết nối');

  // Phiên B nhận tiến độ 20%
  await act(async () => {
    esB.simulateOpen();
    esB.emit('progress', { percent: 20, completed_count: 2, total_count: 10 });
  });

  assert.equal(harness.result.progress.percent, 20, 'Phiên B đang ở 20%');

  // Bây giờ snapshot muộn của phiên A mới hoàn tất (trả về 90% và câu hỏi của A)
  await act(async () => {
    resolveSessionAResync({
      progress: { percent: 90, completedCount: 9, totalCount: 10, hasData: true },
      question_statuses: { '1-1': { status: 'done', variant_id: 'A-variant-1' } },
    });
    await new Promise((r) => setTimeout(r, 100));
  });

  // TIÊU CHÍ ĐẠT F06: Snapshot phiên A trả về muộn tuyệt đối KHÔNG được ghi đè vào phiên B!
  assert.equal(
    harness.result.progress.percent,
    20,
    'Tiến độ của phiên B vẫn phải là 20%, không bị 90% của phiên A ghi đè',
  );
  assert.equal(
    harness.result.questionStatuses['1-1']?.variant_id,
    undefined,
    'Dữ liệu câu hỏi của phiên A không được lọt vào phiên B',
  );

  await harness.unmount();
});

test('F06 Ca còn lỗi: Bắt đầu tải snapshot ở A, chuyển A -> B -> A, snapshot của lượt A đầu tiên trả về muộn không được ghi đè vào lượt A thứ hai', async () => {
  MockEventSource.instances = [];
  let resolveSessionAFirstResync;
  const sessionAFirstPromise = new Promise((resolve) => {
    resolveSessionAFirstResync = resolve;
  });

  let resyncCallCount = 0;
  const mockOnResync = async (sid) => {
    resyncCallCount += 1;
    if (sid === 'session-A' && resyncCallCount === 1) {
      // Lượt A đầu tiên: trả về muộn
      return await sessionAFirstPromise;
    }
    if (sid === 'session-A' && resyncCallCount > 1) {
      // Lượt A thứ hai: trả về bình thường (25%)
      return {
        progress: { percent: 25, completedCount: 1, totalCount: 4, hasData: true },
        question_statuses: { '1-1': { status: 'done', variant_id: 'A2-q1' } },
      };
    }
    return { progress: { percent: 10, completedCount: 1, totalCount: 10, hasData: true } };
  };

  let currentId = 'session-A';
  const harness = renderHookHarness(() =>
    useSSE(currentId, {
      requestTicket: async (sid) => ({ ticket: `ticket-${sid}` }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
    }),
  );

  await harness.render();
  const esA1 = MockEventSource.instances[0];

  // Lượt A đầu tiên: nhận lỗi mất lịch sử -> bắt đầu tải snapshot lượt 1
  await act(async () => {
    esA1.simulateOpen();
    esA1.emit('error', { error_code: 'ERR_EVENT_HISTORY_LOST' });
  });

  // Chuyển sang phiên B
  currentId = 'session-B';
  await harness.render();

  // Chuyển quay lại phiên A (lượt A thứ hai)
  currentId = 'session-A';
  await harness.render();

  // Giả lập lượt A thứ hai cập nhật tiến độ (ví dụ 25%)
  await act(async () => {
    const esA2 = MockEventSource.instances[MockEventSource.instances.length - 1];
    esA2.simulateOpen();
    esA2.emit('progress', { percent: 25, completed_count: 1, total_count: 4 });
  });

  assert.equal(harness.result.progress.percent, 25, 'Lượt A thứ hai đang ở 25%');

  // Bây giờ request snapshot của lượt A đầu tiên mới trả về (chứa 90%)
  await act(async () => {
    resolveSessionAFirstResync({
      progress: { percent: 90, completedCount: 9, totalCount: 10, hasData: true },
      question_statuses: { '1-1': { status: 'done', variant_id: 'A1-stale' } },
    });
    await new Promise((r) => setTimeout(r, 100));
  });

  // TIÊU CHÍ ĐẠT: Lượt A hiện tại (25%) không được bị 90% ghi đè!
  assert.equal(
    harness.result.progress.percent,
    25,
    'Tiến độ của lượt A hiện tại phải giữ nguyên 25%, không bị 90% của lượt cũ ghi đè',
  );
  assert.notEqual(
    harness.result.questionStatuses['1-1']?.variant_id,
    'A1-stale',
    'Dữ liệu câu hỏi cũ không được ghi đè',
  );

  await harness.unmount();
});

test('F07: Khi snapshot trả về status generated (100%), useSSE chuyển ngay sang completed và isDone mà không cần nối lại SSE', async () => {
  MockEventSource.instances = [];
  let onDoneCalled = false;

  const mockOnResync = async () => ({
    status: 'generated',
    session_status: 'generated',
    progress: { percent: 100, completedCount: 4, totalCount: 4, hasData: true },
  });

  const harness = renderHookHarness(() =>
    useSSE('session-f07-hook-done', {
      requestTicket: async () => ({ ticket: 't-f07' }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
      onDone: () => {
        onDoneCalled = true;
      },
    }),
  );

  await harness.render();
  const es = MockEventSource.instances[0];

  // Phát sinh lỗi mất lịch sử trong stream -> kích hoạt onResync
  await act(async () => {
    es.simulateOpen();
    es.emit('error', { error_code: 'ERR_EVENT_HISTORY_LOST' });
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 200));
  });

  // TIÊU CHÍ ĐẠT: snapshot báo generated -> hook hoàn tất ngay, không cố nối lại SSE
  assert.equal(harness.result.isDone, true, 'isDone phải là true');
  assert.equal(harness.result.connectionState, 'completed', 'connectionState phải là completed');
  assert.equal(onDoneCalled, true, 'onDone callback phải được gọi');
  assert.equal(harness.result.progress.percent, 100);

  await harness.unmount();
});

test('F09: Khi snapshot trong triggerRecovery báo 100% nhưng session_status vẫn là generating -> KHÔNG đánh dấu completed/isDone, tiếp tục thử nối lại SSE', async () => {
  MockEventSource.instances = [];
  let onDoneCalled = false;

  const mockOnResync = async () => ({
    status: 'generating',
    session_status: 'generating', // BACKEND VẪN GENERATING
    progress: { percent: 100, completedCount: 4, totalCount: 4, hasData: true },
  });

  const harness = renderHookHarness(() =>
    useSSE('session-f09-hook-recovery-generating', {
      requestTicket: async () => ({ ticket: 't-f09' }),
      eventSourceFactory: (url) => new MockEventSource(url),
      onResync: mockOnResync,
      onDone: () => {
        onDoneCalled = true;
      },
    }),
  );

  await harness.render();
  assert.equal(MockEventSource.instances.length, 1);
  const es = MockEventSource.instances[0];

  // Phát sinh lỗi mất lịch sử trong stream -> kích hoạt onResync
  await act(async () => {
    es.simulateOpen();
    es.emit('error', { error_code: 'ERR_EVENT_HISTORY_LOST' });
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 200));
  });

  // TIÊU CHÍ ĐẠT:
  // 1. isDone vẫn phải là false (vì status là generating, chưa kết thúc)
  // 2. connectionState không được là 'completed', mà chuyển sang 'reconnecting'
  // 3. onDone callback tuyệt đối không được gọi
  assert.equal(harness.result.isDone, false, 'isDone vẫn phải là false khi session_status là generating');
  assert.notEqual(harness.result.connectionState, 'completed', 'connectionState không được là completed');
  assert.equal(onDoneCalled, false, 'onDone callback tuyệt đối không được gọi');
  assert.equal(harness.result.progress.percent, 100, 'Phần trăm tiến độ vẫn hiển thị 100%');

  // Đợi timer reconnect 600ms để hook kết nối lại stream SSE
  await act(async () => {
    await new Promise((r) => setTimeout(r, 700));
  });

  // Đã tạo kết nối EventSource mới để tiếp tục lắng nghe sự kiện done hoặc error
  assert.equal(MockEventSource.instances.length, 2, 'Phải mở kết nối SSE mới để tiếp tục theo dõi');

  await harness.unmount();
});
