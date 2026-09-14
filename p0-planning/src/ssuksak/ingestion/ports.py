"""Ingestion Port (L1).

CLAUDE.md §17 "Port 우선 원칙". PDF 라이브러리를 Ingestion 파이프라인 안쪽에
들이지 않는다. 이 Protocol 뒤에 격리한다.

이렇게 하는 실질 이유가 둘 있다.

1. **프로젝트 필수 dependency를 늘리지 않는다.** PDF 파싱 라이브러리는 Ingestion
   빌드 단계에서만 필요하고 Planning Core 런타임에는 필요 없다.
   `pyproject.toml`을 건드리지 않고 Adapter에서 lazy import한다.
2. **셀 복원 규칙을 PDF 없이 테스트한다.** 테스트는 `FakeSourceDocument`로
   좌표만 주입한다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .cells import PageCells

__all__ = ["PdfSourceError", "SourceDocument", "SourceDocumentReader"]


class PdfSourceError(RuntimeError):
    """Source 파일을 열거나 읽을 수 없다. 추측으로 메우지 않는다."""


@runtime_checkable
class SourceDocument(Protocol):
    """한 Source 파일."""

    @property
    def page_count(self) -> int: ...

    def page_text(self, page: int) -> str:
        """1-based page의 평문. 연령·주제 판정에 쓴다."""
        ...

    def page_cells(self, page: int, *, rejoin: bool = True) -> PageCells:
        """1-based page의 복원된 셀. 표 선이 없으면 빈 `PageCells`."""
        ...

    def close(self) -> None: ...


@runtime_checkable
class SourceDocumentReader(Protocol):
    """경로 → `SourceDocument`."""

    def open(self, path: str) -> SourceDocument:
        """Raises: PdfSourceError."""
        ...
