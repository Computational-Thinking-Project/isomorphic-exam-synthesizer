# Week 4 Decision Register Alignment Proposals (Q01, Q06, Q07, Q14)

> **Document Status:** PROPOSAL FOR WEEK 4 DECISION ALIGNMENT (TAM PROPOSAL)  
> **Author:** Pham Khanh Tam (`@AI-WFox`)  
> **Consulted Stakeholders:** Duy (`@johannguyen015`), Hung (`@benalexx007`), Boi Anh (`@htbaax`), Quynh (`@nhatquynh1107`)  

---

## 1. Resolution Summary Table

| Decision ID | Topic | Proposed Consensus / Technical Policy | Impacted Code / Docs |
|---|---|---|---|
| **Q01** | Source solutions optional vs required | **Mandatory for Golden Demo (Fail-Closed); Optional in long-term product.** Source questions in the Golden Demo must provide complete solutions to prevent broken Typst/DOCX export bundles. `description.md` optional solutions remain the target for post-MVP. | `backend/app/api/routes/sessions.py`, `backend/app/services/exporter/` |
| **Q06** | Pre-approval preview projection API | **Implemented in `W4-MVP-05`.** Endpoint `GET /api/sessions/{session_id}/finalize/preview` returns `PreviewSnapshotResponse` with full display projection, synchronized solutions, and cross-version answer matrix. | `backend/app/api/routes/finalize.py`, `docs/api/preview-projection-contract.md` |
| **Q07** | Shuffle preferences editing semantics | **Editable before shuffle; Re-shuffle required if changed post-shuffle; Locked upon approve.** Stage 3 allows updating preferences before finalize shuffle. Once approved, HTTP 423 locks all changes. | `backend/app/services/finalize/service.py`, `backend/migrations/008_finalize_persist_shuffle_rpc.sql` |
| **Q14** | Golden 3-question Markdown oracle & fallback | **3-Question Math Corpus Locked.** Verified with golden fixture `w4_preview_snapshot_fixture.json`. Deterministic 4-attempt fallback uses recorded permits to safeguard quota. | `backend/tests/fixtures/w4_preview_snapshot_fixture.json` |

---

## 2. Detailed Technical Rationales

### Q01: Source Solutions Policy
- **Problem Statement:** `docs/description.md` notes that source solutions are optional, whereas the downstream export compiler (`ApprovedExportSnapshot`) strictly requires non-empty `solution_md: Text` (1..16000 chars) for every approved question to render the Teacher's Answer & Solution Guide.
- **Proposed Technical Policy:**
  - For the Week 4 Golden Demo (15/11), all source questions must provide complete solutions.
  - Confirmation of source without solutions fails closed for the demo run to prevent downstream export failure.
  - Long-term feature: Automated AI solution synthesis will be introduced post-MVP to fulfill the optional solution vision in `description.md`.

### Q06: Post-Shuffle Pre-Approval Preview Projection Contract
- **Problem Statement:** The existing `GET /api/sessions/{session_id}/finalize/matrix` was locked behind `status in ('approved', 'exported')` and omitted question stems, permuted choices, and explanations. Frontend needed an authoritative pre-approval view.
- **Technical Policy Implemented (`W4-MVP-05`):**
  - Dedicated endpoint: `GET /api/sessions/{session_id}/finalize/preview`.
  - Accessible when `status == 'reviewed'` (with `is_finalized == True`), as well as post-approval.
  - Returns `PreviewSnapshotResponse` containing `versions` (with display slot orders 1..M, permuted options A-D, display correct keys, synchronized `solution_md`) and cross-version `matrix`.
  - Data structure supplies all fields needed by Hung's `W4-MVP-07` DB adapter to instantiate `ApprovedExportSnapshot` alongside `exam_sessions.title` and `updated_at`.

### Q07: Shuffle Preferences Semantics
- **Problem Statement:** When can a teacher modify the two shuffle toggles (`shuffle_questions`, `shuffle_options`), and what happens if they are changed after shuffle?
- **Proposed Technical Policy:**
  - **Before Finalize Shuffle:** Teachers can adjust toggles in the Stage 3 UI. The preferences are saved via generation config updates.
  - **During Finalize Shuffle:** `POST /finalize/shuffle` computes the deterministic permutation and commits `is_finalized = True`.
  - **After Finalize Shuffle (Pre-Approve):** If the teacher changes toggles, the UI displays a prompt informing them that a re-shuffle is required. Re-invoking `POST /finalize/shuffle` safely re-computes the projection.
  - **After Final Approve:** Session is permanently locked (HTTP 423 `ERR_SESSION_LOCKED`). No further shuffle or content modifications are permitted.

### Q14: Golden 3-Question Corpus & Fallback Strategy
- **Problem Statement:** Ensuring repeatable, non-flaky execution for the 15/11 live demonstration without burning live Gemini API quotas.
- **Technical Policy:**
  - Pinned 3 high-school math topics:
    1. Calculus: Extrema of cubic polynomial.
    2. Calculus: Definite integral with power rule.
    3. Analytic Geometry: Radius and center of sphere in $Oxyz$.
  - Golden snapshot fixture committed in `backend/tests/fixtures/w4_preview_snapshot_fixture.json` (OFF/OFF baseline).
  - Test suites run against isolated database mocks and deterministic stubs, preserving quotas for live reviewer demonstration.
