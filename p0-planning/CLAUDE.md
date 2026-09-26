# P0 Planning Core — Foundation Rules

This file applies to `p0-planning/` and is more specific than the repository-root
guidance when defining P0 Planning Core domain types.

## Architecture

- Keep the dependency direction `adapters -> application -> domain`.
- Domain code must not depend on DB, HTTP, file I/O, an LLM SDK, or another
  external service.
- Application ports define logical capabilities only. They must not pre-empt an
  unresolved physical DB, HTTP, or provider contract.
- Test adapters are replaceable development tools, not production persistence.

## Shared plan state

- Plans use `DRAFT` and `CONFIRMED`.
- Generated plans start as `DRAFT`.
- A confirmed parent is required before creating a child plan; concrete gates
  belong to later Yearly, Monthly, and Weekly slices.

## Provenance

Keep three independent axes:

1. Evidence Source: where a value came from.
2. Generation Method: how its current value was produced.
3. Audit History: who or what changed it, and when.

Allowed Evidence Source types are:

```text
CURRICULUM
THEME_REFERENCE
PARENT_PLAN
DAYCARE_PROFILE
CLASSROOM_PROFILE
EVENT
SAFETY_RULE
ACTIVITY_REFERENCE
INSTITUTION_SAMPLE
CALENDAR
TREND
EXTERNAL_CONTEXT
```

`AI` and `TEACHER_EDIT` are not Evidence Source types. LLM-assisted generation
is represented by `RULE_LLM`. A value written by a person from the beginning is
`MANUAL`. A later teacher edit keeps the current Generation Method, `rule_id`
and `rule_version` and adds a `TEACHER_EDITED` Audit Event (value change and
actor); the edit never erases Evidence. Whether the current value is
teacher-edited is read from Audit History, not from the legacy
`GenerationMethod.TEACHER_EDIT` value, which production code no longer writes
(2026-09-26 Human Decision; the enum's removal is undecided).

Parent Lineage is an immutable aggregate snapshot, not a fourth provenance
axis. When a child item uses its parent as evidence, record a separate
`PARENT_PLAN` Evidence Source.

## PR0 boundary

- Constraint is a representation type only.
- Do not implement Yearly, Monthly, Weekly, safety, activity, retrieval, RAG,
  LLM calls, provider adapters, physical persistence, HTTP, UI, or production
  composition in this foundation.
- JSON artifacts use LF as their canonical byte representation.
