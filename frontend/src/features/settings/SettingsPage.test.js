import assert from 'node:assert/strict';
import { register } from 'node:module';
import { test } from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { useAuthStore } from '../auth/authStore.js';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { readDefaultNumVersions, writeDefaultNumVersions } from './defaultVersionsPreference.js';

ensureDomEnvironment();
register('../../test-loader.mjs', import.meta.url);
const { default: SettingsPage } = await import('./SettingsPage.jsx');
const { default: ProtectedRoute } = await import('../auth/ProtectedRoute.jsx');

async function renderSettings(t, auth, profileState) {
  const originalAuth = useAuthStore.getState();
  useAuthStore.setState(auth);
  const container = document.createElement('div');
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    useAuthStore.setState(originalAuth);
  });
  await act(async () => root.render(
    React.createElement(MemoryRouter, {
      initialEntries: ['/settings'],
      future: { v7_startTransition: true, v7_relativeSplatPath: true },
    }, React.createElement(Routes, null,
      React.createElement(Route, {
        path: '/login',
        element: React.createElement('p', null, 'Đăng nhập'),
      }),
      React.createElement(Route, { element: React.createElement(ProtectedRoute, { profileState }) },
        React.createElement(Route, { path: '/settings', element: React.createElement(SettingsPage) }),
      ),
    )),
  ));
  return container;
}

test('Settings keeps edits local until save and shows failures without discarding them', async (t) => {
  const store = new Map();
  let storageBlocked = true;
  window.localStorage = {
    getItem: (key) => store.get(key) ?? null,
    setItem(key, value) {
      if (storageBlocked) throw new Error('Storage denied');
      store.set(key, value);
    },
  };
  t.after(() => { delete window.localStorage; });
  const container = await renderSettings(t, {
    status: 'authenticated',
    user: { id: 'teacher-a', name: 'Giáo viên Toán', email: 'sample@example.com', created_at: '2026-11-16T20:00:00Z' },
    session: { user: { id: 'teacher-a', user_metadata: { avatar_url: 'https://lh3.googleusercontent.com.evil.example/photo' } } },
  });
  const radios = () => container.querySelectorAll('input');
  const submit = () => container.querySelector('form').dispatchEvent({
    type: 'submit', bubbles: true, cancelable: true, preventDefault() {},
  });

  assert.equal(radios().length, 4);
  assert.equal(radios()[1].checked, true);
  assert.equal(container.querySelector('a').getAttribute('href'), '/dashboard');
  assert.match(container.textContent, /17\/11\/2026/);
  assert.match(container.textContent, /GT/);
  assert.equal(container.querySelectorAll('img').length, 1); // Brand only.

  const choice = radios()[2];
  const propsKey = Object.keys(choice).find((key) => key.startsWith('__reactProps$'));
  await act(async () => choice[propsKey].onChange());
  assert.equal(radios()[2].checked, true);
  assert.equal(readDefaultNumVersions('teacher-a'), null);

  await act(async () => submit());
  assert.match(container.textContent, /Chưa lưu được/);
  assert.equal(radios()[2].checked, true);
  assert.equal(readDefaultNumVersions('teacher-a'), null);

  storageBlocked = false;
  await act(async () => submit());
  assert.match(container.textContent, /Đã lưu cài đặt/);
  assert.equal(readDefaultNumVersions('teacher-a'), 3);

  writeDefaultNumVersions('teacher-b', 4);
  await act(async () => useAuthStore.setState({
    user: { id: 'teacher-b', email: 'other@example.com' },
    session: { user: { id: 'teacher-b', user_metadata: { picture: 'https://lh3.googleusercontent.com/photo' } } },
  }));
  assert.equal(radios()[3].checked, true);
  assert.match(container.textContent, /Chưa có thông tin/);
  const photos = container.querySelectorAll('img');
  assert.equal(photos.length, 3); // Brand and the two account avatars.
  const errorHandler = Object.keys(photos[2]).find((key) => key.startsWith('__reactProps$'));
  await act(async () => photos[2][errorHandler].onError());
  assert.equal(container.querySelectorAll('img').length, 2);
});

test('guest and a profile awaiting verification cannot reach Settings', async (t) => {
  const container = await renderSettings(t, {
    status: 'profile_pending', user: null,
  }, { error: 'Chưa thể tải hồ sơ.', retry() {} });
  assert.match(container.textContent, /Chưa thể tải hồ sơ/);
  assert.match(container.textContent, /Thử lại tải hồ sơ/);
  assert.doesNotMatch(container.textContent, /Tùy chọn sinh đề/);

  await act(async () => useAuthStore.setState({ status: 'unauthenticated' }));
  assert.equal(container.textContent, 'Đăng nhập');
});
