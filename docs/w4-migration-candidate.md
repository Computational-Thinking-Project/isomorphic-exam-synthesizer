# W4 migration checkpoint — Git inventory, không phải applied ledger

Đạt cập nhật 11/11/2026 trên base `dev@294c69a1a085ac6487d65b633e06a2f1112e2046`. [Historical inventory73583d7](w4-migration-inventory.md) giữ nguyên; không dùng bản lịch sử để suy DB hiện đã áp migration nào. SHA256 dưới đây tính từ **Git blob bytes**, không từ working-copy CRLF.

| Migration / nguồn ghim | SHA256 Git blob | Trạng thái đủ dùng cho OPS |
|---|---|---|
| `017_generation_lifecycle_recovery.sql` — dev294c69a, PR52 đã merge | `76544a154a9230529cbb385958784e32dcfb93bcc17f358622f5b82ef721fdff` | Merged/reviewer verified; DB-applied và live recovery UNVERIFIED |
| `018_review_current_snapshot.sql` — PR54@7c7200f4cc5b02a355a60993a19b1fc865f81579 | `4e36271d5254343c228132f22e765dfe76b09a518e06a8f898d36701ea14012d` | Open/Approve của Đạt và FE2; chưa thuộc base dev này, DB-applied UNVERIFIED |
| `019_w4_source_readiness_config.sql` — PR61@b32789917b7d1a6f19a52f4718c25dca7224559c | `5ca0464ddaac534caa0f85c615cc31dee187bee32e5ee7a19609b976dd2ce6ba` | Open/Request changes HTTP F01–F02; chưa thuộc base, không deploy như approved candidate |

## Bằng chứng đã kiểm và giới hạn

- PR52@3d05949: [Đạt Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52#pullrequestreview-5852213066) sau 23pass/0skip trên PostgreSQL17 cô lập. Suite dùng bootstrap/migration selections của fixture, không phải xác nhận toàn migration chain production.
- PR54@7c7200f: [Đạt Approve](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/54#pullrequestreview-5857922227), 23pass/0skip trên PostgreSQL15-alpine network-none; có full selected chain, replay018 và populated016→017→018.
- PR61@b327899: [Đạt review](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/61#pullrequestreview-5857931153), PostgreSQL baseline6pass, readiness24pass/1optional-skip, config guards64pass; API136pass. Baseline/readiness019 tests không áp018, không gọi đây là shared ledger hay full application E2E.
- File010 empty và012 có nội dung là lịch sử cần giữ. Không tự skip/rename hoặc áp SQL dựa riêng vào basename.

- Reviewer-only combined probe: ghép SQL018@7c7200f rồi019@b327899 trong DB PostgreSQL15 network-none; **4/4 pass** (complete matrix, regenerating state, validation priority, replay018). Không sửa source PR; chưa phải full019-after018 regression, worker/FE E2E hoặc approved deployment manifest. Evidence local ignored `.artifacts/review-w4-20261111/combined-pg.txt`.

## Điều kiện trước khi áp trên DB ứng dụng

Duy/Hùng bàn giao approved ordered manifest (bao gồm prerequisites/bootstrap và đường fresh/upgrade từ ledger thực), backend-compatible SHA, backup owner + restore rehearsal/forward-fix và quyền chạy. Proposed sequence017→018→019 không thay quyết định deployment của DB owner; PR head có thể thay đổi nên phải đối chiếu hash lại sau merge.

Operator ghi actual applied version/checksum/time/operator/DB alias và kết quả kiểm; chưa có receipt này thì DB-applied vẫn UNVERIFIED. Không chạy destructive tests trên Supabase nhóm/production. Không tải/chạy SQL tự động từ file inventory này. Authority/ENV0 tại [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53); input đủ dùng theo [DB0](tasks/TASK-W4-OPS.md#input-handoff).
