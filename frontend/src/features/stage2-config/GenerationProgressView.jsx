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
    badgeClass: 'bg-support-bg text-highlight border-support-line',
    icon: Search,
  },
  generating: {
    label: 'Đang soạn nội dung',
    badgeClass: 'bg-support-bg text-highlight border-support-line',
    icon: Loader2,
    spin: true,
  },
  validating: {
    label: 'Đang kiểm tra',
    badgeClass: 'bg-accent-soft text-accent-ink border-accent-border',
    icon: Search,
  },
  retrying: {
    label: 'Đang tinh chỉnh',
    badgeClass: 'bg-accent-soft text-accent-ink border-accent-border',
    icon: RefreshCw,
    spin: true,
  },
  done: {
    label: 'Hoàn thành',
    badgeClass: 'bg-approved-bg text-approved-ink border-approved-border',
    icon: CheckCircle,
  },
  missing: {
    label: 'Chưa sinh',
    badgeClass: 'bg-danger-soft text-danger border-danger-border',
    icon: AlertCircle,
  },
  pending: {
    label: 'Chờ xử lý',
    badgeClass: 'bg-rail text-muted border-line',
    icon: Clock,
  },
};

export default function GenerationProgressView({
  sessionTitle = '',
  numVersions = null,
  totalSourceQuestions = null,
  progress = null,
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
  const totalVariants = effectiveNumVersions && totalSourceQuestions ? effectiveNumVersions * totalSourceQuestions : null;

  // F02: Phân biệt rõ ràng giữa "Chưa có dữ liệu snapshot" và "Đã xác nhận chưa lưu câu nào (0/4)"
  const hasSnapshotData = Boolean(
    progress &&
    (progress.hasData === true ||
     (progress.completedCount !== undefined && progress.completedCount !== null) ||
     (progress.percent !== undefined && progress.percent !== null))
  );

  const percent = hasSnapshotData ? Math.min(100, Math.max(0, progress.percent ?? 0)) : 0;
  const completedCount = hasSnapshotData ? (progress.completedCount ?? 0) : null;

  const isPartial =
    progress?.session_status === 'partial_generated' ||
    Boolean(progress?.is_partial) ||
    (isDone && (progress?.percent ?? 100) < 100);

  // Đảm bảo tab mã đề luôn hợp lệ nếu số lượng mã đề thay đổi
  useEffect(() => {
    if (effectiveNumVersions && activeVersionTab > effectiveNumVersions) {
      setActiveVersionTab(1);
    }
  }, [effectiveNumVersions, activeVersionTab]);

  return (
    <div className="paper-ui mx-auto max-w-5xl space-y-6">
      {/* Khối Header trạng thái kết nối & tiến độ tổng quát */}
      <div className="rounded-2xl border border-line bg-surface p-6 shadow-paper backdrop-blur-sm sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-support-bg px-3 py-1 text-xs font-semibold text-highlight">
                Bước 2 · Đang tạo mã đề
              </span>
            </div>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-strong">
              {sessionTitle || 'Đang tạo các biến thể đề thi'}
            </h2>
          </div>

          {/* Badge trạng thái kết nối thời gian thực SSE */}
          <div className="flex items-center gap-2">
            {connectionState === 'connected' && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-approved-border bg-approved-bg px-3 py-1 text-xs font-medium text-approved-ink">
                <span className="h-2 w-2 rounded-full bg-approved-ink animate-pulse" />
                Kết nối thời gian thực
              </span>
            )}
            {connectionState === 'reconnecting' && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-border bg-accent-soft px-3 py-1 text-xs font-medium text-accent-ink">
                <Loader2 className="h-3 w-3 animate-spin text-accent-ink" />
                Đang kết nối lại ({reconnectCount})
              </span>
            )}
            {(connectionState === 'disconnected' || connectionState === 'failed') && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-danger-border bg-danger-soft px-3 py-1 text-xs font-medium text-danger">
                <WifiOff className="h-3 w-3" />
                Mất kết nối
              </span>
            )}
            {isDone && !isPartial && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-approved-border bg-approved-bg px-3 py-1 text-xs font-medium text-approved-ink">
                <CheckCircle className="h-3.5 w-3.5 text-approved-ink" />
                Đã hoàn tất
              </span>
            )}
          </div>
        </div>

        {/* Thanh tiến trình lớn */}
        <div className="mt-6">
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold text-strong">
              {hasSnapshotData ? `${percent}%` : 'Đang cập nhật'}
            </span>
            <div className="text-right text-xs text-muted">
              <span className="font-semibold text-ink">
                {hasSnapshotData
                  ? (totalVariants ? `${completedCount} / ${totalVariants}` : `${completedCount} câu`)
                  : 'Chưa có dữ liệu tiến độ'}
              </span>{' '}
              {hasSnapshotData && (totalVariants ? 'câu hỏi đã hoàn tất' : 'đã xử lý')}
            </div>
          </div>

          {/* Progress bar line */}
          <div className="mt-3 h-3.5 w-full overflow-hidden rounded-full bg-rail">
            <div
              className={`h-full transition-all duration-500 ease-out ${
                isDone
                  ? 'bg-gradient-to-r from-approved-ink to-approved-ink'
                  : 'bg-gradient-to-r from-highlight via-highlight to-highlight'
              }`}
              style={{ width: `${hasSnapshotData ? percent : 0}%` }}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
            <p className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-highlight" />
              {hasSnapshotData
                ? (progress?.message || (isDone ? (isPartial ? 'Còn câu hỏi cần sinh bổ sung.' : 'Hoàn thành sinh tất cả các mã đề.') : 'Đang xử lý song song các mã đề...'))
                : 'Chưa có dữ liệu tiến độ cho phiên làm việc này.'}
            </p>

            {hasSnapshotData && progress?.estimatedSeconds !== null && progress?.estimatedSeconds !== undefined && !isDone && (
              <p className="flex items-center gap-1 text-ink">
                <Clock className="h-3.5 w-3.5 text-muted" />
                Thời gian ước tính: ~{progress.estimatedSeconds}s
              </p>
            )}
          </div>
        </div>

        {/* Thông báo lỗi và nút kết nối lại */}
        {error && (
          <div
            role="alert"
            className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger-border bg-danger-soft p-4 text-danger"
          >
            <div className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 shrink-0 text-danger" />
              <span>{error}</span>
            </div>
            {onReconnect && (
              <button
                type="button"
                onClick={onReconnect}
                className="inline-flex items-center gap-1.5 rounded-lg border border-danger-border bg-danger-soft px-3 py-1.5 text-xs font-semibold text-strong hover:bg-danger-soft"
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
            className="mt-6 rounded-xl border border-accent-border bg-accent-soft p-4 text-xs text-accent-ink"
          >
            <div className="flex items-center gap-2 font-semibold text-accent-ink">
              <AlertTriangle className="h-4 w-4 shrink-0 text-accent-ink" />
              <span>Có {warnings.length} cảnh báo trong quá trình sinh đề (tiến trình vẫn đang tiếp tục):</span>
            </div>
            <ul className="mt-2 list-disc pl-5 space-y-1 text-accent-ink">
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
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-approved-border bg-approved-bg p-5 text-approved-ink">
            <div className="flex items-center gap-3">
              <CheckCircle className="h-6 w-6 shrink-0 text-approved-ink" />
              <div>
                <h4 className="text-sm font-bold text-strong">
                  {effectiveNumVersions
                    ? `Đã sinh xong ${effectiveNumVersions} mã đề thi đẳng cấu!`
                    : 'Đã sinh xong tất cả các mã đề thi đẳng cấu!'}
                </h4>
                <p className="mt-0.5 text-xs text-approved-ink">
                  Hệ thống đang tự động chuyển hướng sang trang xem và duyệt đề (Stage 3)...
                </p>
              </div>
            </div>

            {onComplete && (
              <button
                type="button"
                onClick={onComplete}
                className="inline-flex items-center gap-1.5 rounded-xl bg-approved-ink px-4 py-2 text-xs font-semibold text-white shadow-soft  hover:bg-approved-ink"
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
            className="mt-6 rounded-xl border border-accent-border bg-accent-soft p-5 text-accent-ink"
          >
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-accent-ink" />
                <div>
                  <h4 className="text-sm font-bold text-strong">
                    Tiến trình hoàn thành một phần (<code>partial_generated</code>)
                  </h4>
                  <p className="mt-1 text-xs text-accent-ink">
                    {hasSnapshotData ? (
                      <>
                        Đã tạo được <strong className="text-strong">{completedCount}</strong>
                        {totalVariants ? ` / ${totalVariants}` : ''} câu hỏi ({percent}%).
                        {totalVariants && completedCount < totalVariants
                          ? ` Còn thiếu ${totalVariants - completedCount} câu do gặp lỗi hoặc hạn mức sinh đề.`
                          : ' Một số câu hỏi chưa thể hoàn tất đầy đủ.'}
                      </>
                    ) : (
                      'Chưa có dữ liệu tiến độ cho các câu hỏi của phiên làm việc này.'
                    )}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {onRetryGeneration && (
                  <button
                    type="button"
                    onClick={onRetryGeneration}
                    disabled={isRetrying}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-accent-border bg-accent px-3.5 py-2 text-xs font-semibold text-strong shadow-soft  hover:bg-accent disabled:opacity-50"
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
                    className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-rail px-4 py-2 text-xs font-semibold text-strong hover:bg-rail"
                  >
                    Duyệt các câu đã tạo
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Lưới câu hỏi thời gian thực: Tabs theo từng mã đề */}
      <div className="rounded-2xl border border-line bg-surface p-6 shadow-paper backdrop-blur-sm sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
          <div>
            <h3 className="text-lg font-bold text-strong">
              Chi tiết trạng thái từng câu hỏi
            </h3>
            <p className="mt-0.5 text-xs text-muted">
              Theo dõi các câu đã tạo trước khi chuyển sang duyệt.
            </p>
          </div>

          {/* Version tabs: Đề 1, Đề 2, ... */}
          {effectiveNumVersions ? (
            <div className="flex flex-wrap items-center gap-2">
              {Array.from({ length: effectiveNumVersions }, (_, i) => i + 1).map((vIdx) => {
                const isTabActive = activeVersionTab === vIdx;
                return (
                  <button
                    key={vIdx}
                    type="button"
                    onClick={() => setActiveVersionTab(vIdx)}
                    aria-pressed={isTabActive}
                    className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                      isTabActive
                        ? 'bg-highlight text-white shadow-md '
                        : 'border border-line bg-rail text-ink hover:bg-rail'
                    }`}
                  >
                    Đề {vIdx}
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
                      ? 'border-danger-border bg-danger-soft hover:border-danger-border'
                      : qWarning
                      ? 'border-accent-border bg-accent-soft hover:border-accent-border'
                      : 'border-line bg-rail hover:border-line'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
                        isMissing
                          ? 'bg-danger-soft text-danger'
                          : 'bg-rail text-ink'
                      }`}
                    >
                      {qNo}
                    </span>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <p className="text-xs font-semibold text-strong">
                          Câu {qNo} (Đề {activeVersionTab})
                        </p>
                        {qWarning && (
                          <span
                            title={qWarning.message || 'Có cảnh báo'}
                            className="inline-flex items-center text-accent-ink"
                          >
                            <AlertTriangle className="h-3 w-3" />
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-muted truncate max-w-[140px]">
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
          <div className="mt-6 rounded-xl border border-line bg-rail p-8 text-center">
            <Loader2 className="mx-auto h-7 w-7 animate-spin text-highlight" />
            <h4 className="mt-3 text-sm font-semibold text-strong">
              Đang đồng bộ cấu hình số lượng mã đề từ máy chủ...
            </h4>
            <p className="mt-1 text-xs text-muted">
              Tiến trình sinh đề AI vẫn đang chạy bình thường ở trên. Lưới chi tiết từng câu hỏi sẽ xuất hiện ngay khi cấu hình được nhận diện.
            </p>
          </div>
        )}

        <div className="mt-6 rounded-xl border border-line bg-rail p-3 text-center text-xs text-muted">
          💡 <em>Lưu ý: Bạn không cần can thiệp trong quá trình sinh. Sau khi hoàn tất, bạn có thể xem lại và bấm "Tạo lại câu này" cho từng câu cụ thể ở Bước 3.</em>
        </div>
      </div>
    </div>
  );
}
