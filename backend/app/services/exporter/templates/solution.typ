// Solution Paper Template in Typst (TASK-306)
// Compiles A4 Vietnamese answer matrix table and step-by-step solutions.

#set document(title: [Hướng dẫn giải và Bảng đáp án], author: [Hệ thống Isomorphic Exam Synthesizer])
#set page(
  paper: "a4",
  margin: (top: 2cm, bottom: 2cm, left: 2cm, right: 2cm),
  footer: locate(loc => {
    let page_number = counter(page).at(loc).first()
    let total_pages = counter(page).final(loc).first()
    align(center)[
      #text(size: 9pt, fill: luma(100))[
        Trang #page_number / #total_pages
      ]
    ]
  })
)
#set text(
  font: ("Liberation Serif", "Times New Roman", "DejaVu Serif"),
  size: 11pt,
  lang: "vi"
)
#set par(justify: true, leading: 0.7em)

// Header layout
#align(center)[
  #text(weight: "bold", size: 14pt)[HƯỚNG DẪN GIẢI VÀ BẢNG ĐÁP ÁN CHI TIẾT]\
  #text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: #version_code]\
  #text(style: "italic", size: 10pt)[(Hệ thống tự động biên dịch và đối soát ma trận đáp án)]
]

#v(8pt)
#line(length: 100%, stroke: 1pt)
#v(10pt)

// Section 1: Quick answer key matrix
#text(weight: "bold", size: 12pt)[I. BẢNG ĐÁP ÁN NHANH]
#v(6pt)

#answer_matrix_table

#v(16pt)

// Section 2: Step-by-step detailed explanations
#text(weight: "bold", size: 12pt)[II. LỜI GIẢI CHI TIẾT TỪNG CÂU]
#v(8pt)

#solutions_content
