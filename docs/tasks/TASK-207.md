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

## Self-check evidence — original implementation at 7a8f886

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

- Quỳnh verified F02/F07/F09/F10 at 7a8f886; their existing threads are resolved.
- F11 is the current remediation; independent verification and GitHub Approve remain required.
- Final-head CI and PR #30 worker/clone/SSE/FE integration remain separate gates.

## F11 — numeric fingerprint remediation

- Source: [F11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32#discussion_r4479665885);
  reproduced on 7a8f886 with a valid Blueprint absolute tolerance of 1e-7.
- Code fix: 1de15d6. Only migration010's JSON number serialization changes:
  precise integer tokens, Python binary64 roundtrip/notation, exponent padding,
  signed underflow, midpoint shortening and pinned float output configuration.
  SHA256, public interfaces, seed/mapping version and worker ownership are unchanged.
- result_for now uses the real Python Blueprint fingerprint, not SQL's expected
  field. The regression rejects a wrong hash without writing either store, then
  verifies persist, lost-response replay, migration replay, retry and full resume.
- AI review follow-up: restore w2_ai_contract.json byte-identically from owner
  handoff 6b0558b (blob 3b0ac5b2117001285b2eb72b37c2c790b6091991). Regenerate
  the UTF-8 SQL receipt; add five offline model/render/key/seed evidence tests.
  The receipt explicitly labels its synthetic slot/version request hash; it is
  not direct GenerationService completed-cache evidence.
- Fresh final author checks:
  - PostgreSQL15 W2 suite: **71 passed, 0 skipped**.
  - PostgreSQL17 W2 suite: **71 passed, 0 skipped**.
  - Full backend + scripts/blueprint: **1084 passed, 341 skipped**,
    19 deprecation warnings. DB/live opt-ins are distinct from the SQL runs above.
  - API/Auth/ownership/mode regression: **77 passed**.
  - Ruff and Mypy passed (91 application source files); git diff --check passed.
- Numeric parity includes nested JSON/Unicode/key ordering, exact large integers,
  notation boundaries, caller GUC changes, underflow/subnormals and a deterministic
  sample of 256 binary64 patterns.
- F11 is author claimed_fixed, pending Quỳnh's independent verification and final
  CI/GitHub Approve. F02/F07/F09/F10 remain reviewer verified. No immutable context
  rewrite, historical backfill, worker/SSE/FE E2E or cloud deployment is claimed.
