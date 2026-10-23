"""월간 놀이계획안 hwpx 양식을 만든다.

**표를 손으로 그리지 않는다.** 한글이 저장한 `annual.hwpx` 의 칸을 복제해서 행·열 수와
글자만 바꾼다. 글꼴·문단·테두리 묶음(`header.xml`)도 있는 것을 복제해서 쓴다 — 손으로
쓰면 한글이 파일을 안 여는 경로가 수십 개 생긴다(`app/shared/hwpx.py` 머리말).

    docker compose exec backend python scripts/build_monthly_template.py

근거 — 멘토가 준 월간 놀이계획안 2장(0세 · 3세)과 하민의 11기관 조사.
  본문 행   기본생활습관(10/11) · 안전교육(9/11) · 소방대피 · 건강·영양교육
  뺀 것     특성화 · 특별활동 시간표. 7/11 기관뿐이고 원마다 프로그램이 달라서
            칸을 고정하면 맞는 원이 없다.
"""

from __future__ import annotations

import copy
import pathlib
import zipfile

from lxml import etree

from app.shared.hwpx import _set_text

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
NS = {"hp": HP, "hh": HH, "hc": HC}

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/features/plans/templates/annual.hwpx"
TARGET = ROOT / "app/features/plans/templates/monthly.hwpx"

SECTION = "Contents/section0.xml"
HEADER = "Contents/header.xml"

#: 칸 너비. 합이 글이 들어가는 폭(41952)과 같아야 한다. 첫 칸은 분류 이름이라 넓다.
#: 10pt 한글 한 글자가 1000 이고 칸 좌우 여백이 1020 이다 — 첫 칸은 일곱 글자까지 한 줄.
COLUMNS = [8992, 6592, 6592, 6592, 6592, 6592]

#: 한 줄 높이. 한글이 글자 양을 보고 다시 계산하므로 어림값이다.
LINE = 1280

#: 더할 배경색. 멘토 자료의 연한 파랑 머리글 + 주차별 파스텔을 따른다.
FILLS = {
    "head": "#DCE9F5",
    "band": "#EFF4F9",
    "w1": "#EDE4F3",
    "w2": "#FADEE3",
    "w3": "#DCEFE4",
    "w4": "#FBF0D5",
    "w5": "#E3EAF7",
}

#: 더할 글자 모양. 양식에 굵은 돋움이 없어서 만든다. (본보기 id, 크기, 굵게)
#: id 1 은 함초롬돋움 10pt — 표 안은 이 글꼴로 통일한다. 바탕체(id 0)는 획이 얇아
#: 칸이 촘촘한 계획표에서 읽기 나쁘다.
CHAR_STYLES = {
    "label": (1, 1000, True),  # 분류 이름 · 머리 칸
    "band": (1, 1100, True),  # 묶음 머리말 한 줄짜리 띠
    "value": (1, 1000, False),  # 교사가 채우는 칸
}

#: 양식에 있는 문단 모양. 20 = 가운데, 12 = 왼쪽.
CENTER, LEFT = "20", "12"

WEEK_FILLS = ["w1", "w2", "w3", "w4", "w5"]

#: 본문은 빈 줄 하나다. 내보낼 때 계획안의 Section 수만큼 복제해서 채운다
#: (`hwpx.fill_grid`). 어느 Section 이 있는지는 원마다 고른 TemplateProfile 이 정한다 —
#: 안전교육·바깥놀이는 어디나 있고, 기본생활습관·소방대피는 고르는 원만 있다.
#: 그래서 행 이름을 양식에 박지 않는다.

# 표 한 장. 줄마다 (글자, 가로로 합칠 칸 수, 색, 글자 모양, 문단 모양).
# 값 칸은 비워 둔다 — 코드가 채우고, 교사가 한글에서 고친다.
#
# 글자 안의 줄바꿈은 빈 줄이고, 그만큼 칸이 벌어진다. 한글은 cellSz 높이를 무시하고 글자
# 양으로 다시 계산하므로 높이를 벌리는 길은 이것뿐이다. 글자가 들어가면 그 칸은 글자 수에
# 맞게 다시 잡히니, 여기 빈 줄은 **아무것도 안 넣었을 때의 모습**이다.
#
# 빈 줄을 다 더해서 21줄을 넘기면 안 된다. A4 한 쪽에 22줄까지 들어간다 — 넘기면 표가
# 두 쪽으로 쪼개져 출력된다. 본문 줄이 늘어나는 몫도 생각해서 여유를 둔다.
EMPTY = ""
BLANK_2 = "\n"
BLANK_3 = "\n\n"
Cell = tuple[str, int, str | None, str, str]
LAYOUT: list[list[Cell]] = [
    [("놀이 주제", 1, "head", "label", CENTER), (EMPTY, 5, None, "value", LEFT)],
    [("예상 기간", 1, "head", "label", CENTER), (EMPTY, 5, None, "value", LEFT)],
    [("주제 선정 이유", 1, "head", "label", CENTER), (BLANK_2, 5, None, "value", LEFT)],
    [("예상되는 놀이 방향", 6, "band", "band", LEFT)],
    [
        ("함께하는 활동", 2, "head", "label", CENTER),
        ("그림", 2, "head", "label", CENTER),
        ("유아 예상 자유놀이", 2, "head", "label", CENTER),
    ],
    # 가운데가 그림 자리다. 사진을 넣으면 한글이 그 칸을 더 벌린다.
    [(BLANK_3, 2, None, "value", LEFT)] * 3,
    [("구분", 1, "head", "label", CENTER)]
    + [(f"{n}주차", 1, WEEK_FILLS[n - 1], "label", CENTER) for n in range(1, 6)],
    [(EMPTY, 1, "head", "label", CENTER)] + [(BLANK_2, 1, None, "value", LEFT)] * 5,
    [("우리반 안내 사항", 6, "band", "band", LEFT)],
    [(BLANK_2, 6, None, "value", LEFT)],
]


def add_fills(header: etree._Element) -> dict[str, str]:
    """색 칸을 header.xml 에 더하고 「이름 → id」를 돌려준다."""
    fills = header.find(".//hh:borderFills", NS)
    entries = fills.findall("hh:borderFill", NS)
    sample = entries[-1]  # 테두리가 그려진 칸. 이걸 복제해야 선이 남는다.
    next_id = max(int(entry.get("id")) for entry in entries) + 1

    ids: dict[str, str] = {}
    for name, color in FILLS.items():
        entry = copy.deepcopy(sample)
        entry.set("id", str(next_id))
        for old in entry.findall("hc:fillBrush", NS):
            entry.remove(old)
        brush = etree.SubElement(etree.SubElement(entry, f"{{{HC}}}fillBrush"), f"{{{HC}}}winBrush")
        brush.set("faceColor", color)
        brush.set("hatchColor", "#999999")
        brush.set("alpha", "0")
        fills.append(entry)
        ids[name] = str(next_id)
        next_id += 1

    fills.set("itemCnt", str(len(fills.findall("hh:borderFill", NS))))
    return ids


def add_char_styles(header: etree._Element) -> dict[str, str]:
    """글자 모양을 더하고 「이름 → id」를 돌려준다.

    굵게는 `<hh:bold/>` 하나다. 한글은 자식 차례를 따지므로 밑줄(`hh:underline`) 앞에 넣는다.
    """
    chars = header.find(".//hh:charProperties", NS)
    entries = {int(entry.get("id")): entry for entry in chars.findall("hh:charPr", NS)}
    next_id = max(entries) + 1

    ids: dict[str, str] = {}
    for name, (base, height, bold) in CHAR_STYLES.items():
        entry = copy.deepcopy(entries[base])
        entry.set("id", str(next_id))
        entry.set("height", str(height))
        if bold:
            entry.insert(
                list(entry).index(entry.find("hh:underline", NS)), etree.Element(f"{{{HH}}}bold")
            )
        chars.append(entry)
        ids[name] = str(next_id)
        next_id += 1

    chars.set("itemCnt", str(len(chars.findall("hh:charPr", NS))))
    return ids


def build_table(
    table: etree._Element,
    fills: dict[str, str],
    chars: dict[str, str],
    layout: list[list[Cell]] = LAYOUT,
    columns: list[int] = COLUMNS,
) -> None:
    """표를 `layout` 모양으로 갈아끼운다. 원본 칸을 복제해서 쓴다.

    `layout` · `columns` 는 주간 양식(`build_weekly_template.py`)도 같은 길로 만들려고 받는다.
    """
    rows = table.findall("hp:tr", NS)
    blank = copy.deepcopy(rows[0].find("hp:tc", NS))
    plain = blank.get("borderFillIDRef")
    for row in rows:
        table.remove(row)

    height = 0
    for row_index, cells in enumerate(layout):
        tr = etree.SubElement(table, f"{{{HP}}}tr")
        lines = max(text.count("\n") + 1 for text, *_ in cells)
        column = 0
        for text, span, fill, char, para in cells:
            tc = copy.deepcopy(blank)
            tc.set("header", "1" if fill else "0")
            tc.set("borderFillIDRef", fills[fill] if fill else plain)
            _set_text(tc, text)
            for p in tc.iter(f"{{{HP}}}p"):
                p.set("paraPrIDRef", para)
            for run in tc.iter(f"{{{HP}}}run"):
                run.set("charPrIDRef", chars[char])

            addr = tc.find("hp:cellAddr", NS)
            addr.set("colAddr", str(column))
            addr.set("rowAddr", str(row_index))
            tc.find("hp:cellSpan", NS).set("colSpan", str(span))
            tc.find("hp:cellSpan", NS).set("rowSpan", "1")

            size = tc.find("hp:cellSz", NS)
            size.set("width", str(sum(columns[column : column + span])))
            size.set("height", str(lines * LINE))
            tr.append(tc)
            column += span
        height += lines * LINE

    table.set("rowCnt", str(len(layout)))
    table.set("colCnt", str(len(columns)))
    size = table.find("hp:sz", NS)
    size.set("width", str(sum(columns)))
    size.set("height", str(height))


def build(
    target: pathlib.Path = TARGET, layout: list[list[Cell]] = LAYOUT, columns: list[int] = COLUMNS
) -> dict[str, str]:
    """`annual.hwpx` 를 복제해 `layout` 표 하나짜리 양식을 `target` 에 쓴다.

    더한 글자 모양(「이름 → id」)을 돌려준다.
    """
    with zipfile.ZipFile(SOURCE) as archive:
        order = archive.namelist()
        parts = {name: archive.read(name) for name in order}

    header = etree.fromstring(parts[HEADER])
    fills, chars = add_fills(header), add_char_styles(header)
    parts[HEADER] = etree.tostring(header, xml_declaration=True, encoding="UTF-8", standalone=True)

    section = etree.fromstring(parts[SECTION])
    tables = section.findall(".//hp:tbl", NS)
    if len(tables) != 1:
        raise SystemExit(f"양식에 표가 {len(tables)}개다. 1개일 때만 쓸 수 있다.")
    build_table(tables[0], fills, chars, layout, columns)
    parts[SECTION] = etree.tostring(
        section, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # mimetype 이 맨 앞에 압축 없이 들어가야 한글이 연다. 나머지 차례도 양식 그대로 둔다.
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for name in order:
            if name == "mimetype":
                out.writestr(zipfile.ZipInfo("mimetype"), parts[name], zipfile.ZIP_STORED)
            else:
                out.writestr(name, parts[name])
    return chars


def main() -> None:
    chars = build()
    print(
        f"{TARGET} — {len(LAYOUT)}행 × {len(COLUMNS)}열, 색 {len(FILLS)} · 글자 모양 {len(chars)}"
    )


if __name__ == "__main__":
    main()
