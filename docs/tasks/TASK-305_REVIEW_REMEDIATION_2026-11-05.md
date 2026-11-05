# PR #33 / TASK-305 — F01–F03 remediation and M5 evidence

05/11/2026, Asia/Saigon. Baseline `9e9ec1463738e0ab14be0cfb3e012df67f5b4e4a`,
base `dev@99dc8d307cb22b489cb17553d487f0ce5f7573e7`. Workflow v0.1 proposed,
docs `506384b`. Author implementation + local execution + self-review; independent
review/GitHub Approve remain separate. No merge or cloud deployment.

Scope follows the user's pasted review: reproduce/fix F01/F02, determine the
F03 deterministic contract and remediate it, update the PR body and request
Đạt's re-review of the new head. This explicitly extends the earlier A+B-only
scope into the reported content-lock and approval defects; it does not claim
all TASK-305 C–F/export requirements complete.

## Independent baseline check

Read current production, SQL/schema, owner assignment/contracts, tests and live
PR metadata. HEAD matched9e9ec146, dev remained ancestor; worktree contained only
the three pre-existing unrelated artifacts, all preserved. No migration009 was
found in fetched origin branches before creating it. SQL006/007/008 and TASK-303
algorithm/models remain unchanged in this remediation.

Live Actions logs at the baseline confirm:

- [Pipeline278](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/41986520146),
  backend job127108423760: **1039 passed,130 skipped**, mypy90 files/0 errors,
  Ruff passed; frontend build job127108423957 success.
- [Docker239](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/41986520018),
  job127108423029: **1005 passed,122 skipped**, standalone Blueprint41 passed/1 skipped.
- These counts are baseline evidence, not checks of the later remediation commit.
  The old F-TEST-IMPORT is not reopened; current finalize tests collect and run.

Fresh PostgreSQL15 fixture at the baseline reproduced **all three** findings:

```text
F02: wrong key approved: approved
F01: direct owner content write / unlock: UPDATE 1 UPDATE 1
F03: alternate permutation committed: True
```

F01's fixture explicitly granted typical broad authenticated DML privileges;
this proves the conditional exploit locally, not production grants. F02 replaced
one actual display answer with another A–D key, maintaining aliases and structural
coverage, before real approval. F03 used the existing shuffler with identity
preferences to form a different internally consistent permutation, while retaining
the real snapshot/preferences and required seed in the submitted RPC payload.

## M5: author response and verification

| ID | Reproduction/root cause | Remediation | Local verification / remaining acceptance |
|---|---|---|---|
| F01 / P1 | Owner-only FOR ALL policies plus table grants permit post-approval edits and unlocking; profile deletion can cascade as the FK trigger owner. | Forward009 revokes table **and column** mutations on versions/questions/keys/audit, SELECT-only owner policies, client TRUNCATE/TRIGGER/REFERENCES and profile DELETE removal. Invoker triggers block direct locked-state writes on the content graph, including late service-role writes. Direct client lifecycle forging is rejected; draft create/metadata/delete remain supported. | **claimed_fixed, local verified**: real authenticated/service-role cases, broad pre-upgrade grants, column ACL checks, forged role claims, source/config/blueprint guards, profile cascade, TRUNCATE, RLS read isolation and an actual approval/config blocking-PID interleaving. HTTP metadata/delete map locked DB errors to423. Independent reviewer must re-verify. |
| F02 / P1 | SQL007 checked coverage/aliases/canonical set, not the actual current display row's key/mapping. |009 replaces approval definition, retaining existing guards/idempotency. Exact one current question and one key per version/display slot; compare both key aliases to q.correct_key and canonical IDs to q.canonical_question_no, under parent lock and before approval/audit. | **claimed_fixed, local verified**: wrong key, swapped canonical mapping with valid set coverage, missing display slot and duplicate display slot denied with full state/audit unchanged; valid approval and replay keep timestamp/audit identities. |
| F03 / P2 | Contract TASK-303 explicitly requires same seed/input → same output; SQL's bijection/seed check alone cannot prove the Python RNG output. | Trusted backend attestation boundary: owner JWT/RLS reads → unchanged Python shuffler → separate service-only RPC client. SQL checks actual PostgreSQL principal, verified actor ownership and all existing snapshot/integrity guards. Browser actor/permutation body is ignored; no owner writer fallback. Finalized config cannot be changed/deleted/reinserted behind the receipt. | **claimed_fixed, local verified**: authenticated RPC execution denied even for a valid alternate permutation and forged service claim; trusted wrong/missing actor denied; forged HTTP body results in the actual expected server permutation; missing writer fails closed; existing seed/rollback/retry/parity/concurrency suite remains green. Independent contract acceptance pending. |

Current authoritative [Finalize RPC contract](../api/finalize-rpc-contract.md)
and [DEC-T305-SEC-002](../change_log.md) describe the principal boundary and rollout.
SQL009 is a forward replacement, not an edit to deployed historical migrations.
It also refreshes the existing solution helper so an earlier008 installation
receives the parity fix without replaying/rewriting008.

## Execution on remediation source

Python3.11.17, asyncpg0.32.0, PostgreSQL15.19/Alpine/musl/UTF8/en_US.utf8,
Ruff0.17.1, mypy2.4.0. The new `task305-review-pg` container had network none,
database `task305_isolated` and a read-only source mount. DB runners shared only
that container's network namespace; no Docker socket/cloud credentials. Additional
suite/upgrade databases used random `task305_test_*` names, pre-DDL database checks
and cleanup. No production/staging or default-postgres destructive fixture.

All Python commands below run in backend with PYTHONPATH=/workspace/backend.

| Command | Actual result |
|---|---|
| `python -m pytest tests/services tests/api tests/shuffler tests/validation -q -p no:cacheprovider` | **651 passed,9 skipped,0 failed**, 40.36s |
| `RUN_TASK305_REAL_DB_TESTS=1 EXAM_TEST_DB_DESTRUCTIVE=1 python tests/migrations/run_task305_real_db_suites.py` | **9 passed,0 skipped/failed**, 7.93s; fixtures apply006–009 |
| `RUN_TASK305_WRITER_DB_TEST=1 TASK305_WRITER_TEST_DSN=postgresql://postgres@127.0.0.1/task305_isolated python -m pytest tests/migrations/test_shuffle_writer_db.py tests/migrations/test_shuffle_writer_adversarial.py tests/migrations/test_finalize_security_boundary.py -q -p no:cacheprovider` | **142 passed,0 skipped/failed**, 35.97s:100 existing writer +42 security/upgrade cases |
| `python -m mypy app --ignore-missing-imports --cache-dir /tmp/task305-review-mypy` | **0 errors,90 source files** |
| `python -m ruff check app tests /workspace/scripts/blueprint` | **passed** |
| Root `python -m ruff format --check backend/app backend/tests`, compared with clean origin/dev archive | Both exit1, **same49 baseline files**, no new failures; current109/dev90 already formatted |
| `git diff --check` | **passed** |

The9 skips in the broad run are still skips. Their execution evidence is the
separate9-pass run, not relabelling skips. Warnings are existing Starlette/httpx
and HTTP422 deprecations. Earlier interim141/137/100 and34/32 runs were checkpoints,
not totals to add to142. New fixture/lint mistakes were corrected against the SQL
contract and rerun; no production validation was relaxed to pass tests.

The142 SQL cases include real fault/rollback and locking evidence, not mocked
transactions. Migration-specific fresh **and populated legacy** tests apply006–008,
seed valid data and broad table/column grants, inject a failure at the end of009
before COMMIT, then verify old function/ACL/data restoration. Successful009 and
replay preserve every seeded business row and enable only the trusted writer.
The fresh/legacy fixture user seeding is explicit and keeps foreign keys enabled.

Security tests inspect row snapshots including timestamps, history, users and
blueprints. The100 older tests explicitly model the trusted backend principal for
writer calls, keeping connection PID/transaction for concurrency. Raw client-denial
tests **do not** use that role-switch helper. This is an intentional new contract,
not a mock that grants the production browser additional privileges.

## Changed files and self-review

- Production: `api/routes/finalize.py` (writer dependency),
  `services/finalize/service.py` (separate writer/verified actor/no fallback),
  `api/routes/sessions.py` (HTTP423 mapping), `core/database.py` (client use docs),
  new `migrations/009_finalize_security_boundary.sql`.
- Tests: new `test_finalize_security_boundary.py`, adapted writer/adversarial
  fixtures, shuffle API/unit tests, Review/Finalize real-DB chain to009.
- Documentation: Finalize contract, migration README, change log, this packet;
  earlier A+B gate labelled historical with a link to the new boundary.

Self-review checked the full production diff, historical migration immutability,
caller/actor split, table versus column grants, cascade and TRUNCATE paths,
config delete/reinsert, late service DML, actual-key join multiplicity, stale input,
malformed receipts, transaction rollback/replay and mixed-version behavior.
It identified and closed profile-cascade, column-grant, config-reinsert and late
worker paths in addition to the review's minimal examples. The shared006 and
TASK-303 shuffler are unchanged; no direct table fallback, guessed recovery ID,
new Review ledger or second shuffle writer authority was added.

## Handoff / limits

- Author considers F01–F03 fixed and locally verified, ready for **re-review**.
  This packet does not itself close external review threads or grant Approve.
- New-head CI must be reported from actual GitHub after push; baseline CI above
  cannot certify the new commit. PR body is updated to the actual new head and
  Đạt is requested to review that head; no Draft/Ready flag change or merge.
- Deployed Supabase JWT verification/table-read RLS/PostgREST pooling, actual
  migration ledger and cloud rollout are **NOT VERIFIED**. PostgreSQL roles/RLS,
  transactions/locks are real locally; positive HTTP auth/transport are injected.
- Backend reader/writer split and009 require a coordinated/feature-gated rollout;
  mismatched versions fail closed, never owner fallback. Service secrets remain
  server-side. Administrative DB owners/compromised service credentials are not
  untrusted end-user principals; SQL does not reimplement Fisher–Yates.
- Finalized configuration editing and approved→exported need authorized locked
  RPCs if introduced by their owners. No reconfiguration/export/unlock workflow
  or broad C–F completion was added or inferred from these three fixes.
- Existing49 formatter failures and full deployment/integration acceptance remain
  distinct. No claim that all TASK-305 or production verification is complete.
