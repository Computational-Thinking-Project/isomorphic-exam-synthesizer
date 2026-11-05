const descriptions = new Map([
  ['MISSING_ANSWER', ['Thiếu đáp án đúng', 'Xác định đáp án đúng (A/B/C/D) cho câu hỏi, hoặc bổ sung đáp án tương ứng vào bảng đáp án cuối đề.']],
  ['UNPARSED_OMML', ['Chưa đọc được công thức Word', 'Chuyển công thức bị lỗi sang văn bản hoặc LaTeX phù hợp rồi nạp lại nguồn.']],
  ['UNPARSED_IMAGE', ['Chưa đọc được hình ảnh', 'Dùng nguồn Đại số dạng văn bản/LaTeX. Bài bắt buộc hình vẽ nằm ngoài phạm vi hiện tại.']],
  ['AMBIGUOUS_FORMAT', ['Cấu trúc câu hỏi chưa rõ', 'Tách rõ số câu, nội dung, các phương án A–D và đáp án đúng trong nguồn.']],
  ['EMPTY_STEM', ['Thiếu nội dung câu hỏi', 'Bổ sung nội dung câu hỏi trong file hoặc văn bản nguồn.']],
  ['CONFLICTING_ANSWER_KEY', ['Đáp án không thống nhất', 'Chốt một đáp án đúng và đồng bộ giữa câu hỏi với bảng đáp án cuối đề.']],
  ['SURPLUS_ANSWER_KEY', ['Có đáp án không khớp câu hỏi', 'Đối chiếu số câu với bảng đáp án; sửa hoặc bỏ đáp án thừa trong nguồn.']],
  ['DUPLICATE_QUESTION_NO', ['Số câu bị trùng', 'Đánh số các câu không trùng nhau và cập nhật bảng đáp án tương ứng.']],
  ['INVALID_QUESTION_NO', ['Số câu không hợp lệ', 'Dùng số nguyên dương cho số câu và đối chiếu lại bảng đáp án.']],
  ['INVALID_FORMAT', ['Nguồn chưa đúng cấu trúc', 'Kiểm tra nội dung câu hỏi, đủ bốn phương án A–D, đáp án và số câu từ 1 đến 20.']],
]);
const fallback = ['Lỗi nội dung chưa xác định', 'Kiểm tra cấu trúc câu hỏi, các phương án và đáp án trong nguồn rồi nạp lại.'];
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' ? value.trim() : '';
const useful = item => isRecord(item) && (text(item.error_type) !== '' || text(item.message) !== '');

/** Read the ingestion envelope only; leave the original error and source untouched. */
export function readIncompleteError(cause) {
  if (cause?.response?.status !== 422) return null;
  const detail = cause.response.data?.detail;
  if (!isRecord(detail) || !Array.isArray(detail.errors) || !detail.errors.some(useful)) return null;
  return {
    message: 'Chưa đọc được đầy đủ nội dung đề.',
    errors: detail.errors.map(value => {
      const item = isRecord(value) ? value : {};
      const [title, guidance] = descriptions.get(text(item.error_type)) ?? fallback;
      const location = item.question_no === 0 ? 'Toàn đề'
        : Number.isInteger(item.question_no) && item.question_no > 0 ? `Câu ${item.question_no}` : 'Chưa xác định vị trí';
      return { location, title, detail: text(item.message), guidance };
    }),
  };
}
