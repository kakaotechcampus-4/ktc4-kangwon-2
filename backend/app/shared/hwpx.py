"""hwpx 로 내보낸다. 한글이 만든 양식 파일의 표 칸 글자만 갈아끼우고 다시 압축한다.

계획안(features/plans)과 일지(features/documents)가 같이 쓴다. 양식 파일은 각 feature 의
`templates/` 에 둔다.

**표를 새로 그리지 않는다.** `header.xml`(글꼴·문단 모양·테두리)을 손으로 쓰면 한글이
파일을 안 여는 경로가 수십 개 생긴다. 한글이 저장한 양식을 그대로 두고 `hp:t` 만 바꾼다.

**`.hwp` 를 만들지 않는다.** 바이너리 포맷이라 쓸 수 없다. 교사가 한글에서
「다른 이름으로 저장 → .hwp」 한 번이면 된다.

zip 안의 파일 순서와 압축 방식을 양식 그대로 따른다.
- `mimetype` 이 맨 앞에 압축 없이 들어가야 한다. 이게 틀리면 한글이 안 연다.
"""

import copy
import io
import re
import zipfile
from collections.abc import Callable, Sequence
from urllib.parse import quote

from fastapi import Response
from lxml import etree

MEDIA_TYPE = "application/hwp+zip"

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
OPF = "http://www.idpf.org/2007/opf/"
NS = {"hp": HP, "opf": OPF}

SECTION = "Contents/section0.xml"
PACKAGE = "Contents/content.hpf"
PREVIEW = "Preview/PrvText.txt"

# 양식에서 제목 자리를 표시한 글자. 표 밖에 있는 첫 번째 것만 바꾼다.
TITLE_PLACEHOLDER = "제목"

# 양식을 저장한 사람이 남는 칸. 양식을 새로 넣을 때마다 지우기를 잊지 않도록 내보낼 때 다시 비운다.
_PERSONAL_META = ("creator", "lastsaveby")

# XML 1.0 이 담지 못하는 제어 문자. 교사가 붙여넣은 글에 섞여 오면 lxml 이 저장을 거부한다.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class TemplateMismatch(Exception):
    """양식의 표가 채울 내용과 맞지 않는다. 양식 파일이 바뀌었다는 뜻이라 서버 쪽 오류다."""


def fill_table(
    template: bytes, title: str, header_rows: int, rows: Sequence[Sequence[str]]
) -> bytes:
    """양식의 첫 번째 표에 `rows` 를 채운 hwpx 를 돌려준다.

    `header_rows` 줄은 양식의 머리행이라 건드리지 않는다. 칸 안의 줄바꿈(`\\n`)은
    문단을 나눠 담는다 — 한글은 `hp:t` 안의 줄바꿈 문자를 줄로 보지 않는다.
    """

    def fill(table: etree._Element) -> None:
        cells = _cells(table)
        height, width = int(table.get("rowCnt")), int(table.get("colCnt"))
        if height != header_rows + len(rows):
            raise TemplateMismatch(
                f"양식 표는 {height}줄인데 머리행 뒤로 {len(rows)}줄을 채우려 한다."
            )
        for r, row in enumerate(rows, start=header_rows):
            if len(row) != width:
                raise TemplateMismatch(f"양식 표는 {width}칸인데 {len(row)}칸을 채우려 한다.")
            for c, text in enumerate(row):
                _set_text(cells[(r, c)], text)

    return _rewrite(template, title, fill)


def fill_grid(
    template: bytes,
    title: str,
    header_rows: int,
    rows: Sequence[Sequence[str]],
    footer: Sequence[Sequence[str]],
) -> bytes:
    """양식 표의 본문 한 줄을 `rows` 만큼 복제해 채운다. 줄 수가 날마다 다른 일지용이다.

    양식 표는 머리행 `header_rows` 줄 · 빈 본문 원형 1줄 · 꼬리 줄들로 되어 있어야 한다.
    `footer` 는 꼬리 줄마다 **그 줄에 실제로 있는 칸** 순서대로의 글자다 — 병합된 칸은 하나로 센다.

    한글은 칸마다 적힌 (행, 열) 주소와 표의 `rowCnt` 로 표를 그린다. 줄을 끼워 넣으면 그 아래
    칸의 주소와 `rowCnt` 를 같이 밀어야 한다 — 하나라도 어긋나면 한글이 파일을 안 연다.
    """

    def fill(table: etree._Element) -> None:
        trs = table.findall("hp:tr", NS)
        if len(trs) != header_rows + 1 + len(footer):
            raise TemplateMismatch(
                f"양식 표는 {len(trs)}줄인데 "
                f"머리행 {header_rows} · 원형 1 · 꼬리 {len(footer)}줄을 기대한다."
            )
        if not rows:
            raise ValueError("본문 줄이 없다.")
        prototype, tail = trs[header_rows], trs[header_rows + 1 :]
        width = int(table.get("colCnt"))
        if len(prototype.findall("hp:tc", NS)) != width:
            raise TemplateMismatch("본문 원형 줄에 병합된 칸이 있다.")

        extra = len(rows) - 1
        for tr in tail:
            for tc in tr.findall("hp:tc", NS):
                addr = tc.find("hp:cellAddr", NS)
                addr.set("rowAddr", str(int(addr.get("rowAddr")) + extra))

        # 복제는 채우기 전의 빈 원형에서 뜬다 — 채운 줄을 복제하면 앞 줄 서식이 번진다.
        blank = copy.deepcopy(prototype)
        anchor = prototype
        for i, row in enumerate(rows):
            if len(row) != width:
                raise TemplateMismatch(f"양식 표는 {width}칸인데 {len(row)}칸을 채우려 한다.")
            if i == 0:
                tr = prototype
            else:
                tr = copy.deepcopy(blank)
                anchor.addnext(tr)
                anchor = tr
            for tc, text in zip(tr.findall("hp:tc", NS), row, strict=True):
                tc.find("hp:cellAddr", NS).set("rowAddr", str(header_rows + i))
                _set_text(tc, text)

        table.set("rowCnt", str(int(table.get("rowCnt")) + extra))
        size = table.find("hp:sz", NS)
        row_height = max(int(sz.get("height")) for sz in blank.iterfind("hp:tc/hp:cellSz", NS))
        size.set("height", str(int(size.get("height")) + extra * row_height))

        for tr, texts in zip(tail, footer, strict=True):
            tcs = tr.findall("hp:tc", NS)
            if len(tcs) != len(texts):
                raise TemplateMismatch(f"꼬리 줄은 {len(tcs)}칸인데 {len(texts)}칸을 채우려 한다.")
            for tc, text in zip(tcs, texts, strict=True):
                _set_text(tc, text)

    return _rewrite(template, title, fill)


def _rewrite(template: bytes, title: str, fill: Callable[[etree._Element], None]) -> bytes:
    """양식을 풀어 첫 번째 표를 `fill` 로 채우고, 제목 · 문서 정보 · 미리보기를 맞춰 다시 묶는다."""
    with zipfile.ZipFile(io.BytesIO(template)) as src:
        infos = src.infolist()
        parts = {info.filename: src.read(info.filename) for info in infos}

    section = etree.fromstring(parts[SECTION])
    table = section.find(".//hp:tbl", NS)
    if table is None:
        raise TemplateMismatch("양식에 표가 없습니다.")
    fill(table)
    _set_title(section, title)

    parts[SECTION] = _dump(section)
    parts[PACKAGE] = _package(parts[PACKAGE], title)
    if PREVIEW in parts:
        parts[PREVIEW] = _preview(section, title)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in infos:
            dst.writestr(info, parts[info.filename], compress_type=info.compress_type)
    return out.getvalue()


def download(content: bytes, fallback_name: str, title: str) -> Response:
    """내려받기 응답. 한글 파일명은 filename* 로만 안전하게 간다.

    filename 은 그걸 못 읽는 브라우저용이라 영문(`fallback_name`)으로 둔다.
    """
    disposition = (
        f"attachment; filename=\"{fallback_name}.hwpx\"; filename*=UTF-8''{quote(title + '.hwpx')}"
    )
    return Response(content, media_type=MEDIA_TYPE, headers={"Content-Disposition": disposition})


def _cells(table: etree._Element) -> dict[tuple[int, int], etree._Element]:
    """(행, 열) → 칸. 주소는 한글이 칸마다 적어둔 `hp:cellAddr` 를 쓴다.

    `hp:tr` 안의 순서로 세면 병합된 칸이 있을 때 열 번호가 밀린다.
    이 표의 칸만 모은다 — 칸 안에 표가 또 들어 있으면 그 칸들은 이 표 소속이 아니다.
    """
    cells = {}
    for tr in table.findall("hp:tr", NS):
        for tc in tr.findall("hp:tc", NS):
            addr = tc.find("hp:cellAddr", NS)
            cells[(int(addr.get("rowAddr")), int(addr.get("colAddr")))] = tc
    return cells


def _set_title(section: etree._Element, title: str) -> None:
    for t in section.iter(f"{{{HP}}}t"):
        in_table = any(True for _ in t.iterancestors(f"{{{HP}}}tbl"))
        if t.text == TITLE_PLACEHOLDER and not in_table:
            t.text = _clean(title)
            _drop_layout(next(t.iterancestors(f"{{{HP}}}p")))
            return
    raise TemplateMismatch(f"양식에 「{TITLE_PLACEHOLDER}」 자리가 없습니다.")


def _set_text(tc: etree._Element, text: str) -> None:
    """칸의 글자를 통째로 바꾼다. 서식은 칸의 첫 문단 · 첫 글자 모양을 그대로 물려받는다."""
    sub_list = tc.find("hp:subList", NS)
    paragraphs = sub_list.findall("hp:p", NS)
    prototype = paragraphs[0]
    for p in paragraphs:
        sub_list.remove(p)

    for line in _clean(text).split("\n"):
        p = copy.deepcopy(prototype)
        run, *extra = p.findall("hp:run", NS)
        for other in extra:
            p.remove(other)
        for child in list(run):
            run.remove(child)
        if line:
            etree.SubElement(run, f"{{{HP}}}t").text = line
        _drop_layout(p)
        sub_list.append(p)


def _drop_layout(p: etree._Element) -> None:
    """줄 배치 캐시를 지운다. 글자가 바뀌면 틀린 값이 되고, 없으면 한글이 다시 계산한다."""
    for layout in p.findall("hp:linesegarray", NS):
        p.remove(layout)


def _clean(text: str) -> str:
    # 탭은 한글에서 `hp:tab` 요소라 글자로 넣으면 깨진다. 칸 안에서는 띄어쓰기로 충분하다.
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\t", " "))


def _package(data: bytes, title: str) -> bytes:
    """문서 정보. 제목을 맞추고 양식을 저장한 사람의 이름을 비운다."""
    package = etree.fromstring(data)
    for meta in package.iterfind(".//opf:meta", NS):
        if meta.get("name") in _PERSONAL_META:
            meta.text = None
    title_el = package.find(".//opf:title", NS)
    if title_el is not None:
        title_el.text = _clean(title)
    return _dump(package)


def _preview(section: etree._Element, title: str) -> bytes:
    """탐색기 미리보기용 평문. 양식의 것을 그대로 두면 채우기 전의 빈 표가 보인다.

    형식은 한글이 쓰는 그대로다 — 제목 한 줄, 그 아래 표 한 줄에 `<칸><칸>`.
    """
    lines = [_clean(title)]
    table = section.find(".//hp:tbl", NS)
    for tr in table.findall("hp:tr", NS):
        texts = [
            " ".join("".join(t.itertext()) for t in tc.iterfind(".//hp:t", NS))
            for tc in tr.findall("hp:tc", NS)
        ]
        lines.append("".join(f"<{text}>" for text in texts))
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def _dump(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
