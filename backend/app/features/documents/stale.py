"""근거가 바뀐 문서에 `stale` 을 붙인다 (docs/api-spec.md §11 「stale — 원본이 바뀌었다는 표시」).

**전파는 연쇄다.** 관찰 기록을 고치면 그걸 쓴 일일 보육일지가, 그 일지를 쓴 주간 보육일지가
`stale` 이 된다. 멈출 때까지 따라간다. 문서를 지우지 않는다 — 교사가 보고 판단한다.

**판정은 사본과 원본의 문자열 비교다.** 모델이 개입하지 않는다 (3단 게이트의 2단).
사본은 `document_sources` 에 생성 시점 그대로 남아 있다.

`stale` 을 되돌려 `false` 로 만드는 일은 여기서 하지 않는다. 교사가 다시 보는 것이 목적이라
원본이 우연히 원래 값으로 돌아와도 한 번 본 뒤에 풀어야 한다 — 푸는 길은 교사가 누르는
`POST /api/documents/{id}/refresh` 또는 비교·검증을 통과한 원자적 `reconfirm`이다.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.features.centers.models import Class
from app.features.documents.models import Document, DocumentSource


@dataclass(frozen=True)
class SourceImpact:
    """직접 영향을 받은 확정 일일 보육일지. 전파되는 문서 전체와 구분한다."""

    affected_document_ids: tuple[int, ...] = ()
    newly_stale_document_ids: tuple[int, ...] = ()


def _sources(center_id: int | None):
    query = select(DocumentSource.document_id).join(
        Document, Document.id == DocumentSource.document_id
    )
    if center_id is not None:
        query = query.join(Class, Class.id == Document.class_id).where(Class.center_id == center_id)
    return query


def observation_changed(
    session: Session, observation_id: int, fact: str | None, date: datetime.date | None
) -> None:
    """관찰 기록이 바뀌었거나(`fact`·`date`) 사라졌다(둘 다 None).

    **사본과 같은 문서는 건드리지 않는다** — 영역·상황만 고쳤으면 사실은 그대로다.
    `class_id` · `child_id` 는 §10 이 수정을 막으므로 비교하지 않는다.
    """
    source_changed(session, "observation", observation_id, fact, date)


def source_changed(
    session: Session,
    kind: str,
    source_id: int,
    text: str | None,
    date: datetime.date | None,
    *,
    center_id: int | None = None,
    force: bool = False,
) -> SourceImpact:
    """근거 원본(관찰 기록 · 일과 기록)이 바뀌었거나(`text`·`date`) 사라졌다(둘 다 None).

    `text` 는 문서가 사본으로 남긴 문자열과 같은 모양이어야 한다 — 일과 기록은
    `RoutineRecord.fact_text()` 다. 사본과 같으면 문서를 건드리지 않는다.
    """
    query = _sources(center_id).where(
        DocumentSource.source_kind == kind,
        DocumentSource.source_id == source_id,
    )
    if text is not None and not force:
        query = query.where(
            or_(DocumentSource.text != text, DocumentSource.date.is_distinct_from(date))
        )
    document_ids = set(session.scalars(query))
    # 행 잠금 뒤 상태를 읽는다. 동시에 두 근거가 바뀌어도 신규 stale을 둘 다 세지 않는다.
    confirmed = list(
        session.scalars(
            select(Document)
            .where(
                Document.id.in_(document_ids),
                Document.kind == "dailyLog",
                Document.status == "CONFIRMED",
            )
            .order_by(Document.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    impact = SourceImpact(
        affected_document_ids=tuple(sorted(doc.id for doc in confirmed)),
        newly_stale_document_ids=tuple(sorted(doc.id for doc in confirmed if not doc.stale)),
    )
    _mark(session, document_ids, center_id=center_id)
    return impact


def document_changed(session: Session, document_id: int) -> None:
    """문서가 사라졌거나 확정이 풀렸다. **그 문서를 근거로 쓴 문서들**을 끝까지 `stale` 로.

    문서 자신은 건드리지 않는다 — 바뀐 것은 이 문서고, 다시 봐야 하는 것은 이걸 쓴 쪽이다.
    §11 판정 기준의 「근거가 문서일 때 … status」 와 「원본 없음」이 여기로 온다.
    """
    dependents = session.scalars(
        select(DocumentSource.document_id).where(
            DocumentSource.source_kind == "document",
            DocumentSource.source_id == document_id,
        )
    )
    _mark(session, set(dependents))


def _mark(session: Session, document_ids: set[int], *, center_id: int | None = None) -> None:
    """이 문서들과, 이 문서들을 근거로 쓴 문서들을 끝까지 따라가 `stale` 로 바꾼다.

    `seen` 으로 한 번 본 문서는 다시 보지 않는다 — 근거 관계에 순환이 생겨도 멈춘다.
    """
    seen: set[int] = set()
    frontier = document_ids
    while frontier:
        seen |= frontier
        frontier = (
            set(
                session.scalars(
                    _sources(center_id).where(
                        DocumentSource.source_kind == "document",
                        DocumentSource.source_id.in_(frontier),
                    )
                )
            )
            - seen
        )
    if seen:
        session.execute(update(Document).where(Document.id.in_(seen)).values(stale=True))
