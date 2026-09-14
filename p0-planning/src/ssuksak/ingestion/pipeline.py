"""Corpus → Evidence Store (L1).

재현 가능한 ingestion이 목적이다. 같은 입력 + 같은 `ingestion_version`이면
언제나 같은 record 집합과 같은 `content_sha256`이 나온다.

`generated_at` 같은 build metadata는 content와 **분리**한다. 그렇지 않으면
같은 내용을 다시 만들 때마다 전체 SHA가 달라져 재현성을 확인할 수 없다.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from dataclasses import dataclass, field

from .classifiers import classify_age_page, classify_section
from .evidence_builder import PageContext, build_page_records
from .models import (
    AgeEvidenceType,
    EvidenceRecord,
    ExtractionQuality,
    MachineReadability,
    SourceSection,
)
from .ports import PdfSourceError, SourceDocumentReader

__all__ = [
    "EVIDENCE_STORE_SCHEMA_VERSION",
    "INGESTION_VERSION",
    "IngestionResult",
    "SourceFile",
    "ingest_corpus",
    "store_payload",
]

EVIDENCE_STORE_SCHEMA_VERSION = "institution-evidence.schema.v0"
INGESTION_VERSION = "institution-evidence-ingestion-v0.1.0"
"""Ingestion Pipeline version. record_id·분류 규칙이 바뀌면 올린다."""

TEMPLATE_FAMILY = frozenset(
    {"마성어린이집", "우리어린이집", "키즈로스쿨어린이집", "혜솔어린이집"}
)
"""2026-09-12 Corpus 재분석에서 확인된 Template Family. 독립 Source 보정용이다."""

_FN_MONTH = re.compile(r"\((\d{1,2})월\)")
_FN_YEAR = re.compile(r"(20\d{2})")
_FN_INST = re.compile(r"([가-힣A-Za-z0-9·\s]+?(?:어린이집|유치원))")
_FN_ESTAB = re.compile(
    r"_(국공립|민간|가정|법인단체|법인·단체등|법인·단체|직장|협동|사회복지법인|법인)_"
)
_TITLE_MONTH = re.compile(r"(\d{1,2})\s*월")


@dataclass(frozen=True, slots=True)
class SourceFile:
    """ingest 대상 파일 하나."""

    path: str
    sha256: str
    readable: bool

    @property
    def name(self) -> str:
        return pathlib.PurePath(self.path).name


@dataclass(slots=True)
class IngestionResult:
    records: list[EvidenceRecord] = field(default_factory=list)
    sources: list[SourceFile] = field(default_factory=list)
    files_scanned: int = 0
    files_text_layer: int = 0
    files_image_only: int = 0
    files_without_cells: list[str] = field(default_factory=list)
    files_failed: list[tuple[str, str]] = field(default_factory=list)
    pages_scanned: int = 0
    pages_with_cells: int = 0


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_filename(name: str) -> dict[str, object]:
    """파일명에서 읽을 수 있는 것만 읽는다. **본문이 Truth다.**"""
    stem = pathlib.PurePath(name).stem
    month = _FN_MONTH.search(stem)
    year = _FN_YEAR.search(stem)
    estab = _FN_ESTAB.search(f"_{stem}_")
    inst = _FN_INST.search(stem)
    return {
        "month": int(month.group(1)) if month else None,
        "year": int(year.group(1)) if year else None,
        "establishment": estab.group(1) if estab else None,
        "institution": inst.group(1).strip().split("_")[-1] if inst else None,
    }


def _page_month(text: str, fn_month: int | None) -> int | None:
    if fn_month is not None:
        return fn_month
    for m in _TITLE_MONTH.finditer(text):
        v = int(m.group(1))
        if 1 <= v <= 12:
            return v
    return None


def _page_theme(page_cells, text: str) -> str | None:
    """면의 월 주제. 주제 행이 있을 때만 읽는다."""
    for (_top, _bottom), columns in page_cells.rows():
        order = sorted(columns)
        if not order:
            continue
        label = " ".join(columns[order[0]].items).strip()
        if classify_section(label) is SourceSection.THEME and len(order) > 1:
            value = " ".join(columns[order[1]].items).strip()
            if value:
                return value[:40]
    return None


def ingest_corpus(
    sources: list[SourceFile], reader: SourceDocumentReader
) -> IngestionResult:
    """Corpus 전체를 Evidence Record로 만든다.

    image-only Source는 읽을 수 없다는 사실을 그대로 남기고 record를 만들지 않는다.
    추정하지 않는다.
    """
    result = IngestionResult(sources=sorted(sources, key=lambda s: s.path))

    for src in result.sources:
        result.files_scanned += 1
        if not src.readable:
            result.files_image_only += 1
            continue
        result.files_text_layer += 1

        try:
            doc = reader.open(src.path)
        except PdfSourceError as exc:
            result.files_failed.append((src.path, str(exc)))
            continue

        fn = parse_filename(src.path)
        institution = fn["institution"]
        try:
            page_count = doc.page_count
            found_cells = False
            for page in range(1, page_count + 1):
                result.pages_scanned += 1
                text = doc.page_text(page)
                cells = doc.page_cells(page)
                if not cells.has_cells:
                    continue
                found_cells = True
                result.pages_with_cells += 1

                ages, age_kind = classify_age_page(text)
                ctx = PageContext(
                    source_path=src.path,
                    source_sha256=src.sha256,
                    page=page,
                    institution_id=institution,
                    institution_type=fn["establishment"],
                    year=fn["year"],
                    month=_page_month(text, fn["month"]),
                    age_scope=ages,
                    age_evidence_type=age_kind,
                    monthly_theme=_page_theme(cells, text),
                    template_family=institution in TEMPLATE_FAMILY,
                    machine_readability=MachineReadability.TEXT_LAYER,
                )
                result.records.extend(build_page_records(ctx, cells))
            if not found_cells:
                result.files_without_cells.append(src.path)
        finally:
            doc.close()

    result.records.sort(key=lambda r: r.record_id)
    return result


def store_payload(result: IngestionResult) -> dict[str, object]:
    """Evidence Store Artifact의 **content 부분**. build metadata를 넣지 않는다."""
    return {
        "schema_version": EVIDENCE_STORE_SCHEMA_VERSION,
        "ingestion_version": INGESTION_VERSION,
        "store_id": "ssuksak.institution-evidence",
        "normative_status": "CORPUS_OBSERVATION_NON_NORMATIVE",
        "disclaimer": (
            "이 Artifact는 Corpus 관찰값이며 사람이 승인한 canonical Reference가 "
            "아니다. Activity Reference를 대체하지 않고 Plan Item의 값이 되지 "
            "않는다. LLM Grounding Context로만 사용한다."
        ),
        "source_count": result.files_scanned,
        "source_text_layer_count": result.files_text_layer,
        "source_image_only_count": result.files_image_only,
        "source_hash_manifest": [
            {"path": s.path, "sha256": s.sha256,
             "machine_readability": ("TEXT_LAYER" if s.readable else "IMAGE_ONLY")}
            for s in result.sources
        ],
        "record_count": len(result.records),
        "records": [
            json.loads(r.model_dump_json(exclude_none=True)) for r in result.records
        ],
    }


def content_sha256(payload: dict[str, object]) -> str:
    """content만의 SHA. `generated_at` 같은 build metadata를 제외한 값이다."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def summarize(result: IngestionResult) -> dict[str, object]:
    import collections

    recs = result.records
    return {
        "files_scanned": result.files_scanned,
        "files_text_layer": result.files_text_layer,
        "files_image_only": result.files_image_only,
        "files_without_cells": len(result.files_without_cells),
        "files_failed": len(result.files_failed),
        "pages_scanned": result.pages_scanned,
        "pages_with_cells": result.pages_with_cells,
        "records_total": len(recs),
        "by_section": dict(
            collections.Counter(r.source_section.value for r in recs).most_common()
        ),
        "by_setting": dict(collections.Counter(r.setting.value for r in recs)),
        "by_age_evidence_type": dict(
            collections.Counter(r.age_evidence_type.value for r in recs)
        ),
        "by_extraction_quality": dict(
            collections.Counter(r.extraction_quality.value for r in recs)
        ),
        "general_grounding_eligible": sum(
            1 for r in recs if r.general_grounding_eligible
        ),
        "outdoor_activity_eligible": sum(
            1 for r in recs if r.outdoor_activity_eligible
        ),
        "week_position_present": sum(1 for r in recs if r.week_position is not None),
    }
