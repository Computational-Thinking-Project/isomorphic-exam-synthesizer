import { AlertTriangle, CheckCircle2, FileText } from 'lucide-react';
import MathRenderer from '../../components/MathRenderer.jsx';

const VALID_OPTION_KEYS = ['A', 'B', 'C', 'D'];

/**
 * Read-only preview of saved source questions and answers (hides canonical Blueprint metadata).
 */
export default function SourceQuestionPreview({ questions }) {
  const invalidKeyCount = questions.filter((q) => !VALID_OPTION_KEYS.includes(q.correct_key)).length;

  return (
    <section
      aria-label="Nguồn đề đã lưu"
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-soft"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-5 py-3.5">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 shrink-0 text-highlight" aria-hidden="true" />
          <h3 className="text-sm font-bold text-strong">
            Bản đọc đề nguồn · {questions.length} câu nguồn
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {invalidKeyCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md border border-accent-border bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent-ink">
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              {invalidKeyCount} câu thiếu đáp án
            </span>
          )}
          <span className="rounded-md border border-line bg-rail px-2 py-0.5 text-[11px] font-medium text-muted">
            Chỉ đọc
          </span>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        {questions.length === 0 ? (
          <div className="flex h-full min-h-[16rem] flex-col items-center justify-center rounded-xl border border-dashed border-line bg-canvas/50 p-6 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-support-line bg-support-bg text-highlight">
              <FileText className="h-5 w-5" aria-hidden="true" />
            </div>
            <p className="mt-3 text-sm font-semibold text-strong">
              Phiên chưa có câu nguồn đã lưu.
            </p>
            <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted">
              Nhập văn bản hoặc tải tệp ở khung bên cạnh để nạp đề.
            </p>
            <ol className="mt-4 w-full max-w-sm space-y-1.5 rounded-xl border border-line bg-surface p-3.5 text-left text-xs text-ink">
              <li>1. Dán đề kèm 4 phương án A–D và đáp án, hoặc chọn tệp DOCX, TeX, MD.</li>
              <li>2. Bấm <strong>Nạp nguồn</strong> để kiểm tra hiển thị công thức và đáp án.</li>
              <li>3. Bấm <strong>Xác nhận đề gốc và tiếp tục</strong> khi bản đọc đã chính xác.</li>
            </ol>
          </div>
        ) : (
          <ol className="space-y-4">
            {questions.map((question) => {
              const hasValidKey = VALID_OPTION_KEYS.includes(question.correct_key);
              return (
                <li
                  key={question.id}
                  className="min-w-0 space-y-3 rounded-xl border border-line bg-canvas/40 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 pb-2.5">
                    <div className="flex items-center gap-2">
                      <span className="rounded-lg border border-support-line bg-support-bg px-2.5 py-0.5 text-xs font-bold text-highlight">
                        {Number.isInteger(question.question_no)
                          ? `Câu ${question.question_no}`
                          : 'Câu nguồn'}
                      </span>
                      <span className="text-xs text-muted">Đề gốc</span>
                    </div>
                    {!hasValidKey && (
                      <span className="inline-flex items-center gap-1 rounded-md border border-accent-border bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent-ink">
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                        Chưa xác định đáp án
                      </span>
                    )}
                  </div>

                  <div className="min-w-0 overflow-x-auto overflow-y-hidden py-1 text-sm leading-relaxed text-strong">
                    <MathRenderer
                      content={
                        typeof question.raw_content === 'string'
                          ? question.raw_content
                          : 'Chưa có nội dung câu.'
                      }
                    />
                  </div>

                  <ol className="space-y-2 pt-1">
                    {VALID_OPTION_KEYS.map((key) => {
                      const isKey = question.correct_key === key;
                      return (
                        <li
                          key={key}
                          aria-label={isKey ? `Phương án ${key} đúng` : undefined}
                          className={`flex items-start justify-between gap-2 rounded-xl border p-2.5 transition-colors ${
                            isKey
                              ? 'border-approved-border bg-approved-bg text-approved-ink font-semibold shadow-soft'
                              : 'border-line bg-surface text-ink'
                          }`}
                        >
                          <div className="flex min-w-0 flex-1 items-start gap-2">
                            <span
                              className={`pt-0.5 text-xs font-bold ${
                                isKey ? 'text-approved-ink' : 'text-muted'
                              }`}
                            >
                              {key}.
                            </span>
                            <div
                              className={`min-w-0 overflow-x-auto overflow-y-hidden py-0.5 text-sm ${
                                isKey ? 'keyed-content' : ''
                              }`}
                            >
                              <MathRenderer
                                inline
                                content={
                                  typeof question.options?.[key] === 'string'
                                    ? question.options[key]
                                    : 'Chưa có phương án.'
                                }
                              />
                            </div>
                          </div>
                          {isKey && (
                            <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-approved-border bg-surface px-2 py-0.5 text-[11px] font-semibold text-approved-ink">
                              <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                              Đúng
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ol>

                  {!hasValidKey && (
                    <p className="pt-1 text-xs text-muted">Đáp án: Chưa xác định</p>
                  )}

                  {question.solution_md ? (
                    <div className="mt-2 min-w-0 overflow-x-auto rounded-xl border border-line bg-surface p-3 text-xs leading-relaxed text-ink">
                      <span className="mb-1 block font-semibold text-strong">Lời giải chi tiết:</span>
                      <MathRenderer content={question.solution_md} />
                    </div>
                  ) : (
                    <p className="mt-1 text-xs italic text-muted">
                      Đề gốc chưa kèm lời giải; bạn vẫn có thể tiếp tục.
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}
