"""Ingestion ports keep document/PDF libraries outside the evidence pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol, runtime_checkable

from ..planning.evidence.models import (
    AgeEvidenceType,
    CellCoordinates,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)


class SourceReadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IngestionSource:
    path: str
    sha256: str
    machine_readability: MachineReadability

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise ValueError("IngestionSource.path must be non-blank")
        if not isinstance(self.sha256, str) or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("IngestionSource.sha256 must be lowercase SHA-256")
        if not isinstance(self.machine_readability, MachineReadability):
            raise ValueError("IngestionSource.machine_readability is invalid")


@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    page: int
    institution_id: str | None
    institution_type: str | None
    year: int | None
    month: int | None
    age_scope: tuple[int, ...]
    age_evidence_type: AgeEvidenceType
    monthly_theme: str | None
    source_section: SourceSection
    source_label: str
    setting: Setting
    extraction_quality: ExtractionQuality
    extraction_method: str
    source_cell: CellCoordinates
    experience_text: str | None = None
    activity_text: str | None = None
    week_position: int | None = None
    week_label: str | None = None
    template_family: bool = False
    reuse_policy: ReusePolicy = ReusePolicy.CONTEXT_ONLY


@runtime_checkable
class InstitutionEvidenceReader(Protocol):
    """Convert one source document into structured, source-faithful observations."""

    def read(self, source: IngestionSource) -> tuple[EvidenceObservation, ...]: ...
