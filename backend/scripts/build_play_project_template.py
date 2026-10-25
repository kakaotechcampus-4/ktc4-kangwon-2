"""놀이 프로젝트형 연간 hwpx 양식을 만든다(ADR-042).

다른 양식처럼 표를 손으로 그리지 않는다. 하민이 한글에서 다듬고 확인한 예시 문서(저장소 밖,
`연간7_5pt_가독성B.hwpx`)에서 **글자만 비운다** — 쪽 · 글꼴 · 열 너비 · 병합 · 칸 여백 · 테두리는
그 파일 그대로다.

    python scripts/build_play_project_template.py <예시 문서.hwpx>

비우는 것
  제목 두 곳          「제목」 자리 표시(`hwpx.TITLE_PLACEHOLDER`)로
  본문 칸             첫 문단만 남기고 글자를 지운다. 글자 모양(run)은 남긴다 —
                      배움 칸은 굵은 `[영역]` run 과 보통 run 두 개가 원형이다.
  줄 배치 캐시        비운 문단의 것
  편집 상태 · 정보     커서 위치 · 문서 제목 · 작성자
머리행 · 쪽 설정 · 빈 줄 문단은 건드리지 않는다.
"""

from __future__ import annotations

import io
import pathlib
import sys
import zipfile

from lxml import etree

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.shared.hwpx import (  # noqa: E402
    NS,
    PACKAGE,
    PREVIEW,
    SECTION,
    TITLE_PLACEHOLDER,
    _drop_layout,
    _dump,
    _package,
)

TARGET = ROOT / "app/features/plans/templates/play_project_annual.hwpx"
SETTINGS = "settings.xml"
HEADER_ROWS = 1


def _blank_cell(tc: etree._Element) -> None:
    sub_list = tc.find("hp:subList", NS)
    first, *rest = sub_list.findall("hp:p", NS)
    for p in rest:
        sub_list.remove(p)
    for t in first.findall("hp:run/hp:t", NS):
        t.getparent().remove(t)
    _drop_layout(first)


def build(source: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(source)) as src:
        infos = src.infolist()
        parts = {info.filename: src.read(info.filename) for info in infos}

    section = etree.fromstring(parts[SECTION])
    tables = section.findall(".//hp:tbl", NS)
    if len(tables) != 2:
        raise SystemExit(f"표가 두 개여야 한다: {len(tables)}")
    for table in tables:
        for tr in table.findall("hp:tr", NS)[HEADER_ROWS:]:
            for tc in tr.findall("hp:tc", NS):
                _blank_cell(tc)

    titles = 0
    for p in section.findall("hp:p", NS):
        texts = p.findall("hp:run/hp:t", NS)
        if any(t.text for t in texts) and p.find(".//hp:tbl", NS) is None:
            texts[0].text = TITLE_PLACEHOLDER
            for t in texts[1:]:
                t.getparent().remove(t)
            _drop_layout(p)
            titles += 1
    if titles != 2:
        raise SystemExit(f"제목이 두 곳이어야 한다: {titles}")

    parts[SECTION] = _dump(section)
    parts[PACKAGE] = _package(parts[PACKAGE], "")
    settings = etree.fromstring(parts[SETTINGS])
    for caret in settings.iter("{*}CaretPosition"):
        caret.set("listIDRef", "0")
        caret.set("paraIDRef", "0")
        caret.set("pos", "0")
    parts[SETTINGS] = _dump(settings)
    if PREVIEW in parts:
        parts[PREVIEW] = (TITLE_PLACEHOLDER + "\r\n").encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in infos:
            dst.writestr(info, parts[info.filename], compress_type=info.compress_type)
    return out.getvalue()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    TARGET.write_bytes(build(pathlib.Path(sys.argv[1]).read_bytes()))
    print(f"{TARGET} — 표 2 · 제목 2")


if __name__ == "__main__":
    main()
