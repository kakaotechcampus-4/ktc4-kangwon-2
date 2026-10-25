"""놀이 프로젝트형 연간 양식(`plans/templates/play_project_annual.hwpx`)과 채우기(ADR-042).

양식은 `scripts/build_play_project_template.py` 가 만든다. 쪽 나눔 · 글자 잘림은 한글에서
사람이 봐야 알지만, 여기서 걸러지는 것들은 열기 전에 다 틀린 것이다.
"""

import zipfile
from io import BytesIO

import pytest
from lxml import etree

from app.features.plans.play_project_hwpx import (
    TEMPLATE,
    PlayPeriodRows,
    PlayRow,
    fill_play_project,
)
from app.shared.hwpx import NS, TemplateMismatch, to_hwp

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
TITLE = "2026 연간놀이계획안 - 만4세 예시반"
LABELS = ["3~5월\n봄", "6~8월\n여름", "9~11월\n가을", "12~2월\n겨울"]
LEARNING_2 = [
    ("신체운동·건강", "신체활동 즐기기", "신체 움직임을 조절한다."),
    ("예술경험", "창의적으로 표현하기", "움직임과 춤으로 표현한다."),
]
LEARNING_3 = [
    *LEARNING_2,
    ("자연탐구", "자연과 더불어 살기", "날씨와 계절의 변화를 생활과 관련짓는다."),
]


def periods(rows_per_period: int = 5) -> list[PlayPeriodRows]:
    # 배움은 2개 · 3개를 섞는다 — 계약은 2~3개다.
    return [
        PlayPeriodRows(
            label,
            [
                PlayRow(
                    f"놀이 {p}-{r}",
                    f"재료 {p}-{r}",
                    f"지원 방향 {p}-{r}",
                    LEARNING_3 if (p + r) % 2 else LEARNING_2,
                )
                for r in range(rows_per_period)
            ],
        )
        for p, label in enumerate(LABELS)
    ]


def parts(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def tables(content: bytes) -> list[etree._Element]:
    return etree.fromstring(parts(content)["Contents/section0.xml"]).findall(".//hp:tbl", NS)


def bold_chars(content: bytes) -> set[str]:
    header = etree.fromstring(parts(content)["Contents/header.xml"])
    return {c.get("id") for c in header.iter(f"{HH}charPr") if c.find(f"{HH}bold") is not None}


def cell(table: etree._Element, row: int, col: int) -> etree._Element:
    for tc in table.iterfind("hp:tr/hp:tc", NS):
        addr = tc.find("hp:cellAddr", NS)
        if (int(addr.get("rowAddr")), int(addr.get("colAddr"))) == (row, col):
            return tc
    raise AssertionError((row, col))


def paragraphs(tc: etree._Element) -> list[list[tuple[str, str]]]:
    """칸의 문단마다 (글자 모양 id, 글자) run 목록."""
    return [
        [(run.get("charPrIDRef"), "".join(run.itertext())) for run in p.iterfind("hp:run", NS)]
        for p in tc.iterfind("hp:subList/hp:p", NS)
    ]


@pytest.fixture(scope="module")
def filled() -> bytes:
    return fill_play_project(TEMPLATE.read_bytes(), TITLE, periods())


def test_template_is_blank_two_tables_with_merged_periods() -> None:
    template = TEMPLATE.read_bytes()
    found = tables(template)
    assert len(found) == 2
    for table in found:
        assert (table.get("rowCnt"), table.get("colCnt"), table.get("repeatHeader")) == (
            "11",
            "5",
            "1",
        )
        # 병합을 펼친 11 × 5 격자의 칸마다 정확히 한 셀
        covered = []
        for tc in table.iterfind("hp:tr/hp:tc", NS):
            addr, span = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
            r, c = int(addr.get("rowAddr")), int(addr.get("colAddr"))
            covered += [
                (r + i, c + j)
                for i in range(int(span.get("rowSpan")))
                for j in range(int(span.get("colSpan")))
            ]
        assert sorted(covered) == [(r, c) for r in range(11) for c in range(5)]
        body = [tc for tc in table.iterfind("hp:tr/hp:tc", NS) if tc.get("header") == "0"]
        assert len(body) == 42  # 시기 2 + 10줄 × 4
        assert all(not "".join(tc.itertext()).strip() for tc in body)
    files = parts(template)
    assert files["Contents/section0.xml"].decode().count("<hp:t>제목</hp:t>") == 2
    package = etree.fromstring(files["Contents/content.hpf"])
    metas = {m.get("name"): m.text for m in package.iterfind(".//opf:meta", NS)}
    assert not metas.get("creator") and not metas.get("lastsaveby")
    assert not package.find(".//opf:title", NS).text


def test_mimetype_is_stored_first(filled: bytes) -> None:
    with zipfile.ZipFile(BytesIO(filled)) as archive:
        first = archive.infolist()[0]
    assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)


def test_every_selected_play_lands_in_its_period_and_row(filled: bytes) -> None:
    first, second = tables(filled)
    for p, period in enumerate(periods()):
        table = first if p < 2 else second
        top = 1 + (p % 2) * 5
        assert [text for para in paragraphs(cell(table, top, 0)) for _, text in para] == (
            period.label.split("\n")
        )
        for r, row in enumerate(period.rows, start=top):
            for col, value in enumerate((row.play_name, row.materials, row.support_direction), 1):
                assert "".join(cell(table, r, col).itertext()) == value


def test_learning_lines_bold_only_the_domain(filled: bytes) -> None:
    bold = bold_chars(filled)
    lines = 0
    for p, period in enumerate(periods()):
        table = tables(filled)[p // 2]
        for r, row in enumerate(period.rows, start=1 + (p % 2) * 5):
            got = paragraphs(cell(table, r, 4))
            assert len(got) == len(row.learning)  # 2개 · 3개 그대로
            for para, (domain, category, content) in zip(got, row.learning, strict=True):
                (head_char, head), (rest_char, rest) = para
                assert (head, rest) == (f"[{domain}]", f" {category} - {content}")
                assert head_char in bold and rest_char not in bold
                lines += 1
    assert lines == sum(len(row.learning) for period in periods() for row in period.rows)


def test_titles_preview_and_metadata(filled: bytes) -> None:
    files = parts(filled)
    section = files["Contents/section0.xml"].decode()
    assert section.count(TITLE) == 2 and "<hp:t>제목</hp:t>" not in section
    preview = files["Preview/PrvText.txt"].decode()
    assert preview.count(TITLE) == 2
    assert all(f"<놀이 {p}-{r}>" in preview for p in range(4) for r in range(5))
    # 배움 줄은 run 을 붙여 잇고 줄 사이만 띄운다
    assert "<[신체운동·건강] 신체활동 즐기기 - 신체 움직임을 조절한다. [예술경험] 창의" in preview
    package = etree.fromstring(files["Contents/content.hpf"])
    metas = {m.get("name"): m.text for m in package.iterfind(".//opf:meta", NS)}
    assert not metas.get("creator") and not metas.get("lastsaveby")


def test_changed_paragraphs_drop_the_line_layout_cache(filled: bytes) -> None:
    for table in tables(filled):
        for tc in table.iterfind("hp:tr/hp:tc", NS):
            if tc.get("header") == "0":
                assert tc.find(".//hp:linesegarray", NS) is None


@pytest.mark.parametrize(
    "bad",
    [periods()[:3], [*periods()[:3], periods(4)[3]]],
    ids=["three-periods", "four-plays"],
)
def test_wrong_shape_is_refused(bad: list[PlayPeriodRows]) -> None:
    with pytest.raises(TemplateMismatch):
        fill_play_project(TEMPLATE.read_bytes(), TITLE, bad)


def test_empty_learning_is_refused() -> None:
    bad = periods()
    bad[0].rows[0] = bad[0].rows[0]._replace(learning=[])
    with pytest.raises(ValueError, match="배움"):
        fill_play_project(TEMPLATE.read_bytes(), TITLE, bad)


def test_converts_to_hwp(filled: bytes) -> None:
    """ADR-039 — `.hwp` 도 같은 hwpx 에서 바꿔 만든다."""
    assert to_hwp(filled)[:8] == bytes.fromhex("d0cf11e0a1b11ae1")
