import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  Download,
  FileArchive,
  FileSpreadsheet,
  FileText,
  GraduationCap,
  Info,
  Key,
  Layers,
  LayoutGrid,
  Loader2,
  Lock,
  RefreshCw,
  Sliders,
} from 'lucide-react';
import { stage3PreviewPath } from '../../sessionPaths.js';
import { useAuthStore } from '../auth/authStore.js';
import { getSessionDetail } from '../../services/sessions.js';
import {
  getExportStatus,
  triggerExport as defaultTriggerExport,
  issueDownloadUrl as defaultIssueDownloadUrl,
  fetchAnswerKey as defaultFetchAnswerKey,
} from '../../services/exportService.js';
import { createExportController } from './exportController.js';

const buttonClass =
  'inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-semibold text-strong hover:bg-rail disabled:cursor-not-allowed disabled:opacity-50 transition-colors shadow-sm';
const primaryButtonClass =
  'inline-flex items-center gap-2 rounded-xl bg-highlight px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#253b57] disabled:cursor-not-allowed disabled:opacity-50 transition-all shadow-soft';

function formatBundleSize(sizeBytes) {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) return '';
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  const kb = sizeBytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

function defaultOpenDownload(url, filename) {
  if (typeof document === 'undefined') return;
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'exam_bundle.zip';
  link.rel = 'noopener noreferrer';
  link.click();
}

const AVAILABLE_VISIBLE_FIELDS = [
  { id: 'title', label: 'Tiêu đề đề thi' },
  { id: 'student_name', label: 'Họ và tên thí sinh' },
  { id: 'student_id', label: 'Số báo danh' },
  { id: 'student_class', label: 'Lớp / Phòng thi' },
  { id: 'school', label: 'Trường / Cơ quan chủ quản' },
  { id: 'subject', label: 'Môn học' },
  { id: 'exam_type', label: 'Loại kỳ thi' },
  { id: 'grade', label: 'Khối lớp' },
  { id: 'semester', label: 'Học kỳ' },
  { id: 'academic_year', label: 'Năm học' },
  { id: 'exam_date', label: 'Ngày thi' },
  { id: 'duration_minutes', label: 'Thời gian làm bài' },
];

const AVAILABLE_FORMATS = [
  { id: 'pdf', label: 'PDF chuẩn in ấn (.pdf)', note: 'Bắt buộc hoặc định dạng chính' },
  { id: 'tex', label: 'Mã nguồn XeLaTeX (.tex)', note: 'Dành cho biên tập viên và in ấn chuyên nghiệp' },
  { id: 'md', label: 'Văn bản Markdown (.md)', note: 'Đọc và lưu trữ dạng văn bản thuần' },
];

export default function SessionExportPage({
  loadSession = getSessionDetail,
  getStatus = getExportStatus,
  triggerExport = defaultTriggerExport,
  issueDownloadUrl = defaultIssueDownloadUrl,
  fetchAnswerKey = defaultFetchAnswerKey,
  openDownload = defaultOpenDownload,
}) {
  const { sessionId } = useParams();
  const accountKey = useAuthStore((state) => `${state.user?.id ?? ''}:${state.sessionVersion}`);

  return (
    <SessionExportView
      key={`${accountKey}:${sessionId}`}
      sessionId={sessionId}
      accountKey={accountKey}
      loadSession={loadSession}
      getStatus={getStatus}
      triggerExport={triggerExport}
      issueDownloadUrl={issueDownloadUrl}
      fetchAnswerKey={fetchAnswerKey}
      openDownload={openDownload}
    />
  );
}

function SessionExportView({
  sessionId,
  accountKey,
  loadSession,
  getStatus,
  triggerExport,
  issueDownloadUrl,
  fetchAnswerKey,
  openDownload,
}) {
  const isCurrent = useCallback(() => {
    const auth = useAuthStore.getState();
    return auth.status === 'authenticated' && `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey;
  }, [accountKey]);

  const [controller] = useState(() =>
    createExportController({
      loadSession,
      getStatus,
      triggerExport,
      issueDownloadUrl,
      fetchAnswerKey,
      openDownload,
      isCurrent,
    }),
  );

  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );

  useEffect(() => {
    void controller.load(sessionId, { accountKey });
    return () => controller.cancel();
  }, [controller, sessionId, accountKey]);

  const isBusy = state.busyAction !== null;
  const previewLink = sessionId ? stage3PreviewPath(sessionId) : '/dashboard';
  const showZipContents = ['ready_to_export', 'preparing', 'poll_timeout', 'ready_to_download', 'failed'].includes(state.phase);
  const statusLabel = state.detail?.status === 'exported'
    ? 'Đã xuất gói đề'
    : state.detail?.status === 'approved'
    ? 'Đã phê duyệt cuối'
    : state.detail?.status;
  const artifactSizeText = formatBundleSize(state.artifact?.size_bytes ?? state.artifact?.size);

  const selectedConfig = state.selectedConfig;

  const handleToggleVisibleField = (fieldId) => {
    const current = new Set(selectedConfig.visible_fields);
    if (current.has(fieldId)) {
      current.delete(fieldId);
    } else {
      current.add(fieldId);
    }
    controller.setConfig({ visible_fields: Array.from(current) });
  };

  const handleToggleFormat = (formatId) => {
    const current = new Set(selectedConfig.formats);
    if (current.has(formatId)) {
      if (current.size > 1) {
        current.delete(formatId);
      }
    } else {
      current.add(formatId);
    }
    controller.setConfig({ formats: Array.from(current) });
  };

  const handleChangeAnswerSheet = (sheetType) => {
    if (sheetType === 'omr_bubbles') return; // Khóa theo I-EXT-04
    controller.setConfig({ answer_sheet: sheetType });
  };

  const getIdentityBadge = () => {
    if (state.identityKind === 'configured') {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-highlight/10 px-2.5 py-0.5 text-xs font-semibold text-highlight border border-highlight/20">
          <Sliders className="w-3 h-3" />
          Gói xuất tùy chỉnh
        </span>
      );
    }
    if (state.identityKind === 'ext_default') {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-support-bg px-2.5 py-0.5 text-xs font-semibold text-highlight border border-support-line">
          <Layers className="w-3 h-3" />
          Gói EXT v3.1 mặc định (mã 101, 102...)
        </span>
      );
    }
    if (state.identityKind === 'legacy_default') {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2.5 py-0.5 text-xs font-semibold text-muted border border-line">
          Gói chuẩn MVP
        </span>
      );
    }
    return null;
  };

  return (
    <div className="session-export paper-ui min-h-screen bg-canvas text-strong font-sans py-6 sm:py-8 px-4 sm:px-6 lg:px-8">
      <main className="mx-auto max-w-3xl space-y-6">
        {/* Top Session Navigation & Step Badge */}
        <header className="space-y-3 border-b border-line pb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to="/dashboard"
                className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-highlight hover:bg-support-bg transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Thư viện đề</span>
              </Link>
              <span className="text-line" aria-hidden="true">/</span>
              <span className="inline-flex shrink-0 items-center rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 text-xs font-semibold text-highlight">
                Bước 3/3 · Xuất đề &amp; Tải gói ZIP
              </span>
            </div>
            <Link
              to={previewLink}
              data-testid="export-link-preview"
              className="inline-flex items-center gap-1.5 rounded-lg border border-support-line bg-support-bg px-3 py-1 text-xs font-semibold text-highlight hover:bg-highlight hover:text-white transition-colors"
            >
              <FileText className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Xem bản đã duyệt</span>
            </Link>
          </div>

          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-strong">Xuất đề &amp; Tải gói ZIP</h1>
            <p className="mt-1 text-sm text-muted leading-relaxed">
              Tùy chỉnh bố cục phiếu trả lời, trường hiển thị và tải về gói ZIP hoàn chỉnh hoặc tải riêng bảng đáp án.
            </p>
          </div>
        </header>

        {state.phase === 'loading' && (
          <div role="status" className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-6 text-muted shadow-soft">
            <Loader2 className="w-5 h-5 animate-spin text-highlight" />
            <p className="text-sm">Đang tải thông tin xuất đề…</p>
          </div>
        )}

        {state.detail && (
          <section className="rounded-2xl border border-line bg-surface p-6 sm:p-8 shadow-paper space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
              <div className="min-w-0 flex-1">
                <h2 className="break-words text-xl font-bold text-strong">{state.detail.title}</h2>
                <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 font-medium text-highlight">
                    <BookOpen className="h-3 w-3" aria-hidden="true" />
                    Môn: {state.detail.subject || 'Chưa ghi'}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-support-line bg-support-bg px-2.5 py-0.5 font-medium text-highlight">
                    <GraduationCap className="h-3 w-3" aria-hidden="true" />
                    Khối {state.detail.grade}
                  </span>
                  {getIdentityBadge()}
                </div>
              </div>
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-approved-bg px-3 py-1 text-xs font-semibold text-approved-ink border border-approved-border">
                <Lock className="h-3 w-3" aria-hidden="true" />
                {statusLabel}
              </span>
            </div>

            {/* FORM TÙY CHỌN CẤU HÌNH XUẤT ĐỀ (EXT-03) */}
            {showZipContents && (
              <div data-testid="export-config-panel" className="rounded-xl border border-line bg-canvas/60 p-5 space-y-5">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <div className="flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-highlight" aria-hidden="true" />
                    <h3 className="text-sm font-bold text-strong">Tùy chọn cấu hình xuất đề (EXT v3.1)</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => controller.resetConfig()}
                    className="text-xs text-muted hover:text-highlight transition-colors"
                  >
                    Khôi phục mặc định
                  </button>
                </div>

                {/* Khối 1: Trường hiển thị */}
                <div className="space-y-2.5">
                  <span className="block text-xs font-semibold text-strong uppercase tracking-wider">
                    1. Trường thông tin hiển thị trên trang bìa
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    {AVAILABLE_VISIBLE_FIELDS.map((field) => {
                      const isChecked = selectedConfig.visible_fields.includes(field.id);
                      return (
                        <label
                          key={field.id}
                          className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 cursor-pointer hover:bg-rail transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => handleToggleVisibleField(field.id)}
                            className="rounded border-line text-highlight focus:ring-highlight h-3.5 w-3.5"
                          />
                          <span className="text-ink font-medium">{field.label}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                {/* Khối 2: Mẫu phiếu trả lời */}
                <div className="space-y-2.5">
                  <span className="block text-xs font-semibold text-strong uppercase tracking-wider">
                    2. Mẫu phiếu trả lời trắc nghiệm
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                    {/* Không kèm */}
                    <label
                      onClick={() => handleChangeAnswerSheet('none')}
                      className={`flex flex-col justify-between rounded-xl border p-3 cursor-pointer transition-all ${
                        selectedConfig.answer_sheet === 'none'
                          ? 'border-highlight bg-highlight/5 text-strong ring-1 ring-highlight'
                          : 'border-line bg-surface text-ink hover:bg-rail'
                      }`}
                    >
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold">Không kèm phiếu</span>
                          <input
                            type="radio"
                            name="answer_sheet"
                            data-testid="radio-sheet-none"
                            checked={selectedConfig.answer_sheet === 'none'}
                            onClick={() => handleChangeAnswerSheet('none')}
                            onChange={() => handleChangeAnswerSheet('none')}
                            className="text-highlight focus:ring-highlight h-3.5 w-3.5"
                          />
                        </div>
                        <p className="text-[11px] text-muted leading-tight">
                          Đề thi truyền thống, thí sinh khoanh trực tiếp vào đề.
                        </p>
                      </div>
                    </label>

                    {/* Ô điền A/B/C/D */}
                    <label
                      onClick={() => handleChangeAnswerSheet('written_boxes')}
                      className={`flex flex-col justify-between rounded-xl border p-3 cursor-pointer transition-all ${
                        selectedConfig.answer_sheet === 'written_boxes'
                          ? 'border-highlight bg-highlight/5 text-strong ring-1 ring-highlight'
                          : 'border-line bg-surface text-ink hover:bg-rail'
                      }`}
                    >
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold">Ô điền A/B/C/D</span>
                          <input
                            type="radio"
                            name="answer_sheet"
                            data-testid="radio-sheet-written"
                            checked={selectedConfig.answer_sheet === 'written_boxes'}
                            onClick={() => handleChangeAnswerSheet('written_boxes')}
                            onChange={() => handleChangeAnswerSheet('written_boxes')}
                            className="text-highlight focus:ring-highlight h-3.5 w-3.5"
                          />
                        </div>
                        <p className="text-[11px] text-muted leading-tight">
                          Khung ô vuông đầu đề, giáo viên chấm nhanh hoặc thu trang đầu.
                        </p>
                      </div>
                      <span className="mt-2 inline-flex items-center gap-1 rounded bg-highlight/10 px-1.5 py-0.5 text-[10px] font-semibold text-highlight w-fit">
                        Khuyên dùng
                      </span>
                    </label>

                    {/* Phiếu OMR (Khóa) */}
                    <div
                      title="Đang kiểm định mẫu in thực tế theo I-EXT-04"
                      className="flex flex-col justify-between rounded-xl border border-line bg-surface/50 p-3 opacity-60 cursor-not-allowed text-muted"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold">Tô tròn OMR</span>
                          <input
                            type="radio"
                            name="answer_sheet"
                            data-testid="radio-sheet-omr"
                            disabled
                            checked={false}
                            className="text-line h-3.5 w-3.5 cursor-not-allowed"
                          />
                        </div>
                        <p className="text-[11px] leading-tight">
                          Mẫu tô tròn chuẩn máy chấm app TNMaker.
                        </p>
                      </div>
                      <span className="mt-2 inline-flex items-center gap-1 rounded bg-muted/20 px-1.5 py-0.5 text-[10px] font-semibold text-muted w-fit">
                        <Lock className="w-2.5 h-2.5" />
                        Đang kiểm định mẫu in
                      </span>
                    </div>
                  </div>
                </div>

                {/* Khối 3: Định dạng tệp xuất */}
                <div className="space-y-2.5">
                  <span className="block text-xs font-semibold text-strong uppercase tracking-wider">
                    3. Định dạng tài liệu đóng gói
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                    {AVAILABLE_FORMATS.map((fmt) => {
                      const isChecked = selectedConfig.formats.includes(fmt.id);
                      return (
                        <label
                          key={fmt.id}
                          className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 cursor-pointer hover:bg-rail transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => handleToggleFormat(fmt.id)}
                            className="rounded border-line text-highlight focus:ring-highlight h-3.5 w-3.5"
                          />
                          <div className="min-w-0">
                            <span className="text-ink font-semibold block">{fmt.label}</span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>

                {/* MINH HỌA TRỰC QUAN MẪU Ô ĐIỀN ĐÁP ÁN (written_boxes) */}
                {selectedConfig.answer_sheet === 'written_boxes' && (
                  <div
                    data-testid="written-boxes-preview"
                    className="rounded-xl border border-line bg-surface p-4 space-y-3 mt-4"
                  >
                    <div className="flex items-center justify-between border-b border-line pb-2">
                      <div className="flex items-center gap-2">
                        <LayoutGrid className="w-4 h-4 text-highlight" />
                        <span className="text-xs font-bold text-strong uppercase tracking-wide">
                          Minh họa mẫu ô điền đáp án (Đầu trang 1 đề thi)
                        </span>
                      </div>
                      <span className="text-[11px] text-muted">Bản mô phỏng</span>
                    </div>

                    <div className="rounded-lg border border-dashed border-line bg-canvas p-3 space-y-3 text-xs">
                      {/* Giả lập thông tin thí sinh */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 border-b border-line pb-2 font-mono text-[11px] text-muted">
                        <div>Họ &amp; tên: .................................</div>
                        <div>SBD: ....................</div>
                        <div>Lớp: ..............</div>
                      </div>

                      {/* Khung ô vuông số */}
                      <div className="space-y-1">
                        <p className="text-[11px] font-semibold text-strong">
                          BẢNG ĐIỀN ĐÁP ÁN TRẮC NGHIỆM (Học sinh điền A, B, C hoặc D):
                        </p>
                        <div className="overflow-x-auto pb-1">
                          <table className="w-full text-center border-collapse border border-line text-[11px]">
                            <thead>
                              <tr className="bg-rail font-semibold text-muted">
                                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((num) => (
                                  <th key={num} className="border border-line px-2 py-1 min-w-[28px]">
                                    {num}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((num) => (
                                  <td key={num} className="border border-line h-8 bg-surface text-line font-mono font-bold">
                                    &nbsp;
                                  </td>
                                ))}
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <p className="text-[10px] text-muted italic flex items-center gap-1">
                        <Info className="w-3 h-3 text-highlight shrink-0" />
                        Giáo viên có thể thu trang đầu hoặc đối chiếu nhanh với ma trận đáp án mà không cần lật từng trang.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {showZipContents && (
              <div
                data-testid="zip-structure-info"
                className="rounded-xl border border-line bg-canvas p-4 space-y-2 text-xs text-ink"
              >
                <div className="flex items-center gap-2 font-semibold text-strong">
                  <FileArchive className="h-4 w-4 text-highlight shrink-0" aria-hidden="true" />
                  <span>Nội dung gói ZIP (w4-export-v2 · chỉ tải trọn gói)</span>
                </div>
                <ul className="list-disc pl-5 space-y-1 text-muted">
                  <li>
                    Mỗi mã đề có 1 file PDF (<code className="text-strong">pdf/exam_&lt;mã&gt;.pdf</code>), 1 nguồn XeLaTeX (<code className="text-strong">latex/exam_&lt;mã&gt;.tex</code>) và 1 Markdown (<code className="text-strong">markdown/exam_&lt;mã&gt;.md</code>).
                  </li>
                  <li>
                    Cấu trúc mỗi tài liệu gồm: <strong>đề thi</strong> &rarr; <strong>ma trận đáp án</strong> &rarr; <strong>lời giải chi tiết</strong> (không hỗ trợ tải lẻ từng file hoặc từng mã).
                  </li>
                  <li>
                    Lưu ý khi phát đề: file đã kèm ma trận đáp án và lời giải ở các trang sau; chỉ gửi phần trang đề thi cho thí sinh.
                  </li>
                </ul>
              </div>
            )}

            {/* KHU VỰC TẢI ĐÁP ÁN RIÊNG BIỆT (EXT-03) */}
            {showZipContents && (
              <div
                data-testid="answer-key-section"
                className="rounded-xl border border-line bg-surface p-4 space-y-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-0.5">
                    <h3 className="text-sm font-bold text-strong flex items-center gap-1.5">
                      <Key className="w-4 h-4 text-highlight" />
                      <span>Tải bảng đáp án riêng biệt</span>
                    </h3>
                    <p className="text-xs text-muted">
                      Tải ngay file đáp án độc lập (CSV / JSON) mà không cần chờ hay giải nén gói ZIP đầy đủ.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      data-testid="download-answer-key-csv"
                      disabled={isBusy}
                      onClick={() => void controller.downloadAnswerKey({ target: 'session', format: 'csv' })}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-canvas px-3 py-1.5 text-xs font-semibold text-strong hover:bg-rail disabled:opacity-50 transition-colors shadow-sm"
                    >
                      {state.busyAction === 'answer_key' ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <FileSpreadsheet className="w-3.5 h-3.5 text-highlight" />
                      )}
                      <span>Tải đáp án (CSV)</span>
                    </button>
                    <button
                      type="button"
                      data-testid="download-answer-key-json"
                      disabled={isBusy}
                      onClick={() => void controller.downloadAnswerKey({ target: 'session', format: 'json' })}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-canvas px-3 py-1.5 text-xs font-semibold text-strong hover:bg-rail disabled:opacity-50 transition-colors shadow-sm"
                    >
                      {state.busyAction === 'answer_key' ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <FileText className="w-3.5 h-3.5 text-highlight" />
                      )}
                      <span>Tải đáp án (JSON)</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {state.phase === 'blocked' && (
              <div role="alert" className="rounded-xl border border-accent-border bg-accent-soft p-4 text-xs text-accent-ink flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 shrink-0 text-accent-ink mt-0.5" />
                <p>{state.error}</p>
              </div>
            )}

            {state.phase === 'unwired' && (
              <div role="status" className="rounded-xl border border-support-line bg-support-bg p-4 text-xs text-highlight flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-highlight mt-0.5" />
                <p>
                  Phiên đã sẵn sàng để xuất đề, nhưng tính năng xuất file hoàn chỉnh chưa được nối vào giao diện.
                </p>
              </div>
            )}

            {state.phase === 'ready_to_export' && (
              <div className="space-y-4">
                <p className="text-sm text-ink leading-relaxed">
                  Đề thi đã được duyệt cuối. Bấm nút bên dưới để đóng gói PDF, LaTeX, Markdown và đáp án thành file ZIP theo cấu hình đã chọn.
                </p>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.startExport()}
                    className={primaryButtonClass}
                  >
                    {state.busyAction === 'export' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang khởi tạo đóng gói…</span>
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" />
                        <span>Tạo gói ZIP</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'preparing' && (
              <div className="space-y-4">
                <div role="status" className="rounded-xl border border-support-line bg-support-bg p-4 text-xs text-highlight flex items-center gap-3">
                  <Loader2 className="w-4 h-4 animate-spin text-highlight shrink-0" />
                  <p>
                    Đang biên dịch PDF và đóng gói đề thi… Vui lòng giữ nguyên trang hoặc quay lại sau.
                  </p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    {state.busyAction === 'refresh' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang kiểm tra…</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Kiểm tra trạng thái</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'poll_timeout' && (
              <div className="space-y-4">
                <div role="status" className="rounded-xl border border-accent-border bg-accent-soft p-4 text-xs text-accent-ink flex items-start gap-2.5">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-accent-ink mt-0.5" />
                  <p>{state.error}</p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    {state.busyAction === 'refresh' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang kiểm tra…</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Kiểm tra trạng thái</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'ready_to_download' && (
              <div className="space-y-4">
                <div role="status" className="rounded-xl border border-approved-border bg-approved-bg p-4 text-xs text-approved-ink flex items-start gap-2.5">
                  <CheckCircle2 className="w-5 h-5 text-approved-ink shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="font-semibold">
                      Gói đề thi đã sẵn sàng để tải xuống ({state.artifact?.filename}).
                    </p>
                    {artifactSizeText && (
                      <p className="text-[11px] text-approved-ink">
                        Dung lượng gói ZIP: <strong>{artifactSizeText}</strong>
                      </p>
                    )}
                    {state.packagingKey && (
                      <p className="text-[11px] text-muted">
                        Mã gói: <code className="font-mono text-strong">{state.packagingKey}</code>
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.download()}
                    className={primaryButtonClass}
                  >
                    {state.busyAction === 'download' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang lấy liên kết tải…</span>
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" />
                        <span>Tải gói ZIP</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    <RefreshCw className="w-4 h-4" />
                    <span>Làm mới trạng thái</span>
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'failed' && (
              <div className="space-y-4">
                <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                  <p>{state.error}</p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.startExport()}
                    className={primaryButtonClass}
                  >
                    {state.busyAction === 'export' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Đang thử lại…</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Thử đóng gói lại</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'error' && (
              <div className="space-y-4">
                <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                  <p>{state.error}</p>
                </div>
                <div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void controller.refreshStatus()}
                    className={buttonClass}
                  >
                    <RefreshCw className="w-4 h-4" />
                    <span>Kiểm tra trạng thái</span>
                  </button>
                </div>
              </div>
            )}

            {state.phase === 'ready_to_download' && state.error && (
              <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
                <p>{state.error}</p>
              </div>
            )}
          </section>
        )}

        {!state.detail && state.phase === 'error' && (
          <div className="space-y-4">
            <div role="alert" className="rounded-xl border border-danger-border bg-danger-soft p-4 text-xs text-danger flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 text-danger mt-0.5" />
              <p>{state.error}</p>
            </div>
            <div>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.load(sessionId, { accountKey })}
                className={buttonClass}
              >
                <RefreshCw className="w-4 h-4" />
                <span>Thử tải lại</span>
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
