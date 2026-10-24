"""Generate a DRAFT play-project yearly plan for one period (ADR-042 PLAY_PROJECT, P1 prototype).

P1 scope: one layout period per call, no institution evidence (the play-role artifact is not
approved yet), no repair, no edit / regenerate / confirm. A rejected proposal stores nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.errors import DomainError
from ..domain.plan import PlanItem, PlanStatus
from ..domain.play_project_plan import (
    PlayPeriod,
    PlayPeriodRows,
    PlayProjectLayout,
    PlayProjectYearlyPlan,
    PlayRow,
)
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..planner.contracts import ProposalRejectedError
from ..planner.play_project import (
    PLAY_PROJECT_PROMPT_VERSION,
    PlayProjectProvider,
    build_play_project_request,
    parse_play_project_proposal,
    validate_play_project,
)
from ..rules.yearly_reference_rules import validate_age_set
from .ports import Clock, IdGenerator, PlanRepository

SYSTEM_ACTOR = "play_project_application"
RULE_ID = "play_project.generate"

# The reference HWP's measured shape (4 periods x 5 rows), not a national standard (ADR-042 §3).
PLAY_PROJECT_LAYOUT_V0_1 = PlayProjectLayout(
    layout_version="play-project-layout-v0.1.0",
    periods=(
        PlayPeriod("m03_m05", (3, 4, 5), "3월~5월"),
        PlayPeriod("m06_m08", (6, 7, 8), "6월~8월"),
        PlayPeriod("m09_m11", (9, 10, 11), "9월~11월"),
        PlayPeriod("m12_m02", (12, 1, 2), "12월~2월"),
    ),
    rows_per_period=5,
)


class PlayProjectGenerationError(DomainError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CurriculumReferenceRepository(Protocol):
    def get_catalog(self, catalog_id: str, catalog_version: str) -> CurriculumCatalog | None: ...


@dataclass(frozen=True, slots=True)
class GeneratePlayProjectPlanCommand:
    school_year: int
    classroom_ref: str
    target_ages: frozenset[int]
    period_key: str
    curriculum_catalog_id: str
    curriculum_catalog_version: str
    layout: PlayProjectLayout = PLAY_PROJECT_LAYOUT_V0_1


class GeneratePlayProjectPlan:
    def __init__(
        self,
        *,
        curriculum_repository: CurriculumReferenceRepository,
        plan_repository: PlanRepository[PlayProjectYearlyPlan],
        provider: PlayProjectProvider,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._curriculum = curriculum_repository
        self._plans = plan_repository
        self._provider = provider
        self._clock = clock
        self._ids = id_generator

    def execute(self, command: GeneratePlayProjectPlanCommand) -> PlayProjectYearlyPlan:
        ages = validate_age_set(command.target_ages)
        period = command.layout.period(command.period_key)
        if period is None:
            raise PlayProjectGenerationError("UNKNOWN_PERIOD")
        catalog = self._curriculum.get_catalog(
            command.curriculum_catalog_id, command.curriculum_catalog_version
        )
        if catalog is None:
            raise PlayProjectGenerationError("CURRICULUM_REFERENCE_NOT_FOUND")
        if not catalog.is_active:
            raise PlayProjectGenerationError("CURRICULUM_REFERENCE_NOT_ACTIVE")

        request = build_play_project_request(
            period=period, ages=ages, row_count=command.layout.rows_per_period, catalog=catalog
        )
        proposal = parse_play_project_proposal(
            self._provider.generate_play_project(request).content
        )
        codes = validate_play_project(proposal, request)
        if codes:
            raise ProposalRejectedError(codes)

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()
        generation = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=RULE_ID,
            rule_version=PLAY_PROJECT_PROMPT_VERSION,
        )

        def item(value: str, evidence: tuple[EvidenceSource, ...] = ()) -> PlanItem:
            item_id = self._ids.new_item_id()
            created = AuditEvent(
                event_type=AuditEventType.CREATED,
                occurred_at=now,
                plan_id=plan_id,
                item_id=item_id,
                system_actor=SYSTEM_ACTOR,
            )
            return PlanItem(item_id, value, evidence, generation, AuditHistory((created,)))

        rows = []
        for index, row in enumerate(proposal.rows, 1):
            contents = [catalog.get(content_id) for content_id in row.learning_content_ids]
            rows.append(
                PlayRow(
                    row_key=f"row{index}",
                    play_name=item(row.play_name),
                    materials=item(row.materials),
                    support_direction=item(row.support_direction),
                    learning=item(
                        "\n".join(c.display for c in contents),
                        tuple(
                            EvidenceSource(
                                source_type=EvidenceSourceType.CURRICULUM,
                                source_id=c.content_id,
                                source_version=catalog.catalog_version,
                            )
                            for c in contents
                        ),
                    ),
                )
            )

        plan = PlayProjectYearlyPlan(
            plan_id=plan_id,
            school_year=command.school_year,
            classroom_ref=command.classroom_ref,
            target_ages=ages,
            status=PlanStatus.DRAFT,
            layout_version=command.layout.layout_version,
            periods=(PlayPeriodRows(period, tuple(rows)),),
            audit=AuditHistory(
                (
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=now,
                        plan_id=plan_id,
                        system_actor=SYSTEM_ACTOR,
                    ),
                )
            ),
        )
        self._plans.save(plan.plan_id, plan)
        return plan
