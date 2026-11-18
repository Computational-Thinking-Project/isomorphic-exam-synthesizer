import MathRenderer from '../../components/MathRenderer.jsx';

export default function SourceQuestionPreview({ questions }) {
  return (
    <section
      aria-label="Nguồn đề đã lưu"
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-soft"
    >
      <header className="border-b border-line bg-surface px-5 py-3.5">
        <h3 className="text-sm font-bold text-strong flex items-center justify-between">
          <span>Bản đọc đề nguồn · {questions.length} câu nguồn</span>
        </h3>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        {questions.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center rounded-xl border border-dashed border-line p-6 text-center text-xs text-muted">
            <p>Phiên chưa có câu nguồn đã lưu.</p>
            <p className="mt-1">Nhập văn bản hoặc tải tệp ở khung bên cạnh để nạp đề.</p>
          </div>
        ) : (
          <ol className="space-y-6">
            {questions.map((question) => (
              <li
                key={question.id}
                className="min-w-0 space-y-3 border-b border-line pb-6 last:border-b-0 last:pb-0"
              >
                <div className="flex items-center gap-2 border-b border-line/60 pb-2.5">
                  <span className="rounded-lg bg-support-bg px-2.5 py-0.5 text-xs font-bold text-highlight border border-support-line">
                    {Number.isInteger(question.question_no)
                      ? `Câu ${question.question_no}`
                      : 'Câu nguồn'}
                  </span>
                  <span className="text-xs text-muted">Đề gốc</span>
                </div>

                <div className="min-w-0 overflow-x-auto overflow-y-hidden py-2 text-sm text-strong leading-relaxed">
                  <MathRenderer
                    content={
                      typeof question.raw_content === 'string'
                        ? question.raw_content
                        : 'Chưa có nội dung câu.'
                    }
                  />
                </div>

                {/* Danh sách phương án A - D */}
                <ol className="space-y-2 pt-1">
                  {['A', 'B', 'C', 'D'].map((key) => {
                    const isKey = question.correct_key === key;
                    return (
                      <li
                        key={key}
                        aria-label={isKey ? `Phương án ${key} đúng` : undefined}
                        className={`flex items-start justify-between gap-2 rounded-xl p-2.5 border transition-all ${
                          isKey
                            ? 'border-approved-border bg-approved-bg text-approved-ink font-semibold shadow-soft'
                            : 'border-zinc-200/60 bg-white/60 text-ink hover:border-zinc-300'
                        }`}
                      >
                        <div className="flex items-start gap-2 min-w-0 flex-1">
                          <span
                            className={`text-xs font-bold ${
                              isKey ? 'text-approved-ink' : 'text-muted'
                            }`}
                          >
                            {key}.
                          </span>
                          <div className={`min-w-0 overflow-x-auto overflow-y-hidden py-1 ${isKey ? 'keyed-content' : ''}`}>
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


                      </li>
                    );
                  })}
                </ol>

                {!['A', 'B', 'C', 'D'].includes(question.correct_key) && (
                  <p className="pt-1 text-xs text-muted">Đáp án: Chưa xác định</p>
                )}

                {question.solution_md ? (
                  <div className="mt-2 rounded-xl border border-line bg-rail p-3 text-xs text-ink leading-relaxed">
                    <span className="font-semibold text-strong block mb-1">Lời giải chi tiết:</span>
                    <MathRenderer content={question.solution_md} />
                  </div>
                ) : (
                  <p className="mt-1 text-xs italic text-muted">
                    Đề gốc chưa kèm lời giải; bạn vẫn có thể tiếp tục.
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
