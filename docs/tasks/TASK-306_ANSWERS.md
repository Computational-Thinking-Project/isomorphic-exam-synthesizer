# Technical Feedback & Contract Answers — TASK-306

**Task:** TASK-306 — Typst Subprocess PDF Compiler Engine  
**PR:** [#25](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/25)  
**Responded by:** Nguyễn Bá Duy (`@johannguyen015`)  
**Status:** Resolved  

---

### 1. Docker Runtime Environment for Typst CLI
- **Question:** Does the Docker dev/staging environment have the Typst CLI binary pre-installed, or do we need to add Typst to `backend/Dockerfile`?
- **Answer:**
  - `backend/Dockerfile` (lines 6–14) has **Typst binary v0.11.1** already pre-installed at `/usr/local/bin/typst`.
  - The subprocess runner must invoke `["typst", "compile", ...]` safely with `shell=False`.
  - No modifications to `Dockerfile` are necessary.

### 2. PDF Naming Convention
- **Question:** What is the agreed PDF file naming format for generated artifacts?
- **Answer:**
  - Standardized according to `docs/tasks/W3_ASSIGNMENT.md#L41`:
    - `exam_{code}.pdf` (exam question paper per version code)
    - `answers_matrix.pdf` (answer keys matrix across all version codes)
    - `solutions_{code}.pdf` (detailed step-by-step explanations per version code)
