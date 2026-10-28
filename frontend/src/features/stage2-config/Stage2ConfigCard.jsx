import { useId, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  HelpCircle,
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
 * - Lựa chọn các chế độ biến thể hợp lệ dựa trên Blueprint (chống xung đột)
 * - Tùy chọn xáo trộn thứ tự câu hỏi (shuffle_questions)
 * - Thẻ tóm tắt tự động tổng số lượng câu hỏi và mã đề cần sinh
 * - Gửi cấu hình và xử lý trạng thái lỗi/xung đột rõ ràng
 */
export default function Stage2ConfigCard({
  session,
  initialConfig = null,
  onSubmit,
  isSubmitting = false,
  error = null,
  onBack,
}) {
  const formId = useId();

  // Danh sách các chế độ từ Blueprint
  const supportedModes = session?.blueprint_summary?.supported_modes || [];
  const isBlueprintReady = Boolean(
    session?.blueprint_summary && session.blueprint_summary.is_ready !== false,
  );

  // Giá trị khởi tạo từ cấu hình đã lưu hoặc mặc định
  const defaultNumVersions = initialConfig?.n_versions ?? initialConfig?.num_versions ?? 2;
  const availableModes = supportedModes.filter((m) => m.is_available !== false).map((m) => m.id);

  // Phân biệt: nếu initialConfig có mảng active_variation_modes (kể cả rỗng []), giữ nguyên lựa chọn
  // Nếu chưa có config (null/undefined), chọn tất cả các mode khả dụng
  const hasSavedModes =
    Array.isArray(initialConfig?.active_variation_modes) ||
    Array.isArray(initialConfig?.variation_modes);

  const rawConfiguredModes = Array.isArray(initialConfig?.active_variation_modes)
    ? initialConfig.active_variation_modes
    : Array.isArray(initialConfig?.variation_modes)
    ? initialConfig.variation_modes
    : null;

  const defaultModes = hasSavedModes
    ? rawConfiguredModes.filter((id) => availableModes.includes(id))
    : availableModes;

  const [numVersions, setNumVersions] = useState(defaultNumVersions);
  const [selectedModes, setSelectedModes] = useState(defaultModes);
  const [shuffleQuestions, setShuffleQuestions] = useState(
    initialConfig?.ordering_preferences?.shuffle_questions ?? true,
  );
  const [shuffleOptions, setShuffleOptions] = useState(
    initialConfig?.ordering_preferences?.shuffle_options ?? false,
  );
  const [validationError, setValidationError] = useState('');

  const totalQuestions = session?.source_questions?.length || session?.blueprint_summary?.total_questions || 0;
  const totalVariantsToGenerate = numVersions * totalQuestions;

  function toggleMode(modeId, isAvailable) {
    if (!isAvailable || isSubmitting) return;

    setValidationError('');
    setSelectedModes((prev) => {
      if (prev.includes(modeId)) {
        return prev.filter((id) => id !== modeId);
      }
      return [...prev, modeId];
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setValidationError('');

    if (!isBlueprintReady) {
      setValidationError('Đề nguồn chưa hoàn tất phân tích Blueprint. Vui lòng quay lại Giai đoạn 1 để xác nhận đề gốc.');
      return;
    }

    if (numVersions < 1 || numVersions > 4) {
      setValidationError('Số lượng mã đề phải từ 1 đến 4.');
      return;
    }

    const payload = {
      n_versions: Number(numVersions),
      active_variation_modes: selectedModes,
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
    <div className="mx-auto max-w-4xl rounded-2xl border border-slate-700 bg-slate-900/90 p-6 shadow-xl backdrop-blur-sm sm:p-8">
      {/* Header tóm tắt phiên làm việc */}
      <div className="mb-8 border-b border-slate-800 pb-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-sky-500/20 px-3 py-1 text-xs font-semibold text-sky-300">
                Giai đoạn 2: Cấu hình sinh đề
              </span>
              <span className="text-xs text-slate-400">
                Môn: {session?.subject || 'Toán'} • Khối {session?.grade || 12}
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">
              {session?.title || 'Cấu hình tạo đề thi đẳng cấu'}
            </h1>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-800/60 px-4 py-3 text-right">
            <p className="text-xs text-slate-400">Đề nguồn đã duyệt</p>
            <p className="text-xl font-bold text-sky-400">
              {totalQuestions} <span className="text-sm font-normal text-slate-300">câu hỏi</span>
            </p>
          </div>
        </div>
      </div>

      {/* Thông báo lỗi nếu có */}
      {(error || validationError) && (
        <div
          role="alert"
          className="mb-6 flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-rose-200"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
          <div className="text-sm">
            <p className="font-semibold">Cần điều chỉnh cấu hình:</p>
            <p>{validationError || error}</p>
          </div>
        </div>
      )}

      <form id={formId} onSubmit={handleSubmit} className="space-y-8">
        {/* Phần 1: Chọn số lượng mã đề */}
        <div>
          <label className="block text-base font-semibold text-white">
            1. Số lượng mã đề cần sinh (N)
          </label>
          <p className="mt-1 text-sm text-slate-400">
            Hệ thống sẽ tạo ra các đề thi có cùng cấu trúc ma trận nhưng khác biệt về số liệu hoặc ngữ cảnh.
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[1, 2, 3, 4].map((n) => {
              const isSelected = numVersions === n;
              return (
                <button
                  key={n}
                  type="button"
                  onClick={() => setNumVersions(n)}
                  disabled={isSubmitting}
                  className={`flex flex-col items-center justify-center rounded-xl border p-4 transition-all ${
                    isSelected
                      ? 'border-sky-500 bg-sky-950/50 text-white shadow-lg shadow-sky-950/40 ring-2 ring-sky-500/40'
                      : 'border-slate-700 bg-slate-800/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  <span className="text-3xl font-extrabold">{n}</span>
                  <span className="mt-1 text-xs text-slate-400">
                    {n === 1 ? '1 phiên bản' : `${n} mã đề so le`}
                  </span>
                  {isSelected && (
                    <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-sky-500/20 px-2 py-0.5 text-[11px] font-medium text-sky-300">
                      <Check className="h-3 w-3" /> Đã chọn
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Phần 2: Chế độ biến thể (Variation Modes) */}
        <div>
          <div className="flex items-center justify-between">
            <label className="block text-base font-semibold text-white">
              2. Chế độ biến thể bài toán (Variation Modes)
            </label>
            <span className="text-xs text-slate-400">
              Đọc từ Blueprint tự động
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Chọn các phương pháp sinh biến thể câu hỏi tương đương. Các chế độ không khả dụng đã được hệ thống tự động lọc.
          </p>

          <div className="mt-4 space-y-3">
            {!isBlueprintReady ? (
              <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-4 text-center text-sm text-amber-200">
                <p className="font-semibold">Chưa có thông tin Blueprint khả dụng</p>
                <p className="mt-1 text-xs text-amber-300/80">
                  Đề nguồn chưa hoàn tất phân tích Blueprint hoặc thiếu dữ liệu câu hỏi. Vui lòng quay lại Giai đoạn 1 để xác nhận đề gốc.
                </p>
              </div>
            ) : supportedModes.length === 0 ? (
              <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4 text-sm text-slate-300">
                <div className="flex items-start gap-3">
                  <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-sky-400" />
                  <div>
                    <p className="font-semibold text-white">Đề nguồn giữ nguyên bài toán gốc</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Các câu hỏi trong đề được phân tích chỉ áp dụng chế độ giữ nguyên (không biến đổi số liệu hoặc ngữ cảnh). Hệ thống sẽ sinh các mã đề dựa trên xáo trộn thứ tự câu hỏi bên dưới.
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              supportedModes.map((mode) => {
                const isSelected = selectedModes.includes(mode.id);
                const isAvailable = mode.is_available !== false;

                return (
                  <div
                    key={mode.id}
                    onClick={(e) => {
                      if (e.target?.tagName?.toLowerCase() === 'input') return;
                      toggleMode(mode.id, isAvailable);
                    }}
                    className={`relative flex items-start gap-4 rounded-xl border p-4 transition-all ${
                      !isAvailable
                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/40 opacity-55'
                        : isSelected
                        ? 'cursor-pointer border-sky-500/60 bg-sky-950/25 ring-1 ring-sky-500/30'
                        : 'cursor-pointer border-slate-700 bg-slate-800/40 hover:border-slate-600 hover:bg-slate-800/70'
                    }`}
                  >
                    <div className="pt-0.5">
                      <input
                        type="checkbox"
                        id={`mode-${mode.id}`}
                        checked={isSelected && isAvailable}
                        disabled={!isAvailable || isSubmitting}
                        onChange={() => toggleMode(mode.id, isAvailable)}
                        className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900 disabled:opacity-40"
                      />
                    </div>

                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`text-sm font-semibold select-none ${
                            isAvailable ? 'text-white' : 'text-slate-400'
                          }`}
                        >
                          {mode.label}
                        </span>
                        {isAvailable ? (
                          <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-300">
                            Hỗ trợ {mode.question_count}/{totalQuestions} câu
                          </span>
                        ) : (
                          <span className="rounded bg-rose-950/40 px-2 py-0.5 text-[11px] font-medium text-rose-300">
                            Không khả dụng
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-slate-400">
                        {mode.description}
                      </p>
                      {!isAvailable && mode.unavailable_reason && (
                        <p className="mt-1.5 flex items-center gap-1 text-xs text-amber-400/90">
                          <HelpCircle className="h-3.5 w-3.5" />
                          {mode.unavailable_reason}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Phần 3: Tùy chọn xáo trộn ban đầu */}
        <div>
          <label className="block text-base font-semibold text-white">
            3. Tùy chọn xáo trộn thứ tự đề thi
          </label>
          <p className="mt-1 text-sm text-slate-400">
            Tối ưu hóa khả năng chống nhìn bài giữa các thí sinh ngồi cạnh nhau.
          </p>

          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  id="shuffle-questions-checkbox"
                  checked={shuffleQuestions}
                  disabled={isSubmitting}
                  onChange={(e) => setShuffleQuestions(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">
                      Xáo trộn thứ tự câu hỏi giữa các mã đề (shuffle_questions)
                    </span>
                    <Shuffle className="h-3.5 w-3.5 text-slate-400" />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">
                    Các câu hỏi sẽ được hoán vị ngẫu nhiên trên từng mã đề, đảm bảo thí sinh cùng phòng làm các câu khác vị trí nhau.
                  </p>
                </div>
              </label>
            </div>

            <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-4">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  id="shuffle-options-checkbox"
                  checked={shuffleOptions}
                  disabled={isSubmitting}
                  onChange={(e) => setShuffleOptions(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">
                      Xáo trộn thứ tự các đáp án A, B, C, D (shuffle_options)
                    </span>
                    <Shuffle className="h-3.5 w-3.5 text-sky-400" />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">
                    Xáo trộn vị trí các phương án lựa chọn trên từng câu hỏi giữa các mã đề, phòng trường hợp dù đã tạo câu hỏi khác nhau nhưng vị trí đáp án đúng ở các mã đề lại giống nhau (ví dụ: câu 1 của các mã 101, 102, 103 đều rơi vào phương án A).
                  </p>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Phần 4: Thẻ tóm tắt thông số trực quan */}
        <div className="rounded-xl border border-sky-800/40 bg-sky-950/20 p-5">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-sky-400" />
            <div>
              <h3 className="text-sm font-semibold text-sky-200">
                Tóm tắt cấu hình sinh đề:
              </h3>
              <p className="mt-1 text-sm text-slate-300">
                Hệ thống sẽ sinh <strong className="text-white">{numVersions} mã đề</strong>, mỗi mã gồm <strong className="text-white">{totalQuestions} câu hỏi tương đương</strong>.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <span className="flex items-center gap-1.5 rounded-lg bg-slate-800/80 px-2.5 py-1 text-slate-200">
                  <Layers className="h-3.5 w-3.5 text-sky-400" />
                  Tổng cộng: <strong className="text-white">{totalVariantsToGenerate}</strong> câu hỏi biến thể
                </span>
                {selectedModes.length > 0 ? (
                  <span className="flex items-center gap-1.5 rounded-lg bg-slate-800/80 px-2.5 py-1 text-slate-200">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    {selectedModes.length} chế độ biến thể được kích hoạt
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 rounded-lg bg-slate-800/80 px-2.5 py-1 text-slate-200">
                    <HelpCircle className="h-3.5 w-3.5 text-slate-400" />
                    Không chọn biến thể (giữ nguyên câu hỏi gốc)
                  </span>
                )}
                {shuffleQuestions && (
                  <span className="flex items-center gap-1.5 rounded-lg bg-slate-800/80 px-2.5 py-1 text-slate-200">
                    <Shuffle className="h-3.5 w-3.5 text-amber-400" />
                    Thứ tự câu hỏi xáo ngẫu nhiên
                  </span>
                )}
                {shuffleOptions && (
                  <span className="flex items-center gap-1.5 rounded-lg bg-slate-800/80 px-2.5 py-1 text-slate-200">
                    <Shuffle className="h-3.5 w-3.5 text-sky-400" />
                    Thứ tự đáp án (A, B, C, D) xáo ngẫu nhiên
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Nút hành động */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-4">
          {onBack ? (
            <button
              type="button"
              onClick={onBack}
              disabled={isSubmitting}
              className="rounded-xl border border-slate-700 px-5 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white disabled:opacity-50"
            >
              Quay lại Bước 1
            </button>
          ) : (
            <div />
          )}

          <button
            type="submit"
            disabled={isSubmitting || !isBlueprintReady}
            className="flex items-center gap-2 rounded-xl bg-sky-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-600/30 hover:bg-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
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
