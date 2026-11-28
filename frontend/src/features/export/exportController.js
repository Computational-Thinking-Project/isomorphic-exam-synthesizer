export const EXPORTABLE_STATUSES = new Set(['approved', 'exported']);
export const POLL_INTERVAL_MS = 2000;
export const MAX_POLL_DURATION_MS = 120000;
const URL_EXPIRY_BUFFER_MS = 5000;

export const DEFAULT_EXPORT_CONFIG = {
  visible_fields: ['title', 'student_name', 'student_id', 'student_class'],
  answer_sheet: 'none',
  formats: ['pdf'],
};

export function makeStorageKey(accountKey, sessionId) {
  const safeAccount = accountKey ? String(accountKey).trim() : 'anonymous';
  return `export_state:${safeAccount}:${sessionId}`;
}

function persistState(storage, accountKey, sessionId, data) {
  if (!storage || !sessionId) return;
  try {
    const key = makeStorageKey(accountKey, sessionId);
    storage.setItem(
      key,
      JSON.stringify({
        sessionId,
        accountKey: accountKey || null,
        packagingKey: data.packagingKey ?? null,
        identityKind: data.identityKind ?? null,
        effectiveConfig: data.effectiveConfig ?? null,
        selectedConfig: data.selectedConfig ?? null,
        updatedAt: Date.now(),
      })
    );
  } catch {
    // Ignore storage quota or private browsing exceptions safely
  }
}

function clearPersistedState(storage, accountKey, sessionId) {
  if (!storage || !sessionId) return;
  try {
    const key = makeStorageKey(accountKey, sessionId);
    storage.removeItem(key);
  } catch {
    // Ignore storage errors safely
  }
}

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
    if (code === 'ERR_EXPORT_PACKAGE_NOT_FOUND' || action === 'download' || action === 'status') {
      return 'Không tìm thấy gói xuất đề đã lưu hoặc gói đã hết hạn. Vui lòng bấm xuất bản lại.';
    }
    if (action === 'answer_key') {
      return 'Không tìm thấy dữ liệu đáp án cho phiên hoặc phiên bản này.';
    }
    return 'Không tìm thấy phiên hoặc bạn không có quyền truy cập.';
  }
  if (status === 409) {
    if (code === 'ERR_EXPORT_NOT_READY' || action === 'download') {
      return 'Gói đề thi chưa sẵn sàng để tải. Vui lòng kiểm tra lại trạng thái đóng gói.';
    }
    return 'Phiên chưa ở trạng thái duyệt cuối hoặc đang xung đột thao tác.';
  }
  if (code === 'ERR_EXPORT_QUESTION_LIMIT') {
    return 'Số lượng câu hỏi vượt quá giới hạn cho phép của mẫu xuất đề.';
  }
  if (code === 'ERR_EXPORT_CONFIG_INVALID') {
    return 'Cấu hình xuất bản không hợp lệ. Vui lòng kiểm tra lại các trường đã chọn.';
  }
  if (code === 'ERR_EXPORT_OMR_UNAVAILABLE') {
    return 'Mẫu phiếu trả lời trắc nghiệm (OMR) hiện đang được kiểm định và tạm thời chưa khả dụng.';
  }
  if (status === 422 || code === 'ERR_EXPORT_BUILD_FAILED') {
    return 'Không thể đóng gói đề thi (lỗi tạo tệp đầu ra). Vui lòng kiểm tra dữ liệu và thử lại.';
  }
  if (status === 423) {
    return 'Phiên đang bị khóa thao tác chỉnh sửa.';
  }
  if (status === 503 || status === 504 || !status) {
    if (action === 'export') {
      return 'Chưa xác nhận được kết quả đóng gói từ máy chủ. Vui lòng bấm "Kiểm tra trạng thái" trước khi thử lại.';
    }
    if (action === 'download') {
      return 'Tạm thời chưa cấp được liên kết tải xuống. Vui lòng thử lại sau.';
    }
    if (action === 'answer_key') {
      return 'Dịch vụ tải đáp án tạm thời gián đoạn. Vui lòng thử lại.';
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
  const sizeBytes = Number.isFinite(payload?.size_bytes)
    ? payload.size_bytes
    : (Number.isFinite(payload?.size) ? payload.size : null);
  const sha256 = typeof payload?.sha256 === 'string'
    ? payload.sha256
    : (typeof payload?.hash === 'string' ? payload.hash : null);
  return {
    filename: typeof payload?.filename === 'string' && payload.filename ? payload.filename : fallbackName,
    size_bytes: sizeBytes,
    sha256,
    size: sizeBytes,
    hash: sha256,
  };
}

/**
 * State machine cho màn hình xuất đề và tải ZIP (W4-MVP-09 / EXT-03).
 * Nhận adapter qua dependency injection để cô lập với chi tiết HTTP adapter.
 */
export function createExportController({
  loadSession,
  getStatus,
  triggerExport,
  issueDownloadUrl,
  fetchAnswerKey,
  openDownload = () => {},
  storage = (typeof window !== 'undefined' && window.sessionStorage) ? window.sessionStorage : null,
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
    accountKey: null,
    detail: null,
    artifact: null,
    downloadGrant: null,
    selectedConfig: { ...DEFAULT_EXPORT_CONFIG },
    effectiveConfig: null,
    packagingKey: null,
    identityKind: null,
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
    const statusValue = snapshot?.state ?? snapshot?.status;
    const packagingKey = snapshot?.packaging_key !== undefined ? snapshot.packaging_key : state.packagingKey;
    const identityKind = snapshot?.identity_kind !== undefined ? snapshot.identity_kind : state.identityKind;
    const effectiveConfig = snapshot?.effective_config !== undefined ? snapshot.effective_config : state.effectiveConfig;

    if (statusValue === 'ready') {
      stopPolling();
      publish({
        phase: 'ready_to_download',
        artifact: normalizeArtifact(snapshot, sessionId),
        packagingKey,
        identityKind,
        effectiveConfig,
        // A ready refresh may select a new packager version with the same filename.
        // Reauthorize the next download instead of reusing an older artifact URL.
        downloadGrant: null,
        error: '',
        errorCode: null,
        busyAction: null,
      });
      persistState(storage, state.accountKey, sessionId, {
        packagingKey,
        identityKind,
        effectiveConfig,
        selectedConfig: state.selectedConfig,
      });
      return;
    }
    if (statusValue === 'preparing' || statusValue === 'pending') {
      publish({
        phase: 'preparing',
        artifact: null,
        packagingKey,
        identityKind,
        effectiveConfig,
        error: '',
        errorCode: null,
        busyAction: null,
      });
      persistState(storage, state.accountKey, sessionId, {
        packagingKey,
        identityKind,
        effectiveConfig,
        selectedConfig: state.selectedConfig,
      });
      if (allowStartPoll) {
        startPolling(sessionId, packagingKey);
      }
      return;
    }
    if (statusValue === 'failed') {
      stopPolling();
      const code = snapshot?.error_code ?? snapshot?.code ?? null;
      publish({
        phase: 'failed',
        artifact: null,
        packagingKey,
        identityKind,
        effectiveConfig,
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
      packagingKey,
      identityKind,
      effectiveConfig,
      downloadGrant: null,
      error: '',
      errorCode: null,
      busyAction: null,
    });
  };

  const startPolling = (sessionId, key) => {
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
          const snapshot = await getStatus(sessionId, {
            packagingKey: key || state.packagingKey,
            signal: op.signal,
          });
          if (!op.current()) return;
          const pollStatus = snapshot?.state ?? snapshot?.status;
          if (pollStatus === 'preparing' || pollStatus === 'pending') {
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
          if ((key || state.packagingKey) && cause?.response?.status === 404) {
            clearPersistedState(storage, state.accountKey, sessionId);
            publish({
              phase: 'ready_to_export',
              packagingKey: null,
              identityKind: null,
              effectiveConfig: null,
              artifact: null,
              downloadGrant: null,
              error: 'Gói xuất đề không còn tồn tại trên máy chủ. Vui lòng xuất lại.',
              errorCode: 'ERR_EXPORT_PACKAGE_NOT_FOUND',
              busyAction: null,
            });
            return;
          }
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

    setConfig(patch) {
      if (!patch || typeof patch !== 'object') return;
      const updated = {
        ...state.selectedConfig,
        ...patch,
      };
      if (Array.isArray(patch.visible_fields)) {
        updated.visible_fields = [...patch.visible_fields];
      }
      if (Array.isArray(patch.formats)) {
        updated.formats = [...patch.formats];
      }
      publish({ selectedConfig: updated });
      persistState(storage, state.accountKey, state.sessionId, {
        packagingKey: state.packagingKey,
        identityKind: state.identityKind,
        effectiveConfig: state.effectiveConfig,
        selectedConfig: updated,
      });
    },

    resetConfig() {
      const reset = {
        ...DEFAULT_EXPORT_CONFIG,
        visible_fields: [...DEFAULT_EXPORT_CONFIG.visible_fields],
        formats: [...DEFAULT_EXPORT_CONFIG.formats],
      };
      publish({ selectedConfig: reset });
      persistState(storage, state.accountKey, state.sessionId, {
        packagingKey: state.packagingKey,
        identityKind: state.identityKind,
        effectiveConfig: state.effectiveConfig,
        selectedConfig: reset,
      });
    },

    async load(sessionId, { accountKey } = {}) {
      revision += 1;
      const op = beginRequest();

      let savedState = null;
      if (storage) {
        try {
          const raw = storage.getItem(makeStorageKey(accountKey, sessionId));
          if (raw) savedState = JSON.parse(raw);
        } catch {
          savedState = null;
        }
      }

      const packagingKey = savedState?.packagingKey || null;
      const identityKind = savedState?.identityKind || null;
      const effectiveConfig = savedState?.effectiveConfig || null;
      const selectedConfig = savedState?.selectedConfig
        ? { ...DEFAULT_EXPORT_CONFIG, ...savedState.selectedConfig }
        : { ...DEFAULT_EXPORT_CONFIG };

      publish({
        ...initialState,
        phase: 'loading',
        sessionId,
        accountKey: accountKey || null,
        packagingKey,
        identityKind,
        effectiveConfig,
        selectedConfig,
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
        try {
          const snapshot = await getStatus(sessionId, { packagingKey, signal: op.signal });
          if (!op.current()) return;
          applyStatusSnapshot(sessionId, snapshot);
        } catch (cause) {
          if (!op.current()) return;
          if (packagingKey && cause?.response?.status === 404) {
            clearPersistedState(storage, accountKey, sessionId);
            publish({
              phase: 'ready_to_export',
              packagingKey: null,
              identityKind: null,
              effectiveConfig: null,
              artifact: null,
              downloadGrant: null,
              error: '',
              errorCode: null,
              busyAction: null,
            });
            return;
          }
          throw cause;
        }
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

    async startExport(customConfig) {
      if (
        state.busyAction !== null
        || !state.detail
        || !EXPORTABLE_STATUSES.has(state.detail.status)
        || !hasExportAdapters()
        || state.phase === 'preparing'
        || state.phase === 'error'
      ) {
        return;
      }

      const sessionId = state.sessionId;
      const configToUse = customConfig || state.selectedConfig;
      const op = beginRequest();
      publish({ busyAction: 'export', error: '', errorCode: null });

      try {
        const result = await triggerExport(sessionId, configToUse, { signal: op.signal });
        if (!op.current()) return;
        const rawStatus = result?.state ?? result?.status;
        const normalizedStatus = rawStatus === 'pending' ? 'preparing' : (rawStatus || 'preparing');
        applyStatusSnapshot(sessionId, { ...result, state: normalizedStatus, status: normalizedStatus });
      } catch (cause) {
        if (!op.current()) return;
        const status = cause?.response?.status;
        if (status === 503 || status === 504 || !status) {
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
        const snapshot = await getStatus(sessionId, {
          packagingKey: state.packagingKey,
          signal: op.signal,
        });
        if (!op.current()) return;
        applyStatusSnapshot(sessionId, snapshot);
      } catch (cause) {
        if (!op.current()) return;
        if (state.packagingKey && cause?.response?.status === 404) {
          clearPersistedState(storage, state.accountKey, sessionId);
          publish({
            phase: 'ready_to_export',
            packagingKey: null,
            identityKind: null,
            effectiveConfig: null,
            artifact: null,
            downloadGrant: null,
            error: 'Gói xuất đề không còn tồn tại trên máy chủ. Vui lòng xuất lại.',
            errorCode: 'ERR_EXPORT_PACKAGE_NOT_FOUND',
            busyAction: null,
          });
          return;
        }
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
        const response = await issueDownloadUrl(sessionId, {
          packagingKey: state.packagingKey,
          signal: op.signal,
        });
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

    async downloadAnswerKey({ target = 'original', versionId, format = 'csv' } = {}) {
      if (state.busyAction !== null || !state.sessionId || typeof fetchAnswerKey !== 'function') {
        return;
      }

      const sessionId = state.sessionId;
      const op = beginRequest();
      publish({ busyAction: 'answer_key', error: '', errorCode: null });

      try {
        const data = await fetchAnswerKey(sessionId, {
          target,
          versionId,
          format,
          signal: op.signal,
        });
        if (!op.current()) return;

        const ext = format === 'json' ? 'json' : 'csv';
        const targetTag = target === 'version' && versionId ? `v_${versionId}` : target;
        const filename = `answer_key_${sessionId}_${targetTag}.${ext}`;

        let fileUrl;
        if (typeof data === 'string') {
          const mime = format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8';
          fileUrl = `data:${mime},` + encodeURIComponent(data);
        } else if (typeof data === 'object' && data !== null) {
          fileUrl = 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(data, null, 2));
        } else {
          fileUrl = String(data);
        }

        openDownload(fileUrl, filename);
        publish({ busyAction: null, error: '', errorCode: null });
        return { data, filename, url: fileUrl };
      } catch (cause) {
        if (!op.current()) return;
        publish({
          busyAction: null,
          error: formatExportError(cause, 'answer_key'),
          errorCode: extractErrorCode(cause),
        });
      }
    },
  };
}
