# TASK-302 / TASK-301 review RPC contract

**Database implementation available on this branch; not deployed, integrated or approved.**
Migration `006_stage3_review_and_shuffle.sql` contains the schema, private ledger
and RPCs below. Hùng owns these database operations; Duy owns the existing
ReviewRepository/service/API callers. No parallel repository is introduced.

Decisions: [Duy: boundary, auth, Model A, lifecycle and quota](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6546291626),
[Đạt: callback and accounting](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551270882),
[adapter handoff](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551386372).
Compared on 2026-11-04 against TASK-301 `68b375f`, TASK-305 `d7a3d3f`,
TASK-207a/b `31ed3bc`, TASK-304 `a8f61d5`, and dev `ac18e72`.
Database tests and remaining integration work are recorded in [TASK-302](../tasks/TASK-302.md).

**Publication checkpoint, 2026-11-04:** the independently checked artifact baseline
below is TASK-301 `68b375f`. Duy subsequently delivered
[TASK-301 `553a009`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#issuecomment-6624727072),
including receipt lookup, independent confirmation bootstrap, producer lease/retry
and caller recovery. Those changes are author-reported, not yet adopted or
independently verified on this branch. In particular, this checkpoint still uses
the legacy confirmation bootstrap and has no producer lease/status RPCs. Do not
combine these two versions of 006 or deploy this checkpoint with the latest caller
until TASK-302 reconciles the SQL/contract and verifies the combined head.

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
| `review_recover_session` | `session_id UUID` | Worker | `session_id, session_status, recovered_count, recoveries` |
| `review_accept_question` | `session_id UUID, question_id UUID, action_id UUID` | Owner JWT | `previous_question_id, question_id, question_status, invalidated_version_ids, progress` |
| `review_revert_question` | Same as accept | Owner JWT | Same as accept |
| `review_get_progress` | `session_id UUID` | Owner JWT | `progress` |

Except the permit and session recovery, results include `session_id, session_status, replayed`.
Owner calls require the authenticated role and derive the audit actor from
`auth.uid()`, then check ownership inside the transaction. Worker calls require
`service_role` EXECUTE privileges and the service-role claim. Their actor is the
authenticated creator stored in the operation, never an actor supplied in a request.
Worker functions are unavailable to authenticated/anon; owner functions are not
granted to service_role. Use separate JWT and worker clients in the wrapper.

The three new tables (`review_operations`, `review_attempts`,
`review_action_receipts`) have RLS enabled and no direct grants to any API role,
including service_role. Internal `_review_*` helpers have no API-role EXECUTE.
Only the nine review entry points receive the specific grants above; the three
artifact entry points have the separate grants below. SECURITY DEFINER
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

## Confirmed artifacts - database authority (P1-P4)

TASK-302 adopts the storage/protocol proposed by Duy in
[TASK-301 `68b375f`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/commit/68b375f6fddfc9085dff9be4f2a73c3fa5a7c45d),
following [Duy's producer ownership confirmation](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6621050876)
and [Dat's consumer contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6594059670).
These are implemented locally in 006, not deployed. Duy owns Python producer,
public confirmation/background/resume and ReviewRepository/service integration.
This document is DB authority; a matching mapper does not establish HTTP E2E.

| RPC | Parameters after `p_` | Caller / result |
|---|---|---|
| `confirm_source_artifacts` | `session_id UUID, actor_id UUID, confirmation_id UUID, expected_updated_at TIMESTAMPTZ, sources JSONB` | Worker; confirmation receipt with actor/time, sources, legacy Stage 1 status |
| `publish_canonical_blueprint` | `session_id UUID, publication JSONB` | Worker; source/Blueprint revision IDs, replayed |
| `get_source_artifacts` | `session_id UUID` | Owner JWT or worker; confirmation, pending_source_question_ids, ready; read only |

Private, RLS-enabled tables with no API-role grants (including service_role):
`source_artifact_confirmations` stores owner-derived actor, DB time and durable receipt;
`source_artifact_revisions` stores exact confirmed input and per-question fingerprint;
`canonical_blueprint_revisions` stores full canonical JSON/schema and its source revision;
`source_artifact_heads` selects current source/Blueprint revisions. IDs are UUID strings.
History survives source deletion and cascades only with its session. No legacy backfill.
Only the three entry points above receive grants; `_artifact_*`/snapshot helpers are private.

Each `sources` entry contains `source_question_id, source_revision_id, confirmed_input,
source_fingerprint`. Input is exactly `id, question_text, options[4], correct_answer,
solution`; map raw_content -> question_text, correct_key -> correct_answer,
solution_md NULL -> empty solution. Object options map in A/B/C/D order.
The backend derives actor from verified HTTP identity; never expose worker hash/actor
parameters directly to clients. Under the session lock, confirmation checks ownership,
draft/updated_at, whole source set and exact live content before calling the existing
`confirm_exam_source` (003). Both legacy confirmation and revision writes are atomic.
Confirmation replay compares source content/fingerprints, ignoring newly proposed revision
IDs, and returns the original committed revisions. Producers must use returned IDs.

Only the production Python expression computes the fingerprint:
`source_fingerprint([source_to_item(SourceQuestion.model_validate(confirmed_input))])`.
It covers one question's canonical source and extraction context; it is not the
whole-exam hash. SQL stores/compares this evidence, without another hashing algorithm.
Full 0.4.0 schema/semantic validation is the trusted Python producer's responsibility
(`prepare_blueprint_artifact`); SQL checks structure/version, exact source/hash and FK
binding. API roles cannot directly insert artifacts or assert validation themselves.
The strict caller independently verifies hash/schema before the first permit.

Publication contains `source_question_id, source_revision_id, source_fingerprint,
blueprint_revision_id, schema_version="0.4.0", canonical_blueprint`. Extract outside
DB transactions. Publish only against the still-current confirmed revision/content.
A new Blueprint gets a new UUID. Same-ID/same-body replay is read only, including
after invalidation/locking; it never repoints heads. Different payload -> idempotency
conflict. Source edits (including number/missing-answer changes) delete the head and
clear legacy confirmed_at; edit-and-revert does not revive it. Source changes also
demote reviewed -> generated, preserving approval 007's state gate under the same
lock. This adds no Stage 1 edit API or draft transition. Inserts/deletes also
serialize through the session lock. Approved/exported/non-NULL-approved_at content
is locked. All writers must lock the parent before child DML; row triggers are a
final guard, not a substitute for transaction lock order.

### Frozen reservation envelope

| Snapshot field | Meaning |
|---|---|
| `format` | Literal `confirmed_artifacts_v1` |
| `source_revision_id` | Current persisted confirmed source revision |
| `blueprint_revision_id` | Current persisted canonical Blueprint revision |
| `blueprint_source_revision_id` | Stored Blueprint source binding, equals source_revision_id |
| `blueprint_source_fingerprint` | Stored binding fingerprint, equals source_snapshot.content_hash |
| `source_snapshot` | Exact confirmed input plus persisted per-question content_hash |
| `blueprint` | Full canonical 0.4.0 document, unchanged |
| `current_variant` | id = reserved question_id, version_id, source_question_id = source_snapshot.id, content/stem_latex, canonical options/correct_key/solution_md |
| `peer_variants` | Same representation; current candidates for this source in other session versions, sorted by UUID; no history/reserved version |

The whole confirmed source set must still match and all canonical publications must
be ready. Missing/stale artifacts raise `REVIEW_SOURCE_MISMATCH` before reserve;
no live-row substitution or legacy downgrade. Current/peer options, answer and
solution come from one canonical candidate; NULL canonical solution stays NULL,
never replaced with the shuffled display solution. version_id is required by Duy's
strict mapper for distinct-peer-version validation. Mapping works on detached copies.

Acquire/complete compare persisted revisions/hash/document/source/current candidate
to the frozen snapshot under the parent lock. New publication supersedes an active
operation even for an identical body. Peers remain frozen; another slot's permitted
accept/revert does not rewrite them or the receipt. A grant committed before
supersession stays charged; later permits/completion fail and worker fail/recover
settles the original operation. A settled replay never authorizes another dispatch.

Pass only source_snapshot/blueprint/current_variant/peer_variants and the existing
session_id/question_id/operation_id/acquire_attempt to TASK-304. Revision fields
are wrapper metadata, not new adapter kwargs. Before permit/provider, reject missing
fields, invalid hash/revision/schema and current/peer identity mismatch. After a
successful reserve, any mapper/input/validation failure must best-effort settle the
original operation with a sanitized error; recovery closes unfinished work. Never
synthesize solution/report/checks or math verification to force completion.

Storage errors use `ARTIFACT_NOT_FOUND`, `ARTIFACT_WORKER_REQUIRED`,
`ARTIFACT_OWNER_MISMATCH`, `ARTIFACT_INVALID_PAYLOAD`, `ARTIFACT_SOURCE_MISMATCH`,
`ARTIFACT_IDEMPOTENCY_CONFLICT`, `ARTIFACT_STALE`, `ARTIFACT_LOCKED`. Review snapshot
failure retains `REVIEW_SOURCE_MISMATCH`; caller `frozen_inputs` at `68b375f` maps
invalid frozen evidence to HTTP 422 `ERR_SOURCE_NOT_CONFIRMED`. Duy must map artifact
producer errors at the public boundary; do not expose raw SQL/provider exceptions.

### Caller recovery order (R1)

Adopt worker `review_recover_session(session_id)` before **every new Reject
reservation**, after ownership/session guards, including a retry of the caller's
own regenerating question. GET progress remains read only. Existing-ID replays
must reconcile operation_status/settlement before dispatch; an active replay does
not authorize a second orchestrator. This is lazy recovery, with no automatic
180-second scheduler. SQL supports it; wiring was pending at `68b375f`.
Duy reports it implemented at `553a009`; adoption/verification remains pending here.
Deploy 003/004/005/006 storage and producer, then reservation/strict callers; drain
old writers before dispatch. Never rewrite old receipts to claim v1 compatibility.

## Operation ownership, snapshots and settlement

Reserve records the initiating actor, current candidate, prior review status and a
180-second DB-clock expiry. It leaves that candidate current, marks it regenerating,
and sets session status generated. The partial active-operation index enforces
Model A: one active regeneration/session. Other-slot accepts remain allowed.

New reservations return `format="confirmed_artifacts_v1"` as specified below.
Missing artifacts fail before operation creation or charge. Acquire/complete check
current source/Blueprint revision bindings and the canonical reserved candidate;
fail/recover can settle superseded operations without refund. Historical receipts,
including `database_rows`, remain unchanged/replayable but cannot authorize new AI
work. No hash or canonical Blueprint is fabricated during reserve or migration.

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

### Restart-safe recovery discovery — F06

When only the session ID survives a worker restart, call
`review_recover_session(p_session_id)` using the worker client. Do not SELECT the
private ledger or infer an operation UUID from a question's `regeneration_id`.
This RPC locks the session first, discovers its expired active operation using
the database clock, then settles it through the same failure helper in that
transaction. Model A permits at most one active operation per session.

```json
{
  "session_id": "<uuid>",
  "session_status": "generated",
  "recovered_count": 0,
  "recoveries": []
}
```

For a successful recovery, `recoveries` contains the full
`review_recover_regeneration` settlement object, including the actual operation ID,
ledger-based `api_calls_used`, and progress. The audit uses the actor stored in
the reservation. `recovered_count` counts operations
settled by **this call**, not historical recoveries; it is 0 or 1 and equals the
array length. An empty, unexpired or already settled session returns 0 and `[]`
without audit/state/quota writes. Retrying after a lost successful response also
returns 0; it does not replay the earlier recovery as a new event. A caller that
retained the operation ID can use operation recovery to replay its receipt.
Unknown sessions raise `REVIEW_NOT_FOUND`. Authorization is worker-only even
for a no-op. Audit failure rolls back settlement so a subsequent call can retry;
concurrent recovery paths cannot duplicate audit or refund committed grants.

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
transaction. The pinned 004/005 at `31ed3bc` and 007 at `d7a3d3f` are tested with
006 on fresh and upgraded databases: charged-receipt replay, recovery followed by
approval, approval denial during an active operation, and review mutation denial
after approval. This verifies those paths, not all possible TASK-305 writer inputs.
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

**Competing 008:** Duy [confirmed it was never applied to shared Supabase Cloud
and removed it from #28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6568707780).
Do not apply the old competing implementation after 006 or maintain both.
006 detects the incompatible attempt ledger and stops without rewriting it or
resetting quota. That guard is not a conversion script or a certificate of deployed compatibility.

Supabase rollout, live JWT/RLS/AI, public HTTP/background E2E and shuffle-writer
integration are not yet verified. The pinned mapper/adapter can be checked with
an actual RPC fixture and offline provider (see the migration-test README). This
does not certify the public caller, including recovery before every new Reject.

## Progress IDs and compatibility

New progress results include `unapproved_question_ids`: UUIDs of all current
non-approved candidates, including regenerating, sorted by UUID in the same
transaction as slot counts. Its length equals current_slots - approved_slots,
including extra/duplicate current rows if corruption exists. When v1 confirmation
exists, a changed source set or pending publication also makes
ready=false, even if every surviving candidate is approved. Legacy-only sessions
retain their existing confirmation/readiness path; regeneration still requires v1.
An invalid confirmation does not block settlement of an old operation.
Historical action/settlement receipts keep their original progress JSON; clients
needing current IDs must GET progress, never invent [] for an absent field.
