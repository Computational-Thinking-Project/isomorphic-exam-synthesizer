# TASK-204 source confirmation evidence

Author scope: A0–A3, B0–B3; workflow v0.1 proposed (`506384b`).
Starting code: `ab15447`; fetched dev: `8289971`. The two supplied task plans
are the acceptance inputs. No FE changes, remote migrations or real AI calls.

## Q01 mutation coverage

| Source mutation | Parent lock | Revision update |
|---|---|---|
| ingest-file / ingest-text → replace_source_questions | RPC 002 FOR UPDATE, trigger 006 | 011 AFTER row trigger, same transaction |
| clone_session direct INSERT | trigger 006 FOR UPDATE | 011 AFTER row trigger |
| direct INSERT / DELETE / content UPDATE | trigger 006 FOR UPDATE | 011 AFTER row trigger |
| UPDATE of warning flag (006 content fast path) | 011 parent UPDATE | 011 AFTER row trigger |
| no-op UPDATE | no content change | no bump |
| rollback / failed trigger | transaction rollback | token rolls back with source |
| parent cascade delete | parent already removed | no row recreated |

Migration 010 is empty but its remote deployment history cannot be established
from Git. Retain it unchanged and append 011; do not renumber deployed history.
011 revokes direct worker execution of the timestamp overload. Apply 011 and
deploy the UUID caller together; the old backend cannot confirm after the revoke.
006–009 remain unchanged.

GET `/api/sessions/{id}` uses user JWT and one `get_session_source_preview`
RPC for `session`, `source_revision` (UUID string), and ordered source rows.
Exam versions are fetched separately, outside this snapshot.
POST `/api/sessions/{id}/confirm-source` echoes `{"source_revision":"<UUID>"}`
with a stable UUID `Idempotency-Key`. Success is 200 `blueprinted` even while
canonical production is pending. Confirmation reads the same preview RPC.
For a draft, a stale revision returns 409 `ERR_SOURCE_REVISION_CONFLICT` even
when the current source is empty or missing answers. A matching revision with
empty or incomplete source returns 422, as does a missing or malformed revision.
The canonical transaction still checks revision and content under its lock.
A content mismatch returns 409 `ERR_SOURCE_CHANGED`. A same-key retry with
unchanged content can replay after confirmation even with an older preview
revision. A same-key request with changed content returns 409
`ERR_IDEMPOTENCY_CONFLICT`.

After timeout/read failure the outcome is uncertain: read session and artifact
status, then reconcile using the same key. Persist the key across F5 by authenticated
user/session/operation. On 409 refresh preview, ask the teacher to reconfirm,
then use a new operation/key. Do not infer rollback from a lost response.

Local SQL role stubs test RPC ACL/ownership; they do not prove deployed Supabase
JWT verification, PostgREST overload dispatch or real table-read RLS.

## Checkpoints and acceptance

Implementation commits and exact executed results are kept in the short
[test evidence](source-confirm-test-evidence.md). Q01/Q02 backend behavior is
locally verified; FE1/FE2 integration and independent acceptance remain pending.
No change was made to [TASK-204 PR42](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/42)
or its review state.

Modes use [profile1.0](source-artifacts-contract.md), pinned to BE2 remote7e9377f.
FE2 must use the canonical endpoint and object adapter, including explicit
`ready === true` and valid `[]`. Legacy readiness inference remains a FE owner task.
Migration009 already prevents an authenticated owner from resetting the new token;
the real-DB tamper test grants UPDATE explicitly and still verifies rejection.
Current readers require migration012. Deploy011/012 and the UUID API together.

Postreview remediation (baseline ab9f09a): migration013 freezes source and warning
flags after confirmation; draft writes, clone and parent cascade remain valid.
Ingest freeze races return409 `ARTIFACT_SOURCE_LOCKED`. Confirm now requires the
stable UUID header: missing422, malformed400. This is a breaking FE1 change;
header persistence/adoption remains unverified and blocks integrated readiness.
No FE2/BE2 code or shared review action-key behavior is changed.

PR #43 adds migration 014 to revoke legacy `confirm_exam_source` execution for
`PUBLIC`, `anon`, `authenticated` and `service_role`. The UUID
`confirm_source_artifacts` RPC remains service-role-only. Apply 014 on fresh
and upgraded databases after the earlier migrations. Before Supabase
integration, reconcile migration 010 with BE2's actual deployment history
without renumbering deployed migrations. Verify the owner preview and UUID
confirmation through deployed PostgREST, including replay and denial of the
legacy RPC. Configured CORS origins may send `Idempotency-Key` in preflight.
