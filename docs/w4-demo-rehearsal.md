# W4 — Script thao tác và phiếu diễn tập của Đạt

Bản chuẩn bị cho W4-MVP-21; chưa chạy nghiệm thu. [Runbook OPS](w4-staging-runbook.md) là nguồn lệnh build/deploy; [bảng input](tasks/TASK-W4-OPS.md#input-handoff) là nơi tổng hợp duy nhất. Không đổi task/contract hoặc thay quyết định môi trường tại Issue #53. Mỗi thành viên chạy Docker local của mình; diễn tập local không tự là private beta/G1/G2.

## Trước buổi chạy

- Nhận candidate SHA/manifest tương thích từ Duy; đối chiếu checkout sạch, image IDs, DB ledger, config revision và prompt/model thực. Nếu thiếu, vẫn đọc thử script nhưng ghi BLOCKED cho chạy tích hợp.
- Dùng checkout riêng theo runbook mục2; không switch/reset/xóa working tree đang có công việc. Operator điền env qua kênh được cấp; không copy env của người khác. Build static Compose một worker, chạy preflight/smoke, ghi Typst version.
- Nhận Golden Markdown3 câu, quyền sử dụng và oracle key/solution đã được Quỳnh/Tâm/Duy duyệt; N=2, shuffle mặc định OFF/OFF. Không tự bịa Golden để đánh nghiệm thu PASS.
- Xác nhận tài khoản A/B/admin/non-admin, quyền test và nơi lưu evidence. Các ca restart/fault injection/security phải dùng môi trường cô lập đã được phép; không phá DB production.
- Mở browser sạch, kiểm origin/callback; đóng bảng env, token, DevTools headers và URL có signed token trước khi quay. Nếu chưa có consent/nơi lưu thì chỉ ghi checklist không nhạy cảm.

## Script 8 bước cho người thao tác

| Bước | Thao tác / lời dẫn ngắn | Kỳ vọng / bằng chứng |
|---|---|---|
| 1 | “Tôi nhập tài liệu để tạo đề nguồn.” Đăng nhập A, tạo session mới và import Golden. | Đúng3 câu; ghi session alias, ảnh UI đã làm sạch; chưa gọi đây là đề sinh. |
| 2 | “Tôi xem và xác nhận đề nguồn trước khi tạo mẫu.” Kiểm nội dung/options/key, xác nhận rồi chờ canonical Blueprint ready. | Không sinh Blueprint trước xác nhận; nếu nguồn sai thì dừng sửa ở bước nguồn; ghi revision/artifact tham chiếu. |
| 3 | “Từ mẫu đã xác nhận, tôi cần hai mã đề.” Chọn N=2; kiểm hai shuffle toggles OFF/OFF, modes không cho giáo viên tùy chọn theo contract W4. | UI/payload đúng contract đã chốt; contract/code chưa đồng bộ thì FAIL/BLOCKED, không giả hành vi. |
| 4 | “Hệ thống sinh và lưu từng kết quả.” Generate, quan sát progress; F5 một lần khi phù hợp để kiểm khôi phục. | Đủ6 slots hoặc hiện lỗi/partial đúng; committed slots không sinh trùng, quota không reset; snapshot/SSE đúng. |
| 5 | “Giáo viên kiểm soát từng câu.” Review, sinh lại bằng button, Revert về nguồn; Accept các câu đạt. | Đúng current record, key/solution/options tương ứng; regen/revert dùng session phụ nếu làm lệch Golden. Không nhập prompt tự do. |
| 6 | “Tôi kiểm bản cuối trước khi khóa.” Preview OFF/OFF rồi kiểm ca shuffle đã được owner hỗ trợ; F5 xem mapping. | Thứ tự/choices/đáp án/lời giải nhất quán, không shuffle lại ngoài ý muốn. Ca shuffle khác dùng session riêng nếu cần. |
| 7 | “Tôi duyệt và tải bộ đề.” Final approval, thử sửa sau lock ở ca được phép, export rồi tải ZIP mới. | Lock423 theo endpoint contract; export trước duyệt bị chặn ở ca riêng; ZIP thật mở được,6/6 slots khớp oracle. |
| 8 | “Mở lại phiên vẫn giữ kết quả.” Reload/mở lại session và kiểm state, preview/download/resume. | Không tạo job/approval/export trùng; locked state và dữ liệu đã lưu còn đúng. |

Không cần ép mọi nhánh lỗi vào một Golden session. Tách ca regen/revert, fallback hết retry, partial/retry, ownership A/B, metrics admin và process restart; dẫn kết quả case ID. Ca chưa chạy ghi UNRUN, không suy từ health200. Nếu bước chặn thất bại, giữ evidence lỗi, ghi FAIL/BLOCKED và chuyển owner; không đổi code/prompt giữa buổi để tiếp tục gắn nhãn cùng head.

## Phiếu chạy — sao chép ra thư mục evidence được duyệt

Mẫu trống, không phải báo cáo đã chạy. Chưa thao tác dùng UNRUN; thiếu input dùng BLOCKED; hành vi sai dùng FAIL. Chỉ PASS khi có bằng chứng. G0/G1/G2 theo runbook, Duy xác nhận nghiệm thu riêng.

```text
Run ID / gate / thời gian +07:
Operator / observer / môi trường local hoặc URL không token:
Checkout SHA / deployed SHA / images:
DB manifest+applied ledger / config revision / prompt+model:
Golden artifact+oracle revision / permission reference / N / toggles:
Bước 1..8: UNRUN | PASS | FAIL | BLOCKED; actual; evidence reference:
Ca riêng: ID / môi trường / head / actual / evidence / giới hạn:
ZIP: tên artifact đã làm sạch / checksum / đã mở các formats nào:
Kết quả tổng / blocker ID / owner xác nhận hoặc TBD / bước tiếp:
Duy acceptance: NOT ACCEPTED hoặc link/ngày xác nhận:
```

### Đối chiếu đủ6 slots

Dùng nhãn S1/S2/S3 theo nguồn và V1/V2 theo mã đề, không dùng chỉ số hiển thị sau shuffle làm định danh nguồn. Nếu shuffle options bật, so nội dung option đúng sau permutation với oracle; ký tự A/B/C/D có thể đổi. Kiểm lời giải suy ra đúng option hiển thị, không chỉ đếm6 rows hoặc so checksum ZIP.

| Slot nguồn/mã | Câu hiển thị / vị trí | Option đúng theo oracle → key hiển thị | Lời giải đúng nội dung | DB/preview ↔ ZIP | Kết quả/evidence |
|---|---|---|---|---|---|
| S1/V1 | Chưa ghi | Chưa kiểm | Chưa kiểm | Chưa kiểm | UNRUN |
| S2/V1 | Chưa ghi | Chưa kiểm | Chưa kiểm | Chưa kiểm | UNRUN |
| S3/V1 | Chưa ghi | Chưa kiểm | Chưa kiểm | Chưa kiểm | UNRUN |
| S1/V2 | Chưa ghi | Chưa kiểm | Chưa kiểm | Chưa kiểm | UNRUN |
| S2/V2 | Chưa ghi | Chưa kiểm | Chưa kiểm | Chưa kiểm | UNRUN |
| S3/V2 | Chưa ghi | Chưa kiểm | Chưa kiểm | Chưa kiểm | UNRUN |

## Kết thúc và phục hồi

Lưu log đã làm sạch, checksum ZIP và phiếu chạy tại nơi được duyệt; recording chỉ khi có quyền. Không đưa JWT, service-role/Gemini key, signed URL còn hạn hay roster cá nhân vào repo. Lỗi module chuyển đúng owner theo runbook mục4; đổi head/config/ledger/prompt phải ghi run mới và kiểm lại phần bị ảnh hưởng. Rollback app chỉ khi tương thích schema và được operator có quyền thực hiện; restore/forward-fix DB do Duy/Hùng bàn giao, không tự down -v/prune. Với stack local riêng, dừng bằng docker compose down đúng project sau buổi chạy nếu không cần giữ; không xóa dữ liệu môi trường chung.

Mốc theo W4: script12/11, rehearsal13/11, proof14/11, demo/bàn giao15/11. Đây là mốc nguồn, không tự xác nhận lịch cá nhân hoặc kết quả PASS.
