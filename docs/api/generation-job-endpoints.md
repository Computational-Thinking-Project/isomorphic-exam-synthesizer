# TASK-207b: Generation jobs and SSE integration contract

## Implementation status

Author checkpoint 07/11/2026: The uncommitted Python integration now calls
PR #52's migration 017 finish-with-error and fenced stale scanner RPCs,
exposes the durable error on snapshot/restarted terminal SSE, and schedules
startup/30-second scan plus 60-second terminal cleanup. PR #52 is not yet
merged/applied; all new RPC tests are fixtures. The historical status below
describes the earlier 005/015/016 integration.

Local WIP at `936d48c` plus uncommitted changes mounts the job, snapshot and
stream routes in `main.py`. `GenerationJobRepository` calls the merged 005/015/016
RPCs. Claim uses the authenticated owner client; fenced worker writes use the
service role client. The owner-only ticket lookup reads the current session owner
from trusted server-side storage. This has fixture coverage; live PostgREST/RLS,
restart and proxy acceptance remain pending.

`AIBatchAdapter` calls the existing GenerationService. Product jobs dispatch one
batch using the frozen snapshot and committed full `QuestionResult` cache. The
older per-target Protocol remains for isolated runner tests only. Frozen
`active_variation_modes=[]` and `canonical_dimensions=[]` use
`persist_generation_clone` without Gemini; `AI_RESULT` uses
`persist_generation_result` with the full raw result and display projection.

## AI batch adapter contract

- Map source rows with `map_source_questions(rows,session_id)`; content and IDs
  are preserved and options are ordered A-D explicitly.
- Build internal `AIBatchInputs` from trusted stored sources/confirmation hash,
  canonical Blueprint JSON by source ID, base_seed, exact variation_modes and
  completed QuestionResult records. The adapter does not confirm a source or
  invent a hash from client input. AI receives frozen canonical dimensions;
  public mode IDs remain in the SQL snapshot. Empty public/canonical modes use
  the clone path and never call this adapter.
- Inject `AIRuntime.generation` into `AIBatchAdapter`; call
  `run(plan,inputs,store,deadline=...,on_result=...)`. Source/version/cache
  identities and ordering must agree with the job plan.
- The required async callback receives `PreparedAIResult(target,draft,raw_result)`.
  Persist the whole raw result/provenance and the display draft when available.
  Commit before returning and before publishing question_done/progress. Error
  results have no draft; do not invent a row. Completed cache gets no new callback.
- Callback failure propagates and may cancel sibling AI tasks. Keep acknowledged
  commits and reconcile uncertain writes; never auto-retry the callback.
- `JobRequestReservation` supplies the gateway's one-reservation-per-transport
  RequestContext. It requires an existing durable store; it implements no SQL
  or local quota substitute. Fatal/uncertain reservation failures are latched,
  checked before delivery and after the batch, and block further dispatches.
- Source/result validation, request deadlines, seed/fingerprints and cross-version
  uniqueness remain with the existing AI service. The adapter never loops
  single-question generation or wraps the batch in ProviderCalls.send.

The module is verified with real AI service/gateway/validator code and offline
SDK/persistence fixtures. Full Rule4 context, warning-after-exhaustion policy,
atomic DB semantics and live API/browser/proxy acceptance remain integration gates.

## HTTP factories

`create_generation_job_router(store_factory, runner=...)`, prefix `/api/sessions`:

- `POST /{session_id}/generate`: Bearer auth, existing ownership check and shared
  generation quota. No configuration request body. Atomically claim the stored
  configuration through the adapter, then schedule the runner in `BackgroundTasks`.
- `POST /{session_id}/retry-generation`: same guards, with `retry=True`. The store
  returns already committed targets; the runner skips them without modification.
- Acceptance: HTTP 202, `{"session_id":"<UUID>","status":"generating"}`.
- Active job in this worker: HTTP 409 `ERR_ALREADY_GENERATING`. SQL state/fencing
  conflicts from another worker map to HTTP 409 `ERR_CONFIG_CONFLICT`.
- Unknown claim/storage failures: safe HTTP 503; verify durable state before
  retrying. No automatic mutation retry or rollback claim.

`create_generation_stream_router(tickets=..., events=..., registry=...,
is_current_owner=...)`, same prefix:

- `POST /{session_id}/events/ticket`: Bearer auth and user-scoped ownership.
  Optional `last_event_id` and `stream_epoch` query parameters are checked
  against the current broker before issuing a ticket; stale marks return 409
  `ERR_EVENT_HISTORY_LOST`.
  Returns `{"ticket":"<UUID>","expires_at":"<ISO8601>"}`, no-store.
- Ticket lifetime is exactly 60 seconds, using monotonic expiration; each ticket
  binds session and verified user. No JWT is retained in the ticket store.
- `GET /{session_id}/events?ticket=...&last_event_id=...`: consume the ticket,
  recheck current ownership through the mandatory trusted server-side callback,
  validate the cursor and open `text/event-stream`. A token identifying another
  session, an expired token or an already consumed token gets HTTP 401.
- Owner change: 403. Owner lookup unavailable: generic 503, no successful stream.
- Query cursor takes precedence over native `Last-Event-ID`; malformed cursors
  get 422. SSE responses use `Cache-Control: no-store` and `X-Accel-Buffering: no`.
- Each handshake attempt consumes its valid ticket; failures after consumption
  require a fresh ticket. Never log tickets or Bearer tokens.

Factories use the existing Auth helpers. Sync ownership SDK calls run in the
threadpool so these new routes do not block other active streams.

## Event stream and reconnect

Wire frame:

```text
id: 14
event: question_done
data: {"timestamp":"2026-10-27T10:30:00Z","question_no":3,"version_index":1,"status":"done","percent_complete":45.0,"retry_count":0,"error_message":null,"error_code":null,"session_status":null,"completed_count":9,"total_count":20,"message":"Question saved successfully."}

```

JSON encoding prevents newlines in values from injecting SSE frames. Named
events are `progress`, `question_done`, `warning`, `error` and `done`.
`question_no` and `version_index` are null for overall job events. Integers are
strict, progress is finite in [0,100], and timestamps require a timezone.

The internal `GenerationEvent` model retains the W2 `{id,event,data}` envelope.
On the wire, SSE carries id/event as native fields and JSON contains only the
inner payload. This matches PR22 `a4cf946`'s hook: no second `data` wrapper.
Runner events include paired `completed_count`/`total_count` and a safe `message`.
An initial progress event covers resume, including an already complete job; a
progress event after each successful save updates counts immediately. Warnings
provide the `message` consumed by the UI, without exposing raw exceptions.

One shared broker per event loop/worker retains the last 50 events per session.
IDs keep increasing across retry jobs. Replay includes events newer than the
cursor, suppressing terminal `done/error` events from earlier jobs so they do
not terminate a new retry stream. Heartbeat is `: heartbeat\n\n` every 15 seconds;
the first response body comment establishes the stream immediately.

An expired history or future cursor returns HTTP 409
`ERR_EVENT_HISTORY_LOST` before the response starts. A slow consumer overtaken
by the ring receives a connection-level error and closes. That error has no
event ID and must not advance a replay cursor. Reload durable session progress
before reconnecting; do not silently assume the missing events were delivered.
`GET /{session_id}/generation-snapshot` returns durable completed/failure counts,
question statuses, optional `generation_error_code`, `stream_epoch` and
`resume_after_event_id`. It captures the
broker cursor before the DB read, then FE2 passes both marks to the ticket and
stream routes. A worker restart changes the epoch. Ticket issuance checks both
marks and returns 409 before EventSource opens when the cursor is unavailable.
The route brackets the result RPC with reads of the session's `id`, `status` and
`updated_at`. If finish or retry changes that revision between reads, it returns
HTTP 409 `ERR_CONFIG_CONFLICT` with a reload-state message instead of combining
counts from one revision with status from another. FE2 should reload the durable
snapshot before requesting a new ticket; this read-only rejection does not retry
or alter the job.
If the broker has no terminal event after a restart but the durable session is
terminal, ticket issuance reads committed counts and adds one terminal event;
`partial_generated` then reaches FE2 as `done` with its actual percentage.
The recovered event carries `generation_error_code` from migration 017 when
present; a null legacy code uses a safe generic failure code.
The broker's retry revision prevents a terminal read that started before
`reopen` from publishing an old terminal event into the new job stream.
The snapshot uses the owner JWT and returns `Cache-Control: no-store`.

Current default capacities: 4096 live tickets, 1024 session histories. Expired
tickets are pruned on access and every 60 seconds. Capacity fails explicitly.
Issued tickets, pending jobs and HTTP responses hold idempotent buffer leases.
Failed/cancelled claims and empty
disconnected streams release their slots; invalid cursors allocate nothing.
History or buffers still held by another job/subscriber/ticket are preserved.
Terminal histories are retained for at least 15 minutes before cleanup;
each session still holds only the newest 50 events, so this is not a 15-minute
guarantee of complete replay. No unbounded history is retained.

`GenerationStreamingResponse` explicitly closes its generator and lease in
cancellation-shielded cleanup. An ASGI send error can occur while the generator
is paused at yield; relying only on its finally block would leave gauges and
subscribers active until GC. Tests cover ASGI 2.3/2.4, first/later body failures,
cancellation while sending and header failure before generator entry.

## Job lifecycle and accounting

- The shared runner has a local duplicate guard; the DB claim remains authoritative.
  `job_id` fences every later mutation to prevent stale workers from saving after
  recovery. No endpoint accepts a caller-selected job ID or owner ID.
- A plan contains every source in every version (1–20 sources, 1–4 versions),
  committed targets and the existing durable Gemini count. Retry does not reset it.
- AI runs missing targets in its bounded batch; clone traverses frozen slots in
  deterministic order. Save each result immediately;
  emit `question_done` only after the save completes. Existing rows are preserved.
- The adapter invokes Tâm's four validation stages with the frozen Blueprint
  before AI accept/retry and retains solution consistency checks. Saveable candidates
  with warnings still count toward a complete `generated` job. No saveable
  candidate emits a warning and creates no fake row.
- The current isolated runner uses `ProviderCalls.send` for raw attempts. The
  new AI batch path instead injects JobRequestReservation into the existing
  gateway hook, reserving once immediately before transport, with a durable
  session cap of 250 including Blueprint usage. Never combine both wrappers.
- The shared AI gateway bounds outbound concurrency to three and disables SDK
  retries. Local validation and heuristic/mock operations do not reserve calls.
- The shared gateway observer reports actual SDK attempts to the runtime registry;
  reservation counts or QuestionResult.attempts are not a substitute for it.
- Execution timeout is at most 600 seconds. Quota/timeout with committed progress
  finishes `partial_generated`; without any committed progress it finishes `failed`.
  Fatal errors finish `failed` while preserving already committed rows.
- Finalization is fenced and bounded. If its DB outcome is unknown, emit a safe
  error and report `state_persisted=False`; never claim the session update succeeded.
- `done.data.session_status` distinguishes `generated` from `partial_generated`.
  FE must retain the actual percentage and missing targets for partial results,
  rather than forcing every `done` event to a complete successful job.
- Before a claim, the on-access stale RPC still fences the old job. Migration 017
  additionally tracks generation activity on the DB clock and provides a
  service-role, cursor-paged scanner. Its locked fail RPC stores
  `ERR_GENERATION_INTERRUPTED`. The scanner runs at startup/every 30 seconds;
  each pass handles up to 100 rows and continues its cursor next pass.

## Required adapters and remaining integration

`GenerationJobRepository` now maps the merged migrations 005/015/016 to the
Python store: owner claim, worker quota reservation, full AI result or clone
persist, completed-result load, finish and fail-stale. The worker uses the
service-role client; the current-owner lookup uses trusted server-side storage.
Python never emulates transactions with unrelated writes. The SQL finish RPC
verifies actual DB completeness; an uncertain save is not proof that no row was
committed. An isolated PostgREST/RLS test database remains necessary.

Quỳnh's mapping/batch modules adapt frozen confirmed inputs and full
QuestionResult to the existing service. Offline tests prove neither live Gemini
behavior nor all four integrated validators.
Legacy flat fallback Blueprint records are not automatically canonical AI inputs.

The app starts a shared runtime registry and mounts job, snapshot and stream
factories, scanner and cleanup loop. Broker/ticket/runner are process scoped;
OPS still needs to verify single-worker deployment, restart recovery, SSE proxy
buffering/timeouts and ticket-safe access logs.

PR18/21 provide real async batch generation with completed/on_result callbacks
and cross-version uniqueness. An adapter must preserve that batch behavior,
confirmed server hash and cached result fingerprints; looping over independent
single-question calls is not an equivalent integration. The gateway already
disables hidden SDK retries and reserves once immediately before transport.
Its request hook does not yet provide complete runtime outcome instrumentation;
do not wrap the whole service in ProviderCalls.send or reserve twice.

Collector snapshot PR22 `2d74017` preserves partial percentage/counts and explicitly
sends shuffle_options:false. Remaining gates include retry button vs reconnect,
missing-card status/reload partial, history-loss resync, case-sensitive mode IDs
and saved config/Blueprint detail projection. Do not change backend defaults or
partial policy to conceal these differences. PR19/20 supply rule/aggregator
contracts, not DB or app lifecycle adapters.

Partial-generation restrictions on export/finalize belong at those endpoints;
none are implemented or bypassed by this module. DB RLS, locking, rollback,
concurrency and crash recovery still require isolated integration tests.
