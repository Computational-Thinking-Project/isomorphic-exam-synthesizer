import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
  fetchSessionDetail,
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
export default function Stage2ConfigPage({
  loadSession = fetchSessionDetail,
  saveConfig = saveSessionConfig,
  startGen = startGeneration,
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

  // Tải dữ liệu phiên làm việc
  useEffect(() => {
    let active = true;

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
        if (!active) return;
        setSession(data);

        // Nếu session đã ở trạng thái generating hoặc đã được cấu hình trước đó
        if (data.status === 'generating') {
          setIsGenerating(true);
        }
        if (data.config) {
          setActiveConfig(data.config);
        }
      } catch (err) {
        if (!active) return;
        setSessionError(err?.message || 'Không thể tải thông tin phiên làm việc.');
      } finally {
        if (active) {
          setIsLoadingSession(false);
        }
      }
    }

    load();

    return () => {
      active = false;
    };
  }, [sessionId, loadSession]);

  // Hook SSE kết nối khi ở trạng thái isGenerating
  const sseState = useSSEHook(sessionId, {
    enabled: isGenerating,
  });

  // Xử lý nộp form cấu hình
  async function handleConfigSubmit(payload) {
    if (isSubmittingConfig) return;

    setIsSubmittingConfig(true);
    setConfigError(null);

    try {
      await saveConfig(sessionId, payload);
      setActiveConfig(payload);

      // Kích hoạt background generation
      await startGen(sessionId);
      setIsGenerating(true);
    } catch (err) {
      if (err?.code === 'ERR_CONFIG_CONFLICT') {
        setConfigError(
          'Cấu hình xung đột với Blueprint của đề bài (ERR_CONFIG_CONFLICT). Vui lòng bỏ chọn các chế độ không tương thích.',
        );
      } else {
        setConfigError(
          err?.message || 'Không thể lưu cấu hình hoặc khởi động tiến trình sinh đề.',
        );
      }
    } finally {
      setIsSubmittingConfig(false);
    }
  }

  function handleCompleteRedirect() {
    navigate(`/session/${sessionId}/stage3`);
  }

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
              onClick={() => navigate(`/session/${sessionId}/stage1`)}
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
          numVersions={activeConfig?.num_versions || 2}
          totalSourceQuestions={
            session?.source_questions?.length || session?.blueprint_summary?.total_questions || 10
          }
          progress={sseState.progress}
          questionStatuses={sseState.questionStatuses}
          connectionState={sseState.connectionState}
          isDone={sseState.isDone}
          error={sseState.error}
          reconnectCount={sseState.reconnectCount}
          onReconnect={sseState.reconnect}
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
        />
      )}
    </div>
  );
}
