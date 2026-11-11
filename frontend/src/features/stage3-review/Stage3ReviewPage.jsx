import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  CheckCircle2,
  Download,
  Eye,
  FileCheck,
  Info,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';
import { fetchSessionDetail, retryGeneration } from '../../services/stage2Service.js';
import {
  acceptQuestion,
  rejectAndRegenerateQuestion,
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
 * Chuẩn hóa đối tượng options từ mảng hoặc dictionary sang format { A: ..., B: ..., C: ..., D: ... }
 */
function normalizeOptions(options) {
  if (!options) return {};
  if (Array.isArray(options)) {
    const letters = ['A', 'B', 'C', 'D'];
    const res = {};
    options.forEach((opt, idx) => {
      if (idx < 4) res[letters[idx]] = opt;
    });
    return res;
  }
  return options;
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
  loadSession = fetchSessionDetail,
  retryGen = retryGeneration,
  acceptQuestionFn = acceptQuestion,
  regenerateQuestionFn = rejectAndRegenerateQuestion,
}) {
  const params = useParams();
  const sessionId = params.sessionId || params.id;
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
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

    try {
      const data = await loadSession(targetSessionId);
      if (
        !isMountedRef.current ||
        loadOperationRef.current !== currentOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setSession(data);

      // Thu thập các ID hoặc mã câu đã được duyệt trước đó
      const initialApproved = new Set();
      if (Array.isArray(data.version_questions)) {
        data.version_questions.forEach((q) => {
          if (q.status === 'approved') {
            if (q.id) initialApproved.add(q.id);
            const qVIdx = q.version_index ?? q.version_code;
            const qNo = q.question_no ?? q.number;
            if (qVIdx && qNo) initialApproved.add(`${qVIdx}-${qNo}`);
          }
        });
      }
      if (Array.isArray(data.exam_versions)) {
        data.exam_versions.forEach((ver, idx) => {
          const vIdx = ver.version_index ?? ver.index ?? idx + 1;
          const qList = ver.questions || ver.version_questions || [];
          qList.forEach((q) => {
            if (q.status === 'approved') {
              if (q.id) initialApproved.add(q.id);
              const qNo = q.question_no ?? q.number;
              if (qNo) initialApproved.add(`${vIdx}-${qNo}`);
            }
          });
        });
      }
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
      setError(extractErrorString(err, 'Không thể tải chi tiết phiên làm việc.'));
      setIsLoading(false);
    }
  }, [sessionId, loadSession]);

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
    setError(null);
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

      if (Array.isArray(next.version_questions)) {
        next.version_questions = next.version_questions.map((q) => {
          const matchesId = q.id && updatedVariant.id && q.id === updatedVariant.id;
          const qVIdx = q.version_index ?? q.version_code;
          const matchesSlot = targetVIdx && qVIdx === targetVIdx && (q.question_no ?? q.number) === qNoToMatch;
          return matchesId || matchesSlot ? { ...q, ...updatedVariant } : q;
        });
      }

      if (Array.isArray(next.exam_versions)) {
        next.exam_versions = next.exam_versions.map((ver, idx) => {
          const currentVIdx = ver.version_index ?? ver.index ?? idx + 1;
          const questionsKey = ver.questions ? 'questions' : ver.version_questions ? 'version_questions' : 'questions';
          const qList = ver[questionsKey] || [];
          const updatedList = qList.map((q) => {
            const matchesId = q.id && updatedVariant.id && q.id === updatedVariant.id;
            const matchesSlot = targetVIdx && currentVIdx === targetVIdx && (q.question_no ?? q.number) === qNoToMatch;
            return matchesId || matchesSlot ? { ...q, ...updatedVariant } : q;
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

  const handleCloseSolutionModal = useCallback(() => {
    if (isRegeneratingSingle || isApprovingSingle) return;
    setSelectedSolution(null);
  }, [isRegeneratingSingle, isApprovingSingle]);

  // Xử lý Tạo lại câu hỏi trong SolutionDialog (Reject & Targeted Regeneration)
  const handleRegenerateSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isRegeneratingSingle) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.id || variant.question_id || `var-${versionIndex}-${qNo}`;

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

      const newOptions = normalizeOptions(res.options || variant.options);
      // Tạo object mới sạch từ response; không kế thừa cờ fallback/warning từ candidate cũ
      const updatedVariant = {
        id: res.question_id || res.id || variant.id,
        question_id: res.question_id || res.id || variant.question_id,
        source_question_id: variant.source_question_id,
        question_no: variant.question_no ?? qNo,
        number: variant.number ?? qNo,
        version_index: versionIndex,
        status: res.status || 'pending_review',
        content: res.content || res.stem_latex || res.stem || variant.content,
        options: newOptions,
        correct_key: res.correct_key || variant.correct_key,
        solution_md: res.solution_md ?? res.solution ?? variant.solution_md ?? '',
        is_fallback: Boolean(res.is_fallback),
        source_fallback: Boolean(res.source_fallback),
        has_warning: Boolean(res.has_warning),
        warning_message: res.warning_message || null,
        validation_report: res.validation_report || null,
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
        if (updatedVariant.id) next.delete(updatedVariant.id);
        next.delete(`${versionIndex}-${qNo}`);
        return next;
      });

      setActionMessage({
        type: 'success',
        text: `Đã tạo lại câu ${qNo} (mã đề #${100 + versionIndex}). Kiểm tra đáp án và duyệt phiên bản mới.`,
      });
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
  }, [selectedSolution, isRegeneratingSingle, regenerateQuestionFn, sessionId, updateVariantInSession]);

  // Xử lý Duyệt biến thể trong SolutionDialog
  const handleApproveSingle = useCallback(async () => {
    if (!selectedSolution?.variant || isApprovingSingle) return;
    const { variant, qNo, versionIndex } = selectedSolution;
    const targetQId = variant.id || variant.question_id || `var-${versionIndex}-${qNo}`;

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
        next.add(`${versionIndex}-${qNo}`);
        return next;
      });

      setActionMessage({
        type: 'success',
        text: `Đã duyệt câu ${qNo} · Mã đề #${100 + versionIndex}.`,
      });
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
  }, [selectedSolution, isApprovingSingle, acceptQuestionFn, sessionId, updateVariantInSession]);

  // Xử lý sinh bù câu thiếu (retry partial generation)
  const handleRetryMissingQuestion = async (versionIndex, questionNo) => {
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
        text: `Đã gửi yêu cầu sinh bù cho câu ${questionNo} (Mã đề #${100 + versionIndex}). Đang đồng bộ...`,
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
          navigate(`/session/${targetSessionId}/stage2`);
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

  const numVersions = session?.config?.n_versions || session?.exam_versions?.length || 1;
  const totalSourceQuestions = session?.source_questions?.length || 0;
  const totalLoadedVariants = countTotalLoadedVariants(session);
  const isPartial = session?.status === 'partial_generated';
  const hasLoadedAnyVariants = totalLoadedVariants > 0;
  const totalExpectedSlots = numVersions * totalSourceQuestions;

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

  const isFinalizeDisabled =
    totalExpectedSlots === 0 || approvedCount < totalExpectedSlots || isPartial;

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
      <div className="flex min-h-[400px] flex-col items-center justify-center gap-3 p-8">
        <Loader2 className="h-8 w-8 animate-spin text-sky-400" />
        <p className="text-xs text-slate-400">Đang tải chi tiết đề thi và các câu hỏi biến thể...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <div
          role="alert"
          className="rounded-2xl border border-rose-500/40 bg-rose-950/40 p-6 text-center shadow-xl"
        >
          <AlertCircle className="mx-auto h-10 w-10 text-rose-400" />
          <h2 className="mt-3 text-lg font-bold text-white">Không thể tải đề thi</h2>
          <p className="mt-1 text-sm text-rose-200">{error}</p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              type="button"
              onClick={loadData}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Thử lại
            </button>
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Về Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      {/* Header điều hướng & tóm tắt */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <button
            type="button"
            onClick={() => navigate(`/session/${sessionId}/stage2`)}
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold text-sky-400 hover:text-sky-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Quay lại Cấu hình Stage 2
          </button>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            {session?.title || 'Xem & Duyệt Đề Thi Đẳng Cấu'}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Môn học: <span className="text-slate-200">{session?.subject || 'Toán'}</span> • Lớp:{' '}
            <span className="text-slate-200">{session?.grade || 12}</span> • Số mã đề:{' '}
            <span className="text-slate-200">{numVersions}</span>
          </p>
        </div>

        {/* Nút xuất bản / phê duyệt header */}
        <div className="flex items-center gap-2">
          {isPartial ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRetryAllMissing}
                disabled={isRetryingAll}
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/50 bg-amber-600 px-3.5 py-2 text-xs font-semibold text-white shadow-lg shadow-amber-600/30 hover:bg-amber-500 disabled:opacity-50"
              >
                {isRetryingAll ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Sinh bù tất cả câu thiếu
              </button>
              <button
                type="button"
                disabled
                title="Chưa thể xuất bản vì đề thi chưa hoàn tất 100% câu hỏi (trạng thái partial_generated)"
                className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2 text-xs font-semibold text-slate-500 opacity-60"
              >
                <Download className="h-3.5 w-3.5" />
                Xuất bản file (Bị khóa)
              </button>
            </div>
          ) : (
            <button
              type="button"
              disabled
              title="Tính năng phê duyệt & xuất bản file đề thi sẽ sẵn sàng khi hoàn tất tích hợp API Stage 3."
              className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2 text-xs font-semibold text-slate-400 opacity-70"
            >
              <FileCheck className="h-3.5 w-3.5" />
              Phê duyệt & Xuất bản đề (Chờ Stage 3)
            </button>
          )}
        </div>
      </div>

      {/* Thông báo thao tác */}
      {actionMessage && (
        <div
          role="status"
          className={`rounded-xl border p-4 text-xs font-medium ${
            actionMessage.type === 'success'
              ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200'
              : 'border-rose-500/40 bg-rose-950/30 text-rose-200'
          }`}
        >
          {actionMessage.text}
        </div>
      )}

      {/* Cảnh báo trạng thái sinh một phần (partial_generated) */}
      {isPartial && (
        <div
          role="alert"
          className="rounded-2xl border border-amber-500/50 bg-amber-950/40 p-6 text-amber-200 shadow-xl"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-amber-400" />
            <div>
              <h3 className="text-base font-bold text-white">
                Cảnh báo: Đề thi có câu hỏi chưa hoàn tất (<code>partial_generated</code>)
              </h3>
              <p className="mt-1 text-xs text-amber-200/90 leading-relaxed">
                Tiến trình sinh đề bị dừng trước khi hoàn thành 100% (do chạm trần hạn ngạch API
                Gemini hoặc câu hỏi không đạt ràng buộc nghiệm đẹp). Theo quy chế W2, tính năng Xuất
                bản file và Phê duyệt cuối bị tạm khóa cho đến khi đủ câu. Bạn có thể duyệt từng câu
                bên dưới và bấm nút <strong>"Sinh bù câu này"</strong> đối với các câu bị thiếu.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Thông báo khi backend chưa nạp dữ liệu chi tiết câu hỏi */}
      {!hasLoadedAnyVariants && (
        <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-8 text-center text-slate-300">
          <Info className="mx-auto h-8 w-8 text-sky-400" />
          <h3 className="mt-3 text-base font-semibold text-white">
            Đang đồng bộ dữ liệu chi tiết các mã đề từ Backend
          </h3>
          <p className="mt-1 text-xs text-slate-400 max-w-md mx-auto">
            {isPartial
              ? 'Phiên này được ghi nhận ở trạng thái sinh dở (partial_generated), nhưng API chi tiết hiện tại chưa nạp danh sách câu hỏi biến thể. Giao diện đang giữ trạng thái chờ để tránh đánh dấu sai các câu đã lưu trong cơ sở dữ liệu.'
              : 'Các mã đề thi đã được ghi nhận. Dữ liệu chi tiết từng câu hỏi biến thể đang trong quá trình đồng bộ từ cơ sở dữ liệu.'}
          </p>
        </div>
      )}

      {/* Thanh chọn Tab mã đề */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
        {Array.from({ length: numVersions }, (_, i) => i + 1).map((vIdx) => {
          const isTabActive = activeVersionTab === vIdx;
          return (
            <button
              key={vIdx}
              type="button"
              onClick={() => setActiveVersionTab(vIdx)}
              className={`rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
                isTabActive
                  ? 'bg-sky-600 text-white shadow-md shadow-sky-600/30'
                  : 'border border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800'
              }`}
            >
              Mã đề #{100 + vIdx} (Đề {vIdx})
            </button>
          );
        })}
      </div>

      {/* Danh sách các câu hỏi trong mã đề được chọn */}
      <div className="space-y-4">
        {Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).map((qNo) => {
          const variant = findVariantInSession(session, activeVersionTab, qNo);
          const isMissing = !variant;
          const regKey = `${activeVersionTab}-${qNo}`;
          const isRegenerating = regeneratingQuestions[regKey];

          if (isMissing) {
            if (!hasLoadedAnyVariants) {
              return null;
            }

            return (
              <div
                key={qNo}
                className="rounded-2xl border border-rose-500/50 bg-rose-950/20 p-5 shadow-lg transition-all"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-rose-900/60 text-xs font-bold text-rose-200">
                      {qNo}
                    </span>
                    <div>
                      <h4 className="text-sm font-bold text-white">
                        Câu {qNo} (Mã đề #{100 + activeVersionTab}) — Chưa được sinh thành công
                      </h4>
                      <p className="mt-0.5 text-xs text-rose-300/80">
                        Câu hỏi này bị gián đoạn do chạm hạn mức API hoặc không đạt ràng buộc nghiệm đẹp.
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRetryMissingQuestion(activeVersionTab, qNo)}
                    disabled={isRegenerating}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-900/40 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-rose-900/60 disabled:opacity-50"
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
            variant.attempts >= 4 ||
            variant.source_fallback ||
            variant.warning_flag === 'fallback'
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

          return (
            <div
              key={qNo}
              className={`rounded-2xl border p-5 shadow-lg transition-all ${
                isApproved
                  ? 'border-emerald-600/40 bg-slate-900/90'
                  : hasWarning
                  ? 'border-amber-500/50 bg-slate-900/90'
                  : 'border-slate-700 bg-slate-900/90'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-950/80 text-xs font-bold text-sky-300 border border-sky-800/40">
                    {qNo}
                  </span>
                  <span className="text-xs font-semibold text-white">
                    Câu {qNo} (Mã đề #{100 + activeVersionTab})
                  </span>

                  {/* Badge trạng thái duyệt */}
                  {isApproved ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">
                      <CheckCircle className="h-3 w-3" />
                      Đã duyệt
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-0.5 text-[11px] font-medium text-slate-300">
                      Chưa duyệt
                    </span>
                  )}

                  {/* Badge phản ánh chất lượng thẩm định nếu chưa duyệt */}
                  {!isApproved && hasWarning && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-950/40 px-2.5 py-0.5 text-[11px] font-medium text-amber-300">
                      <AlertTriangle className="h-3 w-3" />
                      Cần thẩm định (Có cảnh báo)
                    </span>
                  )}
                  {!isApproved && !hasWarning && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">
                      <CheckCircle className="h-3 w-3" />
                      Đạt chuẩn
                    </span>
                  )}
                </div>

                {/* Nút Kiểm tra đáp án (Mở modal SolutionDialog) */}
                <button
                  type="button"
                  data-review-inspect={true}
                  onClick={() => handleOpenSolutionModal(variant, qNo, activeVersionTab)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-sky-600 bg-sky-600/20 px-3 py-1.5 text-xs font-semibold text-sky-200 hover:bg-sky-600 hover:text-white transition-all shadow-sm"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Kiểm tra đáp án
                </button>
              </div>

              {/* Badge Fallback: Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc */}
              {isFallback && (
                <div className="mt-3 rounded-xl border border-amber-500/40 bg-amber-950/30 p-2.5 text-xs text-amber-300 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                  <span className="font-semibold">
                    Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc
                  </span>
                </div>
              )}

              {/* Thông báo chi tiết cảnh báo nếu có và không phải fallback */}
              {!isFallback && hasWarning && (
                <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-950/20 p-2.5 text-xs text-amber-200/90 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                  <span>{warningMsg}</span>
                </div>
              )}

              {/* Nội dung đề bài */}
              <div className="mt-3 text-sm text-slate-200">
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
                            ? 'border-emerald-500/60 bg-emerald-950/30 text-emerald-200'
                            : 'border-slate-800 bg-slate-800/40 text-slate-300'
                        }`}
                      >
                        <span
                          className={`font-bold ${
                            isCorrect ? 'text-emerald-400' : 'text-slate-400'
                          }`}
                        >
                          {key}.
                        </span>
                        <div className="flex-1">
                          <MathRenderer content={String(optVal)} inline />
                        </div>
                        {isCorrect && (
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Lời giải chi tiết nếu có */}
              {variant.solution_md && (
                <div className="mt-3 rounded-xl border border-slate-800 bg-slate-800/30 p-3 text-xs text-slate-300">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-400">
                    <Sparkles className="h-3.5 w-3.5 text-sky-400" />
                    Lời giải chi tiết:
                  </div>
                  <div className="mt-1">
                    <MathRenderer content={variant.solution_md} />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Thanh trạng thái dưới cùng: Tiến độ duyệt & Nút Rà bộ đề (PREVIEW.html layout) */}
      <div className="sticky bottom-0 z-40 mt-8 rounded-2xl border border-slate-800 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
              className={`flex h-2.5 w-2.5 rounded-full ${
                approvedCount === totalExpectedSlots && totalExpectedSlots > 0
                  ? 'bg-emerald-400'
                  : 'bg-amber-400'
              }`}
            />
            <span className="text-sm font-medium text-slate-300">
              Đã duyệt{' '}
              <strong className="font-bold text-white">
                {approvedCount}/{totalExpectedSlots}
              </strong>{' '}
              câu
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              data-review-finalize={true}
              disabled={isFinalizeDisabled}
              onClick={() => navigate(`/session/${sessionId}/stage3/preview`)}
              className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-6 py-2.5 text-xs font-semibold text-white shadow-lg shadow-sky-600/30 hover:bg-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
            >
              Rà bộ đề
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Modal Kiểm tra đáp án (SolutionDialog) */}
      {selectedSolution && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="solution-dialog-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
        >
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm transition-opacity"
            onClick={isRegeneratingSingle || isApprovingSingle ? undefined : handleCloseSolutionModal}
          />

          {/* Dialog Container */}
          <div className="solution-dialog relative z-10 flex max-h-[90vh] w-full max-w-5xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
            {/* Dialog Header */}
            <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
              <div>
                <h2
                  id="solution-dialog-title"
                  className="text-lg font-bold text-white"
                >
                  Kiểm tra đáp án · Câu {selectedSolution.qNo} · Mã {100 + selectedSolution.versionIndex}
                </h2>
                <p className="text-xs text-slate-400">
                  Đối chiếu biến thể sinh bởi AI với câu hỏi gốc và lời giải chi tiết.
                </p>
              </div>
              <button
                type="button"
                onClick={handleCloseSolutionModal}
                disabled={isRegeneratingSingle || isApprovingSingle}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white disabled:opacity-50"
                aria-label="Đóng"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Dialog Body (2 Columns) */}
            <div className="dialog-copy flex-1 overflow-y-auto p-6 space-y-4">
              {/* Fallback warning trong modal nếu có */}
              {(selectedSolution.variant.is_fallback ||
                selectedSolution.variant.attempts >= 4 ||
                selectedSolution.variant.source_fallback ||
                selectedSolution.variant.warning_flag === 'fallback') && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-950/40 p-3 text-xs font-semibold text-amber-300 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                  <span>Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc</span>
                </div>
              )}

              <div className="solution-columns grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* Column 1: Biến thể đang xem */}
                <section className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <h3 className="text-sm font-bold text-slate-200">
                      Biến thể · Câu {selectedSolution.qNo} · Mã {100 + selectedSolution.versionIndex}
                    </h3>
                    <span
                      className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                        isSelectedVariantApproved
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      {isSelectedVariantApproved ? 'Đã duyệt' : 'Chưa duyệt'}
                    </span>
                  </div>

                  <div className="mt-3 text-sm text-slate-100">
                    <MathRenderer
                      content={
                        selectedSolution.variant.content ||
                        selectedSolution.variant.raw_content ||
                        ''
                      }
                    />
                  </div>

                  {/* Danh sách options */}
                  <div className="mt-4 space-y-2">
                    {Object.entries(selectedSolution.variant.options || {}).map(([key, optVal]) => {
                      const isCorrect =
                        String(key).toUpperCase() ===
                        String(selectedSolution.variant.correct_key || selectedSolution.variant.answer).toUpperCase();
                      return (
                        <div
                          key={key}
                          className={`flex items-start gap-2.5 rounded-xl border p-2.5 text-xs ${
                            isCorrect
                              ? 'border-emerald-500/60 bg-emerald-950/40 text-emerald-100 font-medium'
                              : 'border-slate-800 bg-slate-900/50 text-slate-300'
                          }`}
                        >
                          <span
                            className={`font-bold ${
                              isCorrect ? 'text-emerald-400' : 'text-slate-400'
                            }`}
                          >
                            {key}.
                          </span>
                          <div className="flex-1">
                            <MathRenderer content={String(optVal)} inline />
                          </div>
                          {isCorrect && (
                            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>

                {/* Column 2: Đáp án và lời giải chi tiết */}
                <section className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <h3 className="text-sm font-bold text-sky-300">
                      Đáp án và lời giải
                    </h3>
                    <span className="text-xs font-semibold text-emerald-400">
                      Đáp án đúng: {selectedSolution.variant.correct_key || selectedSolution.variant.answer}
                    </span>
                  </div>

                  <div className="mt-3 text-xs leading-relaxed text-slate-300">
                    {selectedSolution.variant.solution_md ? (
                      <MathRenderer content={selectedSolution.variant.solution_md} />
                    ) : (
                      <p className="italic text-slate-500">
                        Chưa có lời giải chi tiết bằng Markdown cho câu hỏi này.
                      </p>
                    )}
                  </div>
                </section>
              </div>
            </div>

            {/* Dialog Footer Actions: STRICTLY 2 Buttons (Tạo lại & Duyệt biến thể) */}
            <div className="review-popup-actions flex items-center justify-end gap-3 border-t border-slate-800 bg-slate-950/80 px-6 py-4">
              {/* Nút 1: Tạo lại (data-review-regenerate) */}
              <button
                type="button"
                data-review-regenerate={true}
                disabled={isRegeneratingSingle || isApprovingSingle}
                onClick={handleRegenerateSingle}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white disabled:opacity-50"
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
                disabled={isRegeneratingSingle || isApprovingSingle || isSelectedVariantApproved}
                onClick={handleApproveSingle}
                className={`inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-xs font-semibold shadow-lg transition-all ${
                  isSelectedVariantApproved
                    ? 'cursor-not-allowed bg-emerald-700/60 text-emerald-200 opacity-80'
                    : 'bg-emerald-600 text-white shadow-emerald-600/30 hover:bg-emerald-500 disabled:opacity-50'
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
          </div>
        </div>
      )}
    </div>
  );
}
