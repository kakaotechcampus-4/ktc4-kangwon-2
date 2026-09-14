"""LLM Proposal 문자열 정책 (L5).

**오탐 테스트가 핵심이다.** 금지 패턴이 정상 보육 표현을 막으면 Validator가
품질 장치가 아니라 방해물이 된다.
"""

from __future__ import annotations

import pytest

from ssuksak.planning.rules.monthly_llm_text_policy import (
    find_official_claims,
    find_safety_education,
    find_source_identifiers,
    normalize_for_comparison,
)

# ============================================== 정규화


@pytest.mark.parametrize(
    "variant",
    [
        "여름 과일 신체 놀이하기",
        "여름 과일  신체 놀이하기",
        " 여름 과일 신체 놀이하기 ",
        "여름 과일 신체 놀이하기.",
        "여름 과일 신체 놀이하기!",
        "여름 과일 신체 놀이하기~",
        "여름 과일 신체 놀이하기…",
        "「여름 과일 신체 놀이하기」",
        "여름 과일\t신체 놀이하기",
    ],
)
def test_cosmetic_differences_normalize_to_the_same_value(variant):
    assert normalize_for_comparison(variant) == normalize_for_comparison(
        "여름 과일 신체 놀이하기"
    )


@pytest.mark.parametrize(
    "other",
    [
        "여름 과일로 몸을 움직여요",
        "여름 과일 신체 놀이",
        "과일 신체 놀이하기",
        "여름 채소 신체 놀이하기",
    ],
)
def test_genuinely_different_wording_stays_different(other):
    """의미가 비슷해도 코드가 같다고 판정하지 않는다."""
    assert normalize_for_comparison(other) != normalize_for_comparison(
        "여름 과일 신체 놀이하기"
    )


def test_fullwidth_and_halfwidth_normalize_together():
    assert normalize_for_comparison("（여름）놀이") == normalize_for_comparison("(여름)놀이")


def test_empty_text_normalizes_to_empty():
    assert normalize_for_comparison("   ") == ""


# ============================================== 금지 Claim


@pytest.mark.parametrize(
    "text",
    [
        "법적으로 반드시 포함해야 하는 활동입니다.",
        "법령에 따라 편성했습니다.",
        "법정 기준에 맞춘 순서입니다.",
        "의무적으로 실시하는 놀이입니다.",
        "반드시 실시해야 합니다.",
        "공식 권장 순서를 따랐습니다.",
        "공식적으로 권장되는 배치입니다.",
        "국가 기준에 따른 구성입니다.",
        "국가에서 정한 순서입니다.",
        "누리과정에서 반드시 다루어야 합니다.",
        "누리과정 기준 순서로 배치했습니다.",
        "표준 주차 구성입니다.",
        "표준 순서를 따랐습니다.",
        "평가제 통과 기준을 만족합니다.",
    ],
)
def test_official_and_legal_claims_are_detected(text):
    assert find_official_claims(text)


@pytest.mark.parametrize(
    "text",
    [
        "여름 자연을 탐색하는 흐름으로 구성했습니다.",
        "아이들이 반드시 즐거워할 놀이입니다.",
        "손을 반드시 씻고 놀이를 시작해요.",
        "교사가 권장하는 방법으로 놀이를 안내합니다.",
        "우리 반 아이들의 관심을 기준으로 배치했습니다.",
        "놀이 순서는 아이들의 반응에 따라 바뀔 수 있습니다.",
        "표준 크기의 공을 사용해 놀이해요.",
        "국가유산 답사 놀이를 해요.",
    ],
)
def test_normal_phrases_are_not_flagged_as_claims(text):
    """`반드시`·`권장`·`기준`·`표준`이 들어갔다고 막지 않는다."""
    assert not find_official_claims(text)


def test_claim_result_reports_category_not_the_sentence():
    """Violation detail에 원문 문장이 흘러가지 않게 하는 지점이다."""
    hits = find_official_claims("법적으로 반드시 실시해야 합니다.")
    assert "legal_basis" in hits
    for hit in hits:
        assert "법적" not in hit


# ============================================== Safety


@pytest.mark.parametrize(
    "text",
    [
        "이번 주 안전교육은 교통안전입니다.",
        "안전 교육을 실시합니다.",
        "법정 안전교육 시간을 포함했습니다.",
        "교통안전 교육을 진행해요.",
        "실종·유괴 예방 교육을 해요.",
        "약물 오남용 예방 교육을 합니다.",
        "성폭력 예방 교육을 실시해요.",
        "아동학대 예방 교육을 진행합니다.",
        "소방 훈련을 실시합니다.",
        "지진 훈련을 해요.",
        "심폐소생술을 배워요.",
    ],
)
def test_statutory_safety_education_is_detected(text):
    assert find_safety_education(text)


@pytest.mark.parametrize(
    "text",
    [
        "안전 약속을 지키며 놀이터를 이용해요.",
        "친구와 안전하게 놀이해요.",
        "놀이 기구를 안전하게 사용하는 방법을 이야기 나눠요.",
        "안전한 그늘에서 휴식해요.",
        "교통기관 놀이를 하며 신호등을 만들어요.",
        "우리 동네 교통기관을 살펴봐요.",
        "교육적인 놀이를 계획했습니다.",
    ],
)
def test_normal_safety_wording_is_not_flagged(text):
    """`안전` 한 단어로 막으면 정상 바깥놀이 표현이 거부된다."""
    assert not find_safety_education(text)


# ============================================== 식별자 누출


@pytest.mark.parametrize(
    "text,expected",
    [
        ("E06 근거를 참고해 구성했어요.", "evidence_ref"),
        ("출처 S1의 사례를 참고했습니다.", "source_group"),
        ("ev_a83b8c06154a 기록을 반영했습니다.", "record_id"),
    ],
)
def test_grounding_identifiers_in_visible_text_are_detected(text, expected):
    assert expected in find_source_identifiers(text)


def test_institution_name_in_visible_text_is_detected():
    found = find_source_identifiers(
        "가어린이집 사례처럼 놀이해요.",
        institution_names=frozenset({"가어린이집", "나어린이집"}),
    )
    assert "institution_name" in found


@pytest.mark.parametrize(
    "text",
    [
        "여름 과일 신체 놀이하기",
        "우리 동네 지도 보며 산책하기",
        "5월의 놀이를 계획했어요.",
        "2026년 여름을 즐겨요.",
    ],
)
def test_normal_text_has_no_identifier_leakage(text):
    assert not find_source_identifiers(
        text, institution_names=frozenset({"가어린이집"})
    )


def test_unrelated_institution_names_do_not_match():
    assert not find_source_identifiers(
        "우리 동네를 산책해요.", institution_names=frozenset({"가어린이집"})
    )
