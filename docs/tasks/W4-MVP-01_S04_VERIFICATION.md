# W4-MVP-01 — S04 local migration and worker compatibility

2026-11-09, Asia/Saigon. AUTHOR, workflow v0.1 proposed.
HEAD:65c536291b0ad23c39e3b7f0615098943117d6e3; dev:f104fae6188310b386b9e359c8f72d49c5db43bf.
The execution sections below describe the pre-commit local implementation. The user
subsequently authorized committing/pushing this checkpoint; see handoff below.
No PR creation/merge, deployment or Production access is authorized.

## Authorized decisions and source verification

The user explicitly allocated018 and authorized S04 without waiting for a Quỳnh
comment. Retain both NUMERICAL and parameter_variation as compatibility aliases,
normalize to one canonical values dimension, derive permissions server-side and
default shuffle OFF/OFF. This authorization supersedes the former local coding
block on allocation/mapping; Production ledger remains UNVERIFIED, not approved.

Refreshed dev/task/PR30/PR52 refs: dev ends016; PR52@598b959 owns017 and is still
unmerged. Inspected PR30@b6b642225b45e2744fda8826ebc70c8db0a3850e:
job_repository.claim reads context.canonical_dimensions into AIBatchInputs;
ai_batch_adapter.run passes them to generate_exam_drafts. Existing mode_mapper
supports both aliases with semantic deduplication. No owner module was edited.

## Implementation and invariant

New018_w4_source_readiness_config.sql is transactional and forward-only. It changes
the table default and replaces only the five-input save_generation_config RPC.
It locks exam_sessions first; verifies owner/role, configurable state, no approved,
finalized or frozen-job state; enforces N1–4, exact neutral[] mode argument and
exactly two JSON Boolean preference keys; then rechecks canonical evidence and
expected manifest while locked. No NO_CONFIRMATION bypass remains in new saves.

All source policies must be nonempty with valid transformation objects/dimensions.
For each source, independently test values/context membership and intersect across
all questions. Stable output: NUMERICAL,parameter_variation,context_swap filtered
by intersection; canonical_dimensions values,context each at most once. A valid
empty mapped intersection produces Original Clone; malformed/not-ready never does.
Only config and parent status are written. SQL failure rolls back those writes.

SECURITY DEFINER retains fixed search_path and explicit authenticated/service_role
EXECUTE, revoking PUBLIC/anon. No table grants were widened. Existing job/clone/
finalize functions and historical stored config values are unchanged. Fresh
schema.sql's default is aligned; no historical numbered migration was modified.
The new migration must follow reviewed017; tests read immutable PR52 Git bytes
without copying or merging its SQL into this branch.

## Actual tests and evidence

PostgreSQL15-alpine image digest is the one pinned in LOCAL_VERIFICATION.
Every test uses a fresh network-none container/database with no exposed ports,
host mounts, external DSN or Production credentials; cleanup is local-only.

| Suite | Result |
|---|---|
| Config suite with018 and real SQL→PR30 worker probe | 22 PASS,0 FAIL,0 SKIP;179.650s |
| Additional concurrent saves, save-vs-claim and injected persistence rollback | 3 PASS,0 FAIL,0 SKIP |
| Baseline/fresh/upgrade/replay suite | 6 PASS,0 FAIL,0 SKIP;59.371s |
| Focused ingest/confirm/mode mapper API/unit regression | 121 PASS,0 FAIL,0 SKIP;6 warnings;2.35s |
| Ruff changed test modules / existing application | PASS |
| Historical002–016 diff, whitespace | PASS; unchanged historical SQL |

The original19 S02 assertions now pass under018. Three added cases verify a frozen
snapshot with values once, the independent frozen-job fence, and the worker probe.
The three additional concurrency/rollback cases were run separately after being
added, not counted as part of the22-case execution. No distinct suites with
overlapping baseline assertions are combined into an inflated total.

The worker probe uses actual SQL claim/completed receipts, replays transport in
an isolated PR30 archive, and executes the real GenerationJobRepository and
AIBatchAdapter. A fake generation service receives variation_modes=[values] once,
returns four successful fixture candidates (2 sources×2 versions), and the adapter
delivers four distinct prepared slots. It does not prove provider/math quality or
actual HTTP/JWT/PostgREST. It does prove aliases do not duplicate worker targets.

Fresh018 checks exact function identity (no old four-arg overload), owner/anon
EXECUTE, table write denial, source-freeze trigger and migration replay. Populated
upgrade preserves complete historical config rows with explicit ON/ON and all
22 synthetic baseline rows, then verifies a new row defaults OFF/OFF.

Evidence correction: the S02 empty-policy test previously stopped on
get_source_artifacts raising22023, before it called config save. Its assertion now
checks that actual error without weakening the desired config rejection. A fresh
W4_BASELINE_015=1 run of that corrected test failed because save **returned success
with empty modes**. The identical test is now GREEN with018. The prior9-failure
summary included the earlier readiness assertion; do not treat that old trace as
proof that its config call executed. New baseline RED evidence is independent.

Logs in /tmp/w4-evidence: s04-empty-baseline-red.log, s04-green-final.log,
s04-upgrade.log, s04-race-rollback.log, s04-api.log. The preliminary018 run retained
the incorrect readiness assertion and failed there; it is superseded by final
execution, not counted as PASS. No xfail/expectedFailure was used.

## Reproduction

Create a separate archive of PR30@b6b6422 (do not merge it); set W4_PR30_CHECKOUT
to that directory. With .venv dependencies and the local Docker daemon:

```sh
PYTHONPATH=backend RUN_POSTGRES_MIGRATION_TESTS=1 \
DOCKER_HOST=unix:///var/run/docker.sock DOCKER_CONTEXT=default \
W4_PR30_CHECKOUT=/tmp/w4-pr30-checkout .venv/bin/python -m unittest discover \
  -s backend/tests/migrations -p test_w4_source_readiness_config.py -v

PYTHONPATH=backend RUN_POSTGRES_MIGRATION_TESTS=1 \
DOCKER_HOST=unix:///var/run/docker.sock DOCKER_CONTEXT=default \
.venv/bin/python -m unittest discover -s backend/tests/migrations \
  -p test_w4_baseline_chain.py -v
```

The first command now includes the three later concurrency/rollback cases as
well. To reproduce the old empty-policy defect, set W4_BASELINE_015=1 and use
-k empty_policy; it must fail against the pinned pre018 schema/015, without changing018.

## Remaining work

S04's local scope is implemented and verified as above. S05/S06 Stage3 preference
RPC/API and S07 PR30/FE2 request adaptation are not implemented by018. Existing
PR30 HTTP code still sends selected modes and must be updated by its owner before
an integrated rollout. Stage3 naming/error-contract decisions remain pending.
S08 complete W4 security/finalize race matrix and S09 local Supabase JWT/PostgREST/
RLS on one integrated SHA are NOT RUN. Production drift/history remains unresolved.
No Production migration or release is authorized. **W4-MVP-01 is not complete.**

## User-authorized commit/push checkpoint

The user requested saving S00–S04 and continuing the remaining work later.
Pre-push checks: Ruff, Mypy (91 application files), SymPy LaTeX smoke and diff
checks PASS. Full backend/Blueprint suite: **1143 passed,562 skipped,0 failed**,
25 warnings,38.58s. Explicit PostgreSQL runs above remain the database evidence;
default skips are not PASS. Frontend/Docker CI was not rerun for this checkpoint.

The first full run failed its real XeLaTeX exporter test because the environment
lacked TeX Gyre Termes. Extracted Debian fonts-texgyre into /tmp and used a local
FONTCONFIG_FILE; no exporter code or assertions changed. The targeted test then
passed, followed by the full green rerun. Logs: pre-push-tests.log,
pre-push-xelatex.log, pre-push-tests-final.log under /tmp/w4-evidence.

Resume with S05/S06 reviewed-only preferences RPC/API, then owner-coordinated
PR30/FE2 adaptation and S08/S09.018 has only been executed in disposable local
tests with pinned unmerged017 bytes; do not apply it to Production from this
checkpoint. Production ledger/drift and actual Supabase JWT/RLS remain unresolved.
