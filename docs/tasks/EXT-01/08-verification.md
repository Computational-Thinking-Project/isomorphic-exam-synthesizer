# EXT-01 / 08 — Kiểm thử và nghiệm thu

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Chuẩn bị fixtures/test harness ngay; chạy kiểm tương ứng sau từng gói, tích hợp cuối sau dependency.
- **File / đầu vào:** Các tests/commands và toàn bộ A01/A02/DoD bên dưới là nguồn nghiệm thu duy nhất.
- **Thứ tự làm:** Mỗi gói chạy subset liên quan; ghi command/head/môi trường/pass-fail-skip; DB disposable/full chain/PostgREST theo gate; kiểm UI/AI/artifact thật khi đủ; review độc lập trước Ready.
- **Đầu ra / điều kiện hoàn thành gói:** M3/M5 và evidence tại integration HEAD; chưa tick Done cho test chưa chạy, chưa gọi CI xanh là live pass.
- **Kiểm chứng:** Toàn bộ A01/A02, A03/A20 phối hợp; không nhân bản ma trận sang file khác. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** đã có bản G0/G1 của author. Xem [bằng chứng và giới hạn ngày 27/11](08-verification.md#evidence-20261127). Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="evidence-20261127"></a>

## Kết quả kiểm của author · 27/11/2026

Windows, PowerShell, Python 3.14, Node 24.16, Docker Desktop / PostgreSQL 15 Alpine. Checkpoint M2 là `49cd9b7`. Code tích hợp và ca nghiệm thu cuối là `7144d33`. Bản bàn giao tiếp sau chỉ sửa Markdown. A01 có 14 ca đạt ở mức UI local. A02 có 17 ca đạt ở mức ghi trong bảng, 8 ca có bằng chứng một phần và 5 ca chưa chạy do gate. Suite dùng mock, PG cô lập, Gemini thật và Edge local có phạm vi riêng.

| Lượt kiểm | SHA / môi trường | Kết quả thực tế |
|---|---|---|
| API, service, AI sau M3–M4 | Working tree sau M2 | 268 pass. Đường Q02 và prompt retry được kiểm trước khi nối UI. |
| Regression toàn backend | `93672c3`, Windows UTF-8 | 2296 pass, 797 skip theo điều kiện của suite. Lượt trước dùng code page Windows có 14 lỗi đọc fixture và 1 timeout validator. Chạy lại toàn bộ với UTF-8 đạt. Từ SHA này đến `7144d33`, backend chỉ bổ sung bước assert trong test PG opt-in. |
| Review API, service, targeted AI | `7144d33`, ASGI/RPC doubles, Gemini mock | 278 pass, 1 skip là Gemini opt-in. |
| Provider Gemini thật | Working tree có test live sau `3ebd333`, cùng mã adapter và test live ở `7144d33` | 15/15 test trong file targeted khi bật live, gồm 1 test gửi fixture Toán qua Gemini và validator thật, giới hạn 4 call. Permit dùng fixture bộ nhớ. |
| PostgreSQL 15 disposable | `93672c3` | 35 pass gồm 8 migration EXT-01, 4 service asyncpg và 23 snapshot. Regression RPC/chain upstream riêng đạt 47 pass và 7 subtest. |
| Migration 028 và archived replay | `652b5e7`, cùng backend/test PG với `7144d33` | 8/8 pass. Đã chạy full chain 002–028 trên DB test, rerun 028, kiểm role/signature, race, recover khóa/expiry và replay candidate B sau khi accept B rồi sinh C. |
| Frontend regression, ESLint, build | `7144d33`, Node DOM harness / Vite | 631/631 pass, 0 fail/skip/cancel. ESLint và build pass. Vite cảnh báo chunk lớn hơn 500 kB. |
| Browser native | Edge headless trên Windows, fixture I-EXT-01; source ngay trước `93672c3` | Pass. Mở dialog, kiểm 8 checkbox, chọn lý do, đóng dialog, Accept inline, xác minh focus Preview và readiness trước/sau. Các thay đổi UI sau lần này chỉ là câu báo chờ readiness. |
| Static | `93672c3`, cùng backend/app với `7144d33` | Ruff pass. Mypy pass trên 128 source file. |

**Lệnh kiểm đã chạy.** Từ root, dùng `$env:PYTHONUTF8='1'` khi chạy toàn backend. Mỗi nhóm opt-in PG chạy trên database/container riêng do fixture tạo. Lượt PG legacy còn đặt `PYTHONPATH=backend;backend/tests/migrations`.

```powershell
python -m ruff check backend/app scripts/blueprint
python -m mypy backend/app --ignore-missing-imports
python -m pytest backend/tests scripts/blueprint/tests -q -s --disable-warnings --tb=line
python -X utf8 -m pytest backend/tests/api/test_ext01_reject_api.py backend/tests/api/test_review_api.py backend/tests/api/test_review_rpc_http.py backend/tests/services/test_review_lifecycle.py backend/tests/services/test_review_receipts.py backend/tests/services/test_review_contract_parsers.py backend/tests/services/test_review_flow.py backend/tests/services/test_ext01_durable_reasons.py backend/tests/ai/test_targeted_regeneration.py -q --disable-warnings --tb=line

# Suite opt-in Gemini, fixture tổng hợp
$env:RUN_EXT01_LIVE_AI='1'
python -X utf8 -m pytest backend/tests/ai/test_targeted_regeneration.py -q -s --tb=line --disable-warnings

# Các suite PostgreSQL disposable
$env:RUN_POSTGRES_MIGRATION_TESTS='1'
$env:RUN_TASK305_REAL_DB_TESTS='1'
$env:EXAM_TEST_DB_DESTRUCTIVE='1'
python -X utf8 -m pytest backend/tests/migrations/test_ext01_review_reasons_pg.py backend/tests/services/test_review_real_db_integration.py backend/tests/migrations/test_review_snapshot_pg.py -q -s --tb=line
$env:RUN_UPSTREAM_MIGRATION_TESTS='1'
$env:PYTHONPATH='backend;backend/tests/migrations'
python -X utf8 -m pytest backend/tests/migrations/test_review_rpcs.py backend/tests/migrations/test_review_migration_chain.py -q -s --tb=line

# Từ frontend/
node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js src/services/stage3Service.test.js
npm test -- --test-concurrency=1
npm run lint
npm run build
```

**A01.** File `frontend/src/features/stage3-review/Stage3Review.test.js` kiểm thứ tự 2×3, vòng lại mã hiện tại và biên 1×1/4×20 (01/02/12), điều hướng khi pending, A→B→A và hai read cùng session trả ngược thứ tự (03/04/13), lỗi/mất response và mismatch candidate (05/06/14), reload fixture accept/regenerate/revert và trạng thái khóa (07/10), server ready true/false (08/09), đáp án, lời giải, dialog, focus và xác nhận (11). Edge kiểm bổ sung đường tương tác nêu trên. Chưa có phiên đăng nhập hosted chạy đủ 14 ca với DB thật.

| A02 | Mức kiểm | Bằng chứng hoặc điều kiện còn thiếu |
|---|---|---|
| 01–03, 29 | Pass API | Body cũ, enum, canonicalization và payload sai trước side effect. |
| 04–08, 17 | Pass service/PG | Binding ở lookup/reserve, receipt vắng/malformed, conflict, race, role ACL, signature và migration replay trên DB disposable. |
| 09 | Pass mock và provider smoke | Đã kiểm prompt đầu, retry schema, duplicate và solution repair. Một operation với Gemini thật qua validator. |
| 10, 13, 14, 19, 20 | Pass theo lớp | Permit/quota, timeout/cancel, failed/recovered, FE key retry/retire, complete/settle/replay và candidate mới pending. PG thật có Accept rồi regenerate tiếp. |
| 25 | Pass ASGI/service và PG | Owner denial trước worker, pre-read guard, lỗi post-read, active/expired, khóa approve/post-shuffle và gọi recover lần hai. |
| 11, 12 | Một phần | PG kiểm lease, recovery sau reserve và replay sau Accept + regeneration kế tiếp. Worker crash được mô phỏng bằng operation còn trong ledger. Chưa kill process live hoặc chạy replay sau một lượt shuffle thật trong cùng kịch bản. |
| 15, 18, 21, 22 | Một phần | Có fixture revert có/thiếu lời giải, clone 1.0/1.1 mixed và fallback; regression Preview/Export, approve khi active, Stage 2 saved-result resume đạt trong các suite riêng. Chưa kiểm delete race liên EXT, job hosted cũ, hay xác nhận provenance và mode từ owner. |
| 24, 30 | Một phần | Đã kiểm đến candidate thay thế, đáp án/lời giải và accept, cùng migration fresh/legacy/rerun. Chưa có file export của chính operation sau shuffle/approve liên EXT, hoặc diễn tập coordinated rollback/roll-forward sau lỗi deploy. |
| 16, 23, 26, 27, 28 | Skip theo gate | Q04 chặn mode/slot guard, Q05 chặn rollout và PostgREST schema cache dùng chung, Q06–Q08 chặn chứng nhận classifier/reader/provenance của consumer. |

Fixture policy chứa projected fields phục vụ đối chiếu 1.0/1.1. Chưa có consumer xác nhận các fixture đủ dùng cho Preview/Export. A20 và GitHub Approve/CI thuộc các bước tiếp theo.

<a id="section-5"></a>

## 5. Kế hoạch tự kiểm

<a id="section-5-1"></a>

### 5.1. Ma trận nghiệm thu A01 — Review UI và recovery

| ID | Ca kiểm | Kết quả mong đợi |
|---|---|---|
| A01-01 | 2 mã × 3 câu, accept C1 mã 101 | Sang C2 mã 101, không sang mã 102 trước khi hết câu chưa duyệt cùng mã |
| A01-02 | Bỏ qua C1, duyệt câu cuối cùng mã | Quay lại C1 trước khi đổi mã |
| A01-03 | Chuyển câu/mã/session trước response | Không auto-advance hoặc ghi đè candidate đang xem mới |
| A01-04 | Chuyển đi rồi quay lại vị trí cũ trước response | Epoch thay đổi, không auto-advance |
| A01-05 | Accept lỗi hoặc timeout; refetch lỗi | Không nhảy câu, đối soát server; khóa Preview nếu chưa sync |
| A01-06 | Accept trả success nhưng snapshot khác status/ID | Không ép status approved, không dùng approval ID cũ |
| A01-07 | Reload sau accept/reject/revert; quay lại câu đã duyệt | Server authoritative; vị trí xem chỉ là tiện ích |
| A01-08 | Tất cả local approved nhưng server ready=false; missing/active operation | Preview khóa; hiển thị tình trạng có thể phục hồi |
| A01-09 | ready=true, reviewed, không busy/sync issue | Cho mở Preview; không auto mở |
| A01-10 | Read-only, post-shuffle, approved/exported, deep link | Không ghi dữ liệu trái contract; route thích hợp |
| A01-11 | Inline answer/solution, thiếu lời giải, keyboard/focus/confirmation | Đúng candidate, đúng nhãn, không tạo validator FE |
| A01-12 | N=1/4, M=1/20; slot thiếu; điều hướng sau last | Không sai index, không lặp vô hạn, không nhảy sang slot không thể duyệt |
| A01-13 | Initial load/refetch cùng session trả sai thứ tự; A→B→A | Chỉ nhận read hợp lệ; không ghi đè snapshot mới |
| A01-14 | Accept error nhưng server đã commit; reload đang regenerating | Hiển thị server đúng, không auto-advance; reconcile theo Q03 |

<a id="section-5-2"></a>

### 5.2. Ma trận nghiệm thu A02 — Reasons, idempotency, AI và DB

| ID | Ca kiểm | Kết quả mong đợi |
|---|---|---|
| A02-01 | Không body/body null/`{}`/`{"reasons": []}` | Caller MVP tương thích; canonical reasons `[]` |
| A02-02 | Nhiều reasons; trùng/đảo thứ tự | Cùng tập canonical, lưu đúng |
| A02-03 | Mã lạ, sai kiểu, null theo Q01 | 422, không gọi AI/tạo operation/tăng quota |
| A02-04 | Cùng key/tập reasons; receipt lịch sử thiếu reasons | Replay đúng kết quả cũ; legacy rỗng |
| A02-05 | Cùng key, khác reasons ở lookup và reserve | 409; không phát sinh write/AI |
| A02-06 | Hai request cùng key đồng thời, cùng/khác tập | Chỉ operation hợp lệ dispatch; conflict đúng |
| A02-07 | Cross-owner/cross-session/candidate cũ | 404/409/423 theo contract; không truy cập trái quyền |
| A02-08 | RPC signature cũ và role trực tiếp | Không bypass reason binding hoặc RLS/ACL |
| A02-09 | AI prompt đầu tiên, retry schema/validator/solution repair | Teacher reasons được giữ; validator/blueprint không suy yếu |
| A02-10 | Duplicate candidate, timeout, cancel, quota 30, max 4 calls | Giữ prior candidate khi failure; đúng permit/settlement, không charge replay |
| A02-11 | Kill worker sau reserve, lease hết hạn; retry cùng key hoặc reload mất key | Recover prior status; không dispatch mới khi operation active; key mới sau terminal |
| A02-12 | Completed reject replay sau accept, regenerate tiếp, shuffle | Đúng kết quả operation cũ; không hồi sinh candidate lịch sử; UI refetch |
| A02-13 | Failed/recovered operation và retry mới | Không tái dùng key terminal vô hạn; theo Q02/Q03 |
| A02-14 | Regeneration thành công → accept mới | ID mới, pending_review, giữ mapping/answer/solution |
| A02-15 | Revert frozen source có/thiếu lời giải; accept lại | Đúng nguồn, key, provenance; pending_review; Preview/Export nhất quán |
| A02-16 | Shuffle-only reject trực tiếp | Chặn trước reserve/AI, không tăng quota; AI mode vẫn hoạt động |
| A02-17 | Migration fresh, DB populated có receipt cũ, chạy lại nếu quy trình yêu cầu | Không đổi ID, quota, receipt, ACL ngoài dự kiến |
| A02-18 | Race delete/approve với review operation | Không xóa/approve dở dang; phối hợp EXT-04 với session lock |
| A02-19 | Mất response reserve/complete/settlement với reasons không rỗng | Retry cùng binding, `_settle` không conflict sai, không dispatch thêm; 503 sau commit không rollback |
| A02-20 | Normal complete / uncertain complete / replay | Cùng projection đã commit, cả khi live candidate đổi |
| A02-21 | Job Stage 2 cũ có saved results, resume sau thay đổi targeted prompt | Fingerprint generation thường không đổi; A03 phối hợp Tâm |
| A02-22 | AI/clone/fallback mixed policy; legacy clone null | AI mode cần Accept; provenance/Export đúng hoặc blocker có owner; không suy mode từ origin |
| A02-23 | Rollout old/new DB/backend/FE và RPC schema cache | Caller hợp lệ hoạt động theo chiến lược Q05, caller cũ không bypass |
| A02-24 | Reject A → generate B → Accept B → Shuffle → Preview → Approve → Export | A/B có key khác nhau; shuffle đổi nhãn; file đề/đáp án/lời giải đúng B và projection, không lẫn A |
| A02-25 | Recovery non-owner/unknown session, approved/post-shuffle; recovery commit rồi snapshot read lỗi | Không có worker mutation trước owner check; đúng routing; lỗi đọc không che commit, retry không double-settle |
| A02-26 | Frozen/live mode lệch; legacy/new thiếu mode; mode lạ; policy 1.0/1.1 | Legacy có evidence mới dùng default; dữ liệu mới sai bị chặn trước reserve/AI; replay cũ giữ Q02 |
| A02-27 | Clone-only AI reject, shuffle-only reject/revert trực tiếp; UI đọc capability | Đúng Q04 đã được xác nhận; không bypass qua direct RPC, không tạo operation/quota |
| A02-28 | R09 qua Export reader và Finalize repository với mixed-policy/negative fixtures [§3.6.1](07-preview-export-provenance.md#section-3-6-1) | Projection đủ field; classifier không chặn nhầm; provenance invalid bị từ chối ở cả Preview/Export |
| A02-29 | Body `[]`, scalar, field lạ, malformed JSON, `reasons:null` | 422 trước operation write/AI/quota; phân biệt với `{"reasons":[]}` |
| A02-30 | Migration dependency/schema thiếu; DDL rollback; backend smoke lỗi sau DDL | Không bật guard/traffic sớm; rollback transaction hoặc roll-forward tương thích, không mất receipt |

A20 (Quỳnh chủ trì, Duy/Tâm/Đạt/Hùng/Bội Anh phối hợp): backfill hai lần với tên trùng và hậu tố sẵn, draft/approved/exported, mã legacy ngoài miền OMR; so sánh nguồn/lượt/mã/receipt/artifact trước/sau; hồi quy `AI → Review → Preview → Approve → Export`. Duy kiểm phần Review và điều phối đầy đủ bằng chứng, không nhận thay scope migration Bank/Export. Duy không tự chứng nhận A20 khi consumer chưa tích hợp. A03/A05 có case liên quan source/mode do Tâm chủ trì; Duy hỗ trợ tại Review boundary.

<a id="section-5-3"></a>

### 5.3. Test files và commands

| Nhóm | File hiện có ưu tiên |
|---|---|
| API / snapshot | `backend/tests/api/test_review_api.py`, `test_review_rpc_http.py`, `test_review_snapshot.py` |
| Service / receipt | `backend/tests/services/test_review_lifecycle.py`, `test_review_receipts.py`, `test_review_flow.py`, `test_review_contract_parsers.py` |
| PostgreSQL | `backend/tests/migrations/test_review_rpcs.py`, `test_review_snapshot_pg.py`, `test_review_migration_chain.py`, `test_w4_baseline_chain.py`; `backend/tests/services/test_review_real_db_integration.py` |
| AI | `backend/tests/ai/test_targeted_regeneration.py`, `backend/tests/services/test_review_ai_dependency.py` |
| Preview/Export R09 | `backend/tests/exporter/test_snapshot_reader.py`, `test_snapshot_q01.py`, `test_snapshot_builder.py`; `backend/tests/services/test_finalize_display_contract.py`; `backend/tests/api/test_finalize_preview.py`; `backend/tests/migrations/test_export_q01_pg.py` |
| Policy | `backend/tests/generation/test_per_question_policy.py` cùng targeted/DB guard tests mới |
| FE | `frontend/src/features/stage3-review/Stage3Review.test.js`, `frontend/src/services/stage3Service.test.js` |

**Regression FE cần chỉnh có chủ đích tại #109@1072d1c:** test dòng 597 (dialog → inline, đồng thời cập nhật assertion ở dòng 654 không còn cấm `'Lý do từ chối'`), 660 (accept + snapshot mock phải cập nhật), 871 (Preview gate `progress.ready`), 996 (hiện mới test `acceptQuestionFn`, cần bổ sung case `reject` retry uncertain/terminal + `reasons`), 2816 và 2864 (question-major → version-major, accept inline); giữ focus test 2889 cho reasons/revert dialog. Giữ các test candidate identity #85, stale session/unmount, read-only/partial, post-shuffle 409 và approved/exported 423. Mock snapshot phải phản ánh mutation thực, không sửa business logic để thỏa mock tĩnh. Không bỏ test regression để làm xanh CI.

Từ root repo, trong môi trường đã setup dependencies theo hướng dẫn:

```bash
ruff check backend/app scripts/blueprint
mypy backend/app --ignore-missing-imports
python -m pytest backend/tests/api/test_review_api.py backend/tests/services/test_review_lifecycle.py backend/tests/services/test_review_receipts.py backend/tests/ai/test_targeted_regeneration.py -q
python -m pytest backend/tests/exporter/test_snapshot_reader.py backend/tests/exporter/test_snapshot_q01.py backend/tests/exporter/test_snapshot_builder.py backend/tests/services/test_finalize_display_contract.py backend/tests/api/test_finalize_preview.py backend/tests/generation/test_per_question_policy.py -q
python -m pytest backend/tests scripts/blueprint/tests -q
```

```bash
cd frontend
node --test --test-concurrency=1 src/features/stage3-review/Stage3Review.test.js src/services/stage3Service.test.js
npm run lint
npm run build
npm test
```

Theo [isolated_postgres.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/tests/services/isolated_postgres.py), TASK-305 real DB suite cần Docker và hai biến opt-in. Ví dụ Bash, **chỉ cho disposable test DB**:

```bash
RUN_TASK305_REAL_DB_TESTS=1 EXAM_TEST_DB_DESTRUCTIVE=1 \
  python -m pytest backend/tests/services/test_review_real_db_integration.py -q
```

PowerShell tương đương: thiết lập `$env:RUN_TASK305_REAL_DB_TESTS='1'` và `$env:EXAM_TEST_DB_DESTRUCTIVE='1'`, chạy cùng pytest target, sau đó xóa hai biến môi trường. Không chạy trên DB chia sẻ/production. Kiểm tra fixture áp migration nào: suite trên dùng `schema.sql` rồi 006, 007, 008, 009 và adapter asyncpg; **không đủ chứng minh full current chain**. `test_review_migration_chain.py` cũng opt-in `RUN_UPSTREAM_MIGRATION_TESTS=1` và cần các pinned commits; không mặc định nó bao phủ EXT migration.

Bổ sung rehearsal/test full chain đúng baseline đến 027 + migration mới và migration phối hợp EXT-02/04 (tùy head triển khai), trên DB cô lập mới và DB có dữ liệu/receipt cũ. Ghi rõ migration list, role, kết quả pass/fail/skip. PG thật không chứng minh PostgREST schema cache; chạy smoke RPC mới qua PostgREST môi trường test với owner và non-owner, kiểm old caller theo Q05. Đối chiếu [w4-migration-candidate](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/docs/w4-migration-candidate.md); Git inventory không phải applied ledger.

Local runtime theo CONTRIBUTING: `scripts/dev.ps1 setup`, `doctor`, `up`, `smoke`, `test` (PowerShell/pwsh theo nền tảng). Chạy UI browser thật và API/DB thật cho A01/A02, ít nhất một ca targeted regeneration với AI thật nếu cấu hình/quota cho phép; mock prompt tests không thay kiểm provider. Nếu thiếu môi trường/key, ghi blocker và phạm vi chưa đạt, không nhận live integration pass. CI theo `.github/workflows/ci.yml`, `docker-ci.yml`; không bỏ checks. `ci.yml` ở base chỉ thấy frontend install + build; không suy npm lint/test đã chạy từ CI xanh. Ghi kết quả chạy riêng. A01/A02 và retry/concurrency/ACL/migration cần bằng chứng môi trường test thật theo task [§5](#section-5); mock không thay nghiệm thu.

<a id="section-8"></a>

## 8. Definition of Done

- [ ] F-019: PR #109 và integration HEAD đã đối chiếu, ghi phần tái sử dụng/delta và evidence; không nhầm kết quả tác giả với tự kiểm.
- [ ] M1/M2: scope, base/head, reviewer/dự phòng, ETA, input dependencies và migration ordering đã chốt.
- [ ] Gates G0–G4 được xác nhận theo phạm vi bàn giao; ghi link/head/owner, không tick chỉ vì plan đã đủ nội dung.
- [ ] Recovery endpoint kiểm owner trước service-role mutation; A02-25 đạt.
- [ ] Frozen mode/policy và legacy discriminator có contract/fixture; A02-26/27 đạt.
- [ ] R09 có reader/classifier/verifier đầy đủ và test qua repository; A02-28 đạt hoặc ghi blocker owner nếu ngoài phần bàn giao.
- [ ] API: optional reasons, enum validation, canonicalization, caller MVP tương thích.
- [ ] DB: lookup/reserve cùng binding, legacy receipt rỗng, concurrency, ACL, quota và mode guard đạt trên PG thật.
- [ ] Replay/recovery: cả ba response path cùng projection; non-empty reasons khi settlement uncertain; Q02/Q03 chốt; worker chết/expiry/reload, failure retry, không duplicate dispatch.
- [ ] AI: reasons từ reservation đã xác nhận, giữ qua retry; blueprint/validator/permit không suy yếu; resume job cũ không hồi quy, Q04 mode/policy đã tích hợp.
- [ ] FE: inline đáp án/lời giải/accept, reasons dialog, revert, navigation epoch và authoritative snapshot.
- [ ] Readiness: server gate; không tự approve hoặc tự chuyển Preview; missing/recovery/lock đúng.
- [ ] A01/A02 đạt trên HEAD triển khai; A02-24 đối soát artifact cuối, answer/solution đúng; phần live/DB chưa kiểm ghi rõ.
- [ ] I-EXT-01 có fixture đúng schema, contract version, consumer acknowledgement và evidence tích hợp khi có.
- [ ] Migration chain/rehearsal, PostgREST smoke/rollout, regression, lint/typecheck/build, CI áp dụng đạt; independent review, xử lý blocker.
- [ ] A20 phối hợp khi đủ các EXT; không tuyên bố hoàn thành toàn nhóm nếu chưa có evidence.
