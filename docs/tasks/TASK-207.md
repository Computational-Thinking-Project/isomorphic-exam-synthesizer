# TASK-207a/b — PR #32 implementation and handoff

## Assignment and scope

- Author: Duy / PR #32; Python worker/preflight/clone/SSE owner: Quỳnh / PR #30.
- Source: user-approved implementation plan, 05/11/2026; existing coordination
  [PR #32](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32)
  and [W2 input](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6635728977).
- Workflow v0.1 proposed, docs commit 506384b; M2/M3/M5.
- Starting head b586ae6; adopted dev 426ca0c (PR #33); merged locally without conflict.
  The W3 assignment remains context, not a new deadline for this remediation.
- Implement SQL/RPC, permissions, session detail, regressions and shared contract.
  No worker/UI/generator/shuffler rewrite, cloud deployment or repository merge.
- Preserve pre-existing untracked .pr32-independent-gates/ and .task305-integration/.
  Neither is included in this implementation's commits.

## Implementation

| Step | Output |
|---|---|
| T1 | Merge dev, keep 006–009, replace abandoned W2 migration 008 with forward 010 |
| T2 | Narrow RPC JSON types, update API doubles, align root/backend asyncio test configuration |
| T3 | Exact public modes/NONE, fail-closed readiness, expected manifest under config lock |
| T4 | Ordered confirmed snapshot/hash, immutable context, initial claim atomicity, stable retry identity |
| T5 | Full result/projection atomicity, immutable success, failure retry, typed resume envelopes, exact finish slots |
| T6 | Fresh/populated upgrade, replay, ACL/GUC probes, concurrency/rollback, review/finalize compatibility |
| T7 | Shared API contract/change log, actual RPC fixture, M5 and PR package |

The implementation uses the existing two W2 tables and SQL/RPC boundaries.
Private wrappers retain the prior legacy implementations; canonical W2 cannot
use display-only persistence. No generic snapshot/mapping framework or automatic
historical conversion is introduced.

## Self-check evidence

Environment: existing backend image, Python 3.11; PostgreSQL 15 disposable
network-none container. asyncpg 0.32.0 is an optional test dependency, not a new
production requirement. Auth/table/provider doubles are distinguished from SQL.

- Ruff: backend/app and scripts/blueprint plus changed Python tests — passed.
- Mypy: backend/app --ignore-missing-imports — passed, 91 source files.
- Full CI-shaped collection:
  python -m pytest backend/tests scripts/blueprint/tests -q
  — **1079 passed, 316 skipped**, 19 deprecation warnings.
  The skipped cases include real-DB opt-ins/live provider; no DB pass is inferred.
- Explicit W2 PostgreSQL suite:
  python -m pytest backend/tests/migrations/test_generation_w2.py -q
  with RUN_TASK207_REAL_DB_TESTS=1 and verified disposable TASK207_TEST_DSN
  — **46 passed, 0 skipped**.
- Real DB suite includes verify_migration_004_permissions.sql, no-legacy canonical
  producer/config/claim/persist/retry, success/failure overwrite probes, lost-response
  replay, independent concurrent claim/persist, failed-transaction rollback,
  populated pre-010 upgrade/replay and review/shuffle/final approval.
- SymPy LaTeX smoke and git diff --check — passed.
- [RPC receipt excerpts](../../backend/tests/fixtures/w2_rpc_receipt.json):
  actual PostgreSQL outputs, explicit omitted_fields for repeated full documents.

Initial root pytest collection exposed missing asyncio_mode=auto when collecting
backend and scripts together; root configuration now matches backend. An early
cross-language hash probe also found whitespace-only solution disagreement;
the SQL mapper now matches Python's whitespace set and parity tests pass.

These are author checks on the implementation, not independent review or GitHub
approval. Remote CI status must be checked on the pushed head.

## Contract and remaining integration inputs

Authoritative [API/RPC contract](../api/generation-config-endpoint.md).

PR #30 must consume the exact manifest as p_expected_snapshot on canonical save,
snapshot_id/context from claim and full-result envelopes from resume; validate
AI model/prompt/request fingerprint against that context before cache acceptance.
DB validates slot/seed/Blueprint/projection consistency without duplicating the
complete Python model validator.

Clone orchestration and its distinct record contract remain PR #30 work.
This PR does not fabricate an AI QuestionResult or validation proof for clone.
Unknown historic/display-only output is not silently promoted into resume evidence.
Canonical schema/producer ownership remains with migration 006; read exposure
is a W2 RPC in migration 010, not public table access.

## M5 / completion gates

- F02 — author claimed_fixed: exact legacy IDs and canonical no-fallback semantics;
  public mode intersection and malformed/not-ready API regressions.
- F07 — author claimed_fixed: column privileges/guards retained across 005/009,
  actual role/GUC attack probes and legitimate owner CRUD verified locally.
- F09 — author self-check passed: final Auth/ownership/sessions fixtures execute
  through assertions; RPC doubles now explicitly model NO_CONFIRMATION.
- F10 — actual RPC examples/signatures supersede the stale description.
- Independent finding verification and GitHub Approve remain reviewer actions.
- Merge readiness also requires applicable remote CI green on the final head.
- DB/Python self-check is not worker/provider/SSE/FE E2E or Supabase rollout.
