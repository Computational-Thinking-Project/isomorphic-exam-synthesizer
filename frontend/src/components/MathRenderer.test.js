import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderToString } from 'react-dom/server';
import { createMathElement } from './mathRendererCore.js';

test('render đúng công thức toán học nội dòng ($...$) với KaTeX', () => {
  const content = 'Phương trình bậc hai $x^2 - 5x + 4 = 0$ có hai nghiệm.';
  const element = createMathElement({ content });
  const html = renderToString(element);

  assert.ok(html.includes('Phương trình bậc hai'), 'Phải chứa đoạn văn bản tiếng Việt');
  assert.ok(html.includes('class="katex"'), 'Phải chứa thẻ bọc class katex');
  assert.ok(html.includes('<math xmlns="http://www.w3.org/1998/Math/MathML"'), 'Phải chứa phần tử MathML');
  assert.ok(html.includes('x^2 - 5x + 4 = 0'), 'Phải chứa công thức nguồn trong annotation');
});

test('render đúng công thức toán dạng khối ($$...$$)', () => {
  const content = 'Tích phân định nghĩa:\n\n$$\n\\int_{0}^{1} x \\, dx = \\dfrac{1}{2}\n$$\n';
  const element = createMathElement({ content });
  const html = renderToString(element);

  assert.ok(html.includes('katex-display'), 'Công thức khối phải có class katex-display');
  assert.ok(html.includes('int_{0}^{1}'), 'Phải chứa ký hiệu tích phân');
});

test('xử lý công thức LaTeX lỗi cú pháp an toàn, không làm sập ứng dụng', () => {
  const content = 'Công thức lỗi thiếu đóng ngoặc: $\\dfrac{1}{$';
  let html = '';

  assert.doesNotThrow(() => {
    const element = createMathElement({ content });
    html = renderToString(element);
  }, 'Không được quăng ngoại lệ làm crash ứng dụng');

  assert.ok(html.includes('#ef4444'), 'Công thức lỗi phải được bôi đỏ với mã màu cảnh báo');
  assert.ok(html.includes('\\dfrac{1}{'), 'Phần công thức lỗi phải được giữ lại cho người dùng thấy');
});

test('ngăn chặn thực thi mã HTML thô và script (chống XSS)', () => {
  const maliciousInput = '<script>alert("hack")</script><img src="x" onerror="alert(1)" /> Toán: $a+b$';
  const element = createMathElement({ content: maliciousInput });
  const html = renderToString(element);

  assert.ok(!html.includes('<script>'), 'Không được render thẻ script thô');
  assert.ok(!html.includes('onerror="alert(1)"'), 'Không được render thuộc tính onerror');
  assert.ok(html.includes('&lt;script&gt;'), 'Thẻ script phải bị escape sang ký tự an toàn');
});

test('hỗ trợ tiếng Việt UTF-8 và cú pháp Markdown (đậm, nghiêng, danh sách)', () => {
  const markdown = '**Đề bài:** Tìm giá trị *x* sao cho:\n- Điểm $A(1, 2)$\n- Điểm $B(3, 4)$';
  const element = createMathElement({ content: markdown });
  const html = renderToString(element);

  assert.ok(html.includes('<strong>Đề bài:</strong>'), 'Phải parse được cú pháp in đậm');
  assert.ok(html.includes('<em>x</em>'), 'Phải parse được cú pháp in nghiêng');
  assert.ok(html.includes('<li>'), 'Phải parse được danh sách');
});

test('chế độ inline không tạo thẻ khối p', () => {
  const inlineContent = 'Tỷ lệ $\\dfrac{7}{18}$';
  const element = createMathElement({ content: inlineContent, inline: true });
  const html = renderToString(element);

  assert.ok(!html.includes('<p>'), 'Chế độ inline không được chứa thẻ p');
  assert.ok(html.includes('<span>'), 'Chế độ inline phải bọc bằng thẻ span');
});

test('xử lý chuỗi rỗng hoặc null an toàn', () => {
  assert.doesNotThrow(() => {
    const emptyElement = createMathElement({ content: '' });
    renderToString(emptyElement);
    const nullElement = createMathElement({ content: null });
    renderToString(nullElement);
  });
});
