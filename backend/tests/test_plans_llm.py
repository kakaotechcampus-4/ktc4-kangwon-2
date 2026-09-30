"""주제 생성기. **모델이 준 것을 그대로 믿지 않는지**를 본다.

진짜 엘리스를 부르지 않는다 — 전송 계층을 갈아끼워 응답만 흉내 낸다. 확인할 것은
「엘리스가 잘 답하나」가 아니라 「엘리스가 이상하게 답했을 때 우리가 막나」다.
"""

import json

import pytest
from ssuksak.planning.application.ports import OptionalContextResult  # noqa: F401
from ssuksak.planning.application.yearly_ports import ThemeTextRequest
from ssuksak.planning.domain.year_month import YearMonth

from app.features.plans.llm import (
    EliceThemeTextGenerator,
    ThemeTextBudgetExceeded,
    ThemeTextFailed,
    ThemeTextUnavailable,
)

BASE = "https://mlapi.example.com/v1"
KEY = "test-only-not-a-secret"


# 학년도는 3월에 시작해 익년 2월에 끝난다.
ACADEMIC_MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


def _requests(count=2):
    return tuple(
        ThemeTextRequest(
            period=YearMonth(2026 if index < 10 else 2027, ACADEMIC_MONTHS[index]),
            theme_id=f"theme_{index}",
            reference_label=f"참고 주제 {index}",
            target_ages=(3,),
        )
        for index in range(count)
    )


def _answers(content: str):
    """엘리스가 이 내용을 돌려준 것처럼 만든다."""

    def transport(url, *, headers, payload, timeout):
        assert headers["Authorization"] == f"Bearer {KEY}"
        # 온도가 0 이어야 같은 입력에 같은 계획안이 나온다.
        assert payload["temperature"] == 0
        assert payload["response_format"] == {"type": "json_object"}
        return {"choices": [{"message": {"content": content}}]}

    return EliceThemeTextGenerator(BASE, KEY, transport=transport)


def test_열두_달을_한_번에_보내고_받는다():
    sent = {}

    def transport(url, *, headers, payload, timeout):
        sent["user"] = json.loads(payload["messages"][1]["content"])
        themes = [
            {"theme_id": month["theme_id"], "value": f"만든 주제 {month['month']}"}
            for month in sent["user"]["months"]
        ]
        return {"choices": [{"message": {"content": json.dumps({"themes": themes})}}]}

    generator = EliceThemeTextGenerator(BASE, KEY, transport=transport)

    results = generator.generate(_requests(12))

    # 호출은 한 번이다. 달마다 부르면 12배고 문체가 갈린다.
    assert len(sent["user"]["months"]) == 12
    assert len(results) == 12
    assert results[0].value == "만든 주제 3"
    assert [r.period.calendar_month for r in results] == list(ACADEMIC_MONTHS)


def test_달이_빠지면_거부한다():
    """조용히 채우면 교사는 열두 달이 다 있는 줄 알고 확정한다."""
    generator = _answers(json.dumps({"themes": [{"theme_id": "theme_0", "value": "하나만"}]}))

    with pytest.raises(ThemeTextFailed, match="빠진 달"):
        generator.generate(_requests(2))


def test_요청하지_않은_달이_오면_거부한다():
    generator = _answers(json.dumps({"themes": [{"theme_id": "지어낸것", "value": "엉뚱한 주제"}]}))

    with pytest.raises(ThemeTextFailed, match="요청하지 않은"):
        generator.generate(_requests(1))


def test_같은_달이_두_번_오면_거부한다():
    generator = _answers(
        json.dumps(
            {
                "themes": [
                    {"theme_id": "theme_0", "value": "첫 번째"},
                    {"theme_id": "theme_0", "value": "두 번째"},
                ]
            }
        )
    )

    with pytest.raises(ThemeTextFailed, match="두 번"):
        generator.generate(_requests(1))


@pytest.mark.parametrize("value", ["", "   "])
def test_빈_주제는_거부한다(value):
    generator = _answers(json.dumps({"themes": [{"theme_id": "theme_0", "value": value}]}))

    with pytest.raises(ThemeTextFailed, match="비었다"):
        generator.generate(_requests(1))


@pytest.mark.parametrize("content", ["JSON 이 아닌 말", '{"다른키": []}', '{"themes": "배열아님"}'])
def test_형식이_다르면_거부한다(content):
    with pytest.raises(ThemeTextFailed):
        _answers(content).generate(_requests(1))


def test_설정이_틀리면_부르기_전에_막는다():
    with pytest.raises(ThemeTextUnavailable, match="https"):
        EliceThemeTextGenerator("http://평문주소", KEY)
    with pytest.raises(ThemeTextUnavailable, match="API_KEY"):
        EliceThemeTextGenerator(BASE, "   ")


def test_한도에_걸리면_재시도로_안_풀린다고_알린다():
    """401 은 키가 지워졌다는 뜻이고 429 는 한도다. 재시도 버튼을 띄우면 안 된다."""
    from urllib import error as urllib_error

    def transport(url, *, headers, payload, timeout):
        raise urllib_error.HTTPError(url, 429, "Too Many Requests", {}, None)

    generator = EliceThemeTextGenerator(BASE, KEY, transport=_wrap(transport))

    with pytest.raises(ThemeTextBudgetExceeded):
        generator.generate(_requests(1))


def _wrap(raw):
    """진짜 전송 계층의 오류 변환을 그대로 태운다."""
    from app.features.plans import llm

    def transport(url, *, headers, payload, timeout):
        original = llm.urllib_request.urlopen
        try:
            llm.urllib_request.urlopen = lambda *a, **k: raw(
                url, headers=headers, payload=payload, timeout=timeout
            )
            return llm._post_json(url, headers=headers, payload=payload, timeout=timeout)
        finally:
            llm.urllib_request.urlopen = original

    return transport


def test_빈_요청이면_부르지_않는다():
    def transport(url, **kwargs):
        raise AssertionError("부르면 안 된다")

    assert EliceThemeTextGenerator(BASE, KEY, transport=transport).generate(()) == ()
