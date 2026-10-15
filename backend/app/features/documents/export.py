"""문서 내보내기 — `GET /api/documents/{id}/export/hwp` (docs/api-spec.md §11 「내보내기」).

§9 계획안 내보내기와 같은 규칙이다. 확정본만 · 출처를 싣지 않는다 · 경로는 `hwp` 지만
파일은 hwpx 다(`shared/hwpx.py`).

**3층을 종이에서 합친다(ADR-024).** 화면과 검사에서는 사실 · 해석 · 지원이 나뉘어 있지만
실물 양식에는 해석 칸과 지원 칸이 따로 없다. 「평가」 한 칸에 해석, 빈 줄, 지원 순서로 잇는다.

지금은 관찰일지만 있다. 일일 보육일지는 일과 행 수가 날마다 달라 표에 줄을 늘리는 일이
따로 필요하다.
"""

from pathlib import Path

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.features.documents.models import DocumentSection
from app.features.documents.router import (
    DbSession,
    _error,
    _observation_domains,
    _own_document,
    _sources,
)
from app.features.observations.models import DOMAINS
from app.shared.auth.dependency import CurrentUser
from app.shared.hwpx import download, fill_table

router = APIRouter(prefix="/documents", tags=["documents"])

TEMPLATE_DIR = Path(__file__).parent / "templates"

# 양식의 머리행(영역 · 관찰내용) 줄 수. 그 아래가 5영역 · 평가 순서다.
OBSERVATION_HEADER_ROWS = 1


@router.get("/{document_id}/export/hwp")
def export_document(document_id: int, session: DbSession, user: CurrentUser) -> Response:
    doc = _own_document(session, user, document_id)
    if doc.kind != "observation":
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "지금은 관찰일지만 내보낼 수 있습니다.",
            ["kind"],
        )
    if doc.status != "CONFIRMED":
        raise _error(
            status.HTTP_409_CONFLICT, "GATE_BLOCKED", "확정된 문서만 내보낼 수 있습니다.", []
        )

    sources = _sources(session, doc.id)
    domains = _observation_domains(session, sources)
    missing = [f"sources.{s.source_id}" for s in sources if s.source_id not in domains]
    if missing:
        # 영역을 모르면 어느 행에 넣을지 정할 수 없다. 빼고 내보내면 교사가 고른 사실이
        # 제출 문서에서 조용히 사라진다.
        raise _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "근거 관찰 기록이 사라졌습니다. 확정을 취소하고 문서를 새로 만들어주세요.",
            missing,
        )

    # 영역 안에서는 날짜순이다. 같은 날이면 교사가 고른 순서를 지킨다(sorted 는 안정 정렬).
    by_domain: dict[str, list[str]] = {domain: [] for domain in DOMAINS}
    for source in sorted(sources, key=lambda s: s.date):
        by_domain[domains[source.source_id]].append(
            f"({source.date.month}/{source.date.day}) {source.text}"
        )

    bodies = dict(
        session.execute(
            select(DocumentSection.heading, DocumentSection.body).where(
                DocumentSection.document_id == doc.id
            )
        ).all()
    )
    rows = [[domain, "\n".join(lines)] for domain, lines in by_domain.items()]
    rows.append(["평가", f"{bodies['해석']}\n\n{bodies['지원']}"])

    content = fill_table(
        (TEMPLATE_DIR / "observation.hwpx").read_bytes(),
        doc.title,
        OBSERVATION_HEADER_ROWS,
        rows,
    )
    return download(content, f"document-{doc.id}", doc.title)
