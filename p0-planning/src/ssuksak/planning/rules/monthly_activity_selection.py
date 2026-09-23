"""Pure deterministic ranking of already eligible Activity candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..domain.activity_reference import ActivityCandidate

RULE_ID = "monthly.activity.reference_candidate_selection"
RULE_VERSION = "v2"


@dataclass(frozen=True, slots=True)
class ActivitySelectionTrace:
    rule_id: str
    rule_version: str
    eligible_candidate_ids: tuple[str, ...]
    selected_activity_id: str | None
    selected_sort_key: tuple[object, ...] | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActivitySelection:
    candidate: ActivityCandidate | None
    trace: ActivitySelectionTrace

    @property
    def has_selection(self) -> bool:
        return self.candidate is not None


def _sort_key(
    candidate: ActivityCandidate,
    *,
    calendar_month: int,
    used_activity_ids: frozenset[str],
    current_activity_id: str | None,
    parent_theme_id: str | None,
    used_curriculum_domains: Mapping[str, int],
) -> tuple[object, ...]:
    repeat = int(candidate.activity_id in used_activity_ids) + int(
        candidate.activity_id == current_activity_id
    )
    theme = int(parent_theme_id is not None and not candidate.links_theme(parent_theme_id))
    display = int(candidate.has_confirmed_display_issue)
    curriculum = sum(
        used_curriculum_domains.get(link.domain, 0)
        for link in candidate.curriculum_links
    )
    evidence = -candidate.evidence_strength_for_month(calendar_month)
    return repeat, theme, display, curriculum, evidence, candidate.activity_id


def _reasons(key: tuple[object, ...], *, only: bool) -> tuple[str, ...]:
    if only:
        return ("ONLY_ELIGIBLE_CANDIDATE",)
    reasons: list[str] = []
    labels = (
        "AVOIDED_REPEAT_IN_MONTH",
        "MATCHED_PARENT_THEME",
        "AVOIDED_CONFIRMED_DISPLAY_QUALITY_ISSUE",
        "AVOIDED_CURRICULUM_DOMAIN_REPEAT",
        "STRONGER_MONTH_EVIDENCE",
    )
    for index, label in enumerate(labels):
        if key[index] == 0 or (index == 4 and int(key[index]) < 0):
            reasons.append(label)
    reasons.append("TIE_BREAK_STABLE_ACTIVITY_ID")
    return tuple(reasons)


def select_activity_for_cell(
    candidates: Sequence[ActivityCandidate],
    *,
    calendar_month: int,
    used_activity_ids: frozenset[str] = frozenset(),
    current_activity_id: str | None = None,
    parent_theme_id: str | None = None,
    used_curriculum_domains: Mapping[str, int] | None = None,
) -> ActivitySelection:
    """Rank without filtering; hard eligibility belongs to ActivityCatalog."""
    ordered_ids = tuple(sorted(candidate.activity_id for candidate in candidates))
    if not candidates:
        return ActivitySelection(
            None,
            ActivitySelectionTrace(
                RULE_ID,
                RULE_VERSION,
                (),
                None,
                None,
                ("NO_ELIGIBLE_CANDIDATE",),
            ),
        )
    domains = used_curriculum_domains or {}
    ranked = sorted(
        candidates,
        key=lambda candidate: _sort_key(
            candidate,
            calendar_month=calendar_month,
            used_activity_ids=used_activity_ids,
            current_activity_id=current_activity_id,
            parent_theme_id=parent_theme_id,
            used_curriculum_domains=domains,
        ),
    )
    selected = ranked[0]
    key = _sort_key(
        selected,
        calendar_month=calendar_month,
        used_activity_ids=used_activity_ids,
        current_activity_id=current_activity_id,
        parent_theme_id=parent_theme_id,
        used_curriculum_domains=domains,
    )
    return ActivitySelection(
        selected,
        ActivitySelectionTrace(
            RULE_ID,
            RULE_VERSION,
            ordered_ids,
            selected.activity_id,
            key,
            _reasons(key, only=len(candidates) == 1),
        ),
    )
