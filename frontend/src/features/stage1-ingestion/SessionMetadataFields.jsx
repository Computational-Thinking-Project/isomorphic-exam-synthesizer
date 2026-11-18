import { useId } from 'react';

const inputClass = 'mt-2 min-h-11 w-full rounded-xl border border-control-border bg-surface px-3.5 py-2.5 text-sm text-strong placeholder-muted focus:border-highlight focus:outline-none focus:ring-2 focus:ring-highlight/20 disabled:opacity-50';

// Both creation entry points keep the same fields and API metadata.
export default function SessionMetadataFields({ metadata, onChange, disabled = false, titleRef }) {
  const id = useId();

  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-5">
      <legend className="sr-only">Thông tin bộ đề</legend>
      <div>
        <label htmlFor={`${id}-title`} className="block text-sm font-semibold text-strong">
          Tên bộ đề <span className="text-danger" aria-hidden="true">*</span>
        </label>
        <input
          ref={titleRef}
          id={`${id}-title`}
          type="text"
          required
          disabled={disabled}
          value={metadata.title}
          onChange={(event) => onChange('title', event.target.value)}
          placeholder="Ví dụ: Đề kiểm tra giữa kỳ I — Toán 12"
          className={inputClass}
        />
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div>
          <p className="text-sm font-semibold text-strong">Môn học</p>
          <p className="mt-2 flex min-h-11 items-center rounded-xl bg-rail px-3.5 py-2.5 text-sm text-strong">
            Toán học
          </p>
        </div>
        <div>
          <label htmlFor={`${id}-grade`} className="block text-sm font-semibold text-strong">Khối lớp</label>
          <select
            id={`${id}-grade`}
            required
            disabled={disabled}
            value={metadata.grade}
            onChange={(event) => onChange('grade', Number(event.target.value))}
            className={inputClass}
          >
            {Array.from({ length: 12 }, (_, index) => index + 1).map((grade) => (
              <option key={grade} value={grade}>Lớp {grade}</option>
            ))}
          </select>
        </div>
      </div>
    </fieldset>
  );
}
