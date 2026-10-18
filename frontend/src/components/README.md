# MathRenderer — TASK-105

`MathRenderer` là component hiển thị văn bản Markdown kết hợp công thức toán học LaTeX nội dòng (`$...$`) và khối (`$$...$$`), sử dụng thư viện `react-markdown`, `remark-math` và `rehype-katex`.

## Tính năng & An toàn
1. **KaTeX Integration**: Nhúng sẵn `katex/dist/katex.min.css`, hiển thị chính xác các ký hiệu toán học phổ biến (phân số `\dfrac`, căn bậc hai `\sqrt`, tích phân `\int`, v.v.).
2. **Khả năng chịu lỗi (Error Resilience)**: Cấu hình `throwOnError: false` với mã màu `#ef4444`. Công thức LaTeX sai cú pháp không làm vỡ hoặc sập toàn bộ ứng dụng React.
3. **Chống XSS**: Không bật `rehype-raw`, toàn bộ mã HTML độc hại (`<script>`, `<img onerror>`) bị escape an toàn.
4. **Hỗ trợ tiếng Việt**: Hiển thị trơn tru các câu hỏi trắc nghiệm tiếng Việt kết hợp công thức toán học.

## Đặc tả Props

| Prop | Kiểu dữ liệu | Mặc định | Mô tả |
|---|---|---|---|
| `content` | `string` | `''` | Chuỗi văn bản Markdown hoặc LaTeX |
| `className` | `string` | `''` | Class Tailwind bổ sung cho thẻ bọc ngoài |
| `inline` | `boolean` | `false` | Nếu `true`, render dạng thẻ `<span>` thay vì khối `<div>` |

## Ví dụ sử dụng

```jsx
import MathRenderer from './components/MathRenderer.jsx';

// 1. Hiển thị nội dung câu hỏi
<MathRenderer
  content="Tìm nghiệm của phương trình $x^2 - 5x + 4 = 0$."
  className="text-base text-slate-100"
/>

// 2. Hiển thị lựa chọn phương án (inline)
<div className="flex items-center gap-2">
  <span>A.</span>
  <MathRenderer content="$\dfrac{7}{18}$" inline />
</div>

// 3. Hiển thị công thức dạng khối
<MathRenderer
  content="$$\int_{0}^{1} x \, dx = \dfrac{1}{2}$$"
/>
```

## Xem thử giao diện (Standalone Preview)

Từ thư mục `frontend/`, chạy `npm run dev` và mở đường dẫn `/math-preview.html` trên trình duyệt. Trang preview cung cấp:
- Đề thi mẫu tương thích với contract fixture `contracts/fixtures/variant.json`.
- Kiểm tra hiển thị công thức lỗi.
- Live playground cho phép nhập trực tiếp nội dung để xem kết quả tức thì.

## Kiểm thử tự động

```bash
npm test
npm run lint
npm run build
```
Bộ test tự động `MathRenderer.test.js` kiểm tra đầy đủ 7 trường hợp: công thức inline, block, tiếng Việt, xử lý lỗi LaTeX, chống XSS, chế độ inline và giá trị rỗng.
