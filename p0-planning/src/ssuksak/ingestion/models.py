"""Evidence Record Contract (L1).

`docs/analysis/monthly-llm-planner-vnext-design.md` §5와 2026-09-13 L0 결정
(OD-N13 / OD-N14 / OD-N15)을 구현한다.

**Activity Reference와 역할이 다르다.**

    Activity Reference   사람이 승인한 canonical 후보. Plan Item의 값이 된다.
    Evidence Store       Corpus 관찰값. LLM Grounding Context로만 쓴다.
                         canonical이 아니고 Plan Item의 값이 되지 않는다.

원칙 4개.

1. **원문 label을 canonical 값으로 덮어쓰지 않는다.** `source_section`과
   `source_label`을 둘 다 남긴다.
2. **`week_position`을 추정하지 않는다.** 원문에 주차가 적혀 있을 때만 채운다.
3. **`grounding_eligible`은 파생값이다.** 파일 필드로 두지 않는다
   (CLAUDE.md §8의 `runtime_active` 파생 원칙과 같다).
4. **읽을 수 없으면 추정하지 않는다.** image-only는 그 사실을 그대로 남긴다.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "AgeEvidenceType",
    "EvidenceRecord",
    "EvidenceSourceType",
    "ExtractionQuality",
    "MachineReadability",
    "ReusePolicy",
    "SourceSection",
    "Setting",
]


class EvidenceSourceType(str, Enum):
    """Evidence Record가 어떤 종류의 Source에서 왔는지.

    `INSTITUTION_SAMPLE`은 2026-09-13 Human Decision(OD-N13)으로 승인된 값이며
    CLAUDE.md §13.1 / docs/screen-spec.md §6.1의 허용 목록에 등재돼 있다.

    Domain `provenance.EvidenceSourceType`에 같은 값을 추가하는 것은 Plan Item
    Evidence를 실제로 기록하는 단계(L4~L6)의 일이다. L1은 Evidence Store만
    만들고 Plan Item을 건드리지 않으므로 여기서 Domain enum을 바꾸지 않는다.
    두 enum의 **문자열 값은 일치해야 한다** — 테스트로 고정한다.
    """

    INSTITUTION_SAMPLE = "INSTITUTION_SAMPLE"


class SourceSection(str, Enum):
    """원문 행을 옮긴 canonical section. 원문 label은 따로 보존한다."""

    OUTDOOR_PLAY = "outdoor_play"
    INDOOR_PLAY = "indoor_play"
    INDOOR_ALTERNATIVE = "indoor_alternative"
    WEEK_EXPERIENCE = "week_experience"
    SAFETY_EDUCATION = "safety_education"
    DAILY_ROUTINE = "daily_routine"
    EVENT = "event"
    THEME = "theme"
    UNKNOWN = "unknown"


class Setting(str, Enum):
    """활동이 이루어지는 물리 환경.

    `INDOOR_ALTERNATIVE`는 `INDOOR`와 다르다. 바깥놀이가 불가능할 때 대신하는
    별도 Section 소속이라는 뜻이며, **outdoor 후보로 쓰지 않는다**
    (`docs/analysis/activity-v0-2-1-setting-audit.md`).
    """

    OUTDOOR = "OUTDOOR"
    INDOOR = "INDOOR"
    INDOOR_ALTERNATIVE = "INDOOR_ALTERNATIVE"
    UNKNOWN = "UNKNOWN"


class AgeEvidenceType(str, Enum):
    """그 **면**이 단일연령 근거인지.

    범위(`만3~5세`) · 열거(`만4,5세`) · `혼합` 표기가 하나라도 있으면
    단일연령이 아니다. 같은 면에 서로 다른 연령이 따로 적혀 있어도 아니다.
    """

    SINGLE_AGE_PAGE = "SINGLE_AGE_PAGE"
    MIXED_AGE_PAGE = "MIXED_AGE_PAGE"
    AGE_UNKNOWN = "AGE_UNKNOWN"


class MachineReadability(str, Enum):
    TEXT_LAYER = "TEXT_LAYER"
    IMAGE_ONLY = "IMAGE_ONLY"


class ReusePolicy(str, Enum):
    """L0 결정(OD-N13 파생 Contract).

    `CONTEXT_ONLY`가 P0 기본이다. Grounding Context로는 쓰되 원문 문자열을
    Product 값으로 그대로 복사하지 않는다. 따라서 `CONTEXT_ONLY` Record를
    근거로 만든 Activity의 origin은 `LLM_SYNTHESIZED`다.

    `PRODUCT_OUTPUT_ALLOWED`는 라이선스·계약 근거가 확인된 Record에만 쓴다.
    **현재 P0 Corpus에는 해당 Record가 없다.** 임의로 올리지 않는다.
    """

    CONTEXT_ONLY = "CONTEXT_ONLY"
    PRODUCT_OUTPUT_ALLOWED = "PRODUCT_OUTPUT_ALLOWED"


class ExtractionQuality(str, Enum):
    """추출 품질. L0 결정(OD-N13 파생 Contract §2).

    VALID         셀 구조 복구 성공 · 내용 완결 · fragment 징후 없음
    NEEDS_REVIEW  문장 절단 가능성 · ambiguous section · 다중 셀 관계 불확실
    INVALID       empty body · 명백한 parser fragment · 사용 불가 좌표
    """

    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INVALID = "INVALID"


class CellCoordinates(BaseModel):
    """원문 셀 좌표. 재현·감사용이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_top: float
    row_bottom: float
    column: int
    item_index: int


class EvidenceRecord(BaseModel):
    """Retrieval 단위. **면 안의 셀 항목 하나**가 기본 단위다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    source_type: EvidenceSourceType

    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)

    institution_id: str | None = None
    institution_type: str | None = None

    year: int | None = None
    month: int | None = None

    age_scope: tuple[int, ...] = ()
    age_evidence_type: AgeEvidenceType

    monthly_theme: str | None = None

    source_section: SourceSection
    source_label: str = Field(min_length=1)

    week_position: int | None = None
    week_label: str | None = None

    experience_text: str | None = None
    activity_text: str | None = None

    setting: Setting

    template_family: bool = False
    machine_readability: MachineReadability

    reuse_policy: ReusePolicy = ReusePolicy.CONTEXT_ONLY
    extraction_quality: ExtractionQuality

    extraction_method: str = Field(min_length=1)
    source_cell: CellCoordinates | None = None

    @field_validator("age_scope")
    @classmethod
    def _p0_target_ages(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        for a in v:
            if not 3 <= a <= 5:
                raise ValueError(f"P0 Target은 만3~5세다: {v}")
        if len(set(v)) != len(v):
            raise ValueError(f"age_scope에 중복이 있다: {v}")
        return tuple(sorted(v))

    @field_validator("month")
    @classmethod
    def _valid_month(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 12:
            raise ValueError(f"month는 1~12여야 한다: {v}")
        return v

    @field_validator("week_position")
    @classmethod
    def _valid_week(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 6:
            raise ValueError(f"week_position은 1~6이어야 한다: {v}")
        return v

    # --------------------------------------------------------- 파생값

    @property
    def single_age(self) -> int | None:
        """단일연령 면이면 그 연령. 아니면 None."""
        if self.age_evidence_type is AgeEvidenceType.SINGLE_AGE_PAGE and (
            len(self.age_scope) == 1
        ):
            return self.age_scope[0]
        return None

    @property
    def general_grounding_eligible(self) -> bool:
        """LLM Grounding Context에 넣어도 되는가. **파생값이다.**

        "깨진 문자열이지만 Context에는 넣자"는 정책을 쓰지 않는다.
        """
        return (
            self.machine_readability is MachineReadability.TEXT_LAYER
            and self.extraction_quality is ExtractionQuality.VALID
        )

    @property
    def outdoor_activity_eligible(self) -> bool:
        """바깥놀이 Activity Grounding에 쓸 수 있는가.

        일반 eligibility와 **별개 축**이다. 실내대체는 원문이 명시한 별도
        Section이므로 일반 Context로는 유효해도 outdoor 후보가 될 수 없다.
        """
        return (
            self.general_grounding_eligible
            and self.source_section is SourceSection.OUTDOOR_PLAY
            and self.setting is Setting.OUTDOOR
        )

    @property
    def text(self) -> str | None:
        return self.activity_text or self.experience_text
