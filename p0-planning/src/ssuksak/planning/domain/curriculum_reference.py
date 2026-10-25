"""Versioned 누리과정 content Reference: the only ids a play-project learning cell may cite."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidDomainValueError
from .theme_reference import ActivationStatus


@dataclass(frozen=True, slots=True)
class CurriculumContent:
    content_id: str
    domain: str
    category: str
    text: str

    def __post_init__(self) -> None:
        for name in ("content_id", "domain", "category", "text"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"CurriculumContent.{name} must be non-blank")

    @property
    def display(self) -> str:
        """The official wording the server shows; the LLM never writes it."""
        return f"{self.domain} - {self.category} - {self.text}"


@dataclass(frozen=True, slots=True)
class CurriculumCatalog:
    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    contents: tuple[CurriculumContent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.activation_status, ActivationStatus):
            raise InvalidDomainValueError("CurriculumCatalog.activation_status is invalid")
        ids = [content.content_id for content in self.contents]
        if not ids or len(ids) != len(set(ids)):
            raise InvalidDomainValueError("CurriculumCatalog needs unique content ids")

    @property
    def is_active(self) -> bool:
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def get(self, content_id: str) -> CurriculumContent | None:
        return next((c for c in self.contents if c.content_id == content_id), None)
