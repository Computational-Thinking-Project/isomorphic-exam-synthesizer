# Finalize RPC boundary — TASK-305

05/11/2026. Owner: Duy/TASK-305. Migration **009** is the forward authority after
006/007/008. This remediation responds to PR #33 review F01–F03; it is implemented
and locally tested, pending independent owner/reviewer acceptance. The shared
Review RPC authority in migration006 is unchanged.

## HTTP and trusted shuffle writer

`POST /api/sessions/{session_id}/finalize/shuffle` retains its metadata response.
The route verifies the user's JWT and ownership. All session/progress/canonical
reads use `get_user_db` with that user's RLS context. The server computes output
with TASK-303's existing `prepare_shuffle`/Fisher–Yates implementation; it accepts
neither permutations nor actor identity from the HTTP body.

Only the separate `get_service_db` client may execute
`public.finalize_persist_shuffle(p_session_id uuid,p_payload jsonb) RETURNS jsonb`.
Payload: `{actor_id, snapshot, versions}`. `actor_id` is the verified CurrentUser
ID, supplied by the trusted backend, not a browser parameter. SQL requires the
actual selected PostgreSQL principal `service_role`, locks the session, binds
stored ownership to `actor_id`, rechecks status/readiness/exact snapshot and
validates all display/key/canonical/permutation/solution invariants before atomic
persistence. JWT role claim GUCs alone do not authorize execution.

`PUBLIC`, `anon` and `authenticated` cannot execute the writer, even if their
payload is internally consistent. This closes submission of a different valid
bijection with the same seed: the backend is the trusted computation boundary.
SQL does **not** reimplement Python's random generator. A compromised service key
is outside the end-user threat boundary and must never reach a browser. The
service client must not be re-authenticated with the user's access token.

No trusted writer configuration means failure, never owner-client fallback.
Strict receipt parsing, canonical snapshot revalidation, no-op retry, rollback,
and parent locking remain required. A lost response after commit is uncertain
outcome: report failure and retry the same snapshot safely; do not assume rollback.

## Approval and direct DML

`finalize_approve_session(uuid,uuid,timestamptz)` keeps its signature and existing
owner/worker authorization, readiness and idempotency. Under the root lock it now
requires exactly one current question and one key for **each version/display
slot**, matching `correct_option == display_correct_key == q.correct_key` and
`canonical_question_no == q.canonical_question_no`. Coverage/aliases alone are
insufficient. Failure precedes approval timestamp and APPROVE_ALL audit writes.

Migration009 revokes client table **and column** mutation privileges for versions,
version questions, answer keys and review logs, and changes their owner policies
to SELECT-only. It revokes client TRUNCATE/TRIGGER/REFERENCES privileges on the
content graph and client DELETE of profiles (which could otherwise cascade as
the FK trigger owner). Owner read isolation is preserved.

Invoker triggers protect sessions, sources, blueprints, config, versions,
questions and keys against direct `authenticated`/`anon`/`service_role` writes
after approved/exported or non-null approved_at. Direct client session creation
must be draft; clients may edit only title/subject/grade/updated_at before locking.
Lifecycle/counter/ownership fields cannot be forged through table DML. Legitimate
Review/Finalize SECURITY DEFINER RPCs enforce their own owner/worker checks and
root locks; those routines are the trusted transition authority. DB administrators
remain a privileged maintenance boundary.

Finalized config cannot be changed/deleted/reinserted through direct DML behind
an existing shuffle receipt. A future reconfiguration RPC must invalidate keys,
seed/permutations and finalized flags together under the root lock; no implicit
reset or post-approval unlock is introduced. Export's legal approved→exported
transition likewise needs an authorized locked RPC, not a direct service update.
Session metadata/delete HTTP routes translate DB ERR_SESSION_LOCKED into HTTP423.

Direct child DML guards acquire the parent lock before checking locked state;
ordinary transactional writers should use root-first RPC ordering. PostgreSQL may
abort a conflicting direct child write with a deadlock error if it already holds
a child tuple; such errors must remain failures, never fallback writes.

## Migration / rollout

Apply existing006→007→008, then **009 last**. Do not edit/replay an older function
definition after009 without reapplying009. The forward migration replaces Finalize
definitions, refreshes the solution helper, updates ACL/policies/triggers in one
transaction and preserves existing rows. It is tested on populated fresh/legacy
chains, failure before COMMIT and replay; this is not evidence of a cloud ledger.

Deploy the backend reader/writer split and009 as one coordinated, feature-gated
rollout: mixed old/new versions may reject shuffle and must fail closed. Existing
service-role configuration is required. No deployment/production secrets, merge,
or migration ledger was changed in this local remediation.
