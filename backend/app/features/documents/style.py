"""관찰일지 초안의 말투 예시 (AI ③, ADR-083).

그 교사가 전에 확정한 관찰일지의 해석 · 지원에서 **아이가 안 나오는 짧은 문장** 몇 개를 골라
「말투 참고」로 보낸다. 문장 끝 · 길이 · 연결어를 닮게 하려는 것이고, 내용은 가져오지 않는다.

**아이가 나오는 문장은 가명으로 바꿔 보내지 않고 뺀다.** 바꿔 보내면 다른 아이(또는 같은 아이의
옛) 장면이 이 초안에 섞인다. 아이를 찾는 일은 초안의 가명표와 같은 장치가 한다
(`verify.center_children` + `shared/childCode.table_for_text`) — 원 전체 아이 이름 · 성을 뗀 이름 ·
등록한 부르는 이름 · 외자 꼴(「민이가」 · 「민은」). 아래 하나라도 걸리면 그 문장을 버린다.

    가명표          초안과 같은 표가 아이를 하나라도 찾았다
    가릴 수 없음     표를 못 만든다(홀로 선 외자 「민」 등) — 가리지 못하면 보내지 않는다
    따옴표          아이가 한 말을 옮긴 문장이다
    이름 꼴          「하윤이가」 · 「민이가」처럼 낱말 머리 한두 글자 + 「이가 · 이는 …」 —
                    지금 명단에 없는(지운) 아이 이름일 수 있다

이름 꼴은 「고양이가」 · 「놀이가」 같은 낱말도 버린다. 버리는 쪽으로만 틀리니 예시가 줄 뿐
이름이 새지 않는다. 남은 문장도 초안을 만들 때 사실과 같은 표로 한 번 더 가린다(draft.py).
"""

import re
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.auth.models import User
from app.features.centers.models import Class
from app.features.documents.models import Document, DocumentSection
from app.features.documents.verify import Row, center_children
from app.shared.auth.ownership import own_class_clause
from app.shared.childCode import SubstitutionError, load_pool, table_for_text
from app.shared.gates.judge import split_sentences

# 예시 수. 셋이면 말투가 보이고, 문장당 수십 토큰이라 한 번에 100토큰 남짓 는다(ADR-083).
LIMIT = 3
# 짧은 발췌만 — 긴 문장일수록 장면(누가 · 무엇을)이 따라온다.
MIN_CHARS, MAX_CHARS = 10, 60
# 확정본을 이만큼만 읽는다. 최근 글이 지금 말투에 가깝다.
RECENT_DOCUMENTS = 10

_QUOTES = re.compile(r"[「」『』\"“”'‘’]")
# 외자(「민이가」)도 잡게 한두 글자다.
_NAME_LIKE = re.compile(r"(?<![가-힣])[가-힣]{1,2}이(?:가|는|를|와|랑|도|의|에게|한테|처럼)")


def pick_examples(
    texts: Iterable[str],
    own: Sequence[Row],
    others: Sequence[Row],
    offset: int,
    limit: int = LIMIT,
) -> list[str]:
    """`offset` 으로 돌려 고른다 — 반 전체 초안에서 아이마다 다른 예시를 보게(획일화를 줄인다).

    `own` · `others` 는 초안을 만드는 반과 같은 원 다른 반의 (실명, 가명, 부르는 이름)이다.
    """
    pseudonyms = load_pool()

    def names_child(sentence: str) -> bool:
        try:
            return table_for_text(pseudonyms, own, others, sentence) is not None
        except SubstitutionError:
            return True

    pool: list[str] = []
    for text in texts:
        for sentence in split_sentences(text):
            if not MIN_CHARS <= len(sentence) <= MAX_CHARS or sentence in pool:
                continue
            if _QUOTES.search(sentence) or _NAME_LIKE.search(sentence):
                continue
            if names_child(sentence):
                continue
            pool.append(sentence)
    if not pool:
        return []
    start = offset % len(pool)
    return (pool[start:] + pool[:start])[:limit]


def teacher_examples(session: Session, user: User, class_id: int, child_id: int) -> list[str]:
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
    own, others = center_children(session, class_id)
    return pick_examples(texts, own, others, offset=child_id)
