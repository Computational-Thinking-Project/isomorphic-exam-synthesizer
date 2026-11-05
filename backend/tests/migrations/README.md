# TASK-302 PostgreSQL schema and RPC tests

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
