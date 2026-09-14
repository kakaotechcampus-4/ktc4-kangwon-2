"""LLM Proposal 문자열 정책 (L5).

**결정론적 문자열 규칙만 둔다.** 의미 유사도를 추측하지 않는다 — 그것은 코드가
할 수 없는 일이고, 할 수 있는 척하면 오탐으로 정상 계획안을 막는다.

세 종류를 판정한다.

    정규화        비교를 위한 표준형 (공백·문장부호·유니코드 차이 흡수)
    금지 Claim    법적·공식 권위를 주장하는 표현
    Safety 누출   법정 안전교육을 생성·배치하려는 표현

패턴을 **좁게** 시작한다. `안전`·`교육`·`놀이` 같은 일반 단어만으로 막지 않는다.
`안전 약속을 지키며 놀이터를 이용해요`는 정상 활동 표현이지 법정 안전교육이
아니다. 오탐을 테스트로 고정한다.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "OFFICIAL_CLAIM_PATTERNS",
    "SAFETY_EDUCATION_PATTERNS",
    "find_official_claims",
    "find_safety_education",
    "find_source_identifiers",
    "normalize_for_comparison",
]

_PUNCTUATION = re.compile(r"[.,!?~·・…\"'`“”‘’()\[\]{}<>《》「」『』:;\-–—/\\]+")
_SPACES = re.compile(r"\s+")


def normalize_for_comparison(text: str) -> str:
    """Exact-copy 비교용 표준형.

    같은 문장을 다르게 적은 것을 같게 만든다. **의미를 보지 않는다.**

        "여름 과일 신체 놀이하기"
        "여름 과일  신체 놀이하기 "
        "여름 과일 신체 놀이하기."

    셋 다 같은 값이 된다. 반면 `여름 과일로 몸을 움직여요`는 다른 값이다 —
    의미가 비슷해도 코드가 같다고 판정하지 않는다.

    NFKC를 쓰는 이유: 전각/반각과 호환 문자를 흡수해야 `Ａ`와 `A`,
    `（` 와 `(` 가 갈라지지 않는다.
    """
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _PUNCTUATION.sub(" ", normalized)
    return _SPACES.sub(" ", normalized).strip().casefold()


# --------------------------------------------------------------- 금지 Claim

OFFICIAL_CLAIM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("legal_basis", r"법\s*적\s*으로"),
    ("legal_basis", r"법령\s*(에|상|에서|에\s*따라)"),
    ("legal_basis", r"법정\s*(기준|요건|시간|의무|교육)"),
    ("mandatory", r"의무\s*적\s*으로"),
    ("mandatory", r"반드시\s*(실시|이수|편성)"),
    ("mandatory", r"(해야|하여야)\s*만\s*합니다"),
    ("official_recommendation", r"공식\s*(적으로\s*)?(권장|지정|인정)"),
    ("official_recommendation", r"국가\s*(기준|표준|지정|에서\s*정한)"),
    ("curriculum_authority", r"누리과정\s*(에서|상|에\s*따라)\s*반드시"),
    ("curriculum_authority", r"누리과정\s*(기준|표준)\s*(순서|주차)"),
    ("standard_order", r"표준\s*(순서|주차|차시)"),
    ("standard_order", r"권장\s*(주차|순서)\s*(입니다|이며|임)"),
    ("assessment", r"평가\s*(제|인증)\s*(통과|합격|기준)"),
)
"""법적·공식 권위를 주장하는 표현.

각 항목은 `(범주, 정규식)`이다. 범주는 Violation detail에 쓰며 어떤 종류의
주장인지 사람이 바로 알 수 있게 한다.

**`반드시` 한 단어로 막지 않는다.** `반드시 손을 씻어요`는 정상 문장이다.
`반드시 실시`처럼 시행 의무를 주장할 때만 잡는다.

근거: CLAUDE.md §5(LLM은 법정 기준을 판단하지 않는다),
docs/demo-source-of-truth.md 금지 표현, OD-N14 UI 정책
(`공식 권장 1주차` · `누리과정 기준 순서` · `표준 주차` 금지).
"""

SAFETY_EDUCATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("safety_education", r"안전\s*교육"),
    ("safety_education", r"법정\s*안전"),
    (
        # 법정 안전교육 별표6 구분명 + (예방/대비/관리) + 교육/훈련.
        # `실종·유괴 예방 교육`처럼 구분명과 `교육` 사이에 말이 끼는 실제 표기를
        # 흡수한다. 구분명 없이 `교육` 한 단어만으로는 걸리지 않는다.
        "statutory_category",
        r"(교통안전|생활안전|재난\s*대비|실종[\s·・\-]*유괴|"
        r"약물\s*(?:오남용|오용[\s·・\-]*남용)|"
        r"성폭력\s*예방|아동학대\s*예방|감염병\s*예방)"
        r"(?:\s*(?:예방|대비|관리|등))*\s*(교육|훈련)",
    ),
    ("drill", r"(소방|대피|비상\s*대응|지진)\s*훈련"),
    ("drill", r"심폐소생술"),
)
"""법정 안전교육을 **생성·배치**하려는 표현.

Proposal Schema에 Safety 자리가 없어도 자유 문자열 안에 끼워 넣을 수 있다.

**좁게 시작한다.** `안전` 한 단어로 막지 않는다 —
`안전 약속을 지키며 놀이터를 이용해요`는 바깥놀이 활동이지 법정 안전교육이
아니며, 그것까지 막으면 정상 계획안이 거부된다.
`안전교육`처럼 복합어이거나 법정 구분명 + `교육/훈련`일 때만 잡는다.
"""

_OFFICIAL = tuple((kind, re.compile(p)) for kind, p in OFFICIAL_CLAIM_PATTERNS)
_SAFETY = tuple((kind, re.compile(p)) for kind, p in SAFETY_EDUCATION_PATTERNS)


def _scan(text: str, compiled) -> tuple[str, ...]:
    """걸린 **범주**만 돌려준다. 매칭된 원문 조각을 돌려주지 않는다.

    Violation detail에 문장이 흘러 들어가지 않게 하는 지점이다(§24).
    """
    hits = [kind for kind, pattern in compiled if pattern.search(text)]
    return tuple(dict.fromkeys(hits))


def find_official_claims(text: str) -> tuple[str, ...]:
    """법적·공식 권위 주장 범주. 없으면 빈 tuple."""
    return _scan(unicodedata.normalize("NFKC", text), _OFFICIAL)


def find_safety_education(text: str) -> tuple[str, ...]:
    """법정 안전교육 생성 범주. 없으면 빈 tuple."""
    return _scan(unicodedata.normalize("NFKC", text), _SAFETY)


# ------------------------------------------------------------ 식별자 누출

_REF_TOKEN = re.compile(r"(?<![0-9A-Za-z])E\d{2,}(?![0-9])")
_SOURCE_GROUP_TOKEN = re.compile(r"(?<![0-9A-Za-z])S\d{1,3}(?![0-9])")
_RECORD_ID_TOKEN = re.compile(r"\bev_[0-9a-f]{6,}")


def find_source_identifiers(
    text: str, *, institution_names: frozenset[str] = frozenset()
) -> tuple[str, ...]:
    """사용자에게 보이는 문자열에 Grounding 내부 식별자가 있는지.

    검사 대상은 `activity.value` · `experience` · `month_flow_rationale`처럼
    **화면에 나가는 문자열**이다. `grounding_refs=["E06"]` 같은 metadata는
    정상이므로 검사하지 않는다.

    Args:
        institution_names: Packet audit의 실제 기관명. Planner에게 준 적이
            없는 값이므로 결과에 나타나면 어디선가 샌 것이다.
    """
    found: list[str] = []
    if _REF_TOKEN.search(text):
        found.append("evidence_ref")
    if _SOURCE_GROUP_TOKEN.search(text):
        found.append("source_group")
    if _RECORD_ID_TOKEN.search(text):
        found.append("record_id")
    for name in institution_names:
        if name and name in text:
            found.append("institution_name")
            break
    return tuple(dict.fromkeys(found))
