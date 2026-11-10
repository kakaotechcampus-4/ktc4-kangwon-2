"""근거가 바뀐 문서에 `stale` 을 붙인다 (docs/api-spec.md §11 「stale — 원본이 바뀌었다는 표시」).

**전파는 연쇄다.** 관찰 기록을 고치면 그걸 쓴 일일 보육일지가, 그 일지를 쓴 주간 보육일지가
`stale` 이 된다. 멈출 때까지 따라간다. 문서를 지우지 않는다 — 교사가 보고 판단한다.

**판정은 사본과 원본의 문자열 비교다.** 관찰 기록은 사실 · 날짜 · 영역 · 상황을 본다(ADR-088).
모델이 개입하지 않는다 (3단 게이트의 2단).
사본은 `document_sources` 에 생성 시점 그대로 남아 있다.

`stale` 을 되돌려 `false` 로 만드는 일은 여기서 하지 않는다. 교사가 다시 보는 것이 목적이라
원본이 우연히 원래 값으로 돌아와도 한 번 본 뒤에 풀어야 한다 — 푸는 길은 교사가 누르는
`POST /api/documents/{id}/refresh` 또는 비교·검증을 통과한 원자적 `reconfirm`이다.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.features.centers.models import Class
from app.features.documents.models import Document, DocumentSource
from app.features.observations.models import Observation


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
    session: Session,
    observation_id: int,
    observation: Observation | None,
    *,
    domain_moved: bool = False,
) -> SourceImpact:
    """관찰 기록이 바뀌었거나(`observation` 은 고친 뒤 값) 사라졌다(None).

    사본과 사실 · 날짜 · 영역 · 상황 중 하나라도 다르면 `stale` 이다 (ADR-088). 영역은
    종이의 행을, 상황은 관찰 칸 글과 AI 입력을 바꾼다 — 확정한 글과 다른 종이가 나간다.

    **영역 · 상황 사본이 없는 옛 문서(NULL, 「다시 확인」)는** 종이가 지금 원본 영역을 따른다.
    그래서 원본 영역이 실제로 바뀌었을 때(`domain_moved`)만 `stale` 이다. 상황은 옛 종이에
    쓰이지 않아 보지 않는다. `class_id` · `child_id` 는 §10 이 수정을 막으므로 비교하지 않는다.

    돌려주는 영향은 이 기록을 **직접** 인용한 확정 문서(관찰일지 · 영유아 평가)다. 일과 기록의
    `source_changed` 와 같은 규칙이다 — 초안과 연쇄로 따라간 문서는 stale 로 바꾸되 세지 않는다.
    """
    query = _sources(None).where(
        DocumentSource.source_kind == "observation",
        DocumentSource.source_id == observation_id,
    )
    if observation is not None:
        differs = [
            DocumentSource.text != observation.fact,
            DocumentSource.date.is_distinct_from(observation.date),
            and_(DocumentSource.domain.is_not(None), DocumentSource.domain != observation.domain),
            and_(
                DocumentSource.context.is_not(None), DocumentSource.context != observation.context
            ),
        ]
        if domain_moved:
            differs.append(DocumentSource.domain.is_(None))
        query = query.where(or_(*differs))
    document_ids = set(session.scalars(query))
    impact = _confirmed_impact(session, document_ids)
    _mark(session, document_ids)
    return impact


def _confirmed_impact(session: Session, document_ids: set[int], kinds=None) -> SourceImpact:
    """직접 영향을 받은 확정 문서. 행 잠금 뒤 stale 을 읽는다 — 동시에 두 근거가 바뀌어도
    새로 stale 이 된 문서를 둘 다 세지 않는다."""
    query = select(Document).where(Document.id.in_(document_ids), Document.status == "CONFIRMED")
    if kinds is not None:
        query = query.where(Document.kind.in_(kinds))
    confirmed = list(
        session.scalars(
            query.order_by(Document.id).with_for_update().execution_options(populate_existing=True)
        ).all()
    )
    return SourceImpact(
        affected_document_ids=tuple(doc.id for doc in confirmed),
        newly_stale_document_ids=tuple(doc.id for doc in confirmed if not doc.stale),
    )


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
    # 일과 기록을 직접 인용하는 종류 둘이다 — 일일, 그리고 일일을 쓰지 않는
    # 원의 주간. 연쇄로 stale 이 된 문서는 애초에 이 집합에 없다(§10-1).
    impact = _confirmed_impact(session, document_ids, ("dailyLog", "weeklyLog"))
    _mark(session, document_ids, center_id=center_id)
    return impact


def document_changed(session: Session, document_id: int) -> SourceImpact:
    """문서가 사라졌거나 확정이 풀렸다. **그 문서를 근거로 쓴 문서들**을 끝까지 `stale` 로.

    문서 자신은 건드리지 않는다 — 바뀐 것은 이 문서고, 다시 봐야 하는 것은 이걸 쓴 쪽이다.
    §11 판정 기준의 「근거가 문서일 때 … status」 와 「원본 없음」이 여기로 온다.

    돌려주는 영향은 **이 문서를 직접 근거로 쓴 문서**만 센다. 연쇄로 따라간 문서는
    stale 로 바꾸되 안내 건수에 넣지 않는다 — 일과 기록의 영향 응답과 같은 규칙이다.
    """
    dependents = set(
        session.scalars(
            select(DocumentSource.document_id).where(
                DocumentSource.source_kind == "document",
                DocumentSource.source_id == document_id,
            )
        )
    )
    # 행 잠금 뒤 stale 을 읽는다. 동시에 두 근거가 풀려도 새로 stale 이 된 문서를 둘 다 세지 않는다.
    direct = list(
        session.scalars(
            select(Document)
            .where(Document.id.in_(dependents))
            .order_by(Document.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    impact = SourceImpact(
        affected_document_ids=tuple(doc.id for doc in direct),
        newly_stale_document_ids=tuple(doc.id for doc in direct if not doc.stale),
    )
    _mark(session, dependents)
    return impact


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
