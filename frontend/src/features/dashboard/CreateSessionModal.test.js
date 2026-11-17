import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { register } from 'node:module';
import React, { act } from 'react';
import { DOMElement, ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
document.oninput = null;

const { createRoot } = await import('react-dom/client');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);

const { api } = await import('../../services/api.js');
const { default: CreateSessionModal } = await import('./CreateSessionModal.jsx');

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('CreateSessionModal (F02 & F03)', () => {
  let postCalls = [];
  let accountKey;

  beforeEach(() => {
    postCalls = [];
    useAuthStore.getState().setSession({
      user: { id: 'account-a' },
      access_token: 'fixture-token-a',
    });
    useAuthStore.getState().setProfile(
      { id: 'account-a', email: 'teacher@example.test' },
      useAuthStore.getState().sessionVersion,
    );
    auth.getSession = async () => ({
      data: { session: useAuthStore.getState().session },
      error: null,
    });
    accountKey = `account-a:${useAuthStore.getState().sessionVersion}`;
  });

  async function mountModal(props = {}) {
    const container = document.createElement('div');
    const root = createRoot(container);

    const defaultProps = {
      isOpen: true,
      onClose: () => {},
      onCreated: () => {},
      onCheckSessions: () => {},
      accountKey,
      ...props,
    };

    await act(async () => {
      root.render(React.createElement(CreateSessionModal, defaultProps));
      await new Promise((r) => setTimeout(r, 70));
    });

    function getElements() {
      const form = container.querySelector('form');
      const input = container.querySelector('input');
      const alert = container.querySelector('[role="alert"]');
      const buttons = container.querySelectorAll('button');
      const submitButton = buttons.find((b) => b.getAttribute('type') === 'submit') || null;
      const checkButton = alert ? alert.querySelector('button') : null;

      return {
        container,
        form,
        input,
        alert,
        alertText: alert ? alert.textContent : '',
        submitButton,
        checkButton,
        isSubmitDisabled: submitButton
          ? (submitButton.getAttribute('disabled') !== null || Boolean(submitButton.disabled))
          : false,
      };
    }

    async function changeTitle(value) {
      const { input } = getElements();
      assert.ok(input, 'Cần input để nhập tiêu đề');
      await act(async () => {
        const protoSetter = Object.getOwnPropertyDescriptor(DOMElement.prototype, 'value').set;
        protoSetter.call(input, value);
        input.dispatchEvent({
          type: 'input',
          bubbles: true,
        });
        await new Promise((r) => setTimeout(r, 20));
      });
    }

    async function submitForm() {
      const { form } = getElements();
      assert.ok(form, 'Cần form để submit');
      await act(async () => {
        form.dispatchEvent({
          type: 'submit',
          bubbles: true,
          preventDefault: () => {},
        });
        await new Promise((r) => setTimeout(r, 50));
      });
    }

    async function unmount() {
      await act(async () => {
        root.unmount();
      });
    }

    async function updateProps(nextProps) {
      await act(async () => {
        root.render(React.createElement(CreateSessionModal, { ...defaultProps, ...nextProps }));
        await new Promise((r) => setTimeout(r, 20));
      });
    }

    return {
      container,
      root,
      getElements,
      changeTitle,
      submitForm,
      unmount,
      updateProps,
    };
  }

  it('Shared metadata: all grades are available and selecting grade 1 sends Mathematics metadata', async () => {
    api.defaults.adapter = async (config) => {
      postCalls.push(config);
      return { status: 201, data: {
        id: 'grade-one', user_id: 'account-a', title: 'Toán lớp 1', subject: 'Toán', grade: 1,
        status: 'draft', created_at: '2026-11-17T00:00:00Z', updated_at: '2026-11-17T00:00:00Z',
      }, headers: {}, config };
    };
    const modal = await mountModal();
    try {
      const grade = modal.container.querySelector('select');
      assert.equal(grade.options.length, 12);
      assert.equal(grade.options.find((option) => option.value === '12').selected, true);
      assert(modal.container.textContent.includes('Toán học'));
      assert(!modal.container.textContent.includes('THPT'));
      await modal.changeTitle('Toán lớp 1');
      await act(async () => {
        Object.getOwnPropertyDescriptor(DOMElement.prototype, 'value').set.call(grade, '1');
        grade.dispatchEvent({ type: 'change', bubbles: true });
      });
      await modal.submitForm();
      assert.equal(postCalls.length, 1);
      assert.deepEqual(JSON.parse(postCalls[0].data), { title: 'Toán lớp 1', subject: 'Toán', grade: 1 });
    } finally {
      await modal.unmount();
    }
  });

  it('F02: HTTP 500 hiển thị nút "Kiểm tra danh sách phiên" và disable nút tạo', async () => {
    api.defaults.adapter = async (config) => {
      postCalls.push(config);
      const err = new Error('Internal Server Error');
      err.response = { status: 500, data: { detail: 'Database error' } };
      throw err;
    };

    let checkCalled = false;
    const modal = await mountModal({
      onCheckSessions: () => { checkCalled = true; },
    });

    await modal.changeTitle('Đề thi học kỳ 1');
    await modal.submitForm();

    const elements = modal.getElements();
    assert.equal(postCalls.length, 1, 'Đã gửi 1 POST request');
    assert.ok(elements.alert, 'Phải có alert hiển thị lỗi');
    assert.ok(elements.checkButton, 'Phải có nút kiểm tra danh sách phiên');
    assert.match(elements.checkButton.textContent, /Kiểm tra danh sách phiên/);
    assert.equal(elements.isSubmitDisabled, true, 'Nút submit phải bị vô hiệu hóa khi createUncertain');

    // Thử click submit thêm lần nữa -> không có POST thứ hai
    await modal.submitForm();
    assert.equal(postCalls.length, 1, 'Không gửi POST lần thứ hai khi trạng thái là uncertain');

    // Click nút kiểm tra danh sách phiên
    await act(async () => {
      elements.checkButton.dispatchEvent({
        type: 'click',
        bubbles: true,
      });
      await new Promise((r) => setTimeout(r, 10));
    });

    assert.equal(checkCalled, true, 'Callback onCheckSessions phải được gọi khi click');
    await modal.unmount();
  });

  it('F02: Remount modal với key mới sau khi refresh cho phép submit lại bình thường', async () => {
    let callCount = 0;
    api.defaults.adapter = async (config) => {
      callCount++;
      postCalls.push(config);
      if (callCount === 1) {
        const err = new Error('Gateway Timeout');
        err.response = { status: 504, data: {} };
        throw err;
      }
      return {
        status: 201,
        data: {
          id: 'session-retry-ok',
          user_id: 'account-a',
          title: 'Đề thi đã tạo lại',
          subject: 'Toán',
          grade: 12,
          status: 'draft',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        headers: {},
        config,
      };
    };

    let createdId = null;
    const modal1 = await mountModal({
      onCreated: (id) => { createdId = id; },
    });

    await modal1.changeTitle('Đề thi thử lần 1');
    await modal1.submitForm();

    assert.equal(modal1.getElements().isSubmitDisabled, true, 'Modal 1 bị lock do 504');
    await modal1.unmount();

    // Giả lập Dashboard remount modal mới với key mới
    const modal2 = await mountModal({
      onCreated: (id) => { createdId = id; },
    });

    await modal2.changeTitle('Đề thi đã tạo lại');
    await modal2.submitForm();

    assert.equal(callCount, 2, 'Modal 2 gửi request tạo thành công');
    assert.equal(createdId, 'session-retry-ok', 'Nhận đúng ID phiên đã tạo');
    await modal2.unmount();
  });

  it('F03: Request pending rồi unmount -> signal bị abort và callback onCreated không được gọi', async () => {
    const deferred = createDeferred();
    let abortedSignal = false;

    api.defaults.adapter = async (config) => {
      postCalls.push(config);
      if (config.signal) {
        if (config.signal.aborted) {
          abortedSignal = true;
        } else {
          config.signal.addEventListener('abort', () => {
            abortedSignal = true;
          });
        }
      }
      return deferred.promise;
    };

    let createdCalled = false;
    const modal = await mountModal({
      onCreated: () => { createdCalled = true; },
    });

    await modal.changeTitle('Đề thi đang tạo');

    // Kích hoạt submit để request bắt đầu gửi đi và pending
    const { form } = modal.getElements();
    await act(async () => {
      form.dispatchEvent({
        type: 'submit',
        bubbles: true,
        preventDefault: () => {},
      });
      // Đợi một chút để axios request interceptor và adapter được gọi
      await new Promise((r) => setTimeout(r, 20));
    });

    assert.equal(postCalls.length, 1, 'Request tạo phiên phải đang được gửi đi');

    // Unmount modal ngay khi request đang pending
    await modal.unmount();

    assert.ok(
      abortedSignal || postCalls[0]?.signal?.aborted,
      'Signal phải nhận được tín hiệu abort khi modal unmount',
    );

    // Sau khi unmount, backend mới phản hồi trả về
    await act(async () => {
      deferred.resolve({
        status: 201,
        data: {
          id: 'session-late',
          user_id: 'account-a',
          title: 'Đề thi muộn',
          subject: 'Toán',
          grade: 12,
          status: 'draft',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        headers: {},
        config: postCalls[0],
      });
      await new Promise((r) => setTimeout(r, 20));
    });

    assert.equal(createdCalled, false, 'onCreated tuyệt đối không được gọi khi component đã unmount');
  });

  it('Tạo phiên thành công bình thường -> onCreated nhận đúng session ID', async () => {
    api.defaults.adapter = async (config) => {
      postCalls.push(config);
      return {
        status: 201,
        data: {
          id: 'session-success-789',
          user_id: 'account-a',
          title: 'Đề Toán 12 Chuẩn',
          subject: 'Toán',
          grade: 12,
          status: 'draft',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        headers: {},
        config,
      };
    };

    let createdId = null;
    const modal = await mountModal({
      onCreated: (id) => { createdId = id; },
    });

    await modal.changeTitle('Đề Toán 12 Chuẩn');
    await modal.submitForm();

    assert.equal(postCalls.length, 1);
    assert.equal(createdId, 'session-success-789', 'onCreated nhận đúng ID phiên mới');
    await modal.unmount();
  });
});
