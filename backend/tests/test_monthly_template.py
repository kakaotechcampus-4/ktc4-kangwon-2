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

from app.shared.hwpx import NS, TemplateMismatch, fill_grid

# hwpx.NS 에는 본문(hp)만 있다. 양식 모양은 header.xml 쪽 이름(hh · hc)에 들어 있다.
HEAD = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
}

TEMPLATE = Path(__file__).parents[1] / "app/features/plans/templates/monthly.hwpx"

ROWS, COLUMNS = 10, 6
#: 머리행 7줄 · 본문 원형 1줄 · 꼬리 2줄.
HEADER_ROWS = 7
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


def test_the_body_row_is_cloned_per_section(template: bytes) -> None:
    """Section 수만큼 본문 줄이 늘어야 한다. 행 이름은 양식이 아니라 계획안이 들고 온다."""
    content = fill_grid(
        template,
        "3세반 2026-10 놀이계획안",
        HEADER_ROWS,
        rows=[
            ["안전교육", "교통안전", "", "", "", ""],
            ["바깥놀이", "낙엽 모으기", "", "", "", ""],
            ["기본생활습관", "손 씻기", "", "", "", ""],
        ],
        footer=[["우리반 안내 사항"], [""]],
        header={(0, 1): "바람과 나뭇잎", (6, 1): "1주차"},
    )
    table = table_of(content)
    assert int(table.get("rowCnt")) == ROWS + 2
    printed = [t.text for t in table.iter(f"{{{NS['hp']}}}t")]
    for text in (
        "바람과 나뭇잎",
        "1주차",
        "안전교육",
        "낙엽 모으기",
        "손 씻기",
        "우리반 안내 사항",
    ):
        assert text in printed


def test_a_header_address_outside_the_header_rows_is_refused(template: bytes) -> None:
    """본문 원형 줄을 머리 칸으로 채우면 복제될 때 그 글자가 모든 줄에 번진다."""
    with pytest.raises(TemplateMismatch):
        fill_grid(
            template,
            "제목",
            HEADER_ROWS,
            rows=[["", "", "", "", "", ""]],
            footer=[["우리반 안내 사항"], [""]],
            header={(HEADER_ROWS, 0): "여기는 본문이다"},
        )


def test_cells_use_the_added_char_styles(template: bytes) -> None:
    """표 안 글자는 전부 양식에 더한 돋움체를 가리켜야 한다.

    가리키는 id 가 header.xml 에 없으면 한글이 파일을 안 연다.
    """
    with zipfile.ZipFile(BytesIO(template)) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
    defined = {c.get("id"): c for c in header.findall(".//hh:charPr", HEAD)}
    assert len(defined) == int(header.find(".//hh:charProperties", HEAD).get("itemCnt"))

    table = table_of(template)
    used = {run.get("charPrIDRef") for run in table.iter(f"{{{NS['hp']}}}run")}
    assert used <= defined.keys()
    bold = {i for i, c in defined.items() if c.find("hh:bold", HEAD) is not None}
    assert used & bold, "굵은 글씨를 쓰는 칸이 없다."


def test_label_cells_are_centered(template: bytes) -> None:
    """분류 이름은 가운데, 교사가 채우는 칸은 왼쪽이어야 한다."""
    cells = {
        (
            int(tc.find("hp:cellAddr", NS).get("rowAddr")),
            int(tc.find("hp:cellAddr", NS).get("colAddr")),
        ): tc
        for tc in table_of(template).iter(f"{{{NS['hp']}}}tc")
    }
    assert cells[(0, 0)].find(".//hp:p", NS).get("paraPrIDRef") == "20"  # 놀이 주제
    assert cells[(6, 1)].find(".//hp:p", NS).get("paraPrIDRef") == "20"  # 주차 머리
    assert cells[(0, 1)].find(".//hp:p", NS).get("paraPrIDRef") == "12"  # 값 칸


def test_column_widths_add_up(template: bytes) -> None:
    """칸 너비 합이 표 너비와 다르면 한글이 표를 제멋대로 늘린다."""
    table = table_of(template)
    width = int(table.find("hp:sz", NS).get("width"))
    for tr in table.findall("hp:tr", NS):
        total = sum(int(tc.find("hp:cellSz", NS).get("width")) for tc in tr.findall("hp:tc", NS))
        assert total == width


def test_the_empty_form_fits_one_page(template: bytes) -> None:
    """빈 양식이 A4 한 쪽을 넘으면 표가 두 쪽으로 쪼개져 출력된다.

    줄 수로 센다 — 한글이 cellSz 높이를 무시하고 글자 양으로 다시 계산하기 때문이다.
    한 쪽에 22줄까지 들어간다(2026-10-20 에 한글에서 확인).
    """
    lines = 0
    for tr in table_of(template).findall("hp:tr", NS):
        lines += max(len(tc.findall(".//hp:p", NS)) for tc in tr.findall("hp:tc", NS))
    assert lines <= 21, f"빈 양식이 {lines}줄이다."
