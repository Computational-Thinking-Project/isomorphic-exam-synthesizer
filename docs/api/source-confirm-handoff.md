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
canonical production is pending. Missing/malformed revision is 422; stale
revision is 409 `ERR_SOURCE_REVISION_CONFLICT`; content race is 409
`ERR_SOURCE_CHANGED`. Same key with changed source content conflicts.

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
