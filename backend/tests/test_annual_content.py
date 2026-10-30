"""연간 소주제의 문서 단위 생성 계약. 실제 모델 대신 고정 전송 응답을 쓴다."""

import json

import pytest

from app.features.plans.annual_content import parse_subthemes, subthemes_for_month
from app.shared.llm import LlmFailed

MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


@pytest.mark.parametrize(
    "stored", [{"9": "연간 소주제"}, {"9": [None]}, [], {"9": {"value": "글"}}]
)
def test_corrupt_parent_sidecar_is_not_sent_as_context(stored):
    with pytest.raises(ValueError, match="snapshot"):
        subthemes_for_month(stored, 9)


def test_parent_sidecar_uses_only_the_target_month_and_supports_old_plans():
    assert subthemes_for_month({"9": ["교사 확정값"], "10": ["다른 달"]}, 9) == ("교사 확정값",)
    assert subthemes_for_month(None, 9) == subthemes_for_month({}, 9) == ()
    edited = ["", " ", "긴 문장" * 100] + [f"교사 소주제 {i}" for i in range(8)]
    assert subthemes_for_month({"9": edited}, 9) == tuple(edited)


def answer():
    return {
        "months": [{"month": m, "sub_themes": ["함께 알아보기", "놀이로 만나기"]} for m in MONTHS]
    }


def test_12개월_순서대로_소주제가_검증된다():
    assert list(parse_subthemes(json.dumps(answer()), MONTHS)) == [str(m) for m in MONTHS]


@pytest.mark.parametrize(
    "broken", ["missing", "duplicate", "extra", "blank", "type", "field", "too_many"]
)
def test_잘못된_생성은_조용히_채우지_않는다(broken):
    data = answer()
    if broken == "missing":
        data["months"].pop()
    elif broken == "duplicate":
        data["months"][1]["month"] = 3
    elif broken == "extra":
        data["months"].append({"month": 13, "sub_themes": ["하나", "둘"]})
    elif broken == "blank":
        data["months"][0]["sub_themes"] = ["   ", "둘"]
    elif broken == "type":
        data["months"][0]["month"] = "3"
    elif broken == "field":
        data["months"][0]["safety_education"] = ["traffic_safety"]
    else:
        data["months"][0]["sub_themes"] *= 3
    with pytest.raises(LlmFailed):
        parse_subthemes(json.dumps(data), MONTHS)


def test_모든_달과_연령을_소주제_호출_한번에_보낸다(monkeypatch):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3, 4, 5}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if month >= 3 else 2027, month),
                theme=SimpleNamespace(value=f"주제 {month}"),
            )
            for month in MONTHS
        ),
    )
    calls = []

    def complete(system, user, **kwargs):
        calls.append(json.loads(user))
        return json.dumps(
            {
                "months": [
                    {
                        "month": m["month"],
                        "sub_themes": [f"예상 경험 {i}" for i in range(m["week_count"])],
                    }
                    for m in calls[-1]["months"]
                ]
            }
        )

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    result = annual_content.generate_subthemes(plan)
    assert len(result) == 12
    assert len(calls) == 1
    assert calls[0]["target_ages"] == [3, 4, 5]
    assert [month["month"] for month in calls[0]["months"]] == list(MONTHS)
    assert len(calls[0]["curriculum_context"]["contents"]) == 59
    assert {m["month"]: m["week_count"] for m in calls[0]["months"]}[9] == 5
    assert len(result["9"]) == 5 and len(result["10"]) == 4


def test_생성_소주제가_주차보다_적으면_성공으로_저장하지_않는다(monkeypatch):
    from types import SimpleNamespace

    from ssuksak.planning.domain.year_month import YearMonth

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if m >= 3 else 2027, m),
                theme=SimpleNamespace(value="월별 주제"),
            )
            for m in MONTHS
        ),
    )
    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(
        annual_content, "complete_json", lambda *args, **kwargs: json.dumps(answer())
    )
    with pytest.raises(LlmFailed, match="주차 수"):
        annual_content.generate_subthemes(plan)
