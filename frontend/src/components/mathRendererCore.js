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
      components: inline
        ? {
            p: ({ children }) => React.createElement('span', null, children),
          }
        : undefined,
    },
    safeContent,
  );
}
