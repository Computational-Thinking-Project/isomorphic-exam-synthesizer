import { useState } from 'react';

export default function BrandLogo({
  size = 'md',
  className = '',
}) {
  const [hasError, setHasError] = useState(false);

  // Exact aspect ratio and coordinate clipping from docs/ui-walkthrough/PREVIEW.html
  // Original image: 666 x 375. Content bounding box: 594 x 128 at (40, 128).
  const sizeClasses =
    size === 'sm'
      ? 'w-[180px] sm:w-[210px]'
      : size === 'lg'
        ? 'w-[260px] sm:w-[320px] md:w-[360px]'
        : 'w-[210px] sm:w-[250px] md:w-[270px]';

  return (
    <div
      className={`relative inline-block select-none overflow-hidden ${sizeClasses} aspect-[594/128] shrink-0 ${className}`}
      role="img"
      aria-label="EXAM MIRROR"
    >
      {!hasError ? (
        <img
          src="/brand-logo.png"
          alt="EXAM MIRROR"
          onError={() => setHasError(true)}
          className="absolute w-[calc(100%*666/594)] max-w-none left-[calc(-100%*40/594)] top-[-100%] h-auto pointer-events-none select-none"
          draggable={false}
        />
      ) : (
        <span className="flex h-full w-full items-center font-black text-xl tracking-tight text-strong uppercase">
          Exam Mirror
        </span>
      )}
    </div>
  );
}
