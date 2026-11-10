"""등록된 이름에서 교사가 실제로 쓰는 표기를 뽑는다.

children.name 은 "박서준" 인데 교사는 "서준이가 블록을 쌓았다" 라고 쓴다.
등록된 전체 이름만 찾으면 아무것도 안 걸리고 실명이 그대로 LLM 으로 나간다.
치환 장치가 있는데 안 걸리는 게 제일 흔한 실패 경로다.

성을 떼는 것까지만 한다. "서준이" · "준이" 같은 애칭은 다루지 않는다 --
규칙으로 만들면 과잉 치환이 늘어난다.

외자 아이(김민 -> 민)는 성을 떼면 한 글자라 떼지 않는다. 교사는 "민이가" 라고 쓰므로
등록할 때 "부르는 이름"(children.call_name)을 받아 가명표에 넣는다(ADR-004 보완).
"""

import re

# 두 글자 성. 한 글자로 끊으면 "남궁민수" 가 "궁민수" 가 된다.
_TWO_SYLLABLE_SURNAMES = frozenset(
    {"남궁", "황보", "제갈", "사공", "선우", "서문", "독고", "동방", "망절"}
)

# 두 글자 이름(김민)을 「성 + 외자」로 볼 한 글자 성. 흔한 성 가운데, 그 글자로 시작하는
# 아이 이름보다 성으로 쓰이는 일이 더 많은 것만 넣었다 [판단].
# 뺀 것 -- 서 · 하 · 지 · 민 · 도 · 윤 · 유 · 주 · 우 · 채 · 은 · 현 · 진 · 나 · 소 · 선 · 연 ·
# 성 · 원 · 여 · 설 · 시 · 예. 서준 · 하윤 · 지호처럼 성 없이 적은 이름이 흔해서, 넣으면
# 그 아이마다 부르는 이름 칸이 뜨고 "준" · "윤" 한 글자로 글을 막는다.
# 이 · 정 · 한 은 넣었다. 이준 · 정우 · 한결도 있지만 성으로 쓰는 사람이 훨씬 많고,
# 빼면 그 성의 외자 아이 이름이 그대로 나간다. 성 없는 이름이 걸리면 부르는 이름을 적으면 풀린다.
_ONE_SYLLABLE_SURNAMES = frozenset(
    "김이박최정강조장임한오신권황안송전홍고문양손배백허남심노곽차구엄천방공함변염추"
)


def name_variants(full_name: str) -> list[str]:
    """등록 이름과, 성을 뗀 이름을 준다. 긴 것부터다.

        박서준   -> ["박서준", "서준"]
        남궁민수 -> ["남궁민수", "민수"]
        김하나   -> ["김하나", "하나"]      <- "하나" 는 흔한 단어다. 아래 주의 참조
        서준     -> ["서준"]                 "서" 는 성 목록에 없다. 성이 없다고 본다
        김민     -> ["김민"]                 외자. 성을 떼면 한 글자만 남아 떼지 않는다
        남궁민   -> ["남궁민"]               외자. 위와 같다

    **한 글자 성 + 두 글자 이름에만 정확하다.** 그 밖은 등록 이름만 찾는다.
    외자(김민 · 남궁민)는 one_syllable() 이 알려 주고, 부르는 이름으로 메운다.
    추측으로 떼면 "궁민" 같은 조각이 생겨 엉뚱한 곳이 치환된다. 못 가리면 안 뗀다.
    근본 해결은 등록할 때 성과 이름을 따로 받는 것이다(PR #40 리뷰). children 컬럼과
    온보딩 화면이 같이 바뀌므로 별도 PR 로 한다.

    주의: 성을 뗀 이름이 보통 단어와 겹치면 과잉 치환이 난다.
    "하나도 안 먹었다" 가 "서아도 안 먹었다" 가 된다. 한국어는 낱말 경계가 없어서
    정규식으로 막을 수 없다. 복원하면 원문으로 돌아오므로 유출은 아니고,
    LLM 이 이상한 문장을 보는 비용만 있다. 실명이 새는 것보다 이쪽이 낫다고 봤다.
    """
    name = full_name.strip()
    if not name:
        raise ValueError("이름이 비어 있다")
    variants = [name]
    surname = _surname_length(name)
    # 성을 떼고 두 글자 이상 남을 때만 뗀다. 한 글자(민 · 진)를 치환 대상에 넣으면
    # 본문의 아무 "민" 이나 바뀐다. 실명이 새는 것보다 낫다는 균형이 여기서는 깨진다 --
    # 한 글자는 걸리는 양이 너무 많아 문장이 통째로 망가진다.
    if surname and len(name) - surname >= 2:
        variants.append(name[surname:])
    return variants


def one_syllable(full_name: str) -> str | None:
    """외자 아이면 성을 뗀 그 한 글자를 준다. 아니면 None.

        김민 -> "민"    남궁민 -> "민"    서준 -> None    박서준 -> None    민 -> None

    한 글자로 등록한 이름(민)은 그 글자 자체가 치환 대상이라 여기 들지 않는다.
    """
    name = full_name.strip()
    surname = _surname_length(name)
    return name[surname:] if surname and len(name) - surname == 1 else None


def _surname_length(name: str) -> int:
    """성이 몇 글자인가. 가릴 수 없으면 0 이다.

    목록에 있는 두 글자 성이 먼저다 -- "남궁민수" 를 한 글자로 끊으면 "궁민수" 가 된다.
    """
    if name[:2] in _TWO_SYLLABLE_SURNAMES:
        return 2
    # 세 글자 이상이면 첫 글자를 성으로 본다. 한국 이름 대부분이 그렇다.
    if len(name) >= 3:
        return 1
    # 두 글자는 첫 글자가 목록의 성일 때만 외자로 본다(김민). 아니면 성 없는 표기다(서준).
    return 1 if len(name) == 2 and name[0] in _ONE_SYLLABLE_SURNAMES else 0


def call_suffix(full_name: str, call_name: str) -> str:
    """부르는 이름에서 이름 뒤에 붙은 꼴. 가명에 같은 꼴을 붙여 보낸다.

        김민 · 민이   -> "이"     가명 가람 -> 가람이
        이안 · 이안이 -> "이"     (성 없이 적은 이름이 외자로 잡혔을 때)
        김민 · 김민   -> ""

    외자 글자나 등록 이름으로 시작해야 한다. 외자 글자 하나뿐이면 받지 않는다 --
    본문의 아무 "민" 이나 바뀐다. 맞지 않으면 ValueError.
    """
    name, call = full_name.strip(), call_name.strip()
    if call.startswith(name):
        return call[len(name) :]
    syllable = one_syllable(name)
    if syllable and call.startswith(syllable) and call != syllable:
        return call[len(syllable) :]
    raise ValueError(f"부르는 이름이 이름으로 시작하지 않는다: {name} · {call}")


# 외자 뒤에 바로 붙는 꼴 -- 조사 · 부르는 꼴(민아 · 민이 · 민이가 · 민은 · 민을 · 민도 ...).
# 낱말이 「외자 + 이 가운데 하나」로 끝나면 그 글자를 이름으로 본다.
_PARTICLES = (
    *("", "가", "는", "를", "도", "만", "의", "와", "랑", "네", "야", "께"),
    *("한테", "에게", "하고", "처럼", "보다"),
)
_TAILS = frozenset({head + p for head in ("", "이") for p in _PARTICLES} | {"아", "은", "을", "과"})


def bare_words(text: str, syllables: set[str]) -> list[str]:
    """글에서 외자 글자로 시작해 그 뒤가 조사 · 부르는 꼴뿐인 낱말을 찾는다.

    「민이가」 · 「민아」 · 「민」 은 걸리고, 「민속놀이」 · 「고민」 · 「김민이」 는 안 걸린다.
    「봄을」 · 「별을」 처럼 이름이 아닌 말도 걸린다 -- 모르면 이름으로 본다.
    """
    words = re.findall("[가-힣]+", text)
    return sorted({w for w in words if w[0] in syllables and w[1:] in _TAILS})
