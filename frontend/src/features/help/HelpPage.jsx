import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigationType } from 'react-router-dom';
import { ChevronDown, FileText, ListChecks, SlidersHorizontal } from 'lucide-react';
import BrandLogo from '../../components/BrandLogo.jsx';
import { limitations, questions, stages, troubleshooting } from './helpContent.js';

const sections = [
  { id: 'bat-dau', label: 'Bắt đầu nhanh' },
  { id: 'faq', label: 'Câu hỏi thường gặp' },
  { id: 'xu-ly-loi', label: 'Xử lý lỗi' },
  { id: 'gioi-han-ai', label: 'Giới hạn AI' },
];
const stageIcons = [FileText, SlidersHorizontal, ListChecks];
const frameClass = 'mx-auto w-full max-w-[1160px] px-4 sm:px-8';
const sectionHeadingClass = 'mb-4 scroll-mt-6 text-2xl font-bold leading-tight tracking-tight sm:text-[28px]';
const paperClass = 'rounded-2xl border border-line bg-surface shadow-soft';

export default function HelpPage() {
  const { hash, state } = useLocation();
  const navigationType = useNavigationType();
  const headingRef = useRef(null);
  const fromDashboard = state?.fromDashboard === true;

  useEffect(() => {
    if (!hash) {
      if (navigationType !== 'POP') {
        window.scrollTo?.(0, 0);
        headingRef.current?.focus({ preventScroll: true });
      }
      return;
    }

    const id = hash.slice(1);
    if (id === 'help-main' || sections.some((section) => section.id === id)) {
      const target = document.getElementById(id);
      target?.scrollIntoView();
      target?.focus({ preventScroll: true });
    }
  }, [hash, navigationType]);

  return (
    <div className="paper-ui min-h-screen bg-canvas text-ink">
      <a
        href="#help-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-lg focus:bg-surface focus:p-3 focus:font-semibold focus:text-highlight"
      >
        Chuyển đến nội dung chính
      </a>
      <header className="border-b border-line bg-surface">
        <div className={`${frameClass} flex flex-wrap items-center justify-between gap-3 py-3`}>
          <BrandLogo size="md" className="max-[360px]:!w-[180px]" />
          <Link
            to={fromDashboard ? '/dashboard' : '/login'}
            className="inline-flex items-center rounded-lg border border-control-border bg-surface px-4 py-2 text-sm font-semibold text-highlight hover:bg-rail"
          >
            {fromDashboard ? 'Về Thư viện đề' : 'Đăng nhập'}
          </Link>
        </div>
      </header>

      <main id="help-main" tabIndex={-1} className={`${frameClass} scroll-mt-4 pb-10`}>
        <div className="flex items-center justify-between gap-8 py-6 sm:py-7 lg:min-h-[192px]">
          <div>
            <h1 ref={headingRef} tabIndex={-1} className="text-3xl font-extrabold leading-tight tracking-tight text-strong sm:text-[40px]">
              Trung tâm trợ giúp
            </h1>
            <p className="mt-2 text-base text-muted">Tạo, duyệt và xuất đề qua ba giai đoạn.</p>
          </div>
          <img src="/library-artwork.webp" alt="" width="240" height="128" className="hidden h-auto w-60 shrink-0 md:block" />
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-[224px_minmax(0,1fr)] lg:gap-7">
          <nav aria-labelledby="help-toc" className={`${paperClass} border-t-[3px] border-t-accent px-4 pb-2 pt-4`}>
            <h2 id="help-toc" className="px-1 pb-2 text-xl font-bold text-strong">Mục lục</h2>
            <ul className="divide-y divide-line border-t border-line">
              {sections.map(({ id, label }) => (
                <li key={id}>
                  <a href={`#${id}`} className="flex items-center px-1 py-2 text-sm font-semibold text-highlight underline-offset-4 hover:underline">
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <div className="grid min-w-0 gap-8">
            <section aria-labelledby="bat-dau">
              <h2 id="bat-dau" tabIndex={-1} className={`${sectionHeadingClass} text-strong`}>Bắt đầu nhanh</h2>
              <ol className="grid gap-4">
                {stages.map(({ title, description }, index) => {
                  const Icon = stageIcons[index];
                  return (
                    <li key={title} className={`${paperClass} grid grid-cols-[2.5rem_minmax(0,1fr)] items-start gap-3 p-4 sm:gap-4 sm:p-6`}>
                      <span className="grid h-10 place-items-center rounded-lg bg-support-bg text-highlight">
                        <Icon className="h-5 w-5" aria-hidden="true" />
                      </span>
                      <div>
                        <h3 className="text-lg font-bold text-strong">{title}</h3>
                        <p className="mt-1 text-base">{description}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </section>

            <section aria-labelledby="faq">
              <h2 id="faq" tabIndex={-1} className={`${sectionHeadingClass} text-strong`}>Câu hỏi thường gặp</h2>
              <div className={`${paperClass} divide-y divide-line`}>
                {questions.map(({ title, answer }) => (
                  <details key={title} className="group">
                    <summary className="flex min-h-[52px] cursor-pointer list-none items-center justify-between gap-4 rounded-lg px-4 py-3 text-base font-semibold text-strong hover:bg-rail focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-highlight sm:px-5 [&::-webkit-details-marker]:hidden">
                      {title}
                      <ChevronDown className="h-4 w-4 shrink-0 text-highlight group-open:rotate-180" aria-hidden="true" />
                    </summary>
                    <p className="px-4 pb-4 text-base sm:px-5">{answer}</p>
                  </details>
                ))}
              </div>
            </section>

            <section aria-labelledby="xu-ly-loi">
              <h2 id="xu-ly-loi" tabIndex={-1} className={`${sectionHeadingClass} text-strong`}>Xử lý lỗi</h2>
              <ul className={`${paperClass} divide-y divide-line`}>
                {troubleshooting.map(({ title, description }) => (
                  <li key={title} className="px-4 py-3 sm:px-5">
                    <h3 className="text-lg font-bold text-strong">{title}</h3>
                    <p className="mt-1 text-base">{description}</p>
                  </li>
                ))}
              </ul>
            </section>

            <section aria-labelledby="gioi-han-ai" className="rounded-2xl border border-accent-border bg-accent-soft p-4 sm:p-6">
              <h2 id="gioi-han-ai" tabIndex={-1} className={`${sectionHeadingClass} text-accent-ink`}>Giới hạn AI</h2>
              <ul className="list-disc space-y-2 pl-5 text-base">
                {limitations.map((limit) => <li key={limit}>{limit}</li>)}
              </ul>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
