# Issue #93 — Stage 1 Source Ingestion and Blueprint Status Redesign Evidence

Captured on 19/11/2026 in headless Chromium against a temporary local Vite harness rendering the real React Stage 1 components under `<React.StrictMode>` with fixture data and stubbed API responses; **no live backend, PostgreSQL/Supabase session, or OAuth verification** is implied.

Before baseline refers to the prior Stage 1 UI captured in [PR #78](../pr78-polish/README.md). Desktop captures use a 1440 × 900 viewport; mobile captures use a 375 × 812 viewport.

## Before / After Comparison

| Scenario | Before (PR #78) | After (Issue #93) | Key UX / Layout Changes |
|---|---|---|---|
| Draft workspace (Desktop 1440 × 900) | [Before](../pr78-polish/stage1-after-1440.jpg) | [Draft text mode](stage1-after-desktop-draft-1440.png), [File upload mode](stage1-after-desktop-file-1440.png) | Step indicator (`Bước 1/3 · Đề gốc`), status badge (`Bản nháp`), live character counter (`N / 100.000 ký tự`), collapsible format hint, dynamic CTA emphasis (`Nạp nguồn` primary when empty or dirty), file type guidance chips (`.docx`, `.tex`, `.md`, `Không nhận .pdf`), green `Đúng` badges on keyed answers, `overflow-x-auto` KaTeX containment |
| Draft tabs (Mobile 375 × 812) | [Before preview tab](../pr78-polish/stage1-preview-after-375.jpg) | [Input tab](stage1-after-mobile-input-375.png), [Preview tab](stage1-after-mobile-preview-375.png) | Clean tab switcher between source editor and parsed question list; KaTeX formulas contained within cards without document horizontal overflow |
| Confirmed / Blueprint `failed` (Desktop 1440 × 900) | [Before confirmed](../pr78-polish/stage1-readonly-after-1440.jpg) | [Failed state](stage1-after-desktop-blueprint-failed-1440.png) | Semantic danger card (`Cần thử lại`) with clear retry guidance, enabled `Thử lại` action (`failed && !retryAccepted` only), disabled `Tiếp tục cấu hình` until ready |
| Confirmed / Blueprint `ready` (Desktop & Mobile) | — | [Desktop](stage1-after-desktop-blueprint-ready-1440.png), [Mobile](stage1-after-mobile-blueprint-ready-375.png) | Semantic `Sẵn sàng` status card with `100%` `<progress>` indicator, enabled `Tiếp tục cấu hình` CTA (full-width on mobile), zero internal canonical schema fields or variation dimension labels exposed |

## Verification Notes

- Measured viewport fit at both `1440 × 900` and `375 × 812` with document `scrollWidth` within viewport bounds and KaTeX integral expressions contained inside preview cards.
- Confirmed interactive `Thử lại` flow on `?scenario=blueprint_failed` transitions to `Đang chuẩn bị cấu trúc đề` / `Đang xử lý`. After merging `PR #91` (`#87`) into `dev`, `BlueprintStatusCard` was updated to also preserve `pending` retry recovery and `retryOutcomeUnknown` progress states (verified via automated DOM tests).
- Also resolved a `<React.StrictMode>` mount-remount deadlock in `sourceIngestion.js` `dispose()` where aborting an initial `checkCanonicalStatus` left `phase === 'checking_status'` stuck on `blueprinted` sessions.
- Not verified here: live backend worker execution, production Auth/API round-trips, screen-reader announcement testing, or browser zoom at 200%.
