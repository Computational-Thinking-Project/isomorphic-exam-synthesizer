import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { exportPath, stage2Path, stage3PreviewPath } from '../../sessionPaths.js';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  CheckCircle2,
  Eye,
  Info,
  Loader2,
  Lock,
  RefreshCw,
} from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';
import { getSessionDetail } from '../../services/sessions.js';
import { retryGeneration } from '../../services/stage2Service.js';
import {
  acceptQuestion,
  rejectAndRegenerateQuestion,
  fetchReviewSnapshot,
  adaptReviewSnapshot,
  normalizeOptions,
} from '../../services/stage3Service.js';

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

/**
 * Thu thập toàn bộ ID, candidate_id và mã vị trí (${vIdx}-${qNo}) của các câu đã được duyệt
 */
function extractApprovedIds(sessionData) {
  const approved = new Set();
  if (!sessionData) return approved;

  if (Array.isArray(sessionData.version_questions)) {
    sessionData.version_questions.forEach((q) => {
      if (q.status === 'approved') {
        if (q.id) approved.add(q.id);
        if (q.candidate_id) approved.add(q.candidate_id);
        const qVIdx = q.version_index ?? q.version_code;
        const qNo = q.question_no ?? q.number;
        if (qVIdx && qNo) approved.add(`${qVIdx}-${qNo}`);
      }
    });
  }

  if (Array.isArray(sessionData.exam_versions)) {
    sessionData.exam_versions.forEach((ver, idx) => {
      const vIdx = ver.version_index ?? ver.index ?? idx + 1;
      const qList = ver.questions || ver.version_questions || [];
      qList.forEach((q) => {
        if (q.status === 'approved') {
          if (q.id) approved.add(q.id);
          if (q.candidate_id) approved.add(q.candidate_id);
          const qNo = q.question_no ?? q.number;
          if (qNo) approved.add(`${vIdx}-${qNo}`);
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
}) {
  const params = useParams();
  const sessionId = params.sessionId || params.id;
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
  const [lockedDetail, setLockedDetail] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const [activeVersionTab, setActiveVersionTab] = useState(1);
  const [regeneratingQuestions, setRegeneratingQuestions] = useState({});
  const [isRetryingAll, setIsRetryingAll] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  // Trạng thái modal Kiểm tra đáp án (SolutionDialog)
  const [selectedSolution, setSelectedSolution] = useState(null);
  const [isRegeneratingSingle, setIsRegeneratingSingle] = useState(false);
  const [isApprovingSingle, setIsApprovingSingle] = useState(false);
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
      const errCode = err?.response?.data?.error_code || err?.response?.data?.code;
      const isLocked423 = httpStatus === 423 || errCode === 'ERR_SESSION_LOCKED';

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
    setActiveVersionTab(1);
    setRegeneratingQuestions({});
    setIsRetryingAll(false);
    setSelectedSolution(null);
    setApprovedVariantIds(new Set());
    setActionMessage(null);
    setIsRegeneratingSingle(false);
    setIsApprovingSingle(false);
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
      (sq) => (sq.question_no ?? sq.number) === qNo
    );
    setSelectedSolution({
      variant: {
        ...variant,
        options: normalizeOptions(variant.options),
      },
      qNo,
      versionIndex,
      originalQuestion,
    });
  }, [session]);



  const isContentLocked = ['approved', 'exported'].includes(session?.status);

  // Xử lý Tạo lại câu hỏi trong SolutionDialog (Reject & Targeted Regeneration)
  const handleRegenerateSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isRegeneratingSingle || isContentLocked) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.candidate_id || variant.id || variant.question_id || `var-${versionIndex}-${qNo}`;

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
        next.delete(`${versionIndex}-${qNo}`);
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
            next.delete(`${versionIndex}-${qNo}`);
            if (variant.id) next.delete(variant.id);
            if (variant.candidate_id) next.delete(variant.candidate_id);
            if (replacement?.id) next.delete(replacement.id);
            if (replacement?.candidate_id) next.delete(replacement.candidate_id);
            authoritativeApproved.forEach((id) => {
              if (
                id !== `${versionIndex}-${qNo}` &&
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
  }, [selectedSolution, isRegeneratingSingle, isContentLocked, regenerateQuestionFn, sessionId, updateVariantInSession, loadSession]);

  // Xử lý Duyệt biến thể trong SolutionDialog
  const handleApproveSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isApprovingSingle || isContentLocked) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.candidate_id || variant.id || variant.question_id || `var-${versionIndex}-${qNo}`;

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
        next.add(`${versionIndex}-${qNo}`);
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
          // Đảm bảo không ghi đè trạng thái approved vừa duyệt nếu snapshot từ mock tĩnh trả về câu chưa duyệt
          adapted.exam_versions = (adapted.exam_versions || []).map((ver) => {
            if ((ver.version_index ?? 1) === versionIndex) {
              const qList = (ver.questions || []).map((q) => {
                if ((q.question_no ?? q.number) === qNo) {
                  return { ...q, status: 'approved' };
                }
                return q;
              });
              return { ...ver, questions: qList };
            }
            return ver;
          });
          setSession(adapted);
          const authoritativeApproved = extractApprovedIds(adapted);
          setApprovedVariantIds((prev) => {
            const merged = new Set(prev);
            authoritativeApproved.forEach((id) => merged.add(id));
            if (variant.id) merged.add(variant.id);
            if (variant.candidate_id) merged.add(variant.candidate_id);
            merged.add(`${versionIndex}-${qNo}`);
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
  }, [selectedSolution, isApprovingSingle, isContentLocked, acceptQuestionFn, sessionId, updateVariantInSession, loadSession]);

  // Xử lý sinh bù câu thiếu (retry partial generation)
  const handleRetryMissingQuestion = async (versionIndex, questionNo) => {
    if (isContentLocked) return;
    const regKey = `${versionIndex}-${questionNo}`;
    const currentOp = ++retryOperationRef.current;
    const targetSessionId = sessionId;

    setRegeneratingQuestions((prev) => ({ ...prev, [regKey]: true }));
    setActionMessage(null);

    try {
      await retryGen(sessionId);
      if (
        !isMountedRef.current ||
        retryOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setActionMessage({
        type: 'success',
        text: `Đã gửi yêu cầu sinh bù cho câu ${questionNo} (Đề ${versionIndex}). Đang đồng bộ...`,
      });
      await loadData();
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
        text: extractErrorString(err, 'Không thể gửi yêu cầu sinh bù câu này.'),
      });
    } finally {
      if (
        isMountedRef.current &&
        retryOperationRef.current === currentOp &&
        activeSessionIdRef.current === targetSessionId
      ) {
        setRegeneratingQuestions((prev) => ({ ...prev, [regKey]: false }));
      }
    }
  };

  const handleRetryAllMissing = async () => {
    if (isContentLocked) return;
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
        text: 'Đã kích hoạt sinh bù toàn bộ các câu hỏi còn thiếu. Đang chuyển hướng về tiến trình sinh đề...',
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
        text: extractErrorString(err, 'Không thể kích hoạt sinh bù toàn bộ.'),
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
        const slotKey = `${vIdx}-${qNo}`;
        if (
          v &&
          (v.status === 'approved' ||
            (v.id && approvedVariantIds.has(v.id)) ||
            approvedVariantIds.has(slotKey))
        ) {
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
      if (candidate && candidate.status !== 'approved' && !approvedVariantIds.has(`${version}-${number}`)) {
        setReviewFilter('all');
        setActiveVersionTab(version);
        handleOpenSolutionModal(candidate, number, version);
        setTimeout(() => document.getElementById(`review-${version}-${number}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 0);
        return;
      }
    }
    setActionMessage({type: 'success', text: 'Không còn câu chưa duyệt.'});
  };

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
    totalExpectedSlots === 0 || approvedCount < totalExpectedSlots || isPartial || isApprovingSingle || isRegeneratingSingle || isRetryingAll;

  const isSelectedVariantApproved = useMemo(() => {
    if (!selectedSolution?.variant) return false;
    const { variant, versionIndex, qNo } = selectedSolution;
    const slotKey = `${versionIndex}-${qNo}`;
    return (
      variant.status === 'approved' ||
      (variant.id && approvedVariantIds.has(variant.id)) ||
      approvedVariantIds.has(slotKey)
    );
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
              <button
                type="button"
                onClick={loadData}
                className="inline-flex items-center gap-2 rounded-xl bg-rail px-4 py-2 text-xs font-semibold text-ink hover:bg-rail"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Thử lại
              </button>
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

  return (
    <div className="paper-ui min-h-screen bg-canvas text-ink">
      <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      {/* Header điều hướng & tóm tắt */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
        <div>
          <button
            type="button"
            onClick={() => navigate(stage2Path(sessionId))}
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold text-highlight hover:text-highlight"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Xem thông tin lần sinh
          </button>
          <h1 className="text-2xl font-bold tracking-tight text-strong">
            {session?.title || 'Xem & Duyệt Đề Thi Đẳng Cấu'}
          </h1>
          <p className="mt-1 text-xs text-muted">
            Môn học: <span className="text-ink">{session?.subject || 'Toán'}</span> • Lớp:{' '}
            <span className="text-ink">{session?.grade || 12}</span> • Số mã đề:{' '}
            <span className="text-ink">{numVersions}</span>
          </p>
        </div>

        {/* Nút xuất bản / phê duyệt header */}
        <div className="flex items-center gap-2">
          {isContentLocked ? (
            <button
              type="button"
              data-testid="stage3-btn-goto-export"
              onClick={() => navigate(exportPath(sessionId))}
              className="inline-flex items-center gap-1.5 rounded-xl bg-approved-ink px-4 py-2 text-xs font-semibold text-white shadow-soft  hover:bg-approved-ink"
            >
              <Lock className="h-3.5 w-3.5" />
              Tới màn hình Xuất bản
            </button>
          ) : isPartial && hasLoadedAnyVariants && totalLoadedVariants < totalExpectedSlots ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRetryAllMissing}
                disabled={isRetryingAll}
                className="inline-flex items-center gap-1.5 rounded-xl border border-accent-border bg-accent px-3.5 py-2 text-xs font-semibold text-strong shadow-soft  hover:bg-accent disabled:opacity-50"
              >
                {isRetryingAll ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Sinh bù tất cả câu thiếu
              </button>
            </div>
          ) : null}
        </div>
      </div>

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
      {isContentLocked && (
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

      {/* Thanh chọn Tab mã đề */}
      <div className="flex items-center gap-2 overflow-x-auto border-b border-line pb-3">
        {Array.from({ length: numVersions }, (_, i) => i + 1).map((vIdx) => {
          const isTabActive = activeVersionTab === vIdx;
          return (
            <button
              key={vIdx}
              type="button"
              disabled={isApprovingSingle || isRegeneratingSingle}
              onClick={() => {setActiveVersionTab(vIdx);setSelectedSolution(null);}}
              aria-pressed={isTabActive}
              className={`rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
                isTabActive
                  ? 'bg-highlight text-white shadow-md '
                  : 'border border-line bg-rail text-ink hover:bg-rail'
              }`}
            >
              {versionLabel(session, vIdx)} · {Array.from({length: totalSourceQuestions}, (_, i) => i+1).filter(n => findVariantInSession(session,vIdx,n)?.status === 'approved' || approvedVariantIds.has(`${vIdx}-${n}`)).length}/{totalSourceQuestions}
            </button>
          );
        })}
      </div>

      <div role="group" aria-label="Lọc câu hỏi" className="flex flex-wrap gap-2">
        {[['all','Tất cả'],['pending','Chưa duyệt'],['warning','Có cảnh báo'],['approved','Đã duyệt']].map(([value,label]) => {
          const count = Array.from({length:totalSourceQuestions},(_,i)=>findVariantInSession(session,activeVersionTab,i+1)).filter((v,i)=>{
            const approved = v?.status === 'approved' || approvedVariantIds.has(`${activeVersionTab}-${i+1}`);
            return value === 'all' || (value === 'pending' && !approved) || (value === 'approved' && approved) || (value === 'warning' && Boolean(v?.has_warning || v?.is_fallback || v?.source_fallback || v?.warning_flag || v?.warning_message));
          }).length;
          return <button type="button" key={value} aria-pressed={reviewFilter===value} disabled={isApprovingSingle || isRegeneratingSingle} onClick={()=>{setReviewFilter(value);setSelectedSolution(null);}} className="rounded-lg border border-line px-3 py-2 text-sm aria-pressed:bg-support-bg">{label} ({count})</button>;
        })}
      </div>
      {/* Danh sách các câu hỏi trong mã đề được chọn */}
      <div className="space-y-4">
        {Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).map((qNo) => {
          const variant = selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab ? selectedSolution.variant : findVariantInSession(session, activeVersionTab, qNo);
          const isMissing = !variant;
          const regKey = `${activeVersionTab}-${qNo}`;
          const isRegenerating = regeneratingQuestions[regKey];

          if (isMissing) {
            if (['approved', 'warning'].includes(reviewFilter)) return null;
            if (!hasLoadedAnyVariants) {
              return null;
            }

            return (
              <div
                key={qNo}
              style={{scrollMarginTop: 24}} id={`review-${activeVersionTab}-${qNo}`}
                style={{scrollMarginTop: 24}} id={`review-${activeVersionTab}-${qNo}`}
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
                      <p className="mt-0.5 text-xs text-danger">
                        Câu hỏi này bị gián đoạn do chạm hạn mức API hoặc không đạt ràng buộc nghiệm đẹp.
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRetryMissingQuestion(activeVersionTab, qNo)}
                    disabled={isRegenerating || isContentLocked}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-danger-border bg-danger-soft px-3.5 py-1.5 text-xs font-semibold text-strong hover:bg-danger-soft disabled:opacity-50"
                  >
                    {isRegenerating ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    Sinh bù câu này
                  </button>
                </div>
              </div>
            );
          }

          // Hiển thị câu hỏi đã hoàn tất
          const options = normalizeOptions(variant.options);
          const correctKey = variant.correct_key || variant.answer;
          const slotKey = `${activeVersionTab}-${qNo}`;
          const isApproved =
            variant.status === 'approved' ||
            (variant.id && approvedVariantIds.has(variant.id)) ||
            approvedVariantIds.has(slotKey);

          const isFallback = Boolean(
            variant.is_fallback ||
            variant.source_fallback ||
            variant.warning_flag === 'fallback' ||
            (variant.attempts >= 4 && variant.is_fallback !== false)
          );

          const hasWarning = Boolean(
            variant.has_warning ||
            variant.status === 'warning' ||
            variant.status === 'needs_review' ||
            variant.warning_message ||
            (variant.validation_report && variant.validation_report.is_valid === false)
          );

          const warningMsg =
            variant.warning_message ||
            variant.validation_report?.warning ||
            variant.validation_report?.message ||
            'Câu hỏi có cảnh báo nghiệm hoặc ràng buộc cần lưu ý.';

          const pinned = selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab;
          if (!pinned && ((reviewFilter === 'pending' && isApproved) || (reviewFilter === 'approved' && !isApproved) || (reviewFilter === 'warning' && !hasWarning && !isFallback))) return null;
          return (
            <div
              key={qNo}
              style={{scrollMarginTop: 24}} id={`review-${activeVersionTab}-${qNo}`}
              className={`rounded-2xl border p-5 shadow-soft transition-all ${
                isApproved
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
                  {isApproved ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-approved-border bg-approved-bg px-2.5 py-0.5 text-[11px] font-medium text-approved-ink">
                      <CheckCircle className="h-3 w-3" />
                      Đã duyệt
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-rail px-2.5 py-0.5 text-[11px] font-medium text-ink">
                      Chưa duyệt
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

                {/* Nút Kiểm tra đáp án (Mở modal SolutionDialog) */}
                <button
                  type="button"
                  data-review-inspect={true}
                  disabled={isRegeneratingSingle || isApprovingSingle}
                  aria-expanded={selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab}
                  aria-controls={`solution-${activeVersionTab}-${qNo}`}
                  onClick={() => selectedSolution?.qNo === qNo && selectedSolution?.versionIndex === activeVersionTab ? setSelectedSolution(null) : handleOpenSolutionModal(variant, qNo, activeVersionTab)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-support-line bg-support-bg px-3 py-1.5 text-xs font-semibold text-highlight hover:bg-highlight hover:text-strong transition-all shadow-sm"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Xem lời giải
                </button>
              </div>

              {/* Badge Fallback: Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc */}
              {isFallback && (
                <div className="mt-3 rounded-xl border border-accent-border bg-accent-soft p-2.5 text-xs text-accent-ink flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-accent-ink" />
                  <span className="font-semibold">
                    Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc
                  </span>
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
                        <div className="flex-1">
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
                {actionMessage && <p role="status" className="text-sm">{actionMessage.text}</p>}
                <section className="rounded-xl border border-line bg-surface p-4">
                  <div className="flex items-center justify-between border-b border-line pb-2.5">
                    <h3 className="text-sm font-bold text-highlight">
                      Đáp án và lời giải
                    </h3>
                    <span className="text-xs font-semibold text-approved-ink">
                      Đáp án đúng: {selectedSolution.variant.correct_key || selectedSolution.variant.answer}
                    </span>
                  </div>

                  <div className="mt-3 text-xs leading-relaxed text-ink">
                    {selectedSolution.variant.solution_md ? (
                      <MathRenderer content={selectedSolution.variant.solution_md} />
                    ) : (
                      <p className="italic text-muted">
                        Chưa có lời giải chi tiết cho câu hỏi này.
                      </p>
                    )}
                  </div>
                </section>
                  {selectedSolution.originalQuestion && <details className="rounded-xl border border-line p-4 text-sm"><summary className="cursor-pointer font-semibold">Xem câu nguồn</summary><MathRenderer content={selectedSolution.originalQuestion.raw_content || selectedSolution.originalQuestion.content || ''} /></details>}
            {!isContentLocked && <div className="review-popup-actions flex flex-wrap items-center justify-end gap-3 border-t border-line bg-surface px-6 py-4">
              {/* Nút 1: Tạo lại (data-review-regenerate) */}
              <button
                type="button"
                data-review-regenerate={true}
                disabled={isRegeneratingSingle || isApprovingSingle || isContentLocked}
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

              {/* Nút 2: Duyệt biến thể (data-review-approve) */}
              <button
                type="button"
                data-review-approve={true}
                disabled={isRegeneratingSingle || isApprovingSingle || isSelectedVariantApproved || isContentLocked}
                onClick={handleApproveSingle}
                className={`inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-xs font-semibold shadow-soft transition-all ${
                  isSelectedVariantApproved
                    ? 'cursor-not-allowed bg-approved-bg text-approved-ink opacity-80'
                    : 'bg-approved-ink text-white  hover:bg-approved-ink disabled:opacity-50'
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
            </div>}
                  {isSelectedVariantApproved && <button type="button" className="rounded-lg border border-line px-4 py-2 text-sm" onClick={goToNextUnreviewed}>Đến câu chưa duyệt tiếp theo</button>}
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
            {isFinalizeDisabled && (
              <p className="text-sm text-muted" role="status">
                {totalExpectedSlots === 0 ? 'Chưa có đủ dữ liệu câu hỏi.' : isPartial ? 'Cần sinh đủ câu và duyệt tất cả câu hỏi.' : `Còn ${Math.max(0, totalExpectedSlots - approvedCount)} câu chưa duyệt.`}
              </p>
            )}
            <button
              type="button"
              data-review-finalize={true}
              disabled={isFinalizeDisabled}
              onClick={() => navigate(stage3PreviewPath(sessionId))}
              className="inline-flex items-center gap-2 rounded-xl bg-highlight px-6 py-2.5 text-xs font-semibold text-white shadow-soft  hover:bg-highlight focus:outline-none focus:ring-2 focus:ring-highlight disabled:cursor-not-allowed disabled:opacity-50 transition-all"
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
