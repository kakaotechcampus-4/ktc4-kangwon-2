"""Deterministic selection from a Yearly Theme Reference catalog."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.theme_reference import ThemeCandidate, ThemeCatalog
from ..domain.year_month import YearMonth
from .errors import YearlyRuleError
from .yearly_reference_rules import validate_age_set

RULE_ID = "yearly.theme.sample_derived_candidate_selection"
RULE_VERSION = "v2"

REASON_ONLY_CANDIDATE = "ONLY_ELIGIBLE_CANDIDATE"
REASON_STRONGER_EVIDENCE = "STRONGER_MONTH_EVIDENCE"
REASON_AVOIDED_ADJACENT_REPEAT = "AVOIDED_ADJACENT_REPEAT"
REASON_EXCLUDED_CURRENT = "EXCLUDED_CURRENT_THEME_ON_RESELECTION"
REASON_KEPT_CURRENT_TO_AVOID_ADJACENT = "KEPT_CURRENT_THEME_TO_AVOID_ADJACENT_REPEAT"
REASON_KEPT_SOLE_CANDIDATE = "KEPT_SOLE_CANDIDATE_NO_ALTERNATIVE"
REASON_TIE_BREAK_THEME_ID = "TIE_BREAK_STABLE_THEME_ID"


@dataclass(frozen=True, slots=True)
class ThemeSelectionTrace:
    """Rule-local explanation of why one eligible candidate was selected."""

    period: YearMonth
    selected_theme_id: str
    reason: str
    rule_id: str
    rule_version: str
    eligible_theme_ids: tuple[str, ...]
    evidence_strength: int
    avoided_adjacent_repeat: bool
    excluded_theme_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThemeSelection:
    candidate: ThemeCandidate
    trace: ThemeSelectionTrace


def _sort_key(
    candidate: ThemeCandidate,
    calendar_month: int,
    adjacent: frozenset[str],
    excluded: frozenset[str],
) -> tuple[int, int, int, str]:
    return (
        1 if candidate.theme_id in adjacent else 0,
        1 if candidate.theme_id in excluded else 0,
        -candidate.evidence_strength_for_month(calendar_month),
        candidate.theme_id,
    )


def select_theme_for_period(
    *,
    catalog: ThemeCatalog,
    period: YearMonth,
    ages: frozenset[int],
    adjacent_theme_ids: frozenset[str] = frozenset(),
    exclude_theme_id: str | None = None,
) -> ThemeSelection:
    """Select one candidate using stable and explainable priorities.

    Priority is: avoid an adjacent repeat, avoid the explicitly excluded current
    candidate, prefer stronger evidence for the calendar month, then stable id.
    Penalties are soft so a sole eligible candidate remains selectable.
    """

    validated_ages = validate_age_set(ages)
    eligible = catalog.eligible_candidates(period.calendar_month, validated_ages)
    if not eligible:
        raise YearlyRuleError(
            RULE_ID,
            f"no eligible Theme candidate for {period.value} and ages {sorted(ages)}",
            period=period,
        )

    adjacent = frozenset(adjacent_theme_ids)
    excluded = frozenset({exclude_theme_id}) if exclude_theme_id else frozenset()
    ranked = sorted(
        eligible,
        key=lambda candidate: _sort_key(
            candidate, period.calendar_month, adjacent, excluded
        ),
    )
    chosen = ranked[0]

    eligible_ids = frozenset(candidate.theme_id for candidate in eligible)
    effective_adjacent = adjacent & eligible_ids
    effective_excluded = excluded & eligible_ids
    reason = _classify(
        chosen=chosen,
        ranked=ranked,
        eligible=eligible,
        calendar_month=period.calendar_month,
        adjacent=effective_adjacent,
        excluded=effective_excluded,
    )

    return ThemeSelection(
        candidate=chosen,
        trace=ThemeSelectionTrace(
            period=period,
            selected_theme_id=chosen.theme_id,
            reason=reason,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            eligible_theme_ids=tuple(sorted(eligible_ids)),
            evidence_strength=chosen.evidence_strength_for_month(
                period.calendar_month
            ),
            avoided_adjacent_repeat=bool(effective_adjacent)
            and chosen.theme_id not in effective_adjacent,
            excluded_theme_ids=tuple(sorted(adjacent | excluded)),
        ),
    )


def _classify(
    *,
    chosen: ThemeCandidate,
    ranked: list[ThemeCandidate],
    eligible: tuple[ThemeCandidate, ...],
    calendar_month: int,
    adjacent: frozenset[str],
    excluded: frozenset[str],
) -> str:
    if len(eligible) == 1:
        return REASON_ONLY_CANDIDATE

    eligible_ids = {candidate.theme_id for candidate in eligible}
    adjacent_safe = eligible_ids - adjacent
    if chosen.theme_id in excluded and chosen.theme_id not in adjacent:
        if not adjacent_safe - excluded:
            return REASON_KEPT_CURRENT_TO_AVOID_ADJACENT
    if chosen.theme_id in adjacent and chosen.theme_id in excluded:
        return REASON_KEPT_SOLE_CANDIDATE
    if chosen.theme_id in adjacent and not adjacent_safe:
        return REASON_KEPT_SOLE_CANDIDATE
    if excluded and chosen.theme_id not in excluded:
        return REASON_EXCLUDED_CURRENT
    if adjacent and chosen.theme_id not in adjacent:
        return REASON_AVOIDED_ADJACENT_REPEAT

    same_penalty = [
        candidate
        for candidate in ranked[1:]
        if (candidate.theme_id in adjacent) == (chosen.theme_id in adjacent)
        and (candidate.theme_id in excluded) == (chosen.theme_id in excluded)
    ]
    if same_penalty:
        chosen_strength = chosen.evidence_strength_for_month(calendar_month)
        if (
            same_penalty[0].evidence_strength_for_month(calendar_month)
            == chosen_strength
        ):
            return REASON_TIE_BREAK_THEME_ID
    return REASON_STRONGER_EVIDENCE
