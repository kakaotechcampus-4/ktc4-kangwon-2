"""Generate a DRAFT play-project yearly plan for one period (ADR-042 PLAY_PROJECT, P1 prototype).

P1 scope: one layout period per call, no institution evidence (the play-role artifact is not
approved yet), no repair, no select / edit / regenerate / confirm. A rejected proposal stores nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.errors import DomainError, InvalidDomainValueError
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
    PlayProjectProvider,
    build_play_project_request,
    parse_play_project_proposal,
    validate_play_project,
)
from ..planner.teacher_memo import normalize_teacher_memo, split_memo_applied, with_memo_evidence
from ..rules.yearly_reference_rules import validate_age_set
from .ports import Clock, IdGenerator, PlanRepository

SYSTEM_ACTOR = "play_project_application"
RULE_ID = "play_project.generate"

# The reference HWP's measured shape (4 periods x 5 rows), not a national standard (ADR-042 §3).
# 2026-10-24 decision: the AI offers 10 candidates per period and the teacher keeps 5, since an
# institution may lack the materials a play needs.
PLAY_PROJECT_LAYOUT_V0_2 = PlayProjectLayout(
    layout_version="play-project-layout-v0.2.0",
    periods=(
        PlayPeriod("m03_m05", (3, 4, 5), "3월~5월"),
        PlayPeriod("m06_m08", (6, 7, 8), "6월~8월"),
        PlayPeriod("m09_m11", (9, 10, 11), "9월~11월"),
        PlayPeriod("m12_m02", (12, 1, 2), "12월~2월"),
    ),
    candidates_per_period=10,
    selected_per_period=5,
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
    layout: PlayProjectLayout = PLAY_PROJECT_LAYOUT_V0_2
    avoid_play_names: tuple[str, ...] = ()  # other periods' plays in the same year
    # ADR-057: the teacher's request note, applied only inside the Rule range.
    teacher_memo: str = ""

    def __post_init__(self) -> None:
        if normalize_teacher_memo(self.teacher_memo) != self.teacher_memo:
            raise InvalidDomainValueError("teacher_memo must be normalized")


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
            period=period,
            ages=ages,
            row_count=command.layout.candidates_per_period,
            catalog=catalog,
            avoid_play_names=command.avoid_play_names,
            teacher_memo=command.teacher_memo,
        )
        content, memo_applied, memo_skipped = split_memo_applied(
            self._provider.generate_play_project(request).content, request.memo_addresses
        )
        proposal = parse_play_project_proposal(content)
        codes = validate_play_project(proposal, request)
        if codes:
            raise ProposalRejectedError(codes)

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()
        generation = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=RULE_ID,
            rule_version=request.prompt_version,
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
            marked = f"cand{index}" in memo_applied
            rows.append(
                PlayRow(
                    row_key=f"cand{index}",
                    play_name=item(row.play_name, with_memo_evidence((), marked)),
                    materials=item(row.materials, with_memo_evidence((), marked)),
                    support_direction=item(row.support_direction, with_memo_evidence((), marked)),
                    learning=item(
                        "\n".join(c.display for c in contents),
                        with_memo_evidence(
                            tuple(
                                EvidenceSource(
                                    source_type=EvidenceSourceType.CURRICULUM,
                                    source_id=c.content_id,
                                    source_version=catalog.catalog_version,
                                )
                                for c in contents
                            ),
                            marked,
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
            teacher_memo=command.teacher_memo,
            memo_notices=memo_skipped,
        )
        self._plans.save(plan.plan_id, plan)
        return plan
