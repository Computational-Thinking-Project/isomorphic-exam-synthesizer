# PR #33 / TASK-305 — Kế hoạch triển khai rút gọn cho coding agent

**Mode:** author; **repo:** `Computational-Thinking-Project/isomorphic-exam-synthesizer`; **PR:** https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/33. **Snapshot kiểm ngày 04/11/2026 ~22:15 ICT:** PR HEAD `3f84ac16626ef06a55d823dbf5d52a2564e51f9b`, base `dev` `99dc8d307cb22b489cb17553d487f0ce5f7573e7`; `mergeable=true` nhưng Đạt vẫn `CHANGES_REQUESTED`. **Mục tiêu:** sửa lỗi nội bộ, khôi phục CI, kiểm chứng SQL/DB và xin re-review; **không** tự merge, deploy hoặc triển khai TASK-303/307/308.

> **Quy tắc thực thi:** Mọi kết luận gắn với SHA trên; nếu HEAD/base khác, kiểm lại diff và bằng chứng trước khi áp dụng. Chỉ thực hiện thay đổi trong quyền author PR #33. Không tự chốt contract chưa có xác nhận; không biến test mock/skip thành bằng chứng PostgreSQL hoặc E2E.

## 1. Căn cứ cố định

| Mã | Bằng chứng đã kiểm | Kết luận dùng để triển khai |
|---|---|---|
| E01 | [PR #33](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/33) `3f84ac1` | Diff 15 file, không còn ReviewRepository/SQL006 trong diff với `dev`; mergeable không đồng nghĩa ready. |
| E02 | [CI 41854608186](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/41854608186) | Frontend, Ruff, mypy (89 files) đạt; backend pytest lỗi collection. |
| E03 | [Docker CI 41854608330](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/actions/runs/41854608330) | Docker cũng dừng ở cùng collection error. |
| E04 | [`test_finalize.py:44`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/tests/api/test_finalize.py#L44) | Import `MockSupabaseClient` từ `test_review_lifecycle` không còn hợp lệ sau cập nhật RPC fixtures. |
| E05 | [Finalize DB fixture](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/tests/services/test_finalize_real_db_integration.py#L181-L236) và [Review DB fixture](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/tests/services/test_review_real_db_integration.py#L178-L213) | `DROP SCHEMA public CASCADE`; default `PG_TEST_DSN` trỏ DB `postgres`: nguy cơ xóa dữ liệu. |
| E06 | [`finalize/repository.py:305–347`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/app/services/finalize/repository.py#L305-L347) | Matrix đã fail-closed, không fallback; kiểm config, N×M display keys, alias và A–D. |
| E07 | [SQL007:128–215](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/migrations/007_finalize_approve_session_rpc.sql#L128-L215) | Approval chưa đọc `answer_keys`, dù kiểm `is_finalized`, approved/current, `_review_progress.ready`. |
| E08 | [SQL006 `_review_progress`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/99dc8d307cb22b489cb17553d487f0ce5f7573e7/backend/migrations/006_stage3_review_and_shuffle.sql#L357-L410) | Readiness review/source/ledger không xác nhận display keys. |
| E09 | [SQL007 actor/role](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/migrations/007_finalize_approve_session_rpc.sql#L31-L101) | Nhánh `service_role` lấy từ claim GUC; cần kiểm thử giả role, **chưa chứng minh** được exploit qua PostgREST thật. |
| E10 | [Review RPC contract §Finalization](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/99dc8d307cb22b489cb17553d487f0ce5f7573e7/docs/api/review-rpc-contract.md#L326-L361) | Review writer + approval dùng parent row lock `exam_sessions`; invalidation trong cùng transaction. |
| E11 | [`TASK-303_ANSWERS.md`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/99dc8d307cb22b489cb17553d487f0ce5f7573e7/docs/tasks/TASK-303_ANSWERS.md), [`shuffler/schemas.py`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/99dc8d307cb22b489cb17553d487f0ce5f7573e7/backend/app/services/shuffler/schemas.py#L82-L158) | `display_no/display_correct_key` sau shuffle; alias DB `question_no/correct_option`; core shuffler không ghi DB. |
| E12 | [Export snapshot contract](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/99dc8d307cb22b489cb17553d487f0ce5f7573e7/docs/export-w3-bundler.md#L40-L67) | Export dùng displayed options/key/solution; mapper DB revision chưa nghiệm thu. |
| E13 | [Đạt review F06](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/33#pullrequestreview-5745235554), [PR #28](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/28) | `dev` đã có `review_recover_session`: re-test lỗi cũ, không hồi sinh repository cũ. |
| E14–15 | [`test_finalize.py:600–733`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/tests/api/test_finalize.py#L600-L733), [`1243–1269`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3f84ac16626ef06a55d823dbf5d52a2564e51f9b/backend/tests/api/test_finalize.py#L1243-L1269) | Test cũ vẫn mong fallback rỗng keys và chuẩn hóa `'  a  '` → `A`; trái contract strict. |

**Bất biến:** (a) SQL006/review RPC trên `dev` là authority, không phục hồi code/SQL008 cạnh tranh; (b) không dùng Python lock, đọc SELECT riêng hoặc CAS để thay DB transaction/parent lock; (c) approval và matrix đều fail-closed, không đoán display key từ canonical; (d) không chạy fixture phá DB thật/shared; (e) `implemented ≠ tested ≠ independently verified ≠ approved ≠ merged ≠ deployed`; (f) không giả keys, revision, actor hay `is_finalized`; (g) không sửa nhánh thành viên khác.

## 2. Khởi động, điều kiện dừng và thứ tự công việc

**Trước khi sửa:** đọc `AGENTS.md`, `CONTRIBUTING.md`, `docs/review/WORKFLOW.md`, `docs/review/TEMPLATES.md`, `docs/tasks/TASK-305.md` và contract SQL006/007; chạy các lệnh đọc sau, ghi SHA và worktree:

```bash
git status --short
git branch --show-current
git worktree list
git fetch origin
git rev-parse HEAD
git rev-parse origin/dev
git diff --name-status origin/dev...HEAD
git diff --check origin/dev...HEAD
git log -5 --oneline
```

**Không chạy real-DB tests trước WP-02.** Ghi chứng cứ `HEAD/base, commands, environment, pass/fail/skip, known gaps` (chưa chạy = `NOT RUN`). Không `reset --hard`, force-push, ghi đè worktree/untracked hoặc đưa secrets vào logs.

**Dừng và hỏi owner khi:** (S1) branch/head không xác định hoặc có uncommitted work của người khác; (S2) test DB không chứng minh được isolated, DSN trỏ shared/production; (S3) cần định nghĩa `version_questions.correct_key` canonical/display mà writer chưa xác nhận; (S4) migration đã apply ngoài test cần upgrade path; (S5) sửa đòi GRANT ledger, bypass RLS hoặc tin `p_user_id`; (S6) test xanh nhưng chưa có GitHub Approve thì chỉ request re-review, không merge.

| WP | Nội dung | Ưu tiên | Sau | Phạm vi |
|---|---|---|---|---|
| 00 | Xác nhận baseline và finding | P0 | — | NOW |
| 01 | Sửa import/fixture collection | P0 | 00 | NOW |
| 02 | Cô lập PostgreSQL tests an toàn | P0 | 00 | NOW |
| 03 | Đồng bộ strict matrix/API tests | P0 | 01 | NOW |
| 04 | Bổ sung SQL007 display-key guard | P1 | 02,03 | NOW, value semantics gated |
| 05 | Adversarial F16 role/actor | P1 | 02 | NOW, runtime auth gated |
| 06 | Python precheck/receipt/idempotency/error | P1 | 01,03 | NOW |
| 07 | F01/F06 recovery/concurrency/rollback | P1 | 02,04,05 | NOW |
| 08 | Offline shuffle↔matrix↔export parity | P1 | 03 | NOW, locked DB snapshot gated |
| 09 | Fresh/legacy/replay migrations | P1 | 02,04,05 | NOW |
| 10 | Full regression và GitHub Actions | P0/P1 | 01–09 | NOW |
| 11 | Docs, PR, reviewer handoff | P2 | 10 | NOW |
| EXT | Writer shuffle, deployed DB, locked export snapshot, Approve | Gate | owner khác | EXTERNAL |

WP-01 và WP-02 có thể song song nếu tách worktree/commit không chồng chéo. Mọi WP chạy DB phải phụ thuộc WP-02.

## 3. Work packages — bước thực thi và Definition of Done

### WP-00 — Baseline và finding register
**Lý do:** PR #28 đã merge, #33 có diff và CI rõ ràng.

**Làm:** (1) Chạy phần khởi động §2, ghi branch/HEAD/base/diff/status/log; (2) phân loại 15 file hiện tại, cảnh báo nếu `services/review/*` hoặc SQL006 xuất hiện trong diff; (3) đọc code ở exact HEAD, không dùng line cũ; (4) lập register `F01, F03, F06, F16, F19 → repro → code → evidence → reviewer state`, chưa xác minh ghi `OPEN`; (5) ghi CI backend/Docker fail `MockSupabaseClient`, frontend/Ruff/mypy pass.

**DoD:** SHA/worktree/diff được lưu; ngoài-scope có giải thích; mỗi finding có trạng thái bằng chứng, không biến báo cáo author thành reviewer verified; không ghi đè worktree.

### WP-01 — Sửa pytest collection, không phục dựng mock sai
**File:** `backend/tests/api/test_finalize.py`, `backend/tests/services/test_review_lifecycle.py`, `test_review_flow.py`, `test_finalize_display_contract.py`. **Lý do:** import dòng 44 không còn class, CI/Docker fail.

1. Tìm usages và fixtures hiện có:
   ```bash
   rg -n 'MockSupabaseClient|test_review_lifecycle|fallback|normalize|correct_option' backend/tests/api/test_finalize.py
   rg -n 'class .*Client|def state\(|class .*State|def .*rpc' backend/tests/services/test_review_flow.py backend/tests/services/test_review_lifecycle.py
   ```
2. Phân test thành: HTTP/auth/UUID → `TestClient` + dependency override; receipt/fail-closed → RPC stub đúng schema; matrix → fixture `Tables`/service; DB transaction/recovery/concurrency → test PostgreSQL sau WP-02. Không tạo lại shared mock table writes chỉ để xanh.
3. Xóa import cũ; chuyển từng test giữ **ý nghĩa finding**. Test sai contract chuyển WP-03; fake UUID chỉ dùng cho mock tests, real RPC dùng UUID chuẩn. Không xóa test hay hạ assertions âm thầm.
4. Chạy:
   ```bash
   python -m pytest backend/tests/api/test_finalize.py --collect-only -q
   python -m pytest backend/tests/services/test_finalize_display_contract.py -q
   ```

**DoD:** collection không error; không còn import/class lỗi thời; mỗi test được giữ/thay thế có giải thích; tests transaction không lấy memory fake làm chứng cứ atomic; ghi collected/pass/skip thực.

### WP-02 — Cô lập real-DB integration tests
**File:** `backend/tests/services/test_finalize_real_db_integration.py`, `test_review_real_db_integration.py`, fixture chung mới phù hợp cấu trúc repo. **Lý do:** cả hai `DROP SCHEMA public CASCADE` trên default database `postgres`.

1. **Không chạy hai module trước khi sửa.** Rà toàn bộ `asyncpg.connect`, role/schema setup, `DROP/CREATE`, teardown, `PG_TEST_DSN`.
2. Bỏ default DSN `.../postgres`. Dùng **fixture chung**: ưu tiên PostgreSQL 15 container dành riêng cho test + DB ngẫu nhiên `task305_test_<random>`; hoặc explicit test-admin DSN local đã xác minh, tạo DB riêng cùng tên. Tách connection quản trị tạo/drop DB và connection chạy test.
3. Preflight xác minh DB do fixture vừa tạo; thiếu Docker/DSN/permissions hoặc DSN nhầm shared/production → fail/skip rõ ràng, **không fallback DB postgres**. Chỉ reset schema bên trong DB tạm được tạo, cleanup `try/finally` cả setup failure/timeout; không drop DB admin.
4. Hai module phải cách ly (mỗi module DB riêng hoặc orchestrator tương đương), cả khi parallel.
5. Negative tests: không DSN/Docker; DSN `postgres` hoặc không do fixture tạo; setup lỗi giữa chừng; hai test modules chạy cùng lúc. Assert DB ngoài fixture bất biến.
6. Ghi opt-in và safety trong test README; chạy probes container/DB tự tạo, so DB/schema trước-sau; không log secret.

**DoD:** không còn đường mặc định xóa `public` của shared DB; test DB random/isolated/cleanup; negative safety tests đạt; hai module không reset lẫn nhau; có bằng chứng isolation/teardown. Không tự cài thêm runtime dependency khi công cụ sẵn có đủ.

### WP-03 — Đồng bộ tests với strict matrix contract
**File:** `test_finalize.py`, `test_finalize_display_contract.py`; chỉ sửa repository nếu chứng minh bug mới. **Lý do:** E14–15 trái E06.

1. Đọc `fetch_matrix_raw` và `get_answers_matrix`: đúng 1 config, N versions finalized, đủ `version × display_no`, key A–D, alias nhất quán, **không fallback**.
2. Đổi `test_f03_empty_answer_keys_fallback_to_version_questions` thành mong 409 `ERR_INCONSISTENT_ANSWER_KEYS`, dù version_questions có key. Đổi `test_f11_matrix_normalizes_lowercase_and_whitespace_keys` thành từ chối `'a'`/`'  a  '`, positive-control `A`–`D`; nếu muốn normalize policy mới, hỏi owner.
3. Bổ sung fixtures có `generation_configs`, `is_finalized=true`, đủ sources/N×M keys. Cover empty/missing/duplicate/extra keys, key E, alias `display_no/question_no` và `display_correct_key/correct_option` mismatch, missing source, wrong N, unfinalized, duplicate codes, version lạc session, bool/string `question_no`.
4. Positive assert **từng ô**, natural numeric sort; HTTP 409 đúng error code, không 500.
5. Chạy `python -m pytest backend/tests/services/test_finalize_display_contract.py backend/tests/api/test_finalize.py -q`, báo passed/failed/skipped; không ẩn test.

**DoD:** test khớp strict behavior, positive/negative từng invariant; focused tests xanh non-skipped; không sửa shuffler/exporter ngoài scope.

### WP-04 — Guard display keys trong cùng SQL007 transaction
**File:** `backend/migrations/007_finalize_approve_session_rpc.sql`, `backend/tests/migrations/test_finalize_readiness.py`, real-DB tests, `finalize/repository.py` error mapping. **Lý do:** E07/E08 không kiểm keys, có thể approved nhưng matrix 409.

1. Đọc SQL006 `answer_keys` columns, alias trigger, unique `(version_id,display_no)`, `_review_progress`, rồi so với Python strict matrix.
2. Dựng **positive PostgreSQL fixture**: 1 config N, M>0 confirmed/ready sources, N versions, N×M approved current candidates, không op active, tất cả finalized và N×M keys hợp lệ. Approval **phải pass** trước khi negative tests; không lấy `REVIEW_SOURCE_MISMATCH` làm chứng cứ key guard.
3. Trong `finalize_approve_session` **sau `exam_sessions FOR UPDATE`, trước UPDATE/audit**, kiểm mỗi version đủ duy nhất positions `1..M`, không dư/thiếu; `question_no=display_no` đúng range; `correct_option=display_correct_key ∈ {A,B,C,D}`; `canonical_question_no` ánh xạ nguồn hợp lệ. Chỉ áp dụng permutation bijection sau khi đối chiếu writer/schema đủ căn cứ. Không suy keys từ `version_questions.correct_key`.
4. Guard + approve + APPROVE_ALL audit cùng transaction. Nếu dùng `ERR_INCONSISTENT_ANSWER_KEYS`, map error về HTTP 409 an toàn trong repository; không rò raw SQL.
5. Negative tests **các precondition khác đều hợp lệ**: empty/missing/extra/duplicate key, invalid A–D, aliases conflict, canonical mapping sai; assert status vẫn reviewed, `approved_at NULL`, không audit mới. Audit insert fault phải rollback toàn bộ.
6. Positive/retry: 1 approval + 1 audit, replay timestamp/audit bất biến. Không tự yêu cầu revalidate khi đã approved nếu chưa chốt policy.
7. **Dừng ở EXT-01:** không assert `answer_keys.correct_option = version_questions.correct_key` nếu chưa biết trường version question canonical/display; không tự sửa writer. Nếu SQL007 đã deployed, hỏi EXT-03 trước khi sửa historical migration. Chỉ chạy trên DB WP-02.

**DoD:** positive thực đạt; thiếu/sai keys bị từ chối bởi **SQL007** trước commit, không đổi status/approved_at/audit; DB rollback/alias/error mapping test đạt; ghi giới hạn structural ≠ value semantics; có PostgreSQL version/HEAD/logs.

### WP-05 — F16: kiểm vai trò, JWT/actor spoofing
**File:** SQL007, test PostgreSQL role/ACL; **không** sửa SQL006 grants. **Lý do:** SQL007 suy `service_role` từ claim GUC và nhánh đó tin `p_user_id`; **chưa kết luận** exploit production.

1. DB tạm: user A owner, B nonowner, session ready; roles `authenticated`, `anon`, `service_role` theo harness. Positive authenticated A và service_role hợp lệ; negative B mang sub B nhưng `p_user_id=A`, anon/no JWT; assert state/audit.
2. Adversarial **local only**: `SET ROLE authenticated`, thử GUC `request.jwt.claim.role='service_role'` hoặc JSON claims role service_role + sub B, gọi approval với `p_user_id=A`. **Phải bị chặn**; nếu được approve, ghi reproducer/SQLSTATE, đánh dấu security blocker.
3. Nếu bypass: sửa theo principal **được DB thực sự xác thực** (không tin claim tự đặt); đọc SQL006 auth convention, hỏi Hùng/DB owner nếu thiếu PostgREST runtime contract; **không** nới ACL hoặc bỏ actor check.
4. Test legacy/JSON claim, malformed/missing sub, forged p_user_id, owner/nonowner, direct EXECUTE, approved replay; audit actor phải khớp identity đã xác thực.

**DoD:** A/B/anon/service role thật được kiểm PostgreSQL; không bypass owner/role; nếu còn bypass → `BLOCKED`, không merge; báo ranh giới SQL harness vs real JWT/PostgREST.

### WP-06 — Python prechecks, receipts, errors và idempotency
**File:** `finalize/repository.py`, `finalize/service.py`, API/service tests. **Lý do:** SQL007 là authority, Python có khác biệt logic.

1. Python config check đang chỉ dùng `len(set(n_versions))>1`, có thể chấp nhận nhiều config cùng N; đổi sang `count=0 → ERR_CONFIG_NOT_FOUND`, `count≠1 → ERR_CONFIG_AMBIGUOUS`, `count=1` mới chấp nhận. Test duplicate cùng N kể cả DB constraint chặn thông thường.
2. SQL007 chỉ approve `reviewed`; sửa docstring/message/test Python còn ghi `generated` được approve; không nới SQL.
3. Strict receipt: `status='approved'`, session ID đúng, timestamp string hợp lệ, schema đúng; negative `{}`, `[]`, `None`, denied, wrong session, invalid/missing timestamp, 2 rows; fail-closed.
4. Map `ERR_CONFIG_NOT_FOUND`, `ERR_CONFIG_AMBIGUOUS`, `ERR_NOT_ALL_QUESTIONS_APPROVED`, `ERR_VERSIONS_NOT_FINALIZED`, `ERR_QUESTION_REGENERATING`, `ERR_INCONSISTENT_ANSWER_KEYS`, `ERR_INVALID_SESSION_STATE`, `ERR_UNAUTHORIZED`, `PGRST202`, `42501`, timeout; không trả raw SQL/secrets qua HTTP.
5. RPC missing/permission/timeout/malformed receipt → không table-write fallback; transaction timeout có thể đã commit, không tự giả rollback hoặc refund. Kiểm approved retry giữ timestamp + chỉ 1 APPROVE_ALL audit trong DB.
6. Check router UUID trước ownership (400), missing auth (401), nonowner (403/404), review mutation sau approve (423); chạy focused tests.

**DoD:** Python/SQL nhất quán config/status; malformed receipt fail; error mapping an toàn; RPC-only; idempotency được DB chứng minh; không đụng ReviewRepository/SQL006.

### WP-07 — F01/F06 concurrency, recovery và immutability
**File/contract:** `services/review/{repository,service}.py`, `api/routes/review.py`, SQL006, `docs/api/review-rpc-contract.md`, [review Đạt F06](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/33#pullrequestreview-5745235554). **Lý do:** `dev` đã thay recovery thành RPC worker-only.

1. Kiểm Python recovery gọi `review_recover_session` bằng worker client; không đọc `review_operations` bằng owner SELECT hoặc đoán op từ `question.regeneration_id`/ID câu.
2. Trên DB WP-02, tạo **operation qua owner reservation RPC thật** với confirmed source/snapshot đúng SQL006 (không INSERT fake ledger bypass ACL). Cho hết hạn với `regeneration_id=NULL`; worker recovery phải đóng ledger + audit/state nhất quán, repeat idempotent; public progress không báo recovered giả.
3. Sau recovery reserve mới thành công; late completion op A đã recovered không đè op B, không double audit/quota.
4. Hai connections độc lập với barriers: mutation giữ parent lock trước approval → approval đợi/đọc trạng thái sau mutation; approval commit trước Accept/Reject/Revert/recovery-completion → mutation bị chặn, content/keys/is_finalized/audit không đổi.
5. Inject lỗi audit/invalidation trong RPC: toàn transaction rollback. Gắn từng repro cũ F01/F06 với kết quả exact head; **không kết luận shuffle writer** đạt nếu EXT-01 chưa có. Không coi Python asyncio.Lock là DB serialization.

**DoD:** F06 repro đã bị chặn thật; hai interleavings có assert session/versions/keys/ledger/quota/audit; replay/fault rollback đạt; không nới private ledger hay khôi phục fallback; báo phạm vi review+approval, không shuffle E2E.

### WP-08 — Parity offline: shuffler → matrix → exporter
**File:** `services/shuffler/{service,schemas}.py`, `services/exporter/{bundle_models,export_pipeline}.py`, tests. **Lý do:** code TASK-303/306/307 đã merge; chưa cần DB writer để so logic.

1. Đọc `display_no`, `display_correct_key`, `canonical_question_no`, `permutation_map`, `solution_md`, canonical fields và alias serialization.
2. Chạy shuffler thật cho ≥2 mã đề, ≥3 câu, có permutation câu/options khác nhau, seed kiểm soát. Assert canonical input bất biến, displayed key/solution đồng bộ.
3. Map output thành `AnswerKeyRecord`/fixture hiện có, đưa qua matrix repository/service, assert từng `version × display_no`.
4. Dựng `ApprovedExportSnapshot` **từ cùng fixture trong memory**; so rendered options/key/solution và matrix PDF/source nếu CLI có sẵn. CLI thiếu → unit renderer, đánh dấu skipped, không gọi E2E.
5. Negative: canonical key nhầm display, đảo key giữa mã đề, thiếu/trùng slot, solution chưa cập nhật. Ghi rõ lỗi nào thực sự bị bắt.
6. **STOP EXT-02** khi cần locked DB revision/mapper, không tạo giả revision hoặc exporter endpoint/storage.

**DoD:** offline parity từng ô cho 2 mã; canonical giữ nguyên, negative controls; phân biệt module offline và locked DB export.

### WP-09 — PostgreSQL migration chain fresh/legacy/replay
**File:** `backend/tests/migrations/{README.md,test_review_migration_chain.py,test_finalize_readiness.py}`; SQL007. **Lý do:** harness PostgreSQL 15 đã có và các upstream SHA đã pin.

1. Xác minh bằng `git ls-tree origin/dev backend/migrations` rằng 004/005 có/không merge. Chain pinned: 004/005 `2f6840d42c87d04f55e12d25c1bdd71c9481c652` → local SQL006 `dev` → SQL007 `HEAD` (không coi pinned SHA là production).
2. Chạy trên PostgreSQL 15 **DB tạm WP-02**/`PostgresCase` Docker case UUID: fresh schema → chain; legacy fixture → chain ở DB khác.
3. Verify SQL007 DDL/replay (APPROVE_ALL enum, review_logs nullable audit, role/grants/SECURITY DEFINER, FK/actor) và preserve receipts, quota, audit; khi gặp SQL008/ledger mơ hồ phải fail-closed, không backfill giả/xóa history.
4. Run actual migrations/ACL/rollback/idempotent replay; include active review denies approval, approved denies review mutation; nếu `asyncpg` skip, không tính pass.
5. Nếu đã deploy 006/007 ngoài test, hỏi EXT-03 về forward-only/repair; không tự rewrite applied migration hoặc chạy DB shared.

**DoD:** logs phân biệt fresh/legacy/replay, PostgreSQL version và commit SHAs; preserve data/ledger và rollback; real DB cases non-skipped; không đụng cloud/shared.

### WP-10 — Full regression, CI và release gate
**Lý do:** mọi CI công cụ đã có; chỉ chạy **sau WP-02**.

```bash
python -m ruff check backend/app scripts/blueprint
python -m ruff check backend/tests/api/test_finalize.py backend/tests/services/test_finalize_display_contract.py
python -m mypy backend/app --ignore-missing-imports
git diff --check origin/dev...HEAD
python -m pytest backend/tests/api/test_finalize.py --collect-only -q
python -m pytest backend/tests/api/test_finalize.py backend/tests/services/test_finalize_display_contract.py -q
# PostgreSQL migration test harness tự tạo container/DB riêng:
RUN_POSTGRES_MIGRATION_TESTS=1 python -m unittest discover -s backend/tests/migrations -v
# Chỉ sau WP-02: DB riêng và đúng env opt-in ghi trong README:
python -m pytest backend/tests/services/test_finalize_real_db_integration.py backend/tests/services/test_review_real_db_integration.py -q
python -m pytest backend/tests scripts/blueprint/tests -q
```

Windows PowerShell cho migration suite:
```powershell
$env:RUN_POSTGRES_MIGRATION_TESTS = '1'
python -m unittest discover -s backend/tests/migrations -v
Remove-Item Env:RUN_POSTGRES_MIGRATION_TESTS
```

1. Ghi `passed/failed/skipped` **từng suite**, đặc biệt PostgreSQL. Không tính skip là DB evidence.
2. `git diff --name-only origin/dev...HEAD`: tránh kéo ReviewRepository/SQL006 cũ; mọi file ngoài scope phải giải thích.
3. Commit tách nhóm: (a) CI/fixture, (b) DB isolation, (c) SQL007/finalize, (d) docs; không force-push. Push chỉ nhánh PR #33 nếu được giao quyền.
4. Chạy/kiểm GitHub Actions **trên exact final HEAD**: backend, frontend, Docker. Lỗi nào sửa đúng nguyên nhân; không disable tests/assertions. Lưu commands, OS/Python, PostgreSQL 15 image, SHA, logs và URLs, không secrets.

**DoD:** backend+frontend+Docker SUCCESS cùng SHA; collection, focused, full, PostgreSQL **thực chạy và pass**, Ruff/mypy/diff check đạt; không scope creep; báo cáo có evidence. Một job fail → `WP-10 NOT DONE`.

### WP-11 — Docs, PR handoff và re-review
**File:** `docs/tasks/{TASK-305.md,TASK-305-implementation-plan.md,PLAN_FIX_F01_TASK305.md}`, PR body, `finalize/repository.py` (UTF-8). **Lý do:** body còn head `75e6981`, 501 tests, fallback matrix, “không sửa schema”; code hiện khác.

1. Cập nhật HEAD/base, scope thực: SQL007 approve/audit/matrix strict; SQL006/review lifecycle đã thuộc `dev` sau PR #28, không nhận credit sai.
2. Sửa claims: SQL007 có đổi enum, review_logs, grants/functions; không nói “không sửa schema”. Không còn fallback matrix. SQL007 chỉ approve `reviewed` (không phải `generated`). Chưa xác nhận cloud deploy.
3. Thay pass counts lịch sử (`501/501`, `13/13`, v.v.) bằng **kết quả chạy exact final SHA** kèm skipped/limit. Sửa mojibake `Ma tr?n ??p ?n...` thành Unicode UTF-8, test/lint.
4. Finding register F01/F03/F06/F16/F19: link review + exact repro/CI + `author fixed / locally verified / awaiting independent review`; không tự ghi `reviewer verified`.
5. Phân biệt module offline exporter và real DB locked snapshot còn blocked. Đưa known external gates và links vào PR body.
6. **Chỉ sau WP-10 đạt**, và chỉ nếu được quyền GitHub write: đăng comment ngắn nhờ Đạt re-review trên HEAD SHA mới với log/Actions; không Approve/merge. Cần câu hỏi owner thì dùng PR Conversation, không tự gửi tin/đăng ngoài phạm vi quyền.

**DoD:** docs/body và UTF-8 đúng code/HEAD, finding có evidence và status chính xác, yêu cầu re-review đúng quyền; không claim production/E2E/approval.

## 4. External gates — phải hỏi owner, không tự bịa

**EXT-01 — Tâm `@AI-WFox` / TASK-303.** Đã có core shuffler/aliases, **chưa xác nhận writer**. Cần link PR/commit và xác nhận: (1) endpoint/hàm thực sự ghi `version_questions`, `answer_keys`, `exam_versions.permutations`, seed, `is_finalized` và owner triển khai nếu chưa có; (2) `version_questions.question_no/correct_key` mang display hay canonical semantics và đồng bộ với `answer_keys` thế nào; (3) ghi toàn bộ trong **một transaction** có parent `exam_sessions` lock/status/approved_at guard hay chưa; (4) fail/retry/concurrent approve/idempotency và tests thật. **Được làm trước:** structural SQL guard, unit/fixture parity; **không được khẳng định:** key-value parity với DB writer, atomic shuffle, E2E.

**EXT-02 — Owner TASK-307/308/export.** Có `ApprovedExportSnapshot` nhưng thiếu DB mapper/locked revision. Cần: (1) owner, PR/commit/interface `approved DB → locked display snapshot → ApprovedExportSnapshot`; (2) revision/DB read transaction/RPC dùng chung cho matrix, exams/solutions, PDFs, TeX/MD, download; (3) fail-closed/error code khi thiếu/sai keys hoặc source thay đổi, và chính sách mismatch với rendered options. **Không tạo giả revision/endpoint/storage hoặc dùng hai nguồn đáp án.**

**EXT-03 — Hùng `@benalexx007`/DB owner.** Cần bằng chứng thực về env nào đã apply 006/008 cạnh tranh/007 cũ; schema migration history, constraints, operations/attempts/logs/keys, quota/receipts/legacy; nếu đã apply, ai sở hữu forward-only migration, rollback/data repair. **Không** rewrite ledger/reset quota/backfill actor/canonical đoán mò/drop shared schema/apply cloud.

**EXT-04 — Đạt `@Thanhdat3010`/reviewer.** Sau WP-10, cung cấp HEAD, backend/Docker URLs, F01/F06/F16/F19 repro, strict keys/approval guard, PG evidence; xin review **exact head** và GitHub Approve. Approve PR khác không thay #33.

## 5. Acceptance matrix — 22 ca bắt buộc

| Test | Điều kiện/tác động | Kết quả bắt buộc |
|---|---|---|
| T01 | `test_finalize.py` collect | Không ImportError; không bỏ tests. |
| T02 | Không test DB | Không xóa `postgres.public`; fail/skip an toàn. |
| T03 | DSN không do fixture tạo | Chặn trước destructive DDL; DB ngoài fixture bất biến. |
| T04 | Hai real-DB modules cùng lúc | Không xóa tables của nhau. |
| T05 | Matrix N=2, M=3, 6 display keys | Codes 101/102; 3 rows, đúng cả 6 ô. |
| T06 | `answer_keys=[]` nhưng version_questions có key | 409 `ERR_INCONSISTENT_ANSWER_KEYS`, không fallback. |
| T07 | Missing/duplicate/extra/alias mismatch/key E | 409 hoặc DB constraint; không matrix. |
| T08 | Sai N, unfinalized, duplicate codes | Fail closed. |
| T09 | Ready sources/approved variants/finalized/keys đầy đủ | SQL007 approves + **1** APPROVE_ALL audit. |
| T10 | Keys rỗng; mọi guard khác pass | Approval fail, session/audit không đổi. |
| T11 | N=2,M=3, thiếu đúng 1 display slot | Approval fail, không partial commit. |
| T12 | Dư slot/alias conflict/key ngoài A–D | Approval fail, zero side effects. |
| T13 | Approve rồi retry | `approved_at` giữ nguyên, không thêm audit/quota. |
| T14 | User B, `p_user_id=A` | Denied; không approve session A. |
| T15 | Authenticated giả claim `service_role` bằng GUC | Không nhận quyền service role; nếu bypass, security blocker. |
| T16 | Expired operation, `regeneration_id=NULL` | Worker RPC đóng ledger; reserve lại thành công, không phantom recovered. |
| T17 | A recovered, B active, A late completion | Không overwrite B, không double audit/charge. |
| T18 | Approval commit trước review mutation | Mutation denied/423; versions/keys/content bất biến. |
| T19 | Review mutation giữ lock trước approval | Approval đợi, đọc readiness mới, không approve sai. |
| T20 | Audit insert lỗi trong approve | Toàn bộ transaction rollback. |
| T21 | Hai mã shuffle order/options khác nhau | Display key khớp matrix/export; canonical bất biến. |
| T22 | PostgreSQL 15, 004/005→006→007 fresh/upgrade/replay | Data/ledger preserved, không backfill giả, ambiguous migration fail closed. |

**Không tính PASS:** T10/T11 fail do source chưa ready thay vì keys; fake/mock không thực thi DB nhưng gọi “atomic rollback”; real-DB suites đều skipped.

## 6. Mẫu báo cáo kết quả của agent

```markdown
# Execution report — PR #33 / TASK-305
- Worktree / branch:
- HEAD before → after / base dev:
- Changed files / commit(s) pushed (if authorized):

| WP | DONE / PARTIAL / BLOCKED | Evidence (SHA/command/log) | Remaining blocker |
|---|---|---|---|
| 00 | | | |
| 01 | | | |
| 02 | | | |
| 03 | | | |
| 04 | | | |
| 05 | | | |
| 06 | | | |
| 07 | | | |
| 08 | | | |
| 09 | | | |
| 10 | | | |
| 11 | | | |

| Test command | Environment | Passed | Failed | Skipped | CI/log |
|---|---|---:|---:|---:|---|

- DB isolation proof / DBs touched / cleanup:
- F16 role spoof outcome; review ACL unchanged:
- RPC-only/no fallback evidence:
- SQL007 keys preapprove positive+negative/rollback evidence:
- External confirmations pending: Tâm / export / Hùng / Đạt:
- Internal implementation completed? YES/NO
- CI + Docker success same HEAD? YES/NO
- PostgreSQL tests actually executed? YES/NO
- Ready for independent re-review? YES/NO
- Reviewer GitHub Approved? YES/NO
- Safe to merge under repo policy? YES/NO
```

## 7. Overall Definition of Done

- **P0:** WP-00..03 và WP-10 collection/CI; không còn import error, destructive DB fixture, hoặc test bị xóa/tắt để qua CI.
- **P1:** WP-04/05/06/07/09 có positive, negative và PostgreSQL non-skipped evidence; security bypass chưa sửa ⇒ **BLOCKED**. WP-08 chỉ nghiệm thu *offline fixture integration*, không gọi full export E2E.
- **WP-11:** docs/PR ghi đúng head/test outcomes; chỉ xin re-review sau CI xanh, không tự nhận Đạt Approve.
- **EXT:** hỏi owner và chặn đúng dependency; im lặng không phải xác nhận. Không có cloud deployment/merge/approval trong DoD của coding agent.

**Giới hạn:** Hoàn thành các WP nội bộ không đồng nghĩa đã kiểm toàn bộ `shuffle writer → immutable approved DB snapshot → matrix/API/export`, hoặc có đường nâng cấp an toàn cho các database đã triển khai. Những điều đó cần xác nhận owner và bằng chứng riêng.
