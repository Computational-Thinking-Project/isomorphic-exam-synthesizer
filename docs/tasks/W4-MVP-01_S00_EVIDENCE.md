# W4-MVP-01 — S00 evidence and blocked handoff

Observed 2026-11-09, Asia/Saigon. Role: **AUTHOR**. Workflow: v0.1 **proposed**.
Historical first-run status: **S00 BLOCKED — applied migration ledger and migration allocation unverified**.
The user subsequently authorized independent local work despite the Production
ledger gap. Current results and the superseding step/dependency classification
are in [the local verification and drift report](W4-MVP-01_LOCAL_VERIFICATION.md).
The sections below preserve the first-run observations, not the current test status.

## Authority and inspected inputs

The user authorized implementation and required passing each step's gate before
continuing. The uploaded `W4-MVP-01_AGENT_EXECUTION_PLAN.md` was read completely;
its planning-session restrictions describe the earlier document-generation task.
The current user's no-merge, no-deploy, no-production-database-modification and
ownership restrictions remain in force.

Inspected repository instructions: `AGENTS.md`, `CONTRIBUTING.md`,
`agents/johannguyen015/AGENTS.md`, `docs/review/WORKFLOW.md`, and author templates
in `docs/review/TEMPLATES.md`. Workflow documents last changed at
`506384bb312058d8ad2bec759fed8957b19940b3` for the inspected paths.
Task inputs include the task-branch implementation plan, W4 assignment v2.1,
relevant W4 task detail, ADR-0001, migration test README, and live Issues #45/#46.
GitHub PR metadata, complete changed-file lists, reviews, review threads and
conversation timelines were refreshed for #30/#42/#49/#52. OPS PR #51 and its
migration inventory/candidate documents were inspected for missing ledger evidence.

## Git baseline

| Item | Verified value |
|---|---|
| Repository | `Computational-Thinking-Project/isomorphic-exam-synthesizer` |
| Initial checkout | Clean `work` branch at `f104fae6188310b386b9e359c8f72d49c5db43bf` |
| Refreshed `origin/dev` | `f104fae6188310b386b9e359c8f72d49c5db43bf` |
| Task branch / current HEAD | `feat/w4-mvp-01-source-readiness` / `65c536291b0ad23c39e3b7f0615098943117d6e3` |
| Target vs dev | 0 behind, 1 ahead; only `docs/tasks/W4-MVP-01_IMPLEMENTATION_PLAN.md` added |
| Implementation plan Git blob | `7bbe360949be569bec2a3031dbb08ca688c1ecf5` |

Fetched dev/task and PR head refs without merging or rebasing. Created a local
task branch from the fetched task ref; no original changes existed to overwrite.
Git fetch/ls-remote worked. `gh auth status` failed with an invalid configured
token; the GitHub connector supplied the required read access. No token value was
printed. No remote writes were made.

## PR dependencies and ownership

All four PRs remain open and unmerged. The CI Pipeline and Docker environment
workflow runs returned success for each listed head. These are remote workflow
conclusions, not locally reproduced tests or proof of non-skipped database tests.

| PR | Current full head SHA | Review / dependency | Changed-file overlap with W4-01 |
|---|---|---|---|
| [#30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30) | `b6b642225b45e2744fda8826ebc70c8db0a3850e` | Draft; CHANGES_REQUESTED; F02 resource-bound thread unresolved/outdated, no subsequent independent approval observed | Quỳnh owns config model/route/service/repository and worker; shared `backend/app/main.py` and `docs/change_log.md`; no competing config endpoint |
| [#42](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/42) | `7d72dca58118a9d2dd9c8fd343933c931494ce49` | Draft; no submitted reviews or inline threads returned | Philip owns Stage 1 confirmation files; preserve them |
| [#49](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/49) | `5b5006481bd9be8cda81580154e7340106b87016` | CHANGES_REQUESTED; four unresolved current threads; mergeable=false reported | Tâm owns `finalize.py`, shared `schemas.py`, finalize service/repository; avoid edits; shared changelog requires coordination |
| [#52](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52) | `598b959c69c0f1c6362daed50fd544cb09dd73f7` | CHANGES_REQUESTED; F01 claimed fixed, unresolved/outdated thread, independent re-verification not observed | Owns `backend/migrations/017_generation_lifecycle_recovery.sql`; do not reuse 017 or edit that PR |

Remote CI run IDs (CI Pipeline / Docker environment): #30
`42491362930` / `42491362916`; #42 `42370228553` / `42370228570`;
#49 `42353224697` / `42353224806`; #52 `42480267518` / `42480267458`.

FE2 Stage 2/3 forms and services remain Bội Anh's responsibility under the plan.
W4-01 owns source scheduler removal, a new forward migration after allocation,
new independent preferences modules/tests, scoped API/migration documentation,
and the minimal coordinated router mount. No owner files were modified.

## Migration findings: Git evidence only

Observed file order: `backend/scripts/schema.sql`, migrations 002–009, empty
010 placeholder, then 011–016. Migration 017 exists only on the inspected PR #52
head; it has not merged into the refreshed dev/task branches. No 018 file exists
in dev, task, or the four inspected PR migration file lists. This does **not**
prove 018 is unused in an applied ledger or other concurrent work.

OPS PR [#51](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/51)
at `092b0a99abe9df598f7d79e0ba3d657e6d1c8f6c` explicitly labels
`docs/w4-migration-inventory.md` as static Git inventory, not an approved order
or applied ledger. Its `docs/w4-migration-candidate.md` explicitly says the
deployment ledger has not been supplied. Its candidate 017 hash matches the
current PR #52 Git blob, but that establishes content identity only.

No DSN/database/Supabase/Postgres environment variable names were found in the
inspection, and root/backend/frontend `.env` files are absent. Managed-environment
status reports no configured secrets, runtime variables or outbound identities.
No database was connected to, modified, or tested; deployed function definitions,
roles, RLS, triggers, checksums and applied history remain **UNKNOWN**.

Relevant function identities verified in Git SQL, not a running database:

- 011: `get_session_source_preview(uuid) RETURNS jsonb`;
  `confirm_source_artifacts(uuid,uuid,uuid,uuid,jsonb) RETURNS jsonb`.
- 015: `get_generation_source_snapshot(uuid) RETURNS jsonb`;
  `save_generation_config(uuid,int,jsonb,jsonb,jsonb) RETURNS jsonb`;
  `claim_generation_job(uuid,boolean) RETURNS jsonb` (subsequently replaced by 016).
- 009: `finalize_persist_shuffle(uuid,jsonb) RETURNS jsonb`;
  `finalize_guard_direct_mutation() RETURNS trigger`.
- 016: `persist_generation_clone(uuid,uuid,jsonb) RETURNS jsonb`.

Static gaps reproduced by inspection: sessions.py still schedules legacy Blueprint
work at lines 508 and 578; schema.sql line 122 defaults to ON/ON; 015's config RPC
defaults to ON/ON, assigns client modes, and admits the `NO_CONFIRMATION` branch.
No claim of runtime reproduction is made.

## Verification and step status

| Evidence tier | Actual result |
|---|---|
| S00 Git checks | Fetch, ls-remote, branch comparison, migration inventory/signature inspection succeeded; `git diff --check` passed |
| A: Unit/API | NOT RUN — S01 gate not entered; no passed/failed/skipped totals claimed |
| B: PostgreSQL | NOT RUN — no connected or verified disposable target; fresh/upgrade, grants and race gates unexecuted |
| C: Integrated owners/CI | Remote PR workflow conclusions recorded above; no combined SHA or integrated execution; no owner sign-offs inferred |
| D: Supabase JWT/PostgREST/RLS | NOT RUN — local Auth/PostgREST runtime and two test identities not provisioned/verified |
| Implementation / automated tests / API or migration changes | NONE — S01–S09 not started |
| Commit / push / PR creation / merge / deployment | NONE / NO / NO / NO / NO |

Only this S00 evidence report was added. Historical migrations and production
code remain unchanged. The evidence report is uncommitted.

## Blocker and decision needed

**B-S00-LEDGER:** Duy/OPS must provide a sanitized, read-only applied ledger
and approved ordered manifest identifying the environment, migration IDs/names
and checksums, whether 017 is applied, and whether 018 is unused. Reconcile this
with the refreshed refs before choosing a forward migration number. A Git hash
inventory or successful CI cannot satisfy this gate. No production credentials
are requested and no production connection has been attempted.

The uploaded plan's S00 acceptance requires a verified migration slot and
sanitized migration evidence. Its final first-step instruction states:
"No migration implementation may begin until S00's SQL-number/ledger gate is
satisfied." The user's stricter instruction requires each gate to pass before
continuing, so this run stops at S00 rather than entering S01 independently.

Further unresolved owner/product decisions remain as listed in the uploaded
plan: source missing-solution policy (Q01), worker alias mapping (Q02), Stage 3
route/error contract (Q04), empty canonical transformation policy (Q05), legacy
stored-job compatibility (Q06), external reviews and integrated test evidence.
They were not silently resolved in this run.

**First remaining step:** finish S00 ledger/allocation reconciliation; then S01
confirmation regression tests on the pinned task branch and a verified
disposable PostgreSQL target. Do not infer S00 PASS from this report.

## Static SHA-256 inventory

Computed from exact Git blobs at the task HEAD, except the explicitly labeled
PR #52 candidate. These are not applied-ledger checksums or execution evidence.

| Git path | SHA-256 |
|---|---|
| `backend/scripts/schema.sql` | `0710b6a7638101ec9571699e2d0208761461ee7eaf3e72858c173387fe468e35` |
| `backend/migrations/002_replace_source_questions_rpc.sql` | `8dae5f4d5b5cd05d098faa5cfa8b13ff34e40d31b60de2f545b6407eabf6d0d0` |
| `backend/migrations/003_confirm_exam_source_rpc.sql` | `9d410a002820d8b5b49bca02f0e9882fa3182f553a295a57a8d1f003dbb34093` |
| `backend/migrations/004_save_generation_config_rpc.sql` | `c66a1416b875ee407f0663301d841120cf9b5b5c16480ea07aea4435583aba25` |
| `backend/migrations/005_generation_job_operations_rpc.sql` | `55d3d51d1608ad4ec6c57d542428af728d6cdec28373846d0752018da4f1ea65` |
| `backend/migrations/006_stage3_review_and_shuffle.sql` | `c6a50d885f0382c791db2ad7dcd1450c4f766e58d2884dbae615a8028daa27c5` |
| `backend/migrations/007_finalize_approve_session_rpc.sql` | `bd2ccc61b9ce14e1661c50c5671fc2e4da2baf4a681b52a4c5d13cf60acca78e` |
| `backend/migrations/008_finalize_persist_shuffle_rpc.sql` | `f32935cbf48a27d2c8c988ba8dfc1accefdb48300b9e273c094710b63d18d63f` |
| `backend/migrations/009_finalize_security_boundary.sql` | `b4516597de80f8678381968678b46748ff92a4d7c7b4ad581fc3378cb6ac4bef` |
| `backend/migrations/010_source_artifact_supported_modes.sql` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `backend/migrations/011_source_confirmation_revision.sql` | `e450637bac39ff47c3677de497d84bc42aba948dac656f6c4009f67135a8f0cf` |
| `backend/migrations/012_source_artifact_supported_modes.sql` | `dd58de9603cf36fefd794dcbd5904c52c9216d10014fdd13edc63691218ef54d` |
| `backend/migrations/013_source_freeze_guard.sql` | `1a04b5ff975a68605cd8eed9b1fc579a33f1b3f5897b738863a41989413e39ff` |
| `backend/migrations/014_disable_legacy_source_confirmation.sql` | `9f408a274739b82ae94803aff1bee594ab4a0111273bdfb08410366ea59a4113` |
| `backend/migrations/015_stage2_canonical_w2_integration.sql` | `63b18dc6b541ec48c55ee3e4d5371cb8f84bc96c429b85f052feeb260521dc1b` |
| `backend/migrations/016_stage2_original_clone.sql` | `539f929112eb1803fb0f4d1e5464155a07808e6640ecd6ce2bf42dca1a823427` |
| `backend/migrations/017_generation_lifecycle_recovery.sql` (PR #52 only) | `d84880d30ff372b22ecdbc0e94efd11135869209c3695235467e7e1cf0d7ca4b` |
