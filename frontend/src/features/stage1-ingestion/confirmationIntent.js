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
      const intent = JSON.parse(value);
      if (!isSourceUuid(intent?.sourceRevision) || !isSourceUuid(intent?.idempotencyKey)) {
        throw new Error('Invalid confirmation intent');
      }
      return intent;
    },
    save({ sourceRevision, idempotencyKey }) {
      storage().setItem(key, JSON.stringify({ sourceRevision, idempotencyKey }));
    },
    clear() { storage().removeItem(key); },
  };
}
