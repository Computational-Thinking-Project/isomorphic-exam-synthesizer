# W4-MVP-08 — Private export integration proposal

Status: **Q09 architecture accepted with mandatory requirements by Duy** in
[PR63 decision](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6819045971).
RPC/ledger/recovery and forward migration020 are implemented for isolated testing.
Q10 HTTP/UI contract is accepted by [Philip](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6825618302).
Routes are registered; export runtime defaults to disabled. Shared DB application
and the OPS handoff remain gated. No cloud resource is configured by this code.
Input status: [task plan](../tasks/W4-MVP-08.md).
Depends on [snapshot 07](export-snapshot-contract.md) / PR #58.

## Current source-reuse policy — Issue #80

[Issue #80](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/80)
supersedes the earlier blanket source-solution prerequisite. New confirmed-source
fallback/Original Clone/Revert rows without an explanation must carry exactly
`Không có lời giải cho câu hỏi này.`. This is a disclosure, not a validated
mathematical explanation. Existing real solutions remain unchanged, AI candidates
still require their normal validated explanations, and teacher approval remains
mandatory.

The notice is nonempty and uses the existing snapshot/bundle path; preserve it
verbatim, including after question/option shuffle. It needs no new public field,
renderer placeholder or exporter-side AI call. The verified-empty capability below
remains for eligible historical rows; it is not the producer policy for new rows.
Producer implementation/migration024 merged through PR #81 (`dev@26af798`).
The task08 integration tests apply that migration in disposable PostgreSQL;
this does not certify its shared deployment. Full producer-to-export compatibility still needs
verification on a common candidate, including real PDF/private Storage/download.

The original database synchronization incident #75 has reported production
acceptance evidence. That does not certify migration020 or this export runtime:
their actual ledger, private bucket/access and runtime budget gates remain in the
task08 input registry. Ready for code review does not authorize activation.

## Implemented boundary

`PrivateExportService` is synchronous. Bind `user_snapshot_loader(get_user_db)` to
the verified user's RLS client; never substitute a service-role reader. The HTTP
adapter must derive owner ID from `get_current_user`, never JSON/query parameters.
For revised Q01, bind `user_snapshot_loader(user_db, provenance_db=writer)`.
The worker's RPC-timeout client verifies only session-scoped generation receipts
and clone snapshots, after user ownership/approval checks; all exam content stays
on the user/RLS client. Missing verifier or invalid provenance fails closed for
empty solutions. Nonempty AI solutions remain mandatory. Verified fallback/clone
roots can retain empty solution bodies and their headings in all exported formats.
The private service preserves 07's internal validation capability; client JSON
cannot grant this exception. Public JSON, revision identity and packager version
are unchanged for previously supported nonempty snapshots.
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

`ExportLedger` is implemented by `SupabaseExportLedger` and RPC020. Only tests
supply a RAM double; there is no production fallback without the durable adapter.
`SupabasePrivateExportStore` uses the installed SDK signatures, immutable
`upsert=false`, `application/zip`, cache-control 0. It does not create buckets,
inspect ACLs or prove the configured bucket is private. Signed URLs must be HTTPS.
Server clients, their timeouts and bucket limits must be supplied/confirmed by OPS.

Current packaging is **`w4-export-v2`**, following Hùng's requested per-version
layout (20/11/2026, Issue92 follow-up). ZIP root remains `exam_bundle_<session_id>/`.
Each version has exactly `pdf/exam_<code>.pdf`, `latex/exam_<code>.tex` and
`markdown/exam_<code>.md`: exam → that version's answer matrix → detailed solutions.
PDF/TeX start the matrix on a new page after the exam; Markdown flows continuously.
There is no separate `solutions_<code>.pdf` or cross-version `answers_matrix.pdf`
in v2. Root README and LaTeX compile README remain. The ZIP has `3N+3` entries
including `<root>/manifest.json` for N versions. Manifest
contains format `w4-export-v2`, session ID, snapshot revision, and each other file's
relative path, SHA256 and byte length. It excludes itself. The ledger stores the
digest/size of the entire ZIP. No timestamps in the manifest. A packaging/rendering
change that changes artifact semantics must bump `PACKAGER_VERSION`; otherwise a
ready artifact is intentionally reused without recompiling. The v2 bump creates a
different packaging key for the same snapshot: v1 objects/ledger rows stay immutable,
and an explicit Export on the v2 runtime builds a new artifact. Before that export,
v2 status can be idle even for a session already marked exported by v1. Ready v2
exports replay normally. No migration/backfill or deletion is required: RPC020
already namespaces the ledger by version-derived packaging key. Old already-issued
URLs keep pointing to their original immutable objects until expiry.
The FE clears its cached grant when applying a ready status snapshot, since the
current artifact can change across packager versions while keeping the filename.
The next download reissues an authorized link; repeated downloads without a
status refresh can still reuse an unexpired grant.

## Q09 — accepted architecture / implemented RPC020

Duy accepted the architecture; implementation still requires independent review
and deployment acceptance. Migration020 has no dependency on019/021 DDL; both
are now merged in dev. Fresh manifests must retain019→020→021. Isolated tests
also verify adding020 to a populated approved database already containing021.
For such environments, Duy/OPS must verify the applied ledger and the deployment
tool's backfill procedure before execution. Do not renumber an existing migration
or infer applied DB state from Git. No shared migration is applied here.

- Separate export ledger, not new values in `session_status`. Unique current
  identity `(session_id, packaging_key)`; key is SHA256 of
  `w4-export-v2 + "\n" + snapshot_revision`. Snapshot revision includes session ID.
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

Recovery runs in the same service operation on explicit export POST; read/status
never takes over or builds. No background scanner was added. Lease900s remains a
provisional budget, not permission to ship without OPS timeout/worker review.

### SQL and Python interface

`private_export_ledger_command(p_session_id uuid, p_actor_id uuid, p_identity jsonb,
p_action text, p_token uuid DEFAULT NULL, p_receipt jsonb DEFAULT NULL,
p_reason text DEFAULT NULL) RETURNS jsonb` is executable only by `service_role`.
The invoker's actual PostgreSQL role is checked inside the SECURITY DEFINER
function; a JWT role/GUC alone cannot grant writer authority. The ledger table
has RLS and no direct grants to anon/authenticated/service_role.

Identity: `{revision, packaging_key, packager_version}`; SQL recomputes packaging
key with UTF-8 SHA256. Backend supplies actor/session/revision from verified auth
and snapshot07, never client JSON. DB also binds rows to the approved timestamp
and title on first claim and rechecks them before every command. SQL trusts the
backend's content digest; it does not reproduce Python's content serialization.

Receipt: exactly `{object_path, filename, sha256, size_bytes}`; checkpoint path is
bound to its build token. Completion must match the immutable persisted receipt.
Recovery keeps the old path while using a new token; path token and active token
are intentionally different after takeover.

| Command / port | Result / effect |
|---|---|
| read / read | idle, pending, ready or failed; no DML or locks |
| claim / claim | claimed/new build authority; pending/live lease; ready/reuse; recovering/expired receipt with new authority |
| checkpoint / record_built | Persist expected receipt before upload; return the persisted receipt and current token in pending/ready acknowledgments; backend requires both to match, otherwise no upload. Exact replay accepted, changed receipt rejected |
| complete / complete | ready metadata and approved→exported in one transaction; exact replay accepted |
| fail / fail | Only build failures before checkpoint; fenced, cannot clear unknown uploads or ready |
| restart / restart | Only recovery with matching receipt and backend-attested missing/checksum_mismatch; clear unusable receipt and grant another new build token/path |

Claim uses DB-clock expiry under root-first locks, including same-key concurrent
requests. Mutation checks token and live lease; ready completion/checkpoint replay
is allowed after expiry only for identical committed receipt/token. Backend receipt
attests successful Storage verification; SQL cannot inspect Storage bytes.

Verification errors `ERR_EXPORT_OBJECT_NOT_FOUND` (structured Storage `NoSuchKey`
with status404) or
`ERR_EXPORT_CHECKSUM_MISMATCH` allow a fenced restart. Permission errors, timeouts,
5xx, generic/legacy404, `NoSuchBucket`, `AccessDenied` and unknown responses
preserve receipt and return unknown outcome. An SDK that cannot expose an
object-specific code cannot authorize a missing-object restart. Objects
are never deleted here. If restart commits but its response is lost, the caller
also returns unknown; a later explicit request waits for/reclaims the lease.

Migration020 narrows the historical owner policy to raw/source buckets and adds
restrictive INSERT/UPDATE/DELETE guards for the export bucket on anon/authenticated,
including protection against extra permissive policies. A separate SELECT policy
preserves existing owner-only export reads, matching Q09's mutation-only scope.
Signed URLs issued by this backend still require owner authorization and TTL3600;
this does not limit what a user can do with their own Storage JWT.
The migration does not change public
flags, MIME/size limits, secrets or unrelated bucket configuration.

## I08-11S — Storage/access handoff (Đạt, Duy coordinates access)

Preferred bucket is existing `exam-export-bundles`, private, with the session-first
path above. Current bundler ceiling is 100 MiB (20 MiB per PDF), **not proof the
Storage project accepts that size**. Đạt must confirm bucket name/private ACL,
actual file-size/MIME limits, SDK upload/read-back timeouts, owner-safe test access
and the secure channel/location for credentials. Do not paste credentials/JWTs or
live signed URLs on GitHub. If the real plan limit is smaller, report the conflict
before choosing to lower the app ceiling or change the Storage plan.

The historical base policy allows owner `FOR ALL` Storage access. Duy explicitly
requires backend-only mutations for exports; migration020 implements that targeted
change. Đạt must review the policy and applied manifest before deployment, and
provide live ACL evidence; isolated PostgreSQL policy tests are not live proof.

An already-issued URL is a bearer credential for up to 3600s. Cross-owner API
issuance must be blocked; direct opening of an existing URL does not re-check
owner JWT. No claim of per-click auth or revocation without actual Storage proof.

## Q10 — accepted HTTP/UI handoff (Philip)

Confirmed implementation: synchronous POST via `asyncio.to_thread`, with200 ready
or202 only for an already-live claim. It can take multiple compiler calls (up to
9 × 30s) plus Storage IO; the production browser/proxy/worker/lease budget still
requires OPS confirmation. No in-memory background job broker is introduced.
Cancellation/disconnect does not stop or roll back a running thread. Clients
reconcile through GET before a manual POST retry.

Implemented routes under `/api/sessions/{session_id}`:

| Endpoint | Preferred behavior |
|---|---|
| `POST /export` | 200 ready with filename/hash/size, 202 pending only if another live claim exists; no client content/keys/owner/revision |
| `GET /export` | 200 state idle/preparing/ready/failed; safe fixed error code on failed; no automatic build, signed URL or state mutation |
| `POST /export/download-url` | 200 `{url, expires_at, expires_in:3600, filename}` only after authorized ready check; no-store |

Service uses `pending` internally, mapped to public `preparing` by the
HTTP adapter. `idle` means no attempt; `failed` requires explicit retry. Default
accepted UI behavior: poll every 2s, stop after 120s and show explicit refresh; stop on ready,
failed, auth/conflict or unmount. Stopping polls does not cancel a backend attempt.
Disable duplicate clicks; use GET before retry after network/503 outcome-unknown.
Never infer download readiness from session status alone or auto-POST on F5.

Existing auth errors 401/403/404 and snapshot 400/409 remain. Accepted mappings:
422 `ERR_EXPORT_BUILD_FAILED`, 503 compiler/storage/transport unavailable or
outcome-unknown, 409 download-not-ready. DB/Storage availability must not become
409 invalid content. Nonempty request bodies are rejected with400
`ERR_EXPORT_REQUEST_BODY_NOT_ALLOWED`; owner/revision/content are derived on the
server, never from client JSON. URL/status/artifact responses use no-store.

### Runtime opt-in and IO lifecycle

`PRIVATE_EXPORT_ENABLED=false` is the safe default. To enable in an authorized
environment, OPS must first verify the ordered migration manifest, private bucket
ACL and size/MIME limits, then explicitly configure:

- `PRIVATE_EXPORT_ENABLED=true`
- `PRIVATE_EXPORT_BUCKET=exam-export-bundles` (fixed by policy020; other values fail closed)
- `PRIVATE_EXPORT_RPC_TIMEOUT_SECONDS` (integer1–120)
- `PRIVATE_EXPORT_STORAGE_TIMEOUT_SECONDS` (integer1–300)

Timeouts have no implicit production value. Missing settings return503
`ERR_EXPORT_UNAVAILABLE` without creating privileged clients. Service credentials
stay backend-only in existing configuration. The authenticated user/RLS reader
is still supplied through `get_user_db`; its installed SDK default PostgREST IO
timeout is120s. Dedicated privileged RPC/Storage HTTP clients use the configured
per-IO timeouts, with no application retry. Their lifecycle is entirely inside the
worker so a disconnected request cannot close its in-flight Storage/RPC client.
These are IO inactivity limits, not a total runtime deadline; they do not prove
lease900s or proxy budgets sufficient. No shared migration is applied by startup.

Download filename is `exam_bundle_<session_id>.zip`. Use a user gesture with the
fresh signed URL; the server asks Storage for Content-Disposition download. Test
actual cross-origin/browser behavior; don't assume an HTML download attribute
overrides cross-origin behavior. On URL expiry request a new URL via authenticated
API. Responses containing a URL must use `Cache-Control: no-store` and not log it.

## Verification limits

Tests include compiler/manifest, fake-port failure injection and real isolated
PostgreSQL020 RPC/locking/recovery/policy probes. Exact results live in the task
plan. SQL test transport replaces PostgREST only; blob storage is still fake.
Local HTTP transport tests do not establish deployed Supabase/JWT/PostgREST,
Storage ACL/URL expiry or full W2→export. These remain unverified and must pass
before08 Done.
