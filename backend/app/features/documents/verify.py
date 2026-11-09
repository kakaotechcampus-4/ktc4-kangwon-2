"""일지 AI 검토 — 3단 게이트 3단(`POST /api/documents/{id}/verify`, ADR-071).

순서가 정해져 있다 (CLAUDE.md 「3단 게이트」):

    1 · 2단  shared/gates/sections.py — 모델 없이. 걸리면 3단을 부르지 않는다
    가명      원 전체 아이 이름을 가명으로 (shared/childCode). 못 바꾸면 부르지 않는다
    3단      shared/gates/judge.py — jev 가 문장마다 판정
    이름 되돌림  화면에 보일 문장만 원래 이름으로

판정 결과는 저장하지 않는다. 확정은 이 단계를 요구하지 않는다(router.confirm_document).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Child, Class
from app.features.documents.draft import KIND_LABELS
from app.features.documents.models import Document, DocumentSource
from app.shared.childCode import NameTable, load_pool, mask, table_for_text, unmask_from
from app.shared.gates.judge import Issue, Source, judge
from app.shared.gates.sections import SectionLike
from app.shared.llm import decide, is_mock

logger = logging.getLogger("app.server")


def name_table(session: Session, class_id: int, text: str) -> NameTable | None:
    """원 전체 아이(다른 반 포함) 중 글에 나온 아이로 표를 만든다 (PR #422 과 같은 범위).

    교사는 옆 반 아이 이름도 적는다. 못 바꾸면 SubstitutionError 가 그대로 올라간다.
    """
    center_id = select(Class.center_id).where(Class.id == class_id).scalar_subquery()
    rows = session.execute(
        select(Child.class_id, Child.name, Child.code)
        .join(Class, Class.id == Child.class_id)
        .where(Class.center_id == center_id)
        .order_by(Child.id)
    ).all()
    own = [(name, code) for owner, name, code in rows if owner == class_id]
    others = [(name, code) for owner, name, code in rows if owner != class_id]
    return table_for_text(load_pool(), own, others, text)


def verify_sections(
    session: Session,
    doc: Document,
    sections: Sequence[SectionLike],
    sources: Sequence[DocumentSource],
) -> tuple[list[Issue], Literal["jev", "mock"]]:
    """1 · 2단을 지난 글만 받는다(부르는 쪽이 먼저 막는다).

    **mock 이면 판정하지 않는다** — 빈 목록을 「통과」로 읽지 않게 `mock` 을 같이 돌려준다.
    오류(SubstitutionError · LlmUnavailable · LlmBudgetExceeded · LlmFailed · KeyError)는
    그대로 올린다.
    판정하지 못한 문서를 통과로 보이게 하지 않으려는 것이다.
    """
    if is_mock():
        return [], "mock"
    bodies = {s.heading: s.body for s in sections if s.heading in ("해석", "지원")}
    whole = "\n".join([*(src.text for src in sources), *bodies.values()])
    table = name_table(session, doc.class_id, whole)

    def hide(text: str) -> str:
        return text if table is None else mask(text, table)

    masked_sources = [Source(src.source_id, src.date, hide(src.text)) for src in sources]
    masked_bodies = {h: hide(b) for h, b in bodies.items()}
    issues = judge(doc.kind, KIND_LABELS[doc.kind], masked_bodies, masked_sources, decide)
    # 문장은 가명으로 판정했다. 화면에는 교사가 쓴 이름 그대로 돌려준다 — 성을 뺀 「가명이」처럼
    # 교사가 쓴 꼴을 살리려고 그 칸 원문을 기준으로 되돌린다(unmask_from).
    shown = [
        Issue(
            i.heading,
            i.sentence if table is None else unmask_from(i.sentence, table, bodies[i.heading]),
            i.code,
            i.source_id,
            i.reason,
            i.fix,
        )
        for i in issues
    ]
    # 글은 찍지 않는다(ADR-004). 무엇이 몇 건 걸렸는지만 남겨 오탐 · 기준값을 본다.
    counts = Counter(i.code for i in shown)
    logger.info(
        "gate_judge kind=%s issues=%s codes=%s",
        doc.kind,
        len(shown),
        ",".join(f"{code}:{n}" for code, n in sorted(counts.items())) or "-",
    )
    return shown, "jev"
