import { useEffect, useState, useCallback } from 'react';
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
  X,
} from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';
import {
  fetchFinalizePreview,
  executeFullShuffle,
  triggerFinalizeApprove,
} from '../../services/stage3PreviewService.js';
import { stage3Path, exportPath } from '../../sessionPaths.js';

export default function Stage3PreviewPage() {
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

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast(null);
    }, 4000);
  };

  const loadData = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);

    try {
      const data = await fetchFinalizePreview(sessionId);
      setPreviewData(data);
      setNeedsShuffle(!data.is_finalized);
      if (data.versions?.length > 0 && !selectedTab) {
        setSelectedTab(data.versions[0].version_code);
      }
    } catch (err) {
      // 409 ERR_SHUFFLE_REQUIRED: Session ở trạng thái reviewed nhưng chưa shuffle
      if (err.status === 409 || err.errorCode === 'ERR_SHUFFLE_REQUIRED') {
        setNeedsShuffle(true);
        setError(null);
      } else if (err.status === 423) {
        // Đã khóa, cố nạp dữ liệu ở chế độ view-only
        setError('Phiên làm việc đã được phê duyệt và khóa nội dung.');
      } else {
        setError(err.message || 'Không thể tải bản xem trước đề thi.');
      }
    } finally {
      setLoading(false);
    }
  }, [sessionId, selectedTab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Tự động chọn tab đầu tiên khi có dữ liệu versions
  useEffect(() => {
    if (previewData?.versions?.length > 0 && (!selectedTab || selectedTab === 'matrix')) {
      if (!selectedTab) {
        setSelectedTab(previewData.versions[0].version_code);
      }
    }
  }, [previewData, selectedTab]);

  // Xử lý bấm nút duy nhất: Xáo trộn mã đề
  const handleShuffle = async () => {
    setShuffling(true);
    setError(null);
    try {
      await executeFullShuffle(sessionId);
      showToast('Đã xáo trộn các mã đề và cập nhật đáp án thành công!', 'success');
      await loadData();
    } catch (err) {
      showToast(err.message || 'Không thể thực hiện xáo trộn đề thi.', 'error');
    } finally {
      setShuffling(false);
    }
  };

  // Xử lý Phê duyệt cuối cùng & Khóa đề (HTTP 423)
  const handleApprove = async () => {
    setApproving(true);
    setApproveError(null);
    try {
      await triggerFinalizeApprove(sessionId);
      setIsApproveModalOpen(false);
      showToast('Đã phê duyệt và khóa đề thi thành công!', 'success');
      // Chuyển tiếp sang Stage 4 Export
      navigate(exportPath(sessionId));
    } catch (err) {
      setApproveError(err.message || 'Có lỗi xảy ra khi phê duyệt đề thi.');
    } finally {
      setApproving(false);
    }
  };

  const isLocked = previewData?.status === 'approved' || previewData?.status === 'exported';
  const currentVersion = previewData?.versions?.find((v) => v.version_code === selectedTab);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      {/* Toast Notification */}
      {toast && (
        <div
          role="status"
          className={`fixed top-4 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border text-sm transition-all animate-in fade-in slide-in-from-top-2 ${
            toast.type === 'error'
              ? 'bg-rose-950/90 border-rose-500/50 text-rose-200'
              : 'bg-emerald-950/90 border-emerald-500/50 text-emerald-200'
          }`}
        >
          {toast.type === 'error' ? (
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
          ) : (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          )}
          <p>{toast.message}</p>
        </div>
      )}

      {/* Header bar */}
      <header className="border-b border-slate-800 bg-slate-950/80 sticky top-0 z-20 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              type="button"
              data-testid="btn-back"
              onClick={() => navigate(stage3Path(sessionId))}
              className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors py-1.5 px-2.5 rounded-lg hover:bg-slate-800"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Quay lại duyệt từng câu</span>
            </button>
            <div className="h-4 w-px bg-slate-800" />
            <h1 className="text-base sm:text-lg font-semibold text-slate-100 flex items-center gap-2">
              <span>Rà soát & Phê duyệt đề thi (Stage 3)</span>
            </h1>
          </div>

          <div className="flex items-center gap-3">
            {/* Status badge */}
            {isLocked ? (
              <span
                data-testid="badge-status-locked"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              >
                <Lock className="w-3.5 h-3.5" />
                Đã phê duyệt & Khóa đề (HTTP 423)
              </span>
            ) : needsShuffle ? (
              <span
                data-testid="badge-status-pending"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Chờ xáo trộn mã đề
              </span>
            ) : (
              <span
                data-testid="badge-status-ready"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-sky-500/10 text-sky-400 border border-sky-500/30"
              >
                <Check className="w-3.5 h-3.5" />
                Đã xáo trộn · Sẵn sàng duyệt
              </span>
            )}

            {/* Header Action Buttons */}
            {!isLocked && !needsShuffle && (
              <button
                type="button"
                data-testid="btn-open-approve"
                onClick={() => setIsApproveModalOpen(true)}
                disabled={shuffling}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition-colors shadow-sm disabled:opacity-50"
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
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-medium text-sm transition-colors shadow-sm"
              >
                <FileText className="w-4 h-4" />
                <span>Chuyển sang màn hình Xuất bản</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-sky-500" />
            <p className="text-sm">Đang tải bản chiếu xem trước đề thi...</p>
          </div>
        ) : error && !needsShuffle ? (
          <div className="p-6 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-200 max-w-2xl mx-auto my-12 text-center">
            <AlertCircle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold mb-2">Không thể tải bản xem trước</h2>
            <p className="text-sm text-rose-300 mb-6">{error}</p>
            <button
              type="button"
              data-testid="btn-retry"
              onClick={() => loadData()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-sm font-medium transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Thử lại</span>
            </button>
          </div>
        ) : needsShuffle ? (
          /* Trạng thái chưa xáo trộn: Thẻ hướng dẫn và NÚT DUY NHẤT "Xáo trộn mã đề" */
          <div className="max-w-xl mx-auto my-16 p-8 rounded-2xl bg-slate-950/60 border border-slate-800 text-center shadow-xl">
            <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center mx-auto mb-5">
              <Sparkles className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-slate-100 mb-2">
              Toàn bộ câu hỏi đã được duyệt thành công
            </h2>
            <p className="text-sm text-slate-400 leading-relaxed mb-6">
              Tất cả các câu hỏi biến thể của các mã đề đã được thẩm định đạt yêu cầu.
              Nhấn nút bên dưới để hệ thống thực hiện xáo trộn ngẫu nhiên thứ tự các câu hỏi
              và các phương án A, B, C, D cho toàn bộ các mã đề thi.
            </p>
            <button
              type="button"
              data-testid="btn-shuffle"
              onClick={handleShuffle}
              disabled={shuffling}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-base transition-all shadow-md hover:shadow-amber-500/20 disabled:opacity-50"
            >
              {shuffling ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Đang xáo trộn các mã đề...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-5 h-5" />
                  <span>Xáo trộn mã đề</span>
                </>
              )}
            </button>
          </div>
        ) : (
          /* Bản xem trước hoàn chỉnh khi đã xáo trộn */
          <div className="space-y-6">
            {/* Locked Notice Banner */}
            {isLocked && (
              <div
                data-testid="banner-locked"
                className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/30 flex items-center justify-between text-emerald-200"
              >
                <div className="flex items-center gap-3">
                  <Lock className="w-5 h-5 text-emerald-400 shrink-0" />
                  <div>
                    <h3 className="text-sm font-semibold text-emerald-100">
                      Đề thi đã được phê duyệt và khóa nội dung vĩnh viễn (HTTP 423)
                    </h3>
                    <p className="text-xs text-emerald-300/80">
                      Nội dung đề thi và ma trận đáp án không thể thay đổi. Bạn có thể xem bản in hoặc chuyển sang bước xuất bản.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => navigate(exportPath(sessionId))}
                  className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors shrink-0 ml-4"
                >
                  Tới màn hình Xuất bản
                </button>
              </div>
            )}

            {/* Navigation Tabs (Version Codes + Answers Matrix) */}
            <div className="border-b border-slate-800">
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
                        ? 'border-sky-500 text-sky-400 bg-sky-500/5'
                        : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    <FileText className="w-4 h-4" />
                    <span>Mã đề {ver.version_code}</span>
                    <span className="text-xs py-0.5 px-2 rounded-full bg-slate-800 text-slate-400">
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
                      ? 'border-sky-500 text-sky-400 bg-sky-500/5'
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
                  }`}
                >
                  <Grid className="w-4 h-4" />
                  <span>Ma trận đáp án đối soát</span>
                </button>
              </nav>
            </div>

            {/* Tab Content: Version Exam Viewer */}
            {selectedTab !== 'matrix' && currentVersion && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-bold text-slate-100">
                      Bản in Đề thi — Mã đề {currentVersion.version_code}
                    </h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Đã được xáo trộn câu hỏi và phương án ngẫu nhiên. Đáp án đúng và lời giải đã được đồng bộ tự động.
                    </p>
                  </div>
                </div>

                <div className="space-y-6">
                  {currentVersion.questions?.map((q) => (
                    <article
                      key={q.id || q.question_no}
                      data-testid={`question-card-${q.question_no}`}
                      className="p-6 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4"
                    >
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                        <div className="flex items-center gap-3">
                          <span className="px-2.5 py-1 rounded bg-slate-800 text-sky-300 font-bold text-sm">
                            Câu {q.question_no}
                          </span>
                          <span className="text-xs text-slate-500">
                            [Gốc: #{q.canonical_question_no}]
                          </span>
                        </div>
                        <span className="text-xs text-slate-400 flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-emerald-400" />
                          Đã duyệt
                        </span>
                      </div>

                      {/* Question Content */}
                      <div className="text-slate-200 text-base leading-relaxed">
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
                                  ? 'bg-emerald-950/30 border-emerald-500/50 text-emerald-200'
                                  : 'bg-slate-900/60 border-slate-800 text-slate-300'
                              }`}
                            >
                              <span
                                className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold shrink-0 ${
                                  isCorrect
                                    ? 'bg-emerald-500 text-slate-950'
                                    : 'bg-slate-800 text-slate-400'
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
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-400 shrink-0"
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
                        <div className="mt-4 pt-3 border-t border-slate-800/80">
                          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                            Lời giải chi tiết
                          </h4>
                          <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-800 text-slate-300 text-sm leading-relaxed">
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
                  <h2 className="text-lg font-bold text-slate-100">
                    Bảng ma trận đối soát đáp án các mã đề
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Đối chiếu nhanh phân bố đáp án đúng của từng câu hỏi qua tất cả các mã đề thi đã hoán vị.
                  </p>
                </div>

                <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60">
                  <table data-testid="matrix-table" className="w-full text-left text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 bg-slate-900/80 text-slate-400 text-xs uppercase font-medium">
                        <th className="py-3 px-4 w-28">Câu số</th>
                        {previewData?.versions?.map((v) => (
                          <th key={v.version_code} className="py-3 px-4">
                            Mã đề {v.version_code}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {previewData?.matrix?.map((row) => (
                        <tr key={row.question_no} className="hover:bg-slate-900/40 transition-colors">
                          <td className="py-3 px-4 font-semibold text-slate-300">
                            Câu {row.question_no}
                          </td>
                          {previewData?.versions?.map((v) => {
                            const ans = row.answers?.[v.version_code] || '-';
                            return (
                              <td key={v.version_code} className="py-3 px-4">
                                <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
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
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in"
        >
          <div className="w-full max-w-lg rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-2xl space-y-6">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0">
                  <Lock className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100">
                    Xác nhận phê duyệt & Khóa đề thi
                  </h3>
                  <p className="text-xs text-slate-400">Kích hoạt vĩnh viễn HTTP 423 Content Lock</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsApproveModalOpen(false)}
                className="text-slate-400 hover:text-slate-200 p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-200 text-xs leading-relaxed flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-100 mb-1">
                  Hành động này không thể hoàn tác!
                </p>
                <p>
                  Sau khi phê duyệt, toàn bộ câu hỏi, phương án xáo trộn, đáp án và lời giải của tất cả {previewData?.n_versions || 0} mã đề sẽ được khóa vĩnh viễn trên cơ sở dữ liệu. Bạn sẽ được chuyển sang màn hình xuất bản file (Export).
                </p>
              </div>
            </div>

            {approveError && (
              <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                <p>{approveError}</p>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                data-testid="btn-cancel-approve"
                disabled={approving}
                onClick={() => setIsApproveModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 text-sm font-medium transition-colors disabled:opacity-50"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                data-testid="btn-confirm-approve"
                disabled={approving}
                onClick={handleApprove}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition-colors shadow-md disabled:opacity-50"
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
