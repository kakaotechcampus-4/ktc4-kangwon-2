"""Play-centred monthly (PLAY_MONTHLY) LLM planning: one document request, at most one repair.

The Rule fixes the month, weeks, list sizes, the parent plays, the allowed 누리과정 content
ids, the eight safety slots with each slot's allowed refs, and the approved daily-life
entries. The LLM writes theme, rationale, play names and safety sentences, and picks ids
inside those ranges. Habit / health / nutrition text is the approved entry sentence: the LLM
picks the entry, never rewrites it. The Rule also fixes the 소방대피 · 재난대비 topic ids; the LLM
writes one candidate sentence per id, never a date, route, assembly place or procedure.
Validation checks the ids and invented facts, not whether a sentence matches its topic.
Teacher-input cells and weekly safety placement are not
part of the response at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.daily_life_reference import DailyLifeEntry
from ..domain.safety_placement import SafetyKind
from .contracts import ProposalParseError, RawLlmResponse
from .parser import _STRING, _object_schema
from .text_policy import MAX_RATIONALE_CHARS, visible_text_violations
from .weekly import unsupported_facts

PLAY_MONTHLY_PROMPT_VERSION = "play-monthly-planner-v1"
PLAY_MONTHLY_REPAIR_PROMPT_VERSION = "play-monthly-repair-v1"
CONTENT_MIN, CONTENT_MAX = 1, 3  # content ids per activity (first contract proposal)
ACTIVITY_SECTIONS = ("together", "free_play")

SYSTEM_PROMPT = (
    "너는 어린이집 놀이중심 월간계획안 초안을 쓰는 도우미다. 응답은 JSON 객체 하나다: "
    '{"target_month", "theme", "rationale", "together": [{"name", "content_ids", "parent_ref"}], '
    '"free_play": [{"name", "content_ids", "parent_ref"}], "safety": [{"slot", "text", "refs"}], '
    '"habits": [{"week_id", "entry_id"}], "health_entry_id", "nutrition_entry_id", "drills": [{"topic_id", "text"}]}. '
    "target_month 는 요청 값을 그대로 쓴다. "
    "theme 은 이 달에 예상되는 놀이를 나타내는 놀이 주제다. rationale 은 이 주제를 고른 까닭을 합니다체 2~4문장으로 쓴다 — "
    "부모 연간의 해당 시기 놀이와 계절 · 생활을 바탕으로 예상되는 놀이를 설명하고, 유아가 실제로 보인 관심 · 관찰 · 실시 · 성과를 사실처럼 쓰지 않는다. "
    "together 는 함께 하는 활동, free_play 는 유아 예상 자유놀이다. 각각 counts 의 개수를 정확히 쓰고, name 은 놀이 이름이다. "
    "모든 놀이 이름은 서로 달라야 한다. "
    "parent_plays 는 부모 연간에서 교사가 고른 이 시기의 놀이다. emphasized 가 true 인 놀이는 이번 달에 더 이어 갈 놀이다. "
    "어떤 놀이가 부모 놀이 하나를 실제로 이어 가면 parent_ref 에 그 놀이의 ref 를 쓰고, 연간에 없는 새 놀이면 null 로 둔다. "
    f"content_ids 는 curriculum_contents 의 content_id 중 그 놀이에 실제로 드러나는 경험과 명확하게 연결되는 {CONTENT_MIN}~{CONTENT_MAX}개다. "
    "개수를 채우려고 연결이 약한 내용을 고르지 않는다. "
    "safety 는 safety_slots 의 slot 마다 정확히 하나씩 쓴다. text 는 그 달 유아에게 할 안전교육 내용 한 문장이며, 「[교통안전]」 같은 영역 이름을 앞에 붙이지 않는다. "
    "refs 는 그 slot 의 allowed_refs 중 text 가 실제로 근거한 것이다 — 법정 영역 slot 은 정확히 1개, 생활안전 slot 은 1개 이상이다. "
    "habits 는 weeks 의 week_id 마다 하나씩, habit_entries 의 entry_id 를 고른다. 주차 수가 항목 수보다 많지 않으면 같은 항목을 되풀이하지 않는다. "
    "health_entry_id 는 health_entries, nutrition_entry_id 는 nutrition_entries 의 entry_id 중 하나다. 그 문장은 쓰지 않는다. "
    "drills 는 drill_topics 의 topic_id 마다 하나씩, 그 상황을 가정한 소방대피 · 재난대비 훈련 주제를 유아가 알아듣는 말로 한 문장 쓴다. "
    "훈련 날짜 · 시각 · 대피 경로 · 집결 장소 · 담당자 · 실시 결과와 그 원의 비상대응 절차는 쓰지 않는다 — 교사가 쓴다. "
    "발달 · 건강 효과를 단정하지 않는다. 반 이름 · 원 이름은 쓰지 않는다. "
    "어린이날 · 추석처럼 누구나 아는 공휴일 · 기념일은 쓸 수 있다. "
    "그 원만의 행사, 입력에 없는 날짜 · 요일 · 시각 · 사람 이름 · 기관 정보는 지어내지 않는다."
)
REPAIR_INSTRUCTION = (
    " 이번 요청은 수리다. original 은 처음 요청, previous_response 는 앞선 응답, issues 는 문제가 된 자리다. "
    "previous_response 를 같은 형식으로 다시 쓰되 issues 의 location 에 해당하는 값만 고친다. 다른 자리는 한 글자도 바꾸지 않는다."
)

_ACTIVITY_SCHEMA = _object_schema(
    {"name": _STRING, "content_ids": {"type": "array", "items": _STRING}, "parent_ref": {"type": ["string", "null"]}}
)
_SAFETY_SCHEMA = _object_schema(
    {"slot": _STRING, "text": _STRING, "refs": {"type": "array", "items": _STRING}}
)
_HABIT_SCHEMA = _object_schema({"week_id": _STRING, "entry_id": _STRING})
_DRILL_SCHEMA = _object_schema({"topic_id": _STRING, "text": _STRING})
RESPONSE_SCHEMA = _object_schema(
    {
        "target_month": _STRING,
        "theme": _STRING,
        "rationale": _STRING,
        "together": {"type": "array", "items": _ACTIVITY_SCHEMA},
        "free_play": {"type": "array", "items": _ACTIVITY_SCHEMA},
        "safety": {"type": "array", "items": _SAFETY_SCHEMA},
        "habits": {"type": "array", "items": _HABIT_SCHEMA},
        "health_entry_id": _STRING,
        "nutrition_entry_id": _STRING,
        "drills": {"type": "array", "items": _DRILL_SCHEMA},
    }
)


@dataclass(frozen=True, slots=True)
class SafetySlot:
    """One of the eight safety candidate slots; the Rule fixes its kind and allowed refs."""

    slot: str  # a legal category_id, or life_safety_1 / life_safety_2
    kind: SafetyKind
    label: str
    allowed: tuple[tuple[str, str], ...]  # (ref, grounding text)
    category_id: str | None = None
    topic_group: str | None = None


@dataclass(frozen=True, slots=True)
class PlayMonthlyRequest:
    prompt_version: str
    system_prompt: str
    user_content: str
    # The first request's payload. Fact checks always read it, so a repair cannot launder an
    # invented fact through its own previous_response.
    fact_source: str
    target_month: str
    week_ids: tuple[str, ...]
    counts: dict[str, int]
    allowed_content_ids: frozenset[str]
    parent_refs: frozenset[str]
    safety_slots: tuple[SafetySlot, ...]
    habit_entry_ids: tuple[str, ...]
    health_entry_ids: frozenset[str]
    nutrition_entry_ids: frozenset[str]
    drill_topic_ids: tuple[str, ...]  # fixed by the Rule; the LLM writes one sentence each
    fingerprint: str

    @property
    def source_refs(self) -> frozenset[str]:
        """Internal ids handed to the LLM; none may appear in teacher-visible text."""
        return frozenset(
            {
                *self.allowed_content_ids,
                *self.parent_refs,
                *(ref for slot in self.safety_slots for ref, _ in slot.allowed),
                *self.habit_entry_ids,
                *self.health_entry_ids,
                *self.nutrition_entry_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class ProposedActivity:
    name: str
    content_ids: tuple[str, ...]
    parent_ref: str | None


@dataclass(frozen=True, slots=True)
class ProposedSafety:
    slot: str
    text: str
    refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlayMonthlyProposal:
    target_month: str
    theme: str
    rationale: str
    together: tuple[ProposedActivity, ...]
    free_play: tuple[ProposedActivity, ...]
    safety: tuple[ProposedSafety, ...]
    habits: tuple[tuple[str, str], ...]  # (week_id, entry_id)
    health_entry_id: str
    nutrition_entry_id: str
    drills: tuple[tuple[str, str], ...]  # (topic_id, text)


@dataclass(frozen=True, slots=True)
class PlayMonthlyIssue:
    """A content-free finding: ``location`` is a section, an index or a validated key."""

    location: str
    code: str


class PlayMonthlyProvider(Protocol):
    def generate_play_monthly(self, request: PlayMonthlyRequest) -> RawLlmResponse: ...


def parent_ref(period_key: str, row_key: str) -> str:
    """Parent play address; the period keeps cand1 of different seasons apart."""
    return f"{period_key}.{row_key}"


def build_play_monthly_request(
    *,
    target_month: str,
    month_label: str,
    ages: frozenset[int],
    weeks: tuple[tuple[str, str], ...],  # (week_id, display_label)
    counts: dict[str, int],
    period_label: str,
    parent_plays: tuple[tuple[str, str, str, str, bool], ...],  # ref, name, materials, support, emphasized
    catalog: CurriculumCatalog,
    safety_slots: tuple[SafetySlot, ...],
    habit_entries: tuple[DailyLifeEntry, ...],
    health_entries: tuple[DailyLifeEntry, ...],
    nutrition_entries: tuple[DailyLifeEntry, ...],
    drill_topics: tuple[tuple[str, str, str], ...],  # (topic_id, label, situation)
    reference_versions: tuple[str, ...],
) -> PlayMonthlyRequest:
    def entries(values: tuple[DailyLifeEntry, ...]) -> list[dict]:
        return [{"entry_id": e.entry_id, "label": e.label, "text": e.text} for e in values]

    payload = {
        "target_month": target_month,
        "month_label": month_label,
        "ages": sorted(ages),
        "weeks": [{"week_id": w, "label": label} for w, label in weeks],
        "counts": counts,
        "parent_period": period_label,
        "parent_plays": [
            {"ref": ref, "play_name": name, "materials": materials, "support_direction": support, "emphasized": emphasized}
            for ref, name, materials, support, emphasized in parent_plays
        ],
        "curriculum_contents": [{"content_id": c.content_id, "text": c.display} for c in catalog.contents],
        "safety_slots": [
            {"slot": s.slot, "label": s.label, "allowed_refs": [{"ref": r, "text": t} for r, t in s.allowed]}
            for s in safety_slots
        ],
        "habit_entries": entries(habit_entries),
        "health_entries": entries(health_entries),
        "nutrition_entries": entries(nutrition_entries),
        "drill_topics": [
            {"topic_id": t, "label": label, "situation": situation} for t, label, situation in drill_topics
        ],
    }
    user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return PlayMonthlyRequest(
        prompt_version=PLAY_MONTHLY_PROMPT_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
        fact_source=user_content,
        target_month=target_month,
        week_ids=tuple(w for w, _ in weeks),
        counts=dict(counts),
        allowed_content_ids=frozenset(c.content_id for c in catalog.contents),
        parent_refs=frozenset(p[0] for p in parent_plays),
        safety_slots=safety_slots,
        habit_entry_ids=tuple(e.entry_id for e in habit_entries),
        health_entry_ids=frozenset(e.entry_id for e in health_entries),
        nutrition_entry_ids=frozenset(e.entry_id for e in nutrition_entries),
        drill_topic_ids=tuple(t for t, _, _ in drill_topics),
        fingerprint=_fingerprint(PLAY_MONTHLY_PROMPT_VERSION, SYSTEM_PROMPT, user_content, *reference_versions),
    )


def build_repair_request(
    request: PlayMonthlyRequest, previous_content: str, issues: tuple[PlayMonthlyIssue, ...]
) -> PlayMonthlyRequest:
    user_content = json.dumps(
        {
            "original": json.loads(request.user_content),
            "previous_response": json.loads(previous_content),
            "issues": [{"location": i.location, "code": i.code} for i in issues],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    system_prompt = SYSTEM_PROMPT + REPAIR_INSTRUCTION
    return PlayMonthlyRequest(
        **{
            **{name: getattr(request, name) for name in PlayMonthlyRequest.__dataclass_fields__},
            "prompt_version": PLAY_MONTHLY_REPAIR_PROMPT_VERSION,
            "system_prompt": system_prompt,
            "user_content": user_content,
            "fingerprint": _fingerprint(
                PLAY_MONTHLY_REPAIR_PROMPT_VERSION, system_prompt, user_content, request.fingerprint
            ),
        }
    )


def parse_play_monthly_proposal(content: str) -> PlayMonthlyProposal:
    """Strict: a missing, extra or mistyped key is a parse error, never a guessed value."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProposalParseError("play-monthly response is not JSON") from exc
    _require_keys(data, RESPONSE_SCHEMA, "response")
    for name in ("target_month", "theme", "rationale", "health_entry_id", "nutrition_entry_id"):
        _require_str(data[name])

    def items(name: str, schema: dict) -> list[dict]:
        values = data[name]
        if not isinstance(values, list):
            raise ProposalParseError(f"{name} must be a list")
        for value in values:
            _require_keys(value, schema, name)
        return values

    def strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise ProposalParseError("expected a list of strings")
        return tuple(_require_str(v) for v in value)

    def activities(name: str) -> tuple[ProposedActivity, ...]:
        result = []
        for a in items(name, _ACTIVITY_SCHEMA):
            if a["parent_ref"] is not None:
                _require_str(a["parent_ref"])
            result.append(ProposedActivity(_require_str(a["name"]), strings(a["content_ids"]), a["parent_ref"]))
        return tuple(result)

    return PlayMonthlyProposal(
        target_month=data["target_month"],
        theme=data["theme"],
        rationale=data["rationale"],
        together=activities("together"),
        free_play=activities("free_play"),
        safety=tuple(
            ProposedSafety(_require_str(s["slot"]), _require_str(s["text"]), strings(s["refs"]))
            for s in items("safety", _SAFETY_SCHEMA)
        ),
        habits=tuple(
            (_require_str(h["week_id"]), _require_str(h["entry_id"])) for h in items("habits", _HABIT_SCHEMA)
        ),
        health_entry_id=data["health_entry_id"],
        nutrition_entry_id=data["nutrition_entry_id"],
        drills=tuple(
            (_require_str(d["topic_id"]), _require_str(d["text"])) for d in items("drills", _DRILL_SCHEMA)
        ),
    )


def validate_play_monthly(
    proposal: PlayMonthlyProposal, request: PlayMonthlyRequest
) -> tuple[PlayMonthlyIssue, ...]:
    """Every finding blocks storage; empty means the proposal may be stored."""
    issues: list[PlayMonthlyIssue] = []

    def add(location: str, code: str) -> None:
        issues.append(PlayMonthlyIssue(location, code))

    def text(location: str, value: str, **limits: int) -> None:
        # Safety words are expected content in a plan that has its own safety section.
        # The repair is validated against the first request too, so its ids stay blocked.
        for code in visible_text_violations(value, evidence_refs=request.source_refs, **limits):
            if code != "SAFETY_CONTENT_LEAKAGE":
                add(location, code)
        if unsupported_facts(value, request.fact_source):
            add(location, "UNSUPPORTED_FACT")

    if proposal.target_month != request.target_month:
        add("target_month", "TARGET_MONTH_MISMATCH")
    text("theme", proposal.theme)
    text("rationale", proposal.rationale, max_chars=MAX_RATIONALE_CHARS)

    names: set[str] = set()
    for section in ACTIVITY_SECTIONS:
        rows = getattr(proposal, section)
        if len(rows) != request.counts[section]:
            add(section, "ACTIVITY_COUNT")
        for index, row in enumerate(rows):
            location = f"{section}[{index}]"
            text(location, row.name)
            name = " ".join(row.name.split())
            if name in names:
                add(location, "DUPLICATE_PLAY_NAME")
            names.add(name)
            if not CONTENT_MIN <= len(row.content_ids) <= CONTENT_MAX:
                add(location, "CONTENT_ID_COUNT")
            if len(set(row.content_ids)) != len(row.content_ids):
                add(location, "DUPLICATE_CONTENT_ID")
            if not set(row.content_ids) <= request.allowed_content_ids:
                add(location, "UNKNOWN_CONTENT_ID")
            if row.parent_ref is not None and row.parent_ref not in request.parent_refs:
                add(location, "UNKNOWN_PARENT_REF")

    slots = {s.slot: s for s in request.safety_slots}
    seen: set[str] = set()
    for item in proposal.safety:
        slot = slots.get(item.slot)
        if slot is None:
            add("safety", "UNKNOWN_SAFETY_SLOT")
            continue
        if item.slot in seen:
            add("safety", "DUPLICATE_SAFETY_SLOT")
            continue
        seen.add(item.slot)
        location = f"safety:{item.slot}"
        text(location, item.text)
        if item.text.lstrip().startswith("["):
            add(location, "SAFETY_LABEL_IN_TEXT")
        allowed = {ref for ref, _ in slot.allowed}
        refs = set(item.refs)
        if (
            not refs
            or len(refs) != len(item.refs)
            or not refs <= allowed
            or (slot.kind is SafetyKind.STATUTORY and len(refs) != 1)
        ):
            add(location, "SAFETY_REF")
    if seen != set(slots):
        add("safety", "MISSING_SAFETY_SLOT")

    weeks = set(request.week_ids)
    habit_ids = set(request.habit_entry_ids)
    used_weeks: set[str] = set()
    used_entries: set[str] = set()
    no_repeat = len(request.week_ids) <= len(habit_ids)
    for week_id, entry_id in proposal.habits:
        if week_id not in weeks:
            add("habits", "UNKNOWN_WEEK")
            continue
        if week_id in used_weeks:
            add("habits", "DUPLICATE_WEEK")
            continue
        used_weeks.add(week_id)
        location = f"habits:{week_id}"
        if entry_id not in habit_ids:
            add(location, "UNKNOWN_ENTRY")
        elif no_repeat and entry_id in used_entries:
            add(location, "DUPLICATE_HABIT")
        used_entries.add(entry_id)
    if used_weeks != weeks:
        add("habits", "MISSING_WEEK")

    if proposal.health_entry_id not in request.health_entry_ids:
        add("health", "UNKNOWN_ENTRY")
    if proposal.nutrition_entry_id not in request.nutrition_entry_ids:
        add("nutrition", "UNKNOWN_ENTRY")

    topics = set(request.drill_topic_ids)
    written: set[str] = set()
    for topic_id, drill_text in proposal.drills:
        if topic_id not in topics:
            add("drills", "UNKNOWN_DRILL_TOPIC")
        elif topic_id in written:
            add("drills", "DUPLICATE_DRILL_TOPIC")
        else:
            written.add(topic_id)
            text(f"drills:{topic_id}", drill_text)
    if written != topics:
        add("drills", "MISSING_DRILL_TOPIC")
    return tuple(dict.fromkeys(issues))


def changed_locations(before: PlayMonthlyProposal, after: PlayMonthlyProposal) -> frozenset[str]:
    """Where a repair changed the proposal: element locations, or a whole section when its shape changed."""
    changed: set[str] = {
        name
        for name in ("target_month", "theme", "rationale")
        if getattr(before, name) != getattr(after, name)
    }
    if before.health_entry_id != after.health_entry_id:
        changed.add("health")
    if before.nutrition_entry_id != after.nutrition_entry_id:
        changed.add("nutrition")
    for section in ACTIVITY_SECTIONS:
        old, new = getattr(before, section), getattr(after, section)
        if len(old) != len(new):
            changed.add(section)
        else:
            changed.update(f"{section}[{i}]" for i, (a, b) in enumerate(zip(old, new)) if a != b)
    for section, old, new in (
        ("safety", {s.slot: s for s in before.safety}, {s.slot: s for s in after.safety}),
        ("habits", dict(before.habits), dict(after.habits)),
        ("drills", dict(before.drills), dict(after.drills)),
    ):
        reshaped = old.keys() != new.keys() or (len(old), len(new)) != (
            len(getattr(before, section)),
            len(getattr(after, section)),
        )
        if reshaped:
            changed.add(section)
        else:
            changed.update(f"{section}:{key}" for key in old if old[key] != new[key])
    return frozenset(changed)


def section_of(location: str) -> str:
    return location.split("[", 1)[0].split(":", 1)[0]


def repair_scope_issues(
    changed: frozenset[str], flagged: tuple[PlayMonthlyIssue, ...]
) -> tuple[PlayMonthlyIssue, ...]:
    """A repair may only touch a flagged location, or anything in a section flagged as a whole."""
    locations = {i.location for i in flagged}
    return tuple(
        PlayMonthlyIssue(section_of(location), "REPAIR_CHANGED_UNFLAGGED")
        for location in sorted(changed)
        if location not in locations and section_of(location) not in locations
    )


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _require_keys(value: object, schema: dict, where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(schema["properties"]):
        raise ProposalParseError(f"{where} keys do not match the strict schema")


def _require_str(value: object) -> str:
    if not isinstance(value, str):
        raise ProposalParseError("expected a string")
    return value
