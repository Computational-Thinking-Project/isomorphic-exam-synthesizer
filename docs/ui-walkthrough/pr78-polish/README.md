# PR #78 — Paper Canvas polish evidence

Captured on 17/11/2026 in the local Brave browser. Screenshots use the actual React components with fixture data; **no live backend or OAuth verification** is implied.

Before: source from PR head `212457be5d3388ebe28fb58056d3ea81ec680597`, with its own compiled Tailwind stylesheet. After: the local working tree on that head. Brand assets and fixture inputs are the same. Desktop pairs use a 1440 × 1000 viewport; images are viewport captures unless the image includes the full page. Mobile captures use 375 × 812; the additional tablet capture uses 1024 × 900.

The portable `PREVIEW.html` remained the design direction in the task/code. Its `file:` URL was blocked by browser policy; these pairs compare the actual application before and after, rather than claiming a pixel comparison with the portable reference.

| Step | Surface and outcome | Before | After |
|---|---|---|---|
| 1 | Login: simpler sign-in card, preserved two-column layout | [Desktop](login-before-1440.jpg) | [Desktop](login-after-1440.jpg), [mobile](login-after-375.jpg) |
| 2 | Dashboard: no incomplete search/filter, no static activity indicator, clear row actions | [Desktop](dashboard-before-1440.jpg) | [Desktop](dashboard-after-1440.jpg), [tablet](dashboard-after-1024.jpg), [mobile](dashboard-after-375.jpg) |
| 3 | Create: shared title/Mathematics/grade fields | [Desktop](create-before-1440.jpg) | [Desktop](create-after-1440.jpg), [mobile](create-after-375.jpg), [modal](create-modal-after-375.jpg) |
| 4 | Stage 1: fewer nested cards and one correct-answer label | [Desktop](stage1-before-1440.jpg) | [Desktop](stage1-after-1440.jpg), [mobile read tab](stage1-preview-after-375.jpg) |
| 5 | Confirmed source: read-only preview and meaningful status actions | — | [Desktop](stage1-readonly-after-1440.jpg) |

All four main surfaces were visually inspected at desktop/mobile sizes; the 1024 px dashboard screenshot also checks that action labels fit without wrapping. Mobile images show only the viewport; lower list rows remain scrollable.

[Responsive measurements](responsive-checks.json): login, creation, dashboard, Stage 1 draft and Stage 1 read-only at 375/768/1024/1440 px. All 20 document `scrollWidth` measurements were no greater than the viewport width. This is a layout check, not proof against every long-content or browser-specific case.

Keyboard checks in the local fixture: selecting grade 1; Shift+Tab from title to close and from close to cancel; Escape closing the modal and restoring focus to its trigger. The mobile Stage 1 tab round-trip retained an entered textarea value.

Not verified here: production OAuth/API/DB, actual browser zoom at 200%, exhaustive screen-reader/contrast validation, deployed later-stage visuals. Automated regression results and the component inventory are in [TASK-77](../../tasks/TASK-77.md).

The author inspected these images; this is not independent acceptance or GitHub Approve.
