# TASK-207b: Generation jobs and SSE integration contract

## Implementation status

Python implements the event models, bounded ticket store, event broker, job
runner and two router factories. They are exercised in isolated tests. Product
`main.py` does not register these factories: real durable storage, current-owner
lookup and the AI/validator adapter must be supplied explicitly. No in-memory
database or fake AI is installed in the product app.

The current branch predates the async AI integration already on `dev`. Do not
copy or replace that AI implementation. Connect its raw request boundary and
confirmed Blueprint inputs when integrating the branches.

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
data: {"id":14,"event":"question_done","data":{"timestamp":"2026-10-27T10:30:00Z","question_no":3,"version_index":1,"status":"done","percent_complete":45.0,"retry_count":0,"error_message":null,"error_code":null,"session_status":null}}

```

JSON encoding prevents newlines in values from injecting SSE frames. Named
events are `progress`, `question_done`, `warning`, `error` and `done`.
`question_no` and `version_index` are null for overall job events. Integers are
strict, progress is finite in [0,100], and timestamps require a timezone.

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
tickets are pruned on access. Capacity fails explicitly. The owner of app
lifecycle must call broker `forget` for terminal, unsubscribed histories after
its agreed replay retention period. No unbounded history is retained.

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
- Each real outbound attempt, including repair/retry/solution calls, must pass
  through `ProviderCalls.send`. Durable quota is reserved immediately before
  transport and is capped at 250 across the session, including Blueprint usage.
- One shared semaphore bounds outbound calls to three across jobs. Local
  validation and heuristic/mock operations do not reserve calls. The AI adapter
  must account for hidden SDK retries instead of wrapping a whole high-level method.
- Known provider failures increment runtime error statistics. Unknown outcomes
  on cancellation/whole-job timeout are released without inventing a result.
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
Duy must confirm atomic DB operations, stable errors, current-owner lookup,
job fencing representation and an isolated test database. Python never emulates
transactions with unrelated writes. `finish` must verify actual DB completeness;
an uncertain save is not proof that no row was committed.

AI must map confirmed source/Blueprint/config data to its real async service and
return a validated `GeneratedDraft`; local test doubles prove neither real
Gemini behavior nor the four production validators. The legacy flat fallback
Blueprint and the AI service's structured Blueprint need an explicit adapter.

The eventual app lifespan must create/start one shared runtime registry, broker,
ticket store and runner, and mount both factories with real adapters. Keep
generation config persistence behind its separate TASK-207a RPC gate. OPS must
verify single worker, SSE proxy buffering/timeouts and ticket-safe access logs.

Partial-generation restrictions on export/finalize belong at those endpoints;
none are implemented or bypassed by this module. DB RLS, locking, rollback,
concurrency and crash recovery still require isolated integration tests.
