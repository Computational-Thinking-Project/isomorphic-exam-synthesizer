# Dashboard UI — TASK-103

Dashboard is connected to `/dashboard` under `ProtectedRoute`, using the shared mock auth store and mock session data. Google/Supabase authentication, backend sessions and the Clone Modal are not integrated yet. The current layout is provisional; this increment does not complete TASK-103.

## Run and check

From the frontend directory:

```powershell
npm.cmd ci
npm.cmd run test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

Use the address printed by Vite; the configured port is 3000, but Vite may choose another available port.

1. Open `/dashboard` without a session: expect a redirect to `/login`.
2. Open `/auth-preview`, select **Dùng phiên mẫu**, then **Mở Dashboard**: expect loading followed by three session cards.
3. Click create, continue/view or clone: expect a notice identifying the action/session. These actions do not yet create sessions, navigate to editing screens or open a modal.
4. Select **Đăng xuất mẫu** or reload Dashboard: expect `/login`. Mock sessions are held only in memory and do not survive reload.

The auth preview and mock sign-out control are development-only. The production build includes Dashboard through App, but real sign-in/session restoration is not implemented, so there is no production login path into Dashboard yet.

## Standalone state preview

From the frontend directory, run `npm.cmd run dev` and open `/dashboard-preview.html` on the address printed by Vite. The selector covers success, empty and error scenarios. Retry in the fixed error scenario returns an error again; selecting success restores the list.

The HTML entry is `frontend/dashboard-preview.html`; the React entry is `src/features/dashboard/dashboard-preview.jsx`. This separate preview renders only in development and is not included in the default production build. The routed Dashboard is included in that build.

## Props and ownership

| Component | Props |
|---|---|
| DashboardPage | `loadSessions(): Promise<Session[]>`, `onCreate()`, `onOpen(session)`, `onClone(session)` |
| DashboardSessionCard | `session`, `onOpen(session)`, `onClone(session)` |

TV1 owns the page/card and `DashboardRoute.jsx`, which supplies the stable mock loader and callback notices. TV2 receives the selected session through `onClone(session)` and implements the Clone Modal; TV1 will integrate it later. These callback names are the handoff; they do not define the final backend request/response or modal completion contract.

`dashboardMock.js` supplies `listDashboardSessions({ scenario })`, where scenario is success, empty or error. Session fields are `id`, `title`, `subject`, `created_at`, `status`; these are illustrative fixtures, not the final TV3 API contract. Approved/exported fixtures show a view label; destination routes are decided by the parent after the status contract is agreed.

## Verification and remaining work

Verified on 17/10/2026 after receiving auth PR #2 and integrating the route:

- `npm.cmd run test`: 3/3 auth-store unit tests passed; these are not automated Dashboard tests.
- Full `npm.cmd run lint`, `npm.cmd run build` and `git diff --check`: passed.
- Browser: protected route, checking state, mock sign-in, loading/list, action notices, mock sign-out and reload passed. Standalone preview empty/error/retry and return to success passed.
- Mobile 390×844: one column, no horizontal overflow. Captured console had no errors; React Router future-flag warnings remain.

The last author-provided `npm audit` report on 17/10/2026 contained 15 vulnerabilities (4 low, 5 moderate, 6 high). Audit has not passed; no dependency upgrades or `npm audit fix --force` were applied in this increment. Dependency remediation requires separate compatibility checks and review.

Remaining work: real Google/Supabase auth and persistent sessions (TASK-101 integration), TV3's session list/status contract and API, real create/open navigation, and TV2's Clone Modal. Visual layout/style still needs agreement with TV2 against the group's design direction.
