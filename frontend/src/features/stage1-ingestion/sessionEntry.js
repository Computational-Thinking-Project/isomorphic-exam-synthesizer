export function validateSessionMetadata({ title, subject, grade }) {
  if (typeof title !== 'string' || !title.trim() || [...title.trim()].length > 255) {
    return 'Tên phiên phải có từ 1 đến 255 ký tự.';
  }
  if (typeof subject !== 'string' || [...subject.trim()].length > 100) {
    return 'Môn học tối đa 100 ký tự.';
  }
  if (!Number.isInteger(grade) || grade < 1 || grade > 12) {
    return 'Khối lớp phải là số nguyên từ 1 đến 12.';
  }
  return '';
}

function errorMessage(error, creating) {
  const status = error?.response?.status;
  if (status === 401) return 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.';
  if (status === 403) return 'Bạn không có quyền thực hiện thao tác này.';
  if (status === 404) return 'Không tìm thấy phiên hoặc bạn không có quyền truy cập.';
  if (status === 422) return 'Thông tin phiên không hợp lệ. Kiểm tra lại rồi thử lại.';
  if (status === 429) return 'Bạn thao tác quá nhanh. Hãy chờ một chút rồi thử lại.';
  return creating
    ? 'Chưa xác nhận được kết quả tạo phiên. Quay về Dashboard kiểm tra danh sách trước khi tạo lại.'
    : 'Không tải được chi tiết phiên. Vui lòng thử lại.';
}

// One controller per account and route ID; no session data is persisted here.
export function createSessionEntryController({ create, load, onCreated, isCurrent = () => true }) {
  let state = { phase: 'idle', detail: null, error: '', createUncertain: false };
  const listeners = new Set();
  let revision = 0;
  let request;
  const publish = (next) => {
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  };
  const cancel = () => {
    revision += 1;
    request?.abort();
  };
  const begin = () => {
    cancel();
    request = new AbortController();
    const version = revision;
    const signal = request.signal;
    return { signal, current: () => revision === version && !signal.aborted && isCurrent() };
  };
  return {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    cancel,
    async load(id) {
      const operation = begin();
      publish({ phase: 'loading', detail: null, error: '' });
      try {
        if (!id || id.toLowerCase() === 'new') throw new Error('Invalid session ID');
        const detail = await load(id, { signal: operation.signal });
        if (operation.current()) publish({ phase: 'ready', detail });
      } catch (error) {
        if (operation.current()) publish({ phase: 'error', error: errorMessage(error, false) });
      }
    },
    async submit(metadata) {
      if (state.phase === 'creating' || state.phase === 'created' || state.createUncertain || !isCurrent()) return;
      const error = validateSessionMetadata(metadata);
      if (error) { publish({ error }); return; }
      const operation = begin();
      publish({ phase: 'creating', error: '' });
      try {
        const created = await create({
          title: metadata.title.trim(), subject: metadata.subject.trim(), grade: metadata.grade,
        }, { signal: operation.signal });
        if (!operation.current()) return;
        publish({ phase: 'created' });
        onCreated(created.id);
      } catch (cause) {
        if (!operation.current()) return;
        const status = cause?.response?.status;
        const uncertain = !status || status >= 500 || status === 408;
        publish({ phase: 'error', error: errorMessage(cause, true), createUncertain: uncertain });
      }
    },
  };
}
