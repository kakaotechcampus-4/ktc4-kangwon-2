"""보육일지 hwpx 양식 두 개를 한글이 저장한 일일 양식에서 만든다.

**표를 손으로 그리지 않는다.** `header.xml`(글꼴·문단 모양·테두리)을 손으로 쓰면 한글이
파일을 안 여는 경로가 수십 개 생긴다 (`scripts/build_monthly_template.py` 머리말).
`daily_log.hwpx` 의 칸을 지우거나 복제해서 두 양식을 만든다.

    python scripts/build_journal_templates.py

만드는 것

    daily_log.hwpx    꼬리에 「반 운영 특이사항」 줄을 더한다 (제자리에서 고친다)
    weekly_log.hwpx   날짜별 5칸 + 꼬리 「주간 총평」

근거는 현장 실물이다. 멘토가 준 2025년 주간 보육일지(도담어린이집 만3세)는 하루마다
「우리반 놀이 | 놀이 이해 및 분석 | 앞으로의 지원방향」 세 칸과 그 아래 「반 운영 특이사항」
한 줄을 둔다. 우리 문서의 사실 · 해석 · 지원 3층과 그대로 맞는다. 하루를 표 하나로 두는
대신 **한 표에 날짜마다 한 줄**로 담는다 — 담기는 내용은 같고, 중앙육아종합지원센터
공식 작성사례 ③(날짜 × 반 운영 특이사항 표)과도 같은 모양이다.

일일 양식의 「반 운영 특이사항」은 공식 양식 5종 전부에 있는 칸이고, 사례 ④는 표 맨 아래
한 줄로 둔다 (`docs/references/보육일지-공식양식.md`).

두 번 돌려도 같은 결과다 — 이미 붙어 있는 특이사항 줄은 지우고 다시 만든다.
"""

import copy
import zipfile
from pathlib import Path

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
TEMPLATES = Path(__file__).resolve().parent.parent / "app/features/documents/templates"
DAILY = TEMPLATES / "daily_log.hwpx"
WEEKLY = TEMPLATES / "weekly_log.hwpx"

DAILY_NOTE_LABEL = "반 운영 특이사항"
WEEKLY_HEAD = ("날짜", "우리반 놀이", "놀이 이해 및 분석", "앞으로의 지원방향", DAILY_NOTE_LABEL)
WEEKLY_FOOTER_LABEL = "주간 총평"


def text_of(tc: etree._Element) -> str:
    return "".join(t.text or "" for t in tc.iter(f"{{{HP}}}t"))


def set_text(tc: etree._Element, text: str) -> None:
    """칸의 글자를 바꾼다. 빈 칸(글자 요소가 아예 없는 칸)이면 첫 run 에 하나 만든다."""
    runs = list(tc.iter(f"{{{HP}}}t"))
    if runs:
        runs[0].text = text
        for extra in runs[1:]:
            extra.text = ""
        return
    if not text:
        return
    run = tc.find("hp:subList/hp:p/hp:run", NS)
    etree.SubElement(run, f"{{{HP}}}t").text = text


def load(path: Path) -> tuple[etree._Element, etree._Element]:
    root = etree.fromstring(zipfile.ZipFile(path).read("Contents/section0.xml"))
    return root, next(root.iter(f"{{{HP}}}tbl"))


def save(root: etree._Element, source: Path, target: Path) -> None:
    """양식의 zip 순서와 압축 방식을 그대로 두고 본문만 갈아끼운다.

    `mimetype` 이 맨 앞에 압축 없이 들어가야 한글이 연다 (`app/shared/hwpx.py`).
    원본의 `ZipInfo` 를 그대로 쓰면 순서도 압축 방식도 따라온다.
    """
    section = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    # **먼저 통째로 읽는다.** 제자리에서 고칠 때(source == target) 쓰기로 열면 원본이
    # 잘려 나가 읽던 zip 이 깨진다.
    with zipfile.ZipFile(source) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for item, data in entries:
            out.writestr(item, section if item.filename == "Contents/section0.xml" else data)


def renumber(table: etree._Element) -> None:
    rows = table.findall("hp:tr", NS)
    table.set("rowCnt", str(len(rows)))
    for index, row in enumerate(rows):
        for cell in row.findall("hp:tc", NS):
            cell.find("hp:cellAddr", NS).set("rowAddr", str(index))


def row_height(row: etree._Element) -> int:
    return max(int(sz.get("height")) for sz in row.iterfind("hp:tc/hp:cellSz", NS))


def base_table() -> tuple[etree._Element, etree._Element]:
    """특이사항 줄을 아직 안 붙인 일일 양식 — 머리행 1 · 본문 원형 1 · 꼬리 1."""
    root, table = load(DAILY)
    rows = table.findall("hp:tr", NS)
    if len(rows) == 4 and text_of(rows[3].find("hp:tc", NS)).strip() == DAILY_NOTE_LABEL:
        table.remove(rows[3])
        size = table.find("hp:sz", NS)
        size.set("height", str(int(size.get("height")) - row_height(rows[3])))
        renumber(table)
        rows = table.findall("hp:tr", NS)
    assert len(rows) == 3, f"일일 양식은 머리행 · 원형 · 꼬리 3줄이어야 하는데 {len(rows)}줄이다."
    assert table.get("colCnt") == "4", f"일일 양식은 4칸이어야 하는데 {table.get('colCnt')}칸이다."
    return root, table


def build_daily() -> None:
    root, table = base_table()
    footer = table.findall("hp:tr", NS)[2]
    note = copy.deepcopy(footer)
    set_text(note.findall("hp:tc", NS)[0], DAILY_NOTE_LABEL)
    set_text(note.findall("hp:tc", NS)[1], "")
    footer.addnext(note)
    size = table.find("hp:sz", NS)
    size.set("height", str(int(size.get("height")) + row_height(note)))
    renumber(table)
    save(root, DAILY, DAILY)
    print(f"{DAILY.name} — 꼬리 2줄 (놀이 평가 및 다음날 지원계획 · {DAILY_NOTE_LABEL})")


def build_weekly() -> None:
    root, table = base_table()
    head, prototype, footer = table.findall("hp:tr", NS)
    widths = [int(tc.find("hp:cellSz", NS).get("width")) for tc in head.findall("hp:tc", NS)]

    # 4칸을 5칸으로 늘린다. 날짜는 「30일(월)」 한 줄이라 좁히고, 남은 너비를 네 칸이 나눈다.
    total = sum(widths)
    body = 6000
    rest = total - body
    shares = [rest // 4] * 4
    shares[-1] += rest - sum(shares)
    for row in (head, prototype):
        cells = row.findall("hp:tc", NS)
        extra = copy.deepcopy(cells[-1])
        row.append(extra)
        cells = row.findall("hp:tc", NS)
        cells[0].find("hp:cellSz", NS).set("width", str(body))
        for index, cell in enumerate(cells[1:], start=1):
            cell.find("hp:cellSz", NS).set("width", str(shares[index - 1]))
            cell.find("hp:cellAddr", NS).set("colAddr", str(index))
            cell.find("hp:cellSpan", NS).set("colSpan", "1")
            set_text(cell, "")
    for cell, text in zip(head.findall("hp:tc", NS), WEEKLY_HEAD, strict=True):
        set_text(cell, text)

    # 꼬리는 「이름 | 병합된 값」 두 칸이다. 늘어난 칸 수만큼 병합 수를 올린다.
    tail = footer.findall("hp:tc", NS)
    assert len(tail) == 2, f"꼬리 줄이 2칸이 아니다 — {len(tail)}칸이다."
    tail[0].find("hp:cellSz", NS).set("width", str(body))
    tail[1].find("hp:cellSz", NS).set("width", str(rest))
    tail[1].find("hp:cellSpan", NS).set("colSpan", "4")
    set_text(tail[0], WEEKLY_FOOTER_LABEL)
    set_text(tail[1], "")

    table.set("colCnt", "5")
    save(root, DAILY, WEEKLY)
    print(f"{WEEKLY.name} — {' | '.join(WEEKLY_HEAD)} + {WEEKLY_FOOTER_LABEL}")


if __name__ == "__main__":
    build_weekly()
    build_daily()
