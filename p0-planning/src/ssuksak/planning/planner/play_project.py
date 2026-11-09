"""Play-project yearly LLM planning (ADR-042 PLAY_PROJECT, P1 prototype): one period per request.

The Rule fixes the period, row count and the allowed 누리과정 content ids; the LLM writes
play name, materials and support text and picks content ids inside that range. The server
renders the official learning wording from the Reference — the LLM never writes it.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.play_project_plan import PlayPeriod
from ..domain.teacher_memo import MemoNotice
from .contracts import ProposalParseError, RawLlmResponse
from .parser import _STRING, _object_schema
from .teacher_memo import (
    CANDIDATE_MEMO_PROMPT,
    CANDIDATE_MEMO_PROMPT_TAG,
    TEACHER_MEMO_PROMPT,
    TEACHER_MEMO_PROMPT_TAG,
    memo_properties,
)
from .text_policy import MAX_RATIONALE_CHARS, visible_text_violations
from .weekly import unsupported_facts
from ..venue_policy import VENUE_GUIDANCE, VENUE_POLICY_TAG, venue_memo

# v7 (ADR-077, 2026-11-09): per-candidate Rule hints (play_seeds); periods run in parallel, so
# the first call carries no other period's plays.
PLAY_PROJECT_PROMPT_VERSION = "play-project-planner-v7" + VENUE_POLICY_TAG
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
    "정해진 문형 · 맺는말을 되풀이하지 않는다 — 후보마다 놀이에 맞게 쓰고, 모든 후보를 같은 단계 순서나 같은 조건 문장으로 쓰지 않는다. "
    "매번 재료 준비로 시작할 필요는 없으며, 그 놀이에서 중요한 지원을 중심으로 자연스럽게 쓴다. "
    "유아가 앞으로 할 행동이나 놀이 순서를 정해 두지 않고, 놀이가 어떻게 이어질지는 유아의 선택에 열어 둔다. "
    "유아가 실제로 한 일 · 관찰 · 결과나 지금 가진 관심을 사실처럼 쓰지 않고, "
    "발달 효과를 단정하지 않으며, 특정 결과물이나 사용 방법을 꼭 해야 하는 것으로 정하지 않는다. "
    "반 이름 · 원 이름은 쓰지 않는다. "
    "learning_content_ids 는 curriculum_contents 의 content_id 중 이 놀이 · 지원 방향에 실제로 드러나는 경험과 명확하게 연결되는 2개를 기본으로 고른다. "
    "세 번째는 놀이 · 지원 방향에 별도의 경험이 분명히 드러날 때만 추가하며, 전체 개수는 2~3개다. "
    "개수를 채우려고 연결이 약한 내용을 고르거나, 고른 내용에 맞추려고 놀이 · 지원 방향에 없는 경험을 덧붙이지 않는다. "
    "영역 · 내용범주 · 내용 문장은 쓰지 않는다. "
    "어린이날 · 추석처럼 누구나 아는 공휴일 · 기념일은 쓸 수 있다. "
    "그 원만의 행사, 입력에 없는 날짜 · 사람 이름 · 기관 정보는 지어내지 않는다."
)
# v7: the sentence measured as condition ⑦, sent right after VENUE_GUIDANCE as measured
# (docs/evaluation/runs/2026-11-09-play-annual/).
SEED_PROMPT = (
    " play_seeds 는 Rule 이 정한 후보별 중심 누리과정 내용(nuri_content_id, nuri_content)과 중심 자료(material_hint)"
    "이다 — rows 의 n 번째 후보는 play_seeds 의 n 번째를 쓴다. "
    "놀이는 유아가 중심 누리과정 내용을 실제로 경험하는 놀이로 짓고, learning_content_ids 에 nuri_content_id 를 넣는다."
    " 중심 자료를 놀이에 자연스럽게 쓰되, 어색하면 비슷한 자료로 바꿔도 된다."
)

# ADR-077 (하민 결정 2026-11-09): the central hint skips 1.2 건강하게 생활하기 · 1.3 안전하게 생활하기
# (condition ⑦, 59 -> 51 contents). learning_content_ids still choose from all 59 contents.
SEED_EXCLUDED_PREFIXES = ("nuri2019.1.2.", "nuri2019.1.3.")
# [출처] 2019 개정 누리과정 해설서 p.48-49 「풍부한 놀이자료 제공」이 예로 든 자료 종류
# (PDF · 인쇄 쪽 구분 미확인). Category names only, no quoted sentence.
MATERIAL_HINTS = ("일상의 평범한 사물", "자연물", "악기", "미술 재료", "그림책", "재활용품")
NEAR_PLAY_NAME = 0.6  # bigram Jaccard; catches 6 of the 24 'same play' pairs (ADR-077)


@dataclass(frozen=True, slots=True)
class PlaySeed:
    nuri_content_id: str
    nuri_content: str
    material_hint: str


def draw_play_seeds(
    catalog: CurriculumCatalog, period_keys: Sequence[str], rows: int, rng: random.Random
) -> dict[str, tuple[PlaySeed, ...]]:
    """One central 누리과정 content per candidate, all different across the year, and the six
    material kinds spread evenly (1~2 times) inside each period."""
    contents = [c for c in catalog.contents if not c.content_id.startswith(SEED_EXCLUDED_PREFIXES)]
    picks = iter(rng.sample(contents, len(period_keys) * rows))
    seeds = {}
    for key in period_keys:
        materials = [MATERIAL_HINTS[n % len(MATERIAL_HINTS)] for n in range(rows)]
        rng.shuffle(materials)
        seeds[key] = tuple(
            PlaySeed(c.content_id, c.text, material)
            for c, material in zip(itertools.islice(picks, rows), materials, strict=True)
        )
    return seeds


def _squeeze(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text)


def similar_play_names(a: str, b: str, line: float = NEAR_PLAY_NAME) -> bool:
    """Same after dropping spaces and punctuation, or bigram Jaccard >= line."""
    ga, gb = (
        {t[i : i + 2] for i in range(len(t) - 1)} or {t} for t in (_squeeze(a), _squeeze(b))
    )
    return _squeeze(a) == _squeeze(b) or len(ga & gb) / len(ga | gb) >= line


def overlapping_candidates(
    periods: Sequence[Sequence[tuple[str, str, bool]]],
) -> list[tuple[int, int]]:
    """(period index, candidate index) to make again, for (play_name, materials, memo_applied) rows.

    Two candidates of different periods overlap when their names, or names + materials, are
    similar. The later period's one is redone; if it carries the teacher's request, the earlier
    one; if both do, neither (ADR-077).
    """
    found = set()
    for i, j in itertools.combinations(range(len(periods)), 2):
        for (a, (na, ma, memo_a)), (b, (nb, mb, memo_b)) in itertools.product(
            enumerate(periods[i]), enumerate(periods[j])
        ):
            if not (similar_play_names(na, nb) or similar_play_names(f"{na} {ma}", f"{nb} {mb}")):
                continue
            if not memo_b:
                found.add((j, b))
            elif not memo_a:
                found.add((i, a))
    return sorted(found)


# Human Decision 2026-11-05(하민): the memo goes to all four periods, so each period answers only
# its own season's requests and quotes them verbatim — the Application matches them across periods.
PERIOD_MEMO_PROMPT_TAG = "+period-memo-v1"
MEMO_REFLECTED = "memo_reflected"
PERIOD_MEMO_PROMPT = """
- 놀이 프로젝트형은 연간을 네 구간으로 나눠 구간마다 따로 쓴다. teacher_memo는 연간 전체에 적은 요청이고,
  이번 응답은 period_label · months 구간 하나다.
  계절 · 달을 짚은 요청은 이 구간의 계절 · 달에 맞을 때만 반영한다. 다른 구간(계절 · 달)을 짚은 요청은
  이 구간에서 무시하고 memo_skipped에도 적지 않는다 — 그 구간을 쓸 때 따로 다룬다.
  계절 · 달을 짚지 않은 요청은 이 구간에도 해당한다.
- memo_reflected에는 이 구간에서 실제로 반영한 요청을 메모 원문에서 그대로 옮겨 적는다(바꿔 쓰지 않는다).
  없으면 빈 배열이다.
- 여기서는 memo_skipped의 summary도 줄여 쓰지 않고 메모 원문에서 그 요청 부분을 그대로 옮겨 적는다(80자 이내).
"""

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
    # ADR-060: row keys memo_applied may name; None = no teacher memo.
    memo_addresses: tuple[str, ...] | None = None
    # ADR-077: row n uses seed n; () = no hints (the validator then checks nothing about them).
    play_seeds: tuple[PlaySeed, ...] = ()


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


def play_project_response_schema(request: PlayProjectRequest) -> dict:
    if request.memo_addresses is None:
        return RESPONSE_SCHEMA
    return _object_schema(
        dict(
            RESPONSE_SCHEMA["properties"],
            **memo_properties(request.memo_addresses),
            **{MEMO_REFLECTED: {"type": "array", "items": _STRING}},
        )
    )


class PlayProjectProvider(Protocol):
    def generate_play_project(self, request: PlayProjectRequest) -> RawLlmResponse: ...


def build_play_project_request(
    *,
    period: PlayPeriod,
    ages: frozenset[int],
    row_count: int,
    catalog: CurriculumCatalog,
    avoid_play_names: tuple[str, ...] = (),
    teacher_memo: str = "",
    play_seeds: tuple[PlaySeed, ...] = (),
) -> PlayProjectRequest:
    row_count = len(play_seeds) or row_count
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
        "play_seeds": [
            {
                "nuri_content_id": s.nuri_content_id,
                "nuri_content": s.nuri_content,
                "material_hint": s.material_hint,
            }
            for s in play_seeds
        ],
    }
    memo = tuple(f"cand{i}" for i in range(1, row_count + 1)) if teacher_memo else None
    prompt_version = PLAY_PROJECT_PROMPT_VERSION
    system_prompt = SYSTEM_PROMPT + VENUE_GUIDANCE + SEED_PROMPT
    if memo is not None:  # rows answer in order, so row i is cand{i}
        payload["teacher_memo"] = {"text": teacher_memo, "addresses": list(memo)}
        prompt_version += TEACHER_MEMO_PROMPT_TAG + PERIOD_MEMO_PROMPT_TAG + CANDIDATE_MEMO_PROMPT_TAG
        system_prompt += TEACHER_MEMO_PROMPT + PERIOD_MEMO_PROMPT + CANDIDATE_MEMO_PROMPT
    user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return PlayProjectRequest(
        prompt_version=prompt_version,
        system_prompt=system_prompt,
        user_content=user_content,
        period_key=period.key,
        row_count=row_count,
        allowed_content_ids=frozenset(c.content_id for c in catalog.contents),
        avoid_play_names=frozenset(" ".join(n.split()) for n in avoid_play_names),
        packet_fingerprint=hashlib.sha256(
            (prompt_version + catalog.catalog_version + user_content).encode()
        ).hexdigest(),
        memo_addresses=memo,
        play_seeds=tuple(play_seeds),
    )


def split_memo_reflected(content: str, request: PlayProjectRequest) -> tuple[str, tuple[str, ...]]:
    """응답에서 `memo_reflected`(이 구간이 반영한 메모 원문 조각)를 떼어 낸다. 메모가 없으면 그대로."""

    if request.memo_addresses is None:
        return content, ()
    try:
        root = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProposalParseError("play-project response is not JSON") from exc
    raw = root.pop(MEMO_REFLECTED, None) if isinstance(root, dict) else None
    if not isinstance(raw, list) or not all(isinstance(quote, str) for quote in raw):
        raise ProposalParseError("memo_reflected must be an array of strings")
    return json.dumps(root, ensure_ascii=False), tuple(raw)


def remaining_memo_notices(
    memo: str, periods: tuple[tuple[tuple[MemoNotice, ...], tuple[str, ...]], ...]
) -> tuple[MemoNotice, ...]:
    """구간별 (반영 못한 요청, 반영한 원문 조각)을 모아, 어느 구간에서도 반영되지 않은 요청만 남긴다.

    요청은 메모 원문 위치로 식별한다: 반영 못한 요청의 원문 조각이 다른 구간들이 반영한 조각으로
    모두 덮이면 뺀다. 원문에서 찾지 못한 요약은 식별할 수 없으니 그대로 남긴다(조용히 숨기지 않는다).
    """

    # ponytail: verbatim span matching — a quote the LLM paraphrased stays as a notice.
    text = _squash(memo)
    covered: set[int] = set()
    for _, reflected in periods:
        for quote in reflected:
            covered |= _span(text, quote)
    notices = dict.fromkeys(notice for skipped, _ in periods for notice in skipped)
    return tuple(n for n in notices if not (span := _span(text, n.summary)) or not span <= covered)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _span(text: str, quote: str) -> set[int]:
    quote = _squash(quote)
    start = text.find(quote) if quote else -1
    return set(range(start, start + len(quote))) if start >= 0 else set()


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
                getattr(row, name), teacher_venue_text=venue_memo(request.user_content),
                **({"max_chars": limit} if limit else {})
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
    # ADR-077: the Rule fixed each candidate's central content, so the Rule checks it is linked.
    if any(
        seed.nuri_content_id not in row.learning_content_ids
        for seed, row in zip(request.play_seeds, proposal.rows)
    ):
        codes.append("SEED_CONTENT_MISSING")
    return tuple(dict.fromkeys(codes))


def _require_keys(value: object, schema: dict, where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(schema["properties"]):
        raise ProposalParseError(f"{where} keys do not match the strict schema")
