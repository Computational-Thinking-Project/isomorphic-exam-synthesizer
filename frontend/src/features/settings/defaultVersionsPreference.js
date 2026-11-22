const KEY_PREFIX = 'exam-mirror.settings.default-versions.v1:';

export const SYSTEM_DEFAULT_NUM_VERSIONS = 2;

export function readDefaultNumVersions(userId) {
  if (!userId) return null;

  try {
    const value = window.localStorage.getItem(KEY_PREFIX + userId);
    return ['1', '2', '3', '4'].includes(value) ? Number(value) : null;
  } catch {
    return null;
  }
}

export function writeDefaultNumVersions(userId, value) {
  if (!userId || !Number.isInteger(value) || value < 1 || value > 4) return false;

  try {
    window.localStorage.setItem(KEY_PREFIX + userId, String(value));
    return true;
  } catch {
    return false;
  }
}
