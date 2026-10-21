"""주간계획안 양식(`plans/templates/weekly.hwpx`)이 쓸 수 있는 모양인지 본다.

양식은 `scripts/build_weekly_template.py` 가 만든다. 한글이 여는지는 사람이 열어봐야
알지만, 여기서 걸러지는 것들은 열기 전에 다 틀린 것이다(월간 `test_monthly_template.py` 와 같다).
"""

import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from lxml import etree

from app.features.forms import hwp_form
from app.shared.hwpx import NS, fill_grid, to_hwp

TEMPLATE = Path(__file__).parents[1] / "app/features/plans/templates/weekly.hwpx"

ROWS, COLUMNS = 4, 2
#: 머리 3줄(반 · 기간 · 구분 | 내용) · 본문 원형 1줄 · 꼬리 없음.
HEADER_ROWS = 3
CLASS_CELL, PERIOD_CELL = (0, 1), (1, 1)

#: 주간 Template A 의 12칸. 칸 이름은 양식이 아니라 계획안이 들고 온다.
SECTIONS = [
    ["주제", "우리나라와 세계 여러 나라"],
    ["소주제", "세계 여러 나라의 놀이를 알아보아요."],
    ["목표", "여러 나라의 놀이에 관심을 갖는다.\n친구와 규칙을 정해 함께 놀이한다."],
    ["기본생활", "놀이한 뒤 사용한 물건을 제자리에 정리해요."],
    ["안전교육", "불이 나면 대피하는 길을 익혀요."],
    ["실내놀이", "쌓기 — 세계의 탑 만들기"],
    ["대·소집단 활동", "이야기 나누기 — 가 보고 싶은 나라"],
    ["바깥놀이", "사방치기"],
    ["대체놀이", "강당에서 매트 사방치기"],
    ["가정연계", ""],
    ["행사", ""],
    ["특별활동", ""],
]
HEADER = {CLASS_CELL: "햇살반 (만 4세)", PERIOD_CELL: "9월 2주 · 2026-09-07 ~ 2026-09-11"}


def table_of(content: bytes) -> etree._Element:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    return section.find(".//hp:tbl", NS)


def _filled(template: bytes) -> bytes:
    return fill_grid(template, "햇살반 9월 2주 주간계획안", HEADER_ROWS, SECTIONS, [], HEADER)


@pytest.fixture
def template() -> bytes:
    return TEMPLATE.read_bytes()


def test_mimetype_is_stored_first(template: bytes) -> None:
    """맨 앞에 압축 없이 들어 있어야 한글이 연다."""
    with zipfile.ZipFile(BytesIO(template)) as archive:
        first = archive.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


def test_cell_addresses_and_widths_add_up(template: bytes) -> None:
    """칸 주소 · 너비가 어긋나면 한글이 파일을 안 열거나 표를 제멋대로 늘린다."""
    table = table_of(template)
    assert (int(table.get("rowCnt")), int(table.get("colCnt"))) == (ROWS, COLUMNS)
    width = int(table.find("hp:sz", NS).get("width"))
    for index, tr in enumerate(table.findall("hp:tr", NS)):
        tcs = tr.findall("hp:tc", NS)
        assert [
            (
                int(tc.find("hp:cellAddr", NS).get("rowAddr")),
                int(tc.find("hp:cellAddr", NS).get("colAddr")),
            )
            for tc in tcs
        ] == [(index, c) for c in range(COLUMNS)]
        assert sum(int(tc.find("hp:cellSz", NS).get("width")) for tc in tcs) == width


def test_header_labels_are_printed_and_section_names_are_not(template: bytes) -> None:
    printed = {t.text for t in table_of(template).iter(f"{{{NS['hp']}}}t")}
    assert {"반", "기간", "구분", "내용"} <= printed
    assert not {"주제", "안전교육", "바깥놀이"} & printed  # 계획안이 들고 온다


def test_the_body_row_is_cloned_per_section(template: bytes) -> None:
    table = table_of(_filled(template))
    assert int(table.get("rowCnt")) == HEADER_ROWS + len(SECTIONS)
    rows = [
        [
            "".join(t.text or "" for t in tc.iter(f"{{{NS['hp']}}}t"))
            for tc in tr.findall("hp:tc", NS)
        ]
        for tr in table.findall("hp:tr", NS)
    ]
    assert rows[0][1] == HEADER[CLASS_CELL] and rows[1][1] == HEADER[PERIOD_CELL]
    assert [row[0] for row in rows[HEADER_ROWS:]] == [label for label, _ in SECTIONS]
    assert rows[HEADER_ROWS + 7][1] == "사방치기"


def test_the_filled_form_converts_to_hwp_and_reads_back(template: bytes, tmp_path) -> None:
    """`.hwp` 로 바꾼 뒤 양식 등록이 쓰는 pyhwp 로 다시 읽어도 칸 글자가 같다(ADR-039)."""
    path = tmp_path / "weekly.hwp"
    path.write_bytes(to_hwp(_filled(template)))
    [table] = hwp_form.from_hwp(path)
    read = [[cell["text"] for cell in row] for row in table]

    def as_read(text: str) -> str:  # pyhwp 는 칸 안 줄바꿈 · 연속 공백을 한 칸으로 읽는다
        return re.sub(r"\s+", " ", text).strip()

    expected = [
        ["반", HEADER[CLASS_CELL]],
        ["기간", HEADER[PERIOD_CELL]],
        ["구분", "내용"],
        *SECTIONS,
    ]
    assert read == [[as_read(text) for text in row] for row in expected]


def test_the_empty_form_fits_one_page(template: bytes) -> None:
    """빈 양식이 A4 한 쪽(22줄)을 넘지 않는다 — 월간과 같은 기준."""
    lines = sum(
        max(len(tc.findall(".//hp:p", NS)) for tc in tr.findall("hp:tc", NS))
        for tr in table_of(template).findall("hp:tr", NS)
    )
    assert lines <= 21
