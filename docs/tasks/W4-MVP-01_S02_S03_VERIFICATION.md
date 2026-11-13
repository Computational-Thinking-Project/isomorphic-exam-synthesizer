# W4-MVP-01 — S01/S02 regression fence and S03 implementation

Superseded for current config status by [S04 verification](W4-MVP-01_S04_VERIFICATION.md):
018 is now locally implemented under later user authorization. That report also
corrects the old empty-policy test's early assertion and records actual RED→GREEN.

Date: 2026-11-09, Asia/Saigon. AUTHOR; workflow v0.1 proposed.
HEAD remains `65c536291b0ad23c39e3b7f0615098943117d6e3` on
`feat/w4-mvp-01-source-readiness`; dev `f104fae6188310b386b9e359c8f72d49c5db43bf`.
Changes are local and uncommitted. Production was not accessed or changed.

## Authorization and owner check

The user accepted the existing PostgreSQL baseline and authorized S02 RED tests
and independent S03 implementation while ledger/Supabase Local remain blocked.
S00 Git/PR/ownership is PASS; applied Production history is UNVERIFIED.
The previous local verification report is historical; the current results below
supersede its S02/S03 NOT IMPLEMENTED entries.

Fetched PR heads: #30 `b6b642225b45e2744fda8826ebc70c8db0a3850e`,
#42 `6d3c555b935fdd65a1498920475bdafe009a6154`,
#49 `ec303a42cda7ebf9e6550a3c52856259931e6a5d`,
#52 `598b959c69c0f1c6362daed50fd544cb09dd73f7`.
Comparing each PR to dev found no changes to sessions.py or test_ingest.py.
No PR30 config/worker/main.py, FE1/FE2, PR49 finalize/schemas, or PR52 SQL/test
implementation was modified. Existing uncommitted baseline files were preserved.

## S01 rerun before implementation

- API confirmation/session/ownership: **103 passed, 0 failed, 0 skipped**.
- Real PostgreSQL source confirmation revision suite: **16 passed, 0 failed,
  0 skipped**, 72.545s. This includes owner checks, same-key receipt replay,
  concurrent confirmation/source writes, stale revision, rollback and source freeze.

Commands (repository root; .venv dependencies from the preceding local setup):

```sh
SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_ANON_KEY=local-test-only \
SUPABASE_SERVICE_ROLE_KEY=local-test-only PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/api/test_confirm_source.py backend/tests/api/test_sessions.py \
  backend/tests/api/test_ownership.py -q -p no:cacheprovider --tb=short

PYTHONPATH=backend RUN_POSTGRES_MIGRATION_TESTS=1 \
DOCKER_HOST=unix:///var/run/docker.sock DOCKER_CONTEXT=default \
.venv/bin/python -m unittest discover -s backend/tests/migrations \
  -p test_source_confirmation_revision.py -v
```

## S02 actual RED, not skips or fixture failures

New module: `backend/tests/migrations/test_w4_source_readiness_config.py`.
Every case creates a random database in a network-none PostgreSQL15 container,
applies schema.sql and the unchanged002–016 chain, seeds two persisted sources,
and uses the real confirmation/claim/publication RPCs to establish readiness.
Config saves execute as actual authenticated owner/foreign-owner roles.
All denied-write tests compare persisted full-row state (sessions/configs/jobs/
results/receipts/heads) and SQLSTATE. Malformed-policy/hash fixtures use the test
administrator without disabling triggers or ACLs. Missing source solutions stay
NULL; no fake solution is inserted. No external DSN, network port or host mount.

Final explicitly enabled run: **19 tests: 10 PASS, 9 FAIL (expected RED),
0 errors, 0 skipped**. Failures remain ordinary assertions; no xfail,
expectedFailure, assertion relaxation or migration implementation was introduced.

| Desired invariant (RED test) | Actual unchanged015/schema behavior |
|---|---|
| No confirmation cannot save despite legacy blueprints | NO_CONFIRMATION legacy branch accepts and writes config/configured state |
| Neutral client modes derive common dimensions | Saves empty modes/dimensions although both sources permit values/context |
| Intersection excludes context missing from one source | Saves empty dimensions instead of shared values |
| Client NUMERICAL cannot select permission | Nonempty requested mode accepted |
| Client NONE cannot force clone | NONE normalized to empty modes and accepted |
| RPC omitted ordering defaults OFF/OFF | Stored ON/ON |
| Table omitted ordering defaults OFF/OFF | Stored ON/ON |
| Extra ordering key rejected | Unexpected key persisted |
| Empty canonical policy cannot silently clone | get_source_artifacts reports not ready, but config save accepts the empty policy |

The ten PASS cases establish working controls: valid strict booleans and missing
keys rejected; four flag combinations retained; invalid N rejected; pending/failed
canonical denied; invalid dimension denied; missing/forged manifest denied;
foreign owner denied; direct authenticated INSERT denied; stale source fingerprint
denied; schema-valid disjoint policies permit a legitimate Original Clone.
No representative worker alias was chosen: intersection assertions check canonical
dimensions, leaving the unresolved NUMERICAL/parameter_variation choice to owners.

```sh
PYTHONPATH=backend RUN_POSTGRES_MIGRATION_TESTS=1 \
DOCKER_HOST=unix:///var/run/docker.sock DOCKER_CONTEXT=default \
.venv/bin/python -m unittest discover -s backend/tests/migrations \
  -p test_w4_source_readiness_config.py -v
```

This command must exit nonzero against the unchanged baseline. The initial
15-case run yielded7 failures; the final19-case run adds intersection, empty
policy, invalid dimension and stale hash coverage. An initial discovery attempt
also imported unrelated ReviewRpcTests; it was interrupted, module import changed
to an alias, and the owned leftover container removed. Only the complete final
run is counted. No initial interrupted or partial execution is labeled PASS.

## S03 source change and RED→GREEN evidence

Production-code delta is only `backend/app/api/routes/sessions.py`: remove the
two pre-confirm `background_tasks.add_task(trigger_blueprint_pipeline, ...)`
calls and their unused import. Keep route signatures, parsing/validation,
storage behavior, atomic replacement, response schemas and confirmation producer.
The two existing BackgroundTasks parameters remain for signature compatibility.
Legacy helper/table/history remain intact; search found no other production
scheduler caller. Existing legacy helper tests are retained.

Added parameterized HTTP regression in test_ingest.py for both text and Markdown
file entry points: real parser/validation and response, one awaited replacement,
expected upload behavior, and zero scheduled tasks. Before changing source:
**2 FAIL**, both specifically because add_task received trigger_blueprint_pipeline.
After removing the hook, the unchanged assertions pass.

Post-change focused suite (ingest, legacy helper, confirm-source, sessions,
ownership): **146 passed, 0 failed, 0 skipped**, 6 warnings, 3.20s.
Real SQL-backed HTTP/producer no-AI suite: **1 passed, 0 failed, 0 skipped**,
13.045s. It verifies pending/retry/ready and receipt replay with outbound transport
blocked; JWT validation is injected, so this is not Supabase JWT/PostgREST proof.

```sh
SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_ANON_KEY=local-test-only \
SUPABASE_SERVICE_ROLE_KEY=local-test-only PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/api/test_ingest.py backend/tests/api/test_legacy_blueprint_helpers.py \
  backend/tests/api/test_confirm_source.py backend/tests/api/test_sessions.py \
  backend/tests/api/test_ownership.py -q -p no:cacheprovider --tb=short

PYTHONPATH=backend RUN_POSTGRES_MIGRATION_TESTS=1 \
DOCKER_HOST=unix:///var/run/docker.sock DOCKER_CONTEXT=default \
.venv/bin/python -m unittest discover -s backend/tests/migrations \
  -p test_source_no_ai_integration.py -v
```

Static checks: Ruff backend/app and scripts/blueprint PASS; Ruff on both touched
test modules PASS; Mypy backend/app --ignore-missing-imports PASS (91 files).
Whitespace checks PASS. Full backend/frontend/CI suites NOT RUN in this turn.

## Artifacts, status and remaining blockers

Local logs in /tmp/w4-evidence: s01-current.log, s01-sql-current.log,
s02-red-complete.log, s03-before.log, s03-green.log, s03-no-ai-current.log,
s03-mypy.log. These are execution artifacts, not CI or reviewer approval.

- Completed: S01 rerun; S02 negative baseline encoded and actual RED reproduced;
  S03 scoped scheduler removal and regression verification.
- Coding decisions still pending for dependent S04–S07: worker alias contract,
  Stage3 RPC/HTTP/error contract and PR30/FE2 owner adaptations. No need to block
  independent tests on Supabase Local. S02 is a successful defect reproduction,
  **not a green W4 config implementation**.
- Migration blocker: applied ledger/allocation not verified;017 remains PR52's;
 018 not created, applied, or reserved by this agent. No historical SQL changed.
- Release blockers: actual local Supabase Auth/JWT/PostgREST/RLS, current combined
  owner SHA, S08 feature security/races/fresh+upgrade, S09 end-to-end and product
  missing-solution decisions remain unverified. Production drift remains unresolved.
- Next safe step: obtain those owner/allocation decisions, then implement S04's
  forward-only correction and rerun the unchanged RED assertions to GREEN.
- Commit: NONE. Push / PR creation / merge / deploy / Production access: NO.

**W4-MVP-01 is not complete.**
