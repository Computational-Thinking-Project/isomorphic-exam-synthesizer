import { useState } from 'react';
import { useAuthStore } from '../auth/authStore.js';
import DashboardPage from './DashboardPage.jsx';
import { listDashboardSessions } from './dashboardMock.js';

export default function DashboardRoute() {
  const [notice, setNotice] = useState('');
  const setUser = useAuthStore((state) => state.setUser);

  return (
    <>
      <aside className="mx-auto max-w-6xl border-b border-slate-700 px-4 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-amber-300">
            Dashboard đang dùng dữ liệu mẫu, chưa kết nối API.
          </p>

          {import.meta.env.DEV && (
            <button
              type="button"
              onClick={() => setUser(null)}
              className="rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800"
            >
              Đăng xuất mẫu
            </button>
          )}
        </div>

        <p role="status" className="mt-3 break-words text-sm text-slate-300">
          {notice}
        </p>
      </aside>

      <DashboardPage
        loadSessions={listDashboardSessions}
        onCreate={() => {
          setNotice('Đã nhận thao tác Tạo đề mới; chưa nối màn nhập nguồn.');
        }}
        onOpen={(session) => {
          setNotice(`Đã chọn mở: ${session.title} (${session.id}).`);
        }}
        onClone={(session) => {
          setNotice(`Đã chọn nhân bản: ${session.title}; đang chờ Clone Modal.`);
        }}
      />
    </>
  );
}