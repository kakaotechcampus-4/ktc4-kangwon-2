"""월간 v2 양식(`plans/templates/play_monthly.hwpx`)과 채우기.

쪽 나눔 · 글꼴 · 겹침은 한글에서 사람이 봐야 안다. 여기서 걸러지는 것들은 열기 전에 다 틀린 것이다.
"""

import zipfile
from dataclasses import replace
from io import BytesIO

import pytest
from lxml import etree
from ssuksak.planning.application.generate_play_monthly_plan import SPECIAL_ACTIVITY_START
from ssuksak.planning.application.play_monthly_document import (
    PlayMonthlyDocument,
    PlayMonthlyDocumentPart,
    PlayMonthlyDocumentWeek,
)
from ssuksak.planning.domain.play_monthly_plan import TimetableSize
from ssuksak.planning.domain.provenance import SplitAxis

from app.features.plans.play_monthly_hwpx import HWPUNIT_PER_MM, TEMPLATE, fill_play_monthly
from app.features.plans.play_project_hwpx import TEMPLATE as PLAY_PROJECT_TEMPLATE
from app.shared.hwpx import NS, TemplateMismatch, to_hwp

CLASS = "만 3·4세 햇살반"
FOOTER = [
    "*예상 놀이 방향은 [2019 개정 누리과정]의 목적에 따라 ‘유아 놀이 중심’ 활동이 진행 될 수 있도록"
    " 융통성 있게 구성되었습니다. ",  # 전달본 그대로 — 끝 공백까지
    "*유아들의 흥미도와 참여 정도에 따라 다른 방향으로 조정됩니다.",
]


V, H = SplitAxis.VERTICAL, SplitAxis.HORIZONTAL


def parts(shape, texts) -> PlayMonthlyDocumentPart:
    """Core 시작 모양 표기(None = 칸, (축, 비율, 첫째, 둘째) = 경계) → 문서 칸.

    글은 차례로 붙인다.
    """
    if shape is None:
        return PlayMonthlyDocumentPart(next(texts))
    axis, ratio, first, second = shape
    return PlayMonthlyDocumentPart(
        axis=axis, ratio=ratio, parts=(parts(first, texts), parts(second, texts))
    )


def days(*shapes) -> tuple[PlayMonthlyDocumentPart, ...]:
    texts = iter(f"특활 {i}" for i in range(1, 100))
    return tuple(parts(shape, texts) for shape in shapes)


def document(weeks: int = 5, plays: int = 5) -> PlayMonthlyDocument:
    return PlayMonthlyDocument(
        title="3월 놀이계획안",
        age="만 3·4세",
        class_name="햇살반",
        period="2027.03.01 ~ 2027.03.31",
        theme="합성 주제",
        direction="합성 놀이 방향",
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
        specialized_titles=tuple(f"특성화 {i}" for i in range(1, 6)),
        specialized_contents=("합성 내용", "", "", "", ""),
        special_activity=days(*SPECIAL_ACTIVITY_START),
        special_activity_size=TimetableSize((20, 20, 20, 20, 20), 24),
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
        address = (int(addr.get("rowAddr")), int(addr.get("colAddr")))
        assert address not in out, f"같은 주소 칸 두 개 {address}"
        out[address] = tc
    return out


def lines(tc: etree._Element) -> list[str]:
    return ["".join(p.itertext()) for p in tc.iterfind("hp:subList/hp:p", NS)]


def week_row(content: bytes, row: int) -> list[etree._Element]:
    return sorted(
        (tc for (r, c), tc in cells(content).items() if r == row and c > 0),
        key=lambda tc: int(tc.find("hp:cellAddr", NS).get("colAddr")),
    )


def x_span(tc: etree._Element, content: bytes) -> tuple[int, int]:
    """칸의 왼쪽 · 오른쪽 세로선 x — 격자 번호가 바뀌어도 비교할 수 있다."""
    x = {0: 0}
    tcs = list(table(content).iterfind("hp:tr/hp:tc", NS))
    for _ in tcs:
        for other in tcs:
            c = int(other.find("hp:cellAddr", NS).get("colAddr"))
            if c in x:
                end = c + int(other.find("hp:cellSpan", NS).get("colSpan"))
                x[end] = x[c] + int(other.find("hp:cellSz", NS).get("width"))
    c = int(tc.find("hp:cellAddr", NS).get("colAddr"))
    return x[c], x[c + int(tc.find("hp:cellSpan", NS).get("colSpan"))]


def special_cells(content: bytes) -> list[etree._Element]:
    """특별활동 칸 구역(요일 머리 아래 행들) — 위 → 아래, 왼쪽 → 오른쪽."""
    rows = int(table(content).get("rowCnt")) - 28 + 2  # 전달본 칸 구역은 2행
    return sorted(
        (tc for (r, c), tc in cells(content).items() if 20 <= r < 20 + rows),
        key=lambda tc: (
            int(tc.find("hp:cellAddr", NS).get("rowAddr")),
            int(tc.find("hp:cellAddr", NS).get("colAddr")),
        ),
    )


def text(tc: etree._Element) -> str:
    return "".join(tc.itertext())


def size(tc: etree._Element) -> tuple[int, int]:
    found = tc.find("hp:cellSz", NS)
    return int(found.get("width")), int(found.get("height"))


def assert_whole_grid(content: bytes) -> None:
    """병합을 펼친 격자의 칸마다 정확히 한 셀, 같은 세로선은 어느 줄에서나 같은 x."""
    found = table(content)
    rows, cols = int(found.get("rowCnt")), int(found.get("colCnt"))
    covered, spans = [], []
    for tc in found.iterfind("hp:tr/hp:tc", NS):
        addr, span = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
        r, c = int(addr.get("rowAddr")), int(addr.get("colAddr"))
        rs, cs = int(span.get("rowSpan")), int(span.get("colSpan"))
        # 0 병합 칸은 펼치면 사라져 덮임 검사를 빠져나간다 — 크기 · 병합 수를 먼저 본다.
        assert min(rs, cs, *size(tc)) > 0, (r, c, rs, cs, size(tc))
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
    return fill_play_monthly(TEMPLATE.read_bytes(), document())


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


def test_the_class_line_is_the_age_alone_when_the_class_name_is_blank() -> None:
    content = fill_play_monthly(TEMPLATE.read_bytes(), replace(document(), class_name=""))
    assert lines(cells(content)[(0, 0)]) == ["3월 놀이계획안", "만 3·4세"]


def test_values_land_in_their_cells(filled: bytes) -> None:
    got = cells(filled)
    assert lines(got[(1, 2)]) == ["합성 주제"]
    assert lines(got[(5, 7)]) == ["합성 놀이 방향"]
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


def test_footer_and_labels_stay_as_the_template(filled: bytes) -> None:
    template, got = cells(TEMPLATE.read_bytes()), cells(filled)
    assert lines(got[(27, 0)]) == FOOTER
    for row in (14, 17, 18, 19, 22, 23, 26, 27):
        for address in [a for a in template if a[0] == row]:
            assert lines(got[address]) == lines(template[address])


def test_specialized_titles_and_contents_fill_the_template_cells(filled: bytes) -> None:
    got = cells(filled)
    columns = (0, 4, 8, 11, 14)
    assert [lines(got[(15, c)]) for c in columns] == [[f"특성화 {i}"] for i in range(1, 6)]
    assert [lines(got[(16, c)]) for c in columns] == [["합성 내용"], *[[""]] * 4]


def test_five_weeks_and_the_start_timetable_keep_the_template_grid(filled: bytes) -> None:
    """칸 구역(20~21행)은 Core 시작 모양(정수 비율)으로 다시 그려 폭 · 높이만 몇 단위 다르다."""

    def shape(content: bytes) -> list[tuple]:
        return [
            (
                tc.find("hp:cellAddr", NS).attrib,
                tc.find("hp:cellSpan", NS).attrib,
                *(() if r in (20, 21) else (size(tc)[0], tc.get("borderFillIDRef"))),
            )
            for tc in table(content).iterfind("hp:tr/hp:tc", NS)
            for r in [int(tc.find("hp:cellAddr", NS).get("rowAddr"))]
        ]

    assert shape(filled) == shape(TEMPLATE.read_bytes())
    assert table(filled).get("colCnt") == "17"
    template = special_cells(TEMPLATE.read_bytes())
    for got, want in zip(special_cells(filled), template, strict=True):
        assert all(abs(a - b) <= 30 for a, b in zip(size(got), size(want), strict=True))
    assert_whole_grid(filled)


def test_special_activity_parts_are_printed_where_the_tree_puts_them(filled: bytes) -> None:
    order = [1, 2, 5, 6, 7, 8, 11, 12, 13, 3, 4, 9, 10]  # 칸 주소 순서 — 월 · 수 아래 칸은 21행
    assert [lines(tc) for tc in special_cells(filled)] == [[f"특활 {i}"] for i in order]


def test_a_deeper_split_adds_rows_and_moves_the_rows_below() -> None:
    thursday = (V, 30, None, (V, 50, None, (H, 10, None, None)))
    shapes = (*SPECIAL_ACTIVITY_START[:3], thursday, SPECIAL_ACTIVITY_START[4])
    doc = replace(document(), special_activity=days(*shapes))
    content = fill_play_monthly(TEMPLATE.read_bytes(), doc)

    assert_whole_grid(content)
    assert table(content).get("rowCnt") == "30"  # 경계 높이 30 · 48 · 65 % → 칸 구역 2행 → 4행
    got = cells(content)
    assert lines(got[(26, 0)]) == ["우리반 생일"]
    assert lines(got[(27, 3)]) == ["합성 가정연계"]
    assert lines(got[(29, 0)]) == FOOTER
    found = sorted((text(tc) for tc in special_cells(content)), key=lambda t: int(t.split()[1]))
    assert found == [f"특활 {i}" for i in range(1, 17)]
    height = round(24 * HWPUNIT_PER_MM)
    first, second = round(height * 30 / 100), round(height * 65 / 100)
    thursday_cells = [tc for tc in special_cells(content) if text(tc) in {"특활 11", "특활 12"}]
    assert [size(tc)[1] for tc in thursday_cells] == [first, second - first]


@pytest.mark.parametrize("axis", [V, H])
def test_splitting_the_small_part_again_and_again_keeps_every_cell_positive(axis) -> None:
    """작은 첫 갈래를 10%로 깊이 4까지 — 정수 나눗셈이면 경계가 겹쳐 0 크기 · 0 병합 칸이 나온다."""
    small = (axis, 10, (axis, 10, (axis, 10, (axis, 10, None, None), None), None), None)
    shapes = (*SPECIAL_ACTIVITY_START[:3], small, SPECIAL_ACTIVITY_START[4])
    doc = replace(
        document(),
        special_activity=days(*shapes),
        special_activity_size=TimetableSize((20, 20, 20, 5, 35), 16),
    )
    content = fill_play_monthly(TEMPLATE.read_bytes(), doc)

    assert_whole_grid(content)  # 모든 칸 폭 · 높이 · 병합 수 > 0
    raw = table(content).findall("hp:tr/hp:tc", NS)
    assert len(raw) == len(cells(content)) == 77 - 13 + 17  # 주소 중복 없음, 칸 구역 13 → 17칸
    found = sorted((text(tc) for tc in special_cells(content)), key=lambda t: int(t.split()[1]))
    assert found == [f"특활 {i}" for i in range(1, 18)]


def test_column_widths_and_height_are_drawn() -> None:
    widths = (30, 10, 20, 25, 15)
    doc = replace(document(), special_activity_size=TimetableSize(widths, 40))
    content = fill_play_monthly(TEMPLATE.read_bytes(), doc)

    assert_whole_grid(content)
    header = sorted(
        (tc for (r, c), tc in cells(content).items() if r == 19),
        key=lambda tc: int(tc.find("hp:cellAddr", NS).get("colAddr")),
    )
    total = int(table(content).find("hp:sz", NS).get("width"))
    got = [x1 - x0 for x0, x1 in (x_span(tc, content) for tc in header)]
    assert all(abs(g - total * w // 100) <= 30 for g, w in zip(got, widths, strict=True))
    thursday = next(tc for tc in special_cells(content) if text(tc) == "특활 11")
    assert size(thursday)[1] == round(40 * HWPUNIT_PER_MM)
    assert x_span(thursday, content) == x_span(header[3], content)


def test_a_wrong_number_of_special_activity_days_is_refused() -> None:
    doc = replace(document(), special_activity=document().special_activity[:4])
    with pytest.raises(TemplateMismatch):
        fill_play_monthly(TEMPLATE.read_bytes(), doc)


def test_a_four_week_month_gets_four_equal_columns_in_the_first_four_colors() -> None:
    content = fill_play_monthly(TEMPLATE.read_bytes(), document(4))

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
        fill_play_monthly(TEMPLATE.read_bytes(), document(weeks))


def test_every_play_row_is_printed_without_truncation() -> None:
    content = fill_play_monthly(TEMPLATE.read_bytes(), document(plays=12))
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
        fill_play_monthly(PLAY_PROJECT_TEMPLATE.read_bytes(), document())


def test_the_filled_hwpx_converts_to_hwp(filled: bytes) -> None:
    assert to_hwp(filled)


def test_the_table_may_break_across_pages(filled: bytes) -> None:
    # 전달본은 「글자처럼 취급」이라 긴 내용이 1쪽 아래에서 잘린다 — 채울 때 끈다.
    assert table(TEMPLATE.read_bytes()).find("hp:pos", NS).get("treatAsChar") == "1"
    found = table(filled)
    assert found.find("hp:pos", NS).get("treatAsChar") == "0"
    assert found.getparent().getparent().find("hp:linesegarray", NS) is None
