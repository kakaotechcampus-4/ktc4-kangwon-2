"""놀이 프로젝트형 연간계획안을 생성하고 응답 형식으로 옮긴다 (api-spec §4)."""

import json
from dataclasses import replace
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictStr, StringConstraints
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_curriculum_reference_repository import JsonCurriculumReferenceRepository

# Core 가 공개 창구에 아직 안 내놓아 안쪽에서 가져온다 — router.py 와 같다.
from ssuksak.planning.application.generate_play_project_plan import (
    PLAY_PROJECT_LAYOUT_V0_2,
    GeneratePlayProjectPlan,
    GeneratePlayProjectPlanCommand,
)
from ssuksak.planning.domain.play_project_plan import ROW_FIELDS, PlayProjectYearlyPlan
from ssuksak.planning.planner.contracts import RawLlmResponse
from ssuksak.planning.planner.play_project import PlayProjectRequest

from app.features.plans.models import Plan
from app.features.plans.monthly_llm import monthly_llm_provider
from app.features.plans.monthly_schemas import RevisionIn
from app.features.plans.runtime import FixedPlanIdGenerator, SystemClock, UuidGenerator
from app.features.plans.schemas import (
    EvidenceOut,
    GenerationOut,
    PlayCandidateOut,
    PlayCellOut,
    PlayPeriodOut,
    PlayProjectPlanOut,
)
from app.shared.llm import is_mock

CURRICULUM_CATALOG_ID = "ssuksak.nuri-curriculum-content"
CURRICULUM_CATALOG_VERSION = "nuri-curriculum-content-v0.1.0"
_PERIOD_LABELS = {
    "m03_m05": "3~5월",
    "m06_m08": "6~8월",
    "m09_m11": "9~11월",
    "m12_m02": "12~2월",
}


class MockPlayProjectProvider:
    def generate_play_project(self, request: PlayProjectRequest) -> RawLlmResponse:
        content_ids = sorted(request.allowed_content_ids)
        return RawLlmResponse(
            content=json.dumps(
                {
                    "period_key": request.period_key,
                    "rows": [
                        {
                            "play_name": (
                                f"{_PERIOD_LABELS[request.period_key]} 함께하는 놀이 {index + 1}"
                            ),
                            "materials": "종이 상자와 천 조각, 자연물",
                            "support_direction": (
                                "주변의 모양과 움직임을 살펴보는 놀이를 지원하면 유아들이 "
                                "자료를 자유롭게 놓고 이어 보며 놀이를 넓혀 갈 수 있도록 돕는다."
                            ),
                            "learning_content_ids": [
                                content_ids[index % len(content_ids)],
                                content_ids[(index + 1) % len(content_ids)],
                            ],
                        }
                        for index in range(request.row_count)
                    ],
                },
                ensure_ascii=False,
            ),
            model="mock",
        )


def curriculum_repository():
    return JsonCurriculumReferenceRepository()


def provider():
    return MockPlayProjectProvider() if is_mock() else monthly_llm_provider()


def generate(school_year: int, classroom_ref: str, target_ages: frozenset[int]):
    plan_id = UuidGenerator().new_plan_id()
    use_case = GeneratePlayProjectPlan(
        curriculum_repository=curriculum_repository(),
        plan_repository=InMemoryPlanRepository(),
        provider=provider(),
        clock=SystemClock(),
        id_generator=FixedPlanIdGenerator(plan_id),
    )
    results = []
    avoid_play_names = ()
    for period in PLAY_PROJECT_LAYOUT_V0_2.periods:
        result = use_case.execute(
            GeneratePlayProjectPlanCommand(
                school_year=school_year,
                classroom_ref=classroom_ref,
                target_ages=target_ages,
                period_key=period.key,
                curriculum_catalog_id=CURRICULUM_CATALOG_ID,
                curriculum_catalog_version=CURRICULUM_CATALOG_VERSION,
                avoid_play_names=avoid_play_names,
            )
        )
        results.append(result)
        avoid_play_names += tuple(
            candidate.play_name.value for candidate in result.periods[0].candidates
        )
    return replace(results[0], periods=tuple(result.periods[0] for result in results))


def format_of(row: Plan) -> str:
    """양식은 본문에 있다. 없으면 월별 주제형이다(ADR-043 §1 · 마이그레이션 없음)."""
    return row.body.get("format", "MONTHLY_THEME")


def _cell(item) -> PlayCellOut:
    return PlayCellOut(
        item_id=item.item_id.value,
        value=item.value,
        evidence=[
            EvidenceOut(
                source_type=source.source_type.value,
                source_id=source.source_id,
                source_version=source.source_version,
                effective_date=None,
                display_name=source.display_name,
            )
            for source in item.evidence
        ],
        generation=GenerationOut(
            method=item.generation.method.value,
            rule_id=item.generation.rule_id,
            rule_version=item.generation.rule_version,
        ),
    )


def to_out(row: Plan, plan: PlayProjectYearlyPlan) -> PlayProjectPlanOut:
    return PlayProjectPlanOut(
        id=row.id,
        revision=row.revision,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        status=plan.status.value,
        format=plan.format,
        format_version=plan.layout_version,
        periods=[
            PlayPeriodOut(
                period_key=p.period.key,
                label=p.period.label,
                months=list(p.period.months),
                candidates=[
                    PlayCandidateOut(
                        row_key=c.row_key, **{name: _cell(getattr(c, name)) for name in ROW_FIELDS}
                    )
                    for c in p.candidates
                ],
                selected=list(p.selected),
            )
            for p in plan.periods
        ],
    )


def _no_duplicates(keys: list[str]) -> list[str]:
    if len(keys) != len(set(keys)):
        raise ValueError("같은 후보를 두 번 고를 수 없습니다")
    return keys


# row_key 는 Core 가 "cand1".."candN" 으로 만든다(domain/play_project_plan.py:67). 형식 · 길이
# 규칙은 Core 에 없어 모양은 걸지 않고, 없는 후보는 Core 의 invalid_selection 이 막는다.
# 5개는 layout.selected_per_period(application/play_project_lifecycle.py:84)와 같은 값이다.
_Selected = Annotated[list[StrictStr], Field(max_length=5), AfterValidator(_no_duplicates)]


class PlaySelections(BaseModel):
    """네 구간을 모두 받는다(api-spec §6-1). 구간 키는 _PERIOD_LABELS 와 같다."""

    model_config = ConfigDict(extra="forbid")

    m03_m05: _Selected
    m06_m08: _Selected
    m09_m11: _Selected
    m12_m02: _Selected


class SaveSelectionIn(RevisionIn):
    selections: PlaySelections


class EditItemIn(RevisionIn):
    # 본문이 JSONB 라 맞출 컬럼이 없다. Core 생성 검사의 가장 긴 칸(지원 방향 600자,
    # planner/text_policy.py:8 MAX_RATIONALE_CHARS)에 맞춘다.
    value: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=600)
    ]
