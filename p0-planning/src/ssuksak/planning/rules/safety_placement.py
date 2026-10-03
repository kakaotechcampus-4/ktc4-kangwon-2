"""Apply and verify the product safety Placement Policy against the legal Rule.

The Rule never invents placement: months and week ordinals come only from the
HUMAN_APPROVED policy. Intervals are checked at month granularity; annual hours
are never verified here because the Plan holds no duration data.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.monthly_plan import MonthlyCell, MonthlyPlan
from ..domain.monthly_verification import (
    FindingKind,
    Severity,
    VerificationRuleRef,
    VerificationSourceRef,
    Violation,
    ViolationEvidence,
    ViolationLocation,
)
from ..domain.provenance import EvidenceSourceType
from ..domain.safety_placement import SafetyKind, SafetyPlacement, SafetyPlacementPolicy
from ..domain.safety_rule import SafetyLegalRule
from ..domain.week_period import WeekId, WeekPeriod
from ..domain.year_month import YearMonth
from .monthly_verification import RuleVerificationResult

SAFETY_SECTION_KEY = "safety_education"
PLACEMENT_RULE_ID = "monthly.safety.placement"
PLACEMENT_RULE_VERSION = "v1"
PLACEMENT_RULE_REF = VerificationRuleRef(PLACEMENT_RULE_ID, PLACEMENT_RULE_VERSION)
OFFICIAL_GROUNDING_MISSING = "SAFETY_OFFICIAL_GROUNDING_MISSING"
SUPPLEMENTAL_GROUNDING_INVALID = "SAFETY_SUPPLEMENTAL_GROUNDING_INVALID"
ANNUAL_HOURS_NOT_VERIFIED = "SAFETY_ANNUAL_HOURS_NOT_VERIFIED"


def official_ref(category_id: str, index: int) -> str:
    """Stable id of one official content item of the legal Rule (1-based)."""
    return f"annex6:{category_id}:{index}"


def is_official_ref(ref: str, category_id: str | None = None) -> bool:
    prefix = "annex6:" if category_id is None else f"annex6:{category_id}:"
    return ref.startswith(prefix)


def policy_violations(policy: SafetyPlacementPolicy, rule: SafetyLegalRule) -> tuple[str, ...]:
    """Why a policy cannot run with this legal Rule; empty means it can."""
    problems = []
    if policy.legal_rule_version != rule.legal_rule_version:
        problems.append(
            f"policy targets {policy.legal_rule_version}, active Rule is {rule.legal_rule_version}"
        )
    placed = {entry.category_id for entry in policy.entries}
    for unknown in sorted(placed - {category.category_id for category in rule.categories}):
        problems.append(f"{unknown} is not a legal category")
    for category in rule.categories:
        months = sorted({entry.month for entry in policy.entries if entry.category_id == category.category_id})
        if not months:
            problems.append(f"{category.category_id} is never placed")
            continue
        # The school-year placement repeats every year, so the gap wraps around.
        gaps = [(later - earlier) % 12 or 12 for earlier, later in zip(months, months[1:] + months[:1])]
        if max(gaps) > category.interval_months:
            problems.append(
                f"{category.category_id} gap {max(gaps)} months exceeds {category.interval_months}"
            )
    return tuple(problems)


@dataclass(frozen=True, slots=True)
class SafetySlot:
    week_id: WeekId
    placement: SafetyPlacement


def official_content_focus(
    policy: SafetyPlacementPolicy, rule: SafetyLegalRule, category_id: str, target_month: YearMonth
) -> str:
    """The policy's focus_rule applied to one placement: official order, rotating by school year."""
    start = policy.school_year_start_month
    school_order = lambda month: (month - start) % 12  # noqa: E731
    months = sorted({e.month for e in policy.entries if e.category_id == category_id}, key=school_order)
    school_year = target_month.calendar_year - (1 if target_month.calendar_month < start else 0)
    items = rule.category(category_id).content_items
    index = ((school_year - policy.base_school_year) * len(months) + months.index(target_month.calendar_month)) % len(items)
    return official_ref(category_id, index + 1)


def month_safety_slots(
    policy: SafetyPlacementPolicy,
    target_month: YearMonth,
    active_weeks: tuple[WeekPeriod, ...],
    rule: SafetyLegalRule | None = None,
) -> tuple[SafetySlot, ...]:
    """One slot per active week: the policy's STATUTORY weeks, SUPPLEMENTAL elsewhere."""
    if policy.focus_rule is not None and rule is None:
        raise ValueError("A focus policy needs the legal Rule's official content items")
    statutory = {entry.week_ordinal: entry.category_id for entry in policy.for_month(target_month.calendar_month)}
    if statutory and max(statutory) > len(active_weeks):
        raise ValueError(
            f"{target_month.value} has {len(active_weeks)} active weeks; the policy needs {max(statutory)}"
        )
    return tuple(
        SafetySlot(
            period.week_id,
            SafetyPlacement(
                SafetyKind.STATUTORY if ordinal in statutory else SafetyKind.SUPPLEMENTAL,
                statutory.get(ordinal),
                policy.policy_version,
                policy.legal_rule_version,
                (
                    official_content_focus(policy, rule, statutory[ordinal], target_month)
                    if ordinal in statutory and policy.focus_rule is not None
                    else None
                ),
            ),
        )
        for ordinal, period in enumerate(active_weeks, start=1)
    )


def select_supplemental_primaries(
    slot_count: int, candidates: tuple[tuple, ...]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """One distinct topic per supplemental week, preferring unused labels.

    candidates are (ref, supplemental_label, topic_group[, tier]) in retrieval rank order;
    tier 0 is the target month, 1 the MONTH_INDEPENDENT cross-month fallback. The
    tier decides first, then an unused label; the same topic is never used twice.
    Each slot gets its topic's first ref as primary and at most one more ref of
    the same topic as support. Too few distinct topics fails closed.
    """
    topics: dict[str, tuple[str, list[str]]] = {}
    tiers: dict[str, int] = {}
    for ref, label, group, *rest in candidates:
        topics.setdefault(group, (label, []))[1].append(ref)
        tiers[group] = min(tiers.get(group, 9), rest[0] if rest else 0)
    chosen: list[str] = []
    used_labels: set[str] = set()
    for _ in range(slot_count):
        remaining = [group for group in topics if group not in chosen]
        if not remaining:
            raise ValueError(
                f"{slot_count} supplemental weeks need distinct approved topics; only {len(topics)} available"
            )
        pick = min(remaining, key=lambda g: (tiers[g], topics[g][0] in used_labels))
        chosen.append(pick)
        used_labels.add(topics[pick][0])
    return tuple((topics[g][1][0], tuple(topics[g][1][1:2])) for g in chosen)


def verify_monthly_safety_placement(plan: MonthlyPlan) -> RuleVerificationResult:
    """Check each placed safety Cell's grounding against its kind and category."""
    cells = tuple(cell for cell in plan.cells if cell.safety is not None)
    placements = {cell.safety for cell in cells}
    sources = tuple(
        sorted(
            {VerificationSourceRef("safety.placement_policy", p.policy_version) for p in placements}
            | {VerificationSourceRef("safety.legal_rule", p.legal_rule_version) for p in placements},
            key=lambda source: (source.source_id, source.source_version),
        )
    )
    findings = [finding for cell in cells if (finding := _cell_finding(cell, sources))]
    if cells:
        findings.append(
            _finding(
                ANNUAL_HOURS_NOT_VERIFIED,
                FindingKind.NOT_VERIFIED,
                Severity.WARNING,
                ViolationLocation(SAFETY_SECTION_KEY),
                "Annual legal hours are not verified: the Plan records no education duration",
                "annual_hours_min=not_evaluated",
                sources,
            )
        )
    return RuleVerificationResult(PLACEMENT_RULE_REF, sources, tuple(findings))


def _cell_finding(cell: MonthlyCell, sources: tuple[VerificationSourceRef, ...]) -> Violation | None:
    if not cell.value.strip():
        return None
    placement = cell.safety
    official = [s for s in cell.evidence if s.source_type is EvidenceSourceType.SAFETY_RULE and is_official_ref(s.source_id)]
    samples = [s for s in cell.evidence if s.source_type is EvidenceSourceType.INSTITUTION_SAMPLE]
    location = ViolationLocation(cell.section_key, cell.week_id)
    if placement.kind is SafetyKind.STATUTORY:
        focus = placement.official_content_focus_ref
        if focus is not None and {s.source_id for s in official} == {focus}:
            return None
        if focus is None and any(is_official_ref(s.source_id, placement.category_id) for s in official) and all(
            is_official_ref(s.source_id, placement.category_id) for s in official
        ):
            return None
        code, message = OFFICIAL_GROUNDING_MISSING, (
            f"STATUTORY {placement.category_id} requires its own official content grounding only"
        )
    else:
        if samples and not official:
            return None
        code, message = SUPPLEMENTAL_GROUNDING_INVALID, (
            "SUPPLEMENTAL safety requires Sample grounding and no official legal content"
        )
    observed = f"kind={placement.kind.value};category={placement.category_id};refs=" + ",".join(
        s.source_id for s in (*official, *samples)
    )
    return _finding(code, FindingKind.VIOLATION, Severity.ERROR, location, message, observed, sources)


def _finding(code, kind, severity, location, message, observed, sources) -> Violation:
    return Violation(
        rule_id=PLACEMENT_RULE_ID,
        rule_version=PLACEMENT_RULE_VERSION,
        code=code,
        finding_kind=kind,
        severity=severity,
        location=location,
        message=message,
        evidence=(ViolationEvidence(observed, sources),),
    )
