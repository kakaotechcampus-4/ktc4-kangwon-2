"""근거가 바뀐 문서에 `stale` 을 붙인다 (docs/api-spec.md §11 「stale — 원본이 바뀌었다는 표시」).

**전파는 연쇄다.** 관찰 기록을 고치면 그걸 쓴 일일 보육일지가, 그 일지를 쓴 주간 보육일지가
`stale` 이 된다. 멈출 때까지 따라간다. 문서를 지우지 않는다 — 교사가 보고 판단한다.

**판정은 사본과 원본의 문자열 비교다.** 모델이 개입하지 않는다 (3단 게이트의 2단).
사본은 `document_sources` 에 생성 시점 그대로 남아 있다.

`stale` 을 되돌려 `false` 로 만드는 일은 여기서 하지 않는다. 교사가 다시 보는 것이 목적이라
원본이 우연히 원래 값으로 돌아와도 한 번 본 뒤에 풀어야 한다 — 푸는 길은 교사가 누르는
`POST /api/documents/{id}/refresh` 하나다.
"""

import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.features.documents.models import Document, DocumentSource


def observation_changed(
    session: Session, observation_id: int, fact: str | None, date: datetime.date | None
) -> None:
    """관찰 기록이 바뀌었거나(`fact`·`date`) 사라졌다(둘 다 None).

    **사본과 같은 문서는 건드리지 않는다** — 영역·상황만 고쳤으면 사실은 그대로다.
    `class_id` · `child_id` 는 §10 이 수정을 막으므로 비교하지 않는다.
    """
    source_changed(session, "observation", observation_id, fact, date)


def source_changed(
    session: Session, kind: str, source_id: int, text: str | None, date: datetime.date | None
) -> None:
    """근거 원본(관찰 기록 · 일과 기록)이 바뀌었거나(`text`·`date`) 사라졌다(둘 다 None).

    `text` 는 문서가 사본으로 남긴 문자열과 같은 모양이어야 한다 — 일과 기록은
    `RoutineRecord.fact_text()` 다. 사본과 같으면 문서를 건드리지 않는다.
    """
    query = select(DocumentSource.document_id).where(
        DocumentSource.source_kind == kind,
        DocumentSource.source_id == source_id,
    )
    if text is not None:
        query = query.where(
            or_(DocumentSource.text != text, DocumentSource.date.is_distinct_from(date))
        )
    _mark(session, set(session.scalars(query)))


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


def _mark(session: Session, document_ids: set[int]) -> None:
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
                    select(DocumentSource.document_id).where(
                        DocumentSource.source_kind == "document",
                        DocumentSource.source_id.in_(frontier),
                    )
                )
            )
            - seen
        )
    if seen:
        session.execute(update(Document).where(Document.id.in_(seen)).values(stale=True))
