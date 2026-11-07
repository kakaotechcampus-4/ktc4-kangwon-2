"""정부 어린이집 목록 사본 (ADR-068).

`resources/daycares/daycares.csv` — `scripts/fetch_daycares.py` 가 매달 받는다
(어린이집정보공개포털).
가입할 때 정부 서버를 부르지 않는다. 그쪽이 멈춰도 첫 설정이 막히지 않게 사본만 읽는다.

**정부 목록에는 어린이집 고유 번호가 없다.** 「시도 · 시군구 · 이름 · 주소」 넷을 이은 글자를
한 원의 열쇠(`key`)로 쓴다. 2026-10 사본 25,546곳에서 넷이 겹치는 곳은 없다.
"""

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

CSV = Path(__file__).resolve().parents[3] / "resources" / "daycares" / "daycares.csv"
SEARCH_LIMIT = 30


@dataclass(frozen=True)
class Daycare:
    sido: str
    sigungu: str
    name: str
    kind: str
    status: str
    address: str

    @property
    def key(self) -> str:
        return "|".join((self.sido, self.sigungu, self.name, self.address))


@cache
def _all() -> dict[str, Daycare]:
    with CSV.open(encoding="utf-8", newline="") as f:
        rows = (Daycare(**row) for row in csv.DictReader(f))
        return {d.key: d for d in rows}


def find(key: str) -> Daycare | None:
    return _all().get(key)


def _plain(text: str) -> str:
    """「햇살 어린이집」과 「햇살어린이집」을 같게 본다."""
    return "".join(text.split())


def search(sido: str, sigungu: str, q: str) -> list[Daycare]:
    """그 시군구 어린이집 중 이름에 `q` 가 든 곳. 이름 앞부분이 맞는 곳을 먼저, 가나다순."""
    needle = _plain(q)
    hits = [
        d
        for d in _all().values()
        if d.sido == sido and d.sigungu == sigungu and needle in _plain(d.name)
    ]
    hits.sort(key=lambda d: (not _plain(d.name).startswith(needle), d.name))
    return hits[:SEARCH_LIMIT]
