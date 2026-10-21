# Mentor pilot audit implementation plan

**Goal:** Verify the implemented teacher flows on the latest develop revision, fix reproducible defects, and provide a click-by-click pilot guide.

**Architecture:** Keep existing UI and API contracts. Run the real Next/FastAPI/Postgres stack with a separate local test database and mock generation. Preserve the original checkout and running containers. Verify production availability separately from local fixes.

**Tech stack:** Next.js, React, TypeScript, FastAPI, PostgreSQL, Playwright.

**Spec:** `docs/PRD.md` §4–6, `docs/screen-spec.md`, `docs/api-spec.md`, and applicable ADRs.

## Constraints and completion conditions

- Only pseudonymous test children; no real LLM calls from local execution.
- No production data reset, merging, or deployment as part of this audit.
- A passing request alone is insufficient: saved content must remain visible after refresh.
- Observe the actual screen labels for the mentor guide.
- Check facts, teacher confirmation, class isolation, export behavior, and failure recovery.

## Tasks

- [x] Prepare a separate branch, local database, mock backend, and current frontend.
- [x] Run existing lint/type/unit checks and real-stack browser regressions; record failures before changing code.
- [x] Walk through signup/onboarding, home observations, observation journal, routines/daily journal, library, annual/monthly plans, exports, evaluation, and settings.
- [x] For each reproducible defect, add a focused regression and repair the existing implementation at its cause.
- [x] Run affected checks, the complete frontend required checks, and applicable backend tests.
- [x] Save the mentor click guide, results, remaining limitations, and deployment status in `docs/`.

## Screenshot follow-up (2026-10-21)

- [x] Trace blank annual subthemes/safety to the existing input contract; make the current generation limit and missing subthemes visible rather than invent content in the exporter.
- [x] Connect the existing monthly HWPX endpoint to a confirmed-plan download button; export only CONTENT sections.
- [x] Compact monthly evidence, keep week headers visible, and distinguish fact/interpretation/support in the journal editor.
- [x] Validate saved annual/monthly/journal content inside both HWPX XML and its preview through browser downloads; rerun required checks (frontend 525, browser 20 plus final focused 6, affected backend 75, lint/format/build).
