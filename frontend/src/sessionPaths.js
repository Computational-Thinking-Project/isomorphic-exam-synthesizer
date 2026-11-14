import { generatePath } from 'react-router-dom';

export const STAGE1_ROUTE = '/session/:sessionId/stage1';
export const STAGE2_ROUTE = '/session/:sessionId/stage2';
export const STAGE3_ROUTE = '/session/:sessionId/stage3';
export const STAGE3_PREVIEW_ROUTE = '/session/:sessionId/stage3/preview';
export const EXPORT_ROUTE = '/session/:sessionId/export';

function buildSessionPath(route, sessionId) {
  return generatePath(route, { sessionId: encodeURIComponent(sessionId) });
}

export function stage1Path(sessionId) {
  return buildSessionPath(STAGE1_ROUTE, sessionId);
}

export function stage2Path(sessionId) {
  return buildSessionPath(STAGE2_ROUTE, sessionId);
}

export function stage3Path(sessionId) {
  return buildSessionPath(STAGE3_ROUTE, sessionId);
}

export function stage3PreviewPath(sessionId) {
  return buildSessionPath(STAGE3_PREVIEW_ROUTE, sessionId);
}

export function exportPath(sessionId) {
  return buildSessionPath(EXPORT_ROUTE, sessionId);
}
