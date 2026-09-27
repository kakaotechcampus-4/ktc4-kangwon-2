"""연간계획안 검사기 — 규칙은 고르지 않고 검사한다 (ADR-014).

규칙 엔진은 계획안을 만들지 않는다. 이미 만들어진 계획안을 읽고 어긋난 곳을 짚는다.

결과를 두 가지로 나눠 낸다.

    VIOLATION    확실히 어긋났다.      교사가 고쳐야 한다
    UNVERIFIED   판단할 근거가 없다.   교사가 채워야 한다

**근거 없이 「위반」이라고 하면 없는 기준으로 교사를 막는다.**
`safety_education_legal_v1.json` 의 `rule_must_not` 이 「배치 Source 가 없을 때 법적 충족을
주장」을 금지한다. 충족을 못 주장하면 위반도 못 주장한다 — 방향만 다르고 같은 문제다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

VIOLATION = "VIOLATION"
UNVERIFIED = "UNVERIFIED"

# 학년도는 3월에 시작해 익년 2월에 끝난다. months 배열은 항상 이 순서다 (api-spec §4).
# 주기 계산이 배열 순서를 그대로 믿으므로 순서가 틀리면 아래에서 거부한다.
SCHOOL_YEAR_MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)

# 법정 시수 원본은 p0-planning 쪽 하나만 둔다 (ADR-014). backend 에 복사본을 만들지 않는다.
# ponytail: backend 이미지의 빌드 컨텍스트가 ./backend 라 이 파일은 컨테이너 안에 없다.
#           지금은 검사기를 부르는 엔드포인트가 없어서 문제가 되지 않는다. 엔드포인트를
#           만드는 PR 이 컨텍스트를 저장소 루트로 올리고 Dockerfile 에 COPY 를 한 줄 더한다.
LEGAL_RULES_PATH = (
    Path(__file__).resolve().parents[5]
    / "p0-planning"
    / "data"
    / "rules"
    / "safety_education_legal_v1.json"
)


@dataclass(frozen=True, slots=True)
class Violation:
    """검사기가 찾은 한 건. `detail` 은 교사에게 그대로 보여도 되는 한 줄이다."""

    rule: str
    severity: str
    detail: str
    month: int | None = None


@dataclass(frozen=True, slots=True)
class PlannedActivity:
    """계획안에 배치된 활동 하나. DB 행이 아니라 이미 읽어온 값이다.

    **연령은 범위가 아니라 점의 집합이다.** 활동은 떨어진 연령을 지원할 수 있다 —
    활동 참고자료에 강강술래와 투호놀이가 `supported_ages: [3, 5]` 로 들어 있다.
    만 4세는 빼고 만 3세와 만 5세만 받는다는 뜻이다.

    범위(`age_min`~`age_max`)로 읽으면 그 둘이 만 4세도 지원한다고 잘못 읽힌다.
    혼합반이 실측 39% 라 만 3~5세 반이 제일 흔한데 거기서 검사가 통과해 버린다.

    **반은 반대다 — 반 연령은 범위다.** 계획안 실측 369건에서 한 반이 떨어진 연령을
    갖는 경우가 0건이다(docs/PRD.md 「연령 표기」).
    """

    month: int
    title: str
    supported_ages: frozenset[int]


@lru_cache(maxsize=1)
def load_legal_rules() -> Mapping[str, Any]:
    """법령 전사 파일을 읽는다. 값을 보완하거나 추측하지 않는다."""
    return json.loads(LEGAL_RULES_PATH.read_text(encoding="utf-8"))


def legal_hours(
    months: Sequence[Mapping[str, Any]],
    rules: Mapping[str, Any] | None = None,
) -> list[Violation]:
    """법정 안전교육 6구분의 주기와 연간 시수를 검사한다.

    P0 에서는 대부분 UNVERIFIED 가 나온다. 배치 계획 입력이 없으면 주기를 셀 수 없고,
    연간계획안에는 교육 시간을 적는 칸 자체가 없어 시수는 어느 경우에도 셀 수 없다.
    """
    rules = rules if rules is not None else load_legal_rules()
    _require_approved(rules)
    _require_school_year_order(months)
    _require_legal_categories(months, rules)

    # 한 달이라도 배치를 모르면 그 해의 주기를 셀 수 없다. 모르는 달에 교육이 있었을
    # 수도 없었을 수도 있어서, 센 결과가 위반인지 아닌지 가릴 수 없다.
    placement_unknown = any(m["safety_education_state"] == "SOURCE_REQUIRED" for m in months)
    found: list[Violation] = []
    for category in rules["categories"]:
        label = category["official_label"]
        if placement_unknown:
            found.append(
                Violation(
                    rule="legal_hours",
                    severity=UNVERIFIED,
                    detail=(
                        f"{label} — 안전교육 배치 계획이 없어 "
                        f"{category['interval_verbatim']} 주기를 확인할 수 없습니다"
                    ),
                )
            )
        else:
            found.extend(_interval_gaps(months, category))
        found.append(
            Violation(
                rule="legal_hours",
                severity=UNVERIFIED,
                detail=(
                    f"{label} — 연간계획안에 교육 시간이 없어 "
                    f"{category['annual_hours_min_verbatim']} 충족을 확인할 수 없습니다"
                ),
            )
        )
    return found


def age(
    activities: Iterable[PlannedActivity],
    class_age_min: int,
    class_age_max: int,
) -> list[Violation]:
    """반 연령을 다 받쳐주지 못하는 활동을 짚는다.

    혼합반(3~5세 한 반)이면 활동이 세 연령을 모두 지원해야 한다. 하나라도 빠지면
    그 반의 누군가는 그 활동을 못 한다. 연령은 학년도 기준 연 나이다 — 만 나이가 아니다.

    **지원 연령을 하나씩 확인한다.** 최소·최대만 보면 가운데가 비어도 통과한다 —
    `supported_ages` 가 `{3, 5}` 인 활동이 만 3~5세 반을 다 받는다고 읽힌다.
    """
    if class_age_min > class_age_max:
        raise ValueError(f"반 연령 범위가 뒤집혔다: {class_age_min}~{class_age_max}")

    needed = set(range(class_age_min, class_age_max + 1))
    found: list[Violation] = []
    for activity in activities:
        missing = sorted(needed - activity.supported_ages)
        if not missing:
            continue
        supported = "·".join(str(a) for a in sorted(activity.supported_ages))
        found.append(
            Violation(
                rule="age",
                severity=VIOLATION,
                month=activity.month,
                detail=(
                    f"「{activity.title}」은 {supported}세 활동입니다. "
                    f"반은 {class_age_min}~{class_age_max}세인데 "
                    f"{'·'.join(str(a) for a in missing)}세가 빠집니다"
                ),
            )
        )
    return found


def _require_approved(rules: Mapping[str, Any]) -> None:
    """사람이 승인한 법령 파일만 쓴다.

    파일 자체가 `runtime_active == (domain_owner_approval == "HUMAN_APPROVED")` 를 항상
    만족해야 한다고 정한다. 승인 없이 검사를 돌리면 검토받지 않은 기준으로 교사를 막는다.
    """
    review = rules["review"]
    approved = review["domain_owner_approval"] == "HUMAN_APPROVED"
    if not approved or review["runtime_active"] != approved:
        raise ValueError(
            "승인되지 않은 법령 파일이다. "
            f"domain_owner_approval={review['domain_owner_approval']!r} "
            f"runtime_active={review['runtime_active']!r}"
        )


def _require_legal_categories(
    months: Sequence[Mapping[str, Any]],
    rules: Mapping[str, Any],
) -> None:
    """`safety_education` 에 법정 6구분 밖의 값이 들어오면 거부한다.

    조용히 무시하면 그 달에 교육이 배치됐는데도 빈 달로 세어 **없는 위반**이 나온다.
    「생활안전」 같은 기관 label 을 법정 구분으로 매핑하지도 않는다
    (`safety_education_legal_v1.json` 의 `rule_must_not`). 어느 쪽에도 넣을 수 없으므로
    받지 않는다 — 기관 label 은 `institution_category` 로 따로 관리한다.
    """
    legal = {c["category_id"] for c in rules["categories"]}
    unknown = sorted({v for m in months for v in m["safety_education"]} - legal)
    if unknown:
        raise ValueError(f"법정 6구분에 없는 안전교육 값이다: {', '.join(unknown)}")


def _require_school_year_order(months: Sequence[Mapping[str, Any]]) -> None:
    order = [m["month"] for m in months]
    if order != list(SCHOOL_YEAR_MONTHS):
        raise ValueError(f"months 는 3월부터 익년 2월까지 12개여야 한다. 받은 순서: {order}")


def _interval_gaps(
    months: Sequence[Mapping[str, Any]],
    category: Mapping[str, Any],
) -> list[Violation]:
    """한 구분이 `interval_months` 를 넘겨 비어 있는 구간을 찾는다.

    학년도 시작과 끝도 구간으로 센다. 3월부터 8월까지 교통안전이 한 번도 없으면
    「2개월에 1회 이상」을 못 지킨 것이고, 이건 배치를 알고 있을 때만 말할 수 있다.
    """
    span = category["interval_months"]
    placed = [i for i, m in enumerate(months) if category["category_id"] in m["safety_education"]]

    found: list[Violation] = []
    for before, after in zip([-1, *placed], [*placed, len(months)], strict=True):
        empty = after - before - 1
        if empty < span:
            continue
        first = months[before + 1]["month"]
        last = months[after - 1]["month"]
        found.append(
            Violation(
                rule="legal_hours",
                severity=VIOLATION,
                month=first,
                detail=(
                    f"{category['official_label']} — {first}월부터 {last}월까지 {empty}개월 동안 "
                    f"없습니다. 법은 {category['interval_verbatim']}입니다"
                ),
            )
        )
    return found
