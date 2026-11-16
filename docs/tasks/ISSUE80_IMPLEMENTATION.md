# Issue #80 — implementation and review handoff

- Role: author preparing independent review; workflow v0.1 proposed / INPUT-20261109, docs revision 7b7387f.
- Branch: `fix/issue-80-optional-source-solutions`; base: `dev@a379ec197df2d75a9db35449fc26c8651274689f`.
- Scope/authority: Issue #80 and the approved implementation plan; Revert overlaps the existing #46 workstream.
- Status: implementation and focused verification complete; Draft PR, independent review and CI pending.

## Behavior and implementation

| Path | Input without explanation | Output / review |
|---|---|---|
| AI generation | Allowed from confirmed frozen sources | Existing structured solution/schema/key/validation checks; no validation relaxation |
| Original Clone | No Gemini generation calls | Frozen stem/options/key, original solution or exact missing-solution notice; pending review |
| Four-attempt fallback | Existing retry/quota conditions | Frozen source with warning, not_validated provenance and pending review; no fifth explanation call |
| Revert | Exact source_question_id/revision from job snapshot | New source-derived current row, warning/audit, pending review; invalidate shuffle and keys |

The exact notice is `Không có lời giải cho câu hỏi này.`. It is disclosure, not a mathematical explanation or AI validation evidence.
Real nonblank source solutions remain verbatim. Wrong solution types fail closed.
Stage 2 retains config-save success and displays startup message/code/question numbers separately.

Migration `024_source_reuse_optional_solutions.sql` replaces only `_generation_claim_010`,
`_generation_fallback_record`, `persist_generation_clone`, and `_review_apply_action`.
Historical migrations, schema, signatures, owners, security modes and access grants are retained.
Claim session locks, frozen manifests, job tokens, quota and committed-slot checks remain.
Source-reuse projection does not change source inputs, hashes, revisions, seeds or AI result kinds.
Old blank clone records replay against their original fingerprint/current projection without being rewritten.
Historical Revert receipts replay unchanged; new Revert requires teacher approval again.
Approved/exported sessions stay locked. No production DB operations were performed.

## Verification findings addressed

Code inspection found Revert assigning the canonical number to the display slot after shuffle.
The new row now retains the current slot's `question_no`, while canonical number/options/key/solution
come from the frozen source. Regression starts from a separately inserted AI candidate with a
different answer, reverts at display position 2/canonical position 1, checks restored key A,
not_validated status, action replay/audit and subsequent Accept. Foreign-owner and corrupted
frozen-revision attempts must leave the original current row/audit unchanged.
The strengthened fixture initially failed because it attempted authenticated access to the
private receipt ledger, then because it tried to mutate immutable canonical fields; those
fixture errors were corrected without loosening production permissions or triggers.

## Reproducible checks (Windows, Python 3.14, local disposable PostgreSQL)

From `backend/`:

```powershell
python -X utf8 -m pytest tests/generation/test_job_repository.py tests/generation/test_jobs.py tests/services/test_review_receipts.py tests/services/test_review_contract_parsers.py tests/services/test_review_validation.py tests/ai/test_generation_pipeline.py tests/shuffler/test_shuffler.py tests/exporter/test_bundle_builder.py -q -k 'not compile_real_xelatex_when_available'
```

Result: **250 passed, 1 deselected**. Includes AI validation, missing source projection,
16 key-remapping combinations, review contracts and export boundary/source rendering.

From repo root, isolated migration fixture creates/removes its own container/random DBs:

```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS='1'
$env:ISSUE80_POSTGRES_IMAGE='postgres:17-alpine' # repeat with postgres:15-alpine
python -X utf8 -m pytest backend/tests/migrations/test_w4_confirmed_source_fallback_pg.py -q -x --tb=short
```

Final strengthened results: **19 passed on PostgreSQL 17**; **5 passed, 14 deselected
on PostgreSQL 15** with `-k issue80` (prior full PG15 baseline: 18 passed). Coverage includes real writers/read-back, fencing, permissions,
null/empty/Unicode whitespace, clone upgrade/reapply/replay and frozen-source Revert.

For HTTP adapter tests, create a disposable postgres:17-alpine container bound only to
127.0.0.1 (e.g. port 55480), with database `task207_cluster_issue80`, test-only trust auth,
and roles `anon`, `authenticated`, `service_role BYPASSRLS`. From `backend/`:

```powershell
$env:RUN_TASK207_REAL_DB_TESTS='1'
$env:TASK207_TEST_DSN='postgresql://postgres@127.0.0.1:55480/task207_cluster_issue80'
python -X utf8 -m pytest tests/migrations/test_w4_generation_adapter_pg.py -q -x --tb=short
```

Result: **16 passed**. Real SQL/HTTP bridge with fixture auth/provider stubs; covers
AI/clone, missing explanations, four-attempt fallback, lost-response reconciliation,
retry/resume, historical Q01 guards and foreign-owner checks. Not live JWT/PostgREST/Gemini.

Static checks: root `python -m ruff check backend/app scripts/blueprint` and
`python -m mypy backend/app --ignore-missing-imports` passed; changed Python tests also Ruff-clean.
`git diff --check` passed. Frontend `npm run lint`, `npm run build` and
`node --test src/features/stage2-config/Stage2ConfigPage.test.js`: **32 passed**;
build reports the existing large-chunk advisory.

## Unverified paths / acceptance still pending

- Real XeLaTeX test was retried and **failed before compiler launch** in Python subprocess
  DuplicateHandle: WinError 6 (PTY); prior pipe execution gave WinError 50. No PDF-render PASS claimed.
- Preview/private-export Golden was not run: PR #49@955748d, #58@1c01ad3 and #63@1d61406
  remain unmerged. Current #58 still accepts nonempty notice through its normal solution branch;
  its newer verified-empty provenance exception is separate and unchanged by this work.
- No complete preview -> final approval -> private Storage -> ZIP download run, no live Gemini,
  JWT/RLS transport smoke, no production catalog verification and no independent GitHub Approve.
- Concurrency primitives were inspected and existing fencing/ownership tests pass; exhaustive
  concurrent Revert/Accept/regeneration interleavings still require independent scrutiny.

## Review and deployment guidance

Highest risk: SQL Revert source/revision/hash verification, display/canonical mapping, single-current-row
swap plus audit/receipt atomicity; clone legacy expected-record/fingerprint replay; claim policy-only
removal and grants; action-specific receipt validation. Verify rejected/invalid AI outputs still fail
and that the notice never becomes a validator exception.

Before deployment, verify target ledger and migration-number availability. Drain generation/review
mutations, apply 024, deploy matching backend, smoke, then reopen traffic. Old workers must not run
against newly permissive SQL. Forward-fix rather than replaying 022 or rewriting committed/approved
snapshots. Unlocked historical blank clones can Revert and reapprove to obtain the disclosure.

Acceptance requires independent review/CI and the complete integrated Golden on one deployed SHA;
this handoff does not certify production completion. No changes to PRs #49/#58/#63, merge or deploy.
