# ENV0-1 — so sánh hosting 0đ cho private beta

Đạt chuẩn bị 08/11/2026 cho [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53) và [PR51](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/51). Đây là đề xuất có điều kiện, chưa chọn/cấp phát nhà cung cấp hoặc kiểm live. Phạm vi OPS11/21; Duy điều phối quyết định và input. Ngân sách mặc định 0đ, không mua domain/VPS.

| Phương án | Điều kiện / đánh đổi | Kết luận cho repo hiện tại |
|---|---|---|
| Máy nhóm có Docker Linux engine + static Compose + Tailscale Serve | Cần máy sẵn có, owner cho quyền vận hành, điện/mạng và lịch uptime. Serve chỉ phục vụ tailnet, có HTTPS và áp access rules. Personal miễn phí tối đa6 users; phải kiểm điều kiện sử dụng và tổng thành viên, không chia tài khoản để lách hạn mức. | Ưu tiên đánh giá nếu đáp ứng đủ audience/uptime. Giữ Nginx→backend và loopback hiện hành,1 worker. Chi phí hosting tăng thêm có thể0đ; điện/mạng vẫn có chi phí. Chưa có host hoặc roster nên chưa kết luận khả thi. |
| Render Free | Có TLS; ngủ sau15 phút idle, filesystem tạm,750 giờ/workspace/tháng;0.1 CPU/512MB. | Chỉ là ứng viên thử nghiệm. Cần điều chỉnh cách đóng gói/routing so với Compose, private access gate và đo RAM/CPU khi validator+Typst chạy. Chưa chứng minh hợp baseline static Compose hoặc demo ổn định. |
| Cloudflare Quick Tunnel | Không bảo đảm uptime, URL đổi, không hỗ trợ SSE. | Loại khỏi phương án nghiệm thu có generation SSE. Không dùng URL khó đoán làm private gate. |

Nguồn chính thức kiểm ngày08/11: [Tailscale pricing](https://tailscale.com/pricing), [Serve HTTPS/access rules](https://tailscale.com/docs/features/tailscale-serve), [Render Free limits](https://render.com/docs/free), [Render compute](https://render.com/docs/compute-plans), [Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). Hạn mức có thể đổi; kiểm lại trước cấp phát. Các nhận xét phù hợp repo là đánh giá kỹ thuật, chưa là kết quả benchmark.

## Đề xuất và dữ liệu cần để chốt

1. Duy/nhóm giao số thành viên cần truy cập và xác định có máy nào được phép chạy Docker trong các slot kiểm/demo. Không ghi danh sách email hay secret vào GitHub. Nếu audience vượt gói miễn phí hoặc không có uptime, loại phương án máy nhóm+Serve hiện đề xuất, không tự thu hẹp người dùng.
2. Khi có host phù hợp, Đạt kiểm Docker/Compose/build/health trên máy đó bằng runbook và preflight; ghi SHA/image/config. Không mở backend8000 ra Internet. Nếu dùng Serve, bật HTTPS/access rules, kiểm quyền cả frontend lẫn business API; không bật public Funnel. Chưa cài hoặc đổi cấu hình host từ tài liệu này.
3. Philip/Duy cùng OPS xác nhận exact origin, Supabase redirects và Google callback. Kiểm login/logout/F5/deep-link qua URL thật; ngoài nhóm bị từ chối truy cập và business API403 theo ENV0-5. Tailnet gate không tự chứng minh Supabase principal allowlist/RLS; owner Auth cần implementation/evidence tương ứng.
4. Chạy SSE qua toàn chuỗi proxy: nhận stream, reconnect/replay/resync và restart giữa job. Đồng thời đo validator/Typst trong giới hạn tài nguyên, quota Gemini, Storage/export. Provider có HTTPS không đồng nghĩa các kiểm này đã PASS.
5. Nếu không giải pháp0đ nào đáp ứng điều kiện thiết yếu, ghi rõ điều kiện thất bại và phương án/chi phí để Duy phê duyệt trước. Không tự chuyển sang trả phí. Named tunnel/Access cần đánh giá riêng nếu nhóm đã có domain/quyền; Quick Tunnel bị loại không có nghĩa mọi Cloudflare Tunnel đều thiếu SSE.

## Trạng thái bàn giao

So sánh đã chuẩn bị; khả thi thực tế **PENDING**. Quyền host/Supabase/OAuth/Storage, kênh secret, approved team principals/count, backup đã nhận lời và lịch vận hành còn thiếu. Máy local kiểm gần nhất không có Docker CLI. PR30 F02, PR52 fullchain real-DB/ACL và approved migration manifest vẫn là gates riêng; không deploy candidate chưa bàn giao. ENV0 được cập nhật tập trung ở Issue53, không ghi DEPLOYED/G0/G1 PASS từ bản so sánh này.
