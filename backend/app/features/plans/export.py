"""계획안 내보내기 — `GET /api/plans/{id}/export/hwp` (docs/api-spec.md §9).

기본은 hwpx 다. `?format=hwp` 면 그 hwpx 를 `.hwp` 로 바꿔 준다(`shared/hwpx.py`, ADR-039).

**확정본만 내보낸다.** 내보낸 파일은 제출 문서다. DRAFT 를 내보낼 수 있으면 교사가
확인하지 않은 초안이 그대로 제출되는 길이 생긴다. 확정 전 내용은 화면에서 본다.

**출처를 싣지 않는다.** evidence · generation 은 화면에서 근거를 보여주는 값이다.
제출 문서에 섞이면 안 된다 — 여기서는 교사가 읽는 글자만 꺼낸다.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from ssuksak.planning import PlanId
from ssuksak.planning.domain.play_project_plan import PLAY_PROJECT_FORMAT

from app.features.plans.monthly_router import _current as _monthly_detail
from app.features.plans.monthly_router import _own_row as _monthly_row
from app.features.plans.monthly_schemas import SectionOut
from app.features.plans.play_project import format_of
from app.features.plans.play_project_hwpx import PlayPeriodRows, PlayRow, fill_play_project
from app.features.plans.router import DbSession, _detail, _play_plan, _repo, _row
from app.features.plans.weekly_router import _current as _weekly_detail
from app.features.plans.weekly_router import _own_row as _weekly_row
from app.features.plans.weekly_router import _weekly_repo
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.hwpx import Format, download, fill_grid, fill_table

router = APIRouter(prefix="/plans", tags=["plans"])

TEMPLATE_DIR = Path(__file__).parent / "templates"

# 양식의 머리행(월 · 주제 · 소주제) 줄 수.
# 안전교육 열은 2026-10-22 결정으로 양식에서 뺐다 — 안전교육은 월간이 채운다. 교사 입력값
# (ADR-041)은 API · DB 에 그대로 있고 제출 문서에만 싣지 않는다. 다시 켜려면 git 이력의
# 4열 양식과 이 줄 만들기를 되살린다.
ANNUAL_HEADER_ROWS = 1

_NOT_CONFIRMED = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "GATE_BLOCKED",
        "message": "확정된 계획안만 내보낼 수 있습니다.",
        "fields": [],
    },
)

_PLAY_NOT_CONFIRMED = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "GATE_BLOCKED",
        "message": "놀이 프로젝트형 연간계획안은 확정한 뒤 내려받을 수 있습니다.",
        "fields": [],
    },
)

# 양식 시기 칸(두 줄: 기간 · 계절). 구간 키는 Core layout 의 period.key 다.
PLAY_PERIOD_LABELS = {
    "m03_m05": "3~5월\n봄",
    "m06_m08": "6~8월\n여름",
    "m09_m11": "9~11월\n가을",
    "m12_m02": "12~2월\n겨울",
}


def _learning(value: str) -> list[tuple[str, str, str]]:
    """배움 칸 글(`영역 - 범주 - 내용` 줄들)을 세 조각으로. 영역 · 범주 이름에 「 - 」가 없다."""
    lines = []
    for line in value.splitlines():
        parts = line.split(" - ", 2)
        if len(parts) != 3:
            # 서버가 만든 칸이라 정상이면 늘 세 조각이다. 아니면 데이터가 깨진 것이라 500 이다.
            raise ValueError(f"배움 줄이 세 조각이 아니다: {line!r}")
        lines.append((parts[0], parts[1], parts[2]))
    return lines


def _export_play_project(session, user, row, format: Format) -> Response:
    plan = _play_plan(session, user, row)
    klass = require_own_class(session, user, int(plan.classroom_ref))
    periods = []
    for p in plan.periods:
        by_key = {c.row_key: c for c in p.candidates}
        rows = [
            PlayRow(
                c.play_name.value,
                c.materials.value,
                c.support_direction.value,
                _learning(c.learning.value),
            )
            for c in (by_key[key] for key in p.selected)
        ]
        periods.append(PlayPeriodRows(PLAY_PERIOD_LABELS[p.period.key], rows))
    title = f"{plan.school_year} 연간놀이계획안 - {klass.name}"
    content = fill_play_project(
        (TEMPLATE_DIR / "play_project_annual.hwpx").read_bytes(), title, periods
    )
    return download(content, f"plan-{row.id}", title, format)


@router.get("/{plan_id}/export/hwp")
def export_plan(
    plan_id: int, session: DbSession, user: CurrentUser, format: Format = "hwpx"
) -> Response:
    """확정된 연간계획안을 내보낸다. 월간은 아래 별도 경로를 쓴다."""
    row = _row(session, user, plan_id)
    if format_of(row) == PLAY_PROJECT_FORMAT:
        if row.status != "CONFIRMED":
            raise _PLAY_NOT_CONFIRMED
        return _export_play_project(session, user, row, format)
    if row.status != "CONFIRMED":
        raise _NOT_CONFIRMED
    plan = _detail(row, _repo(session, user).get(PlanId(row.plan_ref)))
    klass = require_own_class(session, user, plan.class_id)

    title = f"{klass.name} {plan.school_year}학년도 연간 보육계획안"
    rows = [[f"{month.month}월", month.theme, "\n".join(month.sub_themes)] for month in plan.months]
    content = fill_table(
        (TEMPLATE_DIR / "annual.hwpx").read_bytes(), title, ANNUAL_HEADER_ROWS, rows
    )
    return download(content, f"plan-{row.id}", title, format)


# ── 월간 (§9-1) ───────────────────────────────────────────────────────────

# 양식 머리행 줄 수. 그 아래 한 줄이 본문 원형이고, 꼬리 두 줄이 「우리반 안내 사항」이다.
MONTHLY_HEADER_ROWS = 7

# 머리행에서 채우는 칸의 (행, 열).
THEME_CELL = (0, 1)
PERIOD_CELL = (1, 1)
REASON_CELL = (2, 1)
WEEK_ROW = 6

# 양식의 주차 칸 수. 한 달은 많아야 다섯 주다.
MONTHLY_WEEKS = 5

_TOO_MANY_WEEKS = HTTPException(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={
        "code": "VALIDATION_FAILED",
        "message": f"양식은 {MONTHLY_WEEKS}주까지 담습니다.",
        "fields": [],
    },
)


def _month_value(section: SectionOut) -> str:
    """한 달에 하나인 Section 의 값. 주마다 있는 Section 에는 쓰지 않는다."""
    return "\n".join(cell.value for cell in section.cells if cell.value)


@router.get("/monthly/{plan_id}/export/hwp")
def export_monthly_plan(
    plan_id: int, session: DbSession, user: CurrentUser, format: Format = "hwpx"
) -> Response:
    """월간계획안을 hwpx 로 내려준다. 연간과 같이 확정본만, 출처는 빼고 내보낸다.

    **행 이름을 양식에 박아두지 않는다.** 주마다 값이 있는 Section 이 몇 개인지는 원이 고른
    TemplateProfile 이 정한다 — 안전교육 · 바깥놀이는 어디나 있고 기본생활습관 · 소방대피는
    고르는 원만 있다. 양식의 본문 한 줄을 그 수만큼 복제해서 채운다.
    """
    row = _monthly_row(session, user, plan_id)
    if row.status != "CONFIRMED":
        raise _NOT_CONFIRMED
    plan = _monthly_detail(session, user, plan_id)
    klass = require_own_class(session, user, plan.class_id)

    weeks = [week for week in plan.weeks if week.active]
    if len(weeks) > MONTHLY_WEEKS:
        raise _TOO_MANY_WEEKS
    sections = sorted(
        (s for s in plan.sections if s.visible and s.role == "CONTENT"),
        key=lambda s: s.order,
    )
    monthly = [s for s in sections if s.repeat_by != "WEEK"]
    weekly = [s for s in sections if s.repeat_by == "WEEK"]

    # 주마다 있는 Section 하나가 본문 한 줄이다. 그 달에 없는 주 칸은 빈 칸으로 남긴다.
    values = {
        (section.section_key, cell.week_id): cell.value
        for section in weekly
        for cell in section.cells
    }
    rows = [
        [section.label or section.section_key]
        + [values.get((section.section_key, week.week_id), "") for week in weeks]
        + [""] * (MONTHLY_WEEKS - len(weeks))
        for section in weekly
    ]

    theme = next((s for s in monthly if s.section_key == "theme"), None)
    # 한 달에 하나인 나머지 Section(목표 · 중점 등)은 「주제 선정 이유」 칸에 이름과 함께 담는다.
    # 어느 Section 이 오는지 원마다 달라서, 칸을 따로 두면 비는 칸이 생긴다.
    reason = "\n".join(
        f"[{section.label or section.section_key}] {_month_value(section)}"
        for section in monthly
        if section is not theme and _month_value(section)
    )

    header = {
        THEME_CELL: "" if theme is None else _month_value(theme),
        PERIOD_CELL: "" if not weeks else f"{weeks[0].start_date} ~ {weeks[-1].end_date}",
        REASON_CELL: reason,
    }
    for index in range(MONTHLY_WEEKS):
        label = weeks[index].label if index < len(weeks) else ""
        header[(WEEK_ROW, index + 1)] = label

    title = f"{klass.name} {plan.target_month} 놀이계획안"
    content = fill_grid(
        (TEMPLATE_DIR / "monthly.hwpx").read_bytes(),
        title,
        MONTHLY_HEADER_ROWS,
        rows,
        footer=[["우리반 안내 사항"], [""]],
        header=header,
    )
    return download(content, f"monthly-plan-{row.id}", title, format)


# ── 주간 (§9-6) ───────────────────────────────────────────────────────────

# 양식(`templates/weekly.hwpx`, scripts/build_weekly_template.py)의 머리 3줄:
# 반 · 기간 · 「구분 | 내용」.
WEEKLY_HEADER_ROWS = 3
WEEKLY_CLASS_CELL = (0, 1)
WEEKLY_PERIOD_CELL = (1, 1)


def _ages_label(ages) -> str:
    """「만 4세」 · 혼합 「만 3·4세」 — 반 연령 표기(ADR-038)."""
    return "만 " + "·".join(str(age) for age in sorted(ages)) + "세"


@router.get("/weekly/{plan_id}/export/hwp")
def export_weekly_plan(
    plan_id: int, session: DbSession, user: CurrentUser, format: Format = "hwpx"
) -> Response:
    """주간계획안을 hwpx 로 내려준다. 월간과 같이 확정본만, 출처는 빼고 내보낸다.

    화면은 카드형이지만 제출 문서는 기관 표 양식이다(2026-10-21 하민 결정). **행 이름을 양식에
    박아두지 않는다** — Section 하나가 본문 한 줄이고, 이름은 계획안이 들고 온 `label` 이다.
    기간은 응답의 `display_end_date` 를 쓴다 — 토요일을 켠 원이면 토요일까지다.
    """
    row = _weekly_row(session, user, plan_id)
    if row.status != "CONFIRMED":
        raise _NOT_CONFIRMED
    plan = _weekly_detail(session, user, plan_id)
    klass = require_own_class(session, user, plan.class_id)

    sections = sorted(
        (s for s in plan.sections if s.visible and s.role == "CONTENT"), key=lambda s: s.order
    )
    rows = [
        [section.label or section.section_key, "\n".join(c.value for c in section.cells if c.value)]
        for section in sections
    ]
    period = plan.week_period
    # 연령은 만들 때 계획안에 굳은 값이다 — 반 설정이 뒤에 바뀌어도 제출 문서는 그대로다.
    ages = _weekly_repo(session, user.center_id).get(PlanId(row.plan_ref)).target_ages
    header = {
        WEEKLY_CLASS_CELL: f"{klass.name} ({_ages_label(ages)})",
        WEEKLY_PERIOD_CELL: f"{period.label} · {period.start_date} ~ {plan.display_end_date}",
    }
    title = f"{klass.name} {period.label} 주간계획안"
    content = fill_grid(
        (TEMPLATE_DIR / "weekly.hwpx").read_bytes(),
        title,
        WEEKLY_HEADER_ROWS,
        rows,
        footer=[],
        header=header,
    )
    return download(content, f"weekly-plan-{row.id}", title, format)
