/* global document, location, sessionStorage, URLSearchParams */
import { createElement as h, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { api } from '../../src/services/api.js';
import { useAuthStore } from '../../src/features/auth/authStore.js';
import Stage1Route from '../../src/features/stage1-ingestion/Stage1Route.jsx';
import '../../src/index.css';

// Fixture data, auth and transport are local to this entry. No API request leaves the browser.
const mode = new URLSearchParams(location.search).get('case') === 'committed' ? 'committed' : 'retry';
const storeKey = `task204-fixture:${mode}`;
const sessionId = '10000000-0000-4000-8000-000000000001';
const user = { id: 'fixture-task204', email: 'teacher@example.test' };
const revisions = ['20000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000002'];
const fixture = JSON.parse(sessionStorage.getItem(storeKey) ?? 'null') ?? {
  source: 0, confirmed: false, attempts: 0, key: null, sameKey: null, log: [],
};
const persist = () => {
  sessionStorage.setItem(storeKey, JSON.stringify(fixture));
  document.getElementById('report').textContent = [
    `HTTP/Auth fixture · ${mode} · không gọi API thật`,
    `POST confirm: ${fixture.attempts} | Retry giữ key: ${fixture.sameKey ?? 'chưa retry'} | Đã xác nhận: ${fixture.confirmed}`,
    fixture.log.slice(-8).join(' → '),
  ].join('\n');
};
const question = () => ({ id: `fixture-source-${fixture.source}`, session_id: sessionId, question_no: 1,
  raw_content: fixture.source ? 'Nguồn B: Giải $3x-5=10$.' : 'Nguồn A: Giải $x+1=2$.',
  options: fixture.source ? { A: '5', B: '3', C: '1', D: '0' } : { A: '1', B: '2', C: '3', D: '4' }, correct_key: 'A' });
const detail = () => ({ id: sessionId, user_id: user.id, title: 'Đại số fixture', subject: 'Toán', grade: 12,
  status: fixture.confirmed ? 'blueprinted' : 'draft', created_at: '2026-11-05T00:00:00Z',
  updated_at: '2026-11-05T00:00:00Z',
  source_revision: revisions[fixture.source], source_questions: [question()], exam_versions: [] });
const response = (config, data) => ({ status: 200, config, data, headers: {} });
const fail = (config, status, code) => { throw { config, response: { status, data: { error_code: code } } }; };

useAuthStore.getState().setSession({ user, access_token: 'fixture-only' });
useAuthStore.getState().setProfile(user, useAuthStore.getState().sessionVersion);
api.interceptors.request.clear();
api.interceptors.request.use((config) => {
  config._authScope = { userId: user.id, version: useAuthStore.getState().sessionVersion };
  return config;
});
api.defaults.adapter = async (config) => {
  if (config.method === 'get' && config.url === `/sessions/${sessionId}`) {
    fixture.log.push(`GET phiên (${detail().status})`); persist();
    return response(config, detail());
  }
  if (config.method === 'get' && config.url.endsWith('/source-artifacts')) {
    fixture.log.push('GET artifact'); persist();
    if (!fixture.confirmed) fail(config, 404, 'ERR_SESSION_NOT_FOUND');
    return response(config, { session_id: sessionId, canonical_status: 'pending', ready: false, supported_modes: null });
  }
  if (config.method === 'post' && config.url.endsWith('/ingest-text')) {
    fixture.source = 1;
    fixture.log.push('POST nạp'); persist();
    return response(config, { session_id: sessionId, total_questions: 1, questions: [question()] });
  }
  if (config.method === 'post' && config.url.endsWith('/confirm-source')) {
    const key = config.headers.get('Idempotency-Key');
    const revision = JSON.parse(config.data).source_revision;
    fixture.attempts++;
    fixture.sameKey = fixture.key ? fixture.key === key : null;
    fixture.key ??= key;
    fixture.log.push('POST confirm'); persist();
    if (revision !== revisions[fixture.source] || fixture.sameKey === false) fail(config, 409, 'ERR_SOURCE_REVISION_CONFLICT');
    if (fixture.attempts === 1) {
      fixture.confirmed = mode === 'committed';
      persist();
      throw new Error('Fixture mất response');
    }
    fixture.confirmed = true;
    persist();
    return response(config, { session_id: sessionId, confirmation_id: key, status: 'blueprinted',
      canonical_status: 'pending', total_blueprints: 0 });
  }
  throw new Error('Unexpected fixture request');
};

function Stage2Fixture() { return h('h1', null, `Stage 2 fixture · ${useParams().sessionId}`); }

persist();
createRoot(document.getElementById('app')).render(h(StrictMode, null,
  h(MemoryRouter, { initialEntries: [`/session/${sessionId}/stage1`],
    future: { v7_startTransition: true, v7_relativeSplatPath: true } }, h(Routes, null,
    h(Route, { path: '/session/:sessionId/stage1', element: h(Stage1Route) }),
    h(Route, { path: '/session/:sessionId/stage2', element: h(Stage2Fixture) })))));
