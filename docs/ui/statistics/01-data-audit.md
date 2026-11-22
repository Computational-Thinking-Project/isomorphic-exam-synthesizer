# Stage 1: Statistics Data Audit & Verified Backend Inventory

> **Document Status:** OFFICIAL SPECIFICATION & CODEBASE AUDIT  
> **Milestone:** M1 (Stage 1 Deliverable)  
> **Target System:** Isomorphic Exam Synthesizer  
> **Verified Against:** Repository Git Tree (Backend FastAPI, PostgreSQL Migrations, Frontend Client)  
> **Auditor / Owner:** Worker M1 (Data Audit & UX Architecture Worker)  
> **Key References:** `docs/api/statistics-endpoint.md`, `backend/app/api/routes/users.py`, `backend/app/models/schemas.py`, `backend/migrations/027_my_session_status_counts.sql`, `docs/metrics/w4-kpi-definitions.md`

---

## 1. Executive Summary & Purpose

This audit establishes the **authoritative, verified data inventory** of all backend statistics capabilities available in the Isomorphic Exam Synthesizer codebase. Its purpose is to guarantee that all user interface designs, architectural blueprints, wireframes, and frontend implementations bind **strictly to real, verified backend contracts** without inventing unsupported metrics, mock filters, or fictitious business entities.

### Key Audit Findings
1. **Primary Teacher Statistics Endpoint:** The backend provides exactly one authenticated route for teacher-level usage metrics: `GET /api/users/me/statistics`. It returns an atomic snapshot of 4 summary counters and an 11-bucket lifecycle status breakdown (`SessionStatisticsResponse`).
2. **Zero Filter Support:** The statistics endpoint accepts **no query parameters**. There is **no backend support** for date range filters, semester selectors, course/subject tags, or grade-level filtering. The metrics reflect all retained sessions owned by the authenticated caller across all time.
3. **Product Domain Scope (No Student/Submission Data):** The platform is exclusively an **exam authoring and synthesis tool for teachers**. The database and API contain **zero student, student submission, grading, or test-score models**. Any dashboard UI representing "student performance" or "test pass rates" is invalid and prohibited.
4. **Specification vs. Implementation Gap (W4 KPIs):** The four core quality KPIs specified in `docs/metrics/w4-kpi-definitions.md` (FPAR, RPAI, ECR, GTL) are **formal specification proposals**. There are **no backend API endpoints, RPCs, or controllers** implementing or serving these KPIs. Displaying them on the teacher dashboard as live API-backed metrics would require fabricating data and is strictly avoided.

---

## 2. Primary Endpoint Audit: `GET /api/users/me/statistics`

### 2.1 Route Definition & Access Control

| Attribute | Verified Value | Code Location |
|---|---|---|
| **HTTP Method & Path** | `GET /api/users/me/statistics` | `backend/app/api/routes/users.py:54` |
| **API Tag** | `Users` | `backend/app/main.py:200` |
| **Authentication** | Required. Bearer token via `Authorization: Bearer <supabase_jwt>` | `backend/app/api/dependencies.py` (`get_user_db`) |
| **Rate Limiting** | Governed by `@crud_rate_limit` | `backend/app/api/routes/users.py:55` |
| **Response Headers** | `Cache-Control: private, no-store` | `backend/app/api/routes/users.py:68` |
| **Query Parameters** | **None**. Any query parameters sent in the request are ignored. | `backend/app/api/routes/users.py:54-60` |
| **Data Scope** | Strictly filtered to sessions where `s.user_id = auth.uid()` | `backend/migrations/027_my_session_status_counts.sql:14` |

### 2.2 Underlying Database Query & RPC Contract

The endpoint executes a single PostgreSQL RPC function: `public.get_my_session_status_counts()`.

- **Migration File:** `backend/migrations/027_my_session_status_counts.sql` (lines 3–17)
- **Function Definition:**
  ```sql
  CREATE FUNCTION public.get_my_session_status_counts()
  RETURNS jsonb
  LANGUAGE sql
  STABLE
  SECURITY INVOKER
  SET search_path = pg_catalog
  AS $$
      SELECT coalesce(jsonb_agg(to_jsonb(counts)), '[]'::jsonb)
      FROM (
          SELECT s.status::text AS status, count(*) AS count
          FROM public.exam_sessions AS s
          WHERE s.user_id = (SELECT auth.uid())
          GROUP BY s.status
      ) AS counts;
  $$;
  ```
- **Security & Permissions:**
  - `SECURITY INVOKER`: Runs with the privileges of the executing user context.
  - Permissions: `REVOKE ALL ON FUNCTION public.get_my_session_status_counts() FROM PUBLIC, anon, service_role;` and `GRANT EXECUTE TO authenticated;`.
  - Row Level Security (RLS) & Multi-tenancy: Strictly constrained by `s.user_id = (SELECT auth.uid())`. A caller can never view another user's session status counts.

### 2.3 Response Schema & Python Transformation

- **Pydantic Models:** Defined in `backend/app/models/schemas.py:83-106`.
  ```python
  SessionCount = Annotated[int, Field(strict=True, ge=0)]

  class SessionStatusCounts(BaseModel):
      draft: SessionCount
      blueprinted: SessionCount
      configured: SessionCount
      generating: SessionCount
      partial_generated: SessionCount
      generated: SessionCount
      reviewed: SessionCount
      approved: SessionCount
      exported: SessionCount
      failed: SessionCount
      unknown: SessionCount

  class SessionStatisticsResponse(BaseModel):
      total_sessions: SessionCount
      in_progress_sessions: SessionCount
      approved_not_exported_sessions: SessionCount
      exported_sessions: SessionCount
      by_status: SessionStatusCounts
  ```

- **Backend Aggregation Logic (`backend/app/api/routes/users.py:22-51`):**
  1. Status dictionary initialization: `dict.fromkeys(SessionStatusCounts.model_fields, 0)` initializes all 11 buckets to `0`.
  2. Status validation & mapping: Iterates through RPC result rows `{"status": str, "count": int}`.
     - If `status` is unrecognized or `null`, the count is added to `unknown`.
     - Valid status strings increment their corresponding bucket.
  3. Aggregate derivation:
     - `total_sessions = sum(counts.values())`: Total sum of all 11 buckets. Each retained session (including clones) contributes exactly once.
     - `in_progress_sessions = sum(counts[key] for key in IN_PROGRESS_STATUSES)`: Sum of buckets `draft`, `blueprinted`, `configured`, `generating`, `partial_generated`, `generated`, `reviewed`.
     - `approved_not_exported_sessions = counts["approved"]`: Exactly the count of sessions in status `approved` awaiting export package creation.
     - `exported_sessions = counts["exported"]`: Exactly the count of sessions that have generated a completed export package.

### 2.4 Detailed Field Inventory for `SessionStatisticsResponse`

| Field Path | Data Type | Unit | Nullable | Source / Derivation | Business Meaning |
|---|---|---|---|---|---|
| `total_sessions` | `int >= 0` | Sessions | No | Sum of all 11 status buckets | Total exam sessions retained in the teacher's library across all time. |
| `in_progress_sessions` | `int >= 0` | Sessions | No | Sum of 7 active pipeline status buckets | Sessions currently in active authoring, generation, or review (Stage 1 through Stage 3). |
| `approved_not_exported_sessions` | `int >= 0` | Sessions | No | Direct count: `by_status.approved` | Sessions that passed quality review and final approval, but have not yet been packaged into export bundles. |
| `exported_sessions` | `int >= 0` | Sessions | No | Direct count: `by_status.exported` | Sessions that have completed packaging into downloadable LaTeX/PDF/Word zip archives. |
| `by_status.draft` | `int >= 0` | Sessions | No | `exam_sessions.status = 'draft'` | Sessions created in Stage 1 with raw input (text/file) being edited or ingested. |
| `by_status.blueprinted` | `int >= 0` | Sessions | No | `exam_sessions.status = 'blueprinted'` | Sessions where source questions and parameter blueprints are locked and confirmed. |
| `by_status.configured` | `int >= 0` | Sessions | No | `exam_sessions.status = 'configured'` | Sessions where Stage 2 generation configuration (versions, variation modes) is saved. |
| `by_status.generating` | `int >= 0` | Sessions | No | `exam_sessions.status = 'generating'` | Sessions with an active asynchronous background AI generation job running. |
| `by_status.partial_generated` | `int >= 0` | Sessions | No | `exam_sessions.status = 'partial_generated'` | Sessions where generation partially completed or was interrupted before completion. |
| `by_status.generated` | `int >= 0` | Sessions | No | `exam_sessions.status = 'generated'` | Sessions where all $N \times M$ candidate questions are generated and awaiting review. |
| `by_status.reviewed` | `int >= 0` | Sessions | No | `exam_sessions.status = 'reviewed'` | Sessions where all questions are approved by the teacher and ready for final shuffle. |
| `by_status.approved` | `int >= 0` | Sessions | No | `exam_sessions.status = 'approved'` | Sessions with finalized question shuffle, locked answer matrix, awaiting export. |
| `by_status.exported` | `int >= 0` | Sessions | No | `exam_sessions.status = 'exported'` | Sessions with finalized export packages generated. |
| `by_status.failed` | `int >= 0` | Sessions | No | `exam_sessions.status = 'failed'` | Sessions where AI generation failed unrecoverably (e.g. rate limit exhaustion, model error). |
| `by_status.unknown` | `int >= 0` | Sessions | No | Rows with `status IS NULL` or unrecognized status | Defensive bucket for legacy or malformed session records. |

### 2.5 Error Scenarios & Behavior

- **HTTP 401 Unauthorized:** Missing, expired, or malformed Supabase JWT Bearer token.
- **HTTP 503 Service Unavailable:** Database query timeout, Postgres connection failure, or invalid payload schema:
  ```json
  {
    "detail": "Session statistics temporarily unavailable"
  }
  ```
- **Empty Account (Zero Sessions):** If a user has created 0 sessions, the RPC returns `[]`, which the backend parses cleanly into all zeros:
  ```json
  {
    "total_sessions": 0,
    "in_progress_sessions": 0,
    "approved_not_exported_sessions": 0,
    "exported_sessions": 0,
    "by_status": {
      "draft": 0, "blueprinted": 0, "configured": 0, "generating": 0,
      "partial_generated": 0, "generated": 0, "reviewed": 0,
      "approved": 0, "exported": 0, "failed": 0, "unknown": 0
    }
  }
  ```

---

## 3. Secondary Metrics & Telemetry Endpoints Audit

In addition to the primary teacher statistics endpoint, the codebase contains two specialized telemetry endpoints. These serve distinct operational or workflow functions and are documented here to define their boundaries.

### 3.1 Session Review Progress: `GET /api/sessions/{session_id}/review/progress`

- **Location:** `backend/app/api/routes/review.py:138-155`
- **Purpose:** Monitors review completion progress within a single Stage 3 exam session.
- **Permissions:** Restricted to the authenticated owner of `{session_id}` (`assert_ownership("exam_sessions", session_id, current_user.id)`).
- **Parameters:** Path parameter `session_id` (UUID). No query parameters.
- **Underlying SQL RPC:** `public.review_get_progress(p_session_id UUID)` in `backend/migrations/006_stage3_review_and_shuffle.sql:435`.
- **Response Schema (`ReviewProgressResponse` in `backend/app/models/schemas.py:410-486`):**
  - `session_id` (UUID string)
  - `expected_slots` / `required_count` (int >= 0): Target matrix size ($N \times M$ questions).
  - `current_slots` / `current_count` (int >= 0): Number of active candidate questions (`is_current = TRUE`).
  - `approved_slots` / `approved_count` (int >= 0): Number of active candidate questions with `status = 'approved'`.
  - `regenerating_slots` / `regenerating_count` (int >= 0): Slots currently undergoing AI regeneration.
  - `missing_slots` (int >= 0): Missing candidate slots ($\max(0, \text{expected} - \text{current})$).
  - `duplicate_slots` (int >= 0): Excess candidate slots ($\max(0, \text{current} - \text{expected})$).
  - `ready` / `can_finalize` (bool): `True` when $100\%$ slots approved, 0 regenerating, 0 duplicates, and session status is `generated` or `reviewed`.
  - `unapproved_question_ids` (List[str]): UUIDs of unapproved question items.
  - `is_complete` (bool): `True` when `expected > 0 && current == expected && approved == expected`.
- **UI Boundary:** This endpoint provides **session-scoped granular review metrics** within Stage 3 (`Stage3ReviewPage.jsx`). It is not an aggregated account-level statistics endpoint.

### 3.2 Runtime Operational Metrics: `GET /api/health/metrics`

- **Location:** `backend/app/api/routes/health.py:25-42`
- **Purpose:** Diagnostic health check and worker telemetry for system administrators and DevOps.
- **Permissions:** Admin-only (`get_current_admin_user`).
  - In `ENVIRONMENT == 'development'`: Open to any authenticated user.
  - In production/staging: Requires user email to be in `ADMIN_EMAILS` allowlist; otherwise returns HTTP 403 Forbidden.
- **Response Schema (`RuntimeMetricsResponse` in `backend/app/models/runtime_metrics.py:12-38`):**
  - `status`: `"operational"`
  - `gemini_model`: str (e.g., `"gemini-2.5-pro"`)
  - `uptime_seconds`: float >= 0 (Server uptime since process start)
  - `active_sse_connections`: int >= 0 (Current open Server-Sent Events streams)
  - `gemini_call_count`: int >= 0 (Total outbound LLM calls started)
  - `gemini_error_rate`: float in `[0.0, 1.0]` (Proportion of failed completed LLM calls)
  - `background_jobs_running`: int >= 0 (Active background generation tasks on this worker)
  - `process_memory_mb`: float >= 0 (Process RSS memory in MiB)
- **UI Boundary:** Excluded from the teacher-facing Statistics Dashboard. In a multi-worker deployment, these values reflect only the specific worker handling the request.

---

## 4. Telemetry Gap Analysis: The Four Core KPIs (`docs/metrics/w4-kpi-definitions.md`)

`docs/metrics/w4-kpi-definitions.md` outlines four target evaluation KPIs for the project (W4-MVP-14):

```
+---------------------------------------------------------------------------------------------+
|                                    W4-MVP-14 SPECIFICATION                                  |
+------------------------------+-------------------------------+------------------------------+
| 1. FPAR (First-Pass Rate)    | 2. RPAI (Regen / Accepted)    | 3. ECR (Export Completion)   |
| M_first_pass / M_accepted    | K_regen / M_accepted          | S_exported / (S_created - S) |
+------------------------------+-------------------------------+------------------------------+
| 4. GTL (Turnaround Latency): p50 / p95 wall-clock elapsed time (T_completed - T_started)    |
+---------------------------------------------------------------------------------------------+
```

### Verification Against Codebase Reality:
1. **No REST Route Implements These KPIs:** Comprehensive inspection of `backend/app/api/routes/` confirms that no API endpoint computes, aggregates, or returns FPAR, RPAI, ECR, or GTL.
2. **Database Event Lineage Exists, but Queries Do Not:** While the underlying raw tables (`generation_jobs`, `version_questions`, `review_logs`, `exam_sessions`) exist in Postgres:
   - There are no stored procedures, views, or RPCs calculating FPAR or RPAI across sessions.
   - There is no endpoint aggregating p50/p95 turnaround latency (GTL).
3. **Dashboard Implication:** The frontend Statistics Dashboard **must not fabricate or fake these metrics**. The dashboard UI must strictly visualize the verified session counts provided by `GET /api/users/me/statistics`.

---

## 5. Architectural Constraints & Unsupported Capabilities (Strict Boundaries)

To ensure zero fabrication and preserve architectural integrity, the following negative constraints are binding on all dashboard designs and implementations:

```
+----------------------------------------------------------------------------------------------------+
|                                 STRICT BOUNDARIES & UNSUPPORTED CAPABILITIES                        |
+------------------------------------+---------------------------------------------------------------+
| Feature / Concept                  | Status & Justification                                        |
+------------------------------------+---------------------------------------------------------------+
| Date Range Filtering (From/To)     | UNSUPPORTED: Endpoint takes no query params. All-time count.  |
| Course / Subject / Grade Filters   | UNSUPPORTED: Endpoint groups solely by session status.        |
| Time-Series Historical Charts      | UNSUPPORTED: No temporal grouping (daily/weekly/monthly).     |
| Student Profiles & Submissions     | ABSENT: Platform has no students or student submissions.      |
| Exam Scores & Pass Rates           | ABSENT: System synthesizes exams for teachers; does not grade. |
| AI Token Count / Cost Estimation   | EXCLUDED: Excluded from endpoint by design (see doc below).    |
| Teacher Time Saved Estimator       | PROHIBITED: Banned by w4-kpi-definitions without baseline.   |
+------------------------------------+---------------------------------------------------------------+
```

### 5.1 No Query Parameters or Temporal Filters
- `GET /api/users/me/statistics` does not take `start_date`, `end_date`, `period`, or `interval`.
- Providing a date-picker or "Last 30 Days" dropdown in the UI would be deceptive because the backend cannot filter by date.
- The UI must honestly present the data as **cumulative account-level lifetime statistics**.

### 5.2 No Student or Grading Concept
- The Isomorphic Exam Synthesizer is an authoring tool enabling teachers to generate mathematically valid exam variants from a source exam.
- The database schema contains `exam_sessions`, `source_questions`, `question_blueprints`, `exam_versions`, and `version_questions`.
- It contains **no student accounts, student rosters, test-taking portals, student answer submissions, or score distributions**.
- Visualizations depicting "Average Student Score", "Class Performance", or "Score Distribution" are fundamentally incorrect for this product.

### 5.3 Exclusion of AI Token Usage and Cost
- As documented in `docs/api/statistics-endpoint.md:18`:
  > *"Gemini usage is excluded because Stage 2 counts reservations before dispatch and Stage 3 uses a separate budget. The stored session retry counter lacks a verified increment contract."*
- Consequently, token consumption, quota depletion, and API billing are not part of `SessionStatisticsResponse`.

---

## 6. Frontend Integration & Mocking Verification

### 6.1 Frontend Client Service
The frontend service is implemented in `frontend/src/services/statistics.js`:
```javascript
import { api } from './api.js';

export async function getMyStatistics({ signal } = {}) {
  const { data } = await api.get('/users/me/statistics', { signal });
  return data;
}
```
- Uses the configured Axios instance (`frontend/src/services/api.js`).
- Automatically injects the Supabase JWT Bearer token via request interceptors.
- Supports native `AbortController` signal to cleanly cancel in-flight requests during account switches or unmounting.

### 6.2 Dev Mock Middleware Fixtures
Defined in `frontend/dev-mocks/statistics.js` for isolated offline development and testing:
- **`normalStatisticsFixture` (23 total sessions):**
  - `total_sessions`: 23
  - `in_progress_sessions`: 17 (`draft: 4`, `blueprinted: 3`, `configured: 2`, `generating: 1`, `partial_generated: 1`, `generated: 4`, `reviewed: 2`)
  - `approved_not_exported_sessions`: 3 (`approved: 3`)
  - `exported_sessions`: 2 (`exported: 2`)
  - `failed`: 1, `unknown`: 0
- **`emptyStatisticsFixture` (0 sessions):**
  - All 4 counters and 11 status buckets return `0`.

### 6.3 Automated Test Verification
Direct execution confirms that all statistics data parsing, schema handling, and mock fixtures pass 100%:
- `frontend/src/features/statistics/StatisticsPage.test.js`: 4/4 passing tests.
- `frontend/dev-mocks/statistics.test.js`: 5/5 passing tests.
- `backend/tests/observability/test_metrics_models.py`: 102/102 passing tests.

---

## 7. Audit Conclusion & Design Boundaries

The statistics dashboard must be designed and built around the **precise, verified schema** of `GET /api/users/me/statistics`:
1. **Core Summary Deck:** Focus on the 4 primary volume indicators (`total_sessions`, `in_progress_sessions`, `approved_not_exported_sessions`, `exported_sessions`).
2. **Operational Alerting:** Highlight incidents via an alert banner when `failed > 0` or `unknown > 0`.
3. **Pipeline Funnel:** Structure the authoring flow into a 4-stage pipeline matching the product lifecycle:
   - Stage 01: Ingestion & Blueprint (`draft` + `blueprinted`)
   - Stage 02: AI Variant Generation (`configured` + `generating` + `partial_generated` + `generated`)
   - Stage 03: Review & Approval (`reviewed` + `approved`)
   - Stage 04: Packaging & Export (`exported`)
4. **Status Breakdown:** Present the complete, transparent 11-status distribution bar chart and composition breakdown.
5. **Zero Fabrication:** Absolutely no unbacked mock charts, fake time-series, or fictitious student metrics.
