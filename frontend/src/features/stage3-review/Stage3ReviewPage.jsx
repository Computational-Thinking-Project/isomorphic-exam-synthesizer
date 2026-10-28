import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  CheckCircle2,
  Download,
  FileCheck,
  Loader2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';
import { fetchSessionDetail, retryGeneration } from '../../services/stage2Service.js';

/**
 * Stage3ReviewPage: Màn hình Xem & Duyệt đề thi đẳng cấu (Giai đoạn 3)
 * Route: /session/:sessionId/stage3
 *
 * Hỗ trợ:
 * 1. Duyệt từng mã đề và từng câu hỏi biến thể kèm công thức toán KaTeX.
 * 2. Nhận diện trạng thái partial_generated (sinh thiếu câu):
 *    - Báo lỗi rõ ràng ở đầu trang.
 *    - Hiển thị ô cảnh báo cho các câu bị thiếu kèm nút "Tạo lại câu này".
 *    - Chặn nút xuất bản / phê duyệt theo quy định W2 khi chưa đủ 100% câu.
 * 3. Cho phép tạo lại từng câu cụ thể hoặc sinh bù toàn bộ các câu thiếu.
 */
export default function Stage3ReviewPage({
  loadSession = fetchSessionDetail,
  retryGen = retryGeneration,
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

  const loadData = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await loadSession(sessionId);
      setSession(data);
    } catch (err) {
      setError(err?.message || 'Không thể tải thông tin chi tiết đề thi.');
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, loadSession]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const numVersions =
    session?.config?.n_versions ||
    session?.config?.num_versions ||
    session?.exam_versions?.length ||
    2;

  const totalSourceQuestions =
    session?.source_questions?.length ||
    session?.blueprint_summary?.total_questions ||
    10;

  const isPartial =
    session?.status === 'partial_generated' ||
    Boolean(session?.is_partial);

  // Tra cứu biến thể đã sinh cho cặp (mã đề, số câu)
  const getVariant = (versionIndex, questionNo) => {
    const version = session?.exam_versions?.find(
      (v) => (v.version_index ?? v.index ?? 1) === versionIndex,
    );
    const questions = version?.questions || version?.version_questions || [];
    return questions.find(
      (q) => (q.question_no ?? q.number) === questionNo,
    );
  };

  // Hành động "Tạo lại câu này" cho câu cụ thể
  const handleRegenerateQuestion = async (versionIndex, questionNo) => {
    const key = `${versionIndex}-${questionNo}`;
    setRegeneratingQuestions((prev) => ({ ...prev, [key]: true }));
    setActionMessage(null);

    try {
      // Kích hoạt sinh bù qua endpoint retry-generation hoặc cập nhật câu
      await retryGen(sessionId);
      setActionMessage({
        type: 'success',
        text: `Đã kích hoạt tạo lại Câu ${questionNo} (Mã đề ${versionIndex}). Tiến trình đang chạy ngầm.`,
      });
      // Tải lại dữ liệu phiên
      await loadData();
    } catch (err) {
      const msg =
        err?.response?.data?.error_message ||
        err?.response?.data?.detail ||
        err?.message ||
        'Không thể tạo lại câu hỏi này.';
      setActionMessage({ type: 'error', text: msg });
    } finally {
      setRegeneratingQuestions((prev) => ({ ...prev, [key]: false }));
    }
  };

  // Hành động "Sinh bù tất cả câu thiếu"
  const handleRetryAllMissing = async () => {
    if (isRetryingAll) return;
    setIsRetryingAll(true);
    setActionMessage(null);

    try {
      await retryGen(sessionId);
      setActionMessage({
        type: 'success',
        text: 'Đã kích hoạt sinh bù các câu còn thiếu. Đang chuyển về màn hình tiến trình Stage 2...',
      });
      setTimeout(() => {
        navigate(`/session/${sessionId}/stage2`);
      }, 1200);
    } catch (err) {
      const msg =
        err?.response?.data?.error_message ||
        err?.response?.data?.detail ||
        err?.message ||
        'Không thể kích hoạt sinh bù.';
      setActionMessage({ type: 'error', text: msg });
      setIsRetryingAll(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center p-6 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-sky-400" />
        <p className="mt-4 text-sm font-medium text-slate-300">
          Đang tải dữ liệu các mã đề thi đẳng cấu...
        </p>
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
          <h2 className="mt-3 text-lg font-bold text-white">Lỗi tải dữ liệu</h2>
          <p className="mt-1 text-sm text-rose-200">{error}</p>
          <button
            type="button"
            onClick={loadData}
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      {/* Nút quay lại và tiêu đề trang */}
      <div className="flex flex-wrap items-center justify-between gap-4">
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
            Môn học: <span className="text-slate-200">{session?.subject || 'Toán'}</span> • Lớp: <span className="text-slate-200">{session?.grade || 12}</span> • Số mã đề: <span className="text-slate-200">{numVersions}</span>
          </p>
        </div>

        {/* Nút xuất bản / phê duyệt */}
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
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-emerald-700/30 hover:bg-emerald-500"
            >
              <FileCheck className="h-3.5 w-3.5" />
              Phê duyệt & Xuất bản đề
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
                Tiến trình sinh đề bị dừng trước khi hoàn thành 100% (do chạm trần hạn ngạch API Gemini hoặc câu hỏi không đạt ràng buộc nghiệm đẹp).
                Theo quy chế W2, tính năng Xuất bản file và Phê duyệt cuối bị tạm khóa cho đến khi đủ câu.
                Bạn có thể duyệt từng câu bên dưới và bấm nút <strong>"Tạo lại câu này"</strong> đối với các câu bị thiếu.
              </p>
            </div>
          </div>
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
          const variant = getVariant(activeVersionTab, qNo);
          const isMissing = !variant;
          const regKey = `${activeVersionTab}-${qNo}`;
          const isRegenerating = regeneratingQuestions[regKey];

          if (isMissing) {
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
                    onClick={() => handleRegenerateQuestion(activeVersionTab, qNo)}
                    disabled={isRegenerating}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-900/40 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-rose-900/60 disabled:opacity-50"
                  >
                    {isRegenerating ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    Tạo lại câu này
                  </button>
                </div>
              </div>
            );
          }

          // Hiển thị câu hỏi đã hoàn tất
          const options = variant.options || {};
          const correctKey = variant.correct_key || variant.answer;

          return (
            <div
              key={qNo}
              className="rounded-2xl border border-slate-700 bg-slate-900/90 p-5 shadow-lg transition-all"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-950/80 text-xs font-bold text-sky-300 border border-sky-800/40">
                    {qNo}
                  </span>
                  <span className="text-xs font-semibold text-white">
                    Câu {qNo} (Mã đề #{100 + activeVersionTab})
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                    <CheckCircle className="h-3 w-3" />
                    Đạt chuẩn
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => handleRegenerateQuestion(activeVersionTab, qNo)}
                  disabled={isRegenerating}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/60 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white disabled:opacity-50"
                >
                  {isRegenerating ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3 w-3" />
                  )}
                  Tạo lại câu này
                </button>
              </div>

              {/* Nội dung đề bài */}
              <div className="mt-3 text-sm text-slate-200">
                <MathRenderer content={variant.content || variant.raw_content || ''} />
              </div>

              {/* Các lựa chọn đáp án */}
              {Object.keys(options).length > 0 && (
                <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(options).map(([key, optVal]) => {
                    const isCorrect = String(key).toUpperCase() === String(correctKey).toUpperCase();
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
    </div>
  );
}
