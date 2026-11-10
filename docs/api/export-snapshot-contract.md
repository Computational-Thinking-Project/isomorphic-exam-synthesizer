# Approved export snapshot — adapter contract (W4-MVP-07)

**Status: proposed, not accepted.** Derived from `backend/app/services/exporter/bundle_models.py`
(`ApprovedExportSnapshot`) and the persisted tables. It does **not** redefine the
preview projection of task 05; the preview is only a comparison oracle (see
[W4_TASK_DETAIL](../tasks/W4_TASK_DETAIL.md), Q06). Open decisions are asked on PR #58 and
are marked below. Plan: [W4-MVP-07](../tasks/W4-MVP-07.md).

## Entry point

```python
snapshot = await load_approved_export_snapshot(db, session_id, user_id)
```

`backend/app/services/exporter/snapshot_adapter.py`. `user_id` must come from verified
authentication, never from a request body. The adapter reads persisted rows only; it
accepts no keys, questions, solutions or permutations from a client.

## Output shape

Exactly `ApprovedExportSnapshot` (`extra="forbid"`, frozen). Typed example:
[`backend/tests/fixtures/export_snapshot_golden.json`](../../backend/tests/fixtures/export_snapshot_golden.json)
(3 questions x 2 versions; version 102 permutes questions and options).

| Field | Source | Notes |
|---|---|---|
| `session_id` | `exam_sessions.id` | UUID |
| `title` | `exam_sessions.title` | Required, non-blank; blank fails closed (no default title) |
| `status` | `exam_sessions.status` | `approved` or `exported` only |
| `revision` | `snapshot_revision(...)` | **Open (Duy):** default `sha256:` hash of the validated content; see below |
| `versions[].code` | `exam_versions.version_code` | Sorted numerically when numeric |
| `versions[].questions[]` | current `version_questions` rows | `question_no` is the display slot 1..M |
| `...correct_key` | `version_questions.correct_key` | Display key after shuffle (A–D) |
| `...solution_md` | `version_questions.solution_md` | Non-blank, as stored for the display order |

`revision` default: SHA-256 over the session id and the JSON dump of the validated versions, so
it depends only on approved content and is the same before and after an `approved -> exported`
change. `exam_sessions.updated_at` was proposed in the task 05 contract, but
`finalize_approve_session` changes it on approval. Changing the source only changes
`snapshot_revision` and the `revision` values in the fixtures.

## Read order (consistency)

PostgREST calls are separate transactions. Reads are consistent only because approved/exported
content is locked by migration 009 and the RPC lock checks (read from the code; migrations 005
and 016 not checked, no PostgreSQL test yet). Order: session row first → continue only if
`status ∈ {approved, exported}` and `approved_at` is set → config, sources, versions, current
questions, answer keys → re-read the session and require `user_id`, `status`, `approved_at`,
`updated_at` unchanged. **Open (Duy):** a dedicated read RPC and the client choice (service client:
non-owner 403; user RLS client: non-owner sees 404).

## Fail-closed rules

The builder reuses `DisplayQuestion`/`DisplayVersion` and additionally requires:

- `generation_configs.n_versions` (1–4) equals the number of `exam_versions`; unique codes;
  every version `is_finalized`, with a stored `shuffle_seed` and `permutations` (stale receipt otherwise).
- Exactly one current `approved` row per (version, source question); slots `question_no` = 1..M;
  `canonical_question_no` is a permutation of 1..M.
- `answer_keys` has exactly one row per (version, 1..M); `correct_option` = `display_correct_key` =
  `version_questions.correct_key`; `display_no` = `question_no`; `canonical_question_no` matches.
- Non-blank content and `solution_md` (**Q01 is only a proposal until Tâm settles it**), four options
  that are distinct after normalization, status `approved`.

## Errors (`ReviewDomainException`)

| HTTP | Code | When |
|---|---|---|
| 400 | `ERR_INVALID_SESSION_ID` | Not a canonical UUID |
| 403 | `ERR_UNAUTHORIZED` | Row visible but owned by another user |
| 404 | `ERR_SESSION_NOT_FOUND` | Missing (or invisible under RLS) |
| 409 | `ERR_INVALID_SESSION_STATE` | Not `approved`/`exported`, or `approved_at` missing |
| 409 | `ERR_INCONSISTENT_ANSWER_KEYS` | Answer key table inconsistent with the questions |
| 409 | `ERR_EXPORT_SNAPSHOT_INVALID` | **New, proposed.** Any other inconsistent persisted data or a session that changed during the read |

Messages name the version code and slot, and failing field names only; never content,
solutions, keys or raw values. A sanitized identity (`session_id`, `revision`, status, version
codes, question count) is logged for comparing a ZIP with the preview.

## Not covered here

Export route, Storage, ZIP and signed URL and the `approved -> exported` RPC (task 08); preview
parity (waiting for Tâm to confirm the task 05 fixture); a PostgreSQL test of the real tables.

## Regenerating the fixture

From `backend/` with `PYTHONPATH=backend:backend/tests/exporter`, build with
`build_approved_snapshot(to_rows(golden_rows()))` and write
`snap.model_dump(mode="json")` as UTF-8 JSON with sorted keys and LF endings. A test fails when the
fixture and the builder disagree.
