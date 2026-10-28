"""월간 v2 양식(`plans/templates/play_monthly.hwpx`)과 채우기.

쪽 나눔 · 글꼴 · 겹침은 한글에서 사람이 봐야 안다. 여기서 걸러지는 것들은 열기 전에 다 틀린 것이다.
"""

import zipfile
from datetime import date
from io import BytesIO

import pytest
from lxml import etree
from ssuksak.planning.application.play_monthly_document import (
    PlayMonthlyDocument,
    PlayMonthlyDocumentWeek,
)

from app.features.plans.play_monthly_hwpx import TEMPLATE, fill_play_monthly
from app.features.plans.play_project_hwpx import TEMPLATE as PLAY_PROJECT_TEMPLATE
from app.shared.hwpx import NS, TemplateMismatch, to_hwp

CLASS = "만 3·4세 햇살반"
FOOTER = [
    "*예상 놀이 방향은 [2019 개정 누리과정]의 목적에 따라 ‘유아 놀이 중심’ 활동이 진행 될 수 있도록"
    " 융통성 있게 구성되었습니다. ",  # 전달본 그대로 — 끝 공백까지
    "*유아들의 흥미도와 참여 정도에 따라 다른 방향으로 조정됩니다.",
]


def document(weeks: int = 5, plays: int = 5) -> PlayMonthlyDocument:
    return PlayMonthlyDocument(
        month=3,
        target_ages=frozenset({3, 4}),
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 31),
        theme="합성 주제",
        rationale="합성 이유",
        together=tuple(f"함께 놀이 {i}" for i in range(1, plays + 1)),
        free_play=tuple(f"자유 놀이 {i}" for i in range(1, plays + 1)),
        weeks=tuple(
            PlayMonthlyDocumentWeek(
                "청결" if i > 1 else "", f"습관 {i}", f"안전 {i}" if i % 2 else ""
            )
            for i in range(1, weeks + 1)
        ),
        drill="합성 훈련",
        health="합성 건강",
        nutrition="",  # 빈 칸에는 「[영양] 」 을 붙이지 않는다
        birthdays="합성 생일",
        home_connection="합성 가정연계",
    )


def section(content: bytes) -> etree._Element:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return etree.fromstring(archive.read("Contents/section0.xml"))


def table(content: bytes) -> etree._Element:
    (found,) = section(content).findall(".//hp:tbl", NS)
    return found


def cells(content: bytes) -> dict[tuple[int, int], etree._Element]:
    out = {}
    for tc in table(content).iterfind("hp:tr/hp:tc", NS):
        addr = tc.find("hp:cellAddr", NS)
        out[(int(addr.get("rowAddr")), int(addr.get("colAddr")))] = tc
    return out


def lines(tc: etree._Element) -> list[str]:
    return ["".join(p.itertext()) for p in tc.iterfind("hp:subList/hp:p", NS)]


def week_row(content: bytes, row: int) -> list[etree._Element]:
    return sorted(
        (tc for (r, c), tc in cells(content).items() if r == row and c > 0),
        key=lambda tc: int(tc.find("hp:cellAddr", NS).get("colAddr")),
    )


def assert_whole_grid(content: bytes) -> None:
    """병합을 펼친 격자의 칸마다 정확히 한 셀, 같은 세로선은 어느 줄에서나 같은 x."""
    found = table(content)
    rows, cols = int(found.get("rowCnt")), int(found.get("colCnt"))
    covered, spans = [], []
    for tc in found.iterfind("hp:tr/hp:tc", NS):
        addr, span = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
        r, c = int(addr.get("rowAddr")), int(addr.get("colAddr"))
        rs, cs = int(span.get("rowSpan")), int(span.get("colSpan"))
        covered += [(r + i, c + j) for i in range(rs) for j in range(cs)]
        spans.append((c, c + cs, int(tc.find("hp:cellSz", NS).get("width"))))
    assert sorted(covered) == [(r, c) for r in range(rows) for c in range(cols)]
    x = {0: 0}
    for _ in range(cols):
        for start, end, width in spans:
            if start in x:
                assert x.setdefault(end, x[start] + width) == x[start] + width, (start, end)
    assert len(x) == cols + 1 and x[cols] == int(found.find("hp:sz", NS).get("width"))


@pytest.fixture(scope="module")
def filled() -> bytes:
    return fill_play_monthly(TEMPLATE.read_bytes(), document(), CLASS)


def test_the_template_is_one_28_by_17_table_with_77_cells() -> None:
    found = table(TEMPLATE.read_bytes())
    shape = (found.get("rowCnt"), found.get("colCnt"), found.get("pageBreak"))
    assert shape == ("28", "17", "CELL")
    assert len(found.findall("hp:tr/hp:tc", NS)) == 77
    assert_whole_grid(TEMPLATE.read_bytes())


def test_mimetype_is_stored_first(filled: bytes) -> None:
    with zipfile.ZipFile(BytesIO(filled)) as archive:
        first = archive.infolist()[0]
    assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)


def test_title_is_month_only_and_class_stays_on_its_right_aligned_paragraph(filled: bytes) -> None:
    template, got = cells(TEMPLATE.read_bytes())[(0, 0)], cells(filled)[(0, 0)]
    assert lines(got) == ["3월 놀이계획안", CLASS]

    def style(tc: etree._Element) -> list[tuple[str, str]]:
        return [
            (p.get("paraPrIDRef"), p.find("hp:run", NS).get("charPrIDRef"))
            for p in tc.iterfind("hp:subList/hp:p", NS)
        ]

    assert style(got) == style(template) == [("19", "21"), ("37", "20")]
    assert "2027" not in "".join(got.itertext())


def test_values_land_in_their_cells(filled: bytes) -> None:
    got = cells(filled)
    assert lines(got[(1, 2)]) == lines(got[(5, 7)]) == ["합성 주제"]
    assert lines(got[(2, 2)]) == ["2027.03.01 ~ 2027.03.31"]
    assert lines(got[(3, 2)]) == ["합성 이유"]
    assert lines(got[(6, 0)]) == [f"함께 놀이 {i}" for i in range(1, 6)]
    assert lines(got[(6, 12)]) == [f"자유 놀이 {i}" for i in range(1, 6)]
    for address, value in {
        (11, 3): "합성 훈련",
        (12, 3): "[건강] 합성 건강",
        (12, 11): "",
        (24, 3): "합성 생일",
        (25, 3): "합성 가정연계",
    }.items():
        assert lines(got[address]) == [value]
    assert [lines(tc) for tc in week_row(filled, 8)] == [[f"{i}주"] for i in range(1, 6)]
    assert [lines(tc) for tc in week_row(filled, 9)] == [
        ["습관 1"],
        *(["[청결]", f"습관 {i}"] for i in range(2, 6)),
    ]
    assert [lines(tc) for tc in week_row(filled, 10)] == [
        [f"안전 {i}" if i % 2 else ""] for i in range(1, 6)
    ]


def test_footer_timetables_and_labels_stay_as_the_template(filled: bytes) -> None:
    template, got = cells(TEMPLATE.read_bytes()), cells(filled)
    assert lines(got[(27, 0)]) == FOOTER
    for row in (*range(14, 24), 26, 27):
        for address in [a for a in template if a[0] == row]:
            assert lines(got[address]) == lines(template[address])
    assert all(not "".join(got[a].itertext()) for a in template if a[0] in (15, 16, 20, 21))


def test_five_weeks_keep_the_template_grid(filled: bytes) -> None:
    def shape(content: bytes) -> list[tuple]:
        return [
            (
                tc.find("hp:cellAddr", NS).attrib,
                tc.find("hp:cellSpan", NS).attrib,
                tc.find("hp:cellSz", NS).get("width"),
                tc.get("borderFillIDRef"),
            )
            for tc in table(content).iterfind("hp:tr/hp:tc", NS)
        ]

    assert shape(filled) == shape(TEMPLATE.read_bytes())
    assert table(filled).get("colCnt") == "17"


def test_a_four_week_month_gets_four_equal_columns_in_the_first_four_colors() -> None:
    content = fill_play_monthly(TEMPLATE.read_bytes(), document(4), CLASS)

    assert_whole_grid(content)
    for row in (8, 9, 10):
        got, template = week_row(content, row), week_row(TEMPLATE.read_bytes(), row)
        assert [int(tc.find("hp:cellSz", NS).get("width")) for tc in got] == [10495] * 4
        fills = [tc.get("borderFillIDRef") for tc in got]
        assert fills == [tc.get("borderFillIDRef") for tc in template[:4]]
    assert [lines(tc) for tc in week_row(content, 8)] == [[f"{i}주"] for i in range(1, 5)]
    assert [lines(tc) for tc in week_row(content, 10)] == [["안전 1"], [""], ["안전 3"], [""]]
    assert len(table(content).findall("hp:tr/hp:tc", NS)) == 74


@pytest.mark.parametrize("weeks", [3, 6])
def test_a_week_count_outside_the_core_rule_is_refused(weeks: int) -> None:
    with pytest.raises(TemplateMismatch):
        fill_play_monthly(TEMPLATE.read_bytes(), document(weeks), CLASS)


def test_every_play_row_is_printed_without_truncation() -> None:
    content = fill_play_monthly(TEMPLATE.read_bytes(), document(plays=12), CLASS)
    got, template = cells(content), cells(TEMPLATE.read_bytes())

    for address, name in (((6, 0), "함께"), ((6, 12), "자유")):
        paragraphs = got[address].findall("hp:subList/hp:p", NS)
        texts = ["".join(p.itertext()) for p in paragraphs]
        assert texts == [f"{name} 놀이 {i}" for i in range(1, 13)]
        # 번호 · 글머리는 양식 문단 모양이 단다.
        expected = template[address].find("hp:subList/hp:p", NS).get("paraPrIDRef")
        assert {p.get("paraPrIDRef") for p in paragraphs} == {expected}


def test_filled_paragraphs_drop_the_line_layout_cache(filled: bytes) -> None:
    got = cells(filled)
    for address in [(0, 0), (1, 2), (6, 0), (11, 3), (25, 3)]:
        assert got[address].find(".//hp:linesegarray", NS) is None


def test_preview_lists_the_values_not_the_placeholders(filled: bytes) -> None:
    with zipfile.ZipFile(BytesIO(filled)) as archive:
        preview = archive.read("Preview/PrvText.txt").decode()
    assert preview.startswith(f"<3월 놀이계획안 {CLASS}>")
    assert "X월" not in preview and "XX반" not in preview


def test_another_template_is_refused() -> None:
    with pytest.raises(TemplateMismatch):
        fill_play_monthly(PLAY_PROJECT_TEMPLATE.read_bytes(), document(), CLASS)


def test_the_filled_hwpx_converts_to_hwp(filled: bytes) -> None:
    assert to_hwp(filled)


def test_the_table_may_break_across_pages(filled: bytes) -> None:
    # 전달본은 「글자처럼 취급」이라 긴 내용이 1쪽 아래에서 잘린다 — 채울 때 끈다.
    assert table(TEMPLATE.read_bytes()).find("hp:pos", NS).get("treatAsChar") == "1"
    found = table(filled)
    assert found.find("hp:pos", NS).get("treatAsChar") == "0"
    assert found.getparent().getparent().find("hp:linesegarray", NS) is None
