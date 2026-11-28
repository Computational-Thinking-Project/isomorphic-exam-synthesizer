import MathRenderer from '../../components/MathRenderer.jsx';
import { normalizeOptions } from '../../services/stage3Service.js';

export function ReviewSolution({ question }) {
  const solution = question?.solution_md?.trim();
  return <section aria-label="Lời giải"><h3>Lời giải</h3>
    {solution && solution !== 'Không có lời giải cho câu hỏi này.'
      ? <MathRenderer content={solution} /> : <p>Chưa có lời giải</p>}
  </section>;
}

export function ReviewQuestionContent({ question }) {
  const options = normalizeOptions(question?.options);
  const key = String(question?.correct_key || question?.answer || '').trim().toUpperCase();
  return (
    <div className="stage3-question-content">
      <MathRenderer content={question?.content || question?.raw_content || ''} />
      <div className="stage3-question-options">
        {Object.entries(options).map(([label, value]) => {
          const keyed = label === key;
          return (
            <div key={label} data-answer-key={keyed ? label : undefined}
              className={`stage3-option${keyed ? ' stage3-option-keyed' : ''}`}>
              <span className="stage3-option-letter">{label}.</span>
              <div className="min-w-0"><MathRenderer content={String(value)} inline /></div>
              {keyed && <span className="answer-key-label">Đáp án</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Stage3Comparison({ source, questionNo, versionIndex, tabs, children }) {
  return (
    <div className="stage3-comparison">
      <section data-review-source className="stage3-read-panel" aria-label="Câu gốc chỉ đọc">
        <header className="stage3-panel-heading">
          <h2>Câu gốc · Câu {questionNo ?? '—'}</h2>
          <span className="stage3-readonly-badge">Chỉ đọc</span>
        </header>
        <div className="stage3-panel-body" tabIndex={0} key={questionNo}>
          {source ? <><ReviewQuestionContent question={source} /><ReviewSolution question={source} /></> : <p>Chưa có câu nguồn để đối chiếu.</p>}
        </div>
      </section>
      <section data-review-variant className="stage3-read-panel stage3-variant-panel" aria-label="Biến thể đang đối chiếu">
        <div role="tablist" aria-label="Chọn mã đề" className="stage3-version-tabs">{tabs}</div>
        <div role="tabpanel" id="stage3-variant-panel" aria-labelledby={`stage3-version-${versionIndex}`}
          tabIndex={0} className="stage3-panel-body" key={`${questionNo}-${versionIndex}`}>
          {children}
        </div>
      </section>
    </div>
  );
}
