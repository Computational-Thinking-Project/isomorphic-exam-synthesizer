# Dashboard UI — TASK-103

Dashboard is connected to `/dashboard` under `ProtectedRoute`. Google/Supabase sign-in, session restoration and sign-out are implemented in the shared auth flow, but application profile verification is still pending. A valid Supabase session enters `profile_pending` and does not grant access to Dashboard yet.

Dashboard still uses mock session data and action notices. Backend session APIs, real create/open navigation and the Clone Modal are not integrated in this branch. The current layout is provisional; TASK-101/103 are not complete.

## Run and check

From the frontend directory:

```powershell
npm.cmd ci
npm.cmd run test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

Use the address printed by Vite; the configured port is 3000, but Vite may choose another available port. For Supabase environment variables and Google redirects, follow the [frontend setup guide](../../../README.md). The standalone Dashboard preview below does not require a Supabase connection.

1. Open `/dashboard` without a session: while auth is being checked, expect a waiting message; afterward, expect a redirect to `/login`.
2. On `/login`, sign in with Google using the existing Supabase configuration. After returning, expect the message that a session exists but profile verification is not connected. Dashboard remains blocked.
3. Reload: the Supabase session should be restored and return to `profile_pending`. This does not load real Dashboard data.
4. Select **Đăng xuất** on `/login`: expect the session to end. Reload should keep you signed out; opening `/dashboard` should return to `/login`.

The previous mock auth route has been removed. Do not manually set a mock user in the auth store to bypass profile verification. Use the standalone preview to inspect Dashboard while profile integration is pending. Its behavior does not verify authentication or protected-route access.

## Standalone state preview

From the frontend directory, run `npm.cmd run dev` and open `/dashboard-preview.html` on the address printed by Vite. The selector covers success, empty and error scenarios. Retry in the fixed error scenario returns an error again; selecting success restores the list.

1. Select **Có dữ liệu**: expect loading followed by three sample session cards.
2. Click **Tạo đề mới**, continue/view or clone: expect a notice identifying the action/session. These actions do not create sessions, navigate to editing screens or open a modal.
3. Select **Danh sách rỗng**: expect an empty-state message.
4. Select **Lỗi tải danh sách**: expect an error and **Thử lại** button. Retry stays in the simulated error scenario; switch back to **Có dữ liệu** to restore the list.

The HTML entry is `frontend/dashboard-preview.html`; the React entry is `src/features/dashboard/dashboard-preview.jsx`. This separate preview renders only in development and is not included in the default production build. The routed Dashboard is included in that build.

## Props and ownership

| Component | Props |
|---|---|
| DashboardPage | `loadSessions(): Promise<Session[]>`, `onCreate()`, `onOpen(session)`, `onClone(session)` |
| DashboardSessionCard | `session`, `onOpen(session)`, `onClone(session)` |

TV1 owns the page/card and `DashboardRoute.jsx`, which supplies the stable mock loader and callback notices. TV2 receives the selected session through `onClone(session)` and implements the Clone Modal; TV1 will integrate it later. These callback names are the handoff; they do not define the final backend request/response or modal completion contract.

`dashboardMock.js` supplies `listDashboardSessions({ scenario })`, where scenario is success, empty or error. Session fields are `id`, `title`, `subject`, `created_at`, `status`; these are illustrative fixtures, not the final TV3 API contract. Approved/exported fixtures show a view label; destination routes are decided by the parent after the status contract is agreed.

## Verification and remaining work

Current documentation checkpoint, 19/10/2026:

- Google sign-in/session handling is implemented, but profile verification is not connected. `ProtectedRoute` requires `authenticated` and an application user; `profile_pending` cannot enter Dashboard.
- Dashboard's loader and create/open/clone callbacks still use mocks/notices. `DashboardRoute.jsx` also retains a development-only **Đăng xuất mẫu** control that only clears the auth store; it is not the Supabase sign-out flow. Replace it when integrating the authenticated Dashboard; use the real sign-out button on `/login` at this checkpoint.
- The recorded auth checkpoint is 37 unit tests, lint/build and 20 controlled browser bootstrap checks; see the [frontend setup guide](../../../README.md) for scope and limits. These are not Dashboard API or Clone Modal tests and were not rerun for this documentation-only change.
- This update was checked against the source and local documentation links. No new browser, backend, Docker or account-isolation checks were run.

Historical Dashboard UI verification on 17/10/2026, before the real auth changes above:

- `npm.cmd run test`: 3/3 auth-store unit tests passed; these are not automated Dashboard tests.
- Full `npm.cmd run lint`, `npm.cmd run build` and `git diff --check`: passed.
- Browser: protected route, checking state, mock sign-in, loading/list, action notices, mock sign-out and reload passed. Standalone preview empty/error/retry and return to success passed.
- Mobile 390×844: one column, no horizontal overflow. Captured console had no errors; React Router future-flag warnings remain.

The last author-provided `npm audit` report on 17/10/2026 contained 15 vulnerabilities (4 low, 5 moderate, 6 high). Audit has not passed; no dependency upgrades or `npm audit fix --force` were applied in this increment. Dependency remediation requires separate compatibility checks and review.

Remaining work: integrate TV3/Duy's application profile and session APIs after review; display the user name/avatar and use real sign-out in Dashboard; integrate TV2/Bội Anh's Clone Modal after its review fixes; connect create/open navigation and refresh the list after cloning. Then verify real session persistence, errors and data separation between accounts with the backend. Coordinate Docker/env verification with TV6/Tâm.

The visual layout remains provisional. Apply the agreed design in its own implementation step; this README update does not change or approve the interface.
