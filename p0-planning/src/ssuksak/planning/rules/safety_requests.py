"""교사 메모의 법정 안전교육 개수 · 주차 요청을 주에 배치한다(ADR-057 2층).

LLM 은 요청을 정해진 모양(`SafetyRequest`)으로 뽑기만 한다. 어느 주에 무엇을 둘지는 여기서 정한다.
- 짚은 주를 먼저 채우고, 남은 횟수는 앞쪽 빈 주부터 채운다.
- 한 범주를 여러 주에 둘 때 주마다 다른 문장이다: 첫 주는 LLM 이 쓴 후보, 그다음 주들은
  그 범주의 공식 내용 항목 중 후보가 인용하지 않은 것을 하나씩(RULE_ONLY). 항목 수가 상한이다.
- 못 채운 것은 알림(`RULE_CONFLICT`)으로 남긴다. 생성을 막지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.safety_placement import STATUTORY_SHORT_LABELS
from ..domain.teacher_memo import MemoNotice, MemoNoticeReason, SafetyRequest

SAFETY_REQUEST_RULE_ID = "monthly.safety.teacher_request"
SAFETY_REQUEST_RULE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class SafetyRequestPlacement:
    # 범주마다 더 만들 후보: (category_id, 공식 내용 항목 ref, 항목 글) — 순서대로 두 번째 문장부터.
    extras: tuple[tuple[str, str, str], ...]
    # week_id → (category_id, n): n = 0 이면 LLM 후보, n ≥ 1 이면 그 범주의 n 번째 extra.
    weeks: dict[str, tuple[str, int]]
    notices: tuple[MemoNotice, ...]


def place_safety_requests(
    requests: tuple[SafetyRequest, ...],
    *,
    week_ids: tuple[str, ...],
    allowed: dict[str, tuple[tuple[str, str], ...]],  # category_id → 공식 내용 항목 (ref, 글)
    cited: dict[str, tuple[str, ...]],  # category_id → LLM 후보가 인용한 ref
) -> SafetyRequestPlacement:
    merged: dict[str, tuple[list[str], int]] = {}
    for request in requests:
        if request.slot not in allowed:
            continue  # 스키마가 막는다. 생활안전 · 모르는 범주는 배치하지 않는다.
        weeks, count = merged.setdefault(request.slot, ([], 0))
        weeks.extend(w for w in request.weeks if w in week_ids and w not in weeks)
        merged[request.slot] = (weeks, max(count, request.count))

    spare = {
        category: [(ref, text) for ref, text in allowed[category] if ref not in cited.get(category, ())]
        for category in merged
    }
    used = {category: 0 for category in merged}  # 쓴 문장 수
    placed: dict[str, tuple[str, int]] = {}
    missed: dict[str, list[str]] = {category: [] for category in merged}

    def take(category: str) -> int | None:
        n = used[category]
        if n > len(spare[category]):
            return None
        used[category] += 1
        return n

    for category, (weeks, _) in merged.items():
        for week in weeks:
            if week in placed or (n := take(category)) is None:
                missed[category].append(week)
                continue
            placed[week] = (category, n)
    for category, (_, count) in merged.items():
        while used[category] < count:
            free = next((w for w in week_ids if w not in placed), None)
            if free is None or (n := take(category)) is None:
                break
            placed[free] = (category, n)

    notices = []
    for category, (weeks, count) in merged.items():
        label = STATUTORY_SHORT_LABELS.get(category, category)
        if used[category] < count:
            notices.append(f"{label} {count}번 중 {used[category]}번만 넣었어요")
        moved = [str(week_ids.index(w) + 1) for w in missed[category]]
        if moved:
            notices.append(f"{label}: {', '.join(moved)}주차에는 넣지 못했어요")
    extras = tuple(
        (category, *spare[category][n - 1])
        for category in merged
        for n in range(1, used[category])
    )
    return SafetyRequestPlacement(
        extras, placed, tuple(MemoNotice(text, MemoNoticeReason.RULE_CONFLICT) for text in notices)
    )
