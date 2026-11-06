import MathRenderer from '../../components/MathRenderer.jsx';

export default function SourceQuestionPreview({ questions, versionCount = 0 }) {
  return (
    <section aria-label="Nguồn đề đã lưu" className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-600">
      <h3 className="border-b border-slate-600 px-4 py-3 font-semibold">
        Nguồn đã lưu · {questions.length} câu nguồn · {versionCount} bản đề
      </h3>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {questions.length === 0 ? <p>Phiên chưa có câu nguồn đã lưu.</p> : (
          <ol className="space-y-5">
            {questions.map((question) => (
              <li key={question.id} className="space-y-2 border-b border-slate-700 pb-4 last:border-0">
                <h4 className="font-semibold">{Number.isInteger(question.question_no) ? `Câu ${question.question_no}` : 'Câu nguồn'}</h4>
                <MathRenderer content={typeof question.raw_content === 'string' ? question.raw_content : 'Chưa có nội dung câu.'} />
                <ol className="space-y-2">
                  {['A', 'B', 'C', 'D'].map((key) => (
                    <li key={key} className={question.correct_key === key ? 'font-semibold' : ''}>
                      <span>{key}. </span>
                      <MathRenderer inline content={typeof question.options?.[key] === 'string'
                        ? question.options[key] : 'Chưa có phương án.'} />
                    </li>
                  ))}
                </ol>
                <p>Đáp án: <strong>{['A', 'B', 'C', 'D'].includes(question.correct_key) ? question.correct_key : 'Chưa xác định'}</strong></p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
