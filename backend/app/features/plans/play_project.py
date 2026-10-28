"""놀이 프로젝트형 연간계획안을 응답 형식으로 옮긴다 (api-spec §4 「놀이 프로젝트형 응답」)."""

# Core 가 공개 창구(`ssuksak.planning`)에 아직 안 내놓아 안쪽에서 가져온다 — router.py 와 같다.
from ssuksak.planning.domain.play_project_plan import ROW_FIELDS, PlayProjectYearlyPlan

from app.features.plans.models import Plan
from app.features.plans.schemas import (
    EvidenceOut,
    GenerationOut,
    PlayCandidateOut,
    PlayCellOut,
    PlayPeriodOut,
    PlayProjectPlanOut,
)


def format_of(row: Plan) -> str:
    """양식은 본문에 있다. 없으면 월별 주제형이다(ADR-043 §1 · 마이그레이션 없음)."""
    return row.body.get("format", "MONTHLY_THEME")


def _cell(item) -> PlayCellOut:
    return PlayCellOut(
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
            )
            for p in plan.periods
        ],
    )
