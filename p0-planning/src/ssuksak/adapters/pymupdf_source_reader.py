"""PyMuPDF 기반 `SourceDocumentReader` (L1).

CLAUDE.md §17의 가역 Adapter다. PDF 라이브러리를 **여기에만** 가둔다.

**`pymupdf`를 프로젝트 필수 dependency로 만들지 않는다.** 이 Adapter는
Evidence Store를 빌드할 때만 필요하고 Planning Core 런타임에는 필요 없다.
따라서 import를 함수 안으로 미루고, 없으면 명확한 오류를 낸다.

    # Evidence Store 빌드 시에만
    PYTHONPATH=<pdftools 설치 경로> python -m ssuksak.dev.build_evidence_store

`pyproject.toml`에 추가할지는 미결이다 — `docs/open-decisions.md` OD-N16.
"""

from __future__ import annotations

from ..ingestion.cells import PageCells, Word, build_cells
from ..ingestion.ports import PdfSourceError

__all__ = ["PyMuPdfSourceDocument", "PyMuPdfSourceReader"]


def _require_pymupdf():
    try:
        import pymupdf  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - 설치 환경에 따라 달라진다
        raise PdfSourceError(
            "pymupdf가 설치되어 있지 않다. Evidence Store 빌드 전용 의존성이며 "
            "Planning Core 런타임에는 필요 없다. 격리 설치 경로를 PYTHONPATH로 "
            "지정하거나 별도 환경에서 실행한다"
        ) from exc
    return pymupdf


def _rules(page) -> tuple[list[tuple[float, float, float]],
                          list[tuple[float, float, float]]]:
    """표의 수직/수평 선분. 병합 셀 때문에 좌표 구간까지 보존한다."""
    vs: list[tuple[float, float, float]] = []
    hs: list[tuple[float, float, float]] = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                (x0, y0), (x1, y1) = item[1], item[2]
                if abs(x0 - x1) < 1.5:
                    vs.append((round(x0, 1), min(y0, y1), max(y0, y1)))
                elif abs(y0 - y1) < 1.5:
                    hs.append((round(y0, 1), min(x0, x1), max(x0, x1)))
            elif item[0] == "re":
                r = item[1]
                vs += [(round(r.x0, 1), r.y0, r.y1), (round(r.x1, 1), r.y0, r.y1)]
                hs += [(round(r.y0, 1), r.x0, r.x1), (round(r.y1, 1), r.x0, r.x1)]
    return vs, hs


class PyMuPdfSourceDocument:
    """한 PDF. 페이지 번호는 1-based다."""

    __slots__ = ("_doc", "_path")

    def __init__(self, doc, path: str) -> None:
        self._doc = doc
        self._path = path

    @property
    def page_count(self) -> int:
        return int(self._doc.page_count)

    def _page(self, page: int):
        if not 1 <= page <= self.page_count:
            raise PdfSourceError(f"{self._path}: page {page}가 범위 밖이다")
        return self._doc[page - 1]

    def page_text(self, page: int) -> str:
        return self._page(page).get_text("text")

    def page_cells(self, page: int, *, rejoin: bool = True) -> PageCells:
        p = self._page(page)
        vs, hs = _rules(p)
        words = [
            Word(x0=w[0], top=w[1], x1=w[2], bottom=w[3], text=w[4])
            for w in p.get_text("words")
        ]
        return build_cells(
            page=page, words=words, vertical_rules=vs, horizontal_rules=hs,
            rejoin=rejoin,
        )

    def close(self) -> None:
        self._doc.close()


class PyMuPdfSourceReader:
    """경로 → `PyMuPdfSourceDocument`."""

    def open(self, path: str) -> PyMuPdfSourceDocument:
        pymupdf = _require_pymupdf()
        try:
            doc = pymupdf.open(path)
        except Exception as exc:  # noqa: BLE001 - 라이브러리 예외를 Port 예외로 변환
            raise PdfSourceError(f"{path}: 열 수 없다 ({type(exc).__name__})") from exc
        return PyMuPdfSourceDocument(doc, path)
