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

Để áp dụng an toàn mà không chạy lại toàn bộ `schema.sql` (vốn chứa DDL không idempotent và policies trùng lặp), migration reconciliation `003b_reconcile_baseline.sql` được thiết lập và kiểm thử rehearsal thành công trong container PostgreSQL 15 cô lập.

### Candidate Manifest được kiểm thử Rehearsal (003b + 004–022)

| Thứ tự | File / Migration | SHA256 Git blob | Vai trò / Mục đích | Trạng thái Rehearsal |
|---|---|---|---|---|
| 01 | `003b_reconcile_baseline.sql` | `39dfcc48ceef71e69c6f2b4c149db4bf3c8163cc21def6a8a507be2751caec31` | Tạo 5 bảng baseline thiếu & RLS/grants an toàn | PASS |
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

## Điều kiện trước khi áp trên DB ứng dụng

Duy/Hùng bàn giao approved ordered manifest (bao gồm prerequisites/bootstrap và đường fresh/upgrade từ ledger thực), backend-compatible SHA, backup owner + restore rehearsal/forward-fix và quyền chạy. Proposed sequence017→018→019 không thay quyết định deployment của DB owner; PR head có thể thay đổi nên phải đối chiếu hash lại sau merge.

Operator ghi actual applied version/checksum/time/operator/DB alias và kết quả kiểm; chưa có receipt này thì DB-applied vẫn UNVERIFIED. Không chạy destructive tests trên Supabase nhóm/production. Không tải/chạy SQL tự động từ file inventory này. Authority/ENV0 tại [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53); input đủ dùng theo [DB0](tasks/TASK-W4-OPS.md#input-handoff).
