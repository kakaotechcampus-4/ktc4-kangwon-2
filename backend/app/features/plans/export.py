"""계획안 내보내기 — `GET /api/plans/{id}/export/hwp` (docs/api-spec.md §9).

기본은 hwpx 다. `?format=hwp` 면 그 hwpx 를 `.hwp` 로 바꿔 준다(`shared/hwpx.py`, ADR-039).

**확정본만 내보낸다.** 내보낸 파일은 제출 문서다. DRAFT 를 내보낼 수 있으면 교사가
확인하지 않은 초안이 그대로 제출되는 길이 생긴다. 확정 전 내용은 화면에서 본다.

**출처를 싣지 않는다.** evidence · generation 은 화면에서 근거를 보여주는 값이다.
제출 문서에 섞이면 안 된다 — 여기서는 교사가 읽는 글자만 꺼낸다.
"""

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from lxml import etree
from ssuksak.planning import PlanId
from ssuksak.planning.domain.play_project_plan import PLAY_PROJECT_FORMAT

from app.features.plans.annual_hwpx import AnnualMonthRows, fill_annual_v1
from app.features.plans.monthly_router import _current as _monthly_detail
from app.features.plans.monthly_router import _monthly_repo
from app.features.plans.monthly_router import _own_row as _monthly_row
from app.features.plans.monthly_schemas import SectionOut
from app.features.plans.play_monthly_hwpx import _set_paragraph, _text
from app.features.plans.play_project import format_of
from app.features.plans.play_project_hwpx import (
    PlayPeriodRows,
    PlayRow,
    _preview,
    fill_play_project,
)
from app.features.plans.router import DbSession, _detail, _play_plan, _repo, _row
from app.features.plans.weekly_router import _current as _weekly_detail
from app.features.plans.weekly_router import _own_row as _weekly_row
from app.features.plans.weekly_router import _weekly_repo
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.hwpx import (
    NS,
    PACKAGE,
    PREVIEW,
    SECTION,
    Format,
    TemplateMismatch,
    _cells,
    _dump,
    _package,
    _set_text,
    download,
    fill_grid,
)

router = APIRouter(prefix="/plans", tags=["plans"])

TEMPLATE_DIR = Path(__file__).parent / "templates"

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
    rows = [AnnualMonthRows(month.month, month.theme, month.sub_themes) for month in plan.months]
    content = fill_annual_v1(
        (TEMPLATE_DIR / "annual_v1_weeks.hwpx").read_bytes(), title, plan.school_year, rows
    )
    return download(content, f"plan-{row.id}", title, format)


# ── 월간 (§9-1) ───────────────────────────────────────────────────────────

# 한 쪽 양식(2026-10-31 결정). 4주 · 5주 달은 주차 칸 폭이 달라 파일을 따로 둔다. 둘 다 한글
# 2024 에서 빈 양식 1/1쪽을 확인한 전달본 그대로다.
MONTHLY_TEMPLATES = {4: "monthly_v1_4weeks.hwpx", 5: "monthly_v1_5weeks.hwpx"}
MONTHLY_PERIOD_CELL = (2, 1)
# 한 달에 하나인 Section → 칸, 주마다 있는 Section → 줄. 주차 칸의 열은 주차 머리 줄에서 읽는다 —
# 4주 · 5주 양식의 열 주소가 다르다.
# 소방대피/재난대비는 주 칸 없이 한 칸(12행, 12열 합침)이다.
MONTHLY_MONTH_CELLS = {"theme": (1, 1), "goals": (3, 1), "drill": (12, 1)}
MONTHLY_WEEK_ROWS = {
    "focus": 7,
    "outdoor_play": 8,
    "indoor_alternative": 9,
    "basic_habit": 10,
    "safety_education": 11,
}
MONTHLY_WEEK_HEADER = 6
# 양식에 자리가 있는지 채우기 전에 본다 — 다른 파일이 들어오면 엉뚱한 줄에 쓰지 않는다.
MONTHLY_LABELS = {
    (1, 0): "놀이 주제",
    (2, 0): "예상 기간",
    (3, 0): "이번 달 목표",
    (7, 0): "소주제",
    (8, 0): "바깥놀이",
    (9, 0): "실내 대체활동",
    (10, 0): "기본생활습관",
    (11, 0): "안전교육",
    (12, 0): "소방대피/재난대비",
}

_UNSUPPORTED_WEEKS = HTTPException(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={
        "code": "VALIDATION_FAILED",
        "message": "양식은 4주 · 5주인 달만 담습니다.",
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

    줄은 양식에 박혀 있다. 원이 켜지 않은 Section(목표 · 기본생활습관 · 실내 대체활동)과
    아직 계획안이 만들지 않는 줄(행사 · 시간표)은 빈칸이다 — 교사가 한글에서 적는다.
    소방대피/재난대비 줄은 훈련 칸이 있는 계획만 채운다(없으면 빈칸).
    양식에 자리가 없는 Section 이 오면 버리지 않고 멈춘다.
    """
    row = _monthly_row(session, user, plan_id)
    if row.status != "CONFIRMED":
        raise _NOT_CONFIRMED
    plan = _monthly_detail(session, user, plan_id)
    klass = require_own_class(session, user, plan.class_id)

    weeks = [week for week in plan.weeks if week.active]
    if len(weeks) not in MONTHLY_TEMPLATES:
        raise _UNSUPPORTED_WEEKS
    texts = {MONTHLY_PERIOD_CELL: f"{weeks[0].start_date} ~ {weeks[-1].end_date}"}
    rows: dict[int, list[str]] = {}
    for section in plan.sections:
        if not section.visible or section.role != "CONTENT":
            continue
        if section.section_key in MONTHLY_MONTH_CELLS:
            texts[MONTHLY_MONTH_CELLS[section.section_key]] = _month_value(section)
        elif section.section_key in MONTHLY_WEEK_ROWS:
            values = {cell.week_id: cell.value for cell in section.cells}
            if section.section_key == "safety_education" and plan.safety_weeks:
                # 후보 모드는 칸을 비워 두고 표시값을 응답마다 계산한다(ADR-052). 미배치 주는 빈칸.
                values = {week.week_id: week.display_value for week in plan.safety_weeks}
            rows[MONTHLY_WEEK_ROWS[section.section_key]] = [
                values.get(week.week_id, "") for week in weeks
            ]
        else:
            raise TemplateMismatch(f"월간 양식에 {section.section_key} 줄이 없다.")

    # 연령은 만들 때 계획안에 굳은 값이다 — 반 설정이 뒤에 바뀌어도 제출 문서는 그대로다.
    ages = _monthly_repo(session, user.center_id).get(PlanId(row.plan_ref)).target_ages
    title = f"{klass.name} {plan.target_month} 놀이계획안"
    content = _fill_monthly(
        (TEMPLATE_DIR / MONTHLY_TEMPLATES[len(weeks)]).read_bytes(),
        title,
        (f"{plan.month}월 놀이계획안", f"{_ages_label(ages)} {klass.name}"),
        texts,
        rows,
    )
    return download(content, f"monthly-plan-{row.id}", title, format)


def _fill_monthly(
    template: bytes,
    title: str,
    heading: tuple[str, str],
    texts: dict[tuple[int, int], str],
    rows: dict[int, list[str]],
) -> bytes:
    """제목 칸(0,0)의 두 문단, `texts` 의 칸, `rows` 의 주차 줄(주마다 한 칸)을 채운다.

    제목이 표 안에 있어 `fill_grid`(표 밖 「제목」 자리)를 못 쓴다.
    """
    with zipfile.ZipFile(io.BytesIO(template)) as src:
        infos = src.infolist()
        parts = {info.filename: src.read(info.filename) for info in infos}

    section = etree.fromstring(parts[SECTION])
    cells = _cells(section.find(".//hp:tbl", NS))
    for address, label in MONTHLY_LABELS.items():
        if address not in cells or _text(cells[address]) != label:
            raise TemplateMismatch(f"양식 {address} 칸이 「{label}」 이 아니다.")
    paragraphs = cells[(0, 0)].findall("hp:subList/hp:p", NS)
    if len(paragraphs) != 2:
        raise TemplateMismatch("제목 칸은 제목 · 반 표시 두 문단이어야 한다.")
    for p, text in zip(paragraphs, heading, strict=True):
        _set_paragraph(p, text)
    for address, text in texts.items():
        _set_text(cells[address], text)
    columns = sorted(col for row, col in cells if row == MONTHLY_WEEK_HEADER and col > 0)
    for line, values in rows.items():
        if len(values) != len(columns):
            raise TemplateMismatch(f"양식 주차 칸은 {len(columns)}개인데 {len(values)}주다.")
        for col, text in zip(columns, values, strict=True):
            _set_text(cells[(line, col)], text)

    parts[SECTION] = _dump(section)
    parts[PACKAGE] = _package(parts[PACKAGE], title)
    if PREVIEW in parts:
        parts[PREVIEW] = _preview(section)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in infos:
            dst.writestr(info, parts[info.filename], compress_type=info.compress_type)
    return out.getvalue()


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
