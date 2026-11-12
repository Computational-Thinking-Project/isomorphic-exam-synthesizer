# Kế hoạch triển khai & Bàn giao Week 4: W4-MVP-04 — FE2 (`htbaax`)

| Thông tin | Giá trị |
|---|---|
| **Mã nhiệm vụ** | **`W4-MVP-04`** (Stage 3 Review FE + Điều chỉnh Stage 2 Config UI theo Issue #45 & Issue #46) |
| **Owner** | Bội Anh (`@htbaax` — FE2, Frontend Core 2) |
| **Giai đoạn** | Week 4 (06–15/11/2026) — Chuẩn bị Demo MVP |
| **Bản tham chiếu UI** | [`docs/ui-walkthrough/PREVIEW.html`](../ui-walkthrough/PREVIEW.html) (Màn hình `S06 · Duyệt` & `S05 · Cấu hình`) |
| **Hợp đồng & Tài liệu cơ sở** | `docs/tasks/W4_TASK_DETAIL.md`, `docs/tasks/W4_ASSIGNMENT.md`, `docs/api/review-rpc-contract.md`, [Issue #45](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/45), [Issue #46](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/46) |
| **Trạng thái** | ✅ **Ready for review — Đã hoàn thành 100% mã nguồn và kiểm thử** |

---

## 1. Bối cảnh & Phạm vi thực hiện

Week 4 tập trung hoàn thiện trải nghiệm thẩm định đề thi đẳng cấu phục vụ buổi Demo MVP ngày 15/11. Nhiệm vụ **`W4-MVP-04`** bao gồm hai trọng tâm:

1. **Đồng bộ Stage 2 Config UI (Issue #45):**
   - Đưa hai tùy chọn xáo trộn (`shuffle_questions` và `shuffle_options`) về giá trị mặc định tắt (`false`/`false`), hỗ trợ độc lập 4 tổ hợp cấu hình.
   - Ẩn hoàn toàn thao tác chọn `variation_modes` thủ công của giáo viên; thay bằng các informative badges hiển thị năng lực phân tích tự động từ Blueprint kèm lý do không khả dụng. Ghi rõ: *"Hệ thống tự động phân tích và áp dụng các chế độ biến thể toán học tối ưu từ Blueprint đề nguồn đã xác nhận (theo quy ước Issue #45)"*.
   - Chuẩn hóa payload lưu cấu hình luôn gửi `active_variation_modes: []` để backend tự suy diễn theo canonical Blueprint.

2. **Triển khai Giao diện Duyệt biến thể Stage 3 (W4-MVP-04):**
   - Thiết kế giao diện tuân thủ 100% bản mô phỏng trực quan [`docs/ui-walkthrough/PREVIEW.html`](../ui-walkthrough/PREVIEW.html) (Màn hình S06).
   - **Nút "Kiểm tra đáp án":** Đặt trên từng câu hỏi biến thể, mở modal đối chiếu `solution-dialog`.
   - **Modal `SolutionDialog` (`.solution-dialog`):**
     - Cột 1: Câu hỏi biến thể và 4 phương án A, B, C, D (render bằng `MathRenderer`).
     - Cột 2: Lời giải chi tiết KaTeX (`variant.solution_md`) và làm nổi bật đáp án đúng.
     - **Chỉ có đúng 2 nút hành động ở footer:**
       1. **"Tạo lại" (`data-review-regenerate`):** Tự động gửi request từ chối & kích hoạt AI sinh lại biến thể mới (Targeted Regeneration) ngoài DB transaction. Hiển thị trạng thái *"Đang tạo lại…"*; khi hoàn tất **giữ nguyên modal mở** và nạp ngay câu mới tạo để giáo viên tiếp tục thẩm định.
       2. **"Duyệt biến thể" (`data-review-approve`):** Gửi request phê duyệt; chuyển trạng thái thành *"Đã duyệt"* và tăng số lượng câu duyệt ở thanh tiến độ.
     - **Không có nút Hoàn nguyên (Revert)** và **không có modal nhập lý do từ chối**.
   - **Badge Fallback chuẩn (Issue #46):** Khi AI sinh lỗi sau 4 lượt và hệ thống giữ nguyên câu hỏi gốc, hiển thị chính xác chuỗi:
     > **"Không tạo được biến thể hợp lệ; đã giữ nguyên câu hỏi gốc"**
   - **Thanh trạng thái cố định ở dưới cùng (Bottom Sticky Bar):**
     - Hiển thị tiến độ: `Đã duyệt X/Y câu`.
     - Nút chính **"Rà bộ đề"** (`data-review-finalize`) đặt ngay kế bên tiến độ duyệt, có icon mũi tên `ArrowRight`.
     - Nút "Rà bộ đề" bị vô hiệu hóa khi chưa duyệt đủ 100% câu hỏi; tự động kích hoạt (enabled) khi `approvedCount === totalExpectedSlots`, bấm vào sẽ điều hướng sang bước Rà soát & Chốt bộ đề (`/session/:id/stage3/preview` — S07).

---

## 2. Danh mục File thay đổi & Chức năng

| File | Loại thay đổi | Mô tả chi tiết |
|---|---|---|
| `frontend/src/features/stage2-config/Stage2ConfigCard.jsx` | Sửa đổi | Cập nhật mặc định 2 cờ xáo trộn thành `false`; chuyển danh sách variation modes thành informative badges; gửi `active_variation_modes: []` theo Issue #45. |
| `frontend/src/features/stage2-config/Stage2Config.test.js` | Sửa đổi | Cập nhật 14 unit tests khớp với cờ xáo trộn mặc định tắt và các informative badges (14/14 pass). |
| `frontend/src/services/stage3Service.js` | Tạo mới | Cung cấp các hàm gọi API: `acceptQuestion`, `rejectAndRegenerateQuestion`, `fetchReviewProgress` chuẩn hóa qua axios `api` client. |
| `frontend/src/services/stage3Service.test.js` | Tạo mới | Unit test kiểm thử việc gọi đúng endpoint, method và header `Idempotency-Key` (3/3 pass). |
| `frontend/src/features/stage3-review/Stage3ReviewPage.jsx` | Sửa đổi | Triển khai modal `SolutionDialog`, 2 nút Tạo lại / Duyệt biến thể, badge fallback chuẩn, và thanh bottom bar với nút "Rà bộ đề". |
| `frontend/src/features/stage3-review/Stage3Review.test.js` | Sửa đổi | Bổ sung các kịch bản kiểm thử mới cho dialog, duyệt, tạo lại inline, badge fallback, F01 reset version tab và F02 chặn solution fallback cũ (18/18 pass). |
| `frontend/src/features/stage2-config/Stage2ConfigPage.jsx` | Sửa đổi | Bổ sung màn hình Recovery View khi phiên sinh đề bị `failed`, hiển thị `generation_error_code` và nút Thử lại tiến trình sinh đề (`retryGeneration`). |
| `frontend/src/features/stage2-config/Stage2ConfigPage.test.js` | Sửa đổi | Bổ sung unit tests cho Recovery View khi phiên `failed` và nhận mã lỗi từ `fetchGenerationSnapshot` (25/25 pass). |
| `frontend/src/services/stage2Service.js` | Sửa đổi | Bảo toàn `generation_error_code` từ session detail và `fetchGenerationSnapshot`, fallback shuffle về `false/false` khi thiếu dữ liệu. |
| `docs/tasks/W4_TASK_MVP_04_PLAN.md` | Tạo mới | Kế hoạch chi tiết và tài liệu bàn giao M2/M3. |

---

## 3. Bằng chứng kiểm thử tự động (How Tested)

```bash
# 1. Chạy toàn bộ kiểm thử Unit & Integration Frontend
export PATH="$HOME/.temp-node/bin:$PATH" && cd frontend && npm test

# Kết quả:
# ✔ 384 tests passed
# ℹ tests 384
# ℹ suites 0
# ℹ pass 384
# ℹ fail 0
# ℹ duration_ms 12253.3035
# ℹ pass 372
# ℹ fail 0
# ℹ duration_ms 12234.988292

# 2. Kiểm tra Production Build
export PATH="$HOME/.temp-node/bin:$PATH" && cd frontend && npm run build

# Kết quả:
# ✓ 1910 modules transformed.
# dist/index.html                   0.71 kB │ gzip:   0.43 kB
# dist/assets/index-86rfLLPI.css   58.38 kB │ gzip:  13.98 kB
# dist/assets/index-CJWiqILJ.js   768.34 kB │ gzip: 237.10 kB
# ✓ built in 1.31s
```

---

## 4. Handoff & Kế hoạch tích hợp tiếp theo

- **Bàn giao cho:**
  - **Duy (`@johannguyen015` — Leader / Backend):** Review tính tương thích với endpoint `POST /questions/{id}/accept`, `POST /questions/{id}/reject` và GET review snapshot/progress.
  - **Philip (`@philip-kkk` — W4-MVP-10 / Stage 1-2-3 Route Foundation):** Sẵn sàng tích hợp luồng điều hướng mượt mà giữa Stage 2 -> Stage 3 Review -> Stage 3 Finalize Preview (`/session/:id/stage3/preview`).
  - **Tâm (`@tam-w4-mvp-05` / W4-MVP-06):** Điểm nối nút "Rà bộ đề" kích hoạt bước Preview xáo trộn.
