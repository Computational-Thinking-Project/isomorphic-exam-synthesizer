import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

/**
 * Cấu hình plugin KaTeX an toàn cho toàn bộ ứng dụng:
 * - throwOnError: false để không quăng lỗi làm sập giao diện
 * - errorColor: '#ef4444' để bôi đỏ phần công thức lỗi
 * - strict: false để chấp nhận các ký hiệu thông dụng
 */
export const katexPlugins = [
  remarkMath,
  [
    rehypeKatex,
    {
      throwOnError: false,
      errorColor: '#ef4444',
      strict: false,
    },
  ],
];

/**
 * Components định dạng danh sách (ol, ul, li) cho ReactMarkdown
 * Khắc phục hiện tượng Tailwind Preflight xóa số thứ tự và bullet.
 */
export const markdownListComponents = {
  ol: ({ children, className = '', ...props }) =>
    React.createElement(
      'ol',
      { className: `list-decimal pl-6 space-y-1 my-2 text-slate-100 ${className}`, ...props },
      children,
    ),
  ul: ({ children, className = '', ...props }) =>
    React.createElement(
      'ul',
      { className: `list-disc pl-6 space-y-1 my-2 text-slate-100 ${className}`, ...props },
      children,
    ),
  li: ({ children, className = '', ...props }) =>
    React.createElement(
      'li',
      { className: `pl-1 leading-relaxed ${className}`, ...props },
      children,
    ),
};

/**
 * Tạo element ReactMarkdown với cấu hình toán học chuẩn
 * @param {Object} options
 * @param {string} options.content - Nội dung Markdown/LaTeX
 * @param {boolean} [options.inline=false] - Chế độ hiển thị inline
 * @returns {React.ReactElement}
 */
export function createMathElement({ content = '', inline = false }) {
  const safeContent = typeof content === 'string' ? content : String(content ?? '');

  return React.createElement(
    ReactMarkdown,
    {
      remarkPlugins: [katexPlugins[0]],
      rehypePlugins: [katexPlugins[1]],
      components: {
        ...markdownListComponents,
        ...(inline
          ? {
              p: ({ children }) => React.createElement('span', null, children),
            }
          : {}),
      },
    },
    safeContent,
  );
}
