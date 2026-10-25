"""Play-project yearly LLM planning (ADR-042 PLAY_PROJECT, P1 prototype): one period per request.

The Rule fixes the period, row count and the allowed 누리과정 content ids; the LLM writes
play name, materials and support text and picks content ids inside that range. The server
renders the official learning wording from the Reference — the LLM never writes it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.play_project_plan import PlayPeriod
from .contracts import ProposalParseError, RawLlmResponse
from .parser import _STRING, _object_schema
from .text_policy import MAX_RATIONALE_CHARS, visible_text_violations
from .weekly import unsupported_facts

PLAY_PROJECT_PROMPT_VERSION = "play-project-planner-v6"  # v5: materials naming · v6: support text, learning ids
LEARNING_MIN, LEARNING_MAX = 2, 3  # 2026-10-24 decision
TEXT_FIELDS = ("play_name", "materials", "support_direction")

SYSTEM_PROMPT = (
    "너는 어린이집 놀이 프로젝트형 연간계획안 초안을 쓰는 도우미다. 응답은 JSON 객체 하나다: "
    '{"period_key": <요청의 period_key>, "rows": [{"play_name", "materials", "support_direction", '
    '"learning_content_ids"}]}. rows 는 요청의 row_count 개를 정확히 쓴다. '
    "rows 는 교사가 골라 쓸 놀이 후보다 — 모두 서로 다른 놀이로 쓴다. "
    "원마다 갖춘 자료가 다르므로 후보마다 필요한 자료의 종류가 서로 다양하게 한다. "
    "avoid_play_names 는 같은 연간의 다른 시기에 이미 있는 놀이다 — 그 놀이와 같거나 소재 · 놀이 방식이 비슷한 놀이는 쓰지 않는다. "
    # 2026-10-24 decision: tone rules measured from the reference yearly plan; no reference
    # sentence is sent as an example.
    "play_name 은 그 시기 · 연령 유아의 호기심이 떠오르는 놀이 이름이다 — 유아에게 말을 거는 해요체 · 감탄 · 질문으로 "
    "10~25자 안팎으로 쓰고, 후보 중 여러 개에는 살랑살랑 · 보글보글 같은 의성어 · 의태어를 넣는다. "
    "필요하면 「~ 놀이」 「~ 구성하기」처럼 놀이 종류를 끝에 붙인다. "
    # v5 (2026-10-25 decision): materials name what to prepare. Not a banned-word list — an exact
    # tool the play needs keeps its exact name.
    "materials 는 준비할 물품이 바로 떠오르도록 익숙하고 구체적인 물품 이름을 쉼표로 짧게 나열한다. "
    "같은 놀이 기능을 충족한다면 흔히 쓰는 재료를 먼저 고르되, 특정 도구 · 교구가 꼭 필요하면 그 정확한 이름을 쓴다. "
    "단어를 이어 붙여 그럴듯한 물품 이름을 만들거나, 기능이 다른 익숙한 물건으로 억지로 바꾸지 않는다. "
    "같은 종류가 여럿이면 「재활용품(상자, 휴지심 등)」처럼 묶음 이름 뒤 괄호에 예시를 넣고, 그 밖에는 물품마다 풀이를 붙이지 않는다 — "
    "만드는 법 · 놓는 곳 · 쓰는 방법은 support_direction 에 쓴다. "
    "준비해 볼 후보로 쓰고 원에 이미 있거나 주변 시설을 쓸 수 있다고 단정하지 않는다. "
    "「또는」 「(선택)」 「몇 종류」 같은 흐린 표현은 줄이고, 개수는 쓰지 않는다. "
    # v6 (2026-10-25 decision): lead with the teacher's concrete support; no fixed connective,
    # step order or ending list (v5 runs used one frame in nearly every candidate).
    "support_direction 은 이 놀이에서 교사가 무엇을 어떻게 지원하는지다. 합니다체로 쓰고 아이는 「유아」 또는 「유아들」이라고 부른다. 1~3문장 100~180자로 쓴다. "
    "교사의 구체적인 지원을 우선 드러낸다 — 재료를 마련하거나 더하기, 공간을 꾸미거나 넓히기, 유아의 말 · 질문을 듣고 함께 이야기 나누기, "
    "놀이를 이어 갈 시간을 두기처럼 그 놀이에 맞는 지원을 자연스러운 말로 쓴다. "
    "매번 재료 준비로 시작할 필요 없이, 그 놀이에서 중요한 지원을 중심으로 쓴다. "
    "정해진 문형 · 맺는말을 되풀이하지 않는다 — 후보마다 놀이에 맞게 쓰고, 모든 후보를 같은 단계 순서나 같은 조건 문장으로 쓰지 않는다. "
    "유아가 앞으로 할 행동이나 놀이 순서를 정해 두지 않고, 놀이가 어떻게 이어질지는 유아의 선택에 열어 둔다. "
    "유아가 실제로 한 일 · 관찰 · 결과나 지금 가진 관심을 사실처럼 쓰지 않고, "
    "발달 효과를 단정하지 않으며, 특정 결과물이나 사용 방법을 꼭 해야 하는 것으로 정하지 않는다. "
    "반 이름 · 원 이름은 쓰지 않는다. "
    "learning_content_ids 는 curriculum_contents 의 content_id 중 이 놀이 · 지원 방향에 실제로 드러나는 경험과 연결되는 것을 고른다 — "
    "명확하게 연결되는 2개를 기본으로 고르고, 세 번째는 놀이 · 지원 방향에 별도 경험이 분명히 드러날 때만 더한다. "
    "개수를 채우려고 연결이 약한 내용을 고르거나, 고른 내용에 맞추려고 놀이 · 지원 방향에 없는 경험을 덧붙이지 않는다. "
    "영역 · 내용범주 · 내용 문장은 쓰지 않는다. "
    "어린이날 · 추석처럼 누구나 아는 공휴일 · 기념일은 쓸 수 있다. "
    "그 원만의 행사, 입력에 없는 날짜 · 사람 이름 · 기관 정보는 지어내지 않는다."
)

RESPONSE_SCHEMA = _object_schema(
    {
        "period_key": _STRING,
        "rows": {
            "type": "array",
            "items": _object_schema(
                {
                    "play_name": _STRING,
                    "materials": _STRING,
                    "support_direction": _STRING,
                    "learning_content_ids": {"type": "array", "items": _STRING},
                }
            ),
        },
    }
)


@dataclass(frozen=True, slots=True)
class PlayProjectRequest:
    prompt_version: str
    system_prompt: str
    user_content: str
    period_key: str
    row_count: int
    allowed_content_ids: frozenset[str]
    avoid_play_names: frozenset[str]
    packet_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProposedPlayRow:
    play_name: str
    materials: str
    support_direction: str
    learning_content_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlayProjectProposal:
    period_key: str
    rows: tuple[ProposedPlayRow, ...]


class PlayProjectProvider(Protocol):
    def generate_play_project(self, request: PlayProjectRequest) -> RawLlmResponse: ...


def build_play_project_request(
    *,
    period: PlayPeriod,
    ages: frozenset[int],
    row_count: int,
    catalog: CurriculumCatalog,
    avoid_play_names: tuple[str, ...] = (),
) -> PlayProjectRequest:
    payload = {
        "period_key": period.key,
        "period_label": period.label,
        "months": list(period.months),
        "ages": sorted(ages),
        "row_count": row_count,
        "avoid_play_names": list(avoid_play_names),
        "curriculum_contents": [
            {"content_id": c.content_id, "text": c.display} for c in catalog.contents
        ],
    }
    user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return PlayProjectRequest(
        prompt_version=PLAY_PROJECT_PROMPT_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
        period_key=period.key,
        row_count=row_count,
        allowed_content_ids=frozenset(c.content_id for c in catalog.contents),
        avoid_play_names=frozenset(" ".join(n.split()) for n in avoid_play_names),
        packet_fingerprint=hashlib.sha256(
            (PLAY_PROJECT_PROMPT_VERSION + catalog.catalog_version + user_content).encode()
        ).hexdigest(),
    )


def parse_play_project_proposal(content: str) -> PlayProjectProposal:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProposalParseError("play-project response is not JSON") from exc
    _require_keys(data, RESPONSE_SCHEMA, "response")
    row_schema = RESPONSE_SCHEMA["properties"]["rows"]["items"]
    if not isinstance(data["period_key"], str) or not isinstance(data["rows"], list):
        raise ProposalParseError("period_key must be a string and rows a list")
    rows = []
    for row in data["rows"]:
        _require_keys(row, row_schema, "row")
        ids = row["learning_content_ids"]
        if not all(isinstance(row[name], str) for name in TEXT_FIELDS) or not (
            isinstance(ids, list) and all(isinstance(i, str) for i in ids)
        ):
            raise ProposalParseError("row field has the wrong type")
        rows.append(
            ProposedPlayRow(
                row["play_name"], row["materials"], row["support_direction"], tuple(ids)
            )
        )
    return PlayProjectProposal(data["period_key"], tuple(rows))


def validate_play_project(
    proposal: PlayProjectProposal, request: PlayProjectRequest
) -> tuple[str, ...]:
    """Content-free validation codes; empty means the proposal may be stored."""
    codes: list[str] = []
    if proposal.period_key != request.period_key:
        codes.append("PERIOD_MISMATCH")
    if len(proposal.rows) != request.row_count:
        codes.append("ROW_COUNT")
    names = [" ".join(row.play_name.split()) for row in proposal.rows]
    if len(set(names)) != len(names) or not request.avoid_play_names.isdisjoint(names):
        codes.append("DUPLICATE_PLAY_NAME")
    for row in proposal.rows:
        for name in TEXT_FIELDS:
            limit = MAX_RATIONALE_CHARS if name == "support_direction" else None
            found = visible_text_violations(
                getattr(row, name), **({"max_chars": limit} if limit else {})
            )
            # 2026-10-24 decision: safety words (e.g. 교통안전) are ordinary play content here;
            # SAFETY_CONTENT_LEAKAGE guards monthly cells, not play-project text.
            codes.extend(
                f"{name.upper()}:{code}" for code in found if code != "SAFETY_CONTENT_LEAKAGE"
            )
            # A date, time or teacher name not in the input is an invented fact (weekly W-02 check).
            # Holiday names (어린이날 · 추석) carry no such token and stay allowed.
            if unsupported_facts(getattr(row, name), request.user_content):
                codes.append(f"{name.upper()}:UNSUPPORTED_FACT")
        ids = row.learning_content_ids
        if not LEARNING_MIN <= len(ids) <= LEARNING_MAX:
            codes.append("LEARNING_COUNT")
        if len(set(ids)) != len(ids):
            codes.append("DUPLICATE_CONTENT_ID")
        if not set(ids) <= request.allowed_content_ids:
            codes.append("UNKNOWN_CONTENT_ID")
    return tuple(dict.fromkeys(codes))


def _require_keys(value: object, schema: dict, where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(schema["properties"]):
        raise ProposalParseError(f"{where} keys do not match the strict schema")
