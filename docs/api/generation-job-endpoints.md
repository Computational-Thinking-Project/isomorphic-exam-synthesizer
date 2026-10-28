# TASK-207b: Generation jobs and SSE integration contract

## Implementation status

Python implements the event models, bounded ticket store, event broker, job
runner, two router factories and explicit AI batch mapping/reservation adapters.
AI PR18/21 is now inherited through Quỳnh's dev synchronization at `91843e0`.
Product `main.py` does not register the TASK-207 factories: durable storage,
current-owner lookup and the runner's transition to the batch callback path
remain pending. No in-memory database or fake AI is installed in the product app.

`AIBatchAdapter` calls the existing GenerationService; it does not implement
another generator or gateway. The current isolated GenerationJobRunner still
uses its per-target Protocol, so the new adapter is not a drop-in replacement
until the durable snapshot/result persistence contract is integrated.

## AI batch adapter contract

- Map source rows with `map_source_questions(rows,session_id)`; content and IDs
  are preserved and options are ordered A-D explicitly.
- Build internal `AIBatchInputs` from trusted stored sources/confirmation hash,
  canonical Blueprint JSON by source ID, base_seed, exact variation_modes and
  completed QuestionResult records. The adapter does not confirm a source or
  invent a hash from client input. Modes are passed unchanged, including [].
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
- Active job: HTTP 409 with `detail.code=ERR_ALREADY_GENERATING`.
- Unknown claim/storage failures: safe HTTP 503; verify durable state before
  retrying. No automatic mutation retry or rollback claim.

`create_generation_stream_router(tickets=..., events=..., registry=...,
is_current_owner=...)`, same prefix:

- `POST /{session_id}/events/ticket`: Bearer auth and user-scoped ownership.
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
The frontend/DB integration must provide the current cursor for this resync.

Current default capacities: 4096 live tickets, 1024 session histories. Expired
tickets are pruned on access. Capacity fails explicitly. Pending jobs and HTTP
responses hold idempotent buffer leases. Failed/cancelled claims and empty
disconnected streams release their slots; invalid cursors allocate nothing.
History or buffers still held by another job/subscriber are preserved. The owner of app
lifecycle must call broker `forget` for terminal, unsubscribed histories after
its agreed replay retention period. No unbounded history is retained.

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
- Run missing targets in deterministic order. Save each candidate immediately;
  emit `question_done` only after the save completes. Existing rows are preserved.
- AI supplies the four validation stages and retry behavior. Saveable candidates
  with warnings still count toward a complete `generated` job. No saveable
  candidate emits a warning and creates no fake row.
- The current isolated runner uses `ProviderCalls.send` for raw attempts. The
  new AI batch path instead injects JobRequestReservation into the existing
  gateway hook, reserving once immediately before transport, with a durable
  session cap of 250 including Blueprint usage. Never combine both wrappers.
- The shared AI gateway bounds outbound concurrency to three and disables SDK
  retries. Local validation and heuristic/mock operations do not reserve calls.
- ProviderCalls already models known/unknown outcomes in the isolated runner.
  The new shared AI path still needs a raw outcome hook for runtime metrics;
  reservation counts or QuestionResult.attempts are not a substitute for it.
- Execution timeout is at most 600 seconds. Quota/timeout with committed progress
  finishes `partial_generated`; without any committed progress it finishes `failed`.
  Fatal errors finish `failed` while preserving already committed rows.
- Finalization is fenced and bounded. If its DB outcome is unknown, emit a safe
  error and report `state_persisted=False`; never claim the session update succeeded.
- `done.data.session_status` distinguishes `generated` from `partial_generated`.
  FE must retain the actual percentage and missing targets for partial results,
  rather than forcing every `done` event to a complete successful job.
- Before a claim, ask the store to atomically fail a `generating` row untouched
  for 12 minutes with `ERR_GENERATION_INTERRUPTED`. This is recovery on access;
  an application-wide periodic sweep still needs a durable enumeration adapter
  and lifecycle integration. Cleanup releases job/SSE runtime handles in finally.

## Required adapters and remaining integration

`GenerationJobStore` defines Python methods, not assumed RPC wire names:
`claim`, `reserve_gemini_call`, `save_draft`, `finish` and `fail_stale`.
Duy must confirm atomic DB operations, stable errors, worker access,
job fencing representation and an isolated test database. Quỳnh can implement
the current-owner Python lookup using the existing trusted server DB client once
access/lifetime is agreed. Python never emulates
transactions with unrelated writes. `finish` must verify actual DB completeness;
an uncertain save is not proof that no row was committed.

Quỳnh's mapping/batch modules now adapt confirmed inputs and QuestionResult to
the existing service. Real snapshot loading and persistence remain pending;
offline tests prove neither live Gemini behavior nor all four integrated validators.
Legacy flat fallback Blueprint records are not automatically canonical AI inputs.

Extend the existing AIRuntime lifespan to create/start one shared runtime registry,
broker, ticket store and runner, then mount both factories with real adapters. Keep
generation config persistence behind its separate TASK-207a RPC gate. OPS must
verify single worker, SSE proxy buffering/timeouts and ticket-safe access logs.

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
