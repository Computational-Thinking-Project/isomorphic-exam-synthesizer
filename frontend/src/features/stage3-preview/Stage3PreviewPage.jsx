import useDialogFocus from '../../hooks/useDialogFocus.js';
import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  FileText,
  Grid,
  Loader2,
  Lock,
  RefreshCw,
  Sparkles,
  AlertCircle,
  AlertTriangle,
  Shuffle,
  X,
} from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';
import {
  fetchFinalizePreview,
  fetchOrderingPreferences,
  executeFinalizeShuffle,
  triggerFinalizeApprove,
} from '../../services/stage3PreviewService.js';
import { stage3Path, exportPath } from '../../sessionPaths.js';

export default function Stage3PreviewPage({
  loadPreview = fetchFinalizePreview,
  loadPreferences = fetchOrderingPreferences,
} = {}) {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [needsShuffle, setNeedsShuffle] = useState(false);
  const [shuffling, setShuffling] = useState(false);
  const [approving, setApproving] = useState(false);
  const [selectedTab, setSelectedTab] = useState('');
  const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
  const [approveError, setApproveError] = useState(null);
  const [toast, setToast] = useState(null);
  const [shuffleQuestions, setShuffleQuestions] = useState(false);
  const [shuffleOptions, setShuffleOptions] = useState(false);
  const [sessionStatus, setSessionStatus] = useState('reviewed');
  const isMountedRef = useRef(true);
  const requestIdRef = useRef(0);
  const activeSessionIdRef = useRef(sessionId);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // F05, R1 & F02: Reset trạng thái, đóng modal và hủy cờ khi sessionId thay đổi để tránh stale data và approve/shuffle nhầm phiên
  useEffect(() => {
    activeSessionIdRef.current = sessionId;
    setPreviewData(null);
    setSelectedTab('');
    setError(null);
    setNeedsShuffle(false);
    setIsApproveModalOpen(false);
    setApproveError(null);
    setShuffling(false);
    setApproving(false);
    setShuffleQuestions(false);
    setShuffleOptions(false);
    setSessionStatus('reviewed');
  }, [sessionId]);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => {
      if (isMountedRef.current) {
        setToast(null);
      }
    }, 4000);
  };

  // F04 & F05: loadData chỉ phụ thuộc vào sessionId, dùng requestIdRef để loại bỏ race condition
  const loadData = useCallback(async () => {
    if (!sessionId) return;
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    try {
      const data = await loadPreview(sessionId);
      if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return;
      setPreviewData(data);
      setNeedsShuffle(!data.is_finalized);
      if (data.status) {
        setSessionStatus(data.status);
      }
      if (data.ordering_preferences) {
        setShuffleQuestions(Boolean(data.ordering_preferences.shuffle_questions ?? false));
        setShuffleOptions(Boolean(data.ordering_preferences.shuffle_options ?? false));
      }
      if (data.versions?.length > 0) {
        setSelectedTab((prev) => prev || data.versions[0].version_code);
      }
    } catch (err) {
      if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return;
      // F03: Chỉ kích hoạt needsShuffle khi mã lỗi là ERR_SHUFFLE_REQUIRED
      if (err.errorCode === 'ERR_SHUFFLE_REQUIRED' || err.data?.error_code === 'ERR_SHUFFLE_REQUIRED') {
        setNeedsShuffle(true);
        setError(null);

        // Khôi phục ordering_preferences đã lưu ở backend theo Issue #45
        const errPrefs = err.response?.data?.ordering_preferences || err.data?.ordering_preferences;
        if (errPrefs && typeof errPrefs === 'object') {
          setShuffleQuestions(Boolean(errPrefs.shuffle_questions ?? false));
          setShuffleOptions(Boolean(errPrefs.shuffle_options ?? false));
        } else if (typeof loadPreferences === 'function') {
          try {
            const prefs = await loadPreferences(sessionId);
            if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return;
            if (prefs && typeof prefs === 'object') {
              setShuffleQuestions(Boolean(prefs.shuffle_questions ?? false));
              setShuffleOptions(Boolean(prefs.shuffle_options ?? false));
              if (prefs.status) {
                setSessionStatus(prefs.status);
              }
            }
          } catch {
            // Giữ mặc định false/false theo Issue #45
          }
        }
      } else if (err.status === 423) {
        // Đã khóa, cố nạp dữ liệu ở chế độ view-only
        setError('Phiên làm việc đã được phê duyệt và khóa nội dung.');
      } else {
        setError(err.message || 'Không thể tải bản xem trước đề thi.');
      }
    } finally {
      if (isMountedRef.current && currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [sessionId, loadPreview, loadPreferences]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Xử lý hoàn tất sắp xếp / xáo trộn mã đề (F02: cô lập targetSessionId; hỗ trợ cả 4 tổ hợp Boolean theo Issue #45)
  const handleShuffle = async (preferences = { shuffle_questions: false, shuffle_options: false }) => {
    const targetSessionId = sessionId;
    const sanitizedPrefs = {
      shuffle_questions: Boolean(preferences.shuffle_questions),
      shuffle_options: Boolean(preferences.shuffle_options),
    };
    setShuffling(true);
    setError(null);
    try {
      await executeFinalizeShuffle(targetSessionId, sanitizedPrefs);
      if (!isMountedRef.current || activeSessionIdRef.current !== targetSessionId) return;
      let toastMsg = 'Đã áp dụng cấu hình xáo trộn đề thi.';
      if (!sanitizedPrefs.shuffle_questions && !sanitizedPrefs.shuffle_options) {
        toastMsg = 'Đã giữ nguyên thứ tự câu hỏi và đáp án.';
      } else if (sanitizedPrefs.shuffle_questions && sanitizedPrefs.shuffle_options) {
        toastMsg = 'Đã xáo trộn câu hỏi và đáp án.';
      } else if (sanitizedPrefs.shuffle_questions && !sanitizedPrefs.shuffle_options) {
        toastMsg = 'Đã xáo trộn thứ tự câu hỏi (giữ nguyên đáp án).';
      } else if (!sanitizedPrefs.shuffle_questions && sanitizedPrefs.shuffle_options) {
        toastMsg = 'Đã xáo trộn thứ tự đáp án (giữ nguyên câu hỏi).';
      }
      showToast(toastMsg, 'success');
      await loadData();
    } catch (err) {
      if (!isMountedRef.current || activeSessionIdRef.current !== targetSessionId) return;
      showToast(err.message || 'Không thể thực hiện hoàn tất sắp xếp đề thi.', 'error');
    } finally {
      if (isMountedRef.current && activeSessionIdRef.current === targetSessionId) {
        setShuffling(false);
      }
    }
  };

  const isLocked = Boolean(
    previewData?.status === 'approved' ||
    previewData?.status === 'exported' ||
    sessionStatus === 'approved' ||
    sessionStatus === 'exported'
  );

  // F02: Chỉ cho phép phê duyệt khi previewData đã tải hoàn tất, hợp lệ và đã finalized
  const canApprove =
    !loading &&
    !error &&
    !needsShuffle &&
    !isLocked &&
    previewData?.session_id === sessionId &&
    previewData?.status === 'reviewed' &&
    previewData?.is_finalized === true;

  // Xử lý Phê duyệt cuối cùng & Khóa đề - F02
  const handleApprove = async () => {
    const targetSessionId = sessionId;
    if (!canApprove || activeSessionIdRef.current !== targetSessionId) {
      setApproveError('Dữ liệu xem trước chưa sẵn sàng hoặc không hợp lệ để phê duyệt.');
      return;
    }
    setApproving(true);
    setApproveError(null);
    try {
      await triggerFinalizeApprove(targetSessionId);
      if (!isMountedRef.current || activeSessionIdRef.current !== targetSessionId) return;
      setIsApproveModalOpen(false);
      showToast('Đã phê duyệt và khóa đề thi thành công!', 'success');
      navigate(exportPath(targetSessionId));
    } catch (err) {
      if (!isMountedRef.current || activeSessionIdRef.current !== targetSessionId) return;
      setApproveError(err.message || 'Có lỗi xảy ra khi phê duyệt đề thi.');
    } finally {
      if (isMountedRef.current && activeSessionIdRef.current === targetSessionId) {
        setApproving(false);
      }
    }
  };

  const approveDialogRef = useDialogFocus(isApproveModalOpen, approving, () => setIsApproveModalOpen(false));

  const currentVersion = previewData?.versions?.find((v) => v.version_code === selectedTab);

  return (
    <div className="paper-ui min-h-screen bg-surface text-strong flex flex-col font-sans">
      {/* Toast Notification */}
      {toast && (
        <div
          role="status"
          className={`fixed top-4 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-soft border text-sm transition-all animate-in fade-in slide-in-from-top-2 ${
            toast.type === 'error'
              ? 'bg-danger-soft border-danger-border text-danger'
              : 'bg-approved-bg border-approved-border text-approved-ink'
          }`}
        >
          {toast.type === 'error' ? (
            <AlertCircle className="w-5 h-5 text-danger shrink-0" />
          ) : (
            <CheckCircle2 className="w-5 h-5 text-approved-ink shrink-0" />
          )}
          <p>{toast.message}</p>
        </div>
      )}

      {/* Header bar */}
      <header className="border-b border-line bg-surface sticky top-0 z-20 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 min-h-16 py-3 flex flex-wrap gap-3 items-center justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              data-testid="btn-back"
              onClick={() => navigate(stage3Path(sessionId))}
              className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors py-1.5 px-2.5 rounded-lg hover:bg-rail"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Quay lại duyệt từng câu</span>
            </button>
            <div className="h-4 w-px bg-rail" />
            <h1 className="text-base sm:text-lg font-semibold text-strong flex items-center gap-2">
              <span>Xem trước và phê duyệt</span>
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Status badge */}
            {isLocked ? (
              <span
                data-testid="badge-status-locked"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-approved-bg text-approved-ink border border-approved-border"
              >
                <Lock className="w-3.5 h-3.5" />
                Đã phê duyệt & Khóa đề
              </span>
            ) : needsShuffle ? (
              <span
                data-testid="badge-status-pending"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-accent-soft text-accent-ink border border-accent-border"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Chờ chốt thứ tự
              </span>
            ) : canApprove ? (
              <span
                data-testid="badge-status-ready"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-support-bg text-highlight border border-support-line"
              >
                <Check className="w-3.5 h-3.5" />
                Sẵn sàng phê duyệt
              </span>
            ) : null}

            {/* Header Action Buttons: F01 bỏ reshuffle; F02 chỉ render khi canApprove */}
            {canApprove && (
              <button
                type="button"
                data-testid="btn-open-approve"
                onClick={() => setIsApproveModalOpen(true)}
                disabled={shuffling || approving}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-approved-ink hover:bg-approved-ink text-white font-medium text-sm transition-colors shadow-sm disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Phê duyệt & Khóa đề</span>
              </button>
            )}

            {isLocked && (
              <button
                type="button"
                data-testid="btn-goto-export"
                onClick={() => navigate(exportPath(sessionId))}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-highlight hover:bg-highlight text-white font-medium text-sm transition-colors shadow-sm"
              >
                <FileText className="w-4 h-4" />
                <span>Đi đến xuất đề</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-muted gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-highlight" />
            <p className="text-sm">Đang tải bản chiếu xem trước đề thi...</p>
          </div>
        ) : error && !needsShuffle ? (
          <div className="p-6 rounded-xl bg-danger-soft border border-danger-border text-danger max-w-2xl mx-auto my-12 text-center">
            <AlertCircle className="w-10 h-10 text-danger mx-auto mb-3" />
            <h2 className="text-lg font-semibold mb-2">Không thể tải bản xem trước</h2>
            <p className="text-sm text-danger mb-6">{error}</p>
            <button
              type="button"
              data-testid="btn-retry"
              onClick={() => loadData()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-danger hover:bg-danger text-white text-sm font-medium transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Thử lại</span>
            </button>
          </div>
        ) : needsShuffle ? (
          /* Trạng thái chưa chốt thứ tự: Hai tùy chọn xáo trộn độc lập theo Issue #45 */
          <div className="max-w-xl mx-auto my-16 p-8 rounded-2xl bg-surface border border-line shadow-paper">
            <div className="w-16 h-16 rounded-2xl bg-accent-soft border border-accent-border text-accent-ink flex items-center justify-center mx-auto mb-5">
              <Sparkles className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-strong text-center mb-2">
              Toàn bộ câu hỏi đã được duyệt thành công
            </h2>
            <p className="text-sm text-muted text-center leading-relaxed mb-6">
              Các câu hỏi đã được duyệt. Tùy chỉnh xáo trộn câu hỏi và đáp án để chuẩn bị bản xem trước.
            </p>

            {/* Hai tùy chọn xáo trộn độc lập theo Issue #45 */}
            <div className="space-y-3 mb-6">
              <div className="rounded-xl border border-line bg-rail p-4">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    id="shuffle-questions-checkbox"
                    data-testid="checkbox-shuffle-questions"
                    checked={shuffleQuestions}
                    disabled={shuffling || isLocked}
                    onChange={(e) => setShuffleQuestions(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-line bg-surface text-highlight focus:ring-highlight focus:ring-offset-surface disabled:opacity-50"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-strong">
                        Xáo trộn thứ tự câu hỏi giữa các mã đề
                      </span>
                      <Shuffle className="h-3.5 w-3.5 text-muted" />
                    </div>
                    <p className="mt-0.5 text-xs text-muted">
                      Đổi vị trí câu hỏi giữa các mã đề thi độc lập.
                    </p>
                  </div>
                </label>
              </div>

              <div className="rounded-xl border border-line bg-rail p-4">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    id="shuffle-options-checkbox"
                    data-testid="checkbox-shuffle-options"
                    checked={shuffleOptions}
                    disabled={shuffling || isLocked}
                    onChange={(e) => setShuffleOptions(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-line bg-surface text-highlight focus:ring-highlight focus:ring-offset-surface disabled:opacity-50"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-strong">
                        Xáo trộn thứ tự các đáp án A, B, C, D
                      </span>
                      <Shuffle className="h-3.5 w-3.5 text-highlight" />
                    </div>
                    <p className="mt-0.5 text-xs text-muted">
                      Đổi vị trí 4 phương án; đáp án đúng được cập nhật tương ứng trên từng đề.
                    </p>
                  </div>
                </label>
              </div>
            </div>

            {/* Nút hành động duy nhất: Áp dụng & Xem trước */}
            <div className="flex justify-center">
              <button
                type="button"
                id="btn-apply-shuffle"
                data-testid="btn-shuffle"
                onClick={() =>
                  handleShuffle({
                    shuffle_questions: shuffleQuestions,
                    shuffle_options: shuffleOptions,
                  })
                }
                disabled={shuffling || isLocked}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3 rounded-xl bg-highlight hover:bg-highlight text-white font-semibold text-sm transition-all shadow-md disabled:opacity-50"
              >
                {shuffling ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Đang hoàn tất...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Áp dụng & Xem trước</span>
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          /* Bản xem trước hoàn chỉnh khi đã xáo trộn */
          <div className="space-y-6">
            {/* Locked Notice Banner */}
            {isLocked && (
              <div
                data-testid="banner-locked"
                className="p-4 rounded-xl bg-approved-bg border border-approved-border flex items-center justify-between text-approved-ink"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <Lock className="w-5 h-5 text-approved-ink shrink-0" />
                  <div>
                    <h3 className="text-sm font-semibold text-approved-ink">
                      Đề thi đã được phê duyệt và khóa nội dung vĩnh viễn
                    </h3>
                    <p className="text-xs text-approved-ink">
                      Nội dung đề thi và ma trận đáp án không thể thay đổi. Bạn có thể xem bản in hoặc chuyển sang bước xuất bản.
                    </p>
                  </div>
                </div>

              </div>
            )}

            {/* Navigation Tabs (Version Codes + Answers Matrix) */}
            <div className="border-b border-line">
              <nav role="tablist" className="flex gap-2 overflow-x-auto pb-px">
                {previewData?.versions?.map((ver) => (
                  <button
                    key={ver.version_code}
                    role="tab"
                    data-testid={`tab-version-${ver.version_code}`}
                    aria-selected={selectedTab === ver.version_code}
                    onClick={() => setSelectedTab(ver.version_code)}
                    className={`inline-flex items-center gap-2 py-3 px-4 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
                      selectedTab === ver.version_code
                        ? 'border-support-line text-highlight bg-support-bg'
                        : 'border-transparent text-muted hover:text-ink hover:border-line'
                    }`}
                  >
                    <FileText className="w-4 h-4" />
                    <span>Mã đề {ver.version_code}</span>
                    <span className="text-xs py-0.5 px-2 rounded-full bg-rail text-muted">
                      {ver.total_questions || ver.questions?.length || 0} câu
                    </span>
                  </button>
                ))}

                <button
                  role="tab"
                  data-testid="tab-matrix"
                  aria-selected={selectedTab === 'matrix'}
                  onClick={() => setSelectedTab('matrix')}
                  className={`inline-flex items-center gap-2 py-3 px-4 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
                    selectedTab === 'matrix'
                      ? 'border-support-line text-highlight bg-support-bg'
                      : 'border-transparent text-muted hover:text-ink hover:border-line'
                  }`}
                >
                  <Grid className="w-4 h-4" />
                  <span>Bảng đáp án</span>
                </button>
              </nav>
            </div>

            {/* Tab Content: Version Exam Viewer */}
            {selectedTab !== 'matrix' && currentVersion && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-bold text-strong">
                      Bản xem trước — Mã đề {currentVersion.version_code}
                    </h2>
                    <p className="text-xs text-muted mt-0.5">
                      Kiểm tra nội dung, đáp án và lời giải trước khi phê duyệt.
                    </p>
                  </div>
                </div>

                <div className="space-y-6">
                  {currentVersion.questions?.map((q) => (
                    <article
                      key={q.id || q.question_no}
                      data-testid={`question-card-${q.question_no}`}
                      className="p-6 rounded-xl bg-surface border border-line space-y-4"
                    >
                      <div className="flex items-center justify-between border-b border-line pb-3">
                        <div className="flex flex-wrap items-center gap-3">
                          <span className="px-2.5 py-1 rounded bg-rail text-highlight font-bold text-sm">
                            Câu {q.question_no}
                          </span>
                          <span className="text-xs text-muted">
                            [Gốc: #{q.canonical_question_no}]
                          </span>
                        </div>
                        <span className="text-xs text-muted flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-approved-ink" />
                          Đã duyệt
                        </span>
                      </div>

                      {/* Question Content */}
                      <div className="text-ink text-base leading-relaxed">
                        <MathRenderer content={q.content} />
                      </div>

                      {/* Shuffled Options Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                        {q.options?.map((opt, idx) => {
                          const optionLabel = String.fromCharCode(65 + idx);
                          const isCorrect = optionLabel === q.correct_key;

                          return (
                            <div
                              key={optionLabel}
                              className={`p-3.5 rounded-lg border flex items-start gap-3 transition-colors ${
                                isCorrect
                                  ? 'bg-approved-bg border-approved-border text-approved-ink'
                                  : 'bg-surface border-line text-ink'
                              }`}
                            >
                              <span
                                className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold shrink-0 ${
                                  isCorrect
                                    ? 'bg-approved-ink text-white'
                                    : 'bg-rail text-muted'
                                }`}
                              >
                                {optionLabel}
                              </span>
                              <div className="flex-1 text-sm pt-0.5">
                                <MathRenderer content={String(opt)} inline />
                              </div>
                              {isCorrect && (
                                <span
                                  data-testid="badge-correct"
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-approved-bg text-approved-ink shrink-0"
                                >
                                  <Check className="w-3 h-3" />
                                  Đáp án đúng
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>

                      {/* Detailed Solution */}
                      {q.solution_md && (
                        <div className="mt-4 pt-3 border-t border-line">
                          <h4 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">
                            Lời giải chi tiết
                          </h4>
                          <div className="p-4 rounded-lg bg-surface border border-line text-ink text-sm leading-relaxed">
                            <MathRenderer content={q.solution_md} />
                          </div>
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              </div>
            )}

            {/* Tab Content: Answers Matrix Table */}
            {selectedTab === 'matrix' && (
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-bold text-strong">
                    Bảng đáp án các mã đề
                  </h2>
                  <p className="text-xs text-muted mt-0.5">
                    Đối chiếu đáp án đúng của từng câu hỏi giữa các mã đề.
                  </p>
                </div>

                <div className="overflow-x-auto rounded-xl border border-line bg-surface">
                  <table data-testid="matrix-table" className="w-full text-left text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-line bg-surface text-muted text-xs uppercase font-medium">
                        <th className="py-3 px-4 w-28">Câu số</th>
                        {previewData?.versions?.map((v) => (
                          <th key={v.version_code} className="py-3 px-4">
                            Mã đề {v.version_code}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {previewData?.matrix?.map((row) => (
                        <tr key={row.question_no} className="hover:bg-surface transition-colors">
                          <td className="py-3 px-4 font-semibold text-ink">
                            Câu {row.question_no}
                          </td>
                          {previewData?.versions?.map((v) => {
                            const ans = row.answers?.[v.version_code] || '-';
                            return (
                              <td key={v.version_code} className="py-3 px-4">
                                <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-approved-bg text-approved-ink font-bold border border-approved-border">
                                  {ans}
                                </span>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Confirmation Modal for Final Approval */}
      {isApproveModalOpen && (
        <div
          ref={approveDialogRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-labelledby="approve-dialog-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
        >
          <div className="max-h-[90dvh] overflow-y-auto w-full max-w-lg rounded-2xl bg-surface border border-line p-6 shadow-paper space-y-6">
            <div className="flex items-start justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-approved-bg border border-approved-border text-approved-ink flex items-center justify-center shrink-0">
                  <Lock className="w-5 h-5" />
                </div>
                <div>
                  <h3 id="approve-dialog-title" className="text-base font-bold text-strong">
                    Xác nhận phê duyệt & Khóa đề thi
                  </h3>
                  <p className="text-xs text-muted">Kiểm tra kỹ trước khi xác nhận.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsApproveModalOpen(false)}
                disabled={approving}
                aria-label="Đóng"
                className="text-muted hover:text-ink p-1 rounded-lg hover:bg-rail transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-xl bg-accent-soft border border-accent-border text-accent-ink text-xs leading-relaxed flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-accent-ink shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-accent-ink mb-1">
                  Hành động này không thể hoàn tác!
                </p>
                <p>
                  Sau khi phê duyệt, toàn bộ câu hỏi, phương án xáo trộn, đáp án và lời giải của tất cả {previewData?.n_versions || 0} mã đề sẽ được khóa để xuất đề. Bạn sẽ được chuyển sang màn hình xuất đề.
                </p>
              </div>
            </div>

            {approveError && (
              <div className="p-3 rounded-lg bg-danger-soft border border-danger-border text-danger text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-danger" />
                <p>{approveError}</p>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                data-testid="btn-cancel-approve"
                disabled={approving}
                onClick={() => setIsApproveModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-line hover:bg-rail text-ink text-sm font-medium transition-colors disabled:opacity-50"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                data-testid="btn-confirm-approve"
                disabled={approving || !canApprove}
                onClick={handleApprove}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-approved-ink hover:bg-approved-ink text-white text-sm font-semibold transition-colors shadow-md disabled:opacity-50"
              >
                {approving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Đang khóa đề thi...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Xác nhận & Khóa đề</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
