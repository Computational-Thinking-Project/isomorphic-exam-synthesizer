# OPS11/21 — Kiểm Docker local ngày 15/11/2026

Owner: Trương Thành Đạt. Author mode, workflow v0.1 proposed. Đây là kết quả local, chưa là G0 live/G1/G2 hoặc nghiệm thu của Duy.

## Bản đã chạy

- Source `dev@c2ee9fd0a9da8795a3e1833584f8abfcd3120c51`, lấy bằng Git archive sạch; không đưa file untracked vào image.
- Windows Docker Desktop, Linux engine, Compose 5.6.1. Project riêng `dat-w4-c2ee9fd`; static Compose, backend18000/frontend13000 bind loopback.
- Env lấy từ `.env.example`, chỉ thêm hai ports; không đọc/copy env thật, không cấp cloud credentials, không gọi Gemini hoặc sửa DB/Storage.
- Backend image `sha256:905109539364f6dc7720bdc235dd3615d732e61a67bbf97cd77524a547c4631b`.
- Frontend image `sha256:d315caa3f912c7b1d418f6de932bf4aa3944ce6f14aa9d137378149e2589a557`.

## Bằng chứng đã kiểm

| Kiểm | Kết quả |
|---|---|
| Compose config quiet; build static; up --wait | PASS; cả hai containers healthy |
| Backend /health | PASS, HTTP200, status healthy |
| Frontend HTML; /login deep link | PASS, HTTP200 và HTML |
| OpenAPI qua frontend proxy | PASS, schema có GET /health và /api/sessions |
| Anonymous /api/sessions trực tiếp và qua proxy | PASS, cả hai HTTP401 kèm WWW-Authenticate Bearer |
| Anonymous /api/health/metrics trực tiếp và qua proxy | PASS, cả hai HTTP401 kèm WWW-Authenticate Bearer |
| Typst trong backend | 0.11.1 (786457e3) |
| Bộ kiểm scripts/test_w4_ops.py | 6 passed, 6 subtests passed |

### Bổ sung script smoke và kiểm restart local

Đã đưa4 phép kiểm anonymous auth vào `scripts/w4_ops.py smoke` để dùng lại, nâng tổng số lên8 checks. Bộ kiểm sau thay đổi:9 passed,14 subtests passed; Ruff PASS. Chạy script mới trên đúng runtime Docker nêu trên:8/8PASS. Evidence local: `smoke-auth-automated.json` và `smoke-after-restart.json` trong cùng thư mục ignored.

Đã restart riêng backend test rồi chờ cả hai containers healthy và chạy lại8 checks. Đây chỉ là phục hồi process/health/proxy không có job/DB thật; không chứng minh durable recovery hoặc giữ quota/committed slots. Stack test được dừng đúng project sau kiểm, ứng dụng Docker đang có giữ nguyên.

Evidence máy Đạt (ignored, chưa là artifact nhóm đã nhận): `.artifacts/w4-ops-c2ee9fd/smoke.json` và `anonymous.json`. Smoke script ghi checkout tài liệu riêng với deployed SHA được operator truyền vào; không đồng nhất hai SHA này.

Build Vite có cảnh báo JS chunk lớn hơn500kB; build vẫn thành công. Chưa có phép đo hiệu năng browser nên không nhận là lỗi chức năng. Không chạy lại full product suite trong lượt OPS này.

## Phần chưa thể nghiệm thu

- PR67@48b9fd7 đã được Đạt Approve sau404 tests; PR63@f74e34c đã được kiểm268 tests và2 probes SQL kết hợp. Đây là kiểm riêng các PR, không có trong runtime dev này.
- Candidate SQL019→020→021→022 đã bàn giao tại [PR63](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/63#issuecomment-6888228616). Candidate inventory không là approved/applied ledger. Chờ Duy/DB owner xác nhận ledger, đường upgrade/backfill020 nếu021 đã áp, backend tương thích và phạm vi test.
- PR63 còn Draft; cần private bucket/ACL thực tế, MIME/size limits, quyền test và budget timeout/worker/stop-grace/proxy; không tự bật runtime export.
- OAuth, ownership A/B, PostgREST, Gemini, SSE/restart, review/lock và ZIP6 slots chưa kiểm trong lượt này. Thiếu Golden/oracle/quyền test thì giữ BLOCKED cho diễn tập tích hợp, không thay bằng dữ liệu tự tạo để nhận nghiệm thu.
- Đạt chạy [script8 bước](w4-demo-rehearsal.md) khi candidate và các input tại [plan OPS](tasks/TASK-W4-OPS.md#input-handoff) đủ; dùng local trên máy thuyết trình theo phạm vi đã giao, không tự mở host HTTPS cho nhóm.

Không phát hiện lỗi thuộc OPS cần sửa code qua các phép kiểm đã chạy. Chưa nhận task tuần hoàn tất; còn integrated smoke và bàn giao evidence/acceptance.
