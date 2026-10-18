import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import MathRenderer from './MathRenderer.jsx';
import '../../index.css';

const sampleVariant = {
  question:
    'Gieo đồng thời hai con xúc xắc cân đối và đồng chất. Xác định xác suất để giá trị tuyệt đối của hiệu hai số xuất hiện trên mặt xúc xắc là một nghiệm của phương trình bậc hai $x^2 - 5x + 4 = 0$?',
  options: [
    '$\\dfrac{7}{18}$',
    '$\\dfrac{5}{18}$',
    '$\\dfrac{1}{3}$',
    '$\\dfrac{11}{36}$',
  ],
  correct_answer: '$\\dfrac{7}{18}$',
  solution_steps:
    '1. Giải phương trình $x^2 - 5x + 4 = 0 \\iff (x-1)(x-4) = 0 \\iff x = 1$ hoặc $x = 4$.\n\n' +
    '2. Xét $x = 1$: Các cặp số $(a, b)$ có $|a - b| = 1$ là $(1,2), (2,3), (3,4), (4,5), (5,6)$ và hoán vị $\\rightarrow 10$ trường hợp.\n\n' +
    '3. Xét $x = 4$: Các cặp số $(a, b)$ có $|a - b| = 4$ là $(1,5), (2,6), (5,1), (6,2) \\rightarrow 4$ trường hợp.\n\n' +
    '4. Tổng số biến cố thuận lợi: $10 + 4 = 14$.\n\n' +
    '5. Xác suất cần tính: $$P = \\dfrac{14}{36} = \\dfrac{7}{18}$$',
};

const malformedLatexSample =
  'Công thức sai cú pháp không làm sập giao diện:\n\n- Thiếu ngoặc: $\\dfrac{1}{$\n- Lệnh không tồn tại: $\\khongtontai{x}$\n- Ký hiệu hợp lệ: $\\sqrt{x^2 + 1} \\ge 0$';

function MathPreview() {
  const [customText, setCustomText] = useState(
    'Nhập thử LaTeX vào đây: $E = mc^2$ hoặc $$\\int_{0}^{1} x^2 \\, dx = \\frac{1}{3}$$',
  );

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-8">
      <header className="border-b border-slate-700 pb-4">
        <span className="inline-block rounded-full bg-sky-950 px-3 py-1 text-xs font-semibold text-sky-400 border border-sky-800">
          TASK-105 Preview
        </span>
        <h1 className="mt-2 text-3xl font-bold">Xem thử MathRenderer (KaTeX + Markdown)</h1>
        <p className="mt-1 text-slate-400">
          Kiểm tra hiển thị công thức toán, tiếng Việt, đề mẫu từ contract fixtures và khả năng chống crash.
        </p>
      </header>

      {/* Phần 1: Đề mẫu từ variant.json */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold text-sky-300">1. Đề thi mẫu (Tương thích contract variant.json)</h2>
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-1">Nội dung câu hỏi:</h3>
          <MathRenderer content={sampleVariant.question} className="text-lg leading-relaxed" />
        </div>

        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-2">Các phương án lựa chọn:</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {sampleVariant.options.map((opt, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-slate-300">
                  {String.fromCharCode(65 + idx)}
                </span>
                <MathRenderer content={opt} inline />
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-1">Lời giải chi tiết:</h3>
          <div className="rounded-lg border border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-300">
            <MathRenderer content={sampleVariant.solution_steps} />
          </div>
        </div>
      </section>

      {/* Phần 2: Kiểm tra công thức lỗi (Graceful degradation) */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
        <h2 className="text-xl font-semibold text-amber-300">2. Khả năng chịu lỗi (Error Resilience)</h2>
        <p className="text-sm text-slate-400">
          Khi gặp LaTeX sai cú pháp, KaTeX tô đỏ vị trí lỗi thay vì ném ngoại lệ làm sập toàn bộ ứng dụng:
        </p>
        <div className="rounded-lg border border-slate-700 bg-slate-950/40 p-4">
          <MathRenderer content={malformedLatexSample} />
        </div>
      </section>

      {/* Phần 3: Trình thử nghiệm thời gian thực (Interactive Sandbox) */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold text-emerald-300">3. Thử nghiệm trực tiếp (Live Playground)</h2>
        <textarea
          rows={3}
          value={customText}
          onChange={(e) => setCustomText(e.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-sm text-slate-100 focus:border-sky-400 focus:outline-none"
          placeholder="Nhập nội dung Markdown hoặc LaTeX..."
        />
        <div>
          <span className="text-xs font-medium text-slate-400">Kết quả render thời gian thực:</span>
          <div className="mt-2 min-h-16 rounded-lg border border-slate-700 bg-slate-950/60 p-4">
            <MathRenderer content={customText} />
          </div>
        </div>
      </section>
    </main>
  );
}

if (import.meta.env.DEV) {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <MathPreview />
    </StrictMode>,
  );
}
