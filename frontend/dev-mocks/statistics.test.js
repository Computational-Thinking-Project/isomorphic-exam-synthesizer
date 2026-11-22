import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  normalStatisticsFixture,
  emptyStatisticsFixture,
  createStatisticsMockMiddleware,
} from './statistics.js';

test('normalStatisticsFixture satisfies contract invariants', () => {
  const { total_sessions, in_progress_sessions, approved_not_exported_sessions, exported_sessions, by_status } = normalStatisticsFixture;

  const sumOfStatuses = Object.values(by_status).reduce((acc, count) => acc + count, 0);
  assert.equal(total_sessions, sumOfStatuses, 'total_sessions must equal sum of all by_status counts');
  assert.equal(total_sessions, 23);

  const inProgressSum =
    by_status.draft +
    by_status.blueprinted +
    by_status.configured +
    by_status.generating +
    by_status.partial_generated +
    by_status.generated +
    by_status.reviewed;
  assert.equal(in_progress_sessions, inProgressSum, 'in_progress_sessions must equal sum of the 7 in-progress statuses');
  assert.equal(in_progress_sessions, 17);

  assert.equal(approved_not_exported_sessions, by_status.approved);
  assert.equal(approved_not_exported_sessions, 3);

  assert.equal(exported_sessions, by_status.exported);
  assert.equal(exported_sessions, 2);

  assert.equal(by_status.failed, 1);
  assert.equal(by_status.unknown, 0);
});

test('emptyStatisticsFixture has all zero values', () => {
  const { total_sessions, in_progress_sessions, approved_not_exported_sessions, exported_sessions, by_status } = emptyStatisticsFixture;

  assert.equal(total_sessions, 0);
  assert.equal(in_progress_sessions, 0);
  assert.equal(approved_not_exported_sessions, 0);
  assert.equal(exported_sessions, 0);
  for (const [key, count] of Object.entries(by_status)) {
    assert.equal(count, 0, `by_status.${key} must be 0`);
  }
});

test('createStatisticsMockMiddleware ignores other endpoints and methods', () => {
  const middleware = createStatisticsMockMiddleware({ delayMs: 0 });
  let nextCalled = false;

  // POST method
  middleware({ method: 'POST', url: '/api/users/me/statistics' }, {}, () => {
    nextCalled = true;
  });
  assert.equal(nextCalled, true);

  // Other endpoint
  nextCalled = false;
  middleware({ method: 'GET', url: '/api/users/me' }, {}, () => {
    nextCalled = true;
  });
  assert.equal(nextCalled, true);
});

test('createStatisticsMockMiddleware returns normal fixture on GET /api/users/me/statistics', async () => {
  const middleware = createStatisticsMockMiddleware({ scenario: 'normal', delayMs: 5 });
  const headers = {};
  let body = '';
  let statusCode = 0;

  const res = {
    setHeader(name, val) { headers[name] = val; },
    end(data) { body = data; },
    get statusCode() { return statusCode; },
    set statusCode(val) { statusCode = val; },
  };

  await new Promise((resolve) => {
    res.end = (data) => {
      body = data;
      resolve();
    };
    middleware({ method: 'GET', url: '/api/users/me/statistics' }, res, () => {});
  });

  assert.equal(statusCode, 200);
  assert.equal(headers['Content-Type'], 'application/json');
  assert.equal(headers['X-Mock-Data'], 'statistics');
  assert.deepEqual(JSON.parse(body), normalStatisticsFixture);
});

test('createStatisticsMockMiddleware returns error state on error scenario', async () => {
  const middleware = createStatisticsMockMiddleware({ scenario: 'error', delayMs: 5 });
  const headers = {};
  let body = '';
  let statusCode = 0;

  const res = {
    setHeader(name, val) { headers[name] = val; },
    end(data) { body = data; },
    get statusCode() { return statusCode; },
    set statusCode(val) { statusCode = val; },
  };

  await new Promise((resolve) => {
    res.end = (data) => {
      body = data;
      resolve();
    };
    middleware({ method: 'GET', url: '/api/users/me/statistics?ref=dash' }, res, () => {});
  });

  assert.equal(statusCode, 503);
  assert.equal(headers['X-Mock-Data'], 'statistics-error');
  assert.match(body, /temporarily unavailable/);
});
