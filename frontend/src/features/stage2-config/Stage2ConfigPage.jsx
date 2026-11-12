import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { stage1Path, stage3Path } from '../../sessionPaths.js';
import {
  AlertCircle,
  ArrowLeft,
  FileQuestion,
  Loader2,
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
 * 4. Tự động điều hướng sang Stage 3 khi hoàn tất
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
  const isMountedRef = useRef(true);
  const activeSessionIdRef = useRef(sessionId);

  // Tải dữ liệu phiên làm việc với khả năng cô lập tuyệt đối theo sessionId và số lượt tải (sessionOpRef)
  useEffect(() => {
    isMountedRef.current = true;
    activeSessionIdRef.current = sessionId;
    const thisOp = ++sessionOpRef.current;
    resyncOpRef.current += 1;
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

        // F02 / F08: Khi mở lại phiên partial_generated hoặc generating mà chưa có snapshot progress, nạp snapshot
        if (
          data &&
          (data.status === 'generating' || data.status === 'partial_generated') &&
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
      setIsSubmittingConfig(false);
      setIsRetryingGeneration(false);
    };
  }, [sessionId, loadSession, fetchGenSnapshot]);

  // F04 / F06: Callback tải lại snapshot phiên khi mất lịch sử SSE / nhận tín hiệu resync
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

        if (data?.progress) {
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  status: snapStatus || prev.status,
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
          setSession(data);
        }
        return data;
      }
      return null;
    },
    [fetchGenSnapshot, loadSession],
  );

  // Hook SSE kết nối khi ở trạng thái isGenerating
  const sseState = useSSEHook(sessionId, {
    enabled: isGenerating,
    initialProgress: session?.progress,
    initialQuestionStatuses: session?.question_statuses,
    initialResumeAfterEventId:
      session?.resume_after_event_id ?? session?.progress?.resume_after_event_id ?? null,
    initialStreamEpoch:
      session?.stream_epoch ?? session?.progress?.stream_epoch ?? null,
    onResync: handleResyncSnapshot,
  });

  // Xử lý nộp form cấu hình
  async function handleConfigSubmit(payload) {
    if (isSubmittingConfig) return;

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

    try {
      await saveConfig(targetSessionId, payload);
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
        resData?.error_message ||
        resData?.detail ||
        resData?.message ||
        err?.message;

      if (errorCode === 'ERR_CONFIG_CONFLICT') {
        setConfigError(
          `Cấu hình xung đột với Blueprint của đề bài (ERR_CONFIG_CONFLICT): ${
            typeof errorDetail === 'string'
              ? errorDetail
              : 'Vui lòng bỏ chọn các chế độ không tương thích.'
          }`,
        );
      } else {
        setConfigError(
          typeof errorDetail === 'string'
            ? errorDetail
            : 'Không thể lưu cấu hình hoặc khởi động tiến trình sinh đề.',
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
    if (isRetryingGeneration) return;

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
  }, [isRetryingGeneration, retryGen, sessionId, sseState]);


  // Trích xuất số lượng mã đề thật, không võ đoán mặc định 2 khi F5/reload
  const restoredStatuses = session?.question_statuses || {};
  const mergedStatuses = {
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
    (sseState.progress?.percent > 0 || sseState.progress?.completedCount > 0 || sseState.isDone)
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

  const isStreamDone = Boolean(
    sseState.isDone &&
    !sseState.isPartial &&
    String(sseState.progress?.session_status || '').trim().toLowerCase() !== 'partial_generated'
  );

  const isCompletedGenerated = Boolean(isBackendGenerated || isStreamDone);

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

  // Tự động chuyển hướng khi hoàn tất ở cấp độ container độc lập — CHỈ KHI hoàn tất 100% (không partial_generated)
  useEffect(() => {
    if (isGenerating && isCompletedGenerated) {
      const isPartial =
        mergedProgress?.session_status === 'partial_generated' ||
        Boolean(mergedProgress?.is_partial) ||
        (mergedProgress?.percent !== undefined && mergedProgress.percent < 100);

      if (!isPartial) {
        const timer = setTimeout(() => {
          handleCompleteRedirect();
        }, 1500);
        return () => clearTimeout(timer);
      }
    }
  }, [isGenerating, isCompletedGenerated, mergedProgress, handleCompleteRedirect]);

  // Giao diện khi đang tải phiên
  if (isLoadingSession) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center p-6 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-sky-400" />
        <p className="mt-4 text-sm font-medium text-slate-300">
          Đang tải thông tin đề thi và cấu trúc Blueprint...
        </p>
      </div>
    );
  }

  // Giao diện khi tải phiên thất bại
  if (sessionError) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <div
          role="alert"
          className="rounded-2xl border border-rose-500/40 bg-rose-950/40 p-6 text-center shadow-xl"
        >
          <AlertCircle className="mx-auto h-10 w-10 text-rose-400" />
          <h2 className="mt-3 text-lg font-bold text-white">
            Không thể tải phiên làm việc
          </h2>
          <p className="mt-1 text-sm text-rose-200">{sessionError}</p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => window.location.reload()}
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

  // Kiểm tra trạng thái phiên: nếu chưa xong Stage 1 (draft)
  if (session?.status === 'draft') {
    return (
      <div className="mx-auto max-w-2xl p-6">
        <div className="rounded-2xl border border-amber-500/40 bg-amber-950/30 p-8 text-center shadow-xl">
          <FileQuestion className="mx-auto h-12 w-12 text-amber-400" />
          <h2 className="mt-4 text-xl font-bold text-white">
            Đề nguồn chưa được xác nhận (Giai đoạn 1)
          </h2>
          <p className="mt-2 text-sm text-slate-300">
            Phiên làm việc này đang ở trạng thái bản thảo (<code>draft</code>). Bạn cần xác nhận nội dung đề nguồn ở Giai đoạn 1 để hệ thống tự động bóc tách Blueprint trước khi sang cấu hình sinh đề.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => navigate(stage1Path(sessionId))}
              className="rounded-xl bg-amber-600 px-5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-amber-600/30 hover:bg-amber-500"
            >
              Đến Giai đoạn 1 (Xác nhận đề gốc)
            </button>
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
            >
              Về Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }


  return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
      {/* Nút điều hướng phụ trên cùng */}
      <div className="mx-auto mb-6 max-w-5xl">
        <button
          type="button"
          onClick={() => navigate('/dashboard')}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Quay lại Bảng điều khiển (Dashboard)
        </button>
      </div>

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
          connectionState={sseState.connectionState}
          isDone={effectiveIsDone}
          error={retryError || sseState.error}
          reconnectCount={sseState.reconnectCount}
          onReconnect={sseState.reconnect}
          onRetryGeneration={handleRetryGeneration}
          isRetrying={isRetryingGeneration}
          onComplete={handleCompleteRedirect}
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
