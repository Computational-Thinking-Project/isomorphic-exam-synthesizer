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
| **Display Metric 2** | `text-2xl sm:text-3xl font-bold font-mono tabular-nums` | `1.50rem / 24px` → `1.875rem / 30px` | Bold (700) | `1.1` | Status chart totals, secondary counters |
| **Page Title** | `text-2xl sm:text-3xl font-extrabold text-strong tracking-tight` | `1.50rem / 24px` → `1.875rem / 30px` | Extra Bold (800) | `1.2` | Main page title ("Thống kê sử dụng") |
| **Section Header** | `text-base font-bold text-strong` | `1.00rem / 16px` | Bold (700) | `1.5` | Section titles ("Phân bố trạng thái phiên") |
| **Card / Label Header** | `text-xs font-bold text-muted uppercase tracking-wider` | `0.75rem / 12px` | Bold (700) | `1.4` | KPI deck category headers, stage badges ("01", "02") |
| **Body / Row Label** | `text-sm font-medium text-strong` | `0.875rem / 14px` | Medium (500) | `1.5` | Status chart row titles, alert banner copy |
| **Subtitle / Description**| `text-xs text-muted leading-relaxed` | `0.75rem / 12px` | Normal (400) | `1.5` | Subtitles, status descriptions, contextual hints |
| **Micro Benchmark** | `text-[11px] font-semibold uppercase tracking-wider` | `0.6875rem / 11px` | Semi-Bold (600) | `1.3` | Status indicator pills, category labels |

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

All visual representations are built strictly with semantic HTML and Tailwind CSS utilities. Per Issue #97 and finding F102-01, the dashboard focuses exclusively on a single authoritative distribution chart (`StatusChart`) alongside the 4 summary KPIs, eliminating redundant visual models (`CompositionDonut`, `PipelineFunnel`).

#### Horizontal Status Distribution Bars (`StatusChart`)
- **Markup:** Semantic `<section aria-labelledby="status-chart-title">` enclosing `<dl className="divide-y divide-line/60">`.
- **Dynamic Rows Rule:**
  - When `unknown === 0`: Renders exactly **10 `<dt>` / `<dd>` rows** (hides `unknown` to keep the UI clean).
  - When `unknown > 0`: Renders exactly **11 `<dt>` / `<dd>` rows** (reveals `unknown` dynamically alongside the incident banner).
- **Proportional Fill Geometry:**
  - Let `largest = Math.max(1, ...counts)`.
  - Bar width: `largest > 0 ? (count / largest) * 100 : 0`.
  - Non-zero visual clamp: when `count > 0`, CSS width is at least `4%` so small counts remain visible.
- **Zero-State Handling:** Rows with `count === 0` are rendered cleanly with a muted dot (`bg-muted/40`), a muted title (`text-muted`), a blank track, and a grayed-out `0` numeral (`text-muted/50`).

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
│ [← Thư viện đề]                                                            [Số liệu tại thời điểm tải trang]│
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
│ │ STATUS DISTRIBUTION BAR CHART (StatusChart: border border-line rounded-xl bg-surface p-6 shadow-paper)│ │
│ │                                                                                                        │ │
│ │ Phân bố trạng thái phiên                                                               10 trạng thái   │ │
│ │ Chi tiết 11 trạng thái dọc chuỗi nghiệp vụ                                                             │ │
│ │ ────────────────────────────────────────────────────────────────────────────────────────────────────── │ │
│ │ [01] Đang chuẩn bị đề gốc              [========================================      ] 4 phiên (17%)  │ │
│ │ [01] Đã xác nhận đề gốc                [==============================                ] 3 phiên (13%)  │ │
│ │ [02] Đã cấu hình sinh đề               [====================                          ] 2 phiên  (9%)  │ │
│ │ [02] Đang sinh đề                      [==========                                    ] 1 phiên  (4%)  │ │
│ │ [02] Đã sinh một phần                  [==========                                    ] 1 phiên  (4%)  │ │
│ │ [02] Đã sinh đề                        [========================================      ] 4 phiên (17%)  │ │
│ │ [03] Đã duyệt các câu, chờ chốt        [====================                          ] 2 phiên  (9%)  │ │
│ │ [03] Đã duyệt, chưa xuất               [==============================                ] 3 phiên (13%)  │ │
│ │ [04] Đã tạo gói xuất                   [====================                          ] 2 phiên  (9%)  │ │
│ │ [ERR] Sinh đề gặp lỗi                  [==========                                    ] 1 phiên  (4%)  │ │
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
│ [← Thư viện đề]                                                [Số liệu tại thời điểm tải trang] │
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
│ │ STATUS DISTRIBUTION BAR CHART (Full width on tablet)                                         │ │
│ │ [01] Đang chuẩn bị đề gốc                 [=================              ] 4 phiên (17%)    │ │
│ │ [01] Đã xác nhận đề gốc                   [=============                  ] 3 phiên (13%)    │ │
│ │ [02] Đã cấu hình sinh đề                  [=========                      ] 2 phiên  (9%)    │ │
│ │ [02] Đang sinh đề                         [====                           ] 1 phiên  (4%)    │ │
│ │ [02] Đã sinh một phần                     [====                           ] 1 phiên  (4%)    │ │
│ │ [02] Đã sinh đề                           [=================              ] 4 phiên (17%)    │ │
│ │ [03] Đã duyệt các câu, chờ chốt           [=========                      ] 2 phiên  (9%)    │ │
│ │ [03] Đã duyệt, chưa xuất                  [=============                  ] 3 phiên (13%)    │ │
│ │ [04] Đã tạo gói xuất                      [=========                      ] 2 phiên  (9%)    │ │
│ │ [ERR] Sinh đề gặp lỗi                     [====                           ] 1 phiên  (4%)    │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘ │
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
│ [Số liệu tại thời điểm tải trang]       │
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
│ │ PHÂN BỐ TRẠNG THÁI                  │ │
│ │                                     │ │
│ │ ● Đang chuẩn bị đề gốc              │ │
│ │ [=============                    ] │ │
│ │ 4 phiên (17%)                       │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã xác nhận đề gốc                │ │
│ │ [==========                       ] │ │
│ │ 3 phiên (13%)                       │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đang sinh đề                      │ │
│ │ [===                              ] │ │
│ │ 1 phiên (4%)                        │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã sinh đề                        │ │
│ │ [=============                    ] │ │
│ │ 4 phiên (17%)                       │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã duyệt, chưa xuất               │ │
│ │ [==========                       ] │ │
│ │ 3 phiên (13%)                       │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Đã tạo gói xuất                   │ │
│ │ [======                           ] │ │
│ │ 2 phiên (9%)                        │ │
│ │ ─────────────────────────────────── │ │
│ │ ● Sinh đề gặp lỗi                   │ │
│ │ [===                              ] │ │
│ │ 1 phiên (4%)                        │ │
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
- **Data Freshness Label:**
  - Visual: Static label `"Số liệu tại thời điểm tải trang"` in font-mono muted typography.
  - Mental Value: Clearly informs educators that metrics reflect the database state at page load time rather than a continuous realtime subscription (F102-03).
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

### 4.5 Lifecycle State Containers

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
│                   | Status chart cleanly renders zero values without throwing errors.            │
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
|                   | (Target 375) | - Status bars: stacked label/bar  | - Zero horizontal scroll  |
|                   |              |                                   |   (`scrollWidth <= client`)|
|                   |              |                                   | - Tap targets >= 44px     |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Tablet (`sm`)** | `640px` -    | - Deck: 2x2 grid (divide-x & y)   | - Container: `px-6 py-8`  |
|                   | `767px`      | - Status bars: 2-column flex rows | - Bar label grid begins   |
|                   |              |   `sm:grid-cols-[17rem_1fr]`      |   `sm:grid-cols-[17rem_1fr`|
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Tablet (`md`)** | `768px` -    | - Deck: 2x2 grid                  | - Container: `px-6 py-8`  |
|                   | `1023px`     | - Status bars: 2-column flex rows |                           |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Desktop (`lg`)**| `1024px` -   | - Deck: 4-column row (divide-x)   | - Container: `px-8 py-8`  |
|                   | `1439px`     | - Status bars: broadsheet section | - Max width: `72rem`      |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
| **Wide (`xl`)**   | `>= 1440px`  | - Deck: 4-column row              | - Container: `px-8 py-8`  |
|                   |              | - Status bars: broadsheet section | - Max width: `72rem`      |
|                   |              |                                   |   centered with margins   |
+───────────────────+──────────────+───────────────────────────────────+───────────────────────────+
```

### 5.1 Horizontal Overflow Prevention Rules:
1. All containers enforce `max-w-full`.
2. Tables and definition lists use `break-words` and `min-w-0` on text flex containers.
3. Automated verification constraint: `document.documentElement.scrollWidth <= document.documentElement.clientWidth` across 375px, 768px, and 1440px.

---

## 6. Accessibility & Keyboard Navigation Specifications

1. **Focus Ring Indication:**
   - Interactive links and buttons enforce: `focus-visible:ring-2 focus-visible:ring-highlight focus-visible:outline-none focus-visible:ring-offset-2`.
2. **Minimum Tap Target Area:**
   - In accordance with `.paper-ui` and WCAG 2.5.5, all interactive elements have a minimum clickable/tappable height of `2.75rem` (44px).
3. **Screen Reader Semantic Tree:**
   - Summary cards use semantic `<dl>`, `<dt>`, `<dd>`.
   - Status chart uses `<section aria-labelledby="status-chart-title">` with `<dl>`, `<dt>`, `<dd>`.
   - Live regions (`aria-live="polite"`, `role="status"`, `role="alert"`) are employed for loading and error states.
4. **Reduced Motion Compliance:**
   - Respects `@media (prefers-reduced-motion: reduce)` by disabling transition animations.

---

## 7. Conclusion & Implementation Readiness

This design system and wireframe specification provides complete, unambiguous implementation blueprints for Worker M3. Every token, geometry, component boundary, and responsive adaptation is mathematically defined, grounded in real backend data, and fully verified against the project repository.
