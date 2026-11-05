"""Weekly LLM planning (W3b): one document-level request, strict parse, validation, one repair.

docs/weekly-plan-contract.md §10-1 · §11-1 and the 2026-10-21 decisions. The Rule fixes
what may be written (target Sections, allowed grounding refs, ranked outdoor candidates,
parent context); the LLM writes values and picks refs / one outdoor reference inside that
range; the Application attaches parent citations and the Activity Reference itself.
Monthly planner types are reused read-only; weekly codes live here (ADR-033).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.daily_life_reference import DailyLifeCatalog
from ..domain.errors import InvalidDomainValueError
from ..domain.teacher_memo import MemoNotice
from ..domain.week_period import WeekId
from .contracts import (
    ProposalParseError,
    ProposalRejectedError,
    ProposedSectionValue,
    RawLlmResponse,
    is_compatible_monthly_model,
)
from .parser import _STRING, _object_schema, _refs_schema
from .teacher_memo import (
    TEACHER_MEMO_PROMPT,
    TEACHER_MEMO_PROMPT_TAG,
    memo_properties,
    split_memo_applied,
)
from .text_policy import normalize_visible_text, visible_text_violations
from .v1_guidance import (
    NATURAL_PLAY_GUIDANCE,
    V1_GUIDANCE,
    curriculum_context,
    curriculum_source_refs,
)

_log = logging.getLogger(__name__)

WEEKLY_PROMPT_VERSION = "weekly-planner-v2"  # v2: classified indoor · group · alternative targets (W3c)
WEEKLY_REPAIR_PROMPT_VERSION = "weekly-planner-repair-v1"
# W4b one-cell regeneration: its own prompt, like MONTHLY_CELL_PROMPT_VERSION.
WEEKLY_CELL_PROMPT_VERSION = "weekly-cell-planner-v1"
WEEKLY_CELL_REPAIR_PROMPT_VERSION = "weekly-cell-planner-repair-v1"
WEEKLY_CONTEXT_PROMPT_VERSION = "weekly-planner-v3"
WEEKLY_CONTEXT_REPAIR_PROMPT_VERSION = "weekly-planner-repair-v2"
WEEKLY_CONTEXT_CELL_PROMPT_VERSION = "weekly-cell-planner-v2"
WEEKLY_CONTEXT_CELL_REPAIR_PROMPT_VERSION = "weekly-cell-planner-repair-v2"
# ADR-051: a request with a repeat_by DAY target appends this to every version it uses, so
# a v0.1.0 request keeps its prompt, schema and fingerprint unchanged.
DAY_CELLS_SUFFIX = "+day-cells-v1"
REFERENCE_WIRING_SUFFIX = "+monthly-linked-v7"
SAFETY_KEY = "safety_education"
OUTDOOR_KEY = "outdoor_play"
THEME_KEY = "theme"
# Q1 (2026-10-21): these may stand on the parent value alone (PARENT_PLAN grounding).
PARENT_GROUNDABLE_KEYS = frozenset({"focus", "goals", "basic_habit"})
OUTDOOR_REFERENCE_INSTRUCTION = "outdoor_play 는 reference_candidates 중 하나의 reference_id 를 고르고 value 에 그 label 을 쓴다. "
LINKED_OUTDOOR_INSTRUCTION = (
    "outdoor_play 는 같은 주 부모 놀이의 대상·경험을 먼저 이어 간다. "
    "Catalog에서 고르면 reference_id와 label을 그대로 쓴다. 부모 값 또는 허용 근거로 이어 쓸 때는 "
    "reference_id를 null로 두고 실제로 쓴 allowed_grounding_refs만 인용한다. "
    "parent_groundable이 true이고 부모 현재 값을 그대로 이어 쓸 때만 grounding_refs를 비울 수 있다. "
    "부모와 다른 문장을 쓰면 허용된 바깥놀이 기관 근거를 반드시 인용한다. "
    "기관 근거를 인용해 새로 쓰는 바깥놀이는 '활동명: 설명'으로 쓰고, "
    "설명은 그 근거의 대상과 경험을 이번 주에 어떻게 살펴보거나 경험할지 합니다체 한 문장으로 풀어 쓴다. "
    "Catalog label 또는 부모 현재 값을 그대로 이어 쓰는 경우에는 이 설명을 덧붙이지 않는다. "
)
CANDIDATE_DESCRIPTION_TONE = (
    "후보 설명은 합니다체 1~2문장으로 쓰며 해요체·한다체를 섞지 않는다. 재료를 나열하거나 발달 효과를 단정하지 않는다. "
)
LINKED_WRITING_GUIDANCE = (
    " 해당 주 부모 focus → 같은 주 놀이 → 실내대체 순서로 작성한다. 고르기 쉬운 놀이에 맞추려고 focus를 바꾸지 않는다. "
    "목표는 v1 월간처럼 중심 경험을 간결하게 묶되 이번 주의 범위로 좁힌다. "
    "놀이 이름은 기존 v1 월간처럼 대상과 경험이 보이는 짧고 익숙한 명사형으로 쓰며, 원 근거의 자연스러운 표현을 우선한다. "
    "뜻을 줄이려고 명사를 겹쳐 붙이거나 설명 말투인 '해요/해 봅니다'를 이름에 붙이지 않는다. "
    "실내놀이·대소집단 설명은 v2 놀이 설명과 같은 합니다체로, 유아가 탐색할 대상과 경험을 자연스럽게 쓴다. "
    + CANDIDATE_DESCRIPTION_TONE
    + "근거가 짧은 활동명뿐이면 그 대상과 활동의 뜻을 풀어 쓴다. "
    "설명을 구체화하려고 근거에 없는 새 재료·실험 비교 조건·진행 순서·정해진 결과물을 덧붙이지 않는다. "
    "실내놀이는 활동마다 줄을 나눠 '[역할놀이] - 활동명: 짧은 설명'처럼 쓴다. "
    "대괄호에는 근거 본문이나 함께 제공한 원문 영역 이름에서 확인되는 놀이 영역만 쓰고, "
    "영역을 확인할 수 없으면 임의 분류를 붙이지 않는다. 같은 항목의 설명은 간결하게 이어 쓴다. "
    "실내대체는 같은 주 바깥놀이를 실내에서 이어 간다. parent의 같은 주 indoor_alternative가 있고 허용 근거로 이어갈 수 있으면 그 활동을 먼저 구체화한다. "
    "부모 활동을 그대로 수행했다고 쓰거나, 주간에서 고르기 편한 다른 놀이로 이유 없이 바꾸지 않는다. 허용 근거로 이어갈 수 없으면 빈칸으로 두고 관계없는 놀이로 채우지 않는다. "
    "parent의 다른 주 focus도 참고해 이번 주와 다른 주의 경험을 구분하며, 진행 순서나 완성품을 강제하지 않는다. "
    "daily_life_context는 승인된 생활 문장의 표현 참고다. 부모의 현재 습관을 다른 문장으로 교체하지 않고, "
    "예문을 그대로 복사하거나 그 ID를 grounding_refs/reference_id로 인용하지 않는다. 단 부모 현재 값의 계승은 허용한다. "
)

SYSTEM_PROMPT = (
    "너는 어린이집 주간계획안 초안을 쓰는 도우미다. 응답은 JSON 객체 하나다: "
    '{"week_id": <요청의 week_id>, "sections": [{"section_key", "value", "unresolved", '
    '"grounding_refs", "reference_id"}]}. targets 에 있는 Section 만, 하나씩 쓴다. '
    "부모 월간계획(parent)과 근거 자료(evidence)의 범위 안에서 그 반 연령에 맞는 새 문장을 쓴다 — "
    "근거 자료 문장을 그대로 옮기지 않는다. grounding_refs 는 그 Section 의 allowed_grounding_refs 안에서만 고른다. "
    "outdoor_play 는 reference_candidates 중 하나의 reference_id 를 고르고 value 에 그 label 을 쓴다. "
    "입력에 없는 날짜 · 요일 · 시각 · 사람 이름이나 호칭, 행사 운영 세부(시각 · 장소 · 준비물)를 지어내지 않는다. "
    "입력에 있는 행사는 이름 그대로 쓸 수 있다. 법정 기준 충족 같은 주장을 하지 않는다. "
    "쓸 내용이 없으면 unresolved: true, value 는 빈 문자열이다."
)
DAY_PROMPT = (
    " targets 에 days 가 있는 Section 은 value 대신 days 배열로 답한다: 요청한 요일마다 순서대로 "
    '{"day", "value", "unresolved", "grounding_refs"} 하나씩, 그날 할 활동 하나를 쓴다. '
    "요일끼리 같은 문장을 쓰지 않는다. 요일 이름은 day 에만 두고 문장에 쓰지 않는다. "
    "그 요일에 쓸 근거가 없으면 그 요일만 unresolved: true, value 는 빈 문자열이다."
)
DAY_CELL_PROMPT = " 이번에는 days 의 요일 하나만 쓰고, current_plan 에 있는 같은 Section 다른 요일 값과 같은 문장을 쓰지 않는다."
CELL_SYSTEM_PROMPT = SYSTEM_PROMPT + (
    " 이번 요청은 계획안의 한 칸만 다시 쓴다: targets 의 Section 하나만 쓰고, "
    "current_plan 에 있는 다른 칸 내용은 맥락으로만 읽는다."
)


class WeeklyIssueCode(str, Enum):
    ACTIVITY_CANDIDATE_INVALID = "ACTIVITY_CANDIDATE_INVALID"
    WEEK_MISMATCH = "WEEK_MISMATCH"
    SECTION_NOT_REQUESTED = "SECTION_NOT_REQUESTED"
    TEACHER_INPUT_VALUE = "TEACHER_INPUT_VALUE"
    DUPLICATE_SECTION = "DUPLICATE_SECTION"
    MISSING_SECTION = "MISSING_SECTION"
    THEME_REQUIRED = "THEME_REQUIRED"
    UNKNOWN_GROUNDING_REF = "UNKNOWN_GROUNDING_REF"
    WRONG_SOURCE_GROUNDING = "WRONG_SOURCE_GROUNDING"
    RESOLVED_REQUIRES_GROUNDING = "RESOLVED_REQUIRES_GROUNDING"
    REFERENCE_FORBIDDEN = "REFERENCE_FORBIDDEN"
    UNKNOWN_REFERENCE_ID = "UNKNOWN_REFERENCE_ID"
    REFERENCE_REQUIRED = "REFERENCE_REQUIRED"
    TEXT_POLICY = "TEXT_POLICY"
    SOURCE_TEXT_COPY = "SOURCE_TEXT_COPY"
    UNSUPPORTED_FACT = "UNSUPPORTED_FACT"
    DAY_MISMATCH = "DAY_MISMATCH"  # days must be exactly the requested days, in order
    DAY_VALUE_REPEATED = "DAY_VALUE_REPEATED"


# Same idea as the monthly REPAIRABLE_CODES: wording or a ref choice inside a fixed slot.
REPAIRABLE = frozenset({
    WeeklyIssueCode.ACTIVITY_CANDIDATE_INVALID,
    WeeklyIssueCode.TEXT_POLICY,
    WeeklyIssueCode.SOURCE_TEXT_COPY,
    WeeklyIssueCode.WRONG_SOURCE_GROUNDING,
    WeeklyIssueCode.UNSUPPORTED_FACT,
    WeeklyIssueCode.DAY_VALUE_REPEATED,
})


@dataclass(frozen=True, slots=True)
class WeeklyIssue:
    code: WeeklyIssueCode
    section_key: str
    detail: str = ""  # content-free: a code-level reason, never generated text
    day: str | None = None


@dataclass(frozen=True, slots=True)
class WeeklyTarget:
    section_key: str
    allowed_grounding_refs: tuple[str, ...] = ()
    parent_value: str = ""
    semantic_variant: str | None = None
    days: tuple[str, ...] = ()  # repeat_by DAY: the OperatingDay values to write, in order
    parent_groundable: bool = False
    activity_type: str | None = None
    activity_basis: str | None = None
    required_name_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WeeklyDayValues:
    """A repeat_by DAY Section's answer: (day, value) per requested day (ADR-051).

    Weekly-only, so the monthly ProposedSectionValue stays unchanged (ADR-033)."""

    section_key: str
    days: tuple[tuple[str, ProposedSectionValue], ...]


@dataclass(frozen=True, slots=True)
class WeeklyPlanningRequest:
    prompt_version: str
    system_prompt: str
    user_content: str
    week_id: WeekId
    targets: tuple[WeeklyTarget, ...]
    teacher_input_keys: frozenset[str]
    evidence_texts: tuple[tuple[str, str], ...]  # (ref, text) the Rule supplied
    reference_candidates: tuple[tuple[str, str], ...]  # (activity_id, label), ranked
    allowed_fact_text: str  # every input a value may take a date / name from (Q2)
    packet_fingerprint: str = ""
    repair_targets: tuple[str, ...] = ()
    repair_prompt_version: str = WEEKLY_REPAIR_PROMPT_VERSION
    cell_key: str | None = None  # W4b: a one-cell request targets exactly this Section
    context_source_refs: frozenset[str] = frozenset()
    other_day_values: tuple[str, ...] = ()  # a day cell request: the Section's other days now
    reference_wiring: bool = False
    reference_examples: tuple[str, ...] = ()
    # ADR-060: the cell addresses memo_applied may name; None = no teacher memo.
    memo_addresses: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError("WeeklyPlanningRequest.week_id must be WeekId")
        keys = [target.section_key for target in self.targets]
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError("WeeklyPlanningRequest targets must be unique")
        shaped = keys == [self.cell_key] if self.cell_key is not None else THEME_KEY in keys
        if not shaped:
            raise InvalidDomainValueError(
                "A document request targets theme; a cell request targets its one Section"
            )
        if set(keys) & self.teacher_input_keys:
            raise InvalidDomainValueError("Teacher-input Sections are never LLM targets")
        if any(t.parent_groundable and not t.parent_value.strip() for t in self.targets):
            raise InvalidDomainValueError("A parent-groundable target needs its current parent value")
        if any(t.parent_groundable for t in self.targets) and not self.reference_wiring:
            raise InvalidDomainValueError("Parent outdoor grounding requires the linked reference policy")
        evidence = dict(self.evidence_texts)
        for target in self.targets:
            if target.activity_basis is not None and (
                target.activity_type is None or not isinstance(target.activity_basis, str)
                or not target.activity_basis.strip() or not any(
                    target.activity_basis in evidence.get(ref, "") for ref in target.allowed_grounding_refs
                )
            ):
                raise InvalidDomainValueError("A candidate activity basis must be a span of its allowed evidence")
            if not isinstance(target.required_name_terms, tuple) or any(
                not isinstance(term, str) or not term.strip() for term in target.required_name_terms
            ) or target.required_name_terms and target.activity_basis is None:
                raise InvalidDomainValueError("Candidate name requirements need a grounded activity basis")

    def target(self, section_key: str) -> WeeklyTarget | None:
        return next((t for t in self.targets if t.section_key == section_key), None)

    @property
    def request_fingerprint(self) -> str:
        """What was actually sent (W7): prompt version + body, so the W3c weekly evidence and a
        cell request's current_plan count too. packet_fingerprint stays the monthly Packet's."""
        return hashlib.sha256(f"{self.prompt_version}\n{self.user_content}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class WeeklyPlanningOutcome:
    values: tuple[ProposedSectionValue | WeeklyDayValues, ...]
    model: str
    prompt_version: str
    initial_prompt_version: str
    packet_fingerprint: str
    repaired: frozenset[str] = frozenset()
    request_id: str | None = None
    memo_applied: frozenset[str] = frozenset()  # weekly_memo_address of each memo-changed cell
    memo_skipped: tuple[MemoNotice, ...] = ()  # requests the LLM could not apply

    def value(self, section_key: str) -> ProposedSectionValue | None:
        found = next((v for v in self.values if v.section_key == section_key), None)
        return found if isinstance(found, ProposedSectionValue) else None

    def day_value(self, section_key: str, day: str) -> ProposedSectionValue | None:
        found = next((v for v in self.values if v.section_key == section_key), None)
        return dict(found.days).get(day) if isinstance(found, WeeklyDayValues) else None

    def prompt_version_for(self, section_key: str) -> str:
        """The prompt that produced this cell's current value (initial or repair)."""
        return self.prompt_version if section_key in self.repaired else self.initial_prompt_version


class WeeklyPlanningProvider(Protocol):
    def generate_weekly(self, request: WeeklyPlanningRequest) -> RawLlmResponse: ...


def weekly_memo_address(section_key: str, day: str | None) -> str:
    return section_key if day is None else f"{section_key}:{day}"


def _memo_addresses(targets: tuple[WeeklyTarget, ...]) -> tuple[str, ...]:
    """Cells the teacher memo may change (ADR-060): every target but the locked theme and safety."""
    return tuple(
        weekly_memo_address(t.section_key, day)
        for t in targets
        if t.section_key not in {THEME_KEY, "safety_education"}
        for day in (t.days or (None,))
    )


def validate_daily_life_context(daily_life: DailyLifeCatalog, curriculum: CurriculumCatalog | None) -> None:
    if not isinstance(daily_life, DailyLifeCatalog) or not daily_life.is_active or curriculum is None or (
        daily_life.curriculum_catalog_id, daily_life.curriculum_catalog_version
    ) != (curriculum.catalog_id, curriculum.catalog_version) or any(
        entry.content_id not in {content.content_id for content in curriculum.contents}
        for entry in daily_life.entries
    ):
        raise InvalidDomainValueError("Weekly daily-life context must match the approved curriculum")


def build_weekly_request(
    *,
    week_id: WeekId,
    week: dict[str, object],
    ages: tuple[int, ...],
    targets: tuple[WeeklyTarget, ...],
    teacher_input_keys: frozenset[str],
    parent_context: tuple[tuple[str, str], ...],
    evidence: tuple[tuple[str, str, str], ...],  # (ref, text, grounding_class)
    reference_candidates: tuple[tuple[str, str], ...],
    packet_fingerprint: str,
    curriculum: CurriculumCatalog | None = None,
    reference_wiring: bool = False,
    daily_life: DailyLifeCatalog | None = None,
    sibling_focuses: tuple[str, ...] = (),
    teacher_memo: str = "",
) -> WeeklyPlanningRequest:
    body = {
        "task": "weekly_plan",
        "week": {"week_id": week_id.value, **week},
        "ages": list(ages),
        "parent": dict(parent_context),
        "targets": [
            {
                "section_key": t.section_key,
                "semantic_variant": t.semantic_variant,
                "allowed_grounding_refs": list(t.allowed_grounding_refs),
                **({"days": list(t.days)} if t.days else {}),
                **({"parent_groundable": True} if t.parent_groundable else {}),
                **({"activity_type": t.activity_type} if t.activity_type is not None else {}),
                **({"activity_basis": t.activity_basis, "required_name_terms": list(t.required_name_terms)}
                   if t.activity_basis is not None else {}),
                **({"reference_candidates": [
                    {"reference_id": rid, "label": label} for rid, label in reference_candidates
                ]} if t.section_key == OUTDOOR_KEY else {}),
            }
            for t in targets
        ],
        "never_write": sorted(teacher_input_keys),
        "evidence": [{"grounding_ref": r, "text": text, "grounding_class": c} for r, text, c in evidence],
    }
    if curriculum is not None:
        body["curriculum_context"] = curriculum_context(curriculum)
    examples: tuple[str, ...] = ()
    source_refs = curriculum_source_refs(curriculum)
    if reference_wiring:
        body["reference_policy_version"] = REFERENCE_WIRING_SUFFIX.lstrip("+")
        body["monthly_focuses"] = list(sibling_focuses)
        if daily_life is not None:
            validate_daily_life_context(daily_life, curriculum)
            body["daily_life_context"] = {
                "catalog_id": daily_life.catalog_id, "catalog_version": daily_life.catalog_version,
                "purpose": "WORDING_CONTEXT_ONLY",
                "entries": [{"entry_id": e.entry_id, "kind": e.kind.value, "label": e.label,
                             "text": e.text, "content_id": e.content_id} for e in daily_life.entries],
            }
            examples = tuple(e.text for e in daily_life.entries)
            source_refs |= {daily_life.catalog_id, daily_life.catalog_version, *(e.entry_id for e in daily_life.entries)}
    allowed = " ".join([
        *(value for _, value in parent_context),
        *(text for _, text, _ in evidence),
        *(label for _, label in reference_candidates),
    ])
    suffix = DAY_CELLS_SUFFIX if any(t.days for t in targets) else ""
    candidates = "+activity-candidates-v5" if any(t.activity_type is not None for t in targets) else ""
    if candidates:
        source_refs |= {t.section_key for t in targets if t.activity_type is not None}
    memo = _memo_addresses(targets) if teacher_memo else None
    if memo is not None:
        body["teacher_memo"] = {"text": teacher_memo, "addresses": list(memo)}
        allowed += " " + teacher_memo  # the teacher's own facts (Q2), like teacher_facts
    linked = (REFERENCE_WIRING_SUFFIX if reference_wiring else "") + candidates
    if memo is not None:
        linked += TEACHER_MEMO_PROMPT_TAG
    system_prompt = SYSTEM_PROMPT
    if reference_wiring:
        system_prompt = system_prompt.replace(OUTDOOR_REFERENCE_INSTRUCTION, LINKED_OUTDOOR_INSTRUCTION)
        system_prompt += NATURAL_PLAY_GUIDANCE + LINKED_WRITING_GUIDANCE
    elif candidates:
        system_prompt += NATURAL_PLAY_GUIDANCE + CANDIDATE_DESCRIPTION_TONE
    if candidates:
        system_prompt += (
            " activity_type가 있는 target은 교사가 고를 한 주 활동 후보이며 요일에 배치하지 않는다. "
            "각 후보는 Rule이 정한 그 유형과 허용 근거로 짧은 활동명: 설명을 쓴다. 유형 이름은 value에 붙이지 않는다. "
            "먼저 허용 근거와 정해진 유형으로 유아가 무엇을 대상으로 무엇을 하는 활동인지 설명을 정하고, "
            "그 설명의 대상과 실제 행동을 남겨 문서용 활동명을 쓴다. 출력 형식은 활동명: 설명을 유지한다. "
            "유형과 활동명만 읽어도 할 일이 떠올라야 한다. 나누기·탐색·알아보기 같은 말을 붙이는 것만으로 구체화하지 않는다. "
            "이야기나누기는 이야기할 대상이나 상황을, 미술·과학은 표현하거나 살펴볼 대상과 근거에 있는 방식을 남긴다. "
            "activity_basis는 이 후보가 사용할 원문 활동이다. 전체 근거에 다른 활동이 있어도 그 활동으로 바꾸거나 서로 섞어 새 활동을 만들지 않는다. "
            "required_name_terms는 문서 이름에 남겨야 할 활동 정보이며 모두 포함한다. 설명도 activity_basis의 같은 활동을 다룬다. "
            "작품명과 익숙한 놀이명은 유지하고, 모든 제목에 같은 행동어를 억지로 붙이지 않는다. "
            "제목과 설명은 같은 활동을 뜻해야 하며, 근거에 없는 재료·놀이 방법·절차·결과물을 보태지 않는다. "
            "후보를 부모 소주제와 일치시키려고 대상을 바꾸거나 모두 같은 놀이로 만들지 않는다. "
            "같은 Section의 후보끼리 활동 이름이 겹치지 않게 하되 근거에 없는 활동으로 개수를 채우지 않는다. "
            "indoor_play.candidate로 시작하는 target도 같은 형식의 실내 자유놀이 후보다. "
            "후보의 activity_type은 표시할 때 Rule이 붙이므로 value에는 영역 태그를 중복해서 쓰지 않는다. "
        )
    return WeeklyPlanningRequest(
        prompt_version=(WEEKLY_CONTEXT_PROMPT_VERSION if curriculum is not None else WEEKLY_PROMPT_VERSION) + linked + suffix,
        system_prompt=system_prompt + (DAY_PROMPT if suffix else "") + (V1_GUIDANCE if curriculum is not None else "")
        + (TEACHER_MEMO_PROMPT if memo is not None else ""),
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True),
        week_id=week_id,
        targets=targets,
        teacher_input_keys=teacher_input_keys,
        evidence_texts=tuple((r, text) for r, text, _ in evidence),
        reference_candidates=reference_candidates,
        allowed_fact_text=allowed,
        packet_fingerprint=packet_fingerprint,
        repair_prompt_version=(
            WEEKLY_CONTEXT_REPAIR_PROMPT_VERSION if curriculum is not None else WEEKLY_REPAIR_PROMPT_VERSION
        ) + linked + suffix,
        context_source_refs=frozenset(source_refs),
        reference_wiring=reference_wiring,
        reference_examples=examples,
        memo_addresses=memo,
    )


def cell_request(
    request: WeeklyPlanningRequest,
    section_key: str,
    *,
    current_values: tuple[tuple[str, str], ...],
    teacher_facts: tuple[str, ...],
    day: str | None = None,
) -> WeeklyPlanningRequest:
    """The document request narrowed to one Section (W4b, plan §4).

    Same Rule-fixed range — that Section's allowed refs, outdoor candidates, parent
    context — plus the plan's other current values as context. Values a teacher wrote —
    the teacher-input Cells and any Cell whose current value a teacher edited — may
    also supply dates and names (Q2: a teacher's own input; decision B, 2026-10-21).
    """
    target = request.target(section_key)
    if target is None:
        raise InvalidDomainValueError(f"Section is not a target of the weekly request: {section_key}")
    if (day is None) != (not target.days) or (day is not None and day not in target.days):
        raise InvalidDomainValueError("A day cell request names one requested day of a DAY Section")
    if day is not None:
        target = replace(target, days=(day,))
    body = json.loads(request.user_content)
    body["task"] = "weekly_cell"
    body["targets"] = [
        {**t, **({"days": [day]} if day is not None else {})}
        for t in body["targets"] if t["section_key"] == section_key
    ]
    body["evidence"] = [e for e in body["evidence"] if e["grounding_ref"] in target.allowed_grounding_refs]
    body["current_plan"] = dict(current_values)
    contextual = "curriculum_context" in body
    suffix = DAY_CELLS_SUFFIX if request.prompt_version.endswith(DAY_CELLS_SUFFIX) else ""
    linked = REFERENCE_WIRING_SUFFIX if request.reference_wiring else ""
    memo = None
    if request.memo_addresses is not None:
        memo = (weekly_memo_address(section_key, day),)
        body["teacher_memo"]["addresses"] = list(memo)
        linked += TEACHER_MEMO_PROMPT_TAG
    return replace(
        request,
        prompt_version=(WEEKLY_CONTEXT_CELL_PROMPT_VERSION if contextual else WEEKLY_CELL_PROMPT_VERSION) + linked + suffix,
        repair_prompt_version=(
            WEEKLY_CONTEXT_CELL_REPAIR_PROMPT_VERSION if contextual else WEEKLY_CELL_REPAIR_PROMPT_VERSION
        ) + linked + suffix,
        system_prompt=(
            request.system_prompt + " 이번 요청은 targets의 한 칸만 다시 쓰며 current_plan의 다른 값은 맥락으로만 읽는다."
            if contextual or request.reference_wiring
            else CELL_SYSTEM_PROMPT + (DAY_PROMPT if suffix else "") + (TEACHER_MEMO_PROMPT if memo else "")
        ) + (DAY_CELL_PROMPT if day is not None else ""),
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True),
        targets=(target,),
        allowed_fact_text=" ".join((request.allowed_fact_text, *teacher_facts)),
        cell_key=section_key,
        memo_addresses=memo,
        # The caller labels the Section's other day cells "section_key:DAY".
        other_day_values=tuple(
            value for label, value in current_values if day is not None and label.startswith(f"{section_key}:")
        ),
    )


def weekly_response_schema(request: WeeklyPlanningRequest) -> dict:
    """Strict Structured Output for a document, one-cell or repair request (W7, plan §3-1).

    One branch per Section the answer may carry (the repair's flagged ones, else the
    targets), each with only that Section's allowed refs. outdoor_play is one branch per
    ranked candidate fixing reference_id and its label together — the monthly cell schema
    once lacked that pair lock and real Luna-6 regeneration failed (plan §7). theme is
    never unresolved. validate_weekly stays the final check (copies, Q2 facts, duplicates).
    """
    branches = []
    for key in request.repair_targets or tuple(t.section_key for t in request.targets):
        fixed = {"section_key": {"type": "string", "enum": [key]}}
        target = request.target(key)
        refs = _refs_schema(target.allowed_grounding_refs)
        if target.days:
            day_items = [
                _object_schema({
                    "day": {"type": "string", "enum": [day]},
                    "value": _STRING,
                    "unresolved": {"type": "boolean"},
                    "grounding_refs": refs,
                })
                for day in target.days
            ]
            branches.append(_object_schema({
                **fixed,
                "days": {
                    "type": "array",
                    "items": day_items[0] if len(day_items) == 1 else {"anyOf": day_items},
                    "minItems": len(day_items),
                    "maxItems": len(day_items),
                },
                "reference_id": {"type": "null"},
            }))
            continue
        if key == OUTDOOR_KEY:
            branches += [
                _object_schema({
                    **fixed,
                    "value": {"type": "string", "enum": [label]},
                    "unresolved": {"type": "boolean", "enum": [False]},
                    "grounding_refs": _refs_schema(()),
                    "reference_id": {"type": "string", "enum": [reference_id]},
                })
                for reference_id, label in request.reference_candidates
            ]
            if not (request.reference_wiring and (target.parent_groundable or target.allowed_grounding_refs)):
                continue
        branches.append(_object_schema({
            **fixed,
            "value": _STRING,
            "unresolved": {"type": "boolean", "enum": [False]} if key == THEME_KEY else {"type": "boolean"},
            "grounding_refs": refs,
            "reference_id": {"type": "null"},
        }))
    root = {
        "week_id": {"type": "string", "enum": [request.week_id.value]},
        "sections": {"type": "array", "items": branches[0] if len(branches) == 1 else {"anyOf": branches}},
    }
    if request.memo_addresses is not None and not request.repair_targets:
        root.update(memo_properties(request.memo_addresses))  # ADR-060
    return _object_schema(root)


def parse_weekly_proposal(
    content: str, request: WeeklyPlanningRequest
) -> tuple[ProposedSectionValue | WeeklyDayValues, ...]:
    try:
        body = json.loads(content)
        if not isinstance(body, dict) or set(body) != {"week_id", "sections"} or not isinstance(body["sections"], list):
            raise ProposalParseError("Weekly proposal must be {week_id, sections}")
        if body["week_id"] != request.week_id.value:
            raise ProposalRejectedError((WeeklyIssueCode.WEEK_MISMATCH.value,))
        values = []
        for item in body["sections"]:
            if isinstance(item, dict) and set(item) == {"section_key", "days", "reference_id"}:
                values.append(_parse_days(item))
                continue
            if not isinstance(item, dict) or set(item) != {
                "section_key", "value", "unresolved", "grounding_refs", "reference_id"
            } or not isinstance(item["grounding_refs"], list):
                raise ProposalParseError("Weekly section entries need exactly the five keys")
            values.append(ProposedSectionValue(
                section_key=item["section_key"],
                value=item["value"],
                unresolved=item["unresolved"],
                grounding_refs=tuple(item["grounding_refs"]),
                reference_id=item["reference_id"],
            ))
    except (ValueError, TypeError, KeyError, InvalidDomainValueError) as exc:
        raise ProposalParseError("Weekly proposal cannot be decoded") from exc
    return tuple(values)


def _parse_days(item: dict) -> WeeklyDayValues:
    key = item["section_key"]
    if not isinstance(key, str) or not key.strip():  # an empty days list never builds a value that checks it
        raise ProposalParseError("A days entry needs a section_key string")
    if item["reference_id"] is not None or not isinstance(item["days"], list):
        raise ProposalParseError("A days entry has no reference_id and a days list")
    days = []
    for entry in item["days"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"day", "value", "unresolved", "grounding_refs"}
            or not isinstance(entry["grounding_refs"], list)
        ):
            raise ProposalParseError("Weekly day entries need exactly the four keys")
        days.append((entry["day"], ProposedSectionValue(
            section_key=item["section_key"],
            value=entry["value"],
            unresolved=entry["unresolved"],
            grounding_refs=tuple(entry["grounding_refs"]),
        )))
    return WeeklyDayValues(item["section_key"], tuple(days))


def with_reference_labels(
    values: tuple[ProposedSectionValue | WeeklyDayValues, ...], request: WeeklyPlanningRequest
) -> tuple[ProposedSectionValue | WeeklyDayValues, ...]:
    """Outdoor value := the chosen candidate's catalog label (deterministic, like monthly)."""
    labels = dict(request.reference_candidates)
    return tuple(
        replace(v, value=labels[v.reference_id])
        if isinstance(v, ProposedSectionValue)
        and v.section_key == OUTDOOR_KEY and not v.unresolved and v.reference_id in labels
        else v
        for v in values
    )


# Q2 (2026-10-21, scope narrowed the same day): dates, weekdays, clock times and a person's
# name before 선생님 must come from the inputs. 「○○님 · ○○씨」 and 「n/n」 are common in
# children's activities (공주님 · 해님 · 1/2), so they are not blocked — the fact-scope
# warning tells the teacher to check them. ponytail: pattern heuristic — a name is
# "surname + 0-2 syllables" before 선생님 minus a stop-list; widen with a staff list if one exists.
_DATE_TIME = (
    re.compile(r"(?<!\d)\d{1,2}\s*월\s*\d{1,2}\s*일"),
    re.compile(r"[월화수목금토일]요일"),
    re.compile(r"\([월화수목금토일]\)"),
    re.compile(r"(?<!\d)\d{1,2}\s*:\s*\d{2}(?!\d)"),
    re.compile(r"(?:오전|오후)\s*\d{1,2}\s*시"),
    re.compile(r"(?<!\d)\d{1,2}\s*시(?!간)(?:\s*\d{1,2}\s*분)?"),
)
_SURNAMES = set(
    "김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반라왕금옥육인맹제모탁국어은편용"
)
_ROLE_WORDS = frozenset({
    "원장", "원감", "담임", "부모", "선생", "할머", "할아", "어머", "아버", "부모님", "주인", "사장",
    "경찰", "경찰관", "소방관", "소방", "의사", "간호", "기사", "교장", "교감", "반장", "보조", "영양",
    "보건", "마음", "아저", "아가", "손님", "고객", "집배원", "환경", "미화원", "선생님",
    "우리", "우리반", "우리원", "공주", "왕자", "임금", "요리", "미술", "음악", "체육", "과학",
    "유치원", "보육", "놀이", "숲", "생태", "영어", "원어민", "외부", "특별", "체험", "담당", "주임",
    "옆반", "형님반", "동생반", "멋진", "예쁜", "착한", "좋은", "새로운", "고마운", "반가운",
    "함께한", "다정한", "친절한", "따뜻한", "사랑하는", "좋아하는",
    # 한 · 운 endings are common in given names (지한 · 태운), so these modifiers are listed
    # one by one instead of excluding the ending (2026-10-21 decision C).
    "고운", "정다운", "정겨운", "강한", "소중한", "조용한", "성실한", "유쾌한", "차분한", "명랑한",
    "용감한", "편안한", "인자한", "엄격한", "공손한", "현명한", "진지한", "모든", "여러", "어느",
    "유능한", "공평한", "오신", "계신", "고우신",
})
# Endings that are not given names (좋아하는 · 즐거웠던 · 예쁜 · 다른 · 우리의 …): words, not names.
_MODIFIER_TAILS = frozenset("는던된쁜른의")
# A lone syllable before 「 선생님」 is a name only if it is a surname and not a common word
# (「이 선생님」 = this teacher, 「반 · 원 선생님」 = class / center teacher).
_SINGLE_STOP = frozenset("이그저반원전새옆각우")
_NOUN_TAILS = frozenset("날글솜말불꽃볍홀손해달별반")  # 날씨 · 손님 · 해님 · 햇살반 … are not people
# The token starts a word: the last three syllables of a longer word (고마우신 → 마우신) are no name.
_TEACHER_NAME = re.compile(r"(?<![가-힣])([가-힣]{1,3})(\s?)선생님")


def _is_person(token: str) -> bool:
    if len(token) == 1:  # 「김 선생님」 · 「김선생님」
        return token in _SURNAMES and token not in _SINGLE_STOP
    return (
        token[0] in _SURNAMES
        and token not in _ROLE_WORDS
        and token[-1] not in _NOUN_TAILS
        and token[-1] not in _MODIFIER_TAILS
    )


def _fact_tokens(text: str, *, people_only: bool) -> list[str]:
    tokens = [m.group(0) for pattern in _DATE_TIME for m in pattern.finditer(text)]
    tokens += [
        m.group(0) for m in _TEACHER_NAME.finditer(text) if not people_only or _is_person(m.group(1))
    ]
    return [re.sub(r"\s+", "", token) for token in tokens]


def unsupported_facts(value: str, allowed_text: str) -> tuple[str, ...]:
    """W-02: whole tokens are compared, never substrings — 「1월 2일」 is not in 「11월 2일」."""
    allowed = set(_fact_tokens(allowed_text, people_only=False))
    return tuple(dict.fromkeys(f for f in _fact_tokens(value, people_only=True) if f not in allowed))


def validate_weekly(
    values: tuple[ProposedSectionValue | WeeklyDayValues, ...], request: WeeklyPlanningRequest
) -> tuple[WeeklyIssue, ...]:
    issues: list[WeeklyIssue] = []
    seen: set[str] = set()
    candidate_names: set[tuple[str, str]] = set()
    for v in values:
        key = v.section_key
        if key in seen:
            issues.append(WeeklyIssue(WeeklyIssueCode.DUPLICATE_SECTION, key))
            continue
        seen.add(key)
        if key in request.teacher_input_keys:
            issues.append(WeeklyIssue(WeeklyIssueCode.TEACHER_INPUT_VALUE, key))
            continue
        target = request.target(key)
        if target is None:
            issues.append(WeeklyIssue(WeeklyIssueCode.SECTION_NOT_REQUESTED, key))
            continue
        if isinstance(v, WeeklyDayValues) != bool(target.days) or (
            isinstance(v, WeeklyDayValues) and tuple(day for day, _ in v.days) != target.days
        ):
            issues.append(WeeklyIssue(WeeklyIssueCode.DAY_MISMATCH, key))
            continue
        if isinstance(v, ProposedSectionValue):
            issues += _value_issues(v, target, request)
            if target.activity_type is not None:
                name, separator, description = v.value.partition(":")
                normalized = normalize_visible_text(name)
                candidate_name = (key.partition(".")[0], normalized)
                if v.unresolved or not separator or not name.strip() or not description.strip() or candidate_name in candidate_names:
                    issues.append(WeeklyIssue(WeeklyIssueCode.ACTIVITY_CANDIDATE_INVALID, key))
                elif any(normalize_visible_text(term) not in normalized for term in target.required_name_terms):
                    issues.append(WeeklyIssue(WeeklyIssueCode.ACTIVITY_CANDIDATE_INVALID, key, "required_activity_name_term_missing"))
                candidate_names.add(candidate_name)
            continue
        written = {normalize_visible_text(text) for text in request.other_day_values if text.strip()}
        for day, day_value in v.days:
            issues += _value_issues(day_value, target, request, day)
            if day_value.unresolved:
                continue  # WD-3: that day stays empty; no other day's value fills it
            visible = normalize_visible_text(day_value.value)
            if visible in written:
                issues.append(WeeklyIssue(WeeklyIssueCode.DAY_VALUE_REPEATED, key, day=day))
            written.add(visible)
    for target in request.targets:
        if target.section_key not in seen:
            issues.append(WeeklyIssue(WeeklyIssueCode.MISSING_SECTION, target.section_key))
    return tuple(issues)


def _value_issues(
    v: ProposedSectionValue, target: WeeklyTarget, request: WeeklyPlanningRequest, day: str | None = None
) -> list[WeeklyIssue]:
    key = v.section_key
    issues: list[WeeklyIssue] = []
    if v.unresolved:
        if key == THEME_KEY:
            issues.append(WeeklyIssue(WeeklyIssueCode.THEME_REQUIRED, key))
        return issues
    known_refs = {ref for ref, _ in request.evidence_texts}
    for ref in v.grounding_refs:
        if ref not in known_refs:
            issues.append(WeeklyIssue(WeeklyIssueCode.UNKNOWN_GROUNDING_REF, key, day=day))
        elif ref not in target.allowed_grounding_refs:
            issues.append(WeeklyIssue(WeeklyIssueCode.WRONG_SOURCE_GROUNDING, key, day=day))
    if key == OUTDOOR_KEY:
        if v.reference_id is None and not (request.reference_wiring and (target.parent_groundable or target.allowed_grounding_refs)):
            issues.append(WeeklyIssue(WeeklyIssueCode.REFERENCE_REQUIRED, key))
            return issues
        if v.reference_id is not None and v.reference_id not in dict(request.reference_candidates):
            issues.append(WeeklyIssue(WeeklyIssueCode.UNKNOWN_REFERENCE_ID, key))
        if v.reference_id is not None:
            if v.grounding_refs and not any(i.code in {
                WeeklyIssueCode.UNKNOWN_GROUNDING_REF, WeeklyIssueCode.WRONG_SOURCE_GROUNDING
            } for i in issues):
                issues.append(WeeklyIssue(WeeklyIssueCode.WRONG_SOURCE_GROUNDING, key))
            return issues  # the value is the catalog label (with_reference_labels)
    if v.reference_id is not None:
        issues.append(WeeklyIssue(WeeklyIssueCode.REFERENCE_FORBIDDEN, key))
    visible = normalize_visible_text(v.value)
    inherited = bool(target.parent_value.strip()) and visible == normalize_visible_text(target.parent_value)
    if (
        not v.grounding_refs
        and key not in (THEME_KEY, SAFETY_KEY)
        and not (key in PARENT_GROUNDABLE_KEYS and target.parent_value.strip())
        and not (key == OUTDOOR_KEY and target.parent_groundable and inherited)
    ):
        issues.append(WeeklyIssue(WeeklyIssueCode.RESOLVED_REQUIRES_GROUNDING, key, day=day))
    policy = [
        code for code in visible_text_violations(v.value, evidence_refs=request.context_source_refs)
        if not (key == SAFETY_KEY and code == "SAFETY_CONTENT_LEAKAGE")
    ]
    if policy:
        issues.append(WeeklyIssue(WeeklyIssueCode.TEXT_POLICY, key, ",".join(policy), day=day))
    # Q1: inheriting this cell's parent wording is not a copy, even when an institution
    # record reads the same; copying any other institution text still is.
    if visible in {normalize_visible_text(text) for text in (
        *(text for _, text in request.evidence_texts), *request.reference_examples
    )} and not inherited:
        issues.append(WeeklyIssue(WeeklyIssueCode.SOURCE_TEXT_COPY, key, day=day))
    if unsupported_facts(v.value, request.allowed_fact_text):
        issues.append(WeeklyIssue(WeeklyIssueCode.UNSUPPORTED_FACT, key, "date_time_or_teacher_name", day=day))
    return issues


def _codes(issues: tuple[WeeklyIssue, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(issue.code.value for issue in issues))


class WeeklyPlanner:
    """At most two provider calls: the plan and one repair of the flagged Sections."""

    def __init__(self, provider: WeeklyPlanningProvider) -> None:
        self._provider = provider

    def plan(self, request: WeeklyPlanningRequest) -> WeeklyPlanningOutcome:
        """One content-free line per request (CLAUDE.md §21): kind, outcome stage, repair, codes,
        fingerprint. Model, tokens and latency are logged by the transport per call."""
        kind = "cell" if request.cell_key else "document"
        try:
            outcome = self._plan(request)
        except Exception as exc:
            stage = (
                "validation" if isinstance(exc, ProposalRejectedError)
                else "parse" if isinstance(exc, ProposalParseError)
                else "provider"
            )
            codes = ",".join(getattr(exc, "validation_codes", ())) or type(exc).__name__
            _log.warning(
                "Weekly LLM planning failed: kind=%s stage=%s codes=%s fingerprint=%s",
                kind, stage, codes, request.request_fingerprint[:12],
            )
            raise
        _log.info(
            "Weekly LLM planned: kind=%s repaired=%d fingerprint=%s",
            kind, len(outcome.repaired), request.request_fingerprint[:12],
        )
        return outcome

    def _plan(self, request: WeeklyPlanningRequest) -> WeeklyPlanningOutcome:
        response = self._generate(request)
        content, memo_applied, memo_skipped = split_memo_applied(response.content, request.memo_addresses)
        values = with_reference_labels(parse_weekly_proposal(content, request), request)
        issues = validate_weekly(values, request)
        repaired: frozenset[str] = frozenset()
        prompt_version = request.prompt_version
        if issues and all(issue.code in REPAIRABLE for issue in issues):
            flagged = tuple(dict.fromkeys(issue.section_key for issue in issues))
            _log.info("Weekly LLM repair attempted: %s", ",".join(f"{i.code.value}@{i.section_key}" for i in issues))
            repair = replace(
                request,
                prompt_version=request.repair_prompt_version,
                user_content=json.dumps({
                    "original_request": json.loads(request.user_content),
                    "previous_answer": json.loads(content),
                    "fix_sections": [
                        {"section_key": i.section_key, "issue": i.code.value, **({"day": i.day} if i.day else {})}
                        for i in issues
                    ],
                }, ensure_ascii=False, sort_keys=True),
                repair_targets=flagged,
            )
            response = self._generate(repair)
            repaired_values = with_reference_labels(parse_weekly_proposal(response.content, repair), repair)
            keys = [v.section_key for v in repaired_values]
            duplicated = tuple(dict.fromkeys(k for k in keys if keys.count(k) > 1))
            if duplicated:  # the first answer refuses duplicates; the repair must not bypass that
                dup_issues = tuple(WeeklyIssue(WeeklyIssueCode.DUPLICATE_SECTION, k) for k in duplicated)
                # Unvalidated model strings never reach the log: only the code and how many (R-01).
                _log.warning("Weekly LLM repair rejected: DUPLICATE_SECTION x%d", len(duplicated))
                raise ProposalRejectedError(_codes(dup_issues), dup_issues)
            # The repair may only answer requested Sections, as the first answer may (W4b-01):
            # a stray Section would otherwise be dropped silently at the merge below.
            requested = {t.section_key for t in request.targets}
            stray = tuple(dict.fromkeys(k for k in keys if k not in requested))
            if stray:
                stray_issues = tuple(
                    WeeklyIssue(
                        WeeklyIssueCode.TEACHER_INPUT_VALUE
                        if k in request.teacher_input_keys
                        else WeeklyIssueCode.SECTION_NOT_REQUESTED,
                        k,
                    )
                    for k in stray
                )
                _log.warning("Weekly LLM repair rejected: %s", ",".join(_codes(stray_issues)))
                raise ProposalRejectedError(_codes(stray_issues), stray_issues)
            patched = {v.section_key: v for v in repaired_values}
            # Only the flagged Sections may change; every other value stays as first written.
            values = tuple(patched.get(v.section_key, v) if v.section_key in flagged else v for v in values)
            issues = validate_weekly(values, request)
            repaired, prompt_version = frozenset(flagged), request.repair_prompt_version
        if issues:
            _log.warning("Weekly LLM proposal rejected: %s", ",".join(_codes(issues)))
            raise ProposalRejectedError(_codes(issues), issues)
        return WeeklyPlanningOutcome(
            values=values,
            model=response.model,
            prompt_version=prompt_version,
            initial_prompt_version=request.prompt_version,
            packet_fingerprint=request.packet_fingerprint,
            repaired=repaired,
            request_id=response.request_id,
            memo_applied=memo_applied,
            memo_skipped=memo_skipped,
        )

    def _generate(self, request: WeeklyPlanningRequest) -> RawLlmResponse:
        response = self._provider.generate_weekly(request)
        if not is_compatible_monthly_model(response.model):
            raise ProposalRejectedError(("UNEXPECTED_MODEL",))
        return response
