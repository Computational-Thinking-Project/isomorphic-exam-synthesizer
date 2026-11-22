import { useState } from 'react';

export default function UserAvatar({ src, name, size = 'sm' }) {
  const [failed, setFailed] = useState(false);
  const dimensions = size === 'lg' ? 'h-16 w-16 text-xl sm:h-20 sm:w-20 sm:text-2xl' : 'h-10 w-10 text-sm';

  const words = name.trim().split(/\s+/).filter(Boolean);
  const initials = (
    words.length > 1
      ? `${words[0][0]}${words[words.length - 1][0]}`
      : words[0]?.[0] || '?'
  ).toLocaleUpperCase('vi');

  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-support-line bg-support-bg font-semibold text-highlight shadow-soft ${dimensions}`}
    >
      {src && !failed ? (
        <img
          src={src}
          alt=""
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        initials
      )}
    </span>
  );
}
