import { useEffect, useRef, useState } from 'react';
import { listExportFiles, downloadExportFile } from '../../services/exportService.js';

export default function ExportFiles({ sessionId, isCurrent }) {
  const [format, setFormat] = useState('pdf');
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const request = useRef(null);

  useEffect(() => {
    const abort = new AbortController();
    request.current = abort;
    setBusy(null);
    setFiles([]);
    setError('');
    setLoading(true);
    listExportFiles(sessionId, format, { signal: abort.signal })
      .then((items) => { if (!abort.signal.aborted && isCurrent()) setFiles(items); })
      .catch(() => { if (!abort.signal.aborted && isCurrent()) setError('Không tải được danh sách tài liệu. Vui lòng thử lại.'); })
      .finally(() => { if (!abort.signal.aborted && isCurrent()) setLoading(false); });
    return () => abort.abort();
  }, [sessionId, format, isCurrent, reload]);

  async function download(filename) {
    const abort = request.current;
    const current = () => abort && !abort.signal.aborted && isCurrent();
    if (!current()) return;
    setBusy(filename);
    setError('');
    try {
      const blob = await downloadExportFile(sessionId, format, filename, { signal: abort.signal });
      if (!current()) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      if (current()) setError('Không tải được tài liệu. Vui lòng thử lại.');
    } finally {
      if (current()) setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <label className="block text-sm font-semibold text-strong">
        Định dạng tài liệu
        <select
          value={format}
          disabled={busy !== null}
          onChange={(event) => setFormat(event.target.value)}
          className="ml-3 rounded-lg border border-line bg-surface px-3 py-2"
        >
          <option value="pdf">PDF</option>
          <option value="tex">LaTeX (.tex)</option>
          <option value="md">Markdown (.md)</option>
        </select>
      </label>
      {loading && <p role="status">Đang tải danh sách tài liệu…</p>}
      {error && <div role="alert">{error} <button type="button" onClick={() => setReload((value) => value + 1)}>Thử lại</button></div>}
      {!loading && !error && files.length === 0 && <p>Chưa có tài liệu ở định dạng này.</p>}
      <ul className="space-y-2">
        {files.map((file) => (
          <li key={file.filename}>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void download(file.filename)}
              className="min-h-[44px] rounded-xl bg-highlight px-4 py-2 font-semibold text-white disabled:opacity-50"
            >
              {busy === file.filename ? 'Đang tải…' : `Tải ${file.filename}`}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
