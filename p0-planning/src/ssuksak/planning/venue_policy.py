"""Reviewed destinations and explicit teacher input, never inferred facility names."""

import json
import re
from dataclasses import asdict, is_dataclass

from .domain.provenance import AuditEventType, GenerationMethod

VENUE_POLICY_TAG = "+teacher-venues-v2"
VENUE_GUIDANCE = (
    " 교사가 명시한 teacher_venues 또는 현재 요청 사항에 없는 특정 장소를 방문할 활동으로 쓰지 않는다. "
    "teacher_venues는 확정 부모 중 교사가 직접 입력·수정한 값에서 확인한 장소다. AI 초안이나 단순 확정만으로 허용하지 않는다. "
    "시설 종류·창작 놀이 이름을 실제 장소로 추정하지 않는다. 다른 기관의 현장학습은 우리 원의 일정이 아니다. "
    "문제가 된 장소 이름만 지워 일반 활동으로 바꾸지 말고, 다른 적격 근거의 활동을 고른다. "
    "명시한 장소도 이용 가능·예약·일정이 확정됐다고 단정하지 않으며, 가지 말라는 요청을 허용으로 읽지 않는다. "
)

# User example / venue cross-review; the last six are named-place exclusions in
# docs/activity-reference-v0-human-review.md §5. Generic museum/play names are not entries.
REVIEWED_VENUES = {
    "배산유아숲터": "유아숲터", "부산시민공원": "공원", "한강공원": "공원",
    "국립중앙박물관": "박물관", "탄금공원": "공원", "탄금대숲": "숲",
    "능암늪생태공원": "생태공원", "만수계곡": "계곡", "무궁화길": "길", "성불산": "산",
}
_DENIAL = re.compile(
    r"제외|금지|말고|쓰지|넣지|방문하지|가지(?:않|마)|안가|빼(?:줘|주|고|요)|"
    r"안(?:돼|되)|생략|피해|피하|하지마|위험|대신(?:$|실내|교실|원안|다른)"
)
_POSITIVE = re.compile(r"가고|가요|방문|산책|체험|견학|소풍|나들이|예정|반영|넣어")
_FIELD_TRIP = re.compile(r"현장\s*(?:체험\s*학습|학습|체험)|견학")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def named_venues(text: str) -> frozenset[str]:
    # shortcut: unknown venues pass; extend this list only after reviewing an actual place name.
    compact = _compact(text)
    return frozenset(name for name in REVIEWED_VENUES if _compact(name) in compact)


def authorized_venues(teacher_text: str) -> frozenset[str]:
    allowed = set()
    denied = set()
    for clause in re.split(r"[\n.!?;]", teacher_text):
        clause = _compact(clause)
        mentions = sorted((clause.index(name), name) for name in named_venues(clause))
        for index, (start, name) in enumerate(mentions):
            end = mentions[index + 1][0] if index + 1 < len(mentions) else len(clause)
            local = clause[start:end]
            # shortcut: ambiguous negative lists stay denied; add a parser if real memos need broader grammar.
            if not _DENIAL.search(local) and (not _DENIAL.search(clause) or _POSITIVE.search(local)):
                allowed.add(name)
            else:
                denied.add(name)
    return frozenset(allowed - denied)


def unrequested_venues(text: str, teacher_text: str = "") -> frozenset[str]:
    return named_venues(text) - authorized_venues(teacher_text)


def venue_bound_evidence(text: str) -> bool:
    return bool(named_venues(text) or _FIELD_TRIP.search(text))


def venue_memo(user_content: str) -> str:
    """Only original server-authored teacher facts; rejected output is never a source."""
    body = json.loads(user_content)
    body = body.get("original_request", body.get("original", body))
    return "\n".join((body.get("teacher_memo", {}).get("text", ""), *body.get("teacher_venues", ())))


def teacher_authored(item) -> bool:
    for event in reversed(item.audit.events):
        if event.event_type is AuditEventType.TEACHER_EDITED and event.value_change is not None:
            if event.value_change.before != event.value_change.after:
                return True
        elif event.event_type in {AuditEventType.REGENERATED, AuditEventType.CANDIDATE_COPIED}:
            return False
    return item.generation is not None and item.generation.method in {
        GenerationMethod.MANUAL, GenerationMethod.IMPORTED, GenerationMethod.TEACHER_EDIT,
    }


def parent_teacher_venues(items, *, values=(), memo: str = "", inherited=()) -> tuple[str, ...]:
    items = tuple(items)
    current = named_venues("\n".join((*values, *(item.value for item in items))))
    explicit = authorized_venues(memo) | set(inherited)
    for item in items:
        if teacher_authored(item):
            explicit |= authorized_venues(item.value)
    denied = named_venues(memo) - authorized_venues(memo)
    return tuple(sorted((current & explicit) - denied))


def venue_name_only_removed(before: str, after: str) -> bool:
    def normalize(text):
        return re.sub(r"[^\w]", "", text)
    before, after = normalize(before), normalize(after)
    for name in named_venues(before):
        if after in {before.replace(name, ""), before.replace(name, REVIEWED_VENUES[name])}:
            return True
    return False


def venue_name_only_repair(before, after) -> bool:
    if isinstance(before, str) and isinstance(after, str):
        return venue_name_only_removed(before, after)
    if is_dataclass(before) and is_dataclass(after):
        before, after = asdict(before), asdict(after)
    if isinstance(before, dict) and isinstance(after, dict):
        return any(venue_name_only_repair(before[key], after[key]) for key in before.keys() & after.keys())
    if isinstance(before, (tuple, list)) and isinstance(after, (tuple, list)):
        return any(venue_name_only_repair(old, new) for old, new in zip(before, after))
    return False
