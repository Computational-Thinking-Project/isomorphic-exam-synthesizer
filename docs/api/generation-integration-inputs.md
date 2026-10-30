# TASK-207 integration inputs — updated 2026-10-28

This is a source/contract audit, not approval of the referenced PRs or proof
that their migrations are installed in a database. Quỳnh synchronized dev at
merge commit `91843e0`, including AI PR18/21 and ingestion PR15 (`784025a`).
The cleanup fixes, flat SSE payload and AI adapters build on that baseline.
AI service code is now local, but TASK-207 product routes and
durable adapters are still not wired. FE/VAL snapshots below are from the
Collector's 2026-10-28 inspection; PR16 remains an older inspected snapshot.

| Duy PR | Head inspected | State at inspection | Reusable input |
| --- | --- | --- | --- |
| [13](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/13) | `cb5e4e6` | Merged | Session CRUD/detail, source/version row structure, owner-scoped access. |
| [14](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/14) | `9f361a3` | Merged | Verified `CurrentUser`, `authenticated_user_id`, user-scoped DB and ownership helpers. |
| [15](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/15) | Merged source `784025a` | Merged, local | Source ingestion, `replace_source_questions(p_session_id,p_questions)`, atomic-write and uncertain-outcome handling; UTF-8 BOM decoding is present. |
| [16](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/16) | `85541d5` | Open | Confirm-source contract, `confirm_exam_source`, confirmed Blueprint links and fallback metadata. |
| [22](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/22) | `2d74017` | Open at Collector inspection | Flat SSE/counts/messages, partial percentages preserved, explicit shuffle_options:false; retry/resync work remains. |
| [19](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/19) | `5e5b578` | Open | Tâm's rule checker: bounds/invariants/distractors and fallback confidence; no OPS/retention contract. |
| [20](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/20) | `0ffdfea` | Open | Tâm's validation aggregator, report statuses/confidence and entry points. |
| [18](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/18) | `0b75d21` | Merged | AIRuntime, real Blueprint/generation services, budget and result callbacks. |
| [21](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/21) | `4ea420e` | Merged | Cross-version peer uniqueness and persistence requirements for regeneration. |

## Admin input is still missing

In the synchronized local source, `CurrentUser` has id/email/name/access_token; there is no
application admin field, trusted role source or `require_admin`/`is_admin` helper.
`user_metadata` supplies a display name, not admin authorization. SQL references
to `authenticated`, `service_role`, `postgres` and `supabase_admin` concern DB
execution privileges; they do not identify an authenticated application's admin.
TASK-207c access policy remains pending Duy's explicit source/helper/failure
contract. No speculative guard or production bypass was added.

## Config and Blueprint inputs

PR16's confirm RPC accepts session UUID, expected question count, security-warning
acknowledgment and expected updated_at. It locks the session, checks ownership and
draft state, stamps Blueprint confirmed_at and moves the session to blueprinted.
Migration 003 adds unique(source_question_id), is_fallback and extraction_source.

The fallback extractor returns NUMERICAL for numerical questions or NONE for
verbatim preservation. TASK-207a already permits confirmed fallback data, retains
exact mode IDs, accepts [] and checks the intersection across all Blueprints.
It must still reject unconfirmed sources. The flat fallback representation is
not automatically the structured confirmed Blueprint required by the AI service.
Quỳnh implements the Python mapping once the canonical persisted input contract
is available, coordinating representation/policy with the DB and AI owners.
No silent conversion or Gemini call is implied.

Neither the config-save RPC nor a fenced job/quota/progress adapter appears in
these four PRs. Do not reuse the ingestion/confirm RPC as a config save. Duy must
confirm the config wire contract and durable operations in GenerationJobStore.
No particular additional SQL function names are assumed by Python.

PR15's ingestion-only flow and parser fixes are now inherited from dev. Earlier
parser findings against `f35622d` are historical, not assertions about the merged
source. This adapter work changes no ingestion, parser, Auth or SQL implementation.

## Inputs applied from PR22

The frontend reads event.lastEventId and the JSON payload's percent_complete,
completed_count, total_count, version_index, question_no and message directly.
The Python transport now sends native SSE id/event with flat inner JSON, rather
than a double data envelope. Runner progress counts reflect acknowledged durable
saves, including resumed jobs. Warning message is a safe public string.

Verified offline using 11 frames produced by the real Python runner with test
DB/AI doubles, then consumed by PR22's actual useSSE hook in its ReactDOM mock-DOM
harness: 2/2 completed, two done statuses, two warnings, done and a reconnect
using a fresh ticket plus the last native cursor. This is not browser/proxy QA.

Collector snapshot `2d74017` now preserves partial percentages/counts and avoids
redirecting partial jobs. It explicitly sends shuffle_options:false, which the
backend accepts without changing its omitted-field defaults. Remaining work:
the retry button reconnects rather than starting retry-generation; missing cards
can appear done; reload-partial and history-loss snapshot/resync are absent;
case-insensitive mode intersection can disagree with backend exact IDs. GET
detail still needs saved config and exact Blueprint metadata from DB integration.

## AI and validator inputs

PR18/21: use AIRuntime.generation.generate_exam_drafts with sources, canonical
Blueprint JSON by source ID, confirmed_source_hash, n_versions, RequestContext and
completed/on_result. Persist callback results before emitting progress. Keep
resume fingerprints/base_seed and batch cross-version uniqueness. Regeneration
requires all current same-source peers plus an atomic revision/uniqueness check;
that review endpoint is outside the current fix scope.

Gateway SDK retries are disabled (attempts=1); its semaphore is at most 3, and its
quota hook runs once immediately before transport. The successful path returns
question, answer and solution together; there is no mandatory extra solution
request. The supplied reserve hook is not yet a runtime outcome hook.

DB-backed confirmation hash/record shape, atomic quota and durable callbacks
remain missing. PR16's flat fallback record is not automatically the structured
AI Blueprint. No fake AI/DB adapter or product wiring was added.

## Python AI adapters implemented on the synchronized baseline

- `ai_mapping.map_source_questions`: session-scoped, ordered source mapping;
  options are explicitly A-D and content/IDs are preserved. Uses the existing
  AI source checks instead of guessing answers or creating new canonical IDs.
- `prepare_question_result`: returns `PreparedAIResult(target,draft,raw_result)`.
  The display draft is not a substitute for persisting the full QuestionResult
  with seed/fingerprints/validation metadata. None candidates produce no fake row.
- `JobRequestReservation`: injects `reserve_gemini_call` into RequestContext.
  Budget exhaustion stays a budget error; unknown DB errors/cancellation or bad
  committed counts latch a storage failure and block further reservations.
- `AIBatchInputs` requires sources, canonical blueprints, stored confirmation
  hash, base_seed, exact variation_modes and completed results. It is an internal
  server-owned snapshot, not an HTTP body or a proposed database schema.
- `AIBatchAdapter.run(plan,inputs,store,deadline=...,on_result=...)` calls the
  existing service once per batch, preserving uniqueness and resume. The caller
  supplies the shared AIRuntime.generation and an async persistence callback.
  Callbacks receive success and error results; cached targets receive no callback.
  Callback acknowledgement is awaited and duplicate/unplanned deliveries fail.
- The adapter checks the reservation failure latch even when the AI service
  converts a DB exception into an error result. It never retries unknown writes,
  invents a source confirmation, counts a batch as an attempt or reserves twice.

The existing GenerationJobRunner still uses its per-target Protocol. Replacing
that path and mounting routes require the agreed durable store/result schema.
The new module does not claim that callback data is already committed in a real
DB, and does not replace the missing runtime provider-outcome metrics hook.

Tests exercise actual GenerationService, GeminiGateway and CandidateValidator
with offline SDK transport and persistence fixtures, including SSE ordering,
uniqueness retry, solution repair, partial quota, stale cache, storage failure,
deadline and cancellation. This is not live Gemini, DB/RLS or browser acceptance.

PR19/20: validator entry points accept question_text, an A-D ordered option list,
correct answer text/key, Blueprint and optional parameters. Aggregator report
has passed/status/confidence/checks/errors/warnings/execution_time_ms; to_dict
serializes it. A rule-only fallback is not proof of mathematical correctness.
The AI layer's ValidationReport is a different model; never substitute imports
or pass GeneratedDraft's options dictionary directly without an explicit adapter.
The aggregator is synchronous; an async job adapter must keep its CPU/process
work off the event loop and respect the remaining job deadline.

The inspected sources provide no trusted admin source, config-save RPC, job fencing
storage, global stale-job enumeration or history-retention policy. Those gates
remain open. AI and ingestion source are now inherited from dev; the FE/VAL
branches and newer confirm-source work were not merged by this adapter change.
