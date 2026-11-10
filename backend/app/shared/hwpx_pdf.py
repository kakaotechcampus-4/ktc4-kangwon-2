"""다 채운 hwpx 를 PDF 로 바꾼다 (ADR-061). `.hwp` 와 같이 hwpx 한 벌에서 만든다.

**표를 양식에서 그대로 옮겨 그린다.** 칸 주소 · 병합 · 너비 · 높이 · 테두리 · 바탕색 · 글자 크기 ·
굵기 · 정렬을 hwpx 가 적어둔 값으로 reportlab 에 다시 그린다. 계획안 종류마다 따로 그리지 않는다 —
`fill_table` · `fill_grid` 가 채운 결과면 연간 · 월간 · 주간 · 일지 모두 같은 코드로 나온다.

한글의 조판을 흉내 내는 것이라 똑같지는 않다(글꼴은 하나 · 줄 간격 근사).
쪽(첫 문단의 `pageBreak`)마다 한 장에 맞춰 줄인다 — 글이 많으면 글자가 작아진다.
"""

import io
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from lxml import etree
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate, Table

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
NS = {"hp": HP, "hh": HH, "hc": HC}

# HWPUNIT 은 1/7200 인치 = 1/100 pt.
PT = 0.01

# 한글 글꼴 — 서버 이미지는 fonts-nanum(Dockerfile), 로컬 Windows 는 맑은 고딕.
# ponytail: 글꼴 하나로 다 그린다. 양식 글꼴(함초롬 등)을 맞추려면 글꼴 파일을 더 깐다.
FONT_CANDIDATES = (
    (
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ),
    ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
)
FONT, FONT_BOLD = "PlanKR", "PlanKR-Bold"

_ALIGN = {"CENTER": TA_CENTER, "RIGHT": TA_RIGHT, "JUSTIFY": TA_JUSTIFY, "DISTRIBUTE": TA_JUSTIFY}
_VALIGN = {"TOP": "TOP", "CENTER": "MIDDLE", "BOTTOM": "BOTTOM"}
_SIDES = {"leftBorder": "LINEBEFORE", "rightBorder": "LINEAFTER"}
_SIDES |= {"topBorder": "LINEABOVE", "bottomBorder": "LINEBELOW"}
_MM = re.compile(r"([\d.]+)\s*mm")


class FontMissing(Exception):
    """한글 글꼴 파일이 서버에 없다."""


def _register_fonts() -> None:
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont(FONT, regular))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
            return
    raise FontMissing("한글 글꼴 파일이 없습니다.")


def _int(el: etree._Element | None, name: str, default: int = 0) -> int:
    return int(el.get(name, default)) if el is not None else default


class _Header:
    """header.xml 의 글자 모양 · 문단 모양 · 테두리/배경을 id 로 찾는다."""

    def __init__(self, header: etree._Element):
        self.chars = {c.get("id"): c for c in header.iter(f"{{{HH}}}charPr")}
        self.paras = {p.get("id"): p for p in header.iter(f"{{{HH}}}paraPr")}
        self.fills = {b.get("id"): b for b in header.iter(f"{{{HH}}}borderFill")}

    def char(self, ref: str | None) -> tuple[float, bool, str]:
        c = self.chars.get(ref)
        if c is None:
            return 10.0, False, "#000000"
        color = c.get("textColor", "#000000")
        return _int(c, "height", 1000) * PT, c.find("hh:bold", NS) is not None, color

    def align(self, ref: str | None) -> int:
        p = self.paras.get(ref)
        a = p.find(".//hh:align", NS) if p is not None else None
        return _ALIGN.get(a.get("horizontal") if a is not None else "", TA_LEFT)  # type: ignore[arg-type, return-value]

    def word_wrap(self, ref: str | None) -> str | None:
        """한글 줄 나눔. KEEP_WORD 면 어절 단위(긴 어절만 쪼갠다), BREAK_WORD 면 글자 단위."""
        p = self.paras.get(ref)
        b = p.find(".//hh:breakSetting", NS) if p is not None else None
        keep = b is not None and b.get("breakNonLatinWord") == "KEEP_WORD"
        return None if keep else "CJK"

    def cell_style(self, ref: str | None, at: tuple[int, int, int, int]) -> list:
        """칸 하나의 테두리 · 바탕색 — reportlab TableStyle 명령."""
        b = self.fills.get(ref)
        if b is None:
            return []
        c0, r0, c1, r1 = at
        out: list[tuple] = []
        for side, command in _SIDES.items():
            line = b.find(f"hh:{side}", NS)
            if line is None or line.get("type", "NONE") == "NONE":
                continue
            mm = _MM.match(line.get("width", "0.1 mm"))
            width = float(mm.group(1)) * 72 / 25.4 if mm else 0.4
            out.append((command, (c0, r0), (c1, r1), width, colors.HexColor(line.get("color"))))
        brush = b.find(".//hc:winBrush", NS)
        face = brush.get("faceColor") if brush is not None else None
        if face and face.lower() != "none":
            out.append(("BACKGROUND", (c0, r0), (c1, r1), colors.HexColor(face)))
        return out


def _paragraph(p: etree._Element, header: _Header, scale: float = 1.0) -> Paragraph:
    """hwpx 문단 하나 → reportlab 문단. 글자 모양은 run 마다 바꾼다."""
    parts, first = [], None
    for run in p.findall("hp:run", NS):
        text = "".join("".join(t.itertext()) for t in run.findall("hp:t", NS))
        size, bold, color = header.char(run.get("charPrIDRef"))
        if text:
            first = first or (size, bold, color)
            face = FONT_BOLD if bold else FONT
            parts.append(f'<font name="{face}" size="{size * scale:.2f}" color="{color}">')
            parts.append(escape(text) + "</font>")
    size, bold, _ = first or (10.0, False, "#000000")
    style = ParagraphStyle(
        "hwpx",
        fontName=FONT_BOLD if bold else FONT,
        fontSize=size * scale,
        leading=size * scale * 1.3,
        alignment=header.align(p.get("paraPrIDRef")),
        wordWrap=header.word_wrap(p.get("paraPrIDRef")),
    )
    return Paragraph("".join(parts) or "&nbsp;", style)


def _widths(cells: list[tuple[int, int, int]], count: int) -> list[float]:
    """열 너비. 칸은 (첫 열, 열 수, 너비). 한 열짜리 칸부터 풀고, 병합 칸에서 남은 하나를 푼다."""
    known: dict[int, float] = {}
    for col, span, width in cells:
        if span == 1:
            known.setdefault(col, width)
    changed = True
    while changed:
        changed = False
        for col, span, width in cells:
            unknown = [c for c in range(col, col + span) if c not in known]
            if len(unknown) == 1:
                known[unknown[0]] = width - sum(known.get(c, 0) for c in range(col, col + span))
                changed = True
    rest = [c for c in range(count) if c not in known]
    if rest:
        total = max(col_w for _, _, col_w in cells) if cells else 0
        share = max(total - sum(known.values()), 0) / len(rest)
        known.update({c: share for c in rest})
    return [max(known[c], 1) * PT for c in range(count)]


def _table(tbl: etree._Element, header: _Header) -> Table:
    rows, cols = int(tbl.get("rowCnt")), int(tbl.get("colCnt"))  # type: ignore[arg-type]
    grid: list[list] = [["" for _ in range(cols)] for _ in range(rows)]
    style: list = [("FONTNAME", (0, 0), (-1, -1), FONT)]
    spans: list[tuple[int, int, int]] = []
    heights = [0.0] * rows
    for tc in tbl.iterfind("hp:tr/hp:tc", NS):
        addr, span = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
        size, margin = tc.find("hp:cellSz", NS), tc.find("hp:cellMargin", NS)
        r, c = _int(addr, "rowAddr"), _int(addr, "colAddr")
        rs, cs = _int(span, "rowSpan", 1), _int(span, "colSpan", 1)
        sub = tc.find("hp:subList", NS)
        grid[r][c] = [_paragraph(p, header) for p in sub.findall("hp:p", NS)]  # type: ignore[union-attr]
        at = (c, r, c + cs - 1, r + rs - 1)
        if rs > 1 or cs > 1:
            style.append(("SPAN", at[:2], at[2:]))
        valign = _VALIGN.get(sub.get("vertAlign", "CENTER"), "MIDDLE")  # type: ignore[union-attr]
        style.append(("VALIGN", at[:2], at[2:], valign))
        for side, name in (("LEFT", "left"), ("RIGHT", "right")):
            style.append((f"{side}PADDING", at[:2], at[2:], _int(margin, name, 141) * PT))
        for side, name in (("TOP", "top"), ("BOTTOM", "bottom")):
            style.append((f"{side}PADDING", at[:2], at[2:], _int(margin, name, 141) * PT))
        style += header.cell_style(tc.get("borderFillIDRef"), at)
        spans.append((c, cs, _int(size, "width")))
        if rs == 1:
            heights[r] = max(heights[r], _int(size, "height") * PT)
    widths = _widths(spans, cols)

    # 칸 글이 양식 높이보다 길면 줄을 늘린다(한글이 하듯). 한 줄짜리 칸을 먼저 맞추고,
    # 여러 줄에 걸친 칸은 걸친 줄 높이 합이 모자란 만큼을 그 줄들에 고르게 나눈다.
    def row_span(tc: etree._Element) -> int:
        return _int(tc.find("hp:cellSpan", NS), "rowSpan", 1)

    for tc in sorted(tbl.iterfind("hp:tr/hp:tc", NS), key=row_span):
        addr, span = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
        margin = tc.find("hp:cellMargin", NS)
        r, c = _int(addr, "rowAddr"), _int(addr, "colAddr")
        rs, cs = row_span(tc), _int(span, "colSpan", 1)
        pad = (_int(margin, "left", 141) + _int(margin, "right", 141)) * PT
        inner = sum(widths[c : c + cs]) - pad
        need = sum(p.wrap(inner, 10**6)[1] for p in grid[r][c])
        need += (_int(margin, "top", 141) + _int(margin, "bottom", 141)) * PT
        short = need - sum(heights[r : r + rs])
        if short > 0:
            for i in range(r, r + rs):
                heights[i] += short / rs
    return Table(grid, colWidths=widths, rowHeights=heights, style=style)


def _page(section: etree._Element) -> tuple[tuple[float, float], dict[str, float]]:
    page = section.find(".//hp:pagePr", NS)
    margin = page.find("hp:margin", NS)  # type: ignore[union-attr]
    size = (_int(page, "width") * PT, _int(page, "height") * PT)
    if page.get("landscape") == "NARROWLY":  # type: ignore[union-attr]  # 한글은 WIDELY 가 세로다
        size = size[::-1]
    m = {k: _int(margin, k) * PT for k in ("left", "right", "top", "bottom", "header", "footer")}
    return size, {
        "leftMargin": m["left"],
        "rightMargin": m["right"],
        "topMargin": m["top"] + m["header"],
        "bottomMargin": m["bottom"] + m["footer"],
    }


def to_pdf(hwpx: bytes) -> bytes:
    """hwpx → PDF. 글꼴이 없거나 hwpx 가 깨졌으면 예외 — 부르는 쪽이 503 으로 바꾼다."""
    _register_fonts()
    with zipfile.ZipFile(io.BytesIO(hwpx)) as package:
        header = _Header(etree.fromstring(package.read("Contents/header.xml")))
        names = [n for n in package.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)]
        names.sort(key=lambda n: (len(n), n))  # section2 가 section10 보다 앞
        sections = [etree.fromstring(package.read(n)) for n in names]
    size, margins = _page(sections[0])
    frame = (
        size[0] - margins["leftMargin"] - margins["rightMargin"],
        size[1] - margins["topMargin"] - margins["bottomMargin"],
    )

    pages: list[list] = [[]]
    for section in sections:
        for p in section.findall("hp:p", NS):
            if p.get("pageBreak") == "1" and pages[-1]:
                pages.append([])
            text_runs = []
            for run in p.findall("hp:run", NS):
                tables = run.findall("hp:tbl", NS)
                if not tables:
                    text_runs.append(run)
                    continue
                for tbl in tables:
                    pages[-1].append(_table(tbl, header))
            if any("".join(t.itertext()).strip() for r in text_runs for t in r.findall("hp:t", NS)):
                para = etree.Element(p.tag, p.attrib)
                para.extend(text_runs)
                pages[-1].append(_paragraph(para, header))

    story: list = []
    for i, content in enumerate(p for p in pages if p):
        if i:
            story.append(PageBreak())
        # 한 쪽은 한 장 — 넘치면 비율대로 줄인다.
        story.append(KeepInFrame(frame[0], frame[1] - 1, content, mode="shrink"))
    out = io.BytesIO()
    SimpleDocTemplate(out, pagesize=size, **margins).build(story)
    return out.getvalue()
