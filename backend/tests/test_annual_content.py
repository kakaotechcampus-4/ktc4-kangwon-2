"""연간 소주제의 문서 단위 생성 계약. 실제 모델 대신 고정 전송 응답을 쓴다."""

import json

import pytest

from app.features.plans.annual_content import parse_subthemes
from app.shared.llm import LlmFailed

MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


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

    from app.features.plans import annual_content

    plan = SimpleNamespace(
        target_ages=frozenset({3, 4, 5}),
        periods=tuple(
            SimpleNamespace(
                period=SimpleNamespace(calendar_month=month),
                theme=SimpleNamespace(value=f"주제 {month}"),
            )
            for month in MONTHS
        ),
    )
    calls = []

    def complete(system, user, **kwargs):
        calls.append(json.loads(user))
        return json.dumps(answer())

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    result = annual_content.generate_subthemes(plan)
    assert len(result) == 12
    assert len(calls) == 1
    assert calls[0]["target_ages"] == [3, 4, 5]
    assert [month["month"] for month in calls[0]["months"]] == list(MONTHS)
