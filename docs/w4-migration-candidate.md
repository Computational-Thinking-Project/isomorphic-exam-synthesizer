# W4 migration checkpoint — Git inventory, không phải applied ledger

Đạt cập nhật 13/11/2026, đồng bộ `dev@b47e4fa`; runtime local đã build vẫn ghim294c69a. [Historical inventory73583d7](w4-migration-inventory.md) giữ nguyên; không dùng bản lịch sử để suy DB hiện đã áp migration nào. SHA256 dưới đây tính từ **Git blob bytes**, không từ working-copy CRLF.

| Migration / nguồn ghim | SHA256 Git blob | Trạng thái đủ dùng cho OPS |
|---|---|---|
| `017_generation_lifecycle_recovery.sql` — dev294c69a, PR52 đã merge | `76544a154a9230529cbb385958784e32dcfb93bcc17f358622f5b82ef721fdff` | Merged/reviewer verified; DB-applied và live recovery UNVERIFIED |
| `018_review_current_snapshot.sql` — PR54@7c7200f4cc5b02a355a60993a19b1fc865f81579 | `4e36271d5254343c228132f22e765dfe76b09a518e06a8f898d36701ea14012d` | Merged vào dev tại21887c1; Git blob/checksum giữ nguyên, DB-applied UNVERIFIED |
| `019_w4_source_readiness_config.sql` — PR61@9fda6fd568a992ca64172cbcb1047c0ac41f6f31 | `5ca0464ddaac534caa0f85c615cc31dee187bee32e5ee7a19609b976dd2ce6ba` | Merged/Đạt Approve, F01/F02 verified; devb47e4fa, DB-applied UNVERIFIED, chưa phải approved deployment manifest |

## Bằng chứng đã kiểm và giới hạn

- PR52@3d05949: [Đạt Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52#pullrequestreview-5852213066) sau 23pass/0skip trên PostgreSQL17 cô lập. Suite dùng bootstrap/migration selections của fixture, không phải xác nhận toàn migration chain production.
- PR54@7c7200f: [Đạt Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/54#pullrequestreview-5857922227), 23pass/0skip trên PostgreSQL15-alpine network-none; có full selected chain, replay018 và populated016→017→018.
- Historical review PR61@b327899: [Đạt review](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#pullrequestreview-5857931153), PostgreSQL baseline6pass, readiness24pass/1optional-skip, config guards64pass; API136pass. Baseline/readiness019 tests không áp018, không gọi đây là shared ledger hay full application E2E.
- File010 empty và012 có nội dung là lịch sử cần giữ. Không tự skip/rename hoặc áp SQL dựa riêng vào basename.

- Reviewer-only combined probe: ghép SQL018@7c7200f rồi019@b327899 trong DB PostgreSQL15 network-none; **4/4 pass** (complete matrix, regenerating state, validation priority, replay018). Không sửa source PR; chưa phải full019-after018 regression, worker/FE E2E hoặc approved deployment manifest. Evidence local ignored `.artifacts/review-w4-20261111/combined-pg.txt`.

- Re-review PR61@9fda6fd: [Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#pullrequestreview-5884187896), 345pass/1optional worker-skip; baseline002–018→019/replay6pass, readiness24pass/1skip, SQL guards66pass, API249pass. Không tính focused tests hai lần; không chứng nhận worker/PostgREST live.
- PR63@8bb2931 đề xuất020 private export ledger; [OPS review](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#pullrequestreview-5884323942): SQL17pass, private unit29pass/1skip; Q09 adapter findings còn mở. 020 chưa thuộc dev/applied manifest.

## Checkpoint Issue #75 — Schema drift reconciliation và audit rehearsal (15/11/2026)

Đối chiếu thực tế tại Issue #75 cho thấy môi trường DB Supabase hiện hữu chỉ mới áp dụng đến `003_confirm_exam_source_rpc.sql` trên 5 bảng cơ sở (`users`, `exam_sessions`, `source_questions`, `question_blueprints`, `exam_versions`), thiếu các bảng baseline (`generation_configs`, `version_questions`, `answer_keys`, `review_logs`, `security_events`) và toàn bộ chuỗi migrations `004`–`022`.

Để áp dụng an toàn mà không chạy lại toàn bộ `schema.sql` (vốn chứa DDL không idempotent và policies trùng lặp), migration reconciliation `003b_reconcile_baseline.sql` được cập nhật tối giản, an toàn và kiểm thử rehearsal thành công trong container PostgreSQL 15 cô lập.

### Cập nhật và kiểm thử `003b_reconcile_baseline.sql` (Commit `f93cc9b57d0c912bbc15b839f075a8833dc55dfe`)

- **Khắc phục Privilege Regression:** Loại bỏ toàn bộ `GRANT INSERT, UPDATE, DELETE` cấp cho role `authenticated` trên các bảng được bảo vệ (`generation_configs`, `version_questions`, `answer_keys`, `review_logs`, `security_events`). Chỉ cấp quyền `SELECT` tối thiểu cho `authenticated`. Quyền ghi của role `authenticated` bị thu hồi hoàn toàn nhằm ngăn chặn việc hoàn tác (undo) các biện pháp bảo vệ ở migration `009` và `015` khi chạy hoặc replay `003b`.
- **Chính sách Owner-Read RLS trên `generation_configs`:** Bổ sung policy `generation_configs_owner_read` cho phép `authenticated` đọc cấu hình thuộc session của chính mình (`EXISTS (SELECT 1 FROM exam_sessions s WHERE s.id = generation_configs.session_id AND s.user_id = auth.uid())`). Giải quyết triệt để lỗi 0-row khi truy vấn trực tiếp từ `GET /api/sessions/{sessionId}`.
- **Bảo vệ bảng `security_events`:** Kích hoạt RLS, tạo policy cho phép user xem audit log của chính mình (`user_id = auth.uid()`), chỉ cho phép `service_role` thực hiện `INSERT`. Cấm hoàn toàn untrusted `INSERT`, `UPDATE`, `DELETE` từ phía client.
- **Targeted Compatibility Checks:** Thêm kiểm tra catalog tương thích cho enum `question_status`, `review_action_type`, điều kiện tiên quyết 5 bảng cơ sở, và kiểm tra loại bảng/cột thiết yếu nếu các bảng đã tồn tại trước đó. Thất bại có tính nguyên tử (fail closed) khi phát hiện xung đột.
- **Replay Safety:** Replay `003b` sau khi áp dụng toàn bộ chuỗi `004`–`022` thành công 100%, bảo lưu nguyên vẹn trạng thái quyền ghi bị thu hồi, không sinh ra policy thừa và không làm biến đổi bất kỳ bản ghi dữ liệu nào.

### Candidate Manifest được kiểm thử Rehearsal (003b + 004–022)

SQL source commit cho `003b`: `f93cc9b57d0c912bbc15b839f075a8833dc55dfe`

| Thứ tự | File / Migration | SHA256 Git blob | Vai trò / Mục đích | Trạng thái Rehearsal |
|---|---|---|---|---|
| 01 | `003b_reconcile_baseline.sql` | `b8d9497ee4683708be121738e9103bf87039272382d6f882b27f52ace8932b44` | Tạo 5 bảng baseline thiếu, RLS owner-read & least privilege | PASS |
| 02 | `004_save_generation_config_rpc.sql` | `c66a1416b875ee407f0663301d841120cf9b5b5c16480ea07aea4435583aba25` | `save_generation_config` RPC & triggers | PASS |
| 03 | `005_generation_job_operations_rpc.sql` | `55d3d51d1608ad4ec6c57d542428af728d6cdec28373846d0752018da4f1ea65` | `generation_jobs` table & worker RPCs | PASS |
| 04 | `006_stage3_review_and_shuffle.sql` | `c6a50d885f0382c791db2ad7dcd1450c4f766e58d2884dbae615a8028daa27c5` | Review ledger, `_review_lock_session`, artifact tables | PASS |
| 05 | `007_finalize_approve_session_rpc.sql` | `bd2ccc61b9ce14e1661c50c5671fc2e4da2baf4a681b52a4c5d13cf60acca78e` | `finalize_approve_session` RPC | PASS |
| 06 | `008_finalize_persist_shuffle_rpc.sql` | `f32935cbf48a27d2c8c988ba8dfc1accefdb48300b9e273c094710b63d18d63f` | `finalize_persist_shuffle` RPC | PASS |
| 07 | `009_finalize_security_boundary.sql` | `b4516597de80f8678381968678b46748ff92a4d7c7b4ad581fc3378cb6ac4bef` | Finalize mutation guards | PASS |
| -- | `010_source_artifact_supported_modes.sql` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0-byte file lịch sử; bỏ qua khi execute | OMIT |
| 08 | `011_source_confirmation_revision.sql` | `e450637bac39ff47c3677de497d84bc42aba948dac656f6c4009f67135a8f0cf` | `get_session_source_preview`, source revision (FIX 503) | PASS |
| 09 | `012_source_artifact_supported_modes.sql` | `dd58de9603cf36fefd794dcbd5904c52c9216d10014fdd13edc63691218ef54d` | `get_source_artifacts` với supported modes | PASS |
| 10 | `013_source_freeze_guard.sql` | `1a04b5ff975a68605cd8eed9b1fc579a33f1b3f5897b738863a41989413e39ff` | Trigger freeze confirmed sources | PASS |
| 11 | `014_disable_legacy_source_confirmation.sql` | `9f408a274739b82ae94803aff1bee594ab4a0111273bdfb08410366ea59a4113` | Revoke execute trên `confirm_exam_source` cũ | PASS |
| 12 | `015_stage2_canonical_w2_integration.sql` | `63b18dc6b541ec48c55ee3e4d5371cb8f84bc96c429b85f052feeb260521dc1b` | `get_generation_source_snapshot`, result tables | PASS |
| 13 | `016_stage2_original_clone.sql` | `539f929112eb1803fb0f4d1e5464155a07808e6640ecd6ce2bf42dca1a823427` | Original clone persistence | PASS |
| 14 | `017_generation_lifecycle_recovery.sql` | `76544a154a9230529cbb385958784e32dcfb93bcc17f358622f5b82ef721fdff` | `list_stale_generation_jobs` & recovery scanner | PASS |
| 15 | `018_review_current_snapshot.sql` | `4e36271d5254343c228132f22e765dfe76b09a518e06a8f898d36701ea14012d` | `get_review_current_snapshot` | PASS |
| 16 | `019_w4_source_readiness_config.sql` | `5ca0464ddaac534caa0f85c615cc31dee187bee32e5ee7a19609b976dd2ce6ba` | Ordering preferences & config guards | PASS |
| 17 | `021_w4_confirmed_source_fallback.sql` | `6730db5f18be9e18463f8ffcc08ede4ec6af7552810aa7412f8a924981665c67` | Confirmed-source fallback RPCs | PASS |
| 18 | `022_w4_generation_solution_guard.sql` | `ef9c8ce310ad1a7c60576df80d3ce08e5c41a8f643e747d3a2b2fef5cdab682e` | Solution guards on canonical claims | PASS |

*Ghi chú:* Migration `020` (PR #63) chưa được merge vào `dev`, nằm ngoài phạm vi manifest này.

### Bằng chứng Kiểm thử Thực tế trên PostgreSQL 15 Cô lập

Bộ test tự động chuyên biệt `backend/tests/migrations/test_issue75_baseline_reconciliation.py` đã thực thi trực tiếp trên container `postgres:15-alpine` (`--network none`, không mock catalog, không nạp `schema.sql` để che giấu khoảng trống):
- **T01 (Reconciliation cơ sở 5 bảng):** PASS. Tạo đúng 5 bảng thiếu, RLS enabled, enum chuẩn, quyền authenticated chỉ SELECT, bảo toàn 100% dữ liệu gốc.
- **T02 (Chuỗi candidate đầy đủ):** PASS. Áp dụng tuần tự `003b` rồi `004`–`022` (bỏ qua `010`). Tất cả 7 RPC trọng yếu tồn tại, cột `source_content_revision` được tạo kèm giá trị default, toàn bộ bản ghi gốc bảo toàn.
- **T03 (Replay an toàn sau `009`/`015`/`022`):** PASS. Replay `003b` không cấp lại quyền ghi cho `authenticated`, không thay đổi cấu trúc bảng, không làm mất bản ghi.
- **T04 (Từ chối enum không tương thích):** PASS. Phát hiện enum `question_status` thiếu label, rollback toàn bộ transaction.
- **T05 (Từ chối bảng không tương thích):** PASS. Phát hiện đối tượng xung đột (view thay vì table), rollback và giữ nguyên dữ liệu 5 bảng gốc.
- **T06 (Phân lập quyền đọc User A / B):** PASS. User A chỉ đọc được `generation_configs` của mình, không đọc được của User B.
- **T07 (Chặn quyền ghi trực tiếp sau hardening):** PASS. User A thử `INSERT`, `UPDATE`, `DELETE` trực tiếp trên `generation_configs` đều bị PostgreSQL từ chối (`42501`).
- **T08 (Phân lập và chống giả mạo `security_events`):** PASS. `service_role` ghi được audit log, `authenticated` đọc được log của mình nhưng bị từ chối `INSERT` giả mạo.
- **T12 (Hợp đồng `get_session_source_preview`):** PASS. Chủ sở hữu đọc được session kèm revision và danh sách câu hỏi; người dùng khác bị từ chối (`ARTIFACT_NOT_FOUND` / `P0002`).

Kết quả thực thi các bộ kiểm thử liên quan:
1. `test_issue75_baseline_reconciliation.py`: 9/9 tests PASS (30.7s)
2. `test_w4_baseline_chain.py`: 6/6 tests PASS (25.1s)
3. `test_stage3_schema.py`: 16/16 tests PASS (20.9s)
4. `test_source_confirmation_revision.py`: 16/16 tests PASS (54.3s)
5. `test_sessions.py` & `test_confirm_source.py`: 186/186 tests PASS (1.6s)
6. `ruff check` & `mypy`: 0 issues / type safe across 114 source files.

## Điều kiện trước khi áp trên DB ứng dụng

Rehearsal trên môi trường giả lập (synthetic 5-table fixture) đã hoàn tất và đạt 100% tiêu chí kỹ thuật. Tuy nhiên, **tính tương thích trên cơ sở dữ liệu thật vẫn là UNVERIFIED** cho đến khi:
1. DB owner (Duy / Hùng) đối chiếu DDL, RLS policies, trigger và ledger thực tế của Supabase mục tiêu.
2. Snapshot backup thực tế được tạo và kiểm tra khả năng phục hồi (restore verification) trên môi trường cô lập.
3. DB owner ký duyệt (GO decision) cho kế hoạch chạy manifest tuần tự này.

**Trạng thái hiện tại: Shared Supabase = NO-GO.** Không được phép thực thi DDL hoặc migration trực tiếp trên Supabase chia sẻ khi chưa có xác nhận từ Gate 1, 2 và 3.

## PR76 remediation checkpoint — 15/11/2026

This checkpoint supersedes earlier "100% technical readiness" claims for F01/F03.
Original suite at eec31148: independently rerun 9/9 PASS (31.885s), but it did not
execute Stage 2 save and T08 inserted as postgres. Those counts are historical.
The five-table fixture models repository schema, not verified production DDL.

F01 adds a real confirmation → canonical publication → snapshot → owner config
save/reload/resave regression on the partial upgrade. With the original enum,
it fails at save_generation_config with invalid enum value `configured`.
Fixture enum now follows schema.sql (including configured, excluding exporting).
F03 performs T08 inserts under SET LOCAL ROLE service_role and asserts current_user
in the insertion transaction, both after 003b and the complete chain. Since the
fixture service role has BYPASSRLS, this verifies its grants, not the INSERT policy
expression in isolation. SQL migration bytes and the 18-step manifest are unchanged.

F02 remains UNVERIFIED; use the read-only catalog handoff in the staging runbook.
Earlier PR audit comment claiming target catalog PASS is superseded by this status
and Issue75's later UNVERIFIED update. Do not treat table/function presence as an
applied ledger. Correct PR snapshot head is eec3114887c384b6be2a87abc88711e3ddded5b6;
the different eec3114-prefixed SHA in the old PR body is incorrect.

Code can be reviewed after focused/regression checks; live deployment stays NO-GO
pending catalog reconciliation, any reviewed delta, representative-copy rehearsal,
backup/restore proof and DB-owner GO. No shared Supabase changes were performed.

### Local author validation (15/11/2026, working tree based on eec31148)

- F01 RED: new T13 reached real canonical readiness, then failed with
  `invalid input value for enum session_status: "configured"` on the old fixture.
- Focused suite after F01/F03: **10/10 PASS**, 43.969s. Final T13 recheck after
  encoding/import cleanup: **1 PASS**, 10.727s. Network-none PostgreSQL15 containers.
- API session/confirm-source: **186 PASS**, 2.67s, mock environment; Windows Python
  3.14, pytest plugin autoload disabled, pytest_asyncio explicitly loaded. The
  default-plugin attempt was stopped without a result; it is not counted as PASS.
- Ruff (application, blueprint scripts and changed test), mypy (114 application
  files), and git diff --check: PASS.
- Runbook catalog SQL: executed successfully as a read-only transaction against
  local PostgreSQL's postgres database. This checks query syntax, not target
  Supabase metadata or visibility.
- No remote push, PR status change, GitHub approval or live deployment is claimed.
  F01/F03 are author-tested; independent reviewer verification is still pending.

- Migration regressions (baseline chain, source readiness/config, Stage3 schema,
  source confirmation): **63 run, 62 PASS / 1 optional worker SKIP**, 287.581s.
  Command: `RUN_POSTGRES_MIGRATION_TESTS=1`, `PYTHONPATH=backend`, Python unittest
  loading `test_w4_baseline_chain`, `test_w4_source_readiness_config`,
  `test_stage3_schema`, `test_source_confirmation_revision` from migration tests.
  The historical worker probe requires a separately pinned PR30 checkout; this
  skip is not worker/PostgREST/live acceptance evidence.

## Issue #75 ACL follow-up — proposed 19-step candidate

Refs #75. Base: dev@72507c84019021deb42f3668ab893edfdce248c0.
Production remains **NO-GO**. This patch is preparation, not deployment approval.
The preceding 18 SQL blobs/checksums remain unchanged. Append step 19:
`023_users_client_acl_hardening.sql` — SHA256 Git blob: **cac6973da49c9b5f5ca611b9eab2e794cb8c595b47bec812e88d2881b57c33a3**.
Before approval recompute from the final Git blob bytes and compare the bytes
actually submitted to PostgreSQL (do not hash a CRLF working copy).

Exact order: 003b → 004 → 005 → 006 → 007 → 008 → 009 → 011 → 012 →
013 → 014 → 015 → 016 → 017 → 018 → 019 → 021 → 022 → 023.
010 stays empty/omitted; 020 remains outside this candidate.
Only 023 is explicitly replayable; do not replay the entire chain.

023 removes client TRUNCATE/TRIGGER/REFERENCES and, on PostgreSQL >=17,
MAINTAIN. Effective table/column privilege postconditions fail atomically if
PUBLIC, column grants or inheritance retain forbidden access. Required
authenticated SELECT must already exist. No service_role, default ACL,
membership, Auth trigger or RLS policy is changed.

The Production observations are supplied evidence, not a fresh target audit.
Exact PostgreSQL version, current runtime SHA, complete ledger/catalog,
representative-copy rehearsal, backup/isolated restore and DB-owner GO remain
pending. Supabase branch main is not Git main. Do not promote Git branches
or infer the runtime SHA from this checkout.
