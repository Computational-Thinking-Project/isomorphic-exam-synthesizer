# TASK-302 PostgreSQL schema and RPC tests

## W4-MVP-07 export snapshot

`test_export_snapshot_pg.py` requires backend Python dependencies, Docker CLI
and `postgres:15-alpine`, with `RUN_POSTGRES_MIGRATION_TESTS=1`. From the repo root:

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
$env:PYTHONPATH = "$PWD/backend;$PWD/backend/tests/migrations"
python -m unittest discover -s backend/tests/migrations -p test_export_snapshot_pg.py -v
```

Set `DOCKER_BIN` to the absolute CLI path if outside PATH. The suite owns a
random disposable PostgreSQL15 container (`--network none`, no published ports).
Each case creates a fresh DB, installs schema and migrations002–018, supplies
Supabase base grants **before** migrations narrow them, seeds a historical
reviewed 3×2 exam, then executes actual shuffle/approval RPCs. No cloud keys,
shared DB, Gemini or complete W2 producer are involved.

The SQL reader replaces HTTP transport only: separate connections run as
`authenticated` with owner/foreign auth.uid GUCs and real RLS. Cases cover all
six Golden OFF/OFF slots, non-contiguous source labels (3,8,9) through actual
shuffle/approval/export and rejection of a mismatched canonical key, cross-user concealment, locked content/metadata,
Review/shuffle and generation writer fencing (005/016), invalid persisted title,
concurrent reads/rejected writes and uncommitted approval. The unchanged Golden
fixture comes from PR49 at `0f760067d9ba343401b46f0c41839065633bc48a`.
Its illustrative seed strings are not used as persisted receipts: actual
deterministic shuffle receipts are computed. Owner acceptance remains separate.

The actual preview repository comparison explicitly skips until
`FinalizeRepository.fetch_preview_snapshot` is available. Run it again after
task05 integration; a skip is not preview evidence. An isolated local check
loaded PR49's pinned repository separately and compared its projection on the
same DB before approval with export after approval. This does not verify HTTP,
JWT/PostgREST deployment. Pure/stub suite: `python -m pytest backend/tests/exporter -q`
with `backend` on `PYTHONPATH`. The PostgreSQL adapter suite needs backend
dependencies, unlike stdlib-only schema tests; it does not certify PDF/Storage.

### TASK-305 async integration fixtures

The two `tests/services/test_*_real_db_integration.py` modules require `asyncpg`
and opt in with `RUN_TASK305_REAL_DB_TESTS=1` and
`EXAM_TEST_DB_DESTRUCTIVE=1`. Each module starts its own
`postgres:15-alpine` container with a randomly named database and loopback-only
port, verifies the connected database name, and removes that container in fixture
cleanup. `PG_TEST_DSN` is not used. Without the opt-in, Docker CLI, or `asyncpg`,
these tests skip and are not evidence of database verification. This isolation
does not apply to other tests or demonstrate deployed Supabase behavior.

The TASK-305 shuffle writer test, `test_shuffle_writer_db.py`, additionally
requires `asyncpg` and an explicitly isolated PostgreSQL 15 container with no
external network. Provision the disposable `task305_isolated` database using
`task305_shuffle_bootstrap.sql`, `backend/scripts/schema.sql`, migrations 006,
007 and 008 in order, then `task305_shuffle_smoke.sql`. Run the test in the
same container network namespace with `RUN_TASK305_WRITER_DB_TEST=1` and
`TASK305_WRITER_TEST_DSN` set to the test database on `127.0.0.1`. The test
performs destructive setup in that database; never point it at a shared service.

### PR33 security remediation (migration009)

The current application additionally requires
`009_finalize_security_boundary.sql`. For this test fixture, provision bootstrap,
schema,006,007,008 and the existing shuffle smoke seed first, then apply009 last.
The smoke seed intentionally exercises the historical008 interface; current tests
exercise the service-only writer introduced by009. Production uses no test seed.

Run `test_finalize_security_boundary.py` alongside the two writer modules below
with the same explicit disposable opt-in. It adds real authenticated/service-role
DML and RLS tests, wrong-display-key approval cases, forged-role/body attempts,
and fresh/legacy forward-upgrade rollback/replay. Upgrade cases create and drop
only their own random `task305_test_upgrade_<uuid>` database in the verified local
cluster. Test fixtures emulate broad Supabase table/column grants **before**009;
they do not infer deployed privileges or relax production guards.

`run_task305_real_db_suites.py` now applies006–009 in its random databases. The
writer fixtures explicitly switch only their test connection's principal to model
the trusted backend; raw client-denial cases do not use that helper. Local SQL
execution results are separate from opt-in skips in ordinary CI.

See [Finalize RPC contract](../../../docs/api/finalize-rpc-contract.md) for the
owner-reader/service-writer split and coordinated rollout requirement. Run these
DB suites sequentially without pytest-xdist because fault triggers are shared
test fixtures inside the disposable database.

`test_shuffle_writer_adversarial.py` uses the same explicit writer opt-in and
loopback-only `task305_isolated` DSN. It creates a separate 2 x 3 session per
case, checks full-row rollback (including history/timestamps), real PostgreSQL
ACLs, malformed/live/stale input, Unicode solution parity, repair/no-op retries,
lost receipts, silent-trigger faults and `pg_blocking_pids` interleavings.
Run it together with `test_shuffle_writer_db.py`, sequentially: its fault
triggers are cluster-test fixtures and must not run against shared data or in
parallel workers.

For a Python runner sharing the network namespace of that **new disposable,
network-none** PostgreSQL container, without a Docker CLI inside the runner:

```sh
# Working directory: backend; asyncpg is required (verified with 0.32.0).
RUN_TASK305_WRITER_DB_TEST=1 \
TASK305_WRITER_TEST_DSN=postgresql://postgres@127.0.0.1/task305_isolated \
python -m pytest tests/migrations/test_shuffle_writer_db.py \
  tests/migrations/test_shuffle_writer_adversarial.py -q -p no:cacheprovider

RUN_TASK305_REAL_DB_TESTS=1 EXAM_TEST_DB_DESTRUCTIVE=1 \
python tests/migrations/run_task305_real_db_suites.py
```

The second command replaces only the pytest fixture's Docker-launch step with
random `task305_test_<uuid>` databases in that verified local test cluster.
The existing suites and their `assert_disposable_database` guard still run
before destructive DDL. It drops only the random databases it creates. This
alternate runner does not verify the default fixture's Docker-launch path;
`test_isolated_postgres_fixture.py` separately checks that path's refusal and
cleanup guards. No external DSN or production/staging database is accepted.

These tests execute SQL against **PostgreSQL 15**, rather than mocking Supabase.
Each suite class creates a disposable container with no network, published ports, host mounts,
or real credentials, and remove it on completion (including test failures).
Docker Desktop must be running. The runner uses Python 3's standard library;
no host Python packages are required. The `postgres:15-alpine` image must already
be available locally (`docker pull postgres:15-alpine` if necessary).

From the repository root, in PowerShell:

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
# Only if docker.exe is not on PATH; adjust to your installation if different.
$env:DOCKER_BIN = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
python -m unittest discover -s backend/tests/migrations -v
```

Without `RUN_POSTGRES_MIGRATION_TESTS=1`, unittest/pytest report these tests as
**skipped**; an ordinary CI run is not evidence that PostgreSQL checks ran.

The schema suite covers populated legacy upgrade and replay, full initialization plus
migration, canonical immutability with display-only shuffle, independent new
candidate snapshots, the partial current index, both answer-key field formats,
ambiguous/missing mappings, duplicate legacy keys, and transaction rollback.
An incompatible attempt ledger (the competing 008 layout) must stop 006 without
altering receipts, existing quota, or the legacy answer-key schema. This is a
fail-closed upgrade check; conversion of an already deployed 008 needs verified
database state and a separate owner-provided transition.
`fixtures/legacy_schema.sql` snapshots the pre-TASK-302 table definitions from
dev `32d7644`; keep that fixture unchanged when updating the initialization schema.

The `auth`/`storage` bootstrap is a local test stub. These checks do **not** verify
Supabase deployment/JWT/RLS, AI calls, actual shuffle algorithms, or the Python
repository/endpoint integration. Local PostgreSQL role/ACL tests are not a deployed
Supabase authorization test.

`test_review_rpcs.py` additionally runs the actual ten review stored procedures against
independent psql connections: reservation/attempt/recovery races, quota 26–30 and
four/operation, committed grant with lost response, replay after new connection,
late worker after recovery, source-row changes, complete/revert snapshots,
missing expected slots, caller permissions, and rollback on candidate/audit/key
failures. The approval interleaving waits for `pg_blocking_pids` evidence before
committing the competing session lock; it does not rely on a sleep to establish
which transaction wins. It does not implement or certify TASK-305's own writer.

Session recovery additionally checks discovery after a restart without private
ledger SELECT or a question's regeneration UUID, DB-clock lease/no-op behavior,
worker-only authorization, session isolation, concurrent discovery/direct recovery/
late completion, audit rollback/retry, and preservation of uncertain charges.

## Pinned upstream migration chain (additional opt-in)

`test_review_migration_chain.py` reads immutable SQL blobs from these Git commits:

- 004/005: `2f6840d42c87d04f55e12d25c1bdd71c9481c652` (PR #32).
- 007: `d7a3d3f788972f06552cd21a7e7103eceb2f2a55` (PR #33).

This avoids maintaining copies of another owner's unmerged SQL. Fetch those
objects first if absent (network is needed only for that preparation):

```powershell
git fetch origin 2f6840d42c87d04f55e12d25c1bdd71c9481c652 d7a3d3f788972f06552cd21a7e7103eceb2f2a55
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
$env:RUN_UPSTREAM_MIGRATION_TESTS = '1'
python -m unittest discover -s backend/tests/migrations -v
```

Keep `DOCKER_BIN` set as above if needed. Without the second opt-in only the six
chain cases skip; with it, missing Git objects fail rather than silently selecting
a different revision. The suite runs 004/005 → local 006 → 007 on both populated
legacy and full initialization schemas, then tests chain replay, retained charged
receipts, recovery before actual 007 approval, refusal during active review, and
review locking after approval. It verifies these integration paths, not every
generation/approval input or shared-cloud rollout. It never executes `git fetch`
or accesses a remote from inside a test.

The RPC suite uses raw database source/blueprint fixtures and explicit zero-call
candidate payloads where appropriate; it does not claim those legacy rows are
AI-ready canonical documents or confirmed adapter hashes. See the source-to-AI
handoff limitation in `docs/api/review-rpc-contract.md`.

Migration 006 deliberately refuses ambiguous data. Do not delete/deduplicate
history or derive missing canonical values from shuffled display values to make
it pass. Inspect and supply verified source data before retrying.

Actor policy (confirmed by the TASK-302 owner on 2026-10-31): preserve unknown
historical actors as NULL, but require an actor for every new write. Migration
006 uses `CHECK (user_id IS NOT NULL) NOT VALID`: existing NULLs survive, including
on migration replay, while new INSERTs and UPDATEs must satisfy the check. New
backdated rows are not historical exemptions. Updating a historical NULL row also
requires a verified actor; leave it untouched if the actor remains unknown.
Do not validate the constraint or set the column NOT NULL without a verified
historical backfill. Fresh initialization uses an ordinary CHECK because there
is no existing history. The actor foreign key remains enforced. This is a
deliberate exception to the W3 blanket NOT NULL requirement; see the decision in
`docs/tasks/TASK-302.md`. These database constraints do not authenticate a caller
or replace the actor/ownership checks in the lifecycle RPCs/callers.

Actor regressions cover migration replay with historical NULLs, fresh-schema
enforcement, missing/backdated new actors, preserving known actors on UPDATE,
verified historical correction, and invalid actor foreign keys.

## Confirmed artifacts and frozen consumer handoff

Artifact SQL/tests are adapted from Duy/TASK-301 `68b375f` and final `553a0094d9a3c4ddcb30f8f008d964c9362d3c76`.
`test_source_artifacts.py` covers worker confirmation/publication, exact live-source
comparison, owner-scoped reads, invalidation/history, replay, ACL, rollback and
independent-connection confirmation/publication races. These SQL-only tests use a
detached shared AI fixture; they do not import/copy Duy's Python producer.
`test_review_artifacts.py` covers strict v1 reservations, missing/stale evidence,
canonical mapping after display shuffle, superseded permits/completion, charged
recovery, unchanged legacy receipts, content locks and publication races.

To export a receipt **emitted by the real PostgreSQL reservation RPC**, opt in:

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
$env:REVIEW_RPC_FIXTURE_DIR = 'scratch/task302-handoff'
python -m unittest discover -s backend/tests/migrations -p test_review_artifacts.py -v
Remove-Item Env:REVIEW_RPC_FIXTURE_DIR
```

`reservation.json` contains only synthetic test data. It is an ignored generated
artifact, not a manually constructed successful response or a file to commit.
Tests without the export variable do not write results into the working tree.

`check_review_consumer.py` is a separate explicit cross-PR check. Supply backend
Python dependencies and an isolated checkout of TASK-301 at `553a009` on PYTHONPATH
(the producer, strict mapper and TASK-304 adapter do not live on this branch yet):

```powershell
git worktree add --detach scratch/task301-consumer 553a0094d9a3c4ddcb30f8f008d964c9362d3c76
$env:PYTHONPATH = (Resolve-Path scratch/task301-consumer/backend).Path
python backend/tests/migrations/check_review_consumer.py scratch/task302-handoff/reservation.json backend/tests/fixtures/ai_pipeline.json
Remove-Item Env:PYTHONPATH
```

This check verifies the fixture fingerprint with the production producer, validates
the canonical schema and frozen envelope, invokes the real adapter with a fake
provider/permit and checks honest teacher-review output. Eight explicitly corrupted
copies (missing artifacts/hash, wrong binding/hash, legacy format, invalid Blueprint,
current/peer identity mismatch) must fail before another permit/dispatch. No real
Gemini/key/Supabase is used. It does not certify public HTTP/background orchestration,
provider transport, or deployment. The default suites do not discover/invoke this
cross-PR script or import moving upstream code implicitly.

### Final-head adoption and combined application check

The SQL suite also covers owner-only lookup without writes/charges, bootstrap
without 003 or legacy Blueprint rows, silent audit rollback, 420s producer claims,
claim races, read-only status, failed/expired retry and stale-worker fencing.
It upgrades the exact published `8fff9da` checkpoint twice, preserving charged
receipts and ready heads while adding nullable lease fields. That Git object must
be available when opting into the SQL tests (fetch it if using a shallow clone).
Legacy-only acceptance remains supported; regeneration requires confirmed v1.
Peer Revert does not replace a reservation's frozen peer inputs or block completion.

`lease_superseding_publication` is a trusted test setup for subsequent canonical
revision/race guards. It is not the public retry path: production claim skips a
ready head and does not regenerate an already published Blueprint.

For the separate pinned HTTP/producer check, use an isolated detached checkout of
TASK-301 `553a009` with its backend Python dependencies and Docker available.
Overlay only this branch's SQL/init schema, then run its existing opt-in tests:

```powershell
git worktree add --detach scratch/task301-integration 553a0094d9a3c4ddcb30f8f008d964c9362d3c76
Copy-Item backend/migrations/006_stage3_review_and_shuffle.sql scratch/task301-integration/backend/migrations/006_stage3_review_and_shuffle.sql
Copy-Item backend/scripts/schema.sql scratch/task301-integration/backend/scripts/schema.sql
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
$env:PYTHONPATH = (Resolve-Path scratch/task301-integration/backend).Path
python -m unittest discover -s scratch/task301-integration/backend/tests/migrations -p test_source_artifacts.py -v
Remove-Item Env:PYTHONPATH
```

Do not edit the TASK-301 feature branch or commit generated results. This executes
the pinned producer/HTTP/adapter tests against the adopted SQL, not live Gemini.
The recorded local run used a dedicated internal Docker network and a disposable
PostgreSQL service with a test-only SQL transport adapter (no Docker socket mount).
The standard runner above uses independent psql connections instead; neither
transport establishes deployed JWT verification/table-read RLS/PostgREST pooling.
Auth/table transport and gateway are injected; actual PostgreSQL executes RPCs with
their real roles/ACL. Stage-2 generation-job integration is outside this producer/
review check; the existing current candidate is seeded by the fixture.


---

## TASK-204 Source Confirmation (Q01–Q03)

Use PostgreSQL 15 only in disposable containers. No deployed Supabase evidence
is implied. These modules require the backend's locked Python dependencies.

### Actual migration inventory and setup

- **Fresh current schema:** role/auth/storage stubs from `test_stage3_schema.py`,
  `backend/scripts/schema.sql`, then 006, 007, 008, 009, **011**, **012**, **013**.
  `schema.sql` already defines replace_source_questions and legacy confirm_exam_source;
  do not apply 003 again as an invented prerequisite. 010 is retained empty.
- **Upgrade fixture:** `fixtures/legacy_schema.sql` plus synthetic source seed,
  then 006 and 003 (the existing artifact fixture's deliberate legacy compatibility
  setup), followed by 007–009, 002 (to test the actual replacement RPC), 011, 012, 013.
  A real deployment already at 006–009 needs 011, 012 and 013.
- There is no `004_confirm_source_artifacts_rpc.sql` in this branch. Do not
  fabricate or execute it. Migration numbering must be reconciled with BE2's
  unmerged migration 010 before cross-branch deployment.
- 011 revokes direct worker access to the timestamp overload. Deploy it together
  with the UUID API caller, after stopping/draining old callers. Existing receipts,
  fingerprint comparison, audit and 006–009 functions remain authoritative.
- Q01 tests prove fresh bootstrap, populated upgrade and transactional rollback.
  Q02 uses only current canonical heads. Never read legacy Blueprint modes.

### Commands executed in this session

Host Python was absent, so the existing backend image supplied Python/dependencies.
All 82 installed pinned packages matched `backend/requirements.lock`. Prepare that
image using the existing [Docker setup](../../../docs/setup-docker.md) on a fresh
clone; this session reused the already built image and did not rebuild it.
Docker Desktop/WSL supplied the existing Linux CLI, copied into ignored scratch.
The **runner** has a Docker socket to create/remove fixtures; PostgreSQL containers
have `--network none`, no ports, no host mounts and no external credentials.
The runner also has `--network none`. Never mount the socket into product services.

PowerShell from the repository root (adjust only the local CLI source if needed):

```powershell
$repo = (Get-Location).Path
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'scratch') | Out-Null
$drive = $repo.Substring(0,1).ToLowerInvariant()
$wslRepo = '/mnt/host/' + $drive + $repo.Substring(2).Replace('\','/')
wsl --exec cp /mnt/host/wsl/docker-desktop/cli-tools/usr/bin/docker "$wslRepo/scratch/docker-linux"

# Run modules sequentially, each creates and tears down its own disposable container.
$modules = @(
  'test_source_confirmation_revision.py',
  'test_source_supported_modes.py',
  'test_source_no_ai_integration.py',
  'test_source_artifacts.py'
)
foreach ($module in $modules) {
  docker run --rm --network none `
    --mount "type=bind,source=$repo,target=/workspace" `
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock `
    -e DOCKER_BIN=/workspace/scratch/docker-linux -e RUN_POSTGRES_MIGRATION_TESTS=1 `
    -e PYTHONPATH=/workspace/backend -e ENVIRONMENT=test `
    -e GEMINI_API_KEY= -e GEMINI_API_KEYS= -w /workspace `
    --entrypoint python isomorphic-exam-synthesizer-backend:latest `
    -m unittest discover -s backend/tests/migrations -p $module -v
  if ($LASTEXITCODE -ne 0) { throw "Failed: $module" }
}
```

The command above combines the same per-module invocations used during development;
targeted reruns used `-m unittest module.Class.test_method` with working directory
`/workspace/backend/tests/migrations`. With a Python/dependency/Docker installation
on the host, the identical `python -m unittest discover ...` commands work without
the outer container; keep the transport guards in the no-AI integration test.
Missing `RUN_POSTGRES_MIGRATION_TESTS=1` means **SKIP**, never real-DB PASS.

For PR #43, run the ACL subset with `RUN_POSTGRES_MIGRATION_TESTS=1`,
backend test dependencies and the disposable Docker setup above:

```sh
python -m pytest backend/tests/migrations/test_source_confirmation_revision.py \
  -q -k 'legacy_confirmation_disabled or pre_003_overload or fresh_current_schema_chain'
```

These cases apply 014 to a populated upgrade and a fresh schema, deny legacy
calls with both explicit and default arguments, check a surviving pre-003
overload, and verify the service-role UUID confirmation and single-receipt
replay. Before Supabase integration, reconcile 010 with BE2's deployment
history without renumbering it. Local ACLs do not establish deployed PostgREST
dispatch or permissions.

API/regression command executed in the offline backend container, working directory
`/workspace/backend`:

```sh
python -m pytest tests/api tests/services/test_confirmed_artifacts.py \
  tests/services/test_review_ai_dependency.py tests/services/test_review_contract_parsers.py \
  tests/services/test_review_flow.py tests/services/test_review_lifecycle.py \
  tests/services/test_review_receipts.py tests/services/test_review_validation.py -q --tb=short
python -m pytest tests/ai tests/generation -q --tb=short
```

### Fake provider and proof boundary

`test_source_no_ai_integration.py` uses the actual HTTP routes/repository/producer,
SQL role/ACL execution via `SqlClient`, canonical fixture `ai_pipeline.json` validated
by the real artifact mapper, and a fake `Extractor`. It first leaves production
pending, claims a real running lease, records failure, retries with the fake,
then observes ready modes and replays the confirmation. Stale confirm has zero
receipts; injected postcommit read loss retains one receipt and same-key replay
reconciles. Silent audit remains exactly once.

Three defenses: empty API key variables, injected fake extractor, and network-none
runner plus synchronous/asynchronous HTTP, Gemini gateway and socket transport
guards. Spy asserts **zero outbound attempts**, fake extracts exactly once,
and one canonical document in PostgreSQL. Disabling the provider alone would leave
production pending and would not prove the ready path.

SQL fixture identifiers are synthetic OWNER `00000000-0000-0000-0000-000000000001`,
SID `10000000-0000-0000-0000-000000000001`, SOURCE `20000000-0000-0000-0000-000000000001`;
per-test database/container names are random. Canonical schema version is 0.4.0,
public mode mapping 1.0. Runtime observed: PostgreSQL **15.19** (`postgres:15-alpine`).

JWT verification and PostgREST are injected. Table reads in SqlClient use the fixture
superuser; RPCs use authenticated/service_role principals. This proves RPC ACL and
ownership, **not** deployed JWT/table-read RLS or PostgREST overload dispatch. FE2
integration/acceptance and BE2 generation-config integration are separate gates.
See [contract](../../../docs/api/source-artifacts-contract.md) and
[handoff/evidence](../../../docs/api/source-confirm-handoff.md).
### Postreview P1/P2/P3 (baseline ab9f09a)

Migration013 adds an early BEFORE guard: all source writes require draft with no
approved_at, including warning flag and no-op updates. Owner/service attempts after
confirm leave source UUID, content, receipt, heads, readiness and audit unchanged.
Draft flag changes still rotate the UUID and audit once on first confirmation.
The new tests load the actual owner RLS policies from schema.sql; clone, foreign
owner denial and parent cascade are verified locally. Two real connections test
writer-first stale/no receipt and confirm-first source-locked outcomes with bounded
SQL timeouts. Historical-head coverage uses a private test-admin head fixture,
not edits to a confirmed source or a public reset workflow.

Confirm requires a client UUID Idempotency-Key: missing422, malformed400.
Ingest race ARTIFACT_SOURCE_LOCKED is HTTP409; network/unknown-outcome mappings
stay unchanged. FE1 persistence/adoption is a breaking-contract acceptance gate.
The same four PostgreSQL modules above now contain 50 cases (47 prior + 3 new).
The four current Python consumer cases in test_source_artifacts.py apply011–013;
its remaining SQL-only cases intentionally pin historical006 behavior.
For the final backend regression, add tests/ai and tests/generation to the first
pytest command above in the same invocation; do not repeat already-passing suites.


## TASK-207 W2 generation RPCs

The asyncpg driver is the same optional real-DB test dependency used by TASK-305.
Install it in the test environment (not production requirements), e.g.
python -m pip install asyncpg==0.32.0.

Provision a disposable PostgreSQL 15 container, never a shared database. Example
PowerShell from the repository root with backend test dependencies available:

~~~powershell
$token = [guid]::NewGuid().ToString('N')
$pg = "task207-test-$token"
$db = "task207_cluster_$token"
docker run --detach --name $pg --publish 127.0.0.1::5432 -e POSTGRES_HOST_AUTH_METHOD=trust -e "POSTGRES_DB=$db" postgres:15-alpine
try {
  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    docker exec $pg pg_isready -U postgres -d $db
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Milliseconds 250
  }
  if ($LASTEXITCODE -ne 0) { throw "PostgreSQL unavailable" }
  docker exec $pg psql -U postgres -d $db -v ON_ERROR_STOP=1 -c 'CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;'
  if ($LASTEXITCODE -ne 0) { throw "Role setup failed" }
  $port = (docker port $pg 5432/tcp).Trim().Split(':')[-1]
  $env:RUN_TASK207_REAL_DB_TESTS = '1'
  $env:TASK207_TEST_DSN = "postgresql://postgres@127.0.0.1:$port/$db"
  python -m pytest backend/tests/migrations/test_generation_w2.py -q
  python -m pytest backend/tests/migrations/test_generation_clone.py -q
} finally {
  Remove-Item Env:RUN_TASK207_REAL_DB_TESTS -ErrorAction SilentlyContinue
  Remove-Item Env:TASK207_TEST_DSN -ErrorAction SilentlyContinue
  docker rm --force $pg
}
~~~

The fixture requires explicit opt-in, verifies the localhost task207_cluster_*
database, and creates a separate random task207_case_* database per test.
No test drops public or accepts the postgres default database.
Missing driver/provisioning is not SQL verification. The local author run used a
network-none cluster and backend runner sharing only its network namespace, without
host ports, cloud credentials or a Docker socket.

To regenerate the compact actual-RPC handoff fixture, additionally set
TASK207_CONTRACT_OUTPUT to backend/tests/fixtures/w2_rpc_receipt.json in the test
runner's filesystem and run only -k rpc_receipt_for_worker_handoff.
This explicit artifact option is off by default; omitted_fields identifies removed
large document repetitions. Normal CI never rewrites the fixture.

The same disposable fixture now applies 010 then 011. `test_generation_clone.py`
covers Original Clone without a Python worker/provider implementation: exact 2×2
slots, no-solution sources, zero additional quota, role/token/input guards,
concurrent replay, new-connection resume/retry, atomic rollback, intact projection
completion and populated-010 AI upgrade/replay. Skips do not count as DB evidence.
To export the separate actual clone RPC sample, set `TASK207_CLONE_CONTRACT_OUTPUT`
to a writable test-runner path and run
`-k test_clone_matrix_resume_and_finish_without_quota_or_ai`; only the case with
a supplied solution writes the sample. Copy the emitted JSON to
`backend/tests/fixtures/w2_clone_rpc_receipt.json` after reviewing it. The sample
lists omitted context and uses synthetic source data, with no AI cache claim.


## W4-MVP-03 Review Snapshot API (migration 018)

`test_review_snapshot_pg.py` covers the pre-shuffle Review snapshot reader RPC
(`get_review_current_snapshot`) introduced by migration 018, executed against real
disposable PostgreSQL 15 containers.

Like other migration tests in this directory, the suite requires Docker Desktop
and explicit opt-in:

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
# If docker is not on default PATH:
# $env:DOCKER_BIN = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
python -m unittest backend/tests/migrations/test_review_snapshot_pg.py -v
```

Or using pytest:

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
python -m pytest backend/tests/migrations/test_review_snapshot_pg.py -v
```

The suite covers:
1. **Fresh schema and sequential migrations 006–018**: applying full chain cleanly.
2. **Upgrade & Idempotent replay**: upgrade from populated 016/017 states and repeated replay of 018 without state corruption.
3. **Statement snapshot & lock-free reads**: `get_review_current_snapshot` is a `STABLE` function providing single-statement MVCC consistency without taking row locks that block concurrent transactions. Foreign callers receive `404` (concealment) without waiting on session locks.
4. **Canonical projection invariance**: candidate options, key, and solution are projected from immutable canonical columns (`canonical_options`, `canonical_correct_key`, `canonical_solution_md`), ensuring immunity to post-shuffle display mutation or regeneration resets.
5. **Exact slot & provenance alignment**: strict evidence join by slot `(session_id, version_index, source_question_id)` with `version_question_id` verification, progress accounting, and fail-closed defense against multiple current candidates or missing expected slots.
6. **Frozen source integrity & canonical hash verification**: requires valid `confirmed_input` object for every confirmed source, verifies equality with persisted `source_artifact_revisions.confirmed_input`, and validates computed SHA-256 hash across complete source list.
7. **Optional upstream override**: setting `REVIEW_SNAPSHOT_017_SQL` allows testing against custom or unmerged 017 migration scripts; when unset, it defaults to the merged `017_generation_lifecycle_recovery.sql`.

## Private export ledger — 020 / W4-MVP-08

Requires backend Python dependencies, Docker/Linux engine, and no cloud credentials.
Each test uses an isolated PostgreSQL15 database; production schema/ordered local
migrations are installed. `test_private_export_pg.py` upgrades populated approved
data before020 and also checks fresh installation. No deployment is performed.

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
$env:PYTHONPATH = "$PWD/backend;$PWD/backend/tests/migrations"
# Set DOCKER_BIN to Docker Desktop's CLI if it is not on PATH.
python -m pytest backend/tests/exporter backend/tests/migrations/test_export_snapshot_pg.py backend/tests/migrations/test_private_export_pg.py -q
```

This command runs SQL through separate real connections. It covers concurrent
claims, expiry/takeover, stale tokens, checkpoint/upload/complete/restart response
loss, receipt/identity mismatches, read-back, rollback, RPC ACL/RLS and restrictive
export-bucket policies (including an extra permissive policy). Blob storage stays
fake; HTTP/PostgREST/JWT validation and live Storage/URL expiry are not proven.
The candidate019 from PR61 is not in this branch; any additional pinned019 probe
is reported separately from baseline dev018→020. Do not infer a shared migration
manifest or applied DB state from the test's local chain.
