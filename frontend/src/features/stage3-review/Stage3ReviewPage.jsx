import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { exportPath, stage2Path, stage3PreviewPath } from '../../sessionPaths.js';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  Eye,
  Info,
  Loader2,
  Lock,
  RefreshCw,
  RotateCcw,
} from 'lucide-react';
import Stage3InspectionDialog from './Stage3InspectionDialog.jsx';
import Stage3ReviewNotifications from './Stage3ReviewNotifications.jsx';
import BrandLogo from '../../components/BrandLogo.jsx';
import Stage3Comparison, { ReviewQuestionContent, ReviewSolution } from './Stage3Comparison.jsx';
import './stage3Review.css';
import { getSessionDetail } from '../../services/sessions.js';
import { retryGeneration } from '../../services/stage2Service.js';
import {
  acceptQuestion,
  rejectAndRegenerateQuestion,
  revertQuestion,
  fetchReviewSnapshot,
  recoverReviewSession,
  adaptReviewSnapshot,
} from '../../services/stage3Service.js';

function getVariantWarningFlags(variant) {
  const isFallback = Boolean(
    variant?.is_fallback ||
    variant?.source_fallback ||
    variant?.warning_flag === 'fallback' ||
    variant?.origin === 'confirmed_source_fallback' ||
    (variant?.attempts >= 4 && variant?.is_fallback !== false)
  ) && variant?.origin !== 'original_clone';

  const hasWarning = Boolean(
    variant?.has_warning ||
    variant?.warning_flag ||
    variant?.status === 'warning' ||
    variant?.status === 'needs_review' ||
    variant?.warning_message ||
    (variant?.validation_report && variant?.validation_report.is_valid === false)
  );
  return { isFallback, hasWarning };
}

/**
 * Trích xuất an toàn chuỗi thông báo lỗi từ response HTTP
 */
function extractErrorString(err, fallback = 'Đã xảy ra lỗi.') {
  const resData = err?.response?.data;
  if (typeof resData?.error_message === 'string') return resData.error_message;
  if (typeof resData?.message === 'string') return resData.message;
  if (typeof resData?.detail === 'string') return resData.detail;
  if (typeof resData?.detail?.message === 'string') return resData.detail.message;
  if (typeof resData?.detail?.error === 'string') return resData.detail.error;
  if (typeof resData?.error === 'string') return resData.error;
  if (typeof err?.message === 'string') return err.message;
  return fallback;
}

function isVariantApproved(variant, approvedSet) {
  if (!variant) return false;
  if (variant.status === 'approved') return true;
  const candId = variant.id || variant.candidate_id || variant.question_id;
  return Boolean(candId && approvedSet?.has(candId));
}

/**
 * Thu thập toàn bộ ID, candidate_id của các câu đã được duyệt
 */
function extractApprovedIds(sessionData) {
  const approved = new Set();
  if (!sessionData) return approved;

  if (Array.isArray(sessionData.version_questions)) {
    sessionData.version_questions.forEach((q) => {
      if (q.status === 'approved') {
        if (q.id) approved.add(q.id);
        if (q.candidate_id) approved.add(q.candidate_id);
        if (q.question_id) approved.add(q.question_id);
      }
    });
  }

  if (Array.isArray(sessionData.exam_versions)) {
    sessionData.exam_versions.forEach((ver) => {
      const qList = ver.questions || ver.version_questions || [];
      qList.forEach((q) => {
        if (q.status === 'approved') {
          if (q.id) approved.add(q.id);
          if (q.candidate_id) approved.add(q.candidate_id);
          if (q.question_id) approved.add(q.question_id);
        }
      });
    });
  }

  return approved;
}

/**
 * Adapter tìm kiếm biến thể câu hỏi linh hoạt hỗ trợ nhiều cấu trúc dữ liệu từ Backend:
 * - Nested questions trong exam_versions[i].questions hoặc exam_versions[i].version_questions
 * - Flat questions trong session.version_questions (so khớp theo version_id hoặc version_index/code)
 */
function findVariantInSession(session, versionIndex, questionNo) {
  if (!session) return null;

  const versions = session.exam_versions || [];
  const targetCode = String(100 + versionIndex);

  // Tìm phiên bản tương ứng
  const v = versions.find((ver, idx) => {
    const vIdx = ver.version_index ?? ver.index ?? idx + 1;
    const code = String(ver.version_code || '');
    return vIdx === versionIndex || code === targetCode || code === String(versionIndex);
  });

  // 1. Kiểm tra nested trong version
  if (v) {
    const vQuestions = v.questions || v.version_questions || [];
    const found = vQuestions.find((q) => {
      const qNum = q.question_no ?? q.number;
      return qNum === questionNo;
    });
    if (found) return found;
  }

  // 2. Kiểm tra mảng phẳng version_questions ở session root
  if (Array.isArray(session.version_questions)) {
    const found = session.version_questions.find((q) => {
      const qNum = q.question_no ?? q.number;
      if (qNum !== questionNo) return false;

      if (v?.id && q.version_id) {
        return q.version_id === v.id;
      }
      const qVIdx = q.version_index ?? q.version_code;
      return qVIdx === versionIndex || String(qVIdx) === targetCode;
    });
    if (found) return found;
  }

  return null;
}

function findNextUnreviewed(session, version, number) {
  const versions = session.config?.n_versions || session.exam_versions.length;
  const questions = session.source_questions.length;
  for (let dv = 0; dv < versions; dv++) {
    const nextVersion = (version - 1 + dv) % versions + 1;
    for (let dq = 0; dq < questions; dq++) {
      const nextNumber = ((dv === 0 ? number : 0) + dq) % questions + 1;
      const candidate = findVariantInSession(session, nextVersion, nextNumber);
      if (candidate && !['approved', 'regenerating', 'rejected'].includes(candidate.status)) {
        return { version: nextVersion, number: nextNumber };
      }
    }
  }
  return null;
}

function versionLabel(session, index) {
  const version = session?.exam_versions?.find((item, offset) => (item.version_index ?? item.index ?? offset + 1) === index);
  return version?.version_code ? `Mã đề #${version.version_code}` : `Đề ${index}`;
}

/**
 * Đếm tổng số câu hỏi biến thể thực sự đã được nạp trong dữ liệu phiên
 */
function countTotalLoadedVariants(session) {
  if (!session) return 0;
  let count = 0;
  if (Array.isArray(session.version_questions)) {
    count += session.version_questions.length;
  }
  if (Array.isArray(session.exam_versions)) {
    session.exam_versions.forEach((v) => {
      const qList = v.questions || v.version_questions || [];
      count += qList.length;
    });
  }
  return count;
}

/**
 * Sinh UUID v4 cho Idempotency-Key
 */
function generateClientUUID() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID();
    } catch {
      // Fallback nếu crypto.randomUUID không khả dụng
    }
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Stage3ReviewPage: Màn hình Xem & Duyệt đề thi đẳng cấu (Giai đoạn 3)
 * Route: /session/:sessionId/stage3
 */
export default function Stage3ReviewPage({
  loadSession = fetchReviewSnapshot,
  recoverSession = recoverReviewSession,
  loadSessionDetail = getSessionDetail,
  retryGen = retryGeneration,
  acceptQuestionFn = acceptQuestion,
  regenerateQuestionFn = rejectAndRegenerateQuestion,
  revertQuestionFn = revertQuestion,
}) {
  const params = useParams();
  const sessionId = params.sessionId || params.id;
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
  const [lockedDetail, setLockedDetail] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const [activeVersionTab, setActiveVersionTab] = useState(1);
  const [selectedQuestionNo, setSelectedQuestionNo] = useState(1);
  const [isRetryingAll, setIsRetryingAll] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);
  const [reviewSyncRequired, setReviewSyncRequired] = useState(false);

  // Trạng thái modal Kiểm tra đáp án (SolutionDialog)
  const [inspection, setInspection] = useState(null);
  const inspectedVariant = inspection && findVariantInSession(session, inspection.versionIndex, inspection.qNo);
  const selectedSolution = useMemo(() => inspectedVariant ? { ...inspection, variant: inspectedVariant } : null,
    [inspection, inspectedVariant]);
  const [approvalFocus, setApprovalFocus] = useState(null);
  const workspaceRef = useRef(null);
  const [pendingActions, setPendingActions] = useState(new Map());
  const [isShuffle409, setIsShuffle409] = useState(false);
  const [approvedVariantIds, setApprovedVariantIds] = useState(new Set());

  const loadOperationRef = useRef(0);
  const retryOperationRef = useRef(0);
  const mutationOperationRef = useRef(0);
  const isMountedRef = useRef(true);
  const activeSessionIdRef = useRef(sessionId);
  const navigationTimerRef = useRef(null);
  const navigationEpoch = useRef(0);
  const pendingRef = useRef(new Map());
  const [activeRecovery, setActiveRecovery] = useState(false);
  const actionKeysRef = useRef(new Map());

  const loadData = useCallback(async ({ background = false, recover = true } = {}) => {
    if (!sessionId) {
      if (isMountedRef.current) {
        setIsLoading(false);
        setError('Không có mã phiên làm việc hợp lệ.');
      }
      return;
    }

    const currentOp = ++loadOperationRef.current;
    const targetSessionId = sessionId;

    if (!background) setIsLoading(true);
    setError(null);
    setIsShuffle409(false);
    setLockedDetail(null);

    try {
      const rawData = await loadSession(targetSessionId);
      if (
        !isMountedRef.current ||
        loadOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      let data = adaptReviewSnapshot(rawData);
      let active = data?.exam_versions?.some(v => v.questions?.some(q => q.status === 'regenerating'));
      if (active && recover && !data.read_only && data.generation_mode !== 'shuffle_only') {
        const response = await recoverSession(targetSessionId);
        if (!isMountedRef.current || loadOperationRef.current !== currentOp ||
            activeSessionIdRef.current !== targetSessionId) return;
        data = adaptReviewSnapshot(response.snapshot);
        active = response.has_active_operation;
      }
      setActiveRecovery(Boolean(active));
      setReviewSyncRequired(false);
      if (!background) setInspection(null);
      setSession(data);
      setLockedDetail(null);

      const initialApproved = extractApprovedIds(data);
      setApprovedVariantIds(initialApproved);
      setIsLoading(false);
      return data;
    } catch (err) {
      if (
        !isMountedRef.current ||
        loadOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }

      const httpStatus = err?.response?.status ?? err?.status;
      const errCode =
        err?.response?.data?.error_code ??
        err?.response?.data?.code ??
        err?.errorCode;
      const isLocked423 = httpStatus === 423 || errCode === 'ERR_SESSION_LOCKED';
      const isShuffle409 =
        httpStatus === 409 &&
        ['ERR_SHUFFLE_REQUIRED', 'ERR_STAGE_FINALIZING'].includes(errCode);

      if (isShuffle409) {
        setIsShuffle409(true);
        setError('Phiên làm việc đã chốt thứ tự đề thi. Vui lòng chuyển sang màn hình Xem trước & Phê duyệt.');
        setIsLoading(false);
        return;
      }

      if (isLocked423) {
        try {
          const detail = await loadSessionDetail(targetSessionId);
          if (
            !isMountedRef.current ||
            loadOperationRef.current !== currentOp ||
            activeSessionIdRef.current !== targetSessionId
          ) {
            return;
          }
          if (['approved', 'exported'].includes(detail?.status)) {
            setLockedDetail(detail);
            setIsLoading(false);
            return;
          }
          setError('Trạng thái phiên không khớp điều kiện khóa duyệt. Vui lòng thử lại hoặc về Dashboard.');
          setIsLoading(false);
          return;
        } catch (detailErr) {
          if (
            !isMountedRef.current ||
            loadOperationRef.current !== currentOp ||
            activeSessionIdRef.current !== targetSessionId
          ) {
            return;
          }
          setError(
            extractErrorString(
              detailErr,
              extractErrorString(err, 'Không thể tải chi tiết phiên làm việc.'),
            ),
          );
          setIsLoading(false);
          return;
        }
      }

      if (background) {
        setReviewSyncRequired(true);
        setActionMessage({ type: 'error', text: 'Thao tác chưa đối soát được. Vui lòng đọc lại trạng thái.' });
      }
      else setError(extractErrorString(err, 'Không thể tải chi tiết phiên làm việc.'));
      setIsLoading(false);
    }
  }, [sessionId, loadSession, loadSessionDetail, recoverSession]);

  useEffect(() => {
    isMountedRef.current = true;
    activeSessionIdRef.current = sessionId;
    loadOperationRef.current += 1;
    mutationOperationRef.current += 1;
    retryOperationRef.current += 1;

    if (navigationTimerRef.current) {
      clearTimeout(navigationTimerRef.current);
      navigationTimerRef.current = null;
    }

    // Reset sạch sẽ dữ liệu của phiên trước để tránh rò rỉ hoặc hiển thị nhầm khi đang tải phiên mới
    setSession(null);
    setLockedDetail(null);
    setError(null);
    setIsShuffle409(false);
    setActiveVersionTab(1);
    setSelectedQuestionNo(1);
    setIsRetryingAll(false);
    setReviewSyncRequired(false);
    setInspection(null);
    setApprovalFocus(null);
    setApprovedVariantIds(new Set());
    setActionMessage(null);
    setPendingActions(new Map());
    actionKeysRef.current.clear();
    pendingRef.current.clear();
    setActiveRecovery(false);

    loadData();

    return () => {
      isMountedRef.current = false;
      loadOperationRef.current += 1;
      mutationOperationRef.current += 1;
      retryOperationRef.current += 1;
      if (navigationTimerRef.current) {
        clearTimeout(navigationTimerRef.current);
        navigationTimerRef.current = null;
      }
    };
  }, [loadData, sessionId]);

  const handleOpenSolutionModal = (_variant, qNo, versionIndex) => {
    setSelectedQuestionNo(qNo);
    setInspection({ qNo, versionIndex });
  };

  const isFinalLocked = ['approved', 'exported'].includes(session?.status);
  const isPreviewBlocked = isFinalLocked || Boolean(session?.read_only);
  const isShuffleOnly = session?.generation_mode === 'shuffle_only';
  const isReviewReadOnly = isPreviewBlocked || isShuffleOnly;
  const canRetryPartial = session?.status === 'partial_generated' && !isFinalLocked && !isShuffleOnly;

  async function mutate(action, selection, reasons = []) {
    if (!selection || isReviewReadOnly || reviewSyncRequired || isRetryingAll) return;
    const { variant, versionIndex, qNo } = selection;
    const id = variant.candidate_id || variant.id || variant.question_id;
    if (!id || pendingRef.current.has(id) || variant.status === 'regenerating') return;
    if (action === 'reject' && (variant.result_kind === 'ORIGINAL_CLONE' || activeRecovery || [...pendingRef.current.values()].includes('reject'))) return;
    const op = mutationOperationRef.current;
    const epoch = navigationEpoch.current;
    const current = () => isMountedRef.current && activeSessionIdRef.current === sessionId && mutationOperationRef.current === op;
    const binding = JSON.stringify([action, id]);
    const attempt = actionKeysRef.current.get(binding) || { key: generateClientUUID(), reasons };
    const { key } = attempt;
    actionKeysRef.current.set(binding, attempt);
    pendingRef.current.set(id, action);
    setPendingActions(new Map(pendingRef.current));
    ++loadOperationRef.current;
    setActionMessage(null);
    let response;
    let failure;
    try {
      if (action === 'reject') response = await regenerateQuestionFn(sessionId, id, key, { reasons: attempt.reasons });
      else response = await (action === 'accept' ? acceptQuestionFn : revertQuestionFn)(sessionId, id, key);
    } catch (err) {
      failure = err;
    }
    if (!current()) return;
    try {
      const latest = await loadData({ background: true, recover: false });
      if (!current()) return;
      if (failure) {
        const code = failure.response?.data?.error_code ?? failure.errorCode;
        const rejectedBeforeReservation = action === 'reject' && failure.response?.status === 503
          && code === 'ERR_AI_SERVICE_UNAVAILABLE';
        if (rejectedBeforeReservation || ['ERR_OPERATION_FINISHED', 'ERR_ATTEMPT_REPLAYED'].includes(code)) {
          actionKeysRef.current.delete(binding);
        }
        setActionMessage({ type: 'error', text: extractErrorString(failure) });
      }
      if (!latest) return;
      const candidate = findVariantInSession(latest, versionIndex, qNo);
      const latestId = candidate?.candidate_id || candidate?.id || candidate?.question_id;
      if (failure) return;
      const confirmed = action === 'accept' ? latestId === id && candidate.status === 'approved'
        : latestId && latestId === response?.question_id && (action === 'reject' ? latestId !== id : candidate.is_reverted);
      if (!confirmed) {
        setReviewSyncRequired(true);
        return;
      }
      actionKeysRef.current.delete(binding);
      if (action === 'accept' && epoch === navigationEpoch.current && !latest.read_only) {
        setInspection(null);
        const next = findNextUnreviewed(latest, versionIndex, qNo);
        if (next) {
          setActiveVersionTab(next.version);
          setSelectedQuestionNo(next.number);
          setApprovalFocus(next.number);
        } else if (latest.progress?.ready && latest.status === 'reviewed') setApprovalFocus('finalize');
      }
    } finally {
      if (current()) {
        pendingRef.current.delete(id);
        setPendingActions(new Map(pendingRef.current));
      }
    }
  }

  const handleRetryAllMissing = async () => {
    if (!canRetryPartial || isRetryingAll) return;
    const currentOp = ++retryOperationRef.current;
    const targetSessionId = sessionId;

    setIsRetryingAll(true);
    setActionMessage(null);

    try {
      await retryGen(targetSessionId);
      if (
        !isMountedRef.current ||
        retryOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }

      setActionMessage({
        type: 'success',
        text: 'Đã kích hoạt sinh bổ sung các câu còn thiếu. Đang chuyển hướng về tiến trình sinh đề...',
      });

      navigationTimerRef.current = setTimeout(() => {
        if (
          isMountedRef.current &&
          retryOperationRef.current === currentOp &&
          activeSessionIdRef.current === targetSessionId
        ) {
          navigate(stage2Path(targetSessionId));
        }
      }, 1200);
    } catch (err) {
      if (
        !isMountedRef.current ||
        retryOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setActionMessage({
        type: 'error',
        text: extractErrorString(err, 'Không thể kích hoạt sinh bổ sung toàn bộ.'),
      });
    } finally {
      if (isMountedRef.current && retryOperationRef.current === currentOp) {
        setIsRetryingAll(false);
      }
    }
  };

  const numVersions = session?.config?.n_versions || session?.exam_versions?.length || 1;
  const totalSourceQuestions = session?.source_questions?.length || 0;
  const totalLoadedVariants = countTotalLoadedVariants(session);
  const isPartial = session?.status === 'partial_generated';
  const hasLoadedAnyVariants = totalLoadedVariants > 0 || Boolean(session?.raw_snapshot?.versions);
  const totalExpectedSlots = numVersions * totalSourceQuestions;

  // F01: Tự động đưa activeVersionTab về 1 nếu số lượng mã đề của phiên mới nhỏ hơn tab đang chọn
  useEffect(() => {
    if (numVersions > 0 && activeVersionTab > numVersions) {
      setActiveVersionTab(1);
    }
  }, [activeVersionTab, numVersions]);

  // Tính số câu đã duyệt
  const approvedCount = useMemo(() => {
    let count = 0;
    for (let vIdx = 1; vIdx <= numVersions; vIdx++) {
      for (let qNo = 1; qNo <= totalSourceQuestions; qNo++) {
        const v = findVariantInSession(session, vIdx, qNo);
        if (isVariantApproved(v, approvedVariantIds)) {
          count++;
        }
      }
    }
    return count;
  }, [session, numVersions, totalSourceQuestions, approvedVariantIds]);

  // All source positions stay reachable, including missing and already approved pairs.
  const currentQuestionNo = selectedSolution?.versionIndex === activeVersionTab
    ? selectedSolution.qNo
    : selectedQuestionNo >= 1 && selectedQuestionNo <= totalSourceQuestions
      ? selectedQuestionNo : totalSourceQuestions > 0 ? 1 : null;
  const currentVariant = findVariantInSession(session, activeVersionTab, currentQuestionNo);
  const inspectionOpen = selectedSolution?.qNo === currentQuestionNo && selectedSolution?.versionIndex === activeVersionTab;
  const currentSource = session?.source_questions?.find((source) =>
    currentVariant?.source_question_id && (source.source_question_id || source.id) === currentVariant.source_question_id
  ) || session?.source_questions?.find((source) => (source.question_no ?? source.number) === currentQuestionNo);

  const selectVersion = (version) => {
    ++navigationEpoch.current;
    const question = currentQuestionNo ?? selectedQuestionNo;
    setSelectedQuestionNo(question);
    setActiveVersionTab(version);
    setInspection(null);
  };
  const handleVersionKeyDown = (event, version) => {
    const next = event.key === 'ArrowRight' ? version % numVersions + 1
      : event.key === 'ArrowLeft' ? (version + numVersions - 2) % numVersions + 1
      : event.key === 'Home' ? 1 : event.key === 'End' ? numVersions : null;
    if (next === null) return;
    event.preventDefault();
    selectVersion(next);
    event.currentTarget.parentNode?.querySelector(`[data-review-version="${next}"]`)?.focus();
  };
  const goToNextUnreviewed = () => {
    ++navigationEpoch.current;
    const next = findNextUnreviewed(session, activeVersionTab, currentQuestionNo ?? 1);
    if (next) {
      setSelectedQuestionNo(next.number);
      setActiveVersionTab(next.version);
      setInspection(null);
      return;
    }
    setActionMessage({ type: 'success', text: 'Không còn câu chưa duyệt.' });
  };

  const handleSelectNavigatorQuestion = (qNo) => {
    ++navigationEpoch.current;
    setSelectedQuestionNo(qNo);
    setInspection(null);
  };

  const restoredViewRef = useRef(null);
  useEffect(() => {
    if (!session || session.id !== sessionId || restoredViewRef.current === sessionId) return;
    restoredViewRef.current = sessionId;
    try {
      const saved = JSON.parse(sessionStorage.getItem(`review-view:${sessionId}`) || 'null');
      if (!saved) return;
      if (Number.isInteger(saved.version) && saved.version >= 1 && saved.version <= numVersions) setActiveVersionTab(saved.version);
      if (Number.isInteger(saved.question) && saved.question >= 1 && saved.question <= totalSourceQuestions) setSelectedQuestionNo(saved.question);
    } catch { /* View restoration is optional; server data remains authoritative. */ }
  }, [session, sessionId, numVersions, totalSourceQuestions]);
  useEffect(() => {
    if (!session || session.id !== sessionId || restoredViewRef.current !== sessionId) return;
    try {
      sessionStorage.setItem(`review-view:${sessionId}`, JSON.stringify({
        version: activeVersionTab, question: currentQuestionNo,
      }));
    } catch { /* Storage may be unavailable. */ }
  }, [session, sessionId, activeVersionTab, currentQuestionNo]);

  useEffect(() => {
    if (approvalFocus === null || selectedSolution) return;
    const selector = approvalFocus === 'finalize' ? '[data-review-finalize]' : `[data-review-nav-q="${approvalFocus}"]`;
    workspaceRef.current?.querySelector(selector)?.focus();
    setApprovalFocus(null);
  }, [approvalFocus, selectedSolution]);

  const isFinalizeDisabled =
    session?.progress?.ready !== true || session?.status !== 'reviewed' || activeRecovery || isPreviewBlocked || reviewSyncRequired || pendingActions.size > 0 || isRetryingAll;

  const isSelectedVariantApproved = useMemo(() => {
    return isVariantApproved(selectedSolution?.variant, approvedVariantIds);
  }, [selectedSolution, approvedVariantIds]);



  if (isLoading) {
    return (
      <div className="paper-ui min-h-screen bg-canvas text-ink flex items-center justify-center p-8">
        <div className="flex flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-highlight" />
          <p className="text-xs text-muted">Đang tải chi tiết đề thi và các câu hỏi biến thể...</p>
        </div>
      </div>
    );
  }

  if (lockedDetail) {
    return (
      <div className="paper-ui mx-auto max-w-2xl p-6">
        <div
          role="status"
          data-testid="stage3-banner-locked"
          className="rounded-2xl border border-approved-border bg-approved-bg p-8 text-center shadow-paper"
        >
          <Lock className="mx-auto h-12 w-12 text-approved-ink" />
          <h2 className="mt-4 text-xl font-bold text-strong">
            Đề thi đã được phê duyệt và khóa nội dung vĩnh viễn
          </h2>
          {lockedDetail.title && (
            <p className="mt-2 text-sm font-medium text-approved-ink">{lockedDetail.title}</p>
          )}
          <p className="mt-2 text-sm text-ink">
            Phiên làm việc đang ở trạng thái khóa duyệt ({lockedDetail.status}). Mọi thao tác duyệt hoặc tạo lại biến thể đã được khóa; bạn có thể chuyển sang màn hình Xuất bản để tải gói đề thi.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button type="button" data-testid="stage3-btn-goto-export" onClick={() => navigate(exportPath(sessionId))}
              className="rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white">
              Đi đến xuất đề
            </button>

            <button
              type="button"
              data-testid="stage3-btn-goto-preview"
              onClick={() => navigate(stage3PreviewPath(sessionId))}
              className="inline-flex items-center gap-2 rounded-xl border border-approved-border px-4 py-2 text-xs font-medium text-approved-ink hover:bg-approved-bg"
            >
              Xem lại bản rà soát (chỉ đọc)
            </button>
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-xs font-medium text-ink hover:bg-rail"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Về Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="paper-ui min-h-screen bg-canvas text-ink p-6">
        <div className="mx-auto max-w-xl">
          <div
            role="alert"
            className="rounded-2xl border border-danger-border bg-danger-soft p-6 text-center shadow-paper"
          >
            <AlertCircle className="mx-auto h-10 w-10 text-danger" />
            <h2 className="mt-3 text-lg font-bold text-strong">Không thể tải đề thi</h2>
            <p className="mt-1 text-sm text-danger">{error}</p>
            <div className="mt-6 flex justify-center gap-3">
              {isShuffle409 ? (
                <button
                  type="button"
                  data-testid="stage3-btn-goto-preview-409"
                  onClick={() => navigate(stage3PreviewPath(sessionId))}
                  className="inline-flex items-center gap-2 rounded-xl bg-highlight px-4 py-2 text-xs font-semibold text-white hover:bg-highlight shadow-sm"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Chuyển tới Xem trước & Phê duyệt
                </button>
              ) : (
                <button
                  type="button"
                  onClick={loadData}
                  className="inline-flex items-center gap-2 rounded-xl bg-rail px-4 py-2 text-xs font-semibold text-ink hover:bg-rail"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Thử lại
                </button>
              )}
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-xs font-semibold text-ink hover:bg-rail"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Về Dashboard
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isAllApproved = !isFinalizeDisabled;
  const headerBadge = isFinalLocked
    ? { label: 'Đã phê duyệt & Khóa đề', className: 'border-approved-border bg-approved-bg text-approved-ink' }
    : isReviewReadOnly
    ? { label: 'Chỉ xem', className: 'border-line bg-rail text-ink' }
    : isPartial
    ? { label: 'Thiếu câu hỏi', className: 'border-accent-border bg-accent-soft text-accent-ink' }
    : isAllApproved
    ? { label: 'Đủ điều kiện xem trước', className: 'border-approved-border bg-approved-bg text-approved-ink' }
    : { label: 'Đang duyệt', className: 'border-support-line bg-support-bg text-highlight' };

  return (
    <div ref={workspaceRef} className="paper-ui stage3-review-workspace bg-canvas text-ink">
      <main className="stage3-shell">
      <header className="stage3-session-header">
        <BrandLogo size="sm" className="stage3-brand" />
        <div className="stage3-header-details">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h1 className="font-semibold text-strong break-words">{session?.title || 'Đối chiếu và duyệt'}</h1>
            <span className="text-sm font-semibold text-highlight">Bước 3/3 · Duyệt câu hỏi</span>
            <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${headerBadge.className}`}>{headerBadge.label}</span>
          </div>
        </div>
        {isFinalLocked && <button type="button" data-testid="stage3-btn-goto-export" onClick={() => navigate(exportPath(sessionId))}
          className="rounded-lg bg-approved-ink px-4 py-2 text-xs font-semibold text-white">Tới màn hình Xuất bản</button>}
      </header>

      <Stage3ReviewNotifications key={sessionId} message={actionMessage} />
      {activeRecovery && <div role="status">Đang tạo lại câu hỏi. <button type="button"
        onClick={() => void loadData()}>Kiểm tra lại</button></div>}
      {reviewSyncRequired && <div role="alert" className="stage3-session-notice">
        Chưa đối soát được trạng thái review.
        <button type="button" className="text-highlight underline" onClick={() => void loadData()}>Đọc lại trạng thái</button>
      </div>}

      {/* Cảnh báo phiên đã khóa nội dung (approved / exported) */}
      {isFinalLocked && (
        <div
          role="status"
          data-testid="stage3-banner-locked"
          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-approved-border bg-approved-bg p-4 text-approved-ink"
        >
          <div className="flex items-center gap-3">
            <Lock className="h-5 w-5 shrink-0 text-approved-ink" />
            <div>
              <h3 className="text-sm font-semibold text-strong">
                Đề thi đã được phê duyệt và khóa nội dung vĩnh viễn
              </h3>
              <p className="text-xs text-approved-ink">
                Mọi thao tác duyệt hoặc tạo lại biến thể đã bị khóa ở chế độ chỉ xem.
              </p>
            </div>
          </div>

        </div>
      )}

      {/* Cảnh báo trạng thái sinh một phần (partial_generated) */}
      {isPartial && (
        <div
          role="alert"
          className="stage3-session-notice rounded-xl border border-accent-border bg-accent-soft text-accent-ink"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-accent-ink" />
            <div>
              <h3 className="text-base font-bold text-strong">
                Đề thi còn thiếu câu hỏi
              </h3>
              <p className="mt-1 text-xs text-accent-ink leading-relaxed">
                Một số câu hỏi chưa được tạo thành công. Bạn có thể duyệt các câu đã có
                và sinh bù các câu còn thiếu trước khi xem trước toàn bộ đề.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Thông báo khi backend chưa nạp dữ liệu chi tiết câu hỏi */}
      {!hasLoadedAnyVariants && (
        <div className="stage3-session-notice rounded-xl border border-line bg-surface text-center text-ink">
          <Info className="mx-auto h-8 w-8 text-highlight" />
          <h3 className="mt-3 text-base font-semibold text-strong">
            Đang tải nội dung các mã đề
          </h3>
          <p className="mt-1 text-xs text-muted max-w-md mx-auto">
            {isPartial
              ? 'Đang tải các câu đã tạo. Vui lòng chờ trước khi sinh bù câu còn thiếu.'
              : 'Các mã đề đã được tạo. Đang tải nội dung từng câu hỏi.'}
          </p>
        </div>
      )}

      <section aria-label="Điều hướng mã đề và câu hỏi" className="stage3-controls">
        {/* Điều hướng nhanh theo từng câu của mã đề đang xem (theo mẫu SourceNavigator S06) */}
        {totalSourceQuestions > 0 && (
            <nav aria-label="Điều hướng câu hỏi" className="stage3-question-nav">
              {Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).map((qNo) => {
                const navVariant = findVariantInSession(session, activeVersionTab, qNo);
                const isNavMissing = !navVariant;
                const isNavApproved = isVariantApproved(navVariant, approvedVariantIds);
                const { isFallback: navFallback, hasWarning: navWarning } = getVariantWarningFlags(navVariant);
                const isNavSelected = currentQuestionNo === qNo;
                const isNavBusy = Boolean(navVariant && pendingActions.has(navVariant.candidate_id || navVariant.id || navVariant.question_id));

                const statusText = isNavMissing
                  ? 'Thiếu câu'
                  : isNavBusy
                  ? 'Đang xử lý'
                  : isNavApproved
                  ? 'Đã duyệt'
                  : navFallback || navWarning
                  ? 'Có cảnh báo'
                  : 'Chờ duyệt';

                const pillTone = isNavMissing
                  ? 'border-danger-border bg-danger-soft text-danger'
                  : isNavBusy
                  ? 'border-support-line bg-support-bg text-highlight'
                  : isNavApproved
                  ? 'border-approved-border bg-approved-bg text-approved-ink'
                  : navFallback || navWarning
                  ? 'border-accent-border bg-accent-soft text-accent-ink'
                  : 'border-line bg-rail text-ink hover:bg-support-bg';

                return (
                  <button
                    key={qNo}
                    type="button"
                    data-review-nav-q={qNo}
                    aria-current={isNavSelected ? 'true' : undefined}
                    aria-label={`Câu ${qNo}: ${statusText}`}
                    disabled={isRetryingAll}
                    onClick={() => handleSelectNavigatorQuestion(qNo)}
                    className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-semibold transition-all disabled:opacity-60 ${pillTone} ${
                      isNavSelected ? 'ring-2 ring-highlight ring-offset-1' : ''
                    }`}
                  >
                    {isNavBusy ? (
                      <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                    ) : isNavApproved ? (
                      <Check className="h-3 w-3" aria-hidden="true" />
                    ) : isNavMissing ? (
                      <AlertCircle className="h-3 w-3" aria-hidden="true" />
                    ) : navFallback || navWarning ? (
                      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                    ) : null}
                    <span>Câu {qNo}</span>
                  </button>
                );
              })}
            </nav>
        )}
      </section>

      <Stage3Comparison source={currentSource} questionNo={currentQuestionNo} versionIndex={activeVersionTab} tabs={<>
{Array.from({ length: numVersions }, (_, i) => i + 1).map((vIdx) => {
            const isTabActive = activeVersionTab === vIdx;
            return (
              <button
                key={vIdx}
                type="button"
                disabled={isRetryingAll}
                id={`stage3-version-${vIdx}`}
                data-review-version={vIdx}
                role="tab"
                aria-controls="stage3-variant-panel"
                tabIndex={isTabActive ? 0 : -1}
                onKeyDown={(event) => handleVersionKeyDown(event, vIdx)}
                onClick={() => selectVersion(vIdx)}
                aria-selected={isTabActive}

              >
                {versionLabel(session, vIdx)} · {Array.from({length: totalSourceQuestions}, (_, i) => i+1).filter(n => isVariantApproved(findVariantInSession(session,vIdx,n), approvedVariantIds)).length}/{totalSourceQuestions}
              </button>
            );
          })}
      </>}>
        {!currentQuestionNo && <div className="stage3-empty" role="status">Chưa có câu nguồn để đối chiếu.</div>}
        {[currentQuestionNo].filter(Boolean).map((qNo) => {
          const variant = selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab ? selectedSolution.variant : findVariantInSession(session, activeVersionTab, qNo);
          const isMissing = !variant;

          if (isMissing) {
            if (!hasLoadedAnyVariants) {
              return <p key={qNo} role="status">Đang tải nội dung biến thể để đối chiếu…</p>;
            }

            return (
              <div
                key={qNo}
                style={{scrollMarginTop: 24}}
                id={`review-${activeVersionTab}-${qNo}`}
                className="rounded-2xl border border-danger-border bg-danger-soft p-5 shadow-soft transition-all"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-danger-soft text-xs font-bold text-danger">
                      {qNo}
                    </span>
                    <div>
                      <h4 className="text-sm font-bold text-strong">
                        Câu {qNo} ({versionLabel(session, activeVersionTab)}) — Chưa được sinh thành công
                      </h4>
                      <p className="mt-0.5 text-xs text-muted">
                        Chưa có câu cho vị trí này. Hãy sử dụng nút &quot;Sinh bổ sung các câu còn thiếu&quot; để sinh tiếp.
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleRetryAllMissing}
                    disabled={isRetryingAll || !canRetryPartial}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-accent-border bg-accent-soft px-3.5 py-1.5 text-xs font-semibold text-strong hover:bg-accent disabled:opacity-50 transition-colors"
                  >
                    {isRetryingAll ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    <span>Sinh bổ sung các câu còn thiếu</span>

                  </button>
                </div>
              </div>
            );
          }

          // Hiển thị câu hỏi đã hoàn tất
          const isApproved = isVariantApproved(variant, approvedVariantIds);

          const { isFallback, hasWarning } = getVariantWarningFlags(variant);

          const warningMsg =
            variant.warning_message ||
            variant.validation_report?.warning ||
            variant.validation_report?.message ||
            'Câu hỏi có cảnh báo nghiệm hoặc ràng buộc cần lưu ý.';

          const busyAction = pendingActions.get(variant.candidate_id || variant.id || variant.question_id);
          const isCardBusy = Boolean(busyAction) || variant.status === 'regenerating';
          return (
            <div
              key={qNo}
              style={{scrollMarginTop: 24}} id={`review-${activeVersionTab}-${qNo}`}
              className="stage3-variant-card"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-support-bg text-xs font-bold text-highlight border border-support-line">
                    {qNo}
                  </span>
                  <span className="text-xs font-semibold text-strong">
                    Câu {qNo} ({versionLabel(session, activeVersionTab)})
                  </span>

                  {/* Badge trạng thái duyệt */}
                  {isCardBusy ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-[11px] font-medium text-highlight">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {busyAction === 'reject' || variant.status === 'regenerating' ? 'Đang tạo lại' : busyAction === 'revert' ? 'Đang khôi phục' : 'Đang duyệt'}
                    </span>
                  ) : isApproved ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-approved-border bg-approved-bg px-2.5 py-0.5 text-[11px] font-medium text-approved-ink">
                      <CheckCircle className="h-3 w-3" />
                      Đã duyệt
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-rail px-2.5 py-0.5 text-[11px] font-medium text-ink">
                      Chưa duyệt
                    </span>
                  )}

                  {/* Provenance badges */}
                  {variant.origin === 'original_clone' && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-[11px] font-medium text-highlight">
                      <Info className="h-3 w-3" />
                      Giữ nguyên từ đề gốc
                    </span>
                  )}
                  {(variant.is_reverted || variant.origin === 'reverted') && !isApproved && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-accent-border bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent-ink">
                      <RotateCcw className="h-3 w-3" />
                      Đã khôi phục đề gốc — cần duyệt lại
                    </span>
                  )}
                  {(variant.is_reverted || variant.origin === 'reverted') && isApproved && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-[11px] font-medium text-highlight">
                      <RotateCcw className="h-3 w-3" />
                      Đã khôi phục từ đề gốc
                    </span>
                  )}
                  {variant.origin === 'unknown' && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-rail px-2.5 py-0.5 text-[11px] font-medium text-muted">
                      Chưa xác định nguồn tạo câu
                    </span>
                  )}

                  {/* Badge phản ánh chất lượng thẩm định nếu chưa duyệt */}
                  {!isApproved && hasWarning && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-accent-border bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent-ink">
                      <AlertTriangle className="h-3 w-3" />
                      Cần thẩm định (Có cảnh báo)
                    </span>
                  )}

                </div>

              </div>

              {/* Badge Fallback */}
              {isFallback && variant.origin !== 'original_clone' && (
                <div className="mt-3 rounded-xl border border-accent-border bg-accent-soft p-2.5 text-xs text-accent-ink flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-accent-ink" />
                  <span className="font-semibold">
                    Không tạo được biến thể hợp lệ; đã dùng đề gốc đã xác nhận
                  </span>
                  <span className="sr-only"> (Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc)</span>
                </div>
              )}

              {/* Thông báo chi tiết cảnh báo nếu có và không phải fallback */}
              {!isFallback && hasWarning && (
                <div className="mt-3 rounded-xl border border-accent-border bg-accent-soft p-2.5 text-xs text-accent-ink flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-accent-ink mt-0.5" />
                  <span>{warningMsg}</span>
                </div>
              )}

              <ReviewQuestionContent question={variant} />
              <ReviewSolution question={variant} />
              {!isReviewReadOnly && <button type="button" data-review-inline-approve
                className="rounded-lg border border-accent-border bg-accent px-4 py-2"
                disabled={isApproved || reviewSyncRequired || isCardBusy || isRetryingAll || !currentVariant || !(
                    variant.candidate_id || variant.id || variant.question_id)}
                onClick={() => void mutate('accept', { variant, qNo, versionIndex: activeVersionTab })}>
                {isApproved ? 'Đã duyệt' : 'Duyệt biến thể'}
              </button>}



            </div>
          );
        })}
      </Stage3Comparison>

      {selectedSolution && <Stage3InspectionDialog
        key={`${sessionId}-${selectedSolution.versionIndex}-${selectedSolution.qNo}-${selectedSolution.variant.candidate_id || selectedSolution.variant.id}`}
        boundReasons={actionKeysRef.current.get(JSON.stringify(['reject', selectedSolution.variant.candidate_id ||
          selectedSolution.variant.id || selectedSolution.variant.question_id]))?.reasons}
        selection={selectedSolution} versionLabel={versionLabel(session, selectedSolution.versionIndex)}
        message={actionMessage} readOnly={isReviewReadOnly || reviewSyncRequired || selectedSolution.variant.status === 'regenerating'} approved={isSelectedVariantApproved}
        busy={pendingActions.has(selectedSolution.variant.candidate_id || selectedSolution.variant.id || selectedSolution.variant.question_id)}
        canRegenerate={selectedSolution.variant.result_kind !== 'ORIGINAL_CLONE'}
        rejectBusy={activeRecovery || [...pendingActions.values()].includes('reject')}
        canRevert={Boolean(session?.confirmation_id && session?.job_snapshot_id && (selectedSolution.variant.candidate_id || selectedSolution.variant.id || selectedSolution.variant.question_id))}
        onClose={() => setInspection(null)} onApprove={() => mutate('accept', selectedSolution)}
        onRegenerate={reasons => mutate('reject', selectedSolution, reasons)} onRevert={() => mutate('revert', selectedSolution)} onNext={goToNextUnreviewed}
      />}

      <div className="stage3-pair-actions">
        <button type="button" data-review-inspect={true}
          disabled={!currentVariant || isRetryingAll}
          aria-expanded={Boolean(inspectionOpen)}
          aria-controls={currentVariant ? `solution-${activeVersionTab}-${currentQuestionNo}` : undefined}
          onClick={() => inspectionOpen ? setInspection(null) : handleOpenSolutionModal(currentVariant, currentQuestionNo, activeVersionTab)}
          className="inline-flex items-center gap-2 rounded-lg border border-accent-border bg-accent px-4 py-2 text-sm font-semibold text-strong hover:opacity-90 disabled:opacity-50">
          <Eye className="h-4 w-4" aria-hidden="true" />
          {inspectionOpen ? 'Đóng đối chiếu' : 'Kiểm tra đáp án'}
          <span className="sr-only"> (Xem lời giải)</span>
        </button>
      </div>

      {/* Thanh trạng thái dưới cùng: Tiến độ duyệt & Nút Xem trước bộ đề (PREVIEW.html layout) */}
      <footer className="stage3-footer">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Link to="/dashboard" className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-highlight">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />Thư viện đề
            </Link>
            <button type="button" onClick={() => navigate(stage2Path(sessionId))}
              className="rounded-lg border border-line px-3 py-2 text-sm text-highlight">Xem thông tin lần sinh</button>
            <span className="stage3-review-progress">
              <span aria-hidden="true"
                className={`flex h-2.5 w-2.5 rounded-full ${
                  approvedCount === totalExpectedSlots && totalExpectedSlots > 0
                    ? 'bg-approved-ink'
                    : 'bg-accent'
                }`}
              />
              <span className="text-sm font-medium text-ink">
                Đã duyệt{' '}
                <strong className="font-bold text-strong">
                  {approvedCount}/{totalExpectedSlots}
                </strong>{' '}
                câu
              </span>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {canRetryPartial && (
              <button
                type="button"
                disabled={isRetryingAll}
                onClick={handleRetryAllMissing}
                className="inline-flex items-center gap-2 rounded-xl border border-accent-border bg-accent-soft px-4 py-2.5 text-xs font-semibold text-accent-ink hover:bg-accent hover:text-strong transition-all disabled:opacity-50"
              >
                {isRetryingAll ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Đang gửi yêu cầu sinh bổ sung…
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-3.5 w-3.5" />
                    <span>Sinh bổ sung các câu còn thiếu</span>
                    <span className="sr-only"> (Sinh bù tất cả câu thiếu)</span>
                  </>
                )}
              </button>
            )}
            {isFinalizeDisabled ? (
              <p className="text-xs sm:text-sm text-muted" role="status">
                {reviewSyncRequired ? 'Cần đọc lại trạng thái review.' : isReviewReadOnly ? 'Phiên đang chỉ xem hoặc đã khóa.' : totalExpectedSlots === 0 ? 'Chưa có đủ dữ liệu câu hỏi.' : isPartial ? 'Cần sinh đủ câu và duyệt tất cả câu hỏi.' : approvedCount === totalExpectedSlots ? 'Đang chờ phiên sẵn sàng xem trước.' : `Còn ${Math.max(0, totalExpectedSlots - approvedCount)} câu chưa duyệt.`}
              </p>
            ) : (
              <p className="text-xs font-semibold text-approved-ink" role="status">
                Đã duyệt đủ {approvedCount}/{totalExpectedSlots} câu — sẵn sàng xem trước.
              </p>
            )}
            <button
              type="button"
              data-review-finalize={true}
              disabled={isFinalizeDisabled}
              onClick={() => navigate(stage3PreviewPath(sessionId))}
              className="inline-flex items-center gap-2 rounded-lg border border-accent-border bg-accent px-6 py-2.5 text-sm font-semibold text-strong hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Rà bộ đề
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </footer>

    </main>
  </div>
);
}
