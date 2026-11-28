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

export async function getExportStatus(sessionId, options = {}) {
  const { packagingKey, signal } = options;
  const encodedId = encodeSessionId(sessionId);
  const query = packagingKey ? `?packaging_key=${encodeURIComponent(packagingKey)}` : '';
  const { data } = await api.get(`/sessions/${encodedId}/export${query}`, {
    signal,
    headers: NO_STORE_HEADERS,
  });

  if (!isPlainObject(data) || !VALID_EXPORT_STATES.has(data.state)) {
    throw new Error('Phản hồi trạng thái xuất đề không hợp lệ.');
  }
  if (data.state === 'ready') {
    validateReadyMetadata(data);
  }

  const result = {
    state: data.state,
    status: data.state,
    filename: data.filename ?? null,
    sha256: data.sha256 ?? null,
    size_bytes: data.size_bytes ?? null,
    error_code: typeof data.error_code === 'string' ? data.error_code : null,
  };
  if (data.packaging_key !== undefined) result.packaging_key = data.packaging_key;
  if (data.identity_kind !== undefined) result.identity_kind = data.identity_kind;
  if (data.effective_config !== undefined) result.effective_config = data.effective_config;

  return result;
}

export async function triggerExport(sessionId, configOrOptions, maybeOptions) {
  let config = undefined;
  let options = {};

  if (configOrOptions && (configOrOptions.visible_fields || configOrOptions.answer_sheet || configOrOptions.formats)) {
    config = configOrOptions;
    options = maybeOptions || {};
  } else if (configOrOptions && (configOrOptions.signal || configOrOptions.timeout)) {
    options = configOrOptions;
  } else if (isPlainObject(configOrOptions) && Object.keys(configOrOptions).length > 0) {
    config = configOrOptions;
    options = maybeOptions || {};
  }

  const encodedId = encodeSessionId(sessionId);
  const { signal, timeout = EXPORT_POST_TIMEOUT_MS } = options;
  const body = config ? { config } : undefined;

  const { data } = await api.post(`/sessions/${encodedId}/export`, body, {
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

  const result = {
    state: data.state,
    status: data.state,
    filename: data.filename ?? null,
    sha256: data.sha256 ?? null,
    size_bytes: data.size_bytes ?? null,
  };
  if (data.packaging_key !== undefined) result.packaging_key = data.packaging_key;
  if (data.identity_kind !== undefined) result.identity_kind = data.identity_kind;
  if (data.effective_config !== undefined) result.effective_config = data.effective_config;

  return result;
}

export async function issueDownloadUrl(sessionId, optionsOrPackagingKey = {}, maybeOptions = {}) {
  let packagingKey = null;
  let options = {};

  if (typeof optionsOrPackagingKey === 'string') {
    packagingKey = optionsOrPackagingKey;
    options = maybeOptions;
  } else if (isPlainObject(optionsOrPackagingKey)) {
    packagingKey = optionsOrPackagingKey.packagingKey || optionsOrPackagingKey.packaging_key || null;
    options = optionsOrPackagingKey;
  }

  const encodedId = encodeSessionId(sessionId);
  const { signal } = options;
  const body = packagingKey ? { packaging_key: packagingKey } : undefined;

  const { data } = await api.post(`/sessions/${encodedId}/export/download-url`, body, {
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

export async function fetchAnswerKey(sessionId, { target = 'original', versionId, format = 'json', signal } = {}) {
  const encodedId = encodeSessionId(sessionId);
  const params = new URLSearchParams();
  if (target) params.set('target', target);
  if (versionId) params.set('version_id', versionId);
  if (format) params.set('format', format);

  const query = params.toString() ? `?${params.toString()}` : '';
  const { data } = await api.get(`/sessions/${encodedId}/answer-key${query}`, {
    signal,
    headers: NO_STORE_HEADERS,
  });

  return data;
}
