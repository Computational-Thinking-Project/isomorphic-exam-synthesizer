/* global process, setTimeout, clearTimeout */
/**
 * Mock fixture và Vite dev server middleware cho endpoint Statistics.
 * Phục vụ kiểm tra UI tại /statistics mà không cần áp dụng Supabase RPC 027.
 */

export const normalStatisticsFixture = {
  total_sessions: 23,
  in_progress_sessions: 17,
  approved_not_exported_sessions: 3,
  exported_sessions: 2,
  by_status: {
    draft: 4,
    blueprinted: 3,
    configured: 2,
    generating: 1,
    partial_generated: 1,
    generated: 4,
    reviewed: 2,
    approved: 3,
    exported: 2,
    failed: 1,
    unknown: 0,
  },
};

export const emptyStatisticsFixture = {
  total_sessions: 0,
  in_progress_sessions: 0,
  approved_not_exported_sessions: 0,
  exported_sessions: 0,
  by_status: {
    draft: 0,
    blueprinted: 0,
    configured: 0,
    generating: 0,
    partial_generated: 0,
    generated: 0,
    reviewed: 0,
    approved: 0,
    exported: 0,
    failed: 0,
    unknown: 0,
  },
};

export function createStatisticsMockMiddleware(options = {}) {
  const scenario = options.scenario || process.env.MOCK_STATISTICS_SCENARIO || 'normal';
  const delayMs = options.delayMs ?? 600;

  return (req, res, next) => {
    const pathname = req.url ? req.url.split('?')[0] : '';
    if (req.method !== 'GET' || pathname !== '/api/users/me/statistics') {
      return next();
    }

    const timer = setTimeout(() => {
      if (res.writableEnded || req.destroyed) return;

      if (scenario === 'error') {
        res.statusCode = 503;
        res.setHeader('Content-Type', 'application/json');
        res.setHeader('Cache-Control', 'no-store');
        res.setHeader('X-Mock-Data', 'statistics-error');
        res.end(JSON.stringify({ detail: 'Mock API: Session statistics temporarily unavailable' }));
        return;
      }

      const payload = scenario === 'empty' ? emptyStatisticsFixture : normalStatisticsFixture;
      res.statusCode = 200;
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Cache-Control', 'no-store');
      res.setHeader('X-Mock-Data', 'statistics');
      res.end(JSON.stringify(payload));
    }, delayMs);

    if (typeof req.on === 'function') {
      req.on('close', () => clearTimeout(timer));
    }
  };
}
