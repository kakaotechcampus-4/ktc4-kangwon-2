"""검열 3단 — jev 는 떨어뜨리기만 한다 (ADR-016 · ADR-070)."""

from app.features.trends import judge as J
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


def answering(flags: dict | None = None, seen: list | None = None):
    """jev 대신 답한다. `flags` 는 {(자료 키, 질문): 값} — 나머지는 「아니다 · 없음」."""
    flags = flags or {}

    def decide(state, questions):
        if seen is not None:
            seen.append((state, questions))
        out = {}
        for name, q in questions.items():
            key, question = name.split(".")
            value = flags.get((key, question))
            if q["type"] == "choice":
                out[name] = {"choice": value or "없음"}
            else:
                out[name] = {"noul": value if value is not None else 0.0}
        return out

    return decide


def test_버릴_것만_돌려준다():
    """통과 목록을 받지 않는다 — 모델의 「괜찮다」가 보증으로 읽히면 안 된다."""
    items = (item("a", "신문지 놀이"), item("b", "친구 밀기 놀이", "친구를 밀어 넘어뜨려요"))
    result = judge(items, decide=answering({("i2", "위험"): 0.95, ("i2", "인용"): "l2"}))
    assert [d.id for d in result.dropped] == ["b"]
    assert result.dropped[0].quote == "친구를 밀어 넘어뜨려요"
    assert result.dropped[0].why == J.REASONS["위험"]


def test_인용할_줄이_없으면_버리지_않는다():
    items = (item("a", "친구 밀기 놀이", "친구를 밀어 넘어뜨려요"),)
    result = judge(items, decide=answering({("i1", "위험"): 0.95}))
    assert result.dropped == ()


def test_안전을_가르치는_자료는_위험해_보여도_버리지_않는다():
    items = (item("a", "세제를 삼켰을 때", "세제를 삼키면 바로 어른에게 알려요"),)
    flags = {("i1", "위험"): 0.9, ("i1", "안전교육"): 0.95, ("i1", "인용"): "l2"}
    assert judge(items, decide=answering(flags)).dropped == ()


def test_가장_센_이유를_적는다():
    items = (item("a", "점수 놀이", "편을 나눠 점수를 세요"),)
    flags = {("i1", "위험"): 0.2, ("i1", "규칙"): 0.9, ("i1", "인용"): "l2"}
    [row] = judge(items, decide=answering(flags)).dropped
    assert row.why == J.REASONS["규칙"]


def test_모델이_죽으면_아무것도_안_버리고_못_본_수를_남긴다():
    def dead(state, questions):
        raise TimeoutError("엘리스가 응답하지 않는다")

    result = judge((item("a", "놀이"), item("b", "놀이")), decide=dead)
    assert result.dropped == ()
    assert result.unseen == 2
    assert "TimeoutError" in result.failures[0]


def test_본문을_같이_보내고_주소와_채널은_보내지_않는다():
    seen: list = []
    judge((item("a", "제목", "본문 설명이에요"),), decide=answering(seen=seen))
    state, questions = seen[0]
    assert state["items"]["i1"] == {"제목": "제목", "본문": "본문 설명이에요"}
    sent = str(state) + str(questions)
    assert "youtu.be" not in sent and "테스트채널" not in sent


def test_인용_보기는_원문_줄_그대로다():
    """보기에 원문 글자만 있어야 고른 인용이 늘 원문에 있다."""
    it = item("a", "제목이에요", "첫 줄이에요.\n\n둘째 줄이에요! 셋째 문장이에요.")
    assert J.lines_of(it) == ["제목이에요", "첫 줄이에요.", "둘째 줄이에요!", "셋째 문장이에요."]
    for line in J.lines_of(it):
        assert line in f"{it.title}\n{it.description}"


def test_모양이_틀린_답은_못_본_것으로_남긴다():
    def broken(state, questions):
        answers = answering()(state, questions)
        answers["i1.위험"] = {"noul": "높음"}
        return answers

    result = judge((item("a", "놀이"),), decide=broken)
    assert result.dropped == ()
    assert result.unseen == 1


def test_빠진_답도_못_본_것으로_남긴다():
    result = judge((item("a", "놀이"),), decide=lambda state, questions: {})
    assert result.unseen == 1


def test_시간이_다_되면_남은_것을_못_본_것으로_남긴다():
    calls = []

    def slow(state, questions):
        calls.append(1)
        return answering()(state, questions)

    items = tuple(item(str(i), "놀이") for i in range(10))
    result = judge(items, decide=slow, batch_size=4, budget_seconds=-1)
    assert calls == []
    assert result.unseen == 10


def test_묶음마다_따로_묻는다():
    seen: list = []
    items = tuple(item(str(i), f"놀이 {i}번") for i in range(9))
    judge(items, decide=answering(seen=seen), batch_size=4)
    assert [len(state["items"]) for state, _ in seen] == [4, 4, 1]


def test_mock_이면_부르지_않고_못_본_것으로_남긴다(monkeypatch):
    monkeypatch.setattr(J, "is_mock", lambda: True)
    result = judge((item("a", "놀이"),))
    assert result.unseen == 1
    assert result.dropped == ()
