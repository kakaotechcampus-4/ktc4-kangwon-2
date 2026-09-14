"""Table Cell 인식 Activity 추출기 (Parser Root Fix).

v0.2.0을 만든 추출은 `pdftotext -layout`의 **줄** 단위로 동작해서 두 가지 결함을
냈다. 본 모듈은 PDF의 표 선(vector) geometry로 **셀**을 먼저 복원한 뒤 셀 안에서만
분절한다.

    결함 1. 셀 안 줄바꿈(wrap)을 Activity 구분자로 오판
            '장화 신고 물웅덩이' / '건너기'  ← 한 Activity가 두 개로 쪼개짐

    결함 2. 괄선 없는 하위 열을 무시한 구두점 분절
            '우리집에 왜 왔니? 놀이를 해요.'  ← '?'에서 잘림

핵심 구분:

    visual line wrapping   → 재결합해야 한다
    semantic list          → 재결합하면 안 된다

두 가지를 가르는 결정 규칙은 **종결 형태**다. 한국어 Activity label은 `-기`,
`-요/-다`, 또는 명사(`모래놀이`, `강강술래`)로 끝난다. 종결 형태로 끝나지 않은
줄은 다음 줄로 이어진다. 길이나 들여쓰기는 쓰지 않는다 — 이 Corpus의 표는
가운데 정렬이라 들여쓰기가 wrap 신호가 되지 못한다.

    python analysis/tools/cell_extract.py <pdf> [--page N]
"""

from __future__ import annotations

import collections
import io
import pathlib
import re
import sys

__all__ = [
    "TERMINAL_PATTERN",
    "is_terminal_line",
    "rejoin_wrapped_lines",
    "split_line_by_gap",
    "extract_cells",
]

# --------------------------------------------------------------- 종결 판정

TERMINAL_PATTERN = re.compile(
    r"("
    r"기|"                       # -하기 -찾기 -건너기 -만들기
    r"요|다|까|자|래|"            # -해요 -습니다 -일까 -하자 -강강술래
    r"놀이|체험|한마당|"          # 명사 종결 (자주 나오는 말)
    r"[.!?…]"                    # 문장부호 종결
    r")\s*$"
)
"""줄이 그 자체로 끝난 형태인지.

**bare `이`를 종결로 보지 않는다.** `물웅덩이`, `무궁화꽃이`가 종결로 오판되어
wrap이 끊기기 때문이다(이전 Corpus 분석에서 확인된 실패 사례). `놀이`만 예외로
둔다.
"""

CONNECTIVE_TAIL = re.compile(r"(고|며|면서|서|으로|로|와|과|에|을|를|은|는)\s*$")
"""연결어미·조사로 끝나면 확실히 이어진다. 종결 판정보다 우선한다."""


def is_terminal_line(text: str) -> bool:
    """이 줄이 하나의 Activity로 완결되었는지."""
    t = text.strip()
    if not t:
        return True
    if CONNECTIVE_TAIL.search(t):
        return False
    return bool(TERMINAL_PATTERN.search(t))


def rejoin_wrapped_lines(lines: list[str]) -> list[str]:
    """한 셀 안의 줄 목록을 Activity 목록으로 되돌린다.

    종결되지 않은 줄은 다음 줄과 합친다. 종결된 줄은 그대로 하나의 항목이다.

    >>> rejoin_wrapped_lines(["장화 신고 물웅덩이", "건너기"])
    ['장화 신고 물웅덩이 건너기']
    >>> rejoin_wrapped_lines(["투호놀이", "줄다리기", "동대문 놀이"])
    ['투호놀이', '줄다리기', '동대문 놀이']
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


def split_line_by_gap(words, gap_ratio: float = 1.8) -> list[str]:
    """한 줄의 단어들을 큰 x 간격에서 나눈다.

    서진처럼 괄선 없이 좌/우로 두 반이 나뉜 표가 있다. **평균 글자 폭** 대비
    간격이 벌어지면 서로 다른 셀로 본다. 구두점으로 나누지 않는다 — `왔니?`가
    문장 중간에 오는 실제 사례가 있기 때문이다.

    글자 폭은 (전체 단어 폭 합) / (전체 글자 수)로 구한다. 단어 폭을 첫 단어
    길이로 나누면 한 줄 안에서 단어 길이가 다를 때 임계값이 크게 빗나간다.
    """
    if not words:
        return []
    ws = sorted(words, key=lambda w: w[0])
    total_w = sum(max(0.0, w[2] - w[0]) for w in ws)
    total_c = sum(len(w[4]) for w in ws)
    if total_c == 0 or total_w == 0:
        return [" ".join(w[4] for w in ws)]
    char_w = total_w / total_c
    threshold = char_w * gap_ratio

    chunks: list[list[str]] = [[ws[0][4]]]
    for prev, cur in zip(ws, ws[1:]):
        if cur[0] - prev[2] > threshold:
            chunks.append([cur[4]])
        else:
            chunks[-1].append(cur[4])
    return [" ".join(c) for c in chunks]


# --------------------------------------------------------------- 셀 복원


def _rules(page):
    """표의 수직/수평 선분. 병합 셀 때문에 y 구간까지 보존한다."""
    vs, hs = [], []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                (x0, y0), (x1, y1) = it[1], it[2]
                if abs(x0 - x1) < 1.5:
                    vs.append((round(x0, 1), min(y0, y1), max(y0, y1)))
                elif abs(y0 - y1) < 1.5:
                    hs.append((round(y0, 1), min(x0, x1), max(x0, x1)))
            elif it[0] == "re":
                r = it[1]
                vs += [(round(r.x0, 1), r.y0, r.y1), (round(r.x1, 1), r.y0, r.y1)]
                hs += [(round(r.y0, 1), r.x0, r.x1), (round(r.y1, 1), r.x0, r.x1)]
    return vs, hs


def extract_cells(page, *, rejoin: bool = True) -> dict[tuple[float, float, int], list[str]]:
    """(row_top, row_bottom, col_index) → 그 셀의 Activity 목록.

    표 선이 없는 PDF는 빈 dict를 반환한다. 추측으로 셀을 만들지 않는다.

    `rejoin=False`면 줄 재결합을 하지 않고 **원문 줄 그대로** 돌려준다.
    `<바깥놀이 항목> [실내대체활동] <대체안>`처럼 한 줄이 그 자체로 완결된
    레이아웃을 볼 때 필요하다 — 재결합하면 두 줄이 섞여 section 판정이 틀어진다.
    """
    vs, hs = _rules(page)
    if not vs or not hs:
        return {}

    row_edges = sorted({y for y, _, _ in hs})
    words = page.get_text("words")
    cells: dict[tuple[float, float, int], list[str]] = {}

    for top, bottom in zip(row_edges, row_edges[1:]):
        if bottom - top < 6:
            continue
        band_words = [w for w in words if top < (w[1] + w[3]) / 2 < bottom]
        if not band_words:
            continue
        cols = sorted({x for x, y0, y1 in vs if y0 <= top + 2 and y1 >= bottom - 2})
        if len(cols) < 2:
            cols = [min(w[0] for w in band_words) - 1, max(w[2] for w in band_words) + 1]

        def col_of(x: float) -> int:
            for i in range(len(cols) - 1):
                if cols[i] <= x < cols[i + 1]:
                    return i
            return len(cols) - 2

        # 셀 → 줄 → 단어
        grouped: dict[int, dict[float, list]] = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        for w in band_words:
            grouped[col_of(w[0])][round((w[1] + w[3]) / 2, 1)].append(w)

        for col, lines in grouped.items():
            # 괄선 없는 하위 열이 있으면 줄을 먼저 가로로 쪼갠다
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
                cells[(top, bottom, col)] = items
    return cells


# ------------------------------------------------------------------- CLI


def main(argv: list[str]) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if not argv:
        print(__doc__)
        return 1
    import pymupdf

    path = pathlib.Path(argv[0])
    page_no = 0
    if "--page" in argv:
        page_no = int(argv[argv.index("--page") + 1])
    doc = pymupdf.open(str(path))
    cells = extract_cells(doc[page_no])
    print(f"{path.name}  page {page_no}  cells={len(cells)}")
    for (top, bottom, col), items in sorted(cells.items()):
        print(f"  row[{top:.0f}-{bottom:.0f}] col{col}")
        for it in items:
            print(f"      {it}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
