# Issue92 — One combined document per version and format

- Author: Hùng (`benalexx007`); workflow v0.1 proposed + INPUT-20261109, docs baseline7b7387f.
- User-directed scope, 20/11/2026: each version gets one PDF, one TeX, one Markdown;
  exam first, then answer matrix, then solutions. PDF/TeX must separate the end of
  the exam and beginning of the answer section onto different pages; MD can flow.
- Branch `codex/issue-92-per-version-documents`, based on glyph PR103@3f58c23,
  itself based on dev@e7e0088. New PR targets dev so required CI runs; until103
  merges its diff includes that dependency. Review layout delta against3f58c23.
- This is a new layout decision beyond issue92's original A/B wording. Record it
  in the PR Conversation for Duy/Đạt/Tâm to check; do not rewrite existing descriptions.

## Plan / contract

1. Compose the existing safe Typst exam and solution renderers with one explicit
   page break and one document preamble; reuse the version's answer table as its
   matrix. Keep standalone methods available. No math-converter changes.
2. Add the same version-only answer matrix before solutions in MD/TeX; retain
   XeLaTeX `clearpage` immediately before the matrix. No cross-version answer table.
3. Bundle exactly3N content files, plus2 READMEs and the private manifest. Keep
   existing exam filenames/folders, ZIP download/API and snapshot authorization.
4. Bump packager identity to `w4-export-v2` because contents and layout change.
   Existing v1 ledger rows/objects remain untouched; an explicit v2 Export creates
   its own artifact for the same approved snapshot. No migration or backfill.
5. Test source ordering, per-version shuffle/key preservation, blank-solution
   provenance, exact manifests, compiler errors, idempotency and SQL lifecycle.
   Render real PDF and XeLaTeX output; check actual page boundaries and glyphs.
6. Independent GPT-6.2 Sol High review includes unexpected behavior; fix/recheck
   findings before commit/push and request human peer review.

## Impact and boundaries

- Combined `exam_<code>.pdf/.tex/.md` contains answers. Share only the exam pages
  with candidates; there is no separate student-only export in this scope.
- ZIP is retained for multiple versions/formats, READMEs and checksums. No change
  to HTTP response fields, private bucket type, object extension, URL TTL or ACL.
- v2 status is idle until built even if session lifecycle already says exported
  from v1. FE must continue using private export status, as implemented. Rollback
  to v1 resolves v1 identity; it must not relabel v1 objects as v2.
- A ready status refresh discards a cached download URL before the next download:
  another device may already have built v2 with the same filename. This avoids
  showing the v2 receipt while serving a still-valid v1 link. Repeated downloads
  without a status refresh still reuse an unexpired grant.
- Combined PDF footers show the running page number without a whole-file total,
  so detached exam pages do not suggest teacher-only pages are missing. Standalone
  legacy renderer defaults are preserved. No answers are placed before the break.
- Current candidate runtime/DB/principals gates from TASK12 still apply. No shared
  DB/Storage changes, live acceptance, activation or merge is authorized here.
- Reviewer requests: Tâm (`AI-WFox`) renderer/layout, Đạt (`Thanhdat3010`) bundler/
  OPS, Duy (`johannguyen015`) contract and ledger identity consequences, Philip
  (`philip-kkk`) download-grant cache invalidation in the shared FE controller.
- TASK12 PR73's positive Golden oracle must be refreshed for v2 on its own branch
  after integrating this candidate; passing its current v1 contract is historical.

## Checks and handoff

- Actual Typst0.11.1 + Liberation Serif + XeLaTeX in disposable QA image:
  exporter **331 passed**, no skips; Ruff PASS, mypy **128 source files PASS**.
  The XeLaTeX/Poppler packages are QA-only and not added to production Docker.
- PostgreSQL15 isolated, full migration chain through026: **368 passed, 1 skipped**
  (XeLaTeX absent in that separate image), **21 subtests**, 2 warnings. Includes
  v1 ready→v2 idle/build/replay and byte-identical old ledger row/blob. Storage is
  a double; this does not certify shared Supabase/Storage.
- Generated12 PDFs from Golden2×3 and maximum4×20 cases with actual Typst and
  XeLaTeX. Extracted all page texts and rasterized all pages: matrix starts exactly
  on the page after the exam's HẾT marker; no answer section before that boundary.
  Golden:2 pages (exam1, matrix2) for both compilers. Maximum:6 pages for both,
  Typst exam ends2/matrix3, XeLaTeX exam ends4/matrix5. Raw local ignored evidence:
  `.artifacts/issue92/packaging/` (PDFs, PNGs and pages.json).
- FE controller targeted regression: **11 passed**. Full pinned Node22 Docker:
  **560 passed**, ESLint PASS and Vite build PASS (existing chunk-size warning).
  A host Node26 run was559 passed/1 failed in untouched
  Stage3Review.test.js:2617 (missing approve button); do not call it a full PASS.
- Independent GPT-6.2 Sol High review/recheck: **no open actionable findings**. F01 stale
  cached v1 download after v2-ready refresh fixed and independently reproduced/
  rechecked; F02 misleading whole-file footer totals fixed and rechecked for
  combined output. Reviewer independently ran331 exporter tests and11 controller
  tests; compiled10 Typst and10 XeLaTeX documents across1–4 versions/1–20 questions,
  checked page boundaries and every matrix key, and ran the new isolated PG v1/v2
  regression **1/1 PASS**. No author/reviewer counts are summed; no GitHub approval.
- This does not claim integrated G0/G1/G2 acceptance or authorize deployment.
