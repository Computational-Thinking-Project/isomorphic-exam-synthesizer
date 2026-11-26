# EXT-01 / 06 — Frozen mode, slot policy và guard

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Chờ G2/Q04 trước khóa implementation; có thể chuẩn bị fixture/đọc code ngay.
- **File / đầu vào:** Frozen job/config/policy thuộc EXT-02; Review RPC/service và targeted adapter; DTO snapshot/capability sau xác nhận owner.
- **Thứ tự làm:** Nhận frozen mode schema và legacy discriminator; chốt policy 1.0/1.1; đặt guards sau replay nhưng trước reserve; nối dimensions/capability UI; phối hợp dependency migration với gói 02.
- **Đầu ra / điều kiện hoàn thành gói:** Contract được Tâm xác nhận, fixture và guard tests; không tự nhận quyền sửa nhánh EXT-02 hoặc dùng default AI cho dữ liệu mới hỏng.
- **Kiểm chứng:** A02-16/22/26/27; A03 phối hợp EXT-02. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-4-1"></a>

### 3.4.1. Contract mode/policy cần Tâm xác nhận (G2)

- Khi có frozen job snapshot: Review resolve snapshot thuộc đúng session/current candidate; dùng mode đã khóa khi claim, không đọc live config làm nguồn quyết định duy nhất. Nếu config và snapshot không khớp, từ chối operation mới bằng lỗi conflict đã thống nhất, không gọi AI/giữ quota. Replay operation cũ cùng binding vẫn theo Q02.
- Legacy: chỉ fallback `ai_generation` khi evidence xác định snapshot thuộc schema trước EXT-02. Tâm cần giao marker/version hoặc quy tắc nhận diện legacy đủ kiểm được, cùng vị trí frozen `generation_mode`. Chưa có bằng chứng phân biệt legacy/new thì chưa bật feature mode. Snapshot mới thiếu/null/mã mode lạ phải fail closed. Không sửa snapshot lịch sử để hợp thức hóa mode.
- Với `mapping_version='1.1'`: derive `canonical_dimensions` từ frozen canonical blueprint của source, đối chiếu `question_policies[source_question_id]` trong job snapshot theo semantics `_generation_question_policy`/`_generation_is_clone` của 026. Policy thiếu/sai hoặc source binding sai phải conflict trước reserve. Với `1.0`/legacy artifact: dùng contract frozen cũ, không tự áp policy 1.1 lên job cũ; Tâm xác nhận ca tương thích và fixture.
- `values`/`context` là dimensions đưa vào `_prepare` và `_generate` của `GenerationService.regenerate_from_snapshots`; không truyền public aliases như `NUMERICAL`. Thêm tham số tùy chọn cho targeted path, cập nhật adapter/mocks; stage-2 default và fingerprint không đổi. Việc suy policy và teacher feedback phải đi qua validated reservation/frozen evidence, không tin body FE.
- Shuffle-only: chặn reject/revert mới trước reserve/AI. AI mode slot clone-only: đề xuất chặn reject mới, vẫn Accept/Revert theo guard hiện hữu; đây là thay đổi hành vi cần owner xác nhận, không suy permission chỉ từ origin. UI nhận mode/capability từ server theo DTO được chốt (hoặc adapter từ evidence đã công bố), không tự tái dựng policy từ label/variation rỗng. Chốt field chính xác và fixture trong `review-snapshot.md` trước nối FE; backend/DB vẫn enforce khi gọi trực tiếp.
- Bàn giao G2 gồm: nơi lưu frozen mode, legacy discriminator, mapping policy 1.0/1.1, DTO UI, error mapping, migration dependency và test fixture cho từng nhánh. Nếu chưa giao đủ, chỉ triển khai phần targeted reasons độc lập; chưa bật guard mới với quy tắc giả định.
