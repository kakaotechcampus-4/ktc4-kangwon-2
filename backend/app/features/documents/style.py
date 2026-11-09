"""관찰일지 초안의 말투 예시 (AI ③, ADR-083).

그 교사가 전에 확정한 관찰일지의 해석 · 지원에서 **아이가 안 나오는 짧은 문장** 몇 개를 골라
「말투 참고」로 보낸다. 문장 끝 · 길이 · 연결어를 닮게 하려는 것이고, 내용은 가져오지 않는다.

**아이가 나올 수 있는 문장은 가리지 않고 뺀다.** 예시는 옛 글이라 지금 가명표로 다 가려진다는
보장이 없다(review3 1-6). 그래서 가명으로 바꾸는 대신 아래 셋 중 하나라도 걸리면 그 문장을 버린다.

    원 아이 이름    지금 원 아이 이름 · 성을 뗀 이름이 들어 있다
    따옴표         아이가 한 말을 옮긴 문장이다
    이름 꼴        「하윤이가」처럼 낱말 머리 두 글자 + 「이가 · 이는 …」 — 지운 아이 이름일 수 있다

이름 꼴은 「고양이가」 같은 낱말도 버린다. 버리는 쪽으로만 틀리니 예시가 줄 뿐 이름이 새지 않는다.
"""

import re
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.auth.models import User
from app.features.centers.models import Child, Class
from app.features.documents.models import Document, DocumentSection
from app.shared.auth.ownership import own_class_clause
from app.shared.childCode import name_variants
from app.shared.gates.judge import split_sentences

# 예시 수. 셋이면 말투가 보이고, 문장당 수십 토큰이라 한 번에 100토큰 남짓 는다(ADR-083).
LIMIT = 3
# 짧은 발췌만 — 긴 문장일수록 장면(누가 · 무엇을)이 따라온다.
MIN_CHARS, MAX_CHARS = 10, 60
# 확정본을 이만큼만 읽는다. 최근 글이 지금 말투에 가깝다.
RECENT_DOCUMENTS = 10

_QUOTES = re.compile(r"[「」『』\"“”'‘’]")
_NAME_LIKE = re.compile(r"(?<![가-힣])[가-힣]{2}이(?:가|는|를|와|랑|도|의|에게|한테|처럼)")


def pick_examples(
    texts: Iterable[str], names: Iterable[str], offset: int, limit: int = LIMIT
) -> list[str]:
    """`offset` 으로 돌려 고른다 — 반 전체 초안에서 아이마다 다른 예시를 보게(획일화를 줄인다)."""
    variants = {v for name in names for v in name_variants(name)}
    pool: list[str] = []
    for text in texts:
        for sentence in split_sentences(text):
            if not MIN_CHARS <= len(sentence) <= MAX_CHARS or sentence in pool:
                continue
            if _QUOTES.search(sentence) or _NAME_LIKE.search(sentence):
                continue
            if any(v in sentence for v in variants):
                continue
            pool.append(sentence)
    if not pool:
        return []
    start = offset % len(pool)
    return (pool[start:] + pool[:start])[:limit]


def teacher_examples(session: Session, user: User, child_id: int) -> list[str]:
    """이 교사 반의 확정 관찰일지(AI 초안을 교사가 확정한 것) 해석 · 지원에서 고른다."""
    recent = (
        select(Document.id)
        .join(Class, Class.id == Document.class_id)
        .where(
            own_class_clause(user),
            Document.kind == "observation",
            Document.status == "CONFIRMED",
            Document.origin == "AI",
        )
        .order_by(Document.updated_at.desc(), Document.id.desc())
        .limit(RECENT_DOCUMENTS)
    )
    texts: Sequence[str] = session.scalars(
        select(DocumentSection.body)
        .where(
            DocumentSection.document_id.in_(recent.scalar_subquery()),
            DocumentSection.heading.in_(("해석", "지원")),
        )
        .order_by(DocumentSection.document_id.desc(), DocumentSection.heading)
    ).all()
    names = session.scalars(
        select(Child.name)
        .join(Class, Class.id == Child.class_id)
        .where(Class.center_id == user.center_id)
    ).all()
    return pick_examples(texts, names, offset=child_id)
