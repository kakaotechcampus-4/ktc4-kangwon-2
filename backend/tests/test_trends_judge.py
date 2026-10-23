"""검열 3단 — 모델은 떨어뜨리기만 한다 (ADR-016)."""

import json

from app.features.trends.item import RawItem
from app.features.trends.judge import judge


def item(source_id: str, title: str, description: str = "") -> RawItem:
    return RawItem(
        source="youtube",
        source_id=source_id,
        title=title,
        description=description,
        url=f"https://youtu.be/{source_id}",
        published_at="2026-10-17",
        origin="테스트채널",
    )


def answering(payload: dict, seen: list | None = None):
    """모델 대신 정해진 답을 주는 `ask`."""

    def _ask(system_prompt: str, user_content: str) -> str:
        if seen is not None:
            seen.append(user_content)
        return json.dumps(payload, ensure_ascii=False)

    return _ask


def test_버릴_것만_돌려준다():
    """통과 목록을 받지 않는다 — 모델의 「괜찮다」가 보증으로 읽히면 안 된다."""
    items = (item("a", "신문지 놀이"), item("b", "친구 밀기 놀이", "친구를 밀어 넘어뜨려요"))
    result = judge(
        items,
        ask=answering({"drop": [{"id": "b", "quote": "밀어 넘어뜨려요", "why": "다친다"}]}),
    )
    assert [d.id for d in result.dropped] == ["b"]
    assert result.dropped[0].quote == "밀어 넘어뜨려요"
    assert result.unseen == 0


def test_받은_적_없는_id_는_무시한다():
    """모델이 지어낸 id 로 엉뚱한 줄이 사라지면 사람이 「왜 없지」를 못 찾는다."""
    result = judge(
        (item("a", "신문지 놀이"),),
        ask=answering({"drop": [{"id": "없는id", "quote": "뭔가", "why": "그냥"}]}),
    )
    assert result.dropped == ()


def test_인용이_없으면_버리지_않는다():
    """「왜 걸렀나」를 설명할 수 없으면 검열이 아니라 취향이다 (ADR-016)."""
    result = judge(
        (item("a", "놀이"),),
        ask=answering({"drop": [{"id": "a", "quote": "", "why": "위험해 보임"}]}),
    )
    assert result.dropped == ()


def test_모델이_죽으면_아무것도_안_버리고_못_본_수를_남긴다():
    """조용히 0건이 되면 「위험한 게 없었나 보다」로 읽힌다."""

    def broken(system_prompt: str, user_content: str) -> str:
        raise TypeError("끊김")

    result = judge((item("a", "놀이"), item("b", "놀이2")), ask=broken)
    assert result.dropped == ()
    assert result.unseen == 2
    assert result.failures and "judge:" in result.failures[0]


def test_본문을_같이_보낸다():
    """제목만 보내면 위험한 놀이를 못 잡는다 — 제목에 위험한 낱말이 없다."""
    seen: list = []
    judge(
        (item("a", "재미있는 놀이", "친구 목을 조르는 놀이예요"),),
        ask=answering({"drop": []}, seen),
    )
    sent = seen[0]
    assert "목을 조르는" in sent


def test_주소와_채널은_보내지_않는다():
    """주소를 넣으면 모델이 본문 대신 그쪽을 보고 답한 것처럼 쓴다."""
    seen: list = []
    judge((item("a", "놀이", "본문"),), ask=answering({"drop": []}, seen))
    sent = seen[0]
    assert "youtu.be" not in sent and "테스트채널" not in sent


def test_원문에_없는_인용은_버리지_않는다():
    """지어낸 문장이 PR 에 「근거」로 뜨면, 사람이 그걸 읽고 멀쩡한 줄을 지운다."""
    result = judge(
        (item("a", "종이접기", "색종이를 반으로 접어요"),),
        ask=answering({"drop": [{"id": "a", "quote": "친구 목을 조르세요", "why": "위험"}]}),
    )
    assert result.dropped == ()
    assert any("원문에 없는 인용" in f for f in result.failures)


def test_줄바꿈이_공백으로_와도_같은_인용으로_본다():
    result = judge(
        (item("a", "놀이", "친구를 밀어\n넘어뜨려요"),),
        ask=answering({"drop": [{"id": "a", "quote": "친구를 밀어 넘어뜨려요", "why": "다친다"}]}),
    )
    assert [d.id for d in result.dropped] == ["a"]


def test_모양이_틀린_답은_못_본_것으로_남긴다():
    """JSON 으로 읽혔다고 모양이 맞는 것은 아니다. 조용히 「버릴 것 없음」이 되면 안 된다."""
    for broken in ({"drop": ["a"]}, {}, {"drop": "a"}, [], {"drop": [{}]}):
        result = judge((item("a", "놀이", "본문"),), ask=answering(broken))
        assert result.dropped == ()
        assert result.unseen == 1, broken
        assert result.failures


def test_한도_초과도_못_본_것으로_남긴다():
    """여기서 터지면 이미 올라간 그 주 자료가 승인 PR 없이 브랜치에만 남는다."""
    from app.shared.llm.errors import LlmBudgetExceeded

    def over(system_prompt: str, user_content: str) -> str:
        raise LlmBudgetExceeded("한도 초과")

    result = judge((item("a", "놀이"),), ask=over)
    assert result.unseen == 1 and result.failures


def test_시간이_다_되면_남은_것을_못_본_것으로_남긴다():
    """모델이 계속 죽으면 한 번에 30초씩 쓴다. 주간 작업이 통째로 취소되면
    이미 올라간 그 주 자료가 승인 PR 없이 브랜치에만 남는다."""
    import time

    def slow(system_prompt: str, user_content: str) -> str:
        time.sleep(0.05)
        return json.dumps({"drop": []})

    items = tuple(item(f"i{n}", "놀이", "본문") for n in range(30))
    result = judge(items, ask=slow, batch_size=1, budget_seconds=0.1)
    assert result.unseen > 0
    assert any("시간이 다 돼" in f for f in result.failures)


def test_다른_묶음의_id_는_받지_않는다():
    """모델이 보지도 않은 줄에 대고 「버리자」가 나오면 안 된다."""
    answers = [
        json.dumps({"drop": [{"id": "b", "quote": "밀어 넘어뜨려요", "why": "다친다"}]}),
        json.dumps({"drop": []}),
    ]

    def ask(system_prompt: str, user_content: str) -> str:
        return answers.pop(0)

    result = judge(
        (item("a", "놀이", "색종이를 접어요"), item("b", "놀이", "친구를 밀어 넘어뜨려요")),
        ask=ask,
        batch_size=1,
    )
    assert result.dropped == ()
