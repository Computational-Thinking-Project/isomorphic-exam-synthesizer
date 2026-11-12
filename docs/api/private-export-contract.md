# W4-MVP-08 — Private export integration proposal

Status: **implementation of isolated pipeline/SDK adapter; Q09/Q10 and OPS handoff
not accepted**. No public route, migration, production ledger or cloud resource is
enabled by this change. Input status lives only in [task plan](../tasks/W4-MVP-08.md).
Depends on [snapshot 07](export-snapshot-contract.md) / PR #58.

## Implemented boundary

`PrivateExportService` is synchronous. Bind `user_snapshot_loader(get_user_db)` to
the verified user's RLS client; never substitute a service-role reader. The HTTP
adapter must derive owner ID from `get_current_user`, never JSON/query parameters.
Run the whole service operation with `asyncio.to_thread` from async handlers.
Do not pass the async `load_approved_export_snapshot` function to `to_thread`.

The service authorizes via snapshot 07 before every export/status/download call.
400/403/404/409 domain errors propagate; transport/compiler/storage exceptions are
converted to fixed codes, without raw exception text. RLS-hidden foreign sessions
remain 404, consistent with #58; do not use a privileged read just to distinguish
403/404. A visible foreign row is rejected with 403 by snapshot 07.

Pipeline: authorized snapshot → durable claim → complete bundle with manifest →
durable expected path/hash/size checkpoint → immutable upload → content read-back
SHA256/length verification → transactional complete → ready. No signed URL in
export/status results. Download/reissue authorizes again, verifies the object and
requests a 3600s URL. `expires_at` starts immediately before the signing call, so
it is conservative; it is not proof that deployment uses the intended TTL.

`ExportLedger` is a port, **not an implementation of DB locking or recovery**.
Only tests supply a RAM double. There is no production fallback without this port.
`SupabasePrivateExportStore` uses the installed SDK signatures, immutable
`upsert=false`, `application/zip`, cache-control 0. It does not create buckets,
inspect ACLs or prove the configured bucket is private. Signed URLs must be HTTPS.
Server clients, their timeouts and bucket limits must be supplied/confirmed by OPS.

ZIP layout preserves the W3 bundler and adds `<root>/manifest.json`. Manifest
contains format `w4-export-v1`, session ID, snapshot revision, and each other file's
relative path, SHA256 and byte length. It excludes itself. The ledger stores the
digest/size of the entire ZIP. No timestamps in the manifest. A packaging/rendering
change that changes artifact semantics must bump `PACKAGER_VERSION`; otherwise a
ready artifact is intentionally reused without recompiling.

## Q09 — proposed durable ledger / RPC decision (Duy)

Preferred design, pending Duy's DB/RPC review:

- Separate export ledger, not new values in `session_status`. Unique current
  identity `(session_id, packaging_key)`; key is SHA256 of
  `w4-export-v1 + "\n" + snapshot_revision`. Snapshot revision includes session ID.
- States idle/no row, preparing, ready, failed. Every write locks the session,
  checks authenticated actor/owner, approved_at and approved/exported status.
  Use service-only RPCs with explicit verified actor, matching the existing server
  writer boundary; no unrestricted table writes for users/anon.
- Claim token UUID + server-clock lease (proposed 900s, subject to OPS timeout
  budget). Only one live claim per identity. Retry ready returns existing metadata;
  live claim returns pending. Failed retries require explicit POST, never GET.
- Before upload, persist expected object path/hash/size/filename under the token.
  No privileged unverified object is published solely because its path exists.
- Complete checks current token, expected receipt and locked approved snapshot;
  ready metadata and `approved → exported` commit in one transaction. Preserve an
  already-exported lifecycle on retries. Fail matches token, cannot undo ready or
  change the session lifecycle. API responses omit internal tokens/object paths.
- Each attempt uses `<session_id>/<packaging_key>/<token>.zip`, consistent with the
  existing session-first Storage policy. Stale workers cannot overwrite current
  objects; fencing prevents them publishing/clearing a newer claim.
- Upload/DB response loss: retain claim + object and return an outcome-unknown
  code. Complete timeout first reads back ready metadata; only exact receipt match
  is success. Do not mark failed, delete object or immediately rebuild blindly.
- Recovery after lease expiry must acquire a recovery claim/lock, inspect the
  persisted expected receipt, verify object bytes and finalize with fencing. If no
  object/checkpoint can be proven, fence the old attempt before an explicit retry.
  Never delete a committed artifact. Orphan cleanup is a separate owner-authorized
  operation after references and active leases have been checked.

Duy needs to confirm/replace these choices and assign a migration slot/ordered
manifest, and settle who runs recovery (preferred backend recovery invoked by
explicit POST, not GET or a new background scanner by default).
Until then, the port is available for integration but no SQL is invented/applied.
Tests of fake concurrency are not evidence for SQL atomicity/fencing.

## I08-11S — Storage/access handoff (Đạt, Duy coordinates access)

Preferred bucket is existing `exam-export-bundles`, private, with the session-first
path above. Current bundler ceiling is 100 MiB (20 MiB per PDF), **not proof the
Storage project accepts that size**. Đạt must confirm bucket name/private ACL,
actual file-size/MIME limits, SDK upload/read-back timeouts, owner-safe test access
and the secure channel/location for credentials. Do not paste credentials/JWTs or
live signed URLs on GitHub. If the real plan limit is smaller, report the conflict
before choosing to lower the app ceiling or change the Storage plan.

The current base policy allows session owners `FOR ALL` Storage access. Confirm
whether approved export objects must be backend-write-only; preferred choice is
backend-only writes for this bucket with owner-authorized URL issuance. This
policy change requires OPS/DB coordination, not silent reuse of a broad policy.

An already-issued URL is a bearer credential for up to 3600s. Cross-owner API
issuance must be blocked; direct opening of an existing URL does not re-check
owner JWT. No claim of per-click auth or revocation without actual Storage proof.

## Q10 — proposed HTTP/UI handoff (Philip)

Preferred first integration: synchronous POST in a worker thread, avoiding a new
job broker while existing 07/compiler code is synchronous. It can take multiple
compiler calls (up to 9 × 30s) plus Storage IO; Philip/Đạt must confirm browser and
proxy timeout budget. If async 202 is chosen, claim must commit before accepting
the request and scheduling work; the current full-operation method must be split
at that durable boundary. Do not use an unclaimed in-memory BackgroundTask as
proof of acceptance or survival across restart.

Proposed routes under `/api/sessions/{session_id}`:

| Endpoint | Preferred behavior |
|---|---|
| `POST /export` | 200 ready with filename/hash/size, 202 pending only if another live claim exists; no client content/keys/owner/revision |
| `GET /export` | 200 state idle/preparing/ready/failed; safe fixed error code on failed; no automatic build, signed URL or state mutation |
| `POST /export/download-url` | 200 `{url, expires_at, expires_in:3600, filename}` only after authorized ready check; no-store |

Service uses `pending` internally, mapped to public `preparing` by the eventual
HTTP adapter. `idle` means no attempt; `failed` requires explicit retry. Default
proposal: poll every 2s, stop after 120s and show explicit refresh; stop on ready,
failed, auth/conflict or unmount. Stopping polls does not cancel a backend attempt.
Disable duplicate clicks; use GET before retry after network/503 outcome-unknown.
Never infer download readiness from session status alone or auto-POST on F5.

Existing auth errors 401/403/404 and snapshot 400/409 remain. Proposed mappings:
422 `ERR_EXPORT_BUILD_FAILED`, 503 compiler/storage/transport unavailable or
outcome-unknown, 409 download-not-ready. DB/Storage availability must not become
409 invalid content. Exact routes/status/error choices and whether to use async
POST remain Philip/Duy discussion inputs, not accepted frontend requirements.

Download filename is `exam_bundle_<session_id>.zip`. Use a user gesture with the
fresh signed URL; the server asks Storage for Content-Disposition download. Test
actual cross-origin/browser behavior; don't assume an HTML download attribute
overrides cross-origin behavior. On URL expiry request a new URL via authenticated
API. Responses containing a URL must use `Cache-Control: no-store` and not log it.

## Verification limits

Local Docker checks exercise compiler/manifest, fake-ledger orchestration and SDK
call shape. No concrete RPC, public HTTP endpoint, deployed Supabase/JWT/PostgREST,
private ACL, real signed URL expiry or full W2 → export proof is delivered yet.
These are required before declaring 08 Done and stay gated on the inputs above.
