"""Weekly LLM planning (W3b): one document-level request, strict parse, validation, one repair.

docs/weekly-plan-contract.md §10-1 · §11-1 and the 2026-10-21 decisions. The Rule fixes
what may be written (target Sections, allowed grounding refs, ranked outdoor candidates,
parent context); the LLM writes values and picks refs / one outdoor reference inside that
range; the Application attaches parent citations and the Activity Reference itself.
Monthly planner types are reused read-only; weekly codes live here (ADR-033).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from ..domain.errors import InvalidDomainValueError
from ..domain.week_period import WeekId
from .contracts import (
    ProposalParseError,
    ProposalRejectedError,
    ProposedSectionValue,
    RawLlmResponse,
    is_compatible_monthly_model,
)
from .text_policy import normalize_visible_text, visible_text_violations

_log = logging.getLogger(__name__)

WEEKLY_PROMPT_VERSION = "weekly-planner-v1"
WEEKLY_REPAIR_PROMPT_VERSION = "weekly-planner-repair-v1"
SAFETY_KEY = "safety_education"
OUTDOOR_KEY = "outdoor_play"
THEME_KEY = "theme"
# Q1 (2026-10-21): these may stand on the parent value alone (PARENT_PLAN grounding).
PARENT_GROUNDABLE_KEYS = frozenset({"focus", "goals", "basic_habit"})

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


class WeeklyIssueCode(str, Enum):
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


# Same idea as the monthly REPAIRABLE_CODES: wording or a ref choice inside a fixed slot.
REPAIRABLE = frozenset({
    WeeklyIssueCode.TEXT_POLICY,
    WeeklyIssueCode.SOURCE_TEXT_COPY,
    WeeklyIssueCode.WRONG_SOURCE_GROUNDING,
    WeeklyIssueCode.UNSUPPORTED_FACT,
})


@dataclass(frozen=True, slots=True)
class WeeklyIssue:
    code: WeeklyIssueCode
    section_key: str
    detail: str = ""  # content-free: a code-level reason, never generated text


@dataclass(frozen=True, slots=True)
class WeeklyTarget:
    section_key: str
    allowed_grounding_refs: tuple[str, ...] = ()
    parent_value: str = ""
    semantic_variant: str | None = None


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

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError("WeeklyPlanningRequest.week_id must be WeekId")
        keys = [target.section_key for target in self.targets]
        if len(set(keys)) != len(keys) or THEME_KEY not in keys:
            raise InvalidDomainValueError("WeeklyPlanningRequest targets must be unique and include theme")
        if set(keys) & self.teacher_input_keys:
            raise InvalidDomainValueError("Teacher-input Sections are never LLM targets")

    def target(self, section_key: str) -> WeeklyTarget | None:
        return next((t for t in self.targets if t.section_key == section_key), None)


@dataclass(frozen=True, slots=True)
class WeeklyPlanningOutcome:
    values: tuple[ProposedSectionValue, ...]
    model: str
    prompt_version: str
    initial_prompt_version: str
    packet_fingerprint: str
    repaired: frozenset[str] = frozenset()
    request_id: str | None = None

    def value(self, section_key: str) -> ProposedSectionValue | None:
        return next((v for v in self.values if v.section_key == section_key), None)

    def prompt_version_for(self, section_key: str) -> str:
        """The prompt that produced this cell's current value (initial or repair)."""
        return self.prompt_version if section_key in self.repaired else self.initial_prompt_version


class WeeklyPlanningProvider(Protocol):
    def generate_weekly(self, request: WeeklyPlanningRequest) -> RawLlmResponse: ...


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
                **({"reference_candidates": [
                    {"reference_id": rid, "label": label} for rid, label in reference_candidates
                ]} if t.section_key == OUTDOOR_KEY else {}),
            }
            for t in targets
        ],
        "never_write": sorted(teacher_input_keys),
        "evidence": [{"grounding_ref": r, "text": text, "grounding_class": c} for r, text, c in evidence],
    }
    allowed = " ".join([
        *(value for _, value in parent_context),
        *(text for _, text, _ in evidence),
        *(label for _, label in reference_candidates),
    ])
    return WeeklyPlanningRequest(
        prompt_version=WEEKLY_PROMPT_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True),
        week_id=week_id,
        targets=targets,
        teacher_input_keys=teacher_input_keys,
        evidence_texts=tuple((r, text) for r, text, _ in evidence),
        reference_candidates=reference_candidates,
        allowed_fact_text=allowed,
        packet_fingerprint=packet_fingerprint,
    )


def parse_weekly_proposal(content: str, request: WeeklyPlanningRequest) -> tuple[ProposedSectionValue, ...]:
    try:
        body = json.loads(content)
        if not isinstance(body, dict) or set(body) != {"week_id", "sections"} or not isinstance(body["sections"], list):
            raise ProposalParseError("Weekly proposal must be {week_id, sections}")
        if body["week_id"] != request.week_id.value:
            raise ProposalRejectedError((WeeklyIssueCode.WEEK_MISMATCH.value,))
        values = []
        for item in body["sections"]:
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


def with_reference_labels(
    values: tuple[ProposedSectionValue, ...], request: WeeklyPlanningRequest
) -> tuple[ProposedSectionValue, ...]:
    """Outdoor value := the chosen candidate's catalog label (deterministic, like monthly)."""
    labels = dict(request.reference_candidates)
    return tuple(
        replace(v, value=labels[v.reference_id])
        if v.section_key == OUTDOOR_KEY and not v.unresolved and v.reference_id in labels
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
})
# Modifier endings (고마운 · 함께한 · 좋아하는 · 즐거웠던 …): words, not names. ponytail: a rare
# given name ending in 한 is missed rather than blocking ordinary sentences.
_MODIFIER_TAILS = frozenset("운는던된쁜른한")
# A lone syllable before 「 선생님」 is a name only if it is a surname and not a common word
# (「이 선생님」 = this teacher, 「반 · 원 선생님」 = class / center teacher).
_SINGLE_STOP = frozenset("이그저반원전새옆각우")
_NOUN_TAILS = frozenset("날글솜말불꽃볍홀손해달별반")  # 날씨 · 손님 · 해님 · 햇살반 … are not people
_TEACHER_NAME = re.compile(r"([가-힣]{1,3})(\s?)선생님")


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


def validate_weekly(values: tuple[ProposedSectionValue, ...], request: WeeklyPlanningRequest) -> tuple[WeeklyIssue, ...]:
    issues: list[WeeklyIssue] = []
    known_refs = {ref for ref, _ in request.evidence_texts}
    evidence_texts = {normalize_visible_text(text) for _, text in request.evidence_texts}
    candidates = dict(request.reference_candidates)
    seen: set[str] = set()
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
        if v.unresolved:
            if key == THEME_KEY:
                issues.append(WeeklyIssue(WeeklyIssueCode.THEME_REQUIRED, key))
            continue
        for ref in v.grounding_refs:
            if ref not in known_refs:
                issues.append(WeeklyIssue(WeeklyIssueCode.UNKNOWN_GROUNDING_REF, key))
            elif ref not in target.allowed_grounding_refs:
                issues.append(WeeklyIssue(WeeklyIssueCode.WRONG_SOURCE_GROUNDING, key))
        if key == OUTDOOR_KEY:
            if v.reference_id is None:
                issues.append(WeeklyIssue(WeeklyIssueCode.REFERENCE_REQUIRED, key))
            elif v.reference_id not in candidates:
                issues.append(WeeklyIssue(WeeklyIssueCode.UNKNOWN_REFERENCE_ID, key))
            continue  # the value is the catalog label (with_reference_labels)
        if v.reference_id is not None:
            issues.append(WeeklyIssue(WeeklyIssueCode.REFERENCE_FORBIDDEN, key))
        if (
            not v.grounding_refs
            and key not in (THEME_KEY, SAFETY_KEY)
            and not (key in PARENT_GROUNDABLE_KEYS and target.parent_value.strip())
        ):
            issues.append(WeeklyIssue(WeeklyIssueCode.RESOLVED_REQUIRES_GROUNDING, key))
        policy = [
            code for code in visible_text_violations(v.value)
            if not (key == SAFETY_KEY and code == "SAFETY_CONTENT_LEAKAGE")
        ]
        if policy:
            issues.append(WeeklyIssue(WeeklyIssueCode.TEXT_POLICY, key, ",".join(policy)))
        # Q1: inheriting this cell's parent wording is not a copy, even when an institution
        # record reads the same; copying any other institution text still is.
        visible = normalize_visible_text(v.value)
        inherited = bool(target.parent_value.strip()) and visible == normalize_visible_text(target.parent_value)
        if visible in evidence_texts and not inherited:
            issues.append(WeeklyIssue(WeeklyIssueCode.SOURCE_TEXT_COPY, key))
        if unsupported_facts(v.value, request.allowed_fact_text):
            issues.append(WeeklyIssue(WeeklyIssueCode.UNSUPPORTED_FACT, key, "date_time_or_teacher_name"))
    for target in request.targets:
        if target.section_key not in seen:
            issues.append(WeeklyIssue(WeeklyIssueCode.MISSING_SECTION, target.section_key))
    return tuple(issues)


def _codes(issues: tuple[WeeklyIssue, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(issue.code.value for issue in issues))


class WeeklyPlanner:
    """At most two provider calls: the plan and one repair of the flagged Sections."""

    def __init__(self, provider: WeeklyPlanningProvider) -> None:
        self._provider = provider

    def plan(self, request: WeeklyPlanningRequest) -> WeeklyPlanningOutcome:
        response = self._generate(request)
        values = with_reference_labels(parse_weekly_proposal(response.content, request), request)
        issues = validate_weekly(values, request)
        repaired: frozenset[str] = frozenset()
        prompt_version = request.prompt_version
        if issues and all(issue.code in REPAIRABLE for issue in issues):
            flagged = tuple(dict.fromkeys(issue.section_key for issue in issues))
            _log.info("Weekly LLM repair attempted: %s", ",".join(f"{i.code.value}@{i.section_key}" for i in issues))
            repair = replace(
                request,
                prompt_version=WEEKLY_REPAIR_PROMPT_VERSION,
                user_content=json.dumps({
                    "original_request": json.loads(request.user_content),
                    "previous_answer": json.loads(response.content),
                    "fix_sections": [{"section_key": i.section_key, "issue": i.code.value} for i in issues],
                }, ensure_ascii=False, sort_keys=True),
                repair_targets=flagged,
            )
            response = self._generate(repair)
            repaired_values = with_reference_labels(parse_weekly_proposal(response.content, repair), repair)
            keys = [v.section_key for v in repaired_values]
            duplicated = tuple(dict.fromkeys(k for k in keys if keys.count(k) > 1))
            if duplicated:  # the first answer refuses duplicates; the repair must not bypass that
                dup_issues = tuple(WeeklyIssue(WeeklyIssueCode.DUPLICATE_SECTION, k) for k in duplicated)
                _log.warning("Weekly LLM repair rejected: duplicate %s", ",".join(duplicated))
                raise ProposalRejectedError(_codes(dup_issues), dup_issues)
            patched = {v.section_key: v for v in repaired_values}
            # Only the flagged Sections may change; every other value stays as first written.
            values = tuple(patched.get(v.section_key, v) if v.section_key in flagged else v for v in values)
            issues = validate_weekly(values, request)
            repaired, prompt_version = frozenset(flagged), WEEKLY_REPAIR_PROMPT_VERSION
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
        )

    def _generate(self, request: WeeklyPlanningRequest) -> RawLlmResponse:
        response = self._provider.generate_weekly(request)
        if not is_compatible_monthly_model(response.model):
            raise ProposalRejectedError(("UNEXPECTED_MODEL",))
        return response
