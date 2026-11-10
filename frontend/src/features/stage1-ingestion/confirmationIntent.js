import { isSourceUuid } from '../../services/sourceConfirmation.js';

export function createConfirmationIntentStore(accountId, sessionId) {
  const key = `stage1-confirm:${JSON.stringify([accountId, sessionId])}`;
  function storage() {
    if (!accountId || !window.sessionStorage) throw new Error('Confirmation storage unavailable');
    return window.sessionStorage;
  }
  return {
    read() {
      const value = storage().getItem(key);
      if (value === null) return null;
      let intent;
      try { intent = JSON.parse(value); }
      catch { throw Object.assign(new Error('Invalid confirmation intent'), { code: 'ERR_CONFIRM_STORAGE_CORRUPT' }); }
      if (intent?.kind === 'replace-required' && isSourceUuid(intent.sourceRevision)) return intent;
      if (!isSourceUuid(intent?.sourceRevision) || !isSourceUuid(intent?.idempotencyKey)) {
        throw Object.assign(new Error('Invalid confirmation intent'), { code: 'ERR_CONFIRM_STORAGE_CORRUPT' });
      }
      return intent;
    },
    save({ sourceRevision, idempotencyKey }) {
      storage().setItem(key, JSON.stringify({ sourceRevision, idempotencyKey }));
    },
    saveRecovery(sourceRevision) {
      storage().setItem(key, JSON.stringify({ kind: 'replace-required', sourceRevision }));
    },
    clear() { storage().removeItem(key); },
  };
}
