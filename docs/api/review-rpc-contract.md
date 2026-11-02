# TASK-302 / TASK-301 review RPC contract

**Database implementation available on this branch; not deployed, integrated or approved.**
Migration `006_stage3_review_and_shuffle.sql` contains the schema, private ledger
and RPCs below. Hùng owns these database operations; Duy owns the existing
ReviewRepository/service/API callers. No parallel repository is introduced.

Decisions: [Duy: boundary, auth, Model A, lifecycle and quota](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6546291626),
[Đạt: callback and accounting](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551270882),
[adapter handoff](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551386372).
Compared on 2026-11-02 against TASK-301 `a4dd03b`, TASK-305 `8e04613`,
TASK-304 `a8f61d5`, and dev `ada2963` (including TASK-303/306).
Database tests and remaining integration work are recorded in [TASK-302](../tasks/TASK-302.md).

## Interface and authorization — F02/C03

Parameters carry the `p_` prefix in PostgreSQL. IDs are UUID, times TIMESTAMPTZ,
payloads/results JSONB. Each mutation is one short transaction; AI runs outside it.

| RPC | Parameters after `p_` | Allowed caller | Main result |
|---|---|---|---|
| `review_reserve_regeneration` | `session_id UUID, question_id UUID, operation_id UUID` | Owner JWT | `operation_id, question_id, expires_at, max_attempts, snapshot, operation_status` |
| `review_acquire_attempt` | `operation_id UUID, attempt_id UUID` | Worker | The six-field permit below |
| `review_complete_regeneration` | `operation_id UUID, candidate JSONB` | Worker | `operation_id, previous_question_id, question_id, api_calls_used, invalidated_version_ids, progress` |
| `review_fail_regeneration` | `operation_id UUID, error_code TEXT` | Worker | `operation_id, question_id, api_calls_used, operation_status, recovered, progress` |
| `review_recover_regeneration` | `operation_id UUID` | Worker | `operation_id, question_id, api_calls_used, operation_status, recovered`; settled recovery also includes `progress` |
| `review_accept_question` | `session_id UUID, question_id UUID, action_id UUID` | Owner JWT | `previous_question_id, question_id, question_status, invalidated_version_ids, progress` |
| `review_revert_question` | Same as accept | Owner JWT | Same as accept |
| `review_get_progress` | `session_id UUID` | Owner JWT | `progress` |

Except the permit, results include `session_id, session_status, replayed`.
Owner calls require the authenticated role and derive the audit actor from
`auth.uid()`, then check ownership inside the transaction. Worker calls require
`service_role` EXECUTE privileges and the service-role claim. Their actor is the
authenticated creator stored in the operation, never an actor supplied in a request.
Worker functions are unavailable to authenticated/anon; owner functions are not
granted to service_role. Use separate JWT and worker clients in the wrapper.

The three new tables (`review_operations`, `review_attempts`,
`review_action_receipts`) have RLS enabled and no direct grants to any API role,
including service_role. Internal `_review_*` helpers have no API-role EXECUTE.
Only the eight entry points receive the specific grants above. SECURITY DEFINER
functions pin their search path and qualify application tables.

## Durable permit callback — F07

The TASK-304 callable takes these keyword arguments in addition to its snapshots:

```python
operation_id: UUID
acquire_attempt: Callable[[UUID, UUID], Awaitable[AttemptPermit]]
```

`review_acquire_attempt` returns exactly:

```json
{
  "operation_id": "<uuid>",
  "attempt_id": "<uuid>",
  "dispatch_permitted": true,
  "calls_used": 27,
  "remaining_calls": 3,
  "replayed": false
}
```

The wrapper constructs TASK-304's strict `AttemptPermit`; do not pass a raw dict
to that adapter. Counts are session-wide integers and booleans are JSON booleans.
Permit denial returns `dispatch_permitted=false, replayed=false`, not an exception.
Replay returns `dispatch_permitted=false, replayed=true` with the stored counts;
it never authorizes another provider request. Rebinding an attempt ID to another
operation is an idempotency conflict. Unknown operations are not inferred from
some other regenerating question.

Policy confirmed by Duy/Đạt: 30 charged permits/session, at most four granted
permits/operation, including errors/repair/retries. Reserve charges **zero** calls.
Each initial grant atomically inserts its receipt and increments the session
counter under the session lock. A denial does not increment it. Legacy counter
values are carried forward; never reset them or replace them with SUM(new ledger).

The adapter requests a permit at its existing gateway boundary, after waiting for
capacity/key and immediately before transport. A new provider attempt uses a new
attempt UUID. RPC transport retries retain the original IDs. After an uncertain
permit response or replay the adapter stops; the wrapper reconciles rather than
obtaining a new ID to bypass uncertainty. Provider automatic retries remain disabled.

**Lost-response accounting:** a committed grant stays charged even if no provider
request was sent, or if the adapter never received the grant. This is conservative
permit accounting, not exact provider-call measurement. `api_calls_count` reports
acknowledged grants for that invocation. A normal successful completion must match
the operation's granted ledger count; a mismatch rejects completion without losing
the current candidate. Failure, cancellation and recovery do **not** accept a client
count: they settle from the ledger, so acknowledged=0/committed=1 still records one.
There is no fixed-four refund or refund based on an adapter exception's count.
Zero-call fixtures are for explicitly injected mocks; production must not silently
fall back to a mock or local-only budget.

## Operation ownership, snapshots and settlement

Reserve records the initiating actor, current candidate, prior review status and a
180-second DB-clock expiry. It leaves that candidate current, marks it regenerating,
and sets session status generated. The partial active-operation index enforces
Model A: one active regeneration/session. Other-slot accepts remain allowed.

The returned `snapshot` has `format="database_rows"` and frozen
`source_snapshot, blueprint, current_variant, peer_variants`. Source/blueprint rows
must belong to the session and have `confirmed_at`; peers are current candidates
from the same source/session. Acquire/complete reject if those source/blueprint
rows changed after reservation. Neither RPC recomputes a confirmation hash.

**Source-to-AI handoff still required:** the current baseline persists legacy
blueprint columns and no confirmed `source_fingerprint` field. A database row is
not TASK-304's canonical blueprint 0.4.0 or its required confirmed hash. Duy's mapper
must obtain those from the actual confirmed pipeline/storage contract, map field
aliases/options and fail closed when missing. Do not recompute a hash at reject
and label it confirmed, or feed legacy variables/domains as a canonical blueprint.
TASK-302 does not silently invent new source-storage columns or change ingestion.
This snapshot boundary clarification requires acknowledgement during integration.

Complete accepts TASK-304's `RegeneratedVariantResult`: `stem_latex`, four distinct
nonempty option strings, `correct_key` A–D, nonempty `solution_md`, validation report,
and integer `api_calls_count` 0–4. Optional `content` must equal `stem_latex`.
`validation_report.is_valid` and `requires_teacher_review` must be true;
`math_verified` is a boolean and warnings/checks arrays. Database checks enforce
shape and ledger consistency, not independent mathematical correctness or the full
Python validator's normalization. The caller still validates with TASK-304's model.

Completion atomically demotes the old candidate, inserts a new pending-review
candidate with its own canonical snapshot and stable canonical slot, writes audit,
invalidates all session versions, and settles the operation. Fail/recover restore
the reserved candidate's prior status and close only that operation without refund.
Fail takes only a sanitized code (`^[A-Z][A-Z0-9_]{0,79}$`), never provider exception
text. Recovery uses DB time; before expiry it returns `recovered=false` without
writes. A recovered operation cannot complete late or mutate a new reservation.

All writers lock parent session before operation/candidate rows. New mutations
reject approved/exported sessions or a non-NULL approved_at. Existing committed
receipts may be read back after approval, without another mutation. Reusing IDs
with different input is rejected; exact retries return stored results and
`replayed=true`. Reserve replay also returns current `operation_status` and stored
`settlement` for reconciliation. Receipt state describes that committed operation,
not necessarily the latest session state; refresh progress when needed.

## Revert, readiness and finalization — C01/C02

Reject remains binary. Revert follows the current candidate's lineage to its first
candidate, requiring the same version/source throughout; broken/cyclic lineage is
rejected. Restore that original as current/approved without rewriting canonical
fields. Reverting the first candidate acts as idempotent approval, without copying
a row. Repeated accept/revert does not create duplicate audit for an unchanged action.

Successful replacement/revert-to-another-row invalidates **all session versions**:
`is_finalized=false`, NULL seed/permutations, deletion of stale answer keys in the
same transaction. Failure or reserve alone does not alter the old display output.
This session-wide scope and canonical/display persistence policy were confirmed by
[Tâm](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6555305930).
The aliases remain those supported by #24. Actual persistence/shuffle E2E remains unverified.

Accept/revert/complete/fail/recover recalculate readiness inside their transaction.
It requires exactly one configuration, confirmed sources, the configured number
of distinct version codes, one current per expected source/version slot, all approved,
no extraneous slots and no active operation. Missing rows cannot disappear from
the denominator. Progress GET uses a shared parent lock for a consistent read and
does not recover or change lifecycle state.

`progress` contains `expected_slots, current_slots, approved_slots,
regenerating_slots, missing_slots, duplicate_slots` (integers) and `ready` (boolean).
Mutation recalculation sets reviewed only when ready; otherwise generated.

**TASK-305 boundary:** final approval must acquire the same session row lock and
check complete readiness/no active operation plus finalization within that database
transaction. SQL 007 at `8e04613` already locks that row, but must also fail closed
on missing/ambiguous configuration and align with 006's operation/readiness checks.
A Python read followed by a separate CAS is not proof of this boundary.
This PR does not implement or certify TASK-305's final approval writer. Existing
direct table mutation paths must be replaced by the agreed RPCs before production
integration; these RPC tests do not certify the old repository or shuffle callers.

## Error mapping and rollout

The RPC raises a sanitized domain code as its message:
`REVIEW_NOT_FOUND` (SQLSTATE P0002) → 404, including wrong-owner calls;
`REVIEW_STALE` / `REVIEW_BUSY` (55000) and `REVIEW_IDEMPOTENCY_CONFLICT` (22023) → 409;
`REVIEW_LOCKED` (55000) → 423; `REVIEW_QUOTA_EXHAUSTED` (54000) → 429;
`REVIEW_INVALID_PAYLOAD` / `REVIEW_SOURCE_MISMATCH` (22023) → 422.
ACL/worker-role failure is 42501. Duy maps domain codes in the service; SQLSTATE
alone cannot distinguish all HTTP cases. Do not return raw SQL/transport exceptions.
Adapter permit-invalid/uncertain HTTP behavior remains its existing 502 mapping.

Any required write failing rolls back that RPC transaction. A previously committed
permit stays charged. Transport failure does not prove rollback: reconcile using
the same IDs. No source overwrite, history deletion, quota reset, or fake actor
backfill is part of recovery or rollout. Drain old workers before cutover; legacy
regenerating rows without a ledger operation require verified operator handling,
not a fabricated operation/actor or blind automated refund.

Apply with `psql -v ON_ERROR_STOP=1 -f backend/migrations/006_stage3_review_and_shuffle.sql`.
Replay preserves receipts and permissions. The migration owner keeps this filename;
there must not be a second 006 under `006_stage3_review_rpc.sql`. Integration order:
004/005 (#32) → 006 (#36) → 007 (#33). Duy has acknowledged the ordering and historical
actor policy in his [completed response](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6567937686).

**Competing 008:** #28 at `a4dd03b` creates a different `review_attempts` shape and
replaces `review_acquire_attempt` with different authorization/lifecycle behavior.
Do not apply it after 006 or maintain both implementations. TASK-301 must remove the
competing implementation and use these RPCs, as requested in the
[coordination comment](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6568374582).
If 008 has already been applied to a shared database, report its schema/ledger state
before rollout so the migration owner can provide a data-preserving transition.
006 detects the incompatible attempt ledger and stops without rewriting it or
resetting quota. That guard is not a conversion script or a certificate of deployed compatibility.

Supabase rollout, live JWT/RLS, live AI, caller/adapter E2E and shuffle integration
are not yet verified. TASK-301's acquire wrapper now calls an RPC, but still needs
strict response validation and conversion of the remaining direct lifecycle writes.
