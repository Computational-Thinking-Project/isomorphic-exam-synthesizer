# Technical Feedback & Contract Answers — TASK-303

**Task:** TASK-303 — Deterministic Fisher-Yates Shuffler & Solution Sync  
**PR:** [#24](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/24)  
**Responded by:** Nguyễn Bá Duy (`@johannguyen015`)  
**Status:** Resolved  

---

### 1. Structure of `canonical_options`
- **Question:** What is the exact JSONB format of `canonical_options` in the question models: array of strings `["A...", "B..."]` or dictionary map `{"A": "...", ...}`?
- **Answer:**
  - Formatted as an array of 4 strings `["A...", "B...", "C...", "D..."]` according to the Stage 2 schema [`backend/app/models/generation.py#L37`](../../backend/app/models/generation.py#L37).

### 2. Response Schema for `POST /api/sessions/{session_id}/finalize/shuffle`
- **Question:** Does the endpoint return a full permutation list or an object map per question_id?
- **Answer:**
  - Returns metadata conforming to contract [`w3.md#L316`](../../w3.md#L316):
    ```json
    {
      "session_id": "...",
      "status": "reviewed",
      "is_finalized": true,
      "versions": [
        { "version_id": "...", "version_code": "101", "total_questions": 20 }
      ]
    }
    ```
  - Detailed permutation matrices are stored directly into persistent database storage: the `answer_keys` table and `exam_versions.permutations` (JSONB) column.

### 3. Review Findings Resolution (Round 1)
- **F01 (Regex False Positive in `sync_solution_text`):**
  - **Issue:** Conclusion lookahead matched mathematical equations and assignments starting with variable letters (e.g. `Vậy: A = 5`), incorrectly replacing variable $A$ with display option letter $C$ (`Vậy: C = 5`).
  - **Resolution:** Added operator exclusion negative lookahead `(?!\s*(?:[=!<>]|<=|>=|!=|==|\\le|\\ge|\\in|\\notin|[\+\-\*/\\~]))` across both keyword and conclusion regex patterns, ensuring letters followed by comparison or arithmetic operators are strictly excluded from answer choice replacement.
  - **Evidence:** Added unit regression tests in `test_f01_sync_solution_text_excludes_math_equations`.
- **F02 (AnswerKeyRecord Schema Alignment with W3 Contract and Database Baseline):**
  - **Issue:** `AnswerKeyRecord` used legacy column names `(question_no, correct_option)` instead of the W3 specification `(display_no, display_correct_key, canonical_question_no)`.
  - **Resolution:** Updated `AnswerKeyRecord` in `backend/app/services/shuffler/schemas.py` using `validation_alias=AliasChoices(...)`, `serialization_alias=...`, `ConfigDict(populate_by_name=True)`, and backward-compatible properties. The model now seamlessly supports both W3 names and legacy baseline names in construction, attribute access, and serialization.
  - **Evidence:** Added unit regression tests in `test_f02_answer_key_record_schema_and_alias_compatibility`.
- **F03 (Strict Validation for `canonical_correct_key`):**
  - **Issue:** `canonical_correct_key` used unconstrained `str` type and `service.py:220` silently fell back to `'A'` if the key was invalid, masking upstream data errors.
  - **Resolution:** Declared `canonical_correct_key: Literal["A", "B", "C", "D"]` in `CanonicalQuestionInput`, and updated `service.py` to raise `ValueError` on invalid or missing keys instead of silently defaulting to `'A'`.
  - **Evidence:** Added unit regression tests in `test_f03_strict_validation_for_canonical_correct_key`.
