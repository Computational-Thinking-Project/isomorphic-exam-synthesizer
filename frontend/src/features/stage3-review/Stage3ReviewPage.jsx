import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { exportPath, stage2Path, stage3PreviewPath } from '../../sessionPaths.js';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle,
  CheckCircle2,
  ChevronLeft,
  Eye,
  GraduationCap,
  Info,
  Loader2,
  Lock,
  RefreshCw,
  RotateCcw,
} from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';
import { getSessionDetail } from '../../services/sessions.js';
import { retryGeneration } from '../../services/stage2Service.js';
import {
  acceptQuestion,
  rejectAndRegenerateQuestion,
  revertQuestion,
  fetchReviewSnapshot,
  adaptReviewSnapshot,
  normalizeOptions,
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
  const [isRetryingAll, setIsRetryingAll] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  // Trạng thái modal Kiểm tra đáp án (SolutionDialog)
  const [selectedSolution, setSelectedSolution] = useState(null);
  const [isRegeneratingSingle, setIsRegeneratingSingle] = useState(false);
  const [isApprovingSingle, setIsApprovingSingle] = useState(false);
  const [isRevertingSingle, setIsRevertingSingle] = useState(false);
  const [isShuffle409, setIsShuffle409] = useState(false);
  const [approvedVariantIds, setApprovedVariantIds] = useState(new Set());

  const loadOperationRef = useRef(0);
  const retryOperationRef = useRef(0);
  const mutationOperationRef = useRef(0);
  const isMountedRef = useRef(true);
  const activeSessionIdRef = useRef(sessionId);
  const navigationTimerRef = useRef(null);
  const actionKeysRef = useRef(new Map());

  const loadData = useCallback(async () => {
    if (!sessionId) {
      if (isMountedRef.current) {
        setIsLoading(false);
        setError('Không có mã phiên làm việc hợp lệ.');
      }
      return;
    }

    const currentOp = ++loadOperationRef.current;
    const targetSessionId = sessionId;

    setIsLoading(true);
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
      const data = adaptReviewSnapshot(rawData);
      setSession(data);
      setLockedDetail(null);

      const initialApproved = extractApprovedIds(data);
      setApprovedVariantIds(initialApproved);
      setIsLoading(false);
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

      setError(extractErrorString(err, 'Không thể tải chi tiết phiên làm việc.'));
      setIsLoading(false);
    }
  }, [sessionId, loadSession, loadSessionDetail]);

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
    setIsRetryingAll(false);
    setSelectedSolution(null);
    setApprovedVariantIds(new Set());
    setActionMessage(null);
    setIsRegeneratingSingle(false);
    setIsApprovingSingle(false);
    setIsRevertingSingle(false);
    actionKeysRef.current.clear();

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

  // Cập nhật variant trong session state
  const updateVariantInSession = useCallback((updatedVariant, targetVIdx, targetQNo) => {
    setSession((prev) => {
      if (!prev) return prev;
      const next = { ...prev };
      const qNoToMatch = targetQNo ?? updatedVariant.question_no ?? updatedVariant.number;

      const mergeVariantSlot = (oldQ, nextVar) => {
        const merged = { ...oldQ, ...nextVar };
        // Đảm bảo xóa sạch hoàn toàn attempts / warning_flag của câu cũ khi câu mới sinh thành công (không phải fallback)
        if (!nextVar.is_fallback) {
          merged.is_fallback = false;
          merged.source_fallback = false;
          merged.attempts = nextVar.attempts ?? 1;
          merged.warning_flag = nextVar.warning_flag || null;
        }
        return merged;
      };

      if (Array.isArray(next.version_questions)) {
        next.version_questions = next.version_questions.map((q) => {
          const matchesId =
            (q.id && updatedVariant.id && q.id === updatedVariant.id) ||
            (q.candidate_id && updatedVariant.candidate_id && q.candidate_id === updatedVariant.candidate_id) ||
            (q.id && updatedVariant.candidate_id && q.id === updatedVariant.candidate_id) ||
            (q.candidate_id && updatedVariant.id && q.candidate_id === updatedVariant.id);
          const qVIdx = q.version_index ?? q.version_code;
          const matchesSlot = targetVIdx && qVIdx === targetVIdx && (q.question_no ?? q.number) === qNoToMatch;
          return matchesId || matchesSlot ? mergeVariantSlot(q, updatedVariant) : q;
        });
      }

      if (Array.isArray(next.exam_versions)) {
        next.exam_versions = next.exam_versions.map((ver, idx) => {
          const currentVIdx = ver.version_index ?? ver.index ?? idx + 1;
          const questionsKey = ver.questions ? 'questions' : ver.version_questions ? 'version_questions' : 'questions';
          const qList = ver[questionsKey] || [];
          const updatedList = qList.map((q) => {
            const matchesId =
              (q.id && updatedVariant.id && q.id === updatedVariant.id) ||
              (q.candidate_id && updatedVariant.candidate_id && q.candidate_id === updatedVariant.candidate_id) ||
              (q.id && updatedVariant.candidate_id && q.id === updatedVariant.candidate_id) ||
              (q.candidate_id && updatedVariant.id && q.candidate_id === updatedVariant.id);
            const matchesSlot = targetVIdx && currentVIdx === targetVIdx && (q.question_no ?? q.number) === qNoToMatch;
            return matchesId || matchesSlot ? mergeVariantSlot(q, updatedVariant) : q;
          });
          return { ...ver, [questionsKey]: updatedList };
        });
      }

      return next;
    });
  }, []);

  // Xử lý mở modal Kiểm tra đáp án
  const handleOpenSolutionModal = useCallback((variant, qNo, versionIndex) => {
    const originalQuestion = session?.source_questions?.find(
      (sq) => (sq.source_question_id && sq.source_question_id === variant.source_question_id) || (sq.id && sq.id === variant.source_question_id)
    ) || session?.source_questions?.find(
      (sq) => (sq.question_no ?? sq.number) === qNo
    );
    setSelectedSolution({
      variant: {
        ...variant,
        options: normalizeOptions(variant.options),
      },
      qNo,
      versionIndex,
      originalQuestion: originalQuestion ? {
        ...originalQuestion,
        options: normalizeOptions(originalQuestion.options),
      } : null,
    });
  }, [session]);

  const isFinalLocked = ['approved', 'exported'].includes(session?.status);
  const isReviewReadOnly = isFinalLocked || Boolean(session?.read_only);
  const canRetryPartial = session?.status === 'partial_generated' && !isFinalLocked;

  // Xử lý Tạo lại câu hỏi trong SolutionDialog (Reject & Targeted Regeneration)
  const handleRegenerateSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isRegeneratingSingle || isReviewReadOnly) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.candidate_id || variant.id || variant.question_id;
    if (!targetQId) {
      setActionMessage({
        type: 'error',
        text: 'Thiếu định danh câu hỏi để thao tác. Hãy tải lại trang để đồng bộ dữ liệu.',
      });
      return;
    }

    const currentOp = ++mutationOperationRef.current;
    const targetSessionId = sessionId;

    // Giữ nguyên Idempotency-Key ổn định qua các lần retry cho đến khi thành công
    const actionLookupKey = `reject-${targetQId}`;
    let idempotencyKey = actionKeysRef.current.get(actionLookupKey);
    if (!idempotencyKey) {
      idempotencyKey = generateClientUUID();
      actionKeysRef.current.set(actionLookupKey, idempotencyKey);
    }

    setIsRegeneratingSingle(true);
    setActionMessage(null);

    try {
      const res = await regenerateQuestionFn(sessionId, targetQId, idempotencyKey);

      // Chặn stale response nếu người dùng chuyển session hoặc operation token không còn khớp
      if (
        !isMountedRef.current ||
        mutationOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }

      // Xóa action key sau khi gọi thành công
      actionKeysRef.current.delete(actionLookupKey);
      actionKeysRef.current.delete(`accept-${targetQId}`);

      const newOptions = normalizeOptions(res?.options || variant.options);
      // Tạo object mới sạch từ response; không kế thừa cờ fallback/warning từ candidate cũ
      const newCandidateId = res?.candidate_id || res?.question_id || res?.id || variant.candidate_id || variant.id;
      const updatedVariant = {
        id: newCandidateId,
        candidate_id: newCandidateId,
        question_id: newCandidateId,
        source_question_id: variant.source_question_id,
        question_no: variant.question_no ?? qNo,
        number: variant.number ?? qNo,
        version_index: versionIndex,
        status: res?.status || 'pending_review',
        content: res?.content || res?.stem_latex || res?.stem || variant.content,
        options: newOptions,
        correct_key: res?.correct_key || variant.correct_key,
        solution_md: res?.solution_md ?? res?.solution ?? '',
        is_fallback: Boolean(res?.is_fallback),
        source_fallback: Boolean(res?.source_fallback),
        has_warning: Boolean(res?.has_warning),
        warning_message: res?.warning_message || null,
        validation_report: res?.validation_report || null,
        attempts: res?.attempts ?? (res?.is_fallback ? (variant.attempts ?? 4) : 1),
        warning_flag: res?.warning_flag || (res?.is_fallback ? 'fallback' : null),
      };

      // Cập nhật session và giữ nguyên modal mở với nội dung câu mới
      updateVariantInSession(updatedVariant, versionIndex, qNo);
      setSelectedSolution((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          variant: updatedVariant,
        };
      });

      // Bỏ duyệt khỏi danh sách duyệt
      setApprovedVariantIds((prev) => {
        const next = new Set(prev);
        if (variant.id) next.delete(variant.id);
        if (variant.candidate_id) next.delete(variant.candidate_id);
        if (updatedVariant.id) next.delete(updatedVariant.id);
        if (updatedVariant.candidate_id) next.delete(updatedVariant.candidate_id);
        return next;
      });

      setActionMessage({
        type: 'success',
        text: `Đã tạo lại câu ${qNo} (đề ${versionIndex}). Kiểm tra đáp án và duyệt phiên bản mới.`,
      });

      // Refetch current snapshot sau regenerate để cập nhật candidate thay thế và persisted progress
      try {
        const latestRaw = await loadSession(targetSessionId);
        if (
          isMountedRef.current &&
          mutationOperationRef.current === currentOp &&
          activeSessionIdRef.current === targetSessionId &&
          latestRaw
        ) {
          const adapted = adaptReviewSnapshot(latestRaw);
          const snapshotVariant = findVariantInSession(adapted, versionIndex, qNo);

          // Nếu snapshot trả về vẫn mang ID câu cũ bị từ chối (do mock tĩnh hoặc DB replication lag),
          // ưu tiên giữ lại updatedVariant mới sinh thay vì bị rollback về câu cũ
          const isStaleRejected =
            snapshotVariant &&
            (snapshotVariant.id === variant.id ||
              (variant.candidate_id && snapshotVariant.candidate_id === variant.candidate_id));

          if (isStaleRejected) {
            adapted.exam_versions = (adapted.exam_versions || []).map((ver) => {
              if ((ver.version_index ?? 1) === versionIndex) {
                const qList = (ver.questions || []).map((q) => {
                  if ((q.question_no ?? q.number) === qNo) {
                    return updatedVariant;
                  }
                  return q;
                });
                return { ...ver, questions: qList };
              }
              return ver;
            });
          }

          setSession(adapted);
          const replacement = findVariantInSession(adapted, versionIndex, qNo) || updatedVariant;
          if (replacement) {
            setSelectedSolution((prev) => (prev ? { ...prev, variant: replacement } : null));
          }
          const authoritativeApproved = extractApprovedIds(adapted);
          setApprovedVariantIds((prev) => {
            const next = new Set(prev);
            if (variant.id) next.delete(variant.id);
            if (variant.candidate_id) next.delete(variant.candidate_id);
            if (replacement?.id) next.delete(replacement.id);
            if (replacement?.candidate_id) next.delete(replacement.candidate_id);
            authoritativeApproved.forEach((id) => {
              if (
                id !== variant.id &&
                id !== variant.candidate_id &&
                (!replacement || (id !== replacement.id && id !== replacement.candidate_id))
              ) {
                next.add(id);
              }
            });
            return next;
          });
        }
      } catch {
        // Refetch thất bại trong nền không làm hỏng dữ liệu hiển thị từ regenerateQuestionFn
      }
    } catch (err) {
      if (
        !isMountedRef.current ||
        mutationOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setActionMessage({
        type: 'error',
        text: extractErrorString(err, 'Không thể tạo lại câu hỏi.'),
      });
    } finally {
      if (
        isMountedRef.current &&
        mutationOperationRef.current === currentOp &&
        activeSessionIdRef.current === targetSessionId
      ) {
        setIsRegeneratingSingle(false);
      }
    }
  }, [selectedSolution, isRegeneratingSingle, isReviewReadOnly, regenerateQuestionFn, sessionId, updateVariantInSession, loadSession]);

  // Xử lý Duyệt biến thể trong SolutionDialog
  const handleApproveSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isApprovingSingle || isReviewReadOnly) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.candidate_id || variant.id || variant.question_id;
    if (!targetQId) {
      setActionMessage({
        type: 'error',
        text: 'Thiếu định danh câu hỏi để thao tác. Hãy tải lại trang để đồng bộ dữ liệu.',
      });
      return;
    }

    const currentOp = ++mutationOperationRef.current;
    const targetSessionId = sessionId;

    // Giữ nguyên Idempotency-Key ổn định qua các lần retry
    const actionLookupKey = `accept-${targetQId}`;
    let idempotencyKey = actionKeysRef.current.get(actionLookupKey);
    if (!idempotencyKey) {
      idempotencyKey = generateClientUUID();
      actionKeysRef.current.set(actionLookupKey, idempotencyKey);
    }

    setIsApprovingSingle(true);
    setActionMessage(null);

    try {
      await acceptQuestionFn(sessionId, targetQId, idempotencyKey);

      // Chặn stale response nếu người dùng chuyển session hoặc operation token không còn khớp
      if (
        !isMountedRef.current ||
        mutationOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }

      actionKeysRef.current.delete(actionLookupKey);

      const updatedVariant = {
        ...variant,
        status: 'approved',
      };

      updateVariantInSession(updatedVariant, versionIndex, qNo);
      setSelectedSolution((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          variant: updatedVariant,
        };
      });

      setApprovedVariantIds((prev) => {
        const next = new Set(prev);
        if (variant.id) next.add(variant.id);
        if (variant.candidate_id) next.add(variant.candidate_id);
        if (variant.question_id) next.add(variant.question_id);
        return next;
      });

      setActionMessage({
        type: 'success',
        text: `Đã duyệt câu ${qNo} · Đề ${versionIndex}.`,
      });

      // Refetch current snapshot sau accept để cập nhật persisted review progress và freshness token
      try {
        const latestRaw = await loadSession(targetSessionId);
        if (
          isMountedRef.current &&
          mutationOperationRef.current === currentOp &&
          activeSessionIdRef.current === targetSessionId &&
          latestRaw
        ) {
          const adapted = adaptReviewSnapshot(latestRaw);
          const targetCandidateId = variant.candidate_id || variant.id || variant.question_id;

          // Chỉ áp dụng optimistic approved nếu candidate tại slot vẫn đúng là candidate vừa được duyệt (Issue #85)
          adapted.exam_versions = (adapted.exam_versions || []).map((ver) => {
            if ((ver.version_index ?? 1) === versionIndex) {
              const qList = (ver.questions || []).map((q) => {
                if ((q.question_no ?? q.number) === qNo) {
                  const currentCandidateId = q.candidate_id || q.id || q.question_id;
                  if (targetCandidateId && currentCandidateId === targetCandidateId) {
                    return { ...q, status: 'approved' };
                  }
                }
                return q;
              });
              return { ...ver, questions: qList };
            }
            return ver;
          });
          setSession(adapted);

          // Cập nhật selectedSolution nếu đang mở đúng slot này
          setSelectedSolution((prev) => {
            if (!prev) return null;
            if (prev.versionIndex === versionIndex && prev.qNo === qNo) {
              const latestVariant = findVariantInSession(adapted, versionIndex, qNo);
              if (latestVariant) {
                return { ...prev, variant: latestVariant };
              }
            }
            return prev;
          });

          const authoritativeApproved = extractApprovedIds(adapted);
          setApprovedVariantIds((prev) => {
            const merged = new Set(prev);
            authoritativeApproved.forEach((id) => merged.add(id));
            if (variant.id) merged.add(variant.id);
            if (variant.candidate_id) merged.add(variant.candidate_id);
            if (variant.question_id) merged.add(variant.question_id);
            return merged;
          });
        }
      } catch {
        // Refetch thất bại trong nền không làm hỏng optimistic update đã hiển thị cho người dùng
      }
    } catch (err) {
      if (
        !isMountedRef.current ||
        mutationOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setActionMessage({
        type: 'error',
        text: extractErrorString(err, 'Không thể duyệt câu hỏi.'),
      });
    } finally {
      if (
        isMountedRef.current &&
        mutationOperationRef.current === currentOp &&
        activeSessionIdRef.current === targetSessionId
      ) {
        setIsApprovingSingle(false);
      }
    }
  }, [selectedSolution, isApprovingSingle, isReviewReadOnly, acceptQuestionFn, sessionId, updateVariantInSession, loadSession]);

  // Xử lý Khôi phục đề gốc (Revert candidate)
  const handleRevertSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isRevertingSingle || isReviewReadOnly) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.candidate_id || variant.id || variant.question_id;
    if (!targetQId) {
      setActionMessage({
        type: 'error',
        text: 'Thiếu định danh câu hỏi để thao tác. Hãy tải lại trang để đồng bộ dữ liệu.',
      });
      return;
    }

    if (!window.confirm(`Thay biến thể này (Câu ${qNo} · Đề ${versionIndex}) bằng đề gốc đã xác nhận. Câu sẽ cần được duyệt lại. Tiếp tục?`)) {
      return;
    }

    const currentOp = ++mutationOperationRef.current;
    const targetSessionId = sessionId;

    const actionLookupKey = `revert-${targetQId}`;
    let idempotencyKey = actionKeysRef.current.get(actionLookupKey);
    if (!idempotencyKey) {
      idempotencyKey = generateClientUUID();
      actionKeysRef.current.set(actionLookupKey, idempotencyKey);
    }

    setIsRevertingSingle(true);
    setActionMessage(null);

    try {
      const res = await revertQuestionFn(sessionId, targetQId, idempotencyKey);

      if (
        !isMountedRef.current ||
        mutationOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }

      actionKeysRef.current.delete(actionLookupKey);
      actionKeysRef.current.delete(`accept-${targetQId}`);
      actionKeysRef.current.delete(`reject-${targetQId}`);

      const originalQuestion = session?.source_questions?.find(
        (sq) => (sq.source_question_id && sq.source_question_id === variant.source_question_id) || (sq.id && sq.id === variant.source_question_id)
      ) || session?.source_questions?.find(
        (sq) => (sq.question_no ?? sq.number) === qNo
      );

      const newOptions = normalizeOptions(res?.options || originalQuestion?.options || variant.options);
      const newCandidateId = res?.candidate_id || res?.question_id || res?.id || targetQId;
      const updatedVariant = {
        ...variant,
        ...(res || {}),
        id: newCandidateId,
        candidate_id: newCandidateId,
        question_id: newCandidateId,
        source_question_id: variant.source_question_id,
        question_no: variant.question_no ?? qNo,
        number: variant.number ?? qNo,
        version_index: versionIndex,
        status: 'pending_review',
        content: res?.content || originalQuestion?.raw_content || originalQuestion?.content || variant.content,
        options: newOptions,
        correct_key: res?.correct_key || originalQuestion?.correct_key || variant.correct_key,
        solution_md: res?.solution_md !== undefined ? res.solution_md : (originalQuestion?.solution_md || ''),
        is_reverted: true,
        origin: 'reverted',
        is_fallback: false,
        source_fallback: false,
        has_warning: false,
        warning_message: null,
      };

      updateVariantInSession(updatedVariant, versionIndex, qNo);
      setSelectedSolution((prev) => (prev ? { ...prev, variant: updatedVariant } : null));

      setApprovedVariantIds((prev) => {
        const next = new Set(prev);
        if (variant.id) next.delete(variant.id);
        if (variant.candidate_id) next.delete(variant.candidate_id);
        if (updatedVariant.id) next.delete(updatedVariant.id);
        if (updatedVariant.candidate_id) next.delete(updatedVariant.candidate_id);
        return next;
      });

      setActionMessage({
        type: 'success',
        text: `Đã khôi phục đề gốc cho câu ${qNo} (Đề ${versionIndex}). Câu sẽ cần được duyệt lại.`,
      });

      try {
        const latestRaw = await loadSession(targetSessionId);
        if (
          isMountedRef.current &&
          mutationOperationRef.current === currentOp &&
          activeSessionIdRef.current === targetSessionId &&
          latestRaw
        ) {
          const adapted = adaptReviewSnapshot(latestRaw);
          const snapshotVariant = findVariantInSession(adapted, versionIndex, qNo);
          const isStale = snapshotVariant && !snapshotVariant.is_reverted;
          if (isStale) {
            adapted.exam_versions = (adapted.exam_versions || []).map((ver) => {
              if ((ver.version_index ?? 1) === versionIndex) {
                const qList = (ver.questions || []).map((q) => {
                  if ((q.question_no ?? q.number) === qNo) {
                    return updatedVariant;
                  }
                  return q;
                });
                return { ...ver, questions: qList };
              }
              return ver;
            });
          }
          setSession(adapted);
          const replacement = findVariantInSession(adapted, versionIndex, qNo) || updatedVariant;
          if (replacement) {
            setSelectedSolution((prev) => (prev ? { ...prev, variant: replacement } : null));
          }
        }
      } catch {
        // refetch fail silently
      }
    } catch (err) {
      if (
        !isMountedRef.current ||
        mutationOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setActionMessage({
        type: 'error',
        text: extractErrorString(err, 'Không thể khôi phục câu hỏi về đề gốc.'),
      });
    } finally {
      if (
        isMountedRef.current &&
        mutationOperationRef.current === currentOp &&
        activeSessionIdRef.current === targetSessionId
      ) {
        setIsRevertingSingle(false);
      }
    }
  }, [selectedSolution, isRevertingSingle, isReviewReadOnly, revertQuestionFn, sessionId, session, updateVariantInSession, loadSession]);

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

  const [reviewFilter, setReviewFilter] = useState('all');
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

  const goToNextUnreviewed = () => {
    const start = selectedSolution ? (selectedSolution.versionIndex - 1) * totalSourceQuestions + selectedSolution.qNo : 0;
    for (let offset = 0; offset < totalExpectedSlots; offset++) {
      const position = (start + offset) % totalExpectedSlots;
      const version = Math.floor(position / totalSourceQuestions) + 1;
      const number = position % totalSourceQuestions + 1;
      const candidate = findVariantInSession(session, version, number);
      if (candidate && !isVariantApproved(candidate, approvedVariantIds)) {
        setReviewFilter('all');
        setActiveVersionTab(version);
        handleOpenSolutionModal(candidate, number, version);
        setTimeout(() => document.getElementById(`review-${version}-${number}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 0);
        return;
      }
    }
    setActionMessage({type: 'success', text: 'Không còn câu chưa duyệt.'});
  };

  const handleSelectNavigatorQuestion = useCallback((qNo) => {
    if (isApprovingSingle || isRegeneratingSingle || isRevertingSingle) return;
    const variant = findVariantInSession(session, activeVersionTab, qNo);
    const isApproved = isVariantApproved(variant, approvedVariantIds);
    const { isFallback, hasWarning } = getVariantWarningFlags(variant);
    const matchesCurrentFilter =
      reviewFilter === 'all' ||
      (!variant && reviewFilter === 'pending') ||
      (variant && (
        (reviewFilter === 'pending' && !isApproved) ||
        (reviewFilter === 'approved' && isApproved) ||
        (reviewFilter === 'warning' && (hasWarning || isFallback))
      ));
    if (!matchesCurrentFilter) {
      setReviewFilter('all');
    }
    if (variant) {
      handleOpenSolutionModal(variant, qNo, activeVersionTab);
    } else {
      setSelectedSolution(null);
    }
    setTimeout(() => {
      if (isMountedRef.current && typeof document !== 'undefined' && typeof document.getElementById === 'function') {
        document.getElementById(`review-${activeVersionTab}-${qNo}`)?.scrollIntoView?.({
          block: 'nearest',
          behavior: 'smooth',
        });
      }
    }, 0);
  }, [session, activeVersionTab, approvedVariantIds, reviewFilter, isApprovingSingle, isRegeneratingSingle, isRevertingSingle, handleOpenSolutionModal]);

  const restoredViewRef = useRef(null);
  useEffect(() => {
    if (!session || session.id !== sessionId || restoredViewRef.current === sessionId) return;
    restoredViewRef.current = sessionId;
    try {
      const saved = JSON.parse(sessionStorage.getItem(`review-view:${sessionId}`) || 'null');
      if (!saved) return;
      const version = Math.min(numVersions, Math.max(1, saved.version || 1));
      setActiveVersionTab(version);
      setReviewFilter(['all','pending','warning','approved'].includes(saved.filter) ? saved.filter : 'all');
      const candidate = findVariantInSession(session, version, saved.question);
      if (candidate) handleOpenSolutionModal(candidate, saved.question, version);
      requestAnimationFrame(() => window.scrollTo(0, saved.scroll || 0));
    } catch { /* View restoration is optional; server data remains authoritative. */ }
  }, [session, sessionId, numVersions, handleOpenSolutionModal]);
  useEffect(() => {
    if (restoredViewRef.current !== sessionId) return;
    const save = () => {
      try { sessionStorage.setItem(`review-view:${sessionId}`, JSON.stringify({version: activeVersionTab, filter: reviewFilter, question: selectedSolution?.qNo, scroll: window.scrollY})); }
      catch { /* Storage may be unavailable. */ }
    };
    window.addEventListener('scroll', save, {passive:true});
    return () => { save(); window.removeEventListener('scroll', save); };
  }, [sessionId, activeVersionTab, reviewFilter, selectedSolution?.qNo]);

  const isFinalizeDisabled =
    totalExpectedSlots === 0 || approvedCount < totalExpectedSlots || isPartial || isReviewReadOnly || isApprovingSingle || isRegeneratingSingle || isRetryingAll;

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

  const isAllApproved = totalExpectedSlots > 0 && approvedCount >= totalExpectedSlots && !isPartial;
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
    <div className="paper-ui min-h-screen bg-canvas text-ink">
      <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-6 lg:p-8">
      {/* Top Session Bar & Step Badge (đồng bộ PR #100 + ui-walkthrough S06) */}
      <header className="space-y-3 border-b border-line pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Link
              to="/dashboard"
              className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-highlight hover:bg-support-bg transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Thư viện đề</span>
            </Link>
            <span className="text-line" aria-hidden="true">/</span>
            <button
              type="button"
              onClick={() => navigate(stage2Path(sessionId))}
              className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-muted hover:bg-rail hover:text-ink transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Xem thông tin lần sinh</span>
            </button>
            <span className="text-line" aria-hidden="true">/</span>
            <span className="inline-flex shrink-0 items-center rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-xs font-semibold text-highlight">
              Bước 3/3 · Duyệt câu hỏi
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${headerBadge.className}`}>
              {headerBadge.label}
            </span>
            {isFinalLocked ? (
              <button
                type="button"
                data-testid="stage3-btn-goto-export"
                onClick={() => navigate(exportPath(sessionId))}
                className="inline-flex items-center gap-1.5 rounded-xl bg-approved-ink px-4 py-2 text-xs font-semibold text-white shadow-soft hover:bg-approved-ink transition-colors"
              >
                <Lock className="h-3.5 w-3.5" />
                Tới màn hình Xuất bản
              </button>
            ) : canRetryPartial && hasLoadedAnyVariants && totalLoadedVariants < totalExpectedSlots ? (
              <button
                type="button"
                onClick={handleRetryAllMissing}
                disabled={isRetryingAll}
                className="inline-flex items-center gap-1.5 rounded-xl border border-accent-border bg-accent px-3.5 py-2 text-xs font-semibold text-strong shadow-soft hover:opacity-90 disabled:opacity-50 transition-colors"
              >
                {isRetryingAll ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Sinh bù tất cả câu thiếu
              </button>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="break-words text-xl sm:text-2xl font-bold tracking-tight text-strong">
              {session?.title || 'Xem & Duyệt Đề Thi Đẳng Cấu'}
            </h1>
            <p className="mt-1 text-xs text-muted">
              Đối chiếu từng cặp đề gốc và biến thể theo mã đề trước khi chuyển sang bước xem trước bản cuối.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 font-medium text-highlight">
              <BookOpen className="h-3 w-3" aria-hidden="true" />
              Môn: {session?.subject || 'Toán'}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 font-medium text-highlight">
              <GraduationCap className="h-3 w-3" aria-hidden="true" />
              Khối {session?.grade || 12}
            </span>
            <span className="inline-flex items-center rounded-full border border-line bg-surface px-2.5 py-0.5 font-medium text-ink">
              {numVersions} mã đề · {totalSourceQuestions} câu/mã
            </span>
          </div>
        </div>
      </header>

      {/* Thông báo thao tác */}
      {actionMessage && (
        <div
          role="status"
          className={`rounded-xl border p-4 text-xs font-medium ${
            actionMessage.type === 'success'
              ? 'border-approved-border bg-approved-bg text-approved-ink'
              : 'border-danger-border bg-danger-soft text-danger'
          }`}
        >
          {actionMessage.text}
        </div>
      )}

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
          className="rounded-2xl border border-accent-border bg-accent-soft p-6 text-accent-ink shadow-paper"
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
        <div className="rounded-2xl border border-line bg-surface p-8 text-center text-ink">
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

      {/* Khối điều khiển: Chọn mã đề, Điều hướng câu (S06), và Bộ lọc trạng thái */}
      <section aria-label="Điều hướng mã đề và câu hỏi" className="rounded-2xl border border-line bg-surface p-4 shadow-soft space-y-3">
        {/* Thanh chọn Tab mã đề */}
        <div className="flex items-center gap-2 overflow-x-auto border-b border-line pb-3">
          {Array.from({ length: numVersions }, (_, i) => i + 1).map((vIdx) => {
            const isTabActive = activeVersionTab === vIdx;
            return (
              <button
                key={vIdx}
                type="button"
                disabled={isApprovingSingle || isRegeneratingSingle || isRevertingSingle}
                onClick={() => {setActiveVersionTab(vIdx);setSelectedSolution(null);}}
                aria-pressed={isTabActive}
                className={`shrink-0 whitespace-nowrap rounded-xl px-4 py-2 text-xs font-semibold transition-all ${
                  isTabActive
                    ? 'bg-highlight text-white shadow-soft'
                    : 'border border-line bg-rail text-ink hover:bg-support-bg hover:text-highlight'
                }`}
              >
                {versionLabel(session, vIdx)} · {Array.from({length: totalSourceQuestions}, (_, i) => i+1).filter(n => isVariantApproved(findVariantInSession(session,vIdx,n), approvedVariantIds)).length}/{totalSourceQuestions}
              </button>
            );
          })}
        </div>

        {/* Điều hướng nhanh theo từng câu của mã đề đang xem (theo mẫu SourceNavigator S06) */}
        {totalSourceQuestions > 0 && (
          <div className="space-y-2 border-b border-line pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-strong">
                Điều hướng nhanh theo câu ({versionLabel(session, activeVersionTab)})
              </span>
              <span className="text-[11px] text-muted">
                Xanh lá: Đã duyệt · Vàng: Cảnh báo · Đỏ: Thiếu câu · Xám: Chờ duyệt
              </span>
            </div>
            <nav aria-label="Điều hướng câu hỏi" className="flex flex-wrap gap-1.5">
              {Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).map((qNo) => {
                const navVariant = findVariantInSession(session, activeVersionTab, qNo);
                const isNavMissing = !navVariant;
                const isNavApproved = isVariantApproved(navVariant, approvedVariantIds);
                const { isFallback: navFallback, hasWarning: navWarning } = getVariantWarningFlags(navVariant);
                const isNavSelected = selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab;
                const isNavBusy = isNavSelected && (isRegeneratingSingle || isApprovingSingle || isRevertingSingle);

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
                    disabled={isApprovingSingle || isRegeneratingSingle || isRevertingSingle}
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
          </div>
        )}

        <div role="group" aria-label="Lọc câu hỏi" className="flex flex-wrap gap-2">
          {[['all','Tất cả'],['pending','Chưa duyệt'],['warning','Có cảnh báo'],['approved','Đã duyệt']].map(([value,label]) => {
            const count = Array.from({length:totalSourceQuestions},(_,i)=>findVariantInSession(session,activeVersionTab,i+1)).filter((v)=>{
              const { hasWarning, isFallback } = getVariantWarningFlags(v);
              const approved = isVariantApproved(v, approvedVariantIds);
              return value === 'all' || (value === 'pending' && !approved) || (value === 'approved' && approved) || (value === 'warning' && (hasWarning || isFallback));
            }).length;
            return (
              <button
                type="button"
                key={value}
                aria-pressed={reviewFilter===value}
                disabled={isApprovingSingle || isRegeneratingSingle || isRevertingSingle}
                onClick={()=>{setReviewFilter(value);setSelectedSolution(null);}}
                className="rounded-xl border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink transition-colors hover:bg-rail aria-pressed:border-support-line aria-pressed:bg-support-bg aria-pressed:text-highlight"
              >
                {label} ({count})
              </button>
            );
          })}
        </div>
      </section>

      {/* Thông báo bộ lọc rỗng */}
      {(() => {
        const visibleQuestions = Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).filter((qNo) => {
          const variant = findVariantInSession(session, activeVersionTab, qNo);
          const isMissing = !variant;
          if (isMissing) {
            return reviewFilter === 'all' || reviewFilter === 'pending';
          }
          const isApproved = isVariantApproved(variant, approvedVariantIds);
          const { isFallback, hasWarning } = getVariantWarningFlags(variant);
          return (
            reviewFilter === 'all' ||
            (reviewFilter === 'pending' && !isApproved) ||
            (reviewFilter === 'approved' && isApproved) ||
            (reviewFilter === 'warning' && (hasWarning || isFallback))
          );
        });

        if (visibleQuestions.length === 0 && reviewFilter !== 'all') {
          const filterName =
            reviewFilter === 'pending'
              ? 'chưa duyệt'
              : reviewFilter === 'warning'
              ? 'có cảnh báo'
              : 'đã duyệt';
          return (
            <div className="rounded-2xl border border-line bg-surface p-8 text-center">
              <p className="text-sm text-muted">
                Không có câu hỏi nào trong mục {filterName}.
              </p>
              <button
                type="button"
                onClick={() => setReviewFilter('all')}
                className="mt-3 inline-flex items-center gap-1.5 rounded-xl border border-line bg-rail px-4 py-2 text-xs font-semibold text-strong hover:bg-support-bg"
              >
                Xem tất cả
              </button>
            </div>
          );
        }
        return null;
      })()}
      {/* Danh sách các câu hỏi trong mã đề được chọn */}
      <div className="space-y-4">
        {Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).map((qNo) => {
          const variant = selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab ? selectedSolution.variant : findVariantInSession(session, activeVersionTab, qNo);
          const isMissing = !variant;

          if (isMissing) {
            if (['approved', 'warning'].includes(reviewFilter)) return null;
            if (!hasLoadedAnyVariants) {
              return null;
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
                    <span className="sr-only"> (Sinh bù câu này)</span>
                  </button>
                </div>
              </div>
            );
          }

          // Hiển thị câu hỏi đã hoàn tất
          const options = normalizeOptions(variant.options);
          const correctKey = variant.correct_key || variant.answer;
          const isApproved = isVariantApproved(variant, approvedVariantIds);

          const { isFallback, hasWarning } = getVariantWarningFlags(variant);

          const warningMsg =
            variant.warning_message ||
            variant.validation_report?.warning ||
            variant.validation_report?.message ||
            'Câu hỏi có cảnh báo nghiệm hoặc ràng buộc cần lưu ý.';

          const pinned = selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab;
          const isCardBusy = pinned && (isRegeneratingSingle || isApprovingSingle || isRevertingSingle);
          if (!pinned && ((reviewFilter === 'pending' && isApproved) || (reviewFilter === 'approved' && !isApproved) || (reviewFilter === 'warning' && !hasWarning && !isFallback))) return null;
          return (
            <div
              key={qNo}
              style={{scrollMarginTop: 24}} id={`review-${activeVersionTab}-${qNo}`}
              className={`rounded-2xl border p-5 shadow-soft transition-all ${
                pinned
                  ? 'border-highlight bg-surface ring-2 ring-highlight/20'
                  : isApproved
                  ? 'border-approved-border bg-surface'
                  : hasWarning
                  ? 'border-accent-border bg-surface'
                  : 'border-line bg-surface'
              }`}
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
                      {isRegeneratingSingle ? 'Đang tạo lại' : isRevertingSingle ? 'Đang khôi phục' : 'Đang duyệt'}
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

                {/* Nút Kiểm tra đáp án (Mở vùng đối chiếu S06) */}
                <button
                  type="button"
                  data-review-inspect={true}
                  disabled={isRegeneratingSingle || isApprovingSingle || isRevertingSingle}
                  aria-expanded={pinned}
                  aria-controls={`solution-${activeVersionTab}-${qNo}`}
                  onClick={() => pinned ? setSelectedSolution(null) : handleOpenSolutionModal(variant, qNo, activeVersionTab)}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all shadow-sm ${
                    pinned
                      ? 'border-highlight bg-highlight text-white hover:bg-[#253b57]'
                      : 'border-support-line bg-support-bg text-highlight hover:bg-highlight hover:text-white'
                  }`}
                >
                  <Eye className="h-3.5 w-3.5" />
                  <span>{pinned ? 'Đóng đối chiếu' : 'Đối chiếu và duyệt'}</span>
                  <span className="sr-only"> (Xem lời giải)</span>
                </button>
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

              {/* Nội dung đề bài */}
              <div className="mt-3 text-sm text-ink">
                <MathRenderer content={variant.content || variant.raw_content || ''} />
              </div>

              {/* Các lựa chọn đáp án */}
              {Object.keys(options).length > 0 && (
                <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(options).map(([key, optVal]) => {
                    const isCorrect =
                      String(key).toUpperCase() === String(correctKey).toUpperCase();
                    return (
                      <div
                        key={key}
                        className={`flex items-start gap-2 rounded-xl border p-2.5 text-xs ${
                          isCorrect
                            ? 'border-approved-border bg-approved-bg text-approved-ink'
                            : 'border-line bg-rail text-ink'
                        }`}
                      >
                        <span
                          className={`font-bold ${
                            isCorrect ? 'text-approved-ink' : 'text-muted'
                          }`}
                        >
                          {key}.
                        </span>
                        <div className="flex-1 min-w-0 overflow-x-auto">
                          <MathRenderer content={String(optVal)} inline />
                        </div>
                        {isCorrect && (
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-approved-ink" />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}


              {selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab && (
                <div id={`solution-${activeVersionTab}-${qNo}`} role="region" aria-label="Lời giải và thao tác duyệt" className="solution-dialog mt-4 space-y-4 border-t border-line pt-4">
                  {actionMessage && (
                    <p
                      role="status"
                      className={`rounded-xl border px-3.5 py-2.5 text-xs font-medium ${
                        actionMessage.type === 'success'
                          ? 'border-approved-border bg-approved-bg text-approved-ink'
                          : 'border-danger-border bg-danger-soft text-danger'
                      }`}
                    >
                      {actionMessage.text}
                    </p>
                  )}

                  <div className="solution-columns grid grid-cols-1 xl:grid-cols-2 gap-4">
                    {/* Cột 1: Đề gốc đối chiếu */}
                    {selectedSolution.originalQuestion ? (
                      <section className="rounded-xl border border-line bg-canvas p-4 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
                          <div className="flex items-center gap-2">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
                              Đề gốc (Câu {selectedSolution.originalQuestion.question_no ?? selectedSolution.originalQuestion.number ?? qNo})
                            </h3>
                            <span className="rounded-full border border-line bg-surface px-2 py-0.5 text-[10px] font-semibold text-muted">
                              Chỉ đọc
                            </span>
                          </div>
                          <span className="text-xs font-semibold text-highlight">
                            Đáp án đúng: {selectedSolution.originalQuestion.correct_key || selectedSolution.originalQuestion.answer || '—'}
                          </span>
                        </div>
                        <div className="text-xs text-ink leading-relaxed min-w-0 overflow-x-auto">
                          <MathRenderer content={selectedSolution.originalQuestion.raw_content || selectedSolution.originalQuestion.content || ''} />
                        </div>
                        {selectedSolution.originalQuestion.options && Object.keys(selectedSolution.originalQuestion.options).length > 0 && (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-1">
                            {Object.entries(selectedSolution.originalQuestion.options).map(([k, v]) => {
                              const isOrigCorrect = String(k).toUpperCase() === String(selectedSolution.originalQuestion.correct_key || selectedSolution.originalQuestion.answer).toUpperCase();
                              return (
                                <div key={k} className={`p-2 rounded-lg border text-xs flex items-start gap-1.5 ${isOrigCorrect ? 'border-support-line bg-support-bg font-semibold text-highlight' : 'border-line bg-rail text-ink'}`}>
                                  <span className="font-bold">{k}.</span>
                                  <div className="flex-1 min-w-0 overflow-x-auto"><MathRenderer content={String(v)} inline /></div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                        <div className="border-t border-line pt-2 text-xs leading-relaxed text-muted min-w-0 overflow-x-auto">
                          <span className="font-semibold text-strong block mb-1">Lời giải đề gốc:</span>
                          {selectedSolution.originalQuestion.solution_md ? (
                            <MathRenderer content={selectedSolution.originalQuestion.solution_md} />
                          ) : (
                            <p className="italic text-muted">Chưa có lời giải chi tiết cho đề gốc.</p>
                          )}
                        </div>
                      </section>
                    ) : (
                      <section className="rounded-xl border border-line bg-surface p-4 text-xs text-muted">
                        Không có dữ liệu đề gốc tương ứng.
                      </section>
                    )}

                    {/* Cột 2: Biến thể đang xem xét */}
                    <section className="rounded-xl border border-line bg-surface p-4 space-y-3">
                      <div className="flex items-center justify-between border-b border-line pb-2.5">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-highlight">
                          Biến thể ({versionLabel(session, activeVersionTab)} — Câu {qNo})
                        </h3>
                        <span className="text-xs font-semibold text-approved-ink">
                          Đáp án đúng: {selectedSolution.variant.correct_key || selectedSolution.variant.answer}
                        </span>
                      </div>
                      <div className="text-xs text-ink leading-relaxed min-w-0 overflow-x-auto">
                        <MathRenderer content={selectedSolution.variant.content || selectedSolution.variant.raw_content || ''} />
                      </div>
                      {Object.keys(options).length > 0 && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-1">
                          {Object.entries(options).map(([k, v]) => {
                            const isVarCorrect = String(k).toUpperCase() === String(selectedSolution.variant.correct_key || selectedSolution.variant.answer).toUpperCase();
                            return (
                              <div key={k} className={`p-2 rounded-lg border text-xs flex items-start gap-1.5 ${isVarCorrect ? 'border-approved-border bg-approved-bg font-semibold text-approved-ink' : 'border-line bg-rail text-ink'}`}>
                                <span className="font-bold">{k}.</span>
                                <div className="flex-1 min-w-0 overflow-x-auto"><MathRenderer content={String(v)} inline /></div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      <div className="border-t border-line pt-2 text-xs leading-relaxed text-ink min-w-0 overflow-x-auto">
                        <span className="font-semibold text-strong block mb-1">Lời giải biến thể:</span>
                        {selectedSolution.variant.solution_md ? (
                          <MathRenderer content={selectedSolution.variant.solution_md} />
                        ) : (
                          <p className="italic text-muted">Chưa có lời giải chi tiết cho câu hỏi này.</p>
                        )}
                      </div>
                    </section>
                  </div>

                  {!isReviewReadOnly && (
                    <div className="review-popup-actions flex flex-wrap items-center justify-end gap-3 border-t border-line bg-surface px-6 py-4">
                      {/* Nút Khôi phục đề gốc (data-review-revert) */}
                      {Boolean(session?.confirmation_id && session?.job_snapshot_id && (selectedSolution?.variant?.candidate_id || selectedSolution?.variant?.id || selectedSolution?.variant?.question_id)) && (
                        <button
                          type="button"
                          data-review-revert={true}
                          disabled={isRegeneratingSingle || isApprovingSingle || isRevertingSingle || isReviewReadOnly}
                          onClick={handleRevertSingle}
                          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-rail px-4 py-2.5 text-xs font-semibold text-ink hover:bg-support-bg hover:text-strong disabled:opacity-50"
                        >
                          {isRevertingSingle ? (
                            <>
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              Đang khôi phục…
                            </>
                          ) : (
                            <>
                              <RotateCcw className="h-3.5 w-3.5" />
                              Khôi phục đề gốc
                            </>
                          )}
                        </button>
                      )}

                      {/* Nút Tạo lại (data-review-regenerate) */}
                      <button
                        type="button"
                        data-review-regenerate={true}
                        disabled={isRegeneratingSingle || isApprovingSingle || isRevertingSingle || isReviewReadOnly || !(selectedSolution?.variant?.candidate_id || selectedSolution?.variant?.id || selectedSolution?.variant?.question_id)}
                        onClick={() => { if (!isSelectedVariantApproved || window.confirm('Tạo lại sẽ thay nội dung và cần duyệt lại câu này. Tiếp tục?')) void handleRegenerateSingle(); }}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-rail px-4 py-2.5 text-xs font-semibold text-ink hover:bg-rail hover:text-strong disabled:opacity-50"
                      >
                        {isRegeneratingSingle ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Đang tạo lại…
                          </>
                        ) : (
                          <>
                            <RefreshCw className="h-3.5 w-3.5" />
                            Tạo lại
                          </>
                        )}
                      </button>

                      {/* Nút Duyệt biến thể (data-review-approve) */}
                      <button
                        type="button"
                        data-review-approve={true}
                        disabled={isRegeneratingSingle || isApprovingSingle || isRevertingSingle || isSelectedVariantApproved || isReviewReadOnly || !(selectedSolution?.variant?.candidate_id || selectedSolution?.variant?.id || selectedSolution?.variant?.question_id)}
                        onClick={handleApproveSingle}
                        className={`inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-xs font-semibold shadow-soft transition-all ${
                          isSelectedVariantApproved
                            ? 'cursor-not-allowed bg-approved-bg text-approved-ink opacity-80'
                            : 'bg-approved-ink text-white hover:bg-approved-ink disabled:opacity-50'
                        }`}
                      >
                        {isApprovingSingle ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Đang duyệt…
                          </>
                        ) : isSelectedVariantApproved ? (
                          <>
                            <Check className="h-3.5 w-3.5" />
                            Đã duyệt
                          </>
                        ) : (
                          <>
                            <CheckCircle className="h-3.5 w-3.5" />
                            Duyệt biến thể
                          </>
                        )}
                      </button>
                    </div>
                  )}
                  {isSelectedVariantApproved && (
                    <button type="button" className="rounded-lg border border-line px-4 py-2 text-sm" onClick={goToNextUnreviewed}>
                      Đến câu chưa duyệt tiếp theo
                    </button>
                  )}
                </div>
              )}

            </div>
          );
        })}
      </div>

      {/* Thanh trạng thái dưới cùng: Tiến độ duyệt & Nút Xem trước bộ đề (PREVIEW.html layout) */}
      <div className="sticky bottom-0 z-30 mt-8 rounded-2xl border border-line bg-surface p-4 shadow-paper backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
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
                {totalExpectedSlots === 0 ? 'Chưa có đủ dữ liệu câu hỏi.' : isPartial ? 'Cần sinh đủ câu và duyệt tất cả câu hỏi.' : `Còn ${Math.max(0, totalExpectedSlots - approvedCount)} câu chưa duyệt.`}
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
              className="inline-flex items-center gap-2 rounded-xl bg-highlight px-6 py-2.5 text-xs font-semibold text-white shadow-soft hover:bg-[#253b57] focus:outline-none focus:ring-2 focus:ring-highlight disabled:cursor-not-allowed disabled:opacity-50 transition-all"
            >
              Xem trước bộ đề
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
);
}
