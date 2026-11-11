# W4-MVP-10 · M2 nền điều hướng

- Phụ trách: Trung Anh (`philip-kkk`, TV1/FE1). Reviewer đề xuất: Bội Anh cho frontend, Duy cho contract trạng thái. Chờ xác nhận reviewer.
- Nguồn phân công: [W4_ASSIGNMENT](W4_ASSIGNMENT.md) tại `d4350c0` và [W4_TASK_DETAIL](W4_TASK_DETAIL.md) mục W4-MVP-10.
- Workflow v0.1 proposed, bản tài liệu `7b7387f` có cập nhật INPUT-20261109. [Mẫu M2](../review/TEMPLATES.md#m2).
- Nhánh `feat/w4-mvp-10-route-foundation`. Base đã đồng bộ `294c69a`, head lúc lập plan `d4350c0`. [Draft PR #60](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/60).
- Mốc FE-H1 theo phân công: 10/11 18:00 UTC+7, đã qua. FE-H2 và kiểm live: 12/11 12:00 UTC+7. ETA cho các đầu vào Q11 còn thiếu: TBD.

## Phạm vi có thể triển khai

Chuẩn hóa quy tắc mở Stage 1 và Stage 2 theo hành vi đang chạy trên nhánh. Dashboard đọc session detail khi người dùng bấm mở. `getSessionDetail` đã kiểm ID trả về, `source_questions` và `exam_versions`. Resolver chọn đích từ `status` của detail. Stage 1 dùng cùng resolver cho handoff sang Stage 2.

| Dữ liệu đang có | Hành vi giữ làm tiêu chí |
|---|---|
| `draft` | `/session/:sessionId/stage1` |
| `blueprinted`, `configured`, `generating` | `/session/:sessionId/stage2` |
| `partial_generated`, `generated`, `reviewed`, `approved`, `exported`, `failed` | Giữ hành vi mở từ Dashboard hiện tại: ở lại Dashboard và hiện notice. Đích mới chờ Q11 hoặc bàn giao module tương ứng. |
| Status ngoài các nhóm trên | Giữ thông báo trạng thái chưa hỗ trợ và không điều hướng. |

Đường dẫn Stage 3 `/session/:id/stage3` và preview `/session/:id/stage3/preview` đã được nêu trong [handoff PR #59](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/59). Handoff này xác nhận tên đường dẫn. Việc dùng các đường dẫn đó làm đích Resume cho từng trạng thái còn cần contract và component phù hợp. Giữ route Stage 3 đã đăng ký trong `App.jsx`.

## Thứ tự triển khai

| Lượt / file dự kiến | Đầu ra | Input đã có | Cách kiểm |
|---|---|---|---|
| 1. `sessionDestination.js`, `App.jsx`, `Stage1Route.jsx` nếu cần | Dùng chung định nghĩa đường dẫn Stage 1/2 ở những nơi khai báo và tạo URL. Giữ encode ID, luồng `stage1/new` và handoff cùng session. | Route và caller hiện hữu trên `d4350c0`. | Test resolver cho bốn trạng thái có đích và cả các trạng thái đang trả notice. Kiểm Stage 1 mới, Stage 1 đã confirm và Stage 2 direct URL. |
| 2. `DashboardRoute.jsx`, `sessionDestination.test.js`, `Stage1SourcePanel.test.js` | Kiểm lại guard hiện có qua entry point thật. Chỉ sửa handler/guard khi kiểm tái hiện được sai lệch trong phạm vi hiện tại. | `createSessionOpener` đã có abort, revision và kiểm account. `ProtectedRoute` đã phân biệt checking, profile pending và signed out. | Mở hai session liên tiếp, đăng xuất hoặc đổi account khi GET còn pending. Chỉ phiên và account hiện hành được cập nhật hoặc điều hướng. Khi profile đang xác minh, giữ URL và chặn màn protected. |
| 3. Kiểm trên build của nhánh | Gói kết quả cho phần nền điều hướng và danh sách trạng thái còn chờ. | Fixture theo shape API hiện hành. Local stack dùng cho smoke nếu chạy được trên đúng build. | Targeted Node tests, `npm run lint`, `npm run build` từ `frontend/`. Browser smoke Dashboard → Stage 1/2, F5, deep-link và đăng xuất. Ghi fixture và API thật theo môi trường thực chạy. |

Tận dụng test hiện có cho double-click, lỗi GET, response về muộn và handoff Stage 1. Chỉ thêm ca hồi quy nếu entry point đang sửa có hành vi chưa được suite hiện tại kiểm. Bước đầu dùng `node --test src/features/dashboard/sessionDestination.test.js src/features/stage1-ingestion/Stage1SourcePanel.test.js src/services/sessions.test.js` từ `frontend/`. Nếu thay đổi chạm hành vi Stage 2, chạy thêm `src/features/stage2-config/Stage2ConfigPage.test.js`.

## Kế hoạch commit cho PR #60

| Thứ tự | Commit dự kiến | Phạm vi và điểm chốt |
|---|---|---|
| 1 | `docs(w4-mvp-10): add route foundation plan` | Chỉ `docs/tasks/W4-MVP-10.md`. Ghi phạm vi, route matrix đã có căn cứ, các đầu vào Q11 và kế hoạch kiểm. Rà diff và link trước khi commit. |
| 2 | `refactor(navigation): share stage 1 and stage 2 paths` | Đổi định nghĩa route và các caller trong cùng commit để build chạy được ở từng mốc. Giữ các URL và hành vi hiện có. Chạy nhóm targeted tests, thêm `Stage2ConfigPage.test.js` nếu đổi nút quay lại Stage 1, rồi lint/build. |
| Nếu phát hiện lỗi | `fix(navigation): <hành vi tái hiện được>` | Tách lỗi điều hướng hoặc response về muộn khỏi commit refactor. Chỉ sửa file gây lỗi và thêm ca hồi quy nếu suite chưa bao phủ. Đặt tên commit sau khi có ca tái hiện. |
| Cuối | `docs(w4-mvp-10): record route foundation checks` | Cập nhật M2 với kết quả theo SHA, phạm vi browser smoke đã chạy, phần còn chờ Q11 và đầu ra cho nhánh Resume. Chỉ ghi kết quả đã kiểm. |

### Phạm vi file của commit điều hướng

Các đường dẫn dưới đây tính từ `frontend/src/`.

| File | Thay đổi dự kiến |
|---|---|
| `sessionPaths.js` (mới, đề xuất) | Chứa route pattern và hàm tạo URL Stage 1/2 dùng chung. Giữ tham số `sessionId`, encode đúng một lần và hỗ trợ `new` ở Stage 1. |
| `App.jsx` | Dùng route pattern chung cho hai đăng ký Stage 1/2 trong `ProtectedRoute`. |
| `features/dashboard/sessionDestination.js` | Dùng hàm tạo URL chung cho bốn trạng thái đã xác định. Giữ fallback và notice hiện tại. |
| `features/dashboard/DashboardRoute.jsx` | Dùng cùng hàm tạo URL cho nút tạo phiên mới. Logic mở phiên vẫn đi qua `createSessionOpener`. |
| `features/stage1-ingestion/Stage1Route.jsx` | Dùng hàm tạo URL khi nhận ID phiên mới. Handoff sau confirm tiếp tục đọc đích từ resolver, giữ guard account/session và `replace`. |
| `features/stage2-config/Stage2ConfigPage.jsx` | Nếu đổi caller này trong commit, chỉ dùng hàm tạo URL Stage 1 cho nút quay lại nguồn. Giữ nguyên điều kiện hiển thị nút. |

Chạy lại `sessionDestination.test.js`, `Stage1SourcePanel.test.js` và `sessions.test.js` để kiểm hợp đồng hành vi hiện tại. Chỉ sửa các file test khi cần bao phủ ca hồi quy hoặc entry point đã thay đổi. `ProtectedRoute.jsx` và `services/sessions.js` là điểm cần kiểm qua luồng hiện có. Hai URL Stage 2 trong `Stage3ReviewPage.jsx` thuộc màn Bội Anh đang bàn giao qua PR #59 và sẽ được đối chiếu trong nhánh Resume. Mọi thay đổi mapping theo Q11 cần căn cứ từ phản hồi provider trước khi bổ sung vào plan.

## Đầu vào còn chờ

[Comment Q11 trên PR #60](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/60#issuecomment-6792990184) là nơi theo dõi phản hồi của provider. Khi lập plan, thread có yêu cầu từ Trung Anh và chưa có phản hồi xác nhận từ Duy hoặc Bội Anh.

| ID | Cung cấp → nhận | Điều kiện đủ dùng | Trạng thái / ETA |
|---|---|---|---|
| `I-W4MVP10-STATE` | Duy → TV1/W4-MVP-10 | Contract hoặc JSON có phiên bản cho `reviewed` trước/sau shuffle, khả năng phục hồi `failed`, cách đọc `approved`/`exported` và artifact. | Chờ xác nhận trước khi nối các đích này. ETA TBD. |
| `I-W4MVP10-FE2` | Bội Anh → TV1/W4-MVP-10 | Hành vi của `partial_generated`, quyền thao tác khi còn thiếu slot, dữ liệu/props khi vào preview trực tiếp và trách nhiệm điều hướng sau approve. | Đã có đường dẫn Stage 3/preview. Phần hành vi và component wiring chờ xác nhận. ETA TBD. |

Tích hợp Review, Approval, Export và kiểm FE-H2 nằm trong `feat/w4-mvp-10-resume-integration` sau khi nhận các module 03/04/06/09 và build tương thích. Export Download thuộc `feat/w4-mvp-09-export-download`. TASK-207 đã hoàn tất phần triển khai theo xác nhận của TV1. Merge PR #30 không phải điều kiện để triển khai ba lượt nền route trên.

## Bàn giao

- Đầu ra dự kiến cho Bội Anh, Duy và nhánh tích hợp: route matrix có căn cứ, thay đổi điều hướng trên PR #60, kết quả kiểm theo head và danh sách trường hợp chờ Q11.
- Trạng thái tại commit plan: đã lập M2 và đối chiếu các đầu vào Q11.
- Kiểm baseline tại `d4350c0` với Node `v22.20.0`: lệnh targeted ở trên đạt **78/78**. Đây là kết quả trước triển khai trên fixture và unit tests.
