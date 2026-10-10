"""문서 내보내기 — `GET /api/documents/{id}/export/hwp` (docs/api-spec.md §11 「내보내기」).

§9 계획안 내보내기와 같은 규칙이다. 확정본만 · 출처를 싣지 않는다 · 경로는 `hwp` 지만
파일은 hwpx 다(`shared/hwpx.py`).

**3층을 종이에서 합친다(ADR-024).** 화면과 검사에서는 사실 · 해석 · 지원이 나뉘어 있지만
실물 양식에는 해석 칸과 지원 칸이 따로 없다. 꼬리 칸 하나에 해석, 빈 줄, 지원 순서로 잇는다.

**근거가 바뀐(`stale`) 문서는 내보내지 않는다.** 일과 기록의 시간 · 일과 이름 · 활동계획과
관찰 기록의 영역은 원본에서 읽는다. 근거가 바뀐 채로 내보내면 교사가 확정한 것과 다른 종이가 나간다.
"""

from pathlib import Path

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.documents.router import (
    DbSession,
    _error,
    _observation_domains,
    _own_document,
    _sources,
)
from app.features.observations.models import DOMAINS
from app.features.routines.models import RoutineRecord
from app.shared.auth.dependency import CurrentUser
from app.shared.hwpx import download, fill_grid, fill_table

router = APIRouter(prefix="/documents", tags=["documents"])

TEMPLATE_DIR = Path(__file__).parent / "templates"

# 관찰일지 양식의 머리행(영역 · 관찰내용) 줄 수. 그 아래가 5영역 · 평가 순서다.
OBSERVATION_HEADER_ROWS = 1
# 일일 보육일지 양식의 머리행(시간 · 일과 · 활동계획 · 활동실행) 줄 수.
# 그 아래가 일과 원형 한 줄, 꼬리 한 줄이다.
DAILY_LOG_HEADER_ROWS = 1


@router.get("/{document_id}/export/hwp")
def export_document(document_id: int, session: DbSession, user: CurrentUser) -> Response:
    doc = _own_document(session, user, document_id)
    if doc.kind not in ("observation", "dailyLog"):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "관찰일지와 일일 보육일지만 내보낼 수 있습니다.",
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
    else:
        content = _daily_log(session, doc, sources, evaluation)
    return download(content, f"document-{doc.id}", doc.title)


def _evaluation(session: Session, doc: Document) -> str:
    """꼬리 칸 하나에 들어갈 해석 + 지원. 머리말 없이 빈 줄 하나로 나눈다."""
    bodies = dict(
        session.execute(
            select(DocumentSection.heading, DocumentSection.body).where(
                DocumentSection.document_id == doc.id
            )
        ).all()
    )
    return f"{bodies['해석']}\n\n{bodies['지원']}"


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


def _observation(
    session: Session, doc: Document, sources: list[DocumentSource], evaluation: str
) -> bytes:
    """5영역 행에 근거 관찰 기록을, 「평가」 칸에 해석 + 지원을 넣는다."""
    domains = _observation_domains(session, sources)
    _missing([f"sources.{s.source_id}" for s in sources if s.source_id not in domains])

    # 영역 안에서는 날짜순이다. 같은 날이면 교사가 고른 순서를 지킨다(sorted 는 안정 정렬).
    by_domain: dict[str, list[str]] = {domain: [] for domain in DOMAINS}
    for source in sorted(sources, key=lambda s: s.date):
        by_domain[domains[source.source_id]].append(
            f"({source.date.month}/{source.date.day}) {source.text}"
        )
    rows = [[domain, "\n".join(lines)] for domain, lines in by_domain.items()]
    rows.append(["평가", evaluation])
    return fill_table(
        (TEMPLATE_DIR / "observation.hwpx").read_bytes(), doc.title, OBSERVATION_HEADER_ROWS, rows
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
        [["놀이 평가 및 다음날 지원계획", evaluation]],
    )
