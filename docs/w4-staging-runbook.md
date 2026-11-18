# W4 production private beta và demo runbook — bản chuẩn bị

## Checkpoint 13/11 và phạm vi chạy tiếp

Base đã build/kiểm local: `dev@294c69a1a085ac6487d65b633e06a2f1112e2046` (PR51 + PR52 merged). Git archive sạch, static Compose project riêng, env mẫu rỗng, ports13000/18000: build/health/preflight/smoke PASS; anonymous sessions401 trực tiếp/proxy; Typst0.11.1; stack test đã dừng. Không dùng env/DB thật, không thay stack của thành viên khác. Evidence và image IDs tại [checkpoint task](tasks/TASK-W4-OPS.md).

Trước lần integrated smoke tiếp theo, nhận DB0 manifest/applied ledger + compatible candidate SHA, identities/quyền I-OPS-DB, worker #30 và export/Storage Q09/Q10. 017 đã merge; 018 đã merged vào dev21887c1; 019 ở PR61@9fda6fd đã Approve, F01/F02 verified, đã merged vào devb47e4fa; DB-applied UNVERIFIED. Đọc [migration checkpoint/hashes](w4-migration-candidate.md); không áp tất cả PR heads lên DB nhóm để lấp dependency. Chuẩn bị script/phiếu chạy tại [demo rehearsal](w4-demo-rehearsal.md); Q14 Golden/oracle và Q20 nơi lưu proof còn theo bảng input chuẩn.

G0 preflight11/11 và G0 integrated12/11 18:00 là mốc nguồn W4; chưa có proof thật thì ghi BLOCKED, không chuyển health PASS thành nghiệm thu. Việc review/push docs không thay quyền cloud, team access hoặc chốt lại topology #53. Những nhận định ghi base/ngày cũ phía dưới là lịch sử cần đối chiếu checkpoint này.

Owner chuẩn bị: Đạt; trạng thái 07/11/2026: tài liệu kiểm tĩnh, chưa có production private beta URL/deployment proof. [Plan và input owners](tasks/TASK-W4-OPS.md). [Docker setup](setup-docker.md) là hướng dẫn kỹ thuật hiện hành; runbook này bổ sung trình tự nghiệm thu W4, không tự đổi contract sản phẩm.

[Handoff lifecycle/version](w4-ops-handoff.md) có phương án cụ thể cho Duy/Quỳnh chốt; [migration inventory](w4-migration-inventory.md) chỉ giúp đối chiếu checksum, chưa cấp phép thực thi SQL.

## 1. Inventory không chứa giá trị bí mật

| Nhóm | Tên biến/cấu hình đã có | Người phối hợp / cách dùng |
|---|---|---|
| Backend Supabase | SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY | Duy bàn giao project/permissions; service-role chỉ backend |
| Browser Supabase | VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY | Philip + Duy; public build args, phải rebuild frontend khi đổi |
| Gemini | GEMINI_API_KEY, GEMINI_API_KEY_1..3, GEMINI_MODEL, GEMINI_MAX_CONCURRENCY, GEMINI_REQUEST_TIMEOUT_SECONDS, GEMINI_KEY_COOLDOWN_SECONDS | AI/Quỳnh xác nhận model/quota; multi-key không thay session quota; giá trị chỉ ở backend |
| App/Auth | ENVIRONMENT, ADMIN_EMAILS, CORS_ORIGINS, MAX_UPLOAD_SIZE_MB, LOG_LEVEL | Duy/OPS giữ allowlist; ADMIN_EMAILS có trong Settings, operator phải thêm nếu cần; không dùng development để vượt admin gate production private beta |
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

Hiện frontend http://localhost:3000, backend http://localhost:8000; thay theo port thực tế. HTTPS public production private beta cần topology/access được duyệt và TLS ingress riêng; các lệnh này không tự cung cấp HTTPS. Một Uvicorn worker theo image hiện có; không tự scale khi SSE/tickets còn in-memory.

## 3. DB, Auth, deploy và recovery — Quy trình Vận hành Chi tiết (Operator Only)

> [!IMPORTANT]
> **Giới hạn Thẩm quyền:** PR này và các tác vụ chuẩn bị kỹ thuật **KHÔNG THỰC HIỆN** bất kỳ thao tác DDL/migration nào trên database Supabase chia sẻ. Thao tác trên môi trường chia sẻ chỉ được tiến hành sau khi hoàn thành đầy đủ các cổng kiểm soát (Gates) dưới đây.

### 3.1. Trước khi Triển khai (Pre-deployment Gates)
1. **Xác nhận Target Environment & Commit:**
   - Supabase project URL và database alias chính xác.
   - Backend runtime commit SHA khớp với candidate đã kiểm thử.
2. **Đối chiếu Ledger & DDL mục tiêu:**
   - Đối chiếu danh sách bảng, cột, constraints, enums, triggers và migration ledger thực tế trên target DB để xác nhận baseline 5 bảng tương thích.
3. **Phê duyệt Manifest & Checksums:**
   - Đối chiếu 19 bước tuần tự đề xuất trong manifest (`003b` ➔ `004`–`022`, bỏ qua `010` rỗng) cùng các mã băm SHA-256 Git blob tương ứng.
4. **Backup & Phục hồi Độc lập (Mandatory GO/NO-GO Gate):**
   - DB owner (Duy / Hùng) thực hiện backup/snapshot đầy đủ trên dashboard Supabase (PITR / pg_dump).
   - Xác nhận reference backup, người phụ trách và đã kiểm tra phục hồi (restore verification) trên một DB cô lập.
5. **Điều phối Vận hành & Phê duyệt:**
   - Thông báo cửa sổ bảo trì (maintenance window).
   - Nhận phê duyệt chính thức (GO decision) từ DB owner (Duy / Hùng).

### 3.2. Trong khi Triển khai (Execution Sequence)
1. **Kiểm tra Checksum:** Operator kiểm tra tính toàn vẹn của từng file SQL trước khi nạp.
2. **Thực thi Tuần tự:**
   - Áp dụng `003b_reconcile_baseline.sql` để thiết lập các bảng, enum, policy owner-read và quyền tối thiểu.
   - Lần lượt áp dụng chuỗi `004` đến `022`, sau đó `023` (bỏ qua `010` rỗng; không áp dụng `020` chưa merge).
   - Ghi lại nhật ký thực thi: thời gian UTC, người chạy, kết quả từng bước (SUCCESS/FAILURE). Dừng ngay lập tức nếu có bước lỗi.
3. **Tải lại Cache Schema PostgREST:**
   - Sau khi các migrations hoàn tất thành công, bắt buộc thực thi lệnh reload cache trên Supabase:
     ```sql
     NOTIFY pgrst, 'reload schema';
     ```
   - *Lưu ý:* `reload schema` chỉ cập nhật cache của các RPC/bảng đã tồn tại, không thể tự tạo ra các RPC bị thiếu.

### 3.3. Sau khi Triển khai (Post-deployment Smoke & Receipt)
Operator thực hiện kiểm tra và lập Deployment Receipt (tuyệt đối không lưu secret, JWT hay dữ liệu bài thi thật vào báo cáo):
- **S01 RPC:** Kiểm tra `to_regprocedure('public.get_session_source_preview(uuid)') IS NOT NULL`, cùng các RPC `save_generation_config`, `confirm_source_artifacts`, `get_review_current_snapshot`.
- **S02 Session API:** Chủ sở hữu gọi `GET /api/sessions/{sessionId}` trả về 200 OK với `source_revision` và `source_questions`; không còn lỗi HTTP 503 (`PGRST202`).
- **S03 Giao diện Web:** Truy cập `/session/{sessionId}/stage1` tải bình thường và hiển thị đúng sau khi F5.
- **S04 Xác nhận Đề nguồn:** Kiểm tra luồng xác nhận nguồn (`confirm_source_artifacts`) trên session thử nghiệm.
- **S05 Phân lập Tài khoản:** Xác minh User B không thể truy cập session hoặc configuration của User A (HTTP 403/404).
- **S06 Khôi phục Tiến trình:** Scanner phục hồi thế hệ (`list_stale_generation_jobs`) hoạt động đúng quyền `service_role`.
- **S07 Biên bản Bàn giao (Deployment Receipt):** Lưu trữ mã SHA ứng dụng, checksums SQL đã chạy, reference backup, thời gian áp dụng, và kết quả các bước smoke S01–S06.

## 4. Checklist smoke và owner nhận lỗi

### Kiểm local tự động, không dùng token

Sau khi stack sẵn sàng, chạy từ root checkout:

```powershell
python scripts/w4_ops.py smoke --backend http://localhost:8000 --frontend http://localhost:3000 --deployed-sha <FULL_RUNTIME_SHA> --output <NEW_REPORT_PATH.json>
```

Thay placeholders bằng SHA runtime thực và file báo cáo chưa tồn tại; đổi ports nếu dùng stack riêng. Script kiểm8 ca: health, frontend HTML, SPA/login, OpenAPI qua proxy, và anonymous session/metrics qua cả backend lẫn proxy. Bốn ca auth chỉ PASS khi HTTP401 có Bearer challenge; HTTP200/403 hoặc redirect đều FAIL. Không gửi token, không lưu body/headers hay theo redirect. `integrated_acceptance` vẫn `NOT_VERIFIED`; kiểm này không thay đăng nhập/ownership/job restart/Golden/Storage.

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

[Script thao tác, điều kiện diễn tập và phiếu6 slots](w4-demo-rehearsal.md) dùng khi chuẩn bị W4-MVP-21; các mẫu đều chưa chạy nghiệm thu.

Golden input cần Quỳnh/Tâm/Duy bàn giao: Markdown3 câu đủ key/solution có quyền dùng, N=2, shuffle OFF/OFF; đây chưa phải fixture đã có. Không đổi prompt để tối ưu sát demo. Flow modes/fallback W4 theo Q03/#45/#46 cần owner chốt và code tương thích, không giả W2 đã có W4 behavior.

Chạy trên staging/test đã được cấp quyền với candidate SHA đã xác minh, DB ledger tương thích, Gemini, Typst và private Storage hoạt động. Kiểm cấu hình theo [private export contract](api/private-export-contract.md#runtime-opt-in-and-io-lifecycle). Nếu thiếu quyền, fixture/oracle hoặc môi trường, ghi `BLOCKED` cùng bước chưa chạy.

Thao tác qua UI và dùng API dưới đây để đối chiếu hoặc replay có kiểm soát. Tất cả path bắt đầu từ `/api/sessions`; `/{id}` là UUID phiên. Dùng Bearer access token của người dùng sở hữu phiên cho API, trừ kết nối SSE dùng ticket và tải file dùng URL ký.

1. **Tạo và nạp nguồn.** `POST /api/sessions` với JSON `{"title":"Golden E2E","subject":"Toán","grade":12}` trả 201 và `id`. Gửi Markdown qua `POST /{id}/ingest-file` dạng multipart với field `file`, hoặc dán nội dung qua `POST /{id}/ingest-text` với JSON `{"raw_text":"<nội dung Golden>"}`. Kiểm HTTP 200, `total_questions: 3`. `GET /{id}` lấy `source_revision` của bản đã lưu và đối chiếu đủ ba `source_questions` với oracle.
2. **Xác nhận và chờ Blueprint.** Sinh UUID mới cho lần xác nhận này. Gửi `POST /{id}/confirm-source` với header `Idempotency-Key: <UUID>` và JSON `{"source_revision":"<UUID từ GET>"}`. Kiểm HTTP 200, `status: "blueprinted"` và `confirmation_id` khớp key. Nếu mất response, đọc lại phiên trước khi quyết định retry; dùng lại đúng key và revision khi replay cùng lần xác nhận. Nếu revision đổi, đọc và kiểm bản nguồn mới trước khi xác nhận. Poll `GET /{id}/source-artifacts` đến khi `canonical_status: "ready"`, `ready: true`, `completed_count: 3` và `total_questions: 3`. Nếu `pending` hoặc `running`, tiếp tục đọc với khoảng nghỉ và hạn chờ đã định cho run. Nếu `failed`, ghi lỗi và dùng `POST /{id}/source-artifacts/retry` khi đủ điều kiện. Khi kết quả POST chưa rõ, tiếp tục kiểm qua GET trong cửa sổ polling trước lần retry khác.
3. **Cấu hình generation.** Gửi `POST /{id}/config` với JSON dưới đây. Kiểm HTTP 200, `status: "configured"` và `config.n_versions: 2`. [Schema request](../backend/app/models/generation_config.py).

   ```json
   {
     "n_versions": 2,
     "active_variation_modes": [],
     "ordering_preferences": {
       "shuffle_questions": false,
       "shuffle_options": false
     }
   }
   ```

4. **Sinh đề.** Gửi `POST /{id}/generate` với body rỗng. HTTP 202 và `status: "generating"` xác nhận đã tiếp nhận. UI theo dõi SSE. Để replay API, lấy ticket qua `POST /{id}/events/ticket`, sau đó mở `GET /{id}/events?ticket=<ticket>`. Khi reconnect cần ticket mới. Đối chiếu kết quả lưu qua `GET /{id}/generation-snapshot` và `GET /{id}/review/snapshot`. Chờ đủ 6 slot. Ghi lỗi nếu run kết thúc partial/failed hoặc hết hạn chờ. [Generation và SSE](api/generation-job-endpoints.md).
5. **Duyệt ứng viên hiện hành.** Đọc JSON thô từ `GET /{id}/review/snapshot`, lấy từng UUID tại `versions[].slots[].candidate.candidate_id` và kiểm câu, phương án, đáp án, lời giải. Dừng bước duyệt nếu thiếu ứng viên hoặc UUID ở bất kỳ slot nào. Với từng ứng viên đạt, gửi `POST /{id}/questions/{candidate_id}/accept` với body rỗng, kiểm HTTP 200 và `status: "approved"`. Đọc lại snapshot, đối chiếu đủ sáu UUID hiện hành và kiểm `progress.approved_slots: 6`, `progress.ready: true`, `session_status: "reviewed"`. Chạy Reject/Regenerate/Revert trên slot hoặc phiên riêng nếu ảnh hưởng baseline.
6. **Chốt thứ tự và kiểm preview.** `PATCH /{id}/ordering-preferences` với `{"shuffle_questions":false,"shuffle_options":false}`, rồi `POST /{id}/finalize/shuffle` với body rỗng, kể cả OFF/OFF. Đọc `GET /{id}/finalize/preview` và xác minh `is_finalized: true` cùng thứ tự, đáp án và lời giải của cả hai mã. Nếu POST đã xác nhận chốt nhưng GET lỗi, chỉ lặp lại GET (nút **Kiểm tra trạng thái** trên UI) và chờ preview hợp lệ trước khi phê duyệt. Nếu response POST bị mất, đọc preview để đối soát. Chỉ thử chốt lại khi GET xác nhận `ERR_SHUFFLE_REQUIRED` và đã đọc được cấu hình lưu. Chạy ON/ON trên phiên khác nếu cần.
7. **Khóa, export và tải.** `POST /{id}/finalize/approve` với body rỗng, kiểm HTTP 200, `status: "approved"` và `approved_at`. Gửi `POST /{id}/export` với body rỗng. HTTP 202 trả `state: "preparing"`; HTTP 200 có thể trả `state: "ready"`. Poll `GET /{id}/export` với hạn chờ; nếu `failed`, ghi `error_code`; nếu `ready`, lưu metadata `filename`, `size_bytes`, `sha256` làm receipt. Sau `ready`, gửi riêng `POST /{id}/export/download-url` với body rỗng để nhận `url`, `expires_at`, `expires_in`, `filename`. Tải ZIP trực tiếp qua URL ký, không gửi kèm Bearer token. Nếu URL hết hạn, xin URL mới qua cùng endpoint. Trên PowerShell dùng `(Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()` để so với `sha256` từ status và `(Get-Item -LiteralPath $zipPath).Length` để so với `size_bytes`. Dừng với FAIL nếu sai. Kiểm manifest, mở PDF/TeX/MD và đối chiếu đáp án, lời giải đủ 6/6 slot với preview, dữ liệu đã khóa và oracle. [Export/status/download contracts](api/private-export-contract.md).
8. **Resume.** Reload/mở lại phiên, kiểm đúng trạng thái khóa và export đã sẵn sàng. Ghi bằng chứng cho lần đọc lại và các ca phân quyền đã được phép.

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
Session alias / source revision / confirmation receipt / config ID:
Generation and review counts / finalized and approved receipts:
Export ledger receipt / filename / size / expected and downloaded ZIP SHA-256:
Sanitized logs+recording location:
Blockers / module owner / next action:
Acceptance: Duy, actual date/link or NOT ACCEPTED
```

Mốc nguồn W4: script12/11, first attempt13/11, candidate14/11 13:00, security15:00, G1 18:00, freeze19:00; G2 live15/11 16:00 và handoff19:00. Availability chưa tự xác nhận. Thay SHA/config/migration/prompt sau freeze cần rerun bị ảnh hưởng. G2 thất bại vẫn ghi FAIL dù G1 từng PASS.

## 6. Công cụ OPS read-only (11/21)

Chạy từ repo root với Python >=3.11 (hoặc `.venv/Scripts/python.exe`). Không tự deploy, chạy migration hay gọi Gemini. File output dùng đường dẫn mới mỗi lần; `.artifacts/` đã ignored.

```powershell
python scripts/w4_ops.py preflight --output .artifacts/w4/preflight-01.json
python scripts/w4_ops.py smoke --backend http://localhost:8000 --frontend http://localhost:3000 --output .artifacts/w4/smoke-01.json
# Có thể thêm --deployed-sha FULL_40_CHAR_SHA và --zip PATH_TO_EXPORTED_ZIP
python -m unittest discover -s scripts -p test_w4_ops.py
```

Exit 0 chỉ khi tất cả probes PASS; exit 1 khi FAIL/BLOCKED. Preflight không chứng nhận credential hợp lệ. `/openapi.json` qua frontend phải là JSON OpenAPI 3.x có GET `/health` và `/api/sessions`, từ chối SPA HTML hoặc schema thiếu routes; `/login` chỉ kiểm SPA fallback, không chứng nhận OAuth. Metrics/auth/ownership/SSE/Typst/export thật vẫn theo checklist mục4; không gửi token qua CLI. URL chỉ nhận origin không chứa credentials/query/fragment; HTTP redirects bị từ chối. Report không lưu URL, headers, body, command diagnostics hay ZIP contents. Kiểm checksum chỉ đọc artifact có sẵn và chưa đối chiếu 6 slots.

`checkout_sha` là máy chạy script, `operator_supplied_deployed_sha` phải được operator đối chiếu deployment thực; `integrated_acceptance` luôn NOT_VERIFIED. Lưu DB ledger/config/prompt/model, demo8 bước và oracle6 slots theo mẫu mục5; không thay bằng report HTTP. Mỗi HTTP probe timeout10s, mỗi subprocess timeout30s. Tool không khởi động Docker Desktop, không tạo/đổi `.env` và không overwrite evidence cũ.

## 7. Online production private beta — quyết định 08/11

[Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) là nguồn duy nhất chốt ENV0/roster. Không cần server staging riêng. Ngân sách mặc định0đ, audience chỉ nhóm được duyệt; chưa chọn host/provider/domain hoặc chấp nhận chi phí. Khi có phương án host, owner phải đối chiếu uptime/sleep/quota, Docker/static runtime, một worker, HTTPS/OAuth, SSE lâu dài và quyền restart; ngoại lệ trả phí cần Duy duyệt trước.

1. Trước deploy: Duy/Hùng giao approved manifest, real PostgreSQL fresh+upgrade/ACL proof, backend-compatible SHA, backup owner và thử restore cô lập. Giữ historical inventory73583d7; candidate017 ở file riêng. Không chạy destructive tests/migration experiments lên production DB; DB backup không tự bao gồm Storage binaries.
2. Operator được cấp quyền mới triển khai static Compose (không dev overlay/reload), giữ loopback binds/internal; ingress HTTPS/TLS dẫn đến frontend, backend8000 không public. Một replica; không tự scale. Stop grace phải bao phủ shutdown thật sau review/test, không tự nhận10s đủ từ tài liệu.
3. Duy/Auth/OPS chọn access control thực: ingress identity gate hoặc backend authorization allowlist theo principal Supabase đã xác thực. Tài khoản ngoài nhóm bị chặn trước business actions; kiểm ingress/API trực tiếp, A/B/admin/non-admin và revoke. Danh sách/số thành viên qua kênh an toàn, chưa có app-wide allowlist proof. Không dùng ADMIN_EMAILS thay quyền thành viên beta.
4. Philip/Duy/operator xác nhận exact HTTPS origin, Supabase Site URL/redirect allowlist, Google callback; kiểm login/logout/refresh/deep link end-to-end qua access gate. Không bỏ auth để callback chạy.
5. Giữ PR30 F02 và PR52 ACL/real-DB là blockers; deployment trước khi có proof không được công bố private beta ready hoặc cho người dùng thật vào.
6. Ghi DEPLOYED_PRIVATE_BETA riêng với URL không token, SHA/images, config/prompt/model, ledger, real service smoke, access-control proof và primary/backup. Sau đó chạy G0/G1/G2 cùng deployed candidate theo mục4/5; public release chỉ khi P0 security/reliability resolved và quyết định PUBLIC_GO rõ ràng. G2 PASS không tự đồng nghĩa mở public.

Merge docs/preflight PR51 chỉ hoàn tất preparation review, không chứng nhận các gate trên. Lịch W4 là target: 09/11 manifest,10/11 online khi đủ inputs,12/11 G0,14/11 G1,15/11 G2; ETA/availability do từng owner xác nhận. ENV0 hiện TOPOLOGY=DECIDED, HOST/DEPLOY_ACCESS/ROSTER=BLOCKED.

## PR76 remediation — F02 catalog handoff (15/11/2026)

F01/F03 code review may proceed independently; deployment remains **NO-GO**.
DB owner Duy/Hùng runs the following in the target project's SQL editor and
returns filtered metadata, project alias and capture time. Do not include keys,
JWTs, connection strings, user records or exam content. This transaction reads
catalogs only; it creates no RPC, table or permission. Review function definitions
for embedded sensitive constants before sharing.

```sql
BEGIN TRANSACTION READ ONLY;
SELECT current_database(), current_user, version(), now() AS captured_at;
SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname;
SELECT table_name, column_name, ordinal_position, data_type, udt_name,
       is_nullable, column_default, is_identity, is_generated
FROM information_schema.columns WHERE table_schema='public'
ORDER BY table_name, ordinal_position;
SELECT t.typname, e.enumlabel, e.enumsortorder
FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
JOIN pg_enum e ON e.enumtypid=t.oid WHERE n.nspname='public'
ORDER BY t.typname,e.enumsortorder;
SELECT c.relname, con.conname, con.contype, con.convalidated,
       pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' ORDER BY c.relname,con.conname;
SELECT tablename,indexname,indexdef FROM pg_indexes
WHERE schemaname='public' ORDER BY tablename,indexname;
SELECT n.nspname,c.relname,t.tgname,t.tgenabled,
       pg_get_triggerdef(t.oid) AS definition, p.oid::regprocedure AS function
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid
WHERE NOT t.tgisinternal AND (n.nspname='public' OR (n.nspname='auth' AND c.relname='users'))
ORDER BY n.nspname,c.relname,t.tgname;
SELECT p.oid::regprocedure, p.prosecdef,p.proconfig,p.proacl,
       pg_get_functiondef(p.oid) AS definition
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname='handle_new_user';
SELECT * FROM pg_policies WHERE schemaname='public' ORDER BY tablename,policyname;
SELECT grantor,grantee,table_name,privilege_type,is_grantable
FROM information_schema.table_privileges WHERE table_schema='public'
ORDER BY table_name,grantee,privilege_type;
SELECT grantee,table_name,column_name,privilege_type
FROM information_schema.column_privileges WHERE table_schema='public'
ORDER BY table_name,column_name,grantee;
SELECT nspname,nspacl FROM pg_namespace WHERE nspname IN ('public','auth');
SELECT rolname,rolsuper,rolinherit,rolbypassrls FROM pg_roles
WHERE rolname IN ('anon','authenticated','service_role');
SELECT parent.rolname AS granted_role,member.rolname AS member
FROM pg_auth_members m JOIN pg_roles parent ON parent.oid=m.roleid
JOIN pg_roles member ON member.oid=m.member;
SELECT defaclrole::regrole,defaclnamespace::regnamespace,defaclobjtype,defaclacl
FROM pg_default_acl;
SELECT to_regclass('supabase_migrations.schema_migrations') AS migration_ledger;
COMMIT;
```

If the ledger exists, separately export only its `version` and `name` columns
(after inspecting its columns); omit stored statements. If absent or inaccessible,
mark history **Unknown**, not "002–003 applied" inferred from function presence.
Catalog grants can be visibility-filtered: owner must use an account with enough
metadata visibility and record omissions explicitly.

Compare five baseline tables and all present affected objects with application
requirements. Check `configured`, enabled Auth-to-public user sync, owner INSERT
policy and column grants for session creation, owner-only reads and trusted-role
permissions. Classify each item Compatible / Missing / Incompatible / Unknown.
Unknown or incompatible required objects keep deployment NO-GO. Any confirmed
repair needs a minimal reviewed delta and representative rehearsal before deploy;
do not blanket-run schema.sql or remove extra production enum labels.

Before GO record backup reference, isolated restore proof, representative-copy
rehearsal, runtime SHA, Git-blob checksums, independent approval and DB-owner GO.
Stop on the first migration error and use the tested recovery procedure; record
each successful step rather than replaying the whole manifest blindly.

Add post-deployment smoke to S01–S07: test Google login/profile sync and session
creation with approved test identities; save Stage 2 to `configured`, reload the
same config, reject cross-user access, and verify trusted audit insertion. HTTP
session detail exposes `source_revision`; `source_content_revision` is the DB
column. Do not close F00 from local tests or code approval alone.

## Issue #75 — 023 operator supplement (not authorized to execute yet)

Use the 19-step candidate in w4-migration-candidate.md. Preserve all three gates:
G1 technical/catalog/data/runtime/checksum/rehearsal; G2 backup plus isolated
restore proof; G3 independent review plus approved manifest/operator and explicit
Duy/Hùng DB-owner GO. No Production DDL or data writes before all three pass.

### Additional read-only preflight (DB owner)
Capture project alias luorfxpmvczsuvulkfcx, Supabase branch main, capture time,
version() and current_setting('server_version_num'). Export the actual migration
ledger or mark Unknown. Inspect users relacl, column grants, effective privileges
for anon/authenticated, PUBLIC grants, role memberships (including pg_maintain
where available), owner and default ACL for the actual object creator.
Only query MAINTAIN on >=170000. Confirm authenticated SELECT and enabled RLS.
Default grants affect future objects; they do not repair existing users ACL.
Do not automatically change default grants, membership or service_role privileges.

Compare actual baseline columns/enums/constraints/Auth trigger to the candidate.
Check duplicate exam_versions(session_id,version_code), quota range and status/job
rows affected by 005 backfills. Unknown/incompatible prerequisites are NO-GO.
Use a representative isolated restore with the target major PostgreSQL version;
synthetic PostgreSQL15/17 tests are compatibility checks, not Production readiness.

### Execution and transaction boundaries
Record a verified running backend SHA/image and test compatibility with this SQL.
A compatible existing runtime need not be redeployed. Git main is not the Supabase
branch; this procedure does not authorize dev→main promotion.
Pause business writes/workers in the approved window. Verify all 19 SQL checksums.
Execute one file at a time with psql -X -v ON_ERROR_STOP=1.
Keep explicit BEGIN/COMMIT in files; for 004,005,007,008 use psql --single-transaction
per file and rehearse those exact commands first. In particular commit 007 before
calling code using its added enum value. Never wrap the whole chain in one transaction.
Record each committed step/checksum/time/operator and stop on the first error.
Run 023 last, then NOTIFY pgrst, 'reload schema'; and verify RPC dispatch.

### Acceptance and recovery
Require owner GET /api/sessions/{id}=200 with source_revision/source_questions,
original failure case free of 503/PGRST202, Stage1 load/F5, source confirmation,
configured save/reload, B denial against A and anonymous denial.
Check exact required RPC signatures and service/client EXECUTE boundaries including
disabled legacy overloads. Verify unsafe users privileges false and SELECT intact.
Google login must work; inspect the actual approved test identity's profile row,
since /api/users/me can fall back to JWT claims and conceal a broken sync trigger.
Keep JWTs, keys, personal data and exam content out of evidence.

Receipt: SQL source SHA/checksums, applied steps, runtime SHA/image, PostgreSQL
version, backup reference, isolated restore/rehearsal proof, timestamp, operator,
reviewer and each smoke result. Missing evidence is BLOCKED/UNVERIFIED, never PASS.
Keep Issue75 open; no automatic close on merge.

On error roll back the current transaction; earlier commits remain applied.
Do not restart the manifest blindly. DB owner selects the rehearsed forward-fix
or restore procedure and reconciles receipts first. Never restore unsafe grants
as a down migration. Application rollback requires compatibility with the schema
actually reached. Resume traffic only after acceptance.
