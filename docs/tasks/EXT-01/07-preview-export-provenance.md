# EXT-01 / 07 — Provenance thiếu lời giải xuyên Preview/Export

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Chờ G4/Q06 và owner phạm vi; có thể chuẩn bị compatibility fixture ngay.
- **File / đầu vào:** `backend/app/services/exporter/{snapshot_reader,snapshot_provenance}.py`, `backend/app/services/finalize/repository.py`; owner EXT-03/04.
- **Thứ tự làm:** Tái hiện case R09; mở rộng readers; sửa classifier/verifier; giữ legacy và provenance fail-closed; test đường repository rồi artifact; chỉ sửa renderer theo contract đã xác nhận.
- **Đầu ra / điều kiện hoàn thành gói:** Evidence Preview/Export nhất quán với I-EXT-01; không dùng helper test thay reader integration hoặc tự backfill solution.
- **Kiểm chứng:** A02-15/22/24/28; A20 khi đủ input liên task. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-6-1"></a>

### 3.6.1. R09 — Thực hiện đầy đủ Preview/Export provenance (G4)

Đây là kế hoạch phối hợp EXT-03/04, không cấp quyền Duy tự sửa nhánh owner. Scope sửa chỉ được mở khi fixture tái hiện case và owner xác nhận. Giữ nhánh fallback/reverted hiện hữu, không dùng exception clone cho AI-generated/regenerated thiếu solution.

| Lớp / file | Thay đổi cần có | Tiêu chí kiểm |
|---|---|---|
| Export `snapshot_reader.py` | Mở rộng projection `generation_job_snapshots` có `mapping_version` và phần `snapshot_payload` cần cho frozen source/policy. Giữ giới hạn truy vấn theo session và snapshot IDs từ ledger của question đã được RLS-authorized | Reader thật đưa đủ evidence vào `RawSnapshotRows`; không chỉ truyền fixture giàu dữ liệu thẳng vào helper |
| Export `snapshot_provenance.py` | Tách xác minh legacy 1.0 và per-slot 1.1; bỏ điều kiện config toàn phiên rỗng chỉ cho nhánh 1.1 có evidence hợp lệ | Mixed-policy clone null hợp lệ đi qua; AI-result hoặc policy sai không được miễn solution |
| Finalize `repository.py`: `_fetch_provenance_ledger` | Lấy cùng projection frozen evidence như Export; giữ kiểm duplicate ledger/snapshot identity | Không có lỗi do SELECT thiếu field dù helper unit test pass |
| Finalize `_classify_empty_solution_kind` và call sites | Không loại clone 1.1 chỉ vì `_is_original_clone_config(config_row)` false. Cho bước phân loại sử dụng ledger/snapshot đã xác minh, hoặc candidate classification tạm luôn qua verifier bắt buộc trước chấp nhận | Mixed-policy đi tới verifier; chưa đủ evidence không được chấp nhận Preview |
| Finalize `_is_valid_ledger_entry` | Nhánh clone 1.1 dùng per-source policy; 1.0 giữ semantics cũ; unknown/malformed version fail closed | Preview và Export cùng chấp nhận/từ chối một bộ evidence |

Verifier phải giữ: đúng một successful ledger entry, session/source/question/snapshot binding, result_kind clone, fingerprint shape, warning/report phù hợp, không regenerated; riêng 1.1 kiểm policy đầy đủ (kind + dimensions), khớp frozen blueprint theo 026, không chỉ kiểm string `ORIGINAL_CLONE`. Không nới provenance bằng config live hoặc HTTP payload. Snapshot version/policy thiếu hoặc không biết trả lỗi domain hiện hành, không mặc định thành clone. Với 1.0 giữ các invariant legacy đã có; không giả lập 1.1 cho receipt cũ.

Fixture positive: job 1.1 mixed-policy có một clone thiếu solution và một AI slot có solution; legacy 1.0 clone; clone/source có solution; confirmed fallback/reverted theo contract hiện hữu. Fixture negative: thiếu projection/policy, policy lệch blueprint, sai source/session/snapshot, duplicate ledger, fingerprint sai, AI_RESULT giả clone, regenerated thiếu solution. Test qua reader/repository → Preview/Export builder, sau đó kiểm artifact thực ở A02-24. Nếu không có dữ liệu hợp lệ tái hiện legacy-null/1.1, ghi đây là compatibility fixture và không tuyên bố lỗi production.
