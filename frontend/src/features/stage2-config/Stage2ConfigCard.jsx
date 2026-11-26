import { useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Info,
  Loader2,
} from 'lucide-react';
import './stage2.css';

/**
 * Stage2ConfigCard: Form cấu hình sinh biến thể mã đề (Stage 2 - S04)
 * Thiết kế lại theo chuẩn prototype docs/ui-walkthrough/PREVIEW.html và Issue #94.
 *
 * Tiêu chí cốt lõi:
 * 1. Stepper 3 bước chuẩn: 01. Chuẩn bị đề gốc -> 02. Cấu hình và tạo mã -> 03. Duyệt và sử dụng
 * 2. Ô nhập duy nhất: nhãn "Số mã đề (N ∈ [1, 4]) *"
 * 3. Thẻ Workload: X câu/mã × N mã đề = Total biến thể
 * 4. Popup xác nhận trước khi sinh đề
 * 5. KHÔNG có checkbox shuffle hay Blueprint variation selector trên UI
 * 6. Tương thích fallback initialNumVersions từ Cài đặt cá nhân (PR #106)
 * 7. EXT-02: chọn "Sinh đề tương tự" (ai_generation) hoặc "Chỉ xáo trộn" (shuffle_only),
 *    gửi generation_mode; cảnh báo khi chỉ xáo trộn, N > 1 và hai cờ xáo trộn đều tắt.
 */
export default function Stage2ConfigCard({
  session,
  initialConfig = null,
  initialNumVersions = undefined,
  onSubmit,
  isSubmitting = false,
  error = null,
  onBack = null,
  onReturnToStage1 = null,
}) {
  // INT-02: Kiểm tra chuẩn hóa strict readiness của Blueprint
  const isBlueprintReady = Boolean(
    session?.status !== 'draft' &&
    session?.blueprint_summary?.is_ready === true &&
    Array.isArray(session?.blueprint_summary?.supported_modes),
  );

  // Thứ tự fallback chuẩn: initialNumVersions (Settings) ?? initialConfig ?? 2
  const defaultNumVersions =
    initialNumVersions ??
    initialConfig?.n_versions ??
    initialConfig?.num_versions ??
    2;

  const [rawInput, setRawInput] = useState(String(defaultNumVersions));
  // EXT-02: explicit mode; a saved draft reopens with the mode it was saved with.
  const [generationMode, setGenerationMode] = useState(
    initialConfig?.generation_mode === 'shuffle_only' ? 'shuffle_only' : 'ai_generation',
  );
  const isShuffleOnly = generationMode === 'shuffle_only';
  const [isTouched, setIsTouched] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Kiểm tra tính hợp lệ của số mã đề N in [1, 4]
  const parsedNum = parseInt(rawInput.trim(), 10);
  const isInteger = /^\d+$/.test(rawInput.trim());
  const isValidN = isInteger && Number.isInteger(parsedNum) && parsedNum >= 1 && parsedNum <= 4;

  let validationError = '';
  if (isTouched || rawInput.trim() !== '') {
    if (!rawInput.trim()) {
      validationError = 'Vui lòng nhập số mã đề cần tạo.';
    } else if (!isInteger || isNaN(parsedNum)) {
      validationError = 'Số mã đề phải là số nguyên.';
    } else if (parsedNum < 1 || parsedNum > 4) {
      validationError = 'Số mã đề (N) phải nằm trong khoảng từ 1 đến 4.';
    }
  }

  const numVersions = isValidN ? parsedNum : 0;
  const totalQuestions =
    session?.source_questions?.length ||
    session?.blueprint_summary?.total_questions ||
    0;
  const totalVariants = numVersions * totalQuestions;

  // Lấy tên file nguồn hoặc tiêu đề
  const sessionTitle = session?.title || '';
  const sourceFilename =
    session?.source_filename ||
    session?.source_file_name ||
    session?.file_name ||
    sessionTitle ||
    'Đề gốc';

  // Issue #94: Kiểm tra nếu phiên cũ từng lưu shuffle_options = true
  const hadShuffleOptions = Boolean(initialConfig?.ordering_preferences?.shuffle_options);
  // Both flags off in shuffle-only mode: every code would be an identical copy.
  const identicalVersionsWarning =
    isShuffleOnly &&
    numVersions > 1 &&
    !initialConfig?.ordering_preferences?.shuffle_questions &&
    !initialConfig?.ordering_preferences?.shuffle_options;

  async function executeSubmit() {
    if (isSubmitting) return;
    setShowConfirmModal(false);
    if (!onSubmit) return;

    // Issue #94: Payload bảo toàn ordering_preferences cũ hoặc fallback false/false
    const payload = {
      n_versions: numVersions,
      active_variation_modes: [],
      generation_mode: generationMode,
      ordering_preferences: {
        shuffle_questions: Boolean(initialConfig?.ordering_preferences?.shuffle_questions ?? false),
        shuffle_options: Boolean(initialConfig?.ordering_preferences?.shuffle_options ?? false),
      },
    };

    try {
      await onSubmit(payload);
    } catch (err) {
      setSubmitError(err.message || 'Không thể bắt đầu tạo biến thể.');
    }
  }

  function handleSubmit(e) {
    if (e) e.preventDefault();
    setIsTouched(true);
    setSubmitError('');

    if (!isBlueprintReady) {
      setSubmitError('Đề nguồn chưa hoàn tất chuẩn bị. Vui lòng quay lại Bước 1 để xác nhận đề gốc.');
      return;
    }

    if (!isValidN) {
      return;
    }

    // F108-06: Mọi submit hợp lệ đều mở modal xác nhận (không bypass bằng synthetic event)
    setShowConfirmModal(true);
  }

  return (
    <div className="stage2-flow">
      <main className="flow-main" role="region" aria-label="Cấu hình số mã đề">
        {/* Stepper chuẩn 3 bước từ PREVIEW.html */}
        <ol className="flow-stepper" aria-label="Các bước thực hiện">
          <li className="completed">
            <span className="step-indicator" aria-hidden="true">
              ✓
            </span>
            <span>01. Chuẩn bị đề gốc</span>
          </li>
          <li className="current" aria-current="step">
            <span className="step-indicator" aria-hidden="true">
              02
            </span>
            <span>02. Cấu hình và tạo mã</span>
          </li>
          <li>
            <span className="step-indicator" aria-hidden="true">
              03
            </span>
            <span>03. Duyệt và sử dụng</span>
          </li>
        </ol>

        {/* Flow Heading */}
        <header className="flow-heading">
          <div>
            <h1 className="heading-title">Tạo mã đề</h1>
            <p className="heading-subtitle">
              {sessionTitle ? <strong>{sessionTitle} · </strong> : null}
              Nhập số mã đề cần tạo. Mỗi mã giữ đủ câu gốc đã xác nhận.
            </p>
          </div>
        </header>

        {/* Thẻ đề gốc đã xác nhận */}
        <section className="confirmed-source" aria-label="Thông tin đề gốc">
          <div>
            <h2>
              {totalQuestions} câu gốc {isBlueprintReady ? 'đã xác nhận' : 'cần xác nhận lại'}
              <span className="sr-only"> ({totalQuestions} câu hỏi)</span>
            </h2>
            <p>
              {sourceFilename} · Giữ đủ Câu 1 đến Câu {totalQuestions} trong mỗi mã.
            </p>
          </div>
          {onReturnToStage1 && (
            <button
              type="button"
              onClick={onReturnToStage1}
              className="quiet-button"
            >
              Xem đề gốc
            </button>
          )}
        </section>

        {/* Cảnh báo nếu chưa sẵn sàng Blueprint */}
        {!isBlueprintReady && (
          <div role="alert" className="flow-notice is-error">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <div className="flex-1">
              <div>
                <strong>Chưa có thông tin cấu trúc đề khả dụng.</strong> Đề nguồn chưa hoàn tất phân tích cấu trúc đề. Vui lòng quay lại Bước 1 để xác nhận đề gốc.
              </div>
              {onReturnToStage1 && (
                <div style={{ marginTop: '8px' }}>
                  <button
                    type="button"
                    onClick={onReturnToStage1}
                    className="quiet-button"
                    style={{ fontSize: '13px', padding: '4px 12px' }}
                  >
                    Quay về Giai đoạn 1
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Cảnh báo lỗi submit hoặc lỗi từ server */}
        {(error || submitError) && (
          <div role="alert" className="flow-notice is-error">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <div>{error || submitError}</div>
          </div>
        )}

        {/* Form cấu hình */}
        <form id="configure-form" onSubmit={handleSubmit} noValidate>
          <fieldset
            disabled={!isBlueprintReady || isSubmitting}
            style={{ border: 'none', margin: 0, padding: 0 }}
          >
            <fieldset className="generation-mode" aria-describedby="generation-mode-hint">
              <legend>Cách tạo mã đề</legend>
              <label className="generation-mode-option">
                <input
                  type="radio"
                  name="generation_mode"
                  value="ai_generation"
                  data-generation-mode="ai_generation"
                  checked={!isShuffleOnly}
                  onChange={() => setGenerationMode('ai_generation')}
                />
                <span>Sinh đề tương tự</span>
              </label>
              <label className="generation-mode-option">
                <input
                  type="radio"
                  name="generation_mode"
                  value="shuffle_only"
                  data-generation-mode="shuffle_only"
                  checked={isShuffleOnly}
                  onChange={() => setGenerationMode('shuffle_only')}
                />
                <span>Chỉ xáo trộn</span>
              </label>
              <p id="generation-mode-hint" className="generation-mode-hint">
                {isShuffleOnly
                  ? 'Mỗi mã đề giữ nguyên câu hỏi gốc, chỉ đổi thứ tự câu và phương án. Không dùng AI.'
                  : 'AI tạo câu hỏi tương tự cho từng mã đề; bạn duyệt từng câu ở bước sau.'}
              </p>
            </fieldset>

            <div className="configure-question">
              <div>
                <h2>Bạn cần bao nhiêu mã đề?</h2>
                <label htmlFor="code-count">
                  Số mã đề (N ∈ [1, 4]) <span aria-hidden="true">*</span>
                </label>
                <input
                  id="code-count"
                  className="count-input"
                  type="text"
                  inputMode="numeric"
                  value={rawInput}
                  disabled={!isBlueprintReady || isSubmitting}
                  aria-required="true"
                  aria-invalid={Boolean(validationError)}
                  aria-describedby={validationError ? 'n-hint' : undefined}
                  onBlur={() => setIsTouched(true)}
                  onInput={(e) => {
                    setRawInput(e.target.value);
                    setSubmitError('');
                  }}
                  onChange={(e) => {
                    setRawInput(e.target.value);
                    setSubmitError('');
                  }}
                />
                {validationError && (
                  <p id="n-hint" className="n-hint field-error" role="alert">
                    {validationError}
                  </p>
                )}
              </div>
            </div>

            {/* Thẻ tóm tắt khối lượng sinh */}
            <section className="workload" aria-label="Số biến thể cần tạo">
              <p>
                <strong>
                  {totalQuestions} câu/mã × {isValidN ? `${numVersions} mã đề` : '—'} ={' '}
                  {isValidN ? totalVariants.toLocaleString('vi') : '—'} biến thể
                </strong>
              </p>
            </section>

            {identicalVersionsWarning && (
              <div className="flow-notice is-read-only" role="note" data-identical-versions-warning>
                <Info className="h-5 w-5 shrink-0 text-amber-400" />
                <div>
                  <strong>Các mã đề sẽ giống nhau:</strong> xáo trộn câu hỏi và xáo trộn đáp án đang tắt, nên {numVersions} mã đề có cùng thứ tự câu và phương án. Bạn có thể bật xáo trộn ở bước Rà bộ đề trước khi chốt.
                </div>
              </div>
            )}

            {/* Issue #94: Thông báo chỉ đọc nếu phiên cũ từng bật xáo trộn đáp án */}
            {hadShuffleOptions && (
              <div className="flow-notice is-read-only" role="note">
                <Info className="h-5 w-5 shrink-0 text-amber-400" />
                <div>
                  <strong>Thông tin cấu hình:</strong> Phiên này đang bật xáo trộn đáp án trong toàn bộ mã đề. Tùy chọn xáo trộn có thể được điều chỉnh tại Bước 3 (Rà bộ đề) trước khi xuất file.
                </div>
              </div>
            )}
          </fieldset>

          {/* Flow Footer */}
          <footer className="flow-footer">
            {onBack ? (
              <button
                type="button"
                onClick={onBack}
                disabled={isSubmitting}
                className="quiet-button"
              >
                Quay về Dashboard
              </button>
            ) : onReturnToStage1 ? (
              <button
                type="button"
                onClick={onReturnToStage1}
                disabled={isSubmitting}
                className="quiet-button"
              >
                ← Quay lại đề gốc
              </button>
            ) : (
              <div />
            )}

            <div className="footer-right">
              {(!isBlueprintReady || !isValidN) && (
                <small>Xác nhận đề gốc và nhập số mã đề hợp lệ.</small>
              )}

              <button
                type="submit"
                disabled={isSubmitting || !isBlueprintReady || !isValidN}
                className="button-primary"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Đang khởi tạo…
                  </>
                ) : (
                  <>
                    Tạo biến thể
                    <span className="sr-only"> (Bắt đầu sinh đề)</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          </footer>
        </form>
      </main>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div
          className="flow-modal-overlay"
          role="presentation"
          onClick={() => setShowConfirmModal(false)}
        >
          <div
            className="flow-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-modal-title">Tạo biến thể</h2>
            <p>
              {isShuffleOnly
                ? `${totalQuestions} câu gốc × ${numVersions} mã, chỉ xáo trộn, không dùng AI.`
                : `${totalQuestions} câu gốc × ${numVersions} mã = ${totalVariants} biến thể.`}{' '}
              Tạo lượt mới sẽ thay bản nháp và các dấu duyệt, dấu rà hiện tại.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => setShowConfirmModal(false)}
                className="quiet-button"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={executeSubmit}
                className="button-primary"
              >
                Tạo biến thể
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
