"""문서 내보내기 — `GET /api/documents/{id}/export/hwp` (docs/api-spec.md §11 「내보내기」).

§9 계획안 내보내기와 같은 규칙이다. 확정본만 · 출처를 싣지 않는다 · 기본은 hwpx 이고
`?format=hwp` 면 `.hwp` 로 바꿔 준다(`shared/hwpx.py`, ADR-039).

**3층을 종이에서 합친다(ADR-024).** 화면과 검사에서는 사실 · 해석 · 지원이 나뉘어 있지만
실물 양식에는 해석 칸과 지원 칸이 따로 없다. 꼬리 칸 하나에 해석, 빈 줄, 지원 순서로 잇는다.

**근거가 바뀐(`stale`) 문서는 내보내지 않는다.** 일과 기록의 시간 · 일과 이름 · 활동계획은
원본에서 읽는다. 근거가 바뀐 채로 내보내면 교사가 확정한 것과 다른 종이가 나간다.
관찰 기록의 영역 · 상황과 영역 축은 문서가 만들 때 찍은 사본에서 읽는다(ADR-088). 사본이 없는
옛 문서만 예전처럼 원본 영역과 원의 지금 축을 읽는다.
"""

import io
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response, status
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
    document_axis,
)
from app.features.observations.models import AXES
from app.features.routines.models import RoutineRecord
from app.features.routines.weather import day_weather
from app.shared.auth.dependency import CurrentUser
from app.shared.hwpx import Format, download, fill_grid, fill_table

router = APIRouter(prefix="/documents", tags=["documents"])

TEMPLATE_DIR = Path(__file__).parent / "templates"

# 관찰일지 양식의 머리행(영역 · 관찰내용) 줄 수. 그 아래가 5영역 · 평가 순서다.
OBSERVATION_HEADER_ROWS = 1
# 일일 보육일지 양식의 머리행(시간 · 일과 · 활동계획 · 활동실행) 줄 수.
# 그 아래가 일과 원형 한 줄, 꼬리 한 줄이다.
DAILY_LOG_HEADER_ROWS = 1
# 일일 보육일지 양식 제목 아래 머리 줄의 자리 글자 (scripts/build_journal_templates.py).
DAILY_HEAD_PLACEHOLDER = "날짜 · 날씨"
# 주간 보육일지 양식의 머리행(날짜 · 그날의 놀이와 일과) 줄 수.
WEEKLY_LOG_HEADER_ROWS = 1
WEEKDAYS = "월화수목금토일"
# 일일 보육일지 사실 한 줄의 머리 — `[오전 실내놀이 09:20~10:40]`. 시간은 떼고 이름만 남긴다.
_ROUTINE_HEAD = re.compile(r"^\[(.+?)(?:\s\d{1,2}:\d{2}~\d{1,2}:\d{2})?\]")


def _blocked(doc: Document) -> HTTPException | None:
    """내보낼 수 없는 문서면 그 이유. 한 장 받기와 묶음 받기가 같은 규칙을 쓴다."""
    if doc.kind not in ("observation", "dailyLog", "weeklyLog"):
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "관찰일지와 보육일지만 내보낼 수 있습니다.",
            ["kind"],
        )
    if doc.origin == "IMPORT":
        # 올린 원문에는 해석 · 지원 칸이 없어 양식을 채울 수 없다. 원래 파일이 교사에게 있다.
        return _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "올린 원문은 한글 파일로 다시 만들지 않습니다. 원래 파일을 써 주세요.",
            ["origin"],
        )
    if doc.status != "CONFIRMED":
        return _error(
            status.HTTP_409_CONFLICT, "GATE_BLOCKED", "확정된 문서만 내보낼 수 있습니다.", []
        )
    if doc.stale:
        return _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "근거 기록이 바뀌었습니다. 확정을 취소하고 다시 불러와 주세요.",
            ["stale"],
        )
    return None


def _content(session: Session, doc: Document) -> bytes:
    sources = _sources(session, doc.id)
    evaluation = _evaluation(session, doc)
    if doc.kind == "observation":
        return _observation(session, doc, sources, evaluation)
    if doc.kind == "weeklyLog":
        return _weekly_log(session, doc, sources, evaluation)
    return _daily_log(session, doc, sources, evaluation)


@router.get("/{document_id}/export/hwp")
def export_document(
    document_id: int, session: DbSession, user: CurrentUser, format: Format = "hwpx"
) -> Response:
    doc = _own_document(session, user, document_id, read_only=True)
    if (error := _blocked(doc)) is not None:
        raise error
    return download(_content(session, doc), f"document-{doc.id}", doc.title, format)


@router.get("/export/bundle")
def export_bundle(
    session: DbSession, user: CurrentUser, ids: Annotated[list[int], Query(min_length=1)]
) -> Response:
    """확정본 여러 장을 zip 하나로 (ADR-083). 안의 파일은 한 장씩 받을 때와 같은 hwpx 다.

    **한 장이라도 못 내보내면 통째로 거절한다.** 몇 장이 빠졌는지 모르는 묶음을 내면 안 된다.
    화면이 확정 · 근거 그대로인 문서만 골라 보내고 「n명은 빠졌어요」를 따로 알린다.
    hwpx 여러 장을 한 파일로 잇지 않는다 — 양식을 다시 짜야 해서 성진님 몫이다.
    """
    docs = [_own_document(session, user, i, read_only=True) for i in dict.fromkeys(ids)]
    if blocked := [f"ids.{d.id}" for d in docs if _blocked(d) is not None]:
        raise _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "확정했고 근거가 그대로인 문서만 묶어 받을 수 있어요.",
            blocked,
        )
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for doc in docs:
            name, n = f"{doc.title}.hwpx", 1
            while name in used:
                n += 1
                name = f"{doc.title} ({n}).hwpx"
            used.add(name)
            bundle.writestr(name, _content(session, doc))
    disposition = (
        f"attachment; filename=\"documents.zip\"; filename*=UTF-8''{quote('일지 묶음.zip')}"
    )
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


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
# 맨 아래 한 칸의 이름. 교사가 쓴 관찰일지를 그대로 따른다
# (`docs/references/관찰일지-서술-기준.md` — 5영역 A02 는 「종합해석」, 2축 S05 는 「총평」).
AXIS_TAIL = {"NURI_5": "종합해석", "DAILY_PLAY_2": "총평"}


def _observation(
    session: Session, doc: Document, sources: list[DocumentSource], evaluation: str
) -> bytes:
    """영역 행에 근거 관찰 기록을, 「평가」 칸에 해석 + 지원을 넣는다.

    행은 **문서를 만들 때의 축**이다 (observations/models.py AXES · ADR-088). 5영역은 5줄,
    일상생활 · 놀이활동은 2줄짜리 양식으로 나간다. 원이 나중에 축을 바꿔도 이 문서 종이는 그대로다.
    관찰 칸 한 줄은 `(9/5) (바깥놀이) 사실` 이다. 상황이 비었으면 괄호를 붙이지 않는다.
    """
    domains = _observation_domains(session, sources)
    _missing([f"sources.{s.source_id}" for s in sources if s.source_id not in domains])

    axis = document_axis(session, doc)
    names = AXES[axis]

    # 영역 안에서는 날짜순이다. 같은 날이면 교사가 고른 순서를 지킨다(sorted 는 안정 정렬).
    by_domain: dict[str, list[str]] = {domain: [] for domain in names}
    for source in sorted(sources, key=lambda s: s.date):
        domain = domains[source.source_id]
        # 축 사본이 없는 옛 문서에서, 원이 축을 바꾸기 전에 쓴 기록이다. 지금 양식에 그 줄이
        # 없으니 내보낼 수 없다 — 조용히 버리면 교사가 고른 근거가 종이에서 사라진다.
        if domain not in by_domain:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDATION_FAILED",
                f"「{domain}」은 지금 원이 쓰는 관찰 영역이 아니라 양식에 넣을 줄이 없습니다.",
                [f"sources.{source.source_id}"],
            )
        situation = f"({source.context}) " if source.context else ""
        by_domain[domain].append(
            f"({source.date.month}/{source.date.day}) {situation}{source.text}"
        )
    rows = [[domain, "\n".join(lines)] for domain, lines in by_domain.items()]
    rows.append([AXIS_TAIL[axis], evaluation])
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
    # 옛 일일 보육일지는 관찰 기록을 근거로 만들었다(ADR-024). 그 번호는 일과 번호가 아니다 —
    # 일과 테이블에서 찾으면 번호가 우연히 같은 다른 반 · 다른 원의 일과가 종이에 찍힌다.
    # 일과 줄을 채울 원본이 없으니 내보내지 않는다. 재확정 · refresh 도 같은 문서를 막는다.
    if any(s.source_kind != "routine" for s in sources):
        raise _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "관찰 기록으로 만든 예전 일일 보육일지는 한글 파일로 내보낼 수 없습니다. "
            "일과 기록으로 새로 만들어주세요.",
            ["source_kind"],
        )
    ids = [s.source_id for s in sources]
    # 일과 기록 화면과 같은 순서다 — 종이의 행 순서다(routines/router.py).
    # 이 문서의 반 · 그날 일과만 읽는다. 만들 때와 같은 조건이다(router.py 일일 근거 검사).
    routines = session.scalars(
        select(RoutineRecord)
        .where(
            RoutineRecord.id.in_(ids),
            RoutineRecord.class_id == doc.class_id,
            RoutineRecord.date == doc.start_date,
        )
        .order_by(
            RoutineRecord.position,
            RoutineRecord.start_time.asc().nulls_last(),
            RoutineRecord.id,
        )
    ).all()
    found = {r.id for r in routines}
    _missing([f"sources.{i}" for i in ids if i not in found])

    # 어제 지원을 반영한 줄은 원이 고른 표기를 앞에 붙인다. 표시는 사실 글에 없다 (ADR-085).
    mark = session.scalar(
        select(Center.reflect_mark)
        .where(Center.id == Class.center_id)
        .where(Class.id == doc.class_id)
    )
    rows = [[r.time_range(), r.name.strip(), r.plan.strip(), _executed(r, mark)] for r in routines]
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
        lines={DAILY_HEAD_PLACEHOLDER: _daily_head(session, doc)},
    )


def _executed(record: RoutineRecord, mark: str | None) -> str:
    text = record.execution.strip()
    return f"{mark} {text}" if record.reflected and mark else text


def _daily_head(session: Session, doc: Document) -> str:
    """제목 아래 머리 줄 — `날짜 : 2026년 9월 22일 (화)      날씨 : 맑음` (ADR-089).

    날씨는 확정 때 박은 값이다(교사가 고른 값, 없으면 자동 값).
    없으면 「날씨 :」 뒤를 비워 손으로 적게 둔다.
    미세먼지는 싣지 않는다 — 실물 양식에 칸이 없다.
    """
    day = doc.start_date
    # 확정 때 박은 값이 먼저다. 그 칸이 생기기 전에 확정한 옛 문서(NULL)만 지금 값을 읽는다.
    sky = doc.weather if doc.weather is not None else day_weather(session, doc.class_id, day).sky
    sky = sky or ""
    return (
        f"날짜 : {day.year}년 {day.month}월 {day.day}일 ({WEEKDAYS[day.weekday()]})"
        f"{' ' * 6}날씨 : {sky}"
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
    if any(s.source_kind == "routine" for s in sources):
        return _weekly_log_from_routines(session, doc, sources, evaluation)

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
    # 일일 일지마다 근거로 쓴 일과 기록 — 교사가 맞다고 한 활동 이름을 읽는다.
    routine_ids: dict[int, list[int]] = {}
    for document_id, routine_id in session.execute(
        select(DocumentSource.document_id, DocumentSource.source_id).where(
            DocumentSource.document_id.in_(dailies), DocumentSource.source_kind == "routine"
        )
    ):
        routine_ids.setdefault(document_id, []).append(routine_id)
    played = _activities(session, [i for ids in routine_ids.values() for i in ids])
    rows = []
    for copy in sorted(sources, key=lambda s: s.date):
        daily = dailies[copy.source_id]
        rows.append(
            [
                f"{copy.date.month}/{copy.date.day}({WEEKDAYS[copy.date.weekday()]})",
                _our_plays(copy.text, routine_ids.get(daily.id, []), played),
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


def _weekly_log_from_routines(
    session: Session, doc: Document, sources: list[DocumentSource], evaluation: str
) -> bytes:
    """일일 보육일지를 쓰지 않는 원의 주간. 일과 기록을 날짜로 묶어 한 줄씩 담는다.

    **날짜별 「놀이 이해 및 분석」 · 「앞으로의 지원방향」은 비워서 내보낸다.** 그 칸은 하루치
    해석과 지원인데, 이 문서에는 한 주를 통째로 본 해석 · 지원 하나뿐이다. 그것은 꼬리
    「주간 총평」에 들어간다. 지어내서 채우면 교사가 쓰지 않은 말이 종이에 찍힌다.
    """
    played = _activities(session, [s.source_id for s in sources])
    by_date: dict[date, list[DocumentSource]] = {}
    for source in sources:
        by_date.setdefault(source.date, []).append(source)
    rows = [
        [
            f"{day.month}/{day.day}({WEEKDAYS[day.weekday()]})",
            _our_plays("\n".join(s.text for s in copies), [s.source_id for s in copies], played),
            "",
            "",
            "",
        ]
        for day, copies in sorted(by_date.items())
    ]
    return fill_grid(
        (TEMPLATE_DIR / "weekly_log.hwpx").read_bytes(),
        doc.title,
        WEEKLY_LOG_HEADER_ROWS,
        rows,
        [["주간 총평", evaluation]],
    )


def _activities(session: Session, routine_ids: list[int]) -> dict[int, list[str]]:
    """일과 기록마다 교사가 계획안에서 맞다고 한 활동 이름 (ADR-085)."""
    if not routine_ids:
        return {}
    return dict(
        session.execute(
            select(RoutineRecord.id, RoutineRecord.activities).where(
                RoutineRecord.id.in_(routine_ids)
            )
        ).all()
    )


def _our_plays(fact: str, routine_ids: list[int], played: dict[int, list[str]]) -> str:
    """주간 「우리반 놀이」 칸. 교사가 맞다고 한 활동 이름이 있으면 그것, 없으면 일과 이름이다.

    일과 이름(「점심식사」)은 놀이가 아니지만, 계획안을 쓰지 않는 반은 이름 말고 적을 것이 없다.
    """
    names = list(dict.fromkeys(a for i in routine_ids for a in played.get(i, [])))
    return "\n".join(names or _routine_names(fact))


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
