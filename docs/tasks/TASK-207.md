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

Clone SQL persistence/record contract is supplied by forward migration 011 (see
the local follow-up below); Python record/adapter/orchestration remain PR #30 work.
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

## Original Clone follow-up — local author handoff, 05/11/2026

- Source of truth: [Quỳnh's integration requirement](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6635728977),
  read live before designing the SQL contract. Mode: author; workflow v0.1
  proposed/docs 506384b. PR #32 base 426ca0c, starting/current Git head 7e9377f;
  these follow-up changes are uncommitted local work, not a new GitHub head.
- Authorized: SQL/RPC/schema, DB tests and contract/handoff docs. No push, merge,
  cloud writes, PR comments or Python worker/adapter/record implementation.
  Three existing untracked Q01/Q02-Q03/TASK204 plans are preserved.
- Root cause: 010 persists full AI QuestionResult only; Original Clone cannot
  supply that record honestly without invented AI request/validation metadata.
- Decision: forward 011, leaving 010 and the base schema unchanged. Reuse
  generation_target_results/version_questions; introduce AI_RESULT/ORIGINAL_CLONE
  discriminator, separate clone_fingerprint and persist_generation_clone.
  AI raw_result bytes and existing writer stay unchanged. Clone source/slot,
  record/display and timestamp commit atomically without quota or AI proof.
- Snapshot/provenance: exact frozen source revision, source/Blueprint IDs, ordered
  batch hash, slot and seed; same record under a new active token can replay.
  A committed success cannot be overwritten. Resume/claim/finish share exact
  current-projection checks, including identity and persisted content/options/key.
- Shuffle boundary: persist original canonical/display values first. PR #30
  sequences shuffle separately with the existing lifecycle; this RPC rejects a
  pre-shuffled payload. Option/key/solution remapping and SSE/FE remain integration
  work, not completed behavior inferred from these SQL tests.

### M3 draft for PR description — prepared locally, not posted

- Scope/output: [011](../../backend/migrations/016_stage2_original_clone.sql),
  [contract](../api/generation-config-endpoint.md#original-clone-persistence-migration-011),
  [actual RPC sample](../../backend/tests/fixtures/w2_clone_rpc_receipt.json),
  [clone tests](../../backend/tests/migrations/test_generation_clone.py), W2 fixture
  adoption and [test instructions](../../backend/tests/migrations/README.md#task-207-w2-generation-rpcs).
- Environment: existing backend image, Python 3.11, asyncpg 0.32.0 from existing
  test artifacts; PostgreSQL15 network-none disposable container. Read-only repo
  mount; separate random task207_case_* database per test. No shared/cloud DB.
- Checks (author self-check on local worktree):
  - `RUN_TASK207_REAL_DB_TESTS=1 TASK207_TEST_DSN=<verified disposable cluster>`
    `python -m pytest backend/tests/migrations/test_generation_clone.py -q`
    — **40 passed, 0 skipped**, including integer-only slot/seed guards to keep
    the replay fingerprint unambiguous.
  - Same opt-in, `python -m pytest backend/tests/migrations/test_generation_w2.py -q`
    — **71 passed, 0 skipped** (AI writer/load/finish, permissions and migration chain).
  - Opt-ins off, `python -m pytest backend/tests scripts/blueprint/tests -q`
    — **1084 passed, 379 skipped**, 19 existing deprecation warnings. DB/live skips
    are not counted as SQL verification; the two explicit runs above supply DB evidence.
    This regression run preceded the final two numeric DB-only cases; those were
    subsequently run in the 40-case real PostgreSQL suite, not inferred from skips.
  - `ruff check backend/app scripts/blueprint backend/tests/migrations/test_generation_clone.py backend/tests/migrations/test_generation_w2.py`
    — passed. `mypy backend/app --ignore-missing-imports` — passed, 91 app files.
    SymPy LaTeX smoke and `git diff --check` — passed.
- Covered: two sources × two versions, supplied/absent solution, unchanged quota,
  missing/wrong/altered projection, fresh connection/retry/token fencing,
  same/conflicting replay, failed-slot replacement, AI success immutability,
  malformed source/payload, roles/GUC spoof, concurrent calls, transaction rollback,
  populated-010 upgrade and repeated 010→011 chain replay.
- [x] SQL/contract and local self-check evidence prepared.
- [ ] Independent review/GitHub Approve and CI on a future pushed head.
- [ ] PR #30 Python record/adapter/worker + shuffle/SSE/FE integration.
- [ ] Deployed Supabase JWT/RLS/PostgREST and live end-to-end validation.

### Copyable response to Quỳnh — not sent

> PR #32 đã bổ sung local migration 011 cho Original Clone theo comment
> 6635728977. Gọi persist_generation_clone(p_session_id, p_job_token,
> p_clone_record) bằng service_role; record ORIGINAL_CLONE lấy nguyên nguồn/slot
> và revision từ frozen context. SQL trả clone_fingerprint riêng, không fake
> QuestionResult/validation/request fingerprint, không tăng quota. Load/claim trả
> result_kind; adapter cần tách clone khỏi AI completed cache. Persist nguyên bản
> trước shuffle; Python record/adapter/worker, shuffle đồng bộ đáp án/lời giải và
> test tích hợp vẫn thuộc PR #30. Contract và mẫu RPC thật có link ở trên.
> Tự kiểm PostgreSQL15: clone40 + W2 71 passed, 0 skipped; chưa push, chưa có
> reviewer xác minh hoặc deployed/SSE/FE E2E. ETA tích hợp chưa được owner xác nhận.

## Generation lifecycle recovery and durable error follow-up — 07/11/2026

- Source of truth: Quỳnh's input requirement for PR #30 stale scanner and durable error recovery
  ([comment 6690592440](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6690592440)).
- Author: Duy (PR #32 SQL boundary); Consumer: Quỳnh (PR #30 worker lifecycle/SSE).
- Workflow v0.1 proposed; base `dev @ 73583d7`, PR #30 @ 8fb6387.
- Scope: Forward migration `017_generation_lifecycle_recovery.sql`, integration test
  `test_generation_lifecycle_recovery.py`, and authoritative contract `docs/api/generation-lifecycle-recovery.md`.
- No modification to existing 005/015/016 migrations; no Python worker/SSE rewrite.

### Key Technical Outputs

1. **Independent Activity Tracking**:
   - `exam_sessions.generation_last_activity_at TIMESTAMPTZ NULL`: Updated strictly on generation claims, quota reservations, result/clone persists, and heartbeats.
   - Metadata title/subject/grade updates do not refresh generation timestamp, preserving 720s cutoff timeout.
2. **Scanner Enumeration**:
   - `list_stale_generation_jobs(p_cutoff_seconds, p_limit, p_after_activity_at, p_after_session_id)` with keyset pagination over `(generation_last_activity_at, id)` backed by partial index `idx_exam_sessions_generation_stale`.
3. **Atomic Fenced Recovery**:
   - `fail_stale_generation_job_if_current(p_session_id, p_expected_job_token, p_cutoff_seconds)` under `SELECT ... FOR UPDATE`. Transitions session to `failed` and records `ERR_GENERATION_INTERRUPTED` atomically; safely returns `recovered: false` on finished or retried tokens.
4. **Durable Error Persistence & Recovery**:
   - `exam_sessions.generation_error_code TEXT NULL` constrained to `^[A-Z0-9_]{3,64}$`.
   - `finish_generation_job_with_error(p_session_id, p_outcome, p_job_token, p_error_code)` records terminal error code.
   - `load_generation_completed_results(p_session_id)` returns `generation_error_code` for terminal SSE stream reconstruction after process reboot.
   - Retry via `claim_generation_job` resets error code to NULL while preserving consumed quota, snapshot context, and committed results.

### M3 draft for PR description — prepared locally

- Scope/output: [017](../../backend/migrations/017_generation_lifecycle_recovery.sql),
  [contract](../api/generation-lifecycle-recovery.md),
  [integration test suite](../../backend/tests/migrations/test_generation_lifecycle_recovery.py).
- Environment: PostgreSQL 15 & 17 isolated disposable cluster; asyncpg 0.32.0.
- Acceptance Checklist (DB boundary):
  - [x] RPC `list_stale_generation_jobs` with keyset pagination, 1..100 limit, and service_role security.
  - [x] Independent `generation_last_activity_at` timestamp & partial index `idx_exam_sessions_generation_stale`.
  - [x] Fenced `fail_stale_generation_job_if_current` re-verifying job token, status, and cutoff under lock.
  - [x] Stale recovery atomically stores `ERR_GENERATION_INTERRUPTED`.
  - [x] `finish_generation_job_with_error` records error code; `load_generation_completed_results` reads back after reboot.
  - [x] Retry clears error code while preserving quota, snapshot context, and committed results.
  - [x] Fresh/upgrade migration replay, ACL/least privilege, and race conditions covered in integration tests.
  - [x] Contract documentation delivered for PR #30 integration.

### Copyable response to Quỳnh — prepared locally

> PR #32 đã bổ sung forward migration 017 hoàn thiện hai phụ thuộc SQL/RPC mà PR #30 đang chờ:
> 1. Stale Scanner: RPC `list_stale_generation_jobs` (keyset pagination, index hỗ trợ, cutoff 720s DB clock) và RPC fencing `fail_stale_generation_job_if_current(p_session_id, p_expected_job_token, p_cutoff_seconds)`.
> 2. Durable Error Recovery: Cột `generation_error_code` lưu bền vững `ERR_GENERATION_INTERRUPTED` khi stale recovery; RPC `finish_generation_job_with_error` để worker ghi nhận mã lỗi thất bại; `load_generation_completed_results` trả kèm mã lỗi sau restart để khôi phục SSE terminal event; retry tự động xóa lỗi cũ nhưng bảo toàn quota và committed results.
> Tài liệu contract chi tiết đã có tại `docs/api/generation-lifecycle-recovery.md` và test suite tại `backend/tests/migrations/test_generation_lifecycle_recovery.py`. Phía Python chỉ cần cắm adapter vào `job_repository.py`.
