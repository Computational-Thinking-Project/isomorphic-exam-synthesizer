// Exam Paper Template in Typst (TASK-306)
// Compiles A4 Vietnamese standardized multiple-choice examination papers.

#set document(title: [Đề thi trắc nghiệm], author: "Isomorphic Exam Synthesizer")
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
#grid(
  columns: (1.2fr, 1fr),
  gutter: 10pt,
  align: (center, center),
  [
    #text(weight: "bold")[SỞ GIÁO DỤC VÀ ĐÀO TẠO]\
    #text(weight: "bold")[TRƯỜNG THPT CHUYÊN]\
    #text(size: 10pt, style: "italic")[(Đề thi gồm có các trang)]
  ],
  [
    #text(weight: "bold")[KỲ THI KHẢO SÁT CHẤT LƯỢNG]\
    #text(weight: "bold")[NĂM HỌC 2026 - 2027]\
    #text(weight: "bold", size: 12pt)[MÃ ĐỀ THI: #version_code]
  ]
)

#v(6pt)
#line(length: 100%, stroke: 1pt)
#v(4pt)

// Student information block
#block(
  width: 100%,
  stroke: 0.5pt + luma(150),
  inset: 8pt,
  radius: 3pt,
  [
    #grid(
      columns: (1.5fr, 1fr),
      gutter: 12pt,
      [Họ và tên thí sinh: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))],
      [Số báo danh: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))]
    )
    #v(4pt)
    #grid(
      columns: (1.5fr, 1fr),
      gutter: 12pt,
      [Phòng thi: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))],
      [Lớp: #box(width: 1fr, line(length: 100%, stroke: 0.5pt + luma(180)))]
    )
  ]
)

#v(10pt)

// Questions section
#questions_content

#v(16pt)
#align(center)[
  #text(weight: "bold")[-------------------- HẾT --------------------]\
  #text(size: 9pt, style: "italic")[Thí sinh không được sử dụng tài liệu. Cán bộ coi thi không giải thích gì thêm.]
]
