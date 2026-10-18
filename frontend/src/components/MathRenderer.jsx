import { Component } from 'react';
import ReactMarkdown from 'react-markdown';
import { katexPlugins } from './mathRendererCore.js';
import 'katex/dist/katex.min.css';

/**
 * Error boundary nội bộ để bảo vệ ứng dụng khỏi sập màn hình
 * nếu cú pháp LaTeX hoặc Markdown parser gặp lỗi nghiêm trọng.
 */
class MathErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.warn('MathRenderer parser fallback:', error?.message || error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <span className="font-mono text-xs text-rose-400">
          {this.props.fallbackContent || '[Lỗi hiển thị công thức]'}
        </span>
      );
    }
    return this.props.children;
  }
}

/**
 * Component hiển thị Markdown và công thức toán học KaTeX ($...$, $$...$$).
 *
 * @param {Object} props
 * @param {string} [props.content=''] - Nội dung text Markdown kết hợp LaTeX
 * @param {string} [props.className=''] - Class Tailwind bổ sung
 * @param {boolean} [props.inline=false] - Hiển thị dạng inline span thay vì khối div
 */
export default function MathRenderer({
  content = '',
  className = '',
  inline = false,
}) {
  const safeContent = typeof content === 'string' ? content : String(content ?? '');

  if (!safeContent.trim()) {
    return null;
  }

  const Container = inline ? 'span' : 'div';

  return (
    <MathErrorBoundary fallbackContent={safeContent}>
      <Container
        className={`math-renderer ${
          inline ? 'inline-block' : 'space-y-2'
        } ${className}`}
      >
        <ReactMarkdown
          remarkPlugins={[katexPlugins[0]]}
          rehypePlugins={[katexPlugins[1]]}
          components={
            inline
              ? {
                  // Thay thẻ <p> thành <span> khi ở chế độ inline để tránh lồng khối không hợp lệ
                  p: ({ children }) => <span>{children}</span>,
                }
              : undefined
          }
        >
          {safeContent}
        </ReactMarkdown>
      </Container>
    </MathErrorBoundary>
  );
}
