import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

// Đăng ký test-loader để Node import trực tiếp CloneSessionModal.jsx
register('../../test-loader.mjs', import.meta.url);
const { default: CloneSessionModal } = await import('./CloneSessionModal.jsx');

/* =========================================================================
   Môi trường ReactDOM & Browser Harness chuẩn (không phụ thuộc thư viện ngoài)
   Cung cấp cây DOM thật, ref thật, cơ chế bắt phím và phân phối sự kiện React
   ========================================================================= */

class DOMNode {
  constructor(nodeType, nodeName) {
    this.nodeType = nodeType;
    this.nodeName = nodeName;
    this.childNodes = [];
    this.parentNode = null;
    this.ownerDocument = null;
  }
  appendChild(child) {
    this.childNodes.push(child);
    child.parentNode = this;
    return child;
  }
  removeChild(child) {
    const idx = this.childNodes.indexOf(child);
    if (idx >= 0) this.childNodes.splice(idx, 1);
    child.parentNode = null;
    return child;
  }
  insertBefore(child, before) {
    const idx = this.childNodes.indexOf(before);
    if (idx >= 0) this.childNodes.splice(idx, 0, child);
    else this.childNodes.push(child);
    child.parentNode = this;
    return child;
  }
  get textContent() {
    if (this.nodeType === 3) return this._text || '';
    return this.childNodes.map((c) => c.textContent).join('');
  }
  set textContent(v) {
    if (this.nodeType === 3) {
      this._text = String(v);
    } else {
      this.childNodes = [];
      if (v) {
        const textNode = this.ownerDocument?.createTextNode(v) || new DOMNode(3, '#text');
        textNode._text = String(v);
        this.appendChild(textNode);
      }
    }
  }
}

class DOMElement extends DOMNode {
  constructor(tagName) {
    super(1, tagName.toUpperCase());
    this.tagName = tagName.toUpperCase();
    this.style = {};
    this.attributes = {};
    this.listeners = {};
    this._value = '';
  }
  get value() {
    return this._value;
  }
  set value(v) {
    this._value = String(v);
  }
  setAttribute(name, val) {
    this.attributes[name] = String(val);
    this[name] = val;
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
    delete this[name];
  }
  addEventListener(event, fn) {
    (this.listeners[event] = this.listeners[event] || []).push(fn);
  }
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  }
  dispatchEvent(event) {
    event.target = event.target || this;
    event.currentTarget = this;
    if (this.listeners[event.type]) {
      for (const fn of [...this.listeners[event.type]]) {
        fn(event);
      }
    }
    if (this.parentNode && event.bubbles !== false && !event.cancelBubble) {
      this.parentNode.dispatchEvent(event);
    }
  }
  contains(node) {
    let curr = node;
    while (curr) {
      if (curr === this) return true;
      curr = curr.parentNode;
    }
    return false;
  }
  querySelectorAll(selector) {
    const results = [];
    const isFocusableQuery = selector.includes('button') && selector.includes('input');
    function walk(el) {
      for (const child of el.childNodes) {
        if (child.nodeType === 1) {
          const tag = child.tagName.toLowerCase();
          if (isFocusableQuery) {
            if (['button', 'input', 'select', 'textarea'].includes(tag)) {
              results.push(child);
            }
          } else if (selector.startsWith('[') && selector.endsWith(']')) {
            const [attrName, attrVal] = selector.slice(1, -1).split('=');
            const cleanVal = attrVal ? attrVal.replace(/['"]/g, '') : null;
            if (cleanVal !== null) {
              if (child.getAttribute(attrName) === cleanVal) {
                results.push(child);
              }
            } else if (child.getAttribute(attrName) !== null) {
              results.push(child);
            }
          } else if (selector.startsWith('.') && child.attributes.class?.includes(selector.slice(1))) {
            results.push(child);
          } else if (child.tagName.toLowerCase() === selector.toLowerCase()) {
            results.push(child);
          }
          walk(child);
        }
      }
    }
    walk(this);
    return results;
  }
  querySelector(selector) {
    const all = this.querySelectorAll(selector);
    return all[0] || null;
  }
  focus() {
    if (this.ownerDocument) {
      this.ownerDocument.activeElement = this;
    }
  }
  select() {}
}

class DOMDocument extends DOMNode {
  constructor() {
    super(9, '#document');
    this.activeElement = null;
    this.listeners = {};
    this.defaultView = null;
  }
  createElement(tag) {
    const el = new DOMElement(tag);
    el.ownerDocument = this;
    return el;
  }
  createTextNode(text) {
    const t = new DOMNode(3, '#text');
    t._text = text;
    t.ownerDocument = this;
    return t;
  }
  createComment(text) {
    const c = new DOMNode(8, '#comment');
    c._text = text;
    c.ownerDocument = this;
    return c;
  }
  addEventListener(event, fn) {
    (this.listeners[event] = this.listeners[event] || []).push(fn);
  }
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  }
  dispatchEvent(event) {
    event.currentTarget = this;
    if (this.listeners[event.type]) {
      for (const fn of [...this.listeners[event.type]]) {
        fn(event);
      }
    }
  }
}

// Thiết lập global DOM và window cho ReactDOM trong môi trường Node
const doc = new DOMDocument();
const win = {
  document: doc,
  addEventListener(event, fn) {
    (this.listeners = this.listeners || {})[event] = (this.listeners[event] || []).concat(fn);
  },
  removeEventListener(event, fn) {
    if (this.listeners?.[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  },
  dispatchEvent(event) {
    if (this.listeners?.[event.type]) {
      for (const fn of [...this.listeners[event.type]]) {
        fn(event);
      }
    }
  },
  HTMLElement: DOMElement,
  HTMLInputElement: DOMElement,
  HTMLButtonElement: DOMElement,
  HTMLIFrameElement: DOMElement,
};
doc.defaultView = win;
globalThis.document = doc;
globalThis.window = win;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

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

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Helper gắn component thật qua ReactDOM createRoot và điều khiển vòng đời
async function renderRealModal(props) {
  const container = doc.createElement('div');
  const root = createRoot(container);

  async function update(nextProps) {
    await act(async () => {
      root.render(React.createElement(CloneSessionModal, nextProps));
    });
  }

  await update(props);

  function getElements() {
    const dialog = container.querySelector('[role="dialog"]') || container.childNodes[0] || null;
    const input = container.querySelector('input');
    const buttons = container.querySelectorAll('button');
    const cancelButton = buttons.find((b) => b.attributes.type === 'button') || null;
    const submitButton = buttons.find((b) => b.attributes.type === 'submit') || null;
    const form = container.querySelector('form');
    const alert = container.querySelector('[role="alert"]');

    return {
      dialog,
      input,
      cancelButton,
      submitButton,
      form,
      alert,
      alertMessage: alert ? alert.textContent : null,
      submitDisabled: submitButton ? Boolean(submitButton.attributes.disabled) : false,
      hasSpinner: submitButton ? Boolean(submitButton.querySelector('.animate-spin')) : false,
    };
  }

  async function submitForm() {
    const { form } = getElements();
    assert.ok(form, 'Form phải tồn tại để gửi');
    await act(async () => {
      form.dispatchEvent({
        type: 'submit',
        bubbles: true,
        preventDefault: () => {},
      });
      await new Promise((r) => setTimeout(r, 20));
    });
  }

  async function clickCancel() {
    const { cancelButton } = getElements();
    assert.ok(cancelButton, 'Nút Hủy phải tồn tại để bấm');
    await act(async () => {
      cancelButton.dispatchEvent({
        type: 'click',
        bubbles: true,
      });
      await new Promise((r) => setTimeout(r, 20));
    });
  }

  function pressKey(key, options = {}) {
    let prevented = false;
    win.dispatchEvent({
      type: 'keydown',
      key,
      ...options,
      preventDefault: () => {
        prevented = true;
      },
    });
    return { prevented };
  }

  async function unmount() {
    await act(async () => {
      root.unmount();
    });
  }

  return {
    container,
    root,
    update,
    getElements,
    submitForm,
    clickCancel,
    pressKey,
    unmount,
  };
}

/* =========================================================================
   Các ca kiểm thử React Component Thật (Focus trap, Vòng đời, Stale Response)
   ========================================================================= */

test('CloneSessionModal không render gì khi isOpen = false', async () => {
  const harness = await renderRealModal({
    isOpen: false,
    session: sampleSessionA,
    onClose: () => {},
  });
  assert.equal(harness.container.childNodes.length, 0, 'Container rỗng khi isOpen=false');
  await harness.unmount();
});

test('CloneSessionModal không render gì khi session = null', async () => {
  const harness = await renderRealModal({
    isOpen: true,
    session: null,
    onClose: () => {},
  });
  assert.equal(harness.container.childNodes.length, 0, 'Container rỗng khi session=null');
  await harness.unmount();
});

test('CloneSessionModal render đầy đủ dialog, aria attributes và tiêu đề gợi ý', async () => {
  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
  });

  const { dialog, input } = harness.getElements();
  assert.ok(dialog, 'Phải có dialog');
  assert.equal(dialog.getAttribute('role'), 'dialog');
  assert.equal(dialog.getAttribute('aria-modal'), 'true');
  assert.equal(dialog.getAttribute('aria-labelledby'), 'clone-modal-title');
  assert.equal(input.value, '[Bản sao] Đề mẫu — Tích phân');
  await harness.unmount();
});

test('Tab và Shift+Tab giữ focus trong modal qua modalBoxRef thật; đóng trả focus về nút mở', async () => {
  // 1. Nút kích hoạt mở modal nhận focus ban đầu
  const triggerBtn = doc.createElement('button');
  triggerBtn.focus();
  assert.equal(doc.activeElement, triggerBtn, 'Nút mở nhận focus trước khi mở modal');

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
  });

  // Chờ timer focus tự động vào input
  await new Promise((r) => setTimeout(r, 60));
  const { input, submitButton } = harness.getElements();
  assert.equal(doc.activeElement, input, 'Input phải được tự động focus khi mở modal');

  // 2. Focus vào nút cuối cùng (submitButton) và bấm Tab -> Vòng lặp về input đầu tiên
  submitButton.focus();
  assert.equal(doc.activeElement, submitButton);

  const tabResult = harness.pressKey('Tab', { shiftKey: false });
  assert.equal(tabResult.prevented, true, 'Tab ở phần tử cuối cùng phải bị chặn mặc định');
  assert.equal(doc.activeElement, input, 'Tab ở phần tử cuối cùng phải nhảy về phần tử đầu tiên');

  // 3. Focus vào phần tử đầu tiên (input) và bấm Shift + Tab -> Vòng lặp về nút cuối cùng
  input.focus();
  assert.equal(doc.activeElement, input);

  const shiftTabResult = harness.pressKey('Tab', { shiftKey: true });
  assert.equal(shiftTabResult.prevented, true, 'Shift+Tab ở phần tử đầu tiên phải bị chặn mặc định');
  assert.equal(doc.activeElement, submitButton, 'Shift+Tab ở phần tử đầu tiên phải nhảy về nút cuối cùng');

  // 4. Bấm ESC để đóng modal -> Focus phải được trả lại cho triggerBtn
  harness.pressKey('Escape');
  assert.equal(doc.activeElement, triggerBtn, 'Khi đóng modal, focus phải được khôi phục về triggerBtn');

  await harness.unmount();
});

test('Bấm phím ESC đóng modal khi rảnh, nhưng bị chặn khi đang nhân bản', async () => {
  const deferred = createDeferred();
  let closeCallCount = 0;

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => {},
    cloneFn: async () => deferred.promise,
  });

  // Khi chưa gửi: bấm ESC đóng modal
  harness.pressKey('Escape');
  assert.equal(closeCallCount, 1, 'ESC khi rảnh phải gọi onClose');

  // Gửi form
  await harness.submitForm();

  // Khi đang gửi: bấm ESC bị chặn hoàn toàn
  harness.pressKey('Escape');
  assert.equal(closeCallCount, 1, 'ESC khi đang gửi KHÔNG được gọi onClose');

  await act(async () => {
    deferred.resolve({ id: 'done', title: 'Done' });
    await new Promise((r) => setTimeout(r, 20));
  });
  await harness.unmount();
});

test('Bấm nút Hủy khi rảnh gọi onClose đóng modal', async () => {
  let closeCallCount = 0;

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => {},
  });

  await harness.clickCancel();
  assert.equal(closeCallCount, 1, 'Bấm Hủy khi rảnh phải gọi onClose');
  await harness.unmount();
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

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCalled = true; },
    onSuccess: (newSession) => { receivedSession = newSession; },
    cloneFn: mockClone,
  });

  await harness.submitForm();

  assert.ok(receivedSession, 'onSuccess phải được gọi với kết quả clone');
  assert.equal(receivedSession.id, 'cloned-001');
  assert.equal(receivedSession.title, '[Bản sao] Đề mẫu — Tích phân');
  assert.equal(closeCalled, true, 'onClose phải được gọi để đóng modal sau khi thành công');
  await harness.unmount();
});

test('Chống gửi liên tiếp (double-submit) khi form đang trong quá trình nhân bản', async () => {
  const deferred = createDeferred();
  let cloneCallCount = 0;

  const slowClone = async () => {
    cloneCallCount += 1;
    return deferred.promise;
  };

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => {},
    onSuccess: () => {},
    cloneFn: slowClone,
  });

  // Lần 1: gửi form
  await harness.submitForm();
  assert.equal(cloneCallCount, 1, 'Lần 1 phải gọi cloneFn');

  // Lần 2: gửi tiếp ngay khi đang pending
  await harness.submitForm();
  assert.equal(cloneCallCount, 1, 'Lần 2 khi đang submitting phải bị chặn ngay (callCount vẫn là 1)');

  await act(async () => {
    deferred.resolve({ id: 'done', title: 'Done' });
    await new Promise((r) => setTimeout(r, 20));
  });
  await harness.unmount();
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

  const harness = await renderRealModal(baseProps);
  await harness.submitForm();

  // Trang cha đặt isOpen = false trên cùng một instance
  await harness.update({ ...baseProps, isOpen: false });

  // Máy chủ trả về sau khi trang cha đã ẩn hộp thoại
  await act(async () => {
    deferred.resolve({ id: 'late-success', title: 'Late' });
    await new Promise((r) => setTimeout(r, 20));
  });

  assert.equal(successCalled, false, 'onSuccess không được gọi khi trang cha đã ẩn modal');
  assert.equal(closeCallCount, 0, 'onClose không được gọi thừa');
  await harness.unmount();
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

  const harness = await renderRealModal(baseProps);
  await harness.submitForm();

  await harness.update({ ...baseProps, isOpen: false });

  await act(async () => {
    deferred.reject(new Error('Lỗi máy chủ nghiêm trọng'));
    await new Promise((r) => setTimeout(r, 20));
  });

  assert.equal(closeCallCount, 0, 'onClose không được gọi thêm');
  await harness.unmount();
});

test('Trang cha gỡ bỏ (unmount) component khi đang chờ nhân bản: Bỏ qua kết quả trả về muộn', async () => {
  const deferred = createDeferred();
  let successCalled = false;
  let closeCallCount = 0;

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCallCount += 1; },
    onSuccess: () => { successCalled = true; },
    cloneFn: async () => deferred.promise,
  });

  await harness.submitForm();
  await harness.unmount();

  await act(async () => {
    deferred.resolve({ id: 'unmounted', title: 'Unmounted' });
    await new Promise((r) => setTimeout(r, 20));
  });

  assert.equal(successCalled, false, 'onSuccess không được gọi khi unmounted');
  assert.equal(closeCallCount, 0, 'onClose không được gọi khi unmounted');
});

test('Lỗi nhân bản khi modal vẫn mở: giữ nguyên modal, hiện thông báo lỗi và cho thử lại', async () => {
  let successCalled = false;
  let closeCalled = false;

  const failingClone = async () => {
    throw new Error('Tên phiên bị trùng lặp');
  };

  const harness = await renderRealModal({
    isOpen: true,
    session: sampleSessionA,
    onClose: () => { closeCalled = true; },
    onSuccess: () => { successCalled = true; },
    cloneFn: failingClone,
  });

  await harness.submitForm();

  const { alertMessage, submitDisabled } = harness.getElements();
  assert.equal(successCalled, false, 'onSuccess không được gọi khi có lỗi');
  assert.equal(closeCalled, false, 'onClose không được gọi khi có lỗi');
  assert.equal(alertMessage, 'Tên phiên bị trùng lặp', 'Phải hiển thị thông báo lỗi trên UI thật');
  assert.equal(submitDisabled, false, 'Nút submit phải được mở lại để người dùng thử lại');
  await harness.unmount();
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

  // 1. Mở modal và gửi cho A
  const harness = await renderRealModal(baseProps);
  await harness.submitForm();

  // 2. Đổi prop session sang B trên CÙNG MỘT instance thật
  await harness.update({ ...baseProps, session: sampleSessionB });

  // 3. Gửi cho B
  await harness.submitForm();

  // 4. A trả về thành công trong khi B đang chờ
  await act(async () => {
    deferredA.resolve({ id: 'cloned-A', title: 'Bản sao A' });
    await new Promise((r) => setTimeout(r, 20));
  });

  // 5. Kiểm tra: Bấm ESC không được đóng B (B vẫn đang submitting)
  harness.pressKey('Escape');
  assert.equal(closeCallCount, 0, 'ESC không được đóng B vì B vẫn đang submitting');
  assert.equal(successResult, null, 'Kết quả của A cũ phải bị bỏ qua');

  // 6. B hoàn tất thành công
  await act(async () => {
    deferredB.resolve({ id: 'cloned-B', title: 'Bản sao B' });
    await new Promise((r) => setTimeout(r, 20));
  });

  assert.deepEqual(successResult, { id: 'cloned-B', title: 'Bản sao B' }, 'Chỉ nhận kết quả của B');
  assert.equal(closeCallCount, 1, 'onClose được gọi đúng 1 lần khi B xong');
  await harness.unmount();
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

  const harness = await renderRealModal(baseProps);
  await harness.submitForm();

  // Đổi sang phiên B trên cùng một instance
  await harness.update({ ...baseProps, session: sampleSessionB });
  await harness.submitForm();

  // A ném lỗi 500 khi B đang chờ
  await act(async () => {
    deferredA.reject(new Error('Máy chủ A lỗi 500'));
    await new Promise((r) => setTimeout(r, 20));
  });

  // Kiểm tra: Bấm ESC không được đóng B và không hiển thị lỗi của A
  harness.pressKey('Escape');
  assert.equal(closeCallCount, 0, 'ESC không được đóng B');
  const { alertMessage } = harness.getElements();
  assert.equal(alertMessage, null, 'Lỗi của A không được hiển thị làm gián đoạn B');

  // B hoàn tất thành công
  await act(async () => {
    deferredB.resolve({ id: 'cloned-B', title: 'Bản sao B' });
    await new Promise((r) => setTimeout(r, 20));
  });

  assert.deepEqual(successResult, { id: 'cloned-B', title: 'Bản sao B' });
  assert.equal(closeCallCount, 1);
  await harness.unmount();
});
