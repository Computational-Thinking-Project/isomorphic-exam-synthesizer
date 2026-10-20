import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { createMathElement } from './mathRendererCore.js';

// Đăng ký test-loader để Node có thể import trực tiếp MathRenderer.jsx và xử lý CSS
register('../test-loader.mjs', import.meta.url);
const { default: MathRenderer, MathErrorBoundary } = await import('./MathRenderer.jsx');

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

test('hỗ trợ tiếng Việt UTF-8 và danh sách ol, ul có class Tailwind chuẩn (không bị Preflight xóa số)', () => {
  const markdown = '1. Bước giải thứ nhất\n2. Bước giải thứ hai\n- Ghi chú thêm';
  const element = createMathElement({ content: markdown });
  const html = renderToString(element);

  assert.ok(html.includes('<ol class="list-decimal pl-6'), 'Danh sách có thứ tự phải có class list-decimal và padding');
  assert.ok(html.includes('<ul class="list-disc pl-6'), 'Danh sách không thứ tự phải có class list-disc và padding');
  assert.ok(html.includes('Bước giải thứ nhất'), 'Phải hiển thị nội dung tiếng Việt');
});

test('hỗ trợ danh sách lồng nhau (nested list)', () => {
  const markdown = '1. Bước 1\n   - Điểm a: $x=1$\n   - Điểm b: $x=2$\n2. Bước 2';
  const element = createMathElement({ content: markdown });
  const html = renderToString(element);

  assert.ok(html.includes('list-decimal'), 'Cấp 1 phải là list-decimal');
  assert.ok(html.includes('list-disc'), 'Cấp 2 lồng nhau phải là list-disc');
  assert.ok(html.includes('katex'), 'Trong danh sách lồng vẫn render công thức KaTeX');
});

test('chế độ inline không tạo thẻ khối p', () => {
  const inlineContent = 'Tỷ lệ $\\dfrac{7}{18}$';
  const element = createMathElement({ content: inlineContent, inline: true });
  const html = renderToString(element);

  assert.ok(!html.includes('<p>'), 'Chế độ inline không được chứa thẻ p');
  assert.ok(html.includes('<span>'), 'Chế độ inline phải bọc bằng thẻ span');
});

// --- Test trực tiếp component MathRenderer.jsx ---

test('MathRenderer component render wrapper div và class Tailwind tùy biến', () => {
  const element = React.createElement(MathRenderer, {
    content: 'Phương trình $y = ax + b$',
    className: 'custom-math-class',
  });
  const html = renderToString(element);

  assert.ok(html.includes('class="math-renderer space-y-2 custom-math-class"'), 'Phải bọc wrapper div với custom class');
  assert.ok(html.includes('katex'), 'Nội dung bên trong phải chứa công thức KaTeX');
});

test('MathRenderer ở chế độ inline=true sử dụng wrapper span', () => {
  const element = React.createElement(MathRenderer, {
    content: '$\\sqrt{2}$',
    inline: true,
    className: 'text-sky-300',
  });
  const html = renderToString(element);

  assert.ok(html.includes('class="math-renderer inline-block text-sky-300"'), 'Inline phải bọc bằng span inline-block');
  assert.ok(html.includes('<span'), 'Bắt đầu bằng thẻ span');
});

test('MathRenderer trả về null khi content rỗng hoặc chỉ có khoảng trắng', () => {
  const emptyElement = React.createElement(MathRenderer, { content: '' });
  assert.equal(renderToString(emptyElement), '', 'Content rỗng phải render chuỗi rỗng');

  const whitespaceElement = React.createElement(MathRenderer, { content: '   \n  ' });
  assert.equal(renderToString(whitespaceElement), '', 'Chỉ chứa khoảng trắng phải render chuỗi rỗng');
});

test('MathErrorBoundary.getDerivedStateFromProps tự động reset hasError về false khi content thay đổi', () => {
  const previousState = {
    hasError: true,
    prevFallbackContent: 'công thức lỗi cũ',
  };

  // Trường hợp 1: content không đổi -> không reset
  const noChange = MathErrorBoundary.getDerivedStateFromProps(
    { fallbackContent: 'công thức lỗi cũ' },
    previousState,
  );
  assert.equal(noChange, null, 'Khi content không đổi thì không cập nhật state');

  // Trường hợp 2: content đổi sang nội dung mới -> reset hasError = false
  const updatedState = MathErrorBoundary.getDerivedStateFromProps(
    { fallbackContent: 'công thức mới $x=1$' },
    previousState,
  );
  assert.deepEqual(
    updatedState,
    { hasError: false, prevFallbackContent: 'công thức mới $x=1$' },
    'Khi content đổi, phải tự động reset hasError: false và cập nhật prevFallbackContent',
  );
});

test('MathErrorBoundary render fallback span khi hasError = true', () => {
  const boundary = new MathErrorBoundary({ fallbackContent: 'Nội dung dự phòng' });
  boundary.state = { hasError: true, prevFallbackContent: 'Nội dung dự phòng' };
  const html = renderToString(boundary.render());

  assert.ok(html.includes('text-rose-400'), 'Phải có class màu cảnh báo');
  assert.ok(html.includes('Nội dung dự phòng'), 'Phải hiển thị fallbackContent');
});
