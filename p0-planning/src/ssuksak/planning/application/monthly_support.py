"""Shared orchestration helpers for Monthly application use cases."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from functools import partial

from ..context.builder import ContextPacketBuilder
from ..context.models import (
    MonthlyContextPacket,
    OfficialSafetyContent,
    SafetyContext,
    SafetySlotContext,
)
from ..domain.activity_reference import ActivityCatalog
from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_constraint import ConstraintAssessment
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template import SectionRole
from ..domain.monthly_template_profile import TemplateProfile, TemplateProfileRef
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.provenance import EvidenceSource, EvidenceSourceType
from ..domain.safety_placement import SafetyKind, SafetyPlacementPolicy
from ..domain.safety_rule import SafetyLegalRule
from ..domain.week_period import WeekPeriod
from ..domain.year_month import YearMonth
from ..evidence.classification import SemanticClass, grounding_class_for
from ..evidence.ports import EvidenceClassificationRepository, InstitutionEvidenceRepository
from ..evidence.safety_classification import SafetyEvidenceClassification
from ..retrieval.models import RetrievalRequest
from ..retrieval.retriever import SAFETY_RETRIEVAL_VERSION, MonthlyEvidenceRetriever
from ..rules.monthly_verification import (
    verify_monthly_activity_ages,
    verify_monthly_plan,
)
from ..rules.safety_placement import (
    SafetySlot,
    official_ref,
    policy_violations,
    select_supplemental_primaries,
    verify_monthly_safety_placement,
)
from .monthly_dto import ActivityCatalogSelector, SafetyPlacementSelector, SafetyRuleSelector
from .monthly_errors import MonthlyApplicationError
from .ports import (
    ActivityReferenceRepository,
    OptionalContextProvider,
    OptionalContextResult,
    PlanRepository,
    SafetyLegalRuleRepository,
    SafetyPlacementPolicyRepository,
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


def load_safety_placement_policy(
    repository: SafetyPlacementPolicyRepository | None,
    selector: SafetyPlacementSelector | None,
    rule: SafetyLegalRule,
) -> SafetyPlacementPolicy | None:
    """The selected HUMAN_APPROVED policy that fits the legal Rule, or fail closed."""
    if selector is None:
        return None
    if repository is None:
        raise MonthlyApplicationError(
            "safety_placement_repository_required",
            "A safety placement selector requires a repository",
        )
    policy = repository.get_policy(selector.policy_version)
    if policy is None:
        raise MonthlyApplicationError(
            "safety_placement_policy_not_found",
            f"Safety Placement Policy not found: {selector.policy_version}",
        )
    if not policy.runtime_active:
        raise MonthlyApplicationError(
            "safety_placement_policy_not_approved",
            f"Safety Placement Policy is not HUMAN_APPROVED: {selector.policy_version}",
        )
    problems = policy_violations(policy, rule)
    if problems:
        raise MonthlyApplicationError(
            "safety_placement_policy_invalid",
            "Safety Placement Policy does not fit the legal Rule: " + "; ".join(problems),
        )
    return policy


def _safety_context(slots: tuple[SafetySlot, ...], rule: SafetyLegalRule) -> SafetyContext:
    statutory = []
    for slot in slots:
        if slot.placement.category_id and slot.placement.category_id not in statutory:
            statutory.append(slot.placement.category_id)
    focus = {slot.placement.category_id: slot.placement.official_content_focus_ref for slot in slots}
    # With a focus the LLM sees only that one official item; without (v1) the whole category.
    official = tuple(
        OfficialSafetyContent(official_ref(category.category_id, index), category.category_id, category.official_label, text)
        for category_id in statutory
        if (category := rule.category(category_id)) is not None
        for index, text in enumerate(category.content_items, start=1)
        if focus.get(category_id) in (None, official_ref(category_id, index))
    )
    return SafetyContext(
        policy_version=slots[0].placement.policy_version,
        legal_rule_version=rule.legal_rule_version,
        retrieval_version=SAFETY_RETRIEVAL_VERSION,
        slots=tuple(
            SafetySlotContext(
                str(slot.week_id), slot.placement.kind, slot.placement.category_id,
                slot.placement.official_content_focus_ref,
            )
            for slot in slots
        ),
        official_content=official,
    )


def _with_supplemental_primaries(safety: SafetyContext) -> SafetyContext:
    """Assign each supplemental week one distinct approved topic before the LLM runs."""
    slots = [slot for slot in safety.slots if slot.kind is SafetyKind.SUPPLEMENTAL]
    candidates = tuple(
        (ref.evidence_ref, ref.supplemental_label, ref.topic_group, 1 if ref.cross_month else 0)
        for ref in safety.references
        if ref.supplemental_label and ref.topic_group
    )
    try:
        picks = select_supplemental_primaries(len(slots), candidates)
    except ValueError as exc:
        raise MonthlyApplicationError("monthly_safety_grounding_insufficient", str(exc)) from exc
    assigned = dict(zip((slot.week_id for slot in slots), picks))
    return replace(
        safety,
        slots=tuple(
            replace(slot, primary_ref=assigned[slot.week_id][0], support_refs=assigned[slot.week_id][1])
            if slot.week_id in assigned
            else slot
            for slot in safety.slots
        ),
    )


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
    if any(cell.safety is not None for cell in plan.cells):
        verifiers += (verify_monthly_safety_placement,)
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
        classification_repository: EvidenceClassificationRepository,
        context_builder: ContextPacketBuilder,
        safety_classification_repository=None,
        safety_quality_repository=None,
    ) -> None:
        self._evidence = evidence_repository
        self._classification = classification_repository
        self._context = context_builder
        # Without an approved safety classification, no Sample safety evidence is used.
        self._safety_classification = safety_classification_repository
        # Without an approved quality review, no Sample can ground a supplemental week.
        self._safety_quality = safety_quality_repository

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
        grounding_classes: frozenset[SemanticClass] = frozenset(),
        keywords: tuple[str, ...] = (),
        safety_slots: tuple[SafetySlot, ...] = (),
        safety_rule: SafetyLegalRule | None = None,
    ) -> MonthlyContextPacket:
        active_weeks = tuple(period for period in week_periods if period.active)
        safety = _safety_context(safety_slots, safety_rule) if safety_slots and safety_rule else None
        safety_classification: SafetyEvidenceClassification | None = (
            self._safety_classification.get_classification()
            if safety is not None and self._safety_classification is not None
            else None
        )
        safety_quality = (
            self._safety_quality.get_quality()
            if safety is not None and self._safety_quality is not None
            else None
        )
        try:
            retriever = MonthlyEvidenceRetriever(
                self._evidence.get_store(),
                activity_catalog=activity_catalog,
                classification=self._classification.get_classification(),
                safety_classification=safety_classification,
                safety_quality=safety_quality,
            )
        except InvalidDomainValueError as exc:
            raise MonthlyApplicationError(
                "evidence_classification_store_mismatch",
                "The approved Evidence classification does not match the Evidence Store content",
            ) from exc
        retrieval = retriever.retrieve(
            RetrievalRequest(
                target_month=target_month,
                ages=ages,
                confirmed_theme_id=parent_theme_id,
                confirmed_theme_value=parent_theme_value,
                week_count=len(active_weeks),
                keywords=keywords,
                grounding_classes=grounding_classes,
                safety_keywords=(
                    tuple(item.text for item in safety.official_content) if safety is not None else ()
                ),
                safety_categories=(
                    tuple(sorted({item.category_id for item in safety.official_content}))
                    if safety is not None
                    else ()
                ),
            )
        )
        packet = self._context.build(
            retrieval,
            week_periods=week_periods,
            safety=safety,
            safety_classification=safety_classification,
            safety_quality=safety_quality,
            deterministic_constraint_codes=tuple(
                assessment.constraint.code for assessment in constraint_assessments
            ),
        )
        return packet if packet.safety is None else replace(packet, safety=_with_supplemental_primaries(packet.safety))


def snapshot_grounding_classes(snapshot: TemplateSnapshot) -> frozenset[SemanticClass]:
    return frozenset(
        grounding_class
        for section in snapshot.sections
        if section.role is SectionRole.CONTENT
        and (grounding_class := grounding_class_for(section)) is not None
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
    by_ref = {item.evidence_ref: item for item in packet.grounding_items}
    official = packet.safety.official_by_ref if packet.safety is not None else {}
    evidence: list[EvidenceSource] = []
    for ref in refs:
        if ref in official:
            # Official legal content: Legal Rule provenance, never an institution Sample.
            evidence.append(
                EvidenceSource(
                    EvidenceSourceType.SAFETY_RULE,
                    source_id=ref,
                    source_version=packet.safety.legal_rule_version,
                    display_name=official[ref].text,
                )
            )
            continue
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
