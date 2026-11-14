export const EXPORTABLE_STATUSES = new Set(['approved', 'exported']);
export const POLL_INTERVAL_MS = 2000;
export const MAX_POLL_DURATION_MS = 120000;
const URL_EXPIRY_BUFFER_MS = 5000;

function extractErrorCode(cause) {
  const data = cause?.response?.data;
  if (typeof data?.error_code === 'string' && data.error_code) return data.error_code;
  if (typeof data?.code === 'string' && data.code) return data.code;
  return null;
}

export function formatExportError(cause, action = 'general') {
  const status = cause?.response?.status;
  const code = extractErrorCode(cause);

  if (status === 401) {
    return 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.';
  }
  if (status === 403) {
    return 'Bạn không có quyền thực hiện thao tác xuất đề cho phiên này.';
  }
  if (status === 404) {
    return 'Không tìm thấy phiên hoặc bạn không có quyền truy cập.';
  }
  if (status === 409) {
    return action === 'download'
      ? 'Gói đề thi chưa sẵn sàng để tải. Vui lòng kiểm tra lại trạng thái đóng gói.'
      : 'Phiên chưa ở trạng thái duyệt cuối hoặc đang xung đột thao tác.';
  }
  if (status === 422 || code === 'ERR_EXPORT_BUILD_FAILED') {
    return 'Không thể đóng gói đề thi (lỗi tạo tệp đầu ra). Vui lòng kiểm tra dữ liệu và thử lại.';
  }
  if (status === 423) {
    return 'Phiên đang bị khóa thao tác chỉnh sửa.';
  }
  if (status === 503 || !status) {
    if (action === 'export') {
      return 'Chưa xác nhận được kết quả đóng gói từ máy chủ. Vui lòng bấm "Kiểm tra trạng thái" trước khi thử lại.';
    }
    if (action === 'download') {
      return 'Tạm thời chưa cấp được liên kết tải xuống. Vui lòng thử lại sau.';
    }
    return 'Dịch vụ xuất đề tạm thời gián đoạn. Vui lòng thử lại.';
  }
  return 'Không thể xử lý yêu cầu xuất đề. Vui lòng thử lại.';
}

function parseExpiryMs(grant, nowFn) {
  if (typeof grant?.expires_at === 'string') {
    const parsed = Date.parse(grant.expires_at);
    if (!Number.isNaN(parsed)) return parsed;
  }
  if (Number.isFinite(grant?.expires_in) && grant.expires_in > 0) {
    return nowFn() + grant.expires_in * 1000;
  }
  return null;
}

function normalizeArtifact(payload, sessionId) {
  const fallbackName = `exam_bundle_${sessionId}.zip`;
  return {
    filename: typeof payload?.filename === 'string' && payload.filename ? payload.filename : fallbackName,
    size: Number.isFinite(payload?.size) ? payload.size : null,
    hash: typeof payload?.hash === 'string' ? payload.hash : (typeof payload?.sha256 === 'string' ? payload.sha256 : null),
  };
}

/**
 * State machine cho màn hình xuất đề và tải ZIP (W4-MVP-09).
 * Nhận adapter qua dependency injection để cô lập với chi tiết HTTP adapter đang chờ Q10.
 */
export function createExportController({
  loadSession,
  getStatus,
  triggerExport,
  issueDownloadUrl,
  openDownload = () => {},
  isCurrent = () => true,
  now = () => Date.now(),
  scheduleTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  pollIntervalMs = POLL_INTERVAL_MS,
  maxPollDurationMs = MAX_POLL_DURATION_MS,
} = {}) {
  const initialState = {
    phase: 'idle',
    sessionId: null,
    detail: null,
    artifact: null,
    downloadGrant: null,
    error: '',
    errorCode: null,
    busyAction: null,
  };

  let state = { ...initialState };
  let revision = 0;
  let request = null;
  let pollTimer = null;
  let pollStartedAt = 0;
  const listeners = new Set();

  const publish = (patch) => {
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
  };

  const stopPolling = () => {
    if (pollTimer !== null) {
      clearTimer(pollTimer);
      pollTimer = null;
    }
  };

  const cancel = () => {
    revision += 1;
    stopPolling();
    request?.abort();
    request = null;
    state = { ...initialState };
    listeners.forEach((listener) => listener());
  };

  const beginRequest = () => {
    stopPolling();
    request?.abort();
    request = new AbortController();
    const version = revision;
    const signal = request.signal;
    return {
      signal,
      current: () => revision === version && !signal.aborted && isCurrent(),
    };
  };

  const hasExportAdapters = () => (
    typeof getStatus === 'function'
    && typeof triggerExport === 'function'
    && typeof issueDownloadUrl === 'function'
  );

  const applyStatusSnapshot = (sessionId, snapshot, { allowStartPoll = true } = {}) => {
    const statusValue = snapshot?.status;
    if (statusValue === 'ready') {
      stopPolling();
      publish({
        phase: 'ready_to_download',
        artifact: normalizeArtifact(snapshot, sessionId),
        error: '',
        errorCode: null,
        busyAction: null,
      });
      return;
    }
    if (statusValue === 'preparing' || statusValue === 'pending') {
      publish({
        phase: 'preparing',
        artifact: null,
        error: '',
        errorCode: null,
        busyAction: null,
      });
      if (allowStartPoll) {
        startPolling(sessionId);
      }
      return;
    }
    if (statusValue === 'failed') {
      stopPolling();
      const code = snapshot?.error_code ?? snapshot?.code ?? null;
      publish({
        phase: 'failed',
        artifact: null,
        downloadGrant: null,
        error: 'Quá trình đóng gói đề thi gặp lỗi. Bạn có thể bấm thử đóng gói lại.',
        errorCode: typeof code === 'string' ? code : null,
        busyAction: null,
      });
      return;
    }
    stopPolling();
    publish({
      phase: 'ready_to_export',
      artifact: null,
      downloadGrant: null,
      error: '',
      errorCode: null,
      busyAction: null,
    });
  };

  const startPolling = (sessionId) => {
    stopPolling();
    pollStartedAt = now();
    const version = revision;

    const scheduleNext = () => {
      if (revision !== version || !isCurrent()) return;
      if (now() - pollStartedAt >= maxPollDurationMs) {
        stopPolling();
        publish({
          phase: 'poll_timeout',
          busyAction: null,
          error: 'Quá trình đóng gói mất nhiều thời gian hơn dự kiến. Hãy bấm "Kiểm tra trạng thái" để cập nhật.',
        });
        return;
      }

      pollTimer = scheduleTimer(async () => {
        pollTimer = null;
        if (revision !== version || !isCurrent()) return;
        const op = beginRequest();
        try {
          const snapshot = await getStatus(sessionId, { signal: op.signal });
          if (!op.current()) return;
          if (snapshot?.status === 'preparing' || snapshot?.status === 'pending') {
            if (now() - pollStartedAt >= maxPollDurationMs) {
              publish({
                phase: 'poll_timeout',
                busyAction: null,
                error: 'Quá trình đóng gói mất nhiều thời gian hơn dự kiến. Hãy bấm "Kiểm tra trạng thái" để cập nhật.',
              });
              return;
            }
            publish({ phase: 'preparing', error: '', busyAction: null });
            scheduleNext();
          } else {
            applyStatusSnapshot(sessionId, snapshot, { allowStartPoll: false });
          }
        } catch (cause) {
          if (!op.current()) return;
          publish({
            phase: 'error',
            busyAction: null,
            error: formatExportError(cause, 'status'),
            errorCode: extractErrorCode(cause),
          });
        }
      }, pollIntervalMs);
    };

    scheduleNext();
  };

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    cancel,

    async load(sessionId) {
      revision += 1;
      const op = beginRequest();
      publish({
        ...initialState,
        phase: 'loading',
        sessionId,
        busyAction: 'load',
      });

      try {
        const detail = await loadSession(sessionId, { signal: op.signal });
        if (!op.current()) return;

        if (!EXPORTABLE_STATUSES.has(detail?.status)) {
          publish({
            phase: 'blocked',
            detail,
            busyAction: null,
            error: 'Phiên chưa ở trạng thái đã duyệt cuối. Vui lòng hoàn tất duyệt đề trước khi xuất bản.',
          });
          return;
        }

        if (!hasExportAdapters()) {
          publish({
            phase: 'unwired',
            detail,
            busyAction: null,
            error: '',
          });
          return;
        }

        publish({ detail });
        const snapshot = await getStatus(sessionId, { signal: op.signal });
        if (!op.current()) return;
        applyStatusSnapshot(sessionId, snapshot);
      } catch (cause) {
        if (!op.current()) return;
        publish({
          phase: 'error',
          busyAction: null,
          error: formatExportError(cause, 'load'),
          errorCode: extractErrorCode(cause),
        });
      }
    },

    async startExport() {
      if (
        state.busyAction !== null
        || !state.detail
        || !EXPORTABLE_STATUSES.has(state.detail.status)
        || !hasExportAdapters()
        || state.phase === 'preparing'
      ) {
        return;
      }

      const sessionId = state.sessionId;
      const op = beginRequest();
      publish({ busyAction: 'export', error: '', errorCode: null });

      try {
        const result = await triggerExport(sessionId, { signal: op.signal });
        if (!op.current()) return;
        const normalizedStatus = result?.status === 'pending' ? 'preparing' : (result?.status || 'preparing');
        applyStatusSnapshot(sessionId, { ...result, status: normalizedStatus });
      } catch (cause) {
        if (!op.current()) return;
        const status = cause?.response?.status;
        if (status === 503 || !status) {
          publish({
            phase: 'error',
            busyAction: null,
            error: formatExportError(cause, 'export'),
            errorCode: extractErrorCode(cause),
          });
          return;
        }
        publish({
          phase: 'failed',
          busyAction: null,
          error: formatExportError(cause, 'export'),
          errorCode: extractErrorCode(cause),
        });
      }
    },

    async refreshStatus() {
      if (state.busyAction !== null || !state.detail || !hasExportAdapters()) {
        return;
      }

      const sessionId = state.sessionId;
      const op = beginRequest();
      publish({ busyAction: 'refresh', error: '', errorCode: null });

      try {
        const snapshot = await getStatus(sessionId, { signal: op.signal });
        if (!op.current()) return;
        applyStatusSnapshot(sessionId, snapshot);
      } catch (cause) {
        if (!op.current()) return;
        publish({
          phase: 'error',
          busyAction: null,
          error: formatExportError(cause, 'status'),
          errorCode: extractErrorCode(cause),
        });
      }
    },

    async download() {
      if (
        state.busyAction !== null
        || state.phase !== 'ready_to_download'
        || !state.detail
        || typeof issueDownloadUrl !== 'function'
      ) {
        return;
      }

      const currentGrant = state.downloadGrant;
      const isGrantValid = (
        currentGrant?.url
        && currentGrant.expiresAtMs !== null
        && currentGrant.expiresAtMs > now() + URL_EXPIRY_BUFFER_MS
      );

      if (isGrantValid) {
        openDownload(currentGrant.url, currentGrant.filename);
        return;
      }

      const sessionId = state.sessionId;
      const op = beginRequest();
      publish({ busyAction: 'download', error: '', errorCode: null });

      try {
        const response = await issueDownloadUrl(sessionId, { signal: op.signal });
        if (!op.current()) return;
        if (typeof response?.url !== 'string' || !response.url) {
          throw new Error('Missing download URL');
        }
        const filename = typeof response?.filename === 'string' && response.filename
          ? response.filename
          : (state.artifact?.filename || `exam_bundle_${sessionId}.zip`);
        const grant = {
          url: response.url,
          expiresAtMs: parseExpiryMs(response, now),
          filename,
        };
        publish({
          downloadGrant: grant,
          busyAction: null,
          error: '',
          errorCode: null,
        });
        openDownload(grant.url, grant.filename);
      } catch (cause) {
        if (!op.current()) return;
        publish({
          busyAction: null,
          downloadGrant: null,
          error: formatExportError(cause, 'download'),
          errorCode: extractErrorCode(cause),
        });
      }
    },
  };
}
