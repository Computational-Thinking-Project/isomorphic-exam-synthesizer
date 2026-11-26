import { api } from './api.js';

export const EXPORT_POST_TIMEOUT_MS = 120000;

const VALID_EXPORT_STATES = new Set(['idle', 'preparing', 'ready', 'failed']);
const VALID_TRIGGER_STATES = new Set(['ready', 'preparing']);
const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

function encodeSessionId(sessionId) {
  const trimmed = typeof sessionId === 'string' ? sessionId.trim() : '';
  if (!trimmed || trimmed.toLowerCase() === 'new') {
    throw new Error('ID phiên không hợp lệ.');
  }
  return encodeURIComponent(trimmed);
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validateReadyMetadata(data) {
  if (
    typeof data.filename !== 'string'
    || data.filename.trim() === ''
    || typeof data.sha256 !== 'string'
    || data.sha256.trim() === ''
    || !Number.isInteger(data.size_bytes)
    || data.size_bytes < 0
  ) {
    throw new Error('Thông tin gói xuất đề không hợp lệ.');
  }
}

export async function getExportStatus(sessionId, { signal } = {}) {
  const encodedId = encodeSessionId(sessionId);
  const { data } = await api.get(`/sessions/${encodedId}/export`, {
    signal,
    headers: NO_STORE_HEADERS,
  });

  if (!isPlainObject(data) || !VALID_EXPORT_STATES.has(data.state)) {
    throw new Error('Phản hồi trạng thái xuất đề không hợp lệ.');
  }
  if (data.state === 'ready') {
    validateReadyMetadata(data);
  }

  return {
    state: data.state,
    status: data.state,
    filename: data.filename ?? null,
    sha256: data.sha256 ?? null,
    size_bytes: data.size_bytes ?? null,
    error_code: typeof data.error_code === 'string' ? data.error_code : null,
  };
}

export async function triggerExport(sessionId, { signal, timeout = EXPORT_POST_TIMEOUT_MS } = {}) {
  const encodedId = encodeSessionId(sessionId);
  const { data } = await api.post(`/sessions/${encodedId}/export`, undefined, {
    signal,
    timeout,
    headers: NO_STORE_HEADERS,
  });

  if (!isPlainObject(data) || !VALID_TRIGGER_STATES.has(data.state)) {
    throw new Error('Phản hồi khởi tạo xuất đề không hợp lệ.');
  }
  if (data.state === 'ready') {
    validateReadyMetadata(data);
  }

  return {
    state: data.state,
    status: data.state,
    filename: data.filename ?? null,
    sha256: data.sha256 ?? null,
    size_bytes: data.size_bytes ?? null,
  };
}

export async function issueDownloadUrl(sessionId, { signal } = {}) {
  const encodedId = encodeSessionId(sessionId);
  const { data } = await api.post(`/sessions/${encodedId}/export/download-url`, undefined, {
    signal,
    headers: NO_STORE_HEADERS,
  });

  if (
    !isPlainObject(data)
    || typeof data.url !== 'string'
    || !data.url.startsWith('https://')
    || typeof data.expires_at !== 'string'
    || Number.isNaN(Date.parse(data.expires_at))
    || !Number.isInteger(data.expires_in)
    || data.expires_in <= 0
    || typeof data.filename !== 'string'
    || data.filename.trim() === ''
  ) {
    throw new Error('Phản hồi liên kết tải xuống không hợp lệ.');
  }

  return {
    url: data.url,
    expires_at: data.expires_at,
    expires_in: data.expires_in,
    filename: data.filename,
  };
}

export async function listExportFiles(sessionId, format, { signal } = {}) {
  const { data } = await api.get(`/sessions/${encodeSessionId(sessionId)}/export/files`, {
    params: { format }, signal, headers: NO_STORE_HEADERS,
  });
  if (!Array.isArray(data.files) || data.files.some((file) =>
    typeof file.filename !== 'string' || !file.filename.endsWith('.' + format)
    || !Number.isInteger(file.size_bytes) || file.size_bytes < 0)) {
    throw new Error('Danh sách tài liệu không hợp lệ.');
  }
  return data.files;
}

export async function downloadExportFile(sessionId, format, filename, { signal } = {}) {
  const { data } = await api.get(`/sessions/${encodeSessionId(sessionId)}/export/files`, {
    params: { format, filename }, signal, headers: NO_STORE_HEADERS, responseType: 'blob',
  });
  return data;
}
