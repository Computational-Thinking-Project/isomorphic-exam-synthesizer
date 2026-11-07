# W4 staging và demo runbook — bản chuẩn bị

Owner chuẩn bị: Đạt; trạng thái 07/11/2026: tài liệu kiểm tĩnh, chưa có staging URL/deployment proof. [Plan và input owners](tasks/TASK-W4-OPS.md). [Docker setup](setup-docker.md) là hướng dẫn kỹ thuật hiện hành; runbook này bổ sung trình tự nghiệm thu W4, không tự đổi contract sản phẩm.

[Handoff lifecycle/version](w4-ops-handoff.md) có phương án cụ thể cho Duy/Quỳnh chốt; [migration inventory](w4-migration-inventory.md) chỉ giúp đối chiếu checksum, chưa cấp phép thực thi SQL.

## 1. Inventory không chứa giá trị bí mật

| Nhóm | Tên biến/cấu hình đã có | Người phối hợp / cách dùng |
|---|---|---|
| Backend Supabase | SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY | Duy bàn giao project/permissions; service-role chỉ backend |
| Browser Supabase | VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY | Philip + Duy; public build args, phải rebuild frontend khi đổi |
| Gemini | GEMINI_API_KEY, GEMINI_API_KEY_1..3, GEMINI_MODEL, GEMINI_MAX_CONCURRENCY, GEMINI_REQUEST_TIMEOUT_SECONDS, GEMINI_KEY_COOLDOWN_SECONDS | AI/Quỳnh xác nhận model/quota; multi-key không thay session quota; giá trị chỉ ở backend |
| App/Auth | ENVIRONMENT, ADMIN_EMAILS, CORS_ORIGINS, MAX_UPLOAD_SIZE_MB, LOG_LEVEL | Duy/OPS giữ allowlist; ADMIN_EMAILS có trong Settings, operator phải thêm nếu cần; không dùng development để vượt admin gate staging |
| Docker | COMPOSE_PROJECT_NAME, FRONTEND_PORT, BACKEND_PORT | Unique project/ports; hiện bind127.0.0.1; external ingress/TLS chưa cấu hình |
| Export | Typst trong backend image; bucket/private policy và env Storage chưa bàn giao | Hùng cung cấp contract/tên biến; không đặt tên hoặc cấp quyền rộng theo phỏng đoán |
| OAuth/TLS | Browser origin, Supabase redirect allowlist, Google OAuth callback, domain/certificate | Duy/Philip/OPS xác nhận exact URLs; không tự thay cloud |

Không commit/env-dump, không lưu JWT, signed URL còn hiệu lực hay secret vào evidence. Public browser key không phải service-role/Gemini key. Root `.env` đã ignored; script setup chỉ tạo nếu chưa có. Không đọc/ghi đè env hiện hữu để chạy thử.

## 2. Chuẩn bị clean checkout và chạy local

Operator có Git, Docker Linux engine và Compose>=2.24.4; kiểm prereqs theo setup-docker. Chọn approved candidate SHA từ Duy; ghi SHA trước khi build. Checkout dưới đây phải là checkout riêng sạch, không dùng nó để xóa thay đổi của người khác.

```powershell
git clone https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer.git exam-w4
Set-Location exam-w4
git fetch origin dev
# Thay bằng SHA đã được Duy bàn giao; không checkout placeholder.
git checkout --detach <APPROVED_CANDIDATE_SHA>
git rev-parse HEAD
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 doctor
```

Operator điền env qua kênh cấu hình được cấp, đối chiếu inventory. Không paste giá trị vào PR. `setup` với cloud values rỗng chỉ kiểm local/mock, không đủ live acceptance.

```powershell
docker compose config --quiet
.\scripts\dev.ps1 up -NoWatch
.\scripts\dev.ps1 test
.\scripts\dev.ps1 smoke
.\scripts\dev.ps1 down
```

Đây là dev workflow hiện có. Trước protected metrics merge, smoke mong metrics200; sau route bảo vệ phải có patch smoke401/Bearer tương ứng từ Quỳnh/OPS. Không chạy dev helper lẫn static stack cùng project/port.

Static candidate phục vụ build/demo nội bộ:

```powershell
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 120
docker compose exec -T backend typst --version
```

Hiện frontend http://localhost:3000, backend http://localhost:8000; thay theo port thực tế. HTTPS public staging cần topology/access được duyệt và TLS ingress riêng; các lệnh này không tự cung cấp HTTPS. Một Uvicorn worker theo image hiện có; không tự scale khi SSE/tickets còn in-memory.

## 3. DB, Auth, deploy và recovery

1. Nhận migration manifest/compatible SHA từ Duy, proof fresh+upgrade, test project và người có quyền chạy. Không chạy tất cả SQL theo tên file trên shared DB khi chưa biết ledger.
2. Người được cấp quyền áp manifest trên isolated DB, ghi IDs/checksums/kết quả, xác minh config/claim/persist/resume/finish theo backend tests. Không publish raw DB dump.
3. Cấu hình cùng Supabase project cho backend/browser; kiểm login Google thật, callback và browser refresh trên URL đã duyệt. Duy quản lý cấp/revoke ADMIN_EMAILS; ghi thời điểm restart/redeploy cần để áp config mới.
4. Build/deploy đúng SHA, ghi images/config fingerprint không lộ secrets, DB ledger, model/prompt version. Khi env đổi, recreate backend/rebuild browser theo thay đổi; restart đơn thuần không áp Compose env mới.
5. Smoke trước và sau restart. Job cũ phải được fenced, target đã commit không sinh lại, quota không reset. Policy stale scanner/retention/interrupt code còn cần Duy+Quỳnh chốt; không nhận PASS từ health200.
6. Rollback app về candidate trước chỉ sau kiểm tương thích schema. DB rollback/restore hoặc forward-fix do Duy/Hùng có quyền thực hiện; không dùng down -v, prune hay restore phá dữ liệu để che lỗi.
7. Kết thúc test riêng: `docker compose down` đúng project; không xóa volumes/bucket hay môi trường dùng chung.

## 4. Checklist smoke và owner nhận lỗi

| Kiểm | Kỳ vọng / bằng chứng cần ghi | Owner lỗi |
|---|---|---|
| Health/container | backend /health200, frontend HTTP200, Typst version; chưa chứng minh cloud | Đạt/module owner |
| SPA/OAuth | /login và deep link F5 không404; login/logout/callback thật | Philip + Duy |
| Metrics sau patch207c | Anonymous401 + WWW-Authenticate Bearer qua proxy; authenticated non-admin ngoài development403; admin200/no-store; collector lỗi503 | Quỳnh + Duy |
| Ownership | UserB không đọc/ghi sessionA hoặc xin signed link choA; dùng mã theo endpoint contract | Duy + Hùng |
| Generation | Source confirmed trước Blueprint ready; N=2 ×3 sources, modes theo contract được chốt; persist trước progress; retry giữ committed slots/quota | Quỳnh + Duy |
| SSE/recovery | F5/reconnect/history-loss nhận đúng snapshot/cursor; restart không mất committed results | Quỳnh + Philip |
| Review/lock | Accept/Reject/targeted regenerate/Revert đúng current record; approved lock423, premature export bị chặn | Duy + Tâm + FE |
| Export/Storage | ZIP PDF/TeX/MD/key/solution thật, private bucket, issuance authorized, expiry/reissue theo contract; 6/6 key/solution mapping | Hùng + Philip |

## 5. Kịch bản demo8 bước và evidence

Golden input cần Quỳnh/Tâm/Duy bàn giao: Markdown3 câu đủ key/solution có quyền dùng, N=2, shuffle OFF/OFF; đây chưa phải fixture đã có. Không đổi prompt để tối ưu sát demo. Flow modes/fallback W4 theo Q03/#45/#46 cần owner chốt và code tương thích, không giả W2 đã có W4 behavior.

1. Login, tạo/mở session, import Golden Markdown.
2. Preview và xác nhận đề nguồn, chờ canonical Blueprint ready.
3. Cấu hình N=2, kiểm shuffle defaults OFF/OFF.
4. Generate, theo dõi SSE và kết quả6 slots; thử resume ở ca riêng.
5. Review Accept/Reject/Regenerate/Revert; dùng slot/phiên riêng nếu thao tác xung đột, ghi rõ.
6. Shuffle/preview đúng projection đã chốt; refresh không đổi mapping.
7. Final approval, xác minh lock, export/download ZIP thật và đối chiếu6/6 đáp án/lời giải.
8. Reload/mở lại phiên, kiểm locked/export/resume đúng state.

Fallback4attempts có targeted test riêng nếu không xuất hiện Golden; chưa kiểm thì ghi unverified. Không dùng fake provider thay live Golden.

Mỗi lần chạy copy mẫu này vào nơi evidence được Duy chốt; không commit báo cáo PASS trống:

```text
Gate: G0 preflight | G0 live | G1 | G2-Demo
Time (+07):
Operator / reviewer:
Result: PASS | FAIL | BLOCKED
Deployed SHA / image IDs:
Config revision (no values) / DB ledger / prompt+model version:
Staging URL (no bearer token):
Golden fixture+oracle version / N / ordering:
8 steps actual results:
6-slot key+solution comparison:
Targeted fallback/restart/security tests and limits:
ZIP checksum / sanitized logs+recording location:
Blockers / module owner / next action:
Acceptance: Duy, actual date/link or NOT ACCEPTED
```

Mốc nguồn W4: script12/11, first attempt13/11, candidate14/11 13:00, security15:00, G1 18:00, freeze19:00; G2 live15/11 16:00 và handoff19:00. Availability chưa tự xác nhận. Thay SHA/config/migration/prompt sau freeze cần rerun bị ảnh hưởng. G2 thất bại vẫn ghi FAIL dù G1 từng PASS.
