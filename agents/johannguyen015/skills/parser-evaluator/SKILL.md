---
name: parser-evaluator
description: >-
  Use this skill when developing, testing, or debugging the ingestion parsers (DOCX, LaTeX, Markdown)
  for TASK-202. It covers parsing question structures, detecting separate answer keys, catching OMML equations,
  Unicode NFC normalization, and formatting in-memory validation errors for HTTP 422.
---

# Ingestion Parser Evaluator & Runbook (TASK-202 / TASK-203b)

This skill provides step-by-step procedures, specifications, and edge-case handling for developing and verifying the 3 ingestion parsers:
1. `docx_parser.py` (python-docx)
2. `latex_parser.py` (regex / environment extraction)
3. `markdown_parser.py` (markdown & LaTeX formulas)

---

## 1. Specification Checklist for Parsers

Each parser function must process raw input in-memory and return a structured result with question items and detected validation errors:

### A. Question Structure
- **Format:** Pattern like "Câu 1:", "Câu 2:", `\item`, or `1.`
- **Options:** Exactly 4 options `A`, `B`, `C`, `D`.
- **Question Count:** Valid exam question count must be between **1 and 20** (`1 <= len(questions) <= 20`).

### B. Separate Answer Key Parsing (Bảng đáp án riêng)
- Scan for answer tables or trailing keys at the end of the document (e.g., `1.A 2.B 3.C...` or `1-A, 2-B, 3-C...`).
- Automatically match keys to corresponding question numbers and set `correct_key`.
- If an answer cannot be resolved:
  - Mark `has_missing_answer = True` on the question item.
  - Record error: `{"question_no": X, "error_type": "MISSING_ANSWER"}`.

### C. OMML / Equation Detection (Word Equation)
- For `.docx`, inspect underlying XML tags for `w:oMath` or `w:oMathPara`.
- If OMML formulas cannot be reliably extracted to clean text/LaTeX:
  - Mark `has_unparsed_omml = True`.
  - Record error: `{"question_no": X, "error_type": "UNPARSED_OMML"}`.

### D. Unicode NFC Normalization & Sanitation
- Normalize all extracted text, questions, and options:
  ```python
  import unicodedata
  clean_text = unicodedata.normalize("NFC", raw_text.strip())
  ```
- Sanitize control characters while preserving valid math LaTeX symbols (`$`, `\`, `^`, `_`, `{`, `}`).

---

## 2. In-Memory Pre-validation Rules (ADR-002)

1. **Zero Database Mutation on Validation Failure:**
   - If any errors exist (e.g. `MISSING_ANSWER`, `UNPARSED_OMML`, or question count `< 1` or `> 20`):
     - **Do NOT write or update any database rows.**
     - Immediately raise an HTTPException with status code **422 Unprocessable Entity**:
       ```json
       {
         "detail": "Exam content incomplete or unprocessable",
         "errors": [
           {"question_no": 3, "error_type": "MISSING_ANSWER"},
           {"question_no": 7, "error_type": "UNPARSED_OMML"}
         ]
       }
       ```

2. **100% Valid Contract:**
   - Only when `len(errors) == 0` and `1 <= len(questions) <= 20` proceed to database transaction.

---

## 3. Unit Test Verification Workflow

Run parser tests from the `backend/` directory:

```powershell
# Chạy toàn bộ test parser
pytest tests/test_parsers.py -v

# Chạy riêng từng loại parser
pytest tests/test_parsers.py -k "test_docx_parser" -v
pytest tests/test_parsers.py -k "test_latex_parser" -v
pytest tests/test_parsers.py -k "test_markdown_parser" -v
```

### Key Test Fixtures to Cover:
1. **Standard exam:** 10 questions with inline options and trailing answer key.
2. **Missing answer:** Question 4 has no answer key -> Expect HTTP 422 with `MISSING_ANSWER`.
3. **Unparsed OMML:** DOCX file with embedded equation image/OMML -> Expect HTTP 422 with `UNPARSED_OMML`.
4. **Boundary test:** 0 questions or 21 questions -> Expect HTTP 422.
