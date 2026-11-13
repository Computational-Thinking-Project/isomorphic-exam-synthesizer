# W4-MVP-01 — Implementation Plan: Source Confirmation → Canonical Blueprint → Generation Configuration

> **Mode:** AUTHOR — planning only; no production-code change in this commit.  
> **Owner:** Duy (BE1 / database). **Workstream:** W4-MVP-01, W4_ASSIGNMENT v2.1, 06–15/11/2026.  
> **Investigation date:** 2026-11-08 (Asia/Ho_Chi_Minh).  
> **Authoritative integration branch:** `dev` at `f104fae6188310b386b9e359c8f72d49c5db43bf` (merge `Docs/update (#50)`, 2026-11-08T10:54:28Z).  
> **Task branch:** `feat/w4-mvp-01-source-readiness`, created directly at the SHA above and independently read back from the GitHub branch endpoint.  
> **Workflow:** `docs/review/WORKFLOW.md` v0.1 **proposed**, not treated as proven team rollout.  
> **Baseline evidence:** Actual GitHub files and tree at the pinned commit, PR file lists, PR conversations/review threads and issues, not local history or design-only descriptions. **No local Git checkout or working tree was available to inspect**; remote branch was created without touching any local uncommitted files. There has been **no local command execution, PostgreSQL run, real Supabase integration, CI run or deployment during this planning action**. Prior test results below are identified as PR-owner/reviewer claims.

## 1. Executive technical summary

Most **source-confirmation infrastructure already exists on `dev`** (PR #43 merged): atomic preview revision; required stable UUID idempotency; source snapshot, SHA-256 fingerprint and confirmation receipt; canonical production after confirmation; current canonical readiness; owner RPCs; and freeze on all source-question writes after confirmation. **Do not build a second confirmation system or redo 006/011–014.**

SQL generation integration is also **merged** (PR #32, migrations 015/016): canonical snapshot/manifest/hash, `save_generation_config`, N 1–4 validation, frozen generation job context, safe original clone persistence and SQL checks. However, its public configuration flow is **not compliant with Issue #45**: both shuffle flags default **ON** in schema/RPC; SQL accepts client-supplied mode selection; SQL and proposed PR #30 Python path still admit a no-confirmation legacy branch; the new `POST /config` backend HTTP route is **only in PR #30, not merged into `dev`**. Stage 3 has no dedicated, owner-authorized, pre-shuffle preferences update endpoint. These are the main W4-MVP-01 integration gaps.

Additional safety boundary: ingestion schedules **legacy** `question_blueprints` fallback *before confirmation*, through `trigger_blueprint_pipeline`. That does **not** publish a canonical `canonical_blueprint_revisions` record and must never authorize generation; eliminate the obsolete scheduling hook after checking legacy consumers, without replacing the working canonical producer.

**Selected implementation approach:** additive migration after the allocated migration 017 (tentatively **018**, only after checking the ledger at coding time); reuse the existing 015 five-argument RPC signature and 006 confirmation/blueprint artifact tables; derive server-owned modes from locked canonical snapshot using a deterministic policy; remove the production legacy readiness fallback for new config; enforce two strict Boolean shuffle defaults OFF; add a distinct RPC for updating only ordering preferences on a reviewed, not-yet-finalized session. Coordinate HTTP/model adaptation with **Quỳnh's open PR #30** rather than competing edits. Leave W4-MVP-03, Review Write, worker/SSE, Stage 3 FE and export/finalize implementation with their existing owners.

## 2. Repository baseline, exact code inventory and dependencies

### 2.1 Git/remote baseline

- GitHub repository: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer
- `get_repo` confirms `default_branch=dev` and push permission. GitHub `refs/heads/dev` and `branches/dev` returned `f104fae6188310b386b9e359c8f72d49c5db43bf`. This is the **observed** remote HEAD, not a claim it can never change.
- Existing branch search did **not** find `feat/w4-mvp-01-source-readiness` before creation. New branch was created from the exact SHA and its remote branch ref was re-read as the same SHA. Neither `dev` nor `main` was changed.
- No worktree exists in the execution environment: `git status --porcelain`, local `git fetch` and local `git pull` were **not** run. GitHub connector provided remote fetches. At implementation time, create a local worktree from freshly fetched `origin/dev` without discarding unrelated changes.
- The current remote tree ends in `backend/migrations/016_stage2_original_clone.sql`. `backend/migrations/010_source_artifact_supported_modes.sql` is **empty/placeholder**; do not renumber it. A separate **open PR #52 has already allocated migration 017**. Confirm remote deployment ledger independently before applying a new SQL migration.
- This plan is a **task-specific execution plan** under `docs/tasks/`, complementary to the official `W4_ASSIGNMENT.md` and `W4_TASK_DETAIL.md`. It must not replace those shared owner-assignment documents or create rival API contract truth.

### 2.2 Read/inspected baseline (code, not only titles)

| Area | Actual file(s), identifiers | Observation |
|---|---|---|
| Team and task | `AGENTS.md`, `CONTRIBUTING.md`, `docs/review/{WORKFLOW,TEMPLATES}.md`, `docs/tasks/{W4_ASSIGNMENT,W4_TASK_DETAIL}.md` | Author/read/review discipline; W4-MVP-01 backend/DB ownership; distinct W4-MVP-03 workstream |
| Product/architecture | `docs/description.md`, `docs/architecture.md`, `docs/adr/0001-confirm-before-blueprint.md`, `docs/change_log.md` | ADR requires canonical extraction after confirmation. Source solution optional in original scope vs required for safe fallback/export remains unresolved |
| HTTP source and preview | `backend/app/api/routes/sessions.py` `get_session_detail`, `ingest_file`, `ingest_text`, `confirm_source` | Source + UUID revision from one RPC; ingestion still schedules legacy blueprint preprocessor |
| Canonical HTTP | `backend/app/api/routes/source_artifacts.py` `source_preview`, `confirm_source_flow`, `get_source_artifact_status`, `retry_source_artifacts`, `run_producer` | Stable key, canonical readiness, background producer; `ready=true` with `supported_modes=[]` is valid |
| Confirmation producer | `backend/app/services/blueprint/producer.py` `ConfirmedArtifactProducer`, `SourceArtifactRepository`; `backend/app/services/blueprint/service.py` `source_fingerprint` | Frozen source and per-source hash; publication via DB-owned canonical heads |
| Legacy preprocessing | `backend/app/services/parser/ingestion_service.py` `trigger_blueprint_pipeline`; `backend/app/services/parser/blueprint_service.py` `ensure_blueprints_for_session`, `extract_default_blueprint` | Creates legacy `question_blueprints` using heuristic ±5, **not** canonical v0.4.0; runs after ingest |
| Models/auth | `backend/app/models/schemas.py` `ConfirmSourceRequest`, `ParsedQuestionItem`; `backend/app/api/dependencies.py` `get_current_user`, `get_user_db`, `assert_ownership` | Mandatory UUID revision, optional solution, JWT owner checks and RLS-aware clients |
| Database source | `backend/migrations/006_stage3_review_and_shuffle.sql` `confirm_source_artifacts`, `publish_canonical_blueprint`, `claim_source_production` and artifact tables; `011`, `012`, `013`, `014` | Durable receipt, fingerprinted revisions, lease/lock, preview UUID, supported modes, source freeze, legacy-confirm EXECUTE revoke |
| Database generation | `backend/migrations/004_save_generation_config_rpc.sql`, `015_stage2_canonical_w2_integration.sql`, `016_stage2_original_clone.sql` | 015 supersedes old signature, canonical snapshot and locked config; still client-controlled modes and ON/ON defaults; 016 clone fence |
| Finalize guard | `backend/migrations/009_finalize_security_boundary.sql` `finalize_guard_direct_mutation`, `finalize_persist_shuffle` | Blocks altered config after finalized version, protects approved/exported; not a replaceable preferences API |
| Finalize HTTP | `backend/app/api/routes/finalize.py`, `backend/app/services/finalize/service.py` `FinalizeService.shuffle_session` | Routes for shuffle/approve/matrix; no preferences-only update route on dev |
| AI mode mapping | `backend/app/services/generation/mode_mapper.py` `compute_supported_modes_summary`, `PUBLIC_TO_CANONICAL_DIMENSIONS` | Can compute allowed dimensional intersection, but doesn't autonomously choose and save modes |
| FE evidence only | `frontend/src/features/stage2-config/Stage2ConfigCard.jsx`, `frontend/src/services/stage2Service.js` | Exposes `selectedModes`; defaults include `shuffle_questions=true`; FE owner must change |
| Existing test harness | `backend/tests/api/test_{confirm_source,ingest,sessions}.py`, `backend/tests/migrations/test_{source_confirmation_revision,source_supported_modes,source_artifacts,source_no_ai_integration,generation_w2,generation_clone}.py`, `backend/tests/migrations/README.md` | Mock routes + opt-in PostgreSQL suites; skipped DB tests **are not DB passes** |
| Review/export relevant | `backend/migrations/006_stage3_review_and_shuffle.sql` `review_revert_question`, `backend/app/services/exporter/bundle_models.py` | Required solution at export/fallback is a cross-owner handoff; not W4-MVP-01 edit scope |

### 2.3 Live PR/issue status observed on 08/11/2026

| Item | State at inspection | Specific integration implication |
|---|---|---|
| [PR #32](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32) | **Merged** | Reuse `015/016` snapshot/config/clone. Reviewer F12 clone-result-type guard independently verified before merge |
| [PR #41](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/41) | **Merged** | AI W2 fingerprints, candidate/seed/resume fixtures and public mapping contract |
| [PR #43](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/43) | **Merged** | Source confirm/UUID/RLS/ACL. F01–F03 reviewer verified; F04 uppercase UUID GET issue **nonblocking/open**. Some GitHub thread-resolution flags lag reviewer verification; distinguish the two |
| [PR #30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30) | **Open Draft**, head `b6b642225b45e2744fda8826ebc70c8db0a3850e` | Owns new `backend/app/api/routes/generation_config.py`, `backend/app/models/generation_config.py`, config services/repository, generation job/SSE. Head **still requires client `active_variation_modes` and defaults ON/ON**. The F02 validator timeout/thread resource bound review thread is unresolved/outdated; track with owner, not W4-MVP-01 |
| [PR #42](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/42) | **Open Draft**, head `7d72dca58118a9d2dd9c8fd343933c931494ce49` | FE1 accepts source confirmation contract; pending integrated FE1/Supabase local evidence and final merge; do not edit files |
| [PR #49](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/49) | **Open**, head `5b5006481bd9be8cda81580154e7340106b87016` | Tâm owns post-shuffle pre-approval preview; review points out real-DB fixture, permutation integrity, source-slot bijection. Avoid `finalize.py`, `finalize/repository.py`, `finalize/service.py` and shared `schemas.py` |
| [PR #50](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/50) | **Merged** at pinned dev HEAD | Official W4 docs v2.1 are already in `dev` |
| [PR #52](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52) | **Open**, head `598b959c69c0f1c6362daed50fd544cb09dd73f7` | **Owns SQL migration 017** for stale scanner, generation interruption/error persistence. F01 author `claimed_fixed`, reviewer re-verification still pending; do not reuse 017 |
| [Issue #45](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/45) | **Open** | No FE mode selector; backend derives modes; N 1–4; shuffle defaults OFF/OFF; Stage 3 edit before final shuffle; all 4 combinations |
| [Issue #46](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/46) | **Open** | 4-attempt failure fallback and Revert to confirmed source, no fabricated missing solutions; Generation/Review owners implement, this task supplies evidence/contract |

Additional open PRs #51 OPS, #47/#48 dependency updates. They do not justify W4-MVP-01 code ownership. **An open PR/fixture is not merged behavior.**

## 3. As-is architecture and verified sequencing

`ingest-file / ingest-text` → `replace_source_questions_atomically` → `source_questions` + `exam_sessions.source_content_revision` bump (002/011). **Separately, current ingestion schedules `trigger_blueprint_pipeline`**, which writes *legacy* `question_blueprints` before confirmation. This call is not a canonical publication path.

`GET /api/sessions/{id}` → `get_session_source_preview` (`FOR SHARE` on parent session) → ordered rows + opaque UUID revision from one source snapshot. `POST /confirm-source` checks JWT/owner and UUID Idempotency-Key; `confirm_source_flow` prepares fingerprints; `confirm_source_artifacts` (006 + 011 overload) locks parent, checks live content and source revision, serializes receipt key with an advisory transaction lock, saves `confirmed_input`/SHA-256 fingerprints and source heads, transitions to `blueprinted`. A replay returns the same confirmation receipt after actor/session/content binding check.

Only **after this receipt**: `ConfirmedArtifactProducer.resume` claims source-production leases; `publish_canonical_blueprint` checks the frozen source revision, publication job token, fingerprint and schema `0.4.0`, publishes immutable `canonical_blueprint_revisions` and updates `source_artifact_heads`. `GET /source-artifacts` (012) exposes `canonical_status`, `ready`, and modes from the same RPC state; `null` means not-ready; `[]` means ready but no mapped public modes. A source edit after confirmation is **not a supported transition**: migration 013 rejects all writes to `source_questions` when session status is not `draft`. Revising a confirmed source therefore needs a separate/new draft workflow; do not silently reopen frozen rows.

`get_generation_source_snapshot` (015) rechecks current frozen source, SHA/hash, manifest and canonical heads. `save_generation_config` locks session with `FOR UPDATE`, checks snapshot/N, writes `generation_configs` and changes session to `configured`, then `claim_generation_job` snapshots config & source for the W2 producer. **Current defects:** SQL defaults ON/ON, client modes are accepted, and `NO_CONFIRMATION` legacy config is allowed despite ADR-0001; PR30's HTTP/config preflight currently follows these semantics.

`FinalizeService.shuffle_session` uses saved `ordering_preferences` and a server-generated trusted permutation; migration 009's finalized/approved guard protects it. There is **no owner-facing preferences update API** for changing only two shuffle values after review and before the first shuffle.

**Authority ordering:** implemented code/migrations on pinned `dev` → merged contracts/ADRs → Issues #45/#46 for changed product requirements → open PR proposals → legacy description (which is not implementation evidence). The historical `004` and `003` SQL text is not an active public contract when later migrations override/revoke it.

## 4. Audit matrix: requirement → actual gap

Status vocabulary: `IMPLEMENTED_AND_VERIFIED` (direct code evidence plus documented independent regression evidence; not a new production test); `IMPLEMENTED_NOT_TESTED` (code inspected, integration unproven); `PARTIALLY_IMPLEMENTED`; `MISSING`; `INCORRECT`; `BLOCKED_BY_EXTERNAL_DEPENDENCY`; `OUT_OF_SCOPE`.

| Requirement | Source / Contract | Actual Code | File / Function | Status | Evidence | Required Action | Owner |
|---|---|---|---|---|---|---|---|
| JWT auth and ownership | TASK-204 | JWT user client and DB ownership | `dependencies.py` `get_current_user` / `assert_ownership` | IMPLEMENTED_NOT_TESTED | Code + PR43 local tests; live Supabase unverified | Test real local Supabase/PostgREST | Duy/OPS |
| Same-response preview/revision | TASK-204 Q01 | Snapshot RPC and GET | `011` `get_session_source_preview`; `sessions.get_session_detail` | IMPLEMENTED_AND_VERIFIED | PR43 reviewer PostgreSQL/F01–F03; no deployed proof | Preserve; add integrated contract test | Duy |
| Stable key, idempotent replay | confirm-source contract | Receipt keyed by UUID with advisory lock | `006/011` `confirm_source_artifacts` | IMPLEMENTED_AND_VERIFIED | Code, PR43 reviewer replay and SQL tests | Regression only, don't reimplement | Duy |
| Stale source revision | confirm-source contract | Locked UUID check, stale 409 | `011`; `source_artifacts.confirm_source_flow` | IMPLEMENTED_AND_VERIFIED | Code and reviewer F02 409 regression | Test race under real PostgreSQL | Duy |
| Frozen immutable source data/hash | ADR + Issue46 | `confirmed_input`, SHA256, source heads; source writes frozen | `006` source tables, `013` freeze trigger | IMPLEMENTED_AND_VERIFIED | DB schema/trigger + PR43 local test reports | Retain, verify with current full migration chain | Duy |
| Canonical publication only post-confirm | ADR0001 | Producer publication RPC requires receipt, but ingest still writes legacy blueprint | `006` `publish_canonical_blueprint`; `ingestion_service.trigger_blueprint_pipeline` | PARTIALLY_IMPLEMENTED | Explicit legacy pipeline call after both ingests | Remove/suppress pre-confirm legacy task; test canonical absence | Duy |
| Canonical readiness with null vs [] | TASK204 Q02 | Canonical heads/status/modes, ready empty allowed | `012`, `source_artifacts.status_payload` | IMPLEMENTED_AND_VERIFIED | Code + PR43 local SQL evidence | Preserve; add FE2 handoff tests | Duy + htbaax |
| Source changed after confirmation | TASK204/Issue46 | Modification rejected, not silently invalidated | `013` `_guard_source_freeze` | IMPLEMENTED_AND_VERIFIED | SQL BEFORE trigger and negative tests described PR43 | Document new-draft remediation; maintain fail-closed | Duy |
| No legacy direct confirm | PR43 F01 | Legacy overload execution revoked | `014` `confirm_exam_source` grants | IMPLEMENTED_AND_VERIFIED | PR43 independent PostgreSQL verification | Recheck deployed PostgREST ACL | Duy/OPS |
| Generation snapshot freshness/hash | PR32/TASK207 | Checks manifest, per-source hash, current head | `015` `get_generation_source_snapshot` | IMPLEMENTED_NOT_TESTED | Code + PR32 SQL test reports, no current live run | Integration coverage and recheck at save/claim | Duy |
| N values 1..4 | W4-MVP-01 | DB 015 checks, PR30 request model checks | `015` `save_generation_config`; PR30 `GenerationConfigRequest` | PARTIALLY_IMPLEMENTED | DB merged, HTTP route only open PR30 | Reuse; negative API/SQL tests after merge | Quỳnh + Duy |
| Generation before ready blocked | ADR0001 | 015 canonical branch blocks, **NO_CONFIRMATION branch allows legacy** | `015` `save_generation_config` | INCORRECT | Explicit `IF snap->>'reason'='NO_CONFIRMATION' THEN` | Remove legacy fallback from new canonical save RPC, preserve history via controlled migration | Duy |
| Modes derived server-side | Issue45 | DB expects client `p_active_variation_modes`; PR30 requires field | `015` `save_generation_config`; PR30 `config_service.validate_generation_config` | INCORRECT | SQL & latest PR30 head code | Derive in locked DB, change PR30 HTTP request contract via owner | Duy DB; Quỳnh Python |
| No user-visible modes | Issue45 | Stage2 has `selectedModes` UI and service sends modes | `Stage2ConfigCard.jsx`, `stage2Service.js` | BLOCKED_BY_EXTERNAL_DEPENDENCY | Direct dev FE inspection | htbaax removes modes UI/state/submit | htbaax |
| OFF/OFF shuffle defaults | Issue45 | Base schema + 004/015 RPC + PR30 model + dev FE use true | `schema.sql`; `015`; PR30 `OrderingPreferences` | INCORRECT | Direct source lines and service default mismatch | Forward migration OFF/OFF; Python+FE owner adaptation | Duy / Quỳnh / htbaax |
| Four shuffle combinations | Issue45 | `009` writer accepts explicit booleans; end-to-end unproven | `009` `finalize_persist_shuffle` | PARTIALLY_IMPLEMENTED | SQL checks, no current real integrated run | Add cross-layer matrix including identity OFF/OFF | Duy/Tâm/htbaax |
| Stage 3 preferences before shuffle | Issue45 | No dedicated route / atomic RPC | `finalize.py` routes, `009` guard | MISSING | Current route inventory | New owner RPC + thin endpoint; freeze after finalized | Duy W4-01 |
| Lock preferences after shuffle/approval | Issue45 | Existing guard prevents post-finalization config mutation | `009` `finalize_guard_direct_mutation` | IMPLEMENTED_NOT_TESTED | Trigger code; specific new RPC not exercised | Preserve; test race with shuffle and status | Duy |
| Canonical source solution policy | Issue46 + original scope | Parse accepts nullable solution, exporter/fallback expects complete | `schemas.ParsedQuestionItem`; `bundle_models.py` | PARTIALLY_IMPLEMENTED | Contradictory approved product docs; no decision Q01 | Fail-closed implementation policy; product owner signoff | Duy + Quỳnh + Tâm |
| Generation four attempts/fallback | Issue46 | Task assigned to PR30 worker; not merged | PR30 `jobs.py`; `service.py` | BLOCKED_BY_EXTERNAL_DEPENDENCY | PR30 open, review scope | Handoff exact confirmed snapshot and missing-solution status | Quỳnh |
| Review current candidate/Revert | W4-MVP-03/Issue46 | Separate workstream; SQL review write exists | `006` `review_revert_question` | OUT_OF_SCOPE | W4 assignment explicitly separate | Handoff source provenance; no W4-01 modifications | W4-03 / Review owner |
| Live Auth/PostgREST/RLS and migrations | W4 DoD | Local SQL tests reported only | `backend/tests/migrations`, deployment | IMPLEMENTED_NOT_TESTED | No full-stack run this action | Require real local Supabase integration + staging check | OPS/Duy |

**Do not label a PR report or static code inspection as production verification.** Some rows marked `IMPLEMENTED_AND_VERIFIED` have only **pinned independent reviewer local PostgreSQL evidence**, and still require release smoke.

## 5. Target behavior and non-negotiable invariants

**S1.** Exact source content viewed by instructor binds to one opaque UUID revision read from the same preview, then to `confirmation_id` and per-source SHA256 fingerprints. No client-provided hash, actor, or arbitrary source payload is authoritative. One successful key binds one source/session/actor; same-key same-source replay returns same receipt.

**S2.** Without a canonical confirmation receipt and all current v0.4.0 blueprint heads, readiness is **false**, even if legacy `question_blueprints` rows exist. `ready=true, supported_modes=[]` is a legitimate Original Clone context, **not** missing data. Reject `CANONICAL_BLUEPRINTS_INCOMPLETE`, stale hash and malformed variation policy.

**S3.** Source writes after confirmation are refused (`013`); stale/revision conflicts do not write receipts, config, job, or new head. A new draft session is needed to revise confirmed content; never issue in-place source invalidation bypass.

**S4.** Owner must be derived from verified JWT / DB `auth.uid()`, never request body; service-role calls require backend identity check. No direct authenticated table updates to config or privileged snapshot tables; grants and RLS must remain least privilege.

**C1.** Only request-exposed configuration decisions are `n_versions ∈ {1,2,3,4}` and the two **independent** strict Boolean flags. **OFF/OFF** is the server, API and FE default when omitted; ON/ON, ON/OFF, OFF/ON also valid. A frontend variation-mode value must not decide AI permission.

**C2.** Modes are determined from the **intersection** of allowed canonical dimensions for **all** confirmed questions under the DB session lock. Preserve public mapping `NUMERICAL` / `parameter_variation` → `values` and `context_swap` → `context`, but choose a deterministic *internal* alias policy (Section 6). Unknown/invalid transformations **fail closed**, rather than turning malformed data into implicit clone.

**C3.** DB saves one authoritative `source_manifest`, `confirmed_source_hash` binding, `mapping_version` and server-computed modes/dimensions; a subsequent claim checks the frozen manifest. SQL is authoritative even if Python performed a preflight on a slightly earlier read.

**C4.** Any later preference modification before shuffle changes **only** `generation_configs.ordering_preferences`; not N, modes, source manifest, canonical dimensions, claim seed, candidate contents or review. Allowed only when session status is `reviewed`, no `exam_versions.is_finalized`, not approved/exported, not generating; updates share the same parent session row lock as finalization. An identical update is idempotent.

**C5.** As soon as any version is finalized, or the session is approved/exported, preferences are immutable. The existing `009` guard must remain active; no direct table mutation, unshuffle or post-approval backdoor. Shuffle runs during Stage 3 *after review*, never when saving Stage 2 config.

**F1.** Missing `solution_md` must not be synthesized as fake/blank content to satisfy fallback/revert/export. Source confirmation can remain compatible with optional solutions under existing product scope, but **fallback, approve and export must fail closed** if no valid solution. The exact upstream intervention to obtain a confirmed solution is **Q01 product blocker for demo acceptance**, not a reason to reimplement confirmation.

## 6. Design alternatives, selected decisions and rollback rules

| Choice | Alternatives considered | Selection / trade-off |
|---|---|---|
| Confirmation implementation | New source receipt tables / reuse 006+011 | **Reuse 006+011**. Already atomic, source-immutable, idempotent; second storage creates divergent authority |
| Pre-confirm Blueprint | Keep parser fallback as canonical / remove legacy hook / rebuild ingestion | **Remove the two legacy scheduling calls**, preserve ingestion parser and records. They write old `question_blueprints` and waste AI/CPU risk; never publish canonical. Keep legacy SQL for historical compatibility until separately retired |
| Server variation modes | Python-only derivation / direct client request / SQL derivation under lock | **SQL locked derivation**, Python model/UI no modes. Python preflight may project but cannot authorize. DB prevents direct RPC bypass and TOCTOU |
| Alias overlap | Write all aliases incl both `NUMERICAL` and `parameter_variation` / one per dimension | **One representative per dimension** for deterministic worker policy: `values` → `NUMERICAL`, `context` → `context_swap`; `canonical_dimensions` is the deduplicated semantic array. This uses existing profile1.0 aliases, avoids double-counting the same permission. **Confirm worker expectation with Quỳnh before merging contract**; if worker must receive both aliases, keep derivation server-only and document stable ordering/normalization with owner |
| None-only canonical policy | Block because no public modes / `modes=[]` clone | **Original Clone with modes=[]** only for a genuinely ready and schema-valid canonical snapshot, reuse 016 safe clone |
| Client-supplied modes during transition | Ignore silently / reject / trust | **Reject non-empty client selection** from new HTTP/API policy (400/422 agreed contract), accept omitted field and optionally an empty legacy compatibility field that has **no authority**. DB derives even for direct calls. This is intentionally breaking for old FE; coordinate rollout with PR30/htbaax |
| Shuffle defaults | Keep old ON / introduce OFF only in UI / forward SQL default | **Forward DB default change + RPC default OFF/OFF + Python/FE defaults**, preserve explicitly saved existing choices; do not mass-rewrite historical configs without approved migration policy |
| Stage3 preference update | Reuse Stage2 `save_generation_config` after `reviewed` / direct FE UPDATE / separate RPC | **Dedicated `update_generation_ordering_preferences` RPC**, because Stage2 RPC only accepts `blueprinted/configured` and would alter immutable generation parameters. Update only two flags with parent lock; refuse once finalized |
| Source missing solution | Reject all confirmation / invent solution / accept source but block downstream | **Interim fail-closed policy:** preserve optional source confirmation, disallow fallback/revert/export where required fields absent, surface blocking status and ask instructor to correct source in a **new draft**; require **Duy + Quỳnh + Tâm** to approve long-term UX before integrated acceptance. No automatic fake solution |
| Migration sequence | Edit 004/015 history / reuse 017 / append safe migration | **Append migration** after #52 reserved 017 (tentative `018_w4_source_readiness_config.sql`); final number determined only after fresh remote + deployed ledger check. Never rewrite historical 004/015/016 |
| Branch integration | Change PR30 owned files independently / coordinate owner patch | **Duy owns DB/new preferences API; Quỳnh owns PR30 config Python edits**, final merge integration once shared contract/tests pass |

The selected decisions are **implementation recommendations**, not claims that absent product/owner approvals have occurred. On schema/API changes update the authoritative `docs/api/generation-config-endpoint.md` and `docs/change_log.md` in the implementation PR. On owner-owned paths request an owner patch, not a second competing contract.

## 7. File ownership and planned delta

| Path | Ownership | Exact proposed delta |
|---|---|---|
| `backend/app/api/routes/sessions.py` | **Duy W4-01**, coordinate if PR30 rebases shared code | Remove only the two ingestion `background_tasks.add_task(trigger_blueprint_pipeline, ...)` calls plus unused import; keep `confirm_source`/GET logic intact; regression source preview and no legacy Blueprint before confirmation |
| `backend/app/services/parser/ingestion_service.py` | Duy W4-01 | Retain `trigger_blueprint_pipeline` only if other call sites/tests depend on it; no canonical publication from here. No broad rewrite |
| `backend/migrations/018_w4_source_readiness_config.sql` (**tentative new file**) | **Duy DB** | Forward-only defaults, hardened 5-arg `save_generation_config`, server mode derivation, `update_generation_ordering_preferences`, guards/grants |
| `backend/scripts/schema.sql` | **Duy DB**, coordinate repo bootstrap owner | Match *fresh bootstrap* defaults OFF/OFF only; do not delete baseline definitions or duplicate migration logic; tests must prove same final state fresh+upgrade |
| `backend/app/api/routes/generation_preferences.py` (**new**) | **Duy W4-01** | Dedicated `PATCH/POST /{session_id}/ordering-preferences` route, strict Pydantic request, JWT, owner check, RPC call with typed errors; avoid `finalize.py` shared with PR49 |
| `backend/app/models/generation_preferences.py` (**new**) | Duy W4-01 | Strict bool model and response independent of PR30 `generation_config.py` |
| `backend/app/main.py` | **Shared** with PR30, explicitly reserve integration edit | Mount preferences route in a minimal non-overlapping patch **after comparing against latest PR30**, do not overwrite its new generation router mounts |
| `backend/tests/api/test_generation_preferences.py` (**new**) | Duy W4-01 | Auth, ownership, payload, typed state/error, same-value replay |
| `backend/tests/migrations/test_w4_source_readiness_config.py` (**new**) | Duy W4-01 | Actual PostgreSQL fresh/upgrade, source/readiness/config/permission/race/Stage3 preferences |
| `backend/tests/api/test_ingest.py`, `test_confirm_source.py`, `test_sessions.py` | Duy W4-01 | Only targeted regression cases; preserve existing fixtures |
| `backend/tests/migrations/README.md` | Duy W4-01 | Document opt-in disposable DB execution with explicit SKIP semantics, migration order and tested SHA |
| `docs/api/generation-config-endpoint.md`, `docs/change_log.md` | Duy DB contract owner with Quỳnh review | Record new wire shape and server-owned mode policy. Don't overwrite settled PR30 job/SSE contract |
| `backend/app/models/generation_config.py`; `backend/app/services/generation/config_{service,repository}.py`; `backend/app/api/routes/generation_config.py` | **Quỳnh, PR #30; NOT EDIT in W4-01 branch until coordinated integration** | Owner removes request-selected modes, defaults OFF/OFF, verifies DB-derived response. Add tests `backend/tests/api/test_generation_config.py`, `backend/tests/generation/test_config_{models,service,repository}.py` |
| `frontend/src/features/stage2-config/Stage2ConfigCard.jsx`; `frontend/src/services/stage2Service.js` | **htbaax W4-04; no W4-01 edits** | Remove modes UI/payload, OFF/OFF defaults, four combos and reload |
| `backend/app/api/routes/review.py` / Review Write SQL; `backend/app/api/routes/finalize.py` and `backend/app/services/finalize/{repository,service}.py` | **W4-03 / Review owner / Tâm PR49; no W4-01 edits** | Handoff only; never redefine current candidate, Revert, final shuffle or preview here |
| `backend/app/services/generation/{jobs,service}.py` | **Quỳnh W4-02; no W4-01 edits** | Handoff fallback source solution and mode policy |

**File conflict gates:** `main.py` is shared with PR30; `schemas.py` is shared with PR49; avoid touching `schemas.py` by adding a separate model. If PR30 merges first, rebase and adapt narrowly. Never modify another owner's unmerged branch or create a second generation-config endpoint.

## 8. Ordered execution plan, with per-step gates

### Step 0 — Re-pin remote, owner overlap and migration ledger (no production changes)

- **Objective / input:** Starting branch at `f104fae...`; access to PR30/#42/#49/#52 and actual deployed migration history if available.
- **Files/functions:** Inspect `AGENTS.md`, `docs/tasks/W4_TASK_DETAIL.md`, `backend/migrations/*`, `backend/scripts/schema.sql`; `get_generation_source_snapshot` and `save_generation_config` signatures. No existing file edits.
- **As-is → target:** 016 latest on dev, 017 unmerged/allocated → record new integration SHA and a definitive **unused** migration number (018 only if 017 merged and ledger reconciled); record PR30 exact head, file ownership and fullchain dependencies.
- **Algorithm/invariants:** Compare `git ls-tree`/remote file contents, PR changed-filename sets and migration hashes; inspect Supabase `schema_migrations` **read-only** if authorized. Never reset/force-push/renumber/replay unknown applied files.
- **Risks:** Repo dev movement, SQL 010 empty, deployment drift, race with PR52.
- **Tests/commands (local isolated checkout, when available):**
  - `git fetch origin dev && git rev-parse origin/dev && git status --porcelain=v1`
  - `git log --oneline origin/dev -12`
  - `git ls-tree -r --name-only origin/dev backend/migrations`
  - `git diff --name-only origin/dev...origin/feat/task-207c-runtime-metrics` (only if remote ref exists)
- **Expected/accept:** pinned SHA, clean implementation worktree or preserved changes through separate worktree, migration manifest with 010/011–016/017, reviewed ownership. **Dependency:** none. **Advance:** unique migration number + no accidental owner collision.

### Step 1 — Lock current confirmation contract and regression baseline

- **Objective / input:** Full 002–016 migration chain, canonical source tests, PR43 acceptance; no changes to working confirmation logic.
- **Files/functions:** `source_artifacts.confirm_source_flow`, `sessions.get_session_detail`, `ConfirmedArtifactProducer.confirm`, `get_session_source_preview`, `confirm_source_artifacts`, `_guard_source_freeze`; `backend/tests/api/test_confirm_source.py` and `backend/tests/migrations/test_source_confirmation_revision.py`.
- **As-is → target:** Keep UUID revision, stable `Idempotency-Key`, frozen `confirmed_input`, same-key replay, 409 stale/422 incomplete unchanged; document error schema and edge cases. Verify exact key reuse after response loss.
- **Transaction:** Parent row lock `FOR UPDATE` on confirm, advisory xact lock on receipt key, content equality before insertion. A duplicate key bound to another actor/session/content must fail atomically.
- **Invariants:** No receipt on error; no double audit/history; source cannot change post-confirm; no privileged user bypass.
- **Risk:** Existing F04 uppercase UUID GET 503 from PR43 nonblocking; normalize as scoped bug only if no shared owner conflict, else track separately. Avoid behavior change to confirmation.
- **Tests/commands:** `PYTHONPATH=backend python -m pytest backend/tests/api/test_confirm_source.py backend/tests/api/test_sessions.py -q -p no:cacheprovider`; for DB `RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p test_source_confirmation_revision.py -v` with disposable PostgreSQL.
- **Expected/accept:** no regressions for no/invalid token (401), foreign owner (403/404 contract), same key replay, changed source 409, malformed/missing key 400/422, locked 423, rollback. **Dependency:** Step0. **Advance:** confirmation verified locally; no need to rebuild it.

### Step 2 — Separate legacy ingest preprocessing from canonical publication

- **Objective / input:** Step1 done, inspect `question_blueprints` call sites and baseline unit tests.
- **Existing edits:** `backend/app/api/routes/sessions.py` (`ingest_file` and `ingest_text`); consider only unused import in `ingestion_service.py`. **No new production files.**
- **As-is:** Both ingests schedule `trigger_blueprint_pipeline`, which calls `ensure_blueprints_for_session` and writes heuristic legacy `question_blueprints` with `NUMERICAL`/`NONE`; canonical `publish_canonical_blueprint` remains gated separately.
- **To-be:** Ingest ends at persistent draft source+revision and returns success; no legacy preconfirmation background blueprint. After explicit `POST /confirm-source` the existing canonical producer runs. Never remove parser source validation, no new AI calls before confirmation.
- **Algorithm:** Delete two `background_tasks.add_task(...)` lines; remove only now-unused import. Do not remove legacy tables/triggers or introduce fake canonical rows. Assert `canonical_blueprint_revisions` and `source_artifact_confirmations` absent before confirmation.
- **Invariants/risk:** Draft source remains mutable and revision bumps; old clients expecting `question_blueprints` before confirmation may be affected (legacy UI/readiness). The SQL config legacy path is addressed in Step3.
- **Tests/commands:** `PYTHONPATH=backend python -m pytest backend/tests/api/test_ingest.py backend/tests/api/test_legacy_blueprint_helpers.py backend/tests/api/test_confirm_source.py -q -p no:cacheprovider`; DB `RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p test_source_no_ai_integration.py -v`.
- **Expected/accept:** successful ingest creates source only; no background canonical or legacy artifact; confirm then produces canonical with fake provider and current source revision. **Dependency:** Step1. **Advance:** tests prove sequencing without relying on comments/doc claims.

### Step 3 — Forward SQL hardening of config and strict ready gate

- **Objective / input:** Step0 migration slot, baseline `015` contract/fixtures, mode mapping profile 1.0.
- **Files:** New `backend/migrations/018_w4_source_readiness_config.sql` (**tentative**, pick real free number) and `backend/scripts/schema.sql` (fresh default); update `docs/api/generation-config-endpoint.md` and migration README. Do **not** modify `004` or `015` in place.
- **Actual functions:** `get_generation_source_snapshot`, `save_generation_config(uuid,int,jsonb,jsonb,jsonb)`, `generation_configs`.
- **As-is:** 015 config default flags true; saves client-provided modes; permits legacy `NO_CONFIRMATION` with legacy blueprints.
- **To-be:** An owner can save only against `ready=true` and a matching canonical `manifest`. SQL picks canonical dimensions and internal public aliases itself; blocks no confirmation, pending/failed, stale/hash mismatch, malformed v0.4.0 policies, missing sources, invalid N, invalid bool flags and client mode injection.
- **DB transaction/locking strategy (outline, adapt to exact PostgreSQL signature):**
  1. `SELECT * FROM public.exam_sessions WHERE id=p_session_id FOR UPDATE`, verify `auth.uid()` (or service role verified by backend); require status `blueprinted/configured` and not approved/exported.
  2. Obtain `snap := public.get_generation_source_snapshot(id)` while parent lock still held. Require `snap.ready IS TRUE`, `snap.manifest = p_expected_snapshot` (strict) and nonempty ordered confirmed sources.
  3. Verify every canonical Blueprint has a valid array of transformations and allowed dimensions, with no malformed entry. Calculate `intersect_dims = ∩ allowed_dimensions(question)` for all questions. Serialize aliases in stable order (`NUMERICAL` if values, `context_swap` if context), `[]` only if a genuinely valid ready snapshot lacks mapped dimensions.
  4. Reject nonempty client `p_active_variation_modes` (reserved legacy param) and any unknown field at HTTP layer; never use it as authority. Decide whether backward compatibility permits `["NONE"]` only as a non-authoritative alias; preferred is **not** to interpret it as client-selected clone.
  5. Validate `p_n_versions BETWEEN 1 AND 4`; strict exact JSON object with two Boolean flags (no extra keys, no null coercion), default both false. Upsert all config columns atomically: modes/dims, `source_manifest`, `mapping_version` and ordering; status configured. Keep public response compatible with worker's persisted internal fields.
  6. Existing `claim_generation_job` later locks and revalidates frozen manifest (015) — preserve it. One lock ordering (`exam_sessions` then related rows) across save, claim and later preference update avoids deadlocks. No trigger disabling.
- **Invariants:** No legacy bypass; no client authority over modes; single config per session; fail-closed invalid canonical; freeze generation hash/provenance. **Risk:** breaking legacy-only sessions; explicit migration policy: preserve historical stored configs but **do not permit new legacy saves** for this MVP workflow. W2 older clients must update before rollout.
- **Tests/commands:** `PYTHONPATH=backend RUN_TASK207_REAL_DB_TESTS=1 python -m pytest backend/tests/migrations/test_generation_w2.py backend/tests/migrations/test_generation_clone.py backend/tests/migrations/test_w4_source_readiness_config.py -q -p no:cacheprovider --tb=short` on explicitly disposable PostgreSQL (follow `backend/tests/migrations/README.md` for DSN/fixture). Also mock unit `PYTHONPATH=backend python -m pytest backend/tests/unit/test_mode_mapper.py -q`.
- **Expected/accept:** fresh + upgrade migrations both yield default OFF/OFF; no confirmation/pending source rejected, ready `[]` clone allowed, N and 4 boolean combinations work; SQL direct caller cannot smuggle unsupported modes. **Dependency:** Steps0–2. **Advance:** real PostgreSQL transaction + ACL tests pass (not only mocks).

### Step 4 — Owner-coordinated Stage2 HTTP/model adaptation (PR30 handoff)

- **Objective / input:** Step3 SQL contract finalized, PR30 rebase/head, JSON fixture from real SQL.
- **Files owned by Quỳnh:** PR30 `backend/app/models/generation_config.py` `GenerationConfigRequest`/`OrderingPreferences`; `backend/app/services/generation/config_service.py` `validate_generation_config`; `backend/app/services/generation/config_repository.py` `GenerationConfigRepository.save_config`; `backend/app/api/routes/generation_config.py`; `backend/tests/api/test_generation_config.py`; `backend/tests/generation/test_config_{models,service,repository}.py`. **W4-01 shall not edit PR30 branch or open a competing POST route.**
- **As-is:** request `active_variation_modes` required; default flags true, preflight allows `NO_CONFIRMATION`; adapter forwards requested modes.
- **To-be:** public request includes only N and optional ordering; modes derived by authoritative SQL; Python preflight enforces `snapshot_ready` (never legacy `NO_CONFIRMATION`); response may contain internal modes for backend compatibility, but FE must not render/submit them. Defaults OFF/OFF at model and service. Validate strict bool, unknown client mode field rejection under `extra=forbid` or documented transitional empty field; never silently apply it.
- **Algorithm:** Review PR30 factory router wiring against the latest `main.py` and use existing `GenerationConfigStore` RPC adapter with `p_active_variation_modes=[]` **only as neutral compatibility argument**; DB computes authoritative choice. Keep `p_expected_snapshot` from the canonical source snapshot, with DB lock recheck. If response mismatch, verify SQL-derived modes instead of expecting equality with a nonexistent client selection.
- **Risk:** PR30 tests and FE2 still expect old required field; schema change must land simultaneously. **No duplicate PR or production file changes owned by W4-01 without owner coordination.**
- **Tests/commands for owner:** `PYTHONPATH=backend python -m pytest backend/tests/api/test_generation_config.py backend/tests/generation/test_config_models.py backend/tests/generation/test_config_service.py backend/tests/generation/test_config_repository.py -q -p no:cacheprovider`; append Step3 DB suite. 
- **Expected/accept:** only `n_versions` + flags accepted by public HTTP, 401/403/422/409 correctly mapped, modes cannot be dictated by malicious client; ready empty → safe clone, pending → denied. **Dependency:** Step3 DB contract; **Advance:** Quỳnh PR30 commit/JSON handoff ready; no pretense PR30 already merged.

### Step 5 — Standalone Stage3 ordering-preferences RPC, pre-finalization only

- **Objective / input:** W4-01 design, `009` finalize guards, existing saved `generation_configs`, session statuses and shuffle writer snapshot.
- **Files:** add `update_generation_ordering_preferences` to new Step3 forward migration; new `backend/app/models/generation_preferences.py` and `backend/app/api/routes/generation_preferences.py`; test `backend/tests/api/test_generation_preferences.py` and `backend/tests/migrations/test_w4_source_readiness_config.py`; limited `backend/app/main.py` router mount only on integration head after PR30 collision check.
- **As-is:** Stage2 `save_generation_config` disallows `reviewed`; no review-stage preferences route; direct authenticated config writes restricted; finalize guards protect locks.
- **To-be:** authenticated session owner can update **only** two Boolean preferences while status `reviewed` and **before first shuffle**, with no finalized versions or approval. Same-value retry returns same persisted result. No source/regeneration/state or preview side effects.
- **Transaction/SQL pseudocode:** 
  - `SELECT * FROM exam_sessions WHERE id = p_session_id FOR UPDATE`; missing → 404/P0002; foreign owner → 403/42501.
  - `IF status NOT IN ('reviewed') OR approved_at IS NOT NULL THEN fail 409/423`; generating/partial/generated not allowed for this final-choice API (initial Stage2 config covers earlier choice).
  - `IF EXISTS (SELECT 1 FROM exam_versions WHERE session_id=id AND is_finalized) THEN fail 423/55000`; note `009.finalize_guard_direct_mutation` is independent backstop.
  - `SELECT generation_configs WHERE session_id=id FOR UPDATE`; missing or stale manifest/invalid config → 409 (do not auto-create).
  - Strict `jsonb_typeof='object'`, exact two keys, `jsonb_typeof(...)= 'boolean'`; reject injection/extra keys.
  - `UPDATE generation_configs SET ordering_preferences=p_flags WHERE session_id=id`; return session ID, flags, status, optional updated timestamp. Do not change `exam_sessions.status`. Shuffle writer will later lock same session and use the saved flags.
- **Risk:** concurrent user preference update versus first shuffle: parent `FOR UPDATE` serialization ensures one order. If shuffle finishes first, reject preference update 423; if preferences win first, shuffle reads new flags. Race with approval locked; no bypass of guard.
- **Tests/commands:** `PYTHONPATH=backend python -m pytest backend/tests/api/test_generation_preferences.py -q -p no:cacheprovider`; `RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p test_w4_source_readiness_config.py -v` if implemented as unittest fixture, or `RUN_TASK207_REAL_DB_TESTS=1 PYTHONPATH=backend python -m pytest backend/tests/migrations/test_w4_source_readiness_config.py -q -p no:cacheprovider` if using TASK207's real-DB fixture. Pick **one** actual harness and document DSN/opt-in; never point destructive tests at shared DB.
- **Expected/accept:** four combos accepted when reviewed/pre-finalized, unchanged N/modes/hash, cross-user blocked, pre-shuffle update observed by trusted shuffle, after shuffle/approved/exported blocked. **Dependency:** Step3. **Advance:** real-DB interleaving test and full row equality before/after rejected calls pass.

### Step 6 — Freeze migration and regression through generation/finalize boundaries

- **Objective / input:** Step3–5 RPCs, PR30 candidate (when available), current 009 security guard and 015/016 worker snapshots.
- **Files:** W4-01 migration integration tests, `backend/tests/migrations/test_generation_{w2,clone}.py` only if owner accepts shared test additions; `backend/tests/migrations/test_finalize_security_boundary.py` regression **without changing `finalize_*` files**.
- **As-is → target:** Current 009/015/016 already enforce snapshot/job tokens and finalized lock → verify new preference-only RPC does not weaken any existing lock, status, answer key or clone invariant.
- **Algorithm:** Set up source+confirmation+ready canonical; save N, derive modes, claim job; verify immutable `generation_job_snapshots`. Build reviewed session via existing review RPC fixture, race `update_generation_ordering_preferences` against `finalize_persist_shuffle` (use independent DB connections and `pg_blocking_pids` evidence, not sleeps). Test failure rolls back complete row/receipt, and preserve identity permutation in OFF/OFF.
- **Invariants:** Frozen generation content may not be affected by Stage3 ordering; no config after finalized; no direct overwrite of `exam_versions`/`answer_keys`.
- **Risks:** PR49 projection contract not merged; limit to DB existing shuffle writer until owner merges.
- **Tests/commands:** `PYTHONPATH=backend python -m pytest backend/tests/migrations/test_w4_source_readiness_config.py backend/tests/migrations/test_finalize_security_boundary.py -q -p no:cacheprovider` with required opt-in, plus `PYTHONPATH=backend python -m pytest backend/tests/api/test_finalize_shuffle.py -q -p no:cacheprovider`.
- **Expected/accept:** race produces one serial outcome and no malformed artifact; frozen source/seed and answer matrix preserved. **Dependency:** Steps3–5; **Advance:** migration upgrade test + rollback/lock tests pass with actual PostgreSQL.

### Step 7 — Cross-owner handoff contracts and conflict-free integration

- **Objective / input:** Steps3–6 ready, latest heads PR30/42/49/52 and W4-03 task branch. Coordinate via PR discussion; no unsolicited peer-branch edits.
- **Files:** authoritative `docs/api/generation-config-endpoint.md`, `docs/api/source-artifacts-contract.md` only if response changes, `docs/change_log.md`, this task plan checklist; owner-specific file list in Section 7.
- **As-is → target:** Shared policy no longer negotiable: source confirmation precedes canonical, null/[] states correct, modes are backend-owned, defaults OFF/OFF; FE1/FE2/worker honor same contract and use current SHA.
- **Handoff packets:** To Quỳnh: signed JSON request/response, confirmed source fingerprint/manifest, canonical dimensions, internal modes and Q01 failure semantics; to htbaax: only N+2 flags, no modes UI, readiness error/refresh, Stage3 update API and 423 lock; to W4-03: immutable `confirmation_id`/`source_revision_id`/`source_question_id` and invalid candidate/fallback flags, no Review Write API edits; to OPS: numbered migration order and fresh/upgrade proof.
- **Risk:** PR30 ``main.py` overlay, PR49 shared finalize/Pydantic files, #52 migration order, PR42 FE1 key behavior. Resolve through small scoped integration commits after upstream merge or owner's agreed patch.
- **Tests/commands:** `git diff --check`; `ruff check backend/app scripts/blueprint`; `mypy backend/app --ignore-missing-imports`; `PYTHONPATH=backend python -m pytest backend/tests/api backend/tests/unit/test_mode_mapper.py -q -p no:cacheprovider`. FE owner: `cd frontend && npm test && npm run lint && npm run build` **confirm actual `package.json` scripts first; adjust test command if npm test not defined**.
- **Expected/accept:** no parallel implementations, no shared file overwrites, versioned JSON fixtures and clear PR refs. **Dependency:** Steps0–6; **Advance:** owner ACK and fullchain passes.

### Step 8 — Fresh-install, upgrade, deployed local Supabase and release gate

- **Objective / input:** Integration branch includes #52 migration 017 (or verified alternative), #30 routes and W4 config migration, actual local Supabase (Auth/JWT/PostgREST/PG/RLS), fake AI.
- **Files:** `backend/tests/migrations/README.md`; opt-in suites; `docs/integration-test.md` and OPS runbook **only through OPS owner coordination**.
- **As-is → target:** Prior local PostgreSQL/fixture-only reports → one reproducible current-head fresh+upgrade run and authorized API calls through deployed PostgREST. Production staged deployment remains a separate OPS action; do not deploy in this task.
- **Method:** Build disposable fresh database with repo documented schema+ordered migrations; build populated legacy/upgrade fixture and apply forward migration only. Compare schema/function definition/grants/defaults/row preservation across both. Use two real local Auth users to test 401/403 and prohibited direct DML; fake AI canonical producer; GET preview → POST confirm → GET readiness → save config → Stage3 preferences → trusted shuffle on current integrated head.
- **Invariant/risk:** No tests may run destructive DDL against a shared Supabase database; local JWT stubs alone do not prove PostgREST/RLS; don't claim integration if PR30/FE1 still open.
- **Commands after local environment is provisioned:** `RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -v` (documented Docker disposable path); `RUN_TASK207_REAL_DB_TESTS=1 PYTHONPATH=backend python -m pytest backend/tests/migrations/test_generation_w2.py backend/tests/migrations/test_generation_clone.py backend/tests/migrations/test_w4_source_readiness_config.py -q -p no:cacheprovider --tb=short` where applicable; `ruff check backend/app scripts/blueprint`; `mypy backend/app --ignore-missing-imports`. Use `backend/tests/migrations/README.md` and `docs/setup-docker.md` for actual environment/DSNs; never infer a PASS from SKIP.
- **Expected/accept:** exact HEAD/SHA, DB engine/version, applied migration list, non-skipped test counts and sanitized HTTP/DB evidence. **Dependency:** Steps0–7 + available integration branches; **Advance:** W4-MVP-01 coding DoD reached; full Golden live is W4-MVP-13 separate gate.

## 9. API contracts (current vs proposed)

### 9.1 Existing, preserve as-is unless an observed defect is reproduced

| API | Request | Response / readiness | Errors |
|---|---|---|---|
| `GET /api/sessions/{id}` | Authorization Bearer owner JWT | `source_questions` + UUID `source_revision` from same `get_session_source_preview` RPC; separate `blueprint_summary` projection | 401, 403/404, 503 source unavailable; uppercase UUID GET F04 known |
| `POST /api/sessions/{id}/confirm-source` | owner JWT; **required** UUID `Idempotency-Key`; `{"source_revision":"<UUID>"}` | 200 `status=blueprinted`; `confirmation_id`, `canonical_status` possibly `pending`; canonical work after commit | 400 malformed key; 422 missing key/invalid source; 409 stale `ERR_SOURCE_REVISION_CONFLICT` / changed / idempotency conflict; 423 locked; 503/504 uncertain; replay same key |
| `GET /api/sessions/{id}/source-artifacts` | owner JWT | `ready=false` and `supported_modes=null` pending/running/failed; `ready=true` and `supported_modes=[]` valid empty public set | 401/403/404; fail closed |
| `POST /api/sessions/{id}/source-artifacts/retry` | owner JWT | 202 until completed, 200 if already ready; no artificial canonical rows | 409 generating, 423 locked, 503 provider unavailable |

### 9.2 Proposed Stage2 public config (PR30 owner must adopt)

Request for `POST /api/sessions/{id}/config`:

```json
{
  "n_versions": 2,
  "ordering_preferences": {
    "shuffle_questions": false,
    "shuffle_options": false
  }
}
```

- `ordering_preferences` may be omitted and then **both flags default false**. If provided, accept only two actual Booleans, not strings `"false"`, null or extra keys.
- `active_variation_modes` is **not accepted as a selectable field**. The server derives and persists internal modes from all canonical blueprints. The 015 RPC's parameter remains only for old signature compatibility, never for client authority.
- Canonical ready with no compatible public dimensions saves internal `active_variation_modes=[]` = safe Original Clone. Not-ready and malformed policy fail closed.
- Response: maintain `session_id`, `config_id`, `status=configured`, persisted `n_versions`/`ordering_preferences`; internal modes/manifest may be retained in backend response for worker compatibility but **not surfaced as user choices**. Identify separately any API schema change necessary for PR30.
- Errors: 401 token; 403 wrong owner; 404 missing session; 409 wrong state/stale manifest; 422 invalid N/flags or source not ready (contract currently `ERR_SOURCE_NOT_READY`); 400/422 forbidden client-selected modes, depending on approved Pydantic contract; 503 uncertain storage. Align error-body wrappers with PR30's current `{"detail":{"code":...}}` vs `ReviewDomainException` `{"error_code":...}`; **do not invent already-implemented response shape**.

### 9.3 Proposed Stage3 preferences-only endpoint

Suggested HTTP path: `PATCH /api/sessions/{id}/ordering-preferences`, pending coordination with frontend/PR30 route naming. Proposed payload:

```json
{
  "shuffle_questions": true,
  "shuffle_options": false
}
```

Expected 200 `{ "session_id": "<UUID>", "status": "reviewed", "ordering_preferences": { "shuffle_questions": true, "shuffle_options": false } }`. Backend calls the distinct locked `update_generation_ordering_preferences` RPC. Only `reviewed` and **not-yet-finalized**; identical calls return same persisted flags; all other config fields unchanged. 401/403/404 auth/ownership, 422 invalid strict booleans/shape, 409 wrong state/config missing, 423 shuffled/finalized/approved/exported, 503 storage uncertain. **No partial one-flag update** unless separately approved; requiring full preferences object removes accidental re-enabling from omitted fields.

This endpoint **does not run shuffle**. The current `POST /finalize/shuffle` remains owned by Finalize; preview/export order is W4-05/07/08.

## 10. Comprehensive test matrix and evidence type

**Categories:** `M` = unit/API mock fixture, can code and run immediately without DB; `P` = **actual disposable PostgreSQL** (SQL transaction/locks/RLS roles; not a stub); `I` = integration with PR30/FE1/FE2/PR49 merged or branch-adopted; `L` = real local Supabase Auth/PostgREST/RLS smoke (not covered by P). List each category explicitly. Every test records SHA and non-skipped count.

| # | Scenario / expected | Level | Test location / owner |
|---:|---|---|---|
| 01 | No Bearer token → 401 | M, L | `test_confirm_source.py`, new config/preferences API / Duy |
| 02 | Invalid/expired JWT → 401 | M, L | API Auth fixture and local Supabase / Duy/OPS |
| 03 | Foreign owner GET/confirm/config/preferences → 403 or documented 404; no data leak | M, P, L | `test_ownership.py`, new API/SQL ACL / Duy |
| 04 | Direct authenticated config/table/privileged RPC bypass rejected | P, L | New migration test grants/role checks / Duy |
| 05 | Draft GET preview revision matches ordered persisted source | M, P | `test_sessions.py` / Duy |
| 06 | Confirmation success: one frozen snapshot + receipt/heads | M, P | `test_confirm_source.py`, `test_source_artifacts.py` / Duy |
| 07 | Duplicate same UUID key+same revision/source returns same receipt, no new audit | M, P | `test_source_confirmation_revision.py` / Duy |
| 08 | Same idempotency key rebound to another source/session/actor → 409, rollback | M, P | Existing confirmation suites / Duy |
| 09 | Stale preview after source reingest → 409 before incomplete-answer check | M, P | PR43 F02 regression / Duy |
| 10 | Source update/DELETE/INSERT incl warning/no-op after confirmation refused | P | `013` trigger cases / Duy |
| 11 | Source draft edit changes revision, stale old confirmation no receipt | P | `011` test / Duy |
| 12 | Missing answers → 422 on matching revision | M, P | Source validation / Duy |
| 13 | No confirmation but legacy `question_blueprints` present → config **denied** | P, I | New SQL + PR30 config service / Duy/Quỳnh |
| 14 | Canonical pending/running/failed → no config/job; `supported_modes=null` | M, P, I | Source tests, config API / Duy/Quỳnh |
| 15 | Ready canonical `supported_modes=[]` → valid `modes=[]` clone | P, I | `test_generation_clone.py`, PR30 worker / Duy/Quỳnh |
| 16 | Blueprint incomplete/stale hash/bad transformation dimension → fail closed | P | `get_generation_source_snapshot`/new SQL / Duy |
| 17 | `n_versions` = 1,2,3,4 accepted | M, P, I | PR30 request tests + new SQL / Quỳnh/Duy |
| 18 | `n_versions` = 0,5,negative, bool, float, string/null rejected | M, P | PR30 model/SQL / Quỳnh/Duy |
| 19 | OFF/OFF missing prefs and explicit OFF/OFF both persist false/false | M, P, I | `schema.sql` + new RPC + PR30/FE / all |
| 20 | ON/OFF, OFF/ON, ON/ON accepted independently | M, P, I | New config/finalize tests / Duy/Tâm/htbaax |
| 21 | Malformed Boolean strings/null/extra keys rejected, no commit | M, P | Pydantic new API + SQL JSON guard / Duy |
| 22 | Client injects unsupported/public modes: cannot select any server mode | M, P, I | PR30 request/SQL tests / Quỳnh/Duy |
| 23 | Client tries to force `[]` clone when canonical allows variation; server decides | P, I | Config store + PR30 handoff / Duy/Quỳnh |
| 24 | Alias overlap values→one representative, stable order/hash on repeated calls | M, P | `test_mode_mapper.py` + SQL / Duy/Quỳnh |
| 25 | Confirm/save concurrency: save waits for source publication/lock, no stale commit | P | 2 PostgreSQL connections, `pg_blocking_pids` / Duy |
| 26 | Two concurrent saves: one final config, no duplicate row; last serial winner only pre-generation | P | New migration test / Duy |
| 27 | Config save racing generation claim: frozen manifest stays coherent | P, I | 015+new SQL DB; PR30 route / Duy/Quỳnh |
| 28 | Reviewed preferences update succeeds; changes only ordering two flags | M, P | New prefs tests / Duy |
| 29 | Preferences update racing shuffle: one serial order, no mixed receipt | P, I | New SQL + finalize security / Duy/Tâm |
| 30 | Generating/partial/approved/exported/finalized refuses preference updates | M, P | New preferences API/SQL / Duy |
| 31 | Same preference update repeated → same values, no unintended state transition | M, P | New preferences tests / Duy |
| 32 | Missing `solution_md`: no fabricated fallback, no approve/export | M, P, I | Source/config safety handoff, PR30+export tests / Quỳnh/Hùng |
| 33 | N=1..4 Original Clone committed result type; AI_RESULT injection rejected | P, I | `test_generation_clone.py` / Quỳnh/Duy |
| 34 | 4 attempt exhaustion emits exact source snapshot pending review warning | I | PR30 worker fake AI + DB; Issue46 / Quỳnh |
| 35 | Revert returns immutable confirmed source not earliest AI candidate | P, I | Review owner RPC and W4-03 read / Review owner |
| 36 | Session `is_finalized`/approved lock preserves keys/permutation/solution | P, I | `test_finalize_security_boundary.py` / Duy/Tâm |
| 37 | Fresh bootstrap 002–new migration, OFF/OFF defaults, correct grants | P | New migration test / Duy |
| 38 | Populated upgrade 002–016→017→new migration preserves existing config choices/history | P | New migration test / Duy |
| 39 | Repeat forward migration when supported: idempotent schema/code; no rights expansion | P | New migration test / Duy |
| 40 | Cross-API Generation/Review regressions after PR30/PR49 merged | I, L | PR30 job/SSE/Review tests; Golden / owners |
| 41 | FE1 loses HTTP confirm reply, same-key replay, F5, source revision 409 | I, L | PR42 FE + real local Supabase / Philip |
| 42 | FE2 hides modes, two OFF defaults, Stage3 final choice survives F5 | I, L | `Stage2ConfigCard`/Stage3 owner tests / htbaax |

**Execution truthfulness:** Running a default pytest/unittest with all PostgreSQL tests **skipped** does not satisfy any `P` row. A fake JWT or fake provider does not satisfy `L`. PR30 is unmerged, so every `I` requirement dependent on it remains pending, even when its isolated tests report green. Separate source completeness and exporter `solution_md` policy from structural clone test success.

## 11. Tooling, regression commands, environments

At repository root with backend requirements from `backend/requirements.lock` installed:

```sh
ruff check backend/app scripts/blueprint
mypy backend/app --ignore-missing-imports
PYTHONPATH=backend python -m pytest backend/tests/api/test_confirm_source.py backend/tests/api/test_ingest.py backend/tests/api/test_sessions.py backend/tests/api/test_ownership.py -q -p no:cacheprovider
PYTHONPATH=backend python -m pytest backend/tests/api/test_generation_preferences.py backend/tests/unit/test_mode_mapper.py -q -p no:cacheprovider
PYTHONPATH=backend python -m pytest backend/tests/api/test_finalize_shuffle.py backend/tests/api/test_review_api.py -q -p no:cacheprovider
```

Database suites (the opt-ins require **disposable** PostgreSQL and their documented Docker/DSN preparation; default without opt-in is SKIP):

```sh
RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p test_source_confirmation_revision.py -v
RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p test_source_supported_modes.py -v
RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -p test_source_no_ai_integration.py -v
RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -v
# TASK207 suite has its own isolation/DSN setup; see backend/tests/migrations/README.md
RUN_TASK207_REAL_DB_TESTS=1 PYTHONPATH=backend python -m pytest backend/tests/migrations/test_generation_w2.py backend/tests/migrations/test_generation_clone.py -q -p no:cacheprovider --tb=short
```

The two new W4 files in commands above are **planned**, not present at baseline. Before execution, choose the compatible harness, supply the required DSN for a random disposable DB, check `EXAM_TEST_DB_DESTRUCTIVE` if required, document actual container image/SQL engine, and ensure each suite ran rather than skipped. For front-end, check `frontend/package.json` scripts before using `npm test`; known repo commands include `npm run lint` and `npm run build`. CI definitions: `.github/workflows/ci.yml` and `.github/workflows/docker-ci.yml`. Always record SHA + test count + skipped count + fullchain SQL migration order.

## 12. Dependencies, blockers and owner-specific handoff

| ID | Category | Exact unresolved dependency | What can start now? | Owner / evidence gate |
|---|---|---|---|---|
| B0 | **Blocks start only for migration write** | Determine deployed ledger and whether PR52 017 will merge before new migration number is fixed | Code inspection, isolated tests, contract, legacy hook cleanup can start | Duy/OPS; read ledger and remote migration list |
| B1 | **Does not block W4-01 coding; blocks integration** | PR30 still draft; Quỳnh owns model/HTTP and worker whose client modes/defaults contradict #45 | SQL server derivation, prefs RPC, API independent tests | Quỳnh; owner commit, documented JSON and combined DB tests |
| B2 | **Does not block W4-01 coding; blocks integration** | PR42 FE1 and htbaax FE2 pending merged/API-bound behavior | Source/backend regression and SQL can start | Philip/htbaax; local Supabase and FE tests |
| B3 | **Does not block W4-01 coding; blocks integration** | PR49 unresolved integrity findings; shared `main.py`/finalize collisions | New prefs API and pure DB tests not touching preview | Tâm / reviewer; PR49 merge and permutation proof |
| B4 | **Does not block backend coding; blocks demo acceptance** | Q01 optional source solution vs #46 required full fallback/export. No product-approved remedy | Implement fail-closed validation and explicit blocked state, never fake solution | **Duy + Quỳnh + Tâm**; approved product policy and Golden dataset |
| B5 | **Does not block initial coding; blocks release acceptance** | No evidence in this planning action of deployed JWT/PostgREST/RLS and latest full migrations | Unit + PostgreSQL disposable tests | OPS + Duy, with exact deployed SHA |
| B6 | **Not W4-01 scope** | PR30 validator F02 timeout resource bound, worker SSE/lifecycle retry, PR52 review F01 | Track as integration risk; no shared module edit | Quỳnh/Đạt/PR52 reviewer |
| B7 | **Not W4-01 scope** | W4-03 read snapshot, Review Write/Revert correction, Stage3 FE, Export Storage | Handoff confirmed-source provenance and preference contract | W4-03/Review/htbaax/Hùng |

**Q01 interim guidance (not approval):** Maintain source-solution optional at ingestion/confirm (matches existing source schema and original product scope); require full verified solution for any use that *materializes a current fallback candidate* or approved export. When absent, persist truthful blocked state, no fallback with empty `solution_md`, no autoapproval, no export. Instructor must supply source data in an explicitly newly confirmed draft or wait for an approved source-solution workflow. Stronger “reject at confirm” policy would simplify fallback but **changes accepted product scope** and must receive Duy/Quỳnh/Tâm approval first.

**Potential source conflict:** `source_content_revision` changes on draft mutation, while immutable per-question `source_revision_id` in `source_artifact_revisions` is a distinct identifier. Never use one as a substitute for the other in an RPC. `source_fingerprint` is per question; `confirmed_source_hash` hashes the ordered batch. Confirmation receipt and job snapshot provenance must preserve all four identities without conflating them.

**W4-03 parallel boundary:** W4-MVP-01 does **not** write `review.py`, `review/repository.py`, `review/service.py`, Review Write RPC, current-candidate projection or Stage3 snapshot. It supplies `source_question_id`, `source_revision_id`, `confirmation_id`, `source_fingerprint`, authoritative `source_manifest` and `ordering_preferences` constraints as a **read contract**. On a shared `main.py` mount, coordinate a minimal, conflict-free change; it is not permission to take W4-03 files.

## 13. Definition of Done (coding and evidence checklist)

- [ ] `dev` HEAD/PR statuses refreshed; task worktree from fresh remote; migration number unused in Git **and** deployed ledger; no historical migration edited.
- [ ] 006/011–014 source confirmation retained; reliable source preview UUID and key replay; no stale successful commit; JWT/RLS/ACL regression.
- [ ] Ingest no longer schedules pre-confirm legacy Blueprint; canonical publication only from a confirmed receipt; `NO_CONFIRMATION` cannot save config.
- [ ] SQL derives stable allowed modes solely from canonical confirmed heads; malformed policy fails closed; ready `[]` yields no-provider Original Clone using 016.
- [ ] Public Stage2 API does not require/obey client `active_variation_modes`; strict N 1–4; both shuffle defaults OFF/OFF at DB/Python/FE; four combinations valid.
- [ ] Generation snapshot/manifest/hash bound across save/claim/retry; source frozen after confirmation; SQL/HTTP cannot bypass ownership.
- [ ] Stage3 preferences-only API/RPC updates both flags before shuffle, **no** candidate change, respects reviewed/locked status and existing finalized guard.
- [ ] Concurrent confirmation/config/shuffle tests use **real PostgreSQL independent connections** and prove serial outcomes/rollbacks.
- [ ] Fresh and upgrade migrations tested with non-skipped results; no duplicate functions/number collision with PR52.
- [ ] PR30/FE1/FE2/Review/Finalize regression suites pass on pinned integrated head; all CI checks valid for final review SHA.
- [ ] Q01 missing-solution policy explicitly approved or documented as **acceptance blocker**; fail-closed implemented, no fabricated solution.
- [ ] API/SQL changes documented in owner contract and `docs/change_log.md`; handoffs acknowledged; at least one independent GitHub Approve before merge.
- [ ] Supabase Local Auth/JWT/PostgREST/RLS integration evidence and, later, deployed G0/G1 evidence recorded with environment, SHA, migration ledger and test logs. No fixture-only assertion labeled “Integrated Done”.
- [ ] No W4-03 Review Snapshot, Review Write, generation worker/SSE, Stage3 FE, shuffle writer, export or deployment changes accidentally included in W4-01 patch.

## 14. Immediate next coding actions, prioritized

1. Pin and compare current `dev`, PR30 and PR52; reserve additive migration after existing 017 slot; reconcile actual Supabase migration ledger (do not block writing tests/docs while this check is pending).
2. Write **negative real-DB tests first** for `NO_CONFIRMATION`, injected modes, default OFF/OFF, stale manifest and direct-call bypass; these are demonstrable incorrect behavior in 015.
3. Remove the two ingest legacy blueprint scheduler calls and add regression assertions; preserve source confirmation behavior.
4. Implement the forward-only SQL hardening for `save_generation_config` and the separate reviewed-only preferences RPC, keeping `009` guards intact.
5. Give Quỳnh exact PR30 config model/adapter change specification and SQL fixtures, and htbaax strict UI contract, so parallel work proceeds without file collisions.
6. Run local actual PostgreSQL fullchain fresh/upgrade and race suites, then API unit/lint/typecheck. Record failures honestly.
7. Wire dedicated preferences route into **merged/rebased** `main.py` without overwriting PR30's routers, and request owner review.
8. Hand off Q01 blocked-source policy and W4-03 current-source identifiers, then run full local Supabase integration when owners' branches are available.

## 15. Remaining verification gaps and severity

- **HIGH (integration):** PR30 unmerged; code currently demands user mode selection and two defaults ON. A migration alone does not deliver the public contract.
- **HIGH (schema release):** SQL 010 is an empty placeholder, PR52 owns 017, actual remote deployment ledger unknown. Confirm order and rollback/replay before a fresh or upgraded DB is touched.
- **HIGH (acceptance):** Source `solution_md` optional vs fallback/export mandatory Q01 unresolved; do not guess a product decision or publish a fake solution.
- **MEDIUM (integration):** FE1 PR42/FE2 current Stage2 modes UI not yet adopted #45; local Supabase/PostgREST/RLS/Gemini E2E not verified by this planning action.
- **MEDIUM (concurrency):** Preference edit vs finalized shuffle must be verified with DB locks on real independent connections, not only mocks.
- **MEDIUM (other owner):** PR49 preview consistency blockers and PR30 validator resource-bound finding; track but don't rewrite.
- **LOW (existing bug):** PR43 F04 uppercase UUID GET 503, reviewer-described, not re-tested in this action.
- **No claim:** No test suite/CI actually executed during **creation of this plan**. No branch has been merged or production/staging deployment performed.

---

**Plan source links:** [W4 assignment](W4_ASSIGNMENT.md) · [W4 task detail](W4_TASK_DETAIL.md) · [ADR-0001](../adr/0001-confirm-before-blueprint.md) · [Source confirm API](../api/confirm-source-endpoint.md) · [Source artifacts API](../api/source-artifacts-contract.md) · [Generation config API](../api/generation-config-endpoint.md) · [Issue #45](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/45) · [Issue #46](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/46).

**Implementation safety rule:** At execution time re-read all named files/functions at the newest **integration** head; proposals and exact line numbers in this document reflect the pinned `f104fae...` baseline and are not evidence that future code has remained unchanged.
