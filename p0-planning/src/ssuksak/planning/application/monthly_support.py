"""Shared orchestration helpers for Monthly application use cases."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from functools import partial

from ..context.builder import ContextPacketBuilder
from ..context.models import MonthlyContextPacket
from ..domain.activity_reference import ActivityCatalog
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_constraint import ConstraintAssessment
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template_profile import TemplateProfile, TemplateProfileRef
from ..domain.provenance import EvidenceSource, EvidenceSourceType
from ..domain.safety_rule import SafetyLegalRule
from ..domain.week_period import WeekPeriod
from ..domain.year_month import YearMonth
from ..evidence.ports import InstitutionEvidenceRepository
from ..retrieval.models import RetrievalRequest
from ..retrieval.retriever import MonthlyEvidenceRetriever
from ..rules.monthly_verification import (
    verify_monthly_activity_ages,
    verify_monthly_plan,
)
from .monthly_dto import ActivityCatalogSelector, SafetyRuleSelector
from .monthly_errors import MonthlyApplicationError
from .ports import (
    ActivityReferenceRepository,
    OptionalContextProvider,
    OptionalContextResult,
    PlanRepository,
    SafetyLegalRuleRepository,
    TemplateProfileRepository,
)
from .yearly_support import fetch_optional_context


def require_monthly_plan(
    repository: PlanRepository[MonthlyPlan], plan_id: object
) -> MonthlyPlan:
    if not isinstance(plan_id, PlanId):
        raise MonthlyApplicationError(
            "invalid_plan_id", "Monthly use cases require PlanId"
        )
    plan = repository.get(plan_id)
    if plan is None:
        raise MonthlyApplicationError(
            "monthly_plan_not_found", f"Monthly Plan not found: {plan_id}"
        )
    if not isinstance(plan, MonthlyPlan):
        raise MonthlyApplicationError(
            "repository_contract_violation",
            "PlanRepository returned a non-MonthlyPlan value",
        )
    return plan


def require_actor(actor_id: object) -> ActorId:
    if not isinstance(actor_id, ActorId):
        raise MonthlyApplicationError(
            "opaque_actor_required", "Monthly mutation requires ActorId"
        )
    return actor_id


def require_item_id(item_id: object) -> ItemId:
    if not isinstance(item_id, ItemId):
        raise MonthlyApplicationError(
            "invalid_item_id", "Monthly item use cases require ItemId"
        )
    return item_id


def load_template_profile(
    repository: TemplateProfileRepository, selector: TemplateProfileRef
) -> TemplateProfile:
    profile = repository.get_profile(
        selector.profile_id, selector.profile_version
    )
    if profile is None:
        raise MonthlyApplicationError(
            "monthly_template_profile_not_found",
            f"Monthly Template Profile not found: {selector}",
        )
    return profile


def load_safety_rule(
    repository: SafetyLegalRuleRepository, selector: SafetyRuleSelector
) -> SafetyLegalRule:
    rule = repository.get_legal_rule(selector.legal_rule_version)
    if rule is None:
        raise MonthlyApplicationError(
            "safety_rule_not_found",
            f"Safety Rule not found: {selector.legal_rule_version}",
        )
    if not rule.is_active:
        raise MonthlyApplicationError(
            "safety_rule_not_approved",
            f"Safety Rule is not active: {selector.legal_rule_version}",
        )
    return rule


def load_activity_catalog(
    repository: ActivityReferenceRepository | None,
    selector: ActivityCatalogSelector | None,
) -> ActivityCatalog | None:
    if selector is None:
        return None
    if repository is None:
        raise MonthlyApplicationError(
            "activity_repository_required",
            "An Activity Catalog selector requires a repository",
        )
    catalog = repository.get_catalog(selector.catalog_id, selector.catalog_version)
    if catalog is None:
        raise MonthlyApplicationError(
            "activity_catalog_not_found",
            f"Activity Catalog not found: {selector.catalog_id}/{selector.catalog_version}",
        )
    if not catalog.is_active:
        raise MonthlyApplicationError(
            "activity_catalog_not_approved",
            f"Activity Catalog is not HUMAN_APPROVED: {selector.catalog_version}",
        )
    return catalog


def load_plan_activity_catalog(
    repository: ActivityReferenceRepository | None,
    plan: MonthlyPlan,
) -> ActivityCatalog | None:
    ref = plan.activity_catalog_ref
    if ref is None:
        return None
    return load_activity_catalog(
        repository,
        ActivityCatalogSelector(ref.catalog_id, ref.catalog_version),
    )


def with_fresh_monthly_verification(
    plan: MonthlyPlan,
    catalog: ActivityCatalog | None,
) -> MonthlyPlan:
    verifiers = (
        (partial(verify_monthly_activity_ages, catalog=catalog),)
        if catalog is not None
        else ()
    )
    try:
        report = verify_monthly_plan(plan, verifiers)
    except Exception as exc:
        raise MonthlyApplicationError(
            "monthly_verification_failed",
            "Monthly rule verification failed before the Plan was saved",
        ) from exc
    return replace(plan, verification_report=report)


def optional_context_results(
    names: Iterable[str], provider: OptionalContextProvider | None
) -> tuple[OptionalContextResult, ...]:
    return fetch_optional_context(names, provider)


class MonthlyContextPipeline:
    """Reuse PR4 retrieval and packet construction without owning their rules."""

    def __init__(
        self,
        *,
        evidence_repository: InstitutionEvidenceRepository,
        context_builder: ContextPacketBuilder,
    ) -> None:
        self._evidence = evidence_repository
        self._context = context_builder

    def build(
        self,
        *,
        target_month: YearMonth,
        ages: frozenset[int],
        parent_theme_id: str,
        parent_theme_value: str,
        week_periods: tuple[WeekPeriod, ...],
        activity_catalog: ActivityCatalog | None,
        constraint_assessments: tuple[ConstraintAssessment, ...],
        keywords: tuple[str, ...] = (),
    ) -> MonthlyContextPacket:
        active_weeks = tuple(period for period in week_periods if period.active)
        retrieval = MonthlyEvidenceRetriever(
            self._evidence.get_store(), activity_catalog=activity_catalog
        ).retrieve(
            RetrievalRequest(
                target_month=target_month,
                ages=ages,
                confirmed_theme_id=parent_theme_id,
                confirmed_theme_value=parent_theme_value,
                week_count=len(active_weeks),
                keywords=keywords,
            )
        )
        return self._context.build(
            retrieval,
            week_periods=week_periods,
            deterministic_constraint_codes=tuple(
                assessment.constraint.code for assessment in constraint_assessments
            ),
        )


def theme_reference_id(evidence: tuple[EvidenceSource, ...]) -> str:
    references = tuple(
        source
        for source in evidence
        if source.source_type is EvidenceSourceType.THEME_REFERENCE
    )
    if len(references) != 1:
        raise MonthlyApplicationError(
            "theme_reference_required",
            "Monthly parent Theme must resolve to exactly one THEME_REFERENCE",
        )
    return references[0].source_id


def deduplicate_evidence(
    values: Iterable[EvidenceSource],
) -> tuple[EvidenceSource, ...]:
    result: list[EvidenceSource] = []
    seen: set[tuple[object, str, str | None]] = set()
    for value in values:
        key = (value.source_type, value.source_id, value.source_version)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def packet_evidence(
    packet: MonthlyContextPacket, refs: Iterable[str]
) -> tuple[EvidenceSource, ...]:
    by_ref = {
        item.evidence_ref: item
        for item in (
            packet.institution_evidence
            + packet.age_contrast_evidence
            + packet.week_experience_candidates
            + packet.other_outdoor_evidence
        )
    }
    evidence: list[EvidenceSource] = []
    for ref in refs:
        item = by_ref.get(ref)
        if item is None:
            raise MonthlyApplicationError(
                "planner_grounding_not_in_packet",
                f"Planner grounding ref is absent from Context Packet: {ref}",
            )
        evidence.append(
            EvidenceSource(
                EvidenceSourceType.INSTITUTION_SAMPLE,
                source_id=ref,
                source_version=packet.lineage.evidence_store_version,
                display_name=item.source_label,
            )
        )
    return tuple(evidence)
