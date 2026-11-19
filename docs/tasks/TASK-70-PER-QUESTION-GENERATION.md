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
