import { isSourceUuid } from '../../services/sourceConfirmation.js';

const UNCERTAIN_MESSAGE = 'Chưa xác nhận được kết quả nạp nguồn. Đọc lại nguồn đã lưu để kiểm tra; không gửi lại khi thao tác trước chưa rõ kết quả.';
const CONFIRM_UNCERTAIN = 'Chưa rõ kết quả xác nhận. Đọc lại trạng thái phiên trước khi thử lại.';
const CONFIRM_CHANGED = 'Đề nguồn đã thay đổi. Hãy xem và xác nhận lại bản đang hiển thị.';
const CONFIRM_STORAGE = 'Chưa thể lưu thông tin xác nhận trong tab này. Hãy kiểm tra lại rồi thử lại.';
const CONFIRM_RECOVERY = 'Không khôi phục được mã xác nhận cũ. Hãy nạp lại nguồn; chỉ xác nhận sau khi bản mới đã được lưu.';
const isUnavailable = (status) => [401, 403, 404].includes(status);

function errorMessage(cause) {
  if (cause?.code === 'ERR_INGEST_INPUT') return cause.message;
  switch (cause?.response?.status) {
    case 400: return 'Đầu vào không hợp lệ. Kiểm tra nội dung rồi gửi lại.';
    case 401: return 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.';
    case 403: return 'Bạn không có quyền truy cập phiên này.';
    case 404: return 'Không tìm thấy phiên hoặc bạn không có quyền truy cập.';
    case 409: return 'Trạng thái phiên đã thay đổi. Đọc lại phiên trước khi tiếp tục.';
    case 422: return 'Chưa đọc được đầy đủ nội dung đề. Kiểm tra câu hỏi, các phương án và đáp án rồi gửi lại.';
    case 429: return 'Bạn thao tác quá nhanh. Hãy chờ một chút rồi gửi lại.';
    default: return 'Không nạp được nguồn. Kiểm tra lại phiên trước khi gửi lại.';
  }
}

// One instance per account/route. Inputs and last saved source remain separate.
export function createSourceIngestionController({ initialDetail, ingestText, ingestFile, load,
  validateText, validateFile, isCurrent = () => true, confirmSource, readArtifacts,
  retryArtifacts,
  confirmationStore, newConfirmationKey = () => globalThis.crypto.randomUUID(), onConfirmed = () => {} }) {
  const id = initialDetail.id;
  let intent = null;
  let storageBlocked = false;
  let recoveryRevision = null;
  let confirmationConflict = false;
  try { intent = confirmationStore?.read() ?? null; }
  catch { storageBlocked = true; }
  if (intent?.kind === 'replace-required') {
    recoveryRevision = intent.sourceRevision.toLowerCase();
    intent = null;
  }
  const initialCanonicalReady = initialDetail?.blueprint_summary?.is_ready === true;
  const initialCanonicalStatus = initialCanonicalReady
    ? 'ready'
    : (initialDetail?.status === 'blueprinted' ? 'pending' : null);
  let state = {
    detail: initialDetail, text: '', mode: 'text', file: null, upload: null,
    phase: 'idle', error: '', message: '', cause: null,
    uncertain: false, requiresReload: false, unavailable: false,
    confirmationError: storageBlocked ? CONFIRM_STORAGE : recoveryRevision ? CONFIRM_RECOVERY : intent ? CONFIRM_UNCERTAIN : '',
    confirmationPending: Boolean(intent), retryConfirmation: false,
    canonicalStatus: initialCanonicalStatus,
    canonicalReady: initialCanonicalReady,
    canonicalError: '',
  };
  const listeners = new Set();
  let revision = 0;
  let request;
  const publish = (next) => {
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  };
  const busy = () => state.phase !== 'idle';
  const canWrite = () => !busy() && !state.uncertain && !state.requiresReload
    && !state.unavailable && state.detail.status === 'draft' && isCurrent();
  const canSubmit = () => canWrite() && !intent && !storageBlocked;
  const sameRevision = (detail) => isSourceUuid(detail.source_revision)
    && detail.source_revision.toLowerCase() === intent?.sourceRevision.toLowerCase();
  const canConfirm = () => Boolean(confirmSource && confirmationStore && !storageBlocked && !recoveryRevision && canWrite()
    && isSourceUuid(state.detail.source_revision) && state.detail.source_questions.length
    && (!intent || (state.retryConfirmation && sameRevision(state.detail))));
  const invalidate = () => { revision++; request?.abort(); };
  const begin = () => {
    invalidate();
    request = new AbortController();
    const currentRevision = revision;
    const signal = request.signal;
    return { signal, current: () => revision === currentRevision && !signal.aborted && isCurrent() };
  };
  const assertSameSession = (actual) => {
    if (typeof actual !== 'string' || actual.toLowerCase() !== id.toLowerCase()) {
      throw new Error('Unexpected session response');
    }
  };
  async function readDetail(signal) {
    const detail = await load(id, { signal });
    assertSameSession(detail.id);
    if (!Array.isArray(detail.source_questions)) throw new Error('Unexpected detail response');
    return detail;
  }

  function clearIntent() {
    if (intent || recoveryRevision) confirmationStore.clear();
    intent = null;
  }

  function markBlueprinted(detail, canonicalStatus = 'pending', canonicalReady = false, canonicalError = '') {
    try { clearIntent(); } catch { /* a later verified GET may clear the entry */ }
    storageBlocked = false;
    recoveryRevision = null;
    confirmationConflict = false;
    publish({
      detail: { ...detail, status: 'blueprinted' },
      phase: 'idle',
      confirmationPending: false,
      retryConfirmation: false,
      requiresReload: false,
      unavailable: false,
      confirmationError: '',
      message: 'Đã xác nhận đề nguồn.',
      canonicalStatus,
      canonicalReady,
      canonicalError,
    });
  }

  function finishConfirmation(detail) {
    // The server has confirmed the source. Storage failure cannot change that outcome.
    try { clearIntent(); } catch { /* a later verified GET may clear the entry */ }
    storageBlocked = false;
    recoveryRevision = null;
    confirmationConflict = false;
    publish({ detail, phase: 'idle', confirmationPending: false, retryConfirmation: false,
      requiresReload: false, unavailable: false, confirmationError: '', message: 'Đã xác nhận đề nguồn.' });
    onConfirmed(detail);
  }

  async function reconcile(operation, conflict = false) {
    try {
      let detail = await readDetail(operation.signal);
      if (!operation.current()) return;
      let absent = false;
      if (detail.status === 'draft' && sameRevision(detail) && !conflict) {
        try {
          await readArtifacts(id, { signal: operation.signal });
        } catch (cause) {
          if (cause?.response?.status !== 404) throw cause;
          absent = true;
        }
        if (!operation.current()) return;
        if (!absent) detail = await readDetail(operation.signal);
        if (!operation.current()) return;
      }
      if (detail.status === 'blueprinted') {
        let cStatus = detail.blueprint_summary?.is_ready === true ? 'ready' : 'pending';
        let cReady = detail.blueprint_summary?.is_ready === true;
        let cError = '';
        if (readArtifacts) {
          try {
            const artifact = await readArtifacts(id, { signal: operation.signal });
            if (!operation.current()) return;
            cStatus = artifact.canonical_status;
            cReady = artifact.ready === true && artifact.canonical_status === 'ready';
          } catch {
            if (!operation.current()) return;
            if (!cReady) {
              cError = 'Không xác định được trạng thái Blueprint. Vui lòng kiểm tra lại.';
            }
          }
        }
        markBlueprinted(detail, cStatus, cReady, cError);
        return;
      }
      if (['configured', 'generating'].includes(detail.status)) {
        finishConfirmation(detail);
        return;
      }
      const newPreview = detail.status === 'draft' && isSourceUuid(detail.source_revision)
        && (conflict || !sameRevision(detail));
      if (newPreview || detail.status !== 'draft') clearIntent();
      if (newPreview || detail.status !== 'draft') confirmationConflict = false;
      const retryConfirmation = Boolean(intent && absent && sameRevision(detail));
      publish({ detail, phase: 'idle', requiresReload: confirmationConflict, unavailable: false,
        confirmationPending: Boolean(intent), retryConfirmation,
        confirmationError: newPreview ? CONFIRM_CHANGED
          : confirmationConflict || (intent && !retryConfirmation) ? CONFIRM_UNCERTAIN : '' });
    } catch (cause) {
      if (operation.current()) publish({ phase: 'idle', retryConfirmation: false,
        unavailable: state.unavailable || isUnavailable(cause?.response?.status),
        confirmationError: CONFIRM_UNCERTAIN });
    }
  }

  async function reload() {
    if (busy() || !isCurrent()) return;
    const operation = begin();
    if (intent || confirmationConflict) {
      publish({ phase: 'reconciling', message: '', retryConfirmation: false });
      await reconcile(operation, confirmationConflict);
      return;
    }
    publish({ phase: 'reloading', message: '', error: '' });
    try {
      const detail = await readDetail(operation.signal);
      if (!operation.current()) return;
      if (detail.status === 'blueprinted') {
        let cStatus = detail.blueprint_summary?.is_ready === true ? 'ready' : 'pending';
        let cReady = detail.blueprint_summary?.is_ready === true;
        let cError = '';
        if (readArtifacts) {
          try {
            const artifact = await readArtifacts(id, { signal: operation.signal });
            if (!operation.current()) return;
            cStatus = artifact.canonical_status;
            cReady = artifact.ready === true && artifact.canonical_status === 'ready';
          } catch {
            if (!operation.current()) return;
            if (!cReady) {
              cError = 'Không xác định được trạng thái Blueprint. Vui lòng kiểm tra lại.';
            }
          }
        }
        markBlueprinted(detail, cStatus, cReady, cError);
        return;
      }
      if (['configured', 'generating'].includes(detail.status)) {
        finishConfirmation(detail);
        return;
      }
      publish({ detail, phase: 'idle', requiresReload: false, unavailable: false, cause: null,
        message: 'Đã đọc lại nguồn đã lưu.', error: state.uncertain ? UNCERTAIN_MESSAGE : '' });
      // A GET is a snapshot; it cannot establish that an earlier ingest POST has stopped.
    } catch (cause) {
      if (!operation.current()) return;
      publish({ phase: 'idle', cause, requiresReload: true,
        unavailable: state.unavailable || isUnavailable(cause?.response?.status),
        error: 'Chưa đọc lại được phiên. Nguồn đang hiển thị là bản đã biết trước đó.' });
    }
  }

  async function recoverConfirmationStorage() {
    if (!storageBlocked || busy() || !isCurrent()) return;
    const operation = begin();
    publish({ phase: 'reconciling', confirmationError: '' });
    try {
      const detail = await readDetail(operation.signal);
      if (!operation.current()) return;
      if (detail.status === 'blueprinted') {
        markBlueprinted(detail, detail.blueprint_summary?.is_ready === true ? 'ready' : 'pending', detail.blueprint_summary?.is_ready === true);
        return;
      }
      if (['configured', 'generating'].includes(detail.status)) { finishConfirmation(detail); return; }
      if (detail.status !== 'draft' || !isSourceUuid(detail.source_revision)) throw new Error('Recovery unavailable');
      let restored;
      try { restored = confirmationStore.read(); }
      catch (cause) {
        if (cause?.code !== 'ERR_CONFIRM_STORAGE_CORRUPT') throw cause;
      }
      if (restored && restored.kind !== 'replace-required') {
        intent = restored;
        storageBlocked = false;
        await reconcile(operation);
        return;
      }
      // A missing/corrupt key cannot authorize a new confirmation of the same
      // revision. Explicit ingestion must first replace it under the server lock.
      const baseline = restored?.sourceRevision ?? detail.source_revision;
      confirmationStore.saveRecovery(baseline);
      storageBlocked = false;
      recoveryRevision = baseline.toLowerCase();
      publish({ detail, phase: 'idle', confirmationPending: false, retryConfirmation: false,
        confirmationError: CONFIRM_RECOVERY });
    } catch {
      if (operation.current()) publish({ phase: 'idle', confirmationError: CONFIRM_STORAGE });
    }
  }

  async function checkCanonicalStatus() {
    if (busy() || !isCurrent() || !readArtifacts) return;
    const operation = begin();
    publish({ phase: 'checking_status', canonicalError: '' });
    try {
      const artifact = await readArtifacts(id, { signal: operation.signal });
      if (!operation.current()) return;
      const isReady = artifact.ready === true && artifact.canonical_status === 'ready';
      publish({
        phase: 'idle',
        canonicalStatus: artifact.canonical_status,
        canonicalReady: isReady,
        canonicalError: '',
        ...(isReady ? {
          detail: {
            ...state.detail,
            blueprint_summary: {
              ...(state.detail.blueprint_summary || {}),
              is_ready: true,
              supported_modes: artifact.supported_modes,
              total_questions: artifact.total_questions,
            },
          },
        } : {}),
      });
    } catch {
      if (!operation.current()) return;
      publish({
        phase: 'idle',
        canonicalReady: false,
        canonicalError: 'Không xác định được trạng thái Blueprint. Vui lòng kiểm tra lại.',
      });
    }
  }

  async function retryCanonical() {
    if (busy() || !isCurrent() || !retryArtifacts) return;
    const operation = begin();
    publish({ phase: 'retrying_canonical', canonicalError: '' });
    try {
      await retryArtifacts(id, { signal: operation.signal });
      if (!operation.current()) return;
      if (readArtifacts) {
        const artifact = await readArtifacts(id, { signal: operation.signal });
        if (!operation.current()) return;
        const isReady = artifact.ready === true && artifact.canonical_status === 'ready';
        publish({
          phase: 'idle',
          canonicalStatus: artifact.canonical_status,
          canonicalReady: isReady,
          canonicalError: '',
          ...(isReady ? {
            detail: {
              ...state.detail,
              blueprint_summary: {
                ...(state.detail.blueprint_summary || {}),
                is_ready: true,
                supported_modes: artifact.supported_modes,
                total_questions: artifact.total_questions,
              },
            },
          } : {}),
        });
      } else {
        publish({ phase: 'idle', canonicalError: '' });
      }
    } catch {
      if (!operation.current()) return;
      publish({
        phase: 'idle',
        canonicalError: 'Không thể thử lại tạo Blueprint. Vui lòng kiểm tra lại.',
      });
    }
  }

  function proceedToStage2() {
    if (!state.canonicalReady || !isCurrent()) return;
    const detailWithReady = {
      ...state.detail,
      status: 'blueprinted',
      blueprint_summary: {
        ...(state.detail.blueprint_summary || {}),
        is_ready: true,
      },
    };
    onConfirmed(detailWithReady);
  }

  return {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    canSubmit,
    canConfirm,
    canRecoverStorage: () => storageBlocked && !busy() && isCurrent(),
    recoverConfirmationStorage,
    dispose() {
      invalidate();
      // React's development effect replay must be able to restart a read-only recovery.
      if (state.phase === 'reconciling') state = { ...state, phase: 'idle' };
    },
    restoreConfirmation() {
      if (intent) return reload();
      if (state.detail.status === 'blueprinted' && !state.canonicalReady) {
        return checkCanonicalStatus();
      }
    },
    checkCanonicalStatus,
    retryCanonical,
    proceedToStage2,
    reload,
    setMode(mode) {
      if (busy() || !isCurrent() || !['text', 'file'].includes(mode)) return;
      publish({ mode, ...(state.cause?.code === 'ERR_INGEST_INPUT' ? { error: '', cause: null } : {}) });
    },
    selectFiles(files) {
      if (busy() || !isCurrent()) return;
      try {
        if (files.length !== 1) {
          throw Object.assign(new Error('Vui lòng chọn đúng một tệp đề nguồn.'), { code: 'ERR_INGEST_INPUT' });
        }
        const file = validateFile(files[0]);
        publish({ file, upload: null, message: '',
          ...(state.cause?.code === 'ERR_INGEST_INPUT' ? { error: '', cause: null } : {}) });
      } catch (cause) {
        // An invalid replacement must not accidentally submit the previously selected file.
        publish({ file: null, upload: null, message: '',
          ...(!state.uncertain && !state.requiresReload && !state.unavailable
            ? { error: errorMessage(cause), cause } : {}) });
      }
    },
    clearFile() {
      if (busy() || !isCurrent()) return;
      publish({ file: null, upload: null,
        ...(state.cause?.code === 'ERR_INGEST_INPUT' ? { error: '', cause: null } : {}) });
    },
    setText(text) {
      if (busy() || !isCurrent()) return;
      publish({ text, ...(state.cause?.code === 'ERR_INGEST_INPUT' ? { error: '', cause: null } : {}) });
    },
    cancelRequest() {
      if (!['submitting', 'reloading'].includes(state.phase) || !isCurrent()) return;
      const wasWriting = state.phase === 'submitting';
      invalidate();
      publish({ phase: 'idle', upload: null, message: '',
        ...(wasWriting ? { uncertain: true, error: UNCERTAIN_MESSAGE }
          : { error: 'Đã dừng đọc lại phiên. Nguồn đang hiển thị là bản đã biết trước đó.' }) });
    },
    async submit() {
      if (!canSubmit()) return;
      const fileMode = state.mode === 'file';
      let input;
      try { input = fileMode ? validateFile(state.file) : validateText(state.text); }
      catch (cause) { publish({ error: errorMessage(cause), cause, message: '' }); return; }
      const operation = begin();
      publish({ phase: 'submitting', upload: fileMode ? { complete: false, loaded: 0, total: null } : null,
        error: '', message: '', cause: null });
      let count;
      try {
        const config = { signal: operation.signal };
        if (fileMode) config.onUploadProgress = (event) => {
          if (!operation.current() || state.phase !== 'submitting' || state.upload.complete) return;
          const loaded = Number.isFinite(event.loaded) && event.loaded >= 0 ? event.loaded : 0;
          const total = Number.isFinite(event.total) && event.total > 0 ? event.total : null;
          publish({ upload: { loaded, total, complete: total !== null && loaded >= total } });
        };
        const result = await (fileMode ? ingestFile(id, input, config) : ingestText(id, input, config));
        if (!operation.current()) return;
        assertSameSession(result.session_id);
        if (!Array.isArray(result.questions)) throw new Error('Unexpected source response');
        count = result.questions.length;
      } catch (cause) {
        if (!operation.current()) return;
        const status = cause?.response?.status;
        const uncertain = cause?.code !== 'ERR_INGEST_INPUT'
          && (cause?.outcomeUncertain === true || !status || status >= 500 || status === 408);
        publish({ phase: 'idle', upload: null, cause, uncertain,
          error: uncertain ? UNCERTAIN_MESSAGE : errorMessage(cause),
          requiresReload: status === 409,
          unavailable: isUnavailable(status) });
        return;
      }
      // Ingest's response has no revision. Keep the old preview until a complete snapshot arrives.
      publish({ phase: 'reloading', upload: null, requiresReload: true, confirmationError: '' });
      try {
        const detail = await readDetail(operation.signal);
        if (!operation.current()) return;
        if (detail.status === 'blueprinted') {
          markBlueprinted(detail, detail.blueprint_summary?.is_ready === true ? 'ready' : 'pending', detail.blueprint_summary?.is_ready === true);
          return;
        }
        if (['configured', 'generating'].includes(detail.status)) { finishConfirmation(detail); return; }
        if (recoveryRevision && isSourceUuid(detail.source_revision)
          && recoveryRevision !== detail.source_revision.toLowerCase()) {
          try { confirmationStore.clear(); recoveryRevision = null; }
          catch { storageBlocked = true; }
        }
        publish({ detail, phase: 'idle', requiresReload: false, unavailable: false,
          confirmationError: storageBlocked ? CONFIRM_STORAGE : recoveryRevision ? CONFIRM_RECOVERY : '',
          message: `Đã nạp ${count} câu nguồn.` });
      } catch (cause) {
        if (!operation.current()) return;
        publish({ phase: 'idle', unavailable: isUnavailable(cause?.response?.status),
          error: 'Đã nạp đề nhưng chưa đọc được bản mới. Hãy đọc lại nguồn đã lưu.' });
      }
    },
    async confirm() {
      if (!canConfirm()) return;
      if (!intent) {
        try {
          const next = { sourceRevision: state.detail.source_revision, idempotencyKey: newConfirmationKey() };
          if (!isSourceUuid(next.idempotencyKey)) throw new Error('Invalid confirmation key');
          confirmationStore.save(next);
          intent = next;
        } catch {
          publish({ confirmationError: CONFIRM_STORAGE });
          return;
        }
      }
      const operation = begin();
      publish({ phase: 'confirming', confirmationPending: true, retryConfirmation: false,
        confirmationError: '', error: '', cause: null, message: '' });
      try {
        const confirmResult = await confirmSource(id, { ...intent, signal: operation.signal });
        if (!operation.current()) return;
        const initialStatus = confirmResult?.canonical_status ?? 'pending';
        const isReady = initialStatus === 'ready';
        const nextDetail = {
          ...state.detail,
          status: 'blueprinted',
          ...(isReady ? {
            blueprint_summary: {
              ...(state.detail.blueprint_summary || {}),
              is_ready: true,
            },
          } : {}),
        };
        markBlueprinted(nextDetail, initialStatus, isReady, '');
      } catch (cause) {
        if (!operation.current()) return;
        const status = cause?.response?.status;
        if (status === 409) {
          confirmationConflict = true;
          publish({ phase: 'reconciling', requiresReload: true, confirmationPending: Boolean(intent) });
          await reconcile(operation, true);
          return;
        }
        if (status === 400 || status === 422 || cause?.code === 'ERR_CONFIRM_INPUT') {
          try { clearIntent(); } catch { storageBlocked = true; }
          publish({ phase: 'idle', confirmationPending: Boolean(intent),
            confirmationError: intent ? CONFIRM_STORAGE : 'Không thể xác nhận bản đề này. Hãy kiểm tra đề và thử lại.' });
          return;
        }
        publish({ phase: 'idle', unavailable: isUnavailable(status),
          confirmationError: isUnavailable(status) ? errorMessage(cause) : CONFIRM_UNCERTAIN });
      }
    },
  };
}
