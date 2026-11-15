import { useState } from 'react';
import { Sparkles } from 'lucide-react';

export default function BrandLogo({
  variant = 'default',
  size = 'md',
  className = '',
}) {
  const [hasError, setHasError] = useState(false);

  const imgHeightClass =
    size === 'sm'
      ? 'h-7 sm:h-8'
      : size === 'lg'
        ? 'h-11 sm:h-12'
        : 'h-8 sm:h-9';

  return (
    <div className={`inline-flex items-center gap-3 select-none ${className}`}>
      {!hasError ? (
        <img
          src="/brand-logo.png"
          alt="EXAM MIRROR Logo"
          onError={() => setHasError(true)}
          className={`${imgHeightClass} w-auto object-contain shrink-0`}
          draggable={false}
        />
      ) : (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-support-bg text-highlight border border-support-line font-black">
          <Sparkles className="h-5 w-5" aria-hidden="true" />
        </span>
      )}

      {variant !== 'compact' && (
        <div className="flex flex-col justify-center leading-none">
          <span className="text-sm font-extrabold tracking-tight text-strong uppercase">
            Exam Mirror
          </span>
          <span className="text-[10px] font-medium text-muted tracking-wider mt-0.5">
            Isomorphic Exam Synthesizer
          </span>
        </div>
      )}
    </div>
  );
}
