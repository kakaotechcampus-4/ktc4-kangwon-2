"""놀이 프로젝트형 연간 hwpx (ADR-042) — 고른 놀이를 양식 `play_project_annual.hwpx` 에 채운다.

양식은 A4 세로 두 쪽이다. 쪽마다 제목 · 빈 줄 · 표 하나, 표 하나에 구간 둘 × 놀이 다섯.
시기 칸은 구간마다 다섯 줄을 합쳤다. 열은 시기 · 놀이명 · 지원매체 · 지원 방향 · 배움.

공용 `hwpx.fill_table` 을 쓰지 않는 이유 — 그 함수는 첫 번째 표 · 첫 번째 제목만 채우고,
칸 글자를 첫 run 의 글자 모양 하나로 쓴다. 이 양식은 표 · 제목이 둘이고, 배움 줄은
`[영역]` 만 굵다. 공용 함수를 바꾸면 월간 · 주간 · 일지 양식까지 영향이 가서 여기서 따로 채운다.

내보내기 경로(`export.py`)가 확정본의 고른 5개를 넘긴다. 고르지 않은 후보 ·
근거(evidence) · 생성 정보는 받지 않는다. 배움 글자는 서버가 누리과정 Reference 에서 그린
값을 그대로 받는다(LLM 이 쓴 글이 아니다).
"""

import copy
import io
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lxml import etree

from app.shared.hwpx import (
    HP,
    NS,
    PACKAGE,
    PREVIEW,
    SECTION,
    TITLE_PLACEHOLDER,
    TemplateMismatch,
    _cells,
    _clean,
    _drop_layout,
    _dump,
    _package,
    _set_text,
)

TEMPLATE = Path(__file__).parent / "templates" / "play_project_annual.hwpx"

TABLES = 2
PERIODS_PER_TABLE = 2
ROWS_PER_PERIOD = 5
LEARNING_COLUMN = 4


class PlayRow(NamedTuple):
    play_name: str
    materials: str
    support_direction: str
    # (영역, 내용범주, 내용) — 한 줄이 「[영역] 내용범주 - 내용」 이 되고 `[영역]` 만 굵다.
    learning: Sequence[tuple[str, str, str]]


class PlayPeriodRows(NamedTuple):
    label: str  # 시기 칸. 줄바꿈으로 문단을 나눈다 — 예: "3~5월\n봄"
    rows: Sequence[PlayRow]


def fill_play_project(template: bytes, title: str, periods: Sequence[PlayPeriodRows]) -> bytes:
    with zipfile.ZipFile(io.BytesIO(template)) as src:
        infos = src.infolist()
        parts = {info.filename: src.read(info.filename) for info in infos}

    section = etree.fromstring(parts[SECTION])
    tables = section.findall(".//hp:tbl", NS)
    if len(tables) != TABLES or len(periods) != TABLES * PERIODS_PER_TABLE:
        raise TemplateMismatch(f"양식 표 {len(tables)}개에 구간 {len(periods)}개를 채우려 한다.")
    for i, table in enumerate(tables):
        _fill_table(table, periods[i * PERIODS_PER_TABLE : (i + 1) * PERIODS_PER_TABLE])
    _set_titles(section, title, len(tables))

    parts[SECTION] = _dump(section)
    parts[PACKAGE] = _package(parts[PACKAGE], title)
    if PREVIEW in parts:
        parts[PREVIEW] = _preview(section)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in infos:
            dst.writestr(info, parts[info.filename], compress_type=info.compress_type)
    return out.getvalue()


def _fill_table(table: etree._Element, periods: Sequence[PlayPeriodRows]) -> None:
    cells = _cells(table)
    if int(table.get("rowCnt")) != 1 + PERIODS_PER_TABLE * ROWS_PER_PERIOD:
        raise TemplateMismatch(f"양식 표가 {table.get('rowCnt')}줄이다.")
    for p, period in enumerate(periods):
        if len(period.rows) != ROWS_PER_PERIOD:
            raise TemplateMismatch(f"구간마다 놀이 {ROWS_PER_PERIOD}개인데 {len(period.rows)}개다.")
        top = 1 + p * ROWS_PER_PERIOD
        span = cells[(top, 0)].find("hp:cellSpan", NS)
        if span is None or span.get("rowSpan") != str(ROWS_PER_PERIOD):
            raise TemplateMismatch(f"시기 칸 ({top}, 0) 이 {ROWS_PER_PERIOD}줄 병합이 아니다.")
        _set_text(cells[(top, 0)], period.label)
        for r, row in enumerate(period.rows, start=top):
            _set_text(cells[(r, 1)], row.play_name)
            _set_text(cells[(r, 2)], row.materials)
            _set_text(cells[(r, 3)], row.support_direction)
            _set_learning(cells[(r, LEARNING_COLUMN)], row.learning)


def _set_learning(tc: etree._Element, learning: Sequence[tuple[str, str, str]]) -> None:
    """배움 한 줄 = 문단 하나 = 굵은 run `[영역]` + 보통 run ` 범주 - 내용`.

    공용 `_set_text` 는 첫 run 만 남겨 전부 굵어진다. 양식 원형 문단의 run 두 개를 그대로 복제한다.
    """
    if not learning:
        raise ValueError("배움이 비었다.")
    sub_list = tc.find("hp:subList", NS)
    paragraphs = sub_list.findall("hp:p", NS)
    prototype = paragraphs[0]
    if len(prototype.findall("hp:run", NS)) != 2:
        raise TemplateMismatch("배움 칸 원형 문단은 run 두 개(굵게 · 보통)여야 한다.")
    for p in paragraphs:
        sub_list.remove(p)
    for domain, category, content in learning:
        p = copy.deepcopy(prototype)
        for run, text in zip(
            p.findall("hp:run", NS), (f"[{domain}]", f" {category} - {content}"), strict=True
        ):
            for child in list(run):
                run.remove(child)
            etree.SubElement(run, f"{{{HP}}}t").text = _clean(text)
        _drop_layout(p)
        sub_list.append(p)


def _set_titles(section: etree._Element, title: str, expected: int) -> None:
    """표 밖 「제목」 자리를 모두 바꾼다 — 쪽마다 하나씩, 표 수만큼 있어야 한다."""
    found = [
        t
        for t in section.iter(f"{{{HP}}}t")
        if t.text == TITLE_PLACEHOLDER and next(t.iterancestors(f"{{{HP}}}tbl"), None) is None
    ]
    if len(found) != expected:
        raise TemplateMismatch(f"「{TITLE_PLACEHOLDER}」 자리가 {len(found)}곳이다.")
    for t in found:
        t.text = _clean(title)
        _drop_layout(next(t.iterancestors(f"{{{HP}}}p")))


def _preview(section: etree._Element) -> bytes:
    """탐색기 미리보기 평문. 한글처럼 맨 위 문단마다 한 줄, 표는 줄마다 `<칸><칸>`."""
    lines = []
    for p in section.findall("hp:p", NS):
        table = p.find(".//hp:tbl", NS)
        if table is None:
            lines.append("".join(t.text or "" for t in p.iterfind("hp:run/hp:t", NS)))
            continue
        for tr in table.findall("hp:tr", NS):
            # 문단은 띄어 잇고, 한 문단 안의 run(배움의 `[영역]` · 나머지)은 붙여 잇는다.
            texts = [
                " ".join(
                    "".join(t.text or "" for t in p.iterfind("hp:run/hp:t", NS))
                    for p in tc.iterfind("hp:subList/hp:p", NS)
                )
                for tc in tr.findall("hp:tc", NS)
            ]
            lines.append("".join(f"<{text}>" for text in texts))
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
