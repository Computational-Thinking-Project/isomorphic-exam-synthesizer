import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import DashboardPage from './DashboardPage.jsx';
import { listDashboardSessions } from './dashboardMock.js';
import '../../index.css';

const loaders = {
  success: () => listDashboardSessions(),
  empty: () => listDashboardSessions({ scenario: 'empty' }),
  error: () => listDashboardSessions({ scenario: 'error' }),
};

function DashboardPreview() {
  const [scenario, setScenario] = useState('success');
  const [notice, setNotice] = useState('');

  function handleScenarioChange(event) {
    setScenario(event.target.value);
    setNotice('');
  }

  return (
    <>
      <aside className="mx-auto max-w-6xl border-b border-slate-700 px-4 py-6">
        <p className="mb-3 font-medium text-amber-300">
          Xem thử Dashboard — dữ liệu mẫu, chưa nối API
        </p>

        <label htmlFor="dashboard-scenario" className="mr-3">
          Tình huống:
        </label>
        <select
          id="dashboard-scenario"
          value={scenario}
          onChange={handleScenarioChange}
          className="rounded-lg border border-slate-600 bg-slate-900 p-2"
        >
          <option value="success">Có dữ liệu</option>
          <option value="empty">Danh sách rỗng</option>
          <option value="error">Lỗi tải danh sách</option>
        </select>

        <p role="status" className="mt-3 break-words text-sm text-slate-300">
          {notice}
        </p>
      </aside>

      <DashboardPage
        key={scenario}
        loadSessions={loaders[scenario]}
        onCreate={() => {
          setNotice('Đã nhận thao tác Tạo đề mới; chưa chuyển màn.');
        }}
        onOpen={(session) => {
          setNotice(`Đã chọn mở: ${session.title} (${session.id}).`);
        }}
        onClone={(session) => {
          setNotice(`Đã chọn nhân bản: ${session.title} (${session.id}).`);
        }}
      />
    </>
  );
}

if (import.meta.env.DEV) {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <DashboardPreview />
    </StrictMode>,
  );
}