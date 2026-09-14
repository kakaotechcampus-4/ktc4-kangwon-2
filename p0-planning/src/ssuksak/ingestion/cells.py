"""표 셀 복원 — PDF 라이브러리에 의존하지 않는 순수 로직 (L1).

`analysis/tools/cell_extract.py`에서 검증된 규칙을 Production으로 승격한 것이다.
**PDF를 직접 열지 않는다.** 좌표가 붙은 단어 목록만 받는다. 실제 PDF 읽기는
`ports.PdfCellSource` 구현체가 담당한다(`adapters/pymupdf_cell_source.py`).

이렇게 나눈 이유는 두 가지다.

1. PDF 라이브러리를 프로젝트 필수 dependency로 만들지 않는다.
2. 셀 복원 규칙을 PDF 없이 결정론적으로 테스트할 수 있다.

핵심 구분:

    visual line wrapping   → 재결합해야 한다
    semantic list          → 재결합하면 안 된다

가르는 기준은 **종결 형태**다. 길이나 들여쓰기는 쓰지 않는다 — 이 Corpus의 표는
가운데 정렬이라 들여쓰기가 wrap 신호가 되지 못한다.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass

__all__ = [
    "CELL_EXTRACTION_METHOD",
    "Cell",
    "PageCells",
    "Word",
    "build_cells",
    "is_terminal_line",
    "rejoin_wrapped_lines",
    "split_line_by_gap",
]

CELL_EXTRACTION_METHOD = "table_line_geometry_v1"
"""추출 방식 식별자. Evidence Record의 `extraction_method`에 기록한다."""


@dataclass(frozen=True, slots=True)
class Word:
    """좌표가 붙은 단어 하나. PDF 라이브러리 타입을 도메인에 들이지 않는다."""

    x0: float
    top: float
    x1: float
    bottom: float
    text: str

    @property
    def y_mid(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True, slots=True)
class Cell:
    """복원된 셀 하나."""

    row_top: float
    row_bottom: float
    column: int
    items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PageCells:
    """한 면의 셀 전체. 셀이 없으면 `cells`가 비어 있다."""

    page: int
    cells: tuple[Cell, ...]

    @property
    def has_cells(self) -> bool:
        return bool(self.cells)

    def rows(self) -> list[tuple[tuple[float, float], dict[int, Cell]]]:
        """(row band, column → Cell) 목록을 위에서 아래 순서로."""
        grouped: dict[tuple[float, float], dict[int, Cell]] = collections.defaultdict(dict)
        for c in self.cells:
            grouped[(c.row_top, c.row_bottom)][c.column] = c
        return sorted(grouped.items())


# --------------------------------------------------------------- 종결 판정

TERMINAL_PATTERN = re.compile(
    r"("
    r"기|"                       # -하기 -찾기 -건너기 -만들기
    r"요|다|까|자|래|"            # -해요 -습니다 -일까 -하자 -강강술래
    r"놀이|체험|한마당|"          # 명사 종결
    r"[.!?…]"                    # 문장부호 종결
    r")\s*$"
)
"""줄이 그 자체로 끝난 형태인지.

**bare `이`를 종결로 보지 않는다.** `물웅덩이` · `무궁화꽃이`가 종결로 오판되면
wrap이 끊긴다(2026-09 Corpus 분석에서 확인된 실패 사례). `놀이`만 예외다.
"""

CONNECTIVE_TAIL = re.compile(r"(고|며|면서|서|으로|로|와|과|에|을|를|은|는)\s*$")
"""연결어미·조사로 끝나면 확실히 이어진다. 종결 판정보다 우선한다."""


def is_terminal_line(text: str) -> bool:
    """이 줄이 하나의 항목으로 완결되었는지."""
    t = text.strip()
    if not t:
        return True
    if CONNECTIVE_TAIL.search(t):
        return False
    return bool(TERMINAL_PATTERN.search(t))


def rejoin_wrapped_lines(lines: list[str]) -> list[str]:
    """한 셀 안의 줄 목록을 항목 목록으로 되돌린다.

    >>> rejoin_wrapped_lines(["장화 신고 물웅덩이", "건너기"])
    ['장화 신고 물웅덩이 건너기']
    >>> rejoin_wrapped_lines(["투호놀이", "줄다리기를 해요", "동대문 놀이"])
    ['투호놀이', '줄다리기를 해요', '동대문 놀이']
    """
    out: list[str] = []
    buf: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        buf.append(line)
        if is_terminal_line(line):
            out.append(" ".join(buf))
            buf = []
    if buf:
        # 마지막까지 종결되지 않았으면 있는 그대로 남긴다. 추측해 채우지 않는다.
        out.append(" ".join(buf))
    return out


# ----------------------------------------------------- 괄선 없는 하위 열 분리


def split_line_by_gap(words: list[Word], gap_ratio: float = 1.8) -> list[str]:
    """한 줄의 단어들을 큰 x 간격에서 나눈다.

    괄선 없이 좌/우로 두 반이 나뉜 표가 있다. **평균 글자 폭** 대비 간격이
    벌어지면 서로 다른 셀로 본다. 구두점으로 나누지 않는다 — `왔니?`가 문장
    중간에 오는 실제 사례가 있기 때문이다.

    글자 폭은 (전체 단어 폭 합) / (전체 글자 수)다. 첫 단어 길이로 나누면 한 줄
    안에서 단어 길이가 다를 때 임계값이 크게 빗나간다.
    """
    if not words:
        return []
    ws = sorted(words, key=lambda w: w.x0)
    total_w = sum(max(0.0, w.x1 - w.x0) for w in ws)
    total_c = sum(len(w.text) for w in ws)
    if total_c == 0 or total_w == 0:
        return [" ".join(w.text for w in ws)]
    threshold = (total_w / total_c) * gap_ratio

    chunks: list[list[str]] = [[ws[0].text]]
    for prev, cur in zip(ws, ws[1:]):
        if cur.x0 - prev.x1 > threshold:
            chunks.append([cur.text])
        else:
            chunks[-1].append(cur.text)
    return [" ".join(c) for c in chunks]


# --------------------------------------------------------------- 셀 복원


def build_cells(
    *,
    page: int,
    words: list[Word],
    vertical_rules: list[tuple[float, float, float]],
    horizontal_rules: list[tuple[float, float, float]],
    rejoin: bool = True,
) -> PageCells:
    """표 선(vector) 기하로 셀을 복원한다.

    Args:
        vertical_rules: `(x, y_top, y_bottom)`. 병합 셀 때문에 y 구간을 보존한다.
        horizontal_rules: `(y, x_left, x_right)`.
        rejoin: False면 줄 재결합 없이 원문 줄 그대로 돌려준다.
            `<바깥놀이 항목> [실내대체활동] <대체안>`처럼 한 줄이 그 자체로
            완결된 레이아웃을 읽을 때 필요하다.

    표 선이 없으면 빈 `PageCells`를 반환한다. **추측으로 셀을 만들지 않는다.**
    """
    if not vertical_rules or not horizontal_rules:
        return PageCells(page=page, cells=())

    row_edges = sorted({y for y, _, _ in horizontal_rules})
    out: list[Cell] = []

    for top, bottom in zip(row_edges, row_edges[1:]):
        if bottom - top < 6:
            continue
        band = [w for w in words if top < w.y_mid < bottom]
        if not band:
            continue
        cols = sorted(
            {x for x, y0, y1 in vertical_rules if y0 <= top + 2 and y1 >= bottom - 2}
        )
        if len(cols) < 2:
            cols = [min(w.x0 for w in band) - 1, max(w.x1 for w in band) + 1]

        def col_of(x: float, _cols: list[float] = cols) -> int:
            for i in range(len(_cols) - 1):
                if _cols[i] <= x < _cols[i + 1]:
                    return i
            return len(_cols) - 2

        grouped: dict[int, dict[float, list[Word]]] = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        for w in band:
            grouped[col_of(w.x0)][round(w.y_mid, 1)].append(w)

        for col, lines in grouped.items():
            per_subcol: dict[int, list[str]] = collections.defaultdict(list)
            for y in sorted(lines):
                for k, chunk in enumerate(split_line_by_gap(lines[y])):
                    per_subcol[k].append(chunk)
            items: list[str] = []
            for k in sorted(per_subcol):
                items.extend(
                    rejoin_wrapped_lines(per_subcol[k]) if rejoin else per_subcol[k]
                )
            if items:
                out.append(
                    Cell(row_top=top, row_bottom=bottom, column=col,
                         items=tuple(items))
                )
    return PageCells(page=page, cells=tuple(out))
