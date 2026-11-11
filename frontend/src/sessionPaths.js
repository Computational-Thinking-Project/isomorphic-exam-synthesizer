import { generatePath } from 'react-router-dom';

export const STAGE1_ROUTE = '/session/:sessionId/stage1';
export const STAGE2_ROUTE = '/session/:sessionId/stage2';

export function stage1Path(sessionId) {
  return generatePath(STAGE1_ROUTE, { sessionId: encodeURIComponent(sessionId) });
}

export function stage2Path(sessionId) {
  return generatePath(STAGE2_ROUTE, { sessionId: encodeURIComponent(sessionId) });
}
