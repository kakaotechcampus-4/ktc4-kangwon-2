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


# ── 원 열쇠 맞추기 (scripts/registry_keys.py) ─────────────────────────────────


def _center(session, name, key=None, sido="강원특별자치도", sigungu="춘천시"):
    from app.features.centers.models import Center

    center = Center(
        name=name,
        director_name="김원장",
        region_sido=sido,
        region_sigungu=sigungu,
        registry_key=key,
    )
    session.add(center)
    session.flush()
    return center


def _join_by_list(session, daycare):
    """정부 목록에서 그 어린이집을 고른 새 교사. 들어간 원 id 와 합류 여부를 준다."""
    from fastapi.testclient import TestClient

    from app.features.auth.models import User
    from app.main import app
    from app.shared.auth.dependency import current_user

    user = User(
        email="new@example.com", name="새", password_hash=b"x" * 64, password_salt=b"y" * 16
    )
    session.add(user)
    session.flush()
    app.dependency_overrides[current_user] = lambda: user
    try:
        body = (
            TestClient(app)
            .post(
                "/api/centers",
                json={
                    "name": daycare.name,
                    "director_name": "새원장",
                    "region_sido": daycare.sido,
                    "region_sigungu": daycare.sigungu,
                    "registry_key": daycare.key,
                },
            )
            .json()
        )
    finally:
        app.dependency_overrides.pop(current_user, None)
    return body["id"], body["joined"]


def test_표기가_바뀐_옛_열쇠를_새_열쇠로_옮겨_다음_교사가_같은_원으로_든다(db_session):
    from app.features.centers import registry
    from scripts import registry_keys

    daycare = registry.search("강원특별자치도", "춘천시", "리틀빌리지")[0]
    # 지난달 사본에는 주소가 「…번길」 없이 적혀 있었다고 친다 — 이름은 같다.
    stale = "|".join((daycare.sido, daycare.sigungu, daycare.name, "옛 주소 표기"))
    old = _center(db_session, daycare.name, key=stale)

    moves, notes = registry_keys.run(db_session, apply=True)

    assert moves == {old.id: daycare.key}, notes
    assert _join_by_list(db_session, daycare) == (old.id, True)


def test_열쇠_없는_옛_원은_이름이_하나로_맞으면_열쇠를_채운다(db_session):
    """#415 전에 가입한 교사의 원. 채우면 같은 어린이집을 고른 교사가 그 원으로 든다."""
    from app.features.centers import registry
    from scripts import registry_keys

    daycare = registry.search("강원특별자치도", "춘천시", "리틀빌리지")[0]
    old = _center(db_session, daycare.name.replace("어린이집", " 어린이집"))
    typed = _center(db_session, "목록에없는새어린이집")

    moves, _ = registry_keys.run(db_session, apply=True)

    assert moves[old.id] == daycare.key
    assert typed.id not in moves
    db_session.refresh(old)
    assert old.name == daycare.name.replace("어린이집", " 어린이집")  # 이름은 그대로다
    assert _join_by_list(db_session, daycare) == (old.id, True)


def test_옮길_열쇠를_다른_원이_쓰면_옮기지_않고_적기만_한다(db_session):
    from app.features.centers import registry
    from scripts import registry_keys

    daycare = registry.search("강원특별자치도", "춘천시", "리틀빌리지")[0]
    _center(db_session, "새로든원", key=daycare.key)
    old = _center(db_session, daycare.name)

    moves, notes = registry_keys.run(db_session, apply=False)

    assert old.id not in moves
    assert any(str(old.id) in note and "합쳐야" in note for note in notes)
