import { useState } from 'react';

export default function UserAvatar({ src, name }) {
  const [failed, setFailed] = useState(false);

  const words = name.trim().split(/\s+/).filter(Boolean);
  const initials = (
    words.length > 1
      ? `${words[0][0]}${words[words.length - 1][0]}`
      : words[0]?.[0] || '?'
  ).toLocaleUpperCase('vi');

  return (
    <span
      aria-hidden="true"
      className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-700 text-sm font-semibold text-slate-100"
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