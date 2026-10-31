"""Official assembly point for play-centred monthly (PLAY_MONTHLY) generation (ADR-046 Q3 · Q4).

The backend supplies what it owns: the parent / plan repositories, the provider (the Elice
adapter over its own transport), the clock and the id generator, plus the request facts. The
Reference repositories and every catalog / rule version live here once, so the server keeps
no copy. Approval is still checked by the use case: assembling never turns a draft on.

This module lives in ``adapters`` because it wires concrete JSON Reference adapters;
``planning`` must not import ``adapters``.
"""

from __future__ import annotations

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.json_curriculum_reference_repository import JsonCurriculumReferenceRepository
from ssuksak.adapters.json_daily_life_reference_repository import JsonDailyLifeReferenceRepository
from ssuksak.adapters.json_drill_topic_reference_repository import JsonDrillTopicReferenceRepository
from ssuksak.adapters.monthly_reference_repositories import JsonSafetyLegalRuleRepository
from ssuksak.adapters.safety_evidence_classification_repository import JsonSafetyEvidenceClassificationRepository
from ssuksak.adapters.safety_reference_quality_repository import JsonSafetyReferenceQualityRepository
from ssuksak.planning.application.generate_play_monthly_plan import (
    GeneratePlayMonthlyPlan,
    GeneratePlayMonthlyPlanCommand,
)
from ssuksak.planning.application.play_monthly_lifecycle import EditPlayMonthlyContentIds
from ssuksak.planning.domain.identifiers import PlanId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.planner.play_monthly import PlayMonthlyProvider

CURRICULUM_CATALOG = ("ssuksak.nuri-curriculum-content", "nuri-curriculum-content-v0.1.0")
DAILY_LIFE_CATALOG = ("ssuksak.daily-life", "daily-life-v0.1.0")
DRILL_CATALOG = ("ssuksak.emergency-drill-topics", "emergency-drill-topics-v0.1.0")
LEGAL_RULE_VERSION = "child-welfare-act-decree-annex6-2022-06-21"
SAFETY_CLASSIFICATION_VERSION = "safety-evidence-classification-v0.2.0"
SAFETY_QUALITY_VERSION = "safety-reference-quality-v0.1.0"
# The Evidence Store's version and SHA are read from the store itself, not passed here.


def play_monthly_generation(
    *, parent_repository, plan_repository, provider: PlayMonthlyProvider, clock, id_generator
) -> GeneratePlayMonthlyPlan:
    return GeneratePlayMonthlyPlan(
        parent_repository=parent_repository,
        plan_repository=plan_repository,
        curriculum_repository=JsonCurriculumReferenceRepository(),
        daily_life_repository=JsonDailyLifeReferenceRepository(),
        drill_repository=JsonDrillTopicReferenceRepository(),
        safety_rule_repository=JsonSafetyLegalRuleRepository(),
        evidence_repository=JsonInstitutionEvidenceRepository(),
        safety_classification_repository=JsonSafetyEvidenceClassificationRepository(),
        safety_quality_repository=JsonSafetyReferenceQualityRepository(),
        provider=provider,
        clock=clock,
        id_generator=id_generator,
    )


def play_monthly_command(
    *,
    parent_plan_id: PlanId,
    classroom_ref: str,
    school_year: int,
    target_month: YearMonth,
    emphasized_row_keys: tuple[str, ...] = (),
    class_name: str = "",
) -> GeneratePlayMonthlyPlanCommand:
    """The request facts from the caller; the Reference versions from this module."""
    return GeneratePlayMonthlyPlanCommand(
        parent_plan_id=parent_plan_id,
        classroom_ref=classroom_ref,
        school_year=school_year,
        target_month=target_month,
        curriculum_catalog_id=CURRICULUM_CATALOG[0],
        curriculum_catalog_version=CURRICULUM_CATALOG[1],
        daily_life_catalog_id=DAILY_LIFE_CATALOG[0],
        daily_life_catalog_version=DAILY_LIFE_CATALOG[1],
        legal_rule_version=LEGAL_RULE_VERSION,
        safety_classification_version=SAFETY_CLASSIFICATION_VERSION,
        safety_quality_version=SAFETY_QUALITY_VERSION,
        drill_catalog_id=DRILL_CATALOG[0],
        drill_catalog_version=DRILL_CATALOG[1],
        emphasized_row_keys=emphasized_row_keys,
        class_name=class_name,
    )


def play_monthly_content_ids_edit(*, plan_repository, clock) -> EditPlayMonthlyContentIds:
    """The only lifecycle step that reads a Reference (누리과정); the others need none."""
    return EditPlayMonthlyContentIds(
        plan_repository=plan_repository, curriculum_repository=JsonCurriculumReferenceRepository(), clock=clock
    )
