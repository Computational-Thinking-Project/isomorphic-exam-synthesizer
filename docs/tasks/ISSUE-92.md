# ISSUE-92 — Vietnamese PDF glyph fix (partial scope)

- Owner/author: Hùng (`benalexx007`); workflow v0.1 proposed + INPUT-20261109.
- Input: [Issue92](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/92), source `dev@e7e0088`.
- This change addresses only the incorrectly rendered Vietnamese solution heading.
  The PDF/Markdown/TeX packaging choice remains outside this patch and undecided.

## Reproduction and decision

The existing backend image uses Typst0.11.1 and has none of the three fonts
requested by the templates (Liberation Serif, Times New Roman, DejaVu Serif).
The actual minimal PDF embeds `LinLibertine`, `LinLibertineI`, `LinLibertineBI`.
With the last face, `ờ ớ ợ ở ỡ` lose the base letter, leaving their accents;
the normal and italic rows are legible. The production solution heading reproduces
the defect. This is independent of Markdown/math conversion: the label is fixed
Unicode text in the renderer.

Installing Debian Bookworm `fonts-liberation2` (observed version2.1.5-1) and setting
`TYPST_FONT_PATHS=/usr/share/fonts/truetype/liberation2` makes
the same unmodified renderer embed Liberation Serif's actual regular, italic,
bold and bold-italic faces. The comparison PDF renders the complete characters.
The slim image lacks fontconfig: installing the package alone still falls back.
The explicit search path was checked with the pinned Typst CLI and actual PDFs.
The patch adds the missing font dependency and discovery configuration;
no Typst upgrade, normalization workaround, converter or template change is needed.
The exact internal cause of the bundled fallback's bad outline/subsetting is not
claimed here. Rebuild the backend image to obtain the fix for newly built bundles.
Existing `ready` exports are reused by `(PACKAGER_VERSION, snapshot revision)`;
pressing Export again on an already-exported session returns its old ZIP even
after deployment. This patch does not bump packaging identity, invalidate ledger
rows or overwrite historical objects. Verify with a newly approved, not-yet-exported
session on the rebuilt runtime. Historical artifact regeneration needs a separate
controlled rollout decision; do not delete ledger/Storage objects to force a rebuild.
Native Typst users must install Liberation Serif as well; Docker is the verified
reference environment. If font discovery is unavailable, expose its installed
directory through `TYPST_FONT_PATHS` (as the Dockerfile does). Installing the family applies the already-requested font
to exam/solution/matrix documents and may change line wrapping versus fallback.

## Verification plan and evidence

- Synthetic fixture: `backend/tests/fixtures/vietnamese_solution_heading.typ`,
  normal/italic/bold/bold-italic, NFC and decomposed NFD accents.
- Two real-compiler regressions inspect the font name objects in the resulting
  PDF: the fixture must embed all four requested faces, and the actual solution
  renderer must embed LiberationSerif-BoldItalic. These guard against returning
  to a silent fallback; font selection alone does not prove all painted glyphs.
- Render both the fixture and the production solution PDF with Poppler; inspect
  Vietnamese glyphs, math, labels and clipping. Raw synthetic before/after PDFs,
  PNGs and embedded-font observations stay local ignored under `.artifacts/issue92/`.
- Run exporter regressions and lint/typecheck on the proposed image. Task12 must
  rerun its real Golden bundle regression after integration. A local renderer fix
  is not shared Storage/JWT/G0/G1/G2 acceptance.
- Independent GPT-6.2 Sol High review follows implementation/checks; its final
  findings and rechecks are recorded below.

## Author checks — 20/11/2026

- Built the actual proposed `backend/Dockerfile` as `issue92-backend:20261120`;
  Typst remains0.11.1 and sees all four Liberation Serif faces. The old image
  fails both new tests (fallback embedded); the proposed image passes both.
- `ruff check app tests/exporter/test_vietnamese_pdf_fonts.py`: PASS;
  `mypy app --ignore-missing-imports`: **128 files PASS**;
  `pytest tests/exporter -q`: **326 passed, 1 skipped** (XeLaTeX), 1 warning.
  Run these inside the rebuilt backend image, working directory `/app`.
- Poppler-rendered fixture and actual solution PDF inspected: complete `ờ/ớ/ợ/ở/ỡ`
  in regular/italic/bold/bold-italic and NFD, correct production heading and math.
  Final local evidence is `.artifacts/issue92/final/`; earlier `before-*` evidence
  outside that folder preserves the baseline defect. No binary evidence committed.
- Integrated TASK12 source mounted read-only in the new image: security/API/
  services/exporter **1325 passed, 3 skipped**, 6 warnings. No XFAIL. Then the
  strengthened exact ZIP/manifest Golden check was rerun: **2 passed**.
  Synthetic Golden full/empty bundles each contain5 PDFs; exam/solutions/matrix
  were rendered for layout inspection. This remains renderer-only synthetic QA.
- No cloud/DB mutations or production deployment; no evidence of repaired
  historical exports. ZIP organization remains unchanged.

## Independent review and recheck — 20/11/2026

- GPT-6.2 Sol High independently verified all four discovered faces and both
  new regressions on the actual proposed image. Compared before/after rasterized
  PDFs, NFC/NFD, production heading, math and Golden exam/solution/matrix.
- Unexpected-behavior probe:20-question synthetic documents retained4 exam and5
  solution pages with/without the font path; all pages visually inspected with
  no observed clipping or missing base letters. This is bounded fixture evidence,
  not a guarantee of identical wrapping for every possible document.
- Reviewer raised the ready-export reuse limitation; the normal Export behavior
  and separate historical-rollout requirement are now explicit above. No product
  identity or ledger invalidation was introduced. TASK12's missing TeX/MD oracle
  was also strengthened on its own branch; independent recheck2/2 PASS.
- Final result: no remaining actionable finding in scope; author and reviewer
  agree. Not GitHub Approve, PostgreSQL rerun or deployed/live acceptance.
