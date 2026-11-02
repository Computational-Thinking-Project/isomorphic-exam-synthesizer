const UNCERTAIN_MESSAGE = 'Chưa xác nhận được kết quả nạp nguồn. Đọc lại nguồn đã lưu để kiểm tra; không gửi lại khi thao tác trước chưa rõ kết quả.';

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
export function createSourceIngestionController({ initialDetail, ingestText, load, validateText, isCurrent = () => true }) {
  const id = initialDetail.id;
  let state = {
    detail: initialDetail, text: '', phase: 'idle', error: '', message: '', cause: null,
    uncertain: false, requiresReload: false, unavailable: false,
  };
  const listeners = new Set();
  let revision = 0;
  let request;
  const publish = (next) => {
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  };
  const busy = () => state.phase !== 'idle';
  const canSubmit = () => !busy() && !state.uncertain && !state.requiresReload
    && !state.unavailable && state.detail.status === 'draft' && isCurrent();
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
  return {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    canSubmit,
    dispose: invalidate,
    setText(text) {
      if (busy() || !isCurrent()) return;
      publish({ text, ...(state.cause?.code === 'ERR_INGEST_INPUT' ? { error: '', cause: null } : {}) });
    },
    cancelRequest() {
      if (!busy() || !isCurrent()) return;
      const wasWriting = state.phase === 'submitting';
      invalidate();
      publish({ phase: 'idle', message: '',
        ...(wasWriting ? { uncertain: true, error: UNCERTAIN_MESSAGE }
          : { error: 'Đã dừng đọc lại phiên. Nguồn đang hiển thị là bản đã biết trước đó.' }) });
    },
    async submit() {
      if (!canSubmit()) return;
      let text;
      try { text = validateText(state.text); }
      catch (cause) { publish({ error: errorMessage(cause), cause, message: '' }); return; }
      const operation = begin();
      publish({ phase: 'submitting', error: '', message: '', cause: null });
      try {
        const result = await ingestText(id, text, { signal: operation.signal });
        if (!operation.current()) return;
        assertSameSession(result.session_id);
        if (!Array.isArray(result.questions)) throw new Error('Unexpected source response');
        publish({ detail: { ...state.detail, source_questions: result.questions }, phase: 'idle',
          message: `Đã nạp ${result.questions.length} câu nguồn.`, uncertain: false });
      } catch (cause) {
        if (!operation.current()) return;
        const status = cause?.response?.status;
        const uncertain = cause?.code !== 'ERR_INGEST_INPUT'
          && (cause?.outcomeUncertain === true || !status || status >= 500 || status === 408);
        publish({ phase: 'idle', cause, uncertain,
          error: uncertain ? UNCERTAIN_MESSAGE : errorMessage(cause),
          requiresReload: status === 409,
          unavailable: [401, 403, 404].includes(status) });
      }
    },
    async reload() {
      if (busy() || !isCurrent()) return;
      const operation = begin();
      publish({ phase: 'reloading', message: '', error: '' });
      try {
        const detail = await load(id, { signal: operation.signal });
        if (!operation.current()) return;
        assertSameSession(detail.id);
        if (!Array.isArray(detail.source_questions)) throw new Error('Unexpected detail response');
        publish({ detail, phase: 'idle', requiresReload: false, unavailable: false, cause: null,
          message: 'Đã đọc lại nguồn đã lưu.', error: state.uncertain ? UNCERTAIN_MESSAGE : '' });
        // A GET is a snapshot; it cannot establish that an earlier POST has stopped.
      } catch (cause) {
        if (!operation.current()) return;
        publish({ phase: 'idle', cause, requiresReload: true,
          unavailable: state.unavailable || [401, 403, 404].includes(cause?.response?.status),
          error: 'Chưa đọc lại được phiên. Nguồn đang hiển thị là bản đã biết trước đó.' });
      }
    },
  };
}
