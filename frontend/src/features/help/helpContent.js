export const stages = [
  {
    title: 'Stage 1 · Nhập và xác nhận đề',
    description: 'Dán nội dung hoặc tải tệp DOCX, TeX, Markdown. Kiểm tra câu hỏi, phương án, đáp án và lời giải nếu có. Xác nhận đề nguồn rồi chờ cấu trúc đề (Blueprint) sẵn sàng.',
  },
  {
    title: 'Stage 2 · Cấu hình và sinh đề',
    description: 'Chọn 1–4 mã đề rồi bắt đầu sinh. Theo dõi tiến trình và kiểm tra câu còn thiếu.',
  },
  {
    title: 'Stage 3 · Duyệt, xem trước và xuất đề',
    description: 'Duyệt câu hoặc tạo lại khi có thể. Tại Final Preview, chọn giữ nguyên hoặc xáo trộn thứ tự câu hỏi, chốt và xem lại bản cuối. Phê duyệt rồi tạo và tải ZIP.',
  },
];

export const questions = [
  {
    title: 'Website hỗ trợ những định dạng đề nguồn nào?',
    answer: 'Bạn có thể tải tệp Word (.docx), LaTeX (.tex), Markdown (.md) hoặc dán nội dung Markdown hay LaTeX vào ô nhập văn bản.',
  },
  {
    title: 'Có thể tải PDF lên làm đề nguồn không?',
    answer: 'PDF chỉ có ở đầu ra. Nếu đề nguồn ở dạng PDF, hãy chuyển nội dung sang một định dạng được hỗ trợ và kiểm tra lại câu hỏi, công thức và đáp án sau khi nhập.',
  },
  {
    title: 'Một lần có thể tạo tối đa bao nhiêu mã đề?',
    answer: 'Bạn có thể chọn từ 1 đến 4 mã đề cho một lần sinh.',
  },
  {
    title: 'Có thể thay đổi số mã đề đã chọn trước khi sinh không?',
    answer: 'Có, khi màn cấu hình ở Stage 2 vẫn cho chỉnh sửa. Chọn số mã đề mong muốn trước khi bấm Bắt đầu sinh đề.',
  },
  {
    title: 'Vì sao không thể bắt đầu sinh đề?',
    answer: 'Kiểm tra đề nguồn đã được xác nhận và cấu trúc đề đã sẵn sàng. Nếu đủ điều kiện mà vẫn bị chặn, hãy đọc thông báo của phiên để biết cấu hình hoặc trạng thái nào cần xử lý.',
  },
  {
    title: 'Có thể tiếp tục phiên đang làm sau khi tải lại trang không?',
    answer: 'Có. Mở lại phiên trong Thư viện đề để tiếp tục từ trạng thái đã lưu. Nếu phiên đang sinh đề, bạn có thể tiếp tục theo dõi tiến trình.',
  },
  {
    title: 'Nếu một số câu sinh thất bại thì xử lý thế nào?',
    answer: 'Kiểm tra câu nào còn thiếu và dùng thao tác thử lại cho phần chưa hoàn tất khi giao diện cung cấp. Hoàn tất đủ câu và duyệt các kết quả trước khi chuyển sang xem trước bản cuối.',
  },
  {
    title: 'Có thể xáo trộn thứ tự câu hỏi không?',
    answer: 'Có. Tại Final Preview của Stage 3, chọn giữ nguyên hoặc xáo trộn thứ tự câu hỏi trước khi chốt thứ tự. Kiểm tra kết quả trên bản xem trước rồi phê duyệt.',
  },
  {
    title: 'Vì sao cần kiểm tra và duyệt đề trước khi xuất?',
    answer: 'Kiểm tra giúp phát hiện sai sót trong câu hỏi, đáp án và lời giải. Sau khi duyệt từng câu và kiểm tra bản cuối, phê duyệt bộ đề để khóa nội dung và mở bước xuất đề.',
  },
  {
    title: 'File ZIP sau khi xuất chứa những gì?',
    answer: 'Bạn tải một gói ZIP. Trong gói, mỗi mã đề có tài liệu PDF, LaTeX và Markdown, mỗi tài liệu gồm đề, bảng đáp án và phần lời giải theo dữ liệu có sẵn. Hãy tách phần đề học sinh trước khi chia sẻ.',
  },
];

export const troubleshooting = [
  {
    title: 'Tệp hoặc nội dung đề không hợp lệ',
    description: 'Kiểm tra định dạng và thông báo lỗi. Sửa hoặc thay tệp, rồi kiểm tra phần câu hỏi và đáp án đã trích xuất trước khi xác nhận.',
  },
  {
    title: 'Không đăng nhập được',
    description: 'Kiểm tra kết nối và tài khoản Google đang dùng. Nếu phiên đăng nhập đã hết hạn, hãy đăng nhập lại. Dùng thao tác thử lại nếu màn hình đang báo lỗi kiểm tra phiên hoặc tải hồ sơ.',
  },
  {
    title: 'Cấu trúc đề chưa sẵn sàng',
    description: 'Chờ hệ thống chuẩn bị cấu trúc đề sau khi xác nhận. Kiểm tra lại trạng thái khi cần và dùng thao tác thử lại nếu giao diện cung cấp.',
  },
  {
    title: 'Sinh đề thất bại hoặc còn thiếu câu',
    description: 'Mở lại phiên để xác định phần đã hoàn tất. Dùng thao tác thử lại khi trạng thái phiên cho phép, sau đó kiểm tra các kết quả trước khi duyệt.',
  },
  {
    title: 'Mất kết nối khi sinh đề',
    description: 'Kết nối lại hoặc mở lại phiên để tải tiến trình hiện tại. Nếu chưa biết lượt sinh trước đã được nhận hay chưa, kiểm tra trạng thái phiên trước khi bấm thử lại.',
  },
  {
    title: 'Không thể duyệt hoặc phê duyệt',
    description: 'Tải lại dữ liệu nếu câu vừa thay đổi hoặc trạng thái chưa rõ. Kiểm tra đã sinh đủ và duyệt đủ câu, rồi chốt thứ tự và mở bản xem trước hợp lệ trước khi phê duyệt.',
  },
  {
    title: 'ZIP chưa sẵn sàng hoặc tạo gói thất bại',
    description: 'Kiểm tra bộ đề đã được phê duyệt và xem trạng thái xuất. Nếu hệ thống vẫn đang tạo gói, hãy chờ và kiểm tra lại. Nếu lỗi đã được xác nhận, dùng thao tác thử lại hoặc tải lại khi giao diện cung cấp.',
  },
];

export const limitations = [
  'AI có thể tạo câu hỏi, đáp án hoặc lời giải sai.',
  'Bộ kiểm tra tự động có thể bỏ sót lỗi.',
  'Độ khó có thể khác nhau giữa các mã đề.',
  'Giáo viên cần kiểm tra nội dung, đáp án và lời giải trước khi sử dụng.',
];
