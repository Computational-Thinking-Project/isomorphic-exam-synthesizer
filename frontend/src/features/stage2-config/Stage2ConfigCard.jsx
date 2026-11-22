import { useId, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Check,
  Layers,
  Loader2,
  Shuffle,
  Sparkles,
} from 'lucide-react';

/**
 * Stage2ConfigCard: Form cấu hình sinh đề thi đẳng cấu (Stage 2 - TASK-206)
 *
 * Chức năng:
 * - Chọn số lượng mã đề N in [1, 4]
 * - Lựa chọn các chế độ biến thể hợp lệ dựa trên cấu trúc đề (chống xung đột)
 * - Tùy chọn xáo trộn thứ tự câu hỏi
 * - Thẻ tóm tắt tự động tổng số lượng câu hỏi và mã đề cần sinh
 * - Gửi cấu hình và xử lý trạng thái lỗi/xung đột rõ ràng
 */
export default function Stage2ConfigCard({
  session,
  initialConfig = null,
  initialNumVersions,
  onSubmit,
  isSubmitting = false,
  error = null,
  onBack = null,
  onReturnToStage1 = null,
}) {
  const formId = useId();

  // Danh sách các chế độ từ cấu trúc đề
  const isBlueprintReady = Boolean(
    session?.status !== 'draft' &&
    session?.blueprint_summary?.is_ready === true &&
    Array.isArray(session?.blueprint_summary?.supported_modes),
  );

  // Giá trị khởi tạo từ cấu hình đã lưu hoặc mặc định
  const defaultNumVersions = initialNumVersions ?? initialConfig?.n_versions ?? initialConfig?.num_versions ?? 2;

  const [numVersions, setNumVersions] = useState(defaultNumVersions);
  // Issue #45: Mặc định tắt (false) cho cả hai tùy chọn xáo trộn
  const [shuffleQuestions, setShuffleQuestions] = useState(
    initialConfig?.ordering_preferences?.shuffle_questions ?? false,
  );
  const [shuffleOptions, setShuffleOptions] = useState(
    initialConfig?.ordering_preferences?.shuffle_options ?? false,
  );
  const [validationError, setValidationError] = useState('');

  const totalQuestions = session?.source_questions?.length || session?.blueprint_summary?.total_questions || 0;
  const totalVariantsToGenerate = numVersions * totalQuestions;

  async function handleSubmit(event) {
    event.preventDefault();
    setValidationError('');

    if (!isBlueprintReady) {
      setValidationError('Đề nguồn chưa hoàn tất phân tích cấu trúc đề. Vui lòng quay lại Giai đoạn 1 để xác nhận đề gốc.');
      return;
    }

    if (numVersions < 1 || numVersions > 4) {
      setValidationError('Số lượng mã đề phải từ 1 đến 4.');
      return;
    }

    // Issue #45: Chuẩn hóa payload không gửi user-selected variation modes
    // Backend tự suy ra từ canonical cấu trúc đề khi nhận active_variation_modes: []
    const payload = {
      n_versions: Number(numVersions),
      active_variation_modes: [],
      ordering_preferences: {
        shuffle_questions: Boolean(shuffleQuestions),
        shuffle_options: Boolean(shuffleOptions),
      },
    };

    if (onSubmit) {
      await onSubmit(payload);
    }
  }

  return (
    <div className="paper-ui mx-auto max-w-4xl rounded-2xl border border-line bg-surface p-6 shadow-paper backdrop-blur-sm sm:p-8">
      {/* Header tóm tắt phiên làm việc */}
      <div className="mb-8 border-b border-line pb-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-support-bg px-3 py-1 text-xs font-semibold text-highlight">
                Bước 2 · Tạo mã đề
              </span>
              <span className="text-xs text-muted">
                Môn: {session?.subject || 'Toán'} • Khối {session?.grade || 12}
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-strong sm:text-3xl">
              {session?.title || 'Cấu hình tạo đề thi đẳng cấu'}
            </h1>
          </div>

          <div className="rounded-xl border border-line bg-rail px-4 py-3 text-right">
            <p className="text-xs text-muted">Đề nguồn</p>
            <p className="text-xl font-bold text-highlight">
              {totalQuestions} <span className="text-sm font-normal text-ink">câu hỏi</span>
            </p>
          </div>
        </div>
      </div>

      {/* Thông báo lỗi nếu có */}
      {(error || validationError) && (
        <div
          role="alert"
          className="mb-6 flex items-start gap-3 rounded-xl border border-danger-border bg-danger-soft p-4 text-danger"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger" />
          <div className="text-sm">
            <p className="font-semibold">Cần điều chỉnh cấu hình:</p>
            <p>{validationError || error}</p>
          </div>
        </div>
      )}

      {!isBlueprintReady && (
        <div className="mb-6 rounded-xl border border-accent-border bg-accent-soft p-4 text-center text-sm text-accent-ink">
          <p className="font-semibold">Chưa có thông tin cấu trúc đề khả dụng</p>
          <p className="mt-1 text-xs text-accent-ink">
            Đề nguồn chưa hoàn tất phân tích cấu trúc đề hoặc thiếu dữ liệu câu hỏi. Vui lòng quay lại Giai đoạn 1 để xác nhận đề gốc.
          </p>
          {onReturnToStage1 && (
            <button
              type="button"
              onClick={onReturnToStage1}
              className="mt-3 inline-flex items-center rounded-lg border border-accent-border bg-accent-soft px-3 py-1.5 text-xs font-semibold text-accent-ink hover:bg-accent-soft"
            >
              Quay về Giai đoạn 1
            </button>
          )}
        </div>
      )}

      <form id={formId} onSubmit={handleSubmit} className="space-y-8">
        <fieldset disabled={isSubmitting || !isBlueprintReady} className="space-y-8">
        {/* Phần 1: Chọn số lượng mã đề */}
        <div>
          <label className="block text-base font-semibold text-strong">
            1. Số lượng mã đề cần tạo
          </label>
          <p className="mt-1 text-sm text-muted">
            Các mã đề giữ cấu trúc của đề nguồn đã xác nhận.
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[1, 2, 3, 4].map((n) => {
              const isSelected = numVersions === n;
              return (
                <button
                  key={n}
                  type="button"
                  onClick={() => setNumVersions(n)}
                  aria-pressed={isSelected}
                  disabled={isSubmitting}
                  className={`flex flex-col items-center justify-center rounded-xl border p-4 transition-all ${
                    isSelected
                      ? 'border-support-line bg-support-bg text-strong shadow-soft  ring-2 ring-highlight'
                      : 'border-line bg-rail text-ink hover:border-line hover:bg-rail'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  <span className="text-3xl font-extrabold">{n}</span>
                  <span className="mt-1 text-xs text-muted">
                    {n === 1 ? '1 phiên bản' : `${n} mã đề`}
                  </span>
                  {isSelected && (
                    <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-support-bg px-2 py-0.5 text-[11px] font-medium text-highlight">
                      <Check className="h-3 w-3" /> Đã chọn
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Phần 3: Tùy chọn xáo trộn ban đầu */}
        <div>
          <label className="block text-base font-semibold text-strong">
            2. Thứ tự câu hỏi và đáp án
          </label>
          <p className="mt-1 text-sm text-muted">
            Hai lựa chọn này được <strong>lưu</strong> khi cấu hình. Thứ tự câu hỏi và phương án chỉ được <strong>áp dụng</strong> khi bạn chốt ở màn Xem trước, sau khi duyệt đủ câu.
          </p>

          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-line bg-rail p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  id="shuffle-questions-checkbox"
                  checked={shuffleQuestions}
                  disabled={isSubmitting}
                  onChange={(e) => setShuffleQuestions(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-line bg-rail text-highlight focus:ring-highlight focus:ring-offset-surface"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-strong">
                      Xáo trộn thứ tự câu hỏi giữa các mã đề
                    </span>
                    <Shuffle className="h-3.5 w-3.5 text-muted" />
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    Đổi vị trí câu hỏi giữa các mã đề.
                  </p>
                </div>
              </label>
            </div>

            <div className="rounded-xl border border-line bg-rail p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  id="shuffle-options-checkbox"
                  checked={shuffleOptions}
                  disabled={isSubmitting}
                  onChange={(e) => setShuffleOptions(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-line bg-rail text-highlight focus:ring-highlight focus:ring-offset-surface"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-strong">
                      Xáo trộn thứ tự các đáp án A, B, C, D
                    </span>
                    <Shuffle className="h-3.5 w-3.5 text-highlight" />
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    Đổi vị trí các phương án; đáp án đúng được cập nhật tương ứng.
                  </p>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Phần 4: Thẻ tóm tắt thông số trực quan */}
        <div className="rounded-xl border border-support-line bg-support-bg p-5">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-highlight" />
            <div>
              <h3 className="text-sm font-semibold text-highlight">
                Tóm tắt cấu hình sinh đề:
              </h3>
              <p className="mt-1 text-sm text-ink">
                Hệ thống sẽ sinh <strong className="text-strong">{numVersions} mã đề</strong>, mỗi mã gồm <strong className="text-strong">{totalQuestions} câu hỏi tương đương</strong>.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
                <span className="flex items-center gap-1.5 rounded-lg bg-rail px-2.5 py-1 text-ink">
                  <Layers className="h-3.5 w-3.5 text-highlight" />
                  Tổng cộng: <strong className="text-strong">{totalVariantsToGenerate}</strong> câu hỏi biến thể
                </span>
                <span className="flex items-center gap-1.5 rounded-lg bg-rail px-2.5 py-1 text-ink">
                  <Sparkles className="h-3.5 w-3.5 text-highlight" />
                  Giữ cấu trúc đề nguồn
                </span>
                {shuffleQuestions && (
                  <span className="flex items-center gap-1.5 rounded-lg bg-rail px-2.5 py-1 text-ink">
                    <Shuffle className="h-3.5 w-3.5 text-accent-ink" />
                    Đã chọn đảo thứ tự câu hỏi
                  </span>
                )}
                {shuffleOptions && (
                  <span className="flex items-center gap-1.5 rounded-lg bg-rail px-2.5 py-1 text-ink">
                    <Shuffle className="h-3.5 w-3.5 text-highlight" />
                    Đã chọn đảo thứ tự phương án
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
        </fieldset>

        {/* Nút hành động */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-4">
          {onBack ? (
            <button
              type="button"
              onClick={onBack}
              disabled={isSubmitting}
              className="rounded-xl border border-line px-5 py-2.5 text-sm font-medium text-ink hover:bg-rail hover:text-strong disabled:opacity-50"
            >
              Quay về Dashboard
            </button>
          ) : (
            <div />
          )}

          <button
            type="submit"
            disabled={isSubmitting || !isBlueprintReady}
            className="flex items-center gap-2 rounded-xl bg-highlight px-6 py-3 text-sm font-semibold text-white shadow-soft  hover:bg-highlight focus:outline-none focus:ring-2 focus:ring-highlight focus:ring-offset-2 focus:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Đang lưu cấu hình & khởi động...
              </>
            ) : (
              <>
                Bắt đầu sinh đề
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
