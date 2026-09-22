"""Logical Evidence Store repository port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .store import InstitutionEvidenceStore


@runtime_checkable
class InstitutionEvidenceRepository(Protocol):
    def get_store(self) -> InstitutionEvidenceStore: ...
