# Stage 2: Statistics Dashboard Information Architecture & UX Specification

> **Document Status:** OFFICIAL UX ARCHITECTURE & SPECIFICATION  
> **Milestone:** M1 (Stage 2 Deliverable)  
> **Target System:** Isomorphic Exam Synthesizer  
> **Verified Against:** Codebase Implementation (`StatisticsPage.jsx`), Route Contracts (`docs/api/statistics-endpoint.md`), Data Audit (`01-data-audit.md`)  
> **Auditor / Owner:** Worker M1 (Data Audit & UX Architecture Worker)  

---

## 1. Overview & Architectural Principles

The Statistics Dashboard serves as the central operational hub for educators using the Isomorphic Exam Synthesizer. Its primary purpose is to provide clear, actionable visibility into the teacher's exam creation pipeline, identifying active progress, pending exports, and generation incidents without cognitive clutter.

### Core Architectural Principles:
1. **Truth in Data (Zero Fabrication):** Every chart, counter, and visual element maps directly to verified fields in `SessionStatisticsResponse` (`GET /api/users/me/statistics`). No mock filters (date ranges, course tags) or unbacked metrics (student scores, token billing) are introduced.
2. **Paper Canvas Aesthetic (Anti-Slop):** Eliminate decorative clutter, generic AI gradient cards, and redundant isolated widgets. Visual elements use an authoritative, high-density editorial layout inspired by classic typography, subtle borders, and monospace tabular numerals.
3. **Progressive Disclosure:** Present information in a strict hierarchical order: high-level volume metrics first, followed by urgent incident alerts, then high-level lifecycle composition, and finally granular status distributions.
4. **Action-Oriented Insights:** Every visual metric directly supports an immediate user action: resuming in-progress drafts, exporting approved packages, or retrying failed generation jobs.
5. **Universal Accessibility:** 100% semantic HTML (`<dl>`, `<dt>`, `<dd>`, `<section>`), minimum 44px tap targets, full keyboard accessibility, visible focus rings, and zero horizontal scroll across 375px, 768px, and 1440px viewports.

---

## 2. User Personas & Key User Tasks

### 2.1 User Personas

| Persona | Role & Context | Primary Needs & Mental Model |
|---|---|---|
| **Teacher Nguyen (High School Math Educator)** | Teaches Grade 12 Mathematics. Prepares multiple isomorphic exam versions for semester finals. Needs to ensure all students take balanced but distinct test versions to prevent cheating. | - "How many exam sets have I completed so far?"<br>- "Do I have any approved exams that I forgot to download and print?"<br>- "Are there exams stuck in generation that I need to check?"<br>- "What is my current drafting workload?" |
| **Department Head Le (Subject Lead / Coordinator)** | Coordinates math curriculum and standardized testing across teacher cohorts. Audits overall adoption and exam synthesis volume. | - "Is the team actively creating and finalizing exam sets?"<br>- "Where are exams getting stuck in the authoring pipeline?"<br>- "Are generation failures occurring frequently?" |

### 2.2 Key User Tasks & Decision Flows

```
+--------------------------------------------------------------------------------------------------+
|                                    USER DECISION & ACTION FLOW                                    |
+--------------------------------------------------------------------------------------------------+
|  User Visits Dashboard                                                                           |
|        │                                                                                         |
|        ├─► Task 1: Check Total Volume                                                            |
|        │    └─ Evaluate "Tổng số phiên đề" (Account portfolio size across all sessions)          |
|        │                                                                                         |
|        ├─► Task 2: Triage Immediate Incidents                                                    |
|        │    └─ Check Incident Banner: Any `failed` or `unknown` sessions?                        |
|        │         ├─ Yes ──► Navigate to Library to retry generation or clone session             |
|        │         └─ No  ──► Incident banner hidden (normal clean operational state)              |
|        │                                                                                         |
|        ├─► Task 3: Locate Actionable Approved Sessions                                           |
|        │    └─ Check "Đã duyệt, chưa xuất": Sessions waiting for packaging                       |
|        │         └─► Navigate to Session Export (`/session/:id/export`) to generate download ZIP  |
|        │                                                                                         |
|        ├─► Task 4: Monitor In-Progress Workload                                                  |
|        │    └─ Check "Đang thực hiện": Sessions in Draft, Blueprint, Generation, or Review       |
|        │         └─► Inspect Status Distribution to identify which stage has work in progress    |
|        │                                                                                         |
|        └─► Task 5: Detailed Pipeline Audit                                                       |
|             └─ Inspect 11-Status Distribution Bar Chart to identify exact status counts          |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Metric Hierarchy & Layout Prioritization

The dashboard organizes information into four visual tiers arranged in descending order of urgency and cognitive priority:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TIER 1: GLOBAL NAVIGATION & CONTEXT BAR                                                          │
│ [← Thư viện đề]                                                [Số liệu tại thời điểm tải trang] │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 1.1: PAGE TITLE & ACCOUNT SCOPE                                                             │
│ "Thống kê sử dụng" — Các phiên đề hiện đang lưu trong tài khoản của bạn                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 2: PRIMARY SUMMARY METRICS DECK (Integrated Monolithic 4-Card Deck)                         │
│ ┌──────────────────────┬──────────────────────┬──────────────────────┬─────────────────────────┐ │
│ │ TỔNG SỐ PHIÊN ĐỀ     │ ĐANG THỰC HIỆN       │ ĐÃ DUYỆT, CHƯA XUẤT  │ ĐÃ XUẤT                 │ │
│ │ 23 phiên đề   100%   │ 12 phiên đề    52%   │ 4 phiên đề     17%   │ 5 phiên đề        22%   │ │
│ └──────────────────────┴──────────────────────┴──────────────────────┴─────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 3: CONDITIONAL INCIDENT ALERT BANNER (Rendered only when failed > 0 or unknown > 0)         │
│ [!] Lưu ý trạng thái: Tổng số phiên bao gồm 1 phiên gặp lỗi và 1 phiên chưa xác định             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 4: STATUS DISTRIBUTION BAR CHART (StatusChart)                                              │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 11-STATUS DISTRIBUTION BAR CHART                                                             │ │
│ │ Horizontal bar chart with relative percentage fills                                          │ │
│ │ Accessible definition list (<dl>, <dt>, <dd>)                                                │ │
│ │ Grouped with semantic status dots and tabular counts                                         │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Question-to-Chart / KPI Mapping Matrix

This matrix establishes the explicit, traceable connection between every metric, widget, visual representation, and the underlying backend data contract.

| # | User Question / Need | Dashboard Component | Backend Data Source / Field | Data Type & Derivation | Visual Representation | Interaction & Drill-Down Behavior | Cognitive Value & Decision Supported |
|---|---|---|---|---|---|---|---|
| **Q1** | "How many total exam sessions have I authored in this account?" | **Summary Deck: Total Sessions Card** | `total_sessions` | `int >= 0`<br>(Sum of all 11 buckets) | Monospace tabular numeral (`text-5xl font-bold font-mono`), "phiên đề" unit label, 100% benchmark badge. | Hover state tint (`hover:bg-rail/20`). Navigates to `/dashboard` to view full list. | Measures total platform adoption and long-term portfolio volume. |
| **Q2** | "How many exam sets are currently in progress and require further work?" | **Summary Deck: In Progress Card** | `in_progress_sessions` | `int >= 0`<br>(Sum of in-progress buckets) | Tabular numeral, share percentage of total sessions (`Math.round(in_prog / total * 100)`), blue highlight indicator. | Informs user of pending work items. Contextualizes active workload against completed exams. | Workload awareness: Prevents abandoning half-finished sessions. |
| **Q3** | "Are there approved exams waiting for me to download and print for class?" | **Summary Deck: Approved Pending Export Card** | `approved_not_exported_sessions` | `int >= 0`<br>(Direct count of `by_status.approved`) | Tabular numeral, amber warning indicator, percentage of total sessions. | High-priority call to action. Prompts user to click into Thư viện đề và export final ZIP archives. | Eliminates pipeline bottleneck where exams are approved but not packaged for students. |
| **Q4** | "How many exam packages have I successfully generated and completed?" | **Summary Deck: Exported Card** | `exported_sessions` | `int >= 0`<br>(Direct count of `by_status.exported`) | Tabular numeral, emerald success badge, percentage of total sessions. | Positive confirmation of successful output delivery. | Validates tangible teaching output ready for classroom distribution. |
| **Q5** | "Did any background AI generation tasks fail or encounter errors?" | **Incident Alert Banner** | `by_status.failed`, `by_status.unknown` | `int >= 0`<br>(Counts from status buckets) | Prominent soft red alert card (`border-danger-border bg-danger-soft`), warning icon, bold incident summary. | Displays count of failed/unknown sessions and provides direct troubleshooting advice (retry or clone). | Fast incident awareness: Alerts teacher to failed sessions so they can retry without wondering why an exam didn't finish. |
| **Q6** | "What is the detailed distribution of sessions across all 11 lifecycle statuses?" | **Status Distribution Bar Chart (`StatusChart`)** | `by_status` (all 11 status keys) | 11 non-negative integers (`draft` through `unknown`) | Horizontal proportional bar charts with color-coded stage badges, relative width (`Math.max(4, pct)%`), and definition list `<dl>`. | Transparent granular inspection. Clear distinction between early draft, active generation, review, and completion. | Pinpoints exact operational friction points (e.g., sessions stuck in `generating` vs. waiting in `reviewed`). |

---

## 5. Detailed Component UX Architecture

### 5.1 Tier 1: Navigation & Header Context Bar
- **Back Navigation:** Clean, minimal button `<Link to="/dashboard">` featuring an arrow icon that shifts subtly on hover (`group-hover:-translate-x-0.5`).
- **Data Freshness Notice:** Displays the static label `"Số liệu tại thời điểm tải trang"` in font-mono muted typography, explicitly communicating that data reflects the page-load state rather than a continuous realtime subscription (F102-03).
- **Header Typography:** Large, authoritative title (`text-2xl sm:text-3xl font-extrabold text-strong`) with a concise scope description ("Các phiên đề hiện đang lưu trong tài khoản của bạn.").

### 5.2 Tier 2: Summary Metrics Deck (`dl` Integrated Grid)
- **Monolithic Container:** A single unified white card (`bg-surface border border-line rounded-xl shadow-paper`) partitioned by dividers (`divide-y sm:divide-x divide-line`), rather than four disjointed floating cards.
- **Metric Cards:**
  1. `total_sessions`: Master count of all sessions.
  2. `in_progress_sessions`: Active authoring workload.
  3. `approved_not_exported_sessions`: Sessions approved but pending packaging.
  4. `exported_sessions`: Finalized export packages.
- **Typography & Numeral Formatting:** Uses `font-mono tabular-nums text-4xl sm:text-5xl font-bold text-strong` formatted via `Intl.NumberFormat('vi-VN')` for consistent numeral width and visual grounding.
- **Footers:** Displays percentage share of total sessions alongside clarifying subtitle.

### 5.3 Tier 3: Incident Alert Banner
- **Trigger Condition:** Rendered conditionally **only** when `(by_status.failed > 0 || by_status.unknown > 0)`. When both are zero, the banner occupies zero vertical space.
- **Visual Design:** Warning container with `border border-danger-border bg-danger-soft` and high-contrast red typography (`text-danger`).
- **Copywriting:** Clearly states the exact count of failed and unrecognized sessions, with practical recovery guidance: *"Các phiên gặp sự cố có thể thử sinh lại câu hỏi hoặc nhân bản phiên mới từ Thư viện đề."*

### 5.4 Tier 4: Status Distribution Bar Chart (`StatusChart`)
- Uses semantic `<section aria-labelledby="status-chart-title">` and accessible `<dl>`.
- Dynamic status bucket rows: renders exactly 10 `<dt>` rows when `unknown === 0` (defensive `unknown` bucket is omitted to eliminate unnecessary visual noise) and 11 `<dt>` rows when `unknown > 0` (revealed dynamically to surface unrecognized session anomalies).
- Each item features:
  - Color dot indicating status category.
  - Status title in Vietnamese.
  - Proportional horizontal bar with minimum 4% width for visibility of non-zero values.
  - Formatted count and percentage of total sessions.
- Zero-count states are rendered cleanly with a grayed-out 0 value, maintaining consistent layout height and avoiding layout shifts.

---

## 6. UX State Architecture & Edge Case Handling

The dashboard explicitly handles all possible lifecycle states to ensure resilience against network failures, latency, and account transitions.

```
+──────────────────────────────────────────────────────────────────────────────────────────────────+
|                                    LIFECYCLE STATE ARCHITECTURE                                  |
+──────────────────────────────────────────────────────────────────────────────────────────────────+
|                                                                                                  |
|  [Mount Component / Account Change]                                                              |
|        │                                                                                         |
|        ├──► 1. Loading State (`status === 'loading'`)                                            |
|        │     - Spinner card with `aria-busy="true"` and `role="status"`                          |
|        │     - Text: "Đang tải dữ liệu thống kê..."                                              |
|        │     - Preserves container dimensions to prevent layout cumulative shifts (CLS)          |
|        │                                                                                         |
|        ├──► 2. Error State (`status === 'error'`)                                                |
|        │     - Danger card with `role="alert"` and AlertCircle icon                              |
|        │     - Text: "Không tải được thống kê sử dụng" + detailed error reason                   |
|        │     - Interactive "Thử lại" retry button with focus ring and keyboard support           |
|        │                                                                                         |
|        ├──► 3. Empty Account State (`total_sessions === 0`)                                      |
|        │     - Renders 4 summary cards showing honest zeros (`0 phiên đề`)                       |
|        │     - Friendly guidance card: "Bạn chưa có phiên đề nào trong tài khoản."               |
|        │     - Action button linking to create/ingest first exam session                         |
|        │     - Status chart safely renders empty counts without breaking DOM layout              |
|        │                                                                                         |
|        └──► 4. Stale Request Abort Handling (Account Switching)                                  |
|              - Keyed on `accountKey = ${user?.id}:${sessionVersion}`                             |
|              - Subscribes `AbortController.signal` to `getMyStatistics({ signal })`              |
|              - When user logs out or switches accounts, pending requests are aborted             |
|              - Prevents race conditions and cross-account data leakage                           |
+──────────────────────────────────────────────────────────────────────────────────────────────────+
```

### 6.1 Loading State UX
- Displayed on initial page mount and during explicit re-fetches.
- Renders an accessible status container: `<div role="status" aria-busy="true" aria-live="polite">`.
- Animated spinner (`animate-spin text-highlight`) with clear copy: `"Đang tải dữ liệu thống kê..."`.
- Card structure preserves the page layout geometry to eliminate Cumulative Layout Shift (CLS).

### 6.2 Error State & Recovery UX
- Triggered by network loss, 503 database unavailability, or authentication timeout.
- Renders an alert container: `<div role="alert" className="border-danger-border bg-danger-soft">`.
- Clear error title and contextual subtitle.
- Interactive **"Thử lại"** (Retry) button:
  - Dispatches immediate retry of `getMyStatistics()`.
  - Accessible via keyboard (`Tab`, `Enter`, `Space`).
  - Has explicit focus ring (`focus-visible:ring-2 focus-visible:ring-danger`).

### 6.3 Empty State UX (Zero Sessions)
- Triggered when a new teacher signs up or an account has 0 retained sessions (`total_sessions === 0`).
- **Honest Zeros:** Summary metric cards render `0` without hiding or crashing.
- **Guidance Banner:** Renders a clean informational card:
  - Icon: `FileText` or `PackageCheck`.
  - Title: *"Bạn chưa có phiên đề nào"*.
  - Description: *"Hãy bắt đầu bằng cách tạo phiên làm việc mới tại Thư viện đề để sinh các bộ đề toán hoán vị."*
  - CTA Link: `<Link to="/dashboard">Tạo phiên đề mới</Link>`.
- **Defensive Rendering:** `StatusChart` renders cleanly with 0 counts without division-by-zero errors.

### 6.4 Concurrency & Stale Data Prevention
- In multi-user shared workstations, teachers may log out and another teacher log in without a hard page reload.
- The dashboard root component subscribes to `useAuthStore((state) => ${state.user?.id ?? ''}:${state.sessionVersion})`.
- Changing accounts generates a new React key, completely unmounting the previous state and cancelling any pending HTTP requests via `AbortController.abort()`.
- Verified by automated unit test `aborts stale account data and renders the new account` in `StatisticsPage.test.js`.

---

## 7. Accessibility, Semantics & Responsive Layout Specifications

### 7.1 Semantic HTML Architecture
- **Landmarks:** Top-level `<main>` wraps the primary dashboard content; `<nav aria-label="Điều hướng trang">` wraps navigation links; `<section>` wraps data visualization charts.
- **Definition Lists:** Both the 4-card Summary Deck and the 11-status distribution chart are implemented as semantic `<dl>` elements with paired `<dt>` (terms/labels) and `<dd>` (values/counts). This provides rich screen reader narration without requiring custom ARIA hacks.
- **Vector Graphics:** All decorative icons (`lucide-react`) carry `aria-hidden="true"`. All numerical information is presented in accessible semantic labels and tables.

### 7.2 Keyboard Navigation & Focus Indicators
- Every interactive element (back link, retry button, dashboard links) is fully focusable via standard `Tab` navigation.
- Focus rings conform to the project design tokens: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2`.
- Minimum tap/click target sizes are strictly enforced at `>= 44px` (2.75rem) via `.paper-ui` CSS rules.

### 7.3 Responsive Breakpoint Layout Matrix

| Breakpoint | Viewport Width | Layout Adaptations & Column Rules | Overflow Verification |
|---|---|---|---|
| **Mobile** | `375px` (`< 640px`) | - Summary Deck: 1 column (`grid-cols-1 divide-y divide-line`)<br>- Incident Banner: Stacked vertical flex with shrink-0 icon<br>- Status Distribution: Full width vertical list with proportional bar widths<br>- Header: Stacked title and metadata | Verified `scrollWidth <= 375px`. Zero horizontal scroll. Tap targets >= 44px. |
| **Tablet** | `768px` (`sm: 640px - 1023px`) | - Summary Deck: 2 columns (`sm:grid-cols-2 sm:divide-x`)<br>- Status Distribution: 2-column flex rows (`sm:grid-cols-[17rem_1fr]`) | Verified `scrollWidth <= 768px`. Clean 2x2 grid cards. |
| **Desktop** | `1024px` - `1440px` (`lg: >= 1024px`) | - Summary Deck: 4 columns integrated (`lg:grid-cols-4 lg:divide-x`)<br>- Status Distribution: Full-width broadsheet section with proportional horizontal bars<br>- Max container width: `max-w-[1160px]` centered | Verified `scrollWidth <= 1440px`. High information density without visual crowding. |

---

## 8. IA Conclusion & Verification Summary

The Information Architecture defined in this document establishes a direct, unassailable bridge between the backend capabilities audited in `01-data-audit.md` and the user experience delivered to teachers:
1. Every piece of UI represents genuine, persisted data from `GET /api/users/me/statistics`.
2. The hierarchy prioritizes user needs: volume overview -> incident detection -> macro lifecycle health -> detailed status distribution.
3. Edge states (loading, errors, empty accounts, account switches) are robustly engineered with fail-safe defaults and zero layout shift.
4. The specifications here govern the visual design system (`04-design-system.md`) and QA verification suite (`06-qa-report.md`).
