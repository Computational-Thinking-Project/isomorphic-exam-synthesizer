# TASK-302 / TASK-301 review RPC contract

**Proposed; not implemented or agreed.** This is the TASK-302 database interface
proposal for discussion on its Draft PR. Migration 006 supplies only schema
foundations; it does not create these RPCs, an operation ledger, or attempt records.
Hùng owns the database implementation proposal; Duy owns lifecycle/API integration.
Changes require the affected owners' explicit response before implementation.

References: [TASK-302 plan](../tasks/TASK-302.md),
[open handoff on #28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28#issuecomment-6544415727).
Compared against #28 `4db0869`, #24 `0016b2a`, and #26 `0a3e5e5` on 31/10/2026.
Those PRs remain separate implementations, not integrated-test evidence.

## Calls and authorization — F02/C03, pending Duy

Proposed split: the existing ReviewRepository becomes the caller of database RPCs;
TASK-302 does not create a second review repository. Each call is one short
transaction. No transaction stays open during an AI request.

All parameters below have the `p_` prefix in PostgreSQL. IDs are UUIDs, times are
TIMESTAMPTZ, and each RPC returns one JSONB object. JWT calls derive the actor from
`auth.uid()` and verify session ownership; no client-supplied actor is accepted.
Worker calls are executable only by `service_role`, with PUBLIC/anon/authenticated
EXECUTE revoked. Their audit actor comes from the authenticated operation creator
persisted during reservation, never a sentinel or an arbitrary request field.
This mixed JWT/worker arrangement is a proposal requiring Duy's confirmation.

| RPC name | Parameters (after `p_`) | Caller | Result in addition to common fields |
|---|---|---|---|
| `review_reserve_regeneration` | `session_id UUID, question_id UUID, operation_id UUID` | Owner JWT | `operation_id, question_id, expires_at, max_attempts, snapshot` |
| `review_acquire_attempt` | `operation_id UUID, attempt_id UUID` | Worker | `operation_id, attempt_id, dispatch_permitted BOOLEAN, calls_used, remaining_calls` |
| `review_complete_regeneration` | `operation_id UUID, candidate JSONB` | Worker | `operation_id, previous_question_id, question_id, api_calls_used, invalidated_version_ids` |
| `review_fail_regeneration` | `operation_id UUID, error_code TEXT` | Worker | `operation_id, question_id, api_calls_used, operation_status` |
| `review_recover_regeneration` | `operation_id UUID` | Worker | Same as fail, plus `recovered BOOLEAN` |
| `review_accept_question` | `session_id UUID, question_id UUID, action_id UUID` | Owner JWT | `question_id, question_status, progress` |
| `review_revert_question` | `session_id UUID, question_id UUID, action_id UUID` | Owner JWT | `previous_question_id, question_id, invalidated_version_ids, progress` |
| `review_get_progress` | `session_id UUID` | Owner JWT | `progress` (read-only) |

Common success fields: `session_id UUID, session_status TEXT, replayed BOOLEAN`.
For progress reads, `replayed=false`. Mutation IDs are generated once by the caller
and retained across transport retries. An identical ID/input returns the stored
outcome without duplicate effects; an ID reused with different input is a conflict.
`dispatch_permitted` is true only for the initial acquisition: a replay must never
authorize dispatching the same attempt twice. A lost acquisition response therefore
does not permit an automatic redispatch; quota uncertainty is covered below.

All writes lock session then relevant candidate/operation rows in a consistent
order, verify membership/current identity, and reject approved/locked sessions.
Completion/failure/recovery must verify the operation still owns the reserved
candidate; an expired worker must not overwrite a recovered/new operation.
Recovery uses database time and the existing proposed 180-second stale interval.
An unexpired operation returns `recovered=false` without writes.

## Reservation and candidate payload — F02/F03/F05/F06, pending Duy

Reservation preserves the current candidate while marking it regenerating and
records its prior status, initiating actor, lease and operation identity. It returns
`max_attempts=4` and the frozen adapter inputs:
`source_snapshot, blueprint, current_variant, peer_variants`. Sources/blueprints
must match the confirmed source hash. Peer variants are current rows from the same
session/source. Missing confirmed data is an error, not an invented snapshot.
The repository maps stored fields to the TASK-304 callable described in
[its handoff at the reviewed commit](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/0a3e5e5f8575df2580ddd600fb6e1ad2257cf76e/docs/ai-w3-targeted-regeneration.md).

`candidate` uses TASK-304's `RegeneratedVariantResult`: `stem_latex`, exactly four
unprefixed `options`, `correct_key` A–D, `solution_md`, `validation_report`,
`api_calls_count`. Its compatibility `content` alias, when supplied, must equal
`stem_latex`. Database code validates the shape and `validation_report.is_valid`;
it does not independently certify mathematical correctness. Client-reported call
counts cannot replace the durable attempt ledger; discrepancies fail settlement.

Completion atomically demotes the old current row, inserts one pending-review
candidate with its own canonical snapshot, retains the source/canonical slot,
writes audit, settles the operation, and invalidates finalization. Failure or stale
recovery retains the old candidate and restores its recorded prior status, settles
accounting, and closes only the owned operation. AI failure does not create a
successful candidate or automatically approve one.

Invalidation means `is_finalized=false`, clearing `shuffle_seed`/`permutations`,
and deleting stale answer keys for affected versions in the same transaction.
The proposed affected set is **all session versions**, matching the current
session-wide reshuffle flow. Nothing restores display data into canonical fields.
If any required write fails, the whole database transaction fails. A transport
error with unknown commit outcome must be reconciled using the same operation ID,
not described as proven rollback.

## Attempt accounting — F07, pending Duy and Đạt

Proposed limits: 30 attempts/session, up to 4/operation, including provider failures,
schema repair and retries. TASK-304 would need a durable permit callback immediately
before **each** provider dispatch; its current local `RequestBudget` is not this
mechanism. No change to that adapter is included here.

Each acquired permit consumes one ledger entry and atomically increments the
session count. Completed/failed attempts remain charged; unused potential attempts
are never precharged. The proposal for a crash between permit commit and provider
dispatch is to retain that uncertain charge, rather than refund without proof.
This conservative accounting may count an attempt that never reached the provider:
it is an explicit policy choice requiring confirmation, not a claim of exact
provider-call measurement. Retry never exceeds either bound; recovery never
refunds a fixed four calls. A zero-call explicitly injected mock may settle zero;
production must not silently fall back to it.

## Lifecycle choices and readiness — C01/C02, pending Duy

- Proposed concurrency: one active regeneration per session. Another returns busy;
  reservation replay of the same operation remains idempotent. This is not yet
  agreement on Model A versus Model B in TASK-301.
- Proposed reject input: binary action, without teacher free text.
- Proposed revert: restore the first candidate in that slot as current and approved,
  retaining each candidate's original canonical snapshot. Audit and invalidation
  are atomic. A first-candidate revert is an idempotent approval/no replacement.
- Proposed readiness: accept/revert/complete/fail/recover recalculate in-transaction;
  progress GET remains read-only. `reviewed` requires the full configured version
  set and every confirmed source slot in each version, exactly one current per slot,
  all approved, and no active regeneration. COUNT(approved)=COUNT(existing) alone
  is insufficient. Content changes move the session back to `generated` until this
  predicate holds. Session-level approval/export remains TASK-305 and TASK-308.

`progress` shape: `expected_slots INT, current_slots INT, approved_slots INT,
regenerating_slots INT, missing_slots INT, duplicate_slots INT, ready BOOLEAN`.
The expected set comes from the confirmed source set and `generation_configs.n_versions`;
configuration/source ambiguity is an error rather than permission to mark reviewed.

## Canonical/display handoff — pending Duy and Tâm

Retain the four existing canonical fields: question number, four option strings in
A/B/C/D order, key and solution. New candidates get new snapshots; shuffling updates
display fields only. Answer keys retain synchronized aliases
`question_no/correct_option` and `display_no/display_correct_key`, plus the stable
`canonical_question_no`. This matches #24's `AnswerKeyRecord` aliases, including
legacy serialization. Confirm the session-wide invalidation boundary and mapping
with the actual shuffle persistence path before integration.

## Error mapping and acceptance — pending Duy

Proposed stable domain codes (database-to-HTTP mapping in Duy's service):
`REVIEW_NOT_FOUND` → 404 (also wrong owner, without resource disclosure),
`REVIEW_STALE` / `REVIEW_BUSY` / `REVIEW_IDEMPOTENCY_CONFLICT` → 409,
`REVIEW_LOCKED` → 423, `REVIEW_QUOTA_EXHAUSTED` → 429,
`REVIEW_INVALID_PAYLOAD` / `REVIEW_SOURCE_MISMATCH` → 422.
Unexpected database errors remain failures; unavailable AI is a service-side 503.
Do not parse provider exception text or return raw database/transport details.

Before Ready: owners resolve these choices and signatures, update this contract,
implement RPCs/caller wrappers, and verify real PostgreSQL races, idempotent retries,
late completion after recovery, rollback of audit/invalidation failures, quota
across workers and the integrated TASK-304/TASK-303 paths. Phase A's 15 schema tests
are not evidence of these guarantees. Historical actor handling is already decided
in the plan; JWT/worker authorization and Supabase RLS remain to be verified.
