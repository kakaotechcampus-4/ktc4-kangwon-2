# Annual content implementation plan

**Goal:** Generate annual subthemes, accept teacher safety placements, and preserve them through editing, confirmation and HWPX export.
**Architecture:** Preserve Core's theme contract and existing plan endpoints. Generate subthemes in one follow-up batch before commit. Store manual safety state and audit in one additive JSONB column.
**Tech stack:** FastAPI/Pydantic/PostgreSQL, Next/React, pytest, Playwright.
**Spec:** `docs/api-spec.md` §4, §6–9 and `docs/adr/041-annual-subthemes-and-teacher-safety-placement.md`.

## Constraints

No real LLM locally, no invented safety placements, no confirmed-plan changes, no production deployment. Keep existing PUT callers compatible when safety is omitted. Reuse the shared LLM and HWPX paths. Do not change approved artifacts.

## Tasks

- [x] Backend data/API: add `Plan.annual_safety` and Alembic revision after `0211f5ffef6b`. Add optional typed safety input (omitted preserves, null unknown, [] not placed), official category metadata in annual detail, derive state, append teacher audit and expose month edit history. Tests: invalid/duplicate values 422; save/reload/reset; teacher/center isolation; confirmed 409; concurrent month edits preserved.
- [x] Subthemes: implement `generate_subthemes(plan, transport=None) -> dict[str, list[str]]` in the annual feature. Validate exactly the requested months, 2–5 nonblank bounded strings per month, reject additional fields. Mock is deterministic. Add after Core generation before `_detail`/commit; map shared LLM unavailable/budget/failure errors without partial DB state. Tests use fake transports and assert rollback after generator failure.
- [x] Export: map safety category ids to official labels in annual HWPX. Assert actual cell content and preview text include teacher placements/subthemes, omit evidence/technical ids.
- [x] Frontend: extend existing month input and row types, pass annual detail into GenerationFlow. Show subtheme input and monthly safety checkbox group from server metadata; save edits together, reread checks after save, display missing-placement and unverified-hours states. Existing confirmed plans remain read-only. Update MSW to match omission/null/empty semantics.
- [x] Browser regression: create annual with nonempty subthemes, edit subtheme and safety, refresh, confirm, download real HWPX and inspect XML/preview, reject confirmed edit. Run lint/format/build, frontend tests, affected/full backend tests, real-stack browser tests, migrations and CI.
- [x] Update pilot guide/status/PR with actual scope, verification and limits. Push only the feature branch.
