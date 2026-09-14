"""Institution Sample Corpus → Evidence Store (L1).

`docs/analysis/monthly-llm-planner-l1-evidence-ingestion.md`가 이 모듈의 보고서다.

**Activity Reference를 대체하지 않는다.** Evidence Store는 Corpus 관찰값이며
LLM Grounding Context로만 쓴다. Plan Item의 값이 되지 않는다.

PDF 라이브러리는 `ports.SourceDocumentReader` Protocol 뒤에 격리한다
(`adapters/pymupdf_source_reader.py`). 파이프라인과 분류 규칙은 PDF 없이
테스트된다.
"""

from .models import (
    AgeEvidenceType,
    EvidenceRecord,
    EvidenceSourceType,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from .pipeline import (
    EVIDENCE_STORE_SCHEMA_VERSION,
    INGESTION_VERSION,
    IngestionResult,
    SourceFile,
    ingest_corpus,
    store_payload,
)
from .ports import PdfSourceError, SourceDocument, SourceDocumentReader

__all__ = [
    "EVIDENCE_STORE_SCHEMA_VERSION",
    "INGESTION_VERSION",
    "AgeEvidenceType",
    "EvidenceRecord",
    "EvidenceSourceType",
    "ExtractionQuality",
    "IngestionResult",
    "MachineReadability",
    "PdfSourceError",
    "ReusePolicy",
    "Setting",
    "SourceDocument",
    "SourceDocumentReader",
    "SourceFile",
    "SourceSection",
    "ingest_corpus",
    "store_payload",
]
