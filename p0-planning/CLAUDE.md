# P0 Planning Core — Foundation Rules

This file applies to `p0-planning/` only. **Read the repository-root `CLAUDE.md` first**;
this file adds the rules that are specific to this package. Inside `p0-planning/`,
the narrower rule here wins over the root file (ADR-031). "Read first" is reading
order; "wins" is scope. They do not conflict.

Provenance (the three axes, the Evidence Source values, and how a teacher edit is
recorded) lives in the root `CLAUDE.md`. It is not repeated here — it applies to the
whole project, and keeping two copies is how the two files drifted apart in 2026-10.

## Architecture

- Keep the dependency direction `adapters -> application -> domain`.
- Domain code must not depend on DB, HTTP, file I/O, an LLM SDK, or another
  external service.
- Application ports define logical capabilities only. They must not pre-empt an
  unresolved physical DB, HTTP, or provider contract.
- Test adapters are replaceable development tools, not production persistence.

## Plan state in this package

- Plans use `DRAFT` and `CONFIRMED`.
- Generated plans start as `DRAFT`.
- A confirmed parent is required before creating a child plan: Yearly
  `CONFIRMED` before Monthly, Monthly `CONFIRMED` before Weekly. Weekly is only
  created through a Monthly plan; there is no Yearly-to-Weekly path (ADR-030 PM-04).
- A `CONFIRMED` plan is read-only. Plans have no un-confirm (ADR-030 PM-03).

## Rule / LLM boundary in this package

Rule sets the allowed range (approved candidates, evidence, constraints, section
structure, statutory rules); the LLM decides the meaning of a value inside that
range; Rule verifies the result (ADR-032). The LLM never chooses a `theme_id`,
reference id, cell, week, age fit, statutory value or pass/fail outside that
range — out-of-range output fails closed. Yearly narrows the range to one
Rule-selected theme per month; the LLM writes its text and may not replace it.

## Yearly v0 contract

- `YearlyPlan` has `school_year`, `classroom_ref` and exactly 12 ordered
  `month_periods`, March to the next February, with no duplicate or missing month.
- Each month has a non-blank `theme`. Every editable item has a stable `item_id`
  and `semantic_key`.
- The theme's `theme_id` resolves in the active, human-approved Theme Reference,
  its `source_version` equals the active catalog version, it applies to that
  month and supports every age of the classroom.
- `goals`, `rationale`, `weekly_focus` and institution sections are optional in v0.
- The plan is owned by one classroom; a mixed-age classroom still owns one plan.
- Selected-month regeneration (`RegenerateYearlyPlanItem`) exists in Core only and
  is not exposed over HTTP (ADR-035).

## Template guardrails (Monthly; Weekly follows the same approval procedure)

- Do not hard-code a fixed row count or a fixed 4- or 5-week month. Weeks come
  from the canonical `WeekPeriod` list.
- A section's time unit is `repeat_by`: `NONE` (one value per document) or `WEEK`
  (one value per active week). `null` is for AXIS sections and inactive content
  sections. Monthly accepts only `NONE` and `WEEK`; Weekly P0 does not use `DAY`
  (ADR-027, ADR-030 WQ-02).
- Keep the internal `semantic_key` separate from the source form's `source_label`.
- Do not fix the physical row of `safety_education` as a domain rule.
- A new Template version starts `PENDING_HUMAN_REVIEW` and is never activated until
  a real reviewer approves it. Approval is not inherited across versions, and a
  READY Profile does not mean its base Template is approved (ADR-027).

## Mixed-age classrooms

- A classroom stores an age range (`age_min`, `age_max`). Core receives the age set
  built from that range, e.g. 3–5 → {3, 4, 5} (ADR-038).
- Name ages as "만 N세" in screens and documents. The values are classroom ages
  (the field's "만 N세반"), not ages computed from a birth date.
- A gap combination (만 3세 + 만 5세 without 만 4세) is not supported in P0; it is
  stored as the range 3–5. Revisit with a set model only if collected references
  show such a classroom.
- Classroom ages (a range) and Activity `supported_ages` (a set of points) are
  different concepts; do not read them with the same rule.

## Golden contract

- Deterministic rules get unit tests.
- LLM paths are tested with a fake LLM fed fixed proposals. A golden fixes what
  the Application does with a given proposal, never the model's sentence.
  Natural-language quality belongs to a manual live quality smoke, not to golden.
- Golden fixtures: `tests/finalization/golden/` (`yearly.json`,
  `monthly_rule.json`, `monthly_llm.json`, `cell_regeneration*.json`).
- Do not update an expected value because a new result appeared. Decide first
  whether the contract changed or this is a regression; a contract change records
  its reason in the PR.
- `tests/finalization/test_freeze.py` pins the SHA of approved artifacts
  (Template, Evidence Store, Activity Catalog, statutory Rule). A changed artifact
  is a different contract and must fail there even if golden passes.

## PR0 boundary

These rules scoped the foundation PR (PR0) of this package. They are kept as the
record of what PR0 left out; later Yearly, Monthly and Weekly slices implement
those features under the sections above.

- Constraint is a representation type only.
- Do not implement Yearly, Monthly, Weekly, safety, activity, retrieval, RAG,
  LLM calls, provider adapters, physical persistence, HTTP, UI, or production
  composition in this foundation.
- JSON artifacts use LF as their canonical byte representation (this one still
  applies to every artifact).
