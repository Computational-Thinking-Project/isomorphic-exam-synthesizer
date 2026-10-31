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
