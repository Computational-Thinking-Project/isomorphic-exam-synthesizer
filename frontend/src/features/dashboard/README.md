# Dashboard UI — TASK-103

Current increment uses mock data and a standalone development preview. It is not yet connected to App/router, authentication, backend sessions or the Clone Modal.

## Preview

From the frontend directory, run `npm.cmd run dev` and open `/dashboard-preview.html` on the address printed by Vite. The selector covers success, empty and error scenarios. Retry in the fixed error scenario returns an error again; selecting success restores the list.

The HTML entry is `frontend/dashboard-preview.html`; the React entry is `src/features/dashboard/dashboard-preview.jsx`. The preview renders only in development. The default production build uses `index.html`, so it does not include this preview.

## Props and ownership

| Component | Props |
|---|---|
| DashboardPage | `loadSessions(): Promise<Session[]>`, `onCreate()`, `onOpen(session)`, `onClone(session)` |
| DashboardSessionCard | `session`, `onOpen(session)`, `onClone(session)` |

TV1 owns the page/card and future router integration. TV2 receives the selected session through the parent's clone handler and implements the Clone Modal. The preview only displays callback notices; it does not create/clone sessions or navigate.

`dashboardMock.js` supplies `listDashboardSessions({ scenario })`, where scenario is success, empty or error. Session fields are `id`, `title`, `subject`, `created_at`, `status`; these are illustrative fixtures, not the final TV3 API contract. Approved/exported fixtures show a view label; destination routes are decided by the parent after the status contract is agreed.

## Verification and remaining work

Focused lint of the four JS/JSX files, five manual data assertions and browser checks passed during Codex review on 16/10/2026. Browser checks covered loading/list/empty/error/retry, callbacks, rapid scenario changes, reload and mobile at 390×844.

Auth PR #2 supplies the shared lint/auth setup. After it merges, receive updated dev, integrate the protected Dashboard route and run full frontend lint/build and relevant tests. Real list API, stage navigation and modal integration remain pending. This increment does not complete TASK-103.
