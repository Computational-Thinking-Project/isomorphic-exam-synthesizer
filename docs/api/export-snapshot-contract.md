# Approved export snapshot — W4-MVP-07

Implemented on PR #58 under [Duy's decisions of 11 November](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/58#issuecomment-6801792075).
Derived from `bundle_models.py`, not a replacement for task05's preview API contract.
Consumer acceptance and GitHub approval remain separate. Outstanding inputs:
[W4-MVP-07 plan](../tasks/W4-MVP-07.md).

## Entry point

```python
from app.services.exporter.snapshot_adapter import load_approved_export_snapshot
snapshot = await load_approved_export_snapshot(db, session_id, user_id)
# For Q01 fallback/clone slots with no solution:
snapshot = await load_approved_export_snapshot(
    db, session_id, user_id, provenance_db=provenance_db
)
```

Use the authenticated user's RLS client from `get_user_db`, with `user_id` from
verified authentication. Never use a service client to force 403 instead of an
invisible resource's 404. No client question, solution, key or permutation is accepted.
The coroutine uses synchronous Supabase reads; task08 must run the read/build
operation in a worker thread when calling it from an async route.

Q01 revision (16/11/2026): `db` remains the owner/RLS content reader. The optional
`provenance_db` is a server-owned service client used **only** for read-only
`generation_target_results` / `generation_job_snapshots` verification, scoped to
the already-authorized session and empty-solution question IDs. It cannot supply
content or substitute for ownership. Without this verifier, empty solutions fail
closed; ordinary nonempty solutions never need ledger access. Availability errors
still propagate to task08's sanitized error boundary. This narrow exception
supersedes the previous unconditional ban on service-client reads.

## Output and revision

The result is the frozen, extra-forbid `ApprovedExportSnapshot`. Example:
[`export_snapshot_golden.json`](../../backend/tests/fixtures/export_snapshot_golden.json)
(3 questions × 2 versions, including non-identity question/option permutations).

| Field | Source / rule |
|---|---|
| `session_id` | `exam_sessions.id`, UUID |
| `title` | `exam_sessions.title`, stripped, non-blank, no default |
| `status` | `approved` or `exported`, with valid persisted `approved_at` |
| `revision` | `sha256:` plus lowercase SHA-256 hex of the normalized payload below |
| `versions[].code` | `exam_versions.version_code`, sorted numerically when numeric |
| `versions[].questions[]` | Current approved rows in contiguous display order 1..M |
| Question fields | `id`, `question_no`, `content`, four `options`, display `correct_key`, `solution_md`, `status` |

Hash payload is `{"session_id": <canonical UUID string>, "title": <normalized title>,
"versions": <validated DisplayVersion JSON dumps in output order>}`. Serialize with
`json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`, encode
UTF-8, then hash. This includes IDs, order, content, options, answers and solutions.
It excludes lifecycle status/timestamps: identical content has the same revision
across `approved → exported`; a changed title or question changes the revision.
Title whitespace stripped from the artifact does not change its revision.

Do not substitute `exam_sessions.updated_at`: approval changes it. Preview contract
§4.2 must align with Duy's revision decision; preview currently has no revision
field in its response. Task07 reads DB directly, not the preview response.

## Consistency and validation

Keep table reads: read the session first, require approval, read config, sources,
versions, current questions and keys, then re-read the session. Reject changes to
`user_id`, `status`, `approved_at` or `updated_at` during the read. These are separate
transactions, **not** a transactional snapshot. Consistency relies on the installed
content lock and RPC state/fencing guards after approval. A concurrent
`approved → exported` transition can conservatively reject an in-flight read;
retry with a fresh read. No new read RPC or migration is introduced.

The builder requires:

- Exactly `generation_configs.n_versions` versions (1–4), unique filename-safe codes,
  all finalized with stored seed and permutation receipt.
- Exactly one current approved row for each version/source pair; display slots
  cover 1..M. Canonical numbers retain the positive, unique source labels (for
  example 3, 8, 9), which need not be contiguous. No missing/extra source or slot.
- Exactly one answer-key row per display slot; `correct_option = display_correct_key =
  version_questions.correct_key`; `display_no = question_no`; matching canonical number.
- Non-blank stem, four options distinct after normalization, key A–D.
- Non-blank solution for AI/regenerated candidates. Under [Duy's revised Q01](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/74#issuecomment-6904736595),
  normalize absent/blank display solution to `""` only if canonical solution is
  also absent/blank, `regenerated_from_id` is null, and exactly one successful
  generation receipt matches the question ID/session/source and permitted origin.
  Fallback requires migration021 warning/report provenance. Original Clone requires
  no warning, empty report, empty config modes/dimensions, a valid clone fingerprint
  and the matching frozen empty-mode snapshot. Missing/mismatched/duplicate provenance
  is `409 ERR_EXPORT_SNAPSHOT_INVALID`; a generic AI warning is insufficient.

`DisplayQuestion` still rejects empty solutions on plain JSON construction. The
builder grants an internal, nonserialized per-question validation capability after
checking provenance. `revalidate_snapshot()` preserves that capability through the
compiler/bundler/runtime's defensive revalidation. A JSON dump alone loses it and
must not be treated as a trusted snapshot. No public field or hash payload changes.
PDF/LaTeX/Markdown retain the question's solution heading and blank body; no
placeholder, regeneration or reshuffle occurs during export.

Canonical option/key permutation, solution label synchronization and source numbering
are enforced by shuffle/approval, not recalculated here. PostgreSQL tests install
schema and migrations002–018, exercise actual shuffle/approval, owner RLS, locked
writes, generation fencing and independent concurrent connections. They seed a
historical reviewed exam, not a complete W2 producer run. Superuser DDL or disabled
guards are outside this read contract.

## Errors

| HTTP | `ReviewDomainException.error_code` | Condition |
|---|---|---|
| 400 | `ERR_INVALID_SESSION_ID` | Invalid/noncanonical UUID |
| 403 | `ERR_UNAUTHORIZED` | Visible session owned by another user; defense in depth |
| 404 | `ERR_SESSION_NOT_FOUND` | Missing or invisible under user RLS |
| 409 | `ERR_INVALID_SESSION_STATE` | Not approved/exported or approval timestamp missing |
| 409 | `ERR_INCONSISTENT_ANSWER_KEYS` | Persisted answer mapping mismatch |
| 409 | `ERR_EXPORT_SNAPSHOT_INVALID` | Other invalid persisted content or session changed during read |

The snapshot-invalid code is accepted by Duy. Network, timeout and DB/SDK failures
propagate; **they are not 409**. Task08 must map them through its sanitized
availability/server-error boundary and never return raw SDK exceptions. Domain
messages contain safe field names/version codes/slot numbers only. Logged identity
contains session ID, revision, status, codes and question count; no question, solution
or answer-key content.

## Verification and task08 boundary

[`test_export_snapshot_pg.py`](../../backend/tests/migrations/test_export_snapshot_pg.py)
checks all six slots against the OFF/OFF fixture copied unchanged from PR49 at
`0f760067d9ba343401b46f0c41839065633bc48a`:
[`export_preview_off_off.json`](../../backend/tests/fixtures/export_preview_off_off.json).
The repository parity test runs when task05's `fetch_preview_snapshot` is available;
otherwise it explicitly skips. A local isolated check loaded that exact PR49
repository without changing its branch and passed preview before approval versus
export after approval for every field and the answer matrix. This is not an HTTP,
JWT/PostgREST deployment test or owner acceptance of the fixture.

Task08 receives this model and passes it to the existing bundler. Routes, Storage,
ZIP delivery, signed URLs and the exported-state writer belong to task08. No PDF,
compiler or cloud verification is implied. Run instructions:
[migration test README](../../backend/tests/migrations/README.md#w4-mvp-07-export-snapshot).

To regenerate the export fixture, build `build_approved_snapshot(to_rows(golden_rows()))`
with `backend` and `backend/tests/exporter` on `PYTHONPATH`; write
`model_dump(mode="json")` as sorted-key UTF-8 JSON. Fixture equality prevents drift.
