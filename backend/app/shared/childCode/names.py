"""등록된 이름에서 교사가 실제로 쓰는 표기를 뽑는다.

children.name 은 "박서준" 인데 교사는 "서준이가 블록을 쌓았다" 라고 쓴다.
등록된 전체 이름만 찾으면 아무것도 안 걸리고 실명이 그대로 LLM 으로 나간다.
치환 장치가 있는데 안 걸리는 게 제일 흔한 실패 경로다.

성을 떼는 것까지만 한다. "서준이" · "준이" 같은 애칭은 다루지 않는다 --
규칙으로 만들면 과잉 치환이 늘고, 정확히 하려면 등록할 때 교사에게
"부르는 이름" 을 받아야 한다(children 컬럼 추가. P1).
"""

# 두 글자 성. 한 글자로 끊으면 "남궁민수" 가 "궁민수" 가 된다.
_TWO_SYLLABLE_SURNAMES = frozenset(
    {"남궁", "황보", "제갈", "사공", "선우", "서문", "독고", "동방", "망절"}
)


def name_variants(full_name: str) -> list[str]:
    """등록 이름과, 성을 뗀 이름을 준다. 긴 것부터다.

        박서준   -> ["박서준", "서준"]
        남궁민수 -> ["남궁민수", "민수"]
        김하나   -> ["김하나", "하나"]      <- "하나" 는 흔한 단어다. 아래 주의 참조
        서준     -> ["서준"]                 두 글자면 성이 없다고 본다

    주의: 성을 뗀 이름이 보통 단어와 겹치면 과잉 치환이 난다.
    "하나도 안 먹었다" 가 "서아도 안 먹었다" 가 된다. 한국어는 낱말 경계가 없어서
    정규식으로 막을 수 없다. 복원하면 원문으로 돌아오므로 유출은 아니고,
    LLM 이 이상한 문장을 보는 비용만 있다. 실명이 새는 것보다 이쪽이 낫다고 봤다.
    """
    name = full_name.strip()
    if not name:
        raise ValueError("이름이 비어 있다")
    variants = [name]
    for length in (2, 1):
        if len(name) > length + 1 and (length == 1 or name[:2] in _TWO_SYLLABLE_SURNAMES):
            given = name[length:]
            if given not in variants:
                variants.append(given)
            break
    return variants
