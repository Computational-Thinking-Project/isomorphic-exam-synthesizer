import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';

ensureDomEnvironment();

register('../../test-loader.mjs', import.meta.url);
const { default: ShuffleOnlyConfirmRetry, hasAllCopies, shouldOfferConfirmRetry } = await import(
  './ShuffleOnlyConfirmRetry.jsx'
);
const { stage3PreviewPath, stage3Path } = await import('../../sessionPaths.js');

const SESSION_ID = 'sess-shuffle-1';

function session(overrides = {}) {
  const sources = [{ id: 's1' }, { id: 's2' }];
  const versions = [1, 2].map((index) => ({
    version_index: index,
    questions: sources.map((source) => ({ id: `${source.id}-${index}` })),
  }));
  return {
    session_id: SESSION_ID,
    status: 'generated',
    session_status: 'generated',
    generation_mode: 'shuffle_only',
    config: { n_versions: 2 },
    source_questions: sources,
    exam_versions: versions,
    ...overrides,
  };
}

function render(props) {
  const container = document.createElement('div');
  const root = createRoot(container);
  let location = stage3Path(SESSION_ID);

  function Capture() {
    location = useLocation().pathname;
    return null;
  }

  const element = (extra = {}) =>
    React.createElement(
      MemoryRouter,
      { initialEntries: [stage3Path(SESSION_ID)] },
      React.createElement(Capture),
      React.createElement(
        Routes,
        null,
        React.createElement(Route, {
          path: '*',
          element: React.createElement(ShuffleOnlyConfirmRetry, { sessionId: SESSION_ID, ...props, ...extra }),
        }),
      ),
    );

  return {
    container,
    location: () => location,
    async render(extra) {
      await act(async () => {
        root.render(element(extra));
      });
    },
    async unmount() {
      await act(async () => root.unmount());
    },
  };
}

const button = (container) => container.querySelector('[data-shuffle-only-confirm]');

test('hasAllCopies requires a copy of every source in every version', () => {
  assert.equal(hasAllCopies(session()), true);
  const missing = session();
  missing.exam_versions[1].questions.pop();
  assert.equal(hasAllCopies(missing), false);
  assert.equal(hasAllCopies(session({ config: { n_versions: 3 } })), false);
  assert.equal(hasAllCopies(session({ source_questions: [] })), false);
});

test('shouldOfferConfirmRetry only for generated shuffle-only sessions with all copies', () => {
  assert.equal(shouldOfferConfirmRetry(session(), 'shuffle_only'), true);
  assert.equal(shouldOfferConfirmRetry(session(), 'ai_generation'), false);
  assert.equal(shouldOfferConfirmRetry(session(), null), false);
  assert.equal(shouldOfferConfirmRetry(session({ status: 'reviewed', session_status: 'reviewed' }), 'shuffle_only'), false);
  assert.equal(shouldOfferConfirmRetry(session({ status: 'partial_generated', session_status: 'partial_generated' }), 'shuffle_only'), false);
});

test('button is shown with the notice for a generated shuffle-only session', async () => {
  const harness = render({ session: session(), confirmFn: async () => ({}) });
  await harness.render();
  assert.ok(button(harness.container));
  assert.match(harness.container.textContent, /Đã tạo đủ bản sao\. Phiên chưa hoàn tất xác nhận\./);
  assert.match(harness.container.textContent, /Thử xác nhận lại/);
  await harness.unmount();
});

test('button is hidden for AI mode, reviewed status or missing copies', async () => {
  const missing = session();
  missing.exam_versions[0].questions.pop();
  for (const value of [
    session({ generation_mode: 'ai_generation' }),
    session({ status: 'reviewed', session_status: 'reviewed' }),
    missing,
  ]) {
    const harness = render({ session: value, confirmFn: async () => ({}) });
    await harness.render();
    assert.equal(button(harness.container), null);
    await harness.unmount();
  }
});

test('without generation_mode in the snapshot the saved Stage 2 config decides', async () => {
  for (const [mode, visible] of [['shuffle_only', true], ['ai_generation', false]]) {
    const calls = [];
    const harness = render({
      session: session({ generation_mode: undefined }),
      confirmFn: async () => ({}),
      loadDetail: async (id) => {
        calls.push(id);
        return { generation_config: { generation_mode: mode } };
      },
    });
    await harness.render();
    await act(async () => {});
    assert.deepEqual(calls, [SESSION_ID]);
    assert.equal(Boolean(button(harness.container)), visible);
    await harness.unmount();
  }
});

test('success re-reads the session and opens the next step', async () => {
  const confirmCalls = [];
  const reloads = [];
  const harness = render({
    session: session(),
    confirmFn: async (id) => {
      confirmCalls.push(id);
      return { success: true, session_status: 'reviewed', progress: { ready: true } };
    },
    onConfirmed: async (result) => reloads.push(result.session_status),
  });
  await harness.render();
  await act(async () => button(harness.container).click());
  assert.deepEqual(confirmCalls, [SESSION_ID]);
  assert.deepEqual(reloads, ['reviewed']);
  assert.equal(harness.location(), stage3PreviewPath(SESSION_ID));
  await harness.unmount();
});

test('failure shows the backend reason, re-enables the button and blocks double submit', async () => {
  let release;
  let calls = 0;
  const harness = render({
    session: session(),
    confirmFn: () => {
      calls += 1;
      return new Promise((_, reject) => {
        release = () => reject({
          response: {
            status: 409,
            data: { detail: { code: 'ERR_SHUFFLE_ONLY_NOT_READY', message: 'The copies are not complete or do not match the source.' } },
          },
        });
      });
    },
  });
  await harness.render();
  await act(async () => button(harness.container).click());
  assert.notEqual(button(harness.container).getAttribute('disabled'), null, 'Disabled while in flight');
  await act(async () => button(harness.container).click());
  assert.equal(calls, 1, 'No double submit');
  await act(async () => release());
  assert.match(
    harness.container.querySelector('[data-shuffle-only-confirm-error]').textContent,
    /do not match the source/,
  );
  assert.equal(button(harness.container).getAttribute('disabled'), null);
  assert.equal(harness.location(), stage3Path(SESSION_ID));
  await harness.unmount();
});
