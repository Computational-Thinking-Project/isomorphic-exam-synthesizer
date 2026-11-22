import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { exportPath, stage1Path, stage3Path, stage3PreviewPath } from '../../sessionPaths.js';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  FileQuestion,
  Loader2,
  Lock,
  RefreshCw,
} from 'lucide-react';
import Stage2ConfigCard from './Stage2ConfigCard.jsx';
import GenerationProgressView from './GenerationProgressView.jsx';
import { useSSE } from '../../hooks/useSSE.js';
import {
  fetchGenerationSnapshot,
  fetchSessionDetail,
  retryGeneration,
  saveSessionConfig,
  startGeneration,
} from '../../services/stage2Service.js';

/**
 * Stage2ConfigPage: Trang container chính cho Giai đoạn 2 (/session/:id/stage2)
 *
 * Điều phối:
 * 1. Tải thông tin phiên và trạng thái Blueprint từ API
 * 2. Hiển thị form cấu hình (Stage2ConfigCard)
 * 3. Kích hoạt sinh đề và hiển thị tiến trình SSE thời gian thực (GenerationProgressView)
 * 4. Người dùng chủ động chuyển sang Stage 3 khi hoàn tất
 */
/**
 * Trích xuất chuỗi thông báo lỗi an toàn từ response HTTP (tránh lỗi React child khi response trả về object)
 */
function extractErrorString(err, fallback = 'Không thể thực hiện thao tác.') {
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

export default function Stage2ConfigPage({
  loadSession = fetchSessionDetail,
  fetchGenSnapshot = fetchGenerationSnapshot,
  saveConfig = saveSessionConfig,
  startGen = startGeneration,
  retryGen = retryGeneration,
  useSSEHook = useSSE,
}) {
  const params = useParams();
  const sessionId = params.sessionId || params.id;
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [sessionError, setSessionError] = useState(null);

  const [isSubmittingConfig, setIsSubmittingConfig] = useState(false);
  const [configError, setConfigError] = useState(null);

  const [isGenerating, setIsGenerating] = useState(false);
  const [activeConfig, setActiveConfig] = useState(null);
  const [isRetryingGeneration, setIsRetryingGeneration] = useState(false);
  const [retryError, setRetryError] = useState(null);
  const [isNewRunActive, setIsNewRunActive] = useState(false);

  const submitOperationRef = useRef(0);
  const retryOperationRef = useRef(0);
  const sessionOpRef = useRef(0);
  const resyncOpRef = useRef(0);
  const sseErrorOpRef = useRef(0);
  const isMountedRef = useRef(true);
  const activeSessionIdRef = useRef(sessionId);

  // Tải dữ liệu phiên làm việc với khả năng cô lập tuyệt đối theo sessionId và số lượt tải (sessionOpRef)
  useEffect(() => {
    isMountedRef.current = true;
    activeSessionIdRef.current = sessionId;
    const thisOp = ++sessionOpRef.current;
    resyncOpRef.current += 1;
    sseErrorOpRef.current += 1;
    let active = true;

    // Vô hiệu hóa mọi lượt submit và retry đang chờ của phiên trước
    submitOperationRef.current += 1;
    retryOperationRef.current += 1;
    setIsSubmittingConfig(false);
    setIsRetryingGeneration(false);
    setRetryError(null);

    // Reset sạch sẽ trạng thái của container theo sessionId hiện tại
    setSession(null);
    setIsGenerating(false);
    setIsNewRunActive(false);
    setActiveConfig(null);
    setConfigError(null);
    setSessionError(null);

    async function load() {
      if (!sessionId) {
        setIsLoadingSession(false);
        setSessionError('Không có mã phiên làm việc hợp lệ.');
        return;
      }

      setIsLoadingSession(true);
      setSessionError(null);

      try {
        const data = await loadSession(sessionId);
        if (!active || !isMountedRef.current || sessionOpRef.current !== thisOp || activeSessionIdRef.current !== sessionId) {
          return;
        }

        // F02 / F08 / C8: Khi mở lại phiên partial_generated, generating hoặc generated mà chưa có snapshot progress, nạp snapshot
        if (
          data &&
          (data.status === 'generating' || data.status === 'partial_generated' || data.status === 'generated') &&
          !data.progress
        ) {
          try {
            const snap = await fetchGenSnapshot(sessionId);
            if (
              active &&
              isMountedRef.current &&
              sessionOpRef.current === thisOp &&
              activeSessionIdRef.current === sessionId &&
              snap
            ) {
              if (snap.progress) {
                data.progress = snap.progress;
              }
              if (snap.question_statuses && Object.keys(snap.question_statuses).length > 0) {
                data.question_statuses = {
                  ...(data.question_statuses || {}),
                  ...snap.question_statuses,
                };
              }
              const snapStatus =
                snap.status ||
                snap.session_status ||
                snap.progress?.session_status ||
                snap.progress?.status;
              if (snapStatus) {
                data.status = snapStatus;
              }
              if (snap.generation_error_code) {
                data.generation_error_code = snap.generation_error_code;
              }
              if (snap.stream_epoch) {
                data.stream_epoch = snap.stream_epoch;
              }
              if (snap.resume_after_event_id !== undefined && snap.resume_after_event_id !== null) {
                data.resume_after_event_id = snap.resume_after_event_id;
              }
            }
          } catch {
            // Không có generation-snapshot hoặc chưa triển khai -> giữ nguyên data
          }
        }

        if (!active || !isMountedRef.current || sessionOpRef.current !== thisOp || activeSessionIdRef.current !== sessionId) {
          return;
        }

        setSession(data);

        // F07: Nếu session đã ở trạng thái generating, generated hoặc hoàn thành một phần (partial_generated)
        if (
          data.status === 'generating' ||
          data.status === 'partial_generated' ||
          data.status === 'generated'
        ) {
          setIsGenerating(true);
        }
        if (data.config) {
          setActiveConfig(data.config);
        }
      } catch (err) {
        if (!active || !isMountedRef.current || sessionOpRef.current !== thisOp || activeSessionIdRef.current !== sessionId) {
          return;
        }
        setSessionError(err?.message || 'Không thể tải thông tin phiên làm việc.');
      } finally {
        if (active && isMountedRef.current && sessionOpRef.current === thisOp && activeSessionIdRef.current === sessionId) {
          setIsLoadingSession(false);
        }
      }
    }

    load();

    return () => {
      active = false;
      isMountedRef.current = false;
      submitOperationRef.current += 1;
      retryOperationRef.current += 1;
      sseErrorOpRef.current += 1;
      setIsSubmittingConfig(false);
      setIsRetryingGeneration(false);
    };
  }, [sessionId, loadSession, fetchGenSnapshot]);

  // F04 / F06 / P2: Callback tải lại snapshot phiên khi mất lịch sử SSE / nhận tín hiệu resync
  const handleResyncSnapshot = useCallback(
    async (sid) => {
      const thisSessionOp = sessionOpRef.current;
      const thisResyncOp = ++resyncOpRef.current;
      let data;
      try {
        data = await fetchGenSnapshot(sid);
      } catch {
        data = await loadSession(sid);
      }

      // F06: Kiểm tra lượt nạp phiên (sessionOpRef) và lượt resync (resyncOpRef) cùng sessionId
      if (
        isMountedRef.current &&
        sessionOpRef.current === thisSessionOp &&
        resyncOpRef.current === thisResyncOp &&
        activeSessionIdRef.current === sid
      ) {
        const snapStatus =
          data?.status ||
          data?.session_status ||
          data?.progress?.session_status ||
          data?.progress?.status;

        const errCode =
          data?.generation_error_code ||
          data?.error_code ||
          data?.progress?.generation_error_code ||
          data?.progress?.error_code ||
          null;

        const isFailed = String(snapStatus || '').trim().toLowerCase() === 'failed';
        const isGenerated = String(snapStatus || '').trim().toLowerCase() === 'generated';
        const isPartial = String(snapStatus || '').trim().toLowerCase() === 'partial_generated';

        if (data?.progress) {
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  status: snapStatus || prev.status,
                  generation_error_code: isGenerated ? null : (errCode ?? prev.generation_error_code ?? null),
                  progress: data.progress,
                  question_statuses: {
                    ...(prev.question_statuses || {}),
                    ...(data.question_statuses || {}),
                  },
                  stream_epoch: data.stream_epoch ?? prev.stream_epoch,
                  resume_after_event_id:
                    data.resume_after_event_id !== undefined
                      ? data.resume_after_event_id
                      : prev.resume_after_event_id,
                }
              : prev,
          );
        } else if (data) {
          setSession((prev) => ({
            ...(prev || {}),
            ...data,
            status: snapStatus || data.status || prev?.status,
            generation_error_code: isGenerated
              ? null
              : (errCode ?? data.generation_error_code ?? prev?.generation_error_code ?? null),
          }));
        }

        // P2 & C7: Giải phóng các cờ đang chạy khi snapshot xác nhận trạng thái terminal
        if (isFailed) {
          setIsGenerating(false);
          setIsNewRunActive(false);
        } else if (isGenerated || isPartial) {
          setIsNewRunActive(false);
          setIsGenerating(true);
        }

        return data;
      }
      return null;
    },
    [fetchGenSnapshot, loadSession],
  );

  // P1 & P2 (Duy): Đối soát trạng thái chính thống khi kết nối SSE nhận lỗi
  const handleSSEError = useCallback(
    async (err) => {
      const targetSessionId = sessionId;
      const thisSessionOp = sessionOpRef.current;
      const thisErrorOp = ++sseErrorOpRef.current;

      const isCurrent = () =>
        Boolean(
          isMountedRef.current &&
          activeSessionIdRef.current === targetSessionId &&
          sessionOpRef.current === thisSessionOp &&
          sseErrorOpRef.current === thisErrorOp,
        );

      if (!isCurrent()) return;

      const errCode =
        err?.generation_error_code ||
        err?.error_code ||
        err?.code ||
        null;

      // 1. Thử đối soát với snapshot chính thống từ backend
      let authoritativeFailed = false;
      let confirmedErrorCode = errCode;
      let confirmedProgress = null;

      try {
        const snap = await fetchGenSnapshot(targetSessionId);
        if (!isCurrent()) return;

        const snapStatus = String(
          snap?.status ||
          snap?.session_status ||
          snap?.progress?.session_status ||
          snap?.progress?.status ||
          '',
        ).trim().toLowerCase();

        if (snapStatus === 'failed') {
          authoritativeFailed = true;
          confirmedErrorCode = snap?.generation_error_code || errCode;
          confirmedProgress = snap?.progress;
        } else if (snapStatus === 'generated') {
          // C1: Backend đã hoàn thành toàn bộ (generated) -> Áp dụng terminal snapshot và trạng thái hoàn tất
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  status: 'generated',
                  generation_error_code: null,
                  ...(snap?.progress ? { progress: snap.progress } : {}),
                  question_statuses: {
                    ...(prev.question_statuses || {}),
                    ...(snap?.question_statuses || {}),
                  },
                  stream_epoch: snap?.stream_epoch ?? prev.stream_epoch,
                  resume_after_event_id:
                    snap?.resume_after_event_id !== undefined
                      ? snap.resume_after_event_id
                      : prev.resume_after_event_id,
                }
              : prev,
          );
          setIsNewRunActive(false);
          setIsGenerating(true);
          return;
        } else if (snapStatus === 'partial_generated') {
          // C1: Backend đã hoàn thành một phần (partial_generated) -> Áp dụng terminal snapshot, giữ câu thiếu và khả năng retry
          const errCodeFromSnap =
            snap?.generation_error_code ||
            snap?.error_code ||
            snap?.progress?.generation_error_code ||
            snap?.progress?.error_code ||
            errCode ||
            null;
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  status: 'partial_generated',
                  generation_error_code: errCodeFromSnap ?? prev.generation_error_code ?? null,
                  ...(snap?.progress ? { progress: snap.progress } : {}),
                  question_statuses: {
                    ...(prev.question_statuses || {}),
                    ...(snap?.question_statuses || {}),
                  },
                  stream_epoch: snap?.stream_epoch ?? prev.stream_epoch,
                  resume_after_event_id:
                    snap?.resume_after_event_id !== undefined
                      ? snap.resume_after_event_id
                      : prev.resume_after_event_id,
                }
              : prev,
          );
          setIsNewRunActive(false);
          setIsGenerating(true);
          return;
        } else if (snapStatus === 'generating') {
          // Backend vẫn đang chạy -> lỗi SSE chỉ là transport mạng tạm thời.
          // Giữ nguyên giao diện để người dùng tiếp tục theo dõi và có thể kết nối lại; KHÔNG ép sang failed!
          return;
        }
      } catch {
        if (!isCurrent()) return;

        // Fallback kiểm tra qua loadSession nếu fetchGenSnapshot không khả dụng
        try {
          const latest = await loadSession(targetSessionId);
          if (!isCurrent()) return;

          const latestStatus = String(latest?.status || '').trim().toLowerCase();
          if (latestStatus === 'failed') {
            authoritativeFailed = true;
            confirmedErrorCode = latest?.generation_error_code || errCode;
          } else if (latestStatus === 'generated') {
            setSession((prev) =>
              prev
                ? {
                    ...prev,
                    status: 'generated',
                    generation_error_code: null,
                    ...(latest?.progress ? { progress: latest.progress } : {}),
                    question_statuses: {
                      ...(prev.question_statuses || {}),
                      ...(latest?.question_statuses || {}),
                    },
                    stream_epoch: latest?.stream_epoch ?? prev.stream_epoch,
                    resume_after_event_id:
                      latest?.resume_after_event_id !== undefined
                        ? latest.resume_after_event_id
                        : prev.resume_after_event_id,
                  }
                : prev,
            );
            setIsNewRunActive(false);
            setIsGenerating(true);
            return;
          } else if (latestStatus === 'partial_generated') {
            const errCodeFromLatest =
              latest?.generation_error_code || latest?.error_code || errCode || null;
            setSession((prev) =>
              prev
                ? {
                    ...prev,
                    status: 'partial_generated',
                    generation_error_code: errCodeFromLatest ?? prev.generation_error_code ?? null,
                    ...(latest?.progress ? { progress: latest.progress } : {}),
                    question_statuses: {
                      ...(prev.question_statuses || {}),
                      ...(latest?.question_statuses || {}),
                    },
                    stream_epoch: latest?.stream_epoch ?? prev.stream_epoch,
                    resume_after_event_id:
                      latest?.resume_after_event_id !== undefined
                        ? latest.resume_after_event_id
                        : prev.resume_after_event_id,
                  }
                : prev,
            );
            setIsNewRunActive(false);
            setIsGenerating(true);
            return;
          } else if (latestStatus === 'generating') {
            return;
          }
        } catch {
          // Bỏ qua lỗi mạng trong fallback
        }
      }

      // Kiểm tra lại trước nhánh cập nhật cuối
      if (!isCurrent()) return;

      // 2. Chỉ chuyển session sang failed khi backend xác nhận authoritative failed,
      // HOẶC khi payload từ server là explicit terminal job error (không phải network/transport error)
      const isExplicitJobError = Boolean(
        err?.is_job_error === true ||
        err?.event === 'job_error' ||
        err?.event === 'failed' ||
        (errCode && [
          'ERR_MODEL_TIMEOUT',
          'ERR_GENERATION_FAILED',
          'ERR_GENERATION_INTERRUPTED',
          'ERR_WORKER_CRASHED',
          'ERR_CONFIG_INVALID',
        ].includes(errCode)),
      );

      if (authoritativeFailed || isExplicitJobError) {
        setSession((prev) =>
          prev
            ? {
                ...prev,
                status: 'failed',
                generation_error_code: confirmedErrorCode || prev.generation_error_code || null,
                ...(confirmedProgress ? { progress: confirmedProgress } : {}),
              }
            : prev,
        );
        setIsGenerating(false);
        setIsNewRunActive(false);
      }
    },
    [fetchGenSnapshot, loadSession, sessionId],
  );

  // P2: Đồng bộ dọn dẹp cờ tiến trình sinh khi session chuyển sang failed từ bất kỳ nguồn dữ liệu nào
  useEffect(() => {
    if (session?.status === 'failed' && (isGenerating || isNewRunActive)) {
      setIsGenerating(false);
      setIsNewRunActive(false);
    }
  }, [session?.status, isGenerating, isNewRunActive]);

  const isTerminalSession = Boolean(
    session?.status &&
      ['generated', 'partial_generated', 'failed', 'reviewed', 'approved', 'exported'].includes(
        session.status,
      ),
  );
  const shouldConnectSSE = Boolean(
    isGenerating && (isNewRunActive || !isTerminalSession),
  );

  // Hook SSE kết nối khi cần theo dõi tiến trình thực tế (C4)
  const sseState = useSSEHook(sessionId, {
    enabled: shouldConnectSSE,
    initialProgress: session?.progress,
    initialQuestionStatuses: session?.question_statuses,
    initialResumeAfterEventId:
      session?.resume_after_event_id ?? session?.progress?.resume_after_event_id ?? null,
    initialStreamEpoch:
      session?.stream_epoch ?? session?.progress?.stream_epoch ?? null,
    onResync: handleResyncSnapshot,
    onError: handleSSEError,
  });

  const isPostStage2Locked = ['reviewed', 'approved', 'exported'].includes(session?.status);
  const isFinalExportLocked = ['approved', 'exported'].includes(session?.status);

  // Xử lý nộp form cấu hình
  async function handleConfigSubmit(payload) {
    if (isSubmittingConfig || isPostStage2Locked) return;

    const isBlueprintReady = Boolean(
      session?.status !== 'draft' &&
      session?.blueprint_summary?.is_ready === true &&
      Array.isArray(session?.blueprint_summary?.supported_modes),
    );
    if (!isBlueprintReady) {
      setConfigError('Đề nguồn chưa hoàn tất phân tích Blueprint. Vui lòng quay lại Giai đoạn 1 để xác nhận đề gốc.');
      return;
    }

    const thisOpId = ++submitOperationRef.current;
    const targetSessionId = sessionId;

    setIsSubmittingConfig(true);
    setConfigError(null);

    let configSaved = false;
    try {
      await saveConfig(targetSessionId, payload);
      configSaved = true;
      if (
        !isMountedRef.current ||
        submitOperationRef.current !== thisOpId ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setActiveConfig(payload);

      // Kích hoạt background generation
      await startGen(targetSessionId);
      if (
        !isMountedRef.current ||
        submitOperationRef.current !== thisOpId ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setSession((prev) => (prev ? { ...prev, status: 'generating' } : prev));
      setIsNewRunActive(true);
      setIsGenerating(true);
    } catch (err) {
      if (
        !isMountedRef.current ||
        submitOperationRef.current !== thisOpId ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      const resData = err?.response?.data;
      const errorCode = resData?.code || resData?.detail?.code || err?.code;
      const errorDetail =
        resData?.detail?.message ||
        resData?.error_message ||
        resData?.detail ||
        resData?.message ||
        err?.message;

      if (!configSaved && errorCode === 'ERR_CONFIG_CONFLICT') {
        setConfigError(
          `Cấu hình xung đột với Blueprint của đề bài (ERR_CONFIG_CONFLICT): ${
            typeof errorDetail === 'string'
              ? errorDetail
              : 'Vui lòng bỏ chọn các chế độ không tương thích.'
          }`,
        );
      } else {
        const message = typeof errorDetail === 'string' ? errorDetail : 'Đã xảy ra lỗi. Vui lòng thử lại.';
        const numbers = resData?.detail?.question_numbers;
        const affected = Array.isArray(numbers) ? ` Câu: ${numbers.join(', ')}.` : '';
        setConfigError(
          `${configSaved ? 'Đã lưu cấu hình. Không thể bắt đầu sinh đề: ' : 'Không thể lưu cấu hình: '}${message}${errorCode ? ` (${errorCode})` : ''}${affected}`,
        );
      }
    } finally {
      if (isMountedRef.current && submitOperationRef.current === thisOpId) {
        setIsSubmittingConfig(false);
      }
    }
  }

  const handleCompleteRedirect = useCallback(() => {
    navigate(stage3Path(sessionId));
  }, [navigate, sessionId]);

  const handleRetryGeneration = useCallback(async () => {
    if (isRetryingGeneration || isPostStage2Locked) return;

    const thisRetryOp = ++retryOperationRef.current;
    const targetSessionId = sessionId;

    setIsRetryingGeneration(true);
    setRetryError(null);

    try {
      await retryGen(targetSessionId);
      if (
        !isMountedRef.current ||
        retryOperationRef.current !== thisRetryOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      setSession((prev) =>
        prev
          ? {
              ...prev,
              status: 'generating',
              generation_error_code: null,
            }
          : prev,
      );
      setIsNewRunActive(true);
      setIsGenerating(true);
      sseState.reconnect();
    } catch (err) {
      if (
        !isMountedRef.current ||
        retryOperationRef.current !== thisRetryOp ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }
      const msg = extractErrorString(
        err,
        'Không thể kích hoạt tiến trình sinh bù từ máy chủ.',
      );
      setRetryError(msg);
    } finally {
      if (isMountedRef.current && retryOperationRef.current === thisRetryOp) {
        setIsRetryingGeneration(false);
      }
    }
  }, [isPostStage2Locked, isRetryingGeneration, retryGen, sessionId, sseState]);


  // Trích xuất số lượng mã đề thật, không võ đoán mặc định 2 khi F5/reload
  const restoredStatuses = session?.question_statuses || {};
  const isConfirmedTerminalRun = Boolean(
    session?.status &&
      ['generated', 'partial_generated', 'reviewed', 'approved', 'exported'].includes(session.status) &&
      !isNewRunActive,
  );

  const mergedStatuses =
    isConfirmedTerminalRun && Object.keys(restoredStatuses).length > 0
      ? {
          ...(sseState.questionStatuses || {}),
          ...restoredStatuses,
        }
      : {
          ...restoredStatuses,
          ...(sseState.questionStatuses || {}),
        };

  const statusVersions = Object.keys(mergedStatuses).map((k) =>
    parseInt(k.split('-')[0], 10),
  );
  const maxVersionFromStatuses =
    statusVersions.length > 0
      ? Math.max(...statusVersions.filter((n) => !isNaN(n) && n > 0))
      : null;

  const derivedNumVersions =
    activeConfig?.n_versions ||
    activeConfig?.num_versions ||
    (session?.exam_versions?.length > 0 ? session.exam_versions.length : null) ||
    sseState.progress?.n_versions ||
    sseState.progress?.num_versions ||
    (session?.progress?.totalCount && session?.source_questions?.length
      ? Math.round(session.progress.totalCount / session.source_questions.length)
      : null) ||
    (maxVersionFromStatuses && maxVersionFromStatuses > 0 ? maxVersionFromStatuses : null);

  const mergedProgress =
    isConfirmedTerminalRun && session?.progress
      ? session.progress
      : (sseState.progress?.percent > 0 || sseState.progress?.completedCount > 0 || sseState.isDone)
        ? sseState.progress
        : session?.progress || (sseState.progress?.hasData ? sseState.progress : null);

  // F03 / F07 / F09: Tách trạng thái kết thúc lượt sinh khỏi trạng thái kết nối SSE.
  // F09: Chỉ hoàn tất chuyển Stage 3 khi backend xác nhận 'generated' qua snapshot/detail HOẶC sự kiện kết thúc 'done' từ stream SSE.
  // Khi tiến độ 100% nhưng backend vẫn báo 'generating' (hoặc chưa có done), TUYỆT ĐỐI TIẾP TỤC THEO DÕI, không chuyển Stage 3!
  const currentSnapshotStatus =
    session?.status ||
    session?.progress?.session_status ||
    session?.progress?.status ||
    mergedProgress?.session_status ||
    mergedProgress?.status;

  const normalizedSnapshotStatus = String(currentSnapshotStatus || '').trim().toLowerCase();
  const isGeneratingStatus =
    normalizedSnapshotStatus === 'generating' ||
    String(session?.status || '').trim().toLowerCase() === 'generating';

  const isBackendGenerated =
    !isGeneratingStatus &&
    (normalizedSnapshotStatus === 'generated' ||
      String(session?.status || '').trim().toLowerCase() === 'generated');

  const isSnapshotFinished = Boolean(
    !isGeneratingStatus &&
    (isBackendGenerated ||
      normalizedSnapshotStatus === 'partial_generated' ||
      String(session?.status || '').trim().toLowerCase() === 'partial_generated' ||
      (Boolean(session?.progress?.isDone) && !isGeneratingStatus) ||
      (Boolean(mergedProgress?.isDone) && !isGeneratingStatus))
  );

  const effectiveIsDone = isNewRunActive
    ? sseState.isDone
    : (isSnapshotFinished || sseState.isDone);

  // Giao diện khi đang tải phiên
  if (isLoadingSession) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center p-6 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-highlight" />
        <p className="mt-4 text-sm font-medium text-ink">
          Đang tải thông tin đề thi và cấu trúc Blueprint...
        </p>
      </div>
    );
  }

  // Giao diện khi tải phiên thất bại
  if (sessionError) {
    return (
      <div className="paper-ui min-h-screen bg-canvas text-ink p-6">
        <div className="mx-auto max-w-xl">
          <div
            role="alert"
            className="rounded-2xl border border-danger-border bg-danger-soft p-6 text-center shadow-paper"
          >
            <AlertCircle className="mx-auto h-10 w-10 text-danger" />
            <h2 className="mt-3 text-lg font-bold text-strong">
              Không thể tải phiên làm việc
            </h2>
            <p className="mt-1 text-sm text-danger">{sessionError}</p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={() => window.location.reload()}
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

  // Kiểm tra trạng thái phiên: nếu chưa xong Stage 1 (draft)
  if (session?.status === 'draft') {
    return (
      <div className="paper-ui min-h-screen bg-canvas text-ink p-6">
        <div className="mx-auto max-w-2xl">
          <div className="rounded-2xl border border-accent-border bg-accent-soft p-8 text-center shadow-paper">
            <FileQuestion className="mx-auto h-12 w-12 text-accent-ink" />
            <h2 className="mt-4 text-xl font-bold text-strong">
              Đề nguồn chưa được xác nhận (Giai đoạn 1)
            </h2>
            <p className="mt-2 text-sm text-ink">
              Xác nhận nội dung đề nguồn và chờ phân tích cấu trúc đề trước khi tạo mã đề.
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={() => navigate(stage1Path(sessionId))}
                className="rounded-xl bg-accent px-5 py-2.5 text-xs font-semibold text-strong shadow-soft  hover:bg-accent"
              >
                Đến Giai đoạn 1 (Xác nhận đề gốc)
              </button>
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                className="rounded-xl border border-line px-4 py-2 text-xs font-medium text-ink hover:bg-rail"
              >
                Về Dashboard
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Kiểm tra trạng thái phiên: nếu phiên sinh đề bị thất bại (failed)
  if (session?.status === 'failed' && !isGenerating && !isNewRunActive) {
    const errorCode =
      session?.generation_error_code ||
      session?.error_code ||
      session?.progress?.generation_error_code ||
      session?.progress?.error_code;

    return (
      <div className="paper-ui min-h-screen bg-canvas text-ink p-6">
        <div className="mx-auto max-w-2xl">
          <div
            role="alert"
            className="rounded-2xl border border-danger-border bg-danger-soft p-8 text-center shadow-paper"
          >
            <AlertCircle className="mx-auto h-12 w-12 text-danger" />
            <h2 className="mt-4 text-xl font-bold text-strong">
              Tiến trình sinh đề thi bị gián đoạn hoặc thất bại
            </h2>
            <p className="mt-2 text-sm text-ink">
              Phiên sinh đề gặp sự cố trong quá trình xử lý. Bạn có thể kích hoạt thử lại để tiếp tục tiến trình sinh đề mà không mất cấu hình đã thiết lập.
            </p>
            {errorCode && (
              <div className="mt-4 inline-flex items-center gap-2 rounded-lg border border-danger-border bg-danger-soft px-3.5 py-1.5 text-xs font-mono font-medium text-danger">
                <span>Mã lỗi:</span>
                <strong className="text-strong">{errorCode}</strong>
              </div>
            )}
            {retryError && (
              <div className="mt-3 text-xs text-danger" role="status">
                {retryError}
              </div>
            )}
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={handleRetryGeneration}
                disabled={isRetryingGeneration}
                className="inline-flex items-center gap-1.5 rounded-xl bg-danger px-5 py-2.5 text-xs font-semibold text-white shadow-soft  hover:bg-danger disabled:opacity-50"
              >
                {isRetryingGeneration ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                {isRetryingGeneration ? 'Đang kích hoạt lại…' : 'Thử lại tiến trình sinh đề'}
              </button>
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                className="rounded-xl border border-line px-4 py-2 text-xs font-medium text-ink hover:bg-rail"
              >
                Về Dashboard
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Khóa deep-link Stage 2 khi phiên đã sang Rà soát cuối hoặc đã phê duyệt/xuất bản
  if (isPostStage2Locked && !isGenerating && !isNewRunActive) {
    return (
      <div className="paper-ui mx-auto max-w-2xl p-6">
        <div
          role="status"
          className="rounded-2xl border border-approved-border bg-approved-bg p-8 text-center shadow-paper"
        >
          <Lock className="mx-auto h-12 w-12 text-approved-ink" />
          <h2 className="mt-4 text-xl font-bold text-strong">
            {isFinalExportLocked
              ? 'Đề thi đã được phê duyệt và khóa cấu hình'
              : 'Phiên đã hoàn tất duyệt từng câu'}
          </h2>
          <p className="mt-2 text-sm text-ink">
            {isFinalExportLocked
              ? 'Phiên làm việc đã chốt ở bước phê duyệt cuối cùng. Không thể thay đổi cấu hình hay khởi chạy lại quá trình sinh đề.'
              : 'Toàn bộ biến thể của phiên này đã được duyệt. Hãy chuyển sang màn hình Rà soát cuối để xáo trộn và phê duyệt đề.'}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              type="button"
              data-testid="stage2-btn-goto-locked-target"
              onClick={() => navigate(isFinalExportLocked ? exportPath(sessionId) : stage3PreviewPath(sessionId))}
              className="inline-flex items-center gap-2 rounded-xl bg-approved-ink px-5 py-2.5 text-xs font-semibold text-white shadow-soft  hover:bg-approved-ink"
            >
              <span>{isFinalExportLocked ? 'Tới màn hình Xuất bản' : 'Tới màn hình Rà soát cuối'}</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="rounded-xl border border-line px-4 py-2 text-xs font-medium text-ink hover:bg-rail"
            >
              Về Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="paper-ui min-h-screen bg-canvas text-ink px-4 py-8 sm:px-6 lg:px-8">
      {/* Nút điều hướng phụ trên cùng */}
      <div className="mx-auto mb-6 max-w-5xl">
        <button
          type="button"
          onClick={() => navigate('/dashboard')}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted hover:text-strong"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Quay lại Bảng điều khiển (Dashboard)
        </button>
      </div>

      {['generated', 'partial_generated'].includes(session?.status) && !isNewRunActive && (
        <section className="mx-auto mb-6 max-w-5xl rounded-2xl border border-line bg-surface p-6">
          <h1 className="text-xl font-bold text-strong">Thông tin lần sinh</h1>
          <p className="mt-2 text-sm text-muted">Cấu hình đã dùng cho bộ đề hiện tại · Chỉ đọc</p>
          <dl className="mt-4 flex flex-wrap gap-6 text-sm">
            <div><dt>Số mã đề</dt><dd className="font-semibold">{derivedNumVersions}</dd></div>
            <div><dt>Số câu mỗi đề</dt><dd className="font-semibold">{session?.source_questions?.length ?? 'Chưa có dữ liệu'}</dd></div>
            <div><dt>Xáo trộn câu hỏi</dt><dd>{session?.config?.ordering_preferences?.shuffle_questions ? 'Bật' : 'Tắt'}</dd></div>
            <div><dt>Xáo trộn đáp án</dt><dd>{session?.config?.ordering_preferences?.shuffle_options ? 'Bật' : 'Tắt'}</dd></div>
          </dl>
          <button type="button" onClick={handleCompleteRedirect} className="mt-5 rounded-xl bg-highlight px-4 py-3 font-semibold text-white">Quay lại duyệt câu hỏi</button>
        </section>
      )}
      {isGenerating ? (
        <GenerationProgressView
          sessionId={sessionId}
          sessionTitle={session?.title}
          numVersions={derivedNumVersions}
          totalSourceQuestions={
            session?.source_questions?.length || session?.blueprint_summary?.total_questions || 10
          }
          progress={
            mergedProgress ||
            (session?.status === 'partial_generated'
              ? { session_status: 'partial_generated', is_partial: true }
              : null)
          }
          questionStatuses={mergedStatuses}
          warnings={sseState.warnings}
          connectionState={
            isConfirmedTerminalRun && session?.status === 'generated'
              ? 'completed'
              : sseState.connectionState
          }
          isDone={effectiveIsDone}
          error={
            isConfirmedTerminalRun && session?.status === 'generated'
              ? null
              : retryError || sseState.error
          }
          reconnectCount={sseState.reconnectCount}
          onReconnect={sseState.reconnect}
          onRetryGeneration={handleRetryGeneration}
          isRetrying={isRetryingGeneration}
          onComplete={handleCompleteRedirect}
          onBackToDashboard={() => navigate('/dashboard')}
        />
      ) : (
        <Stage2ConfigCard
          session={session}
          initialConfig={activeConfig || session?.config}
          onSubmit={handleConfigSubmit}
          isSubmitting={isSubmittingConfig}
          error={configError}
          onBack={() => navigate('/dashboard')}
          onReturnToStage1={() => navigate(stage1Path(sessionId))}
        />
      )}
    </div>
  );
}
