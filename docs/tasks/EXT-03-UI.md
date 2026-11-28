# EXT-03 — Bội Anh: Kế hoạch triển khai Giao diện Export & OMR (M2)

- **Tác giả:** Bội Anh (`@htbaax`, FE2 Owner / EXT-03 Giao diện, Mẫu & Đối soát bản in theo phân công EXT v3.1 §1).
- **Phối hợp:** Đạt (`@Thanhdat3010`, Backend EXT-03), Hùng (`@benalexx007`, UI EXT-04), Nhật Quỳnh (`@nhatquynh1107`, DB/Backend EXT-04).
- **Reviewer đề xuất:** Đạt (Export contract & OMR), Hùng (Bank $\rightarrow$ Export handoff), Duy (Review coordinator).
- **Quy trình:** Workflow v0.1 proposed + INPUT-20261109; [M2](../review/TEMPLATES.md#m2).
- **Nhánh:** `feat/ext-03-export-ui` → `dev`. Base đã đối chiếu: `dev@b292443`.
- **Căn cứ kế hoạch:** Phân công EXT v3.1 ngày 25/11/2026 (§1, §EXT-03, §6 A14, A16–A18, A20) và Contract `I-EXT-05` đề xuất tại PR #113 (`docs/tasks/EXT-03.md`).
- **Trạng thái:** **M2 Draft — Plan & Input tracking phía Frontend; chuẩn bị triển khai code.**

---

## 1. Phạm vi công việc phía Giao diện (Frontend Scope)

1. **Form cấu hình xuất bản linh hoạt (`SessionExportPage.jsx`):**
   - Trường hiển thị (`visible_fields`): Tiêu đề, 8 trường metadata, ô thí sinh (`student_name`, `student_id`, `student_class`).
   - Phiếu trả lời (`answer_sheet`): `none`, `written_boxes`, `omr_bubbles` (khóa an toàn `disabled` kèm tooltip).
   - Định dạng tệp (`formats`): `pdf`, `latex`, `markdown` (kiểm tra hợp lệ, chặn lỗi 422 khi non-PDF gửi tùy chọn PDF).
2. **Minh họa trực quan ô điền đáp án (`written_boxes`):**
   - Render preview trực quan khung ô vuông A/B/C/D đặt ngay dưới tiêu đề đề thi để giáo viên xem trước bố cục.
3. **Cơ chế khôi phục sau Reload (F5) & State Machine (`exportController.js`):**
   - Lưu trữ an toàn bộ 4 trường `{session_id, packaging_key, identity_kind, effective_config}` trong `sessionStorage` (cô lập theo `accountKey:sessionId`).
   - Polling trạng thái `preparing` mỗi 2s, tự động hủy polling khi unmount hoặc chuyển phiên.
   - Bắt và xử lý thân thiện toàn bộ mã lỗi: `422 ERR_EXPORT_CONFIG_INVALID`, `422 ERR_EXPORT_OMR_UNAVAILABLE`, `422 ERR_EXPORT_QUESTION_LIMIT`, `404 ERR_EXPORT_PACKAGE_NOT_FOUND`, `409 ERR_EXPORT_NOT_READY`.
4. **Tải đáp án riêng biệt (CSV / JSON):**
   - Tích hợp endpoint `GET /api/sessions/{id}/answer-key` theo từng mã đề hoặc đề gốc mà không cần tải cả file ZIP.
5. **Handoff mượt mà từ Ngân hàng đề (Bank) sang Export:**
   - Nhận `session_id` từ URL `/sessions/:id/export` để nạp đúng dữ liệu phiên đã duyệt.

---

## 2. Bảng theo dõi Đầu vào & Yêu cầu hỗ trợ (Input Dependencies)

| ID Input | Bên giao → Bên nhận | Nội dung yêu cầu | Trạng thái hiện tại |
|---|---|---|---|
| **I-EXT-05** | Đạt (`@Thanhdat3010`) → Bội Anh (`@htbaax`) | Contract API đóng gói xuất bản & tải đáp án riêng. | **Accepted** trên PR #113; Chờ Đạt ghim fixture synthetic mẫu JSON/CSV vào docs. |
| **I-EXT-04** | Đạt (`@Thanhdat3010`) → Bội Anh (`@htbaax`) | Bàn giao file PDF mẫu OMR (TNMaker) khi backend hoàn tất để in test. | **Pending** (Chờ backend Đạt sẵn sàng); UI Export tạm khóa `omr_bubbles`. |
| **I-EXT-05-ROUTING** | Hùng (`@benalexx007`) → Bội Anh (`@htbaax`) | Xác nhận route điều hướng từ Bank/Finalize sang Export là `/sessions/:id/export`. | **Chờ Hùng xác nhận** trên Draft PR này. |
| **I-EXT-02-SNAP** | Quỳnh (`@nhatquynh1107`) → Bội Anh (`@htbaax`) | Đảm bảo snapshot phiên đã duyệt trả về đúng danh sách mã công khai `public_version_code` (101, 102...). | **Decided** ở PR #114; Chờ migration DB. |

---

## 3. Thứ tự triển khai Code & Kiểm thử đa tầng

- **Phase 1: Controller & Service Adapter**
  - Mở rộng [exportService.js](../../frontend/src/services/exportService.js) (gửi config, nhận packaging key, tải đáp án riêng).
  - Cập nhật State Machine [exportController.js](../../frontend/src/features/export/exportController.js) (quản lý 3 nhánh identity, lưu `sessionStorage`, bắt lỗi `422/404/409`).
  - Viết 100% unit tests trong [exportController.test.js](../../frontend/src/features/export/exportController.test.js).
- **Phase 2: Giao diện Form tùy chọn & Preview**
  - Cập nhật [SessionExportPage.jsx](../../frontend/src/features/export/SessionExportPage.jsx) (Form 3 khối, preview `written_boxes`, cụm nút tải đáp án riêng, khóa `omr_bubbles`).
  - Viết component tests trong [SessionExportPage.test.js](../../frontend/src/features/export/SessionExportPage.test.js).
- **Phase 3: Tích hợp Handoff & Resilience**
  - Đấu nối URL với Hùng từ Bank sang Export.
  - Test F5 reload ở mọi trạng thái và test chuyển phiên A $\rightarrow$ B $\rightarrow$ A.
- **Phase 4: Đối soát bản in thực tế OMR (ca A18)**
  - In giấy A4 thật và test quét qua app TNMaker khi Đạt bàn giao PDF.
- **Phase 5: Full Quality Gates**
  - 621+ test suite hiện có + test mới PASS 100%.
  - `npm run lint` 0 lỗi, `npm run build` thành công.
