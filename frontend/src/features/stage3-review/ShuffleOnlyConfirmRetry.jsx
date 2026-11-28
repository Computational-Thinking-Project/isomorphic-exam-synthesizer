import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, RefreshCw } from 'lucide-react';
import { stage3PreviewPath } from '../../sessionPaths.js';
import { getSessionDetail } from '../../services/sessions.js';
import { confirmShuffleOnlyCopies } from '../../services/stage2Service.js';

/**
 * EXT-02 (PR #112): retry the backend confirmation of shuffle-only copies.
 *
 * The worker confirms automatically after a shuffle-only job finishes. If that step was
 * deferred, the session stays 'generated' while Review is read-only, so this button lets the
 * owner retry POST /sessions/{id}/shuffle-only/confirm. It only re-checks stored copies.
 * The review snapshot is readable only by the session owner, so rendering on that page
 * already implies the owner.
 */

/** Every version has a current copy for every source question. */
export function hasAllCopies(session) {
  const sources = Array.isArray(session?.source_questions) ? session.source_questions.length : 0;
  const versions = Array.isArray(session?.exam_versions) ? session.exam_versions : [];
  const expectedVersions = Number(session?.config?.n_versions) || versions.length;
  if (!sources || !versions.length || versions.length !== expectedVersions) return false;
  return versions.every((version) => Array.isArray(version.questions) && version.questions.length === sources);
}

export function shouldOfferConfirmRetry(session, generationMode) {
  const status = session?.session_status || session?.status;
  return generationMode === 'shuffle_only' && status === 'generated' && hasAllCopies(session);
}

function reasonFrom(error) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message;
  if (typeof detail === 'string') return detail;
  return 'Chưa xác nhận được bản sao. Vui lòng thử lại sau.';
}

export default function ShuffleOnlyConfirmRetry({
  session,
  sessionId,
  onConfirmed,
  confirmFn = confirmShuffleOnlyCopies,
  loadDetail = getSessionDetail,
}) {
  const navigate = useNavigate();
  // The review snapshot carries generation_mode once EXT-01's 029b is in; fall back to the
  // saved Stage 2 config so this works before that migration lands.
  const snapshotMode = session?.generation_mode ?? null;
  const [detailMode, setDetailMode] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reason, setReason] = useState('');
  const inFlight = useRef(false);
  const status = session?.session_status || session?.status;

  useEffect(() => {
    let active = true;
    if (snapshotMode || !sessionId || status !== 'generated' || !hasAllCopies(session)) return undefined;
    Promise.resolve()
      .then(() => loadDetail(sessionId))
      .then((detail) => {
        const config = detail?.generation_config || detail?.config;
        if (active) setDetailMode(config?.generation_mode ?? null);
      })
      .catch(() => { if (active) setDetailMode(null); });
    return () => { active = false; };
  }, [snapshotMode, sessionId, status, session, loadDetail]);

  const mode = snapshotMode ?? detailMode;
  if (!shouldOfferConfirmRetry(session, mode)) return null;

  async function handleRetry() {
    if (inFlight.current) return;
    inFlight.current = true;
    setIsSubmitting(true);
    setReason('');
    try {
      const result = await confirmFn(sessionId);
      if (onConfirmed) await onConfirmed(result);
      if (result?.session_status === 'reviewed' && result?.progress?.ready === true) {
        navigate(stage3PreviewPath(sessionId));
      }
    } catch (error) {
      setReason(reasonFrom(error));
    } finally {
      inFlight.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <div role="status" data-testid="shuffle-only-confirm-retry" className="stage3-session-notice">
      <span>Đã tạo đủ bản sao. Phiên chưa hoàn tất xác nhận.</span>{' '}
      <button
        type="button"
        data-shuffle-only-confirm
        disabled={isSubmitting}
        onClick={() => void handleRetry()}
        className="inline-flex items-center gap-1 text-highlight underline disabled:opacity-60"
      >
        {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        {isSubmitting ? 'Đang xác nhận…' : 'Thử xác nhận lại'}
      </button>
      {reason && <p role="alert" data-shuffle-only-confirm-error>{reason}</p>}
    </div>
  );
}
