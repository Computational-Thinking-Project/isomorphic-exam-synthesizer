# Generation Lifecycle Recovery and Durable Error Contract — Migration 017

- **Author**: Duy (PR #32 / TASK-207 SQL boundary)
- **Consumer**: Quỳnh (PR #30 — Python generation worker, lifecycle scanner & SSE recovery)
- **Target Migration**: `backend/migrations/017_generation_lifecycle_recovery.sql`
- **Applicable Schema**: Applied after `016_stage2_original_clone.sql`

This document defines the SQL/RPC contract for stale generation job detection,
fenced failure transitions, authoritative generation activity tracking, and durable
error recovery across worker reboots.

---

## 1. Architectural Decisions

1. **Independent Generation Clock**:
   - `public.exam_sessions.generation_last_activity_at` tracks authentic generation milestones only:
     - Job claims (fresh & retry).
     - Quota reservations (`reserve_generation_quota`).
     - Target question persist (`persist_generation_result`, `persist_generation_clone`).
     - Periodic worker heartbeat (`heartbeat_generation_job`).
   - Standard session metadata edits (`title`, `subject`, `grade`) update `updated_at` via Trigger 004, but **never** refresh `generation_last_activity_at`. Stale recovery evaluates true generation inactivity.
2. **Authoritative Timeout**:
   - Inactivity timeout remains fixed at **720 seconds** calculated on the PostgreSQL server clock (`clock_timestamp()`), eliminating host-clock skew between Python instances.
3. **Fencing Against Concurrency Races**:
   - `fail_stale_generation_job_if_current` accepts `p_expected_job_token` and validates under `SELECT ... FOR UPDATE`. If the worker has finished or retried, recovery is safely rejected without modifying session state.
4. **Durable Error Persistence**:
   - `public.exam_sessions.generation_error_code` stores standard uppercase error codes (e.g., `ERR_GENERATION_INTERRUPTED`, `ERR_MODEL_QUOTA_EXHAUSTED`).
   - Retained in PostgreSQL storage across container reboots, OOM kills, and SSE disconnections.
   - Cleared automatically when a session is retried via `claim_generation_job`.

---

## 2. RPC Signatures & Access Boundaries

| RPC | Parameters | Return Type | Role Access |
|---|---|---|---|
| `list_stale_generation_jobs` | `p_cutoff_seconds INT=720, p_limit INT=50, p_after_activity_at TIMESTAMPTZ=NULL, p_after_session_id UUID=NULL` | `JSONB` | `service_role` only |
| `fail_stale_generation_job_if_current` | `p_session_id UUID, p_expected_job_token UUID, p_cutoff_seconds INT=720` | `JSONB` | `service_role` only |
| `fail_stale_generation_job` | `p_session_id UUID, p_cutoff_seconds INT=720` | `JSONB` | `service_role` only |
| `finish_generation_job_with_error` | `p_session_id UUID, p_outcome TEXT, p_job_token UUID, p_error_code TEXT` | `JSONB` | `service_role` only |
| `load_generation_completed_results` | `p_session_id UUID` | `JSONB` | `authenticated owner`, `service_role` |
| `heartbeat_generation_job` | `p_session_id UUID, p_job_token UUID` | `JSONB` | `service_role` only |

Direct write operations to `generation_last_activity_at` and `generation_error_code` are strictly prohibited for client roles (`authenticated`, `anon`).

### Least Privilege & Defense-in-Depth Model (SEC-01 - SEC-04)
1. **Layer 1 (Schema ACL Whitelisting)**:
   - Table-level `INSERT` and `UPDATE` are revoked from `PUBLIC`, `anon`, and `authenticated`.
   - `authenticated` receives column-level `GRANT UPDATE (title, subject, grade)` and `GRANT INSERT (user_id, title, subject, grade)` only.
   - Column `UPDATE` on `generation_last_activity_at` and `generation_error_code` is explicitly revoked.
2. **Layer 2 (Trigger Guard Enforcement)**:
   - Function `public.guard_exam_sessions_worker_columns()` attaches via `trg_guard_exam_sessions_worker_columns BEFORE INSERT OR UPDATE ON public.exam_sessions`.
   - Rejects non-trusted client roles attempting to alter `generation_last_activity_at`, `generation_error_code`, `status`, `active_job_id`, `gemini_call_count`, `retry_count`, `gemini_review_calls`, `approved_at`, or `user_id` with SQLSTATE `42501`.
   - Protects against privilege leakage even if table-level `UPDATE` is inadvertently granted in deployment environments.
   - *Trigger ordering & behavioral contract*: In PostgreSQL, same-event triggers execute in alphabetical order. Unauthorized direct mutations on `exam_sessions` are rejected with SQLSTATE `42501` (intercepted by `trg_finalize_direct_guard` from migration 009 or `trg_guard_exam_sessions_worker_columns` from migration 017). The contract guarantees rejection with SQLSTATE `42501` and clean statement rollback, without depending on trigger-specific exception strings.
3. **Execution Context**:
   - Worker RPCs execute with `SECURITY DEFINER` and pinned search paths (`SET search_path = pg_catalog, public, pg_temp`).

---

## 3. Specifications & Payloads

### 3.1. Enumerate Stale Jobs — `list_stale_generation_jobs`

Designed for periodic background scanners. Employs keyset pagination over `(generation_last_activity_at, id)` supported by partial index `idx_exam_sessions_generation_stale`.

- **Parameters**:
  - `p_cutoff_seconds` (int, default 720): Cutoff threshold. Rejects $\le 0$ with `22023`.
  - `p_limit` (int, default 50): Page size ($1 \le \text{limit} \le 100$). Rejects invalid limits with `22023`.
  - `p_after_activity_at` (timestamptz, optional): Cursor timestamp component.
  - `p_after_session_id` (uuid, optional): Cursor session ID component.
  *(Both cursor components must be supplied together, or both omitted).*

- **Response Payload**:
```json
{
  "scan_as_of": "2026-11-07T08:00:00.123456+00:00",
  "cutoff_seconds": 720,
  "items": [
    {
      "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001",
      "job_token": "a4d3f572-87a1-432d-9477-d31e98d89001",
      "last_activity_at": "2026-11-07T07:45:00.000000+00:00"
    }
  ],
  "next_cursor": {
    "last_activity_at": "2026-11-07T07:45:00.000000+00:00",
    "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001"
  },
  "has_more": true
}
```
When no more records exist, `next_cursor` is `null` and `has_more` is `false`.

---

### 3.2. Fenced Stale Failure — `fail_stale_generation_job_if_current`

Atomically transitions an inactive session to `status = 'failed'` under `SELECT ... FOR UPDATE`.

- **Success Response** (Conditions met, recovery executed):
```json
{
  "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001",
  "recovered": true,
  "previous_job_id": "a4d3f572-87a1-432d-9477-d31e98d89001",
  "status": "failed",
  "error_code": "ERR_GENERATION_INTERRUPTED"
}
```

- **No-Op Response** (Fencing token mismatch, already completed, or retried):
```json
{
  "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001",
  "recovered": false,
  "current_status": "generated",
  "current_job_id": null,
  "reason": "status_not_generating"
}
```
*(Possible `reason` values: `status_not_generating`, `token_mismatch`, `activity_not_stale`)*.

---

### 3.3. Finish Job with Error — `finish_generation_job_with_error`

Allows worker to finalize an interrupted or failed job with an explicit error code.

- **Parameters**:
  - `p_session_id` (uuid): Exam session ID.
  - `p_outcome` (text): `'failed'` or `'partial_generated'` (or `'generated'` with NULL error code).
  - `p_job_token` (uuid): Active job token matching session.
  - `p_error_code` (text): Code matching `^[A-Z0-9_]{3,64}$`.
- **Validation Rules**:
  - `failed` and `partial_generated` **require** a non-NULL valid `p_error_code` (missing code raises SQLSTATE `22023`).
  - `generated` **requires** a NULL `p_error_code` (specifying an error code raises SQLSTATE `22023`).
  - The historical canonical RPC `finish_generation_job(uuid, text, uuid)` retains its existing contract without modification.

- **Response Payload**:
```json
{
  "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001",
  "status": "failed",
  "outcome": "failed",
  "snapshot_id": "d8e3b2a1-0000-0000-0000-000000000001",
  "generation_error_code": "ERR_MODEL_QUOTA_EXHAUSTED"
}
```

---

### 3.4. Periodic Worker Heartbeat — `heartbeat_generation_job`

Periodically extends the generation activity window for active long-running jobs.

- **Parameters**:
  - `p_session_id` (uuid): Exam session ID.
  - `p_job_token` (uuid): Active job token matching session.
- **Concurrency & Monotonicity Contract**:
  - Acquires row lock via `SELECT ... FOR UPDATE` before updating timestamps.
  - Sets `generation_last_activity_at = GREATEST(generation_last_activity_at, clock_timestamp())`, guaranteeing that a valid heartbeat **never decreases** or regresses the activity timestamp even under concurrent transaction lock contention.
  - `heartbeat_at` in the receipt is the authoritative value persisted in PostgreSQL, captured via `RETURNING`.

- **Response Payload**:
```json
{
  "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001",
  "heartbeat_at": "2026-11-07T08:05:00.123456+00:00",
  "status": "generating"
}
```

---

### 3.5. Read-Back after Restart — `load_generation_completed_results`

Returns completed targets, failure details, and the persisted error code:

```json
{
  "session_id": "c1f7b1b0-9c29-4d6b-b46d-318e8a619001",
  "snapshot_id": "d8e3b2a1-0000-0000-0000-000000000001",
  "context": { ... },
  "completed": [ ... ],
  "failures": [ ... ],
  "generation_error_code": "ERR_GENERATION_INTERRUPTED"
}
```

---

## 4. Integration Guide for PR #30 (Quỳnh)

1. **In `backend/app/services/generation/job_repository.py`**:
   - Update `finish(session_id, outcome, job_token, error_code=None)`:
     - When `error_code` is provided or outcome is `failed`/`partial_generated`, call RPC `finish_generation_job_with_error`.
     - Otherwise, continue calling `finish_generation_job`.
2. **In Stale Scanner Routine**:
   - Loop `list_stale_generation_jobs(p_cutoff_seconds=720, p_limit=50, p_after_activity_at=cursor.activity, p_after_session_id=cursor.sid)`.
   - For each item, invoke `fail_stale_generation_job_if_current(session_id, job_token, cutoff_seconds=720)`.
   - Log recovery events only when `receipt["recovered"] is True`.
3. **In Recovery / SSE Reconnect**:
   - When handling reconnection for a failed session, read `generation_error_code` from `load_generation_completed_results` and emit an SSE terminal event with that explicit code instead of fallback `ERR_GENERATION_FAILED`.

