# Confirm source endpoint — TASK-204 Q01

Current backend contract on `fix/be1-source-confirm-contract`; FE1 adoption and
independent review remain separate gates. See [handoff](source-confirm-handoff.md)
and [real test evidence](source-confirm-test-evidence.md).

W4-MVP-01 ingestion boundary: ingest-file and ingest-text persist parsed draft
source without scheduling legacy `question_blueprints` extraction. Canonical
production continues through the existing confirmation/retry flow below, after
the durable confirmation receipt. Ingestion request/response contracts and
source revision behavior are unchanged. This local code change does not assert
that any deployed database or frontend has been updated.

1. GET `/api/sessions/{id}` with owner JWT. Echo its UUID `source_revision`.
   Revision and ordered source questions come from one locked RPC snapshot.
2. POST `/api/sessions/{id}/confirm-source` with owner JWT, JSON content type,
   **required** stable UUID `Idempotency-Key`, and `{"source_revision":"<UUID from preview>"}`.
   The deprecated `acknowledged_security_warnings` boolean is ignored; audit is silent.
3. Success: HTTP 200 with `session_id`, `status="blueprinted"`, `confirmation_id`,
   `confirmed_at`, `total_questions`, `total_blueprints`, `canonical_status`, `message`.
   `canonical_status="pending"` and `total_blueprints=0` are valid. Source confirmation
   does not wait for canonical production. There is no deterministic fallback here.
4. Poll GET `/api/sessions/{id}/source-artifacts` for canonical readiness and
   [supported modes](source-artifacts-contract.md). A provider must be available
   for background production or the explicit retry endpoint; otherwise source can
   be confirmed while production remains pending.

| HTTP | Meaning |
|---|---|
| 400 | malformed Idempotency-Key |
| 422 | missing Idempotency-Key (rejected before worker RPC) |
| 401 / 403 / 404 | unauthenticated / foreign owner / missing resource |
| 409 `ERR_SOURCE_REVISION_CONFLICT` | stale preview, including when the current draft is empty or missing answers, or a new action on already confirmed source |
| 409 `ERR_SOURCE_CHANGED` | prepared source differs from locked live content |
| 409 `ERR_IDEMPOTENCY_CONFLICT` | same key rebound to different source/actor/session |
| 422 | missing/malformed UUID revision, or empty/invalid source or missing answers with a matching draft revision |
| 423 `ERR_SESSION_LOCKED` | locked source for a new action |
| 503 / 504 | unavailable or uncertain outcome; reconcile/replay the same key |

Domain errors use `{"error_code":"...","detail":"..."}`; HTTP/Pydantic errors
retain FastAPI's `detail` shape. Unknown confirmation failures can return 500
`ERR_ARTIFACT_OUTCOME_UNCERTAIN`; only proven database rollback errors claim rollback.

Same-key replay is allowed after commit, including after transition away from draft;
it can use an older preview revision and returns the original confirmation ID
after validating receipt binding. A fresh
artifact UUID prepared during retry does not change the source-content binding.
A replay does not reapply source audit or create a second canonical revision.

After timeout or response loss, read session and artifacts before retrying. Persist
the key by authenticated user/session/operation across F5. A 409 requires a refreshed
preview and teacher reconfirmation before starting a new key. Never derive revision
from updated_at, an ingest response, a FE hash or an artifact's per-question revision.

The server checks a draft's revision before source completeness using the same
owner preview snapshot as GET. It then calls the UUID overload of
`confirm_source_artifacts`, which locks and
checks revision before delegating to the original 006 receipt/validation/audit
implementation. It does not call legacy `confirm_exam_source` or require rows in
question_blueprints. Apply 011 + 012 with the updated API as a coordinated rollout;
old timestamp callers are revoked and new readers require the modes field.

Postreview P1/P2 adds migration013: all source INSERT/UPDATE/DELETE, including
warning flags and no-op writes, are refused after confirmation with
`ARTIFACT_SOURCE_LOCKED` (SQLSTATE55000). Draft edits/clone and parent FK cascade
remain supported. Ingest races map this error to HTTP409 with that explicit detail.
Source confirmation preserves its silent audit and stable-key replay.

Migration 014 revokes direct execution of all legacy `confirm_exam_source`
signatures from the application roles and `PUBLIC`. The canonical UUID RPC
remains service-role-only. Configured CORS origins can send `Idempotency-Key`
in a preflight request.

**Breaking FE1 contract / release gate:** a missing key used to generate a server
UUID; it now returns422. FE1 must send and persist the UUID by authenticated
user/session/operation across F5 and timeout. FE1 acceptance has not been verified;
do not claim integrated release readiness. Shared review endpoints are unchanged.
