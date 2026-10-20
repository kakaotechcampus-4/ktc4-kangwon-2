"""일과 근거 비교와 원자적 재확정. 원본 → 문서 순으로 잠가 일과 수정과 직렬화한다."""

import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.features.auth.models import User
from app.features.centers.models import Class
from app.features.documents.models import (
    Document,
    DocumentReconfirmation,
    DocumentSection,
    DocumentSource,
)
from app.features.documents.schemas import (
    DocumentReconfirmRequest,
    DocumentSourceComparison,
    SourceComparisonItem,
    SourceReplacementCandidate,
)
from app.features.documents.stale import document_changed
from app.features.observations.models import Observation
from app.features.routines.models import RoutineRecord
from app.shared.gates.sections import check_sections, join_facts


def fail(code: str, message: str, fields: list[str], status: int = 409):
    raise HTTPException(status, detail={"code": code, "message": message, "fields": fields})


def digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def lock_sources(session: Session, user: User, doc, copies) -> None:
    """근거 원본 → 문서 순으로 행을 잠근다. 잠근 뒤에는 커밋할 때까지 원본이 바뀌지 않는다.

    **다시 읽어 확인하는 것으로는 부족하다** — 읽은 직후 다른 트랜잭션이 원본을 바꾸면
    그 값이 사본에 fresh 로 남는다 (F2). 일과 `PUT`·`DELETE` 도 원본 → 문서 순이라
    순서가 같고, 종류 안에서는 언제나 id 오름차순 한 문장이라 교착이 생기지 않는다.

    문서 잠금까지 여기서 끝낸다 — 근거로 쓴 문서와 이 문서를 한 문장으로 오름차순 잠가야
    둘의 순서가 어긋나지 않는다 (`stale` 전파도 같은 오름차순이다).
    """
    cited = [c.source_id for c in copies if c.source_kind == "routine"]
    # 일과 근거 일일 보육일지는 같은 반·같은 날의 일과까지 잠근다 — 대체 후보가 거기서 온다.
    same_day = and_(RoutineRecord.class_id == doc.class_id, RoutineRecord.date == doc.start_date)
    routines = (
        or_(RoutineRecord.id.in_(cited), same_day)
        if doc.kind == "dailyLog"
        else RoutineRecord.id.in_(cited)
        if cited
        else None
    )
    if routines is not None:
        session.scalars(
            select(RoutineRecord)
            .join(Class)
            .where(Class.center_id == user.center_id, routines)
            .order_by(RoutineRecord.id)
            .with_for_update(of=RoutineRecord)
            .execution_options(populate_existing=True)
        ).all()
    observations = [c.source_id for c in copies if c.source_kind == "observation"]
    if observations:
        session.scalars(
            select(Observation)
            .where(Observation.id.in_(observations))
            .order_by(Observation.id)
            .with_for_update(of=Observation)
            .execution_options(populate_existing=True)
        ).all()
    session.scalars(
        select(Document)
        .where(
            Document.id.in_({c.source_id for c in copies if c.source_kind == "document"} | {doc.id})
        )
        .order_by(Document.id)
        .with_for_update(of=Document)
        .execution_options(populate_existing=True)
    ).all()


def replacement_candidates(session: Session, user: User, doc, copies):
    """사라진 근거를 대신할 수 있는 같은 반·같은 날의 일과. 이미 쓰는 일과와 빈 실행은 뺀다."""
    used = {c.source_id for c in copies if c.source_kind == "routine"}
    return [
        SourceReplacementCandidate(id=r.id, text=r.fact_text())
        for r in session.scalars(
            select(RoutineRecord)
            .join(Class)
            .where(
                RoutineRecord.class_id == doc.class_id,
                RoutineRecord.date == doc.start_date,
                Class.center_id == user.center_id,
            )
            .order_by(RoutineRecord.position, RoutineRecord.id)
        )
        if r.id not in used and r.execution.strip()
    ]


def plan_resolutions(session, user, doc, copies, missing_ids, candidates, resolutions):
    """사라진 근거를 어떻게 할지 확인하고 `{사라진 source_id: 바꿀 일과 또는 None(빼기)}` 로 준다.

    `resolutions` 가 비어 있으면 `None` 이다 — 부르는 쪽이 예전 규칙대로 거절한다.
    고르지 않은 사라진 근거, 내줄 수 없는 대체 후보, 전부 빼는 선택은 모두 거절한다.
    대체본은 여기서 다시 읽고 잠근다 — 목록을 본 뒤 지워졌거나 비워졌으면 걸린다.
    """
    chosen: dict[int, object] = {}
    for item in resolutions:
        if item.source_id in chosen or item.source_id not in missing_ids:
            fail("VALIDATION_FAILED", "처리할 수 없는 근거를 골랐습니다.", ["resolutions"], 422)
        chosen[item.source_id] = item
    if not chosen:
        return None
    unresolved = sorted(missing_ids - set(chosen))
    if unresolved:
        fail(
            "GATE_BLOCKED",
            "사라진 근거를 어떻게 할지 먼저 골라주세요.",
            [f"sources.{i}" for i in unresolved],
        )
    offered = {c.id for c in candidates}
    picks: set[int] = set()
    for item in chosen.values():
        if item.action != "replace":
            continue
        if item.replacement_id not in offered or item.replacement_id in picks:
            fail(
                "GATE_BLOCKED",
                "대체할 일과 기록을 다시 골라주세요.",
                [f"sources.{item.source_id}"],
            )
        picks.add(item.replacement_id)
    fresh = {
        r.id: r
        for r in session.scalars(
            select(RoutineRecord)
            .join(Class)
            .where(
                RoutineRecord.id.in_(picks),
                RoutineRecord.class_id == doc.class_id,
                RoutineRecord.date == doc.start_date,
                Class.center_id == user.center_id,
            )
            .execution_options(populate_existing=True)
        )
        if r.execution.strip()
    }
    plan: dict[int, RoutineRecord | None] = {}
    for source_id, item in chosen.items():
        if item.action == "drop":
            plan[source_id] = None
            continue
        pick = fresh.get(item.replacement_id)
        if pick is None:
            fail("GATE_BLOCKED", "대체할 일과 기록을 다시 골라주세요.", [f"sources.{source_id}"])
        plan[source_id] = pick
    if len(copies) == sum(1 for pick in plan.values() if pick is None):
        fail(
            "GATE_BLOCKED",
            "근거를 모두 빼면 보육일지를 만들 수 없습니다. 최소 한 건은 남겨주세요.",
            ["resolutions"],
        )
    return plan


def resolution_trail(copies, plan):
    """뺀·바꾼 근거를 사람이 읽을 수 있게 남긴다. 사본 행이 사라지므로 여기가 유일한 흔적이다."""
    return [
        {
            "source_id": copy.source_id,
            "action": "drop" if plan[copy.source_id] is None else "replace",
            "replacement_id": None if plan[copy.source_id] is None else plan[copy.source_id].id,
            "before": copy.text,
        }
        for copy in copies
        if copy.source_id in plan
    ]


def locked_review(session: Session, user: User, document_id: int):
    """모든 쓰기와 같은 잠금 순서다. 다른 센터·반의 원본은 반환하지 않는다."""
    doc = session.scalar(
        select(Document)
        .join(Class)
        .where(Document.id == document_id, Class.center_id == user.center_id)
    )
    if doc is None:
        fail("NOT_FOUND", "문서를 찾을 수 없습니다.", ["document_id"], 404)
    if doc.kind != "dailyLog":
        fail("GATE_BLOCKED", "일과 근거의 일일 보육일지만 재확정할 수 있습니다.", ["kind"])
    before = list(
        session.scalars(
            select(DocumentSource)
            .where(DocumentSource.document_id == doc.id)
            .order_by(DocumentSource.id)
        )
    )
    # **`kind` 만 보면 모자란다** (#180 수린님 리뷰). 옛 일일 보육일지는 관찰 기록을
    # 근거로 만들어졌고, 아래 비교는 `routine` 이 아닌 사본을 **무조건 「사라짐」**으로
    # 본다(`by_id.get(...) if source_kind == "routine" else None`). 그대로 두면 멀쩡한
    # 관찰 근거를 빼거나 바꿔서 재확정할 수 있고, 근거가 조용히 바뀐 확정본이 남는다.
    #
    # `refresh`(router.py)가 같은 이유로 이미 막는다. 여기도 같게 막는다.
    if any(copy.source_kind != "routine" for copy in before):
        fail("GATE_BLOCKED", "일과 기록이 아닌 근거가 있어 재확정할 수 없습니다.", ["kind"])
    lock_sources(session, user, doc, before)
    doc = session.scalar(
        select(Document).where(Document.id == doc.id).execution_options(populate_existing=True)
    )
    if doc is None:
        fail("NOT_FOUND", "문서를 찾을 수 없습니다.", ["document_id"], 404)
    ids = [c.source_id for c in before if c.source_kind == "routine"]
    routines = list(
        session.scalars(
            select(RoutineRecord)
            .join(Class)
            .where(
                RoutineRecord.id.in_(ids),
                RoutineRecord.class_id == doc.class_id,
                Class.center_id == user.center_id,
            )
            .order_by(RoutineRecord.id)
            .execution_options(populate_existing=True)
        )
    )
    copies = list(
        session.scalars(
            select(DocumentSource)
            .where(DocumentSource.document_id == doc.id)
            .order_by(DocumentSource.id)
            .execution_options(populate_existing=True)
        )
    )
    sections = list(
        session.scalars(
            select(DocumentSection)
            .where(DocumentSection.document_id == doc.id)
            .order_by(DocumentSection.heading)
            .execution_options(populate_existing=True)
        )
    )
    by_id = {r.id: r for r in routines}
    rows = []
    versions = []
    for copy in copies:
        current = by_id.get(copy.source_id) if copy.source_kind == "routine" else None
        if current is not None and (
            current.date != doc.start_date
            or not current.execution.strip()
            or copy.class_id != doc.class_id
        ):
            current = None
        text = current.fact_text() if current else None
        rows.append(
            SourceComparisonItem(
                id=copy.source_id,
                before=copy.text,
                after=text,
                state="missing"
                if text is None
                else "unchanged"
                if text == copy.text
                else "changed",
            )
        )
        # 표시는 분까지지만 충돌 판정은 초를 포함한 원본 값으로 한다.
        versions.append(
            None
            if current is None
            else [
                current.id,
                current.class_id,
                current.date,
                current.start_time,
                current.end_time,
                current.name,
                current.execution,
            ]
        )
    candidates = replacement_candidates(session, user, doc, copies)
    source_hash = digest(versions)
    state_hash = digest(
        [
            doc.id,
            doc.class_id,
            doc.kind,
            doc.status,
            doc.stale,
            doc.updated_at,
            doc.title,
            doc.review_note,
            doc.start_date,
            doc.end_date,
            [[s.heading, s.body, s.source_ids] for s in sections],
            [[c.source_kind, c.source_id, c.text, c.date, c.class_id] for c in copies],
            source_hash,
        ]
    )
    token = hmac.new(settings.secret_key.encode(), state_hash.encode(), hashlib.sha256).hexdigest()
    comparison = DocumentSourceComparison(
        document_id=doc.id,
        updated_at=doc.updated_at.astimezone(UTC),
        review_token=token,
        sources=rows,
        can_reconfirm=doc.status == "CONFIRMED"
        and doc.stale
        and bool(rows)
        and all(r.state != "missing" for r in rows),
        candidates=candidates,
    )
    return doc, copies, sections, source_hash, comparison


def reconfirm(session: Session, user: User, document_id: int, body: DocumentReconfirmRequest):
    doc, copies, stored, source_hash, comparison = locked_review(session, user, document_id)
    request_hash = digest(body.model_dump(mode="json"))
    # 같은 요청을 다시 보냈나. 영수증에는 **끝난 뒤** 모습을 적어 두므로(아래),
    # 방금 잰 값과 그대로 맞으면 첫 요청의 결과를 다시 돌려준다. 이중 적용은 없다.
    receipt = session.scalar(
        select(DocumentReconfirmation).where(
            DocumentReconfirmation.document_id == doc.id,
            DocumentReconfirmation.review_token == body.review_token,
        )
    )
    if receipt is not None:
        if (
            receipt.request_hash == request_hash
            and receipt.completed_at == doc.updated_at
            and receipt.source_hash == source_hash
            and doc.status == "CONFIRMED"
            and not doc.stale
        ):
            return doc
        fail(
            "STALE_WRITE",
            "완료된 검토 이후 내용이 바뀌었습니다. 다시 비교해주세요.",
            ["review_token"],
        )
    if body.updated_at != doc.updated_at or not hmac.compare_digest(
        comparison.review_token, body.review_token
    ):
        fail(
            "STALE_WRITE",
            "비교 이후 원본이나 문서가 바뀌었습니다. 다시 비교해주세요.",
            ["review_token"],
        )
    missing_ids = {row.id for row in comparison.sources if row.state == "missing"}
    plan = plan_resolutions(
        session, user, doc, copies, missing_ids, comparison.candidates, body.resolutions
    )
    if plan is None and not comparison.can_reconfirm:
        fail(
            "GATE_BLOCKED",
            "확정 상태와 누락된 원본을 확인해주세요.",
            ["sources", "status", "stale"],
        )
    if plan is not None and not (doc.status == "CONFIRMED" and doc.stale):
        fail(
            "GATE_BLOCKED",
            "확정 상태와 누락된 원본을 확인해주세요.",
            ["sources", "status", "stale"],
        )
    unchecked = [f"checks.{name}" for name, value in body.checks.model_dump().items() if not value]
    if unchecked:
        fail("VALIDATION_FAILED", "교사 검토를 완료해주세요.", unchecked, 422)
    survivors, dropped = [], []
    for copy, row in zip(copies, comparison.sources, strict=True):
        pick = plan.get(copy.source_id) if plan else None
        if plan and copy.source_id in plan:
            (dropped if pick is None else survivors).append(
                copy if pick is None else (copy, pick.id, pick.fact_text())
            )
        else:
            survivors.append((copy, copy.source_id, row.after))
    texts = [text for _, _, text in survivors]
    ids = [new_id for _, new_id, _ in survivors]
    fields = check_sections(body.sections, texts, set(ids))
    if fields:
        fail("VALIDATION_FAILED", "입력값을 확인해주세요.", fields, 422)

    # 검증을 모두 마친 뒤에만 변경한다. 실패하면 세션이 롤백하고 확정본은 그대로 남는다.
    # 흔적은 사본을 고치기 전에 뜬다 — 아래에서 source_id 와 text 가 새 값으로 바뀐다.
    trail = resolution_trail(copies, plan) if plan else None
    doc.status = "DRAFT"
    for copy, new_id, text in survivors:
        copy.source_id = new_id
        copy.text = text
        copy.date = doc.start_date
    if plan:
        for copy in dropped:
            session.delete(copy)
        session.flush()
    by_heading = {s.heading: s for s in body.sections}
    for section in stored:
        incoming = by_heading[section.heading]
        section.body, section.source_ids = incoming.body, incoming.source_ids
    # 사실은 입력 문구를 신뢰하지 않고 원본으로 구성한다(위 게이트에서 동일성도 검사).
    next(s for s in stored if s.heading == "사실").body = join_facts(texts)
    if body.review_note is not None:
        doc.review_note = body.review_note
    doc.stale = False
    doc.status = "CONFIRMED"
    doc.updated_at = datetime.now(UTC)
    document_changed(session, doc.id)
    # **끝난 뒤** 근거 모습을 다시 잰다. 재시도는 그때의 값과 비교하므로, 근거를 빼거나
    # 바꾼 재확정이면 변경 전 해시로는 영영 어긋난다. 재시도가 재는 것과 같은 길로 잰다.
    # **flush 를 먼저 한다** — 운영 세션은 `autoflush=False` 라서, 안 쓰고 다시 읽으면
    # 아래 `populate_existing` 이 방금 바꾼 값을 DB 의 옛 값으로 덮어쓴다.
    session.flush()
    _, _, _, settled_hash, _ = locked_review(session, user, document_id)
    session.add(
        DocumentReconfirmation(
            document_id=doc.id,
            review_token=body.review_token,
            request_hash=request_hash,
            source_hash=settled_hash,
            completed_at=doc.updated_at,
            resolutions=trail,
        )
    )
    session.commit()
    return doc
