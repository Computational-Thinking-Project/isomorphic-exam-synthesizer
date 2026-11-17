# TASK-77 — Paper Canvas UI through final preview and approval

- Task: [Issue #77](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/77); [PR #78](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/78).
- Mode: **Author**. No new member or reviewer assignments.
- Workflow: **v0.1 proposed**, INPUT-20261109; workflow document commit `7b7387f4c5034e7cf92f4591e80f8a9eb4452122`.
- Branch: `feat/initial-pages-ui-redesign`.
- Snapshot used for this follow-up: base `dev` at `1ff345cc4d1ca04d81abc75b6ca14db0f192c9db`; head `212457be5d3388ebe28fb58056d3ea81ec680597` plus the local working-tree changes described below.
- Updated: **17/11/2026**. Status: **implemented and author-checked locally; not independently accepted**. The owner explicitly authorized commit and push of this follow-up; independent review and GitHub approval remain outstanding.

## Goal and boundaries

Keep the Paper Canvas direction from `docs/ui-walkthrough/PREVIEW.html`, with the existing logo, artwork and semantic palette. Simplify Login, Dashboard, both session-creation entry points, Stage 1, configuration/generation, question review and final preview/approval for teachers. Remove misleading affordances and redundant information, while preserving actual operations and recovery paths.

The user selected **remove Dashboard search/filter** and **retain the reference style while simplifying it**. Existing Issue #77 scope remains: frontend presentation and relevant regression tests, with this task document and visual evidence. No API/schema/auth-controller changes, new production routes, backend work, Export redesign, deployment or merge.

W4 assignment remains the integration context: `docs/tasks/W4_ASSIGNMENT.md`. Issue #77 is the specific UI assignment; this follow-up does not change weekly ownership, deferred KPI work, or deadlines.

## Component inventory and decisions

| Surface / visible elements | Decision / real behavior |
|---|---|
| Login logo, introduction, artwork | Keep existing brand assets and two-column desktop layout; shorten copy; hide large artwork on mobile. |
| Security badge, Google OAuth label, SymPy marketing copy | Remove redundant implementation and promotional labels. |
| Google sign-in | Keep the real OAuth action, pending/disabled behavior and error handling. Spinner only for pending work; failures are alerts. |
| Profile retry and current-account sign-out | Keep conditional controls and actual handlers. |
| Dashboard profile/avatar/sign-out | Keep actual account UI; remove the static green “Đang hoạt động” indicator, which did not measure activity. |
| Dashboard heading/artwork | Keep a shorter introduction and smaller supporting artwork. |
| Search/status filter/clear filters/result counter/filter-empty state | Remove: they filtered only the loaded page, giving an incomplete library search. |
| Create CTA | One per loaded list state: empty-state CTA for zero sessions; heading CTA when sessions exist. |
| Session title/subject/grade/date/status | Keep real metadata; remove the inaccurate blanket editable-draft description. Read-only hint remains for approved/exported sessions. |
| Open/continue/view and clone | Keep real handlers and loading guards. Expand action column to avoid wrapped labels; use stacked rows below 1024 px. |
| List loading/error/retry | Keep actual loading and retry behavior. |
| Pagination | Render only after a successful response with more than one page; preserve server pagination and boundary guards. |
| Creation title/subject/grade | Shared `SessionMetadataFields`: required title, static Mathematics, one grade selector 1–12, default 12. Both callers retain payload `{ title, subject: 'Toán', grade }`. |
| Creation submit/cancel/close | Keep controller and uncertain-result guard. Modal restores focus, traps keyboard navigation and scrolls on small screens. |
| Check-created-sessions action | Keep only for uncertain creation results; preserve its existing list-refresh behavior. |
| Clone title/submit/cancel/close | Keep actual clone behavior, existing focus/request guards; align modal width, scroll containment and footer. |
| Stage 1 breadcrumb/metadata | Keep navigation and actual title/subject/grade; allow a full-width breadcrumb row on mobile. |
| Mobile input/read tabs | Keep in drafts with pressed-state semantics; input stays mounted during tab changes. Remove tabs after source confirmation. |
| Text/file mode, textarea, picker/dropzone, clear-file | Keep in drafts with existing validation, supported formats and progress. Hide after confirmation. |
| Load-source action | Primary before source exists, secondary after loading; hide for read-only source. |
| Source preview / correct-answer chip | Keep KaTeX and keyed option styling; one answer label per question, explicit unknown-answer fallback. Remove version counter and redundant answer footer. |
| Confirm source | Primary when a draft has source questions; preserve readiness/confirmation guards and incomplete-content dialog. Hide for empty/read-only sources. |
| Reload source/status, confirmation storage recovery, stop waiting | Keep real recovery operations under existing availability guards. Stop-waiting remains limited to the existing request phases. |
| Canonical preparation / check / retry / continue | Use teacher-facing “cấu trúc đề” labels. Keep pending/running/ready/failed logic, conditional retry and readiness-gated continue. |
| Incomplete-content dialog | Preserve error list, close, choose-corrected-file and switch-to-text behavior. |
| Stage 1 non-draft destination link | Keep real destination; use Paper Canvas styling and remove HTTP code from routine guidance. |

## Implementation sequence and interfaces

1. Remove page-local search/filter state and redundant UI; retain list and pagination controllers.
2. Extract the shared creation fields; retain `createSessionEntryController` and both existing entry routes.
3. Simplify login notices, dashboard rows and Stage 1 state-specific controls; preserve source ingestion and confirmation controllers.
4. Scope 44 px controls, visible focus and reduced-motion styling under `.paper-ui`, protecting later-stage layouts.
5. Verify behaviors, render the real components with local fixtures, capture before/after evidence and update this handoff.

No public API, wire shape, route or schema changes. The new internal component takes `metadata`, `onChange(field, value)`, `disabled` and an optional title input ref. It replaces duplicate form markup, not the creation controller.

## Author verification — 17/11/2026

- Windows / PowerShell; Node's existing test runner and repository DOM harness.
- `npm --prefix frontend run lint`: **PASS**, 0 errors / 0 warnings after relocating temporary visual fixtures out of the lint source tree.
- `npm --prefix frontend test`: **491 PASS**, 0 fail / skipped / cancelled.
- `npm --prefix frontend run build`: **PASS**. Vite still reports its large-chunk warning; no bundling policy was changed.
- `git diff --check`: checked separately before handoff.
- F01: pagination regression suite retains two-page forward/back/boundary checks and now covers hidden pagination for 0/1/20 sessions plus one create CTA.
- F02/F03: existing uncertain-creation and unmount/cancellation tests pass. New tests exercise grade 1 and Mathematics payload through both creation entry points.
- F04: semantic color configuration retained; lint and production build pass.
- Existing ingestion/file/drop/progress/confirmation/recovery/readiness tests pass with the new labels. Read-only assertions now verify that source editing/loading/confirmation controls are absent.
- Browser: real React components rendered with **local fixture API responses**. Five surfaces (login, creation, dashboard, Stage 1 draft, Stage 1 read-only) × four widths (375/768/1024/1440): no document horizontal overflow in 20 measurements.
- Browser interactions: mobile input/read tab round-trip preserved textarea text; modal grade selection, Shift+Tab focus cycling, Escape close and trigger-focus restoration checked.
- [Visual evidence and limitations](../ui-walkthrough/pr78-polish/README.md).

## Evidence limits and remaining acceptance

- Screenshots compare PR head `212457be` with this working tree using the same fixtures, not a production backend or `PREVIEW.html` screenshot. The integrated browser denied the reference's `file:` URL; no pixel-fidelity claim is made.
- No live Google sign-in, real database/API/Gemini ingestion or deployed workflow smoke was performed. Later-stage frontend suites pass; deployed Stage 2/3/Export visuals remain unverified.
- Actual browser 200% zoom, full screen-reader testing and a complete WCAG AA audit remain unverified; screenshots and width measurements are not accessibility certification.
- Temporary comparison source/fixture code lives only in ignored local cache, outside production entry points. Its authentication bypass and mock adapter are not product changes.
- Previously documented F01–F04 are **author-checked**, not independent reviewer verification or GitHub Approve. PR remains under its existing review/approval process; remote body/check status has not been updated by this follow-up.

## Expanded scope — owner-approved 17/11/2026

The owner expanded PR #78 through final preview and approval, stopping before Export, and selected a list of questions under version tabs for post-generation review. Implementation starts at `5920989`; earlier verification above describes the initial-page snapshot only.

| Surface / controls | Implemented decision and condition |
|---|---|
| Configuration | 1–4 versions, real ordering checkboxes, saved preferences and original readiness guard; remove automatic-mode catalog and technical labels. Submit keeps the existing payload. |
| Generation | Paper Canvas surfaces, actual progress snapshot, unknown-data label, truthful partial-completion badge; reconnect/retry/view use existing handlers. No invented cancel operation. |
| Review | Version tabs and question list, official code when supplied or a neutral version index; solution only in detail dialog. Remove permanently disabled export/coming-soon actions. |
| Review continuation | One preview action with missing/unapproved explanation. Bulk retry appears only when loaded data confirms missing slots. Locked sessions hide mutation actions. |
| Final preview | Keep original-order and full-shuffle operations with plain labels; remove unconditional shuffled claims. Version tabs and answer matrix retain real data. |
| Approval | Existing canApprove and session fences retained; labeled, scrollable confirmation dialog with focus containment, Escape and trigger restoration. Pending approval cannot close the dialog. Successful approval keeps the existing Export destination. |
| Shared presentation | Light semantic surfaces throughout loading/error/locked/dialog states; scoped control sizing and local display-math scrolling. Export is outside the visual changes. |

### Author checks for expanded implementation

- Frontend tests: **491 passed**, 0 failed/skipped/cancelled; includes payload, SSE recovery, partial generation, accept/regenerate, ordering, approval, locked-state and stale-session regression coverage.
- `npm --prefix frontend run lint`: PASS, 0 warnings.
- `npm --prefix frontend run build`: PASS; existing large-chunk warning remains.
- Real React components with local fixture responses: config, progress, review and preview at 375/768/1024/1440 px, **16 measurements without document horizontal overflow**.
- Browser: mobile solution dialog inspected; approval dialog focuses its close control, Escape closes and restores focus to its trigger. Answer matrix rendered and inspected.
- Screenshots: `docs/ui-walkthrough/pr78-polish/review-expanded.png` and `preview-expanded.png`. Fixtures and browser harness remain ignored under node_modules, never enabled in production.
- Limits: no live OAuth/API/DB generation or actual export rendering checked in this follow-up. Actual browser 200% zoom and a complete accessibility audit remain unverified. Browser screenshots use fixtures, not production data. No independent approval, merge or deployment is claimed.


### Source preparation UX follow-up

After confirmation, Stage 1 now polls the existing source-artifacts GET every 2 seconds while pending/running (or retry acceptance is unresolved). The controller retains request/account/session guards; polling stops on readiness, confirmed failure, access errors or unmount. Network failures remain retryable reads and never resubmit confirmation.

Preparation progress uses API completed_count / total_questions, stays below 100 until authoritative readiness, and is indeterminate if counts are missing. The configuration button remains visible and disabled until ready; completion fills the bar and enables the button without navigating automatically. Confirmed failure offers Retry. The manual status button and normal read-only source reload are removed; recovery reload remains available when needed.

Checks: 491 frontend tests passed; lint, build and diff check passed. Build retains its existing chunk-size warning. Live API preparation and browser rendering were not checked in this follow-up.


### Inline post-generation review follow-up

- Removed both 1.5s automatic Stage 2 -> Stage 3 redirects. Completion now waits for explicit navigation. Review links back to read-only generation information, including saved count and ordering preferences.
- Review retains version lists, adds per-version approval counts and state filters, removes unsupported quality claims, and expands one solution inside its question card. Existing guarded accept/regenerate operations are reused, including stable idempotency keys and stale-session fences.
- The source question is expandable. Approved-question regeneration asks for confirmation. The reviewed question remains in place under the pending filter; moving to the next unreviewed question is explicit. View location/filter/version/expanded question are restored through optional session storage, with server-loaded approval data.
- Mutation feedback is shown in the expanded card; final preview stays disabled during mutations. Locked sessions retain read-only solutions.
- Verification: 491 frontend tests PASS; lint/build/diff check PASS (existing chunk-size warning). Local browser fixture verified expansion, acceptance and explicit next-question navigation. Screenshot: `docs/ui-walkthrough/pr78-polish/review-inline.png`.
- Limits: live API/DB, actual 200% zoom, full mobile regression and browser Stage 2 round-trip remain unverified in this follow-up. Existing backend working-tree changes were excluded.
