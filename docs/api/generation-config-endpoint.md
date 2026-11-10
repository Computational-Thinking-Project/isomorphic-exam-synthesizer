# Generation configuration and persistence — TASK-207a/b

## W4-MVP-01 / migration 019 (proposed)

Apply migration 019 after 016 (and pending 017/018 migrations).
Existing rows and historical sessions remain unchanged.

`save_generation_config(uuid,int,jsonb,jsonb,jsonb)` retains its 5-argument signature:
- `p_session_id`: UUID of the session (locks session parent first).
- `p_n_versions`: integer between 1 and 4. Other values reject with `22023 / ERR_CONFIG_CONFLICT`.
- `p_active_variation_modes`: JSONB array, defaults to `[]`.
- `p_ordering_preferences`: JSONB object, defaults to `{"shuffle_questions":false,"shuffle_options":false}`.
  Both boolean fields must be explicit booleans. All 4 combinations are valid.
- `p_expected_snapshot`: JSONB manifest matching current canonical snapshot manifest.

Preconditions & Invariants:
- Session status must be `blueprinted` or `configured`, not approved or finalized.
- Canonical sources must be `ready` (if canonical confirmation exists). Pending, running, or failed canonical production rejects with `22023 / ERR_SOURCE_NOT_READY`.
- Historical confirmed sessions with `NO_CONFIRMATION` remain readable and supported for backward compatibility, but unconfirmed drafts cannot authorize configuration or jobs.
- Direct table write guards on `generation_configs` prevent altering configuration once exam versions are finalized (`is_finalized` = true).

Ingestion de-scheduling (ADR-0001):
- `/ingest-file` and `/ingest-text` no longer schedule background blueprint pipelines before confirmation. Canonical preparation is triggered exclusively upon explicit source confirmation via `confirm_source_flow`.

PR #32 owns this SQL/session-detail contract. PR #30 owns Python preflight,
HTTP error mapping, worker orchestration, AI/clone adapters and SSE.
Migrations **010 → 011** follow adopted 004–009. Implementation/self-check is not
independent approval, deployed Supabase evidence or worker/provider E2E.

## Readiness and public profile 1.0

The only published modes are case-sensitive:

| Public ID | Canonical dimension |
|---|---|
| NUMERICAL | values |
| parameter_variation | values |
| context_swap | context |

Keep selected public IDs, deduplicate exact IDs, and store resolved dimensions
separately with mapping_version="1.0". Direct canonical dimension IDs,
STRUCTURAL, variable_inversion, unknown IDs and whitespace/case variants are
rejected. Exactly ["NONE"] normalizes to []; mixed NONE is rejected.

A mode is selectable only when **every confirmed canonical Blueprint** supports
its dimension. GET session detail exposes the three public aliases, including
disabled modes present on only part of the batch. It never exposes all callable
AI dimensions automatically.

- Canonical confirmation exists: use its artifacts; never fall back on RPC error,
  stale/missing evidence or malformed Blueprint.
- Legacy lookup is allowed only after an explicit NO_CONFIRMATION RPC receipt.
  Legacy mode comparison uses exact stored IDs on both GET and save.
- Not ready: is_ready=false, supported_modes=null.
- Ready with no published variation available: supported_modes=[]; explicit []
  remains the Original Clone choice.

Original Clone keeps confirmed source content/options/key/available solution,
uses zero Gemini/provider quota, and belongs to PR #30's separate orchestration.
Do not call the existing AI generator with [] to implement clone. Migration 011
provides a separate `persist_generation_clone` SQL boundary. PR #30 owns its
Python record/adapter and worker integration. Never fabricate AI validation for
a clone. This contract follows the
[integration requirement](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6635728977).

## RPC signatures and access

All RPCs live in public. UUID/text JSON values are strings.

| RPC | Parameters | EXECUTE |
|---|---|---|
| get_generation_source_snapshot | p_session_id UUID | authenticated owner, service_role |
| save_generation_config | p_session_id UUID, p_n_versions INT, p_active_variation_modes JSONB='[]', p_ordering_preferences JSONB='{"shuffle_questions":true,"shuffle_options":true}', p_expected_snapshot JSONB=NULL | authenticated owner, service_role |
| claim_generation_job | p_session_id UUID, p_is_retry BOOLEAN=false | authenticated owner, service_role |
| reserve_generation_quota | p_session_id UUID, p_calls_requested INT, p_job_token UUID | service_role |
| persist_generation_result | see below | service_role |
| persist_generation_clone | p_session_id UUID, p_job_token UUID, p_clone_record JSONB | service_role |
| load_generation_completed_results | p_session_id UUID | authenticated owner, service_role |
| finish_generation_job | p_session_id UUID, p_outcome TEXT, p_job_token UUID | service_role |
| fail_stale_generation_job | p_session_id UUID, p_cutoff_seconds INT=720 | service_role |

PUBLIC/anon cannot execute these RPCs. Private legacy wrappers and hash helpers
are not callable by API roles. Worker tables are service SELECT-only, with writes
through SECURITY DEFINER RPCs. Connection principal determines service authority;
a caller-supplied JWT role claim or custom GUC cannot elevate authenticated.

### Read snapshot and save configuration

get_generation_source_snapshot returns session_id, ready, reason. A ready response
also contains confirmation_id, confirmed_sources, source_order,
confirmed_source_hash and manifest. Each ordered source includes source ID,
question_no, confirmed_input, source/Blueprint revision IDs, source fingerprint,
full canonical Blueprint 0.4.0 and Blueprint fingerprint.

manifest is an object with confirmation_id and sources, an ordered array of
{source_question_id, question_no, source_revision_id, blueprint_revision_id}.
Preflight passes that **unchanged** as p_expected_snapshot. Canonical save without
the manifest fails closed. Legacy four-argument calls remain resolvable through
the optional fifth argument; canonical callers must adopt it. Migration 010
removes the old four-argument function to avoid ambiguous overloads.

save_generation_config locks the parent session, checks owner/state, 1–4 versions,
1–20 sources, boolean ordering preferences, readiness, exact manifest and mode
intersection before updating config/status. It stores source_manifest,
canonical_dimensions and mapping_version alongside existing config fields.
Direct authenticated config writes cannot bypass this boundary.
A revision changing to another ready revision still conflicts with the old manifest.

The response retains success, session_id, config_id, status="configured", config.
config additionally includes source_manifest, canonical_dimensions and mapping_version.

### Hash semantics

confirmed_source_hash is the AI ordered batch hash:
source_fingerprint(prepare_sources(ordered_sources)). Per-source fingerprints hash
one canonical source item, not the entire batch. Fingerprints use SHA256 over
UTF-8 canonical JSON: sorted keys, compact separators, Unicode preserved.
SQL parity tests exercise the existing Python source mapper and AI fixtures;
jsonb::text and concatenated per-source hashes are not substitutes.
The Blueprint fingerprint likewise matches the AI canonical document fingerprint.


Decimal canonicalization is defined on the Blueprint read back from JSONB, as the
worker consumes it. Integer tokens retain arbitrary precision. Decimal tokens
follow Python's binary64 roundtrip and repr notation: fixed notation for exponents
-4 through 15, scientific notation otherwise, .0 for integral floats, and signed/
padded exponents. The helper pins extra_float_digits and accepts a shorter midpoint
representation only when it roundtrips to the exact same float. PostgreSQL's
default rendering differs from Python at both 1e-7 and midpoint cases such as 1e23.

F11 regression expectations and candidate Blueprint fingerprints use the actual
Python helper rather than the SQL snapshot's fingerprint field. Source batch hash,
SHA256, RPC shapes, mapping version and seed are unchanged. The fix does not rewrite
existing immutable contexts or backfill historical results.

### Claim and retry

Initial canonical claim rechecks the saved manifest, persists its execution context
and changes status/token in **one transaction**. It returns the existing fields:
session_id, job_id, status, starting_quota, gemini_call_count, config,
committed_targets; plus snapshot_id and context.

context contains the ready source snapshot/manifest, full ordered sources and
Blueprints, batch hash, base_seed=100, n_versions, ordering_preferences,
public_modes, canonical_dimensions and mapping_version="1.0".
Version indices are 1-based; source indices are 0-based in source_order.
Slot seed = base_seed + version_index*1000 + source_index.

Retry from failed/partial_generated issues a new job_id (fencing token) while
keeping the **same snapshot_id, context, seed and session quota**. It does not
re-read mutable source heads to rebuild the old execution context. Missing or
incompatible context conflicts; display rows cannot reconstruct a missing snapshot.
This PR does not add a new-generation/reset workflow after completion.

The snapshot table's job_token records its creating token; active_job_id on the
session is the current fencing token. They intentionally differ after retry.
committed_targets includes only successful full-result targets with a current
projection, not arbitrary version_questions rows.

### Full result persistence

persist_generation_result signature, in order:

~~~sql
(p_session_id UUID, p_job_token UUID, p_version_index INT,
 p_source_question_id UUID, p_question_no INT,
 p_is_success BOOLEAN, p_error_code TEXT, p_attempts INT,
 p_seed INT, p_request_fingerprint TEXT, p_raw_result JSONB,
 p_content TEXT, p_options JSONB, p_correct_key TEXT,
 p_solution_md TEXT, p_has_warning BOOLEAN DEFAULT FALSE)
RETURNS JSONB
~~~

p_raw_result is the complete QuestionResult.model_dump(mode="json").
The trusted Python adapter validates that model and expected AI request fingerprint;
SQL checks identity, seed, Blueprint fingerprint, metadata and projection consistency.
SQL does not duplicate the entire Pydantic/AI validator or infer model/prompt metadata
from a hash. Warning/teacher-review results are successful when no hard checks fail.
Failed records retain full error/attempt metadata and do not become completed targets.

The RPC locks the session, verifies generating/current token and validates the
snapshot's source/version/question number before writing. Full result, display
projection and session timestamp commit atomically. Failure rolls all back.

- Successful slot + identical full record: return replayed=true without rewriting.
- Successful slot + different record or a later failed request: conflict.
- Failed/missing slot: retry is permitted and replaces all associated metadata.
- Existing display-only slot: explicit conflict, never silently adopted as W2 full result.

The response contains success, replayed, session_id, snapshot_id, version_index,
source_question_id and version_question_id (null for failed targets).
Legacy persist_version_question remains available only for sessions without
canonical confirmation. It rejects canonical W2 sessions.

### Original Clone persistence (migration 011)

`persist_generation_clone(UUID, UUID, JSONB) RETURNS JSONB` accepts an exact record
with these fields; no extra fields or AI-shaped payloads are accepted:

| Field | Value from claim |
|---|---|
| result_kind | `"ORIGINAL_CLONE"` |
| snapshot_id | claim.snapshot_id |
| version_index | integer 1 through context.n_versions |
| source_question_id, question_no | ordered context.confirmed_sources entry |
| source_revision_id, source_fingerprint, blueprint_revision_id | same frozen entry |
| confirmed_source_hash | context.confirmed_source_hash |
| seed | context.base_seed + version_index * 1000 + zero-based source index |
| content | entry.confirmed_input.question_text |
| options | entry.confirmed_input.options, four nonempty strings in original order |
| correct_key | entry.confirmed_input.correct_answer, A/B/C/D |
| solution_md | entry.confirmed_input.solution, unchanged, including null/empty |

Pass the exact confirmed strings, including whitespace and mathematical values.
The existing producer maps a missing source solution to `""`; SQL never invents
a solution. `seed` is deterministic provenance, not a provider request or proof.

The RPC verifies actual service principal, generating status/current token,
frozen modes/dimensions `[]`, snapshot/source revision/slot and every payload field
before writing. It uses the frozen confirmed source even if live source heads
subsequently change; a retry does not replace the frozen context. Full clone
record, canonical/display projection and timestamp commit in one transaction.
No Gemini reserve/call occurs, no quota is reset or incremented, attempts=0 and
the display validation_report stays `{}`. Invalid clone inputs raise an error
without creating a result/projection; they are missing slots on retry.

The server derives `clone_fingerprint = SHA256(UTF8(_generation_json(record)))`.
This hashes the entire exact record with the canonical JSON semantics above;
it is separate from the AI request fingerprint. The stored request_fingerprint
is NULL. AI rows are backfilled with `result_kind="AI_RESULT"`; their raw_result,
AI request_fingerprint and persist_generation_result signature stay intact.
Migration 011 rejects both successful and failed AI writes for frozen clone jobs
(`public_modes=[]` and `canonical_dimensions=[]`) before any result/projection write
with `22023 / ERR_CONFIG_CONFLICT: clone job requires ORIGINAL_CLONE result kind`.
Ordinary AI-mode jobs retain 010's result validation and persistence behavior.

Response: success, replayed, session_id, snapshot_id, version_index,
source_question_id, version_question_id, result_kind and clone_fingerprint.
Identical replay under the current token returns the same display ID without a
write; conflicting input is rejected. Committed success of either kind cannot be
overwritten. A failed/missing slot of the valid kind may be persisted; a stale token cannot replay.
Any prior wrong-kind row, including a failed AI row, conflicts instead of being
replaced by clone persistence. Preserve it for explicit reconciliation.
If a committed projection was changed or removed, reconcile explicitly; retry
must not regenerate/replace that success.

Persist **before shuffling**: this RPC accepts an original projection, not a
pre-shuffled projection or a rewritten solution. PR #30 owns sequencing the
existing shuffle path after generation/review, including answer/solution remapping.
Ordering preferences remain in context. SQL does not compute a shuffle or certify
PR #30's shuffler integration.

[Actual clone RPC request/response/resume sample](../../backend/tests/fixtures/w2_clone_rpc_receipt.json)
contains synthetic test source data and real DB outputs; omitted context is
explicitly listed. The sample is not a Python worker or completed-cache fixture.

### Resume and finish

load_generation_completed_results returns session_id, snapshot_id, context,
completed and failures. Each result entry contains snapshot_id, version_index,
source_question_id, question_no, is_success, seed, request_fingerprint, raw_result,
plus result_kind and clone_fingerprint. committed_targets also includes result_kind.
Preserve raw_result in full. Branch on result_kind **before** parsing raw_result:
`AI_RESULT` uses the existing QuestionResult and AI model/prompt/fingerprint cache
checks; `ORIGINAL_CLONE` uses the clone record, context/slot/source binding and
clone_fingerprint, and must never enter the AI `completed` cache. Unknown kinds
fail closed. Each job accepts only its frozen mode's kind: `ORIGINAL_CLONE` for
clone jobs and `AI_RESULT` for other jobs. Before claim/resume/finish returns,
any active-snapshot row of the wrong kind (successful or failed) raises
`55006 / ERR_CONFIG_CONFLICT: result kind differs from frozen job`.
This conflict preserves existing rows, session status/token and projections;
claim's transaction rolls back any attempted state change. No historical row is
silently excluded or automatically converted. The committed-slot query also
filters by the expected kind before checking projection integrity.
A cache hit does not spend quota or overwrite the persisted provenance.

finish_generation_job accepts generated/partial_generated/failed under the active
token. generated requires every (configured version, snapshot source) to have a
successful full result and its matching current display projection. Display rows
alone or an equal total count in wrong slots cannot authorize completion.
Failure keeps the current status/token.
Migration 011 checks exact source/version/question number, current projection,
content, canonical/display options, key, solution and warning against the persisted
record. An equal count with a wrong slot or altered projection fails. Resume and
claim use the same intact-projection check. This is a generation-time resume
boundary; subsequent review/shuffle changes are not resumable generation evidence.

## Errors and migration compatibility

Business codes are stable prefixes in the PostgreSQL error message; adapters must
inspect the code as well as SQLSTATE, since 22023 covers multiple business errors.

| SQLSTATE | Business condition | HTTP mapping owned by PR #30 |
|---|---|---|
| P0002 | Session not found | 404 |
| 42501 | Ownership/ACL violation | 403 |
| 22023 | ERR_SOURCE_NOT_READY | 409 |
| 22023 | ERR_CONFIG_CONFLICT: modes/input/result invalid | 422 |
| 22023 | ERR_SOURCE_NOT_READY: malformed frozen clone source/options/key/solution | 409 |
| 55006 | ERR_CONFIG_CONFLICT: missing/changed manifest, retry/state mismatch, persisted wrong result kind; stale token | 409 |
| 23505 | Immutable target/display-only conflict | 409 |
| 54000 | Provider quota above 250 | 429 |

Apply 002–011 in order after the base schema, including 004/005 even on a database
that already adopted 006–009 through pinned upstream test inputs. Migration 010 is
atomic and replay-tested with populated result data. It preserves 006–009, source
history and existing config. Do not deploy the abandoned unmerged W2 migration 008;
a database manually using that experimental schema requires explicit reconciliation,
not silent data conversion. No down migration or automatic historical backfill is added.
011 adds a checked discriminator and separate nullable clone fingerprint to the
existing result table, relaxing request_fingerprint only for clone rows. Existing
AI result bytes/projections remain unchanged. Replaying 010 must be followed by
011 to restore the final public wrappers; private 010 claim/finish/AI-persist wrappers retain
their original state/legacy checks and are not executable by API roles. Fresh,
populated-010 upgrade, 011 replay and 010→011 replay are covered by DB tests.
The base schema deliberately keeps W2 tables in the migration chain, as before.

## Evidence and handoff

[Real RPC receipt excerpts](../../backend/tests/fixtures/w2_rpc_receipt.json) are
generated by test_rpc_receipt_for_worker_handoff, including success and failure
resume records. omitted_fields lists the large canonical document repetitions
excluded from this sample; the actual RPC returns them in full.
The fixture has test-only random IDs and no credentials.
It is explicitly labeled synthetic_request_fingerprint=true: its slot/version
hash is a SQL test identifier, not the AI hash of source/Blueprint/seed/modes/
model/prompt. It cannot be used directly as GenerationService completed-cache
evidence, particularly with context documents omitted. PR #30 must use the real
AI fingerprint when integrating.

The AI fixture is restored byte-for-byte from owner handoff PR #41 at 6b0558b
(Git blob 3b0ac5b2117001285b2eb72b37c2c790b6091991). Offline tests check
QuestionResult plus rendered solution/key/seed consistency; JSON roundtrip alone
is insufficient to detect corrupted UTF-8 evidence.

[W2 PostgreSQL tests](../../backend/tests/migrations/test_generation_w2.py) exercise
fresh/upgrade, canonical producer → config → claim → persist → finish/retry,
permission probes, concurrency, rollback and review → shuffle → final approval.
See the [test instructions](../../backend/tests/migrations/README.md#task-207-w2-generation-rpcs)
and [implementation record](../tasks/TASK-207.md).

PR #30 must adopt the fifth config parameter, full context/result envelopes and
the clone RPC/discriminator in its own Python record/adapter. No worker, SSE, browser, live-provider or deployed
PostgREST/JWT/RLS E2E result is implied by these SQL and API-double tests.
