# EXT-01 / 05 — Inline Review, điều hướng và đồng bộ snapshot

[← Mục lục và điều phối](../../../EXT-01-Implementation-Plan-v1.2.md)

- **Ưu tiên / điều kiện bắt đầu:** Đọc/chuẩn bị tests ngay; sửa UI sau G0. Inline/navigation độc lập có thể dùng fixture, không cần chờ toàn bộ Q04–Q08.
- **File / đầu vào:** `frontend/src/features/stage3-review/{Stage3ReviewPage,Stage3Comparison,Stage3InspectionDialog,Stage3ReviewNotifications}.jsx`, `stage3Review.css`, `frontend/src/services/stage3Service.js`.
- **Thứ tự làm:** Inline answer/solution/Accept; read epoch và navigation epoch; bỏ optimistic overwrite; next-unreviewed theo mã; nối reasons/recovery sau gói 01–04; giữ focus, lock và routing.
- **Đầu ra / điều kiện hoàn thành gói:** UI và component/service tests trên baseline đã đồng bộ. Reasons chỉ mở khi backend/AI đã tích hợp; capability mode và consumer readiness mới chờ G2/G4.
- **Kiểm chứng:** A01-01–14; A02-11/13/14/15/24 phối hợp backend/consumer. Xem [ma trận và lệnh kiểm](08-verification.md).
- **Trạng thái thực thi:** chưa xác nhận code/test của gói. Theo dõi input/owner/ETA tại [09 — Inputs và bàn giao](09-inputs-handoff.md), không lập bảng trạng thái song song.

Các số mục cũ được giữ để truy vết review; đường dẫn code trong backtick tính từ root repository. Tách file không đổi phân công, quyền hoặc chiến lược PR.

<a id="section-3-5"></a>

### 3.5. Inline Review, auto-advance và state (V04, V07)

Tận dụng `Stage3Comparison`, `ReviewQuestionContent`, `Stage3ReviewNotifications`, `MathRenderer`, CSS, focus và confirmation dialog từ PR #109. Đáp án/lời giải/Accept hiển thị inline dưới câu; dialog dành cho chọn reasons và xác nhận sinh lại/hoàn nguyên. Không cần redesign cả workspace. Giữ API service `rejectAndRegenerateQuestion(sessionId, questionId, key, config)`; đề xuất thêm reasons trong options/config được destructure tách khỏi Axios config hoặc tham số bổ sung tương thích, không thay ý nghĩa tham số thứ tư; kiểm mọi caller (R11).

- Snapshot authoritative quyết định nội dung, candidate identity, trạng thái duyệt và readiness. Sau mutation success **hoặc lỗi**, refetch qua cơ chế read epoch chung; nếu thất bại hoặc kết quả chưa nhất quán, báo cần đồng bộ và khóa mutation/Preview. Nếu accept báo lỗi nhưng snapshot sau đó đã approved, hiển thị đúng server nhưng không auto-advance. Không ghi đè snapshot bằng response cũ (`732-742`), không merge `approvedVariantIds` cũ vào tập authoritative (`757-764`), không giữ fallback `correct_key: s.correct_key || 'A'` ở `adaptReviewSnapshot` (`stage3Service.js:170`), và không dựa vào `res?.has_warning` / `res?.is_fallback` từ `RegeneratedQuestionResponse` (vốn không có trong schema) thay cho snapshot sau refetch.
- Derive candidate đang xem từ snapshot và tọa độ phiên/mã/câu; tránh giữ nhiều bản sao cạnh tranh (`session`, `selectedSolution`, `approvedVariantIds`). Chỉ refactor state/handler liên quan trực tiếp, không viết lại toàn bộ trang.
- Dùng `candidate_id` cho mutation; dùng `version_id`/version index và source question identity cho điều hướng theo contract. Guard mounted, session generation/identity (kể cả A→B→A), mutation token; dùng một cơ chế read epoch chung cho initial load, refetch/reconcile cùng session hoặc tuần tự hóa đọc. Không cho request bắt đầu trước mutation/refetch mới ghi đè snapshot mới. `freshness_token` là hash, không phải thứ tự tăng dần. Test hai response cùng session về sai thứ tự (R08).
- Cho đổi mã/câu/session trong lúc chờ Accept (cả click và keyboard — gỡ khóa `isApprovingSingle` ở `Stage3ReviewPage.jsx:1056, 1089, 1364, 1394`); chỉ khóa mutation xung đột trên slot đích. Đặt Accept inline, không phụ thuộc modal giữ focus/khóa navigator. Ghi nhận `navigationEpoch` khi gửi accept và tăng mỗi lần người dùng chủ động điều hướng. Chỉ auto-advance nếu epoch, session và cặp mã/câu chưa đổi, snapshot xác nhận candidate đích đã approved. Tránh ghi đè candidate mới đang xem dù chỉ khác mã/câu trong cùng session.
- Dùng một helper nhỏ `findNextUnreviewed` cho auto-advance và điều hướng chủ động (thay vòng lặp question-major `(qNo - 1) * versions + versionIndex` ở `771-777`): tìm câu chưa duyệt phía sau trong mã hiện tại; vòng lại câu đã bỏ qua cùng mã; sau đó chuyển mã khác theo thứ tự ổn định. Bỏ qua slot không có candidate để duyệt, hiển thị recovery nếu còn slot thiếu. Không auto-advance khi lỗi, reload, read-only hoặc khi không xác nhận được trạng thái. Khi không còn câu cần duyệt, focus Preview nếu readiness hợp lệ; không tự điều hướng sang Preview.
- Hỗ trợ `pending_review`, `approved`, `rejected`, `regenerating`, `candidate: null` và `read_only`. `origin`, `is_reverted`, `has_warning`, validation report chỉ là evidence; không tạo FE business validator thay backend.
- Giữ hỗ trợ bàn phím/focus và MathRenderer. Vị trí xem lưu client là tiện ích, không phải business state; server quyết định tiến độ. Xác minh tab/session reload, deep link, trạng thái post-shuffle và khóa approved/exported theo routing contract hiện hành.

**Readiness gate:** dùng `snapshot.progress.ready === true`, session `reviewed` và các UI guard hiện hành (không busy, không read-only, không đang cần reconcile). Không suy readiness từ số câu duyệt. Trạng thái post-shuffle dùng API Preview tương ứng; không ép review snapshot đọc được sau shuffle.

`ReviewSnapshotProgress` hiện chỉ có `expected_slots`, `current_slots`, `approved_slots`, `missing_slots`, `ready`. `regenerating_slots` và `duplicate_slots` thuộc `/review/progress`, không tự thêm vào `/review/snapshot` chỉ để FE kiểm lại business rule.

<a id="section-3-6"></a>

### 3.6. Revert và nguồn thiếu lời giải (V08)

Migration 024 `_review_apply_action` đã kiểm frozen source, source revision, blueprint, source hash; tạo candidate mới `pending_review`, giữ đáp án/lời giải và provenance. Tái sử dụng đường này, không viết lại. Lưu ý PR #109 (`Stage3ReviewPage.jsx:1576`) hiện khóa `canRevert` theo `session?.confirmation_id && session?.job_snapshot_id`, cần mở điều kiện hợp lệ cho nhánh `legacy_root` (`NOT has_conf AND NOT has_job`) sau khi chốt phạm vi; không đổi ngữ nghĩa auto-approve legacy nếu chưa chốt contract với consumer.

Nguồn thiếu lời giải hiện có thể được biểu diễn bằng null/rỗng ở nguồn hoặc placeholder `Không có lời giải cho câu hỏi này.` ở candidate (`024`/`026`). Cần sửa kiểm tra truthiness tại `Stage3InspectionDialog.jsx:66` (và khối lời giải inline mới) để chuẩn hóa hiển thị `"Chưa có lời giải"` khi gặp `null`, chuỗi rỗng hoặc chính chuỗi placeholder đó, không hiểu placeholder là lời giải toán học. Không tự sinh lời giải khi revert; không tự đổi placeholder thành null nếu chưa thống nhất Q06 vì Preview/Export kiểm provenance cho lời giải rỗng.

R09: migration 026:351–382 clone mới dùng placeholder, nhưng tương thích replay `legacy_expected` với solution null. Export `verified_empty_solution` hiện kiểm `active_variation_modes`, `canonical_dimensions`, `public_modes` rỗng ở cấp session khi origin là clone. Mixed-policy AI mode có clone legacy null có thể không thỏa; đây là rủi ro tĩnh, không kết luận lỗi production. Kiểm riêng AI-generated/regenerated có lời giải, clone/fallback/reverted thiếu nguồn và legacy clone null/rỗng trong mixed policy. Chỉ sửa adapter thuộc owner Đạt nếu test xác nhận blocker; không tự nới provenance hoặc backfill solution hàng loạt.

Đọc [snapshot_provenance.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/exporter/snapshot_provenance.py) và [snapshot_builder.py](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/efed79b/backend/app/services/exporter/snapshot_builder.py) cùng Đạt; xác minh key/solution sau shuffle, Preview và Export. Nếu contract thiếu bằng chứng để phân biệt lời giải thiếu, chốt thay đổi tối thiểu trước khi code.
