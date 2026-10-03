"""연간 주제 문장을 만든다. 호출과 mock/real 분기는 `shared/llm` 이 한다.

여기 남는 것은 **연간 주제에만 있는 것** 뿐이다 — 프롬프트, 열두 달을 한 번에
보내는 방식, 돌아온 답이 요청한 달과 맞는지 보는 검사.

`p0-planning` 을 건드리지 않는다. 포트(`ThemeTextGenerator`)는 그쪽에 있고 구현은
여기 둔다 — 도메인이 어디서 문장을 얻는지 몰라야 공급자를 갈아끼울 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from ssuksak.planning.application.yearly_ports import ThemeTextRequest, ThemeTextResult

from app.shared.llm import LlmFailed, complete_json, is_mock, require_config

SYSTEM_PROMPT = """너는 어린이집 교사의 연간보육계획안 작성을 돕는다.

주어진 달마다 **주제 문장 하나**를 쓴다. 규칙:

1. 반드시 참고자료의 주제(reference_label)를 벗어나지 않는다. 새 주제를 지어내지 않는다.
2. 한국어로 쓴다. 15자 이내의 명사구로 끝낸다.
3. 대상 연령(target_ages)이 알아들을 수 있는 말을 쓴다.
4. 활동·교구·날짜를 쓰지 않는다. 그건 월간계획안이 정한다.
5. 요청받은 달만 답한다. 빼거나 더하지 않는다.

반드시 아래 JSON 으로만 답한다.

{"themes": [{"theme_id": "<요청받은 그대로>", "value": "<주제 문장>"}]}"""


class EliceThemeTextGenerator:
    """엘리스 MLAPI 로 12개월 주제를 **한 번에** 받는다.

    달마다 따로 부르면 호출이 12배고, 그때마다 문체가 갈린다. 한 번에 보내면
    모델이 열두 달을 같이 보고 흐름을 맞춘다.
    """

    def __init__(self, *, transport=None) -> None:
        require_config()
        self._transport = transport

    def generate(self, requests: tuple[ThemeTextRequest, ...]) -> tuple[ThemeTextResult, ...]:
        if not requests:
            return ()
        asked = {request.theme_id: request for request in requests}
        content = complete_json(SYSTEM_PROMPT, _user_content(requests), transport=self._transport)
        return tuple(_parse(content, asked))


def _user_content(requests: tuple[ThemeTextRequest, ...]) -> str:
    return json.dumps(
        {
            "months": [
                {
                    "theme_id": request.theme_id,
                    "reference_label": request.reference_label,
                    "month": request.period.calendar_month,
                    "target_ages": list(request.target_ages),
                }
                for request in requests
            ]
        },
        ensure_ascii=False,
    )


def _parse(content: str, asked: Mapping[str, ThemeTextRequest]) -> list[ThemeTextResult]:
    """**모델이 준 것을 그대로 믿지 않는다.**

    요청한 달이 빠지거나 없던 달이 끼면 거부한다. 조용히 채우면 교사는 열두 달이
    다 있는 줄 알고 확정한다 — 빈 달은 §7 확정에서야 드러난다.
    """
    try:
        parsed = json.loads(content)
        themes = parsed["themes"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LlmFailed('응답이 {"themes": [...]} 형식이 아니다') from exc
    if not isinstance(themes, list):
        raise LlmFailed("themes 는 배열이어야 한다")

    results: list[ThemeTextResult] = []
    seen: set[str] = set()
    for item in themes:
        if not isinstance(item, dict):
            raise LlmFailed("themes 항목은 객체여야 한다")
        theme_id = item.get("theme_id")
        value = item.get("value")
        if theme_id not in asked:
            raise LlmFailed(f"요청하지 않은 주제가 왔다: {theme_id!r}")
        if theme_id in seen:
            raise LlmFailed(f"같은 주제가 두 번 왔다: {theme_id!r}")
        if not isinstance(value, str) or not value.strip():
            raise LlmFailed(f"주제 문장이 비었다: {theme_id!r}")
        seen.add(theme_id)
        results.append(
            ThemeTextResult(period=asked[theme_id].period, theme_id=theme_id, value=value.strip())
        )
    missing = sorted(set(asked) - seen)
    if missing:
        raise LlmFailed(f"빠진 달이 있다: {missing}")
    return results


def theme_text_generator():
    """진짜와 가짜를 고른다. 설정 판단은 `shared/llm` 이 한다.

    **기본이 mock 이다.** 키가 없는 채로 real 이 돌면 매번 401 을 받고 원인을 찾기까지
    오래 걸린다. 반대로 mock 인 채 배포되면 교사가 받는 문장이 참고자료 라벨 그대로인데
    **근거가 흐려지지는 않는다** — 더 안전한 쪽이 기본이어야 한다.
    """
    if is_mock():
        from ssuksak.adapters.deterministic_theme_text_generator import (
            DeterministicThemeTextGenerator,
        )

        return DeterministicThemeTextGenerator()
    return EliceThemeTextGenerator()
