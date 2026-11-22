import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readDefaultNumVersions, writeDefaultNumVersions } from './defaultVersionsPreference.js';

test('version preferences round-trip 1–4 separately for each account', (t) => {
  const values = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    },
  };
  t.after(() => { delete globalThis.window; });

  assert.equal(readDefaultNumVersions('teacher-a'), null);
  assert.equal(writeDefaultNumVersions('teacher-b', 4), true);
  for (const value of [1, 2, 3, 4]) {
    assert.equal(writeDefaultNumVersions('teacher-a', value), true);
    assert.equal(readDefaultNumVersions('teacher-a'), value);
    assert.equal(readDefaultNumVersions('teacher-b'), 4);
  }
  for (const value of [0, 5, 2.5, '3', null]) {
    assert.equal(writeDefaultNumVersions('teacher-a', value), false);
  }
  assert.equal(readDefaultNumVersions('teacher-a'), 4);
  assert.equal(writeDefaultNumVersions('', 2), false);
});

test('unavailable storage and invalid stored values leave the preference unset', (t) => {
  let value;
  const browser = {
    localStorage: {
      getItem: () => value,
      setItem: () => { throw new Error('Quota exceeded'); },
    },
  };
  globalThis.window = browser;
  t.after(() => { delete globalThis.window; });

  for (value of [null, '', '2.0', '4\n', '0', '5', 'json']) {
    assert.equal(readDefaultNumVersions('teacher'), null);
  }
  assert.equal(writeDefaultNumVersions('teacher', 3), false);

  Object.defineProperty(browser, 'localStorage', {
    get() { throw new Error('Storage blocked'); },
  });
  assert.equal(readDefaultNumVersions('teacher'), null);
  assert.equal(writeDefaultNumVersions('teacher', 3), false);
});
