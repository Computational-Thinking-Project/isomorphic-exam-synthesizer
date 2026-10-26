# TASK-207a: Generation configuration contract

## Implementation status

This document defines the agreed contract. This branch implements request and
response models, pure validation, a read-only context repository, an internal
store interface and a router factory, covered by unit and API tests.

The router factory requires an explicit store factory. It is currently registered
only in isolated test apps with fixture-only persistence. Product `main.py` does
not register this endpoint. The real save adapter and database RPC integration
remain pending; the tests do not prove database atomicity, concurrency or RLS.

## HTTP request

`POST /api/sessions/{session_id}/config`, with a UUID path parameter and an
authenticated owner. Use the existing auth, user-scoped database client and
ownership helpers. Do not use a service-role client to bypass RLS.

```json
{
  "n_versions": 2,
  "active_variation_modes": ["NUMERICAL"],
  "ordering_preferences": {
    "shuffle_questions": true,
    "shuffle_options": false
  }
}
```

- `n_versions` is required: a strict integer from 1 through 4. Strings, floats
  and booleans are invalid.
- `active_variation_modes` is required: an array of strict strings. Trim each
  item, reject blank items and remove duplicates while preserving first order.
  Mode IDs are case-sensitive; do not translate, uppercase or restrict them to
  a hard-coded enum.
- `active_variation_modes: []` is valid: no variation modes are enabled. Do not
  automatically choose a mode. Source and Blueprint readiness must still pass.
- `ordering_preferences` can be omitted. Both flags default to `true`; a partial
  object defaults only its omitted flag. Each supplied flag must be a strict
  boolean, including accepting `false` unchanged.
- Reject `null` and unknown fields at both request and ordering levels. In
  particular, do not accept `user_id`, `session_id` or `status` in the body.

Saving these preferences does not shuffle questions, call Gemini, generate
versions or open an SSE stream. Those actions belong to subsequent tasks.

## Pure business validation

Allow saves only at session status `blueprinted` or `configured`. A save at
`configured` replaces the current configuration; it does not append a second
current configuration. Reject `draft`, `generating` and all later states.

A session must contain 1–20 source questions. Every source must belong to that
session and have exactly one matching Blueprint with a non-null `confirmed_at`.
Missing, duplicate, unconfirmed or incorrectly linked Blueprints mean the source
is not ready. A confirmed fallback Blueprint is allowed, including one exposing
`NONE`; this operation does not create or modify source questions or Blueprints.

The allowed modes are the **intersection across all source Blueprints**. For
example, `Q1: [NUMERICAL, NONE]` and `Q2: [NONE]` allow only `NONE`. Requesting
`NUMERICAL` reports a conflict for Q2. An empty requested list remains valid.

Stored `variation_modes` must be an array of nonblank strings, including an
empty array. Malformed stored data is an internal error, never silently changed
to `[]`. Validation must perform no database writes, network or AI calls.

## Success response

Return HTTP **200** for both first save and overwrite. Return the normalized
configuration actually saved, not merely the original request or a success flag.

```json
{
  "session_id": "11111111-1111-4111-8111-111111111111",
  "status": "configured",
  "config": {
    "n_versions": 2,
    "active_variation_modes": ["NUMERICAL"],
    "ordering_preferences": {
      "shuffle_questions": true,
      "shuffle_options": false
    }
  }
}
```

## Errors

Business errors use FastAPI's existing `HTTPException.detail` envelope:

```json
{
  "detail": {
    "code": "ERR_CONFIG_CONFLICT",
    "message": "Requested modes are not supported by every source Blueprint.",
    "conflicts": [
      {
        "source_question_id": "22222222-2222-4222-8222-222222222222",
        "unsupported_modes": ["NUMERICAL"]
      }
    ]
  }
}
```

| HTTP | Code | Meaning |
| --- | --- | --- |
| 409 | `ERR_SESSION_NOT_CONFIGURABLE` | Session state does not allow saving. |
| 422 | `ERR_SOURCE_NOT_READY` | Source count or confirmed Blueprint links are invalid. |
| 400 | `ERR_CONFIG_CONFLICT` | Modes not supported by every Blueprint; include per-question `conflicts`. |
| 500 | `ERR_CONFIG_STORAGE_FAILURE` | Malformed internal data or storage failure; return a safe generic message. |

Invalid payloads and UUIDs use the standard FastAPI 422 validation response.
Reuse existing auth/ownership behavior: a known non-owner may get 403, while a
row hidden by RLS may produce 404. Do not bypass RLS just to distinguish them.
Do not replace the global error handler or expose raw database exceptions.

The future route uses the existing shared CRUD rate-limit policy and the
required `Request`/`Response` signature described in
[endpoint conventions](endpoint-conventions.md).

## Database integration gate — Duy supplies SQL/RPC

The proposed RPC name is `save_generation_config`. Its exact parameter names,
result shape and stable error encoding must be confirmed against Duy's SQL
before implementing the repository. Logical inputs are session UUID,
`n_versions`, normalized modes and ordering preferences, through the
authenticated user client. Do not trust a caller-supplied user ID.

One database transaction must:

1. Verify the authenticated owner's access.
2. Lock the session, then read its current state and source/Blueprint data.
3. Revalidate state, readiness and requested modes inside that transaction.
4. Upsert exactly one current configuration per session.
5. Update the session to `configured` and its `updated_at`.
6. Commit both changes together; roll back both if a write fails.

The database must serialize concurrent saves; the last committed save becomes
current. A session that enters `generating` before the locked check must be
rejected. Duy supplies uniqueness or an equivalent mechanism; Python must not
silently delete duplicate records or emulate atomicity with two separate writes.

The result must carry either the saved data sufficient for the success response
or a stable domain error code and details. Python must not inspect human-readable
exception text to discover error categories. A failure response must not leave a
partially committed configuration/status change.

Unit tests with fixtures or fake repositories do not prove database locking,
RLS, rollback or concurrency. Those checks require Duy/OPS to provide the RPC,
an isolated test database, two test identities and agreed seed/cleanup access.
Do not run integration tests against the shared `.env` database. Until these
inputs exist, stop before real persistence and report TASK-207a as incomplete.
