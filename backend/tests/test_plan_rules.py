"""연간계획안 검사기 (ADR-014).

법령 원본은 p0-planning 쪽 파일 하나뿐이라(ADR-014) 테스트도 그 파일을 그대로 읽는다.
값을 복사해 오면 원본이 바뀌어도 테스트가 통과한다.
"""

import json

import pytest

from app.features.plans.rules.verify import (
    SCHOOL_YEAR_MONTHS,
    UNVERIFIED,
    VIOLATION,
    PlannedActivity,
    age,
    legal_hours,
    load_legal_rules,
)

CATEGORY_COUNT = 6


def months(placement: dict[int, list[str]] | None = None, state: str = "SOURCE_REQUIRED"):
    """12개월 배열을 만든다. placement 에 준 달만 값이 들어간다."""
    placement = placement or {}
    return [
        {
            "month": m,
            "safety_education": placement.get(m, []),
            "safety_education_state": state,
        }
        for m in SCHOOL_YEAR_MONTHS
    ]


def test_법령_파일이_6구분_44시간이다():
    rules = load_legal_rules()
    assert len(rules["categories"]) == CATEGORY_COUNT
    assert rules["derived_totals"]["annual_hours_min_sum"] == 44


def test_배치_계획이_없으면_위반이라고_하지_않는다():
    """P0 의 기본 상태다. 충족도 위반도 주장하지 않는다."""
    found = legal_hours(months())

    assert all(v.severity == UNVERIFIED for v in found)
    assert len(found) == CATEGORY_COUNT * 2  # 구분마다 주기 하나 · 시수 하나


def test_배치를_아는데_한_번도_없으면_위반이다():
    found = legal_hours(months(state="NOT_PLACED"))
    breaches = [v for v in found if v.severity == VIOLATION]

    assert len(breaches) == CATEGORY_COUNT
    assert all(v.month == 3 for v in breaches)
    assert "12개월 동안" in breaches[0].detail


def test_주기를_지키면_위반이_없다():
    """교통안전은 2개월에 1회 이상이다."""
    placed = {m: ["traffic_safety"] for m in (3, 5, 7, 9, 11, 1)}
    found = legal_hours(months(placed, state="PLACED"))

    assert not [v for v in found if v.severity == VIOLATION and "교통안전" in v.detail]


def test_학년도_첫_구간이_비면_위반이다():
    """3·4월에 없으면 첫 2개월이 빈다. 앞뒤 구간도 구간으로 센다."""
    placed = {m: ["traffic_safety"] for m in (5, 7, 9, 11, 1)}
    found = legal_hours(months(placed, state="PLACED"))
    breaches = [v for v in found if v.severity == VIOLATION and "교통안전" in v.detail]

    assert len(breaches) == 1
    assert breaches[0].month == 3
    assert "3월부터 4월까지 2개월" in breaches[0].detail


def test_시수는_배치를_알아도_확인할_수_없다():
    """연간계획안에 교육 시간을 적는 칸이 없다. 셀 방법이 없으므로 셌다고 하지 않는다."""
    placed = {m: ["traffic_safety"] for m in (3, 5, 7, 9, 11, 1)}
    found = legal_hours(months(placed, state="PLACED"))

    hours = [v for v in found if "시간" in v.detail]
    assert len(hours) == CATEGORY_COUNT
    assert all(v.severity == UNVERIFIED for v in hours)


def test_달_순서가_틀리면_거부한다():
    """주기 계산이 배열 순서를 그대로 믿는다. 틀린 순서로 세면 없는 위반이 나온다."""
    with pytest.raises(ValueError, match="3월부터"):
        legal_hours(months()[::-1])


def test_혼합반은_세_연령을_다_지원해야_한다():
    found = age([PlannedActivity(5, "가위로 오리기", 4, 5)], class_age_min=3, class_age_max=5)

    assert len(found) == 1
    assert found[0].severity == VIOLATION
    assert found[0].month == 5
    assert "3~5세입니다" in found[0].detail


def test_반_연령을_덮으면_통과한다():
    wide = PlannedActivity(5, "봄 산책", 3, 5)
    assert age([wide], class_age_min=3, class_age_max=5) == []
    assert age([wide], class_age_min=4, class_age_max=4) == []


def test_반_연령_범위가_뒤집히면_거부한다():
    with pytest.raises(ValueError, match="뒤집"):
        age([], class_age_min=5, class_age_max=3)


def test_승인되지_않은_법령_파일은_거부한다():
    """사람 검토를 안 거친 기준으로 교사를 막지 않는다."""
    rules = json.loads(json.dumps(load_legal_rules()))
    rules["review"]["domain_owner_approval"] = "PENDING"
    rules["review"]["runtime_active"] = True

    with pytest.raises(ValueError, match="승인되지 않은"):
        legal_hours(months(), rules)


def test_법정_6구분_밖의_값은_거부한다():
    """조용히 무시하면 배치된 달을 빈 달로 세어 없는 위반이 나온다."""
    with pytest.raises(ValueError, match="생활안전"):
        legal_hours(months({5: ["생활안전"]}, state="PLACED"))
