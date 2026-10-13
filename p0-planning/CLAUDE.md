# P0 Planning Core — Foundation Rules

This file applies to `p0-planning/` only. **Read the repository-root `CLAUDE.md` first**;
this file adds the rules that are specific to this package.

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
- A confirmed parent is required before creating a child plan; concrete gates
  belong to later Yearly, Monthly, and Weekly slices.

## PR0 boundary

- Constraint is a representation type only.
- Do not implement Yearly, Monthly, Weekly, safety, activity, retrieval, RAG,
  LLM calls, provider adapters, physical persistence, HTTP, UI, or production
  composition in this foundation.
- JSON artifacts use LF as their canonical byte representation.
