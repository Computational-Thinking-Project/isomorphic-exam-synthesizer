# TASK-207 integration inputs verified on 2026-10-27

This is a source/contract audit, not approval of the referenced PRs or proof
that their migrations are installed in a database. No remote code was merged.

| Duy PR | Head inspected | State at inspection | Reusable input |
| --- | --- | --- | --- |
| [13](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/13) | `cb5e4e6` | Merged | Session CRUD/detail, source/version row structure, owner-scoped access. |
| [14](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/14) | `9f361a3` | Merged | Verified `CurrentUser`, `authenticated_user_id`, user-scoped DB and ownership helpers. |
| [15](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/15) | `f35622d` | Open | Source ingestion, `replace_source_questions(p_session_id,p_questions)`, row-lock/atomic-write pattern, uncertain-outcome handling. |
| [16](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/16) | `85541d5` | Open | Confirm-source contract, `confirm_exam_source`, confirmed Blueprint links and fallback metadata. |

## Admin input is still missing

Across all four heads, `CurrentUser` has id/email/name/access_token; there is no
application admin field, trusted role source or `require_admin`/`is_admin` helper.
`user_metadata` supplies a display name, not admin authorization. SQL references
to `authenticated`, `service_role`, `postgres` and `supabase_admin` concern DB
execution privileges; they do not identify an authenticated application's admin.
TASK-207c access policy remains pending Duy's explicit source/helper/failure
contract. No speculative guard or production bypass was added.

## Config and Blueprint inputs

PR16's confirm RPC accepts session UUID, expected question count, security-warning
acknowledgment and expected updated_at. It locks the session, checks ownership and
draft state, stamps Blueprint confirmed_at and moves the session to blueprinted.
Migration 003 adds unique(source_question_id), is_fallback and extraction_source.

The fallback extractor returns NUMERICAL for numerical questions or NONE for
verbatim preservation. TASK-207a already permits confirmed fallback data, retains
exact mode IDs, accepts [] and checks the intersection across all Blueprints.
It must still reject unconfirmed sources. The flat fallback representation is
not automatically the structured confirmed Blueprint required by the AI service.
The AI owner must provide the adapter; no silent conversion or Gemini call is implied.

Neither the config-save RPC nor a fenced job/quota/progress adapter appears in
these four PRs. Do not reuse the ingestion/confirm RPC as a config save. Duy must
confirm the config wire contract and durable operations in GenerationJobStore.
No particular additional SQL function names are assumed by Python.

PR15's ingestion background hook remains a placeholder. In the reviewed head,
the option regex can truncate P(A)/f(A) inside option content; this was reproduced
and reported separately. Do not copy that parser logic into generation. Fixes to
Duy's parser/auth/SQL remain on his scope and were not made during TASK-207 work.
