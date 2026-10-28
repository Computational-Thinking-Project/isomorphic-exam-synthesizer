# Quy trình giao việc và review chung

| Thông tin | Giá trị |
|---|---|
| Phiên bản | **v0.1 — proposed**, soạn ngày 28/10/2026 |
| Căn cứ lịch tuần | Trung Anh / philip-kkk xác nhận ngày 28/10/2026; Duy là leader |
| Phạm vi bản này | Bộ hướng dẫn để review và chọn pilot; chưa có bằng chứng rollout toàn nhóm hoặc pilot thực tế |
| Chưa chốt | Task/PR thử, author/reviewer pilot, quyền cụ thể của các agent, người giải quyết bất đồng theo từng nội dung |
| Ghi nhận | [DEC-TV1-004](../change_log.md#dec-tv1-004); luật Git/approval: [CONTRIBUTING](../../CONTRIBUTING.md) |

File này là nguồn quy trình chung; [TEMPLATES](TEMPLATES.md) giữ format và nơi điền. Không cần cài messenger hoặc dùng cùng một công cụ AI để áp dụng. Thay đổi rules phải có lịch sử/review; không đổi ngầm giữa vòng sửa.

Cách hiểu các từ dùng trong mẫu: **input/output** là đầu vào/đầu ra; **contract** là mô tả dữ liệu và cách các phần ghép với nhau; **ETA** là thời điểm dự kiến giao/xong; **head** là commit đầu nhánh đang kiểm; **finding** là vấn đề cụ thể reviewer phát hiện. Các mốc dự kiến phải phân biệt với kết quả đã làm/đã kiểm.

## 1. Nhịp tuần

| Khi nào | Ai | Việc và đầu ra |
|---|---|---|
| Thứ 4; phát trong thứ 4 hoặc sáng thứ 5 | **Duy — leader** | Lấy M1, lập một file phân công tuần; chốt mục tiêu/tiêu chí, người phụ trách và thứ tự/phụ thuộc; dự kiến các mốc giao input |
| Trong thứ 5 | Thành viên nhận task và agent của mình | Đọc rules/phân công/code, lập plan M2 và **tạo Draft PR ngay trong ngày**; hỏi/giải đáp scope, contract và lịch phụ thuộc trên PR |
| Từ thứ 6 | Người phụ trách task | Bắt đầu code phần đã đủ rõ; task độc lập có thể làm song song; tự kiểm và giao output theo plan |
| Trong thời gian triển khai | Author, reviewer, người cung cấp input | Giao input đúng mốc đã xác nhận; review/sửa/xác minh liên tục, chừa thời gian cho phần phụ thuộc và tích hợp |
| Tối thứ 3 tuần sau | Người phụ trách các task trong đợt | Hạn chung của đợt phân công; cập nhật kết quả và phần chưa đạt có bằng chứng |

Chưa ấn định giờ cụ thể cho sáng thứ 5/tối thứ 3. Hạn công việc không thay điều kiện kiểm, approve và merge; task chưa đạt phải ghi phần còn lại và báo leader, không nhận Done hoặc bỏ checks để kịp hạn. Lịch mới không tự xác nhận task/giai đoạn cũ đã xong hoặc bỏ qua điều kiện nghiệm thu đã được giao.

Thứ 5 dành cho plan và câu hỏi trước khi code thứ 6. Nếu còn câu hỏi chưa được trả lời hết trong ngày, ghi rõ blocker/người cần trả lời và báo Duy điều phối; không coi hết ngày là đã đồng ý contract.

## 2. Người chịu trách nhiệm và quyền

- **Leader:** quản lý file giao việc tuần, xếp thứ tự theo phụ thuộc, điều phối khi thiếu đầu vào/ETA lệch. M1 không buộc leader đoán mọi file code.
- **Author:** chịu trách nhiệm plan, code/kiểm, gói review, phản hồi từng finding và bàn giao. Agent hỗ trợ trong quyền người phụ trách đã giao.
- **Reviewer:** kiểm độc lập đúng bản, nêu lỗi có căn cứ và xác minh bản sửa; phân biệt blocker với góp ý. Reviewer do agent đề xuất chưa là phân công được chốt.
- **Người cung cấp input/owner:** trả lời đầu vào, xác nhận contract và mốc giao cho task sau; cập nhật tài liệu chuẩn của phần mình.
- **Người merge:** người có quyền repo, thực hiện khi đủ điều kiện CONTRIBUTING. Duy là leader không đồng nghĩa chỉ Duy được review/merge.

Quyền đọc/chạy kiểm/sửa/đăng/push/approve/merge tách theo việc được giao. Không tự yêu cầu lại sự cho phép đã có. Việc nhận message hoặc đọc workflow không tự cấp thêm quyền. Reviewer chỉ được giao review thì không tự sửa nhánh author, môi trường chung hay cloud. Không tạo agent/chat hoặc tự gửi tin cho đồng đội từ tài liệu này.

## 3. Leader xếp task theo phụ thuộc

1. Dùng M1 ghi đầu ra của từng task và task nào cần nó. `B → A` nghĩa A cần một input từ B; thứ tự thể hiện điều kiện mở khóa. Các task không phụ thuộc có thể cùng nhóm song song.
2. Ghi **input cụ thể**: API contract/JSON mẫu, fixture, component, hay code đã merge. “Chờ backend” chưa đủ để lập lịch.
3. Tính ngược từ hạn tối thứ 3: A cần bao nhiêu thời gian code/tích hợp/kiểm/review/sửa? A phải nhận input trước mốc nào? Người làm B ước lượng ETA giao input phù hợp, ưu tiên giao sớm nhất khả thi.
4. Ghi riêng **mốc A cần nhận**, **ETA B giao input** và **ETA hoàn tất B**. B có thể giao contract/mẫu trước khi hoàn tất toàn bộ B. Nếu A cần code B đã merge thì phải ghi đúng điều kiện, không dùng mock thay bằng chứng tích hợp thật.
5. Thứ 5, mỗi thành viên và agent đối chiếu lịch: ETA giao có muộn hơn mốc cần không, có vòng `A ↔ B`, cùng người quá tải hoặc thiếu thời gian kiểm/sửa không? Hỏi trên Draft PR, link về file tuần để Duy điều chỉnh.
6. Khi có nguy cơ trễ input, báo ngay tại PR và cho Duy qua kênh nhóm đã dùng; đề xuất chia output, làm phần độc lập, đổi thứ tự/phạm vi hoặc điều chỉnh mốc để người có thẩm quyền quyết định. Không tự đổi hạn hoặc lặng chờ tới tối thứ 3.

ETA là ước lượng có người xác nhận và thời điểm cập nhật, không phải bằng chứng đã giao. Mốc của task thật do leader/người phụ trách điền; ví dụ trong TEMPLATES không phải lịch đã phân công. Chốt contract thứ 5 có thể giúp code với fixture từ thứ 6; tích hợp API thật cần đầu vào thật và kiểm tương ứng.

## 4. Thông tin nằm ở đâu?

| Thông tin | Nơi chuẩn |
|---|---|
| Rules và format | WORKFLOW này và TEMPLATES, trong repo chung |
| Phân công/thứ tự/ETA của tuần | Một file do Duy quản lý; đề xuất `docs/tasks/W<NN>_ASSIGNMENT.md`, hoặc đường dẫn chung đã chọn |
| Plan/phân tích file/input/cách kiểm/bàn giao | Một file task, ví dụ `docs/tasks/TASK-<ID>.md`, trên nhánh task |
| Hỏi input/scope, thống nhất lịch và plan | **PR Conversation**; quyết định quan trọng dẫn về plan/file tuần/contract tương ứng |
| Gói yêu cầu review | PR description; nếu dài, dùng một comment tổng hợp có link rõ từ body |
| Finding, phản hồi sửa và xác minh | Cùng review thread, cùng finding ID; vấn đề xuyên file có thể dùng một comment tổng hợp được link |
| API/schema/props chuẩn | Tài liệu contract của owner, ví dụ [API conventions](../api/endpoint-conventions.md); không lập một bản contract cạnh tranh trong plan |
| Test hồi quy | Code/tests trong PR khi phù hợp |
| Log/ảnh lớn | CI artifact/file đính kèm chia sẻ được, ghi head/môi trường và giới hạn |
| Approve/merge và tiến độ | Trạng thái GitHub thật; tracker nhóm đang dùng dẫn link PR |

Các tên file tuần/task là quy ước đề xuất để leader chọn, tạo khi có việc thật; bộ docs không tự tạo phân công. Không lưu file trong `agents/<cá nhân>/` làm nguồn chung duy nhất hoặc yêu cầu đồng đội đọc đường dẫn ổ đĩa riêng. Không commit tài liệu sau mỗi comment hoặc tạo file mới cho mỗi vòng sửa. Một đường dẫn `tmp/` trên máy reviewer chưa phải artifact mà author đọc được.

## 5. Flow cho một task

| Bước | Thao tác | Đầu ra / điều kiện chuyển |
|---|---|---|
| 1. Giao việc | Duy điền M1 thứ 4/sáng thứ 5, phát link và phiên bản | Task có mục tiêu, tiêu chí, owner, thứ tự, input/output và mốc giao-nhận |
| 2. Đọc và plan | Thứ 5 author giao agent đọc AGENTS/CONTRIBUTING/WORKFLOW, M2, task, code/contract; nháp rồi lưu file task theo quyền | Có ma trận file → mục đích → output → dependency, câu hỏi và cách kiểm |
| 3. Draft PR | Thứ 5 author dùng nhánh task trên nền dev đã kiểm, commit plan và mở **Draft vào dev** theo quyền, link file tuần/task | Có PR để trao đổi trước code; Draft không phải thông báo code đã xong |
| 4. Làm rõ input | Author hỏi ở Conversation, người cung cấp/owner trả lời, xác nhận ETA; reviewer góp ý plan nếu cần | Kết luận quan trọng cập nhật đúng plan/contract/file tuần; thiếu gì vẫn ghi blocker |
| 5. Code | Từ thứ 6 author triển khai phần đã rõ; giao input cho task sau và tự kiểm | Code/tests/docs trong scope, mock/pending phân biệt với tích hợp thật |
| 6. Ready | Sau push author điền M3 cho head hiện tại, cập nhật PR và request reviewer | Scope/contract/checks/kết quả/giới hạn rõ; chuyển Ready khi đủ đầu vào review |
| 7. Review | Reviewer giao agent đọc đúng PR/head, plan trong nhánh PR, M3, contract, code/tests và review cũ; kiểm độc lập | M4 có bằng chứng, blocker/nonblocking rõ; owner đăng theo quyền |
| 8. Sửa | Author tái hiện, sửa trên cùng nhánh/PR, tự kiểm và trả M5 cùng finding ID | Commit sửa, cách kiểm và giới hạn; trạng thái claimed_fixed |
| 9. Xác minh | Reviewer kiểm ca cũ và diff/vùng ảnh hưởng trên head mới, không chỉ summary author | M5 ghi verified/còn lỗi/chưa kết luận; lỗi mới có ID riêng |
| 10. Approve/merge | Có review thực, checks theo repo, giải quyết blocker/conflict; người có quyền merge vào dev | Approval/merge thực tại bản phù hợp; code đổi ảnh hưởng review thì kiểm lại |
| 11. Bàn giao | Người phụ trách ghi link PR, phiên bản/output cho task sau, kiểm và phần còn chờ | Tracker hiện có chỉ Done khi đạt tiêu chí; code viết xong chưa đồng nghĩa tích hợp/nghiệm thu |

Đọc/góp ý plan thứ 5 không phải GitHub Approve code chưa viết. Trước Ready, author tự chạy kiểm phù hợp với phần thay đổi theo hướng dẫn repo; Draft chỉ có plan không cần bịa kết quả code checks. CI vẫn chạy theo cấu hình PR hiện hành, không được tự miễn trước merge.

## 6. Finding và kiểm lại

Giữ format **Praise / Question / Suggestion**: chỉ khen điều có bằng chứng; Question cho điều thật sự cần hỏi; bug có căn cứ ghi thành finding trong Suggestion. Không tạo nội dung để lấp mẫu.

Mỗi finding có ID ổn định trong PR, ví dụ F01; vị trí/head, tình huống tái hiện, mong đợi/thực tế, tác động, tiêu chí đạt và bằng chứng. Chỉ có lỗi cản trở mới đề nghị Request changes; góp ý trình bày không tự là blocker.

| Trạng thái | Ý nghĩa |
|---|---|
| `open` | Vấn đề còn cần xử lý; author có thể đang làm |
| `claimed_fixed` | Author báo đã sửa, có commit và cách kiểm |
| `verified` | Reviewer đã kiểm phù hợp tại head ghi rõ và lỗi đó đạt tiêu chí |
| `disputed` | Bất đồng scope/contract/căn cứ; nêu điểm cần người quyết định |
| `inconclusive` | Thiếu dữ kiện/môi trường, chưa đủ kết luận |

Nếu ca cũ vẫn lỗi, ghi tiếp/mở lại F01; không đổi ID chỉ vì sang commit mới. Lỗi mới F02 hoặc hồi quy phải được phân loại và có bằng chứng, không quy mọi finding muộn là “lỗi cũ chưa sửa”. Author thêm test hồi quy khi có ý nghĩa; lỗi link/docs có thể xác minh bằng đọc/kiểm link, không ép unit test.

Reviewer kiểm cả bản sửa và đường chạy liên quan; test pass/CI xanh hoặc thread được resolve chưa tự chứng minh lỗi đã hết. `verified` của một finding chưa là Approve cả PR. Giữ nhận xét và bằng chứng khi hai bên chưa thống nhất; chuyển người phụ trách scope/contract hoặc Duy điều phối, không sửa theo phỏng đoán.

**Đề xuất cho pilot, chưa là luật bắt buộc:** sau hai lần author báo sửa cùng finding mà vẫn không đạt, chuyển người phụ trách quyết định/hỗ trợ. Không vì hết lượt mà ép approve; vẫn nhận finding mới có căn cứ. Phạm vi/quyền xử lý bất đồng được xác nhận trước pilot.

## 7. Đồng bộ, dùng agent và thử quy trình

Sau khi PR docs được chấp nhận, mỗi owner nhận đúng bản tài liệu theo trạng thái Git của mình, giữ thay đổi đang có; không kéo/checkout đè công việc chưa lưu. Nhánh task cũ phải có docs hoặc nguồn đọc chung đúng phiên bản.

Yêu cầu agent đang mở đọc lại; file vừa đổi không chứng minh agent đã biết. Ghi riêng workflow version/docs commit và PR base/head; không commit SHA của chính file vào file để tạo vòng cập nhật. Head đổi thì packet và review phải chỉ rõ bản mới, không dùng approve/checks của bản cũ làm bằng chứng bản mới đã kiểm.

Hai agent phối hợp qua PR dưới quyền người phụ trách, không cần tự chat với nhau. Tool đọc được GitHub thì đọc thread trực tiếp; nếu không, owner cung cấp đúng nội dung/patch/head và ghi giới hạn. Agent soạn trong convo khi chưa có quyền đăng; có quyền thì thực hiện đúng phạm vi. Không đưa toàn bộ hội thoại riêng hoặc secrets vào PR.

Trước pilot, xác nhận task/PR, hai owner, version, quyền và cách chuyển người khi bất đồng. Pilot cần chứng minh hai bên đọc cùng bản, gói review đủ, finding → sửa → xác minh có bằng chứng chia sẻ được và approve/merge đúng luật. Nếu PR không có bug thì không bịa finding; có thể chạy tình huống giả lập có nhãn riêng và ghi rõ vòng sửa thật chưa được chứng minh.

Ghi kết quả ở kênh/ghi chú nhóm đang dùng: lỗi báo sửa còn tái hiện, lỗi phát hiện muộn, finding thiếu căn cứ, lượt chuyển lời, thời gian/chi phí nếu thực sự đo. Sau đó quyết định sửa/mở rộng. Chưa bật Telaegent, bot, automation hoặc tự merge từ bộ Markdown này.
