"""아동 실명 치환 (ADR-004).

치환이 조용히 실패하면 실명이 LLM 으로 나간다. 그래서 실패 경로를 전부 본다.
"""

import pytest

from app.shared.childCode import (
    NameTable,
    PseudonymPool,
    SubstitutionError,
    has_final,
    load_pool,
    mask,
    name_variants,
    unmask,
)

# ── 받침 ──────────────────────────────────────────────


def test_받침_판정():
    assert has_final("박서준") is True  # 준 - ㄴ
    assert has_final("김하나") is False  # 나
    assert has_final("한솔") is True  # 솔 - ㄹ
    assert has_final("Kevin") is False  # 한글이 아니면 받침 없음으로 본다


# ── 이름 변형 ─────────────────────────────────────────


def test_성을_뗀_이름도_찾는다():
    # 교사는 "서준이가 블록을 쌓았다" 라고 쓴다. 등록 이름만 찾으면 안 걸린다.
    assert name_variants("박서준") == ["박서준", "서준"]


def test_두_글자_성을_끊지_않는다():
    # 한 글자로 끊으면 "궁민수" 가 된다.
    assert name_variants("남궁민수") == ["남궁민수", "민수"]


def test_두_글자_이름은_성이_없다고_본다():
    assert name_variants("서준") == ["서준"]


def test_성을_떼면_한_글자만_남으면_떼지_않는다():
    """PR #40 리뷰. 세 글자 두 글자 성이 여기 걸린다.

    "남궁민" 을 한 글자 성으로 끊으면 "궁민" 이 나와 엉뚱한 곳이 치환된다.
    바르게 떼면 "민" 인데, 한 글자를 치환 대상에 넣으면 본문의 아무 "민" 이나 바뀐다.
    둘 다 안 되므로 등록 이름만 찾는다.
    """
    assert name_variants("남궁민") == ["남궁민"]
    assert name_variants("선우진") == ["선우진"]


def test_목록에_없는_성은_한_글자로_본다():
    """대부분의 한국 성이 한 글자다. 목록을 늘리는 것으로는 다 못 막는다 --
    근본 해결은 등록할 때 성과 이름을 따로 받는 것이다(별도 PR)."""
    assert name_variants("응우옌티한") == ["응우옌티한", "우옌티한"]


# ── 가명 발급 ─────────────────────────────────────────


def test_가명_Pool_이_받침이_같은_이름을_준다():
    pool = load_pool()
    assert has_final(pool.allocate("박서준", set())) is True
    assert has_final(pool.allocate("김하나", set())) is False


def test_같은_반에서_이미_쓴_가명을_다시_주지_않는다():
    pool = load_pool()
    taken: set[str] = set()
    for _ in range(20):  # 한 반 정원
        code = pool.allocate("박서준", taken)
        assert code not in taken
        taken.add(code)


def test_가명이_동나면_다른_묶음에서_꺼내지_않는다():
    # 조사가 틀어지느니 에러를 낸다.
    pool = PseudonymPool(with_final=["민준"], without_final=["서아"])
    assert pool.allocate("박서준", set()) == "민준"
    with pytest.raises(SubstitutionError, match="모자란다"):
        pool.allocate("박서준", {"민준"})


# ── 치환 ─────────────────────────────────────────────


def test_치환하고_되돌리면_원문이_나온다():
    table = NameTable({"박서준": "민준", "김하나": "서아"})
    text = "박서준이 블록을 쌓고 김하나가 옆에서 보았다."
    masked = mask(text, table)
    assert "박서준" not in masked
    assert "김하나" not in masked
    assert unmask(masked, table) == text


def test_교사가_성을_빼고_써도_걸린다():
    # 이게 제일 흔한 실패 경로다. 등록은 "박서준" 인데 교사는 "서준이" 라고 쓴다.
    table = NameTable({"박서준": "민준"})
    assert mask("서준이가 블록을 쌓았다", table) == "민준이가 블록을 쌓았다"


def test_되돌리면_등록된_전체_이름이_나온다():
    # 성을 뗀 표기로 들어갔어도 복원은 등록 이름으로 한다.
    table = NameTable({"박서준": "민준"})
    assert unmask(mask("서준이가 놀았다", table), table) == "박서준이가 놀았다"


def test_긴_이름을_먼저_바꾼다():
    # "서준" 을 먼저 바꾸면 "서준호" 가 "민준호" 가 된다.
    table = NameTable({"노서준": "민준", "황서준호": "서아"})
    assert mask("서준호와 서준", table) == "서아와 민준"


def test_가명을_또_치환하지_않는다():
    # 한 번 넣은 가명이 다음 규칙에 걸리면 안 된다.
    table = NameTable({"박민준": "도현", "최유찬": "서준"})
    assert mask("박민준과 유찬", table) == "도현과 서준"


def test_이름이_없으면_원문_그대로다():
    # 계획안은 반 단위 문서라 아이 이름이 없다.
    table = NameTable({})
    assert mask("3월 주제는 봄과 나", table) == "3월 주제는 봄과 나"
    assert unmask("3월 주제는 봄과 나", table) == "3월 주제는 봄과 나"


# ── 거부 ─────────────────────────────────────────────


def test_받침이_다른_가명은_거부한다():
    # 이걸 허용하면 "박서준이" -> "서아가" -> "박서준가" 로 조사가 틀어진다.
    with pytest.raises(SubstitutionError, match="받침이 다른"):
        NameTable({"박서준": "서아"})


def test_실명과_같은_가명은_거부한다():
    with pytest.raises(SubstitutionError, match="같다"):
        NameTable({"박서준": "박서준"})


def test_빈_값은_거부한다():
    with pytest.raises(SubstitutionError):
        NameTable({"박서준": ""})
    with pytest.raises(SubstitutionError):
        NameTable({"": "민준"})


def test_가명이_중복되면_거부한다():
    # 둘 다 "민준" 이면 복원할 때 어느 실명인지 알 수 없다.
    with pytest.raises(SubstitutionError, match="중복"):
        NameTable({"박서준": "민준", "이서준": "민준"})


def test_가명이_다른_아이의_이름과_겹치면_거부한다():
    # 박민준의 가명이 "도현" 인데 최도현이 같은 반에 있으면,
    # 치환 결과의 "도현" 이 가명인지 실명인지 구분되지 않는다.
    with pytest.raises(SubstitutionError, match="겹친다"):
        NameTable({"박민준": "도현", "최도현": "서준"})


def test_같은_표기를_두_아이가_쓰면_거부한다():
    # 김하나 · 박하나 -> 둘 다 "하나". 되돌릴 때 어느 쪽인지 알 수 없다.
    with pytest.raises(SubstitutionError, match="같은 표기"):
        NameTable({"김하나": "서아", "박하나": "유나"})


def test_문자열이_아니면_거부한다():
    with pytest.raises(SubstitutionError, match="문자열"):
        mask(None, NameTable({}))  # type: ignore[arg-type]


def test_NameTable_이_아니면_거부한다():
    with pytest.raises(SubstitutionError, match="NameTable"):
        mask("박서준", {"박서준": "민준"})  # type: ignore[arg-type]
