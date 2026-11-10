"""shared/gates 3층 규격 검사 단위 테스트. DB 를 쓰지 않는다."""

import datetime
from dataclasses import dataclass, field

from app.shared.gates.sections import InputExtras, check_sections, join_facts, logger

FACTS = ["블록을 3번 쌓았다가 무너뜨렸다.", "9월 22일에 친구 2명과 함께 놀았다."]
SUPPORT = "다음 주에 블록 영역을 넓혀 4회 더 함께 쌓아 보도록 지원한다."


@dataclass
class Section:
    heading: str
    body: str
    source_ids: list[int] = field(default_factory=lambda: [1, 2])


def _check(
    interpretation: str, facts: list[str] = FACTS, extras: InputExtras | None = None
) -> list[str]:
    sections = [
        Section("사실", join_facts(facts)),
        Section("해석", interpretation),
        Section("지원", SUPPORT),
    ]
    if extras is None:
        return check_sections(sections, facts, {1, 2}, stage="generate")
    return check_sections(sections, facts, {1, 2}, stage="generate", extras=extras)


def test_empty_facts_reject_the_document_even_when_interpretation_and_support_are_long():
    # 교사가 칸을 하나도 안 채운 일일 보육일지다. 해석 · 지원이 기댈 사실이 없다.
    sections = [
        Section("사실", "", []),
        Section("해석", "x" * 30, []),
        Section("지원", SUPPORT, []),
    ]

    # 근거도 비어 있어 칸마다 source_ids 도 같이 걸린다.
    assert check_sections(sections, [], set(), stage="generate")[0] == "sections.사실"


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


def test_class_age_and_nuri_domain_count_are_not_compared_with_facts():
    """#85 — 반 연령 · 누리과정 영역 수는 문서 바깥에서 오는 값이라 사실에 없어도 된다."""
    four = InputExtras(ages=(4,))
    age = "만 4세 유아답게 블록을 쌓으며 끝까지 해 보려는 모습을 보였다."
    assert _check(age, extras=four) == []
    assert _check("블록 놀이가 누리과정 5개 영역 중 신체운동 · 건강과 이어진다.") == []


def test_age_outside_the_class_and_counts_are_still_compared():
    # 만 4세 반 문서에 「만 5세」는 반 연령이 아니다. 「5개」도 영역 수가 아니면 개수다.
    four = InputExtras(ages=(4,))
    assert _check("만 5세 유아답게 블록을 쌓으며 끝까지 해 보려는 모습을 보였다.", extras=four) == [
        "sections.해석"
    ]
    assert _check("블록을 5개 쌓으며 끈기 있게 반복하는 모습을 보여 주었다.", extras=four) == [
        "sections.해석"
    ]
    assert _check("블록 놀이가 4개 영역의 배움과 두루 이어지는 모습을 보였다.") == ["sections.해석"]


def test_decimal_in_a_date_or_period_is_one_number():
    # 「1.5일」은 1 과 5 가 아니라 1.5 하나다. 사실과 같으면 통과, 사실에 없으면 거절.
    facts = ["블록 탑을 1.5일에 걸쳐 완성했다."]
    assert _check("블록 탑을 1.5일에 걸쳐 끝까지 완성하려는 끈기를 보였다.", facts=facts) == []
    assert _check("블록 탑을 2.5일에 걸쳐 끝까지 완성하려는 끈기를 보였다.", facts=facts) == [
        "sections.해석"
    ]


def test_source_date_passes_only_inside_a_real_date():
    # 근거 날짜가 11월 3일이다. 「11월 3일」의 3 은 날짜라 통과,
    # 「3일 동안」의 3 은 기간이라 사실과 견준다.
    third = InputExtras(dates=(datetime.date(2026, 11, 3),))
    plain = ["블록을 쌓았다가 무너뜨렸다."]
    assert (
        _check("11월 3일 블록을 쌓으며 친구와 협력하는 모습을 보였다.", facts=plain, extras=third)
        == []
    )
    assert (
        _check("3일에 블록을 쌓으며 친구와 협력하는 모습을 보였다.", facts=plain, extras=third)
        == []
    )
    for period in ("3일 동안", "3일간", "3일째", "3일 만에"):
        assert _check(
            f"{period} 블록을 쌓으며 끈기 있게 반복하는 모습을 보였다.", facts=plain, extras=third
        ) == ["sections.해석"], period
    # 사실에 같은 기간이 있으면 통과다.
    facts = ["3일 동안 블록을 쌓았다."]
    assert _check("3일 동안 블록을 쌓으며 끈기 있게 반복했다.", facts=facts, extras=third) == []
    # 「간식」은 기간이 아니다.
    assert (
        _check("3일 간식 시간에 친구와 나누어 먹는 모습을 보였다.", facts=plain, extras=third) == []
    )


def test_class_age_and_domain_count_in_short_forms():
    four = InputExtras(ages=(4,))
    assert _check("4세반 유아답게 블록을 쌓으며 끝까지 해 보려는 모습을 보였다.", extras=four) == []
    assert _check("5세반 유아답게 블록을 쌓으며 끝까지 해 보려는 모습을 보였다.", extras=four) == [
        "sections.해석"
    ]
    # 「3세트」는 나이가 아니라 개수다.
    three = InputExtras(ages=(3,))
    assert _check(
        "블록을 3세트 쌓으며 끈기 있게 반복하는 모습을 보였다.",
        facts=["블록을 쌓았다."],
        extras=three,
    ) == ["sections.해석"]
    assert _check("블록 놀이가 누리과정 5영역 가운데 신체운동 · 건강과 이어진다.") == []
    assert _check("블록 놀이가 누리과정 4영역 가운데 신체운동 · 건강과 이어진다.") == [
        "sections.해석"
    ]


def test_short_interpretation_is_reported_once():
    assert _check("7번 쌓음") == ["sections.해석"]


def test_rejection_is_logged_with_stage_and_numbers_but_not_text(monkeypatch):
    # 걸린 초안은 저장되지 않는다. 2단이 몇 건을 잡았는지는 이 줄로만 센다.
    lines = []
    # `app.server` 로거는 propagate=False 라 caplog 가 못 본다 (test_llm_usage_log 와 같다).
    monkeypatch.setattr(logger, "info", lambda fmt, *args: lines.append(fmt % args))

    _check("블록을 5번 쌓으며 끈기 있게 반복하는 모습을 보여 주었다.")

    assert lines == ["gate_sections stage=generate result=fail fields=sections.해석 numbers=5"]
