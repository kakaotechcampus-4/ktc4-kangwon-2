"""정부 어린이집 목록 사본을 받는 스크립트 (scripts/fetch_daycares.py · ADR-068).

망을 타지 않는다. 시도마다 받은 줄을 흉내 내고, 사본은 임시 폴더에 쓴다.
"""

import csv

import pytest

from scripts import fetch_daycares


def _row(sido, n):
    return {
        "sido": sido,
        "sigungu": "춘천시",
        "name": f"가상{n}어린이집",
        "kind": "가정",
        "status": "정상",
        "address": f"주소 {n}",
    }


@pytest.fixture
def portal(tmp_path, monkeypatch):
    """시도 코드마다 몇 곳을 줄지 고른다. 사본은 tmp 에 쓴다."""
    out = tmp_path / "daycares.csv"
    monkeypatch.setattr(fetch_daycares, "OUT", out)
    monkeypatch.setattr(fetch_daycares, "SIDO", ["42", "43"])
    counts = {"42": 10, "43": 10}
    names = {"42": "강원특별자치도", "43": "충청북도"}
    monkeypatch.setattr(
        fetch_daycares,
        "fetch",
        lambda sido, year, month: [_row(names[sido], n) for n in range(counts[sido])],
    )
    monkeypatch.setattr("sys.argv", ["fetch_daycares.py", "2026", "10"])
    return out, counts


def _lines(out):
    with out.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_다_받으면_사본을_쓴다(portal):
    out, _ = portal
    fetch_daycares.main()
    assert len(_lines(out)) == 20


def test_한_시도라도_0곳이면_사본을_덮어쓰지_않는다(portal):
    """한 시도만 빈 표가 와도 덮어쓰면 그 지역 교사는 찾기 결과가 0 이 된다."""
    out, counts = portal
    fetch_daycares.main()
    counts["43"] = 0

    with pytest.raises(SystemExit):
        fetch_daycares.main()

    assert len(_lines(out)) == 20


def test_지난_사본보다_한_시도가_크게_줄면_덮어쓰지_않는다(portal):
    out, counts = portal
    fetch_daycares.main()
    counts["43"] = 5  # 절반이 사라졌다 — 포털 표가 잘렸을 가능성이 더 크다

    with pytest.raises(SystemExit):
        fetch_daycares.main()

    assert len(_lines(out)) == 20
    counts["43"] = 9  # 한 달에 문을 닫는 정도는 받는다
    fetch_daycares.main()
    assert len(_lines(out)) == 19
