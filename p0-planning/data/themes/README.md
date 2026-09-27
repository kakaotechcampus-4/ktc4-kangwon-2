# Yearly Theme Reference

`theme_reference_v0.json` is the versioned input to the deterministic Yearly
Theme rules. It is not a list of monthly themes mandated by the national
curriculum.

## Current artifact

- Catalog: `ssuksak.yearly-theme-reference`
- Version: `theme-reference-v0.1.2`
- Review state: `HUMAN_APPROVED`
- SHA-256:
  `dae9f62db452c56b3b529aaa8e620411e9c11a2072163d6f9cc2a9d2ebc4d902`

The JSON bytes were carried forward unchanged from the approved historical
artifact. Its `applicable_months` values are observations from institution
samples. `curriculum_links` express domain-level educational alignment only;
they are not evidence that a curriculum mandates a theme for a month.

## Runtime contract

- A caller resolves an exact `catalog_id` and `catalog_version`; there is no
  "latest" fallback.
- Only catalog metadata marked `HUMAN_APPROVED` passes the activation rule.
- The JSON adapter validates required fields and strict primitive types before
  constructing the dependency-free domain model.
- Approval cannot be overridden through the repository constructor.
- Changing semantic content requires a new catalog version. Do not silently
  rewrite this approved artifact or its hash.

PR1 provides only the Reference, validation, and deterministic selection rules.
Yearly Generate/Edit/Regenerate/Confirm orchestration belongs to PR2.
