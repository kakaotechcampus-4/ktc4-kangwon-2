"""정부 어린이집 목록을 받아 `resources/daycares/daycares.csv` 로 쓴다 (ADR-068).

어린이집정보공개포털 「어린이집 기본정보」(SHEET, 매월 말일 적재)를 시도마다 한 번씩 받는다.
가입할 때마다 정부 서버를 부르지 않으려고 사본을 저장소에 둔다 — 정부 서버가 멈춰도 가입은 된다.

    cd backend && python scripts/fetch_daycares.py            # 지난달 기준
    cd backend && python scripts/fetch_daycares.py 2026 10    # 기준 연 · 월

받는 칸 중 원을 찾는 데 쓰는 것만 남긴다: 시도 · 시군구 · 어린이집명 · 유형 · 운영현황 · 주소.
출처: 어린이집정보공개포털(한국사회보장정보원), 공공누리 제1유형(출처표시).
"""

import csv
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import httpx

URL = "https://info.childcare.go.kr/info_html5/stat/sheet/StatCrInfoResult.jsp"
OUT = Path(__file__).resolve().parents[1] / "resources" / "daycares" / "daycares.csv"
# 포털 시도 코드. 포털은 광주 · 전남을 「전남광주통합특별시」(12) 하나로 낸다.
SIDO = "11 12 26 27 28 30 31 36 41 43 44 47 48 49 51 52".split()
FIELDS = ["sido", "sigungu", "name", "kind", "status", "address"]
# 포털 표 칸 순서: 번호 · 시도 · 시군구 · 어린이집명 · 유형 · 운영현황 · 우편번호 · 주소 …
COLUMNS = {"sido": 1, "sigungu": 2, "name": 3, "kind": 4, "status": 5, "address": 7}
# 한 시도가 지난 사본보다 이만큼 넘게 줄면 덮어쓰지 않는다. 한 달에 문을 닫는 곳은 1% 남짓이다
# (2026-10 휴지 512 / 25,546). 이보다 크게 줄면 포털 표가 잘렸을 가능성이 더 크다.
MAX_DROP = 0.2


# 우리 지역 고르개(frontend/lib/onboarding/regions.ts)는 기초자치단체까지만 나눈다.
# 포털 이름을 그쪽에 맞춘다.
GWANGJU = {"동구", "서구", "남구", "북구", "광산구"}
OLD_CITY = {"마산시(구)": "창원시", "진해시(구)": "창원시", "창원시(구)": "창원시"}
# 고양시덕양구 · 김해시장유출장소 → 고양시 · 김해시
CITY_PART = re.compile(r"^(.+시)(.+구|.+출장소)$")


def regionize(sido: str, sigungu: str) -> tuple[str, str]:
    """포털의 시도 · 시군구를 우리 지역 이름으로. 광주 · 전남을 가르고, 일반구는 시로 올린다."""
    if sido == "전남광주통합특별시":
        sido = "광주광역시" if sigungu in GWANGJU else "전라남도"
    name = sigungu.replace(" ", "")
    if name in OLD_CITY:
        return sido, OLD_CITY[name]
    part = CITY_PART.match(name)
    return sido, part.group(1) if part else sigungu


class _Rows(HTMLParser):
    """`<tbody>` 안 `<tr>` 마다 `<td>` 글자를 모은다. 정규식으로 표를 읽지 않는다."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._body = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self._body = True
        elif self._body and tag == "tr":
            self._row = []
        elif self._row is not None and tag == "td":
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "tbody":
            self._body = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def fetch(sido: str, year: int, month: int) -> list[dict[str, str]]:
    form = {
        "flag": "crInfo",
        "exlChk": "Y",  # 쪽 나눔 없이 시도 전체를 한 표로 준다
        "std_condi": "Y",
        "wkyear": str(year),
        "wkmonth": f"{month:02d}",
        "sido": sido,
        "sigun": "",
    }
    response = httpx.post(URL, data=form, timeout=180)
    response.raise_for_status()
    parser = _Rows()
    parser.feed(response.text)
    out = []
    for row in parser.rows:
        if len(row) <= COLUMNS["address"]:
            continue
        item = {key: row[at] for key, at in COLUMNS.items()}
        item["sido"], item["sigungu"] = regionize(item["sido"], item["sigungu"])
        if item["name"] and item["status"] != "폐지":
            out.append(item)
    return out


def _by_sido(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["sido"]] = counts.get(row["sido"], 0) + 1
    return counts


def shrunk(old: list[dict[str, str]], new: list[dict[str, str]]) -> list[str]:
    """지난 사본보다 `MAX_DROP` 넘게 줄었거나 사라진 시도. 지난 사본이 없으면 빈 목록이다."""
    before, after = _by_sido(old), _by_sido(new)
    return [
        f"{sido} {count} → {after.get(sido, 0)}"
        for sido, count in sorted(before.items())
        if after.get(sido, 0) < count * (1 - MAX_DROP)
    ]


def _previous() -> list[dict[str, str]]:
    if not OUT.exists():
        return []
    with OUT.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if len(sys.argv) == 3:
        year, month = int(sys.argv[1]), int(sys.argv[2])
    else:
        today = date.today()
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    rows: list[dict[str, str]] = []
    for sido in SIDO:
        got = fetch(sido, year, month)
        print(f"{sido}: {len(got)}", file=sys.stderr)
        # 한 시도만 빈 표가 와도 덮어쓰면 그 지역 교사는 찾기 결과가 0 이 된다.
        if not got:
            raise SystemExit(f"시도 코드 {sido} 를 한 곳도 받지 못했다 — 사본을 덮어쓰지 않는다")
        rows.extend(got)
    if dropped := shrunk(_previous(), rows):
        raise SystemExit(
            f"지난 사본보다 {MAX_DROP:.0%} 넘게 줄었다 ({', '.join(dropped)}) — "
            "사본을 덮어쓰지 않는다. 포털 표를 확인하고, 진짜 줄었으면 사본을 지우고 다시 받는다"
        )
    rows.sort(key=lambda r: (r["sido"], r["sigungu"], r["name"], r["address"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)}곳 · {year}-{month:02d} 기준 → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
