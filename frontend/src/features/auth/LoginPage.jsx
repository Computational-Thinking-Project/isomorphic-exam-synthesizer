import { useState } from 'react';

export default function LoginPage() {
  const [notice, setNotice] = useState('');

  function handleGoogleSignIn() {
    setNotice(
      'Đăng nhập Google chưa được kết nối. Đây là bản kiểm tra giao diện.',
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4 py-12">
      <section
        aria-labelledby="login-title"
        className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8"
      >
        <p className="mb-3 text-sm font-medium text-sky-400">
          Isomorphic Exam Synthesizer
        </p>

        <h1 id="login-title" className="text-3xl font-semibold">
          Đăng nhập
        </h1>

        <p className="mt-3 text-slate-400">
          Không gian dành cho giáo viên quản lý và biên soạn các mã đề.
        </p>

        <button
          type="button"
          onClick={handleGoogleSignIn}
          className="mt-8 w-full rounded-lg bg-sky-400 px-4 py-3 font-semibold text-slate-950 hover:bg-sky-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-400"
        >
          Đăng nhập bằng Google
        </button>

        <p
          role="status"
          aria-live="polite"
          className="mt-4 text-sm text-slate-300"
        >
          {notice}
        </p>
      </section>
    </main>
  );
}