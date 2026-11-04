import assert from 'node:assert/strict';
import { test } from 'node:test';
import { register } from 'node:module';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { readIncompleteError } from './stage1Errors.js';

ensureDomEnvironment();
const { createRoot } = await import('react-dom/client');
const { renderToStaticMarkup } = await import('react-dom/server');
register('../../test-loader.mjs', import.meta.url);
const { default: Dialog } = await import('./IncompleteContentDialog.jsx');
const errors = readIncompleteError({ response: { status: 422, data: { detail: { errors: [
  { question_no: 1, error_type: 'MISSING_ANSWER' },
] } } } }).errors;

async function mount(t, overrides = {}) {
  document.documentElement = document.createElement('html');
  const trigger = document.createElement('button');
  trigger.textContent = 'Nạp nguồn';
  const container = document.createElement('div');
  document.documentElement.appendChild(trigger);
  document.documentElement.appendChild(container);
  trigger.focus();
  const root = createRoot(container);
  const events = [];
  let props = { open: true, errors, onClose: () => events.push('close'),
    onChooseFile: () => events.push('file'), onSwitchToText: () => events.push('text'), ...overrides };
  const render = async next => {
    props = { ...props, ...next };
    await act(async () => root.render(React.createElement(Dialog, props)));
  };
  const unmount = () => act(async () => root.unmount());
  t.after(unmount);
  await render({});
  return { trigger, container, events, render };
}
function press(element, key, shiftKey = false) {
  const event = { type: 'keydown', key, shiftKey, bubbles: true, cancelable: true,
    preventDefault() { this.defaultPrevented = true; } };
  element.dispatchEvent(event);
  return event;
}

test('dialog đóng hoặc không có lỗi không render và không lấy focus', async t => {
  const app = await mount(t, { open: false });
  assert.equal(app.container.textContent, '');
  assert.equal(document.activeElement, app.trigger);
  await app.render({ open: true, errors: [] });
  assert.equal(app.container.textContent, '');
  assert.equal(document.activeElement, app.trigger);
});

test('render lỗi dài/markup như text, có nhãn dialog/list và đúng hướng sửa', () => {
  const model = readIncompleteError({ response: { status: 422, data: { detail: { errors: [
    { question_no: 0, error_type: 'INVALID_FORMAT', message: '<img src=x onerror=alert(1)> ' + 'x'.repeat(2000) },
    { question_no: 3, error_type: 'UNPARSED_OMML', message: '$x\\ne3$' },
  ] } } } });
  const html = renderToStaticMarkup(React.createElement(Dialog, { open: true, errors: model.errors }));
  assert(html.includes('aria-modal="true"'));
  assert(html.includes('aria-labelledby='));
  assert(html.includes('Toàn đề'));
  assert(html.includes('Câu 3'));
  assert(html.includes('&lt;img'));
  assert(!html.includes('<img'));
  assert(html.includes('văn bản hoặc LaTeX'));
  assert(html.includes('overflow-auto'));
  assert(!html.includes('<form'));
});

test('focus ban đầu/Tab/Shift+Tab giữ trong dialog, rerender không giật focus', async t => {
  const app = await mount(t);
  const buttons = app.container.querySelectorAll('button');
  assert.equal(document.activeElement, buttons[0]);
  await act(async () => { buttons[2].focus(); press(buttons[2], 'Tab'); });
  assert.equal(document.activeElement, buttons[0]);
  await act(async () => press(buttons[0], 'Tab', true));
  assert.equal(document.activeElement, buttons[2]);
  buttons[1].focus();
  assert.equal(press(buttons[1], 'Tab').defaultPrevented, undefined);
  await app.render({ errors: [...errors] });
  assert.equal(document.activeElement, buttons[1]);
});

test('Escape/Đóng gọi callback và trả focus; reopen lấy lại focus đúng một lần', async t => {
  const app = await mount(t);
  let close = app.container.querySelector('button');
  await act(async () => press(close, 'Escape'));
  assert.deepEqual(app.events, ['close']);
  assert.equal(document.activeElement, app.trigger);
  await app.render({ open: false });
  await app.render({ open: true });
  close = app.container.querySelector('button');
  assert.equal(document.activeElement, close);
  await act(async () => close.click());
  assert.deepEqual(app.events, ['close', 'close']);
  assert.equal(document.activeElement, app.trigger);
});

test('hai hành động chỉ phát callback riêng, không gọi onClose hoặc phục hồi focus cũ', async t => {
  const app = await mount(t);
  const buttons = app.container.querySelectorAll('button');
  await act(async () => buttons[1].click());
  await act(async () => buttons[2].click());
  assert.deepEqual(app.events, ['file', 'text']);
  assert.notEqual(document.activeElement, app.trigger);
});

test('backdrop đóng, click trong nội dung không đóng', async t => {
  const app = await mount(t);
  await act(async () => app.container.querySelector('h2').click());
  assert.deepEqual(app.events, []);
  await act(async () => app.container.querySelector('[role="dialog"]').click());
  assert.deepEqual(app.events, ['close']);
});

test('không trả focus vào trigger đã rời DOM hoặc disabled', async t => {
  const app = await mount(t);
  app.trigger.setAttribute('disabled', '');
  const close = app.container.querySelector('button');
  await act(async () => close.click());
  assert.notEqual(document.activeElement, app.trigger);
  app.trigger.removeAttribute('disabled');
  document.documentElement.removeChild(app.trigger);
  await act(async () => close.click());
  assert.notEqual(document.activeElement, app.trigger);
});
