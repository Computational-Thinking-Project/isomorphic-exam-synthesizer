import { api } from './api.js';

const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const canonicalStatuses = ['pending', 'running', 'ready', 'failed'];
export const isSourceUuid = (value) => typeof value === 'string' && UUID.test(value);
const sameId = (actual, expected) => isSourceUuid(actual) && actual.toLowerCase() === expected.toLowerCase();

function sessionPath(sessionId) {
  if (!isSourceUuid(sessionId)) {
    throw Object.assign(new Error('Phiên cần xác nhận không hợp lệ.'), { code: 'ERR_CONFIRM_INPUT' });
  }
  return `/sessions/${encodeURIComponent(sessionId)}`;
}

export async function confirmSource(sessionId, { sourceRevision, idempotencyKey, signal } = {}) {
  const path = sessionPath(sessionId);
  if (!isSourceUuid(sourceRevision) || !isSourceUuid(idempotencyKey)) {
    throw Object.assign(new Error('Chưa có thông tin hợp lệ để xác nhận bản đề này.'), { code: 'ERR_CONFIRM_INPUT' });
  }
  const { status, data } = await api.post(`${path}/confirm-source`, { source_revision: sourceRevision }, {
    headers: { 'Idempotency-Key': idempotencyKey }, signal,
  });
  if (status !== 200 || !sameId(data?.session_id, sessionId) || !sameId(data?.confirmation_id, idempotencyKey)
    || data.status !== 'blueprinted' || !canonicalStatuses.includes(data.canonical_status)) {
    throw Object.assign(new Error('Phản hồi xác nhận không hợp lệ.'), {
      code: 'ERR_CONFIRM_RESPONSE', outcomeUncertain: true,
    });
  }
  return data;
}

export async function getSourceArtifactStatus(sessionId, { signal } = {}) {
  const { status, data } = await api.get(`${sessionPath(sessionId)}/source-artifacts`, { signal });
  if (status !== 200 || !sameId(data?.session_id, sessionId) || !canonicalStatuses.includes(data.canonical_status)
    || data.ready !== (data.canonical_status === 'ready')
    || (data.ready ? !Array.isArray(data.supported_modes) : data.supported_modes !== null)) {
    throw new Error('Phản hồi trạng thái chuẩn bị đề không hợp lệ.');
  }
  return data;
}
