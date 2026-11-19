# Issue #70 — Generation policy per question

- Owner: Trương Thành Đạt (Thanhdat3010); author mode.
- Source: https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/70 (19/11/2026). Deadline đợt theo thông báo nhóm: hết CN 22/11; không thay điều kiện CI/review.
- Workflow v0.1 proposed + INPUT-20261109; baseline code dev9305de5. User explicitly requested implementation now.
- Reviewer đề xuất: Duy (generation/RPC integration), Hùng (canonical/frozen schema); chưa tự nhận họ đã chấp thuận.

## Hành vi và phạm vi

Job mới tự suy ra values/context riêng từng canonical Blueprint đã xác nhận. Blueprint hợp lệ chỉ có chiều chưa hỗ trợ dùng Original Clone riêng câu đó; thiếu/sai/rỗng/stale fail closed. Không mở variation selector, không đổi prompt khả năng AI, không ghi lại job lịch sử.

## Thứ tự thực hiện

1. Forward-only migration 026: giữ parent lock/auth/RLS/fencing; config lưu union hỗ trợ để tương thích receipt, mapping_version 1.1; snapshot đóng băng question_policies theo source ID. Writer/read/claim/finish kiểm result kind theo câu. Job 1.0 giữ chính sách toàn đề.
2. Python adapter kiểm policy từ frozen Blueprint; worker lưu Clone qua writer hiện có, AI nhận đúng chiều của câu. Giữ source order/base seed/fingerprint/quota; resume bỏ đúng slot đã commit.
3. Kiểm config/worker/mixed ledger qua PostgreSQL local, legacy retry và các regression generation/review/finalize/export; lint/typecheck.
4. Cập nhật contract/change log, push PR và request review; không tự approve/merge code của mình.

## Input / phối hợp

Yêu cầu nghiệp vụ và canonical mapping đã đủ theo issue70; không cần chờ UI #99/#100. SQL migration mới cần reviewer kiểm contract; chưa apply shared Supabase hoặc cloud. Không thay shared files của các PR UI.

## Bàn giao

Plan ban đầu; implementation/checks chưa chạy tại commit plan. Kết quả cuối cập nhật trong PR M3 và phần dưới sau khi kiểm thực tế.


## Kết quả author — 19/11/2026

- PR [#101](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/101), nhánh `feat/issue-70-per-question-policy`; code/migration/contract đã triển khai theo scope trên. Policy validator được tái sử dụng trong config và scheduler; không thêm bảng hoặc thư viện runtime.
- Python3.13 trên Windows, PostgreSQL16 trong Docker riêng bound127.0.0.1; role/auth fixtures và database ngẫu nhiên được tạo/xóa bởi test. Test không dùng dữ liệu hoặc credentials Supabase nhóm.
- Kiểm cuối: `ruff check backend/app scripts/blueprint` và hai file test mới PASS; `mypy backend/app --ignore-missing-imports` PASS (128files).
- `python -X utf8 -m pytest backend/tests/generation backend/tests/ai/test_generation_pipeline.py -q`: **383passed**. Bao gồm values-only/context-only/both/unsupported trong cùng nguồn, seed từ full source order, reject sai policy và callback AI cho Clone trước persistence.
- Opt-in `RUN_TASK207_REAL_DB_TESTS=1`, DSN PostgreSQL local riêng: `python -X utf8 -m pytest backend/tests/migrations/test_per_question_generation.py -q`: **12passed**. Kiểm migration replay, union disjoint, mixed Clone/AI/fallback, wrong writer, fencing/idempotency, mất fallback response/readback, retry không tăng quota, legacy1.0 không rewrite, upgrade config chưa freeze, reject frozen-policy corruption, foreign owner và all-Clone không cần AI runtime. Mixed case đi tiếp qua review RPC, approve từng câu, shuffle RPC, final approval và approved export snapshot adapter.
- Checkpoint rộng trước chỉnh guard/test cuối: `pytest backend/tests scripts/blueprint/tests -q`: **2171passed,783skipped**; PostgreSQL regression config/adapter/clone/fallback/new policy: **137passed,20skipped**. Các test opt-in khác skip đúng gate; không coi skipped là pass. Sau chỉnh cuối đã kiểm lại focused suites383+12 và lint/typecheck; CI kiểm toàn bộ head cuối riêng.
- Contract bàn giao ở `docs/api/generation-config-endpoint.md` (mục Issue70), generation-job-endpoints và generation-integration-inputs. Phần intersection1.0 trong docs được giữ làm lịch sử, có ghi phạm vi version.
- Chưa kiểm: liveGemini/PostgREST/JWT transport, UI browser, PDF compiler/Storage và shared Supabase deployment. Provider được thay bằng deterministic fixture trong ca worker; SQL/worker/review/shuffle/approval/export-reader là code thật. Không nhận nghiệm thu toàn MVP từ các test này.
- Release: migration026 và worker1.1 phải triển khai cùng nhau sau review. Author chưa apply cloud; chờ reviewer độc lập và CI trước merge. Không tự approve PR của mình.
