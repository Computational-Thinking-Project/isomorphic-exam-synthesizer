# Dashboard UI — TASK-103

Dashboard is connected to `/dashboard` under `ProtectedRoute`. A Supabase session enters `profile_pending`; the shared hook requests `GET /api/users/me` and opens Dashboard only after accepting a profile for the current account/login version. TV1 reported a real profile 200 response and the correct Dashboard name on 23/10/2026.

The routed Dashboard uses the real list service with server pagination and out-of-range correction. The merged Clone Modal is connected through the real clone service; success closes it and reloads page1 even when already on page1. TV1 reported successful browser/cloud list, clone, persistence, question/blueprint copying and denial of account B cloning account A's source, as recorded below. Create/open still show notices pending agreed Stage destinations. The separate previews keep mock data. Auth PR #7 has landed in dev; the layout is provisional and TASK-103 remains incomplete.

### dev integration checkpoint — 26/10/2026

The working tree is integrating dev `bbb7c5e` into `feat/task-103-dashboard-api`, stopping before the merge commit. Conflict resolution preserves the existing real Dashboard route and its list/pagination/account guards/Clone Modal; the resolved route matches its pre-merge contents. Upstream Blueprint tools, configuration and health changes are retained. Agent checks after resolution: **113/113 Node tests, lint and build passed**. The staged candidate differs from dev only in11 Dashboard/setup/docs files; Auth/App/shared-client code matches dev. Browser/cloud checks below remain the author-reported24/10 evidence; no new browser/cloud/Docker run is claimed. No create/detail service or Stage route is added in this integration step.

## Run and check

### Supabase prerequisite for TASK-103 list/clone

On 24/10/2026 TV1 reported `users` exists, but `exam_sessions`, `source_questions`, `question_blueprints`, `session_status` and `question_status` are absent. A real list request returned 500; sanitized backend diagnostics identified PGRST205 for `public.exam_sessions`.

For this exact preflight, [setup_dashboard_sessions.sql](../../../../backend/scripts/setup_dashboard_sessions.sql) creates the three list/clone tables, `session_status`, team ownership policies and explicit authenticated grants. **TV1 reported successful execution on 24/10/2026**, followed by a real authenticated `GET /api/sessions?page=1&page_size=20` returning 200 with `items: []`, `total: 0`, `page: 1`, `page_size: 20`. Subsequent author-reported live clone and ownership checks are recorded below. Do not rerun the script or the full team schema over this setup. The script is intended to run once as postgres without recreating Auth or storage, and fails rather than replacing an existing object.

The grants cover SELECT/INSERT on the three tables and DELETE on the session parent for clone-error cleanup. UPDATE is not granted here; later Stage/editing migrations must agree their required grants with Duy. `question_status` is not used by these three tables, and session detail additionally reads `exam_versions`; those belong to subsequent schema setup. Metadata checks after the script do not prove real list/clone or account isolation. See [DEC-TV1-003](../../../../docs/change_log.md#dec-tv1-003-bổ-sung-db-cho-dashboard-listclone).

### Frontend

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
3. Reload: restore the session, verify the profile again and return to Dashboard. Verify the routed page requests `/api/sessions?page=1&page_size=20`; an empty real account should show the empty state and total 0, without sample cards.
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
| DashboardPage | `loadSessions({ signal }): Promise<Session[]>`, `onCreate()`, `onOpen(session)`, `onClone(session)` |
| DashboardSessionCard | `session`, `onOpen(session)`, `onClone(session)` |

TV1 owns the page/card and `DashboardRoute.jsx`, which supplies a stable real-list adapter and create/open notices. The adapter returns `items` to Page and retains `total/page/page_size`; Page passes an AbortSignal and aborts on cleanup while retaining its active-result guard. Route resets account-specific state with a user ID/session-version key, which stays stable on same-account token refresh. Preview loaders may ignore the optional argument. TV2 owns the merged Clone Modal; TV1 connects the selected session and real clone function in Route.

The routed `onClone(session)` now opens TV2's merged Modal. Its explicit `cloneFn` is [cloneSessionForDashboard](cloneSessionForDashboard.js), which calls the shared sessions service and returns the direct new-session object. It translates API/Auth errors without reading backend detail into user messages or adding retries. Canceled/stale requests retain cancellation semantics. Timeout/network/5xx messages advise reloading the page to check whether a copy exists before resubmission. Route keys Page by page/refresh counter; the account wrapper also clears modal selection on account/login-version changes. Destination navigation is still pending.

`dashboardMock.js` supplies `listDashboardSessions({ scenario })`, where scenario is success, empty or error. Session fields are `id`, `title`, `subject`, `created_at`, `status`; these are illustrative fixtures, not the final TV3 API contract. Approved/exported fixtures show a view label; destination routes are decided by the parent after the status contract is agreed.

## Verification and remaining work

### Live browser and cloud verification — 24/10/2026

Code checkpoint: `6c16807` on `feat/task-103-dashboard-api`, including error-adapter commit `67983d9`. The following results were reported by TV1 while using the real application, backend and shared Supabase; they are not additional automated tests or reviewer approval. The agent received the sanitized verifier output but did not operate the real browser/cloud.

| Scope | Author-reported evidence |
|---|---|
| Empty/list state | GET list200, empty state and disabled pagination; test sessions subsequently appear with correct totals and survive reload. |
| Modal in browser | Correct source/default title, input focus, Tab/Shift+Tab containment, Esc/focus return, blank/whitespace rejection, Cancel/reopen reset; these actions create no copies. |
| Successful clone | One POST201, new session ID/statusdraft, source retained, modal closes and list automatically reloads; F5 preserves the copy. |
| Network failure and explicit retry | Offline attempt preserves modal/title, unlocks controls and does not log out or auto-resubmit; after restoring connectivity, explicit retry succeeds. |
| Account separation | B gets list200 without A's sessions. B's direct clone request using A's existing source ID returns404 and creates no session; returning to A preserves its three sessions at that checkpoint. This is a selected B→A ownership check, not every endpoint or direction. |
| Copy with content | After adding one technical sample question and one unconfirmed blueprint to A's original source, UI clone returns201; list and F5 show four sessions. A read-only verifier returns `passed: true`: each side has one question/blueprint; fixture content, copied content, subject/grade, new IDs, draft status and new foreign-key links all match expectations. |

Only count/boolean results were recorded; no real IDs, tokens or private exam data are included. The fixture is a copy test, not an AI/teacher-approved blueprint or evidence of generation quality. Test preparation used a bounded SQL transaction; that administrator action itself does not prove user permissions. The actual clone and subsequent reads used the logged-in account.

Four test sessions remain for review; the two copies created before adding content remain empty. No cleanup or UPDATE grant was added. A stale Docker frontend initially displayed the old “waiting for Clone Modal” notice; after updating the running build, the browser checks passed. Keep `scripts/dev.ps1 up` watching source, or rebuild before checking new changes.

Remaining: agreed Stage destinations/creation responsibility, create/open integration and its checks, PR review/merge with the correct Auth base. Multi-page cloud data, other ownership directions/endpoints, live clone-error cleanup, timeout/5xx and account-switch-during-request behavior were not tested on cloud; relevant controlled tests below do not replace that coverage.

The following sections are historical checkpoints; the live results above supersede their earlier “unverified” statements for the explicitly tested cases. No tests/lint/build were rerun for this documentation-only update.

### Route–Modal–API checkpoint — 24/10/2026

- Baseline after merging PR6 is `e7530a4`; TV1 reported104 tests passed. Agent reviewed Route wiring, added [the error adapter](cloneSessionForDashboard.js) and [9 adapter tests](cloneSessionForDashboard.test.js). Full frontend **113/113 Node tests**, lint/build and diff-check passed, with no dependency/client/store/backend changes.
- A separate local **18/18 integration suite** passed using actual ReactDOM lifecycle/StrictMode and the real Route/Page/Card/Modal/ProtectedRoute/service/API/store, with a minimal DOM mock and SDK/HTTP fixtures. Cases cover success/page1 refresh/page2→1, busy/double submit, HTTP/network/timeout errors and retry, successful clone followed by list-load failure, account changes with late success/error, same-account refresh, logout and terminal401. This local review suite is separate from the113 Node count and is not part of CI.
- These checks do not verify native browser keyboard/focus, real cloud clone/persistence or sessions A/B ownership. No seed data or new Stage routes were created. Older browser17 and Docker209/85 results below belong to earlier checkpoints, not this integration run.

### After syncing dev — 24/10/2026

- Dashboard branch merged dev `478cc55` at `ca88c07`; session cards now cover all ten schema statuses and use an own-property check for the unknown-status fallback. Auth/API clients and the pending modal/navigation boundaries remain the same.
- TV1 reported **85 frontend Node tests**, host lint/build passed after the merge. TV1 then ran the shared Docker test helper and reported **209 backend tests passed, one StarletteDeprecationWarning, 14.22s**, and **85 frontend tests passed**. These are author-run results; the documentation agent did not rerun Docker. The warning concerns deprecated `httpx` use in Starlette's TestClient; dependency changes are outside this increment.
- The separate Dashboard browser suite remains **17/17 passed** with fixture Auth/HTTP, confirmed from its report. It was run before the labels/dev-sync commits and was not rerun here; it is not part of either Node or pytest count. Real empty-list/UI checks are author-reported. Populated cloud pages, real session ownership A/B, real clone, Clone Modal and Stage navigation remain unverified or unintegrated.

### Pagination code review — 24/10/2026

- Route now requests the selected `page`, computes page count from server metadata, disables Previous/Next until matching metadata is ready and at the boundaries, and redirects an out-of-range page to the last valid page (minimum 1). Page is keyed by page number to clear old cards and abort the prior load; the account wrapper resets pagination on account/login-version changes while preserving it across same-account token refresh.
- TV1 reported the preceding first-page checks passed and the pagination implementation had no errors. Agent reviewed the source and reran **72/72 Node tests**, lint/build and diff-check successfully. Those tests do not execute the React pagination UI.
- TV1 manually ran the separate local browser suite after resolving its server-start issue and reported all cases passed. Agent read the generated report and confirmed **17/17 passed**, with no captured runtime errors/unhandled rejections. It imports the actual Route/Page/ProtectedRoute/service/client/store and replaces Auth/HTTP with fixtures: empty state, 41 items across three pages, loading/boundaries, stable loader, 403/429/500/network errors and retry, bad envelope, out-of-range correction to populated/empty page 1, A→B late responses/state reset, same-account refresh and logout while loading. This is separate from the 72 Node tests and does not verify cloud writes, real populated pages, session RLS or clone. The browser automation permission rejection was not bypassed; the author opened the fixture page manually.

### First-page UI code review — 24/10/2026

- Agent checked Page/Route changes at Dashboard baseline `ae79482`: real first-page adapter, stable callback, retained metadata, 403/429/generic messages, account-keyed state reset and cancellation on cleanup. Added `{ cause }` to the wrapped error to satisfy ESLint `preserve-caught-error`; no other source changes by the agent in this review.
- **72/72 existing Node tests**, lint/build and diff-check passed. These Node tests cover Auth/API/services, not the new React UI behavior. No browser/cloud requests, logout/account-switch interaction or controlled UI race tests were performed in this review. Pagination controls, navigation and modal remain pending.

### Clone service checkpoint — 24/10/2026

- [sessions.js](../../services/sessions.js) now also provides `cloneSession(sessionId, title)` through the shared API client: POST `/api/sessions/{id}/clone` with `{ new_title }`, returning the direct session object. It validates the ID/title and requires a new session ID with status `draft`. The shared client supplies the token and handles 401 refresh/retry at most once; the service adds no retries on network errors, timeouts or 5xx, which could create duplicate copies.
- Agent reviewed TV1's implementation and added 9 clone cases to [sessions.test.js](../../services/sessions.test.js): request/body/token/201, Unicode title limit, invalid input/response, HTTP/network/timeout failures without resubmission, stale responses after account change/logout, and shared 401 retry success/exhaustion. Frontend **72/72 Node tests**, lint/build and diff-check passed. Tests use the actual service/client/store with Auth/HTTP fixtures, without cloud writes or new dependencies.
- Real clone and its database effects remain unverified because the real account's list is empty. Ignoring a response after logout/account change does not cancel a write already performed by the backend. Dashboard list/pagination, Clone Modal and post-clone refresh are still pending.

### List service checkpoint — 24/10/2026

- [sessions.js](../../services/sessions.js) provides `listSessions({ page = 1, pageSize = 20, signal } = {})` through the shared API client, returning the full `{ items, total, page, page_size }` envelope. Invalid input/response throws; HTTP errors remain available to the caller. The page still needs an adapter because its loader expects an array.
- TV1 reported the real service call returning the valid empty first page after DB setup. Clone, populated real pages, session ownership A/B and routed UI remain unverified.
- Agent added 12 cases in [sessions.test.js](../../services/sessions.test.js) using the actual service/client/store with Auth/HTTP fixtures: query/token/envelope, empty/out-of-range pages, invalid data/input, HTTP/network errors without extra retries/logout, cancellation, stale results after logout/account change, and same-account refresh. Frontend **63/63 Node tests**, lint/build and diff-check passed. These are not browser/cloud tests; clone is not implemented in this service yet.

Historical Auth documentation checkpoint — 23/10/2026 (Dashboard list status superseded above):

- Profile verification is connected. `ProtectedRoute` requires `authenticated` and an application user; `profile_pending` cannot enter Dashboard. On 23/10 TV1 reported real profile 200/correct Dashboard name, reload restoring the session/profile, sign-out blocking Dashboard even after reload, and successful Google re-login. TV1 also confirmed a previously absent Google B account automatically received a profile matching its Auth ID, reload retained B and switching back displayed A correctly. Unfiltered profile SELECT probes under A's and B's JWT each succeeded and returned exactly the current user's single row. This verifies profile read isolation for these accounts; real expiry and write/session/storage permissions remain unverified.
- Dashboard's loader and create/open/clone callbacks still use mocks/notices. Its sign-out button now calls Supabase with local scope, handles busy/failure states and relies on App's SIGNED_OUT subscription to clear the store. The navbar displays the backend profile name and an avatar from the matching session's Google metadata, with initials for missing/failed images and a component key covering account, session version and image URL.
- On 23/10 TV1 reported the avatar flow, broken-image fallback and npm test/lint/build passed. The agent reviewed UserAvatar/DashboardRoute and diff-check; no new automated test count was provided. The separate profile read-isolation result is recorded above.
- TV1 subsequently reported successful real `refreshSessionOnce()` followed by `getMyProfile()`, matching the session account; Dashboard remained accessible with the correct identity and survived reload. This tests proactive refresh, not natural token expiry or failed refresh on cloud.
- Agent verification on 22/10 reached 51 Node tests, lint/build and 17 separate controlled browser App checks with Auth/HTTP fixtures; see the [frontend setup guide](../../../README.md) for scope and limits. These are not Dashboard API or Clone Modal tests and were not rerun for this documentation-only change.
- On 21/10/2026, the author reported Docker setup/startup and manual Google sign-in, session restoration, profile-pending route protection and sign-out checks completed. Container checks passed: backend 70 tests with one Starlette deprecation warning, SymPy parser, and frontend tests/lint/build. See the frontend setup guide for scope; these results do not verify Dashboard APIs, Clone Modal, account isolation or the static Nginx build. The documentation agent did not rerun those checks.

Historical Dashboard UI verification on 17/10/2026, before the real auth changes above:

- `npm.cmd run test`: 3/3 auth-store unit tests passed; these are not automated Dashboard tests.
- Full `npm.cmd run lint`, `npm.cmd run build` and `git diff --check`: passed.
- Browser: protected route, checking state, mock sign-in, loading/list, action notices, mock sign-out and reload passed. Standalone preview empty/error/retry and return to success passed.
- Mobile 390×844: one column, no horizontal overflow. Captured console had no errors; React Router future-flag warnings remain.

The last author-provided `npm audit` report on 17/10/2026 contained 15 vulnerabilities (4 low, 5 moderate, 6 high). Audit has not passed; no dependency upgrades or `npm audit fix --force` were applied in this increment. Dependency remediation requires separate compatibility checks and review.

Remaining work: save the resolved dev merge, check its Dashboard-only diff and CI, then connect agreed create/open Stage routes and creation ownership. Auth PR #7 is already squash merged into dev; natural expiry/failed refresh on cloud and the static Nginx build remain unverified. Live coverage is limited to the cases in the latest table; multi-page cloud pagination and untested permission/error scenarios remain outside that evidence. Repeat checks when later integration changes justify it.

The visual layout remains provisional. Apply the agreed design in its own implementation step; this README update does not change or approve the interface.
