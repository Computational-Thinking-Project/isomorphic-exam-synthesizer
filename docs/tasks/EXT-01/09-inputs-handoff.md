# EXT-01 / 09 — Contract liên task và fixture bàn giao

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Chuẩn bị full fixture và giải đáp input ngay; Accepted/Integrated cần consumer xác nhận thực tế.
- **File / đầu vào:** Nguồn trạng thái duy nhất cho I-EXT-01–05, Q01–Q08 và M1; nguồn phân công EXT v3.1.
- **Thứ tự làm:** Hoàn thiện fixture từ mẫu; ghi revision/head; lấy xác nhận còn thiếu trong thread hiện có; cập nhật contract chuẩn và dẫn lại; ghi need-by/ETA theo owner.
- **Đầu ra / điều kiện hoàn thành gói:** I-EXT-01 Delivered/Accepted theo phạm vi; G2/G3/G4 chỉ mở khi đủ evidence. Không đăng tin từ việc đọc file này.
- **Kiểm chứng:** Schema validation fixture; consumer acknowledgement; integrated evidence sau API/DB thật. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-4"></a>

## 4. Đầu vào và câu hỏi — giải đáp trên Draft PR

Nơi tổng hợp input duy nhất: bảng M2 dưới đây (sau khi tạo PR có thể chuyển sang comment tổng hợp và dẫn link). Các ETA dưới đây là đề xuất; ETA được owner xác nhận vẫn là TBD. Không coi im lặng hoặc PR merge là consumer acceptance.

| ID / nguồn | Provider → Consumer | Điều kiện đủ dùng | Need-by / ETA | Mức hiện tại / bước tiếp |
|---|---|---|---|---|
| I-EXT-01 (EXT v3.1 §1) | Duy → Tâm, Đạt, Quỳnh | Contract current candidate, accept/revert, readiness, missing solution và fixture đúng schema; sau đó evidence từ DB/API thật | Contract 26/11; code/evidence dự kiến 30/11; ETA xác nhận TBD | Requested theo phân công; cần consumer xác nhận |
| I-EXT-02 (EXT v3.1 §1) | Quỳnh → Tâm, Đạt | Mẫu nguồn/đích, metadata nullable, receipt/snapshot, miền và sức chứa mã sản phẩm, cặp ID/mã của hai lượt; Duy cần phối hợp migration/session lock cho Review | Contract 26/11; ETA TBD | Theo M1; không đổi owner hoặc ranh giới input |
| I-EXT-03 (EXT v3.1 §1) | Tâm → Quỳnh, Đạt | Canonical source, trạng thái mở lại, projection hậu shuffle có đáp án/lời giải; Duy cần mode guard/slot policy thống nhất với Tâm | Quyết định 26–27/11; ETA TBD | Theo M1; cần thống nhất điểm nối Review |
| I-EXT-04 (EXT v3.1 §1) | Đạt → Quỳnh | Tập con mã/số câu OMR đã kiểm; miền mã sản phẩm từ I-EXT-02 | Trước mở OMR; ETA TBD | Không chặn EXT-01 |
| I-EXT-05 (EXT v3.1 §1) | Đạt/Bội Anh ↔ Hùng/Quỳnh | ID lượt, tải đáp án riêng, contract gói cũ/mới, key và reload | Contract 26–27/11; ETA TBD | Không mở rộng nhiệm vụ Duy ngoài điều phối/điểm nối |

<a id="section-4-1"></a>

### 4.1. Phương án chốt đề xuất (chỉ cần xác nhận đồng ý / chỉnh điểm bất đồng)

Thay vì liệt kê phương án mở, dưới đây là **một phương án triển khai cụ thể** cho từng điểm `Q01–Q08`. Nhóm `Q01–Q03` thuộc nội bộ EXT-01 (Duy chốt và triển khai từ 27/11); nhóm `Q04–Q08` chạm ranh giới liên task — các owner liên quan chỉ cần xác nhận **“Chốt”** trên [Draft PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111) hoặc báo rõ điểm cần đổi.

| ID | Chủ trì ↔ Phối hợp | Thiết kế triển khai; điểm liên task chỉ mở sau gate tương ứng |
|---|---|---|
| **Q01** | Duy (nội bộ EXT-01) | • DTO `RejectQuestionRequest`: `{ "reasons"?: ReviewReasonCode[] }` (`extra="forbid"`).<br>• Allowlist đúng 8 mã uppercase ở [§3.1](01-reject-api.md#section-3-1).<br>• No body / `null` / `{}` / `{"reasons": []}` → `[]`; body top-level `[]`, field lạ, `{"reasons": null}`, sai kiểu phần tử hoặc mã lạ → `422` trước DB/AI.<br>• Chuẩn hóa `sorted(set(reasons))`; giữ header `Idempotency-Key` optional tương thích MVP (UI mới luôn gửi key). |
| **Q02** | Duy (nội bộ EXT-01) | • `completed` cùng key + cùng canonical `reasons`: dựng `RegeneratedQuestionResponse` từ `completion_candidate` (`content = stem_latex`, `options`, `correct_key`, `solution_md`, `validation_report`) + `settlement_result` (`question_id`, `regenerated_from_id = previous_question_id`, `status = "pending_review"`), không đọc live `version_questions`.<br>• `failed` hoặc `recovered` cùng key + cùng `reasons`: trả `409 ERR_OPERATION_FINISHED` (FE tạo `Idempotency-Key` mới cho lần reject sau và refetch snapshot).<br>• Cùng key nhưng khác `canonical_reasons`: trả `409 ERR_ATTEMPT_REPLAYED` (map từ SQL `REVIEW_IDEMPOTENCY_CONFLICT` tại `repository.py:65–68`). |
| **Q03** | Duy (nội bộ EXT-01) | • Thêm endpoint `POST /api/sessions/{session_id}/review/recover` (owner auth + `session_lock_registry`), gọi `recover_stale_operations(session_id)` → `get_current_snapshot(session_id)` (giữ nguyên các guard `409 REVIEW_NOT_READY` / `423 REVIEW_LOCKED` / `409 REVIEW_POST_SHUFFLE_LOCKED` của `021`), trả HTTP `200`:<br>  `{ "recovered_count": int, "has_active_operation": bool, "snapshot": ReviewSnapshotResponse }` (`has_active_operation` = còn slot `status == "regenerating"`).<br>• Thứ tự trong `reject_question`: khi `lookup_regeneration(reasons)` trả `operation_status == "active"`, chạy `recover_stale_operations` dưới lock **trước** `if self.ai_generator is None:` và trước `409 ERR_QUESTION_BUSY`, rồi lookup lại theo `reasons`.<br>• FE mở snapshot thấy slot `regenerating` mà không giữ key active trong tab → gọi `/recover` 1 lần; nếu `has_active_operation == true` (còn hạn 180s), hiện trạng thái đang xử lý + nút **Kiểm tra lại**. `GET /review/snapshot` và `GET /review/progress` giữ nguyên read-only. |
| **Q04** | Duy ↔ **`@AI-WFox`** (Tâm) | • **Chế độ `shuffle_only`:** Chặn cả `reject` và `revert` ngay tại DB RPC (`409 ERR_MODE_SHUFFLE_ONLY`), ẩn/disable hai nút này trên UI. Nguồn authoritative là mode trong frozen job snapshot khi claim (EXT v3.1 §3), không chỉ live `generation_configs`. Áp dụng contract [§3.4.1](06-mode-policy.md#section-3-4-1); Tâm xác nhận vị trí/schema và marker legacy/new trước tích hợp. Không dùng `COALESCE` chung để biến snapshot mới bị thiếu mode thành AI mode.<br>• **Chế độ `ai_generation` (kể cả `026` mixed-policy):** `TargetedRegenerator` bỏ hardcode `variation_modes=[]`, rút chiều biến đổi (`values`, `context`) từ frozen `blueprint` của chính slot đó theo `_generation_question_policy` (`026:35-38`).<br>• **Slot `ORIGINAL_CLONE` trong `ai_generation` mixed-policy:** Chặn `reject` trên slot có `canonical_dimensions == []` (`409 ERR_SLOT_POLICY_CLONE_ONLY`), chỉ cho `Accept` hoặc `Revert` (vì blueprint không mở chiều biến đổi để AI sinh câu mới khác đề gốc). |
| **Q05** | **`@nhatquynh1107`** ↔ Duy, `@AI-WFox`, `@Thanhdat3010` | • Số migration đề xuất, phải kiểm inventory và dependency theo [§3.2.1](02-durable-reasons.md#section-3-2-1) trước chốt: `028` (EXT-01 Review reasons/guard/recover), `029` (EXT-02 Reuse/mode/1–20/shuffle), `030` (EXT-04 Bank/Finalize/Public codes/Delete lock/Backfill), `031` (EXT-03 Export ledger v2).<br>• Deploy `028`: maintenance window ngắn, `DROP` chữ ký 3 tham số `review_lookup_regeneration` / `review_reserve_regeneration`, thay bằng **1 chữ ký 4 tham số duy nhất (không `DEFAULT`)** để tránh PostgREST overload `PGRST203` và chặn caller cũ bypass reasons; chạy `NOTIFY pgrst, 'reload schema'`. |
| **Q06** | **`@Thanhdat3010`**, **`@htbaax`** ↔ Duy, `@AI-WFox`, `@nhatquynh1107` | • **DB:** Giữ nguyên chuỗi `'Không có lời giải cho câu hỏi này.'` cho revert/clone thiếu lời giải (`024`/`026`) để không phá provenance rỗng tại Finalize/Export.<br>• **Review UI (`EXT-01`):** `null`, `""`, và đúng chuỗi `'Không có lời giải cho câu hỏi này.'` đều hiển thị `"Chưa có lời giải"`.<br>• **Preview & Export (`EXT-03`/`04`):** `Stage3PreviewPage` và exporter (`typst_compiler.py`, `source_renderer.py`) đối chiếu đúng chuỗi placeholder đó để hiển thị `"Chưa có lời giải"` (thống nhất chữ với Review).<br>• **Fix R09:** triển khai đầy đủ reader → classifier → provenance → Preview/Export theo [§3.6.1](07-preview-export-provenance.md#section-3-6-1). Export sửa `snapshot_reader.py` và `snapshot_provenance.py`; Finalize sửa `_classify_empty_solution_kind`, `_fetch_provenance_ledger`, `_is_valid_ledger_entry` cùng call sites. Không có hàm `verified_empty_solution` trong Finalize. Không chỉ thay một predicate hoặc nới kiểm tra session-wide mà bỏ evidence. |
| **Q07** | **`@nhatquynh1107`** ↔ Duy, `@AI-WFox` | • Chuyển `DELETE /sessions/{id}` sang RPC `delete_draft_session(p_session_id)`: khóa `exam_sessions ... FOR UPDATE` (cùng khóa root-first với Review/Job/Finalize), kiểm owner.<br>• Chặn `423` nếu `approved`/`exported`/`approved_at IS NOT NULL`; chặn `409` nếu `status='generating'` hoặc `active_job_id IS NOT NULL`.<br>• Tự dọn `review_operations` `active` đã hết hạn (`expires_at <= clock_timestamp()`) trong cùng transaction, chỉ chặn `409 ERR_REVIEW_OPERATION_ACTIVE` nếu còn operation `active` chưa hết hạn. |
| **Q08** | **`@benalexx007`**, **`@AI-WFox`** ↔ Duy | • Nút mở Preview chỉ enable khi `session.session_status === 'reviewed' && session.progress?.ready === true && !reviewSyncRequired && !hasActiveMutation`; không tự chuyển trang sang Preview, không cộng count client, không tự set `approved`.<br>• Giữ điều hướng/chặn sửa cho phiên đã post-shuffle / `approved` / `exported`. |

Duy triển khai `Q01–Q03` và phần FE nội bộ ngay sau khi đồng bộ PR #109; các điểm `Q04–Q08` cần xác nhận từ owner trước khi chốt PR/migration chung.

<a id="section-4-2"></a>

### 4.2. Output I-EXT-01

- Tâm: trạng thái candidate, server readiness, provenance, AI-mode review / shuffle-only guard.
- Quỳnh: điều kiện đủ `reviewed`, canonical snapshot sau accept/revert, active operation lock boundary.
- Đạt: ví dụ câu trước/sau regenerate/revert, answer key, solution, nguồn thiếu solution và provenance, hậu shuffle đúng mapping.

Tận dụng `backend/tests/fixtures/review_snapshot/` (`complete.json`, `partial.json`, `regenerated.json`, `clone.json`, `invalid_validation.json`); chỉ bổ sung fixture revert/missing-solution hoặc case khác còn thiếu. Fixture có ID thực tế hoặc ID giả hợp lệ, mapping source/candidate/version, options, key, solution và provenance khớp DTO; không tự tạo trường không có trong contract.

`complete.json` là đủ candidate sinh ra, **không phải đã duyệt đủ** (`approved_slots=0`, `ready=false`). Tạo fixture ready riêng hoặc chuyển trạng thái fixture bằng helper test. Các ví dụ transition ở [Phụ lục A](#appendix-a) là trích contract để thảo luận, chưa phải full snapshot chạy được hay artifact Delivered.

Ví dụ **trích** `progress` của `/review/snapshot`, không phải full response:

```json
{
  "expected_slots": 2,
  "current_slots": 2,
  "approved_slots": 2,
  "missing_slots": 0,
  "ready": true
}
```

Bàn giao contract/fixture (Decided/Delivered) khác với tích hợp thật (Integrated). Mỗi consumer ghi Accepted theo phiên bản và phạm vi đủ dùng; sau đó bổ sung evidence DB/API thật. Dùng M2 và link PR thay vì nhiều bảng theo dõi trùng nhau.

<a id="section-6-2"></a>

### 6.2. M1 — Điều phối của Duy

Thứ tự tích hợp chính `EXT-01/EXT-02 → EXT-04 → EXT-03`. Hợp đồng I-EXT-02 từ Quỳnh phải đến sớm cho Tâm/Đạt dù code EXT-04 hoàn thành sau; I-EXT-04 chỉ chặn mở OMR, không chặn xuất thường. Hùng/Quỳnh và Đạt/Bội Anh chốt I-EXT-05 sớm. M1 phải ghi riêng need-by, ETA provider giao contract/fixture, ETA code hoàn tất, thời gian consumer tích hợp/kiểm/sửa, reviewer/backup và link Draft PR/tracker. Dưới đây là khung điền, không phải M1 đã xác nhận. [§4](#section-4) là nơi duy nhất tổng hợp input, không lặp tracker input.

| EXT / owner | Reviewer / backup | PR / tracker | ETA task được xác nhận | Consumer tích hợp + kiểm + sửa |
|---|---|---|---|---|
| 01 — Duy (`@johannguyen015`) | Đề xuất `@nhatquynh1107` / `@AI-WFox` / `@benalexx007`; dự phòng TBD | [PR #111](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/111) | TBD (dự toán 29–45h) | `@AI-WFox`/`@Thanhdat3010`/`@nhatquynh1107`: TBD |
| 02 — Tâm (`@AI-WFox`) | TBD / TBD | TBD | TBD | `@nhatquynh1107`/`@Thanhdat3010`: TBD |
| 04 — Quỳnh (`@nhatquynh1107`) / Hùng (`@benalexx007`) | TBD / TBD | TBD | TBD | `@Thanhdat3010`/`@htbaax`: TBD |
| 03 — Đạt (`@Thanhdat3010`) / Bội Anh (`@htbaax`) | TBD / TBD | TBD | TBD | `@nhatquynh1107`/`@benalexx007`: TBD |

Tại bảng [§4](#section-4), điền vào cột Need-by / ETA của từng input: need-by (giữ đề xuất hoặc cập nhật), ETA provider giao contract/fixture, ETA task cung cấp, consumer estimate tích hợp/kiểm/sửa, người và thời điểm xác nhận. Các ETA và estimate consumer đều TBD trước phản hồi. I-EXT-01 đề xuất need-by contract 26/11, evidence integration theo head 30/11; không gọi các ngày đề xuất là ETA đã cam kết. Không tự điền ETA của người khác nếu chưa xác nhận.

Critical path dự kiến EXT-02/04 vì mode/reuse và transaction approve/migration; kiểm lại sau khi owner báo ETA. Với input trễ: ghi phần nghiệm thu độc lập, điều kiện chưa đủ, owner và mốc xử lý trên M2/M1. Giữ một nơi tổng hợp input; không lập thêm hệ thống tracker trùng lặp.

<a id="appendix-a"></a>

## Phụ lục A — I-EXT-01: mẫu transition để chốt contract

Các mẫu sau là **dữ liệu giả, trích trường theo DTO hiện hành**, không phải full JSON snapshot hay kết quả test. Dùng cùng `session_id=10000000-0000-0000-0000-000000000001`, `version_id=30000000-0000-0000-0000-000000000001` (mã nội bộ 101), `source_question_id=20000000-0000-0000-0000-000000000001`; câu nguồn `2x + 4 = 0`, options `["x = -2", "x = 2", "x = -4", "x = 4"]`, key `A`, solution nguồn null trong ca thiếu lời giải. Khi tạo full fixture, lấy đúng envelope/confirmation/job/source revision từ fixture baseline, cập nhật status, counts, provenance, timestamp và freshness token nhất quán; không giả token thành revision tăng dần.

| Transition | candidate_id (UUID giả) | status | Nội dung / options theo A–D | correct_key | solution_md | origin / is_reverted |
|---|---|---|---|---|---|---|
| Trước accept | `40000000-0000-0000-0000-000000000001` | pending_review | 3x + 6 = 0 / `["x = 2", "x = -2", "x = -3", "x = 3"]` | B | `3x = -6 nên x = -2. Chọn B.` | ai_generated / false |
| Sau accept | cùng ID …0001 | approved | Giữ nguyên | B | Giữ nguyên | ai_generated / false |
| Sau reject/regenerate | `40000000-0000-0000-0000-000000000002` | pending_review | 5x - 15 = 0 / `["x = 3", "x = -3", "x = 5", "x = -5"]` | A | `5x = 15 nên x = 3. Chọn A.` | regenerated / false |
| Sau accept mới | cùng ID …0002 | approved | Giữ nguyên | A | Giữ nguyên | regenerated / false |
| Sau revert (nhánh riêng) | `40000000-0000-0000-0000-000000000003` | pending_review | Nội dung/options nguồn | A | `Không có lời giải cho câu hỏi này.` | reverted / true |
| Sau reaccept revert | cùng ID …0003 | approved | Giữ nguồn | A | Giữ placeholder; UI “Chưa có lời giải” | reverted / true |

Mỗi snapshot chỉ chứa candidate current của slot, không chứa cả ba lịch sử. Revert frozen-source phải có validation report/provenance theo 024; mẫu trên không thay thế kiểm nguồn thực. Với 1 phiên bản × 1 câu: trước accept/regen/revert, `progress = {"expected_slots":1,"current_slots":1,"approved_slots":0,"missing_slots":0,"ready":false}`; sau accept nếu tất cả điều kiện DB đủ, `approved_slots:1,ready:true` và session `reviewed`. Missing slot: `candidate:null`, current/approved=0, missing=1, ready=false; regenerating: candidate giữ ID hiện hành, ready=false. Kiểm riêng nhiều mã theo A01; `ready` không suy chỉ từ counts.

A02-24 dùng nhánh candidate …0002: hoán vị options sang `["x = -3", "x = 5", "x = 3", "x = -5"]` thì display key `C`, lời giải đồng bộ `Chọn C`, canonical key vẫn A. Preview/Approve/Export phải dùng projection hậu shuffle và đúng version ID; file xuất không được lấy câu 3x + 6 = 0. Dùng seed fixture hợp lệ có mapping làm đổi nhãn, hoặc chọn case thực tế có mapping đó; chạy shuffler thật, kiểm projection dựa trên mapping đã persist (ví dụ hoán vị trên chỉ minh họa, không mặc định mọi seed cho C). Nhánh revert thiếu solution kiểm độc lập. Mã công khai do EXT-04 cấp, không giả định luôn là 101.

Bàn giao thêm mẫu AI-mode original clone/fallback với pending_review, legacy clone null/mixed-policy và case source có solution. Người nhận xác nhận đủ dùng theo contract, sau đó test thật. Không đánh dấu Decided/Delivered/Accepted/Integrated chỉ vì mẫu đã nằm trong plan.
