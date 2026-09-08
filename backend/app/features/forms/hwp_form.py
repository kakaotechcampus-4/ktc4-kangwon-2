"""HWP/HWPX 양식에서 표 구조를 뽑는다.

양식 문서는 거의 전부 표다. 텍스트만 뽑으면 칸을 잃는다.
- .hwp  : pyhwp의 hwp5html로 XHTML 변환 후 표 파싱 (hwp5txt는 표를 <표>로 버린다)
- .hwpx : OWPML = zip + XML. 표준 라이브러리로 연다

의존성:  pip install pyhwp six olefile    (hwp5html CLI가 PATH에 있어야 한다)
읽기 전용이다. 쓰기는 hwpx를 직접 만들거나 docx로 낸다.
"""
import html
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path


class _Tables(HTMLParser):
    """중첩 표까지 스택으로 처리한다. 정규식은 중첩에서 깨진다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.done = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "br":
            self.handle_data(" ")
        elif tag == "table":
            self.stack.append([])
        elif tag == "tr" and self.stack:
            self.stack[-1].append([])
        elif tag in ("td", "th") and self.stack and self.stack[-1]:
            self.stack[-1][-1].append(
                {"text": "", "rowspan": int(a.get("rowspan", 1)), "colspan": int(a.get("colspan", 1))}
            )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "table" and self.stack:
            self.done.append(self.stack.pop())

    def handle_data(self, data):
        # 현재 열려 있는 가장 안쪽 셀에 붙인다
        for tbl in reversed(self.stack):
            if tbl and tbl[-1]:
                tbl[-1][-1]["text"] += data
                return


def _clean(tables):
    for t in tables:
        for row in t:
            for c in row:
                c["text"] = re.sub(r"\s+", " ", html.unescape(c["text"])).strip()
    return [t for t in tables if t]


def from_html(source: str):
    p = _Tables()
    p.feed(source)
    return _clean(p.done + p.stack)


def from_hwp(path):
    """hwp5html로 변환 후 표 추출. 반환: [[[cell,...],...],...]"""
    if not shutil.which("hwp5html"):
        raise RuntimeError("hwp5html 없음 — pip install pyhwp six")
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["hwp5html", "--output", d, str(path)], check=True, capture_output=True)
        return from_html(Path(d, "index.xhtml").read_text("utf-8", errors="replace"))


def from_hwpx(path):
    """hwpx는 zip+XML. 셀 텍스트만 순서대로 뽑는다 (표 경계는 hc:tbl)."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.startswith("Contents/section") and n.endswith(".xml")]
        xml = "".join(z.read(n).decode("utf-8", "replace") for n in sorted(names))
    tables = []
    for tbl in re.findall(r"<hp:tbl\b.*?</hp:tbl>", xml, re.S):
        rows = []
        for tr in re.findall(r"<hp:tr\b.*?</hp:tr>", tbl, re.S):
            rows.append(
                [
                    {"text": re.sub(r"\s+", " ", "".join(re.findall(r"<hp:t>(.*?)</hp:t>", tc, re.S))).strip(),
                     "rowspan": 1, "colspan": 1}
                    for tc in re.findall(r"<hp:tc\b.*?</hp:tc>", tr, re.S)
                ]
            )
        tables.append(rows)
    return _clean(tables)


def extract(path):
    path = Path(path)
    return from_hwpx(path) if path.suffix.lower() == ".hwpx" else from_hwp(path)


def labels(tables):
    """비어 있지 않은 셀 = 양식의 라벨 후보. 필드 매핑의 출발점."""
    return [c["text"] for t in tables for row in t for c in row if c["text"]]


def _selfcheck():
    src = """<table><tr><td rowspan="2">출결<br/>사항</td><td colspan="3">월요일</td></tr>
             <tr><td>출석</td><td>명</td><td><table><tr><td>중첩</td></tr></table></td></tr></table>"""
    t = from_html(src)
    assert len(t) == 2, t                      # 바깥 표 + 중첩 표
    outer = max(t, key=len)
    assert outer[0][0]["text"] == "출결 사항", outer[0][0]
    assert outer[0][0]["rowspan"] == 2 and outer[0][1]["colspan"] == 3
    assert "중첩" in labels(t)
    print("self-check OK")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        tabs = extract(sys.argv[1])
        print(f"표 {len(tabs)}개")
        for i, t in enumerate(tabs, 1):
            n = sum(len(r) for r in t)
            print(f"[{i}] {len(t)}행 {n}셀 :: {[c['text'] for r in t for c in r if c['text']][:12]}")
    else:
        _selfcheck()
