# TASK-207c: Runtime health metrics contract

## Status and scope

This branch implements response models, the runtime registry, Linux current RSS
reader and a fresh-snapshot collector, with isolated tests. The new TASK-207b
Python broker/runner also accept this same registry for their lifecycle hooks.
They are not registered in the product app. The current product handler still
returns only `status` and `gemini_model`, without auth. Access guard, real AI
instrumentation and protected endpoint integration remain pending.

`RuntimeMetricsCollector.collect()` combines registry activity, configured model
and a new RSS sample, validates all eight response fields and raises a safe
`RuntimeMetricsUnavailableError` on any failure. It never returns partial data
or substitutes zero for a missing observation. The later HTTP adapter must map
this error to the specified 503 body.

The endpoint reports the current backend worker's runtime activity. It is
separate from pedagogical statistics (TASK-401), persistent per-session Gemini
quota accounting (TASK-207b) and the public Docker liveness probe.

## Request and access policy

`GET /api/health/metrics`, with no request body or session/user query parameters.
Require `Authorization: Bearer <user_token>` through the existing
`get_current_user` dependency. Authentication is required in every environment.

| Caller | Intended result |
| --- | --- |
| Missing, malformed or invalid bearer token | Existing Auth 401 response, including `WWW-Authenticate: Bearer`. |
| Verified user, server environment `development` | Allow. |
| Verified administrator, any other environment | Allow after the trusted admin integration is available. |
| Verified non-admin, missing/unrecognized role, any other environment | Deny with 403. |

Only the configured server environment determines development access. Request
headers, query parameters and the caller's claimed environment grant nothing.
`test`, `staging`, `production` and unknown environment values do not implicitly
receive development privileges. Existing Auth service/configuration failures
retain their established error handling; never convert them to successful data.

**Pending admin input:** `CurrentUser` currently exposes no admin role. Duy must
confirm the trusted role source, field/helper contract, missing-role behavior
and role-lookup failure handling before product admin authorization is wired.
Do not add or infer a new admin field just to complete this task. Do not use
editable `user_metadata`, an unverified JWT payload or a caller-supplied admin
header. The Supabase database role `authenticated` alone does not mean business
administrator. Missing integration must fail closed and remains a completion
gate, not a reason to publish metrics without auth.

See [Supabase's metadata guidance](https://supabase.com/docs/guides/auth/users).

## Success response

Return HTTP 200 only after access checks and successful collection of all six
metrics. Preserve the existing `status` and `gemini_model` fields. Return
`Cache-Control: no-store`; polling must not serve a cached runtime snapshot.

Illustrative values, not measured data:

```json
{
  "status": "operational",
  "gemini_model": "configured-model-id",
  "uptime_seconds": 125.5,
  "active_sse_connections": 2,
  "gemini_call_count": 12,
  "gemini_error_rate": 0.25,
  "background_jobs_running": 1,
  "process_memory_mb": 84.25
}
```

`gemini_model` comes from server configuration; it is not hard-coded to the
example. `operational` means the runtime snapshot was collected successfully,
not that Gemini, Supabase, the network and all jobs have passed live probes.
Reading metrics must never call Gemini, create jobs or increment the counters.

## Metric definitions

| Field | Type and range | Definition |
| --- | --- | --- |
| `uptime_seconds` | Finite number >= 0 | Elapsed monotonic time since this worker's application startup. |
| `active_sse_connections` | Integer >= 0 | Currently established SSE connections, not distinct users/sessions or issued tickets. |
| `gemini_call_count` | Integer >= 0 | Outbound Gemini request attempts started in this runtime, including in-flight attempts. |
| `gemini_error_rate` | Finite number in [0, 1] | Failed completed provider attempts divided by all completed provider attempts; 0 when none have completed. |
| `background_jobs_running` | Integer >= 0 | Distinct sessions with an executing generation job in this worker, excluding queued or completed jobs. |
| `process_memory_mb` | Finite number >= 0 | Current backend process RSS, expressed as bytes / 1,048,576 (MiB; retain the W2 field name). |

Counts must not accept booleans as integers. Do not serialize NaN, infinity,
negative counts or arbitrary additional fields. Return no access tokens, API
keys, prompts, user/session IDs, raw exceptions or per-question content.

### Uptime and runtime lifetime

Use a monotonic clock, initialized at application startup rather than import
time or on each request. System wall-clock corrections do not alter uptime.
The collector and its dependencies are shared by producers and readers within
the same app/worker, not recreated on every metrics request.

Restart/reload resets uptime, aggregate call statistics and active handles.
This is runtime state, not a durable ledger. A DB session left `generating`
after a crash is not automatically counted as a running process job; stale-job
recovery belongs to TASK-207b. The MVP assumes one backend worker. Multi-worker
or multi-instance aggregation requires a separate design, not an implicit sum.

Reference: [Python monotonic clock](https://docs.python.org/3.11/library/time.html#time.monotonic).

### SSE and background jobs

Record SSE entry only after a valid handshake establishes the connection.
Rejected/expired tickets and failed handshakes do not increase the gauge. Two
connections watching one session count as two. Close/disconnect/error/cancellation
paths must release their active handles in cleanup, without negative counts or
double-decrementing when cleanup repeats.

Record a job when execution starts, and release it on success, failure or
cancellation. Count executing sessions, not submitted HTTP requests, historical
DB rows or queued work. Instrumentation does not replace the duplicate-job
guards or durable state transitions owned by TASK-207b.

Update/read operations must be safe for sync and async callers. Do not hold a
collector lock across network I/O or an await. Remove completed active handles;
do not retain an unbounded request/job history just to calculate these metrics.

### Gemini attempts and errors

Record an attempt at the outbound request boundary, after local prevalidation
and immediately before the request is sent. Count variant, solution, Blueprint,
retry and AI repair requests that belong to the observed runtime. Each actual
attempt is counted once; calling an orchestrator method is not itself an attempt.

An attempt fails for an observed provider/transport failure, such as an API
error, timeout or lost connection. This does not assert whether the provider
processed or billed an uncertain request. Local JSON/schema/mathematical
validation failure after a successful provider response is not by itself a
provider error. Heuristic repair and mock AI calls send no Gemini request and
must not increase live provider statistics.

Use internal completed/failed counters for the ratio; in-flight requests are
excluded from its denominator. For example, 3 failures among 12 completed
attempts produce 0.25. A later successful retry is a separate attempt; it does
not erase the earlier failure. Cleanup must not record completion twice.

**AI input verified in PR18/21:** the W2 gateway explicitly sets SDK retry
attempts to 1, applies a shared semaphore of at most 3 and invokes
RequestContext.reserve_request immediately before each transport dispatch.
W2 Blueprint extraction now runs through backend AIRuntime; the standalone CLI
is not the W2 request path. These services and their AIRuntime lifespan are now
present on this branch after dev synchronization. The TASK-207 job runner and
runtime metrics collector are not yet connected to that shared AI path. Do not
invent a subprocess metrics bridge for W2 or reuse the legacy sync generator.

**Still pending:** connect one raw-request outcome boundary to the collector
with the AI owner, including success/failure/cancellation. The reserve hook is
not an outcome hook. Do not count an entire batch as a request, double-reserve
the existing DB hook, or mark provider success/failure from local validation.
If any separate process is later included, its reporting/crash contract needs
an explicit bridge rather than assuming shared Python memory.

These counters do not increment or replace `exam_sessions.gemini_call_count`,
`gemini_review_calls` or the 250-call per-batch guard. Their scopes/lifetimes are
different; do not sum persistent session quotas as a runtime approximation.

### Process memory

The initial target is the existing Linux Docker runtime. Plan to read current
process RSS from `/proc/self/status` (`VmRSS`, reported in KiB) and convert to
MiB. This is OS-reported RSS, not exact allocation accounting. It excludes the
whole Windows host, container totals and validator/Blueprint child-process RSS.

Do not substitute peak `ru_maxrss` for current RSS. A native Windows/macOS
provider, or a new dependency such as psutil, needs an explicit platform and OPS
decision before implementation. Unit tests inject a memory reader rather than
depend on the host's changing RAM value.

References: [Linux process status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html),
[Python resource usage](https://docs.python.org/3/library/resource.html).

## Collection failures and availability

If the collector is not initialized, the memory sample cannot be read/parsed,
or a snapshot violates the response contract, return HTTP 503 with safe detail:

```json
{
  "detail": {
    "code": "ERR_RUNTIME_METRICS_UNAVAILABLE",
    "message": "Runtime metrics are temporarily unavailable."
  }
}
```

Do not return invented zero values, a stale snapshot or partial HTTP 200 to
hide a collection failure. Genuine zero observations after startup are valid;
unconnected producers are not evidence that no activity occurred. Coverage
gaps must be documented and remain integration/completion gates. No raw OS,
SDK, path or credential details belong in the error response.

## Public health, quota and smoke compatibility

Keep `GET /health` public and preserve its existing liveness response for Docker
healthchecks. Metrics remain outside the shared CRUD/generation quota policy;
quota exemption does not waive authentication or admin/development access.
Do not alter CORS, existing quotas or the global exception handler for this task.

Before replacing the old public metrics handler, coordinate these consumers
with OPS and update them in the same integration change:

- `scripts/dev.ps1`: the current proxy smoke expects unauthenticated metrics 200.
- `.github/workflows/docker-ci.yml`: the static Nginx smoke uses curl --fail on
  the same unauthenticated endpoint.

The planned token-free proxy smoke should assert 401 with the Auth challenge,
while backend `/health` remains 200. Authorized success belongs in API tests and
an agreed test-account smoke; never insert a production auth bypass or commit a
real JWT to make CI pass. Retain PowerShell 5.1/7 compatibility in script edits.
Ensure only one metrics route remains registered after product integration.

## Implementation and verification gates

1. Contract -> response model/tests -> runtime collector/tests -> memory reader/tests.
2. Access guard and router tested in isolated apps using fake role/clock/providers.
3. Duy confirms the trusted admin source; AI and TASK-207b confirm producer hooks.
4. Connect actual request/job/SSE lifecycle events to one worker collector.
5. Integrate app lifecycle, replace the old route and update OPS smoke checks together.
6. Run relevant tests, backend regression, Ruff, Mypy, format and whitespace checks;
   record actual results and mock/live boundaries in the handoff.

Do not mark TASK-207c complete using fake-only authorization or uninstrumented
producer gauges. No schema migration, shared DB mutation or real Gemini calls
are required merely to develop the models, collector or isolated API tests.
