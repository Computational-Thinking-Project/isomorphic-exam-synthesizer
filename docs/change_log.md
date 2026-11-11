## DEC-W4-MVP-03: Review Read API và Atomic Snapshot RPC (08/11/2026, proposed - remediated 09/11/2026)

- **Mã & Tiêu đề:** `DEC-W4-MVP-03: Review Read API / Current Candidate Snapshot`.
- **Ngày & Người đề xuất:** 08/11/2026 (cập nhật 09/11/2026 theo review) — Senior Backend Engineer cho Duy (BE owner).
- **Ngữ cảnh & Vấn đề (Context):**
  - Giao diện Stage 3 (Review FE - `htbaax`) cần hiển thị đầy đủ ma trận $N \times M$ slots ($N$ phiên bản đề $\times M$ câu nguồn đã xác nhận).
  - Trước đây chưa có endpoint đọc snapshot tập trung: frontend phải gọi các API rời rạc hoặc suy đoán câu hỏi hiện hành từ `exam_versions`, dễ gây sai lệch candidate cũ/mới (đặc biệt sau targeted regeneration, revert và F5).
  - Cần bảo đảm tính nhất quán nguyên tử (single-transaction atomic snapshot), bảo vệ quyền sở hữu (owner authorization không dùng `service_role`), và ẩn hoàn toàn tài nguyên không thuộc sở hữu người dùng (RLS concealment trả về `404 Not Found`).
- **Quyết định mới (Decision):**
  1. **Migration 018 (`backend/migrations/018_review_current_snapshot.sql`):** Bổ sung PostgreSQL read-only RPC `public.get_review_current_snapshot(p_session_id uuid) RETURNS jsonb` với `SECURITY DEFINER` và khai báo `STABLE` (lock-free owner verification trên `exam_sessions WHERE user_id = auth.uid()`). Không dùng lock `FOR SHARE`/`FOR UPDATE` trên session row, đảm bảo non-blocking MVCC statement snapshot nhất quán và che giấu session ngoại lai (404 Not Found) mà không gây tắc nghẽn với writer đồng thời. Tách hàm reader riêng `_get_source_artifacts_data` và cập nhật `_review_progress` thành `STABLE`.
  2. **Frozen Canonical Sources & Immutable Canonical Candidates:** Nguồn được đọc từ `generation_job_snapshots.snapshot_payload->'confirmed_sources'`, chuẩn hóa options 4 phần tử [A, B, C, D], không đọc live table để tránh lệch revision. Candidates được chiếu từ các trường bất biến `canonical_options`, `canonical_correct_key`, `canonical_solution_md` nhằm miễn nhiễm với display shuffle hay reset khi tái sinh.
  3. **Current-Only Candidate & Fail-Closed Guard:** Chỉ đọc candidate có `is_current = true`. Bổ sung kiểm tra version scope ($1..N$), canonical question mapping (`canonical_question_no` khớp `question_no` nguồn) và kiểm tra duplicate candidate. Mọi vi phạm lập tức fail-closed với mã lỗi `503 Service Unavailable`.
  4. **Lifecycle & Status Compatibility:** Bổ sung trạng thái `regenerating` vào schema DTO và contract, tương thích với enum `public.question_status`. Snapshot vẫn đọc được an toàn khi có candidate đang sinh lại (với `ready = false`).
  5. **Authoritative Readiness Consensus:** Tái sử dụng kết quả từ `public._review_progress(s.id)` để xác định `progress.ready` và đối soát `expected_slots`, bảo đảm không tồn tại hai định nghĩa readiness mâu thuẫn giữa Read API và Write API.
  6. **Deterministic Freshness Token:** Băm SHA-256 trên toàn bộ payload response chuẩn (trước khi gắn token), bảo đảm token thay đổi ngay lập tức khi bất kỳ trường dữ liệu nào trong snapshot thay đổi (candidate status, options, solutions, warnings, validation, v.v.).
  7. **Preserve Write API Exception Mapping & Sanitized Malformed Handling:** Phân định ngữ cảnh RPC trong `_map_rpc_exception` (`rpc_name = get_review_current_snapshot` trả 503 cho `REVIEW_SOURCE_MISMATCH`, trong khi Write RPCs giữ nguyên mã lỗi 422 `ERR_INVALID_PAYLOAD`). Schema validation error tại service layer được bắt và trả về mã lỗi 503 `ERR_SNAPSHOT_MALFORMED` với thông điệp an toàn, không rò rỉ chi tiết nội bộ của Pydantic ra ngoài client.
  8. **Authorization Boundary:** Loại bỏ preflight `assert_ownership` tại route GET snapshot, để database RPC làm authoritative security boundary và trả về `REVIEW_NOT_FOUND` (HTTP 404) nhằm che giấu sự tồn tại của session ngoại lai (RLS concealment).
- **Phạm vi ảnh hưởng (Impact):**
  - Cập nhật `backend/migrations/018_review_current_snapshot.sql`.
  - Cập nhật `backend/app/models/schemas.py`, `backend/app/services/review/repository.py`, `backend/app/services/review/service.py`, `backend/app/api/routes/review.py`.
  - Cập nhật `docs/api/review-snapshot.md`, `backend/tests/fixtures/review_snapshot/`.
  - Cập nhật `backend/tests/api/test_review_snapshot.py` (22 tests) và `backend/tests/migrations/test_review_snapshot_pg.py` (23 real PostgreSQL tests).
  - Handoff contract cho Stage 3 Review FE (`htbaax`) và resume routing (Philip).

## DEC-DOCS-INPUT-20261109: Đối chiếu yêu cầu và bàn giao input (proposed)

- **Ngày / người đề xuất:** 09/11/2026 — Trung Anh / philip-kkk, PM hỗ trợ soạn theo yêu cầu.
- **Trạng thái:** đã sửa tài liệu local để review; chưa xác nhận nhóm chấp nhận hoặc rollout. Sửa đổi INPUT-20261109 trên nền workflow v0.1; không đổi ngầm quy tắc giữa vòng review đang chạy.
- **Ngữ cảnh:** audit thảo luận GitHub chốt 16:42:46 UTC+7 ngày 09/11 cho thấy trả lời lệch ID và nhầm mức quyết định/đã giao/đủ dùng/đã tích hợp. Chưa có bằng chứng thay đổi này giảm số vòng trao đổi.
- **Đề xuất:** ID input ổn định, yêu cầu có mục đích/điều kiện đủ dùng, người giao/nhận, need-by/ETA; reply đúng ID kèm artifact/phiên bản và phần còn thiếu; consumer xác nhận phạm vi dùng được. Các mức Requested/Decided/Delivered/Accepted/Integrated chỉ dùng khi phù hợp. Một nơi tổng hợp M2 hoặc comment đang dùng; M1/M3/PR dẫn link, không sao chép trạng thái.
- **Phạm vi ảnh hưởng:** `docs/review/WORKFLOW.md`, `docs/review/TEMPLATES.md`, `.github/pull_request_template.md` và mục log này. M1 đã có người giao/nhận/dependency/ETA; chỉ thêm hướng dẫn dẫn ID. Chưa có căn cứ dùng Issue task template làm nguồn giao việc chính nên giữ nguyên.
- **Giới hạn:** không đổi task/owner/deadline/MVP/kiến trúc, code hoặc gate approve/merge; các PR hiện có không tự được cập nhật. Bản local chưa commit/push hoặc đăng GitHub từ lượt sửa này.
## DEC-DAT-W4-OPS-CI — OPS regression coverage (09/11/2026)

- PR51 review fix: CI chạy OPS unittest và Ruff cho `scripts/w4_ops.py`, `scripts/test_w4_ops.py` trên mỗi PR/push thuộc workflow hiện hành.
- Proxy observation kiểm JSON OpenAPI3.x và routes backend qua `/openapi.json`, tránh SPA fallback báo PASS nhầm. Không đổi API/schema, runtime hay Docker; kết quả vẫn không thay integrated acceptance.

## DEC-DAT-W4-OPS — Production private beta preparation

- Ngày/người:08/11/2026 — Đạt cập nhật theo [quyết định Duy](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/51#issuecomment-6719017111), [ENV0 Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53).
- Chọn một production HTTPS/private beta chỉ nhóm, free-first; không yêu cầu staging riêng. Static Compose một worker, private access gate thực, isolated destructive tests. Không chọn provider/mua dịch vụ/cấp quyền hoặc xác nhận lịch trực.
- Ảnh hưởng: docs OPS11/21 và candidate inventory017; historical inventory giữ nguyên, không sửa runtime/API/SQL/Docker. PR51 preparation merge độc lập deployment acceptance; G0/G1/G2/public proof vẫn pending. PR30 F02 và PR52 ACL/real-DB còn blockers.

## DEC-DOCS-W4-001: Đồng bộ hóa tài liệu W4 theo Review M4 và Quyết định Sản phẩm (08/11/2026, proposed)

- **Ngày / người đề xuất:** 08/11/2026 — Duy (PR #50), theo review M4 của Đạt (@Thanhdat3010).
- **Ngữ cảnh & Vấn đề:** Tài liệu kiến trúc, mô tả và kế hoạch còn chứa mô tả cũ mâu thuẫn với các quyết định kỹ thuật đã chốt: (1) Trích xuất Blueprint chạy trước Source Confirmation và còn checkbox an ninh bắt buộc của người dùng; (2) Stage 2 cho phép chọn variation modes và giao diện shuffle Stage 3 mô tả mutually exclusive; (3) Fallback sau retry và Revert tự động duyệt `approved` hoặc cho phép xuất bản candidate lỗi; (4) Tên file `W4_ASSIGNMENT (1).md` gây lỗi liên kết; (5) Chưa làm rõ trạng thái của đề xuất 3–5 sao; (6) Yêu cầu staging server riêng mâu thuẫn với quyết định mới tại Issue #53.
- **Quyết định mới:**
  1. **F01 (ADR-0001 / Issue #44):** Đồng bộ hóa thứ tự chuẩn: Ingest $\to$ Source Preview (read-only) $\to$ Confirmation (khóa nguồn & persist snapshot) $\to$ Kích hoạt Canonical Blueprint $\to$ Canonical Ready $\to$ Stage 2. Loại bỏ hoàn toàn hộp kiểm cam kết an ninh của người dùng (giữ server-side silent audit).
  2. **F02 (Issue #45):** Stage 2 chỉ chọn $N \in \{1, 2, 3, 4\}$ và hai checkbox xáo trộn độc lập (câu, đáp án) mặc định tắt (`false`/`false`), hỗ trợ 4 tổ hợp hợp lệ. Không hiển thị UI chọn variation modes (backend tự suy ra từ canonical Blueprint). Cấu hình xáo trộn hiển thị lại và cho phép cập nhật ở Stage 3 trước khi bấm final shuffle.
  3. **F03 (Issue #46):** Thử tối đa 4 lần (1 initial + 3 retries). Hết 4 lần thất bại: dùng confirmed source revision làm fallback với trạng thái `pending_review`, `has_warning = true`, `GENERATION_RETRIES_EXHAUSTED` (bắt buộc giảng viên duyệt lại, không tự động approved). Revert cũng về confirmed source revision và trả về `pending_review`. Nguồn thiếu đáp án hoặc lời giải bắt buộc cho downstream/export thì fail-closed.
  4. **F04:** Chuẩn hóa tên file thành `docs/tasks/W4_ASSIGNMENT.md`, cập nhật metadata bản v2.1 và snapshot PRs.
  5. **3–5-star verification:** Đánh dấu rõ trạng thái `PROPOSED / DEFERRED PENDING RUBRIC APPROVAL` theo thẩm quyền của Duy và Tâm; không ép buộc vào Golden MVP baseline.
  6. **ENV0 (Issue #53):** Định hướng Production-first / Private Beta nội bộ nhóm, ưu tiên chi phí 0đ, không bắt buộc staging server riêng biệt.
- **Phạm vi ảnh hưởng:** `docs/architecture.md`, `docs/description.md`, `docs/planning.md`, `docs/tasks/W4_ASSIGNMENT.md`, `docs/tasks/W4_TASK_DETAIL.md`. Không thay đổi code runtime.

## 05/11/2026 — W2 AI policy: owner confirmations

Duy/BE và Bội Anh/FE đã xác nhận mode aliases/NONE theo các link trong [contract AI](ai-w2-integration.md). Đạt cập nhật policy status và acceptance fixtures; không đổi generator/worker/SQL. Quỳnh giữ clone branch, SQL/RPC snapshot và clone persistence đã merge qua PR32; worker integration vẫn do Quỳnh thực hiện; xác nhận policy không phải nghiệm thu triển khai/E2E.

## DEC-DAT-W2-HANDOFF: Contract hash/resume và public-mode proposal

- Ngày/người: 04/11/2026 — Trương Thành Đạt, theo yêu cầu phối hợp I-B-AI/I-B-POLICY trên PR30.
- Contract AI hiện có được làm rõ tại [ai-w2-integration.md](ai-w2-integration.md): ordered batch hash khác per-question revision hash, full QuestionResult/provenance và immutable job snapshot cần giữ khi resume. Fixture/test offline bàn giao cho owner worker/SQL.
- Guard cục bộ: completed candidate.seed phải khớp expected slot seed, không chỉ request fingerprint. Không đổi prompt, provider, retry hoặc quota.
- Checkpoint04/11 ban đầu proposed; policy aliases/NONE đã được owners xác nhận05/11. SQL/RPC snapshot/result và Original Clone đã merge qua PR32 (migrations015/016); worker/FE E2E vẫn pending. Không sửa SQL/worker/FE/gateway/Docker hay nhận W2 E2E đã đạt. [Scope/phối hợp](tasks/TASK-AI-W2-CONTRACT.md).

## TASK-204 PR #43 review findings F01–F03 — 06/11/2026 (proposed)

Migration 014 revokes application access to the legacy confirmation RPC.
The confirmation API checks the draft revision from one snapshot before source
completeness, and credentialed preflight accepts `Idempotency-Key` from configured
origins. See the [confirmation contract](api/confirm-source-endpoint.md).

## TASK-204 postreview P1/P2/P3 — 05/11/2026 (proposed)

Migration013 freezes source rows and warning flags once confirmed, preserving draft
clone/edit and parent cascade. Ingestion lock races map to409. Confirmation now
requires a stable UUID Idempotency-Key (missing422, malformed400); shared review
endpoints are unchanged. This is a breaking FE1 contract pending owner adoption
and F5/timeout persistence acceptance. Existing migrations are unchanged; no public
reset workflow, FE2/BE2 changes or deployment is introduced. See the
[confirmation contract](api/confirm-source-endpoint.md).

## DEC-TASK204-001: Atomic source preview revision and canonical mode profile (proposed)

- Date: 05/11/2026. Author implementation on `fix/be1-source-confirm-contract`;
  independent review and FE/BE2 integration acceptance pending.
- Context: updated_at can repeat and independently queried preview rows can mix
  revisions; canonical readiness and FE mode metadata used incompatible shapes.
- Decision: additive migration011 introduces a per-session source UUID, transactional
  mutation trigger, locked preview RPC and worker-only UUID confirmation wrapper.
  Migration012 extends the existing canonical readiness RPC with public profile1.0
  mode objects, pinned to BE2 `7e9377f`, without reading legacy Blueprint modes.
- Impact: sessions/confirm/artifact APIs, repository validation, offline PostgreSQL
  tests and [handoff](api/source-confirm-handoff.md). Historical migrations006–010
  are unchanged. Deploy011/012 and the updated API together; old timestamp caller
  access is revoked. Supabase/PostgREST/JWT/RLS, FE integration and GitHub approval
  are not established by local SQL evidence.

## DEC-BE1-016: Original Clone SQL persistence (local implementation, pending review)

- Date / owner: 05/11/2026, TASK-207 / Duy, PR #32. Source:
  [PR #30 integration requirement](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30#issuecomment-6635728977).
- Context: frozen W2 snapshots existed, but AI-only persistence could not store
  an honest Original Clone record for modes=[] or resume it after a restart.
- Decision: forward migration 011 adds persist_generation_clone, a result-kind
  discriminator and separate clone fingerprint in the existing result table.
  Frozen source and original display commit atomically; claim/resume/finish check
  exact current projections. Keep 010, AI result serialization/writer, owner/worker
  permissions, current-token fencing and session quota behavior.
- F12 remediation (06/11/2026, author implementation pending review): 011 wraps
  the unchanged 010 AI writer to reject clone-job AI success/failure before writes.
  Completed slots must match the frozen job's result kind. Claim/resume/finish
  report `55006 / ERR_CONFIG_CONFLICT` for historical wrong-kind rows, including
  failures; clone persistence preserves them for explicit reconciliation.
  New clone-job AI writes use the existing `22023 / ERR_CONFIG_CONFLICT` convention.
- Boundary: persist before shuffle. PR #30 owns Python record/adapter/worker,
  shuffle sequencing and answer/solution remapping. No AI validation/provider
  metadata is invented. No cloud writes, push, merge or review approval is implied.
- Evidence and limits: [local author handoff](tasks/TASK-207.md#original-clone-follow-up--local-author-handoff-05112026)
  and [RPC contract](api/generation-config-endpoint.md#original-clone-persistence-migration-011).
  Independent review, CI on a pushed head, worker integration and deployed E2E remain gates.
## 05/11/2026 — TASK-304: tiếp nhận vào dev qua TASK-301

Production adapter/schema/permit tests của PR26 đã có trên dev qua PR28. Đạt đồng bộ nhánh304, cập nhật [bàn giao](ai-w3-targeted-regeneration.md) và [trạng thái](tasks/TASK-304.md), không đổi production code hoặc contract. Consumer đã được kiểm tại31b7f4d; cloud/live Gemini/full product E2E vẫn là gate riêng.

## DEC-TASK305-001: Final approval display-key and principal guards (proposed)

- Date / owner: 04/11/2026, TASK-305 author; pending independent review.
- Context: a reviewed session could be approved without display answer keys; a
  caller able to set a JWT claim GUC could impersonate the service role in a
  local PostgreSQL test.
- Decision: migration 007 checks the structural display-key matrix under the
  session lock and uses the actual database role to identify service calls.
  Missing or inconsistent keys return `ERR_INCONSISTENT_ANSWER_KEYS` (HTTP 409).
  Matrix reads do not infer display answers from canonical questions.
- Impact: finalize SQL, repository, API and regression tests. The shuffle writer
  is implemented in migration 008, but its complete A+B gate, displayed-answer
  semantics, deployed PostgREST role behavior and immutable export integration
  remain unverified. Local PostgreSQL checks do not establish deployed behavior.

## 01/11/2026 — TASK-304: permit bền vững tại boundary dispatch (Draft)

Adapter real nhận operation_id và callback trả AttemptPermit, dùng hook gateway hiện có cho mỗi attempt/retry/repair. Không còn fallback local-only cho review production. DB ledger quyết toán; count adapter chỉ là acknowledged grants, không tự refund khi timeout/cancel hoặc mất response. [Handoff và giới hạn](ai-w3-targeted-regeneration.md), [điều phối #36](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6551270882). Đã triển khai phía adapter; RPC/wrapper/E2E còn phụ thuộc Hùng/Duy, shared contract chưa coi đã được mọi owner chấp nhận.

## DEC-DAT-W3-307: Boundary bundler và dependency template

- Cập nhật 01/11/2026 — Đạt: tích hợp Typst compiler đã merge từ TASK-306 qua `build_compiled_bundle`. Một validated display snapshot cấp dữ liệu cho toàn bộ PDF/ma trận/TeX/Markdown trước khi đóng ZIP; tái sử dụng `build_bundle`, lỗi compiler không trả gói thiếu. Không thêm DB/API/cloud/dependency/Docker. Kiểm tích hợp module bằng fixture, snapshot đã khóa và Storage E2E vẫn pending; [interface/handoff](export-w3-bundler.md).
- Ngày/người: 29/10/2026 — Đạt. ZIP theo phản hồi Duy tại PR #27.
- Triển khai: typed display snapshot, Jinja2 XeLaTeX/Markdown, ZIP bytes + SHA-256, không DB/AI/cloud. Thêm Jinja2/MarkupSafe vào dependency lock cho Docker hiện hành.
- Boundary/bytes/giới hạn cần owner Duy/Tâm/Hùng xác nhận khi ráp; không sửa API/SQL của owner khác. [Handoff](export-w3-bundler.md).
- Chưa nghiệm thu: XeLaTeX compile/layout và E2E snapshot/PDF/Storage thật.

## DEC-BE1-013: Caller review dùng durable receipts và action keys

- CI Pipeline run241 tại be80d1b: backend867 pass/9 skip, lint/typecheck79
  files và frontend build success. Thêm chín TestClient tests đi qua actual
  caller/repository; chỉ inject auth/ownership/RPC/provider, không scheduling.
  Kết quả thực thi các ca mới và Docker/final-head checks được ghi trên PR;
  không nhận JWT/RLS/SQL/concurrency thật từ các fixtures này.

- Tích hợp 04/11/2026: caller `55449fc` ghép dev `8bdc3b1`; giữ cả ADR bundler
  và caller khi giải conflict changelog, không thay code review. Kiểm sau ghép:
  review/exporter/shuffler245 pass/7 skip do thiếu Typst CLI, Ruff pass, mypy79
  files pass, full suite876 collect. Chưa full async/DB/HTTP/concurrency hoặc CI;
  P1–P4/R1/progress IDs và owner artifacts vẫn pending.

- Ngày: 04/11/2026; người triển khai: Duy (`johannguyen015`) qua TASK-301.
- Trạng thái: caller để review, chưa nghiệm thu producer/storage/DB/AI E2E hoặc deployed.
- Bối cảnh: enum reserve làm mất snapshot/replay; validation tự dựng evidence và failure
  RPC nhận exception text; các wrapper/table fakes cũ không khớp SQL authority.
- Thay đổi: typed receipts, strict evidence/counts, worker tách owner, frozen input,
  same-ID retry/settlement/reconciliation, không local ledger/CAS/direct lifecycle writes.
  Accept/Revert thêm optional Idempotency-Key; client cũ không gửi header vẫn dùng được.
- Authority: [review RPC contract](api/review-rpc-contract.md). P1–P4/R1 vẫn proposed;
  yêu cầu progress IDs trong cùng RPC snapshot cần owner TASK-302 xác nhận. Không thay DDL.
- Kiểm: 148 caller tests pass, Ruff/mypy pass; 772 tests collect. Fake RPC/scheduling
  không thay kiểm PostgreSQL/concurrency/ASGI/JWT. Full async local chưa kiểm do quyền
  chạy ngoài môi trường hạn chế bị từ chối; CI/DB checks vẫn bắt buộc trước merge.
- Phạm vi: review routes/service/repository/models cục bộ, regression tests và docs.
  Không sửa nhánh #36/#26, deploy cloud, approve/merge hoặc đóng finding thay reviewer.

## DEC-BE1-012: Đề xuất confirmed artifacts và frozen review payload

- Ngày: 04/11/2026; người đề xuất: Duy (`johannguyen015`).
- Trạng thái: tài liệu gửi thảo luận #36; chờ Hùng/Đạt xác nhận bổ sung. Chưa
  triển khai storage/producer/RPC payload v1 hoặc nghiệm thu caller/E2E.
- Bối cảnh: baseline #36 `a2d2fc3` freeze database_rows; #28 `39083c2` còn đọc
  nguồn sống/tính hash lúc Reject. Chưa có persistence đúng input canonical #26.
- Đề xuất: lưu exact confirmed input, per-question fingerprint và immutable
  revision; lưu validated canonical Blueprint gắn cùng revision/hash; reservation
  freeze artifacts cho adapter. Caller không tự dựng hash/Blueprint để bù thiếu.
  Recovery worker theo session trước mỗi Reject; GET progress/list giữ thuần đọc.
- Authority: [review RPC contract](api/review-rpc-contract.md), kế thừa baseline
  owner #36 và ghi riêng phần đề xuất. Sau thống nhất, cập nhật cùng authority
  của owner, không duy trì contract cạnh tranh.
- Phạm vi: tài liệu TASK-301, liên quan TASK-302/304/305 và producer cần điều phối;
  không tự phân công thêm thành viên hoặc sửa nhánh Hùng. Giữ SQL 004/005 → 006 → 007.
- Kiểm: đọc code/trao đổi đúng các commit ghim trong contract; kiểm link/diff.
  Không chạy product tests trong thay đổi docs, không nhận finding đã verified.

## 24/10/2026 — AI W2 (thay đổi cục bộ, chưa merge)

Gateway async dùng chung, xác nhận nguồn trước Blueprint, canonical core dùng chung CLI/backend, generator theo Blueprint kèm lời giải, bounded validation/retry, resume/callback và lifecycle. [Chi tiết và giới hạn nghiệm thu](ai-w2-integration.md). Chưa tích hợp routes/DB/SSE/UI W2; chưa nghiệm thu Docker/live API.

# Nhật Ký Quyết Định Công Nghệ & Thay Đổi Kiến Trúc (Architecture & Tech Change Log)

> Checkpoint tích hợp 26/10/2026: Auth PR #7 đã squash merge vào dev tại `bbb7c5e`. Nhánh TASK-103 đang ghép nền dev và giữ list/phân trang/Clone Modal thật; chưa lưu merge commit. Các mục DEC-TV1 bên dưới ghi đúng phạm vi lịch sử ở ngày thực hiện, không ghi đè bằng chứng hoặc nhận TASK-103 đã hoàn tất.

> **Mục đích:** Tài liệu này dùng để lưu trữ các **quyết định kỹ thuật (Architecture Decision Records - ADR)**, các thay đổi công nghệ hoặc điều chỉnh quy trình phát triển phát sinh trong quá trình triển khai dự án so với tài liệu thiết kế ban đầu.
> Khi dự án triển khai, mọi thay đổi về stack, quy ước code, cấu trúc thư mục hoặc luồng phối hợp giữa các thành viên đều cần được ghi chép tại đây để đảm bảo tính minh bạch và thống nhất cho toàn đội.

---

## 📋 Mục lục các Quyết định

- [DEC-TV1-004: Bộ hướng dẫn giao việc và review chung v0.1 — proposed](#dec-tv1-004)
- [ADR-001: Chuẩn hóa Model AI `gemini-3.5-flash-lite`, Schema Repair Pass và Kiến Trúc Black-Box Generator](#adr-001-chuẩn-hóa-model-ai-gemini-35-flash-lite-schema-repair-pass-và-kiến-trúc-black-box-generator)
- [DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend](#dec-tv1-001-chuẩn-bị-login-ui-và-kiểm-tra-frontend)
- [DEC-TV1-002: Tích hợp Google OAuth, profile và bootstrap Auth](#dec-tv1-002-tích-hợp-google-oauth-profile-và-bootstrap-auth)
- [DEC-TV1-003: Bổ sung DB cho Dashboard list/clone](#dec-tv1-003-bổ-sung-db-cho-dashboard-listclone)
- [DEC-TV6-001: Shared Docker development workflow](#dec-tv6-001-shared-docker-development-workflow)
- [ADR-002: In-Memory Pre-validation, Zero Cloud Mutation, và Atomic Ingestion Engine (TASK-202)](#adr-002-in-memory-pre-validation-zero-cloud-mutation-và-atomic-ingestion-engine-task-202)
- [DEC-BE1-003: Khắc phục Toàn Diện Phản Hồi Review PR #15 (Vòng 2)](#dec-be1-003-khắc-phục-toàn-diện-phản-hồi-review-pr-15-vòng-2)
- [DEC-BE1-004: Xử lý Triệt Để Ngoại Lệ Mạng và Khẳng Định Trạng Thái Commit CSDL (PR #15 Round 3)](#dec-be1-004-xử-lý-triệt-để-ngoại-lệ-mạng-và-khẳng-định-trạng-thái-commit-csdl-pr-15-round-3)
- [DEC-BE1-005: Chuẩn Hóa Bóc Tách Phương Án Bullet List Trong Parser Markdown & Text (PR #15)](#dec-be1-005-chuẩn-hóa-bóc-tách-phương-án-bullet-list-trong-parser-markdown--text-pr-15)
- [DEC-BE1-006: Khắc Phục Triệt Để Suy Luận Rollback CSDL & Ngoại Lệ Gateway (PR #15 / PR #16 Round 4)](#dec-be1-006-khắc-phục-triệt-để-suy-luận-rollback-csdl--ngoại-lệ-gateway-pr-15--pr-16-round-4)
- [DEC-BE1-007: Bảo Toàn Ranh Giới Câu Hỏi Bảng Nhiều Cột và Nhận Diện Bảng Đáp Án Ô Riêng Biệt (PR #15 Round 5)](#dec-be1-007-bảo-toàn-ranh-giới-câu-hỏi-bảng-nhiều-cột-và-nhận-diện-bảng-đáp-án-ô-riêng-biệt-pr-15-round-5)
- [ADR-003: Atomic Exam Confirmation và Blueprint Concurrency Protection (TASK-205)](#adr-003-atomic-exam-confirmation-và-blueprint-concurrency-protection-task-205)
- [DEC-BE1-008: Phân Loại Ngoại Lệ Mạng Phân Tán và Chuẩn Hóa Kiểm Quyền Migration 003 (TASK-205 Round 3)](#dec-be1-008-phân-loại-ngoại-lệ-mạng-phân-tán-và-chuẩn-hóa-kiểm-quyền-migration-003-task-205-round-3)
- [DEC-BE1-009: Loại Trừ PostgreSQL SQLSTATE Class 08 Khỏi Bằng Chứng Rollback CSDL (TASK-202 / TASK-205 Round 5)](#dec-be1-009-loại-trừ-postgresql-sqlstate-class-08-khỏi-bằng-chứng-rollback-csdl-task-202--task-205-round-5)
- [ADR-004: Tinh Giản Toàn Diện Stage 1 & Stage 2 Sang Kiến Trúc Black-Box, Silent Security Audit, và Chốt Nguồn Nguyên Tử Đơn Điểm](#adr-004-tinh-giản-toàn-diện-stage-1--stage-2-sang-kiến-trúc-black-box-silent-security-audit-và-chốt-nguồn-nguyên-tử-đơn-điểm)
- [DEC-BE1-010: Khắc Phục Triệt Để Fail-Closed Permit RPC, Strict Operation Binding, và Đồng Bộ Contract TASK-302 (TASK-301 F07 v3.0)](#dec-be1-010)
- [DEC-BE1-011: Chuyển Dịch Toàn Diện Review Lifecycle Sang Atomic PostgreSQL Stored Procedures và Kiểm Thử Trên CSDL Thật (Stage 3 Production-Ready)](#dec-be1-011)

---

## Chi tiết các Quyết định

<a id="dec-tv1-004"></a>

### DEC-TV1-004: Bộ hướng dẫn giao việc và review chung v0.1

- **Ngày soạn/người đề xuất:** 28/10/2026 — Trung Anh / philip-kkk / TV1.
- **Trạng thái:** proposed, chuẩn bị để review tài liệu và chọn pilot; chưa ghi nhận PR docs đã merge, toàn nhóm đã đồng bộ hoặc pilot đã chạy. Đây chưa phải ngày nhóm phê duyệt toàn bộ gói quy trình.
- **Ngữ cảnh:** phân công và review cần chung format, đúng phiên bản code, đầu vào có mốc giao rõ và phản hồi lỗi có bằng chứng để giảm chuyển lời/sửa lặp.
- **Phần đã được Trung Anh xác nhận:** Duy là leader; giao việc thứ 4 hoặc sáng thứ 5; thành viên/agent đọc, lập plan và tạo Draft PR để giải đáp trong thứ 5; code từ thứ 6; hạn đợt tối thứ 3 tuần sau. Mẫu leader phải có thứ tự task theo phụ thuộc, mốc cần input, ETA giao input và ETA xong task để task sau còn thời gian code/tích hợp/review/sửa. Chưa chốt giờ hạn hoặc ETA của task thật.
- **Nội dung gói đề xuất:** [WORKFLOW](review/WORKFLOW.md) là nguồn quy trình, [TEMPLATES](review/TEMPLATES.md) có 5 mẫu; hỏi input trên PR Conversation, finding/fix/verify trong cùng thread/ID; code head và kết quả kiểm được cập nhật cho từng lượt. Root AGENTS và hướng dẫn đóng góp dẫn về cùng nguồn.
- **Phạm vi ảnh hưởng:** `AGENTS.md`, `docs/review/WORKFLOW.md`, `docs/review/TEMPLATES.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`, `README.md` và mục này. Thành viên chỉ tạo file tuần/task khi có phân công thật, không bắt Issue hoặc thêm tracker cạnh tranh.
- **Giữ quy định hiện hành:** ít nhất 1 thành viên khác Approve, phối hợp owner, checks phù hợp/CI và quyền merge; verified của agent không thay GitHub Approve. Không thêm bot/messenger, token, CI mới hoặc branch protection.
- **Chờ xác nhận khi rollout:** PR/task pilot, hai owner, quyền cụ thể và cách xử lý bất đồng. Đề xuất chuyển người sau hai lần sửa cùng finding chưa đạt chưa phải luật bắt buộc. Cập nhật căn cứ chấp nhận và kết quả pilot khi thực sự có, không tự chuyển status thành active.

### ADR-001: Chuẩn hóa Model AI `gemini-3.5-flash-lite`, Schema Repair Pass và Kiến Trúc Black-Box Generator
* **Ngày quyết định:** 16/10/2026
* **Người đề xuất:** TV5 (AI Integration & Generator)
* **Bối cảnh:**
  1. Tài liệu ban đầu ghi model `gemini-2.5-flash`. Tuy nhiên, Google đã cập nhật dòng model thế hệ mới `gemini-3.5-flash-lite` với độ trễ cực thấp (khoảng 3s) và độ chính xác toán học cao hơn trên SDK chính thức `google-genai`. Model này không hỗ trợ custom temperature/top-p; việc bỏ tham số sampling tùy chỉnh giúp request luôn ổn định.
  2. Các công thức toán LaTeX (như `\pm`, `\frac`, `\sqrt`) trong phản hồi JSON từ LLM thường gặp lỗi escape ký tự `\` trái với chuẩn JSON của RFC 8259, dễ gây `json.JSONDecodeError` hoặc `ValidationError`.
  3. Giảng viên chỉ có nhu cầu chọn số lượng $N$ đề thi (Stage 02) và bấm tái sinh câu hỏi không đạt yêu cầu (Stage 03) chứ không can thiệp sâu vào cấu trúc Blueprint.
* **Quyết định:**
  1. Cấu hình biến mặc định `GEMINI_MODEL=gemini-3.5-flash-lite` trong `backend/app/core/config.py`.
  2. Xây dựng module `backend/app/services/ai/schema_repair.py` theo kiến trúc bảo vệ 2 lớp:
     - *Lớp 1 (Heuristic):* Tự động làm sạch markdown fences và chuẩn hóa escape backslash LaTeX (`sanitize_latex_backslashes`).
     - *Lớp 2 (AI-Assisted Repair Loop):* Nếu heuristic không đủ, tự động gửi lại phản hồi lỗi cho Gemini kèm thông tin Pydantic error để AI tái cấu trúc (tối đa 2 lần retry).
  3. Xây dựng `VariantGenerator` (`generator.py`) như một hộp đen tự động:
     - Gán seed ngẫu nhiên độc lập cho từng biến thể ở từng phiên bản đề thi để bảo đảm tính tái lập (reproducibility).
     - Hỗ trợ `regenerate_single_variant` kèm cơ chế **Feedback-guided Regeneration**: tiếp nhận feedback lý do từ chối từ tầng Validation (TV7) hoặc giảng viên để AI tránh lặp lại lỗi cũ.
* **Hệ quả / Tác động:**
  - 100% các unit test (11/11 tests) chạy độc lập siêu nhanh (< 1s) với Mock Client.
  - Smoke test với Google Gemini API thật đạt độ trễ ~3.05s với 100% độ chính xác Pydantic schema.
  - Backend Router (TV3) và Frontend (TV1/TV2) có thể cắm trực tiếp mà không cần cấu hình phức tạp.

### DEC-TV1-001: Chuẩn bị Login UI và kiểm tra frontend

- Ngày/người thực hiện: 16/10/2026 — Trung Anh, TV1.
- Bối cảnh: TASK-101 cần màn đăng nhập; frontend có script lint nhưng chưa có công cụ và cấu hình ESLint.
- Quyết định: bổ sung ESLint cho JavaScript/JSX và React Hooks, lockfile, trang /login và router đầu vào.
- Phạm vi ảnh hưởng: frontend package/config, App.jsx và features/auth/LoginPage.jsx.
- Giới hạn: nút Google chỉ hiển thị thông báo; chưa kết nối Supabase hoặc xác thực người dùng.
- Kiểm tra: mở/bấm/reload trang login; npm run lint và npm run build thành công.
- Bổ sung: auth store dùng Zustand, ProtectedRoute và trang thử /auth-preview chỉ trong development.
- Kiểm thử bổ sung: ba unit test cho auth store bằng Node test runner; thêm script npm run test.
- Giới hạn: phiên mẫu không lưu sau reload; chưa kết nối Supabase, Google login hoặc API thật.

### DEC-TV1-002: Tích hợp Google OAuth, profile và bootstrap Auth

- Ngày/người thực hiện: 19–23/10/2026 — Trung Anh, TV1; nhánh `feat/task-101-google-login`, PR #7 → `dev`, chưa nghiệm thu.
- Bối cảnh: thay phiên đăng nhập mẫu bằng Supabase Google OAuth; cần ghép profile của Duy, không xác nhận đăng nhập sản phẩm chỉ bằng việc nhận token. Project chung chưa có các đối tượng profile khi kiểm ngày 23/10.
- Quyết định: giữ một Supabase client, một Zustand store và một Axios API client. Frontend `/login` nhận OAuth redirect, khôi phục/theo dõi phiên; `profile_pending` tải `GET /api/users/me` trước khi mở Dashboard. Đối chiếu user ID/version để bỏ kết quả cũ sau đổi tài khoản, giữ profile khi refresh cùng user. Lỗi 401 refresh/retry tối đa một lần; 403/lỗi tạm được phân biệt. Navbar hiển thị tên backend, ảnh metadata của đúng phiên, fallback chữ viết tắt và SDK sign-out local.
- API không đổi: dùng trực tiếp `id/email/name/created_at`, không thêm avatar vào schema hoặc tạo backend riêng. Endpoint Duy có fallback claims khi query không có dòng; việc xác nhận trigger được kiểm riêng trên Supabase.
- SQL đã áp: `backend/scripts/setup_auth_profiles.sql` lấy bảng/FK/RLS/policy/function/trigger từ schema nhóm, thêm SELECT cho `authenticated` và bổ sung profile Auth đã có. TV1 và Duy cùng quản lý Supabase; TV1 báo đã áp ngày 23/10. Script chỉ dành cho project chưa có các đối tượng Auth, không phải migration chạy lại; khi triển khai schema còn lại cần tránh tạo lại đối tượng/policy trùng tên.
- Cấu hình: host Vite đọc `frontend/.env.local`, Docker đọc `.env` gốc; backend dùng `SUPABASE_URL/SUPABASE_ANON_KEY`, frontend dùng `VITE_SUPABASE_URL/VITE_SUPABASE_PUBLISHABLE_KEY`. Không đổi stack, dependency hoặc đưa secret vào Git.
- Kiểm: TV1 báo login/profile200, reload, logout/route guard, avatar fallback, user B mới tự tạo profile đúng ID, đổi lại A, SELECT profile A/B chỉ trả dòng chính mình và refresh chủ động/profile/reload đều đạt. Agent ngày 22/10 kiểm 51 Node tests/lint/build và 17 browser cases riêng với fixtures; TV1 báo npm checks đạt sau avatar. Chi tiết/giới hạn tại [frontend README](../frontend/README.md#kiểm-tra).
- Giới hạn: expiry/refresh thất bại thật chưa kiểm trên cloud; 401/lỗi phiên đã có kiểm giả lập. Chưa CI head mới, static Nginx hoặc review/nghiệm thu. Dashboard list/clone/create/open vẫn mock, sẽ ghép TASK-103 ở nhánh riêng sau Auth review/merge; không suy SELECT profile chứng minh quyền ghi/sessions/storage.

### DEC-TV1-003: Bổ sung DB cho Dashboard list/clone

- Ngày/người chuẩn bị và áp dụng: 24/10/2026 — Trung Anh/TV1 với hỗ trợ Codex; TV1 xác nhận đã chạy script trên Supabase chung. Nhánh `feat/task-103-dashboard-api` từ nền Auth `978003a`, được user cho tiếp tục trong lúc Auth chờ review. Sửa Auth vẫn ở nhánh Auth; trước merge Dashboard vào dev cần đối chiếu nền Auth đã được chấp nhận, đặc biệt khi squash.
- Bối cảnh: request list thật trả500/PGRST205 cho public.exam_sessions. TV1 kiểm SQL metadata: users có, ba bảng exam_sessions/source_questions/question_blueprints và hai enum session_status/question_status chưa có. Không chạy lại nguyên schema.sql vì Auth đã áp riêng.
- Quyết định: chuẩn bị `backend/scripts/setup_dashboard_sessions.sql` cho đúng trạng thái trên; lấy nguyên định nghĩa ba bảng/FK, session_status và ba policy sở hữu từ schema nhóm. Một transaction, chỉ tạo đối tượng chưa có, không thay thế users/Auth trigger/policy hoặc storage; xung đột đối tượng khiến transaction rollback.
- Quyền: đặt lại grants trên ba bảng mới rồi cấp authenticated SELECT/INSERT, thêm DELETE exam_sessions để backend dọn phiên clone lỗi; RLS vẫn kiểm sở hữu cha/con. Không cấp UPDATE, không cấp quyền bảng cho anon/PUBLIC. Các luồng Stage/editing cần thống nhất grants bổ sung với Duy; không đổi key hoặc dùng service-role để vòng qua quyền.
- Kiểm thật theo TV1: sau khi chạy SQL, request GET /api/sessions?page=1&page_size=20 bằng API client/phiên đăng nhập hiện hành trả200, items là mảng rỗng, total0/page1/page_size20. Chưa chạy clone thật hoặc kiểm RLS A/B cho sessions; list rỗng không chứng minh cách ly dữ liệu giữa hai tài khoản.
- Giới hạn: question_status không được ba bảng này dùng; API detail còn cần exam_versions, các bảng nghiệp vụ khác và storage chưa thiết lập bằng script này. Metadata kiểm cuối không thay kiểm bằng JWT user. Agent đối chiếu định nghĩa với schema, không trực tiếp chạy SQL hoặc gọi cloud thay TV1.
- Phạm vi code: chỉ setup SQL và tài liệu, chưa sessions service/UI/modal/navigation; chưa nghiệm thu TASK-103. Script không tạo dữ liệu thử. Khi Duy áp schema còn lại, tránh tạo lại các đối tượng/policy Auth và Dashboard đã có sau khi script được chạy.

### DEC-TV6-001: Shared Docker development workflow

- Date/author: 2026-10-19 — Khánh Tâm (TV6).
- Context: the original Compose stack serves a static frontend; host dependency
  installs, floating Python versions and fixed container/network names make team
  onboarding inconsistent.
- Decision: keep the static Nginx build, add a Compose Watch development overlay,
  a PowerShell setup/doctor/up/test/smoke/logs/down helper, Python dependency
  lock/hashes, pinned image digests, and container build/smoke CI.
- Node moves to the 22 line in Docker and existing CI to support the frontend's
  ESLint 10 engine requirements. Frontend packages and the build tool are unchanged.
- Frontend public Vite configuration is passed explicitly; backend secrets are not
  passed to frontend containers/builds. Vite's Docker proxy uses backend:8000.
- Impact/review: TV1 frontend startup/public env, TV3 backend startup/env/dependencies,
  TV4 CI. No API/schema, Gemini client, generator or validator implementation changes.
- Verification: see the Docker PR and docs/logbook.md for actual results; real cloud
  integration, another member's machine and ARM execution remain separate checks.

### ADR-002: In-Memory Pre-validation, Zero Cloud Mutation, và Atomic Ingestion Engine (TASK-202)
* **Mã quyết định:** ADR-002 / DEC-BE1-002
* **Ngày quyết định:** 22/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Trong quá trình nạp đề thi nguồn (Stage 1 Ingestion), đề thi từ giảng viên có thể bị thiếu đáp án, sai cấu trúc hoặc chứa công thức Equation / MathType OMML không parse được sang LaTeX. Nếu ghi dữ liệu dở dang vào CSDL, hệ thống sẽ rơi vào trạng thái "ô nhiễm dữ liệu" (dirty state).
  2. Việc upload file lên Supabase Storage ngay khi nhận request dẫn đến rác bộ nhớ (orphaned files) khi file bị từ chối ở tầng validation, gây lãng phí dung lượng storage và tăng độ trễ HTTP.
  3. Thư viện `supabase-py` giao tiếp qua PostgREST HTTP REST API không hỗ trợ khối `async with db.transaction()` trực tiếp, có nguy cơ gây mất dữ liệu cũ nếu xóa xong nhưng insert câu mới bị lỗi giữa chừng.
* **Quyết định:**
  1. **100% In-Memory Pre-validation:** Bóc tách file DOCX/LaTeX/MD, quét bảng đáp án rời, và phát hiện OMML hoàn toàn trong bộ nhớ.
  2. **Zero Cloud Mutation (Phương án 1C):** Nếu phát hiện bất kỳ câu hỏi nào lỗi (thiếu đáp án, lỗi OMML, số câu không thuộc $[1, 20]$), backend **tuyệt đối không ghi đè CSDL và không upload Storage**. Trả về ngay **HTTP 422 Unprocessable Entity** kèm schema `errors: [{"question_no": X, "error_type": "..."}]` cho FE1 hiển thị modal hướng dẫn (`TASK-203b`).
  3. **Chỉ tải file lên Supabase Storage (Bucket `exam-sources`)** với prefix `{session_id}/{uuid}_{clean_name}` khi và chỉ khi 100% câu hỏi đã hợp lệ.
  4. **Atomic Replace qua PostgreSQL Stored Procedure (Phương án 2A):** Viết hàm SQL RPC `replace_source_questions(p_session_id, p_questions)` thực hiện xóa cũ (`question_blueprints`, `source_questions`) và bulk insert mới trong **1 Transaction ACID duy nhất** ở tầng CSDL (kèm fallback an toàn ở tầng ứng dụng nếu RPC chưa được migrate).
  5. **Bảo vệ File Upload (SEC-04):** Làm sạch filename chống Path Traversal (`re.sub` triệt tiêu `..`), chặn đuôi `.pdf` ngay từ vòng ngoài (HTTP 400), kiểm tra Magic Bytes `PK\x03\x04` và giới hạn giải nén $\le 50\text{MB}$ chống Zip Bomb.
* **Hệ quả / Tác động:**
  - Đảm bảo tính toàn vẹn dữ liệu đề thi: CSDL và Storage không bao giờ chứa dữ liệu rác hay trạng thái dở dang.
  - Tối ưu hiệu năng: Giảm số lượng network round-trips từ 3 xuống 1 khi cập nhật đề thi.
  - Phù hợp và ăn khớp 100% với hợp đồng API của Frontend (FE1) tại TASK-201, TASK-203b, và TASK-204.

### DEC-BE1-003: Khắc phục Toàn Diện Phản Hồi Review PR #15 (Vòng 2)
* **Mã quyết định:** DEC-BE1-003
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Parser DOCX bỏ qua các đoạn có text rỗng trước khi kiểm tra cờ OMML, khiến công thức hiển thị đứng riêng 1 dòng bị mất khỏi thân câu hoặc phương án mà không báo lỗi.
  2. Parser LaTeX trích xuất `\item[A.]` nhưng để sót môi trường bao ngoài danh sách (`\begin{enumerate}`, `\begin{tasks}`) ở cuối thân câu và phương án D.
  3. Stored Procedure `replace_source_questions` khai báo `SECURITY DEFINER` nhưng dùng `current_user` để nhận diện admin, khiến điều kiện luôn đúng vì `current_user` trong hàm này luôn là `postgres`.
  4. Ingestion Service trả về thông báo "Session state was not modified" cho mọi ngoại lệ còn lại, gây ngộ nhận khi gặp timeout mạng (máy chủ có thể đã commit thành công nhưng HTTP response bị timeout).
* **Quyết định:**
  1. **DOCX Parser:** Kiểm tra `content_omml_flags` ngay cả khi text đoạn rỗng; bật cờ `has_unparsed_omml = True` và chèn placeholder nhận diện, kích hoạt HTTP 422 `UNPARSED_OMML` từ chối đề thi thiếu nội dung công thức.
  2. **LaTeX Parser:** Xây dựng `clean_latex_list_wrappers` bóc tách sạch sẽ các thẻ mở/đóng môi trường danh sách (`enumerate`, `tasks`, `itemize`, `multicols`) khỏi thân câu và phương án, đồng thời bảo toàn 100% các môi trường toán học (`pmatrix`, `cases`, `aligned`).
  3. **SQL RPC:** Thay thế `current_user` bằng `session_user IN ('postgres', 'supabase_admin')` kết hợp `v_role = 'service_role'`, bảo đảm chỉ caller tin cậy mới được phân quyền quản trị.
  4. **Phân loại Ngoại lệ Ingestion:** Phân biệt lỗi timeout mạng (HTTP 504 Gateway Timeout với cảnh báo trạng thái chưa xác định, không cam kết dữ liệu chưa đổi) với lỗi SQL đã rollback (HTTP 500).
  5. **Tài liệu & Test:** Bổ sung script kiểm thử SQL 5 kịch bản phân quyền trên DB test; bổ sung unit tests cho OMML đứng riêng, LaTeX clean stem/options, và Timeout 504.

### DEC-BE1-004: Xử lý Triệt Để Ngoại Lệ Mạng và Khẳng Định Trạng Thái Commit CSDL (PR #15 Round 3)
* **Mã quyết định:** DEC-BE1-004
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Exception handler trước đây chỉ nhận diện lỗi mạng dựa trên từ khóa trong `str(exc)` (như "timeout", "connection reset").
  2. Các ngoại lệ HTTPX thực tế như `httpx.ReadTimeout("")`, `httpx.ReadError("")` có chuỗi thông báo rỗng, hoặc `RemoteProtocolError("Server disconnected without sending a response.")` khi mô phỏng rớt kết nối sau commit, dẫn đến việc lọt xuống nhánh mặc định HTTP 500 và khẳng định sai "was rolled back".
  3. Khi xảy ra lỗi mạng hoặc mất phản hồi, giao dịch có thể đã commit thành công trên PostgreSQL, việc khẳng định rollback hoặc chưa thay đổi là sai thực tế và nguy hiểm cho tính toàn vẹn dữ liệu.
* **Quyết định:**
  1. **Nhận diện theo Kiểu Ngoại lệ:** Sử dụng `isinstance(exc, ...)` để phân loại trực tiếp các lớp ngoại lệ `httpx.TimeoutException`, `httpx.TransportError`, `httpx.NetworkError`, `httpcore.ProtocolError`, `RemoteProtocolError` và các lớp con (kể cả khi chuỗi thông báo rỗng).
  2. **Trạng thái Chưa Xác Định (HTTP 504):** Mọi lỗi mạng và rớt kết nối trả về HTTP 504 Gateway Timeout với thông điệp rõ ràng: trạng thái chưa xác định, giao dịch có thể đã hoàn tất, và hướng dẫn frontend/người dùng kiểm tra lại phiên trước khi thử lại (`Please verify session state before retrying`).
  3. **Chỉ Khẳng định Rollback khi có Bằng chứng CSDL (HTTP 500):** Chỉ trả về thông báo "Database atomic replacement failed and was rolled back" khi nhận được ngoại lệ xác nhận từ CSDL (`postgrest.exceptions.APIError`). Các lỗi không xác định khác trả về HTTP 500 yêu cầu kiểm tra phiên và tuyệt đối không khẳng định đã rollback.
  4. **Kiểm thử Toàn Diện:** Bổ sung unit tests sử dụng trực tiếp các đối tượng ngoại lệ HTTPX thật gồm `httpx.ReadTimeout("")`, `httpx.ReadError("")`, `httpx.RemoteProtocolError("Server disconnected without sending a response.")`, `httpcore.RemoteProtocolError`, `APIError` có bằng chứng DB, và unconfirmed errors không khẳng định rollback.

### DEC-BE1-005: Chuẩn Hóa Bóc Tách Phương Án Bullet List Trong Parser Markdown & Text (PR #15)
* **Mã quyết định:** DEC-BE1-005
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Đề thi Markdown hoặc raw text từ giảng viên thường sử dụng danh sách gạch đầu dòng (`- A. ...`, `- B. ...`) hoặc dấu sao (`* A. ...`).
  2. Biểu thức chính quy `opt_pattern` trong `utils.py` trước đây chỉ nhận diện tiền tố phương án `[A-D][\.\)]`, khiến ký tự bullet đứng trước bị nuốt vào cuối thân câu hỏi (`stem`), đồng thời bullet của phương án kế tiếp bị dính vào đuôi nội dung phương án trước (ví dụ: `stem: 'Cho x = 1\n-'`, `options: {'A': '1\n-'}`).
  3. Tầng `markdown_parser.py` có khối fallback tìm bullet nhưng bị che khuất do `extract_options_from_text` vẫn nhận diện được 4 phương án dù bị dính ký tự bullet rác.
* **Quyết định:**
  1. **Nâng cấp `opt_pattern` tại nguồn `utils.py`:** Mở rộng pattern hỗ trợ `(?:[\-\*]\s*)?` trước nhãn phương án ở cả đoạn so khớp chính và lookahead kết thúc, bảo đảm điểm bắt đầu `first_opt_pos` bao gồm cả bullet của phương án A.
  2. **Làm sạch Thân câu và Phương án:** Cắt gọt triệt để ký tự bullet thừa, bảo đảm `stem` chỉ chứa nội dung câu hỏi và các giá trị trong `options` thuần khiết, không rò rỉ gạch đầu dòng hoặc dấu sao.
  3. **Bổ sung Unit Test Hồi quy:** Thêm test `test_markdown_parser_bullet_list_options` trong `test_parsers.py` kiểm chứng cho cả hai dạng bullet `-` và `*`.

### DEC-BE1-006: Khắc Phục Triệt Để Suy Luận Rollback CSDL & Ngoại Lệ Gateway (PR #15 / PR #16 Round 4)
* **Mã quyết định:** DEC-BE1-006
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. `is_database_rollback_evidence()` trước đây coi mọi instance của `postgrest.exceptions.APIError` hoặc exception có thuộc tính `code` là bằng chứng khẳng định PostgreSQL đã rollback transaction (`was rolled back`).
  2. Khi các reverse proxy / API Gateway trung gian (Cloudflare, Kong, Nginx) gặp sự cố, chúng trả về phản hồi HTML `502 Bad Gateway`, `503 Service Unavailable`, hoặc `504 Gateway Timeout`. PostgREST Python SDK khi nhận response HTML không parse được JSON sẽ đóng gói thành `APIError` với `code=502/504` và `message="JSON could not be generated"`.
  3. Lỗi gateway chỉ là sự cố lớp mạng chuyển tiếp; server CSDL phía sau có thể đã commit thành công transaction trước khi mất phản hồi. Việc khẳng định "was rolled back" là False Rollback Assertion nguy hiểm cho toàn vẹn dữ liệu.
* **Quyết định:**
  1. **Nhận diện chính xác SQLSTATE:** Chỉ coi là bằng chứng rollback từ CSDL khi `code` là mã PostgreSQL SQLSTATE hợp lệ gồm đúng 5 ký tự alnum (`^[0-9A-Z]{5}$`), đồng thời loại trừ triệt để các mã HTTP gateway (`500, 502, 503, 504`), loại trừ phản hồi không phải JSON (`message == "JSON could not be generated"`), và loại trừ nội dung HTML.
  2. **Thông điệp trung tính cho mọi trường hợp chưa xác định:** Mọi lỗi gateway, phản hồi không phải JSON, `APIError` có code không xác định, hoặc lỗi runtime chưa được chứng minh rollback đều trả về thông báo trung tính yêu cầu kiểm tra phiên (`"Database atomic replacement failed. Please verify session state before retrying."`) và tuyệt đối không khẳng định đã rollback hay dữ liệu chưa đổi.
  3. **Bảo toàn các ca timeout 504:** Giữ nguyên 100% hai hàm `is_network_timeout` và `is_network_transport`, không tự động gửi lại RPC mù quáng ở backend.
  4. **Kiểm thử mô phỏng Gateway chân thực:** Bổ sung unit tests trong `test_ingest.py` và `test_confirm_source.py` kiểm chứng các ca Gateway HTML 502, Gateway HTML 504, non-JSON proxy error, và unknown code.

### DEC-BE1-007: Bảo Toàn Ranh Giới Câu Hỏi Bảng Nhiều Cột và Nhận Diện Bảng Đáp Án Ô Riêng Biệt (PR #15 Round 5)
* **Mã quyết định:** DEC-BE1-007
* **Ngày quyết định:** 27/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Khi đề thi DOCX sử dụng bảng nhiều cột để bố cục câu hỏi (ví dụ 1 hàng 2 ô, mỗi ô là một câu hỏi trọn vẹn), parser trước đây ghép các ô trên cùng hàng thành chuỗi duy nhất bằng `"  ".join()`. Việc này làm gộp các câu hỏi vào nhau, khiến câu đứng trước nuốt nhầm các phương án A, B, C, D của câu đứng sau và làm mất câu đứng sau trong khi API vẫn trả về 200.
  2. Bảng đáp án trong tệp DOCX thường được tách riêng biệt giữa ô số thứ tự và ô phương án chọn (ví dụ: ô 1 là "1", ô 2 là "A", ô 3 là "2", ô 4 là "B", hoặc bảng lưới 2 hàng). Khi ghép nối theo hàng, văn bản trở thành "1 A 2 B", không khớp với regex `KEY_PAIR_PATTERN` vốn yêu cầu dấu phân tách (như "1.A", "1: A"), dẫn đến lỗi từ chối sai 422 `MISSING_ANSWER`.
* **Quyết định:**
  1. **Bảo toàn ranh giới câu hỏi trong bảng nội dung:** Duyệt bảng câu hỏi theo từng ô riêng biệt (`cell-by-cell`) theo đúng thứ tự tài liệu thay vì gộp các ô trong hàng. Mọi đoạn văn và dòng ngắt (`\n`) trong từng ô được giữ nguyên thứ tự, bảo toàn tuyệt đối số lượng câu hỏi, thân câu và 4 phương án độc lập. Nếu bố cục ô bị sai lệch hoặc thiếu phương án, hệ thống từ chối ngay với HTTP 422 `INVALID_FORMAT`.
  2. **Chuẩn hóa nhận diện bảng đáp án dạng bảng ô riêng biệt:** Bổ sung hàm `try_parse_table_as_answer_key(tbl)` nhận diện tự động các kiểu bảng đáp án DOCX:
     - Dạng các cặp ô xen kẽ trong hàng (`1 | A | 2 | B` hoặc `Câu 1 | A`).
     - Dạng lưới 2 hàng (`Hàng 0: 1 2 3`, `Hàng 1: A B C`) có hoặc không có ô tiêu đề.
     - Dạng ô chứa sẵn cặp khóa (`1.A | 2.B`).
     - Bảng có tiêu đề "BẢNG ĐÁP ÁN" / "ĐÁP ÁN".
     Chuẩn hóa các cặp này thành chuỗi đáp án chuẩn `BẢNG ĐÁP ÁN: 1.A  2.B ...` ở cuối tài liệu để `parse_separate_answer_key` bóc tách đồng bộ và cô lập hoàn toàn khỏi thân câu hỏi.
  3. **Kiểm thử Toàn Diện:** Bổ sung 4 unit tests trong `test_parsers.py` và 2 API integration tests trong `test_ingest.py`, kiểm chứng chính xác số câu, thân câu, phương án và quy tắc Zero Cloud Mutation. Toàn bộ 270 backend tests đều đạt 100%.

### ADR-003: Atomic Exam Confirmation và Blueprint Concurrency Protection (TASK-205)
* **Mã quyết định:** ADR-003 / DEC-BE1-004
* **Ngày quyết định:** 25/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Trong quy trình xác nhận đề thi nguồn (Stage 1 Confirmation / TASK-205), việc cập nhật `confirmed_at` trên bảng `question_blueprints` và chuyển `status = 'blueprinted'` trên `exam_sessions` qua 2 lệnh client-side riêng rẽ có nguy cơ gây lỗi trạng thái dở dang (partial lock) hoặc báo thành công giả `HTTP 200` khi bản ghi session bị xóa / đổi trạng thái song song.
  2. Bảng `question_blueprints` thiếu ràng buộc `UNIQUE (source_question_id)`, dẫn tới nguy cơ tác vụ nền (TASK-203) và thao tác xác nhận đồng thời tạo ra các bản ghi blueprint trùng lặp cho cùng một câu hỏi nguồn.
  3. Cơ chế trích xuất fallback biến số ±5 trong `blueprint_service.py` cần được định danh rõ ràng để phân biệt với Blueprint toán học do AI sinh ra ở TASK-203.
* **Quyết định:**
  1. **Ràng buộc Toàn vẹn 1-to-1:** Thêm `CONSTRAINT uq_question_blueprints_source_question UNIQUE (source_question_id)` trên bảng `question_blueprints` và sử dụng `upsert(..., ignore_duplicates=True)` khi sinh blueprint dự phòng.
  2. **Chốt Nguồn Nguyên Tử qua Stored Procedure:** Triển khai hàm PostgreSQL RPC `confirm_exam_source(p_session_id, p_expected_question_count)` thực hiện:
     - Khóa dòng phiên (`FOR UPDATE`).
     - Kiểm tra xác thực và quyền sở hữu (bảo mật SEC-04).
     - Kiểm tra điều kiện trạng thái `status = 'draft'` và đối chiếu số lượng câu hỏi thực tế.
     - Đồng thời khóa `confirmed_at = now()` trên các blueprints và chuyển session sang `'blueprinted'` trong 1 ACID transaction duy nhất.
  3. **Kiểm tra Kết quả Ghi Thực Tế:** Loại bỏ hoàn toàn fallback cập nhật rời; chỉ chốt bằng transaction/RPC. Nếu RPC gặp timeout mạng, trả về HTTP 504 Gateway Timeout không cam kết trạng thái chưa đổi.
  4. **Phân Định Rõ Ràng Hợp Đồng Blueprint:** Đánh dấu rõ cờ `is_fallback: true` và `extraction_source: "FALLBACK_DETERMINISTIC"` cho các blueprint dự phòng từ `extract_default_blueprint` để Stage 2 phân biệt với Blueprint chính thức của AI pipeline (TASK-203).
* **Hệ quả / Tác động:**
  1. Loại bỏ hoàn toàn nguy cơ race condition, nhân bản blueprint và báo thành công sai.
  2. Dữ liệu đề thi và blueprint luôn đồng bộ 100% trong CSDL.
  3. Đáp ứng toàn diện các tiêu chí đánh giá khắt khe trong Code Review từ Lead Reviewer.

### DEC-BE1-008: Phân Loại Ngoại Lệ Mạng Phân Tán và Chuẩn Hóa Kiểm Quyền Migration 003 (TASK-205 Round 3)
* **Mã quyết định:** DEC-BE1-008
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Trong endpoint `confirm-source` (`sessions.py`), việc dùng chuỗi ký tự `"timeout" in err_lower` để bắt ngoại lệ mạng không phát hiện được các lỗi mạng phân tán với thông báo rỗng (`httpx.ReadTimeout("")`, `httpx.ReadError("")`, `RemoteProtocolError`). Khi đó, request rơi vào khối HTTP 500 với thông điệp sai lệch *"was rolled back"*, dù giao dịch có thể đã commit thành công trên PostgreSQL.
  2. Script kiểm quyền CSDL `verify_migration_003_permissions.sql` chưa khởi tạo dữ liệu người dùng mẫu trong `auth.users` và `public.users`, gây lỗi khóa ngoại `exam_sessions_user_id_fkey` khi kiểm thử trên database trắng.
  3. Kịch bản kiểm thử quyền `anon` trong `verify_migration_003_permissions.sql` chạy trực tiếp dưới kết nối superuser `postgres`, khiến RPC tin cậy `session_user` và bỏ qua kiểm tra quyền, không xác thực được cơ chế cấm `EXECUTE` (SQLSTATE 42501).
* **Quyết định:**
  1. **Phân loại ngoại lệ phân tán theo kiểu `isinstance`:** Xây dựng các helper `is_network_timeout`, `is_network_transport`, `is_database_rollback_evidence` kiểm tra cây ngoại lệ `__cause__`/`__context__`. Trả về HTTP 504 Gateway Timeout khi trạng thái commit chưa rõ ràng; chỉ trả về HTTP 500 khẳng định hoàn tác khi có bằng chứng từ `postgrest.exceptions.APIError`.
  2. **Chuẩn hóa script kiểm quyền migration 003:**
     - Thêm preflight tạo mock users trong `auth.users` và `public.users`.
     - Giả lập caller PostgREST qua `SET SESSION AUTHORIZATION authenticator; SET ROLE anon / authenticated / service_role;`.
     - Xác thực role `anon` bị từ chối `EXECUTE` ở tầng PostgreSQL Engine (SQLSTATE 42501 / Least Privilege SEC-04).
     - Thêm Scenario 11 kiểm chứng trực tiếp Quản trị viên CSDL (`session_user IN ('postgres', 'supabase_admin')`) thực thi bảo trì thành công không cần JWT claims.
     - Đóng gói toàn bộ script trong transaction kết thúc bằng `ROLLBACK;`.
  3. **Kiểm thử tự động:** Bổ sung failure mode unit tests với instance ngoại lệ thật trong `test_confirm_source.py`.

### DEC-BE1-009: Loại Trừ PostgreSQL SQLSTATE Class 08 Khỏi Bằng Chứng Rollback CSDL (TASK-202 / TASK-205 Round 5)
* **Mã quyết định:** DEC-BE1-009
* **Ngày quyết định:** 26/10/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Regex `^[0-9A-Z]{5}$` chỉ kiểm tra hình thức độ dài 5 ký tự của mã SQLSTATE, chưa phân biệt ngữ nghĩa nghiệp vụ của các nhóm lỗi trong PostgreSQL.
  2. Khi PostgREST SDK nhận mã lỗi kết nối thuộc SQLSTATE Class 08 (như `08007` - *transaction resolution unknown* hoặc `08006` - *connection failure*), hàm `is_database_rollback_evidence()` vẫn trả về `True`.
  3. Khi gặp lỗi kết nối `08007` / `08006`, máy chủ CSDL có thể đã commit thành công giao dịch trước khi kết nối bị ngắt. Việc khẳng định *"was rolled back"* là sai thực tế.
* **Quyết định:**
  1. **Loại trừ Class 08 và 40003:** Bổ sung `POSTGRES_NON_ROLLBACK_SQLSTATE_PREFIXES = ("08",)` và `POSTGRES_NON_ROLLBACK_SQLSTATES = {"40003"}` vào `ingestion_service.py`. Mọi mã lỗi bắt đầu bằng `08` hoặc `40003` đều bị loại khỏi bằng chứng rollback CSDL.
  2. **Thông báo Trung tính Cho Trạng thái Chưa Xác Định:** Khi gặp lỗi kết nối Class 08, service trả về HTTP 500 trung tính yêu cầu kiểm tra lại phiên (`"Database atomic replacement/confirmation failed. Please verify session state before retrying."`), tuyệt đối không khẳng định đã rollback.
  3. **Bảo toàn Khẳng định Rollback cho Lỗi Dữ liệu Xác định:** Các mã lỗi ràng buộc toàn vẹn thực tế (`23505`, `23503`), lỗi PL/pgSQL (`P0001`) vẫn được khẳng định rollback chính xác.
  4. **Kiểm thử Hồi quy Toàn diện:** Bổ sung các unit tests cho mã `08007`, `08006` và `23505` trên cả 2 endpoint Ingestion và Confirm Source.

### ADR-004: Tinh Giản Toàn Diện Stage 1 & Stage 2 Sang Kiến Trúc Black-Box, Silent Security Audit, và Chốt Nguồn Nguyên Tử Đơn Điểm
* **Mã quyết định:** ADR-004 / DEC-ALL-001
* **Ngày quyết định:** 27/10/2026
* **Người đề xuất:** Toàn đội kỹ thuật (Lead Bá Duy, Frontend Philip, AI & Math Validator)
* **Bối cảnh:**
  1. **Quá tải giao diện & Phức tạp hóa luồng người dùng ở Stage 1:** Thiết kế ban đầu yêu cầu xây dựng trình chỉnh sửa câu nguồn (`PUT /api/source-questions/{id}`), trình sửa tham số Blueprint (`PATCH /api/blueprints/{id}`), và hộp kiểm cam kết an ninh người dùng. Tuy nhiên, qua khảo sát sư phạm, giảng viên chỉ có nhu cầu xem trước đề nguồn để kiểm tra bóc tách đúng hay sai, không có nhu cầu can thiệp sâu vào cấu trúc toán học của Blueprint. Việc cho phép sửa tay trực tiếp dễ gây rủi ro phá vỡ tính giải được của đề thi hoặc tiêm nhiễm mã độc (XSS/SQLi).
  2. **Trải nghiệm người dùng bị ngắt quãng bởi cảnh báo an ninh:** Việc hiển thị huy hiệu đỏ cảnh báo prompt injection và bắt buộc giảng viên tick vào checkbox xác nhận an ninh gây hoang mang, vì người dùng không có chuyên môn bảo mật và không thể xử lý các vấn đề này.
  3. **Rời rạc hóa API chuyển trạng thái:** Các endpoint `/extract-all`, `/confirm`, `/confirm-all` riêng rẽ dễ gây race condition và trạng thái dở dang nếu gọi không đúng thứ tự.
  4. **Cấu hình Stage 2 quá phức tạp:** Việc bắt giảng viên chọn các hộp kiểm chế độ biến thể (`variation_modes`) dễ gây xung đột (Config Conflict) với các câu hỏi lý thuyết không có tham số số học.
* **Quyết định:**
  1. **Stage 1 Read-Only & Black-Box Blueprint Engine:**
     - Chuyển giao diện Stage 1 sang chế độ thẩm định thuần túy (Read-only Previewer bằng KaTeX). Bãi bỏ hoàn toàn các API sửa tay `PUT /api/source-questions/{id}` và `PATCH /api/blueprints/{id}`.
     - Toàn bộ cơ chế bóc tách Blueprint vận hành ngầm tự động (Black-Box AI Pipeline ở TASK-203), không phơi bày endpoint thủ công `/extract-all`.
  2. **Ghi vết an ninh âm thầm (Silent Security Audit Logging - SEC-02):**
     - Khi hệ thống phát hiện chuỗi khả nghi (prompt injection), backend ghi log âm thầm vào bảng `public.security_events` phục vụ kiểm toán nội bộ của quản trị viên.
     - **Tuyệt đối KHÔNG hiển thị cảnh báo an ninh hay bắt người dùng tick cam kết an ninh trên giao diện.** Giao diện chỉ hiển thị các cảnh báo nghiệp vụ: thiếu đáp án (`has_missing_answer`), công thức chưa đọc được (`has_unparsed_omml`).
  3. **Chốt đề nguồn nguyên tử đơn điểm (Single Atomic Confirm-source Endpoint):**
     - Gom toàn bộ quy trình chốt đề vào 1 endpoint duy nhất: `POST /api/sessions/{session_id}/confirm-source`.
     - Thực thi thông qua PostgreSQL Stored Procedure `confirm_exam_source` khóa dòng `FOR UPDATE`, kiểm tra 100% câu hỏi có blueprint, và chuyển `exam_sessions.status = 'blueprinted'` trong 1 ACID transaction.
  4. **Stage 2 Black-box Variation:**
     - Loại bỏ các hộp kiểm chọn `variation_modes` từ Frontend. Backend và AI tự động quyết định chiến lược biến thể đẳng cấu tối ưu cho từng câu hỏi (thay số, đổi ngữ cảnh, hoặc giữ nguyên nguyên văn nếu là câu lý thuyết).
     - Giảng viên chỉ cần chọn số lượng mã đề $N \in \{1, 2, 3, 4\}$ (mặc định $N=4$) và tùy chọn xáo trộn (`shuffle_questions`, `shuffle_options`).
  5. **Thẩm định Stage 3 thuần túy:**
     - Bảng cảnh báo Warning Badge chỉ hiển thị lỗi thẩm định toán học/sư phạm (SymPy không giải được, vi phạm nghiệm). Tuyệt đối không hiển thị cảnh báo hệ thống hoặc kỹ thuật.
* **Hệ quả / Tác động:**
  - Giảm thiểu triệt để số lượng endpoint và form UI cần phát triển/bảo trì, tiết kiệm ít nhất 4 ngày công cho FE và BE.
  - Giao diện đạt chuẩn Zero-Friction: Giảng viên chỉ cần nạp đề $\rightarrow$ xem trước KaTeX $\rightarrow$ bấm 1 nút "Xác nhận đề gốc và tiếp tục" để chuyển sang sinh đề.
  - Bảo đảm an toàn tuyệt đối cho CSDL và hệ thống.

<a id="dec-be1-010"></a>

### DEC-BE1-010: Khắc Phục Triệt Để Fail-Closed Permit RPC, Strict Operation Binding, và Đồng Bộ Contract TASK-302 (TASK-301 F07 v3.0)
* **Mã quyết định:** DEC-BE1-010
* **Ngày quyết định:** 02/11/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Review finding F07 (P1, Changes requested) từ Đạt (@Thanhdat3010) trên PR #28 chỉ ra 3 lỗ hổng bảo mật và toàn vẹn:
     - Wrapper RPC `acquire_attempt` bắt generic `Exception` và tự động fallback sang bảng CAS khi RPC không tồn tại (PGRST202) hoặc lỗi quyền/mạng, dẫn đến fail-open cấp permit và tăng counter sai trái tại production.
     - Migration 008 có điều kiện `OR (q.status = 'regenerating' AND q.is_current)` cho phép `operation_id` ngẫu nhiên chiếm đoạt câu hỏi đang tái sinh của phiên khác; thiếu kiểm tra hạn lease 180s và khóa phiên.
     - Operation identity chưa bền vững và chưa đồng bộ chặt chẽ với schema foundation của TASK-302 (PR #36).
* **Quyết định:**
  1. **Fail-Closed Production Policy:** Loại bỏ hoàn toàn fallback ngầm trong production (`allow_table_fallback=False`). Mọi lỗi RPC (PGRST202, lỗi quyền, ngắt kết nối mạng, malformed payload) đều ghi log ERROR đầy đủ context và raise `ReviewAcquireUnavailableError` (HTTP 503 `ERR_AI_GATEWAY_PERMIT_FAILURE`), triệt tiêu rủi ro rò rỉ quota. Nhánh table CAS chỉ được kích hoạt tường minh trong môi trường test (`allow_table_fallback=True`).
  2. **Strict Operation Binding & Guard trong Stored Procedure (Migration 008):**
     - Bỏ hoàn toàn nhánh OR nguy hiểm; bắt buộc `q.regeneration_id = p_operation_id AND q.is_current = TRUE`.
     - Bổ sung các guard nghiêm ngặt: kiểm tra lease hết hạn sau 180s (`OPERATION_EXPIRED`), kiểm tra trạng thái câu hỏi (`OPERATION_INACTIVE`), chặn phiên đã khóa (`SESSION_LOCKED` cho `approved`/`exported`), chặn phiên đang bận sinh (`SESSION_BUSY` cho `generating`).
     - Trả về mã lỗi từ chối rõ ràng trong payload JSONB (`rejection_reason`), không ném unhandled exception làm crash worker.
  3. **Đồng Bộ Hoàn Toàn Schema và Contract TASK-302:**
     - Ghi nhận `regeneration_id` vào `version_questions` trong TX1 (`reserve_max_quota_and_start_regenerating`) và dọn dẹp khi rollback (`emergency_rollback_tx`).
     - Đồng bộ hóa toàn bộ các cột bổ sung của Migration 006 (`regeneration_id`, `display_no`, `display_correct_key`, `canonical_question_no`, `session_id`, `user_id`, `api_calls_used`, `ck_review_logs_actor_required`) vào `backend/scripts/schema.sql`.
* **Phạm vi ảnh hưởng:** `backend/app/models/schemas.py`, `backend/app/services/review/repository.py`, `backend/app/services/review/service.py`, `backend/migrations/008_stage3_review_acquire_attempt_rpc.sql`, `backend/scripts/schema.sql`, `backend/tests/services/test_review_lifecycle.py`, `docs/tasks/TASK-301.md`.
* **Kiểm chứng:** 58/58 unit/lifecycle tests pass, Ruff check pass, Mypy pass (67 files).

<a id="dec-be1-011"></a>

### DEC-BE1-011: Đồng Bộ Toàn Diện Review Lifecycle Caller Với Hợp Đồng RPC CSDL Của Hùng (TASK-302 / Migration 006)
* **Mã quyết định:** DEC-BE1-011
* **Ngày quyết định:** 02/11/2026
* **Người đề xuất:** BE1 (`johannguyen015` / Nguyễn Bá Duy)
* **Bối cảnh:**
  1. Hùng (TASK-302, PR #36) đã hoàn tất và bàn giao nền tảng CSDL Stage 3 tại Migration `006_stage3_review_and_shuffle.sql` kèm 45/45 test cases pass trên container PostgreSQL 15 thật và tài liệu hợp đồng `docs/api/review-rpc-contract.md`.
  2. Để tránh dẫm chân lên phạm vi công việc của Hùng (không tạo 2 migration cạnh tranh, không sửa đè schema CSDL), Duy (TASK-301) xóa bỏ hoàn toàn migration 008 tự tạo và file test real-db trùng lặp.
  3. Thay vào đó, Duy tập trung làm đúng vai trò Caller: Tái cấu trúc `ReviewRepository` thành Thin Wrapper Client ăn khớp 100% với 8 RPCs chuẩn của Hùng.
* **Quyết định:**
  1. **Xóa bỏ triệt để triển khai CSDL cạnh tranh:**
     - Xóa `backend/migrations/008_stage3_review_acquire_attempt_rpc.sql` và `backend/tests/migrations/test_stage3_lifecycle_real_db.py`.
     - Hoàn nguyên `backend/scripts/schema.sql` khớp hoàn toàn với bản chuẩn của Hùng.
     - Xác nhận: Migration 008 chưa từng chạy lên Supabase Cloud dùng chung.
  2. **Ghép nối Caller `ReviewRepository` với 8 RPCs của Migration 006:**
     - Tách biệt 2 Client: `self.db` (Owner JWT client) cho các RPC Owner (`reserve`, `accept`, `revert`, `get_progress`), và `self.worker_db` (Worker `service_role` client) cho các RPC Worker (`acquire_attempt`, `complete_regeneration`, `fail_regeneration`, `recover_regeneration`).
     - Chuẩn hóa tham số gọi RPC theo đúng `review-rpc-contract.md`:
       - `review_complete_regeneration(p_operation_id, p_candidate)`: Bỏ `p_user_id` và `p_actual_calls` (CSDL tự suy từ ledger và operation context).
       - `review_fail_regeneration(p_operation_id, p_error_code)`: Bỏ `p_user_id` và `p_actual_calls`.
       - `review_accept_question(p_session_id, p_question_id, p_action_id)` và `review_revert_question`: Dùng `p_action_id` (CSDL tự lấy actor từ `auth.uid()`).
     - Chuẩn hóa payload `AttemptPermit` đúng 6 trường: `operation_id, attempt_id, dispatch_permitted, calls_used, remaining_calls, replayed`.
  3. **Ánh xạ ngoại lệ tập trung (`_map_rpc_exception`):**
     - Bắt các mã domain exception sanitized do CSDL ném ra (`REVIEW_NOT_FOUND` $
ightarrow$ 404, `REVIEW_BUSY` $
ightarrow$ 409, `REVIEW_STALE` $
ightarrow$ 409, `REVIEW_LOCKED` $
ightarrow$ 423, `REVIEW_QUOTA_EXHAUSTED` $
ightarrow$ 429, `REVIEW_IDEMPOTENCY_CONFLICT` $
ightarrow$ 409) và chuyển thành `ReviewDomainException`.
* **Phạm vi ảnh hưởng:** `backend/app/services/review/repository.py`, `backend/tests/services/test_review_lifecycle.py`, `docs/tasks/TASK-301.md`.
* **Kiểm chứng:** 58/58 Stage 3 review tests pass (52 lifecycle + 6 API), ruff check clean.


### TASK-301 follow-up to DEC-BE1-013: uncertain reservation response

04/11/2026 — caller draft: bounded reservation reconciliation reuses the original
IDs. Active replay never authorizes AI or a failure write; unresolved responses
return sanitized503 with same-key retry guidance. Seven added regression cases;
five caller modules148 passed, Ruff and mypy69 source files passed. These are
offline RPC-boundary tests, not DB/HTTP/concurrency proof. Proposed P1–P4/R1,
producer/persistence, progress IDs, integration/conflict and review gates remain.


# DEC-DAT-W3-304: Adapter sinh lại từng câu cho review API

- Ngày/người: 29/10/2026 — Đạt; triển khai theo phản hồi Duy trên PR #26.
- Quyết định: không text giáo viên; đầu vào snapshot in-memory + canonical Blueprint/hash xác nhận, dùng lại GenerationService. Pydantic result có report trung thực và api_calls_count; mock chỉ inject tường minh.
- Phạm vi: models/targeted.py, generation/targeted_service.py, giới hạn 2 math retries trong trần 4 attempts ở đường targeted. Không đổi DB/endpoints hoặc sửa nhánh Duy.
- Tích hợp: [handoff](ai-w3-targeted-regeneration.md). Reservation 3 calls và snapshot mapper trong PR #28 còn cần owner đồng bộ; chưa coi E2E hoàn tất.

## DEC-BE1-014: TASK-301 nhận producer confirmed artifacts và tích hợp adapter

- 04/11/2026 — Duy chỉ đạo đưa producer confirmed source/canonical Blueprint vào
  TASK-301. Owner update: PR36 comment6621050876. Storage/frozen envelope/R1 còn
  phối hợp authority TASK-302; chưa nhận persistence đã triển khai/được chấp nhận.
- Tích hợp adapter #26 pin a8f61d5 vào nhánh301; không sửa nhánh Đạt. Giữ cả ADR
  TASK-304 và caller khi giải changelog; không đưa lại các bản ADR trùng lịch sử.
- Repository dùng AttemptPermit thật từ adapter. Hai ca caller→TargetedRegenerator
  dùng generation/RPC fixtures kiểm input frozen, permit và denial settlement.
- Producer preparation dùng existing per-question fingerprint, exact source và
  revision mới; validate canonical0.4.0 cùng source/revision/hash trước publication.
  Prepared payload không phải bằng chứng DB đã confirm; chưa nối write RPC/job/API.
- Local166 tests caller/producer pass; Ruff pass, mypy83 source files pass.
  CI/final-head/DB acceptance vẫn phải kiểm; không deploy, Approve hoặc merge PR.


## DEC-TV7-005: Nền schema Stage 3 tương thích dữ liệu cũ (TASK-302)

- Ngày: 31/10/2026; người đề xuất/triển khai: Hùng (`benalexx007`).
- Trạng thái: nền schema để bàn giao/review trong Draft PR; không phải toàn bộ TASK-302 đã hoàn tất.
- Bối cảnh: schema dev đã có canonical nhưng thiếu cột audit của TASK-301; `answer_keys` dùng tên cũ. Migration `CREATE TABLE IF NOT EXISTS` không nâng cấp bảng đã tồn tại.
- Thực hiện: migration 006 có transaction; backfill session audit và ánh xạ answer key khi suy ra duy nhất, giữ các cột cũ đồng bộ với `display_*`, chặn UPDATE canonical của cùng candidate. Dữ liệu thiếu/mâu thuẫn phải rollback, không tự xóa hay chọn giá trị.
- Ngoại lệ actor được người phụ trách chốt 31/10/2026: giữ NULL cho lịch sử chưa biết, không suy ra actor từ owner. Dùng CHECK NOT VALID để giữ dữ liệu cũ nhưng chặn INSERT/UPDATE thiếu actor; fresh schema dùng CHECK bình thường. Không tự VALIDATE/SET NOT NULL khi lịch sử chưa có backfill đã xác minh. Đây là ngoại lệ đối với W3 NOT NULL toàn bộ dữ liệu, chưa phải đồng nghiệp đã xác nhận đọc hoặc PR đã approve.
- Tại mốc nền 31/10: interface RPC, quota/concurrency, revert và readiness còn chờ; các xác nhận/triển khai sau đó ghi ở DEC-TV7-006. Không dùng schema tests để nhận đã có transaction lifecycle an toàn.
- Phạm vi ảnh hưởng: schema/migration và tests PostgreSQL; không sửa nhánh TASK-301, frontend, cloud hoặc description PR/issue.
- Plan và kết quả kiểm: [TASK-302](tasks/TASK-302.md). [Contract RPC](api/review-rpc-contract.md) giữ interface hiện tại; ledger/RPC được bổ sung sau mốc nền theo DEC-TV7-006.

## DEC-TV7-006: Ledger và RPC review nguyên tử (TASK-302)

- Ngày: 01/11/2026; triển khai: Hùng (`benalexx007`), theo xác nhận policy/boundary của Duy và callback của Đạt trên [PR #36](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36).
- Trạng thái: đã code để bàn giao kiểm/tích hợp; chưa deploy, approve hoặc nghiệm thu toàn luồng.
- Bối cảnh: upfront reservation/local dictionaries không bảo vệ permit sau restart/đa worker; acknowledged count không biết chắc số grant đã commit khi mất response.
- Thực hiện: mở rộng migration 006 của cùng PR bằng private operation/attempt/action receipts và tám RPC; khóa session trước mutation; reserve không charge, grant charge từng lượt dưới trần 30/session và 4/operation; replay không cấp quyền dispatch lần nữa. Complete gộp candidate/audit/invalidation; fail/recover quyết toán theo ledger, giữ uncertain charge và prior candidate; canonical của candidate mới độc lập.
- Policy đã xác nhận: JWT-owner cho user actions, service-role worker với actor từ reservation; Model A; binary reject; revert candidate đầu; readiness theo đủ source/version slots; invalidation toàn phiên khi replacement. [Contract](api/review-rpc-contract.md) dẫn từng comment quyết định và mô tả lost-response reconciliation.
- Cập nhật 02/11: [Tâm đã xác nhận canonical/display và invalidation](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6555305930); [Duy xác nhận actor/thứ tự](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6567937686). Owner quyết định giữ tên 006 hiện có, thứ tự 004/005 → 006 → 007, yêu cầu Duy bỏ implementation ledger/acquire trùng trong 008; [comment phối hợp](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/36#issuecomment-6568374582). Nếu 008 đã được áp dụng thì cần báo trạng thái trước khi chuyển đổi, không reset quota/receipts. 006 có guard dừng an toàn trước ledger không tương thích.
- Giới hạn: snapshot DB legacy chưa là canonical blueprint/hash đã confirm của TASK-304; Duy/Đạt cần xác nhận mapper/storage, không tự bịa hash hay thêm source columns. TASK-301 đã có acquire wrapper nhưng còn direct lifecycle writes/parser; SQL 007 TASK-305 đã khóa session nhưng còn readiness/config compatibility. Caller/shuffle/Supabase/AI E2E chưa kiểm.
- Phạm vi: SQL/schema, PostgreSQL tests và docs TASK-302; không sửa nhánh tác giả khác hoặc description PR/issue đã có. Không đánh dấu finding #28 verified thay reviewer; PR giữ Draft đến khi đủ bàn giao/tích hợp.
- Cập nhật local 03/11: bổ sung worker-only `review_recover_session(UUID)` để discovery + recovery theo session dưới cùng khóa DB, không mở SELECT ledger. Có chín RPC; recovery theo operation ID vẫn giữ nguyên. Kiểm thêm restart, cạnh tranh recovery/completion, rollback, quota và chuỗi 004/005 (`31ed3bc`) → 006 → 007 (`d7a3d3f`) trên fresh/upgrade. Duy đã xác nhận 008 chưa chạy Cloud và đã bỏ. Theo chỉ đạo mới, chỉ hoàn thiện/kiểm local; giao tiếp và commit/push để sau. Không mở rộng source storage hoặc nhận canonical blueprint/hash đã đầy đủ.

## DEC-TV7-007: Nguồn DB duy nhất cho review RPC và confirmed artifacts (TASK-302)

- Ngày/người: 06/11/2026, Hùng (`benalexx007`); chế độ author, workflow v0.1 proposed.
- Bối cảnh: migration 006 đã vào `dev` qua #28 (`f6b3c73`), lấy từ head `d94f138` của #36 (SQL giống hệt, cùng blob). Sổ này mới ghi DEC-TV7-005/006 và phần persistence của TASK-301, chưa ghi các quy tắc bên dưới.
- Quyết định: 006 là nguồn DB duy nhất cho ledger/RPC review, lưu source/Blueprint canonical, receipt lookup và producer lease; không giữ 006/008 cạnh tranh. Reserve đóng băng `confirmed_artifacts_v1` (revision nguồn/Blueprint, candidate hiện tại và peer); acquire/complete kiểm lại revision và candidate hiện tại, không kiểm peer, nên Accept/Revert ở slot khác không làm hỏng operation đang chạy. Readiness tính trên toàn bộ source đã xác nhận, không cần dòng Blueprint legacy; review chỉ-legacy vẫn dùng đường cũ nhưng không dispatch regeneration. Không viết lại receipt, lịch sử hay khoản đã tính quota.
- Bằng chứng: Duy Approve `d94f138` ngày 04/11. Ngày 06/11 chạy lại trên PostgreSQL 15 (Python 3.11 Windows): schema, RPC review, review artifacts và chuỗi 004/005 → 006 → 007 ghim, 83 test OK, không skip. Chưa chạy lại: test producer/consumer TASK-301, toàn bộ backend, và 006 trên chuỗi migration 008–016 hiện tại của `dev`. Không kiểm Supabase/JWT thật hay Gemini thật.
- Phạm vi ảnh hưởng: chỉ tài liệu trong PR này; contract chuẩn nằm ở [review-rpc-contract.md](api/review-rpc-contract.md), plan ở [TASK-302](tasks/TASK-302.md).

## DEC-BE1-015: TASK-301 producer persistence và dependency AI đúng Settings

- 04/11/2026 — Duy/TASK-301, theo scope producer đã giao. Tích hợp baseline #36
  a2d2fc3 vào nhánh301; không sửa nhánh Hùng, deploy hoặc tự nhận owner accepted.
- Cùng migration006 thêm private source/Blueprint revision storage và current
  heads; worker-only confirm_source_artifacts/publish_canonical_blueprint, owner/
  worker read-only get_source_artifacts. Exact source compare,003 transition/audit
  và revision commit nguyên tử; publication compare current revision sau AI.
- Giữ history khi source bị xóa/sửa, chỉ cascade theo xóa session; replay không
  khôi phục pointer cũ. Producer Python dùng BlueprintService, typed receipt và
  same-publication retry; chưa nối existing HTTP confirm-source/background flow.
- Progress cùng snapshot có IDs chưa approved. Reject dependency nay dùng đúng
  Settings.get_gemini_api_keys(); bốn configuration regressions đạt.
- Đã kiểm baseline PostgreSQL57 pass, producer12 pass trước bổ sung history/list
  cases; đang kiểm full expanded suite. Caller/preparation/config170 pass,
  Ruff/mypy84 files pass. Kết quả cuối/head và CI ghi trên PR; không lấy kết quả
  cũ hoặc tests skipped để nhận schema/deployment/E2E đã hoàn tất.
- Authority: docs/api/review-rpc-contract.md. Storage implementation là đề xuất
  cụ thể trên301 để owner đối chiếu; P1–P4/R1 acceptance, frozen mapping và public
  endpoint integration vẫn là gate còn mở.

### Verification follow-up for DEC-BE1-015

Full expanded PostgreSQL71 cases passed, including14 producer cases and pinned
004/005→006→007 chain. Added two producer replay races with independent connections;
targeted16-case result is recorded on PR. Local170 caller/preparation/config tests,
Ruff and mypy84 files pass; full backend/Blueprint1007 collect, not execution.
Public confirm-source/background and frozen-v1 RPC wiring remain in progress.

## DEC-BE1-016: F11 reconcile receipt trước adapter

- Duy/TASK-301: thêm owner-only review_lookup_regeneration(UUID,UUID,UUID), chỉ đọc
  receipt với shared lock, ownership/resource binding. Không reserve/recovery/audit
  hoặc charge. Worker không được EXECUTE lookup của owner.
- Caller xử lý completed/active/failed/recovered replay trước adapter guard;
  fresh key thiếu adapter chỉ lookup rồi503, không tạo operation. Failure outcome
  reconciliation cũng dùng lookup thay reserve. Không thay validator F10.
- Đã kiểm125 tests caller liên quan, ba PostgreSQL lookup cases, Ruff/mypy84 files.
  HTTP regression thêm adapter unavailable khi completed replay, chờ CI thực thi.
- Chưa nhận C03/bootstrap/background/frozen-v1 hoặc toàn TASK-301 đã hoàn thành;
  authority và kế hoạch đã cập nhật thứ tự theo chỉ đạo của Duy.

## DEC-BE1-017: Bootstrap nguồn không phụ thuộc legacy Blueprint

- Duy/TASK-301: worker confirm_source_artifacts không gọi003 và không yêu cầu/
  tạo legacy Blueprint. Source revision, status blueprinted và silent security
  audit commit cùng transaction; canonical_status pending/total_blueprints0.
- Python confirmation DTO không coi legacy blueprint count là canonical ready;
  review readiness của session đã có artifacts dùng canonical heads.
- PostgreSQL18 cases pass, gồm bootstrap khi xóa legacy row và bỏ hẳn function003,
  silent audit/replay, rollback, publication/revision và producer→SQL.
- Public route/background/resume/lease và frozen-v1 vẫn tiếp tục theo kế hoạch;
  không coi blueprinted là canonical ready hoặc báo task Done.


## DEC-BE1-018: TASK-301 background canonical production and frozen-v1

- Ngày/người đề xuất:04/11/2026, Duy theo kế hoạch đã giao.
- Ngữ cảnh: nguồn xác nhận chưa bootstrap canonical; reservation database_rows
  không qua validator, recovery chỉ chạy sau busy.
- Quyết định triển khai trên301, chờ owner #36 adopt: một public confirmation,
  worker producer với lease420s/deadline360s, status GET thuần đọc và retry; frozen
  canonical snapshot từ persisted heads, revision checks ở permit/complete;
  recovery trước fresh reserve sau replay/adapter/guards. Không backfill legacy.
- Phạm vi: cùng migration006, source/review caller và HTTP, authority review-rpc-contract.
  Chưa là chấp nhận của Hùng/Đạt, rollout hay GitHub Approve; kết quả kiểm ở PR #28.

## DEC-T305-AB-001: Shuffle receipt, SQL parity và post-write integrity

- Ngày: 05/11/2026; phạm vi author/self-review TASK-305 A+B trên PR #33,
  baseline `3bb481a`; proposed, chưa thay GitHub review/Approve hoặc deployment.
- Giữ nguyên shuffler TASK-303 và một RPC `finalize_persist_shuffle(uuid,jsonb)`;
  không thay SQL006/007 hay thêm writer/fallback. SQL008 thuộc PR chưa merge;
  thay đổi này không chứng nhận ledger của môi trường đã triển khai.
- Receipt parser thu hẹp kiểu trước khi đọc/hash metadata; malformed receipt
  tiếp tục fail-closed. Chuẩn hóa UUID tại shuffle service để uppercase UUID
  hợp lệ không trở thành lỗi receipt sau khi DB đã commit.
- SQL phải kiểm JSON shape/type, dịch lỗi cast/overflow thành input error và
  đọc lại display/canonical/seed/permutations sau ghi, kiểm số finalized thực;
  trigger sửa âm thầm hoặc bỏ UPDATE phải rollback toàn bộ.
- SQL validator vẫn cần đồng bộ solution độc lập để không tin payload owner.
  Giữ regex SQL với corpus parity chạy qua PostgreSQL thật thay vì bỏ guard
  hay viết lại Fisher-Yates. Đã tái hiện Python/SQL lệch với NBSP; SQL dùng tập
  whitespace Unicode của Python. Corpus regression không phải chứng minh mọi
  Unicode/locale hoặc deployed Supabase/PostgREST.
- Retry khi mất receipt sau commit: trả lỗi transport, không giả định rollback;
  retry cùng snapshot xác minh no-op qua state đầy đủ. Race tests xác nhận
  blocking PID thật và timeout hữu hạn, không suy khóa từ sleep.
- Bằng chứng và gate từng mục: [TASK-305 A+B](tasks/TASK-305_A_B_GATE_2026-11-05.md).

## DEC-T305-SEC-002: Forward remediation F01–F03, PR #33

- Ngày/người phụ trách: 05/11/2026, TASK-305/Duy; user yêu cầu xử lý review
  tại `9e9ec146`. Implemented/local verified, **proposed pending independent
  review**, không thay GitHub Approve hoặc rollout cloud.
- Repro PostgreSQL15: owner UPDATE nội dung và xóa approved_at sau approval được;
  key sai vẫn approve; một permutation khác nhưng tự nhất quán vẫn persist.
- Giữ nguyên lịch sử006–008; migration009 forward-upgrade atomic thay definitions
  Finalize, ACL, owner SELECT-only policies và direct-DML triggers. Revoke cả
  column grants, TRUNCATE/TRIGGER và profile DELETE cascade; quyền đọc owner giữ.
- Approval kiểm đúng current display slot, đáp án thực và canonical mapping dưới
  root lock trước timestamp/audit. Không dùng canonical key làm display fallback.
- Contract TASK-303 yêu cầu tái lập theo seed. Chọn **trusted backend attestation**:
  HTTP owner JWT/RLS reader → Python shuffler hiện có → service-only writer với
  actor từ CurrentUser đã xác thực. SQL revalidates owner/snapshot/integrity dưới
  lock. Không viết lại Python RNG trong SQL, không cho browser gửi permutation,
  không tin JWT role claim để nâng principal, không owner-client fallback.
- Thay đổi caller cần backend và009 rollout đồng bộ; mixed versions fail closed.
  Config finalized cần RPC invalidation riêng nếu muốn reconfigure; export cần
  legal transition qua RPC. Không triển khai thêm hai workflow đó trong lượt này.
- Ảnh hưởng/handoff: TASK-305 caller/migration/tests; owner SQL006 (#36) và TASK-303
  giữ nguyên code nhưng cần biết principal boundary mới. Contract chuẩn tại
  [Finalize RPC](api/finalize-rpc-contract.md); evidence/M5 tại
  [remediation](tasks/TASK-305_REVIEW_REMEDIATION_2026-11-05.md).


## DEC-207-001 — Canonical generation snapshot and durable W2 results

- **Ngày / người phụ trách:** 05/11/2026, Duy / TASK-207a/b, PR #32.
- **Trạng thái:** implementation và author self-check; chờ independent review,
  GitHub Approve và CI trên head được push. Không phải rollout Supabase/E2E worker.
- **Context:** canonical producer không tạo legacy Blueprint rows; config/preflight
  cũ có thể báo readiness lệch nhau, và display-only persistence không đủ resume.
- **Decision:** migration 010 sau 004–009; canonical source manifest được so sánh
  dưới parent lock ở save/initial claim. Snapshot cố định giữ seed/config/source/
  Blueprint/public modes/resolved dimensions/mapping version; retry chỉ đổi token.
  SQL hash projection có parity tests với helper AI hiện có.
- **Policy:** public profile 1.0 chỉ NUMERICAL/parameter_variation→values,
  context_swap→context; exact ["NONE"]→[]; unknown/mixed/sai case bị từ chối.
  GET không fallback legacy khi canonical lỗi/not-ready.
- **Persistence/security:** full QuestionResult và display projection nguyên tử;
  successful target immutable; finish kiểm đúng successful slots. Private wrappers
  giữ đường legacy. Quyền service dựa connection principal, không JWT role GUC.
  Authenticated không ghi config trực tiếp để bypass manifest validation.
- **Compatibility:** canonical caller PR #30 phải truyền p_expected_snapshot và
  tiêu thụ context/result envelopes; bốn tham số legacy vẫn resolve qua default.
  Clone worker/record không bị viết lại hoặc giả lập AI validation trong PR này.
  Giữ 006–009; không automatic backfill/down migration/new-generation workflow.
- **Tests/CI:** đồng bộ asyncio_mode=auto ở root với backend để lệnh CI thu cả
  backend và scripts/blueprint xử lý async fixtures đúng. SQL opt-in chạy riêng,
  bao gồm review/shuffle/final approval; không coi skipped DB tests là pass.
- **Impact:** SQL/session detail/test contract PR #32; Python preflight/worker PR #30;
  canonical producer ownership giữ nguyên. [Contract](api/generation-config-endpoint.md),
  [implementation/evidence](tasks/TASK-207.md).


## DEC-207-002 — F11 numeric fingerprint parity and AI fixture evidence

- **Ngày / phụ trách:** 05/11/2026, Duy / PR #32; author remediation, pending
  independent F11 verification and GitHub Approve.
- **Context:** Quỳnh reproduced a valid Blueprint tolerance 1e-7 whose SQL hash
  differed from Python, rejecting a valid result at persist. The old result_for
  copied SQL's fingerprint, concealing cross-language mismatch.
- **Decision:** change only migration010's number serialization: preserve integer
  precision; match Python decimal/binary64 roundtrip, notation, exponent padding,
  signed underflow and midpoint shortening under a pinned output GUC. Keep
  fingerprint validation; do not coerce numbers to strings.
- **Regression:** independent Python expected hashes, full 1e-7 RPC lifecycle,
  wrong-hash no-write, exact immutable replay/retry/resume, nested JSON/Unicode,
  precision boundaries and a deterministic 256-pattern binary64 sample.
- **AI fixture follow-up:** restore w2_ai_contract.json byte-identically from
  owner handoff 6b0558b (blob 3b0ac5b2117001285b2eb72b37c2c790b6091991).
  Re-export SQL receipt; verify QuestionResult/rendered solution/key/seed evidence.
  Explicitly label the SQL sample's synthetic slot/version hash; it is not native
  GenerationService completed-cache evidence.
- **Compatibility:** same SHA256, RPC signatures, manifest, mapping version and
  seed. No generator/worker changes, new migration, immutable-context rewrite,
  historical backfill or deployed Supabase claim. Existing F02/F07/F09/F10 remain
  reviewer verified; F11 stays in its original
  [thread](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/32#discussion_r4479665885).


## DEC-207-003 — Generation lifecycle recovery and durable error persistence (Migration 017)

- **Ngày / người phụ trách:** 07/11/2026 (cập nhật 10/11/2026 cho PR #52 HEAD 4403f3c), Duy / TASK-207, PR #52; consumer: Quỳnh / PR #30.
- **Trạng thái:** Implemented trên PR #52; reviewer `nhatquynh1107` đã xác minh độc lập F01–F04 trên HEAD `4403f3c` (23 passed, 0 skipped trên PostgreSQL 17 Docker cô lập; 5 checks CI xanh). F05 (ADR documentation) author `claimed_fixed` tại HEAD mới, chờ reviewer xác minh lại; rollout ledger trên Supabase live và PR #30 worker HTTPS E2E tiếp tục ở trạng thái pending; chưa có formal GitHub Approve.
- **Context / Ngữ cảnh:**
  - `updated_at` không phù hợp để phát hiện stale job vì metadata update (tiêu đề, môn, khối lớp) hoặc thao tác ngoài luồng làm mới timestamp này mà không phản ánh tiến trình sinh đề thực tế.
  - Sự cố tiến trình worker đột ngột dừng (crash, OOM, mất mạng) khiến generation job bị kẹt vô thời hạn ở trạng thái `running`.
  - Thiếu cơ chế lưu bền vững mã lỗi thất bại (`generation_error_code`) qua các lần khởi động lại worker và tái kết nối SSE client.
  - Cần cơ chế fencing chống xung đột giữa stale scanner và worker hợp lệ vừa hoàn thành (`finish`) hoặc job đã được retry với token mới.
- **Decision / Quyết định:**
  - Bổ sung migration 017 (`backend/migrations/017_generation_lifecycle_recovery.sql`) thêm hai cột độc lập trên `public.exam_sessions`:
    - `generation_last_activity_at TIMESTAMPTZ NULL`: cập nhật nghiêm ngặt khi claim, reserve quota, persist result/clone và heartbeat.
    - `generation_error_code TEXT NULL`: ràng buộc `CHECK (generation_error_code IS NULL OR generation_error_code ~ '^[A-Z0-9_]{3,64}$')`.
  - Thiết lập ngưỡng stale timeout 720 giây (12 phút) tính theo đồng hồ database (`clock_timestamp()`).
  - Cung cấp `list_stale_generation_jobs(p_cutoff_seconds, p_limit, p_after_activity_at, p_after_session_id)` sử dụng keyset pagination trên cặp `(generation_last_activity_at, id)` với index riêng `idx_exam_sessions_generation_stale`, chặn limit từ 1 đến 100.
  - Cung cấp `fail_stale_generation_job_if_current(p_session_id, p_expected_job_token, p_cutoff_seconds)` với row-level lock (`SELECT ... FOR UPDATE`), kiểm tra tính hợp lệ của token và trạng thái trước khi chuyển sang `failed` và ghi nhận mã lỗi `ERR_GENERATION_INTERRUPTED`. Trả về `recovered: false` an toàn nếu token đã đổi hoặc job đã kết thúc.
  - Đảm bảo tính đơn điệu của heartbeat (`heartbeat_generation_job`) bằng `GREATEST(generation_last_activity_at, clock_timestamp()) RETURNING ... INTO v_activity_at` dưới row lock để triệt tiêu race condition lùi mốc thời gian khi có transaction cạnh tranh lock (F02).
  - Ràng buộc bắt buộc mã lỗi không được NULL tại ranh giới RPC `finish_generation_job_with_error` với SQLSTATE tiêu chuẩn `22023` cho các trạng thái kết thúc thất bại (`failed`, `partial_generated`) (F03).
  - Cung cấp `load_generation_completed_results` trả kèm `generation_error_code` để worker PR #30 tái tạo terminal SSE event sau khi khởi động lại.
  - Xóa `generation_error_code` về NULL khi `claim_generation_job` retry nhưng bảo toàn quota đã trừ và các question targets đã persist trước đó.
  - Phân quyền theo nguyên tắc đặc quyền tối thiểu: thu hồi INSERT/UPDATE trực tiếp trên bảng `exam_sessions` từ `PUBLIC`, `anon`, `authenticated`; whitelist quyền UPDATE cột metadata `(title, subject, grade)` cho `authenticated`; bảo vệ cột worker bằng trigger chặn đứng cập nhật trực tiếp với SQLSTATE `42501`; giới hạn EXECUTE các RPC quản lý lifecycle cho `service_role`; ghim `search_path` cho các hàm SECURITY DEFINER.
- **Alternatives / Lý do chọn giải pháp:**
  - *Không dùng `updated_at`:* Tránh việc chỉnh sửa thông tin đề thi làm gia hạn sai lệch thời gian tính stale của tiến trình worker.
  - *Không theo dõi timeout in-memory tại worker:* Worker có thể bị kill bất ngờ; trạng thái in-memory mất hoàn toàn khi container khởi động lại.
  - *Dùng token fencing và khóa dòng (`FOR UPDATE`):* Ngăn chặn race condition giữa stale scanner chậm chạp và worker vừa hoàn thành nhiệm vụ hoặc job đã retry hợp lệ.
  - *Giữ nguyên migration 005/015/016 và `finish_generation_job` cũ:* Đảm bảo tương thích ngược hoàn toàn cho các pipeline không dùng error code bổ sung.
- **Tác động & Phạm vi:**
  - Schema: `public.exam_sessions` bổ sung 2 cột và 1 index.
  - RPCs: 5 RPC mới và cập nhật trong migration 017 (`list_stale_generation_jobs`, `fail_stale_generation_job_if_current`, `heartbeat_generation_job`, `finish_generation_job_with_error`, `load_generation_completed_results`).
  - Integration: PR #52 cung cấp SQL boundary; PR #30 tiêu thụ cho stale scanner, durable error recovery và SSE terminal emission. PR #52 không chứa Python worker code hay UI code.
- **Tài liệu & Liên kết liên quan:**
  - SQL migration: `backend/migrations/017_generation_lifecycle_recovery.sql`
  - Integration test suite: `backend/tests/migrations/test_generation_lifecycle_recovery.py`
  - API Contract: `docs/api/generation-lifecycle-recovery.md`
  - Task specification: `docs/tasks/TASK-207.md`
  - PR liên quan: [PR #52](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52), [PR #30](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/30)
