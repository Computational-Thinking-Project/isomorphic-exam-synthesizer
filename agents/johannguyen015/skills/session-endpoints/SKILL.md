---
name: session-endpoints
description: >-
  Use this skill when implementing, extending, or reviewing the FastAPI endpoints for exam sessions
  (TASK-202 and TASK-205). It enforces assert_ownership, SEC-04 file upload security, atomic database
  transactions, and proper HTTP 409 / 422 status handling.
---

# FastAPI Session Endpoints Standard & Architecture (TASK-202 / TASK-205)

This skill provides guidelines and patterns for implementing the session ingestion and confirmation endpoints in `backend/app/api/routes/sessions.py`.

---

## 1. Endpoints Specification

### A. File Ingestion Endpoint
- **Route:** `POST /api/sessions/{session_id}/ingest-file`
- **Content-Type:** `multipart/form-data`
- **Flow:**
  1. Authenticate user and verify ownership:
     ```python
     await assert_ownership("exam_sessions", session_id, current_user.id)
     ```
  2. Perform **SEC-04** security validation on the uploaded file:
     - Sanitize filename: `clean_name = re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename)`
     - File size check: $\le 10\text{MB}$ raw upload.
     - For `.docx`: Check magic bytes `PK\x03\x04`, inspect zip entries for `[Content_Types].xml` and `word/document.xml`, verify uncompressed size $\le 50\text{MB}$ (anti-Zip Bomb).
     - Save file to Supabase Storage prefix: `{session_id}/{uuid}_{clean_name}`.
  3. Run In-Memory Parser (refer to `parser-evaluator` skill).
  4. If errors detected $\rightarrow$ return **HTTP 422**.
  5. If valid $\rightarrow$ execute **Atomic Database Transaction** (Section 2) and trigger initial Blueprint pipeline.

---

### B. Direct Text Ingestion Endpoint
- **Route:** `POST /api/sessions/{session_id}/ingest-text`
- **Content-Type:** `application/json`
- **Payload:** `{"raw_text": "..."}` ($\le 100,000$ characters).
- **Flow:**
  1. `await assert_ownership("exam_sessions", session_id, current_user.id)`
  2. Parse with `markdown_parser.py` or `latex_parser.py` in-memory.
  3. Validate question count and format.
  4. Atomic replace into database on success.

---

### C. Source Confirmation & Auto-Blueprint Activation (TASK-205)
- **Route:** `POST /api/sessions/{session_id}/confirm-source`
- **Content-Type:** `application/json`
- **Payload:**
  ```json
  {
    "acknowledged_security_warnings": false
  }
  ```
- **Guards & Status Codes:**
  1. **Ownership:** Verify session belongs to `current_user.id`.
  2. **Precondition (State Machine):** Check session status. If status $\ne$ `'draft'` (e.g., already `'blueprinted'` or `'generating'`), raise:
     ```python
     raise HTTPException(status_code=409, detail="Session is not in draft state")
     ```
  3. **Strict Validation:** Confirm all `source_questions` are valid (`has_missing_answer == False`, `has_unparsed_omml == False`) and blueprints exist. If incomplete, raise `HTTP 422`.
  4. **Security Guard (SEC-02):** If any question has `has_security_warning == True`:
     - If `acknowledged_security_warnings` is `False` or missing $\rightarrow$ raise `HTTP 422` with detail requiring user acknowledgment.
  5. **State Transition:** Update session status to `'blueprinted'`. Return HTTP 200.

---

## 2. Atomic Ingestion & Idempotent Replace Pattern

When replacing questions for a session, use a single database transaction:

```python
async def replace_source_questions_atomically(
    session_id: str, 
    questions: list[SourceQuestion]
) -> None:
    """
    Idempotent and atomic replacement of source questions and question blueprints.
    Guarantees no orphaned or duplicate questions if any step fails.
    """
    async with db.transaction():
        # 1. Clear old data for this session
        await db.table("question_blueprints").delete().eq("session_id", session_id).execute()
        await db.table("source_questions").delete().eq("session_id", session_id).execute()
        
        # 2. Insert new validated questions
        await db.table("source_questions").insert([q.model_dump() for q in questions]).execute()
```

---

## 3. Background Blueprint Extraction Trigger

Upon successful ingestion, kick off the background extraction without blocking the HTTP response:

```python
import asyncio

async def trigger_blueprint_pipeline(session_id: str, questions: list[SourceQuestion]):
    semaphore = asyncio.Semaphore(3)  # Rate-limit concurrent Gemini API calls
    
    async def extract_one(question):
        async with semaphore:
            return await ai_service.extract_blueprint(question)
            
    # Run concurrently in background task
    asyncio.create_task(
        asyncio.gather(*(extract_one(q) for q in questions))
    )
```
