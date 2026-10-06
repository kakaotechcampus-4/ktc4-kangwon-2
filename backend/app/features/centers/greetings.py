"""설정 전에도 내려주는 기존 UI의 월별 기본 문구 (ADR-012: 기본 off)."""

from app.features.centers.schemas import GreetingItem, GreetingsSettings

DEFAULT_TEXTS = {
    3: "경청하는 어린이가 되겠습니다.",
    4: "긍정적인 어린이가 되겠습니다.",
    5: "기쁨을 나누는 어린이가 되겠습니다.",
    6: "친구를 배려하는 어린이가 되겠습니다.",
    7: "감사하는 어린이가 되겠습니다.",
    8: "스스로 참고 기다리는 어린이가 되겠습니다.",
    9: "약속을 잘 지키는 어린이가 되겠습니다.",
    10: "새롭게 생각하는 어린이가 되겠습니다.",
    11: "솔직하게 말하는 어린이가 되겠습니다.",
    12: "끝까지 해내는 어린이가 되겠습니다.",
    1: "어른 말씀을 잘 듣는 어린이가 되겠습니다.",
    2: "바르게 판단하는 어린이가 되겠습니다.",
}


def default_greetings() -> GreetingsSettings:
    return GreetingsSettings(
        enabled=False,
        items=[GreetingItem(month=month, text=text) for month, text in DEFAULT_TEXTS.items()],
    )
