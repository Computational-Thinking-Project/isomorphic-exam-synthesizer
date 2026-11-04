# TASK-302 / TASK-301 review RPC contract

**Status: implemented RPC baseline in TASK-302; proposed source-to-AI extension awaiting owner confirmation.**
This copy is published on Duy's TASK-301 branch for discussion on PR #36. It does
not bring TASK-302's SQL into this branch or certify caller integration/deployment.
Hùng owns database operations; Duy owns ReviewRepository/service/API orchestration.
No second lifecycle repository or migration is introduced.

Baseline authority: [TASK-302 contract at a2d2fc3](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/a2d2fc3c31e3bcc4c3acf178d946c83f0a05b37a/docs/api/review-rpc-contract.md).
Preserve that baseline; the proposed additions below are to be adopted into the same
owner-maintained authority after agreement, not maintained as a competing contract.
Unchanged sections describe the pinned SQL baseline, not the implementation status
of this branch. The versioned snapshot and caller trigger are explicitly proposed.

Compared on 2026-11-04: TASK-301 `39083c2`, TASK-302 `a2d2fc3`,
TASK-304 `a8f61d5`, TASK-305 `d7a3d3f`; workflow v0.1 **proposed**
(docs `506384b`). This change is documentation only.

Decisions: [Duy: boundary, auth, Model A, lifecycle and quota](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6546291626),
[Đạt: callback/accounting](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551270882),
[Hùng: recovery and missing persistence](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6593950942),
[Đạt: confirmed artifact consumer](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6594059670),
[Duy: write-boundary proposal](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6604120134).
Historical DB checks: [TASK-302 results at a2d2fc3](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/a2d2fc3c31e3bcc4c3acf178d946c83f0a05b37a/docs/tasks/TASK-302.md).
They do not test the proposed extension below.

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
Only the nine entry points receive the specific grants above. SECURITY DEFINER
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
must belong to the session; the blueprint must have `confirmed_at`. Peers are current candidates
from the same source/session. Acquire/complete reject if those source/blueprint
rows changed after reservation. Neither RPC recomputes a confirmation hash.

<a id="confirmed-artifacts-v1"></a>

### Confirmed artifacts and frozen AI payload — proposed v1

The following proposal answers the remaining PR #36 persistence/snapshot questions.
The per-question hash, canonical document, frozen inputs and fail-closed semantics
match Hùng's proposal and Đạt's consumer confirmation. Revision identifiers, envelope
fields and the trigger in the next section require Hùng/Đạt's explicit response;
this is not a claim that either owner accepted or implemented these additions.

#### P1. Producer and persistence boundary

At the source-confirmation boundary persist the exact validated `SourceQuestion`
input, a per-question fingerprint, an immutable source revision, and authenticated
confirmation actor/time. The existing entry points are
`backend/app/api/routes/sessions.py::confirm_source` and SQL `confirm_exam_source`.
They currently lock/stamp legacy rows;
they do **not** persist these artifacts. Existing `confirmed_at` alone is insufficient.

Use the existing Python expression:

```python
source_fingerprint([source_to_item(SourceQuestion.model_validate(confirmed_input))])
```

`confirmed_input` contains `id, question_text, options[4], correct_answer, solution`.
Map raw_content→question_text, correct_key→correct_answer, solution_md→solution
(NULL solution maps to the model's empty string). Map options in A/B/C/D order,
preserving their text and the corresponding answer association. Persist the exact
validated input used for this expression. Do not sort options, hash only the stem,
replace this with a whole-exam hash, or implement a second SQL hashing algorithm.

The canonical Blueprint producer validates the full 0.4.0 document using
`validate_math_blueprint` against `source_to_item` for that confirmed input, then
persists it with its own immutable revision and the source revision/fingerprint.
Store its schema version. The legacy `question_blueprints` columns produced by
`parser/blueprint_service.py` are not that document. Never reconstruct one from
variables/domains/invariants or call a fallback document canonical.

Source confirmation and later Blueprint publication may use separate short DB
transactions. No AI call runs inside either transaction. If Python prepares an
input/hash before the DB write, the transaction must compare the exact source
content/revision under the parent-session lock and reject a concurrent edit before
recording confirmation. Blueprint publication must likewise reject a superseded
source revision. The server computes/validates artifacts; a client-supplied hash or
validation flag is not confirmation evidence. Regeneration is unavailable until
both artifacts are durably committed and bound to the same revision/hash. This
proposal does not silently redefine the existing Stage 1 HTTP status machine.

#### P2. Revision, storage and invalidation

Persist source JSON, source revision/fingerprint/actor/time, canonical Blueprint
JSON/schema version/Blueprint revision and its source revision/fingerprint binding.
Proposed revision IDs are immutable UUIDs serialized as strings. Physical storage,
column names and DDL are for TASK-302's owner to confirm; `content_hash TEXT` alone
cannot represent all this evidence. Producer implementation ownership outside the
existing W3 assignments still needs Duy's coordination; no new member is assigned here.

Any edit to source ID, stem, options, answer or solution invalidates the old binding
for new work. Reconfirmation creates a new source revision even after edit-and-revert;
a new Blueprint document creates a new Blueprint revision. Keep old artifacts for
audit. Do not introduce an edit API or permit editing locked sessions by implication.
All allowed publication/edit paths serialize with reserve/acquire/complete through
the parent-session lock, and obey approved/exported/non-NULL-approved_at guards.
Acquire/complete reject superseded source/Blueprint revisions; fail/recover may still
settle their active operation and retain charges. Replay of a settled receipt does
not make that historical revision current again or authorize another AI dispatch.

Legacy rows without verified artifacts stay unavailable for regeneration until the
real confirmation/Blueprint producer supplies them. No migration may fabricate a
historical confirmation, reset quota, remove history, or hash at Reject and call it
previously confirmed. Migration filename/order changes require owner agreement;
retain the existing 004/005 → 006 → 007 ordering meanwhile.

#### P3. Proposed reservation snapshot envelope

Keep the existing reservation RPC signature and response identity/lease fields.
On a new reservation, the RPC verifies persisted artifact ownership, validity and
revision/hash binding under the session lock, then freezes this proposed snapshot:

| Field | Required value/meaning |
|---|---|
| `format` | Literal `confirmed_artifacts_v1` (new proposal; baseline is still `database_rows`) |
| `source_revision_id` | Immutable persisted revision of confirmed source input |
| `blueprint_revision_id` | Immutable persisted revision of the validated canonical document |
| `blueprint_source_revision_id` | Stored Blueprint binding; must equal source_revision_id |
| `blueprint_source_fingerprint` | Stored Blueprint binding; must equal source_snapshot.content_hash |
| `source_snapshot` | Exact confirmed input plus content_hash copied from the persisted per-question fingerprint |
| `blueprint` | Full validated canonical 0.4.0 document, with its native source/item identity and context |
| `current_variant` | Reserved candidate with id equal to response question_id and source_question_id equal to source_snapshot.id |
| `peer_variants` | Current candidates of that same source/session in other versions, excluding the reserved candidate and all history |

Candidate IDs and source IDs are canonical UUID strings at the adapter boundary.
Each current/peer contains content/stem_latex and four option strings from one
consistent canonical candidate representation. Any included key/solution must use
that same representation; never pair display options with a canonical answer key.
Mapping operates on copies, without mutating stored arrays or receipt JSON.

The wrapper validates the envelope, retains its revision metadata for reconciliation,
and passes only source_snapshot/blueprint/current_variant/peer_variants plus the
reservation's session_id/question_id/operation_id and injected acquire_attempt to
TASK-304. These revision fields are wrapper metadata, **not new adapter kwargs**.
The existing TargetedRegenerator signature is unchanged. No SELECT of live rows
may replace a missing frozen field. Do not compute a new confirmed hash/Blueprint.
Replayed reservations return the same frozen payload plus operation_status and
settlement; callers must inspect those fields, not discard them into an OK enum
and invoke AI again. An active replay does not authorize a second orchestrator.

#### P4. Failure handling and evidence required for handoff

Before the first permit/provider call, validate format, IDs, revision/hash binding,
canonical schema and current/peer representation. Missing/mismatched input grants
no new permit and dispatches no provider call. Reject unknown/legacy formats for AI;
legacy baseline RPC availability alone does not mean regeneration is ready.

If reserve committed, every later snapshot/mapper/input-validation failure enters
worker failure settlement with the original operation ID and a sanitized code.
Cancellation remains cancellation after best-effort settlement; recovery handles
unfinished operations. Missing report/solution or invalid candidate output is also
a completion failure, never grounds to synthesize is_valid/math_verified/checks.
Keep TASK-304's actual validation report/checks/warnings and teacher-review flag.
Zero newly acknowledged calls does not mean zero charged calls in the operation
or session. Never refund committed permits; reconcile transport uncertainty using
the same identity, without creating new work to bypass an unknown outcome.

Keep existing adapter/domain errors (SOURCE_NOT_CONFIRMED, BLUEPRINT_INVALID,
PREVIOUS_VARIANT_MISMATCH, REVIEW_SOURCE_MISMATCH and other validator codes).
HTTP mapping of any new wrapper-specific format/revision error must be recorded
with the caller implementation before rollout; this document introduces no new
SQL error code. Never expose raw SQL/provider exception text.

Handoff must include JSON **emitted by the real reservation RPC**, not a hand-built
payload presented as DB evidence: one valid source/Blueprint pair, plus fixtures
for missing artifacts, wrong revision/hash, invalid Blueprint and candidate/peer
identity mismatch. Test real TASK-304 adapter with a fake provider: valid dispatch,
invalid input before acquire, settlement after reserve, unchanged frozen replay,
source/Blueprint edits after reserve and canonical mapping after shuffle. DB tests
must cover publication/reserve races, superseded-operation denial and content lock.
Use independent DB connections for concurrency and the actual JWT/worker ACL split.

Deploy storage and producer support, then reservation support, then strict callers;
drain old writers before enabling dispatch. Keep legacy format explicit until cutover;
do not downgrade or pretend old rows are v1. No superseded receipt is rewritten.
The baseline 57 DB tests and earlier caller mock suites do not establish these new
requirements. Producer, storage, RPC and caller integration remain pending.

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

<a id="recovery-trigger"></a>

### Restart-safe recovery discovery — F06

**Proposed caller trigger (R1):** retain read-only GET progress/list. Validate request
IDs/idempotency key, authenticate the owner and verify question/session ownership
before any worker operation. Apply existing session guards. Before each new Reject
reservation, call worker review_recover_session(session_id), including retry of the
stale question itself rather than only a SESSION_BUSY branch for another question.
An unexpired operation stays busy. Retained operation IDs are reconciled from the
receipt before any redispatch; replay never starts a second AI orchestration.

Unavailable/denied/malformed recovery stops new work with a sanitized availability
error. There is no ledger SELECT, inferred operation UUID, direct-write fallback,
or new table grant. Offline fixtures require explicit injection; a missing RPC
method must not activate them implicitly. After a lost recovery response, retry
the same session: zero new recoveries is valid and does not disprove earlier recovery.

This is lazy recovery on Reject, not a scheduled worker: idle progress may continue
to show regenerating after 180 seconds. It replaces the earlier proposed recovery
on GET in #28, subject to owner confirmation. Final approval continues to reject an
active operation; this does not add hidden recovery to approve or matrix reads.
Public-route tests must cover stale same-question retry, unexpired operations,
worker unavailable, repeated/lost-response recovery, cancellation and late completion.
SQL discovery is already implemented in #36; the full caller trigger is still pending.


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

Supabase rollout, live JWT/RLS, live AI, caller/adapter E2E and shuffle integration
are not yet verified. TASK-301 at 39083c2 calls session recovery on one busy branch; the proposed
pre-reservation trigger and strict fallback gating still need implementation.
These SQL tests do not certify the caller or the proposed artifact contract.


## TASK-301 caller implementation handoff — 2026-11-04

This is caller work in progress, not owner acceptance of the proposed storage/envelope
or deployed integration. SQL signatures remain those of pinned TASK-302 a2d2fc3.
Owner/worker RPC results are parsed as typed receipts, including replay/settlement;
the caller no longer constructs source snapshots or confirmation hashes from live rows.
Baseline database_rows is unavailable for provider dispatch and is failure-settled.
Proposed confirmed_artifacts_v1 parsing is preparatory until producer/RPC handoff.

### HTTP action keys and error behavior

POST accept/revert now accept the same optional UUID Idempotency-Key header as Reject.
Invalid resource/key UUIDs return 400 before handler queries. With a supplied key,
the SQL receipt is checked before its mutation edit guard; a committed replay may be
read after approval, while a new mutation stays locked. The same key cannot bind to
another question/session/action. Without a key the server creates an invocation ID;
separate HTTP requests without a retained key are separate actions.

An active Reject replay returns 409 without dispatching another generator. Completed
replay reads the committed candidate; failed/recovered replay returns 409 and requires
a deliberate new key for new work. Receipt expiry is not reinterpreted using worker
time: DB acquire/complete owns lease validity. Response projection reads may reflect
later state; idempotency guarantees effects, not byte-identical JSON after later writes.

Malformed/identity-mismatched/uncertain RPC results and post-commit read failures return
sanitized availability errors (503). Completion retry retains exactly the operation ID
and validated payload. Source/input/output validation is 422; missing adapter is 503
before reserving or charging; timeout is 504; permit uncertain/invalid keeps existing
502 mapping. Failure RPC receives only a sanitized code, never raw exception text or a
client refund count. A cancelled invocation propagates cancellation after best-effort
settlement. Read failure after commit never initiates a rollback.

### Remaining progress interface decision

The HTTP contract includes unapproved_question_ids, but baseline review_get_progress
returns counts only. Proposed additive field: progress.unapproved_question_ids, UUID
array of current unapproved candidates produced in the same SQL snapshot as counts.
TASK-302 owner confirmation/implementation is still required. The caller checks the
array's uniqueness and cardinality against current_slots-approved_slots. Without this
field, an empty array is only inferred when that difference is zero; otherwise it
returns ERR_PROGRESS_DETAILS_UNAVAILABLE (503), not a fabricated empty list. This safe
failure does not complete the pending progress feature.

The caller retains busy-trigger recovery using review_recover_session and read-only
GET progress. Proposed R1 before every reservation remains awaiting acknowledgement.
No new RPC, table-write fallback, ledger SELECT grant or alternative SQL is introduced.

### Evidence and remaining acceptance

141 local caller/receipt tests pass with actual Python boundaries, explicit fake RPC
fixtures and stubbed scheduling. They cover typed permits, lost responses, replay,
settlement, validation, cancellation, direct handlers and OpenAPI keys. They do not
measure actual DB pool use, locks or concurrency, execute ASGI/JWT, or establish
producer/storage/adapter integration. 765 backend/Blueprint tests collect successfully;
collection is not execution. Full async local execution remains unverified after the
requested unrestricted run was declined. Required CI and PostgreSQL integration are
still mandatory before Ready/merge; no checks are exempted.

### Reservation response uncertainty — caller handoff

The caller retries an unavailable/malformed reservation response at most three
times with exactly the original session/question/operation IDs. A validated active
replay is not permission to dispatch or failure-settle: another request with that
key may be running. It returns409; unresolved responses return sanitized503
ERR_RESERVATION_UNCERTAIN. Only a validated newly active receipt starts generation.
No private-ledger lookup or inferred receipt/operation ID is introduced. Recovery
of a crash/unknown active operation still uses the worker RPC and DB lease.
This caller behavior does not imply acceptance of proposed P1–P4/R1.
