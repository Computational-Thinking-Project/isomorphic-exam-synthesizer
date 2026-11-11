# TASK-207a/b/c — gói merge W2 và bằng chứng smoke local cho PR #30

## M3 cập nhật phạm vi merge W2 — 11/11/2026

- Remote PR #30 tại lượt đối chiếu: Ready for review, base `dev@7601d67`, head `5ce0d07`; CI head này 5/5 success. Head `5ce0d07` merge `dev` gồm PR #52 và docs Docker, không thay Python W2 từ `114bfc7`. Bộ backend/Blueprint **1759 passed, 274 skipped** thuộc `114bfc7`; review Đạt **674 passed, 1 skipped** thuộc `b62e007`. Không cộng hai lượt hoặc gán cho `5ce0d07`.
- PR #52 đã được Approve và merge vào `dev@294c69a`. Suite migration 017 PostgreSQL 17 cô lập **23 passed, 0 skipped**; contract/SQL I-B-STALE đã Delivered. Applied ledger 017 trên Supabase nhóm và deployed SHA tương thích chưa được xác minh theo [checkpoint Đạt 11/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6794577941).
- **Cổng merge code W2:** M3/body đúng head và giới hạn, CI head cuối đạt, finding bắt buộc đã xử lý, reviewer kiểm delta head cuối và GitHub Approve theo CONTRIBUTING. [Review Đạt tại `b62e007`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#pullrequestreview-5844073275) là COMMENT; F01/F02 verified, không có finding code bắt buộc mới trong phạm vi đã kiểm. F03 change log lặp đã được dọn trên commit local `aa78dcc`, chờ đồng bộ remote và reviewer kiểm lại; F04 body trỏ head cũ cần Quỳnh cập nhật PR thực tế, chưa coi bản nháp local là đã đăng. Đạt phân loại cả hai là P3 không chặn code review.
- **Nghiệm thu G0 live W2:** không nằm trong phạm vi merge implementation của PR #30 ở lượt này và chưa chạy. Vẫn cần đúng project, applied ledger, HTTPS/proxy, principals, quota, quyền seed/cleanup/restart và receipt cùng deployed SHA cho config N=1, job/snapshot/SSE, metrics theo vai trò và recovery. Merge PR không đổi các ca này thành PASS/Integrated/Done. Quỳnh không giữ cấu hình; comment yêu cầu Trung Anh chạy/điều phối nghiệm thu do owner tự đăng.
- Phần bên dưới là **snapshot preflight 10/11 tại `114bfc7`**, giữ nguyên để truy vết; các câu “PR #52 còn Open”, “PR #30 Draft” và “tree chưa có 017” chỉ đúng tại thời điểm ấy.

## M3 draft local — 10/11/2026

Đây là bản bàn giao local cho Quỳnh cập nhật PR #30 theo quyền owner; chưa đăng GitHub hoặc chuyển Ready. Workflow v0.1 và INPUT-20261109 vẫn **proposed**. Ba plan M2: [207a](TASK-207a.md), [207b](TASK-207b.md), [207c](TASK-207c.md). Scope là kiểm tích hợp nhỏ trên app local, dữ liệu test `N=1` sau khi đủ cấu hình; G0 live phải kiểm riêng qua HTTPS trên cùng deployed SHA và DB ledger.

### Input FE1 mới nhận để cập nhật PR body

- [Phản hồi I-B-FE1-E2E của Trung Anh](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6765881540) thay checkpoint 02/11: TASK-204/PR #42 đã merge và Stage1 upload/nhập → incomplete → preview/confirm → Stage2 có trong head PR #30. Confirm gửi UUID source revision và Idempotency-Key; confirm thành công chưa chứng minh canonical Blueprint ready. Stage2 khóa submit khi `is_ready=false`/thiếu modes; ready với `supported_modes=[]` cho Original Clone.
- Provider đối chiếu blob 16 file FE với head `114bfc7` và chạy targeted frontend tests **167 passed**. Sau đó sếp chạy lại `scripts/task204/run_existing_p4.ps1` trên Supabase Local; API và browser **PASS**, gồm Auth/JWT/PostgREST/RLS thật, confirm/replay, readiness pending/running/failed/ready, keyboard confirm và các ca F5. Báo cáo sanitized local: `tmp/task204-supabase-local/auth-result.json` và `browser-real-result.json`, cập nhật 18:39–18:40 UTC+7 ngày 10/11. Đây là bằng chứng **Integrated cho P4 Stage1 trên runtime local hiện có** do provider báo cáo; em chưa đọc trực tiếp hai report. Image app chưa được xác minh build từ head `114bfc7`, canonical producer dùng fake algebra/không gọi Gemini; P4 không thay smoke config/generation/SSE của PR #30. FE1 Delivered đủ cho bước tích hợp tiếp; Consumer Accepted cần Quỳnh xác nhận; không ghi toàn TASK-207 Integrated/Done.
- I-OPS-DB/ENV0 chỉ nhận **một phần**: stack `task204-supabase-local` và app `exam-tv1-local` chạy từ host, browser Auth qua proxy `http://127.0.0.1:18080`; ledger local đến 016, thiếu 017. Quyền cloud nhóm, seed/cleanup DB chung, principals cho toàn TASK-207 và quota Gemini vẫn cần Duy/OPS xác nhận. Đây là môi trường P4 riêng, khác Compose `scratch/task207-g0` ở `:3001/:8001`.
- Config W2 trên head này vẫn POST N, modes và hai shuffle flags. Thay đổi W4 #45 bỏ modes/default OFF là delta riêng. Dashboard resume sau generation thuộc W4-MVP-10.
- GitHub PR #30 vẫn Draft tại `114bfc7`; năm check runs trên head này completed/success. F01/F02 đã được Đạt xác minh ở head trước; Bội Anh đã Approve trên `b6b6422`, còn delta `114bfc7` cần review phù hợp. Không có bằng chứng live G0/ledger 017 mới từ phản hồi FE1.

### Đề xuất chốt Ready và handoff W4 theo đúng mức bằng chứng

- **Ready for review:** đủ đầu vào cho review code/contract W2 tại head `114bfc7` sau khi Quỳnh cập nhật M3/body với phản hồi FE1/P4 mới và xác nhận đã nhận input FE1 cho bước tích hợp tiếp. CI 5/5 trên head, backend/Blueprint regression và checks đã được ghi trong PR body. Ready không phải Integrated/Done hoặc quyền merge; reviewer cần kiểm delta hiện hành và giải quyết review state.
- **W4 có thể dùng ngay theo phiên bản:** contract config W2, SQL 015/016, Python API/worker/SSE/metrics ở PR #30 head `114bfc7`, FE2 handoff #40 và FE1 handoff/P4 Stage1 của Trung Anh. Ghi `Delivered` với SHA và scope; W4 #45/#46 là delta riêng, không sửa ngược baseline W2. Vì PR #30 chưa merge, consumer W4 phải lấy đúng head/contract hoặc chờ merge; không nói dev đã chứa code này.
- **Vẫn pending cho tích hợp/merge:** app PR #30 chưa được chứng minh build/run với Supabase thật trên cùng head; config N=1 save/read, Original Clone, snapshot/ticket/SSE, metrics Auth theo vai trò, recovery 017 và G0 HTTPS chưa có bằng chứng. PR #52 còn Open tại `598b959c`, ledger 017 chưa bàn giao. W4 chỉ tiếp tục báo thiếu **input runtime/ledger cụ thể** nếu task của họ phụ thuộc trực tiếp, không báo thiếu toàn bộ contract W2.

- PR/nhánh: [Draft PR #30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30), `feat/task-207c-runtime-metrics`.
- Code: local và remote head `114bfc7de87fc1a363e47c8504e1f7b05dd69e95`; remote base `dev@25a9e7832870d9f38ffa7ce8cd8ee656275861cc`. Repo root ở `feat/task-207-w2-backend@af77481` là phần W4 riêng; không ghép vào PR #30.
- Working tree PR #30 trước lượt này đã có sửa đổi chưa commit ở ba file task 207a/b/c. Giữ nguyên các sửa đổi ấy; không đụng stash, root worktree, dữ liệu người khác hoặc cloud migration.
- Môi trường: Docker Compose của `scratch/task207-g0`, frontend `http://127.0.0.1:3001`, backend `http://127.0.0.1:8001`. Hai container báo `healthy`. Đây không phải HTTPS private beta/G0 live. Không đưa secret hay thông tin tài khoản vào bằng chứng.

### Đã kiểm trong preflight

| Endpoint/kiểm | Kết quả | Giới hạn |
| --- | --- | --- |
| `GET http://127.0.0.1:3001/` | 200 | FE tải trang; chưa có login test. |
| `GET http://127.0.0.1:8001/health` | 200 | Public liveness của BE. |
| `GET http://127.0.0.1:8001/api/health/metrics` không token | 401 | Chỉ xác minh Auth gate; chưa đọc sáu metrics. |
| `GET http://127.0.0.1:3001/api/health/metrics` không token | 401 | Proxy tới protected route, không lấy HTML fallback làm bằng chứng metrics. |
| `GET /api/sessions` không token, qua `:3001` và `:8001` | 401 ở cả hai | Chỉ xác minh Auth gate. |
| Cấu hình worktree `.env` | Supabase URL, anon/service key, Vite URL/key, Gemini key còn trống; `ADMIN_EMAILS` chưa có | Chỉ kiểm hiện diện/độ khớp; chưa xác nhận project đích. Không in giá trị key hoặc mật khẩu. |
| Migration trong code head | 015 và 016 hiện diện; 017 không có trong tree | Không có ledger chứng minh 017 đã áp ở Supabase. PR #52 có 017 nhưng chưa là bằng chứng deploy. |

### Smoke N=1 chờ input

| Task | Luồng sẽ kiểm sau khi cấu hình đúng project và có phiên test | Trạng thái |
| --- | --- | --- |
| 207a | Phiên test đã sẵn sàng → POST config N=1 → GET session/detail đọc lại config, status và revision. | Chưa chạy; I-OPS-DB/ENV0. |
| 207b | POST generate → GET generation-snapshot → POST events/ticket → SSE nhận progress và terminal, đối chiếu committed count. | Chưa chạy; I-OPS-DB/ENV0 và quota Gemini test. |
| 207c | GET health, metrics 401/403/200 theo tài khoản khả dụng; quan sát job/SSE gauges nếu chạy được 207b. | Health 200 và metrics 401 không token đã kiểm; phần có Auth chưa chạy. |
| Recovery 017 | Chỉ kiểm nếu owner cung cấp ledger 017, SHA tương thích và điều kiện restart/test phù hợp. | Chưa kiểm; I-B-STALE/I-OPS-DB. |
| G0 live HTTPS | FE→BE→DB/Auth/SSE/proxy với cùng deployed SHA và ledger. | Chưa kiểm; ENV0/I-OPS-DB. |

**Input còn thiếu, giữ ID hiện có:** cấu hình app local đúng project Supabase nhóm được phép sử dụng; tài khoản test/phiên A, B, admin hoặc non-admin theo khả dụng; quyền seed/cleanup và hạn mức Gemini cho smoke; applied migration ledger 017 nếu muốn kết luận recovery. Người phụ trách đang chuẩn bị cấu hình và tài khoản test. Sau khi nhận, chỉ chạy luồng ghi trên phiên test; không áp migration hay sửa dữ liệu người khác. Mọi kết quả tiếp theo phải ghi lại endpoint, môi trường, SHA, status và phần chưa kiểm tại đây trước khi Quỳnh cập nhật PR.

**Review:** F01/F02 đã được Đạt xác minh ở các head trước; không tự suy ra GitHub Approve hoặc nghiệm thu G0. PR #30 vẫn Draft. Quỳnh tự quyết định push, đăng M3, chuyển Ready và merge.
