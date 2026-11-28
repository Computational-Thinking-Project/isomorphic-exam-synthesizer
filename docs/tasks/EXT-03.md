# EXT-03 — Đạt: plan Export/OMR và bàn giao (M2)

- Author: Đạt (`@Thanhdat3010`, backend); Bội Anh (`@htbaax`, giao diện, mẫu và đối soát bản in) theo EXT v3.1 §1. Reviewer đề xuất: Quỳnh (receipt/ledger/Finalize), Hùng (canonical contract), Duy (Review integration); chưa thay phân công reviewer của leader.
- Workflow: v0.1 proposed + INPUT-20261109; [M2](../review/TEMPLATES.md#m2), [quy trình](../review/WORKFLOW.md).
- Nhánh: `docs/ext-03-export-omr-plan` → `dev`. Base đã đối chiếu: `b29244346094811eaa038fd31fea67969f8f5b7f`, sau Stage 3 #109.
- Nguồn giao việc: [`Ke-hoach-phan-cong-EXT-v3.1-final.md` tại #111 `8fb21e6`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/8fb21e6/Ke-hoach-phan-cong-EXT-v3.1-final.md), EXT v3.1 ngày 25/11/2026: §1 (phân công, I-EXT-01…05), §EXT-03, §6 (A02, A10, A13–A18, A20). Plan tham chiếu thêm [EXT-01/07 provenance](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/350f6d8/docs/tasks/EXT-01/07-preview-export-provenance.md), [EXT-02 tại 68ed813](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/68ed813/docs/tasks/EXT-02.md) và [EXT-04 tại 38aa8df](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/38aa8df5d19a525080cab9bec39e8b52e45bec49/docs/tasks/EXT-04.md).
- Trạng thái: **plan proposed theo EXT v3.1; chưa code EXT-03**. PR #110 (batching/files, gói mặc định) đang review riêng, không coi đã nằm trong dev.
- Lịch đợt: M2/Draft 26/11, code từ 27/11, báo kết quả tối 01/12/2026. Hạn báo kết quả không thay ETA hoàn tất task. ETA tổng EXT-03 **TBD**: phụ thuộc I-EXT-02 (snapshot thật), #112 vào dev và mẫu OMR.

## 1. Phạm vi EXT-03 phía Đạt (EXT v3.1)

1. **Snapshot.** Đơn vị export là một lượt đã duyệt (`session_id`). Lượt EXT đọc snapshot bất biến do Approve ghi (I-EXT-02); lượt MVP cũ giữ projection hiện tại. Không đọc live config để đoán mode/policy.
2. **R09/Q06.** Export reader → provenance → builder/renderers xác minh câu thiếu lời giải bằng ledger và policy frozen theo slot. Placeholder `Không có lời giải cho câu hỏi này.` được coi là thiếu lời giải khi kiểm provenance, hiển thị `Chưa có lời giải`. Không sửa chuỗi DB, canonical content, fingerprint hoặc hash để đổi nhãn. Nhãn không cấp ngoại lệ cho AI-generated/regenerated thiếu lời giải.
3. **Định danh gói.** Ba nhánh identity (MVP cũ không body/key, EXT mặc định, có cấu hình) với `packaging_key`; tên quản lý, tag và thời điểm tải không đổi identity.
4. **Tùy chọn export.** `visible_fields`, `answer_sheet`, `formats` theo EXT v3.1 §EXT-03; 1–20 câu/đề.
5. **Đáp án.** Định dạng đáp án và tải đáp án riêng của đề gốc hoặc từng mã, tách khỏi gói export.
6. **Contract OMR (I-EXT-04).** Xác minh tập con mã/số câu sau khi in, tô, chấm thật; OMR đóng cho tới khi có bằng chứng. Bội Anh kiểm PDF/bản in.

Ngoài phạm vi: Review/regenerate (Duy), mode/reuse/shuffle (Tâm), Bank/Finalize/cấp mã/receipt (Quỳnh), UI Bank/Preview (Hùng), UI Export (Bội Anh), chấm bài trên web, gộp nhiều lượt, PDF riêng cho đề gốc, trang lịch sử file, sửa historical receipts, apply shared DB hoặc merge PR người khác.

## 2. Tái sử dụng phần đang có

Đã đọc tĩnh trên dev; chưa là xác nhận runtime/cloud:

- `backend/app/services/exporter/snapshot_reader.py`: owner/RLS, phiên approved/exported, đọc lại session để phát hiện thay đổi; privileged client chỉ đọc provenance giới hạn theo session/question đã được xác thực. Hiện chỉ đọc `public_modes`, `canonical_dimensions` của job snapshot.
- `snapshot_provenance.py`: ngoại lệ lời giải rỗng kiểm ledger; nhánh clone phụ thuộc modes/dimensions rỗng toàn phiên; chưa có nhánh revert; coi placeholder là có lời giải.
- `snapshot_builder.py`, `snapshot_common.py`: kiểm `version_code` theo `VERSION_CODE_PATTERN`, sắp mã bằng `code_order`; sẽ chuyển sang `public_version_code` cho lượt EXT.
- `bundle_models.py`, `manifest_bundle.py`, `export_pipeline.py`: artifact/manifest; không xây pipeline export song song.
- `private_models.py`, `private_service.py`, `private_repository.py`, `private_storage.py`, migration 020: identity/hash/receipt, claim/fencing/recovery, storage bất biến theo `<session_id>/<packaging_key>/`. `PACKAGER_VERSION` hiện là `w4-export-v2`.
- `source_renderer.py`, `typst_compiler.py`: renderer đề/đáp án/lời giải; tái sử dụng cho mẫu mới.
- `backend/app/api/routes/private_export.py`, `frontend/src/features/export/`: API/status và controller; #110 bổ sung chọn PDF/TeX/MD và tải từng file cho gói mặc định.
- `backend/app/services/generation/mode_mapper.py` (#112 `68ed813`): `job_generation_mode`, `slot_result_kind`; Export import, không viết lại quy tắc (Q-I03-b).

## 3. Trình tự triển khai

| Lượt / file dự kiến | Mục đích và đầu ra | Điều kiện bắt đầu | Cách kiểm |
|---|---|---|---|
| G0 — đối chiếu EXT v3.1, inventory contracts/migrations | Plan này theo EXT v3.1; contract I-EXT-05 đề xuất (§4) | Đã có file phân công | Đối chiếu từng yêu cầu với §EXT-03/§6; không tạo bản phân công khác |
| G1 — tests exporter reader/provenance/builder | Fixture R09 positive/negative chạy qua reader → builder, tái hiện lỗi compatibility thực sự | Fixture I-EXT-01 `8fb21e6`, I-EXT-03 v2 `452937a`; ledger dựng theo schema (Q-I03-a) | Reproduce trước sửa; không chỉ truyền fixture giàu field thẳng vào predicate |
| G2 — `snapshot_reader.py`, `snapshot_provenance.py`, renderers | Projection frozen evidence (`mapping_version`, `generation_mode`, `snapshot_payload`); verifier theo slot qua `mode_mapper`; nhánh revert; nhãn `Chưa có lời giải` | G1; Q-I01-R Decided 28/11; #112 vào dev; Quỳnh dùng cùng quy tắc ở Finalize | Cùng evidence cho cùng kết quả ở Preview/Export; fail closed |
| G3 — đọc `approved_exam_snapshots`, identity v2, ledger/manifest, migration nếu cần | Ba nhánh identity; `public_version_code`; `snapshot_revision` trong key; gói cũ giữ nguyên | I-EXT-02 mục 1–3 + câu hỏi provenance/quyền đọc; số migration theo Q05 | Replay, fencing, interrupted recovery, owner isolation; không overwrite artifact/receipt cũ; A15/A16 |
| G4 — mẫu PDF (`visible_fields`, `written_boxes`), OMR khi đủ điều kiện | Mẫu PDF có cấu hình; OMR chỉ cho tổ hợp đã kiểm (I-EXT-04) | Miền `101`–`999` từ I-EXT-02; phần mềm/mẫu OMR được ghi nhận | Render và xem artifact thật; biên mã/số câu, ngoài miền, key A–D hậu shuffle; A17/A18 |
| G5 — routes export có cấu hình/key, tải đáp án riêng | API theo §4; ghép delta #110 khi merge | I-EXT-05 được Hùng/Bội Anh xác nhận; G3 | Owner auth, 422/404/409, filename/format, bytes/hash, reload/retry; A13/A14/A16 |
| G6 — tích hợp và M3 | Evidence đầu-cuối, CI và request review trên head cuối | Code EXT-01/02/04 đã bàn giao | AI → Review → Preview → Approve → Export; shuffle-only không gọi Gemini; báo rõ mock/live/skip; A20 |

Thứ tự tích hợp: EXT-01/02 → EXT-04 → EXT-03. G0/G1/mẫu PDF có thể làm độc lập; identity mới và OMR không mở từ contract suy đoán. Thay đổi file chung phải chốt trước trên PR Conversation. Không rewrite historical migration hay deploy cloud từ một plan được duyệt.

### R09: điều kiện không được làm mất

- Đúng một successful ledger cho question, gắn đúng session/source/snapshot; kiểm fingerprint shape, report/warning và regenerated identity.
- Kiểu slot lấy từ `mode_mapper.slot_result_kind`: 1.0 giữ quy tắc legacy, 1.1/1.2 theo policy frozen từng slot, `shuffle_only` luôn `ORIGINAL_CLONE`; `GenerationModeConflict` → từ chối. Ledger `result_kind` phải khớp kiểu slot.
- Không chấp nhận chỉ vì `result_kind == ORIGINAL_CLONE`; không dùng live config để nới policy. Nhánh revert theo [Q-I01-R](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7232757638): `w4_frozen` cần `version_questions.is_reverted = true`, `validation_report.reason = "REVERT"`, và `source_revision_id`, `source_fingerprint`, `confirmed_source_hash` khớp job snapshot đóng băng của đúng phiên, đúng `source_question_id`; không có dòng ledger riêng, không đọc Review receipt. Placeholder chỉ hợp lệ khi lời giải trong frozen source thực sự thiếu (null/rỗng/trắng); nguồn có lời giải thì revert phải mang đúng lời giải đó. Phiên legacy không có confirmation/job snapshot đi theo `legacy_root`, không yêu cầu report `REVERT`.
- Reader phải SELECT đủ frozen evidence và giới hạn provenance bằng các ID đã được owner/RLS authorize. Unit helper pass chưa chứng minh query/projection đúng.
- Display key, thứ tự câu/phương án và lời giải khớp permutation/answer_keys đã persist hoặc snapshot đã duyệt; không shuffle lại khi tải hoặc reuse seed cũ.

## 4. I-EXT-05 — contract đề xuất phía Export

Đề xuất của Đạt để Hùng/Quỳnh/Bội Anh xác nhận; chưa triển khai. Định danh theo [đề xuất Hùng](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/113#issuecomment-7222799471): `bank_item_id` là bộ, `session_id` là lượt, `version_id` là phiên bản; mã công khai chỉ để hiển thị. Receipt theo [F-018 đã chốt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/114#issuecomment-7225114873).

**Tạo/đọc gói.** Mọi route kiểm owner qua session; client chỉ gửi cấu hình hoặc key, không gửi nội dung/owner/revision. Header `Cache-Control: no-store`.

| Route | Request | Response |
|---|---|---|
| `POST /api/sessions/{session_id}/export` | Không body: nhánh mặc định theo loại lượt (MVP cũ → identity cũ; EXT → EXT mặc định). Có body: `{"config": {"visible_fields": [...], "answer_sheet": "none" \| "written_boxes" \| "omr_bubbles", "formats": ["pdf", "tex", "md"]}}` | `202 {state: "preparing", packaging_key, identity_kind}` hoặc `200 {state: "ready", packaging_key, identity_kind, effective_config, filename, sha256, size_bytes}` |
| `GET /api/sessions/{session_id}/export?packaging_key=…` | Không key: nhánh mặc định theo loại lượt | `200 {state: "idle" \| "preparing" \| "ready" \| "failed", packaging_key, identity_kind, …}`; `failed` kèm `error_code` cố định |
| `POST /api/sessions/{session_id}/export/download-url` | `{"packaging_key": "…"}`; không body: nhánh mặc định | `200 {url, expires_at, expires_in, filename}` chỉ khi gói ready |

- `identity_kind`: `legacy_default`, `ext_default`, `configured`. Server chuẩn hóa tập/thứ tự `visible_fields` và `formats` trước khi tính key; cấu hình tương đương cho cùng key.
- Lỗi đề xuất: `422 ERR_EXPORT_CONFIG_INVALID` (field lạ, chỉ chọn non-PDF mà gửi tùy chọn PDF không mặc định); `422 ERR_EXPORT_OMR_UNAVAILABLE` (tổ hợp mã/số câu chưa xác minh); `422 ERR_EXPORT_QUESTION_LIMIT` (trên 20 câu); `404 ERR_EXPORT_PACKAGE_NOT_FOUND` (key không thuộc session/user, không phân biệt với không tồn tại); `409 ERR_EXPORT_NOT_READY` (download khi chưa ready). Các mã hiện có của Private Export giữ nguyên.
- Endpoint files của #110 nhận thêm `packaging_key` khi EXT hỗ trợ nhiều cấu hình; hiện chỉ là gói mặc định.

**Tải đáp án riêng.** Đọc từ snapshot đã duyệt (lượt EXT) hoặc projection đã persist (lượt cũ); không build gói, không gọi AI.

- `GET /api/sessions/{session_id}/answer-key?target=version&version_id=…` hoặc `target=original`.
- JSON: `{session_id, target, version_id, public_version_code, questions: [{question_no, correct_key}]}`. Đề gốc dùng thứ tự và key canonical, `version_id`/`public_version_code` là `null`.
- `&format=csv`: file đính kèm UTF-8 có BOM, cột `ma_de,cau,dap_an`, tên `dap-an_<public_version_code>.csv` hoặc `dap-an_de-goc.csv`. Định dạng nhập cho phần mềm OMR chốt riêng sau I-EXT-04.

**Khôi phục sau reload.** UI lưu `{session_id, packaging_key, identity_kind, effective_config}` theo account/session, không lưu URL ký hay token. Reload chỉ gọi `GET` với key đã lưu. `404` hoặc mất key: hỏi người dùng chọn lại, hoặc chỉ `POST` lại khi người dùng bấm, với đủ cấu hình hiệu lực. Không suy ra gói mới nhất; response cũ của account/session/key khác không gây điều hướng hay tải.

| Ví dụ | Request | Kết quả mong đợi |
|---|---|---|
| Lượt MVP cũ | `POST` không body | `identity_kind=legacy_default`, key và artifact/checksum cũ; không build lại nếu artifact còn |
| Lượt EXT mặc định | `POST` không body | `identity_kind=ext_default`, bố cục MVP với mã công khai (ví dụ `105`–`108`) |
| Lượt có cấu hình | `POST` với `config` | `identity_kind=configured`; cùng cấu hình chuẩn hóa → cùng key; đổi tên bộ/tag → cùng key |

## 5. Nơi tổng hợp input duy nhất

Các reply trên Conversation là bằng chứng của cùng ID; chỉ bảng này tổng hợp trạng thái consumer. Không coi provider Deliver/PR merge là Integrated.

| ID / nguồn | Provider → consumer; cần để làm gì | Need-by / ETA | Mức nhận / phần thiếu / bước tiếp |
|---|---|---|---|
| Q-EXT03-SOURCE | Duy → Đạt: file EXT v3.1 | Đã giao | **Resolved**: file có ở [#111 `8fb21e6`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/8fb21e6/Ke-hoach-phan-cong-EXT-v3.1-final.md); plan này đã đối chiếu theo file |
| I-EXT-01 / Q06 | Duy → Đạt: accept/revert/readiness, nguồn thiếu lời giải, fixture R09 | Fixture đã giao; Q-I01-R Decided 28/11 | [Consumer 28/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7231242497): Accepted cho lập plan + G1 với `ext01_review_transitions.json` và `ext01_policy_compatibility.json` tại `8fb21e6`. [Q-I01-R Decided](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111#issuecomment-7232757638) (Duy): bằng chứng revert ghi tại §3; consumer Accepted cho G2 nhánh revert. Chưa Integrated |
| I-EXT-02 | Quỳnh → Đạt: snapshot sau Approve, metadata, mã công khai, miền mã | Decided 27/11; ba câu G3 Decided 28/11 | [Quỳnh Decided](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7216662803): `approved_exam_snapshots`, `public_version_code` `101`–`999`, sắp tăng dần, legacy giữ mã. [Consumer 28/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7231246520): Accepted mục 1–3, 5 cho lập plan; hỏi thêm provenance trong snapshot, quyền đọc, lượt không có snapshot. [Quỳnh Decided 28/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7235458622): `questions[]` mang `version_question_id`/`source_question_id`/`canonical_question_no`, Approve kiểm R09 trước khi ghi; đọc bằng client caller (RLS owner); MVP chọn projection qua liên kết backfill, EXT thiếu snapshot fail closed. [Consumer](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7238428209): Accepted cho G3; hỏi tên liên kết backfill và mã lỗi thiếu snapshot. Chưa Integrated |
| I-EXT-03 | Tâm → Đạt: projection hậu shuffle, frozen mode/policy | Fixture v3 đã giao; G2 cần #112 vào dev + 028 | [Fixture v2 `452937a`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/452937a7215a8354a601377f5fc004ec57163306/docs/tasks/fixtures/I-EXT-03.json): Accepted cho lập plan + G1, đối chiếu bằng script không lệch ([consumer](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7207576807)). [v3 `b230f7b`](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7232959616): `new_source` của reuse lưu `null` thay placeholder; không đổi ngữ nghĩa Export, đã nhận. Q-I03-a/b/c Decided ([Tâm](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7208123829), [Đạt](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/112#issuecomment-7208478586)). Chưa Integrated |
| I-EXT-04 | Đạt → Quỳnh: tập con mã/số câu OMR đã kiểm | Trước mở OMR; ETA TBD | Chưa Delivered. [Bội Anh 28/11](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/113#issuecomment-7238328814): phần mềm chấm **TNMaker** (app điện thoại), in A4 100%; Đạt làm PDF mẫu, Bội Anh in/tô/chấm. Cần ghi nhận phiên bản, quyền dùng mẫu, khổ giấy, vùng mã đề/số câu, định dạng nhập đáp án; in, tô, chấm nhiều mã (Bội Anh kiểm bản in). Miền sản phẩm `101`–`999` không phải miền OMR mặc định |
| I-EXT-05 / F-018 | Đạt/Bội Anh ↔ Hùng/Quỳnh: ID lượt, tải đáp án riêng, gói cũ/mới, key/reload | Contract đề xuất ở §4; cần xác nhận trước G5 | [Đề xuất Hùng](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/113#issuecomment-7222799471) nhận làm ranh giới. F-018 Decided (Quỳnh/Hùng). Contract Export đề xuất tại §4. [Bội Anh xác nhận phía UI](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/113#issuecomment-7238328814) ([ghi nhận](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/113#issuecomment-7238428506)); chờ Hùng xác nhận Bank → Export |
| Q05 | Quỳnh/Tâm/Duy ↔ Đạt: thứ tự/số migration | Trước migration Export; ETA TBD | #111 và #112 đều đang dùng `028` tạm. Migration Export (nếu cần) lấy số sau khi integration head được ghim; #110 không thêm migration |

ETA triển khai/tích hợp/review/sửa ước lượng lại theo thời điểm input giao thực tế, báo Duy nếu không đủ đến tối 01/12; không cắt kiểm tra để bù dependency trễ.

## 6. Tự kiểm và tiêu chí bàn giao

- R09 positive: legacy 1.0 clone; 1.1 mixed AI + clone null/placeholder; nguồn có lời giải; fallback; revert theo Q-I01-R; 1.2 `shuffle_only`. Negative: thiếu projection/policy, policy lệch frozen, sai binding, duplicate ledger, fingerprint lỗi, AI_RESULT giả clone, regenerated thiếu lời giải, AI slot mang placeholder.
- Preview/Export đồng bộ qua repository/reader; key và lời giải hậu shuffle; artifacts PDF/TeX/MD và đáp án riêng. Nhãn hiển thị không đổi checksum input hoặc nội dung đã persist.
- Gói: reload, mất response, export lặp, hai cấu hình song song, claim đồng thời và worker cũ; cùng identity đọc lại artifact cũ, identity mới không ghi đè artifact khác (A15/A16).
- Mã: hai lượt cùng bộ, mã nội bộ 101–104 và công khai 105–108; mã 106 khớp Preview/matrix/Bank/PDF/phiếu/đáp án theo `version_id` (A14).
- PDF: metadata null, không trường, ô điền, nhiều format, công thức, phân trang, bản thí sinh/giáo viên; non-PDF kèm tùy chọn PDF trả 422; trên 20 câu báo lỗi (A17).
- OMR: kiểm mẫu/artifact thật, biên mã/số câu và ngoài miền; chưa có mẫu thì ghi chưa kiểm, không báo hỗ trợ OMR chỉ vì tạo được PDF (A18).
- Checks khi có code: pytest exporter/API và integration Finalize do owner bàn giao; Ruff/mypy; frontend tests/lint/build nếu đổi UI. Compiler/PG qua Docker; không nhận skip host thành pass artifact. CI bắt buộc trước merge.
- UI theo bố cục/palette `docs/ui-walkthrough`, kiểm browser thực tế trước khi yêu cầu review UI; Bội Anh phụ trách UI Export.

## 7. Bàn giao hiện tại — 28/11

- Đã làm: plan đối chiếu EXT v3.1; consumer reply I-EXT-01 (#111), I-EXT-02 và I-EXT-03 (#112); Q-I03-a/b/c Decided; contract I-EXT-05 đề xuất tại §4. #110 chuyển Ready, chờ reviewer submit trên `03e1504`.
- Phát hiện cho G2: Finalize và Export trên dev coi placeholder là có lời giải và kiểm clone theo cả phiên; Export sẽ kiểm theo slot và coi placeholder là thiếu lời giải, Quỳnh cần cùng quy tắc ở Finalize.
- Chưa có code EXT-03, migration, mẫu OMR hoặc consumer acceptance. Kiểm plan: link và diff. Product checks của #110 ghi tại #110, không tính thành kiểm EXT-03.
- Q-I01-R Decided (Duy) và I-EXT-03 v3 đã nhận; test revert thêm vào #115.
- I-EXT-02 ba câu G3 Decided (Quỳnh); §4 được Bội Anh xác nhận phía UI; OMR dùng TNMaker. G4 (`visible_fields`, `written_boxes`) bắt đầu.
- Còn cần: tên liên kết backfill + mã lỗi thiếu snapshot (Quỳnh), xác nhận §4 (Hùng), mẫu OMR (Đạt/Bội Anh), #112 vào dev.
