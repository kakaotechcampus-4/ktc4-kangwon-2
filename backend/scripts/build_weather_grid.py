"""기상청 격자 좌표 엑셀에서 시군구 → 단기예보 격자(nx, ny) 표를 만든다 (ADR-078).

    cd backend && python scripts/build_weather_grid.py <받은 zip 또는 xlsx> <받은 날 YYYY-MM-DD>

엑셀은 공공데이터포털 「기상청_단기예보 ((구)_동네예보) 조회서비스」 참고문서 zip 안에 있다
(`기상청41_단기예보 조회서비스_오픈API활용가이드_격자_위경도(YYMM).xlsx`).
https://www.data.go.kr/data/15084084/openapi.do

표의 열쇠는 우리 원 지역 이름이다 — `resources/daycares/daycares.csv` 의 시도 · 시군구와 같은 글자
(지역 고르개 `frontend/lib/onboarding/regions.ts` 도 같다). 엑셀과 다른 곳은 둘이다.

- 기상청은 광주 · 전남을 「전남광주통합특별시」 하나로 낸다. 우리는 광주광역시 · 전라남도로 나눈다.
- 일반구가 있는 시(고양시 · 수원시 …)는 엑셀에 시 줄이 없고 구 줄만 있다. 행정구역코드가
  가장 작은 구를 쓴다. 격자는 5km 칸이라 같은 시의 구끼리는 0~3칸 차이다.

openpyxl 을 깔지 않는다. xlsx 는 zip 안의 XML 이라 표준 라이브러리로 읽는다.
"""

import csv
import io
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
DAYCARES = RESOURCES / "daycares" / "daycares.csv"
OUT = RESOURCES / "weather" / "kma_grid.csv"
SOURCE = "https://www.data.go.kr/data/15084084/openapi.do"
MERGED = {"광주광역시": "전남광주통합특별시", "전라남도": "전남광주통합특별시"}
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xlsx(path: Path) -> tuple[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".xlsx")]
        if not names:  # xlsx 를 바로 받았다
            return path.name, path.read_bytes()
        return names[0], archive.read(names[0])


def _rows(xlsx: bytes) -> list[list[str]]:
    book = zipfile.ZipFile(io.BytesIO(xlsx))
    shared = [
        "".join(t.text or "" for t in si.iter(f"{M}t"))
        for si in ET.fromstring(book.read("xl/sharedStrings.xml")).iter(f"{M}si")
    ]
    rows = []
    for row in ET.fromstring(book.read("xl/worksheets/sheet1.xml")).iter(f"{M}row"):
        cells = {}
        for c in row.iter(f"{M}c"):
            letters = re.match(r"[A-Z]+", c.get("r")).group(0)
            index = sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(letters))) - 1
            v = c.find(f"{M}v")
            text = "" if v is None else v.text or ""
            cells[index] = shared[int(text)] if c.get("t") == "s" and text else text
        rows.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
    return rows


def build(path: Path) -> tuple[list[dict[str, str]], str]:
    """(표 줄들, 엑셀 파일 이름)."""
    name, xlsx = _xlsx(path)
    # 구분 · 행정구역코드 · 1단계 · 2단계 · 3단계 · 격자 X · 격자 Y
    level2 = {}
    for row in _rows(xlsx)[1:]:
        _, code, sido, sigungu, dong, nx, ny = (row + [""] * 7)[:7]
        if sido and sigungu and not dong:
            level2[(sido, sigungu)] = (code, nx, ny)

    with DAYCARES.open(encoding="utf-8", newline="") as f:
        regions = sorted({(r["sido"], r["sigungu"]) for r in csv.DictReader(f)})
    out = []
    for sido, sigungu in regions:
        kma_sido = MERGED.get(sido, sido)
        hit = level2.get((kma_sido, sigungu))
        kma_name = sigungu
        if hit is None:
            parts = sorted(
                (code, s2, nx, ny)
                for (s1, s2), (code, nx, ny) in level2.items()
                if s1 == kma_sido and s2.startswith(sigungu) and s2.endswith("구")
            )
            if not parts:
                raise SystemExit(f"{name} 에 {sido} {sigungu} 가 없다.")
            code, kma_name, nx, ny = parts[0]
            hit = (code, nx, ny)
        code, nx, ny = hit
        out.append(
            {
                "sido": sido,
                "sigungu": sigungu,
                "nx": nx,
                "ny": ny,
                "kma_code": code,
                "kma_name": f"{kma_sido} {kma_name}",
            }
        )
    return out, name


if __name__ == "__main__":
    rows, name = build(Path(sys.argv[1]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        f.write(f"# 출처: 기상청 {name}\n# {SOURCE} 참고문서 zip\n")
        f.write(f"# 받은 날: {sys.argv[2]} · 만든 방법: backend/scripts/build_weather_grid.py\n")
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{OUT.relative_to(RESOURCES.parent)} — {len(rows)}곳")
