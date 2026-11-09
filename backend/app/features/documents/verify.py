"""일지 AI 검토 — 3단 게이트 3단(`POST /api/documents/{id}/verify`, ADR-071).

순서가 정해져 있다 (CLAUDE.md 「3단 게이트」):

    1 · 2단  shared/gates/sections.py — 모델 없이. 걸리면 3단을 부르지 않는다
    가명      원 전체 아이 이름을 가명으로 (shared/childCode). 못 바꾸면 부르지 않는다
    3단      shared/gates/judge.py — jev 가 문장마다 판정
    이름 되돌림  화면에 보일 문장만 원래 이름으로

판정 결과는 검토한 글의 지문(hash)과 함께 문서에 붙여 둔다(ADR-082 — ADR-071 결정 8 보완).
글이 바뀌면 보이지 않는다. 확정은 이 단계를 요구하지 않는다(router.confirm_document).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Child, Class
from app.features.documents.draft import KIND_LABELS
from app.features.documents.models import Document, DocumentSource
from app.shared.childCode import (
    NameTable,
    SubstitutionError,
    load_pool,
    mask,
    table_for_text,
    unmask_from,
)
from app.shared.gates.judge import MAX_SENTENCES, Issue, Source, TooLong, judge
from app.shared.gates.sections import SectionLike
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable, decide, is_mock

logger = logging.getLogger("app.server")


def name_table(session: Session, class_id: int, text: str) -> NameTable | None:
    """원 전체 아이(다른 반 포함) 중 글에 나온 아이로 표를 만든다 (PR #422 과 같은 범위).

    교사는 옆 반 아이 이름도 적는다. 못 바꾸면 SubstitutionError 가 그대로 올라간다.
    """
    center_id = select(Class.center_id).where(Class.id == class_id).scalar_subquery()
    rows = session.execute(
        select(Child.class_id, Child.name, Child.code, Child.call_name)
        .join(Class, Class.id == Child.class_id)
        .where(Class.center_id == center_id)
        .order_by(Child.id)
    ).all()
    own = [(name, code, call) for owner, name, code, call in rows if owner == class_id]
    others = [(name, code, call) for owner, name, code, call in rows if owner != class_id]
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
    # 상황도 jev 로 나간다. 표를 만드는 글에 빠지면 상황에만 적은 이름이 그대로 나간다.
    whole = "\n".join(
        [*(src.text for src in sources), *(src.context or "" for src in sources), *bodies.values()]
    )
    table = name_table(session, doc.class_id, whole)

    def hide(text: str | None) -> str | None:
        return text if table is None or not text else mask(text, table)

    # 초안 모델이 받은 사본 칸 그대로 — 사실 · 날짜 · 영역 · 상황 (ADR-088).
    masked_sources = [
        Source(src.source_id, src.date, hide(src.text), src.domain, hide(src.context))
        for src in sources
    ]
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


def review_hash(sections: Sequence[SectionLike]) -> str:
    """검토한 글의 지문. 사실까지 넣는다 — 근거를 다시 받아 사실이 바뀌어도 옛 결과가 된다."""
    bodies = {s.heading: s.body for s in sections}
    raw = json.dumps([bodies.get(h, "") for h in ("사실", "해석", "지원")], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def review_record(
    sections: Sequence[SectionLike],
    issues: Sequence[Issue] = (),
    judge_name: Literal["jev", "mock"] | None = None,
    message: str = "",
) -> dict:
    """문서에 붙여 둘 검토 결과. `judge_name` 이 없으면 검토하지 못한 것이다(`failed`)."""
    state = {"jev": "done", "mock": "mock", None: "failed"}[judge_name]
    return {
        "state": state,
        "issues": [asdict(i) for i in issues],
        "message": message,
        "hash": review_hash(sections),
    }


def current_review(doc: Document, sections: Sequence[SectionLike]) -> dict | None:
    """지금 글을 검토한 결과만. 글이 바뀌었으면 None — 옛 결과를 지금 글의 결과로 보이지 않는다."""
    review = doc.ai_review
    return review if review and review.get("hash") == review_hash(sections) else None


def review_draft(
    session: Session,
    doc: Document,
    sections: Sequence[SectionLike],
    sources: Sequence[DocumentSource],
) -> dict:
    """초안을 만들 때 같이 돌리는 검토. **실패해도 초안은 남긴다** (ADR-071 결정 8).

    판정하지 못하면 빈 목록이 아니라 `failed` 와 이유다 — 「문제없음」으로 보이면 안 된다.
    """
    try:
        issues, judge_name = verify_sections(session, doc, sections, sources)
    except SubstitutionError:
        return review_record(
            sections, message="아이 이름을 가명으로 바꾸지 못해 검토하지 않았어요."
        )
    except TooLong:
        return review_record(
            sections, message=f"해석 · 지원 문장이 {MAX_SENTENCES}개를 넘어 검토하지 않았어요."
        )
    except LlmBudgetExceeded:
        return review_record(sections, message="AI 사용 한도를 넘었어요. 담당자에게 알려 주세요.")
    except LlmUnavailable:
        return review_record(sections, message="지금은 AI 검토를 쓸 수 없어요.")
    except (LlmFailed, KeyError):
        return review_record(sections, message="AI 검토를 하지 못했어요. 다시 검토해 주세요.")
    return review_record(sections, issues, judge_name)
