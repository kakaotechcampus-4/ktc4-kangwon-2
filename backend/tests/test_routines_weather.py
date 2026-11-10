"""일과 기록 하루치에 붙는 그날 날씨 (ADR-089 · docs/api-spec.md §10-1 「그날 날씨」).

기상청 · 에어코리아에는 닿지 않는다. `weather.transport` 에 가짜 전송을 끼운다.
"""

import datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.features.centers.models import Center, Class
from app.features.routines import weather
from app.features.routines.models import RegionWeather
from app.main import app

client = TestClient(app)
NOW = datetime.datetime(2026, 11, 9, 10, 0, tzinfo=weather.KST)
TODAY = NOW.date().isoformat()


@pytest.fixture
def klass(db_session, teacher, monkeypatch):
    monkeypatch.setattr(weather, "_now", lambda: NOW)
    # 옛 직접 입력 원처럼 줄임말로 적었다 — 격자 표의 「강원특별자치도 · 춘천시」로 찾는다.
    center = Center(
        name="테스트어린이집", director_name="김원장", region_sido="강원", region_sigungu="춘천"
    )
    db_session.add(center)
    db_session.flush()
    sun = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김",
    )
    db_session.add(sun)
    db_session.flush()
    teacher.center_id = center.id
    return sun


def apis(monkeypatch, *, pty="0", sky="1", stations=None, status=200):
    """가짜 기상청 · 에어코리아. 부른 경로를 돌려준다 — 몇 번 불렀는지 센다."""
    calls = []
    stations = stations or [{"stationName": "석사동", "pm10Value": "40", "pm25Value": "20"}]

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", 1)[-1])
        if status != 200:
            return httpx.Response(status)
        ok = {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"}
        if calls[-1] == "getVilageFcst":
            assert request.url.params["nx"] == "73" and request.url.params["ny"] == "134"
            assert request.url.params["base_time"] == "0200"
            day = request.url.params["base_date"]
            items = [
                {"category": c, "fcstDate": day, "fcstTime": f"{h:02d}00", "fcstValue": v}
                for h in range(3, 24)
                for c, v in (("SKY", sky), ("PTY", pty if h == 15 else "0"))
            ]
            return httpx.Response(
                200, json={"response": {"header": ok, "body": {"items": {"item": items}}}}
            )
        assert request.url.params["sidoName"] == "강원"
        return httpx.Response(200, json={"response": {"header": ok, "body": {"items": stations}}})

    monkeypatch.setattr(weather, "transport", httpx.MockTransport(handle))
    return calls


def _day(klass, day=TODAY):
    response = client.get("/api/routines", params={"class_id": klass.id, "from": day, "to": day})
    assert response.status_code == 200, response.text
    return response.json()["weather"]


def test_비가_한_시간이라도_오면_비고_대체놀이_칩을_띄운다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch, pty="1")

    assert _day(klass) == {
        "date": TODAY,
        "sky": "비",
        "dust": "보통",
        "source": "auto",
        "indoor_hint": "rain",
    }
    assert calls == ["getVilageFcst", "getCtprvnRltmMesureDnsty"]


def test_같은_지역_같은_날은_한_번만_부른다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)

    assert _day(klass)["sky"] == "맑음"
    assert _day(klass)["sky"] == "맑음"

    assert len(calls) == 2
    saved = db_session.scalars(select(RegionWeather)).all()
    assert [(r.region_sido, r.region_sigungu, r.sky, r.dust) for r in saved] == [
        ("강원특별자치도", "춘천시", "맑음", "보통")
    ]


def test_미세먼지는_같은_이름_측정소가_있으면_그_값_없으면_시도_평균(
    db_session, klass, monkeypatch
):
    stations = [
        {"stationName": "춘천", "pm10Value": "160", "pm25Value": "-"},
        {"stationName": "원주", "pm10Value": "20", "pm25Value": "10"},
    ]
    apis(monkeypatch, stations=stations)
    assert _day(klass)["dust"] == "매우나쁨"
    assert _day(klass)["indoor_hint"] == "dust"

    # 같은 이름이 없으면 시도 평균 — PM10 (20+40)/2=30 좋음, PM2.5 (10+40)/2=25 보통 → 나쁜 쪽
    db_session.query(RegionWeather).delete()
    stations = [
        {"stationName": "원주", "pm10Value": "20", "pm25Value": "10"},
        {"stationName": "강릉", "pm10Value": "40", "pm25Value": "40"},
    ]
    apis(monkeypatch, stations=stations)
    assert _day(klass)["dust"] == "보통"


def test_교사가_고른_날씨가_이기고_지우면_자동으로_돌아간다(db_session, klass, monkeypatch):
    apis(monkeypatch)

    chosen = client.put(
        "/api/routines/weather", json={"class_id": klass.id, "date": TODAY, "sky": "흐림"}
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["sky"] == "흐림" and chosen.json()["source"] == "teacher"
    # 다시 고르면 바뀐다 — 반 × 날짜 하나다.
    client.put("/api/routines/weather", json={"class_id": klass.id, "date": TODAY, "sky": "눈"})
    assert _day(klass) == {
        "date": TODAY,
        "sky": "눈",
        "dust": "보통",
        "source": "teacher",
        "indoor_hint": "rain",
    }

    cleared = client.put(
        "/api/routines/weather", json={"class_id": klass.id, "date": TODAY, "sky": None}
    )
    assert cleared.json()["sky"] == "맑음" and cleared.json()["source"] == "auto"


def test_고를_수_없는_값과_남의_반은_거절한다(db_session, klass, monkeypatch):
    apis(monkeypatch)
    bad = client.put(
        "/api/routines/weather", json={"class_id": klass.id, "date": TODAY, "sky": "태풍"}
    )
    assert bad.status_code == 422

    stranger = Center(
        name="남의원", director_name="박", region_sido="서울특별시", region_sigungu="종로구"
    )
    db_session.add(stranger)
    db_session.flush()
    theirs = Class(
        center_id=stranger.id,
        name="별반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="박",
    )
    db_session.add(theirs)
    db_session.flush()
    other = client.put(
        "/api/routines/weather", json={"class_id": theirs.id, "date": TODAY, "sky": "비"}
    )
    assert other.status_code == 404


@pytest.mark.parametrize("status", [500, 401])
def test_바깥_API_가_실패해도_화면은_200_이고_값_없음이다(db_session, klass, monkeypatch, status):
    calls = apis(monkeypatch, status=status)

    assert _day(klass) == {
        "date": TODAY,
        "sky": None,
        "dust": None,
        "source": "none",
        "indoor_hint": None,
    }
    # 못 받은 날은 남기지 않는다 — 다음 조회 때 다시 부른다.
    assert db_session.scalar(select(func.count()).select_from(RegionWeather)) == 0
    _day(klass)
    assert len(calls) == 4


def test_키가_없으면_부르지_않는다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)
    monkeypatch.setattr(settings, "weather_mode", "real")
    monkeypatch.setattr(settings, "is_server", True)
    monkeypatch.setattr(settings, "data_go_kr_service_key", None)

    assert _day(klass)["source"] == "none"
    assert calls == []


def test_로컬_real_과_서버_mock_은_부르지_않는다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)
    monkeypatch.setattr(settings, "data_go_kr_service_key", "key")
    monkeypatch.setattr(settings, "weather_mode", "real")
    monkeypatch.setattr(settings, "is_server", False)
    assert _day(klass)["sky"] is None
    # 서버에서 mock 이면 가짜 날씨가 교사 종이에 찍힌다 — 부르지 않는다.
    monkeypatch.setattr(settings, "weather_mode", "mock")
    monkeypatch.setattr(settings, "is_server", True)
    assert _day(klass)["sky"] is None
    assert calls == []


def test_지난_날짜는_부르지_않고_교사가_고른_값을_쓴다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)
    old = "2026-11-02"

    assert _day(klass, old)["source"] == "none"
    client.put("/api/routines/weather", json={"class_id": klass.id, "date": old, "sky": "비"})
    assert _day(klass, old) == {
        "date": old,
        "sky": "비",
        "dust": None,
        "source": "teacher",
        "indoor_hint": "rain",
    }
    assert calls == []


def test_어제는_하늘만_받는다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)
    weather_of_yesterday = _day(klass, "2026-11-08")
    assert weather_of_yesterday["sky"] == "맑음" and weather_of_yesterday["dust"] is None
    assert calls == ["getVilageFcst"]


def test_하루치가_아니면_날씨를_붙이지_않는다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)
    week = client.get(
        "/api/routines", params={"class_id": klass.id, "from": "2026-11-09", "to": "2026-11-13"}
    )
    assert week.json()["weather"] is None
    assert client.get("/api/routines").json()["weather"] is None
    assert calls == []


def test_표에_없는_지역은_값_없음이다(db_session, klass, monkeypatch):
    calls = apis(monkeypatch)
    db_session.get(Center, klass.center_id).region_sigungu = "어딘가"
    db_session.flush()
    assert _day(klass)["source"] == "none"
    assert calls == []


def test_낮_예보를_한_낱말로_줄인다():
    assert weather.sky_of([0, 0], [1, 1, 3, 4, 4]) == "흐림"
    # 같은 수면 더 흐린 쪽
    assert weather.sky_of([], [1, 3]) == "구름많음"
    assert weather.sky_of([3, 0], [1]) == "눈"
    assert weather.sky_of([1, 3], [1]) == "비나 눈"
    assert weather.sky_of([2], [1]) == "비나 눈"
    assert weather.sky_of([4], [1]) == "비"
    assert weather.sky_of([], []) is None


def test_미세먼지_등급_경계():
    assert weather.dust_of(30, 15) == "좋음"
    assert weather.dust_of(31, None) == "보통"
    assert weather.dust_of(None, 36) == "나쁨"
    assert weather.dust_of(151, 0) == "매우나쁨"
    assert weather.dust_of(None, None) is None


def test_격자_표는_원_지역_고르개의_시군구를_모두_담는다():
    """`resources/weather/kma_grid.csv` 가 가입 때 고르는 230곳(어린이집 목록)을 다 덮어야 한다."""
    import csv

    from app.features.centers.registry import CSV

    with CSV.open(encoding="utf-8", newline="") as f:
        regions = {(r["sido"], r["sigungu"]) for r in csv.DictReader(f)}
    assert regions <= set(weather._grid())
    assert weather.region_of("서울", "종로") == ("서울특별시", "종로구")
