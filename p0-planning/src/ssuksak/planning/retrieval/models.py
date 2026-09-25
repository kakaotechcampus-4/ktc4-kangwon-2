"""Provider-neutral retrieval request, trace, block, and result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.errors import InvalidDomainValueError
from ..domain.year_month import YearMonth
from ..evidence.models import EvidenceRecord


class AgeMatchKind(str, Enum):
    SINGLE_AGE_EXACT = "SINGLE_AGE_EXACT"
    SINGLE_AGE_IN_REQUEST = "SINGLE_AGE_IN_REQUEST"
    MIXED_AGE_COVERING = "MIXED_AGE_COVERING"
    AGE_UNKNOWN = "AGE_UNKNOWN"


AGE_TIER_ORDER = (
    AgeMatchKind.SINGLE_AGE_EXACT,
    AgeMatchKind.SINGLE_AGE_IN_REQUEST,
    AgeMatchKind.MIXED_AGE_COVERING,
    AgeMatchKind.AGE_UNKNOWN,
)


class BlockName(str, Enum):
    INSTITUTION_MONTHLY_EVIDENCE = "institution_monthly_evidence"
    AGE_CONTRAST_EVIDENCE = "age_contrast_evidence"
    WEEK_EXPERIENCE_CANDIDATES = "week_experience_candidates"
    REFERENCE_ACTIVITIES = "reference_activities"
    OTHER_OUTDOOR_EVIDENCE = "other_outdoor_evidence"


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    target_month: YearMonth
    ages: frozenset[int]
    confirmed_theme_id: str
    confirmed_theme_value: str
    week_count: int
    keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError("RetrievalRequest.target_month must be YearMonth")
        if not isinstance(self.ages, frozenset) or not self.ages:
            raise InvalidDomainValueError("RetrievalRequest.ages must be a non-empty frozenset")
        if any(type(age) is not int or age not in {3, 4, 5} for age in self.ages):
            raise InvalidDomainValueError("RetrievalRequest supports P0 ages 3 through 5")
        for name in ("confirmed_theme_id", "confirmed_theme_value"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"RetrievalRequest.{name} must be non-blank")
        if type(self.week_count) is not int or self.week_count < 1:
            raise InvalidDomainValueError("RetrievalRequest.week_count must be positive")
        if not isinstance(self.keywords, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.keywords
        ):
            raise InvalidDomainValueError("RetrievalRequest.keywords must contain non-blank strings")


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    age_match: AgeMatchKind
    structural_score: int
    keyword_overlap: int
    theme_page_match: bool
    total_score: int
    diversity_group: str


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    record: EvidenceRecord
    trace: RetrievalTrace

    @property
    def record_id(self) -> str:
        return self.record.record_id


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    activity_id: str
    label: str
    evidence_strength: int
    has_display_quality_issue: bool
    rank: int


@dataclass(frozen=True, slots=True)
class EvidenceBlock:
    name: BlockName
    top_k: int
    retrieval_reason: str
    items: tuple[RetrievedEvidence, ...] = ()
    reference_items: tuple[ReferenceCandidate, ...] = ()
    eligible_pool_size: int = 0

    @property
    def size(self) -> int:
        return len(self.items) + len(self.reference_items)


@dataclass(frozen=True, slots=True)
class MonthlyEvidenceRetrievalResult:
    request: RetrievalRequest
    blocks: tuple[EvidenceBlock, ...]
    evidence_store_version: str
    evidence_store_sha256: str
    retrieval_version: str
    activity_catalog_id: str = ""
    activity_catalog_version: str = ""

    def block(self, name: BlockName) -> EvidenceBlock:
        for block in self.blocks:
            if block.name is name:
                return block
        raise KeyError(name)

    @property
    def total_evidence_records(self) -> int:
        return sum(len(block.items) for block in self.blocks)
