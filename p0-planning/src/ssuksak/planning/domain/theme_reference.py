"""Theme Reference v0 도메인 모델.

docs/open-decisions.md OD-Y02 / CLAUDE.md §8:
- 사람이 검증하고 version이 부여된 Catalog만 Rule 후보로 활성화한다.
- `applicable_months`는 제품 후보 조건이며 국가가 정한 월별 필수 주제가 아니다.
- `curriculum_links`는 영역 수준 교육적 연계이며 Theme의 직접 국가 지정 출처가 아니다.
- `origin_id`는 upstream lineage이며 Evidence의 canonical source_id를 대신하지 않는다.

activation_status는 외부 요청자가 지정하는 Input이 아니라
ThemeReferenceRepository가 반환하는 ThemeCatalog의 신뢰 가능한 metadata다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActivationStatus(str, Enum):
    """Catalog의 사람 검토 Gate 상태."""

    HUMAN_APPROVED = "HUMAN_APPROVED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class ThemeEvidence:
    """Theme이 실측 Sample에서 관찰된 근거 하나.

    `age_scope`는 문서가 명시적으로 다루는 연령 범위이며
    실제 classroom의 혼합 구성이라고 자동 해석하지 않는다
    (data/themes/theme_reference_v0.json > age_semantics.evidence_age_scope).
    """

    origin_id: str
    page: int
    age_scope: tuple[int, ...]
    observed_month: int
    observed_label: str


@dataclass(frozen=True, slots=True)
class CurriculumLink:
    """누리과정 5개 영역과의 영역 수준 교육적 연계."""

    source_id: str
    domain: str
    source_page: int
    relation: str


@dataclass(frozen=True, slots=True)
class ThemeCandidate:
    """Rule이 선택할 수 있는 Theme 후보 하나."""

    theme_id: str
    label: str
    applicable_months: tuple[int, ...]
    supported_ages: tuple[int, ...]
    allow_mixed_age: bool
    mixed_age_requires_all_supported: bool
    source_version: str
    origin_id: str | None = None
    curriculum_links: tuple[CurriculumLink, ...] = ()
    evidence: tuple[ThemeEvidence, ...] = ()

    # ---------------------------------------------------------------- 적합성

    def supports_month(self, calendar_month: int) -> bool:
        return calendar_month in self.applicable_months

    def supports_age_set(self, ages: frozenset[int]) -> bool:
        """선택된 **모든** 연령을 지원해야 한다.

        CLAUDE.md §11 / theme_reference_v0.json > age_semantics.mixed_age_rule.
        """
        if not ages:
            return False
        if not ages.issubset(set(self.supported_ages)):
            return False
        if len(ages) >= 2:
            if not self.allow_mixed_age:
                return False
            if self.mixed_age_requires_all_supported and not ages.issubset(
                set(self.supported_ages)
            ):
                return False
        return True

    # ------------------------------------------------------- Evidence 강도

    def evidence_strength_for_month(self, calendar_month: int) -> int:
        """해당 달력 월에서 실제로 관찰된 Sample evidence 개수.

        docs 결정(2026-09-10): "현재 월에서 실제 Sample evidence가 더 강한 후보를 우선".
        연령별 가중은 하지 않는다. evidence.age_scope를 classroom 구성으로
        해석하지 않기로 한 Reference 의미 규정을 지키기 위함이며,
        연령 적합성은 이미 age_conditions 필터가 담당한다.
        """
        return sum(1 for e in self.evidence if e.observed_month == calendar_month)


@dataclass(frozen=True, slots=True)
class ThemeCatalog:
    """version이 고정된 Theme 후보 Catalog."""

    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    themes: tuple[ThemeCandidate, ...]
    normative_status: str | None = None
    _by_id: dict[str, ThemeCandidate] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        # frozen dataclass이므로 dict를 in-place로 채운다.
        self._by_id.clear()
        for theme in self.themes:
            if theme.theme_id in self._by_id:
                raise ValueError(f"Catalog에 중복된 theme_id: {theme.theme_id}")
            self._by_id[theme.theme_id] = theme

    @property
    def is_active(self) -> bool:
        """운영 Rule 후보로 활성화 가능한지.

        CLAUDE.md §8: PENDING_HUMAN_REVIEW 상태의 Catalog는
        실제 성공 생성 경로에서 활성 Catalog로 취급하지 않는다.
        """
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def get(self, theme_id: str) -> ThemeCandidate | None:
        return self._by_id.get(theme_id)

    def eligible_candidates(
        self, calendar_month: int, ages: frozenset[int]
    ) -> tuple[ThemeCandidate, ...]:
        """월·연령 조건을 모두 만족하는 후보. 순위 결정은 Rule 계층이 한다."""
        return tuple(
            t
            for t in self.themes
            if t.supports_month(calendar_month) and t.supports_age_set(ages)
        )
