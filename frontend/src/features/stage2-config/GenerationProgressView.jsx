import { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Clock,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  WifiOff,
} from 'lucide-react';

/**
 * 5 trạng thái câu hỏi thân thiện theo đúng yêu cầu người dùng:
 * 1. 🔍 Đang phân tích (analyzing / preparing)
 * 2. ⏳ Đang soạn nội dung (generating)
 * 3. 🔍 Đang kiểm tra (validating)
 * 4. 🔄 Đang tinh chỉnh (retrying)
 * 5. ✅ Hoàn thành (done)
 */
const STATUS_CONFIGS = {
  analyzing: {
    label: 'Đang phân tích',
    badgeClass: 'bg-purple-950/60 text-purple-300 border-purple-700/60',
    icon: Search,
  },
  generating: {
    label: 'Đang soạn nội dung',
    badgeClass: 'bg-sky-950/60 text-sky-300 border-sky-700/60',
    icon: Loader2,
    spin: true,
  },
  validating: {
    label: 'Đang kiểm tra',
    badgeClass: 'bg-amber-950/60 text-amber-300 border-amber-700/60',
    icon: Search,
  },
  retrying: {
    label: 'Đang tinh chỉnh',
    badgeClass: 'bg-orange-950/60 text-orange-300 border-orange-700/60',
    icon: RefreshCw,
    spin: true,
  },
  done: {
    label: 'Hoàn thành',
    badgeClass: 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60',
    icon: CheckCircle,
  },
  missing: {
    label: 'Chưa sinh',
    badgeClass: 'bg-rose-950/60 text-rose-300 border-rose-700/60',
    icon: AlertCircle,
  },
  pending: {
    label: 'Chờ xử lý',
    badgeClass: 'bg-slate-800/80 text-slate-400 border-slate-700',
    icon: Clock,
  },
};

export default function GenerationProgressView({
  sessionId,
  sessionTitle = '',
  numVersions = null,
  totalSourceQuestions = 10,
  progress = {},
  questionStatuses = {},
  warnings = [],
  connectionState = 'connected',
  isDone = false,
  error = null,
  reconnectCount = 0,
  onReconnect,
  onRetryGeneration,
  isRetrying = false,
  onComplete,
}) {
  // Nếu numVersions chưa có, thử suy ra từ các key dạng "${version_index}-${question_no}" trong questionStatuses
  const statusVersions = Object.keys(questionStatuses || {}).map((k) =>
    parseInt(k.split('-')[0], 10),
  );
  const maxVersionFromStatuses =
    statusVersions.length > 0
      ? Math.max(...statusVersions.filter((n) => !isNaN(n) && n > 0))
      : null;
  const effectiveNumVersions =
    numVersions || (maxVersionFromStatuses && maxVersionFromStatuses > 0 ? maxVersionFromStatuses : null);

  const [activeVersionTab, setActiveVersionTab] = useState(1);
  const totalVariants = effectiveNumVersions ? effectiveNumVersions * totalSourceQuestions : null;
  const percent = Math.min(100, Math.max(0, progress.percent ?? 0));
  const completedCount = progress.completedCount ?? 0;

  const isPartial =
    progress?.session_status === 'partial_generated' ||
    Boolean(progress?.is_partial) ||
    (isDone && (progress?.percent ?? 100) < 100);

  // Auto redirect sau khi hoàn tất 1.5 giây — CHỈ KHI sinh đủ 100% đề (không partial_generated)
  useEffect(() => {
    if (isDone && !isPartial && onComplete) {
      const timer = setTimeout(() => {
        onComplete();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [isDone, isPartial, onComplete]);

  // Đảm bảo tab mã đề luôn hợp lệ nếu số lượng mã đề thay đổi
  useEffect(() => {
    if (effectiveNumVersions && activeVersionTab > effectiveNumVersions) {
      setActiveVersionTab(1);
    }
  }, [effectiveNumVersions, activeVersionTab]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {/* Khối Header trạng thái kết nối & tiến độ tổng quát */}
      <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-6 shadow-xl backdrop-blur-sm sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-sky-500/20 px-3 py-1 text-xs font-semibold text-sky-300">
                Giai đoạn 2: Tiến trình sinh đề AI
              </span>
              <span className="text-xs text-slate-400">
                Mã phiên: {sessionId}
              </span>
            </div>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">
              {sessionTitle || 'Đang tạo các biến thể đề thi'}
            </h2>
          </div>

          {/* Badge trạng thái kết nối thời gian thực SSE */}
          <div className="flex items-center gap-2">
            {connectionState === 'connected' && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-3 py-1 text-xs font-medium text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                Kết nối thời gian thực
              </span>
            )}
            {connectionState === 'reconnecting' && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-950/40 px-3 py-1 text-xs font-medium text-amber-300">
                <Loader2 className="h-3 w-3 animate-spin text-amber-400" />
                Đang kết nối lại ({reconnectCount})
              </span>
            )}
            {(connectionState === 'disconnected' || connectionState === 'failed') && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/40 bg-rose-950/40 px-3 py-1 text-xs font-medium text-rose-300">
                <WifiOff className="h-3 w-3" />
                Mất kết nối
              </span>
            )}
            {isDone && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-3 py-1 text-xs font-medium text-emerald-300">
                <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
                Đã hoàn tất
              </span>
            )}
          </div>
        </div>

        {/* Thanh tiến trình lớn */}
        <div className="mt-6">
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold text-white">
              {percent}%
            </span>
            <div className="text-right text-xs text-slate-400">
              <span className="font-semibold text-slate-200">
                {totalVariants ? `${completedCount} / ${totalVariants}` : `${completedCount} câu`}
              </span>{' '}
              {totalVariants ? 'câu hỏi đã hoàn tất' : 'đã xử lý'}
            </div>
          </div>

          {/* Progress bar line */}
          <div className="mt-3 h-3.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full transition-all duration-500 ease-out ${
                isDone
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                  : 'bg-gradient-to-r from-sky-500 via-indigo-500 to-sky-400'
              }`}
              style={{ width: `${percent}%` }}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
            <p className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-sky-400" />
              {progress.message || (isDone ? 'Hoàn thành sinh tất cả các mã đề.' : 'Đang xử lý song song các mã đề...')}
            </p>

            {progress.estimatedSeconds !== null && !isDone && (
              <p className="flex items-center gap-1 text-slate-300">
                <Clock className="h-3.5 w-3.5 text-slate-400" />
                Thời gian ước tính: ~{progress.estimatedSeconds}s
              </p>
            )}
          </div>
        </div>

        {/* Thông báo lỗi và nút kết nối lại */}
        {error && (
          <div
            role="alert"
            className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-rose-200"
          >
            <div className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
            {onReconnect && (
              <button
                type="button"
                onClick={onReconnect}
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/40 bg-rose-900/40 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-900/60"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Kết nối lại
              </button>
            )}
          </div>
        )}

        {/* Khối cảnh báo nghiệp vụ (warnings) */}
        {warnings && warnings.length > 0 && (
          <div
            role="status"
            className="mt-6 rounded-xl border border-amber-500/40 bg-amber-950/30 p-4 text-xs text-amber-200"
          >
            <div className="flex items-center gap-2 font-semibold text-amber-300">
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
              <span>Có {warnings.length} cảnh báo trong quá trình sinh đề (tiến trình vẫn đang tiếp tục):</span>
            </div>
            <ul className="mt-2 list-disc pl-5 space-y-1 text-amber-200/90">
              {warnings.map((w, idx) => {
                const prefix =
                  w?.version_index && w?.question_no
                    ? `Mã đề ${w.version_index}, Câu ${w.question_no}: `
                    : '';
                const msg =
                  w?.message ||
                  w?.warning_message ||
                  w?.warning ||
                  (typeof w === 'string' ? w : JSON.stringify(w));
                return (
                  <li key={idx}>
                    <strong>{prefix}</strong>
                    {msg}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Thông báo kết thúc tiến trình: Phân biệt sinh đủ 100% với hoàn thành một phần (partial_generated) */}
        {isDone && !isPartial && (
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-emerald-500/40 bg-emerald-950/30 p-5 text-emerald-200">
            <div className="flex items-center gap-3">
              <CheckCircle className="h-6 w-6 shrink-0 text-emerald-400" />
              <div>
                <h4 className="text-sm font-bold text-white">
                  {effectiveNumVersions
                    ? `Đã sinh xong ${effectiveNumVersions} mã đề thi đẳng cấu!`
                    : 'Đã sinh xong tất cả các mã đề thi đẳng cấu!'}
                </h4>
                <p className="mt-0.5 text-xs text-emerald-300/90">
                  Hệ thống đang tự động chuyển hướng sang trang xem và duyệt đề (Stage 3)...
                </p>
              </div>
            </div>

            {onComplete && (
              <button
                type="button"
                onClick={onComplete}
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-emerald-700/30 hover:bg-emerald-500"
              >
                Xem đề ngay
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}

        {isDone && isPartial && (
          <div
            role="status"
            className="mt-6 rounded-xl border border-amber-500/50 bg-amber-950/40 p-5 text-amber-200"
          >
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-amber-400" />
                <div>
                  <h4 className="text-sm font-bold text-white">
                    Tiến trình hoàn thành một phần (<code>partial_generated</code>)
                  </h4>
                  <p className="mt-1 text-xs text-amber-200/90">
                    Đã tạo được <strong className="text-white">{completedCount}</strong>
                    {totalVariants ? ` / ${totalVariants}` : ''} câu hỏi ({percent}%).
                    {totalVariants && completedCount < totalVariants
                      ? ` Còn thiếu ${totalVariants - completedCount} câu do gặp lỗi hoặc hạn mức sinh đề.`
                      : ' Một số câu hỏi chưa thể hoàn tất đầy đủ.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {onRetryGeneration && (
                  <button
                    type="button"
                    onClick={onRetryGeneration}
                    disabled={isRetrying}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/50 bg-amber-600 px-3.5 py-2 text-xs font-semibold text-white shadow-lg shadow-amber-600/30 hover:bg-amber-500 disabled:opacity-50"
                  >
                    {isRetrying ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    Sinh bù các câu còn thiếu
                  </button>
                )}
                {onComplete && (
                  <button
                    type="button"
                    onClick={onComplete}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-700"
                  >
                    Đến Stage 3 xem các câu đã sinh
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Lưới câu hỏi thời gian thực: Tabs theo từng mã đề */}
      <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-6 shadow-xl backdrop-blur-sm sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <h3 className="text-lg font-bold text-white">
              Chi tiết trạng thái từng câu hỏi
            </h3>
            <p className="mt-0.5 text-xs text-slate-400">
              Mọi bước kiểm tra và tinh chỉnh đều được hệ thống tự động hoàn thiện.
            </p>
          </div>

          {/* Version tabs: Đề 1, Đề 2, ... */}
          {effectiveNumVersions ? (
            <div className="flex items-center gap-2">
              {Array.from({ length: effectiveNumVersions }, (_, i) => i + 1).map((vIdx) => {
                const isTabActive = activeVersionTab === vIdx;
                return (
                  <button
                    key={vIdx}
                    type="button"
                    onClick={() => setActiveVersionTab(vIdx)}
                    className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                      isTabActive
                        ? 'bg-sky-600 text-white shadow-md shadow-sky-600/30'
                        : 'border border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    Mã đề #{vIdx}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>

        {/* Lưới các câu hỏi trong mã đề được chọn hoặc trạng thái chờ đồng bộ */}
        {effectiveNumVersions ? (
          <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: totalSourceQuestions }, (_, i) => i + 1).map((qNo) => {
              const key = `${activeVersionTab}-${qNo}`;
              const item = questionStatuses[key];
              const qWarning = warnings.find(
                (w) => w?.version_index === activeVersionTab && w?.question_no === qNo,
              );

              // QUAN TRỌNG (Sửa lỗi P2 theo review của Philip và Quỳnh):
              // Khi isDone=true nhưng phiên ở trạng thái partial_generated (sinh một phần):
              // Nếu câu hỏi không có bản ghi status hoặc status !== 'done', tuyệt đối KHÔNG ĐƯỢC
              // đánh dấu là 'done'. Phải hiển thị trạng thái 'missing' (Chưa sinh / Cần sinh bù).
              let statusKey;
              if (item?.status) {
                statusKey = item.status;
              } else if (isDone && !isPartial) {
                statusKey = 'done';
              } else if (isDone && isPartial) {
                statusKey = 'missing';
              } else {
                statusKey = 'pending';
              }

              const isMissing = statusKey === 'missing';
              const statusConfig = STATUS_CONFIGS[statusKey] || STATUS_CONFIGS.pending;
              const Icon = statusConfig.icon;

              return (
                <div
                  key={key}
                  className={`flex items-center justify-between rounded-xl border p-3.5 transition-all ${
                    isMissing
                      ? 'border-rose-500/40 bg-rose-950/20 hover:border-rose-400'
                      : qWarning
                      ? 'border-amber-500/60 bg-amber-950/20 hover:border-amber-400'
                      : 'border-slate-800 bg-slate-800/50 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
                        isMissing
                          ? 'bg-rose-900/60 text-rose-200'
                          : 'bg-slate-700/80 text-slate-200'
                      }`}
                    >
                      {qNo}
                    </span>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-semibold text-white">
                          Câu {qNo} (Đề {activeVersionTab})
                        </p>
                        {qWarning && (
                          <span
                            title={qWarning.message || 'Có cảnh báo'}
                            className="inline-flex items-center text-amber-400"
                          >
                            <AlertTriangle className="h-3 w-3" />
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 truncate max-w-[140px]">
                        {qWarning?.message ||
                          item?.message ||
                          (statusKey === 'done'
                            ? 'Đã hoàn thành'
                            : isMissing
                            ? 'Chưa sinh (cần sinh bù)'
                            : 'Đang xếp hàng...')}
                      </p>
                    </div>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium ${statusConfig.badgeClass}`}
                  >
                    <Icon className={`h-3 w-3 ${statusConfig.spin ? 'animate-spin' : ''}`} />
                    {statusConfig.label}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="mt-6 rounded-xl border border-slate-800 bg-slate-800/30 p-8 text-center">
            <Loader2 className="mx-auto h-7 w-7 animate-spin text-sky-400" />
            <h4 className="mt-3 text-sm font-semibold text-white">
              Đang đồng bộ cấu hình số lượng mã đề từ máy chủ...
            </h4>
            <p className="mt-1 text-xs text-slate-400">
              Tiến trình sinh đề AI vẫn đang chạy bình thường ở trên. Lưới chi tiết từng câu hỏi sẽ xuất hiện ngay khi cấu hình được nhận diện.
            </p>
          </div>
        )}

        <div className="mt-6 rounded-xl border border-slate-800 bg-slate-800/30 p-3 text-center text-xs text-slate-400">
          💡 <em>Lưu ý: Bạn không cần can thiệp trong quá trình sinh. Sau khi hoàn tất, bạn có thể xem lại và bấm "Tạo lại câu này" cho từng câu cụ thể ở Bước 3.</em>
        </div>
      </div>
    </div>
  );
}
