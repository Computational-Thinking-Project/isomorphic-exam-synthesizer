# EXT-02 — Reuse and shuffle: plan and handoff (M2)

- Assignment source: `Ke-hoach-phan-cong-EXT-v3.1-final.md` (EXT v3.1, 25/11/2026), sections 1, 3 (EXT-02), 4 and acceptance rows A03–A08, A11, A12, A20. Repository link TBD (the file is not in the repo yet).
- Owner: Tam (`@AI-WFox`). Reviewers: `@nhatquynh1107` (DB/ACL, EXT-04 boundary) and `@johannguyen015` (Review boundary), requested on this PR.
- Repo / branch: `isomorphic-exam-synthesizer`, `feat/ext-02-reuse-shuffle` → `dev`. Draft PR: this PR.
- Base checked: `dev@b292443` (after #109).
- Batch deadline: results report Tuesday evening 01/12/2026. ETA for this task: 30–40 h of direct work (confirmed by owner on 26/11), coding 27/11–01/12; integration time with EXT-04/EXT-01 is extra and depends on I-EXT-01 / I-EXT-02 dates.
- Status: **plan only (proposed)**. No product code in this PR yet. Statements about current code are static inspection of `dev@b292443`.

## 1. What this task must deliver

Behaviour (from EXT v3.1, EXT-02):

1. **Generation mode.** Stage 2 lets the teacher choose `ai_generation` (similar exams) or `shuffle_only` after source verification. `generation_mode` is stored in the request and saved config; old configs/jobs without the field mean `ai_generation`.
2. **Frozen at claim.** The job snapshot freezes mode, source/revision, number of versions and per-slot policy. Resume/retry use only the snapshot.
3. **Shuffle-only = zero AI.** Every slot is a verified copy of the source, even when the Blueprint allows AI. DB claim, worker, persistence and ledger guarantee no AI call and no quota reservation. Mode is never inferred from empty variation modes.
4. **Backend-verified review for shuffle-only.** Backend checks versions, slots, questions, keys, provenance and state before confirming the copies, moving to `reviewed` and allowing shuffle. AI mode still requires per-question Accept (including clone/fallback slots). The client never sets `approved`.
5. **1–20 questions** checked on the canonical revision before a job is claimed, for new import, clone and reuse; reject before job/quota/AI. Preview/Export also check old data.
6. **Shuffle preferences.** Stage 2 saves `shuffle_questions` / `shuffle_options`; in `reviewed`, before the permutation is persisted, Preview can confirm/change both. Both off keeps order; identical versions allowed with a UI warning. After persisting, flags are locked and shown; a lost response is recovered by reading saved data. Preview/matrix/export use post-shuffle data only.
7. **Reuse from Bank.** `POST /exam-bank/{bank_item_id}/reuse` with `source_type` (`original` / `version`), `source_version_id` (required for `version`), `generation_mode`, `Idempotency-Key`. Checks owner, version belongs to the bank item, source round approved. Returns session ID, real status and next step. Canonical source: original = immutable source of the first round (reuse Blueprint if content and mode match); approved version = post-shuffle projection (question order, options, key, solution) as a new source ID, old seed not applied. Same user/key/payload returns the same session; different payload returns 409. Failure before success rolls back.
8. **Compatibility.** `POST /sessions` and `POST /sessions/{id}/clone` keep payload, response and Dashboard semantics (including clone `new_title`); both create independent drafts and never inherit job token, quota, export history or locks.
9. **Metadata consumer check.** `exam_sessions.subject` / `grade` keep the current contract (`Toán`, `12` default); EXT-02 checks how Stage 2 consumes them and, if they affect AI, shows the effective values for confirmation. Operational parameters never fill null metadata.
10. **Bank entry points.** The reuse endpoint serves both Bank actions requested by the team: "Reuse (shuffle and export)" = `generation_mode='shuffle_only'`, skipping generation and going straight to the shuffle options; "Clone to generate similar" = `generation_mode='ai_generation'`. The Bank buttons themselves (including a Shuffle button next to Clone) are Hung's UI (EXT-04); EXT-02 provides the API and next-step contract.

Findings covered by this task: F-002, F-017 (A03), F-008 (A05, A06), F-009 (A04). F-018 (receipt read, Quynh/Hung) and F-019 (Review baseline, Duy) are not EXT-02 items but must be decided in M2.

Reuse-before-create rule (team agreement): every step below first reuses an existing route/RPC/migration helper (listed under "Already in dev"); anything new is checked for duplicates against open PRs (#111, #110) and announced in this PR's conversation before it is created.

Out of scope: Bank/Finalize/codes/receipts (EXT-04), Export/OMR (EXT-03), Review actions (EXT-01), web grading, merging export rounds.

Already in `dev@b292443` (checked by reading code):
- 1–20 source check at config save: `backend/app/services/generation/config_service.py` (`validate_generation_config`, line ~114).
- `n_versions` 1–4 and `ordering_preferences` in `backend/app/models/generation_config.py`.
- Preferences update in `reviewed`: `PATCH /sessions/{id}/ordering-preferences` → RPC `update_generation_ordering_preferences` (`backend/app/api/routes/sessions.py:299`).
- Per-question policy and clone detection: migration `026` (`_generation_question_policy`, `_generation_is_clone`, `_generation_claim_010` with `mapping_version='1.1'` and `snapshot_payload.question_policies`).
- Clone route `POST /sessions/{id}/clone` (`sessions.py:426`).
- No `generation_mode`, no `shuffle_only`, no Bank reuse endpoint yet.

## 2. Files and order of work (from Friday 27/11)

| Step / files | Change | Output | Needs first | How to check |
|---|---|---|---|---|
| 1. Migration `0NN_generation_mode.sql` (number agreed in Q05) | `generation_configs.generation_mode text NOT NULL DEFAULT 'ai_generation' CHECK (IN ('ai_generation','shuffle_only'))`; same frozen column on `generation_job_snapshots` (nullable for history, no backfill rewrite). New claims write `mapping_version='1.2'` + `generation_mode` + per-slot `question_policies` (all `ORIGINAL_CLONE` in shuffle-only). Helper `public._generation_job_mode(job)` returns `ai_generation` for `mapping_version IN ('1.0','1.1')`, the frozen value for `'1.2'`, and raises `ERR_CONFIG_CONFLICT` for null/unknown. `_generation_is_clone` extended for 1.2. Retry compares frozen mode with config. | Mode frozen at claim; legacy rule checkable | Q05 numbering | PG tests: legacy 1.0/1.1 jobs → `ai_generation`; 1.2 null/unknown → conflict; retry with changed mode → conflict |
| 2. Claim / worker / persistence (`job_repository.py`, `service.py`, `ai_batch_adapter.py`, clone path in 016/024/026) | Shuffle-only: every slot goes through `persist_generation_clone`; no AI reservation, no `gemini_call_count` change; DB rejects AI results for shuffle-only jobs | Zero AI / zero quota guaranteed in DB, not only in Python | Step 1 | A03: AI-capable Blueprint in shuffle-only → 0 AI calls, quota unchanged, also after interrupted resume |
| 3. Backend review for shuffle-only (new RPC `confirm_shuffle_only_copies`, Review/progress readers) | Verify versions/slots/keys/provenance, then move to `reviewed`; AI mode unchanged | Server-side `reviewed` without client `approved` | I-EXT-01 (readiness contract) | A03 + Review regression |
| 4. API + models (`generation_config.py`, `routes/generation_config.py`, `config_service.py`) | `generation_mode` in request/response (default `ai_generation`), 1–20 check also on clone/reuse before claim | Stage 2 contract | Step 1 | API tests, 0/21 rejected before claim |
| 5. Stage 2 UI (`Stage2ConfigPage.jsx`) | Mode choice after verification, effective values shown, warning for identical versions when both shuffle flags are off | Teacher can pick mode | Step 4 | Component tests + native check |
| 6. Shuffle preferences / lock (existing RPC + Preview hook) | Keep current RPC; return locked flags after persist; recovery read on lost response | Preferences contract for Preview (Hung) | I-EXT-02 for post-shuffle naming | A04 (4 combinations, reload before/after persist) |
| 7. Reuse endpoint (`routes/` new `exam_bank_reuse.py`, RPC `reuse_bank_item`) | Owner/version checks, canonical source creation (original vs approved version projection), idempotency table or reuse of existing receipt pattern, rollback on failure | Reuse returns session ID + next step | I-EXT-02 (bank item / version ID shape from Quynh) | A05, A06, A07 |
| 8. Create/clone compatibility | No contract change; add 1–20 and mode default | Old callers unaffected | — | A06 |

## 3. Inputs and questions — answered on this Draft PR

| ID | Provider → receiver | Needed for | Need-by / ETA | Status |
|---|---|---|---|---|
| I-EXT-01 | Duy → Tam | Readiness and accept/revert contract (step 3) | Contract 26/11 per #111; ETA TBD | Requested; reading #111 plan v1.2 |
| I-EXT-02 | Quynh → Tam | Bank item / version IDs, source/target rules, metadata null, receipts (step 7) | Before step 7; ETA TBD | Requested |
| I-EXT-03 | **Tam → Quynh, Dat** | Canonical source rules, reopen state, post-shuffle projection with keys/solutions | Decision 26–27/11 | Contract proposed in §4 below; fixture v1 accepted for planning by EXT-04 at 88eb197; v2 (26/11) adds version/source identity, new source, reopen cases and a label-changing solution: `docs/tasks/fixtures/I-EXT-03.json` |
| Q04 (#111) | Duy ↔ Tam | Mode guard in Review | 26/11 | Answered on #111 (see link in PR conversation) |

Integration order from EXT v3.1: EXT-01/02 → EXT-04 → EXT-03. Schedule risk: steps 1–3 and 7 are the critical path; step 7 depends on I-EXT-02. Overlap risk: Draft PR #110 (Dat) also changes `backend/app/services/generation/service.py` and `test_per_question_policy.py`; step 2 will rebase on it or agree the split with Dat before editing the same functions. If I-EXT-02 is late, steps 1–6 are delivered and accepted independently and step 7 is reported as pending.

## 4. I-EXT-03 contract (proposed)

- **Frozen mode:** `generation_job_snapshots.generation_mode` and `snapshot_payload.generation_mode`, `mapping_version='1.2'`. Legacy = `mapping_version IN ('1.0','1.1')` → `ai_generation`. Read through `public._generation_job_mode(job)` only; never through live `generation_configs`.
- **Per-slot policy:** `snapshot_payload.question_policies[source_question_id] = {canonical_dimensions, result_kind}`; shuffle-only → every slot `ORIGINAL_CLONE`, `canonical_dimensions=[]`.
- **Reopen state:** reuse creates a new draft session at the first step whose evidence is missing (confirm source / analysis / Stage 2); never reopens the source session.
- **Post-shuffle projection:** read from persisted permutation (question order, option order, display key, solution) per `version_id`; the canonical key is unchanged. Fixture: `docs/tasks/fixtures/I-EXT-03.json` (synthetic, for contract agreement only): one AI slot, one clone slot with missing solution, one shuffled version in both modes, and reuse request/response examples (idempotent retry, 409, 21-question rejection).
- **Python reader:** `mode_mapper.job_generation_mode` and `mode_mapper.slot_result_kind` mirror 028 (parity-tested); consumers import them instead of re-implementing the rules.

## 5. Self-check plan

- Real PostgreSQL in Docker (`.\scripts\dev.ps1 test`) for claim/retry/mode/quota/rollback; backend `pytest backend/tests`, `ruff`, `mypy`; frontend `npm test`, `npm run lint`, `npm run build`.
- A03, A04, A05, A06 led by Tam; A07, A08, A11, A12, A20 jointly with Quynh/Hung.
- Not verifiable here: live Gemini (shuffle-only must need none), OMR (EXT-03).

## 6. Handoff — to fill with real results

Phase 1 (26/11, author self-check, not reviewed or accepted). Base `dev@b292443`.

- **Done (code):** migration `backend/migrations/028_generation_mode.sql`; `generation_mode` in `GenerationConfigRequest` / saved config / claim receipt; job repository reads the mode from the frozen snapshot (`frozen_generation_mode`, `mode_question_policy`); Stage 2 mode choice "Sinh đề tương tự" / "Chỉ xáo trộn"; [DEC-EXT02-001](../change_log.md) (proposed).
- **Checked (local, Windows, PostgreSQL 15 in Docker, no live Gemini/Supabase):**
  - `backend/tests/migrations/test_generation_mode_pg.py` (real PostgreSQL): legacy 1.0/1.1 → `ai_generation` without rewriting history; 1.2 null/unknown/inconsistent → `ERR_CONFIG_CONFLICT`; shuffle-only with an AI-capable Blueprint → every slot `ORIGINAL_CLONE`, `reserve_generation_quota` and AI results rejected, quota 0, also after an interrupted retry; changed mode on retry → conflict; 1 and 20 questions accepted, 0 and 21 rejected before claim (no job, no quota); old payload without the mode works; single `save_generation_config` signature with unchanged grants; replay of 028 is idempotent; preferences locked once versions are finalized; the real job runner on shuffle-only makes 0 AI calls and 0 reservations and the result goes through review accept, shuffle and export.
  - Python unit/API tests for the model, config repository, frozen-mode reader and route; Stage 2 card and service tests.
- **Shuffle flags (D):** no new fields. `ordering_preferences.shuffle_questions` / `shuffle_options` (019) are the EXT v3.1 flags; `PATCH /sessions/{id}/ordering-preferences` already allows changes only in `reviewed` and is locked once `finalize_persist_shuffle` marks versions finalized; "both off keeps order" is covered by the existing shuffler tests.
- **Design notes:**
  - Claim also counts 1-20 source questions on the legacy pre-confirmation path; before 028 that path accepted 0 sources.
  - The identical-versions warning is shown only in shuffle-only mode with N > 1 and both flags off; in AI mode the versions differ anyway.
  - Stage 2 has no shuffle checkboxes (Issue #94); the flags are still edited at Preview before the permutation is persisted.
  - Migration number `028` is tentative until Q05 on #111; the EXT-01 Review guard must come after it.
- **Not done in phase 1:** backend confirmation of shuffle-only copies to `reviewed` (step 3, needs I-EXT-01); Bank reuse endpoint (step 7, needs I-EXT-02). Until step 3 lands, Review still shows per-question Accept for shuffle-only sessions, and reject/regenerate on a clone slot is guarded only by the EXT-01 Q04 work.
- I-EXT-03 v2 delivered on 26/11 after EXT-04 feedback; Integrated: not yet (needs the real DB projection after step 7).
- **Accepted:** none yet.
- **Pending:** Q05 numbering, I-EXT-01, I-EXT-02, feedback from Quynh and Dat on the I-EXT-03 fixture, reviewer check of this head.
