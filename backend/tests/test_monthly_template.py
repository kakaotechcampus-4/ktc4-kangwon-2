"""월간 놀이계획안 양식(`plans/templates/monthly.hwpx`)이 쓸 수 있는 모양인지 본다.

양식은 `scripts/build_monthly_template.py` 가 만든다. 한글이 여는지는 사람이 열어봐야
알지만, 여기서 걸러지는 것들은 열기 전에 다 틀린 것이다 — 칸 주소가 어긋나거나,
병합 폭이 열 수를 넘거나, 색 칸이 빠졌거나.
"""

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from lxml import etree

from app.shared.hwpx import NS, TemplateMismatch, fill_cells

# hwpx.NS 에는 본문(hp)만 있다. 양식 모양은 header.xml 쪽 이름(hh · hc)에 들어 있다.
HEAD = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
}

TEMPLATE = Path(__file__).parents[1] / "app/features/plans/templates/monthly.hwpx"

ROWS, COLUMNS = 13, 6
#: 양식에 미리 적혀 있어야 하는 이름. 하나라도 빠지면 교사가 받는 문서가 달라진다.
LABELS = {
    "놀이 주제",
    "예상 기간",
    "주제 선정 이유",
    "예상되는 놀이 방향",
    "함께하는 활동",
    "유아 예상 자유놀이",
    "구분",
    "1주차",
    "5주차",
    "기본생활습관",
    "안전교육",
    "소방대피 / 재난대비",
    "건강 · 영양교육",
    "우리반 안내 사항",
}


def table_of(content: bytes) -> etree._Element:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    return section.find(".//hp:tbl", NS)


@pytest.fixture
def template() -> bytes:
    return TEMPLATE.read_bytes()


def test_mimetype_is_stored_first(template: bytes) -> None:
    """맨 앞에 압축 없이 들어 있어야 한글이 연다."""
    with zipfile.ZipFile(BytesIO(template)) as archive:
        first = archive.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


def test_cell_addresses_cover_every_column(template: bytes) -> None:
    """칸 주소와 병합 폭의 합이 줄마다 열 수와 맞아야 한다. 어긋나면 한글이 파일을 안 연다."""
    table = table_of(template)
    assert (int(table.get("rowCnt")), int(table.get("colCnt"))) == (ROWS, COLUMNS)

    rows = table.findall("hp:tr", NS)
    assert len(rows) == ROWS
    for index, tr in enumerate(rows):
        column = 0
        for tc in tr.findall("hp:tc", NS):
            addr = tc.find("hp:cellAddr", NS)
            assert (int(addr.get("rowAddr")), int(addr.get("colAddr"))) == (index, column)
            column += int(tc.find("hp:cellSpan", NS).get("colSpan"))
        assert column == COLUMNS, f"{index}번째 줄이 {column}칸이다."


def test_labels_are_printed(template: bytes) -> None:
    printed = {t.text for t in table_of(template).iter(f"{{{NS['hp']}}}t")}
    assert LABELS <= printed


def test_every_cell_has_a_background(template: bytes) -> None:
    """칸마다 borderFill 을 가리켜야 색과 테두리가 남는다."""
    with zipfile.ZipFile(BytesIO(template)) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
    fills = {f.get("id") for f in header.findall(".//hh:borderFill", HEAD)}
    assert len(fills) == int(header.find(".//hh:borderFills", HEAD).get("itemCnt"))

    colored = {
        f.get("id")
        for f in header.findall(".//hh:borderFill", HEAD)
        if (f.find("hc:fillBrush/hc:winBrush", HEAD) is not None)
        and f.find("hc:fillBrush/hc:winBrush", HEAD).get("faceColor") != "none"
    }
    assert len(colored) >= 6, "주차별 색이 모자란다."

    used = {tc.get("borderFillIDRef") for tc in table_of(template).iter(f"{{{NS['hp']}}}tc")}
    assert used <= fills
    assert used & colored, "색 칸을 쓰는 데가 없다."


def test_fill_cells_writes_only_the_given_cells(template: bytes) -> None:
    content = fill_cells(
        template, "3세반 10월 놀이계획안", {(0, 1): "바람과 나뭇잎", (7, 1): "손 씻기"}
    )
    printed = [t.text for t in table_of(content).iter(f"{{{NS['hp']}}}t")]
    assert "바람과 나뭇잎" in printed
    assert "손 씻기" in printed
    assert "기본생활습관" in printed  # 머리 칸은 그대로다


def test_fill_cells_rejects_a_merged_away_address(template: bytes) -> None:
    """(0, 2) 는 (0, 1) 에 합쳐져 없는 칸이다. 조용히 지나가면 글자가 사라진다."""
    with pytest.raises(TemplateMismatch):
        fill_cells(template, "제목", {(0, 2): "여기엔 칸이 없다"})
