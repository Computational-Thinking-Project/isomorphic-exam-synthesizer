# Dashboard UI — TASK-103

Dashboard is connected to `/dashboard` under `ProtectedRoute`. A Supabase session enters `profile_pending`; the shared hook requests `GET /api/users/me` and opens Dashboard only after accepting a profile for the current account/login version. TV1 reported a real profile 200 response and the correct Dashboard name on 23/10/2026.

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
2. On `/login`, sign in with Google using the existing Supabase configuration. Wait for profile verification; a successful response opens Dashboard with your name. Profile errors keep access blocked and offer retry/sign-out.
3. Reload: restore the session, verify the profile again and return to Dashboard. The session list itself still uses sample data.
4. Select **Đăng xuất** on Dashboard (or on Login while profile is pending): expect the session to end. Reload should keep you signed out; opening `/dashboard` should return to `/login`.

The previous mock auth route has been removed. Do not manually set a mock user in the auth store to bypass profile verification. Use the standalone preview to inspect Dashboard UI states without a backend. Its behavior does not verify authentication or protected-route access.

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

Current documentation checkpoint, updated 23/10/2026:

- Profile verification is connected. `ProtectedRoute` requires `authenticated` and an application user; `profile_pending` cannot enter Dashboard. On 23/10 TV1 reported real profile 200/correct Dashboard name, reload restoring the session/profile, sign-out blocking Dashboard even after reload, and successful Google re-login. New-user trigger behavior, real expiry and account ownership still need verification.
- Dashboard's loader and create/open/clone callbacks still use mocks/notices. Its sign-out button now calls Supabase with local scope, handles busy/failure states and relies on App's SIGNED_OUT subscription to clear the store. The navbar displays the backend profile name and an avatar from the matching session's Google metadata, with initials for missing/failed images and a component key covering account, session version and image URL.
- On 23/10 TV1 reported the avatar flow, broken-image fallback and npm test/lint/build passed. The agent reviewed UserAvatar/DashboardRoute and diff-check; no new automated test count or real account-isolation result was provided.
- Agent verification on 22/10 reached 51 Node tests, lint/build and 17 separate controlled browser App checks with Auth/HTTP fixtures; see the [frontend setup guide](../../../README.md) for scope and limits. These are not Dashboard API or Clone Modal tests and were not rerun for this documentation-only change.
- On 21/10/2026, the author reported Docker setup/startup and manual Google sign-in, session restoration, profile-pending route protection and sign-out checks completed. Container checks passed: backend 70 tests with one Starlette deprecation warning, SymPy parser, and frontend tests/lint/build. See the frontend setup guide for scope; these results do not verify Dashboard APIs, Clone Modal, account isolation or the static Nginx build. The documentation agent did not rerun those checks.

Historical Dashboard UI verification on 17/10/2026, before the real auth changes above:

- `npm.cmd run test`: 3/3 auth-store unit tests passed; these are not automated Dashboard tests.
- Full `npm.cmd run lint`, `npm.cmd run build` and `git diff --check`: passed.
- Browser: protected route, checking state, mock sign-in, loading/list, action notices, mock sign-out and reload passed. Standalone preview empty/error/retry and return to success passed.
- Mobile 390×844: one column, no horizontal overflow. Captured console had no errors; React Router future-flag warnings remain.

The last author-provided `npm audit` report on 17/10/2026 contained 15 vulnerabilities (4 low, 5 moderate, 6 high). Audit has not passed; no dependency upgrades or `npm audit fix --force` were applied in this increment. Dependency remediation requires separate compatibility checks and review.

Remaining work: verify new-user profile creation, real expiry and account isolation for Auth, integrate TV3/Duy's session APIs and TV2/Bội Anh's Clone Modal after review, connect create/open navigation and refresh the list after cloning. Verify application data persistence/errors/ownership with the backend. Repeat Docker checks when integrating those changes; the real Auth checks do not verify session/clone APIs.

The visual layout remains provisional. Apply the agreed design in its own implementation step; this README update does not change or approve the interface.
