"""검열 3단 — 모델이 본다 (ADR-016).

**떨어뜨리기만 한다. 통과를 보증하지 않는다.**

모델에게 「괜찮은 것을 고르라」고 하면 통과 목록이 보증처럼 쓰인다. 같은 입력에
같은 답이 온다는 보장도 없다(`shared/llm/client.py` — 온도를 못 낮춘다). 그래서
**버릴 것만** 받고, 나머지는 「아직 사람이 안 본 것」으로 둔다. 승인은 PR 에서 사람이 한다.

**제목이 아니라 놀이 서술 전체를 본다.** 위험한 유행 놀이는 제목에 위험한 낱말이
없다 — 그래서 수집 단계에서 설명을 자르지 않는다(sources.py `_body`).

**모델이 죽으면 아무것도 버리지 않는다.** 부가 기능이라 본 기능을 막지 않는다.
대신 못 본 건수를 남겨 사람이 안다 — 조용히 0건이 되면 「위험한 게 없었나 보다」로 읽힌다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.features.trends.item import RawItem
from app.shared.llm.client import complete_json, is_mock
from app.shared.llm.errors import LlmBudgetExceeded, LlmFailed, LlmUnavailable

SYSTEM_PROMPT = """너는 어린이집 교사에게 갈 놀이 소재를 거르는 검열자다.

대상은 **만 3~5세**다. 아래 셋 중 하나라도 걸리면 버린다.

1. 다치는 동작 — 미는 것, 목·가슴을 누르는 것, 숨을 참는 것, 높은 곳에서 뛰는 것,
   불·뜨거운 것, 작은 것을 입에 넣는 것, 물에 들어가는 것
2. 따돌리는 구조 — 한 아이를 지목해 벌을 주거나 빼놓는 규칙
3. 만 3~5세가 규칙을 이해할 수 없는 것 — 글씨를 읽어야 하거나, 편을 나눠 점수를 세거나,
   순서를 여러 단계 기억해야 하는 것

**아래는 버리지 않는다.** 어린이집에서 교사가 보는 앞에서 늘 하는 것들이다.

- 가위·풀·크레파스·물감·점토 같은 일상 교구를 쓰는 것
- 뛰기·구르기·균형 잡기처럼 교실·강당에서 하는 몸놀이
- 요리 활동에서 재료를 자르거나 섞는 것
- 안전·위생을 **가르치는** 내용(「세제를 삼켰을 때」, 「길을 건널 때」)

실수로 다칠 수 있다는 이유만으로 버리지 않는다. **그 놀이의 목적 자체가 위험한
동작일 때만** 버린다.

**버릴 것만 답한다.** 괜찮아 보이는 것은 답에 넣지 않는다 — 네 판단은 통과를
보증하지 않는다. 사람이 뒤에서 다시 본다.

**제목이 아니라 본문을 읽고 판단한다.** 위험한 놀이는 제목에 위험한 낱말이 없다.

**왜 버리는지 본문의 표현을 그대로 인용한다.** 인용할 표현이 없으면 버리지 않는다.

반드시 아래 JSON 으로만 답한다. 버릴 것이 없으면 빈 배열이다.

{"drop": [{"id": "<받은 id 그대로>", "quote": "<본문에서 그대로>", "why": "<한 줄>"}]}"""


@dataclass(frozen=True, slots=True)
class Dropped:
    id: str
    quote: str
    why: str


@dataclass(frozen=True, slots=True)
class JudgeResult:
    dropped: tuple[Dropped, ...] = ()
    #: 모델이 못 본 건수. 0 이 아니면 그 주 자료는 3단을 다 거치지 못한 것이다.
    unseen: int = 0
    failures: list[str] = field(default_factory=list)


def _batch_prompt(items: tuple[RawItem, ...]) -> str:
    """id · 제목 · 본문만 보낸다. 주소와 채널 이름은 판단에 쓰지 않는다.

    주소를 넣으면 모델이 그 쪽을 보고 답한 것처럼 쓴다 — 우리는 본문만 보고 판단해야 한다.
    """
    rows = [
        {"id": item.source_id, "title": item.title, "body": item.description} for item in items
    ]
    return json.dumps({"items": rows}, ensure_ascii=False)


def _ask_model(system_prompt: str, user_content: str) -> str:
    return complete_json(system_prompt, user_content)


def _squash(text: str) -> str:
    """띄어쓰기·줄바꿈만 맞춘다. 모델이 줄바꿈을 공백으로 바꿔 돌려주기 때문이다."""
    return " ".join(text.split())


def _rows(body: object) -> list[dict]:
    """답의 모양을 **실패 처리 안에서** 본다.

    JSON 으로 읽혔다고 모양이 맞는 것은 아니다. `{"drop": ["a"]}` 는 파싱은 되지만
    줄이 문자열이라 `.get` 이 터지고, `{}` 는 조용히 「버릴 것 없음」이 된다 —
    둘 다 못 본 것으로 남겨야 사람이 안다.
    """
    if not isinstance(body, dict) or not isinstance(body.get("drop"), list):
        raise ValueError("drop 배열이 없다")
    rows = body["drop"]
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("drop 의 줄이 객체가 아니다")
        # `{"drop": [{}]}` 처럼 빈 줄이 오면 「버릴 것 없음」으로 읽힌다. 못 본 것으로 남긴다.
        if not isinstance(row.get("id"), str) or not isinstance(row.get("quote"), str):
            raise ValueError("drop 의 줄에 id · quote 가 없다")
    return rows


def judge(
    items: tuple[RawItem, ...],
    *,
    ask=None,
    batch_size: int = 10,
    budget_seconds: float = 300.0,
) -> JudgeResult:
    """버릴 것만 돌려준다.

    `ask(system, user) -> str` 는 시험에서 갈아끼운다. 넣지 않으면 실제 모델을 부른다.

    **시간을 정해 두고 멈춘다.** 모델이 계속 시간 초과로 죽으면 한 번에 30초씩 쓴다 —
    315건이면 32번이라 16분이고, 주간 작업(15분)이 통째로 취소된다. 그러면 이미 올라간
    그 주 자료가 **승인 PR 없이** 브랜치에만 남는다. 남은 것은 못 본 것으로 적는다.
    """
    if not items:
        return JudgeResult()
    # mock 모드에서는 부르지 않는다. 가짜 판정을 「검열했다」로 적으면 안 된다.
    if ask is None and is_mock():
        return JudgeResult(unseen=len(items), failures=["judge: LLM_MODE 가 mock 이다"])
    ask = ask or _ask_model

    # 인용이 **그 줄에 실제로 있는지** 대조하려고 원문을 들고 있는다.
    known = {item.source_id: f"{item.title}\n{item.description}" for item in items}
    dropped: list[Dropped] = []
    failures: list[str] = []
    unseen = 0
    started = time.monotonic()
    for start in range(0, len(items), batch_size):
        chunk = items[start : start + batch_size]
        if time.monotonic() - started > budget_seconds:
            left = len(items) - start
            unseen += left
            failures.append(f"judge: 시간이 다 돼 {left}건을 못 봤다")
            break
        try:
            answer = ask(SYSTEM_PROMPT, _batch_prompt(chunk))
            rows = _rows(json.loads(answer))
        except (
            LlmBudgetExceeded,
            LlmFailed,
            LlmUnavailable,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as error:
            # 한 묶음이 죽어도 나머지는 계속 본다. 트렌드는 부가 기능이고, 여기서 멈추면
            # 이미 올라간 그 주 자료가 승인 PR 없이 브랜치에만 남는다.
            failures.append(f"judge: {type(error).__name__} {error}")
            unseen += len(chunk)
            continue
        for row in rows:
            source_id = str(row.get("id", ""))
            quote = str(row.get("quote", "")).strip()
            source = known.get(source_id)
            # **받은 적 없는 id 는 버린다.** 모델이 지어낸 id 로 엉뚱한 줄이 사라지면
            # 사람이 「왜 없지」를 찾을 길이 없다.
            if source is None or not quote:
                continue
            # **인용이 원문에 없으면 버리지 않는다.** 모델이 지어낸 문장을 PR 에 「근거」로
            # 띄우면, 사람이 그걸 읽고 지운다 — 없는 위험을 보고 멀쩡한 줄을 버리게 된다.
            if _squash(quote) not in _squash(source):
                failures.append(f"judge: 원문에 없는 인용을 받았다 (id={source_id})")
                continue
            dropped.append(Dropped(id=source_id, quote=quote, why=str(row.get("why", "")).strip()))
    return JudgeResult(dropped=tuple(dropped), unseen=unseen, failures=failures)
