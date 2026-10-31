"""연간 v1: 좌우 6개월, canonical 주차만큼 소주제 칸을 나눈다."""

import copy
from collections.abc import Sequence
from typing import NamedTuple

from lxml import etree
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

from app.shared.hwpx import HP, NS, TemplateMismatch, _cells, _rewrite, _set_text


class AnnualMonthRows(NamedTuple):
    month: int
    theme: str
    subthemes: Sequence[str]


def fill_annual_v1(
    template: bytes, title: str, school_year: int, months: Sequence[AnnualMonthRows]
) -> bytes:
    if [month.month for month in months] != [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]:
        raise ValueError("연간은 3월부터 다음 해 2월까지 순서대로 12개월이어야 합니다")
    counts = [
        len(
            canonical_week_periods(
                YearMonth(school_year if m.month >= 3 else school_year + 1, m.month)
            )
        )
        for m in months
    ]
    height = max(sum(counts[:6]), sum(counts[6:]))

    def fill(table):
        original = _cells(table)
        if int(table.get("colCnt")) != 8 or any((0, col) not in original for col in range(8)):
            raise TemplateMismatch("연간 주차 양식은 좌우 4열씩이어야 합니다")
        samples = [copy.deepcopy(original[(0, col)]) for col in range(8)]
        body = [copy.deepcopy(original[(1, col)]) for col in range(4)]
        widths = [int(cell.find("hp:cellSz", NS).get("width")) for cell in samples]
        row_height = min(2500, 65000 // height)
        header_height = 3000
        for row in table.findall("hp:tr", NS):
            table.remove(row)
        rows = [etree.SubElement(table, f"{{{HP}}}tr") for _ in range(height + 1)]

        def cell(row, col, text, *, span=1, cols=1, header=False):
            tc = copy.deepcopy(samples[col] if header else body[col % 4])
            tc.set("header", "1" if header else "0")
            tc.find("hp:cellAddr", NS).attrib.update({"rowAddr": str(row), "colAddr": str(col)})
            tc.find("hp:cellSpan", NS).attrib.update({"rowSpan": str(span), "colSpan": str(cols)})
            tc.find("hp:cellSz", NS).attrib.update(
                {
                    "width": str(sum(widths[col : col + cols])),
                    "height": str(header_height if header else row_height * span),
                }
            )
            _set_text(tc, text)
            rows[row].append(tc)

        for col, text in enumerate(["월", "생활주제", "주", "소주제"] * 2):
            cell(0, col, text, header=True)
        for start in (0, 6):
            row, col = 1, 0 if start == 0 else 4
            for month, count in zip(
                months[start : start + 6], counts[start : start + 6], strict=True
            ):
                cell(row, col, f"{month.month}월", span=count)
                cell(row, col + 1, month.theme, span=count)
                for index in range(count):
                    # Old plans may have five monthly topics in a four-week month: preserve all.
                    value = (
                        "\n".join(month.subthemes[index:])
                        if index == count - 1
                        else (month.subthemes[index] if index < len(month.subthemes) else "")
                    )
                    cell(row + index, col + 2, str(index + 1))
                    cell(row + index, col + 3, value)
                row += count
            if row <= height:
                cell(row, col, "", span=height + 1 - row, cols=4)
        for row in rows:
            row[:] = sorted(row, key=lambda tc: int(tc.find("hp:cellAddr", NS).get("colAddr")))
        table.set("rowCnt", str(height + 1))
        table.find("hp:sz", NS).set("height", str(header_height + row_height * height))
        # A long teacher value must flow to the next page rather than be clipped.
        table.find("hp:pos", NS).set("treatAsChar", "0")

    return _rewrite(template, title, fill)
