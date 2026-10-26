import { useEffect, useState, useSyncExternalStore } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuthStore } from '../auth/authStore.js';
import { createSession, getSessionDetail } from '../../services/sessions.js';
import { createSessionEntryController } from './sessionEntry.js';

const buttonClass = 'rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800 disabled:opacity-50';
const inputClass = 'mt-2 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2';

export default function Stage1Route() {
  const { sessionId } = useParams();
  const accountKey = useAuthStore((state) => `${state.user?.id ?? ''}:${state.sessionVersion}`);
  return <SessionEntry key={`${accountKey}:${sessionId}`} sessionId={sessionId} accountKey={accountKey} />;
}

function SessionEntry({ sessionId, accountKey }) {
  const navigate = useNavigate();
  const isNew = sessionId === 'new';
  const [metadata, setMetadata] = useState({ title: '', subject: 'Toán', grade: 12 });
  const [controller] = useState(() => createSessionEntryController({
    create: createSession,
    load: getSessionDetail,
    isCurrent: () => {
      const auth = useAuthStore.getState();
      return auth.status === 'authenticated' && `${auth.user?.id ?? ''}:${auth.sessionVersion}` === accountKey;
    },
    onCreated: (id) => navigate(`/session/${encodeURIComponent(id)}/stage1`, { replace: true }),
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);

  useEffect(() => {
    if (!isNew) void controller.load(sessionId);
    return () => controller.cancel();
  }, [controller, isNew, sessionId]);

  const creating = state.phase === 'creating' || state.phase === 'created';
  const update = (field, value) => setMetadata((previous) => ({ ...previous, [field]: value }));

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link to="/dashboard" className="text-sky-300 underline">Quay về Dashboard</Link>
      <h1 className="mt-6 text-3xl font-semibold">{isNew ? 'Tạo phiên đề mới' : 'Nguồn đề của phiên'}</h1>

      {isNew ? (
        <form className="mt-6 space-y-5" onSubmit={(event) => {
          event.preventDefault();
          void controller.submit(metadata);
        }}>
          <p className="text-slate-300">Nhập thông tin để tạo phiên. Bước này chưa tải lên hoặc xử lý nguồn đề.</p>
          <fieldset disabled={creating || state.createUncertain} className="space-y-5">
            <div>
              <label htmlFor="session-title">Tên phiên</label>
              <input id="session-title" value={metadata.title} required
                onChange={(event) => update('title', event.target.value)} className={inputClass} />
            </div>
            <div>
              <label htmlFor="session-subject">Môn học</label>
              <input id="session-subject" value={metadata.subject}
                onChange={(event) => update('subject', event.target.value)} className={inputClass} />
            </div>
            <div>
              <label htmlFor="session-grade">Khối lớp</label>
              <input id="session-grade" type="number" min="1" max="12" step="1" required
                value={metadata.grade} onChange={(event) => update('grade', event.target.value === '' ? '' : Number(event.target.value))}
                className={inputClass} />
            </div>
            <button type="submit" className={buttonClass}>{creating ? 'Đang tạo phiên…' : 'Tạo phiên'}</button>
          </fieldset>
          {creating && <p role="status">Đang lưu thông tin phiên…</p>}
        </form>
      ) : (
        <section className="mt-6" aria-label="Thông tin phiên">
          {(state.phase === 'idle' || state.phase === 'loading') && <p role="status">Đang tải phiên…</p>}
          {state.detail && (
            <>
              <h2 className="break-words text-xl font-semibold">{state.detail.title}</h2>
              <p className="mt-3 break-words">Môn: {state.detail.subject || 'Chưa ghi'} · Khối: {state.detail.grade}</p>
              {state.detail.status === 'draft' ? (
                <>
                  <p className="mt-3">Đang chuẩn bị · {state.detail.source_questions.length} câu nguồn · {state.detail.exam_versions.length} bản đề</p>
                  <p className="mt-4 text-slate-300">Đã mở đúng phiên. Phần nhập và xác nhận nguồn đề sẽ được bổ sung ở bước tiếp theo.</p>
                </>
              ) : (
                <p role="status" className="mt-4 text-slate-300">Phiên không còn ở trạng thái nháp. Quay về Dashboard để xem trạng thái mới; màn tiếp tục tương ứng chưa được kết nối.</p>
              )}
            </>
          )}
          {state.phase === 'error' && <button type="button" className={`${buttonClass} mt-4`} onClick={() => void controller.load(sessionId)}>Thử tải lại</button>}
        </section>
      )}
      {state.error && <p role="alert" className="mt-4 text-rose-300">{state.error}</p>}
    </main>
  );
}
