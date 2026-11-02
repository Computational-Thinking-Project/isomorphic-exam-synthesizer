# TASK-302 PostgreSQL schema tests

These tests execute SQL against **PostgreSQL 15**, rather than mocking Supabase.
They create a disposable container with no network, published ports, host mounts,
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

The suite covers populated legacy upgrade and replay, full initialization plus
migration, canonical immutability with display-only shuffle, independent new
candidate snapshots, the partial current index, both answer-key field formats,
ambiguous/missing mappings, duplicate legacy keys, and transaction rollback.
`fixtures/legacy_schema.sql` snapshots the pre-TASK-302 table definitions from
dev `32d7644`; keep that fixture unchanged when updating the initialization schema.

The `auth`/`storage` bootstrap is a local test stub. These checks do **not** verify
Supabase deployment/RLS, AI calls, actual shuffle algorithms, or lifecycle RPC
concurrency, idempotency and quota accounting. Those remain separate integration
checks after the contracts in `docs/tasks/TASK-302.md` are settled.

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
or replace the actor/ownership checks required in the pending lifecycle RPCs.

Actor regressions cover migration replay with historical NULLs, fresh-schema
enforcement, missing/backdated new actors, preserving known actors on UPDATE,
verified historical correction, and invalid actor foreign keys.
