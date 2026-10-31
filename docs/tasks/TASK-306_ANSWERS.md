# Technical Feedback & Contract Answers — TASK-306

**Task:** TASK-306 — Typst Subprocess PDF Compiler Engine  
**PR:** [#25](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/25)  
**Responded by:** Nguyễn Bá Duy (`@johannguyen015`), Trương Thành Đạt (`@Thanhdat3010`), Phạm Khánh Tâm (`@AI-WFox`)  
**Status:** Resolved  

---

### 1. Docker Runtime Environment for Typst CLI
- **Question:** Does the Docker dev/staging environment have the Typst CLI binary pre-installed, or do we need to add Typst to `backend/Dockerfile`?
- **Answer:**
  - `backend/Dockerfile` (lines 6–14) has **Typst binary v0.11.1** already pre-installed at `/usr/local/bin/typst`.
  - The subprocess runner invokes `["typst", "compile", ...]` safely with `shell=False`.
  - No modifications to `Dockerfile` are necessary.

### 2. PDF Naming Convention
- **Question:** What is the agreed PDF file naming format for generated artifacts?
- **Answer:**
  - Standardized according to `docs/tasks/W3_ASSIGNMENT.md#L41`:
    - `exam_{code}.pdf` (exam question paper per version code)
    - `answers_matrix.pdf` (answer keys matrix across all version codes)
    - `solutions_{code}.pdf` (detailed step-by-step explanations per version code)

### 3. Data Adapter Contract for Persisted Models vs Display Schema
- **Question (Reviewer @Thanhdat3010):** How do `render_exam_document` and `render_solution_document` map between persisted database keys (`question_no`, `correct_key`, `stem`, `canonical_*`) and shuffler output keys (`display_no`, `display_correct_key`, `content`, `options`)?
- **Answer:**
  - `TypstCompiler` now transparently adapts both schemas:
    - Question index: `disp_no = q.get("display_no") or q.get("question_no") or q.get("display_order") or idx`
    - Correct answer key: `corr_key = q.get("display_correct_key") or q.get("correct_key") or q.get("canonical_correct_key") or "A"`
    - Question stem: `stem = convert_markdown_to_typst(q.get("content") or q.get("canonical_content") or q.get("stem") or "")`
    - Option list: `opts = q.get("options") or q.get("canonical_options") or ["", "", "", ""]`
    - Solution text: `sol_md = q.get("solution_md") or q.get("canonical_solution_md") or q.get("solution") or ""`
  - This eliminates false fallback to "A" when passing persisted database dictionaries directly.

### 4. Multi-Version Answers Matrix Callable
- **Question (Reviewer @Thanhdat3010):** Which callable generates `answers_matrix.pdf` across multiple versions for the session manifest in TASK-307?
- **Answer:**
  - Implemented `TypstCompiler.render_answers_matrix_document(versions_matrix, exam_title, subject) -> str`.
  - Accepts a sequence of version objects/dictionaries containing `version_code` and `answer_keys` (mapping from question number to correct letter key, e.g. `{1: "A", 2: "C", ...}`).
  - Generates an A4 Vietnamese table with columns: `Câu`, `Mã {code1}`, `Mã {code2}`, etc.
  - Compiles directly to `answers_matrix.pdf` via `compiler.compile_document(typst_markup, "answers_matrix.pdf")`.

### 5. Review Findings Resolution (Round 1)
- **F01 (Author metadata in Typst 0.11.1):** Changed `author: [Isomorphic Exam Synthesizer]` (content) to `author: "Isomorphic Exam Synthesizer"` (string) across `typst_compiler.py`, `templates/exam.typ`, and `templates/solution.typ`.
- **F02 (LaTeX command boundary in Converter):** Replaced `\b` with `(?![a-zA-Z])\s*` and enforced whitespace token separation so commands adjacent to numbers (e.g. `$x=\pm2$`, `$\sin2x$`) or variables (e.g. `$x\in[0;1]$`) compile cleanly.
- **F03 (Typst code injection prevention):**
  - In prose: Escaped backslash `\` first so pre-existing backslashes cannot unescape subsequent `#` escapes.
  - In math: Neutralized `#` to string literals `"#"` to prevent Typst math mode from executing embedded code (e.g. `$#panic(...)$`).
  - In metadata: Sanitized quotes and code markers in document titles and version codes.
- **F04 (Output filename containment):** Strictly validated `output_filename` before compilation: rejected absolute paths, directory traversal (`..`), path separators (`/`, `\\`), and non-`.pdf` extensions; asserted resolved paths stay within temporary directory.

### 6. Review Findings Resolution (Round 2)
- **F03 (Typst code injection prevention via math mode & method chaining):**
  - **Issue:** Method calls on quoted hash `$\#.replace("", panic("REVIEW_MARKER"))$` resulted in consecutive replacement `""#""`, allowing chained method `.replace("", panic(...))` to trigger `panic`.
  - **Resolution:**
    - In `latex_math_to_typst`, neutralized `\#` and `#` to the official Typst math symbol `" hash "`. No literal `#` character ever reaches the Typst math parser, preventing entry into Typst code evaluation mode.
    - Added regex filtering to strip arbitrary chained method invocations `re.sub(r"\.\w+\s*\(", " ", s)` and execution keywords `re.sub(r"\b(?:panic|eval|assert)\b", " ", s)` within math segments.
  - **Evidence:** Added unit test `test_f03_method_chaining_code_injection_prevention_math` and real compile test `test_real_typst_compile_f03_neutralized_payload`.
- **F05 (Answers matrix string literals syntax):**
  - **Issue:** Single quotes in `#text(weight: 'bold')` inside `render_answers_matrix_document` caused Typst 0.11.1 syntax error (`the character ' is not valid in code`).
  - **Resolution:** Changed all single quotes to double quotes `#text(weight: "bold")` across table headers and row items in `typst_compiler.py`.
  - **Evidence:** Added unit test `test_f05_answers_matrix_uses_double_quotes_for_bold` and real compile test `test_real_typst_compile_answers_matrix_document`.

