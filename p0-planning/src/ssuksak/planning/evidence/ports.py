"""Logical Evidence Store repository port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .classification import EvidenceSemanticClassification
from .store import InstitutionEvidenceStore


@runtime_checkable
class InstitutionEvidenceRepository(Protocol):
    def get_store(self) -> InstitutionEvidenceStore: ...


@runtime_checkable
class EvidenceClassificationRepository(Protocol):
    def get_classification(self) -> EvidenceSemanticClassification: ...
