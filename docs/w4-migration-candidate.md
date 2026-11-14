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

## Điều kiện trước khi áp trên DB ứng dụng

Duy/Hùng bàn giao approved ordered manifest (bao gồm prerequisites/bootstrap và đường fresh/upgrade từ ledger thực), backend-compatible SHA, backup owner + restore rehearsal/forward-fix và quyền chạy. Proposed sequence017→018→019 không thay quyết định deployment của DB owner; PR head có thể thay đổi nên phải đối chiếu hash lại sau merge.

Operator ghi actual applied version/checksum/time/operator/DB alias và kết quả kiểm; chưa có receipt này thì DB-applied vẫn UNVERIFIED. Không chạy destructive tests trên Supabase nhóm/production. Không tải/chạy SQL tự động từ file inventory này. Authority/ENV0 tại [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53); input đủ dùng theo [DB0](tasks/TASK-W4-OPS.md#input-handoff).
