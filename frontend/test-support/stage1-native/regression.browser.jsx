/* global document, navigator, requestAnimationFrame, URLSearchParams, location */
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import axios from 'axios';
import Dialog from '../../src/features/stage1-ingestion/IncompleteContentDialog.jsx';
import Panel from '../../src/features/stage1-ingestion/Stage1SourcePanel.jsx';
import { api } from '../../src/services/api.js';
import { useAuthStore } from '../../src/features/auth/authStore.js';
import '../../src/index.css';

// This entry is never imported by App. All HTTP/Auth here is fixture-only.
const session = { user: { id: 'native-fixture' }, access_token: 'not-a-real-token' };
useAuthStore.getState().setSession(session);
api.interceptors.request.clear();
api.interceptors.request.use(config => {
  config._authScope = { userId: session.user.id, version: useAuthStore.getState().sessionVersion };
  return config;
});
const detail = { id: 'native-session', user_id: session.user.id, status: 'draft', title: 'Đại số fixture',
  source_questions: [{ id: 'source-A', question_no: 1, raw_content: '$x+1=2$',
    options: { A: '1', B: '2', C: '3', D: '4' }, correct_key: 'A' }], exam_versions: [] };
const requests = [];
api.defaults.adapter = async config => {
  requests.push({ method: config.method, url: config.url });
  renderReport();
  if (config.method === 'get') return { config, status: 200, headers: {}, data: detail };
  throw new axios.AxiosError('Fixture incomplete', 'ERR_BAD_RESPONSE', config, null, {
    config, status: 422, data: { detail: { errors: [{ question_no: 1, error_type: 'MISSING_ANSWER' }] } },
  });
};
const report = { environment: navigator.userAgent, fixture: 'native DOM + mocked HTTP/Auth, no cloud',
  automated: [], manual: 'NOT RUN: Escape/Tab and native picker require real user interaction', requests };
const controls = document.getElementById('controls');
controls.innerHTML = '<h1>Stage1 native regression · HTTP/Auth mô phỏng</h1><button id="run">Chạy focus-out / lifecycle</button> <button id="open">Mở dialog để kiểm phím</button> <button id="background">Nút nền</button><input id="background-input" aria-label="Input nền"><pre id="report"></pre>';
const background = document.getElementById('background');
let root = createRoot(document.getElementById('modal'));
let closes = 0;
let Component = Dialog;
// Optional temporary baseline exported with git show; never included in production.
if (new URLSearchParams(location.search).has('baseline')) {
  const baselinePath = './baseline.local.jsx';
  Component = (await import(/* @vite-ignore */ baselinePath)).default;
}
const errors = [{ location: 'Câu 1', title: 'Thiếu đáp án', guidance: 'Bổ sung đáp án đúng.' }];
function renderReport() { document.getElementById('report').textContent = JSON.stringify(report, null, 2); }
function check(name, expected, actual) {
  report.automated.push({ name, expected, actual, result: expected === actual ? 'PASS' : 'FAIL' });
  renderReport();
}
function show(open) {
  flushSync(() => root.render(createElement(Component, { open, errors,
    onClose: () => { closes++; show(false); }, onChooseFile: () => show(false), onSwitchToText: () => show(false) })));
}
const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
document.getElementById('run').onclick = async event => {
  event.currentTarget.disabled = true;
  report.automated = [];
  try {
    background.focus(); show(true); await frame();
    const modal = document.querySelector('[role="dialog"]');
    check('native modal is open', true, modal.matches(':modal'));
    for (const target of [background, document.getElementById('background-input')]) {
      target.focus(); await frame();
      check(`focus-out ${target.id}`, true, modal.contains(document.activeElement));
    }
    show(true); await frame();
    check('rerender keeps focus inside', true, modal.contains(document.activeElement));
    show(false); await frame(); background.focus();
    check('closed releases background', true, document.activeElement === background);
    show(true); await frame();
    const before = closes;
    flushSync(() => root.unmount()); await frame(); background.focus();
    check('unmount removes modal', null, document.querySelector('[role="dialog"]'));
    check('unmount releases background', true, document.activeElement === background);
    check('unmount does not call onClose', before, closes);
  } catch (error) {
    report.automated.push({ result: 'FAIL', error: String(error) });
  } finally {
    flushSync(() => root.unmount());
    root = createRoot(document.getElementById('modal'));
    document.getElementById('run').disabled = false;
    renderReport();
  }
};
document.getElementById('open').onclick = () => show(true);
createRoot(document.getElementById('panel')).render(createElement(Panel, { detail, isCurrent: () => true }));
renderReport();
