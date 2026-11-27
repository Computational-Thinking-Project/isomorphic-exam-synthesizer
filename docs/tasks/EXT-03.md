# EXT-03 — Đạt: plan Export/OMR và bàn giao (M2)

- Author: Đạt (`@Thanhdat3010`); phối hợp frontend Bội Anh theo I-EXT-05. Reviewer đề xuất: Quỳnh (receipt/ledger/Finalize), Hùng (canonical contract), Duy (Review integration); chưa thay phân công reviewer của leader.
- Workflow: v0.1 proposed + INPUT-20261109; [M2](../review/TEMPLATES.md#m2), [quy trình](../review/WORKFLOW.md).
- Nhánh: `docs/ext-03-export-omr-plan` → `dev`. Base đã đối chiếu: `b29244346094811eaa038fd31fea67969f8f5b7f`, sau Stage 3 #109.
- Trạng thái: **plan một phần, proposed; chưa code EXT-03**. PR #110 là công việc batching/files đang review riêng, không coi đã nằm trong dev.
- Nguồn hiện đọc được: [EXT-01 v1.2 tại 4618075](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/4618075/EXT-01-Implementation-Plan-v1.2.md), §3.6.1, §4 và Q05/Q06; [EXT-02 tại 3d5577c](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/3d5577c/docs/tasks/EXT-02.md), §4. Hai plan dẫn `Ke-hoach-phan-cong-EXT-v3.1-final.md` ngày 25/11 nhưng chưa cung cấp file/link nguồn trong repo. Chưa đối chiếu được toàn bộ acceptance EXT-03; không tự gán các mã Axx.
- Theo lịch được dẫn ở #111/#112: M2/Draft 26/11, code từ 27/11, báo kết quả tối 01/12/2026. ETA tổng task **TBD** đến khi nhận file phân công, template/miền OMR và I-EXT-02; chưa cam kết hoàn tất cả EXT-03 trong hạn báo cáo.

## 1. Phần Đạt cần làm đã xác định

1. Chuẩn bị Export/OMR, phối hợp EXT-04 về snapshot/receipt/ID lượt và EXT-02 về nguồn cùng permutation sau shuffle. Mọi file dùng snapshot đã khóa, không đọc live config để đoán mode/policy.
2. R09/Q06: sửa phần Export reader → provenance → builder/renderers để xử lý clone thiếu lời giải trong mixed policy bằng evidence đã xác minh. Quỳnh xác nhận phần Finalize/Preview của EXT-04; không tự sửa nhánh của Quỳnh/Duy.
3. Thống nhất hiển thị `Chưa có lời giải` cho null/blank/đúng placeholder `Không có lời giải cho câu hỏi này.` ở presentation. Không sửa chuỗi DB, canonical content, fingerprint hoặc hash để đổi nhãn. Nhãn không cấp ngoại lệ cho AI-generated/regenerated thiếu solution.
4. I-EXT-04: giao cho Quỳnh tập con mã/số câu OMR đã thực sự kiểm. Miền mã sản phẩm lấy từ I-EXT-02; chưa chọn định dạng mã hoặc sức chứa template khi chưa có nguồn.
5. I-EXT-05: Đạt/Bội Anh phối hợp Hùng/Quỳnh về ID lượt, tải đáp án riêng, đọc gói cũ/mới, key và reload. Chưa tự chốt endpoint/schema ledger mới chỉ từ tên `Export ledger v2` trong Q05.

Ngoài phạm vi: thay pipeline Review/regenerate của Duy, mode/reuse của Tâm, Bank/Finalize/cấp mã của Quỳnh, chấm OMR trên web, sửa historical receipts, apply shared DB hoặc merge PR người khác.

## 2. Tái sử dụng phần đang có

Đã đọc tĩnh trên dev; chưa là xác nhận runtime/cloud:

- `backend/app/services/exporter/snapshot_reader.py`: owner/RLS, phiên approved/exported, đọc lại session để phát hiện thay đổi; privileged client chỉ đọc provenance giới hạn theo session/question đã được xác thực.
- `snapshot_provenance.py`: ngoại lệ solution rỗng kiểm ledger; nhánh clone hiện phụ thuộc modes/dimensions rỗng toàn phiên. Reader hiện thiếu `mapping_version`/frozen payload ở projection provenance, cần kiểm R09 qua đường reader thật.
- `snapshot_builder.py`, `bundle_models.py`, `manifest_bundle.py`, `export_pipeline.py`: snapshot hậu shuffle, validation, artifact/manifest; không xây pipeline export song song.
- `private_models.py`, `private_service.py`, `private_repository.py`, `private_storage.py`: identity/hash/receipt, claim/fencing/recovery, private immutable storage. `PACKAGER_VERSION` hiện là `w4-export-v2`; không đổi chỉ để trùng tên đợt EXT.
- `source_renderer.py`, `typst_compiler.py`: renderer có sẵn cho đề/đáp án/lời giải; tái sử dụng cho presentation và file mới sau khi chốt contract.
- `backend/app/api/routes/private_export.py`, `frontend/src/features/export/`: API/status và controller có sẵn. #110 bổ sung chọn PDF/TeX/MD và tải từng file, đang Draft/review tại [03e1504](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/110). Không chép lại delta đó vào plan PR hoặc mặc định đã merge.

## 3. Trình tự triển khai từ 27/11

| Lượt / file dự kiến | Mục đích và đầu ra | Điều kiện bắt đầu | Cách kiểm |
|---|---|---|---|
| G0 — file phân công, inventory contracts/migrations | Chốt acceptance, owner FE/BE, artifacts OMR, miền mã, compatibility và file chung; cập nhật chính plan này | Q-EXT03-SOURCE, I-EXT-02/05 | Đối chiếu từng yêu cầu với M1; không tạo bản phân công khác |
| G1 — tests exporter reader/provenance/builder | Fixture mixed-policy positive/negative R09 chạy qua reader → builder, xác định lỗi compatibility thực sự | I-EXT-01/03 đủ schema/evidence; không cần đợi cả EXT-04 hoàn tất | Reproduce trước sửa; không chỉ truyền fixture giàu field thẳng vào predicate |
| G2 — `snapshot_reader.py`, `snapshot_provenance.py`, builder/renderers khi cần | Projection frozen evidence; verifier theo mapping version; nhãn lời giải thiếu nhất quán | G1 + Q06; Quỳnh chốt ranh giới Finalize | Same evidence phải cho kết quả nhất quán Preview/Export; giữ fail closed |
| G3 — models/ledger/repository/manifest/storage và migration mới nếu contract thực sự cần | Identity/artifact/receipt mới cùng compatibility cũ/mới theo I-EXT-02/05 | Contract fields/key/ID lượt chốt, numbering sau kiểm inventory | Replay, fencing, interrupted recovery, owner isolation; không overwrite artifact/receipt cũ |
| G4 — renderer/template OMR và bộ fixture | Tập con mã/số câu OMR có bằng chứng, giao I-EXT-04 | Miền mã + template/tiêu chí OMR được leader/provider chốt | Biên min/max, ngoài miền, ký tự/leading zero, key A–D hậu shuffle; render và kiểm artifact thật |
| G5 — route/controller/UI tải file, đáp án riêng | Dùng đúng round/version IDs, format, trạng thái và reload; ghép delta #110 khi merge | I-EXT-05, G3; owner Bội Anh xác nhận chia file | Owner auth, filename/format, bytes/hash, stale response/unmount, reload/retry; visual theo walkthrough |
| G6 — tích hợp và M3 | Evidence đầu-cuối, CI và request review trên head cuối | Code EXT-01/02/04 cần cho đường chạy đã bàn giao | AI → Review → Preview → Approve → Export; shuffle-only không gọi Gemini; báo rõ mock/live/skip |

Thứ tự tích hợp theo hai plan provider: EXT-01/02 → EXT-04 → EXT-03. G0/G1/renderer fixture có thể chuẩn bị độc lập khi input đủ; receipt/OMR không mở từ contract suy đoán. Thay đổi chung phải chốt trước trên PR Conversation. Không rewrite historical migration hay deploy cloud từ một plan được duyệt.

### R09: điều kiện không được làm mất

- Một successful ledger cho đúng question, gắn đúng session/source/snapshot; kiểm fingerprint shape, report/warning và regenerated identity theo contract hiện hành.
- Legacy mapping 1.0 giữ semantics legacy; 1.1 kiểm per-slot kind/dimensions và frozen blueprint theo 026. Mapping 1.2 đọc theo contract/helper EXT-02 khi provider bàn giao. Thiếu/unknown/malformed evidence bị từ chối.
- Không chấp nhận chỉ vì `result_kind == ORIGINAL_CLONE`; không dùng live session-wide config để nới policy 1.1/1.2. Không nới nhánh fallback/reverted ngoài contract đã có.
- Reader phải SELECT đủ frozen evidence và giới hạn provenance bằng các ID đã được owner/RLS authorize. Unit helper pass chưa chứng minh query/projection đúng.
- Display key, question/option order và solution phải khớp permutation/answer_keys đã persist; không shuffle lại khi tải hoặc reuse seed cũ để dựng artifact.

## 4. Nơi tổng hợp input duy nhất

Các reply dưới đây và trên Conversation là bằng chứng của cùng ID; chỉ bảng này tổng hợp trạng thái consumer. Không coi provider Deliver/PR merge là Integrated.

| ID / nguồn | Provider → consumer; cần để làm gì | Need-by / ETA | Mức nhận / phần thiếu / bước tiếp |
|---|---|---|---|
| Q-EXT03-SOURCE | Duy → Đạt: file EXT v3.1, acceptance đầy đủ, FE/BE/reviewer và OMR artifacts | M2 26/11; ETA provider TBD | Requested tại [#111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7185636499). Plan hiện một phần; chưa đủ chốt scope/ước lượng tổng |
| I-EXT-01 / Q06 | Duy → Đạt: current candidate/accept/revert/readiness, missing solution và fixture R09 | Contract 26/11 theo #111; code/evidence dự kiến 30/11, chưa ETA owner xác nhận | Nhận hướng contract đủ lập plan; [Đạt trả Q05/Q06](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7185636499). Chưa fixture/code/evidence runtime |
| I-EXT-02 | Quỳnh → Đạt: nguồn/đích, metadata nullable, receipt/snapshot, miền/sức chứa mã, ID/mã hai lượt | Điểm 1–3 cần trước G3, điểm 4 trước G4; ETA provider TBD | [Mẫu `38aa8df`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/38aa8df5d19a525080cab9bec39e8b52e45bec49/docs/tasks/EXT-04.md#L30-L45): nhận một phần, đủ lập plan. [Consumer reply 27/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7207576807) chờ chốt: (1) nguồn authoritative snapshot/projection, (2) tên field mã công khai/title/metadata/ID lượt, (3) quy tắc in mã công khai + legacy giữ mã cũ, (4) định dạng mã/số 0 đầu, (5) ẩn metadata null. Chưa Integrated |
| I-EXT-03 | Tâm → Đạt: canonical source, trạng thái phiên mới, frozen mode/policy và projection hậu shuffle kèm keys/solutions | Fixture v2 đã giao 26/11; Q-I03-a/b/c cần trước kiểm tích hợp với head có 028 | [Fixture v2 `452937a`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/452937a7215a8354a601377f5fc004ec57163306/docs/tasks/fixtures/I-EXT-03.json): Accepted cho lập plan + G1. Đã đối chiếu bằng script, không lệch ([consumer reply 27/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7207576807)). Chờ Q-I03-a ledger 1.2, Q-I03-b cách đọc policy theo slot, Q-I03-c cờ chú thích. Chưa Integrated |
| I-EXT-04 | Đạt → Quỳnh: tập con mã/số câu OMR có bằng chứng | Trước mở OMR; ETA TBD sau I-EXT-02 + template | Chưa Delivered; không dùng toàn miền mã sản phẩm làm miền OMR mặc định |
| I-EXT-05 | Đạt/Bội Anh ↔ Hùng/Quỳnh: round ID, tải đáp án riêng, gói cũ/mới, key/reload | Contract 26–27/11 theo #111; ETA TBD | Cần chốt payload/route/identity, owner UI và tiêu chí compatibility trước G3/G5 |
| Q05 | Quỳnh/Tâm/Duy ↔ Đạt: inventory/thứ tự migration và rollout | Trước migration consumer; ETA TBD | Chốt nguyên tắc dependency ở #111, chưa chốt số 028–031 hoặc deployment. #110 không thêm migration |

ETA triển khai/tích hợp/review/sửa sẽ được ước lượng lại theo scope và thời điểm input giao thực tế, báo leader nếu không đủ khoảng đến tối 01/12; không cắt kiểm tra để bù dependency trễ.

## 5. Tự kiểm và tiêu chí bàn giao

- R09 positive: legacy 1.0 clone; 1.1 mixed AI + clone null/blank; nguồn có solution; fallback/reverted hợp contract; 1.2 shuffle-only sau bàn giao. Negative: missing projection/policy, policy lệch frozen blueprint, sai binding, duplicate ledger, fingerprint lỗi, AI_RESULT giả clone, regenerated thiếu solution.
- Kiểm đồng bộ Preview/Export qua repository/reader, keys và solution hậu shuffle, artifacts PDF/TeX/MD và đáp án riêng. Renderer label không thay checksum input hoặc persisted content.
- Receipt/package compatibility: reload, lost response, repeat export, concurrent claim và stale worker; cùng immutable identity đọc lại artifact cũ, identity mới không ghi đè artifact khác. Chi tiết cũ/mới chỉ chốt sau I-EXT-05.
- OMR: kiểm template/artifact thật, biên miền mã/số câu và ngoài miền; chưa có template thì ghi chưa kiểm, không báo hỗ trợ OMR chỉ vì tạo được PDF. Chấm ảnh/web ngoài scope.
- Checks khi có code: pytest exporter/API và finalize integration được owner bàn giao; Ruff/mypy; frontend tests/lint/build nếu đổi UI. Compiler/PG qua Docker theo setup; không nhận skip host thành pass artifact. CI bắt buộc trước merge.
- UI theo bố cục/palette `docs/ui-walkthrough`, kiểm browser thực tế trước yêu cầu review UI. Đạt phối hợp Bội Anh, không tự redesign hoặc nhận mock là live acceptance.

## 6. Bàn giao hiện tại — 27/11

- Đã làm: đọc source dev và provider plans, lập plan một phần; phản hồi #111 Q05/Q06 và #112 I-EXT-03/overlap #110. Ngày 27/11 trả consumer I-EXT-03 v2 và I-EXT-02 tại [#112](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7207576807). Phát hiện cho G2: verifier Export trên dev kiểm R09 theo cả phiên và chưa coi placeholder là thiếu lời giải; sẽ chuyển sang ledger + policy frozen theo slot. Chưa có code EXT-03, migration, OMR artifact hoặc consumer acceptance.
- Kiểm plan: đường dẫn source/link tương đối và diff. Product checks của #110 được ghi tại #110, không tính thành kiểm EXT-03.
- Còn cần: file giao việc + I-EXT-02/05 để chốt scope, code/fixture I-EXT-01/03 để tích hợp. Phần đủ input sẽ triển khai từ 27/11; phần chưa đủ giữ pending rõ theo ID.
