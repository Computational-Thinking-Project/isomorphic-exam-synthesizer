import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../../index.css';
import GenerationProgressView from './GenerationProgressView.jsx';

function SSEProgressPreviewApp() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [percent, setPercent] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [isDone, setIsDone] = useState(false);
  const [connectionState, setConnectionState] = useState('connected');
  const [questionStatuses, setQuestionStatuses] = useState({});

  const totalQuestions = 6;
  const numVersions = 2;
  const totalVariants = totalQuestions * numVersions;

  function resetSimulation() {
    setIsPlaying(false);
    setPercent(0);
    setCompletedCount(0);
    setIsDone(false);
    setConnectionState('connected');
    setQuestionStatuses({});
  }

  useEffect(() => {
    if (!isPlaying) return;

    let currentStep = 0;
    const interval = setInterval(() => {
      currentStep += 1;
      const newPercent = Math.min(100, Math.round((currentStep / 24) * 100));
      setPercent(newPercent);

      // Mô phỏng diễn tiến từng câu hỏi theo 5 trạng thái thân thiện:
      // 1. analyzing -> 2. generating -> 3. validating -> 4. retrying -> 5. done
      const qIndex = Math.min(totalVariants, Math.ceil(currentStep / 2));
      const vIdx = ((qIndex - 1) % numVersions) + 1;
      const qNo = Math.floor((qIndex - 1) / numVersions) + 1;
      const key = `${vIdx}-${qNo}`;

      let currentStatus = 'analyzing';
      if (currentStep % 4 === 1) currentStatus = 'analyzing';
      else if (currentStep % 4 === 2) currentStatus = 'generating';
      else if (currentStep % 4 === 3) currentStatus = 'validating';
      else currentStatus = 'done';

      setQuestionStatuses((prev) => ({
        ...prev,
        [key]: {
          version_index: vIdx,
          question_no: qNo,
          status: currentStatus,
          message:
            currentStatus === 'analyzing'
              ? 'Đang phân tích mô hình'
              : currentStatus === 'generating'
              ? 'Đang soạn nội dung biến thể'
              : currentStatus === 'validating'
              ? 'Đang kiểm tra lời giải'
              : 'Đã hoàn thành',
        },
      }));

      if (currentStatus === 'done') {
        setCompletedCount((c) => Math.min(totalVariants, c + 1));
      }

      if (currentStep >= 24) {
        setIsDone(true);
        setIsPlaying(false);
        setPercent(100);
        setCompletedCount(totalVariants);
        clearInterval(interval);
      }
    }, 600);

    return () => clearInterval(interval);
  }, [isPlaying, totalVariants]);

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100">
      {/* Thanh điều khiển preview */}
      <div className="mx-auto mb-8 max-w-5xl rounded-xl border border-slate-700 bg-slate-900 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-white">
              Bảng điều khiển Giả lập SSE Stream (Progress Preview)
            </h2>
            <p className="text-xs text-slate-400">
              Kiểm tra hiệu ứng cập nhật tiến trình và các trạng thái câu hỏi thời gian thực
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setIsPlaying((p) => !p)}
              className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500"
            >
              {isPlaying ? 'Tạm dừng mô phỏng' : isDone ? 'Chạy lại từ đầu' : 'Bắt đầu mô phỏng'}
            </button>
            <button
              type="button"
              onClick={resetSimulation}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
            >
              Reset
            </button>
            <button
              type="button"
              onClick={() =>
                setConnectionState((prev) =>
                  prev === 'connected' ? 'reconnecting' : prev === 'reconnecting' ? 'disconnected' : 'connected',
                )
              }
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700"
            >
              Đổi trạng thái mạng ({connectionState})
            </button>
          </div>
        </div>
      </div>

      <GenerationProgressView
        sessionId="mock-session-stage2-001"
        sessionTitle="Đề kiểm tra Giải tích 12 — Chương 1 (Tiến trình xem trước)"
        numVersions={numVersions}
        totalSourceQuestions={totalQuestions}
        progress={{
          percent,
          completedCount,
          totalCount: totalVariants,
          message: isPlaying ? 'Đang sinh câu hỏi...' : isDone ? 'Hoàn tất' : 'Sẵn sàng',
          estimatedSeconds: isDone ? 0 : Math.max(0, 15 - Math.round(percent / 7)),
        }}
        questionStatuses={questionStatuses}
        connectionState={connectionState}
        isDone={isDone}
        reconnectCount={1}
        onReconnect={() => setConnectionState('connected')}
        onComplete={() => alert('Đã hoàn tất! Điều hướng sang Stage 3')}
      />
    </div>
  );
}

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(<SSEProgressPreviewApp />);
}
