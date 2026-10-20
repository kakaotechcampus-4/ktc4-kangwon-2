"""월간 놀이계획안 hwpx 양식을 만든다.

**표를 손으로 그리지 않는다.** 한글이 저장한 `annual.hwpx` 의 표를 복제해서 행·열 수와
글자만 바꾼다. `header.xml` 의 모양(글꼴·문단·테두리)은 건드리지 않는다 — 손으로 쓰면
한글이 파일을 안 여는 경로가 수십 개 생긴다(`app/shared/hwpx.py` 머리말).

색만 더한다. 칸 배경은 `borderFill` 이 들고 있으므로, 색을 넣은 `borderFill` 을 몇 개
붙이고 칸이 그걸 가리키게 한다.

    python backend/scripts/build_monthly_template.py

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

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
NS = {"hp": HP, "hh": HH, "hc": HC}

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/features/plans/templates/annual.hwpx"
TARGET = ROOT / "app/features/plans/templates/monthly.hwpx"

SECTION = "Contents/section0.xml"
HEADER = "Contents/header.xml"

#: 칸 너비. 합이 원본 표 너비(41952)와 같아야 한다. 첫 칸은 분류 이름이라 넓다.
COLUMNS = [7952, 6800, 6800, 6800, 6800, 6800]

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

#: 표 한 장. (글자, 가로로 합칠 칸 수, 색 이름) 세 개씩. 색 이름 None 이면 흰 칸.
#: 값 칸은 비워 둔다 — 코드가 채우고, 교사가 한글에서 고친다.
BODY_ROWS = ["기본생활습관", "안전교육", "소방대피 / 재난대비", "건강 · 영양교육"]
WEEK_FILLS = ["w1", "w2", "w3", "w4", "w5"]

LAYOUT: list[tuple[int, list[tuple[str, int, str | None]]]] = [
    (520, [("놀이 주제", 1, "head"), ("", 5, None)]),
    (520, [("예상 기간", 1, "head"), ("", 5, None)]),
    (1100, [("주제 선정 이유", 1, "head"), ("", 5, None)]),
    (460, [("예상되는 놀이 방향", 6, "band")]),
    (
        460,
        [
            ("함께하는 활동", 2, "head"),
            ("그림", 2, "head"),
            ("유아 예상 자유놀이", 2, "head"),
        ],
    ),
    (2600, [("", 2, None), ("", 2, None), ("", 2, None)]),
    (
        520,
        [("구분", 1, "head")] + [(f"{n}주차", 1, WEEK_FILLS[n - 1]) for n in range(1, 6)],
    ),
    *[(1400, [(name, 1, "head")] + [("", 1, None)] * 5) for name in BODY_ROWS],
    (460, [("우리반 안내 사항", 6, "band")]),
    (1100, [("", 6, None)]),
]


def add_fills(header: etree._Element) -> dict[str, int]:
    """색 칸을 header.xml 에 더하고 「이름 → id」를 돌려준다."""
    fills = header.find(".//hh:borderFills", NS)
    entries = fills.findall("hh:borderFill", NS)
    sample = entries[-1]  # 테두리가 그려진 칸. 이걸 복제해야 선이 남는다.
    next_id = max(int(entry.get("id")) for entry in entries) + 1

    ids: dict[str, int] = {}
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
        ids[name] = next_id
        next_id += 1

    fills.set("itemCnt", str(len(fills.findall("hh:borderFill", NS))))
    return ids


def build_table(table: etree._Element, fill_ids: dict[str, int]) -> None:
    """표를 LAYOUT 모양으로 갈아끼운다. 원본 칸을 복제해서 쓴다."""
    rows = table.findall("hp:tr", NS)
    blank = copy.deepcopy(rows[0].find("hp:tc", NS))
    plain_id = blank.get("borderFillIDRef")
    for row in rows:
        table.remove(row)

    for row_index, (height, cells) in enumerate(LAYOUT):
        tr = etree.SubElement(table, f"{{{HP}}}tr")
        column = 0
        for text, span, fill in cells:
            tc = copy.deepcopy(blank)
            tc.find(".//hp:t", NS).text = text
            tc.set("header", "1" if fill == "head" else "0")
            tc.set("borderFillIDRef", str(fill_ids[fill]) if fill else plain_id)

            addr = tc.find("hp:cellAddr", NS)
            addr.set("colAddr", str(column))
            addr.set("rowAddr", str(row_index))
            tc.find("hp:cellSpan", NS).set("colSpan", str(span))
            tc.find("hp:cellSpan", NS).set("rowSpan", "1")

            size = tc.find("hp:cellSz", NS)
            size.set("width", str(sum(COLUMNS[column : column + span])))
            size.set("height", str(height))
            tr.append(tc)
            column += span

    table.set("rowCnt", str(len(LAYOUT)))
    table.set("colCnt", str(len(COLUMNS)))
    size = table.find("hp:sz", NS)
    size.set("width", str(sum(COLUMNS)))
    size.set("height", str(sum(height for height, _ in LAYOUT)))


def main() -> None:
    with zipfile.ZipFile(SOURCE) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
        order = archive.namelist()

    header = etree.fromstring(parts[HEADER])
    fill_ids = add_fills(header)
    parts[HEADER] = etree.tostring(header, xml_declaration=True, encoding="UTF-8", standalone=True)

    section = etree.fromstring(parts[SECTION])
    tables = section.findall(".//hp:tbl", NS)
    if len(tables) != 1:
        raise SystemExit(f"양식에 표가 {len(tables)}개다. 1개일 때만 쓸 수 있다.")
    build_table(tables[0], fill_ids)
    parts[SECTION] = etree.tostring(
        section, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # mimetype 이 맨 앞에 압축 없이 들어가야 한글이 연다. 나머지 순서도 양식 그대로 둔다.
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as out:
        for name in order:
            if name == "mimetype":
                out.writestr(zipfile.ZipInfo("mimetype"), parts[name], zipfile.ZIP_STORED)
            else:
                out.writestr(name, parts[name])

    print(f"{TARGET} — {len(LAYOUT)}행 × {len(COLUMNS)}열, 색 {len(FILLS)}가지")


if __name__ == "__main__":
    main()
