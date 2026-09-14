"""법정 안전교육 Rule Domain Value Object.

docs/open-decisions.md OD-M04 (`RESOLVED_FOR_P0`):

    법령 Rule은 법정 구분 / 실시 간격 / 연간 최소 시간 / 적용 연령·대상 /
    source·version만 저장한다. **법령 데이터에 특정 월 assignment를 만들지 않는다.**
    Rule은 법정 조건을 검증하며 특정 월·주 배치를 자동 창작하지 않는다.

비법정 기관 label(`생활안전`·`심폐소생술`·`장애인식 개선`·`소방안전`·`비상대응`)을
법정 구분으로 자동 매핑하지 않는다. 이 타입에는 법정 구분만 들어간다.

Domain은 Pydantic을 알지 못한다. 원시 JSON 검증은 Adapter가 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STATUTORY = "STATUTORY"

LEGAL_CATEGORY_COUNT = 6
"""아동복지법 시행령 별표6 <개정 2022. 6. 21.>의 구분 수."""


@dataclass(frozen=True, slots=True)
class SafetyCategory:
    """법정 안전교육 구분 하나.

    `interval_months`와 `annual_hours_min`은 법령이 정한 **간격과 총량**이다.
    특정 월 지정 필드를 두지 않는다. 별표6과 시행령 제28조 전문에 월 지정이
    0건이기 때문이다.
    """

    category_id: str
    official_label: str
    interval_months: int
    annual_hours_min: int

    def __post_init__(self) -> None:
        for name, value in (
            ("category_id", self.category_id),
            ("official_label", self.official_label),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"SafetyCategory.{name}는 비어 있을 수 없다")
        if self.interval_months <= 0:
            raise ValueError(
                f"실시 간격은 1개월 이상이어야 한다: {self.category_id}"
            )
        if self.annual_hours_min <= 0:
            raise ValueError(
                f"연간 최소 시간은 1시간 이상이어야 한다: {self.category_id}"
            )


@dataclass(frozen=True, slots=True)
class SafetyLegalRule:
    """versioned 법정 Rule 데이터.

    `placement_policy_version`은 `legal_rule_version`과 **분리**된다. P0에서는
    제품 기본 배치 정책을 발행하지 않으므로 `None`이며, 값이 생기면 별도
    데이터로 관리한다.
    """

    legal_rule_version: str
    normative_status: str
    categories: tuple[SafetyCategory, ...]
    age_tier_label: str
    placement_policy_version: str | None = None
    runtime_active: bool = False
    _by_id: dict[str, SafetyCategory] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.legal_rule_version.strip():
            raise ValueError("legal_rule_version은 비어 있을 수 없다")
        if self.normative_status != STATUTORY:
            raise ValueError(
                f"법정 Rule의 normative_status는 {STATUTORY}여야 한다: "
                f"{self.normative_status}"
            )
        if len(self.categories) != LEGAL_CATEGORY_COUNT:
            raise ValueError(
                f"별표6 법정 구분은 {LEGAL_CATEGORY_COUNT}개여야 한다: "
                f"{len(self.categories)}개"
            )
        index: dict[str, SafetyCategory] = {}
        for category in self.categories:
            if category.category_id in index:
                raise ValueError(f"category_id가 중복된다: {category.category_id}")
            index[category.category_id] = category
        object.__setattr__(self, "_by_id", index)

    def category(self, category_id: str) -> SafetyCategory | None:
        return self._by_id.get(category_id)

    @property
    def annual_hours_min_total(self) -> int:
        """파생값이다. 법령이 총합을 직접 규정하지는 않는다."""
        return sum(c.annual_hours_min for c in self.categories)

    @property
    def is_active(self) -> bool:
        """사람이 승인한 Rule만 활성으로 취급한다.

        `runtime_active`는 독립 스위치가 아니라 approval에서 파생된 값이다.
        """
        return self.runtime_active

    @property
    def has_placement_policy(self) -> bool:
        return self.placement_policy_version is not None
