"""2축 관찰일지 양식을 5영역 양식에서 만든다.

교사가 쓴 관찰일지 3건 중 2건이 누리과정 5영역이 아니라 **일상생활 · 놀이활동 2축**이었다
(docs/references/관찰일지-서술-기준.md). 5영역 양식 하나로는 그 원이 종이를 못 받는다.

**손으로 그리지 않는다.** 한글이 저장한 `observation.hwpx` 의 줄을 지워 2축 양식을 만든다.
`header.xml` 을 손으로 쓰면 한글이 파일을 안 여는 경로가 수십 개 생긴다 (월간 양식과 같은 이유,
`scripts/build_monthly_template.py`).

    python scripts/build_observation_templates.py
"""

import shutil
import zipfile
from pathlib import Path

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
TEMPLATES = Path(__file__).resolve().parent.parent / "app/features/documents/templates"
SOURCE = TEMPLATES / "observation.hwpx"
TARGET = TEMPLATES / "observation_daily_play.hwpx"

# 남길 줄의 머리 칸. 나머지 영역 줄은 지운다. 머리행(0)과 맨 아래 한 칸은 그대로 둔다.
KEEP = ("일상생활", "놀이활동")

# 맨 아래 한 칸의 이름. 교사가 쓴 문서를 그대로 따른다
# (`docs/references/관찰일지-서술-기준.md`) — 5영역 A02 는 「종합해석」, 2축 S05 는 「총평」이다.
# 「평가」라고 적으면 교사가 제출할 때 칸 이름을 고쳐야 한다.
NURI_TAIL = "종합해석"
DAILY_PLAY_TAIL = "총평"


def head_text(tr: etree._Element) -> str:
    first = tr.find("hp:tc", NS)
    return "".join(t.text or "" for t in first.iter(f"{{{HP}}}t")) if first is not None else ""


def set_head(tr: etree._Element, text: str) -> None:
    first = tr.find("hp:tc", NS)
    runs = [t for t in first.iter(f"{{{HP}}}t")]
    runs[0].text = text
    for extra in runs[1:]:
        extra.text = ""


def rewrite(path: Path, root: etree._Element) -> None:
    """양식의 zip 순서와 압축 방식을 그대로 두고 본문만 갈아끼운다.

    **먼저 통째로 읽는다** — 제자리에서 고칠 때 쓰기로 열면 원본이 잘려 읽던 zip 이 깨진다.
    """
    section = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(path) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for item, data in entries:
            out.writestr(item, section if item.filename == "Contents/section0.xml" else data)


def build_nuri() -> None:
    """5영역 양식의 맨 아래 칸 이름만 교사 문서대로 맞춘다. 줄 수·서식은 건드리지 않는다."""
    root = etree.fromstring(zipfile.ZipFile(SOURCE).read("Contents/section0.xml"))
    table = next(root.iter(f"{{{HP}}}tbl"))
    tail = table.findall("hp:tr", NS)[-1]
    if head_text(tail).strip() == NURI_TAIL:
        print(f"{SOURCE.name} — 이미 「{NURI_TAIL}」이다")
        return
    set_head(tail, NURI_TAIL)
    rewrite(SOURCE, root)
    print(f"{SOURCE.name} — 맨 아래 칸 「{NURI_TAIL}」")


def build() -> None:
    root = etree.fromstring(zipfile.ZipFile(SOURCE).read("Contents/section0.xml"))
    table = next(root.iter(f"{{{HP}}}tbl"))
    rows = table.findall("hp:tr", NS)
    # 머리행 1 + 영역 5 + 평가 1 = 7. 영역 줄 다섯 중 둘만 남기고 셋을 지운다.
    area = rows[1:-1]
    assert len(area) == 5, f"5영역 양식이 아니다 — 영역 줄이 {len(area)}개다."
    for row in area[len(KEEP) :]:
        table.remove(row)
    for row, name in zip(area[: len(KEEP)], KEEP, strict=True):
        set_head(row, name)
    set_head(rows[-1], DAILY_PLAY_TAIL)
    # 지운 만큼 줄 수와 칸 주소를 다시 매긴다. 한글은 cellAddr 로 칸을 찾는다.
    table.set("rowCnt", str(len(table.findall("hp:tr", NS))))
    for index, row in enumerate(table.findall("hp:tr", NS)):
        for cell in row.findall("hp:tc", NS):
            cell.find("hp:cellAddr", NS).set("rowAddr", str(index))

    shutil.copy(SOURCE, TARGET)
    section = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    source = zipfile.ZipFile(SOURCE)
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            data = source.read(item.filename)
            out.writestr(item, section if item.filename == "Contents/section0.xml" else data)
    print(f"{TARGET.name} — {table.get('rowCnt')}줄 ({' · '.join(KEEP)} + {DAILY_PLAY_TAIL})")


if __name__ == "__main__":
    build_nuri()
    build()
