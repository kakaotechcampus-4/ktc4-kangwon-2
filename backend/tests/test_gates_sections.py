"""shared/gates 3층 규격 검사 단위 테스트. DB 를 쓰지 않는다."""

from dataclasses import dataclass, field

from app.shared.gates.sections import check_sections, join_facts

FACTS = ["블록을 3번 쌓았다가 무너뜨렸다.", "9월 22일에 친구 2명과 함께 놀았다."]
SUPPORT = "다음 주에 블록 영역을 넓혀 4회 더 함께 쌓아 보도록 지원한다."


@dataclass
class Section:
    heading: str
    body: str
    source_ids: list[int] = field(default_factory=lambda: [1, 2])


def _check(interpretation: str, facts: list[str] = FACTS) -> list[str]:
    sections = [
        Section("사실", join_facts(facts)),
        Section("해석", interpretation),
        Section("지원", SUPPORT),
    ]
    return check_sections(sections, facts, {1, 2})


def test_empty_facts_reject_the_document_even_when_interpretation_and_support_are_long():
    # 교사가 칸을 하나도 안 채운 일일 보육일지다. 해석 · 지원이 기댈 사실이 없다.
    sections = [
        Section("사실", "", []),
        Section("해석", "x" * 30, []),
        Section("지원", SUPPORT, []),
    ]

    assert check_sections(sections, [], set()) == ["sections.사실"]


def test_numbers_in_interpretation_that_appear_in_facts_pass():
    assert _check("블록을 3번 쌓으며 9월 22일 친구 2명과 협력하는 모습을 보였다.") == []


def test_number_missing_from_facts_rejects_interpretation():
    assert _check("블록을 5번 쌓으며 끈기 있게 반복하는 모습을 보여 주었다.") == ["sections.해석"]


def test_wrong_date_rejects_interpretation():
    assert _check("9월 23일에 친구와 함께 노는 모습에서 사회성이 자라고 있다.") == ["sections.해석"]


def test_numbers_are_compared_whole_not_as_substrings():
    # 사실에 「22」 가 있어도 해석의 「2」 는 없는 숫자다.
    interpretation = "친구 2명과 노는 모습에서 사회성이 자라고 있음을 볼 수 있다."
    assert _check(interpretation, facts=["22일에 놀았다."]) == ["sections.해석"]


def test_new_numbers_in_support_are_allowed():
    # SUPPORT 의 「4회」 는 사실에 없지만 지원이라 통과한다.
    assert _check("블록을 반복해서 쌓으며 끈기 있게 도전하는 모습을 보였다.") == []


def test_short_interpretation_is_reported_once():
    assert _check("7번 쌓음") == ["sections.해석"]
