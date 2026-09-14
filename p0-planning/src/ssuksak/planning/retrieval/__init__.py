"""Monthly Evidence Retrieval (L2).

Planning Request 하나에 필요한 소수의 Evidence를 **결정론적이고 설명 가능하게**
고른다. LLM · Embedding · Vector DB를 쓰지 않는다.

Runtime은 PDF를 읽지 않는다. L1이 만든 Evidence Store Artifact 하나만 읽는다.
"""

from .evidence_repository import (
    DEFAULT_EVIDENCE_STORE_PATH,
    EvidenceStoreError,
    InMemoryInstitutionEvidenceRepository,
    InstitutionEvidenceStore,
    JsonInstitutionEvidenceRepository,
    load_evidence_store_from_dict,
)
from .models import (
    AgeMatchKind,
    BlockName,
    EvidenceBlock,
    MonthlyEvidenceRetrievalResult,
    ReferenceCandidate,
    RetrievalRequest,
    RetrievalTrace,
    RetrievedEvidence,
)
from .ranking import (
    DEFAULT_INSTITUTION_CAP,
    TEMPLATE_FAMILY,
    age_match_kind,
    apply_source_diversity,
    balance_by_single_age,
    diversity_group,
    ngrams,
    rank_records,
    theme_signals,
)
from .retriever import DEFAULT_TOP_K, MonthlyEvidenceRetriever, OfficialEvidencePort

__all__ = [
    "DEFAULT_EVIDENCE_STORE_PATH",
    "DEFAULT_INSTITUTION_CAP",
    "DEFAULT_TOP_K",
    "TEMPLATE_FAMILY",
    "AgeMatchKind",
    "BlockName",
    "EvidenceBlock",
    "EvidenceStoreError",
    "InMemoryInstitutionEvidenceRepository",
    "InstitutionEvidenceStore",
    "JsonInstitutionEvidenceRepository",
    "MonthlyEvidenceRetrievalResult",
    "MonthlyEvidenceRetriever",
    "OfficialEvidencePort",
    "ReferenceCandidate",
    "RetrievalRequest",
    "RetrievalTrace",
    "RetrievedEvidence",
    "age_match_kind",
    "apply_source_diversity",
    "balance_by_single_age",
    "diversity_group",
    "load_evidence_store_from_dict",
    "ngrams",
    "rank_records",
    "theme_signals",
]
