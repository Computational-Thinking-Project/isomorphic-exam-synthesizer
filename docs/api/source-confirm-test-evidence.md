# TASK-204 postreview P1/P2/P3 — 05/11/2026

Baseline ab9f09a, P1/P2 commit48d1d63; final P3 commit contains the exact code tested.
Only additive013 changes SQL; migrations002–012 retain their prior bytes.

- Red: source mutation after confirm and confirm-first writer were accepted;
  missing key returned200; ingest lock race returned500. Fixture SQL permissions
  and missing legacy RLS policies were corrected before interpreting ownership tests.
- Targeted green API: 11 PASS / 0 FAIL / 0 SKIP (87 deselected).
- Final backend regression ran once: 474 PASS / 0 FAIL / 0 SKIP. It combines the
  documented API/artifact/review set with tests/ai and tests/generation.
- Final PostgreSQL run once: 50 PASS / 0 FAIL / 0 SKIP (265.239s), using
  `python -m unittest discover -s backend/tests/migrations -p 'test_source_*.py' -q`.
  Fresh/upgrade chains include013; owner/service frozen writes preserve all state,
  foreign writes are denied by actual local RLS policy, draft edits/clone/cascade work,
  both race directions serialize, audit/replay remain atomic, fake extraction=1 / outbound=0.
- Final Ruff, mypy (90 source files), diff-check: PASS.
- No real AI requests, no push/deploy; FE2/BE2 unchanged.

Migration013 SHA256 (checkout bytes): `1a04b5ff975a68605cd8eed9b1fc579a33f1b3f5897b738863a41989413e39ff`.

Required header is a breaking FE1 change: missing422, malformed400; stable UUID
persistence across F5/timeout remains unverified. Integrated release verdict:
**NOT READY** until FE1 acceptance; existing FE2/BE2, migration010 reconciliation
and deployed JWT/RLS/PostgREST gates remain separate and unresolved.

The previous implementation results/checksums below are historical evidence for
ab9f09a, not a second regression run during this remediation.

---
# TASK-204 local test evidence — 05/11/2026

Branch `fix/be1-source-confirm-contract`, initial head `ab15447`, fetched base
`origin/dev=8289971`. Author implementation only; no GitHub approval or deployment.
Workflow v0.1 proposed, docs commit `506384b`.

| Ticket | Implementation / checkpoint | Evidence |
|---|---|---|
| A0 | 062fd0b — compile/fixture/debug cleanup | compile PASS; baseline stopped at 4 PASS / 1 replay FAIL, fixed in A3 |
| A1 | 589656a — UUID trigger, preview, confirm wrapper | PostgreSQL token/locking/rollback/ACL tests PASS |
| A2 | 16078d0 — UUID request/RPC, stable errors | compile PASS; verified by A3 |
| A3 | 009066c — API revision, replay, preview tests | 60 distinct API cases PASS before Q02 additions |
| B0 | e7cb9d6 — mapping profile 1.0 pinned to BE2 7e9377f | source/consumer contract verified; FE2 acceptance pending |
| B1 | 438a4f2 — canonical modes in one RPC | 43 API + 2 initial real-DB cases PASS |
| B2 | da4cb06 — modes/permissions/history tests | 15 new API + 5 new real-DB cases PASS |
| B3 | final test/runbook commit; 9a774a7 hardening | real no-AI HTTP/SQL integration, regression and teardown below |

## Executed results (distinct cases, not sums of reruns)

- Backend regression: **375 PASS**, 0 FAIL / SKIP, command in migration README.
- Additional fake AI/Blueprint/generation regression: **96 PASS**, 0 FAIL / SKIP.
- After requiring per-question production evidence: **75 PASS** in targeted
  confirm/artifact tests (includes 1 additional regression; overlaps the 375).
- Full CI-style Ruff `backend/app scripts/blueprint`: PASS.
- Mypy `backend/app --ignore-missing-imports`: PASS, 90 source files.
- New test module Ruff: PASS after import/format fixes. Diff whitespace: PASS.
- Compile checked during A0/A2/A3. Deprecation warnings are not failures.

| Real PostgreSQL module | Distinct passing cases | Scope |
|---|---:|---|
| test_source_confirmation_revision.py | 11 | UUID no reuse, source mutation paths, no-op, rollback, fresh/upgrade, locks, owner/tamper/ACL, audit rollback and same-key concurrency |
| test_source_supported_modes.py | 7 | states, validated NONE-only, canonical history/head, duplicate/partial counts, ACL, invalid mapping and publication/read lock |
| test_source_no_ai_integration.py | 1 | actual HTTP/producer + real SQL, stale/no receipt, postcommit response-loss/replay, fake retry to ready |
| test_source_artifacts.py | 28 | existing 006 SQL regressions; four current Python consumer cases explicitly adopt 011/012 |

**47 distinct real PostgreSQL cases PASS, 0 final FAIL / SKIP**, across targeted
runs, not a claimed single 47-case run. Earlier fixture failures (wrong inheritance,
missing preview principal, expected guard error) were fixed and rerun; no xfail or
skip was introduced. An initial discovery run accidentally collected imported
legacy review tests and was aborted; it is excluded from these pass counts.

Runtime: PostgreSQL **15.19**, Python3.11 backend image, network-none disposable
containers; all **82** package versions matched requirements.lock. Synthetic
canonical schema0.4.0 and public mapping1.0. The integration
asserts fake extraction exactly **1**, canonical row count **1**, silent audit **1**,
and external AI/network transport attempts **0**. Runtime key variables are empty;
Gemini gateway, HTTP transports and IP sockets are guarded. All test containers
were removed; one orphan from the aborted runner was explicitly inspected and removed.

Reproduction: [migration README](../../backend/tests/migrations/README.md#task-204-source-confirmation-q01q03).

## Remaining review and rollout gates

- FE1 UUID preview + stable-key retry adoption; FE2 canonical endpoint/object adapter
  and explicit ready gate. No FE files were changed or accepted on owners' behalf.
- BE2 public profile comes from an unmerged remote branch at7e9377f, not a locally
  deployed generation-config endpoint. Reconcile its migration010 with this branch's
  unchanged empty010 before integration. Do not infer generation-config E2E.
- Apply011/012 with updated API in a coordinated rollout; old timestamp RPC worker
  callers are revoked and current readers require the modes field.
- No deployed Supabase/PostgREST/JWT verification/table-read RLS proof. Local RPC
  ownership/ACL is real; SqlClient table reads use fixture superuser and JWT is injected.
- No independent GitHub Approve, merge or push was performed in this session.

## Migration/bootstrap checksums

SHA256 of checkout bytes used by this session. Python reads SQL as UTF-8 with
newline normalization. Raw hashes can differ after a CRLF/LF checkout conversion;
Git review content is the authority for comparison.

| File | SHA256 |
|---|---|
| backend/scripts/schema.sql | e43e7b343a0e964e954493d8c44b43c8d851ac76890a08c4768475e265f3dd6c |
| backend/tests/migrations/fixtures/legacy_schema.sql | 140137059ffb8ab40da54f8b31ef8df0d6daee2d97f18b207e0d7bbb9a6cdb0b |
| backend/migrations/002_replace_source_questions_rpc.sql | 6aff9e72d2bd14069a47727c2dfb906a633d4397940b37b6557b91cf30d9838b |
| backend/migrations/003_confirm_exam_source_rpc.sql | b969f45791dccd9c254826319bb111cb65b26ce89e9f909ed699d8fde2673d3f |
| backend/migrations/006_stage3_review_and_shuffle.sql | 48858fb7ee5ef14431c79c7bf2222a8d5e017187637eb35417a58acc11a0246a |
| backend/migrations/007_finalize_approve_session_rpc.sql | 921fb99490907632c01af06a13ab3a81ca62cbeb85b6b8caa4f2903672e40707 |
| backend/migrations/008_finalize_persist_shuffle_rpc.sql | 813d92a0aefc9d83fd132f32693604691fe33392253525dd1fcaba1c0b62b145 |
| backend/migrations/009_finalize_security_boundary.sql | 2fbe06ce3ba3e2cae937652a8f6844978caa76870f1317433ec9953e6e60c2e5 |
| backend/migrations/010_source_artifact_supported_modes.sql | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| backend/migrations/011_source_confirmation_revision.sql | e450637bac39ff47c3677de497d84bc42aba948dac656f6c4009f67135a8f0cf |
| backend/migrations/012_source_artifact_supported_modes.sql | 098c3ca0caf903883d03d82abcf2499609ca3414fe7a2d47c932db6ceb298800 |
