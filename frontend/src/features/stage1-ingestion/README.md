# Stage1 — source ingestion và session entry

## TASK-203b — checkpoint sau review04/11/2026

`stage1Errors.js` đọc riêng incomplete422 envelope, tạo lỗi toàn đề/câu và hướng sửa cho10mã cùng unknown/malformed fallback. `MISSING_ANSWER` nhắc xác định đáp án đúng A/B/C/D hoặc bổ sung key tương ứng cuối đề. `IncompleteContentDialog` dùng native`showModal()/close()` để cô lập nền, có Đóng/Escape/nativecancel/Tab/focus và cleanup khi đóng/unmount; không gọi API. [M2/kiểm/giới hạn203b](../../../../docs/tasks/TASK-203b.md).

Panel dùng model từ rawcause và một dismissedCause, reset trước submit được phép; đóng/đổi mode không mở lại lỗi cũ, lần nạp mới cùng error object vẫn mở được. Dialog close trước callback để input hết inert; picker luôn mounted và gọi đồng bộ trong click user, không tự POST. Filepanel ẩn ở mode text. Giữ source/input, setMode/guards/controller201 nguyên trạng; lỗi GET/timeout không mở nhầm dialog hoặc đổi cảnh báo uncertain. Không thêm dependency/store/hook chung.

Bản1fc501c đã push/Ready/CI5success; [review Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/31#issuecomment-6627687175) nêu F01/F02 blocking và F03/F04 non-blocking, chưa Approve/merge. Baseline308tests/user L01–L04b trước review được giữ là lịch sử. Bản sửa F01/F03 ở5233322/38c3553 đã **311tests/lint/build đạt**, bundle961.94kBwarning; native Chrome fixture tái hiện baseline thoát focus và xác nhận candidate chặn focus nền/Tab/Escape/cleanup, picker từ dialog text mở được. Helper `test-support/dialog.stub.js` chỉ spy lifecycleAPI, không giả lập inert; tests còn kiểm close trước picker, cancelpicker giữ file/text và logout cleanup. FrontendDocker mớiHealthy/GETtest2C,A; **user04/11 báo “Đạt toàn bộ các bước”** cho picker/Hủy giữdraft, chuyểntext/focus, Tab/ShiftTab/Escape/nền không nhận focus, Chrome200%/CTA và trả100%/F5 giữURL/2C,A. Đây là user reported, không phải reviewer verified hoặc network/DB/Storage trace. Bản sửa chưa push/CI/reviewer xác minh; xem M2 để biết phạm vi.

Native picker mới có bằng chứng ChromeWindows, Safari/iOS chưa kiểm; không tự chốt sản phẩm chỉ hỗ trợ Chrome. Chưa có Storage audit/directmutation/nativeupload100% mới hoặc AI/confirm/Stage2/export end-to-end. TASK201/TASK103 bên dưới là lịch sử nền.

## TASK-201 checkpoint04/11/2026

`Stage1Route` giữ literalnew/create và GETdetail ban đầu. Với IDdraft, `Stage1SourcePanel` dùng plainJS `sourceIngestion` controller và useSyncExternalStore, tái sử dụng [ingestion service](../../services/ingestion.js), client/Auth/store và MathRenderer hiện có. [M2/acceptance](../../../../docs/tasks/TASK-201.md) là nguồn scope và giới hạn review.

Text/file chưa gửi tách khỏi nguồn đã lưu; submit rõ ràng mới POST. File picker/drop dùng chung validator: một DOCX/TeX/MD,1byte–10MiB, không PDF. Native input được reset để chọn lại cùng file; đổi text/file giữ input. Response phải đúng session/count/shape; questions từingest được ghép thành snapshot source_questions của panel, count/preview đổi cùng nhau. Preview nguồn/options/key chỉ đọc, Blueprint ẩn.

Pending khóa gửi/mode; revision/signal/account/route guard cả progress và response. Có total mới tính%,100% chỉ chuyển sang đang xử lý.422giữ input/source/cause choPR31;409yêu cầu GET, non-draft chỉ đọc. Cancel/timeout/5xx/invalid200 giữ cảnh báo chưa rõ và khóa gửi ngay cả sau GET. GET không chứng minh rollback/POST đã dừng; đây không phải durable lock quaF5. Giữ client timeout15s và refresh401 chung, không thêm POSTretry/cache/store.

`SourceQuestionPreview` và [Stage1SourcePanel.test.js](Stage1SourcePanel.test.js) cùng kiểm công thức/options/key, count và lifecycle. Testharness chỉ bổ sung chuẩn Text/Comment.nodeValue; tests mới dùng DOM events, không React internals. Bộ ingestion có22service/29controller/14component cases nằm trong tổngfrontend285, không cộng riêng vào tổng lần nữa.

Candidate sau sửa zoom04/11 đã285tests/lint/buildpass(bundlewarning956.34kB). ExistingID main có min-height40rem: ở viewport thấp/200% trang cuộn dọc, tránh ép vùngnguồn22.6px; newmetadata không đổi. Dockerfrontend rebuildHealthy và native200%,100% theo user,375×812CSS theo agent đã kiểm trên candidate; runtime/test hash được giữ khi cập nhật docs cuối.

User live kiểm text/MD/TeX/DOCX2câuC/A/F5, lỗi incomplete giữ nguồn/file, validation native gồmPDF thật, same-file reselection, pending/cancel, BkhôngmởA và trởAinputrỗng. Agent GET/mode-switch/layout bổ sung evidence. L01missingRPC đã được user sửa bằng migration002 và ảnh metadata; không nhận agent deploy. Native100% chưa quan sát riêng; fixture/controller/component đã kiểm. Direct BPOST/RPC, Storage object audit, fullAI/confirm/Stage2/export không được nhận là đã đạt.

Một parser smoke in-memory với1MiB trailing spaces chạm20s/exit124; chưa rootcause/profiling/BEfix, cần reviewer đánh giá trước khi khẳng định giới hạn tích hợp. Mẫu64KiB đã qua parser và dùng cho ca nativepending. Không dùng input PDF bị chặn làm evidence PDFexport/AI.

P1/P2 công bố24cfe3c; P3 đã commit local241a1ae, zoom08f0cb2; tài liệu nghiệm thu lưu mốc riêng. Chưa push các mốc mới hoặc có CI tương ứng. Chuẩn bị review TASK201 không hoàn tất203b/204. Các ghi chúTASK103 sau đây là lịch sử của session entry, không mô tả phần ingestion hiện tại.

## Lịch sử TASK-103 — entry metadata


Live increment2 checkpoint,27/10: TV1 reported success on Docker development with real login/API for new/F5 without creation, one explicit create/replace/list, existing draft/clone reload after the profile guard fix, detail network failure by browser request blocking and explicit retry after unblocking, signed-out detail/new/F5, B denied A's detail and cross-tab sign-out/account switching clearing unsent form metadata. Increment2 is complete for this metadata entry. Static Nginx, natural expiry, backend500/timeouts and W2 ingestion/confirmation are not covered. The pending author retest below is historical; TASK103 remains incomplete for other destinations. Dashboard now checks fresh detail before open; entry still loads its own detail independently.

Protected route: `/session/:sessionId/stage1`. Literal `new` shows a metadata form; it never calls detail or creates a session on mount/reload. Explicit submit uses the existing create service, then replaces the entry history item with the returned ID route. Defaults Toán/12 are editable; subject and grade follow the backend contract.

Existing IDs are read through the shared detail service with loading, safe errors, retry and a Dashboard link. A draft displays its saved metadata and source/version counts. A session whose latest status is no longer draft displays a notice and does not start processing or redirect to an unimplemented Stage. Upload, extraction, source preview/confirmation and Stage2 are not implemented by this increment. This entry does not complete TASK201 or TASK103.

Reload regression fix,27/10: ProtectedRoute now retains the requested URL while the restored session's profile is pending and blocks the outlet until verification succeeds. Profile failures offer retry at that URL or an explicit return to Login for sign-out; unauthenticated sessions still redirect to Login. A separate browser regression using the real App bootstrap/profile hook reproduced the previous redirect-to-Dashboard and passed after the fix, including delayed/error/retry/logout cases. The original increment-C fixture initialized an already verified profile and did not cover that transition.146tests/lint/build passed after the fix; author retest on Docker is still required.

`sessionEntry.js` owns transient request state. It prevents concurrent create submissions, aborts on route/account cleanup and ignores late results. Account/login-version and route-ID changes remount the entry, clearing private form/detail data. Uncertain create failures block another submission in that entry and ask the user to check Dashboard first; this is not server idempotency. Existing shared client 401 handling remains unchanged.

Checks on26/10/2026 before the first entry commit:146 frontend tests passed (13 new controller tests), lint and build passed. Browser fixture checks exercise the real React route, ProtectedRoute, services and API client with a local Auth substitute and intercepted HTTP responses: new/F5 causes no POST, invalid input, one explicit create, replace navigation, detail/F5,404/retry, changed status, signed-out redirect, account reset and375px layout. No real OAuth/cloud or Docker/Nginx route acceptance is claimed for this new entry. Live create/detail and A/B ownership checks from increment B remain separate evidence.
