import React, { useEffect, useState } from 'react';

export default function App() {
  const [backendStatus, setBackendStatus] = useState<string>('Đang kiểm tra kết nối backend...');
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    fetch('/api/health/metrics')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setBackendStatus(`✅ Backend Operational (AI Model: ${data.gemini_model || 'N/A'})`);
        setLoading(false);
      })
      .catch((err) => {
        setBackendStatus(`⚠️ Chưa kết nối được Backend: ${err.message}`);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center items-center p-6">
      <div className="max-w-2xl w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center space-x-3 mb-4">
          <span className="text-3xl">📐</span>
          <h1 className="text-2xl font-bold text-sky-400">Isomorphic Exam Synthesizer</h1>
        </div>
        <p className="text-slate-400 mb-6 leading-relaxed">
          Hệ thống sinh đề thi trắc nghiệm Toán học đẳng cấu (Isomorphic Math Exam Synthesis),
          thẩm định 4 tầng (Syntax, Logic, SymPy CAS, Rule Fallback) và xuất bản đa định dạng.
        </p>

        <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 mb-6">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Trạng thái kết nối Hệ thống (Smoke Test Day 0)
          </h2>
          <div className="flex items-center space-x-2">
            <span
              className={`w-3 h-3 rounded-full ${
                loading ? 'bg-amber-400 animate-pulse' : backendStatus.startsWith('✅') ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
            />
            <span className="font-mono text-sm text-slate-200">{backendStatus}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-xs text-slate-400 border-t border-slate-800/80 pt-4">
          <div>
            <span className="block font-medium text-slate-300">Frontend:</span>
            React 18 + Vite + TypeScript (Port 3000)
          </div>
          <div>
            <span className="block font-medium text-slate-300">Backend:</span>
            FastAPI + Typst + SymPy (Port 8000)
          </div>
        </div>
      </div>
    </div>
  );
}
