"""Draw the chosen weekly activity leaves on the agreed day form."""

import copy
import io
import zipfile
from fractions import Fraction

from lxml import etree
from ssuksak.planning.application.play_monthly_document import PlayMonthlyDocumentPart

from app.features.plans.play_monthly_hwpx import _grid, _grid_lines, _layout, _renumber_columns
from app.features.plans.play_project_hwpx import _preview
from app.shared.hwpx import NS, PREVIEW, SECTION, TemplateMismatch, _cells, _dump, _set_text


def fill_weekly_activity_grid(content, plan):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    section = etree.fromstring(parts[SECTION])
    table = section.find(".//hp:tbl", NS)
    rows = [] if table is None else table.findall("hp:tr", NS)
    if len(rows) <= 11:
        raise TemplateMismatch("주간 양식에 대소집단 활동 줄이 없다.")
    body = rows[11]
    models = body.findall("hp:tc", NS)
    if not models or "".join(t.text or "" for t in models[0].iter(f"{{{NS['hp']}}}t")) != "활동":
        raise TemplateMismatch("주간 양식의 대소집단 활동 줄이 맞지 않는다.")
    cells = _cells(table)
    physical = _grid_lines(table, list(cells.values()))
    spans = {
        tc: (physical[col], physical[col] + int(tc.find("hp:cellSz", NS).get("width")))
        for (_, col), tc in cells.items()
    }
    label = copy.deepcopy(models[0])
    label_span = spans[models[0]]
    height = int(models[0].find("hp:cellSz", NS).get("height"))
    leaves = []

    def part(node):
        if node.cell is not None:
            return PlayMonthlyDocumentPart(text=plan.find_cell(node.cell).value)
        return PlayMonthlyDocumentPart(
            axis=node.axis, ratio=node.ratio, parts=tuple(part(c) for c in node.children)
        )

    for node, model in zip(plan.activity_grids, models[1:], strict=True):
        shapes = _layout(part(node), Fraction(0), Fraction(1), Fraction(0), Fraction(1))
        x0, x1 = spans[model]
        xs = _grid([x for _, a, b, *_ in shapes for x in (a, b)], x0, x1)
        leaves.extend((text, xs[a], xs[b], y0, y1) for text, a, b, y0, y1 in shapes)
    ys = _grid([y for *_, a, b in leaves for y in (a, b)], 0, height)
    indices = {y: i for i, y in enumerate(sorted(ys.values()))}
    new_rows = [etree.Element(body.tag, body.attrib) for _ in range(len(ys) - 1)]
    label.find("hp:cellSpan", NS).set("rowSpan", str(len(new_rows)))
    new_rows[0].append(label)
    for model in models:
        del spans[model]
    spans[label] = label_span
    for text, x0, x1, y0, y1 in leaves:
        y0, y1 = ys[y0], ys[y1]
        tc = copy.deepcopy(models[1])
        tc.find("hp:cellSz", NS).attrib.update({"width": str(x1 - x0), "height": str(y1 - y0)})
        tc.find("hp:cellSpan", NS).set("rowSpan", str(indices[y1] - indices[y0]))
        _set_text(tc, text)
        new_rows[indices[y0]].append(tc)
        spans[tc] = (x0, x1)
    at = list(table).index(body)
    table.remove(body)
    for i, row in enumerate(new_rows):
        for tc in sorted(list(row), key=lambda c: spans[c][0]):
            row.remove(tc)
            row.append(tc)
        table.insert(at + i, row)
    rows = table.findall("hp:tr", NS)
    for row_no, row in enumerate(rows):
        for tc in row.findall("hp:tc", NS):
            tc.find("hp:cellAddr", NS).set("rowAddr", str(row_no))
    table.set("rowCnt", str(len(rows)))
    _renumber_columns(table, spans)
    parts[SECTION], parts[PREVIEW] = _dump(section), _preview(section)
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for info in infos:
            archive.writestr(info, parts[info.filename], compress_type=info.compress_type)
    return result.getvalue()
