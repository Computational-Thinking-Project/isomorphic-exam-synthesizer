import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuthStore } from '../auth/authStore.js';
import { getSessionDetail } from '../../services/sessions.js';
import { createExportController } from './exportController.js';

const buttonClass = 'rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50';
const primaryButtonClass = 'rounded-lg bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50';

function defaultOpenDownload(url, filename) {
  if (typeof document === 'undefined') return;
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'exam_bundle.zip';
  link.rel = 'noopener noreferrer';
  link.click();
}

export default function SessionExportPage({
  loadSession = getSessionDetail,
  getStatus,
  triggerExport,
  issueDownloadUrl,
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
  openDownload,
}) {
  const isCurrent = useCallback(() => {
    const auth = useAuthStore.getState();
    return auth.status === 'authenticated' && `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey;
  }, [accountKey]);

  const [controller] = useState(() => createExportController({
    loadSession,
    getStatus,
    triggerExport,
    issueDownloadUrl,
    openDownload,
    isCurrent,
  }));

  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );

  useEffect(() => {
    void controller.load(sessionId);
    return () => controller.cancel();
  }, [controller, sessionId]);

  const isBusy = state.busyAction !== null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link to="/dashboard" className="text-sky-300 underline">
        Quay về Dashboard
      </Link>

      <h1 className="mt-6 text-3xl font-semibold">Xuất đề &amp; Tải gói ZIP</h1>

      {state.phase === 'loading' && (
        <p role="status" className="mt-6 text-slate-300">
          Đang tải thông tin xuất đề…
        </p>
      )}

      {state.detail && (
        <section className="mt-6 space-y-4 rounded-xl border border-slate-700 bg-slate-900/60 p-6">
          <div>
            <h2 className="break-words text-xl font-semibold">{state.detail.title}</h2>
            <p className="mt-2 text-sm text-slate-300">
              Môn: {state.detail.subject || 'Chưa ghi'} · Khối: {state.detail.grade} · Trạng thái: {state.detail.status}
            </p>
          </div>

          {state.phase === 'blocked' && (
            <p role="alert" className="rounded-lg border border-amber-700/60 bg-amber-950/40 p-4 text-amber-200">
              {state.error}
            </p>
          )}

          {state.phase === 'unwired' && (
            <p role="status" className="rounded-lg border border-slate-700 bg-slate-800/60 p-4 text-slate-300">
              Phiên đã sẵn sàng để xuất đề, nhưng kết nối API xuất file (Q10 / W4-MVP-08) chưa được nối vào giao diện.
            </p>
          )}

          {state.phase === 'ready_to_export' && (
            <div className="space-y-3">
              <p className="text-slate-300">
                Đề thi đã được duyệt cuối. Bấm nút bên dưới để đóng gói PDF, LaTeX, Markdown và đáp án thành file ZIP.
              </p>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.startExport()}
                className={primaryButtonClass}
              >
                {state.busyAction === 'export' ? 'Đang khởi tạo đóng gói…' : 'Tạo gói ZIP'}
              </button>
            </div>
          )}

          {state.phase === 'preparing' && (
            <div className="space-y-3">
              <p role="status" className="text-sky-200">
                Đang biên dịch PDF và đóng gói đề thi… Vui lòng giữ nguyên trang hoặc quay lại sau.
              </p>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.refreshStatus()}
                className={buttonClass}
              >
                {state.busyAction === 'refresh' ? 'Đang kiểm tra…' : 'Kiểm tra trạng thái'}
              </button>
            </div>
          )}

          {state.phase === 'poll_timeout' && (
            <div className="space-y-3">
              <p role="status" className="rounded-lg border border-amber-700/60 bg-amber-950/40 p-4 text-amber-200">
                {state.error}
              </p>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.refreshStatus()}
                className={buttonClass}
              >
                {state.busyAction === 'refresh' ? 'Đang kiểm tra…' : 'Kiểm tra trạng thái'}
              </button>
            </div>
          )}

          {state.phase === 'ready_to_download' && (
            <div className="space-y-4">
              <p role="status" className="text-emerald-300">
                Gói đề thi đã sẵn sàng để tải xuống ({state.artifact?.filename}).
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => void controller.download()}
                  className={primaryButtonClass}
                >
                  {state.busyAction === 'download' ? 'Đang lấy liên kết tải…' : 'Tải gói ZIP'}
                </button>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => void controller.refreshStatus()}
                  className={buttonClass}
                >
                  Làm mới trạng thái
                </button>
              </div>
            </div>
          )}

          {state.phase === 'failed' && (
            <div className="space-y-3">
              <p role="alert" className="rounded-lg border border-rose-700/60 bg-rose-950/40 p-4 text-rose-200">
                {state.error}
              </p>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.startExport()}
                className={primaryButtonClass}
              >
                {state.busyAction === 'export' ? 'Đang thử lại…' : 'Thử đóng gói lại'}
              </button>
            </div>
          )}

          {state.phase === 'error' && (
            <div className="space-y-3">
              <p role="alert" className="rounded-lg border border-rose-700/60 bg-rose-950/40 p-4 text-rose-200">
                {state.error}
              </p>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => void controller.refreshStatus()}
                className={buttonClass}
              >
                Kiểm tra trạng thái
              </button>
            </div>
          )}

          {state.phase === 'ready_to_download' && state.error && (
            <p role="alert" className="rounded-lg border border-rose-700/60 bg-rose-950/40 p-4 text-rose-200">
              {state.error}
            </p>
          )}
        </section>
      )}

      {!state.detail && state.phase === 'error' && (
        <div className="mt-6 space-y-4">
          <p role="alert" className="rounded-lg border border-rose-700/60 bg-rose-950/40 p-4 text-rose-200">
            {state.error}
          </p>
          <button
            type="button"
            disabled={isBusy}
            onClick={() => void controller.load(sessionId)}
            className={buttonClass}
          >
            Thử tải lại
          </button>
        </div>
      )}
    </main>
  );
}
