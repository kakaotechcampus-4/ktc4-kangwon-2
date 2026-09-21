"""아동 실명 치환 (ADR-004).

치환이 조용히 실패하면 실명이 LLM 으로 나간다. 그래서 실패 경로를 전부 본다.
"""

import pytest

from app.shared.childCode import SubstitutionError, has_final, mask, unmask
from app.shared.childCode.pool import PseudonymPool, load_pool


def test_받침_판정():
    assert has_final("박서준") is True  # 준 - ㄴ
    assert has_final("김하나") is False  # 나
    assert has_final("한솔") is True  # 솔 - ㄹ
    assert has_final("Kevin") is False  # 한글이 아니면 받침 없음으로 본다


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


def test_치환하고_되돌리면_원문이_나온다():
    names = {"박서준": "민준", "김하나": "서아"}
    text = "박서준이 블록을 쌓고 김하나가 옆에서 보았다."
    masked = mask(text, names)
    assert "박서준" not in masked
    assert "김하나" not in masked
    assert unmask(masked, names) == text


def test_긴_이름을_먼저_바꾼다():
    # "서준" 을 먼저 바꾸면 "서준호" 가 "민준호" 가 된다.
    # 받침이 맞아야 하므로 "서준호"(받침 없음)는 받침 없는 가명을 받는다.
    names = {"서준": "민준", "서준호": "서아"}
    assert mask("서준호와 서준", names) == "서아와 민준"


def test_가명을_또_치환하지_않는다():
    # 한 번 넣은 가명이 다음 규칙에 걸리면 안 된다.
    names = {"박서준": "민준", "민준": "도현"}
    assert mask("박서준", names) == "민준"


def test_받침이_다른_가명은_거부한다():
    # 이걸 허용하면 "박서준이" -> "서아가" -> "박서준가" 로 조사가 틀어진다.
    with pytest.raises(SubstitutionError, match="받침이 다른"):
        mask("박서준이 놀았다", {"박서준": "서아"})


def test_실명과_같은_가명은_거부한다():
    with pytest.raises(SubstitutionError, match="같다"):
        mask("박서준", {"박서준": "박서준"})


def test_빈_값은_거부한다():
    with pytest.raises(SubstitutionError):
        mask("박서준", {"박서준": ""})
    with pytest.raises(SubstitutionError):
        mask("박서준", {"": "민준"})


def test_문자열이_아니면_거부한다():
    with pytest.raises(SubstitutionError, match="문자열"):
        mask(None, {})  # type: ignore[arg-type]


def test_가명이_중복되면_되돌리지_않는다():
    # 둘 다 "민준" 이면 복원할 때 어느 실명인지 알 수 없다.
    with pytest.raises(SubstitutionError, match="중복"):
        unmask("민준", {"박서준": "민준", "이서준": "민준"})


def test_이름이_없으면_원문_그대로다():
    # 계획안은 반 단위 문서라 아이 이름이 없다.
    assert mask("3월 주제는 봄과 나", {}) == "3월 주제는 봄과 나"
    assert unmask("3월 주제는 봄과 나", {}) == "3월 주제는 봄과 나"
