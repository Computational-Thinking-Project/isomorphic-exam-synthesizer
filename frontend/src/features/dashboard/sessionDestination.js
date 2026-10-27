const pendingDestinations = new Set([
  'blueprinted', 'configured', 'generating', 'partial_generated',
  'generated', 'reviewed', 'approved', 'exported', 'failed',
]);

// Only connect destinations whose screen and contract have been handed over.
export function sessionDestination(session) {
  if (session.status === 'draft') {
    return { path: `/session/${encodeURIComponent(session.id)}/stage1`, notice: '' };
  }
  return {
    path: null,
    notice: pendingDestinations.has(session.status)
      ? 'Màn tiếp tục cho trạng thái mới nhất của phiên chưa được kết nối. Bạn có thể nhân bản để bắt đầu một phiên nháp mới.'
      : 'Trạng thái mới nhất của phiên chưa được hỗ trợ. Vui lòng tải lại danh sách hoặc quay lại sau.',
  };
}

function openError(cause) {
  const messages = {
    401: 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.',
    403: 'Bạn không có quyền mở phiên này.',
    404: 'Không tìm thấy phiên hoặc bạn không có quyền truy cập.',
    429: 'Bạn thao tác quá nhanh. Hãy chờ một chút rồi thử lại.',
  };
  return messages[cause?.response?.status]
    ?? 'Không mở được phiên. Vui lòng thử lại.';
}

export function createSessionOpener({ load, navigate, isCurrent }) {
  const idle = { phase: 'idle', sessionId: null, notice: '', error: '' };
  let state = idle;
  let revision = 0;
  let request;
  const listeners = new Set();
  const publish = (next) => {
    state = next;
    listeners.forEach((listener) => listener());
  };
  const cancel = () => {
    revision += 1;
    request?.abort();
    publish(idle);
  };
  return {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    cancel,
    async open(sessionId) {
      if (!isCurrent() || (state.phase === 'loading' && state.sessionId === sessionId)) return;
      cancel();
      const version = revision;
      const operation = new AbortController();
      request = operation;
      const current = () => version === revision && !operation.signal.aborted && isCurrent();
      publish({ ...idle, phase: 'loading', sessionId });
      try {
        const detail = await load(sessionId, { signal: operation.signal });
        if (!current()) return;
        const destination = sessionDestination(detail);
        publish({ ...idle, phase: 'ready', sessionId, notice: destination.notice });
        if (destination.path) navigate(destination.path);
      } catch (cause) {
        if (current()) publish({ ...idle, phase: 'error', sessionId, error: openError(cause) });
      }
    },
  };
}
