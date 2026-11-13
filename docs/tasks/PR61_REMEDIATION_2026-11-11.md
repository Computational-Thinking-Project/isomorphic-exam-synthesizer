# PR #61 remediation evidence — 11 November 2026

Author mode, W4-MVP-01; workflow v0.1 proposed / INPUT-20261109 at
`7b7387f`. Implements the user-authorized remediation request, rather than the
attached investigation document's earlier planning-only restrictions.
No GitHub reply, thread resolution, push, approval, deployment or production
change was performed. This is author evidence, not independent reviewer acceptance.

## Version and scope

- Clean initial branch: `feat/w4-mvp-01-source-readiness`.
- Initial local and live PR HEAD: `d10b05eab7c7e2884c4c3eb5b75a401251b72f26`.
- Live PR metadata reported base `294c69a1a085ac6487d65b633e06a2f1112e2046`;
  the freshly fetched `origin/dev` was actually
  `21887c12eeac733f091da12f3516501e1f25ef93` (merged PR #54).
- Merge base before synchronization: `294c69a1a085ac6487d65b633e06a2f1112e2046`.
- Backup: `backup/pr61-pre-remediation-20261111` at the initial HEAD.
- Base synchronization commit: `89e9219`. This local merge incorporates dev;
  it is not a merge of PR #61 into dev. Conflicts in `schemas.py` retain both
  strict ordering DTOs and all upstream snapshot DTOs/exports. Changelog retains
  the W4 decision and the complete current dev history. Its diff against dev is
  now 17 added lines, rather than whole-file line-ending churn.
- Final SHA: use the commit containing this report (`git log -1 --format=%H`).
  No self-referential SHA is embedded in this file.

## Finding / task mapping

| ID / task | Change or existing fix | Verification and remaining boundary |
|---|---|---|
| F01 / F01-01,02 | Existing `d10b05e` StrictBool, required fields and forbidden extras retained. Added alias missing/extra/root-array/null cases, authentication/ownership checks and hidden-alias OpenAPI check in `backend/tests/api/test_sessions.py`. | 93 preferences cases pass; invalid requests make no mutation RPC, all four real boolean combinations remain accepted. Author claimed_fixed; reviewer has not verified. |
| F02 / F02-01,02 | Existing complete-receipt guard and established 422/423/404/403/503 mappings retained. Malformed receipt matrix now covers both routes. SQL test asserts the exact four-field receipt against a separate persisted-state read. | API malformed receipts return 503; valid receipts return exact 200; no success reconstructed from request. SQL receipt check is not executed because DB provisioning is blocked. A 503 does not prove rollback; reload before retry. |
| BASE-01 | Merge current dev, preserving PR54 snapshot models, service, router and migration 018. | 249 API tests pass including snapshot API. Base is now an ancestor locally; remote PR remains unchanged until publication. |
| MIG-01 | Baseline/readiness loops now include 018; W4-only asyncpg fixture adds 017/018, leaving historical W2 fixture behavior intact. Baseline checks snapshot function identity before/after 019 and replay. New guard cases cover snapshot reads after 019/replay and preference updates waiting for a committed approval fence. | Baseline/readiness each fail in Docker setup, 0 tests executed. 66 config guard cases skip without isolated DB provisioning. Fresh/populated/replay, ACL, rollback and concurrency acceptance remain blocked, not passed. |
| RPC-01 | SQL signature preserved; no aliases or overloads introduced. | Static producer/consumer audit confirms `p_n_versions` and `p_expected_snapshot` (jsonb). Isolated PostgreSQL describe/named-call and live PostgREST proof remain pending. |
| CONTRACT-01 / Q01 | Recorded the existing PR30 `/config` route and unresolved W4 adoption under `I-W4MVP01-BE2-01`; no PR30/FE files changed. | Owner schema/default/mode/receipt signoff, consumer acceptance and integration are still blocked. |
| DOC-01 | Correct 019 historical heading, distinguish historical ON/ON/client modes from current rules, explain receipt failures, update migration README and preserve upstream changelog. | Incremental diff check passes. Entire PR still has inherited whitespace noted below. Corrected PR body/replies are prepared below, not posted. |
| VERIFY-01 / HANDOFF-01 | API regressions, lint, types and current remote check inventory executed; this report provides handoff evidence. | Final local commit requires publication and full applicable CI; GitHub review threads remain unresolved. |

Review source: [F01](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#discussion_r4537242914),
[F02](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#discussion_r4537242921),
review `5857931153` requested changes on `b327899`. Both live threads were open
and outdated at inspection; outdated does not mean resolved.

## Changes by file

- `backend/tests/api/test_sessions.py`: F01/F02 alias parity, root validation,
  auth/ownership and OpenAPI coverage. No new product guard implementation.
- `backend/tests/migrations/test_w4_baseline_chain.py`: 002–018 chain,
  snapshot-function preservation, accurate test names and unused-import cleanup.
- `backend/tests/migrations/test_w4_source_readiness_config.py`: include 018.
- `backend/tests/migrations/test_generation_w2.py`: 017/018 only for W4 fixture.
- `backend/tests/migrations/test_w4_config_guards.py`: accurate precursor comment,
  exact SQL receipt, snapshot/replay and parent-lock/approval-fence regressions.
- `backend/tests/migrations/README.md`: current migration order, opt-in limits.
- `docs/api/generation-config-endpoint.md`: current versus historical contract,
  PR30 route/dependency and PATCH receipt/reload policy.
- `backend/app/models/schemas.py`, `docs/change_log.md`: base conflict resolution
  preserving both branches' behavior and history. Other files brought by the
  dev merge are unchanged upstream content, not separately edited workstreams.

No migration SQL, signature, grant, business default, worker or frontend behavior
was changed by this remediation delta.

## Executed checks

Environment: Windows, local Python 3.14.8, pytest 9.1.1, Ruff 0.17.1,
mypy 2.4.1, asyncpg 0.32.0, Docker server 29.8.2. CI uses Python 3.11;
this local environment does not replace that CI check. API tests use dependency
overrides/mocks, not live Supabase or PostgREST. Deprecation warnings: 52.
Commands below run at repository root unless stated otherwise.

| Command | Actual result |
|---|---|
| `python -m pytest backend/tests/api/test_sessions.py -q -k update_ordering_preferences` | 93 passed, 29 deselected |
| `python -m pytest backend/tests/api/test_sessions.py backend/tests/api/test_ingest.py backend/tests/api/test_confirm_source.py backend/tests/api/test_review_snapshot.py -q` | 249 passed |
| `python -m ruff check backend/app scripts/blueprint` | Passed |
| Ruff over the five changed Python test files | Passed after import cleanup |
| `python -m mypy backend/app --ignore-missing-imports` | Passed, 91 source files |
| `RUN_POSTGRES_MIGRATION_TESTS=1 PYTHONPATH=backend PYTHONUTF8=1 python -m unittest discover -s backend/tests/migrations -p test_w4_baseline_chain.py -v` | ERROR in setUpClass: Docker run timeout 60s; 0 executed |
| Same opt-ins, `python -m unittest discover -s backend/tests/migrations -p test_w4_source_readiness_config.py -v` | ERROR in setUpClass: Docker run timeout 60s; 0 executed |
| `python -m pytest backend/tests/migrations/test_w4_config_guards.py -q` | 66 skipped: isolated TASK-207 fixture opt-in/provisioning unavailable; not a pass |
| `git diff --check` | Incremental remediation diff clean |
| `git diff --check origin/dev` | Inherited whitespace in unchanged 019 EOF and historical implementation-plan Markdown. Not represented as a clean entire-PR check. |

Do not sum the focused 93 cases into 249: they are a subset. Initial verification
of the existing preferences suite passed 57 cases before adding the new cases.

The guard fixture requires **`RUN_TASK207_REAL_DB_TESTS=1` plus
`TASK207_TEST_DSN`** pointing to a newly created loopback
`task207_cluster_*` database, not just `RUN_POSTGRES_MIGRATION_TESTS=1`.
See the disposable provisioning recipe in `backend/tests/migrations/README.md`
and substitute the W4 guard test file. The two unittest suites create their own
network-none PostgreSQL 15 containers. No shared/external DSN was used here.

Docker reads succeeded but mutations/start stalled. Disposable PostgreSQL 15/17
probes could not start. Test cleanup ran; a separate backend image probe
`6613d3355906` (`intelligent_golick`) remained in Created state when its cleanup
also timed out. It never ran; retry removal when local Docker works. Existing
application containers were not started, stopped or modified.

## CI and readiness

Remote `d10b05e` check-runs API reports CodeQL and Analyze (actions), both success.
[Observed run](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/43035425671)
is a dynamic CodeQL run, not evidence that the required backend/frontend/Docker
pipeline ran on this remediation. No full final-commit CI evidence is available
for an unpublished local commit. No required check was disabled or bypassed.

F01/F02 are author-tested and ready for focused independent verification.
The combined PR is **not merge-ready / not fully Locally Verified**: isolated
018→019 proof and applicable final-SHA CI remain open. It is not Integration
Verified or Deployment Ready. Supabase Auth/PostgREST, FE2/worker/SSE/Gemini,
deployed ledger, schema drift reconciliation, backup/restore and G0 remain
separate owner/environment gates; none was invented or implicitly accepted.

## I-W4MVP01-BE2-01 — partial handoff, not accepted

PR30 remains open at `66ad00c5634865ff46c9c82db4edbedae5ec1c83`.
Read actual router/model/repository files at that SHA. The observed route is
`POST /api/sessions/{session_id}/config`; no alias decision is implied.

| Contract item | SQL 019 producer | Observed PR30 consumer / missing handoff |
|---|---|---|
| RPC identity | `save_generation_config(uuid,integer,jsonb,jsonb,jsonb)` | Matches identity; keep it |
| Named args | `p_session_id`, `p_n_versions`, `p_active_variation_modes`, `p_ordering_preferences`, `p_expected_snapshot` | Names match; snapshot is JSONB, not text |
| Modes | Exact neutral `[]`, then server derives aliases/dimensions | Client-driven mode list and request-echo receipt comparison still conflict |
| Default preferences | OFF/OFF, strict two JSON booleans | PR30 defaults ON/ON and allows omitted preference fields |
| Readiness | Confirmed current canonical evidence and manifest required | PR30 retains NO_CONFIRMATION legacy preflight |
| Receipt | Persisted derived modes and dimensions | PR30 compares to requested modes/dimensions; needs owner adaptation |
| Error policy | PATCH malformed receipt 503, state reload | Keep POST timeout/uncertain-outcome 504 policy distinct |

Repository search found no alternative parameter names in backend/frontend/docs.
`/configuration` remains in historical `docs/tasks/TASK-305.md:96`; it is not
proof of a current route and was left as historical task scope. No compatibility
alias was added. BE2/DB/FE2 must supply a single approved schema/JSON fixture,
receipt validation rule, route/default policy and consumer acknowledgment.
Acceptance state and ETA remain TBD; no external message was sent.

## Prepared external handoff — not posted

Suggested PR description replacement (fill final SHA from handoff when publishing):

> W4-MVP-01 canonical readiness/configuration and pre-finalization preferences.
> Base synchronized locally with dev `21887c1`, including merged migration 018;
> migration 019 retains its signature and semantics. Existing F01 StrictBool and
> F02 fail-closed receipt fixes are retained, with alias/auth/OpenAPI regressions.
> API regression: 249 passed (93 preferences subset); Ruff/mypy passed. DB chain
> tests failed in Docker setup, and 66 guard tests skipped: 018→019 proof is pending.
> Required final-head CI is pending publication. PR30 exposes POST `/config` on
> its own branch and still needs I-W4MVP01-BE2-01 adaptation; this PR supplies PATCH
> `/ordering-preferences` with hidden `/preferences` alias. Not integrated or
> deployment-ready. Diff size must be read from the actual published diff; no
> under-300-lines claim. Independent reviewer verification remains requested.

Prepared same-thread M5 responses:

- **F01 — Author: claimed_fixed.** Existing fix `d10b05e` preserved. 93 focused
  cases pass, including strict input, both routes, invalid-body no-RPC behavior,
  ownership and all four valid combinations. Please verify on the published
  final SHA; mocked API evidence does not certify PostgREST.
- **F02 — Author: claimed_fixed.** Existing receipt guard preserved. Both route
  matrices return 503 for malformed receipts and exact 200 for valid persisted
  receipt fields; established errors preserved. SQL receipt/replay tests are
  prepared but DB execution remains blocked. A missing receipt does not prove
  rollback. Please independently verify; no thread was resolved here.

Rollback for these local changes: retain the backup ref and revert only the
remediation commits if needed. Do not automatically reverse SQL 019 or apply
`schema.sql` to a deployed database. Any infrastructure recovery/deployment is
outside this request.
