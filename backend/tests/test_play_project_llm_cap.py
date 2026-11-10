"""놀이형 연간의 호출 상한 — 진짜 `play_project.generate` 를 끝까지 돌려 센다(ADR-081).

모델 자리에는 정해 둔 답을 내는 provider 를 두고, **답마다 실제 `post_stream` 을 한 번 지나게 한다**
(`post_stream` → `_once_more` → `_llm_call`). 그래서 스레드 4개 · 재시도 · 상한은 진짜 코드가 센다.
가짜는 둘이다 — 모델 자리의 provider(실제 어댑터 · 메모 가리개를 건너뛴다)와
`_post_stream`(소켓을 여는 안쪽, 첫 시도를 「닿지 못함」으로 끊는다).
생성 오케스트레이션의 최악 경로만 본다 — SSE · DB 저장(라우터)은 보지 않는다.
"""

import json
import random
import threading

import pytest
from ssuksak import timing
from ssuksak.planning.planner.contracts import ProposalRejectedError, RawLlmResponse

from app.features.plans import play_project
from app.shared.llm import LlmCallCapExceeded
from app.shared.llm import client as llm

MEMO = "물놀이를 넣어 주세요"  # 메모가 있으면 구간마다 첫 후보(cand1)가 요청을 반영한 칸이 된다

# 겹치는 이름. (구간, 후보 번호) -> 이름. 나중 구간의 후보가 다시 만들어진다. 나중 구간이 요청을
# 반영한 칸이면(m09_m11 의 0번) 앞 구간의 것(m03_m05 의 1번)이 다시 만들어진다.
# 그래서 네 구간 모두 한 번씩 다시 만들어진다.
OVERLAPS = {
    ("m03_m05", 1): "겹침 가",
    ("m09_m11", 0): "겹침 가",
    ("m03_m05", 2): "겹침 나",
    ("m06_m08", 2): "겹침 나",
    ("m06_m08", 3): "겹침 다",
    ("m09_m11", 3): "겹침 다",
    ("m09_m11", 4): "겹침 라",
    ("m12_m02", 4): "겹침 라",
}
PERIODS = ("m03_m05", "m06_m08", "m09_m11", "m12_m02")
# (구간 4 + 실패한 구간 다시 4 + 겹침 다시 4) × 재시도 한 번씩 2 — client.py 의 설명과 같은 수다.
DESIGNED_MAX = (4 + 4 + 4) * 2


@pytest.fixture(autouse=True)
def server(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "is_server", True)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)


class Scripted:
    """정해 둔 답을 내고, 답마다 실제 전송 경로를 한 번 지난다. 구간 순서는 안 본다."""

    def __init__(self, monkeypatch, *, reject_first=False, overlap=False, undelivered_first=False):
        self.reject_first, self.overlap = reject_first, overlap
        self.undelivered_first = undelivered_first
        self.requests = []
        self.attempts = []  # 망 안쪽(`_post_stream`)에 닿은 시도마다 그 호출의 꼬리표
        self._lock = threading.Lock()
        monkeypatch.setattr(llm, "_post_stream", self._network)
        monkeypatch.setattr(play_project, "provider", lambda: self)

    def _network(self, url, *, headers, payload, timeout, fold, deadline, call):
        with self._lock:
            self.attempts.append(payload["tag"])
            first = self.attempts.count(payload["tag"]) == 1
        if self.undelivered_first and first:
            raise llm._NotDelivered("엘리스에 닿지 못했다")
        return {}

    def stage(self, request):
        """first / recall / redo — 요청 하나가 연간 생성의 어느 단계인가."""
        if request.row_count != 10:
            return "redo"
        # 첫 호출과 다시 부르기는 내용이 같아 `==` 로는 못 가른다 — 몇 번째로 왔는지(`is`)로 본다.
        same = [
            r for r in self.requests if r.row_count == 10 and r.period_key == request.period_key
        ]
        return "first" if same[0] is request else "recall"

    def generate_play_project(self, request):
        with self._lock:
            self.requests.append(request)
            tag = len(self.requests)
            stage = self.stage(request)
        mock = play_project.MockPlayProjectProvider()
        body = json.loads(mock.generate_play_project(request).content)
        if stage == "first" and self.reject_first:
            body["rows"] = []  # 계약 위반 — 이 구간만 한 번 더 부른다(ADR-077)
        elif stage != "redo" and self.overlap:
            for (period, index), name in OVERLAPS.items():
                if period == request.period_key:
                    body["rows"][index]["play_name"] = name
        llm.post_stream(
            "https://x/v1/chat/completions",
            headers={},
            payload={"model": "m", "tag": tag},
            timeout=1,
            fold=list,
            deadline=1,
        )
        return RawLlmResponse(content=json.dumps(body, ensure_ascii=False), model="mock")


def generate():
    """생성 요청 하나(`timing` 실행 하나)를 열고 `play_project.generate` 를 끝까지 돌린다."""
    box = {}

    @timing.timed("annual_play", lambda line: None)
    def handler():
        box["run"] = timing.current()
        try:
            box["plan"] = play_project.generate(
                2026, "1", frozenset({3}), MEMO, rng=random.Random(0)
            )
        except Exception as error:
            box["error"] = error

    handler()
    return box


def test_설계상_최악의_경로는_24번이고_상한_안에서_계획안이_나온다(monkeypatch):
    """네 구간 모두 실패해 다시 부르고, 모두 겹쳐 다시 만들고, 시도마다 첫 전송이 끊긴다."""
    provider = Scripted(monkeypatch, reject_first=True, overlap=True, undelivered_first=True)

    box = generate()

    assert "error" not in box, repr(box.get("error"))
    stages = [provider.stage(r) for r in provider.requests]  # 전체 요청 12개 = 4 + 4 + 4
    assert sorted(stages.count(s) for s in ("first", "recall", "redo")) == [4, 4, 4]
    assert {r.period_key for r in provider.requests if r.row_count != 10} == set(PERIODS)
    assert len(provider.attempts) == DESIGNED_MAX  # 망 앞에서 센 시도
    assert box["run"].llm_calls == DESIGNED_MAX  # 요청이 센 수 — 스레드를 합쳐서
    assert DESIGNED_MAX <= llm.MAX_LLM_CALLS_PER_RUN
    names = [c.play_name.value for p in box["plan"].periods for c in p.candidates]
    assert len(names) == 40 and len(set(names)) == 40  # 겹침이 다 풀렸다


def test_상한에_걸리면_실패한_구간을_다시_부르지_않고_멈춘다(monkeypatch):
    """첫 호출 4개 중 2개가 막힌다 — 그 구간을 다시 부르면 요청이 6개가 된다(ADR-077)."""
    monkeypatch.setattr(llm, "MAX_LLM_CALLS_PER_RUN", 2)
    provider = Scripted(monkeypatch)

    box = generate()

    assert isinstance(box["error"], LlmCallCapExceeded)
    assert len(provider.requests) == 4  # 다시 부르기도 겹침 다시 만들기도 없다
    assert len(provider.attempts) == 2  # 막힌 둘은 망에 나가지 않았다
    assert box["run"].llm_calls == 2


def test_겹침을_다시_만들다_상한에_걸리면_원래_후보로_덮지_않고_멈춘다(monkeypatch):
    """첫 호출 4개는 나가고 겹침 다시 만들기가 막힌다 — 경고만 남기고 이으면 다른 오류가 난다."""
    monkeypatch.setattr(llm, "MAX_LLM_CALLS_PER_RUN", 4)
    provider = Scripted(monkeypatch, overlap=True)

    box = generate()

    assert isinstance(box["error"], LlmCallCapExceeded)
    assert not isinstance(box["error"], ProposalRejectedError)
    assert [provider.stage(r) for r in provider.requests].count("redo") == 4
    assert len(provider.attempts) == 4
