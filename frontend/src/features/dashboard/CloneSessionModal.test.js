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

// Helper mount component có đầy đủ hook state, window listener và cho phép re-render trên cùng instance
function mountModal(initialProps) {
  const hooks = [];
  let hookIndex = 0;
  const effects = [];
  const cleanups = [];
  let currentProps = initialProps;
  let isRendering = false;
  let latestHandlers = {};

  // Giả lập window event listeners cho môi trường kiểm thử Node
  const windowListeners = {};
  const mockWindow = {
    addEventListener(event, fn) {
      (windowListeners[event] = windowListeners[event] || []).push(fn);
    },
    removeEventListener(event, fn) {
      if (windowListeners[event]) {
        windowListeners[event] = windowListeners[event].filter((f) => f !== fn);
      }
    },
    dispatchEvent(event) {
      if (windowListeners[event.type]) {
        for (const fn of [...windowListeners[event.type]]) {
          fn(event);
        }
      }
    },
  };
  globalThis.window = mockWindow;

  const dispatcher = {
    useState(initialValue) {
      const idx = hookIndex++;
      if (hooks[idx] === undefined) {
        hooks[idx] = typeof initialValue === 'function' ? initialValue() : initialValue;
      }
      const setState = (newValue) => {
        hooks[idx] = typeof newValue === 'function' ? newValue(hooks[idx]) : newValue;
        if (!isRendering) {
          render();
        }
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
    let alertMessage = null;

    if (el && el.props && el.props.children) {
      const dialogBox = el.props.children;
      const children = Array.isArray(dialogBox.props.children)
        ? dialogBox.props.children
        : [dialogBox.props.children];

      // Tìm thông báo lỗi alert nếu có
      const alertEl = children.find((c) => c && c.props && c.props.role === 'alert');
      if (alertEl) {
        alertMessage = alertEl.props.children;
      }

      // Tìm form
      const form = children.find((c) => c && c.type === 'form');
      if (form && form.props) {
        formOnSubmit = form.props.onSubmit;
        const formChildren = Array.isArray(form.props.children)
          ? form.props.children
          : [form.props.children];

        const inputDiv = formChildren[0];
        const footer = formChildren[1];

        if (inputDiv && inputDiv.props && inputDiv.props.children) {
          const input = Array.isArray(inputDiv.props.children)
            ? inputDiv.props.children.find((c) => c && c.type === 'input')
            : inputDiv.props.children;
          if (input && input.props) {
            inputTitle = input.props.value;
            inputOnChange = input.props.onChange;
          }
        }

        if (footer && footer.props && footer.props.children) {
          const buttons = Array.isArray(footer.props.children)
            ? footer.props.children
            : [footer.props.children];
          const cancelButton = buttons.find((b) => b && b.props && b.props.type === 'button');
          const submitButton = buttons.find((b) => b && b.props && b.props.type === 'submit');

          if (cancelButton && cancelButton.props) {
            cancelOnClick = cancelButton.props.onClick;
          }
          if (submitButton && submitButton.props) {
            submitDisabled = submitButton.props.disabled;
          }
        }
      }
    }

    return { el, formOnSubmit, cancelOnClick, submitDisabled, inputTitle, inputOnChange, alertMessage };
  }

  function render(newProps) {
    if (newProps !== undefined) currentProps = newProps;
    hookIndex = 0;
    isRendering = true;
    const prevDispatcher = React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current;
    React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = dispatcher;
    let el;
    try {
      el = CloneSessionModal(currentProps);
    } finally {
      React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = prevDispatcher;
      isRendering = false;
    }
    while (effects.length > 0) {
      const { idx, effect } = effects.shift();
      if (typeof cleanups[idx] === 'function') cleanups[idx]();
      cleanups[idx] = effect();
    }
    latestHandlers = extractHandlers(el);
    return latestHandlers;
  }

  function triggerKeyDown(event) {
    mockWindow.dispatchEvent({ type: 'keydown', ...event });
    return latestHandlers;
  }

  function unmount() {
    for (const cleanup of cleanups) {
      if (typeof cleanup === 'function') cleanup();
    }
  }

  render();

  return {
    get el() { return latestHandlers.el; },
    get formOnSubmit() { return latestHandlers.formOnSubmit; },
    get cancelOnClick() { return latestHandlers.cancelOnClick; },
    get submitDisabled() { return latestHandlers.submitDisabled; },
    get inputTitle() { return latestHandlers.inputTitle; },
    get inputOnChange() { return latestHandlers.inputOnChange; },
    get alertMessage() { return latestHandlers.alertMessage; },
    render,
    triggerKeyDown,
    unmount,
  };
}

test('CloneSessionModal không render gì khi isOpen = false', () => {
  const { el } = mountModal({
    isOpen: false,
    session: sampleSessionA,
    onClose: () => {},
  });
  assert.equal(el, null, 'Khi isOpen=false modal phải trả về null');
});

test('CloneSessionModal không render gì khi session = null', () => {
  const { el } = mountModal({
    isOpen: true,
    session: null,
    onClose: () => {},
  });
  assert.equal(el, null, 'Khi session=null modal phải trả về null');
});

test('CloneSessionModal render đầy đủ dialog, aria attributes và tiêu đề gợi ý', () => {
  const html = renderToString(
    React.createElement(CloneSessionModal, {
      isOpen: true,
      session: sampleSessionA,
      onClose: () => {},
    })
  );

  assert.ok(html.includes('role="dialog"'), 'Phải có role="dialog"');
  assert.ok(html.includes('aria-modal="true"'), 'Phải có aria-modal="true"');
  assert.ok(html.includes('aria-labelledby="clone-modal-title"'), 'Phải liên kết tiêu đề modal');
  assert.ok(html.includes('Nhân bản phiên đề thi'), 'Phải có tiêu đề hộp thoại');
  assert.ok(html.includes('[Bản sao] Đề mẫu — Tích phân'), 'Input phải gợi ý tiêu đề mặc định');
});

test('Bấm phím ESC đóng modal khi rảnh, nhưng bị chặn khi đang nhân bản', async () => {
  const deferred = createDeferred();
  let closeCallCount = 0;

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => {},
    cloneFn: async () => deferred.promise,
  });

  // Khi modal mở và chưa gửi: Bấm ESC phải gọi onClose
  modalInstance.triggerKeyDown({ key: 'Escape', preventDefault: () => {} });
  assert.equal(closeCallCount, 1, 'Bấm ESC khi chưa gửi phải gọi onClose đóng modal');

  // Bắt đầu gửi:
  const submitPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // Khi đang gửi: Bấm ESC phải bị chặn hoàn toàn
  modalInstance.triggerKeyDown({ key: 'Escape', preventDefault: () => {} });
  assert.equal(closeCallCount, 1, 'Bấm ESC khi đang gửi KHÔNG được gọi onClose thêm');

  deferred.resolve({ id: 'done', title: 'Done' });
  await submitPromise;
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

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCalled = true; },
    onSuccess: (newSession) => { receivedSession = newSession; },
    cloneFn: mockClone,
  });

  assert.ok(typeof modalInstance.formOnSubmit === 'function', 'Form phải có handler onSubmit');

  await modalInstance.formOnSubmit({ preventDefault: () => {} });

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

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
    onSuccess: () => {},
    cloneFn: slowClone,
  });

  // Gửi lần 1: cloneFn được gọi, request chuyển sang trạng thái pending
  const firstPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });
  assert.equal(cloneCallCount, 1, 'Lần submit đầu tiên phải gọi cloneFn');

  // Gửi lần 2 ngay lập tức khi lần 1 chưa hoàn tất
  const secondPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });
  assert.equal(cloneCallCount, 1, 'Lần submit thứ hai khi đang submitting phải bị chặn (callCount vẫn là 1)');

  // Giải phóng deferred promise
  deferred.resolve({ id: 'c1', title: 'Done' });
  await Promise.all([firstPromise, secondPromise]);
});

test('Bỏ qua kết quả sau khi hộp thoại bị đóng bằng nút Hủy trong lúc đang chờ nhân bản', async () => {
  const deferred = createDeferred();
  let successCalled = false;
  let closeCallCount = 0;

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => { successCalled = true; },
    cloneFn: async () => deferred.promise,
  });

  // 1. Người dùng bấm gửi nhân bản trên modal
  const submitPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // 2. Người dùng chủ động bấm Hủy để đóng modal khi request chưa xong
  modalInstance.cancelOnClick();
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

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => {},
    cloneFn: async () => deferred.promise,
  });

  const submitPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // Người dùng đóng modal trước khi lỗi xảy ra
  modalInstance.cancelOnClick();

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

test('Trang cha gỡ bỏ (unmount) component khi đang chờ nhân bản: Bỏ qua kết quả trả về muộn', async () => {
  const deferred = createDeferred();
  let successCalled = false;
  let closeCallCount = 0;

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => { successCalled = true; },
    cloneFn: async () => deferred.promise,
  });

  const submitPromise = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // Component bị unmount khỏi DOM
  modalInstance.unmount();

  deferred.resolve({ id: 'unmounted-clone', title: 'Bản sao' });
  await submitPromise;

  assert.equal(successCalled, false, 'onSuccess không được gọi khi component đã bị unmount');
  assert.equal(closeCallCount, 0, 'onClose không được gọi khi component đã bị unmount');
});

test('Lỗi nhân bản khi modal vẫn mở: giữ nguyên modal, hiện thông báo lỗi và cho thử lại', async () => {
  let successCalled = false;
  let closeCalled = false;

  const failingClone = async () => {
    throw new Error('Tên phiên bị trùng lặp');
  };

  const modalInstance = mountModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCalled = true; },
    onSuccess: () => { successCalled = true; },
    cloneFn: failingClone,
  });

  await modalInstance.formOnSubmit({ preventDefault: () => {} });

  assert.equal(successCalled, false, 'onSuccess không được gọi khi có lỗi');
  assert.equal(closeCalled, false, 'onClose không được gọi khi có lỗi (giữ modal mở để sửa)');
  assert.equal(modalInstance.alertMessage, 'Tên phiên bị trùng lặp', 'Phải hiển thị thông báo lỗi trên UI');
  assert.equal(modalInstance.submitDisabled, false, 'Nút nhân bản phải được mở lại để người dùng thử lại');
});

test('Cùng một modal chuyển A -> B: A trả về THÀNH CÔNG khi B đang gửi không làm mở khóa và không đóng B', async () => {
  const deferredA = createDeferred();
  const deferredB = createDeferred();

  let successResult = null;
  let closeCallCount = 0;

  const baseProps = {
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: (res) => { successResult = res; },
    cloneFn: async (id) => {
      if (id === sampleSessionA.id) return deferredA.promise;
      if (id === sampleSessionB.id) return deferredB.promise;
      throw new Error('Unknown session');
    },
  };

  // 1. Mở modal và gửi nhân bản cho phiên A
  const modalInstance = mountModal(baseProps);
  const promiseA = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // 2. Chuyển sang phiên B trên CÙNG MỘT instance component (trang cha đổi prop session)
  const updatedB = modalInstance.render({ ...baseProps, session: sampleSessionB });

  // 3. Người dùng gửi nhân bản cho phiên B
  const promiseB = updatedB.formOnSubmit({ preventDefault: () => {} });

  // 4. Request A hoàn tất thành công trong khi B vẫn đang chờ xử lý
  deferredA.resolve({ id: 'cloned-A', title: 'Bản sao A' });
  await promiseA;

  // 5. Kiểm tra: Bấm ESC không được đóng B (B vẫn đang trong quá trình nhân bản)
  modalInstance.triggerKeyDown({ key: 'Escape', preventDefault: () => {} });
  assert.equal(closeCallCount, 0, 'ESC không được phép đóng B vì B vẫn đang submitting');
  assert.equal(successResult, null, 'Kết quả thành công của A cũ phải bị bỏ qua hoàn toàn');

  // 6. Request B hoàn tất thành công sau đó
  deferredB.resolve({ id: 'cloned-B', title: 'Bản sao B' });
  await promiseB;

  assert.deepEqual(successResult, { id: 'cloned-B', title: 'Bản sao B' }, 'Chỉ nhận kết quả của phiên B');
  assert.equal(closeCallCount, 1, 'onClose được gọi đúng 1 lần sau khi B hoàn tất');
});

test('Cùng một modal chuyển A -> B: A trả về LỖI khi B đang gửi không làm mở khóa và không hiện lỗi A', async () => {
  const deferredA = createDeferred();
  const deferredB = createDeferred();

  let successResult = null;
  let closeCallCount = 0;

  const baseProps = {
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: (res) => { successResult = res; },
    cloneFn: async (id) => {
      if (id === sampleSessionA.id) return deferredA.promise;
      if (id === sampleSessionB.id) return deferredB.promise;
      throw new Error('Unknown session');
    },
  };

  // 1. Mở modal và gửi cho A
  const modalInstance = mountModal(baseProps);
  const promiseA = modalInstance.formOnSubmit({ preventDefault: () => {} });

  // 2. Chuyển sang phiên B trên cùng một instance
  const updatedB = modalInstance.render({ ...baseProps, session: sampleSessionB });

  // 3. Gửi cho B
  const promiseB = updatedB.formOnSubmit({ preventDefault: () => {} });

  // 4. Request A ném lỗi máy chủ 500 khi B đang chờ
  deferredA.reject(new Error('Máy chủ A lỗi 500'));
  await promiseA;

  // 5. Kiểm tra: Bấm ESC không được đóng B và không hiển thị thông báo lỗi của A
  modalInstance.triggerKeyDown({ key: 'Escape', preventDefault: () => {} });
  assert.equal(closeCallCount, 0, 'ESC không được đóng B dù A vừa bị lỗi');
  assert.equal(modalInstance.alertMessage, null, 'Lỗi của A không được hiển thị làm gián đoạn phiên B');

  // 6. B hoàn tất thành công
  deferredB.resolve({ id: 'cloned-B', title: 'Bản sao B' });
  await promiseB;

  assert.deepEqual(successResult, { id: 'cloned-B', title: 'Bản sao B' }, 'Phiên B thành công');
  assert.equal(closeCallCount, 1, 'onClose được gọi đúng 1 lần để đóng sau khi B xong');
});
