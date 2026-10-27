"""주간 보육일지 hwpx 양식을 일일 보육일지 양식에서 만든다.

**손으로 그리지 않는다.** 한글이 저장한 `daily_log.hwpx` 의 열을 지워 2열 양식을 만든다.
`header.xml` 을 손으로 쓰면 한글이 파일을 안 여는 경로가 수십 개 생긴다
(`scripts/build_observation_templates.py` · `scripts/build_monthly_template.py` 와 같은 이유).

    python scripts/build_weekly_log_template.py

일일은 하루 일과를 시간 · 일과 · 활동계획 · 활동실행 네 칸으로 적지만, 주간은 날마다
확정한 일일 보육일지 한 줄씩이라 **날짜 · 그날의 놀이와 일과** 두 칸이다.
꼬리 한 줄은 그대로 두고 이름만 「놀이 평가 및 다음 주 지원계획」으로 바꾼다.
"""

import shutil
import zipfile
from pathlib import Path

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
TEMPLATES = Path(__file__).resolve().parent.parent / "app/features/documents/templates"
SOURCE = TEMPLATES / "daily_log.hwpx"
TARGET = TEMPLATES / "weekly_log.hwpx"

HEAD = ("날짜", "그날의 놀이와 일과")
FOOTER_LABEL = "놀이 평가 및 다음 주 지원계획"


def set_text(tc: etree._Element, text: str) -> None:
    runs = list(tc.iter(f"{{{HP}}}t"))
    runs[0].text = text
    for extra in runs[1:]:
        extra.text = ""


def build() -> None:
    root = etree.fromstring(zipfile.ZipFile(SOURCE).read("Contents/section0.xml"))
    table = next(root.iter(f"{{{HP}}}tbl"))
    rows = table.findall("hp:tr", NS)
    assert len(rows) == 3, (
        f"일일 양식이 아니다 — 머리행 · 원형 · 꼬리 3줄이어야 하는데 {len(rows)}줄이다."
    )
    assert table.get("colCnt") == "4", f"일일 양식은 4칸이어야 하는데 {table.get('colCnt')}칸이다."

    # 지우는 세 칸의 너비를 둘째 칸이 물려받는다. 표 전체 너비는 그대로여야 한다.
    head, prototype, footer = rows
    widths = [int(tc.find("hp:cellSz", NS).get("width")) for tc in head.findall("hp:tc", NS)]
    content_width = sum(widths[1:])

    for row in (head, prototype):
        cells = row.findall("hp:tc", NS)
        for cell in cells[2:]:
            row.remove(cell)
        cells[1].find("hp:cellSz", NS).set("width", str(content_width))
    for cell, text in zip(head.findall("hp:tc", NS), HEAD, strict=True):
        set_text(cell, text)

    # 꼬리는 이미 「이름 | 병합된 값」 두 칸이다. 본문이 2칸이 됐으니 병합 수만 줄인다.
    tail = footer.findall("hp:tc", NS)
    assert len(tail) == 2, f"꼬리 줄이 2칸이 아니다 — {len(tail)}칸이다."
    tail[1].find("hp:cellSpan", NS).set("colSpan", "1")
    set_text(tail[0], FOOTER_LABEL)

    table.set("colCnt", "2")

    shutil.copy(SOURCE, TARGET)
    section = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    source = zipfile.ZipFile(SOURCE)
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            data = source.read(item.filename)
            out.writestr(item, section if item.filename == "Contents/section0.xml" else data)
    print(f"{TARGET.name} — {' | '.join(HEAD)} + {FOOTER_LABEL}")


if __name__ == "__main__":
    build()
