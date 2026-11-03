import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

from app.features.plans.annual_hwpx import AnnualMonthRows, fill_annual_v1
from app.shared.hwpx import NS

TEMPLATE = (
    Path(__file__).parents[1] / "app/features/plans/templates/annual_v1_weeks.hwpx"
).read_bytes()
MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


@pytest.mark.parametrize(
    "name,titles", [("annual_v1_weeks.hwpx", 1), ("play_project_annual.hwpx", 2)]
)
def test_annual_templates_use_blue_titles_and_black_table_borders(name, titles):
    directory = Path(__file__).parents[1] / "app/features/plans/templates"
    with zipfile.ZipFile(directory / name) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    ns = {
        **NS,
        "hh": "http://www.hancom.co.kr/hwpml/2011/head",
        "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    }
    margin = section.find(".//hp:pagePr/hp:margin", NS)
    expected_bottom = "4884" if name == "annual_v1_weeks.hwpx" else "1784"
    assert (margin.get("bottom"), margin.get("footer")) == (expected_bottom, "1417")
    fills = {b.get("id"): b for b in header.findall(".//hh:borderFill", ns)}
    title_paragraphs = [
        p for p in section.findall("hp:p", NS) if any(t.text for t in p.findall("hp:run/hp:t", NS))
    ]
    assert len(title_paragraphs) == titles
    for p in title_paragraphs:
        para = header.find(f".//hh:paraPr[@id='{p.get('paraPrIDRef')}']", ns)
        band = fills[para.find("hh:border", ns).get("borderFillIDRef")]
        brush = band.find("hc:fillBrush/hc:winBrush", ns)
        assert brush.get("faceColor") == "#E1F2FE" and brush.get("hatchStyle") == "CROSS"
    for table in section.findall(".//hp:tbl", NS):
        for tc in table.findall("hp:tr/hp:tc", NS):
            fill = fills[tc.get("borderFillIDRef")]
            for edge in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
                line = fill.find(f"hh:{edge}", ns)
                if line is not None and line.get("type") != "NONE":
                    assert line.get("color") == "#000000"
        for tc in table.find("hp:tr", NS).findall("hp:tc", NS):
            brush = fills[tc.get("borderFillIDRef")].find("hc:fillBrush/hc:winBrush", ns)
            assert brush.get("faceColor") == "#E1F2FE"


@pytest.mark.parametrize("year", [2025, 2026, 2027, 2028, 2032])
def test_each_canonical_week_is_covered_once_in_both_halves(year):
    data = [
        AnnualMonthRows(m, f"월 주제 {m}", [f"{m}월 소주제 {i}" for i in range(1, 6)])
        for m in MONTHS
    ]
    output = fill_annual_v1(TEMPLATE, "연간계획안 검증", year, data)
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        assert archive.testzip() is None
        assert (
            archive.infolist()[0].filename == "mimetype"
            and archive.infolist()[0].compress_type == 0
        )
        section = etree.fromstring(archive.read("Contents/section0.xml"))
        preview = archive.read("Preview/PrvText.txt").decode()
    table = section.find(".//hp:tbl", NS)
    rows = int(table.get("rowCnt"))
    grid = set()
    week_counts = []
    for tc in table.findall("hp:tr/hp:tc", NS):
        addr, span, size = [
            tc.find(f"hp:{name}", NS) for name in ("cellAddr", "cellSpan", "cellSz")
        ]
        r, c, rs, cs = (
            int(addr.get("rowAddr")),
            int(addr.get("colAddr")),
            int(span.get("rowSpan")),
            int(span.get("colSpan")),
        )
        assert min(int(size.get("width")), int(size.get("height")), rs, cs) > 0
        for rr in range(r, r + rs):
            for cc in range(c, c + cs):
                assert (rr, cc) not in grid
                grid.add((rr, cc))
        if r and c in (0, 4) and cs == 1:
            month = int("".join(tc.itertext()).strip().removesuffix("월"))
            week_counts.append((month, rs))
    assert grid == {(r, c) for r in range(rows) for c in range(8)}
    for month, span in week_counts:
        assert span == len(
            canonical_week_periods(YearMonth(year if month >= 3 else year + 1, month))
        )
    text = "\n".join(t.text or "" for t in section.findall(".//hp:t", NS))
    for month in data:
        for topic in month.subthemes:
            assert topic in text and topic in preview
    assert "※" not in text
    assert table.find("hp:pos", NS).get("treatAsChar") == "0"
    with zipfile.ZipFile(
        Path(__file__).parents[1] / "app/features/plans/templates/play_monthly.hwpx"
    ) as archive:
        monthly = etree.fromstring(archive.read("Contents/section0.xml"))
    footer = section.find(".//hp:footer", NS)
    assert footer is not None and footer.get("applyPageType") == "BOTH"
    assert (
        footer.xpath(".//hp:t/text()", namespaces=NS)
        == monthly.xpath("//hp:t/text()", namespaces=NS)[-2:]
    )


def test_template_keeps_nanum_gothic_and_nine_point_body():
    with zipfile.ZipFile(io.BytesIO(TEMPLATE)) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    hh = {"hh": "http://www.hancom.co.kr/hwpml/2011/head"}
    assert {f.get("face") for f in header.findall(".//hh:font", hh)} <= {
        "나눔고딕",
        "나눔고딕 Bold",
    }
    chars = {c.get("id"): c for c in header.findall(".//hh:charPr", hh)}
    for tc in section.findall(".//hp:tbl/hp:tr", NS)[1].findall("hp:tc", NS):
        run = tc.find("hp:subList/hp:p/hp:run", NS)
        assert chars[run.get("charPrIDRef")].get("height") == "900"


def test_product_export_route_uses_the_week_cell_template(monkeypatch):
    from types import SimpleNamespace

    from app.features.plans import export

    row = SimpleNamespace(id=1, status="CONFIRMED", plan_ref="annual_test", body={})
    plan = SimpleNamespace(
        class_id=1,
        school_year=2026,
        months=[
            SimpleNamespace(month=m, theme=f"월별 주제 {m}", sub_themes=["교사 수정값"])
            for m in MONTHS
        ],
    )
    monkeypatch.setattr(export, "_row", lambda *args: row)
    monkeypatch.setattr(export, "_repo", lambda *args: SimpleNamespace(get=lambda _: None))
    monkeypatch.setattr(export, "_detail", lambda *args: plan)
    monkeypatch.setattr(export, "require_own_class", lambda *args: SimpleNamespace(name="예시반"))
    response = export.export_plan(1, None, None, format="hwpx")
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    assert section.find(".//hp:tbl", NS).get("colCnt") == "8"
    assert "교사 수정값" in "".join(section.itertext())
