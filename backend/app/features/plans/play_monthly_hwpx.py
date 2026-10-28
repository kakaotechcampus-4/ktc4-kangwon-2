"""월간 v2(PLAY_MONTHLY) hwpx — Core 문서 값을 양식 `play_monthly.hwpx` 에 채운다.

양식은 하민이 확인한 전달본(2026-10-28) 그대로다. 큰 표 하나(28행 · 내부 격자 17열)에
제목 · 반 표시까지 들어 있어 공용 `hwpx.fill_table` 의 표 밖 「제목」 자리가 없다. 그래서 여기서
따로 채운다. 칸 주소는 전달본의 주소이며, 주차 줄만 실제 주 수로 다시 나눈다.

- 주차: 4주인 달은 4칸, 5주인 달은 5칸(2026-10-28 하민 결정). 주차 줄(머리 · 기본생활습관 ·
  안전교육)을 같은 폭으로 나누고, 바뀐 세로선에 맞춰 표 격자 번호를 다시 매긴다. 칸 서식은
  같은 자리의 양식 칸을 따른다(4주면 1~4주 색). Core 규칙 밖의 주 수는 버리지 않고 거절한다.
- 놀이 목록: 행 수대로 문단을 만든다. 번호 · 글머리는 양식 문단 모양이 단다. 자르지 않는다.
- 표시(2026-10-28 하민 결정, 3월 검증 사례와 같게): 예상 기간 「2026.03.01 ~ 2026.03.31」,
  기본생활습관은 「[분류]」 문단 + 문장 문단, 건강 · 영양은 「[건강] 」 · 「[영양] 」 + 문장.
  빈 칸에는 붙이지 않는다.
- 비워 두는 곳: 우리반 안내사항(출력 안 함, 2026-10-28 결정). 하단 고정 문구 두 줄은 손대지 않는다.
- 제목 · 반 표시 · 예상 기간 · 가운데 「예상되는 놀이 방향」 은 계획의 표시 칸 값을 그대로 쓴다
  (layout v0.2.0, 2026-10-28 D-2 · D-6 — 교사가 지운 빈 값도 빈 채로). 반 표시 = 연령 + 반 이름.
- 특성화 시간표: 전달본 제목 5칸(15행) · 내용 5칸(16행)에 그대로 채운다. 칸 구조는 그대로다.
- 특별활동 시간표(ADR-047 · D-8): 요일 머리(19행) 아래 칸 구역(전달본 20~21행)을 교사가 나눈
  모양대로 다시 만든다. 요일마다 나눔 트리를 사각형으로 펼치고, 모든 요일의 가로 경계를 합친
  만큼 행을 두고, 세로 경계는 표 전체 격자에 더해 칸을 병합한다 — 전달본이 이미 쓰는 방식이다.
  요일 열 폭(%)은 머리와 칸 구역에만, 높이(mm)는 칸 구역 전체에 쓴다. 칸은 전달본 (20,0) 칸
  서식을 따른다. 글이 길거나 칸이 작으면 한글이 행을 늘린다 — 줄이거나 자르지 않는다.
- 글자 크기를 줄이거나 자르지 않는다 — 길면 한글이 쪽을 넘긴다(표 `pageBreak="CELL"`).
  전달본 표는 「글자처럼 취급」(`treatAsChar="1"`)이라 쪽을 못 넘기고 1쪽 아래가 잘린다.
  양식 파일은 그대로 두고 채울 때 끈다 — 다른 양식(월간 v1 · 연간 · 주간)과 같은 값이다.

아직 내보내기 경로에 붙지 않았다 — 월간 v2 서버 경로가 생긴 뒤 붙인다. 근거 · 생성 정보 ·
이력 · 내부 ID 는 Core `play_monthly_document` 가 이미 뺀 값만 받는다.
"""

import copy
import io
import zipfile
from itertools import pairwise
from pathlib import Path

from lxml import etree
from ssuksak.planning.application.play_monthly_document import (
    PlayMonthlyDocument,
    PlayMonthlyDocumentPart,
)
from ssuksak.planning.domain.play_monthly_plan import TimetableSize
from ssuksak.planning.domain.provenance import SplitAxis

from app.features.plans.play_project_hwpx import _preview
from app.shared.hwpx import (
    NS,
    PACKAGE,
    PREVIEW,
    SECTION,
    TemplateMismatch,
    _cells,
    _clean,
    _drop_layout,
    _dump,
    _package,
    _set_text,
)

TEMPLATE = Path(__file__).parent / "templates" / "play_monthly.hwpx"

# 전달본의 라벨 칸 — 다른 양식이 들어오면 채우기 전에 멈춘다.
LABELS = {
    (1, 0): "놀 이 주 제",
    (2, 0): "예 상 기 간",
    (3, 0): "주제선정이유",
    (5, 0): "함께 하는 활동",
    (5, 12): "유아 예상 자유놀이",
    (9, 0): "기본생활습관",
    (10, 0): "안전교육",
    (11, 0): "소방대피/재난대비",
    (12, 0): "건강·영양교육",
    (14, 0): "[ 특성화 시간표 ]",
    (18, 0): "[ 특별활동 시간표 ]",
    (24, 0): "우리반 생일",
    (25, 0): "가정연계",
}
WEEK_HEADER, WEEK_HABIT, WEEK_SAFETY = 8, 9, 10
WEEK_FIRST_COLUMN = 3  # 그 왼쪽은 줄 이름 칸
WEEK_COUNTS = (4, 5)  # Core 주차 규칙(평일 3일 이상인 월~금 주)이 만드는 수
SPECIALIZED_ROWS = (15, 16)  # 제목 · 내용
SPECIALIZED_COLUMNS = (0, 4, 8, 11, 14)
SPECIAL_HEADER, SPECIAL_FIRST, SPECIAL_ROWS = 19, 20, 2  # 요일 머리 · 칸 구역(전달본 2행)
DAYS = ("월", "화", "수", "목", "금")
HWPUNIT_PER_MM = 7200 / 25.4
SNAP = round(0.5 * HWPUNIT_PER_MM)  # 요일 경계가 이만큼 안에 다른 줄 세로선이 있으면 그 선을 쓴다


def fill_play_monthly(template: bytes, doc: PlayMonthlyDocument) -> bytes:
    with zipfile.ZipFile(io.BytesIO(template)) as src:
        infos = src.infolist()
        parts = {info.filename: src.read(info.filename) for info in infos}

    section = etree.fromstring(parts[SECTION])
    tables = section.findall(".//hp:tbl", NS)
    if len(tables) != 1:
        raise TemplateMismatch(f"양식 표가 {len(tables)}개다.")
    table = tables[0]
    table.find("hp:pos", NS).set("treatAsChar", "0")
    _drop_layout(next(table.iterancestors(f"{{{NS['hp']}}}p")))  # 표를 담은 문단의 1쪽 높이 캐시
    cells = _cells(table)
    for address, label in LABELS.items():
        if address not in cells or _text(cells[address]) != label:
            raise TemplateMismatch(f"양식 {address} 칸이 「{label}」 이 아니다.")

    if len(doc.weeks) not in WEEK_COUNTS:
        raise TemplateMismatch(f"주차가 {len(doc.weeks)}개다 — 양식은 4주 · 5주만 나눈다.")

    heading = cells[(0, 0)].findall("hp:subList/hp:p", NS)
    if len(heading) != 2:
        raise TemplateMismatch("제목 칸은 제목 · 반 표시 두 문단이어야 한다.")
    _set_paragraph(heading[0], doc.title)
    _set_paragraph(heading[1], " ".join(v for v in (doc.age, doc.class_name) if v))

    _set_text(cells[(1, 2)], doc.theme)
    _set_text(cells[(2, 2)], doc.period)
    _set_text(cells[(3, 2)], doc.rationale)
    _set_text(cells[(5, 7)], doc.direction)
    _set_text(cells[(6, 0)], "\n".join(doc.together))
    _set_text(cells[(6, 12)], "\n".join(doc.free_play))
    _set_text(cells[(11, 3)], doc.drill)
    _set_text(cells[(12, 3)], _tagged("건강", doc.health))
    _set_text(cells[(12, 11)], _tagged("영양", doc.nutrition))
    _set_text(cells[(24, 3)], doc.birthdays)
    _set_text(cells[(25, 3)], doc.home_connection)
    for row, texts in zip(
        SPECIALIZED_ROWS, (doc.specialized_titles, doc.specialized_contents), strict=True
    ):
        for col, text in zip(SPECIALIZED_COLUMNS, texts, strict=True):
            _set_text(cells[(row, col)], text)
    _set_weeks(
        table,
        {
            WEEK_HEADER: [f"{i}주" for i in range(1, len(doc.weeks) + 1)],
            WEEK_HABIT: [
                f"[{w.habit_label}]\n{w.habit}" if w.habit_label else w.habit for w in doc.weeks
            ],
            WEEK_SAFETY: [w.safety for w in doc.weeks],
        },
    )
    _set_special_activity(table, doc.special_activity, doc.special_activity_size)

    parts[SECTION] = _dump(section)
    parts[PACKAGE] = _package(parts[PACKAGE], doc.title)
    if PREVIEW in parts:
        parts[PREVIEW] = _preview(section)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in infos:
            dst.writestr(info, parts[info.filename], compress_type=info.compress_type)
    return out.getvalue()


def _set_weeks(table: etree._Element, rows: dict[int, list[str]]) -> None:
    """주차 줄을 주 수만큼 같은 폭 칸으로 다시 만들고 표 격자 번호를 새로 매긴다.

    칸마다 같은 자리의 양식 칸을 복제해 서식(주차 색)을 물려받는다.
    """
    tcs = table.findall("hp:tr/hp:tc", NS)
    lines = _grid_lines(table, tcs)
    span = {tc: (lines[_col(tc)], lines[_col(tc)] + _width(tc)) for tc in tcs}
    left, right = lines[WEEK_FIRST_COLUMN], lines[int(table.get("colCnt"))]

    for row, texts in rows.items():
        tr = table.findall("hp:tr", NS)[row]
        olds = [tc for tc in tr.findall("hp:tc", NS) if _col(tc) >= WEEK_FIRST_COLUMN]
        if not 0 < len(texts) <= len(olds):
            raise TemplateMismatch(f"주차 줄 {row} 의 양식 칸이 {len(olds)}개다.")
        at = list(tr).index(olds[0])
        for tc in olds:
            tr.remove(tc)
            del span[tc]
        n = len(texts)
        edges = [left + (right - left) * i // n for i in range(n)] + [right]
        for i, text in enumerate(texts):
            tc = copy.deepcopy(olds[i])
            tc.find("hp:cellSz", NS).set("width", str(edges[i + 1] - edges[i]))
            _set_text(tc, text)
            tr.insert(at + i, tc)
            span[tc] = (edges[i], edges[i + 1])

    _renumber_columns(table, span)


def _set_special_activity(
    table: etree._Element, days: tuple[PlayMonthlyDocumentPart, ...], size: TimetableSize
) -> None:
    """특별활동 칸 구역을 요일별 나눔대로 다시 만든다. 행 · 열 번호는 표 전체를 다시 매긴다."""
    if len(days) != len(DAYS):
        raise TemplateMismatch(f"특별활동 요일이 {len(days)}개다.")
    trs = table.findall("hp:tr", NS)
    tcs = table.findall("hp:tr/hp:tc", NS)
    lines = _grid_lines(table, tcs)
    span = {tc: (lines[_col(tc)], lines[_col(tc)] + _width(tc)) for tc in tcs}
    left, right = lines[0], lines[int(table.get("colCnt"))]
    header = trs[SPECIAL_HEADER].findall("hp:tc", NS)
    if [_text(tc) for tc in header] != list(DAYS):
        raise TemplateMismatch(f"양식 {SPECIAL_HEADER}행이 요일 머리 「월 ~ 금」 이 아니다.")
    body = trs[SPECIAL_FIRST : SPECIAL_FIRST + SPECIAL_ROWS]
    model = body[0].find("hp:tc", NS)  # 전달본 (20,0) — 칸 서식
    at = list(table).index(body[0])
    for tr in body:
        for tc in tr.findall("hp:tc", NS):
            del span[tc]
        table.remove(tr)

    # 퍼센트로 나눈 요일 경계는 위 특성화 표의 세로선과 몇 단위씩 어긋나 아주 가는 열을 만든다.
    others = {x for tc, pair in span.items() if tc not in header for x in pair}
    edges = [
        _snap(left + (right - left) * sum(size.column_widths[:i]) // 100, others)
        for i in range(len(DAYS) + 1)
    ]
    for tc, (x0, x1) in zip(header, pairwise(edges), strict=True):
        tc.find("hp:cellSz", NS).set("width", str(x1 - x0))
        span[tc] = (x0, x1)

    height = round(size.height_mm * HWPUNIT_PER_MM)
    leaves = [
        leaf
        for day, (x0, x1) in zip(days, pairwise(edges), strict=True)
        for leaf in _layout(day, x0, x1, 0, height)
    ]
    ys = sorted({y for *_, y0, y1 in leaves for y in (y0, y1)})
    row = {y: i for i, y in enumerate(ys)}
    new_rows = [etree.Element(body[0].tag, body[0].attrib) for _ in ys[1:]]
    for text, x0, x1, y0, y1 in sorted(leaves, key=lambda leaf: (leaf[3], leaf[1])):
        tc = copy.deepcopy(model)
        tc.find("hp:cellSz", NS).set("width", str(x1 - x0))
        tc.find("hp:cellSz", NS).set("height", str(y1 - y0))
        tc.find("hp:cellSpan", NS).set("rowSpan", str(row[y1] - row[y0]))
        _set_text(tc, text)
        new_rows[row[y0]].append(tc)
        span[tc] = (x0, x1)
    for i, tr in enumerate(new_rows):
        table.insert(at + i, tr)

    trs = table.findall("hp:tr", NS)
    for r, tr in enumerate(trs):
        for tc in tr.findall("hp:tc", NS):
            tc.find("hp:cellAddr", NS).set("rowAddr", str(r))
    table.set("rowCnt", str(len(trs)))
    _renumber_columns(table, span)


def _snap(x: int, lines: set[int]) -> int:
    near = min(lines, key=lambda line: abs(line - x))
    return near if abs(near - x) <= SNAP else x


def _layout(
    part: PlayMonthlyDocumentPart, x0: int, x1: int, y0: int, y1: int
) -> list[tuple[str, int, int, int, int]]:
    """나눔 트리 → (글, x0, x1, y0, y1) 사각형. 세로 나눔은 위 · 아래, 가로 나눔은 왼쪽 · 오른쪽."""
    if part.axis is None:
        return [(part.text, x0, x1, y0, y1)]
    first, second = part.parts
    if part.axis is SplitAxis.VERTICAL:
        y = y0 + (y1 - y0) * part.ratio // 100
        return _layout(first, x0, x1, y0, y) + _layout(second, x0, x1, y, y1)
    x = x0 + (x1 - x0) * part.ratio // 100
    return _layout(first, x0, x, y0, y1) + _layout(second, x, x1, y0, y1)


def _renumber_columns(table: etree._Element, span: dict[etree._Element, tuple[int, int]]) -> None:
    """칸마다의 x 구간으로 표 격자 열 번호 · 병합 수를 다시 매긴다."""
    index = {x: i for i, x in enumerate(sorted({x for pair in span.values() for x in pair}))}
    for tc, (x0, x1) in span.items():
        tc.find("hp:cellAddr", NS).set("colAddr", str(index[x0]))
        tc.find("hp:cellSpan", NS).set("colSpan", str(index[x1] - index[x0]))
    table.set("colCnt", str(len(index) - 1))


def _tagged(tag: str, text: str) -> str:
    return f"[{tag}] {text}" if text.strip() else text


def _grid_lines(table: etree._Element, tcs: list[etree._Element]) -> dict[int, int]:
    """격자 번호 → 세로선 x. 칸마다 (시작 번호 + 병합 수) 의 x = 시작 x + 칸 폭."""
    lines = {0: 0}
    grew = True
    while grew:
        grew = False
        for tc in tcs:
            start, end = _col(tc), _col(tc) + int(tc.find("hp:cellSpan", NS).get("colSpan"))
            if start in lines and end not in lines:
                lines[end] = lines[start] + _width(tc)
                grew = True
    if len(lines) != int(table.get("colCnt")) + 1:
        raise TemplateMismatch("양식 표의 세로선을 모두 찾지 못했다.")
    return lines


def _col(tc: etree._Element) -> int:
    return int(tc.find("hp:cellAddr", NS).get("colAddr"))


def _width(tc: etree._Element) -> int:
    return int(tc.find("hp:cellSz", NS).get("width"))


def _text(tc: etree._Element) -> str:
    return "".join(t.text or "" for t in tc.iterfind("hp:subList/hp:p/hp:run/hp:t", NS))


def _set_paragraph(p: etree._Element, text: str) -> None:
    """문단 하나의 글자만 바꾼다.

    제목 칸은 문단마다 정렬 · 글자 모양이 달라 `_set_text`(첫 문단 서식으로 통일)를 못 쓴다.
    """
    run = p.find("hp:run", NS)
    for child in list(run):
        run.remove(child)
    etree.SubElement(run, f"{{{NS['hp']}}}t").text = _clean(text)
    _drop_layout(p)
