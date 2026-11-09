# W4-MVP-01 — schema drift and independent local verification

Current S04 implementation/results: [S04 verification](W4-MVP-01_S04_VERIFICATION.md).
Production history remains unverified; later task-owner allocation authorizes018
for local implementation and supersedes the former allocation/mapping coding block.

Later S01/S02/S03 implementation and results supersede the corresponding pending
statuses below: see [S02/S03 verification](W4-MVP-01_S02_S03_VERIFICATION.md).

Date: 2026-11-09 (Asia/Saigon). AUTHOR; workflow v0.1 proposed.
User authorization supersedes the earlier stop-all interpretation: missing
Production evidence blocks only dependent work. No Production connection is
authorized or attempted. No application behavior or numbered migration changed.

## Current Git, PR and ownership evidence

Task HEAD `65c536291b0ad23c39e3b7f0615098943117d6e3`;
refreshed dev `f104fae6188310b386b9e359c8f72d49c5db43bf`.
Task is ahead by one documentation commit, behind by zero. Existing untracked
S00 evidence was preserved. No reset, rebase, commit, push, PR creation or merge.

| PR | Refreshed head | Observed state / ownership |
|---|---|---|
| #30 | `b6b642225b45e2744fda8826ebc70c8db0a3850e` | Open Draft; CHANGES_REQUESTED; validator F02 thread unresolved/outdated. Quỳnh owns config Python modules, generation and worker; shared main.py/changelog require coordination. |
| #42 | `6d3c555b935fdd65a1498920475bdafe009a6154` | Open, now non-Draft; no submitted reviews returned. Philip owns FE1 and new scripts/task204 local integration tooling. |
| #49 | `ec303a42cda7ebf9e6550a3c52856259931e6a5d` | Open; prior CHANGES_REQUESTED, four unresolved threads returned. New head is not independently approved by this task. Tâm owns finalize.py, schemas.py, finalize service/repository and associated tests. |
| #52 | `598b959c69c0f1c6362daed50fd544cb09dd73f7` | Open, unmerged; CHANGES_REQUESTED; F01 claimed fixed with unresolved/outdated thread. Owns 017 and lifecycle test module. |

Complete changed-file lists and review/thread state were refreshed using the
GitHub connector. `git fetch` refreshed dev, task and PR52 refs; `git ls-remote`
also checked W4/207 heads. FE2 remains Bội Anh's ownership. None of those owner
modules were edited; no independent approval is implied by local test results.

## Production evidence and schema drift

**USER-REPORTED**, not independently queried: project `luorfxpmvczsuvulkfcx`,
Production; public tables users, exam_sessions, exam_versions, source_questions,
question_blueprints; 22 total rows; Authentication accounts exist. No application
migration ledger was found in public/supabase_migrations, and nine important RPCs
were reported absent from public. Internal auth/realtime/storage migration tables
do not establish application history. No table contents, credentials, or users
were copied. The full nine-name RPC query was not supplied in this update.

| Area | Repository requirement | Drift / evidence limit |
|---|---|---|
| Five existing public tables | Present in baseline schema | Presence matches; columns, types, checks, indexes, defaults and RLS remain UNKNOWN. Row count is not schema evidence. |
| Stage 2 configuration | generation_configs | ABSENT per complete user-reported five-table inventory. |
| Generated questions/finalize/review | version_questions, answer_keys, review_logs, security_events | ABSENT per supplied inventory; baseline schema requires them. |
| Confirmed/canonical source | source_artifact_confirmations, source_artifact_revisions, canonical_blueprint_revisions, source_artifact_heads | ABSENT per supplied inventory; schema/006 require them. |
| Private review state | review_operations, review_attempts, review_action_receipts | ABSENT per supplied inventory; 006 creates them. |
| Frozen generation state | generation_job_snapshots, generation_target_results | ABSENT per supplied inventory; 015 creates them. |
| RPCs/triggers/ACLs | 002–016 contracts, optional candidate 017 | Reported RPC absence indicates incompatibility; exact installed definitions, grants, triggers and checksums remain UNKNOWN. |
| Ledger | Applied IDs/checksums/operator/time | Not available; cannot infer exact last migration or claim all migrations never ran. |

**Production compatibility: FAIL against required table inventory.** This is a
schema comparison, not a failed Production test or authorization to repair it.
Exact Production upgrade rehearsal remains BLOCKED without sanitized schema-only
metadata (DDL, enums, columns/defaults, constraints/indexes, RLS/policies, triggers,
functions/grants) supplied by its owner and migration-history reconciliation.
Do not infer that replaying schema.sql repairs an arbitrary old table:
`CREATE TABLE IF NOT EXISTS` does not reconcile existing columns.

## Migration dependency and allocation assessment

Local bootstrap prerequisites: PostgreSQL 15, Supabase roles anon/authenticated/
service_role, auth.users/auth.uid()/auth.role(), and storage stubs for SQL tests.
These test stubs do not provide JWT verification, GoTrue or PostgREST.

| Order | Required predecessor / affected contract |
|---|---|
| schema.sql | Auth/storage platform prerequisites; declares enums, application tables, RLS and base artifacts. It is required before 002; 002 is not a standalone database bootstrap. |
| 002 | Base session/source tables, auth/owner checks; atomic source replacement. |
| 003 | Base source/blueprint/session tables; legacy confirmation and blueprint metadata/uniqueness. |
| 004 | Base generation_configs; shared role/validation/timestamp helpers and four-argument config RPC. |
| 005 | 004 helpers and base versions/questions; job token, quota, claim/persist/finish and worker guards. |
| 006 | Base/current or compatible legacy schema; review canonical/display columns, private ledgers, locks, source artifacts and producer RPCs. Must precede finalize upgrades. |
| 007 | 006 review/canonical invariants; final approval and audit. |
| 008 | 006/007 tables and invariants; persisted shuffle and synchronized solution/key mapping. |
| 009 | Explicit forward upgrade after 006/007/008; replaces finalize authorization/writer and guards direct lifecycle mutations. |
| 010 | Empty retained historical placeholder; no DDL to execute, never renumber. |
| 011 | 006 artifacts, source/session tables and lock helpers; UUID preview revision and five-input confirmation overload. Non-replay-safe CREATE/ADD statements require controlled one-time application. |
| 012 | 006 artifacts and producer contract; replaces source readiness/mode projection. |
| 013 | Source/session lifecycle; adds source freeze trigger, including no-op/warning writes. |
| 014 | Revokes all installed legacy confirmation overloads from client/worker roles. |
| 015 | Documented after 004–014; adds snapshots/results and five-argument config RPC, renames/delegates legacy 005 job functions. |
| 016 | Explicitly after 015; result-kind-aware Original Clone and wrappers around 015 job/persistence contracts. |
| 017 candidate | PR52 explicitly after 016; adds activity/error columns, scanner/fencing/durable error and lifecycle replacements. Unmerged bytes tested only locally. |
| 018 proposal | No file in refreshed dev/task or inspected relevant PR file lists. Production allocation/history and owner reservation remain unverified. No 018 migration was written or applied. |

Fresh and populated SQL execution below proves the stated **ordered chain works**;
it does not prove every predecessor is the mathematically minimal dependency.
Historical SQL and schema.sql were not modified. Candidate017 SHA-256:
`d84880d30ff372b22ecdbc0e94efd11135869209c3695235467e7e1cf0d7ca4b`.
The earlier S00 report retains the full static Git checksum inventory.

## Local environment and executed verification

Created repository-local .venv from backend/requirements.lock, plus asyncpg0.32.0.
UV_CACHE_DIR was set to /tmp/w4-uv-cache because the default cache is read-only.
Docker29.9.2 local socket verified; image postgres:15-alpine digest
`sha256:aae6554de426ae1990f1a939ff183a0299146cf7142a6f4c379c3357af9cc2d8`.
Every SQL suite uses a newly created network-none PostgreSQL container, no exposed
ports, host mounts, external DSN, Production credentials or existing database.
Cleanup removes only containers/databases created by the test harness.

| Check | Final result | Command / scope |
|---|---|---|
| API/unit baseline | PASS: 162 passed, 0 failed, 0 skipped; 8 warnings | pytest test_confirm_source.py, test_sessions.py, test_ownership.py, test_ingest.py, test_legacy_blueprint_helpers.py, test_mode_mapper.py |
| Source confirmation SQL | PASS: 16 tests, 0 failed, 0 skipped | unittest test_source_confirmation_revision.py; receipt/replay, ACL, stale/rollback, parent locks, source freeze and new connections |
| Readiness/mode SQL | PASS: 7 tests, 0 failed, 0 skipped | unittest test_source_supported_modes.py; pending/running/failed/ready, empty mapped modes, malformed policy and owner/anon permissions |
| HTTP/SQL integration without AI | PASS: 1 test, 0 failed, 0 skipped | unittest test_source_no_ai_integration.py; SQL-backed transport with injected auth, not real JWT/PostgREST |
| New migration rehearsal | PASS: 4 tests, 0 failed, 0 skipped | unittest test_w4_baseline_chain.py; fresh002–016, synthetic populated upgrade, both with and without candidate017 |
| New test lint | PASS | .venv/bin/ruff check backend/tests/migrations/test_w4_baseline_chain.py |

The 4 new cases verify RPC identities, owner/anon config EXECUTE, config RLS and
source-freeze trigger. Populated cases seed exactly 22 synthetic rows across the
reported five tables using **repository column definitions**, apply schema.sql
and the chain, then compare every original field (including UUIDs/timestamps)
and row cardinality. This proves that model only, not unknown Production DDL.

Actual earlier failures, not hidden: first source SQL invocation used system
Python without google-genai and produced 16 setup errors; rerun under .venv
passed. Initial new tests used a three-argument scanner signature and produced
two assertion failures; inspected PR52's actual four-argument identity and fixed
the test. The unchanged SQL passed all four cases on rerun. No assertion was
weakened to accept a different RPC or missing object.

Logs: /tmp/w4-evidence/{api,source-revision-venv,source-modes,source-no-ai,
baseline-chain-final}.log. These are local artifacts, not committed or CI proof.

## Reproduction (local only)

From repository root, with .venv dependencies installed and local Docker ready:

```sh
export DOCKER_HOST=unix:///var/run/docker.sock
export DOCKER_CONTEXT=default
export RUN_POSTGRES_MIGRATION_TESTS=1
.venv/bin/python -m unittest discover -s backend/tests/migrations -p test_source_confirmation_revision.py -v
.venv/bin/python -m unittest discover -s backend/tests/migrations -p test_source_supported_modes.py -v
.venv/bin/python -m unittest discover -s backend/tests/migrations -p test_source_no_ai_integration.py -v
.venv/bin/python -m unittest discover -s backend/tests/migrations -p test_w4_baseline_chain.py -v
```

The candidate tests read Git object598b959, which must exist locally from fetching
PR52; they never copy its SQL into numbered history or merge its branch.
API invocation uses SUPABASE_URL=http://127.0.0.1:54321 and two dummy test-only
keys, PYTHONPATH=backend, .venv/bin/python -m pytest with -q -p no:cacheprovider.
No real provider or Production URL is configured.

## Remaining gates and safe next work

- S00 Git/PR/ownership: PASS at the pinned observations. Production ledger and
  final migration allocation: BLOCKED; does not block independent local tests.
- S01 selected API and PostgreSQL regression fence: PASS as executed above;
  actual JWT signature/PostgREST security remains a separate unexecuted gate.
- S02 new W4 config negative contract tests: NOT RUN/not implemented in this
  baseline rehearsal. Existing chain passing does not correct NO_CONFIRMATION,
  client-controlled modes or ON/ON defaults.
- S03 scheduler removal: NOT IMPLEMENTED; no application change in this run.
- S04 numbered migration: BLOCKED by verified allocation/history and unresolved
  worker alias contract. S05/S06 depend on S04 and agreed preferences/error API.
- S07 owner adaptations/integrated SHA: BLOCKED pending Quỳnh/FE2 handoff.
- S08 W4 feature race/fresh/upgrade acceptance: NOT RUN; these baseline tests
  do not substitute for tests of the future W4 migration.
- S09 Supabase Local Auth/JWT/PostgREST/RLS assertions: NOT RUN; runtime setup
  BLOCKED. Supabase CLI3.0.0 from npm fails even for --version with EROFS creating
  /home/agent/.supabase. Retrying with an additional write-path grant did not
  overcome the read-only filesystem. CLI2.54.11 npm postinstall exited1;
  direct GitHub release download returned HTTP504. No local Supabase service
  was started, no project linked, and no two-identity security acceptance or
  combined PR integration is claimed. PostgreSQL tests above remain independent.

Supabase Local next setup: repair the CLI writable configuration directory or
provide a working supported CLI, initialize an unlinked project in a dedicated
local directory, inspect its config (local ports only, remote links absent), then
start local services. Apply only the reviewed local bootstrap/ordered manifest;
use two disposable synthetic Auth identities. Never run db reset or link this
workspace to Production. Environment repair is the immediate dependency for
that track, rather than Production credentials.

Next independent work: encode S02 negative tests against existing015 in the
isolated harness, without choosing a numbered migration; preserve strict
failure/unchanged-row assertions. Obtain worker alias/Stage3 contract decisions
and migration reservation from owners before dependent implementation. Obtain
sanitized schema-only Production metadata through its owner for an exact local
upgrade model; do not copy real rows or access Production from this task.
