"""Activity Reference v0 도메인 모델.

docs/open-decisions.md OD-N03 (부분) / CLAUDE.md §8:
- 사람이 검증하고 version이 부여된 Catalog만 Rule 후보로 활성화한다.
- `applicable_months`는 실제 Evidence가 존재하는 월이며 국가가 정한 월별 필수
  활동이 아니다.
- `curriculum_links`는 영역 수준 교육적 연계이며 Activity의 직접 국가 지정
  출처가 아니다. 근거가 없으면 빈 배열이 정답이다.
- `origin_id`는 upstream lineage이며 Evidence의 canonical source_id를 대신하지
  않는다. Cell Evidence의 canonical `source_id`는 `activity_id`다.

Theme Reference(`theme_reference.py`)와 의도적으로 같은 구조를 쓴다. 연령 판정,
승인 Gate, evidence 강도 계산의 의미가 두 Reference에서 달라지면 안 된다.

**이 모듈에는 ranking이 없다.** 월·연령·slot·setting hard filter까지만 담당하고
후보 우선순위 계산은 M2-B의 Rule 계층이 담당한다. Theme에서 `ThemeCatalog`가
`eligible_candidates`만 갖고 `yearly_theme_selection.py`가 순위를 매기는 것과
같은 분업이다.

**Safety 경계**: Activity Reference는 SafetyEducationPlan도 SafetyLegalRule도
아니다. `safety_education`은 Activity 후보에서 채우지 않으며 `placement_slots`에
그 slot을 넣을 수 없다(`FORBIDDEN_PLACEMENT_SLOTS`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "ActivationStatus",
    "ActivityDisplayQuality",
    "DisplayQualityReviewStatus",
    "ActivityCandidate",
    "ActivityCatalog",
    "ActivityEvidence",
    "ActivitySetting",
    "ActivityThemeLink",
    "CurriculumLink",
    "FORBIDDEN_PLACEMENT_SLOTS",
    "OUTDOOR_PLAY_SLOT",
    "SUPPORTED_PLACEMENT_SLOTS",
    "THEME_RELATION_OBSERVED_TOGETHER",
]

# ---------------------------------------------------------------- 통제 어휘

OUTDOOR_PLAY_SLOT = "outdoor_play"

SUPPORTED_PLACEMENT_SLOTS: frozenset[str] = frozenset({OUTDOOR_PLAY_SLOT})
"""P0에서 Activity가 주장할 수 있는 Template Section semantic_key.

자유 문자열이 아니라 `data/templates/monthly_template_a.json`의 semantic_key에
종속되는 통제 어휘다. Activity가 Template에 없는 slot을 주장할 수 없다.

`focus`와 `indoor_alternative`는 Template A에서 default inactive이고
`indoor_alternative`의 display_mode는 아직 PENDING_HUMAN_DECISION이므로 넣지
않는다. 넓히려면 Template 쪽 결정이 선행되어야 한다.
"""

FORBIDDEN_PLACEMENT_SLOTS: frozenset[str] = frozenset({"safety_education"})
"""절대 허용하지 않는 slot.

법정 안전교육 content를 일반 Activity Catalog에서 채우는 경로를 값 수준에서
없앤다. 배치 source는 기관 안전교육 연간계획 또는 교사 입력이며(OD-M04)
Activity Reference가 그 역할을 대신하지 않는다.
"""

THEME_RELATION_OBSERVED_TOGETHER = "OBSERVED_TOGETHER"
"""같은 Monthly source에서 해당 theme과 함께 관찰됐다는 뜻.

`BELONGS_TO` 같은 규범적 표현을 쓰지 않는다. 국가나 교육과정이 활동을 주제에
귀속시킨 것이 아니라 실측 문서에서 함께 나타난 사실만 기록한다.
"""

CURRICULUM_RELATION_EDUCATIONAL_ALIGNMENT = "EDUCATIONAL_ALIGNMENT"

_CURRICULUM_DOMAINS: frozenset[str] = frozenset(
    {"신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"}
)
"""2019 개정 누리과정 5개 영역. 하위 `내용범주`·`내용` ID를 만들지 않는다."""

MIN_AGE = 3
MAX_AGE = 5
"""P0 대상 연령. 만 0~2세 영아반은 범위 밖이다(CLAUDE.md §4)."""


class ActivationStatus(str, Enum):
    """Catalog의 사람 검토 Gate 상태.

    `theme_reference.ActivationStatus`와 값 집합이 같다. 두 Reference의 승인
    의미가 갈리지 않도록 같은 리터럴을 쓰되, Activity 쪽 import가 Theme 모듈에
    의존하지 않도록 별도로 정의한다.
    """

    HUMAN_APPROVED = "HUMAN_APPROVED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"


class ActivityDisplayQuality(str, Enum):
    """Monthly Cell에 그대로 표시했을 때의 label 품질.

    **Hard Filter가 아니다.** 후보를 제거하지 않고 순위에만 영향을 준다(M2-B v2).
    분류는 사람이 확정하며, 자동 탐지 결과는 `AUTO_CANDIDATE` 상태로만 들어온다.
    """

    GOOD_STANDALONE = "GOOD_STANDALONE"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    TOO_SHORT = "TOO_SHORT"
    POSSIBLE_FRAGMENT = "POSSIBLE_FRAGMENT"
    SECTION_LABEL_LIKE = "SECTION_LABEL_LIKE"
    INSTITUTION_SPECIFIC = "INSTITUTION_SPECIFIC"
    TOO_GENERIC = "TOO_GENERIC"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class DisplayQualityReviewStatus(str, Enum):
    """`display_quality` 값의 검토 상태.

    자동 탐지기에는 아직 False Positive가 있다. 따라서 **`HUMAN_CONFIRMED`만이
    Selection에 영향을 준다.** 나머지는 중립이다.
    """

    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    AUTO_CANDIDATE = "AUTO_CANDIDATE"
    UNREVIEWED = "UNREVIEWED"


class ActivitySetting(str, Enum):
    """활동이 이루어지는 물리 환경.

    `indoor_alternative` Section과 같은 개념이 아니다. 실내대체는 바깥놀이가
    불가능할 때 대신하는 **별도 Section**이며, `INDOOR` Activity는 애초에 실내를
    전제하는 활동이다. M2-A seed는 전부 바깥놀이 행에서 관찰된 `OUTDOOR`다.
    """

    OUTDOOR = "OUTDOOR"
    INDOOR = "INDOOR"
    EITHER = "EITHER"


# ------------------------------------------------------------------- VO


@dataclass(frozen=True, slots=True)
class ActivityEvidence:
    """Activity가 실측 Monthly Sample에서 관찰된 근거 하나.

    `age_scope`는 **문서가 명시적으로 다루는 연령 범위**이며 실제 classroom의
    혼합 구성이라고 자동 해석하지 않는다. 본문에 연령 표기가 없는 문서는 빈
    tuple이며 파일명 표기로 추론하지 않는다(CLAUDE.md §11).

    `observed_label`은 원문 그대로 보존한다. 정규화된 표현은 `ActivityCandidate`
    쪽 `label`과 `aliases`에 둔다.
    """

    origin_id: str
    page: int
    age_scope: tuple[int, ...]
    observed_month: int
    observed_label: str
    observed_section: str
    observed_source_label: str
    matched_via: str | None = None
    match_note: str | None = None

    def __post_init__(self) -> None:
        if not self.origin_id.strip():
            raise ValueError("ActivityEvidence.origin_id는 필수다")
        if self.page < 1:
            raise ValueError(f"page는 1 이상이어야 한다: {self.page}")
        if not 1 <= self.observed_month <= 12:
            raise ValueError(f"observed_month는 1~12여야 한다: {self.observed_month}")
        if not self.observed_label.strip():
            raise ValueError("observed_label은 원문 보존이므로 비울 수 없다")
        for age in self.age_scope:
            if not MIN_AGE <= age <= MAX_AGE:
                raise ValueError(f"age_scope는 만 3~5세만 담는다: {self.age_scope}")


@dataclass(frozen=True, slots=True)
class ActivityThemeLink:
    """Theme Reference record와의 관찰 기반 연결.

    `theme_catalog_version`을 링크마다 기록한다. Theme Reference가 새 version으로
    올라가도 "어느 version 기준으로 검토된 연결인지"가 남는다. 문자열 유사도
    매칭으로 만들지 않는다.
    """

    theme_id: str
    relation: str
    theme_catalog_version: str

    def __post_init__(self) -> None:
        if not self.theme_id.strip():
            raise ValueError("ActivityThemeLink.theme_id는 필수다")
        if self.relation != THEME_RELATION_OBSERVED_TOGETHER:
            raise ValueError(
                "theme link relation은 OBSERVED_TOGETHER만 허용한다. "
                f"규범적 관계를 주장할 수 없다: {self.relation}"
            )
        if not self.theme_catalog_version.strip():
            raise ValueError("theme_catalog_version은 필수다")


@dataclass(frozen=True, slots=True)
class CurriculumLink:
    """누리과정 5개 영역과의 영역 수준 교육적 연계.

    `theme_reference.CurriculumLink`와 필드가 같다. 공식 항목 ID를 만들지 않고
    영역과 해당 공식 PDF 페이지만 기록한다.
    """

    source_id: str
    domain: str
    source_page: int
    relation: str = CURRICULUM_RELATION_EDUCATIONAL_ALIGNMENT

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("CurriculumLink.source_id는 필수다")
        if self.domain not in _CURRICULUM_DOMAINS:
            raise ValueError(
                f"curriculum domain은 누리과정 5개 영역만 허용한다: {self.domain}"
            )
        if self.relation != CURRICULUM_RELATION_EDUCATIONAL_ALIGNMENT:
            raise ValueError(
                "curriculum link relation은 EDUCATIONAL_ALIGNMENT만 허용한다. "
                f"국가 지정 출처를 주장할 수 없다: {self.relation}"
            )


# ------------------------------------------------------------- Candidate


@dataclass(frozen=True, slots=True)
class ActivityCandidate:
    """Rule이 선택할 수 있는 Activity 후보 하나."""

    activity_id: str
    label: str
    supported_ages: tuple[int, ...]
    allow_mixed_age: bool
    mixed_age_requires_all_supported: bool
    applicable_months: tuple[int, ...]
    placement_slots: tuple[str, ...]
    setting: ActivitySetting
    source_version: str
    origin_id: str | None = None
    label_derivation_type: str | None = None
    label_derivation: str | None = None
    aliases: tuple[str, ...] = ()
    theme_links: tuple[ActivityThemeLink, ...] = ()
    curriculum_links: tuple[CurriculumLink, ...] = ()
    evidence: tuple[ActivityEvidence, ...] = ()
    display_quality: ActivityDisplayQuality | None = None
    """Cell 표시 품질. **Optional이다.**

    v0.2.0처럼 이 필드가 없는 Catalog도 그대로 로드되며, 그때 Selection 동작은
    이전과 완전히 동일하다.
    """
    display_quality_review_status: DisplayQualityReviewStatus | None = None
    """`display_quality`의 검토 상태. None이면 미검토와 같이 중립이다."""

    def __post_init__(self) -> None:
        if not self.activity_id.strip():
            raise ValueError("ActivityCandidate.activity_id는 필수다")
        if not self.label.strip():
            raise ValueError(f"{self.activity_id}: label은 비어 있을 수 없다")
        if not self.source_version.strip():
            raise ValueError(f"{self.activity_id}: source_version은 필수다")

        if not self.supported_ages:
            raise ValueError(
                f"{self.activity_id}: supported_ages가 비어 있다. 연령 근거가 없는 "
                "항목은 runtime 후보가 될 수 없다"
            )
        for age in self.supported_ages:
            if not MIN_AGE <= age <= MAX_AGE:
                raise ValueError(
                    f"{self.activity_id}: supported_ages는 만 3~5세만 담는다: "
                    f"{self.supported_ages}"
                )
        if len(set(self.supported_ages)) != len(self.supported_ages):
            raise ValueError(f"{self.activity_id}: supported_ages에 중복이 있다")

        if not self.applicable_months:
            raise ValueError(
                f"{self.activity_id}: applicable_months가 비어 있다. 실제 Evidence가 "
                "존재하는 월만 허용하며 추론으로 채우지 않는다"
            )
        for month in self.applicable_months:
            if not 1 <= month <= 12:
                raise ValueError(
                    f"{self.activity_id}: applicable_months는 1~12여야 한다: "
                    f"{self.applicable_months}"
                )
        if len(set(self.applicable_months)) != len(self.applicable_months):
            raise ValueError(f"{self.activity_id}: applicable_months에 중복이 있다")

        if not self.placement_slots:
            raise ValueError(f"{self.activity_id}: placement_slots는 비울 수 없다")
        for slot in self.placement_slots:
            if slot in FORBIDDEN_PLACEMENT_SLOTS:
                raise ValueError(
                    f"{self.activity_id}: '{slot}'은 Activity Reference가 채울 수 "
                    "없는 slot이다. 법정 안전교육 배치는 기관 연간계획 또는 교사 "
                    "입력이 source이며 일반 Activity Catalog에서 가져오지 않는다"
                )
            if slot not in SUPPORTED_PLACEMENT_SLOTS:
                raise ValueError(
                    f"{self.activity_id}: 알 수 없는 placement slot '{slot}'. "
                    f"허용: {sorted(SUPPORTED_PLACEMENT_SLOTS)}"
                )
        if len(set(self.placement_slots)) != len(self.placement_slots):
            raise ValueError(f"{self.activity_id}: placement_slots에 중복이 있다")

        if not self.allow_mixed_age and self.mixed_age_requires_all_supported:
            raise ValueError(
                f"{self.activity_id}: 혼합연령을 허용하지 않으면서 "
                "mixed_age_requires_all_supported를 요구할 수 없다"
            )

        # supported_ages가 evidence의 age_scope 합집합을 넘지 않는지 확인한다.
        # 근거보다 넓게 주장하는 것을 값 수준에서 막는다.
        if self.evidence:
            observed_ages = {a for e in self.evidence for a in e.age_scope}
            if not set(self.supported_ages) <= observed_ages:
                raise ValueError(
                    f"{self.activity_id}: supported_ages {sorted(self.supported_ages)}가 "
                    f"관찰된 age_scope {sorted(observed_ages)}보다 넓다"
                )
            observed_months = {e.observed_month for e in self.evidence}
            if not set(self.applicable_months) <= observed_months:
                raise ValueError(
                    f"{self.activity_id}: applicable_months "
                    f"{sorted(self.applicable_months)}가 관찰된 월 "
                    f"{sorted(observed_months)}보다 넓다"
                )

    # ---------------------------------------------------------------- 적합성

    def supports_month(self, calendar_month: int) -> bool:
        return calendar_month in self.applicable_months

    def supports_age_set(self, ages: frozenset[int]) -> bool:
        """선택된 **모든** 연령을 지원해야 한다.

        `ThemeCandidate.supports_age_set`과 동일한 의미다. 혼합연령 반에서도
        Activity를 연령별로 복제하지 않고 같은 record가 후보가 된다.
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

    def supports_slot(self, section_key: str) -> bool:
        return section_key in self.placement_slots

    def supports_setting(self, section_key: str) -> bool:
        """Section 의미와 `setting`이 호환되는지.

        `outdoor_play`는 `OUTDOOR` 또는 `EITHER`만 받는다. 실내 전제 활동을
        바깥놀이 Cell에 넣지 않는다.
        """
        if section_key == OUTDOOR_PLAY_SLOT:
            return self.setting in (ActivitySetting.OUTDOOR, ActivitySetting.EITHER)
        return True

    def links_theme(self, theme_id: str) -> bool:
        return any(link.theme_id == theme_id for link in self.theme_links)

    # ------------------------------------------------------- Evidence 강도

    def evidence_strength_for_month(self, calendar_month: int) -> int:
        """해당 달력 월에서 실제로 관찰된 Sample evidence 개수.

        `ThemeCandidate.evidence_strength_for_month`와 같은 정의다. 연령별 가중은
        하지 않는다. evidence.age_scope를 classroom 구성으로 해석하지 않기로 한
        규정을 지키기 위함이며 연령 적합성은 이미 필터가 담당한다.
        """
        return sum(1 for e in self.evidence if e.observed_month == calendar_month)

    @property
    def observed_institution_count(self) -> int:
        return len({e.origin_id for e in self.evidence})

    @property
    def has_confirmed_display_issue(self) -> bool:
        """사람이 확정한 표시 품질 문제가 있는지.

        **`HUMAN_CONFIRMED`이면서 `GOOD_STANDALONE`이 아닐 때만 True다.**
        `AUTO_CANDIDATE` / `UNREVIEWED` / None은 전부 False다 — 자동 탐지기의
        False Positive가 후보를 불리하게 만들면 안 되기 때문이다.
        """
        if self.display_quality_review_status is not DisplayQualityReviewStatus.HUMAN_CONFIRMED:
            return False
        return (
            self.display_quality is not None
            and self.display_quality is not ActivityDisplayQuality.GOOD_STANDALONE
        )


# --------------------------------------------------------------- Catalog


@dataclass(frozen=True, slots=True)
class ActivityCatalog:
    """version이 고정된 Activity 후보 Catalog."""

    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    activities: tuple[ActivityCandidate, ...]
    normative_status: str | None = None
    month_coverage: tuple[int, ...] = ()
    _by_id: dict[str, ActivityCandidate] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.catalog_id.strip():
            raise ValueError("ActivityCatalog.catalog_id는 필수다")
        if not self.catalog_version.strip():
            raise ValueError("ActivityCatalog.catalog_version은 필수다")

        # frozen dataclass이므로 dict를 in-place로 채운다.
        self._by_id.clear()
        for activity in self.activities:
            if activity.activity_id in self._by_id:
                raise ValueError(f"Catalog에 중복된 activity_id: {activity.activity_id}")
            self._by_id[activity.activity_id] = activity

        for activity in self.activities:
            if activity.source_version != self.catalog_version:
                raise ValueError(
                    f"{activity.activity_id}: source_version "
                    f"'{activity.source_version}'이 catalog_version "
                    f"'{self.catalog_version}'과 다르다"
                )

        declared = set(self.month_coverage)
        if declared:
            actual = {m for a in self.activities for m in a.applicable_months}
            if declared != actual:
                raise ValueError(
                    f"month_coverage {sorted(declared)}가 실제 후보 월 "
                    f"{sorted(actual)}과 다르다"
                )

    @property
    def is_active(self) -> bool:
        """운영 Rule 후보로 활성화 가능한지.

        CLAUDE.md §8: PENDING_HUMAN_REVIEW 상태의 Catalog는 실제 성공 생성
        경로에서 활성 Catalog로 취급하지 않는다. 독립 writable 필드가 아니라
        승인 상태에서 파생되는 값이다.
        """
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def get(self, activity_id: str) -> ActivityCandidate | None:
        return self._by_id.get(activity_id)

    def covers_month(self, calendar_month: int) -> bool:
        return any(a.supports_month(calendar_month) for a in self.activities)

    def eligible_candidates(
        self,
        *,
        section_key: str,
        calendar_month: int,
        ages: frozenset[int],
    ) -> tuple[ActivityCandidate, ...]:
        """hard filter를 모두 통과한 후보.

        순위 결정은 하지 않는다. Rule 계층(M2-B)이 담당한다. 반환 순서는
        `activity_id` 기준으로 결정론적이며 우선순위를 뜻하지 않는다.

        미승인 Catalog는 빈 tuple을 반환한다. 승인 Gate를 우회해 후보를 얻는
        경로를 만들지 않는다.
        """
        if not self.is_active:
            return ()
        if section_key in FORBIDDEN_PLACEMENT_SLOTS:
            return ()
        return tuple(
            sorted(
                (
                    a
                    for a in self.activities
                    if a.supports_slot(section_key)
                    and a.supports_setting(section_key)
                    and a.supports_month(calendar_month)
                    and a.supports_age_set(ages)
                ),
                key=lambda a: a.activity_id,
            )
        )
