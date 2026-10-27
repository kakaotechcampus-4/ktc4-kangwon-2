"""문서 내보내기 — `GET /api/documents/{id}/export/hwp` (docs/api-spec.md §11 「내보내기」).

§9 계획안 내보내기와 같은 규칙이다. 확정본만 · 출처를 싣지 않는다 · 기본은 hwpx 이고
`?format=hwp` 면 `.hwp` 로 바꿔 준다(`shared/hwpx.py`, ADR-039).

**3층을 종이에서 합친다(ADR-024).** 화면과 검사에서는 사실 · 해석 · 지원이 나뉘어 있지만
실물 양식에는 해석 칸과 지원 칸이 따로 없다. 꼬리 칸 하나에 해석, 빈 줄, 지원 순서로 잇는다.

**근거가 바뀐(`stale`) 문서는 내보내지 않는다.** 일과 기록의 시간 · 일과 이름 · 활동계획과
관찰 기록의 영역은 원본에서 읽는다. 근거가 바뀐 채로 내보내면 교사가 확정한 것과 다른 종이가 나간다.
"""

import re
from pathlib import Path

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Center, Class
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.documents.router import (
    DbSession,
    _error,
    _observation_domains,
    _own_document,
    _sources,
)
from app.features.observations.models import AXES, DEFAULT_AXIS, NURI_DOMAINS
from app.features.routines.models import RoutineRecord
from app.shared.auth.dependency import CurrentUser
from app.shared.hwpx import Format, download, fill_grid, fill_table

router = APIRouter(prefix="/documents", tags=["documents"])

TEMPLATE_DIR = Path(__file__).parent / "templates"

# 관찰일지 양식의 머리행(영역 · 관찰내용) 줄 수. 그 아래가 5영역 · 평가 순서다.
OBSERVATION_HEADER_ROWS = 1
# 일일 보육일지 양식의 머리행(시간 · 일과 · 활동계획 · 활동실행) 줄 수.
# 그 아래가 일과 원형 한 줄, 꼬리 한 줄이다.
DAILY_LOG_HEADER_ROWS = 1
# 주간 보육일지 양식의 머리행(날짜 · 그날의 놀이와 일과) 줄 수.
WEEKLY_LOG_HEADER_ROWS = 1
WEEKDAYS = "월화수목금토일"
# 일일 보육일지 사실 한 줄의 머리 — `[오전 실내놀이 09:20~10:40]`. 시간은 떼고 이름만 남긴다.
_ROUTINE_HEAD = re.compile(r"^\[(.+?)(?:\s\d{1,2}:\d{2}~\d{1,2}:\d{2})?\]")


@router.get("/{document_id}/export/hwp")
def export_document(
    document_id: int, session: DbSession, user: CurrentUser, format: Format = "hwpx"
) -> Response:
    doc = _own_document(session, user, document_id)
    if doc.kind not in ("observation", "dailyLog", "weeklyLog"):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "관찰일지와 보육일지만 내보낼 수 있습니다.",
            ["kind"],
        )
    if doc.status != "CONFIRMED":
        raise _error(
            status.HTTP_409_CONFLICT, "GATE_BLOCKED", "확정된 문서만 내보낼 수 있습니다.", []
        )
    if doc.stale:
        raise _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "근거 기록이 바뀌었습니다. 확정을 취소하고 다시 불러와 주세요.",
            ["stale"],
        )

    sources = _sources(session, doc.id)
    evaluation = _evaluation(session, doc)
    if doc.kind == "observation":
        content = _observation(session, doc, sources, evaluation)
    elif doc.kind == "weeklyLog":
        content = _weekly_log(session, doc, sources, evaluation)
    else:
        content = _daily_log(session, doc, sources, evaluation)
    return download(content, f"document-{doc.id}", doc.title, format)


# 꼬리 칸 하나에 해석 + 지원이 함께 들어간다. 종이에서 둘을 가르는 머리말은
# 문서마다 다르다 — 일일 보육일지의 칸 이름은 「놀이 평가 및 다음날 지원계획」이고
# 관찰일지는 「평가」다. 칸 이름과 어긋나는 머리말을 쓰면 교사가 제출할 때 고쳐야 한다.
_EVAL_HEADINGS = {
    "observation": ("배움", "지원"),
    "dailyLog": ("놀이 평가", "다음날 지원계획"),
    "weeklyLog": ("놀이 평가", "다음 주 지원계획"),
}


def _evaluation(session: Session, doc: Document) -> str:
    """꼬리 칸 하나에 들어갈 해석 + 지원. 공식 작성 사례처럼 머리말로 나눈다.

    한 칸에 둘을 이어 붙이면 어디까지가 평가이고 어디부터가 계획인지 종이에서 안 보인다.
    중앙육아종합지원센터 공식 작성 사례가 `▸ 놀이상황)` · `▸ 놀이지원)` 로 가르는 자리다
    (docs/references/보육일지-공식양식.md).
    """
    bodies = dict(
        session.execute(
            select(DocumentSection.heading, DocumentSection.body).where(
                DocumentSection.document_id == doc.id
            )
        ).all()
    )
    first, second = _EVAL_HEADINGS.get(doc.kind, ("해석", "지원"))
    return f"▸ {first}) {bodies['해석']}\n\n▸ {second}) {bodies['지원']}"


def _missing(fields: list[str]) -> None:
    # 원본이 없으면 어느 행에 어떻게 넣을지 정할 수 없다. 빼고 내보내면 교사가 고른 사실이
    # 제출 문서에서 조용히 사라진다.
    if fields:
        raise _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "근거 기록이 사라졌습니다. 확정을 취소하고 문서를 새로 만들어주세요.",
            fields,
        )


# 축마다 양식이 다르다. 줄 수가 달라서 한 양식으로는 `fill_table` 이 거절한다
# (`shared/hwpx.py` — 양식 표 줄 수와 채울 줄 수가 같아야 한다).
AXIS_TEMPLATE = {"NURI_5": "observation.hwpx", "DAILY_PLAY_2": "observation_daily_play.hwpx"}


def _observation(
    session: Session, doc: Document, sources: list[DocumentSource], evaluation: str
) -> bytes:
    """영역 행에 근거 관찰 기록을, 「평가」 칸에 해석 + 지원을 넣는다.

    행은 **그 원이 쓰는 축**이다 (observations/models.py AXES). 5영역 원은 5줄,
    일상생활 · 놀이활동을 쓰는 원은 2줄짜리 양식으로 나간다.
    """
    domains = _observation_domains(session, sources)
    _missing([f"sources.{s.source_id}" for s in sources if s.source_id not in domains])

    classroom = session.get(Class, doc.class_id)
    center = session.get(Center, classroom.center_id) if classroom else None
    axis = center.observation_axis if center else DEFAULT_AXIS
    names = AXES.get(axis, NURI_DOMAINS)

    # 영역 안에서는 날짜순이다. 같은 날이면 교사가 고른 순서를 지킨다(sorted 는 안정 정렬).
    by_domain: dict[str, list[str]] = {domain: [] for domain in names}
    for source in sorted(sources, key=lambda s: s.date):
        domain = domains[source.source_id]
        # 원이 축을 바꾸기 전에 쓴 기록이다. 지금 양식에 그 줄이 없으니 내보낼 수 없다 —
        # 조용히 버리면 교사가 고른 근거가 종이에서 사라진다.
        if domain not in by_domain:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDATION_FAILED",
                f"「{domain}」은 지금 원이 쓰는 관찰 영역이 아니라 양식에 넣을 줄이 없습니다.",
                [f"sources.{source.source_id}"],
            )
        by_domain[domain].append(f"({source.date.month}/{source.date.day}) {source.text}")
    rows = [[domain, "\n".join(lines)] for domain, lines in by_domain.items()]
    rows.append(["평가", evaluation])
    return fill_table(
        (TEMPLATE_DIR / AXIS_TEMPLATE[axis]).read_bytes(),
        doc.title,
        OBSERVATION_HEADER_ROWS,
        rows,
    )


def _daily_log(
    session: Session, doc: Document, sources: list[DocumentSource], evaluation: str
) -> bytes:
    """일과 기록마다 한 줄씩, 꼬리 칸에 해석 + 지원을 넣는다. 줄 수는 그날 일과 수다."""
    ids = [s.source_id for s in sources]
    # 일과 기록 화면과 같은 순서다 — 종이의 행 순서다(routines/router.py).
    routines = session.scalars(
        select(RoutineRecord)
        .where(RoutineRecord.id.in_(ids))
        .order_by(
            RoutineRecord.position,
            RoutineRecord.start_time.asc().nulls_last(),
            RoutineRecord.id,
        )
    ).all()
    found = {r.id for r in routines}
    _missing([f"sources.{i}" for i in ids if i not in found])

    rows = [[r.time_range(), r.name.strip(), r.plan.strip(), r.execution.strip()] for r in routines]
    return fill_grid(
        (TEMPLATE_DIR / "daily_log.hwpx").read_bytes(),
        doc.title,
        DAILY_LOG_HEADER_ROWS,
        rows,
        [
            ["놀이 평가 및 다음날 지원계획", evaluation],
            # 공식 양식 5종 전부에 있는 칸이다. 교사가 안 적었으면 빈 칸으로 나간다 —
            # 종이에서 칸 자체가 사라지면 제출할 때 손으로 그려 넣어야 한다.
            ["반 운영 특이사항", doc.class_note.strip()],
        ],
    )


def _weekly_log(
    session: Session, doc: Document, sources: list[DocumentSource], evaluation: str
) -> bytes:
    """확정한 일일 보육일지마다 한 줄씩. 꼬리는 주간 총평이다.

    칸은 현장 실물(멘토 제공 2025 주간 보육일지)과 같다 —
    `날짜 | 우리반 놀이 | 놀이 이해 및 분석 | 앞으로의 지원방향 | 반 운영 특이사항`.
    가운데 셋이 우리 3층(사실 · 해석 · 지원)과 그대로 맞는다.

    **「우리반 놀이」는 그날 일과 이름만 적는다.** 활동실행까지 넣으면 한 줄이 종이 한 장이
    된다. 실물도 놀이 이름을 늘어놓고, 무슨 일이 있었는지는 분석 칸에서 읽는다.
    """
    dailies = {
        d.id: d
        for d in session.scalars(
            select(Document).where(Document.id.in_([s.source_id for s in sources]))
        )
    }
    _missing([f"sources.{s.source_id}" for s in sources if s.source_id not in dailies])

    bodies = {
        (row.document_id, row.heading): row.body
        for row in session.execute(
            select(DocumentSection.document_id, DocumentSection.heading, DocumentSection.body)
            .where(DocumentSection.document_id.in_(dailies))
            .where(DocumentSection.heading.in_(("해석", "지원")))
        ).all()
    }
    rows = []
    for copy in sorted(sources, key=lambda s: s.date):
        daily = dailies[copy.source_id]
        rows.append(
            [
                f"{copy.date.month}/{copy.date.day}({WEEKDAYS[copy.date.weekday()]})",
                "\n".join(_routine_names(copy.text)),
                bodies.get((daily.id, "해석"), ""),
                bodies.get((daily.id, "지원"), ""),
                daily.class_note.strip(),
            ]
        )
    return fill_grid(
        (TEMPLATE_DIR / "weekly_log.hwpx").read_bytes(),
        doc.title,
        WEEKLY_LOG_HEADER_ROWS,
        rows,
        [["주간 총평", evaluation]],
    )


def _routine_names(fact: str) -> list[str]:
    """일일 보육일지의 사실에서 일과 이름만 뽑는다.

    사실 한 줄은 `[오전 실내놀이 09:20~10:40] 활동실행` 이다
    (`routines/models.py` `fact_text`). 대괄호 안에서 시간을 떼면 일과 이름이 남는다.
    """
    names = []
    for line in fact.splitlines():
        head = _ROUTINE_HEAD.match(line.strip())
        if head:
            names.append(head.group(1).strip())
    return names
