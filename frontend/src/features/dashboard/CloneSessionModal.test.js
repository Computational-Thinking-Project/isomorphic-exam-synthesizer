import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React from 'react';
import { renderToString } from 'react-dom/server';

// Đăng ký test-loader để Node có thể import trực tiếp CloneSessionModal.jsx
register('../../test-loader.mjs', import.meta.url);
const { default: CloneSessionModal } = await import('./CloneSessionModal.jsx');

const sampleSessionA = {
  id: 'mock-session-001',
  title: 'Đề mẫu — Tích phân',
  subject: 'Toán',
  status: 'draft',
  created_at: '2026-10-16T02:00:00Z',
};

const sampleSessionB = {
  id: 'mock-session-002',
  title: 'Đề mẫu — Xác suất',
  subject: 'Toán',
  status: 'approved',
  created_at: '2026-10-15T07:30:00Z',
};

// Helper tạo deferred promise để kiểm soát thời điểm trả kết quả chính xác
function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Helper mount component có đầy đủ hook state và cho phép re-render theo props mới (giống trang cha React thật)
function mountModal(initialProps) {
  const hooks = [];
  let hookIndex = 0;
  const effects = [];
  const cleanups = [];
  let currentProps = initialProps;

  const dispatcher = {
    useState(initialValue) {
      const idx = hookIndex++;
      if (hooks[idx] === undefined) {
        hooks[idx] = typeof initialValue === 'function' ? initialValue() : initialValue;
      }
      const setState = (newValue) => {
        hooks[idx] = typeof newValue === 'function' ? newValue(hooks[idx]) : newValue;
      };
      return [hooks[idx], setState];
    },
    useRef(initialValue) {
      const idx = hookIndex++;
      if (hooks[idx] === undefined) {
        hooks[idx] = { current: initialValue };
      }
      return hooks[idx];
    },
    useCallback(fn, deps) {
      const idx = hookIndex++;
      const prev = hooks[idx];
      if (prev && deps && deps.every((d, i) => Object.is(d, prev.deps[i]))) {
        return prev.fn;
      }
      hooks[idx] = { fn, deps };
      return fn;
    },
    useEffect(effect, deps) {
      const idx = hookIndex++;
      const prev = hooks[idx];
      const hasChanged = !prev || !deps || !deps.every((d, i) => Object.is(d, prev.deps[i]));
      if (hasChanged) {
        hooks[idx] = { effect, deps };
        effects.push({ idx, effect });
      }
    },
  };

  function extractHandlers(el) {
    let formOnSubmit = null;
    let cancelOnClick = null;
    let submitDisabled = false;
    let inputTitle = '';
    let inputOnChange = null;

    if (el && el.props && el.props.children) {
      const dialogBox = el.props.children;
      const form = Array.isArray(dialogBox.props.children)
        ? dialogBox.props.children.find((c) => c && c.type === 'form') || dialogBox.props.children[2]
        : null;

      if (form && form.props) {
        formOnSubmit = form.props.onSubmit;
        const inputDiv = form.props.children[0];
        const footer = form.props.children[1];

        if (inputDiv && inputDiv.props && inputDiv.props.children) {
          const input = inputDiv.props.children[1];
          if (input && input.props) {
            inputTitle = input.props.value;
            inputOnChange = input.props.onChange;
          }
        }

        if (footer && footer.props && footer.props.children) {
          const cancelButton = footer.props.children[0];
          const submitButton = footer.props.children[1];
          if (cancelButton && cancelButton.props) {
            cancelOnClick = cancelButton.props.onClick;
          }
          if (submitButton && submitButton.props) {
            submitDisabled = submitButton.props.disabled;
          }
        }
      }
    }

    return { formOnSubmit, cancelOnClick, submitDisabled, inputTitle, inputOnChange };
  }

  function render(newProps) {
    if (newProps !== undefined) currentProps = newProps;
    hookIndex = 0;
    const prevDispatcher = React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current;
    React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = dispatcher;
    let el;
    try {
      el = CloneSessionModal(currentProps);
    } finally {
      React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = prevDispatcher;
    }
    while (effects.length > 0) {
      const { idx, effect } = effects.shift();
      if (typeof cleanups[idx] === 'function') cleanups[idx]();
      cleanups[idx] = effect();
    }
    const handlers = extractHandlers(el);
    return { el, ...handlers };
  }

  function unmount() {
    for (const cleanup of cleanups) {
      if (typeof cleanup === 'function') cleanup();
    }
  }

  const initialRender = render();
  return {
    ...initialRender,
    render,
    unmount,
  };
}

// Helper bóc tách static HTML và element tree để kiểm tra giao diện ban đầu
function inspectModal(props) {
  let captured = {
    modalTree: null,
    formOnSubmit: null,
    cancelOnClick: null,
    submitDisabled: false,
    inputTitle: '',
    inputOnChange: null,
  };

  function TestHarness() {
    const el = CloneSessionModal(props);
    captured.modalTree = el;
    if (el && el.props && el.props.children) {
      const dialogBox = el.props.children;
      const form = dialogBox.props.children.find((c) => c && c.type === 'form')
        || dialogBox.props.children[2];

      if (form && form.props) {
        captured.formOnSubmit = form.props.onSubmit;
        const inputDiv = form.props.children[0];
        const footer = form.props.children[1];

        if (inputDiv && inputDiv.props && inputDiv.props.children) {
          const input = inputDiv.props.children[1];
          captured.inputTitle = input.props.value;
          captured.inputOnChange = input.props.onChange;
        }

        if (footer && footer.props && footer.props.children) {
          const cancelButton = footer.props.children[0];
          const submitButton = footer.props.children[1];
          captured.cancelOnClick = cancelButton.props.onClick;
          captured.submitDisabled = submitButton.props.disabled;
        }
      }
    }
    return el || React.createElement('div', null);
  }

  const html = renderToString(React.createElement(TestHarness));
  return { ...captured, html };
}

test('CloneSessionModal không render gì khi isOpen = false', () => {
  const { html, modalTree } = inspectModal({
    isOpen: false,
    session: sampleSessionA,
    onClose: () => {},
  });
  assert.equal(html, '<div></div>', 'Khi isOpen=false modal không xuất hiện');
  assert.equal(modalTree, null, 'modalTree phải trả về null');
});

test('CloneSessionModal không render gì khi session = null', () => {
  const { html, modalTree } = inspectModal({
    isOpen: true,
    session: null,
    onClose: () => {},
  });
  assert.equal(html, '<div></div>', 'Khi session=null modal không xuất hiện');
  assert.equal(modalTree, null, 'modalTree phải trả về null');
});

test('CloneSessionModal render đầy đủ dialog, aria attributes và tiêu đề gợi ý', () => {
  const { html, inputTitle } = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
  });

  assert.ok(html.includes('role="dialog"'), 'Phải có role="dialog"');
  assert.ok(html.includes('aria-modal="true"'), 'Phải có aria-modal="true"');
  assert.ok(html.includes('aria-labelledby="clone-modal-title"'), 'Phải liên kết tiêu đề modal');
  assert.ok(html.includes('Nhân bản phiên đề thi'), 'Phải có tiêu đề hộp thoại');
  assert.equal(inputTitle, '[Bản sao] Đề mẫu — Tích phân', 'Input phải gợi ý tiêu đề mặc định');
});

test('Thực hiện gửi form trên modal thật thành công gọi onSuccess và onClose', async () => {
  let receivedSession = null;
  let closeCalled = false;

  const mockClone = async (id, title) => ({
    id: 'cloned-001',
    title,
    source_session_id: id,
    status: 'draft',
  });

  const { formOnSubmit } = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCalled = true; },
    onSuccess: (newSession) => { receivedSession = newSession; },
    cloneFn: mockClone,
  });

  assert.ok(typeof formOnSubmit === 'function', 'Form phải có handler onSubmit');

  await formOnSubmit({ preventDefault: () => {} });

  assert.ok(receivedSession, 'onSuccess phải được gọi với kết quả clone');
  assert.equal(receivedSession.id, 'cloned-001');
  assert.equal(receivedSession.title, '[Bản sao] Đề mẫu — Tích phân');
  assert.equal(closeCalled, true, 'onClose phải được gọi để đóng modal sau khi thành công');
});

test('Chống gửi liên tiếp (double-submit) khi form đang trong quá trình nhân bản', async () => {
  const deferred = createDeferred();
  let cloneCallCount = 0;

  const slowClone = async () => {
    cloneCallCount += 1;
    return deferred.promise;
  };

  const { formOnSubmit } = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
    onSuccess: () => {},
    cloneFn: slowClone,
  });

  // Gửi lần 1: cloneFn được gọi, request chuyển sang trạng thái pending
  const firstPromise = formOnSubmit({ preventDefault: () => {} });
  assert.equal(cloneCallCount, 1, 'Lần submit đầu tiên phải gọi cloneFn');

  // Gửi lần 2 ngay lập tức khi lần 1 chưa hoàn tất
  const secondPromise = formOnSubmit({ preventDefault: () => {} });
  assert.equal(cloneCallCount, 1, 'Lần submit thứ hai khi đang submitting phải bị chặn (callCount vẫn là 1)');

  // Giải phóng deferred promise
  deferred.resolve({ id: 'c1', title: 'Done' });
  await Promise.all([firstPromise, secondPromise]);
});

test('Bỏ qua kết quả sau khi hộp thoại bị đóng bằng nút Hủy trong lúc đang chờ nhân bản', async () => {
  const deferred = createDeferred();
  let successCalled = false;
  let closeCallCount = 0;

  const { formOnSubmit, cancelOnClick } = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => { successCalled = true; },
    cloneFn: async () => deferred.promise,
  });

  // 1. Người dùng bấm gửi nhân bản trên modal
  const submitPromise = formOnSubmit({ preventDefault: () => {} });

  // 2. Người dùng chủ động bấm Hủy để đóng modal khi request chưa xong
  cancelOnClick();
  assert.equal(closeCallCount, 1, 'Nút Hủy phải gọi onClose lần 1');

  // 3. Kết quả mạng mới trả về sau khi modal đã đóng
  deferred.resolve({ id: 'late-clone-A', title: 'Bản sao A' });
  await submitPromise;

  assert.equal(
    successCalled,
    false,
    'onSuccess TUYỆT ĐỐI KHÔNG được gọi nếu modal đã bị đóng trước khi server phản hồi',
  );
  assert.equal(
    closeCallCount,
    1,
    'onClose KHÔNG được gọi thêm lần thứ 2 khi kết quả trả về muộn',
  );
});

test('Bỏ qua lỗi máy chủ nếu hộp thoại đã bị đóng trong lúc đang chờ nhân bản', async () => {
  const deferred = createDeferred();
  let closeCallCount = 0;

  const { formOnSubmit, cancelOnClick } = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => {},
    cloneFn: async () => deferred.promise,
  });

  const submitPromise = formOnSubmit({ preventDefault: () => {} });

  // Người dùng đóng modal trước khi lỗi xảy ra
  cancelOnClick();

  // Máy chủ trả về lỗi 500 sau khi modal đã đóng
  deferred.reject(new Error('Máy chủ 500'));
  await submitPromise;

  assert.equal(closeCallCount, 1, 'Đóng modal một lần, không kích hoạt thêm lỗi thừa');
});

test('Trang cha đặt isOpen=false (ẩn hộp thoại) khi đang chờ nhân bản: Bỏ qua kết quả thành công trả về muộn', async () => {
  const deferred = createDeferred();
  let successCalled = false;
  let closeCallCount = 0;

  const baseProps = {
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => { successCalled = true; },
    cloneFn: async () => deferred.promise,
  };

  const modalInstance = mountModal(baseProps);

  // 1. Gửi form trên modal thật
  const submitPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // 2. Trang cha chủ động đặt isOpen = false (ẩn hộp thoại nhưng component vẫn còn trong trang)
  modalInstance.render({ ...baseProps, isOpen: false });

  // 3. Máy chủ phản hồi thành công sau khi trang cha đã ẩn hộp thoại
  deferred.resolve({ id: 'late-success', title: 'Bản sao A muộn' });
  await submitPromise;

  assert.equal(
    successCalled,
    false,
    'onSuccess TUYỆT ĐỐI KHÔNG được gọi khi trang cha đã đặt isOpen=false',
  );
  assert.equal(
    closeCallCount,
    0,
    'onClose KHÔNG được gọi thừa khi trang cha đã tự quản lý ẩn hộp thoại',
  );
});

test('Trang cha đặt isOpen=false (ẩn hộp thoại) khi đang chờ nhân bản: Bỏ qua lỗi máy chủ trả về muộn', async () => {
  const deferred = createDeferred();
  let closeCallCount = 0;

  const baseProps = {
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => {},
    cloneFn: async () => deferred.promise,
  };

  const modalInstance = mountModal(baseProps);

  const submitPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // Trang cha đặt isOpen = false
  modalInstance.render({ ...baseProps, isOpen: false });

  // Máy chủ trả về lỗi 500 sau khi trang cha đã ẩn hộp thoại
  deferred.reject(new Error('Lỗi máy chủ nghiêm trọng'));
  await submitPromise;

  assert.equal(
    closeCallCount,
    0,
    'onClose không được gọi thêm khi trang cha đã chủ động ẩn hộp thoại',
  );
});

test('Lỗi nhân bản khi modal vẫn mở: giữ nguyên modal và không gọi onSuccess/onClose', async () => {
  let successCalled = false;
  let closeCalled = false;

  const failingClone = async () => {
    throw new Error('Tên phiên bị trùng lặp');
  };

  const { formOnSubmit } = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCalled = true; },
    onSuccess: () => { successCalled = true; },
    cloneFn: failingClone,
  });

  await formOnSubmit({ preventDefault: () => {} });

  assert.equal(successCalled, false, 'onSuccess không được gọi khi có lỗi');
  assert.equal(closeCalled, false, 'onClose không được gọi khi có lỗi (giữ modal mở để sửa)');
});

test('Chống race condition: Bỏ qua kết quả cũ khi chuyển từ phiên A sang phiên B', async () => {
  const deferredA = createDeferred();
  const deferredB = createDeferred();

  let lastClonedSession = null;

  // Lượt 1: Modal mở cho phiên A
  const modalA = inspectModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
    onSuccess: (res) => { lastClonedSession = res; },
    cloneFn: async () => deferredA.promise,
  });

  const promiseA = modalA.formOnSubmit({ preventDefault: () => {} });

  // Lượt 2: Chuyển sang phiên B
  modalA.cancelOnClick(); // Đóng A để chuyển sang B

  const modalB = inspectModal({
    isOpen: true,
    session: sampleSessionB,
    onClose: () => {},
    onSuccess: (res) => { lastClonedSession = res; },
    cloneFn: async () => deferredB.promise,
  });

  const promiseB = modalB.formOnSubmit({ preventDefault: () => {} });

  // Request A hoàn thành trước nhưng đã cũ
  deferredA.resolve({ id: 'cloned-A', title: 'Bản sao A' });
  await promiseA;

  assert.equal(
    lastClonedSession,
    null,
    'Kết quả của phiên cũ A phải bị hủy bỏ hoàn toàn, không đè lên phiên B',
  );

  // Request B hoàn thành sau:
  deferredB.resolve({ id: 'cloned-B', title: 'Bản sao B' });
  await promiseB;

  assert.deepEqual(
    lastClonedSession,
    { id: 'cloned-B', title: 'Bản sao B' },
    'Chỉ kết quả của phiên B được chấp nhận',
  );
});
