# Stage 4: Statistics Dashboard Design System & Wireframe Specification

> **Document Status:** OFFICIAL DESIGN SYSTEM & WIREFRAME SPECIFICATION  
> **Milestone:** M2 (Stage 4 Deliverable)  
> **Target System:** Isomorphic Exam Synthesizer  
> **Author / Owner:** Worker M2 (Design Research & Design System Worker)  
> **Verified Against:** Data Audit (`01-data-audit.md`), UX Architecture (`02-information-architecture.md`), Design Research (`03-design-research.md`), Frontend Implementation (`frontend/src/features/statistics/StatisticsPage.jsx`), Theme Tokens (`frontend/tailwind.config.js`)

---

## 1. Overview & Architectural Grounding

This specification establishes the authoritative design system tokens, visual rules, layout geometry, component behaviors, and multi-viewport wireframes for the **Isomorphic Exam Synthesizer Statistics Dashboard**.

### 1.1 The "Paper Canvas" Design Language
The design system is grounded in the repository's foundational **"Paper Canvas"** aesthetic:
- **Quiet Authority:** An editorial, broadsheet-inspired layout that respects the dignity and focus of educators.
- **Monolithic Containerization:** Visual widgets are housed within unified, bordered surfaces sharing single-pixel hairline dividers, rather than fragmented floating cards.
- **Tabular Monospace Grounding:** All numbers, quantities, percentages, and metrics are strictly rendered in `font-mono tabular-nums` to ensure numerical alignment.
- **Zero Charting Dependencies:** All charts are implemented using pure semantic SVG and Tailwind CSS layouts, completely eliminating heavy charting libraries (zero kB added to bundle).
- **Strict Data Integrity:** All visualizations bind strictly to verified fields in `SessionStatisticsResponse` (`GET /api/users/me/statistics` as documented in `01-data-audit.md`).

---

## 2. Design System Foundations

### 2.1 Typography System & Font Stacks

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TYPOGRAPHY SYSTEM STACKS                                                                         │
│                                                                                                  │
│ 1. UI Copy Stack (Inter System):                                                                 │
│    font-sans: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif│
│                                                                                                  │
│ 2. Metric / Tabular Numbers Stack:                                                               │
│    font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace   │
│    Modifiers: font-mono tabular-nums                                                             │
│                                                                                                  │
│ 3. Mathematical Formula Rendering Stack (KaTeX):                                                 │
│    KaTeX_Main, KaTeX_Math, 'Times New Roman', serif                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Typographic Scale & Hierarchy Table

| Level / Role | Tailwind Classes | Size (rem / px) | Weight | Line Height | Usage Context |
|---|---|---|---|---|---|
| **Display Metric 1** | `text-4xl sm:text-5xl font-bold font-mono tabular-nums` | `2.25rem / 36px` → `3.00rem / 48px` | Bold (700) | `1.0` (tight) | Primary KPI counters in Summary Deck (`total_sessions`, `in_progress`) |
| **Display Metric 2** | `text-2xl sm:text-3xl font-bold font-mono tabular-nums` | `1.50rem / 24px` → `1.875rem / 30px` | Bold (700) | `1.1` | Donut center readout, Pipeline Funnel stage volume counters |
| **Page Title** | `text-2xl sm:text-3xl font-extrabold text-strong tracking-tight` | `1.50rem / 24px` → `1.875rem / 30px` | Extra Bold (800) | `1.2` | Main page title ("Thống kê sử dụng") |
| **Section Header** | `text-base font-bold text-strong` | `1.00rem / 16px` | Bold (700) | `1.5` | Section titles ("Phân bố trạng thái phiên", "Quy trình xử lý phiên đề 4 chặng") |
| **Card / Label Header** | `text-xs font-bold text-muted uppercase tracking-wider` | `0.75rem / 12px` | Bold (700) | `1.4` | KPI deck category headers, stage badges ("CHẶNG 01") |
| **Body / Row Label** | `text-sm font-medium text-strong` | `0.875rem / 14px` | Medium (500) | `1.5` | Status chart row titles, alert banner copy |
| **Subtitle / Description**| `text-xs text-muted leading-relaxed` | `0.75rem / 12px` | Normal (400) | `1.5` | Subtitles, stage descriptions, contextual hints |
| **Micro Benchmark** | `text-[11px] font-semibold uppercase tracking-wider` | `0.6875rem / 11px` | Semi-Bold (600) | `1.3` | Donut center unit label ("PHIÊN ĐỀ"), status indicator pills |

---

### 2.2 Spacing System & 4px Layout Grid

The system strictly adheres to a **4px base grid** (0.25rem = 4px).

```
+──────────────────────────────────────────────────────────────────────────────────────────────────+
|                                    4px SPACING SCALE & RHYTHM                                    |
+───────────────+──────────────+──────────────+────────────────────────────────────────────────────+
| Token         | Value (rem)  | Value (px)   | Standard Application                               |
+───────────────+──────────────+──────────────+────────────────────────────────────────────────────+
| `space-1`     | 0.25rem      | 4px          | Dot gaps, hairline offsets, indicator pips         |
| `space-1.5`   | 0.375rem     | 6px          | Micro padding inside badges and pill chips         |
| `space-2`     | 0.50rem      | 8px          | Tight flex gaps, icon-to-label spacing             |
| `space-2.5`   | 0.625rem     | 10px         | Vertical padding between status bar rows           |
| `space-3`     | 0.75rem      | 12px         | Compact horizontal padding in buttons and tags     |
| `space-4`     | 1.00rem      | 16px         | Standard card inner padding on mobile, row gaps    |
| `space-5`     | 1.25rem      | 20px         | Intermediate card padding on tablet                |
| `space-6`     | 1.50rem      | 24px         | Standard desktop card padding (`p-6`), stack gaps  |
| `space-8`     | 2.00rem      | 32px         | Section vertical rhythm (`space-y-8`, `py-8`)      |
| `space-12`    | 3.00rem      | 48px         | Empty state vertical breathing room                |
+───────────────+──────────────+──────────────+────────────────────────────────────────────────────+
```

#### Page Layout Container Constraints:
- Main Page Container: `max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8`
- Desktop Container Max Width: `72rem` (1152px)
- Responsive Side Margins:
  - Mobile (<640px): `px-4` (16px gutter)
  - Tablet (640px - 1023px): `px-6` (24px gutter)
  - Desktop (>=1024px): `px-8` (32px gutter)

---

### 2.3 Color Palette Tokens & Semantic Mappings

The color palette is calibrated for high-contrast accessibility (WCAG AA/AAA compliance) and editorial tranquility.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ COLOR PALETTE TOKENS (TAILWIND CSS & CSS CUSTOM PROPERTIES)                                      │
├───────────────────┬───────────┬──────────────────────────────────────────────────────────────────┤
│ Token Name        | Hex Value | Semantic Purpose & Usage Context                                 │
├───────────────────┼───────────┼──────────────────────────────────────────────────────────────────┤
│ `canvas`          | `#fafafa` | Global background canvas; soothing, soft paper tint              │
│ `surface`         | `#ffffff` | Elevated cards, monolithic decks, modal dialogs                  │
│ `rail`            | `#f4f4f5` | Inactive tracks, progress bar backgrounds, badge fills           │
│ `line`            | `#e4e4e7` | Hairline dividers, outer panel borders, structural grid lines   │
│ `ink`             | `#3f3f46` | Secondary body text, neutral descriptive labels                  │
│ `strong`          | `#27272a` | Primary titles, high-priority numerals, strong emphasis          │
│ `muted`           | `#6b6b74` | Subtitles, disabled states, empty state icons, metadata          │
│ `control-border`  | `#85858f` | Interactive input boundaries and secondary borders               │
│ `highlight`       | `#304c70` | Primary brand Navy: active icons, focus rings, primary bars      │
│ `accent`          | `#f5ce58` | Warm gold: highlight tags, secondary focus rings                 │
│ `approved` (ink)  | `#255c3b` | Deep forest green: approved state text, export success badges   │
│ `approved` (bg)   | `#eaf5ed` | Soft green background fill for success notices                   │
│ `approved` (line) | `#b7d8c1` | Soft green border for success banners                            │
│ `danger` (ink)    | `#a32b32` | Crimson red: critical incident alerts, failed session warnings   │
│ `danger` (soft)   | `#fff1f2` | Soft red background fill for incident alert banner               │
│ `danger` (border) | `#fecdd3` | High-visibility red border for incident alerts                   │
│ `support` (text)  | `#52647b` | Slate blue: secondary navigational elements                      │
└───────────────────┴───────────┴──────────────────────────────────────────────────────────────────┘
```

#### Authoritative Status Semantic Color Mappings (All 11 Status Buckets)

Every status bucket from `SessionStatusCounts` is mapped to an authoritative lifecycle stage, semantic color, and accessible text representation:

| Status Key | Lifecycle Stage | Stage Badge | Vietnamese Display Label | Bar Color Class | Dot / Accent Color | Hex Code |
|---|---|---|---|---|---|---|
| `draft` | Chặng 01: Đề gốc | `01` | Đang chuẩn bị đề gốc | `bg-indigo-600` | Indigo | `#4f46e5` |
| `blueprinted` | Chặng 01: Đề gốc | `01` | Đã xác nhận đề gốc | `bg-indigo-600` | Indigo | `#4f46e5` |
| `configured` | Chặng 02: Sinh AI | `02` | Đã cấu hình sinh đề | `bg-[#304c70]` | Highlight Navy | `#304c70` |
| `generating` | Chặng 02: Sinh AI | `02` | Đang sinh đề | `bg-[#304c70]` | Blue Pulse | `#2563eb` |
| `partial_generated`| Chặng 02: Sinh AI | `02` | Đã sinh một phần | `bg-[#304c70]` | Highlight Navy | `#304c70` |
| `generated` | Chặng 02: Sinh AI | `02` | Đã sinh đề | `bg-[#304c70]` | Sky Blue | `#0284c7` |
| `reviewed` | Chặng 03: Kiểm định | `03` | Đã duyệt các câu, chờ chốt | `bg-amber-600` | Amber | `#d97706` |
| `approved` | Chặng 03: Kiểm định | `03` | Đã duyệt, chưa xuất | `bg-amber-600` | Amber | `#d97706` |
| `exported` | Chặng 04: Xuất bản | `04` | Đã tạo gói xuất | `bg-emerald-600` | Emerald | `#059669` |
| `failed` | Ngoại lệ / Sự cố | `ERR` | Sinh đề gặp lỗi | `bg-danger` | Danger Red | `#a32b32` |
| `unknown` | Ngoại lệ / Sự cố | `N/A` | Chưa xác định | `bg-muted` | Slate Muted | `#6b6b74` |

---

### 2.4 Chart & Visualization Conventions (Zero-Heavy-Dependencies)

All visual representations are built strictly with semantic HTML, Tailwind CSS utilities, and native SVG.

#### 1. SVG Donut Geometry (`CompositionDonut`)
```
Radius r = 56px
Circumference C = 2 * π * 56 ≈ 351.858px
ViewBox = "0 0 140 140"
Stroke Width = 14px
Base Rail Stroke = "var(--rail)" (#f4f4f5)
Coordinate Rotation = -rotate-90 (starts at 12 o'clock noon)
Arc Stroke Dasharray = `${arcLength} ${circumference}`
Arc Stroke Dashoffset = -${cumulativeOffset}
```
- **Categories Partitioned (Sum = `total_sessions`):**
  1. `in_progress_sessions`: Highlight Navy (`#304c70`)
  2. `approved_not_exported_sessions`: Amber (`#d97706`)
  3. `exported_sessions`: Emerald Green (`#059669`)
  4. `exceptions` (`failed + unknown`): Danger Red (`#a32b32`)
- **Center Readout:** Monospace tabular total number with uppercase label `PHIÊN ĐỀ`.
- **Accessible Legend:** Rendered directly beneath the SVG as an accessible tabular list with colored dot markers, Vietnamese labels, session counts, and percentage shares.

#### 2. Horizontal Status Distribution Bars (`StatusChart`)
- **Markup:** Semantic `<section aria-labelledby="status-chart-title">` enclosing `<dl className="divide-y divide-line/60">`.
- **Dynamic Rows Rule:**
  - When `unknown === 0`: Renders exactly **10 `<dt>` / `<dd>` rows** (hides `unknown` to keep the UI clean).
  - When `unknown > 0`: Renders exactly **11 `<dt>` / `<dd>` rows** (reveals `unknown` dynamically alongside the incident banner).
- **Proportional Fill Geometry:**
  - Let `largest = Math.max(1, ...counts)`.
  - Bar width: `largest > 0 ? (count / largest) * 100 : 0`.
  - Non-zero visual clamp: when `count > 0`, CSS width is at least `4%` so small counts remain visible.
- **Zero-State Handling:** Rows with `count === 0` are rendered cleanly with a muted dot (`bg-muted/40`), a muted title (`text-muted`), a blank track, and a grayed-out `0` numeral (`text-muted/50`).

#### 3. 4-Stage Lifecycle Progression Funnel (`PipelineFunnel`)
- **Markup:** 4-column connected grid (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`).
- **Stage Aggregations:**
  - Stage 01 (Đề gốc & Blueprint): `counts.draft + counts.blueprinted`
  - Stage 02 (Sinh biến thể AI): `counts.configured + counts.generating + counts.partial_generated + counts.generated`
  - Stage 03 (Kiểm định & Phê duyệt): `counts.reviewed + counts.approved`
  - Stage 04 (Đóng gói xuất bản): `counts.exported`
- **Visual Presentation:** Monolithic container with hairline cross-dividers (`divide-y sm:divide-x divide-line`), stage index badge, percentage pill, volume counter, and proportional linear fill.

---

### 2.5 Explicitly Banned Anti-Patterns ("Anti-Slop" Manifesto)

To maintain institutional dignity and prevent generic "AI dashboard" tropes, the following patterns are **strictly prohibited** in code and visual design:

```
+──────────────────────────────────────────────────────────────────────────────────────────────────+
|                                  EXPLICITLY BANNED ANTI-PATTERNS                                 |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
| Banned Pattern                     | Architectural Justification & Reason for Prohibition         |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
| ❌ Repetitive Floating Cards        | Fragmenting metrics into 4-8 disconnected floating boxes     |
|    with Drop Shadows               | with `shadow-xl` creates visual noise. Summary metrics must  |
|                                    | be housed in a unified monolithic deck with hairlines.      |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
| ❌ Unpurposed Decorative Gradients  | Neon purple/cyan radial gradients, cosmic particle glows,   |
|    and Neon Glows                  | and glassmorphism blurs (`backdrop-blur-md`) degrade text   |
|                                    | contrast and destroy editorial credibility.                 |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
| ❌ Generic AI Placeholder Metrics  | Visual widgets depicting "Hours Saved by AI", "Productivity |
|    & "Time Saved" Calculators      | Index", or "AI Confidence Score" are fabricated slop.       |
|                                    | Strictly forbidden by `docs/metrics/w4-kpi-definitions.md`. |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
| ❌ Inaccessible Canvas/WebGL Charts| Adding Chart.js, Recharts, or Plotly bundles creates 500kB+ |
|    without Screen Reader `<dl>`    | bloat and renders opaque `<canvas>` elements inaccessible    |
|                                    | to screen readers and keyboard navigation.                  |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
| ❌ Faux Date Pickers & Filter Bars | Adding "Last 30 Days" or "Filter by Subject" dropdowns is   |
|                                    | deceptive because the backend endpoint takes no parameters. |
+────────────────────────────────────+─────────────────────────────────────────────────────────────+
```

---

## 3. Comprehensive Wireframes

### 3.1 Desktop Wireframe (1440px / 1024px Viewport)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ DESKTOP VIEWPORT (1440px / 1024px) — CONTAINER: max-w-6xl mx-auto px-8 py-8                               │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                            │
│ [← Thư viện đề]                                                              [● ĐỒNG BỘ TRỰC TIẾP (Pulse)] │
│                                                                                                            │
│ Thống kê sử dụng                                                                                           │
│ Các phiên đề hiện đang lưu trong tài khoản của bạn.                                                        │
│                                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ SUMMARY METRICS DECK (Unified container: border border-line rounded-xl bg-surface divide-x)           │ │
│ ├────────────────────────────┬────────────────────────────┬────────────────────────────┬─────────────────┤ │
│ │ TỔNG SỐ PHIÊN ĐỀ           │ ĐANG THỰC HIỆN             │ ĐÃ DUYỆT, CHƯA XUẤT        │ ĐÃ XUẤT         │ │
│ │                            │                            │                            │                 │ │
│ │ 23                         │ 17                         │ 3                          │ 2               │ │
│ │ phiên đề                   │ phiên đề                   │ phiên đề                   │ phiên đề        │ │
│ │                            │                            │                            │                 │ │
│ │ 100% tổng số phiên         │ 74% tổng số phiên          │ 13% tổng số phiên          │ 9% tổng số phiên│ │
│ │ Tất cả phiên tạo & nhân bản│ Giai đoạn chuẩn bị & sinh  │ Chờ đóng gói xuất bản      │ Đã đóng gói tải │ │
│ └────────────────────────────┴────────────────────────────┴────────────────────────────┴─────────────────┘ │
│                                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ INCIDENT ALERT BANNER (Conditional: rendered only when failed > 0 || unknown > 0)                      │ │
│ │ [!] Lưu ý trạng thái: Tổng số phiên bao gồm 1 phiên gặp lỗi.                                           │ │
│ │     Các phiên gặp sự cố có thể thử sinh lại câu hỏi hoặc nhân bản phiên mới từ Thư viện đề.            │ │
│ └────────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ MAIN ANALYSIS HUB (Desktop Asymmetric 2-Column Grid: [minmax(0,1fr)_340px] gap-6)                      │ │
│ ├─────────────────────────────────────────────────────────────┬──────────────────────────────────────────┤ │
│ │ STATUS DISTRIBUTION BAR CHART (StatusChart)                 │ MACRO COMPOSITION DONUT (CompositionDonut│ │
│ │                                                             │                                          │ │
│ │ Phân bố trạng thái phiên                 [10 trạng thái]    │ Cơ cấu vòng đời phiên        9% hoàn tất │ │
│ │ Chi tiết 11 trạng thái dọc chuỗi nghiệp vụ                  │ Tỷ lệ hoàn thành qua các chặng           │ │
│ │ ─────────────────────────────────────────────────────────── │ ──────────────────────────────────────── │ │
│ │ [01] Đang chuẩn bị đề gốc       [========       ]  4        │                 ╭──────╮                 │ │
│ │ [01] Đã xác nhận đề gốc         [======         ]  3        │              ╭──╯ 74%  ╰──╮              │ │
│ │ [02] Đã cấu hình sinh đề        [====           ]  2        │              │  23 phiên  │              │ │
│ │ [02] Đang sinh đề               [==             ]  1        │              ╰──╮         ╭──╯              │ │
│ │ [02] Đã sinh một phần           [==             ]  1        │                 ╰──────╯                 │ │
│ │ [02] Đã sinh đề                 [========       ]  4        │                                          │ │
│ │ [03] Đã duyệt các câu, chờ chốt [====           ]  2        │ ──────────────────────────────────────── │ │
│ │ [03] Đã duyệt, chưa xuất        [======         ]  3        │ ■ Đang thực hiện         17 (74%)        │ │
│ │ [04] Đã tạo gói xuất            [====           ]  2        │ ■ Đã duyệt, chưa xuất     3 (13%)        │ │
│ │ [ERR] Sinh đề gặp lỗi           [==             ]  1        │ ■ Đã xuất                 2 (9%)         │ │
│ │                                                             │ ■ Ngoại lệ / lỗi          1 (4%)         │ │
│ └─────────────────────────────────────────────────────────────┴──────────────────────────────────────────┘ │
│                                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 4-STAGE LIFECYCLE PROGRESSION FUNNEL (PipelineFunnel: border border-line rounded-xl bg-surface p-6)    │ │
│ │                                                                                                        │ │
│ │ Quy trình xử lý phiên đề 4 chặng                                     Tổng luân chuyển: 23 phiên        │ │
│ │ Sơ đồ luân chuyển tuyến tính từ nạp nguồn đến đóng gói xuất bản                                        │ │
│ │ ────────────────────────────────────────────────────────────────────────────────────────────────────── │ │
│ │ ┌───────────────────┬───────────────────┬──────────────────────┬─────────────────────────────────────┐ │ │
│ │ │ CHẶNG 01      30% │ CHẶNG 02      35% │ CHẶNG 03         22% │ CHẶNG 04                         9% │ │ │
│ │ │ Đề gốc & Blueprint│ Sinh biến thể AI  │ Kiểm định & Duyệt    │ Đóng gói xuất bản                   │ │ │
│ │ │ Bóc tách & chốt   │ Cấu hình & sinh   │ Đối soát toán & duyệt│ Hoàn thiện PDF/Word                 │ │ │
│ │ │ ───────────────── │ ───────────────── │ ──────────────────── │ ─────────────────────────────────── │ │ │
│ │ │ 7 phiên           │ 8 phiên           │ 5 phiên              │ 2 phiên                             │ │ │
│ │ │ [======         ] │ [=======        ] │ [====              ] │ [==                               ] │ │ │
│ │ └───────────────────┴───────────────────┴──────────────────────┴─────────────────────────────────────┘ │ │
│ └────────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.2 Tablet Wireframe (768px Viewport)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TABLET VIEWPORT (768px) — CONTAINER: max-w-6xl mx-auto px-6 py-6                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│ [← Thư viện đề]                                                    [● ĐỒNG BỘ TRỰC TIẾP (Pulse)] │
│                                                                                                  │
│ Thống kê sử dụng                                                                                 │
│ Các phiên đề hiện đang lưu trong tài khoản của bạn.                                              │
│                                                                                                  │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ SUMMARY METRICS DECK (2x2 Grid: grid-cols-2 divide-x divide-y border border-line rounded-xl) │ │
│ ├──────────────────────────────────────────────┬───────────────────────────────────────────────┤ │
│ │ TỔNG SỐ PHIÊN ĐỀ                             │ ĐANG THỰC HIỆN                                │ │
│ │ 23 phiên đề                         100%     │ 17 phiên đề                            74%    │ │
│ │ Tất cả phiên tạo mới & nhân bản              │ Giai đoạn chuẩn bị và sinh đề                 │ │
│ ├──────────────────────────────────────────────┼───────────────────────────────────────────────┤ │
│ │ ĐÃ DUYỆT, CHƯA XUẤT                          │ ĐÃ XUẤT                                       │ │
│ │ 3 phiên đề                          13%      │ 2 phiên đề                             9%     │ │
│ │ Chờ đóng gói tải về                          │ Đã hoàn tất đóng gói tải về                   │ │
│ └──────────────────────────────────────────────┴───────────────────────────────────────────────┘ │
│                                                                                                  │
│ [!] Lưu ý trạng thái: Tổng số phiên bao gồm 1 phiên gặp lỗi.                                     │
│                                                                                                  │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ MACRO COMPOSITION DONUT (Stacked above status list on tablet)                                │ │
│ │                 ╭──────╮                                                                     │ │
│ │              ╭──╯ 74%  ╰──╮           ■ Đang thực hiện: 17 (74%)   ■ Đã duyệt: 3 (13%)       │ │
│ │              │  23 phiên  │           ■ Đã xuất: 2 (9%)            ■ Lỗi: 1 (4%)             │ │
│ │              ╰──╮         ╭──╯                                                               │ │
│ │                 ╰──────╯                                                                     │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ STATUS DISTRIBUTION BAR CHART (Full width on tablet)                                         │ │
│ │ [01] Đang chuẩn bị đề gốc                 [=================              ] 4                │ │
│ │ [01] Đã xác nhận đề gốc                   [=============                  ] 3                │ │
│ │ [02] Đã cấu hình sinh đề                  [=========                      ] 2                │ │
│ │ [02] Đang sinh đề                         [====                           ] 1                │ │
│ │ [02] Đã sinh một phần                     [====                           ] 1                │ │
│ │ [02] Đã sinh đề                           [=================              ] 4                │ │
│ │ [03] Đã duyệt các câu, chờ chốt           [=========                      ] 2                │ │
│ │ [03] Đã duyệt, chưa xuất                  [=============                  ] 3                │ │
│ │ [04] Đã tạo gói xuất                      [=========                      ] 2                │ │
│ │ [ERR] Sinh đề gặp lỗi                     [====                           ] 1                │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ PIPELINE FUNNEL (2x2 Grid on tablet: sm:grid-cols-2 divide-x divide-y)                       │ │
│ ├──────────────────────────────────────────────┬───────────────────────────────────────────────┤ │
│ │ CHẶNG 01: Đề gốc & Blueprint            30%  │ CHẶNG 02: Sinh biến thể AI               35%  │ │
│ │ 7 phiên                       [======      ] │ 8 phiên                        [=======     ] │ │
│ ├──────────────────────────────────────────────┼───────────────────────────────────────────────┤ │
│ │ CHẶNG 03: Kiểm định & Phê duyệt         22%  │ CHẶNG 04: Đóng gói xuất bản               9%  │ │
│ │ 5 phiên                       [====        ] │ 2 phiên                        [==          ] │ │
│ └──────────────────────────────────────────────┴───────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.3 Mobile Wireframe (375px Viewport)

```
┌─────────────────────────────────────────┐
│ MOBILE VIEWPORT (375px)                 │
│ CONTAINER: px-4 py-6                    │
│ GUARANTEE: scrollWidth <= clientWidth   │
├─────────────────────────────────────────┤
│ [← Thư viện đề]                         │
│ [● ĐỒNG BỘ TRỰC TIẾP]                   │
│                                         │
│ Thống kê sử dụng                        │
│ Các phiên đề hiện đang lưu trong        │
│ tài khoản của bạn.                      │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ SUMMARY METRICS DECK                │ │
│ │ (1-Column Stack: divide-y)          │ │
│ ├─────────────────────────────────────┤ │
│ │ TỔNG SỐ PHIÊN ĐỀ                    │ │
│ │ 23 phiên đề                    100% │ │
│ │ Tất cả phiên tạo mới & nhân bản     │ │
│ ├─────────────────────────────────────┤ │
│ │ ĐANG THỰC HIỆN                      │ │
│ │ 17 phiên đề                     74% │ │
│ │ Giai đoạn chuẩn bị và sinh đề       │ │
│ ├─────────────────────────────────────┤ │
│ │ ĐÃ DUYỆT, CHƯA XUẤT                 │ │
│ │ 3 phiên đề                      13% │ │
│ │ Chờ đóng gói tải về                 │ │
│ ├─────────────────────────────────────┤ │
│ │ ĐÃ XUẤT                             │ │
│ │ 2 phiên đề                       9% │ │
│ │ Đã hoàn tất đóng gói tải về         │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ [!] LƯU Ý TRẠNG THÁI                │ │
│ │ 1 phiên gặp lỗi. Thử sinh lại hoặc  │ │
│ │ nhân bản từ Thư viện đề.            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ CƠ CẤU VÒNG ĐỜI                     │ │
│ │               ╭──────╮              │ │
│ │            ╭──╯ 74%  ╰──╮           │ │
│ │            │  23 phiên  │           │ │
│ │            ╰──╮         ╭──╯           │ │
│ │               ╰──────╯              │ │
│ │                                     │ │
│ │ ■ Đang thực hiện         17 (74%)   │ │
│ │ ■ Đã duyệt, chưa xuất     3 (13%)   │ │
│ │ ■ Đã xuất                 2 (9%)    │ │
│ │ ■ Ngoại lệ / lỗi          1 (4%)    │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ PHÂN BỐ TRẠNG THÁI                  │ │
│ │                                     │ │
│ │ ● Đang chuẩn bị đề gốc              │ │
│ │ [=============                    ] │ │
│ │ 4 phiên                             │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã xác nhận đề gốc                │ │
│ │ [==========                       ] │ │
│ │ 3 phiên                             │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đang sinh đề                      │ │
│ │ [===                              ] │ │
│ │ 1 phiên                             │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã sinh đề                        │ │
│ │ [=============                    ] │ │
│ │ 4 phiên                             │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã duyệt, chưa xuất               │ │
│ │ [==========                       ] │ │
│ │ 3 phiên                             │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã tạo gói xuất                   │ │
│ │ [======                           ] │ │
│ │ 2 phiên                             │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Sinh đề gặp lỗi                   │ │
│ │ [===                              ] │ │
│ │ 1 phiên                             │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ QUY TRÌNH 4 CHẶNG                   │ │
│ │ (1-Column Stack: divide-y)          │ │
│ ├─────────────────────────────────────┤ │
│ │ CHẶNG 01                        30% │ │
│ │ Đề gốc & Blueprint                  │ │
│ │ 7 phiên                             │ │
│ │ [==========                       ] │ │
│ ├─────────────────────────────────────┤ │
│ │ CHẶNG 02                        35% │ │
│ │ Sinh biến thể AI                    │ │
│ │ 8 phiên                             │ │
│ │ [===========                      ] │ │
│ ├─────────────────────────────────────┤ │
│ │ CHẶNG 03                        22% │ │
│ │ Kiểm định & Phê duyệt               │ │
│ │ 5 phiên                             │ │
│ │ [=======                          ] │ │
│ ├─────────────────────────────────────┤ │
│ │ CHẶNG 04                         9% │ │
│ │ Đóng gói xuất bản                   │ │
│ │ 2 phiên                             │ │
│ │ [===                              ] │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

---

## 4. Component Design & Interaction Specifications

### 4.1 Global Header & Navigation (`HeaderNav`)
- **Back Navigation Button:**
  - Element: `<Link to="/dashboard">`
  - Classes: `inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted hover:text-strong transition-colors min-h-[44px]`
  - Micro-Interaction: Arrow icon shifts left by 2px on hover (`group-hover:-translate-x-0.5 transition-transform`).
- **Live Sync Badge:**
  - Visual: Pulsating green status dot (`animate-pulse bg-emerald-500 rounded-full h-2 w-2`) accompanied by label `"ĐỒNG BỘ TRỰC TIẾP"`.
  - Mental Value: Informs educators that metrics reflect active database reality.
- **Refresh Action:**
  - Button with rotating sync icon on click (`disabled:opacity-50`).

---

### 4.2 Summary Metrics Deck (`SummaryDeck`)
- **Container Structure:**
  - Monolithic card: `rounded-xl border border-line bg-surface shadow-paper overflow-hidden`
  - Dividers: `grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:divide-x lg:grid-cols-4`
- **Metric Cards:**
  1. `total_sessions`: Master portfolio count. 100% benchmark.
  2. `in_progress_sessions`: Work in progress. Blue highlight accent (`#304c70`).
  3. `approved_not_exported_sessions`: Action required. Amber accent (`#d97706`).
  4. `exported_sessions`: Completed deliverables. Emerald accent (`#15803d`).
- **Typography & Formatting:**
  - Numeral: `text-4xl sm:text-5xl font-bold font-mono tabular-nums text-strong tracking-tight` formatted via `new Intl.NumberFormat('vi-VN')`.
  - Unit: `text-xs font-medium text-muted ml-1.5`.
  - Share badge: `font-mono text-xs font-semibold px-2 py-0.5 rounded border border-line bg-rail text-muted`.

---

### 4.3 Incident Alert Banner (`IncidentAlertBanner`)
- **Render Condition:** Conditional rendering: **only** when `failed > 0 || unknown > 0`. If both are zero, renders nothing (`null`), leaving zero empty white space.
- **Container Styles:** `rounded-xl border border-danger-border bg-danger-soft p-4 sm:p-5 flex items-start gap-3 text-danger shadow-soft`
- **Icon:** `AlertCircle` (`h-5 w-5 text-danger shrink-0 mt-0.5`).
- **Text Composition:**
  - Title: Bold notice specifying the exact count of failed or unknown sessions.
  - Recovery Guidance: Actionable text directing the teacher to retry generation or clone the session from the Library.

---

### 4.4 Status Distribution Chart (`StatusChart`)
- **Semantic DOM Hierarchy:**
  ```html
  <section aria-labelledby="status-chart-title" class="rounded-xl border border-line bg-surface p-6 shadow-paper">
    <div class="flex items-center justify-between ...">
      <h2 id="status-chart-title">Phân bố trạng thái phiên</h2>
      <span>...</span>
    </div>
    <dl class="divide-y divide-line/60">
      <div class="group grid ...">
        <dt>...</dt>
        <dd>...</dd>
      </div>
    </dl>
  </section>
  ```
- **Dynamic Status Rows:**
  - When `counts.unknown === 0`: Renders exactly **10 `<dt>` elements**.
  - When `counts.unknown > 0`: Renders exactly **11 `<dt>` elements**.
- **Layout Grid per Row:**
  - Desktop / Tablet: `sm:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]`
  - Mobile (<640px): Stacked label above bar with formatted count.
- **Bar Mechanics:**
  - Container track: `h-2 rounded-full bg-rail overflow-hidden`
  - Inner fill: `transition-all duration-500 ease-out ${meta.barColor}`
  - Non-zero clamp: `Math.max(4, (count / largest) * 100)%`

---

### 4.5 Macro Composition Donut (`CompositionDonut`)
- **Visual Presentation:** Dual-layer pure SVG vector graphic with central typography.
- **Base Geometry:**
  ```jsx
  <svg className="h-44 w-44 -rotate-90 transform" viewBox="0 0 140 140" aria-hidden="true">
    <circle cx="70" cy="70" r={56} fill="transparent" stroke="var(--rail)" strokeWidth="14" />
    {/* Dynamic Arcs with strokeDasharray and strokeDashoffset */}
  </svg>
  ```
- **Center Readout:**
  - Total numeral: `font-mono text-3xl font-bold tracking-tight text-strong`
  - Subtitle: `text-[11px] font-semibold uppercase tracking-wider text-muted`
- **Tabular Legend List:**
  - Border top separator: `border-t border-line pt-4 mt-6`
  - Each item displays: color dot (`h-2 w-2 rounded-full`), status label, tabular count, and percentage.

---

### 4.6 4-Stage Lifecycle Progression Funnel (`PipelineFunnel`)
- **Visual Presentation:** Unified 4-column connected panel (`rounded-xl border border-line bg-surface p-6 shadow-paper`).
- **Inner Grid:** `grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:divide-x lg:grid-cols-4 border border-line rounded-lg overflow-hidden bg-canvas`.
- **Card Content:**
  - Header: `CHẶNG 01` / `CHẶNG 02` / `CHẶNG 03` / `CHẶNG 04` with percentage pill.
  - Stage Title: Vietnamese stage name (`text-sm font-bold text-strong`).
  - Stage Description: Explanatory subtitle (`text-xs text-muted line-clamp-2`).
  - Volume Readout: `font-mono text-2xl font-bold tabular-nums text-strong` + `phiên`.
  - Progress Bar: Proportional linear bar indicating stage share of total pipeline work.

---

### 4.7 Lifecycle State Containers

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STATE CONTAINERS SPECIFICATION                                                                   │
├───────────────────┬──────────────────────────────────────────────────────────────────────────────┤
│ State             | DOM Specification & Visual Treatment                                         │
├───────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ **Loading State** | `<div role="status" aria-busy="true" aria-live="polite">`                    │
│                   | Renders animated spinner with label "Đang tải dữ liệu thống kê...".          │
│                   | Retains container height (min-h-[400px]) to prevent layout cumulative shift. │
├───────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ **Error State**   | `<div role="alert" className="border-danger-border bg-danger-soft">`         │
│                   | Renders AlertCircle icon, Vietnamese error explanation, and an interactive   │
│                   | "Thử lại" retry button with full keyboard focus support.                     │
├───────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ **Empty Account** | Renders Summary Deck with honest zeros (`0 phiên đề`).                       │
│                   | Informational empty banner: "Bạn chưa có phiên đề nào trong tài khoản."      │
│                   | Action button: "Tạo phiên đề mới" linking to `/session/new` or `/dashboard`. │
│                   | Donut and Funnel cleanly return `null` without throwing errors.              │
└───────────────────┴──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Responsive Breakpoint Matrix & Layout Rules

```
+──────────────────────────────────────────────────────────────────────────────────────────────────+
|                               RESPONSIVE BREAKPOINT SPECIFICATION                                |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| Breakpoint Token  | Min Width    | Grid / Column Adaptations          | Layout Padding & Overflow |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Mobile (`xs`)** | `< 640px`    | - Deck: 1-column stack (divide-y) | - Container: `px-4 py-6`  |
|                   | (Target 375) | - Hub: 1-column stack             | - Zero horizontal scroll  |
|                   |              | - Funnel: 1-column stack          |   (`scrollWidth <= client`)|
|                   |              | - Status bars: stacked label/bar  | - Tap targets >= 44px     |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Tablet (`sm`)** | `640px` -    | - Deck: 2x2 grid (divide-x & y)   | - Container: `px-6 py-8`  |
|                   | `767px`      | - Hub: 1-column stack             | - Bar label grid begins   |
|                   |              | - Funnel: 2x2 grid                |   `sm:grid-cols-[17rem_1fr`|
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Tablet (`md`)** | `768px` -    | - Deck: 2x2 grid                  | - Container: `px-6 py-8`  |
|                   | `1023px`     | - Hub: Donut above Status list    | - Donut centered          |
|                   |              | - Funnel: 2x2 grid                |                           |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Desktop (`lg`)**| `1024px` -   | - Deck: 4-column row (divide-x)   | - Container: `px-8 py-8`  |
|                   | `1439px`     | - Hub: 2-column split [1fr_340px] | - Donut sticky right col  |
|                   |              | - Funnel: 4-column row            | - Max width: `72rem`      |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Wide (`xl`)**   | `>= 1440px`  | - Deck: 4-column row              | - Container: `px-8 py-8`  |
|                   |              | - Hub: 2-column split [1fr_340px] | - Max width: `72rem`      |
|                   |              | - Funnel: 4-column row            |   centered with margins   |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
```

### 5.1 Horizontal Overflow Prevention Rules:
1. All containers enforce `max-w-full`.
2. Tables and definition lists use `break-words` and `min-w-0` on text flex containers.
3. SVG charts use fixed internal `viewBox` coordinates with responsive outer percentage wrappers (`h-44 w-44`).
4. Automated verification constraint: `document.documentElement.scrollWidth <= document.documentElement.clientWidth` across 375px, 768px, and 1440px.

---

## 6. Accessibility & Keyboard Navigation Specifications

1. **Focus Ring Indication:**
   - Interactive links and buttons enforce: `focus-visible:ring-2 focus-visible:ring-highlight focus-visible:outline-none focus-visible:ring-offset-2`.
2. **Minimum Tap Target Area:**
   - In accordance with `.paper-ui` and WCAG 2.5.5, all interactive elements have a minimum clickable/tappable height of `2.75rem` (44px).
3. **Screen Reader Semantic Tree:**
   - Summary cards use semantic `<dl>`, `<dt>`, `<dd>`.
   - Status chart uses `<section aria-labelledby="status-chart-title">` with `<dl>`, `<dt>`, `<dd>`.
   - SVG charts include `aria-hidden="true"` with accessible tabular legends.
   - Live regions (`aria-live="polite"`, `role="status"`, `role="alert"`) are employed for loading and error states.
4. **Reduced Motion Compliance:**
   - Respects `@media (prefers-reduced-motion: reduce)` by disabling SVG stroke transition animations and pulse rings.

---

## 7. Conclusion & Implementation Readiness

This design system and wireframe specification provides complete, unambiguous implementation blueprints for Worker M3. Every token, geometry, component boundary, and responsive adaptation is mathematically defined, grounded in real backend data, and fully verified against the project repository.
