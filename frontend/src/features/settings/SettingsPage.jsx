import { useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import BrandLogo from '../../components/BrandLogo.jsx';
import { useAuthStore } from '../auth/authStore.js';
import UserAvatar from '../auth/UserAvatar.jsx';
import {
  readDefaultNumVersions,
  SYSTEM_DEFAULT_NUM_VERSIONS,
  writeDefaultNumVersions,
} from './defaultVersionsPreference.js';

const MISSING = 'Chưa có thông tin';
const joinDateFormat = new Intl.DateTimeFormat('vi-VN', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: 'Asia/Ho_Chi_Minh',
});

function profileValue(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function formatJoinDate(value) {
  const time = Date.parse(profileValue(value));
  return Number.isFinite(time) ? joinDateFormat.format(time) : MISSING;
}

function googleAvatarUrl(profileId, authUser) {
  if (authUser?.id !== profileId) return '';
  const { avatar_url: avatar, picture } = authUser.user_metadata ?? {};

  for (const candidate of [avatar, picture]) {
    if (typeof candidate !== 'string' || !candidate.trim()) continue;
    try {
      const url = new URL(candidate);
      if (
        url.protocol === 'https:' &&
        /^(?:lh[0-9]+\.)?googleusercontent\.com$/.test(url.hostname) &&
        !url.username && !url.password && !url.port
      ) {
        return url.href;
      }
    } catch {
      // Try the next metadata field before falling back to initials.
    }
  }

  return '';
}

function SettingsContent({ profile, authUser }) {
  const [saved, setSaved] = useState(
    () => readDefaultNumVersions(profile.id) ?? SYSTEM_DEFAULT_NUM_VERSIONS,
  );
  const [selected, setSelected] = useState(saved);
  const [feedback, setFeedback] = useState(null);

  const name = profileValue(profile.name);
  const email = profileValue(profile.email);
  const displayName = name || email || 'Tài khoản';
  const avatar = googleAvatarUrl(profile.id, authUser);
  const profileFields = [
    ['Họ và tên', name || MISSING],
    ['Email', email || MISSING],
    ['Ngày tham gia', formatJoinDate(profile.created_at)],
  ];

  function savePreference(event) {
    event.preventDefault();
    if (selected === saved) return;

    if (!writeDefaultNumVersions(profile.id, selected)) {
      setFeedback('error');
      return;
    }

    setSaved(selected);
    setFeedback('saved');
  }

  return (
    <div className="paper-ui min-h-screen bg-canvas text-ink">
      <header className="border-b border-line bg-surface shadow-soft">
        <div className="mx-auto flex max-w-[1160px] items-center justify-between gap-3 px-4 py-3 sm:px-8">
          <BrandLogo size="sm" />
          <div className="flex min-w-0 items-center gap-2.5">
            <UserAvatar key={avatar} src={avatar} name={displayName} />
            <span className="hidden truncate text-xs font-bold text-strong sm:block">{displayName}</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1160px] px-4 pb-10 pt-5 sm:px-8 sm:pt-8">
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-2 rounded-md text-sm font-semibold text-highlight hover:underline"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Về Thư viện đề
        </Link>
        <h1 className="mb-6 mt-3 text-3xl font-extrabold tracking-tight text-strong sm:mb-8 sm:mt-5 sm:text-4xl">
          Cài đặt cá nhân
        </h1>

        <section
          aria-labelledby="settings-account-heading"
          className="mb-5 rounded-2xl border border-line bg-surface p-5 shadow-paper sm:mb-6 sm:p-8"
        >
          <h2 id="settings-account-heading" className="text-xl font-bold text-strong sm:text-2xl">
            Thông tin tài khoản
          </h2>
          <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-8">
            <UserAvatar key={avatar} src={avatar} name={displayName} size="lg" />
            <dl className="grid min-w-0 flex-1 gap-3 sm:grid-cols-3 sm:gap-4">
              {profileFields.map(([label, value], index) => (
                <div key={label} className={index ? 'sm:border-l sm:border-line sm:pl-4' : ''}>
                  <dt className="text-sm text-muted">{label}</dt>
                  <dd className="mt-1 break-words font-semibold text-strong">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section
          aria-labelledby="settings-generation-heading"
          className="rounded-2xl border border-line bg-surface p-5 shadow-paper sm:p-8"
        >
          <h2 id="settings-generation-heading" className="text-xl font-bold text-strong sm:text-2xl">
            Tùy chọn sinh đề
          </h2>
          <form onSubmit={savePreference} className="mt-5 sm:mt-6">
            <fieldset aria-describedby="settings-versions-hint">
              <legend className="font-semibold text-strong">Số mã đề mặc định</legend>
              <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4 sm:gap-3">
                {[1, 2, 3, 4].map((count) => (
                  <label
                    key={count}
                    className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-xl border px-2.5 py-3 text-sm font-semibold sm:gap-3 sm:px-4 ${
                      selected === count
                        ? 'border-accent-border bg-accent-soft text-accent-ink'
                        : 'border-line bg-surface text-strong hover:bg-rail'
                    }`}
                  >
                    <input
                      type="radio"
                      name="default-versions"
                      value={count}
                      checked={selected === count}
                      onChange={() => {
                        setSelected(count);
                        setFeedback(null);
                      }}
                      className="h-4 min-h-0 w-4 shrink-0 accent-accent-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-highlight"
                    />
                    {count} mã đề
                  </label>
                ))}
              </div>
            </fieldset>
            <p id="settings-versions-hint" className="mt-4 text-sm text-muted">
              Nếu chưa lưu, phiên mới dùng 2 mã đề. Bạn vẫn có thể đổi ở Giai đoạn 2.
            </p>
            <div className="mt-5 flex flex-wrap items-center justify-end gap-x-4 gap-y-3">
              {feedback === 'saved' && (
                <p role="status" className="me-auto text-sm text-approved-ink">
                  Đã lưu cài đặt trên trình duyệt này.
                </p>
              )}
              {feedback === 'error' && (
                <p role="alert" className="me-auto text-sm text-danger">
                  Chưa lưu được. Hãy kiểm tra quyền lưu dữ liệu của trình duyệt rồi thử lại.
                </p>
              )}
              <button
                type="submit"
                disabled={selected === saved}
                className="rounded-lg border border-accent-border bg-accent px-4 py-2 text-sm font-semibold text-ink shadow-soft enabled:hover:border-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
              >
                Lưu cài đặt
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}

export default function SettingsPage() {
  const profile = useAuthStore((state) => state.user);
  const authUser = useAuthStore((state) => state.session?.user);

  return profile?.id ? <SettingsContent key={profile.id} profile={profile} authUser={authUser} /> : null;
}
