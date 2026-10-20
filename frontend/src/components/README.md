# MathRenderer — TASK-105

`MathRenderer` là component hiển thị văn bản Markdown kết hợp công thức toán học LaTeX nội dòng (`$...$`) và khối (`$$...$$`), sử dụng thư viện `react-markdown`, `remark-math` và `rehype-katex`.

## Tính năng & An toàn
1. **KaTeX Integration**: Nhúng sẵn `katex/dist/katex.min.css`, hiển thị chính xác các ký hiệu toán học phổ biến (phân số `\dfrac`, căn bậc hai `\sqrt`, tích phân `\int`, v.v.).
2. **Khả năng chịu lỗi & Tự phục hồi (Resilience & Auto-recovery)**: 
   - Cấu hình `throwOnError: false` với mã màu `#ef4444`. Công thức LaTeX sai cú pháp không làm vỡ hoặc sập ứng dụng.
   - Bọc `MathErrorBoundary` với `getDerivedStateFromProps` và `key={content}`: khi nội dung được cập nhật sang công thức hợp lệ mới, component tự động phục hồi khỏi trạng thái lỗi mà không cần unmount.
3. **Chống XSS**: Không bật `rehype-raw`, toàn bộ mã HTML độc hại (`<script>`, `<img onerror>`) bị escape an toàn.
4. **Hỗ trợ tiếng Việt & Danh sách có cấu trúc**: Tùy biến `ol` (`list-decimal pl-6`), `ul` (`list-disc pl-6`), `li` để khắc phục việc Tailwind CSS Preflight xóa số thứ tự các bước giải toán. Hỗ trợ danh sách lồng nhau (nested lists).

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

// 3. Hiển thị lời giải nhiều bước có số thứ tự
<MathRenderer
  content={`1. Bước 1: Giải phương trình $x^2 - 4 = 0 \\iff x = \\pm 2$.\n2. Bước 2: Kết luận nghiệm.`}
/>
```

## Kiểm thử tự động

```bash
npm test
npm run lint
npm run build
```
Bộ test tự động `MathRenderer.test.js` bao phủ 12 ca kiểm thử cho cả core parsing, Tailwind list styling, component wrapper, và cơ chế tự phục hồi của `MathErrorBoundary`.
