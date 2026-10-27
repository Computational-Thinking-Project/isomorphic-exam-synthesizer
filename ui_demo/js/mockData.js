// mockData.js - Dữ liệu mẫu chuẩn Toán THPT phục vụ demo UI
window.MOCK_DATA = {
  session: {
    id: "sess_demo_2026",
    title: "Đề Kiểm Tra Định Kỳ Giải Tích 12 - Chương 1 & 2",
    subject: "Toán học THPT",
    status: "draft",
    created_at: "2026-10-27T08:30:00Z",
    n_versions: 4
  },
  source_questions: [
    {
      id: "sq_1",
      question_no: 1,
      stem: "Cho hàm số $y = x^3 - 3x + 2$. Điểm cực đại của đồ thị hàm số là:",
      options: [
        { key: "A", text: "$(-1; 4)$" },
        { key: "B", text: "$(1; 0)$" },
        { key: "C", text: "$(-1; 0)$" },
        { key: "D", text: "$(1; 4)$" }
      ],
      correct_key: "A",
      solution: "Ta có $y' = 3x^2 - 3 = 0 \\Leftrightarrow x = \\pm 1$. Bảng biến thiên cho thấy hàm số đạt cực đại tại $x = -1$, suy ra $y(-1) = (-1)^3 - 3(-1) + 2 = 4$. Vậy điểm cực đại là $(-1; 4)$."
    },
    {
      id: "sq_2",
      question_no: 2,
      stem: "Tìm tập nghiệm $S$ của phương trình $\\log_2(x - 1) = 3$.",
      options: [
        { key: "A", text: "$S = \\{9\\}$" },
        { key: "B", text: "$S = \\{7\\}$" },
        { key: "C", text: "$S = \\{10\\}$" },
        { key: "D", text: "$S = \\{8\\}$" }
      ],
      correct_key: "A",
      solution: "Điều kiện xác định: $x - 1 > 0 \\Leftrightarrow x > 1$. Phương trình tương đương: $x - 1 = 2^3 = 8 \\Leftrightarrow x = 9$ (thỏa mãn điều kiện). Vậy $S = \\{9\\}$."
    },
    {
      id: "sq_3",
      question_no: 3,
      stem: "Tính tích phân $I = \\int_{0}^{1} (2x + 1) dx$.",
      options: [
        { key: "A", text: "$I = 2$" },
        { key: "B", text: "$I = 1$" },
        { key: "C", text: "$I = 3$" },
        { key: "D", text: "$I = \\frac{3}{2}$" }
      ],
      correct_key: "A",
      solution: "Ta có $I = [x^2 + x]_{0}^{1} = (1^2 + 1) - (0^2 + 0) = 2$."
    },
    {
      id: "sq_4",
      question_no: 4,
      stem: "Nghiệm của phương trình $2^{2x-1} = 8$ là:",
      options: [
        { key: "A", text: "$x = 2$" },
        { key: "B", text: "$x = 1$" },
        { key: "C", text: "$x = 3$" },
        { key: "D", text: "$x = \\frac{5}{2}$" }
      ],
      correct_key: "A",
      has_unparsed_omml: true, // Mock cảnh báo bóc tách: công thức toán OMML/ảnh chưa trích xuất trọn vẹn
      solution: "Phương trình tương đương $2^{2x-1} = 2^3 \\Leftrightarrow 2x - 1 = 3 \\Leftrightarrow 2x = 4 \\Leftrightarrow x = 2$."
    },
    {
      id: "sq_5",
      question_no: 5,
      stem: "Hàm số nào dưới đây đồng biến trên khoảng $(-\\infty; +\\infty)$?",
      options: [
        { key: "A", text: "$y = x^3 + 2x$" },
        { key: "B", text: "$y = -x^3 + 3x$" },
        { key: "C", text: "$y = \\frac{x-1}{x+2}$" },
        { key: "D", text: "$y = x^4 + 2x^2$" }
      ],
      correct_key: "A",
      solution: "Xét $y = x^3 + 2x$, có đạo hàm $y' = 3x^2 + 2 > 0, \\forall x \\in \\mathbb{R}$. Do đó hàm số luôn đồng biến trên $\\mathbb{R}$."
    }
  ],
  // Biến thể cho 4 mã đề (101, 102, 103, 104)
  variants: {
    "101": [
      {
        id: "v_101_1",
        question_no: 1,
        source_id: "sq_1",
        status: "pending_review",
        is_reverted: false,
        stem: "Cho hàm số $y = x^3 - 3x + 5$. Điểm cực đại của đồ thị hàm số là:",
        options: [
          { key: "A", text: "$(-1; 7)$" },
          { key: "B", text: "$(1; 3)$" },
          { key: "C", text: "$(-1; 3)$" },
          { key: "D", text: "$(1; 7)$" }
        ],
        correct_key: "A",
        solution: "Ta có $y' = 3x^2 - 3 = 0 \\Leftrightarrow x = \\pm 1$. Tại $x = -1$, $y(-1) = (-1)^3 - 3(-1) + 5 = 7$. Vậy điểm cực đại là $(-1; 7)$."
      },
      {
        id: "v_101_2",
        question_no: 2,
        source_id: "sq_2",
        status: "approved",
        is_reverted: false,
        stem: "Tìm tập nghiệm $S$ của phương trình $\\log_3(x - 2) = 2$.",
        options: [
          { key: "A", text: "$S = \\{11\\}$" },
          { key: "B", text: "$S = \\{8\\}$" },
          { key: "C", text: "$S = \\{7\\}$" },
          { key: "D", text: "$S = \\{10\\}$" }
        ],
        correct_key: "A",
        solution: "ĐKXĐ: $x > 2$. Phương trình $\\Leftrightarrow x - 2 = 3^2 = 9 \\Leftrightarrow x = 11$. Vậy $S = \\{11\\}$."
      },
      {
        id: "v_101_3",
        question_no: 3,
        source_id: "sq_3",
        status: "pending_review",
        is_reverted: false,
        stem: "Tính tích phân $I = \\int_{0}^{2} (2x + 1) dx$.",
        options: [
          { key: "A", text: "$I = 6$" },
          { key: "B", text: "$I = 5$" },
          { key: "C", text: "$I = 4$" },
          { key: "D", text: "$I = 7$" }
        ],
        correct_key: "A",
        solution: "Ta có $I = [x^2 + x]_{0}^{2} = (2^2 + 2) - 0 = 6$."
      },
      {
        id: "v_101_4",
        question_no: 4,
        source_id: "sq_4",
        status: "pending_review",
        is_reverted: false,
        has_security_warning: true,
        stem: "Nghiệm của phương trình $3^{2x-1} = 27$ là:",
        options: [
          { key: "A", text: "$x = 2$" },
          { key: "B", text: "$x = 1$" },
          { key: "C", text: "$x = 3$" },
          { key: "D", text: "$x = 4$" }
        ],
        correct_key: "A",
        solution: "$3^{2x-1} = 3^3 \\Leftrightarrow 2x - 1 = 3 \\Leftrightarrow 2x = 4 \\Leftrightarrow x = 2$."
      },
      {
        id: "v_101_5",
        question_no: 5,
        source_id: "sq_5",
        status: "pending_review",
        is_reverted: false,
        stem: "Hàm số nào dưới đây đồng biến trên khoảng $(-\\infty; +\\infty)$?",
        options: [
          { key: "A", text: "$y = x^3 + 5x$" },
          { key: "B", text: "$y = -x^3 + 2x$" },
          { key: "C", text: "$y = \\frac{x-2}{x+1}$" },
          { key: "D", text: "$y = x^4 + 4x^2$" }
        ],
        correct_key: "A",
        solution: "Xét $y = x^3 + 5x$, $y' = 3x^2 + 5 > 0, \\forall x \\in \\mathbb{R}$. Hàm số luôn đồng biến trên $\\mathbb{R}$."
      }
    ],
    "102": [
      {
        id: "v_102_1",
        question_no: 1,
        source_id: "sq_1",
        status: "approved",
        stem: "Cho hàm số $y = -x^3 + 3x + 1$. Điểm cực tiểu của đồ thị hàm số là:",
        options: [
          { key: "A", text: "$(-1; -1)$" },
          { key: "B", text: "$(1; 3)$" },
          { key: "C", text: "$(-1; 3)$" },
          { key: "D", text: "$(1; -1)$" }
        ],
        correct_key: "A",
        solution: "$y' = -3x^2 + 3 = 0 \\Leftrightarrow x = \\pm 1$. Điểm cực tiểu là $(-1; -1)$."
      },
      {
        id: "v_102_2",
        question_no: 2,
        source_id: "sq_2",
        status: "approved",
        stem: "Tìm tập nghiệm $S$ của phương trình $\\log_2(x + 3) = 4$.",
        options: [
          { key: "A", text: "$S = \\{13\\}$" },
          { key: "B", text: "$S = \\{11\\}$" },
          { key: "C", text: "$S = \\{15\\}$" },
          { key: "D", text: "$S = \\{16\\}$" }
        ],
        correct_key: "A",
        solution: "$x + 3 = 2^4 = 16 \\Leftrightarrow x = 13$."
      },
      {
        id: "v_102_3",
        question_no: 3,
        source_id: "sq_3",
        status: "approved",
        stem: "Tính tích phân $I = \\int_{1}^{2} (2x - 1) dx$.",
        options: [
          { key: "A", text: "$I = 2$" },
          { key: "B", text: "$I = 1$" },
          { key: "C", text: "$I = 3$" },
          { key: "D", text: "$I = 4$" }
        ],
        correct_key: "A",
        solution: "$I = [x^2 - x]_{1}^{2} = (4 - 2) - (1 - 1) = 2$."
      },
      {
        id: "v_102_4",
        question_no: 4,
        source_id: "sq_4",
        status: "approved",
        stem: "Nghiệm của phương trình $5^{2x-3} = 25$ là:",
        options: [
          { key: "A", text: "$x = \\frac{5}{2}$" },
          { key: "B", text: "$x = 2$" },
          { key: "C", text: "$x = 3$" },
          { key: "D", text: "$x = \\frac{3}{2}$" }
        ],
        correct_key: "A",
        solution: "$2x - 3 = 2 \\Leftrightarrow 2x = 5 \\Leftrightarrow x = 5/2$."
      },
      {
        id: "v_102_5",
        question_no: 5,
        source_id: "sq_5",
        status: "approved",
        stem: "Hàm số nào dưới đây nghịch biến trên khoảng $(-\\infty; +\\infty)$?",
        options: [
          { key: "A", text: "$y = -x^3 - x$" },
          { key: "B", text: "$y = x^3 + x$" },
          { key: "C", text: "$y = -x^4 - x^2$" },
          { key: "D", text: "$y = \\frac{-x+1}{x-2}$" }
        ],
        correct_key: "A",
        solution: "$y' = -3x^2 - 1 < 0, \\forall x \\in \\mathbb{R}$. Hàm số nghịch biến trên $\\mathbb{R}$."
      }
    ],
    "103": [
      {
        id: "v_103_1",
        question_no: 1,
        source_id: "sq_1",
        status: "approved",
        stem: "Cho hàm số $y = x^3 - 12x + 1$. Điểm cực đại của đồ thị hàm số là:",
        options: [
          { key: "A", text: "$(-2; 17)$" },
          { key: "B", text: "$(2; -15)$" },
          { key: "C", text: "$(-2; -15)$" },
          { key: "D", text: "$(2; 17)$" }
        ],
        correct_key: "A",
        solution: "$y' = 3x^2 - 12 = 0 \\Leftrightarrow x = \\pm 2$. Cực đại tại $x = -2 \\Rightarrow y = (-2)^3 - 12(-2) + 1 = 17$."
      },
      {
        id: "v_103_2",
        question_no: 2,
        source_id: "sq_2",
        status: "approved",
        stem: "Tìm tập nghiệm $S$ của phương trình $\\log_5(2x - 1) = 2$.",
        options: [
          { key: "A", text: "$S = \\{13\\}$" },
          { key: "B", text: "$S = \\{12\\}$" },
          { key: "C", text: "$S = \\{10\\}$" },
          { key: "D", text: "$S = \\{14\\}$" }
        ],
        correct_key: "A",
        solution: "$2x - 1 = 25 \\Leftrightarrow 2x = 26 \\Leftrightarrow x = 13$."
      },
      {
        id: "v_103_3",
        question_no: 3,
        source_id: "sq_3",
        status: "approved",
        stem: "Tính tích phân $I = \\int_{0}^{1} (3x^2 + 2x) dx$.",
        options: [
          { key: "A", text: "$I = 2$" },
          { key: "B", text: "$I = 1$" },
          { key: "C", text: "$I = 3$" },
          { key: "D", text: "$I = 5$" }
        ],
        correct_key: "A",
        solution: "$I = [x^3 + x^2]_{0}^{1} = 1 + 1 = 2$."
      },
      {
        id: "v_103_4",
        question_no: 4,
        source_id: "sq_4",
        status: "approved",
        stem: "Nghiệm của phương trình $2^{3x-2} = 16$ là:",
        options: [
          { key: "A", text: "$x = 2$" },
          { key: "B", text: "$x = 3$" },
          { key: "C", text: "$x = 1$" },
          { key: "D", text: "$x = 4$" }
        ],
        correct_key: "A",
        solution: "$3x - 2 = 4 \\Leftrightarrow 3x = 6 \\Leftrightarrow x = 2$."
      },
      {
        id: "v_103_5",
        question_no: 5,
        source_id: "sq_5",
        status: "approved",
        stem: "Hàm số nào dưới đây đồng biến trên khoảng $(-\\infty; +\\infty)$?",
        options: [
          { key: "A", text: "$y = 2x^3 + 3x - 1$" },
          { key: "B", text: "$y = -2x^3 + 3x$" },
          { key: "C", text: "$y = \\frac{2x-1}{x+1}$" },
          { key: "D", text: "$y = x^4 + 1$" }
        ],
        correct_key: "A",
        solution: "$y' = 6x^2 + 3 > 0, \\forall x$. Hàm số luôn đồng biến trên $\\mathbb{R}$."
      }
    ],
    "104": [
      {
        id: "v_104_1",
        question_no: 1,
        source_id: "sq_1",
        status: "approved",
        stem: "Cho hàm số $y = x^3 - 3x - 2$. Điểm cực đại của đồ thị hàm số là:",
        options: [
          { key: "A", text: "$(-1; 0)$" },
          { key: "B", text: "$(1; -4)$" },
          { key: "C", text: "$(-1; -4)$" },
          { key: "D", text: "$(1; 0)$" }
        ],
        correct_key: "A",
        solution: "Cực đại tại $x = -1, y = (-1)^3 - 3(-1) - 2 = 0$. Tọa độ $(-1; 0)$."
      },
      {
        id: "v_104_2",
        question_no: 2,
        source_id: "sq_2",
        status: "approved",
        stem: "Tìm tập nghiệm $S$ của phương trình $\\log_2(3x - 2) = 4$.",
        options: [
          { key: "A", text: "$S = \\{6\\}$" },
          { key: "B", text: "$S = \\{5\\}$" },
          { key: "C", text: "$S = \\{7\\}$" },
          { key: "D", text: "$S = \\{4\\}$" }
        ],
        correct_key: "A",
        solution: "$3x - 2 = 16 \\Leftrightarrow 3x = 18 \\Leftrightarrow x = 6$."
      },
      {
        id: "v_104_3",
        question_no: 3,
        source_id: "sq_3",
        status: "approved",
        stem: "Tính tích phân $I = \\int_{0}^{2} (3x^2 - 2x) dx$.",
        options: [
          { key: "A", text: "$I = 4$" },
          { key: "B", text: "$I = 2$" },
          { key: "C", text: "$I = 6$" },
          { key: "D", text: "$I = 8$" }
        ],
        correct_key: "A",
        solution: "$I = [x^3 - x^2]_{0}^{2} = (8 - 4) - 0 = 4$."
      },
      {
        id: "v_104_4",
        question_no: 4,
        source_id: "sq_4",
        status: "approved",
        stem: "Nghiệm của phương trình $7^{2x-5} = 49$ là:",
        options: [
          { key: "A", text: "$x = \\frac{7}{2}$" },
          { key: "B", text: "$x = 3$" },
          { key: "C", text: "$x = 4$" },
          { key: "D", text: "$x = 2$" }
        ],
        correct_key: "A",
        solution: "$2x - 5 = 2 \\Leftrightarrow 2x = 7 \\Leftrightarrow x = 7/2$."
      },
      {
        id: "v_104_5",
        question_no: 5,
        source_id: "sq_5",
        status: "approved",
        stem: "Hàm số nào dưới đây đồng biến trên khoảng $(-\\infty; +\\infty)$?",
        options: [
          { key: "A", text: "$y = 4x^3 + x$" },
          { key: "B", text: "$y = -4x^3 + x$" },
          { key: "C", text: "$y = \\frac{4x-1}{x+2}$" },
          { key: "D", text: "$y = x^4 + 3$" }
        ],
        correct_key: "A",
        solution: "$y' = 12x^2 + 1 > 0, \\forall x \\in \\mathbb{R}$. Hàm số đồng biến trên $\\mathbb{R}$."
      }
    ]
  }
};
