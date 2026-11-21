import useDialogFocus from '../../hooks/useDialogFocus.js';
import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Eye,
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
  const [shuffleRecovery, setShuffleRecovery] = useState(null);
  const [shuffleQuestions, setShuffleQuestions] = useState(false);
  const [shuffleOptions, setShuffleOptions] = useState(false);
  const [sessionStatus, setSessionStatus] = useState('reviewed');
  const [isTeacherMode, setIsTeacherMode] = useState(false);
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
    setShuffleRecovery(null);
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

  // requestIdRef loại bỏ phản hồi cũ khi đổi phiên hoặc bắt đầu lượt đọc mới.
  const loadData = useCallback(async (recovery = null) => {
    if (!sessionId) return null;
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    try {
      const data = await loadPreview(sessionId);
      if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return null;
      if (recovery && (
        data?.session_id !== sessionId ||
        (data.is_finalized !== true && (recovery === 'confirmed' || !data.ordering_preferences))
      )) {
        setError('Chưa thể tải bản xem trước nhất quán với trạng thái chốt thứ tự.');
        return null;
      }
      setShuffleRecovery(null);
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
      return data;
    } catch (err) {
      if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return null;
      // F03: Chỉ kích hoạt needsShuffle khi mã lỗi là ERR_SHUFFLE_REQUIRED
      if (err.errorCode === 'ERR_SHUFFLE_REQUIRED' || err.data?.error_code === 'ERR_SHUFFLE_REQUIRED') {
        if (recovery === 'confirmed') {
          setError('Chưa thể tải bản xem trước nhất quán với trạng thái chốt thứ tự.');
          return null;
        }

        // Khôi phục ordering_preferences đã lưu ở backend theo Issue #45
        const errPrefs = err.response?.data?.ordering_preferences || err.data?.ordering_preferences;
        if (errPrefs && typeof errPrefs === 'object') {
          setShuffleQuestions(Boolean(errPrefs.shuffle_questions ?? false));
          setShuffleOptions(Boolean(errPrefs.shuffle_options ?? false));
        } else if (typeof loadPreferences === 'function') {
          try {
            const prefs = await loadPreferences(sessionId);
            if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return null;
            if (prefs && typeof prefs === 'object') {
              setShuffleQuestions(Boolean(prefs.shuffle_questions ?? false));
              setShuffleOptions(Boolean(prefs.shuffle_options ?? false));
              if (prefs.status) {
                setSessionStatus(prefs.status);
              }
            }
          } catch {
            if (!isMountedRef.current || currentRequestId !== requestIdRef.current) return null;
            setNeedsShuffle(false);
            setError('Không thể tải cấu hình xáo trộn đã lưu. Vui lòng thử lại.');
            return null;
          }
        }
        setShuffleRecovery(null);
        setNeedsShuffle(true);
        return { is_finalized: false };
      } else if (err.status === 423 && err.errorCode === 'ERR_SESSION_LOCKED') {
        setShuffleRecovery(null);
        setNeedsShuffle(false);
        setSessionStatus('approved');
        setError('Phiên làm việc đã được phê duyệt và khóa nội dung.');
        return { is_finalized: true, locked: true };
      } else {
        setError(err.message || 'Không thể tải bản xem trước đề thi.');
        return null;
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
    if (shuffling || shuffleRecovery || activeSessionIdRef.current !== targetSessionId) return;
    const sanitizedPrefs = {
      shuffle_questions: Boolean(preferences.shuffle_questions),
      shuffle_options: Boolean(preferences.shuffle_options),
    };
    setShuffling(true);
    setError(null);
    try {
      try {
        await executeFinalizeShuffle(targetSessionId, sanitizedPrefs);
      } catch (err) {
        if (!isMountedRef.current || activeSessionIdRef.current !== targetSessionId) return;

        // Issue #86: Đối soát khi thao tác chưa nhận được xác nhận từ máy chủ.
        setShuffleRecovery('unknown');
        const reconciled = await loadData('unknown');
        if (!isMountedRef.current || activeSessionIdRef.current !== targetSessionId) return;

        if (reconciled?.is_finalized) {
          showToast('Đã hoàn tất sắp xếp đề thi (đã xác thực trạng thái từ máy chủ).', 'success');
        } else if (reconciled?.is_finalized === false) {
          showToast(err.message || 'Không thể thực hiện hoàn tất sắp xếp đề thi.', 'error');
        }
        return;
      }

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
      setShuffleRecovery('confirmed');
      setNeedsShuffle(false);
      await loadData('confirmed');
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
    !shuffleRecovery &&
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

  const handleTabKeyDown = (e) => {
    const tabs = [
      ...(previewData?.versions?.map((v) => v.version_code) || []),
      ...(isTeacherMode ? ['matrix'] : []),
    ];
    const currentIndex = tabs.indexOf(selectedTab);
    if (currentIndex === -1) return;
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      const nextIndex = (currentIndex + 1) % tabs.length;
      setSelectedTab(tabs[nextIndex]);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const prevIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      setSelectedTab(tabs[prevIndex]);
    }
  };

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
            {isLocked ? (
              <button
                type="button"
                data-testid="btn-back"
                onClick={() => navigate(exportPath(sessionId))}
                className="inline-flex items-center gap-2 text-sm text-highlight hover:underline py-1.5 px-2.5 rounded-lg hover:bg-rail font-semibold"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Đi tới xuất đề</span>
              </button>
            ) : (
              <button
                type="button"
                data-testid="btn-back"
                onClick={() => navigate(stage3Path(sessionId))}
                className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors py-1.5 px-2.5 rounded-lg hover:bg-rail"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Quay lại duyệt từng câu</span>
              </button>
            )}
            <div className="h-4 w-px bg-rail" />
            <h1 className="text-base sm:text-lg font-semibold text-strong flex items-center gap-2">
              <span>Xem trước và phê duyệt</span>
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Status badge & authoritative server status text */}
            <div className="flex flex-col items-end">
              {isLocked ? (
                <>
                  <span
                    data-testid="badge-status-locked"
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-approved-bg text-approved-ink border border-approved-border"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    Đã phê duyệt & Khóa đề
                  </span>
                  <span className="text-[11px] text-muted mt-0.5">Đề đã khóa</span>
                </>
              ) : needsShuffle && !shuffleRecovery ? (
                <>
                  <span
                    data-testid="badge-status-pending"
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-accent-soft text-accent-ink border border-accent-border"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    Chờ chốt thứ tự
                  </span>
                  <span className="text-[11px] text-accent-ink mt-0.5">
                    {shuffling ? 'Đã lưu lựa chọn; đang chờ xác nhận áp dụng' : 'Chưa áp dụng thứ tự cuối'}
                  </span>
                </>
              ) : canApprove ? (
                <>
                  <span
                    data-testid="badge-status-ready"
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-support-bg text-highlight border border-support-line"
                  >
                    <Check className="w-3.5 h-3.5" />
                    Sẵn sàng phê duyệt
                  </span>
                  <span className="text-[11px] text-approved-ink font-medium mt-0.5">
                    Đã áp dụng thứ tự cuối — bản đang xem đã được xác nhận
                  </span>
                </>
              ) : null}
            </div>

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
        ) : shuffleRecovery ? (
          <div
            className="max-w-md mx-auto my-16 p-8 rounded-2xl bg-surface border border-accent-border text-center shadow-paper"
            data-testid={shuffleRecovery === 'confirmed' ? 'preview-recovery-view' : 'outcome-unknown-view'}
          >
            <AlertCircle className="w-10 h-10 text-accent-ink mx-auto mb-3" />
            <h2 className="text-lg font-semibold mb-2 text-strong">
              {shuffleRecovery === 'confirmed'
                ? 'Đã chốt thứ tự, chưa tải được bản xem trước'
                : 'Chưa xác định được kết quả chốt thứ tự'}
            </h2>
            <p className="text-sm text-muted mb-6">
              {shuffleRecovery === 'confirmed'
                ? 'Kiểm tra lại trạng thái để tải bản xem trước trước khi phê duyệt.'
                : 'Yêu cầu hoàn tất đã được gửi tới máy chủ nhưng chưa nhận được phản hồi xác nhận. Vui lòng kiểm tra lại trạng thái trước khi thực hiện lại thao tác.'}
            </p>
            <button
              type="button"
              data-testid="btn-check-status"
              onClick={() => loadData(shuffleRecovery)}
              disabled={loading}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg bg-highlight hover:bg-highlight text-white text-sm font-semibold transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span>Kiểm tra trạng thái</span>
            </button>
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

            {/* Navigation Tabs (Version Codes + Answers Matrix) + Student/Teacher View Mode Toggle */}
            <div className="border-b border-line flex flex-wrap items-center justify-between gap-3 pb-px">
              <nav
                role="tablist"
                aria-label="Các mã đề thi và bảng đáp án"
                onKeyDown={handleTabKeyDown}
                className="flex gap-2 overflow-x-auto"
              >
                {previewData?.versions?.map((ver) => (
                  <button
                    key={ver.version_code}
                    role="tab"
                    id={`tab-version-${ver.version_code}`}
                    aria-controls={`tabpanel-version-${ver.version_code}`}
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

                {isTeacherMode && (
                  <button
                    role="tab"
                    id="tab-matrix"
                    aria-controls="tabpanel-matrix"
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
                )}
              </nav>

              <div className="flex items-center gap-2 py-2">
                <button
                  type="button"
                  data-testid="btn-toggle-view-mode"
                  onClick={() => {
                    if (isTeacherMode && selectedTab === 'matrix') {
                      const firstCode = previewData?.versions?.[0]?.version_code;
                      if (firstCode) setSelectedTab(firstCode);
                    }
                    setIsTeacherMode((prev) => !prev);
                  }}
                  className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-line bg-surface hover:bg-rail text-xs font-semibold text-strong transition-colors shadow-sm"
                >
                  <Eye className="w-3.5 h-3.5 text-highlight" />
                  <span>{isTeacherMode ? 'Đề học sinh' : 'Hiện đáp án và lời giải'}</span>
                </button>
              </div>
            </div>

            {/* Tab Content: Version Exam Viewer */}
            {selectedTab !== 'matrix' && currentVersion && (
              <div
                role="tabpanel"
                id={`tabpanel-version-${currentVersion.version_code}`}
                aria-labelledby={`tab-version-${currentVersion.version_code}`}
                tabIndex={0}
                className="space-y-6 focus:outline-none"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-bold text-strong">
                      Bản xem trước — Mã đề {currentVersion.version_code}
                    </h2>
                    <p className="text-xs text-muted mt-0.5">
                      {isTeacherMode
                        ? 'Chế độ giáo viên: kiểm tra nội dung, đáp án và lời giải trước khi phê duyệt.'
                        : 'Chế độ học sinh: xem cấu trúc đề thi thực tế (ẩn đáp án và lời giải).'}
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
                          <span className={`text-xs text-muted ${isTeacherMode ? 'inline' : 'hidden'}`}>
                            [Gốc: #{q.canonical_question_no}]
                          </span>
                        </div>
                        <span className="text-xs text-muted flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-approved-ink" />
                          Đã duyệt
                        </span>
                      </div>

                      {/* Question Content */}
                      <div className="text-ink text-base leading-relaxed min-w-0 overflow-x-auto">
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
                                isCorrect && isTeacherMode
                                  ? 'bg-approved-bg border-approved-border text-approved-ink'
                                  : 'bg-surface border-line text-ink'
                              }`}
                            >
                              <span
                                className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold shrink-0 ${
                                  isCorrect && isTeacherMode
                                    ? 'bg-approved-ink text-white'
                                    : 'bg-rail text-muted'
                                }`}
                              >
                                {optionLabel}
                              </span>
                              <div className="flex-1 min-w-0 overflow-x-auto text-sm pt-0.5">
                                <MathRenderer content={String(opt)} inline />
                              </div>
                              {isTeacherMode && isCorrect && (
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
                      {isTeacherMode && q.solution_md && (
                        <div className="mt-4 pt-3 border-t border-line min-w-0 overflow-x-auto">
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
            {isTeacherMode && selectedTab === 'matrix' && (
              <div
                role="tabpanel"
                id="tabpanel-matrix"
                aria-labelledby="tab-matrix"
                tabIndex={0}
                className="space-y-4 focus:outline-none"
              >
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
              <div className="p-3.5 rounded-lg bg-danger-soft border border-danger-border text-danger text-xs flex flex-col gap-2">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                  <p className="flex-1">{approveError}</p>
                </div>
                <button
                  type="button"
                  disabled={loading}
                  onClick={async () => {
                    const targetSessionId = sessionId;
                    const data = await loadData();
                    if (
                      !isMountedRef.current ||
                      activeSessionIdRef.current !== targetSessionId
                    ) {
                      return;
                    }
                    if (['approved', 'exported'].includes(data?.status)) {
                      setIsApproveModalOpen(false);
                      navigate(exportPath(targetSessionId));
                    }
                  }}
                  className="self-start rounded-md border border-danger-border bg-surface px-3 py-1 text-xs font-semibold text-danger hover:bg-danger/10 transition-colors disabled:opacity-50"
                >
                  Kiểm tra trạng thái
                </button>
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
