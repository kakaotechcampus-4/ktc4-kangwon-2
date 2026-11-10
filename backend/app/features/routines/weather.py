"""일지 날씨 — 원 지역의 그날 하늘 · 미세먼지 (ADR-089 · docs/api-spec.md §10-1 「그날 날씨」).

**부가 기능이다. 실패해도 오류를 내지 않는다.** 키가 없거나 · 바깥 API 가 죽었거나 · 지역을 표에서
못 찾거나 · 지난 날짜라 예보가 없으면 「값 없음」(None)이다. 일과 기록 화면과 종이는 그대로 돈다.

- 하늘: 기상청 단기예보(getVilageFcst). 그날 02시 발표분의 낮(09~18시) 예보를 한 낱말로 줄인다.
- 미세먼지: 에어코리아 시도별 실시간 측정(getCtprvnRltmMesureDnsty). 시군구 이름과 같은
  측정소가 있으면 그 값, 없으면 시도 측정소 평균. **오늘만** — 실시간 값이라 지난날 것은 없다.
- 교사가 고른 하늘(`RoutineWeather`)이 있으면 그것이 이긴다. 미세먼지는 고르지 않는다
  (종이에 안 나간다).
- 같은 지역 · 같은 날은 한 번만 부른다 — 받은 값을 `RegionWeather` 에 남긴다.
  한쪽만 받았으면 못 받은 쪽만 다음 조회 때 다시 부른다. 남길 때 부르는 쪽 세션을 커밋하지 않는다.

**망을 타는 곳은 `_client()` 하나다.** LLM_MODE 와 같은 규칙이다.

    real   서버(IS_SERVER)에서 키가 있을 때만 부른다. 로컬 real 은 막는다 — 키가 팀 공유다
    mock   서버 밖에서는 가짜 응답(`_fake`)을 쓴다. 서버에서는 부르지 않는다(값 없음)
           — 가짜 날씨가 교사 종이에 진짜처럼 찍히면 안 된다

테스트는 `transport` 에 가짜 전송을 끼운다.
"""

from __future__ import annotations

import csv
import datetime
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from statistics import mean
from typing import Literal
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.features.centers.models import Center, Class
from app.features.routines.models import DUSTS, RegionWeather, RoutineWeather

logger = logging.getLogger("app.server")

KST = ZoneInfo("Asia/Seoul")
KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
AIR_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
# 교사 화면이 기다리는 시간이다. 두 API 를 차례로 부르므로 최악은 이것의 두 배다.
TIMEOUT = 3.0
GRID_CSV = Path(__file__).resolve().parents[3] / "resources" / "weather" / "kma_grid.csv"

# 기상청 02시 발표분은 02:10 뒤에 나온다. 그 전에는 오늘 것을 부르지 않는다.
FIRST_RELEASE = datetime.time(2, 15)
DAYTIME = range(9, 19)
SKY_CODES = {1: "맑음", 3: "구름많음", 4: "흐림"}
# 강수형태: 1 비 · 2 비/눈 · 3 눈 · 4 소나기 (단기예보 활용가이드 「코드값 정보」)
RAIN, RAIN_SNOW, SNOW, SHOWER = 1, 2, 3, 4
# 등급 경계(이하) — 좋음 · 보통 · 나쁨, 넘으면 매우나쁨. 에어코리아 「대기질 예보 등급」(㎍/㎥)
PM10_CUTS = (30, 80, 150)
PM25_CUTS = (15, 35, 75)

# 에어코리아 `sidoName`.
AIR_SIDO = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}
# 예전 직접 입력 원은 줄임말로 적혀 있다 — 화면의 `normalizeProvince` 와 같은 표다.
SIDO_ALIASES = {short: full for full, short in AIR_SIDO.items()} | {
    "서울시": "서울특별시",
    "세종시": "세종특별자치시",
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "제주도": "제주특별자치도",
}

Source = Literal["auto", "teacher", "none"]
IndoorHint = Literal["rain", "dust"]

# 테스트가 가짜 전송을 끼우는 자리다. None 이면 mock 은 `_fake`, real 은 진짜 망이다.
transport: httpx.BaseTransport | None = None


@dataclass(frozen=True)
class DayWeather:
    date: datetime.date
    sky: str | None
    dust: str | None
    source: Source
    indoor_hint: IndoorHint | None


def day_weather(session: Session, class_id: int, day: datetime.date) -> DayWeather:
    """그 반 그날의 날씨. 교사 값 > 자동 값 > 값 없음. 실패해도 예외를 내지 않는다."""
    chosen = session.scalar(
        select(RoutineWeather.sky).where(
            RoutineWeather.class_id == class_id, RoutineWeather.date == day
        )
    )
    region = session.execute(
        select(Center.region_sido, Center.region_sigungu)
        .join(Class, Class.center_id == Center.id)
        .where(Class.id == class_id)
    ).first()
    auto_sky, dust = _auto(session, *region, day) if region else (None, None)
    sky = chosen or auto_sky
    source: Source = "teacher" if chosen else "auto" if auto_sky else "none"
    return DayWeather(day, sky, dust, source, indoor_hint(sky, dust))


def stamp_confirmed_weather(session: Session, doc) -> None:
    """일일 보육일지를 확정할 때 그날 날씨를 문서에 박는다. 종이가 이 값을 싣는다(ADR-089 보완).

    확정한 종이는 확정 뒤에 바뀌면 안 된다 — 교사가 날씨를 고쳐도 확정본은 확정 때 값이다.
    새 값을 싣고 싶으면 확정을 풀고 다시 확정한다. 다른 종류 문서는 날씨 칸이 없어 그대로 둔다.
    """
    if doc.kind == "dailyLog":
        doc.weather = day_weather(session, doc.class_id, doc.start_date).sky or ""


def indoor_hint(sky: str | None, dust: str | None) -> IndoorHint | None:
    """대체놀이 칩을 띄울 까닭. 비 · 눈이 먼저다 — 비 오는 날은 미세먼지와 상관없이 실내다."""
    if sky in ("비", "눈", "비나 눈"):
        return "rain"
    if dust in ("나쁨", "매우나쁨"):
        return "dust"
    return None


def sky_of(ptys: list[int], skies: list[int]) -> str | None:
    """낮 시간 예보를 한 낱말로. 한 시간이라도 비 · 눈이 오면 그쪽, 아니면 가장 많은 하늘 상태.

    같은 수면 더 흐린 쪽이다 — 맑다고 했다가 흐리면 교사가 더 자주 고치게 된다.
    """
    rain = any(p in (RAIN, SHOWER) for p in ptys)
    snow = SNOW in ptys
    if RAIN_SNOW in ptys or (rain and snow):
        return "비나 눈"
    if snow:
        return "눈"
    if rain:
        return "비"
    counts = Counter(s for s in skies if s in SKY_CODES)
    if not counts:
        return None
    return SKY_CODES[max(counts, key=lambda s: (counts[s], s))]


def dust_of(pm10: float | None, pm25: float | None) -> str | None:
    """PM10 · PM2.5 등급 중 나쁜 쪽. 둘 다 없으면 None."""
    grades = [
        sum(value > cut for cut in cuts)
        for value, cuts in ((pm10, PM10_CUTS), (pm25, PM25_CUTS))
        if value is not None
    ]
    return DUSTS[max(grades)] if grades else None


def region_of(sido: str, sigungu: str) -> tuple[str, str] | None:
    """원 지역 → 격자 표의 이름. 예전 직접 입력(「강원」 · 「춘천」)도 받는다. 못 찾으면 None."""
    sido = sido.strip()
    sido = SIDO_ALIASES.get(sido, sido)
    sigungu = sigungu.strip()
    for name in (sigungu, f"{sigungu}시", f"{sigungu}군", f"{sigungu}구"):
        if (sido, name) in _grid():
            return sido, name
    return None


@cache
def _grid() -> dict[tuple[str, str], tuple[int, int]]:
    with GRID_CSV.open(encoding="utf-8", newline="") as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        return {(r["sido"], r["sigungu"]): (int(r["nx"]), int(r["ny"])) for r in rows}


def _auto(
    session: Session, sido: str, sigungu: str, day: datetime.date
) -> tuple[str | None, str | None]:
    """남긴 값이 있으면 그것, 모자란 쪽만 부른다.

    한쪽만 받은 날은 받은 쪽을 남기고, 못 받은 쪽은 다음 조회 때 그쪽만 다시 부른다.
    받은 쪽은 지역 · 날짜마다 한 번만 부른다.
    """
    region = region_of(sido, sigungu)
    if region is None:
        return None, None
    saved = session.execute(
        select(RegionWeather.sky, RegionWeather.dust).where(
            RegionWeather.region_sido == region[0],
            RegionWeather.region_sigungu == region[1],
            RegionWeather.date == day,
        )
    ).first()
    sky, dust = saved or (None, None)
    want_sky, want_dust = _wanted(day)
    want_sky = want_sky and sky is None
    want_dust = want_dust and dust is None
    if not (want_sky or want_dust):
        return sky, dust
    client = _client()
    if client is None:
        return sky, dust
    key = _service_key()
    with client:
        if want_sky:
            sky = _safely("kma", lambda: _fetch_sky(client, key, _grid()[region], day))
        if want_dust:
            dust = _safely("air", lambda: _fetch_dust(client, key, *region))
    if (want_sky and sky) or (want_dust and dust):
        try:
            _save(session, region, day, sky, dust)
        except SQLAlchemyError as error:
            # 못 남겨도 받은 값은 이번 화면에 쓴다. 다음 조회에 다시 부를 뿐이다.
            logger.warning("weather_save_failed error=%s", type(error).__name__)
    return sky, dust


def _wanted(day: datetime.date) -> tuple[bool, bool]:
    """(하늘, 미세먼지) 를 부를 수 있는 날인가."""
    now = _now()
    today = now.date()
    # 기상청 02시 발표분이 나오기 전이다.
    if day == today and now.time() < FIRST_RELEASE:
        return False, False
    # 단기예보는 하루 전 발표분까지만 준다. 그보다 지난날 · 앞날은 부르지 않는다.
    # 미세먼지는 실시간 값이라 오늘만이다.
    return day in (today, today - datetime.timedelta(days=1)), day == today


def _save(
    session: Session, region: tuple[str, str], day: datetime.date, sky: str | None, dust: str | None
) -> None:
    """받은 값을 남긴다. **부르는 쪽 세션을 커밋하지 않는다** — 따로 연 세션에서 커밋한다.

    내보내기 · 일과 조회가 이 함수를 지난다. 그 요청이 하던 일을 날씨가 대신 커밋하면 안 된다.
    같은 순간 두 교사가 같은 지역을 열면 둘 다 부른다. 칸마다 먼저 넣은 값을 남긴다.
    """
    stmt = insert(RegionWeather).values(
        region_sido=region[0], region_sigungu=region[1], date=day, sky=sky, dust=dust
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["region_sido", "region_sigungu", "date"],
        set_={
            "sky": func.coalesce(RegionWeather.sky, stmt.excluded.sky),
            "dust": func.coalesce(RegionWeather.dust, stmt.excluded.dust),
        },
    )
    # 운영에서는 연결을 하나 더 쓴다. 시험은 한 연결 안의 savepoint 라 시험 끝에 같이 되감긴다.
    with Session(session.get_bind(), join_transaction_mode="create_savepoint") as own:
        own.execute(stmt)
        own.commit()


def _service_key() -> str:
    """포털이 주는 키 둘(Encoding · Decoding) 어느 쪽을 넣어도 된다.

    httpx 가 주소에 실을 때 한 번 인코딩한다. Encoding 키를 그대로 실으면 두 번 인코딩돼
    SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 난다 — 그래서 먼저 푼다.
    Decoding 키에는 「%」가 없어 그대로다.
    """
    return unquote(settings.data_go_kr_service_key or "")


def _now() -> datetime.datetime:
    """테스트가 시각을 고정하는 자리다."""
    return datetime.datetime.now(KST)


def _client() -> httpx.Client | None:
    if settings.weather_mode == "real":
        if not (settings.is_server and settings.data_go_kr_service_key):
            return None
        return httpx.Client(timeout=TIMEOUT, transport=transport)
    if settings.is_server:
        return None
    return httpx.Client(timeout=TIMEOUT, transport=transport or httpx.MockTransport(_fake))


class Refused(Exception):
    """API 가 거절했다. 까닭은 포털이 준 짧은 부호다(키가 아니다) — 로그에 그대로 남긴다."""


def _safely(api: str, call: Callable[[], str | None]) -> str | None:
    try:
        return call()
    except Exception as error:
        # 응답 본문 · 키를 찍지 않는다. httpx 예외의 글에는 serviceKey 가 든 주소가 있다 —
        # 예외 이름과 포털 부호만 남긴다.
        reason = str(error) if isinstance(error, Refused) else "-"
        logger.warning(
            "weather_fetch_failed api=%s error=%s reason=%s", api, type(error).__name__, reason
        )
        return None


def _items(response: httpx.Response) -> list[dict]:
    """두 API 모두 `response.header.resultCode` 가 00 이어야 정상이다.

    [실측 2026-11-10] 키가 없거나 등록되지 않았으면 포털 문지기가 401 · 403 과 함께 JSON 을 준다 —
    `{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NULL", …}}}`.
    그 부호를 까닭으로 남긴다. JSON 이 아니면 `.json()` 이 예외를 내고 `_safely` 가 받는다.
    """
    try:
        body = response.json()
    except ValueError:
        response.raise_for_status()
        raise
    gate = body.get("OpenAPI_ServiceResponse")
    if gate:
        raise Refused(str(gate.get("cmmMsgHeader", {}).get("errMsg", response.status_code))[:60])
    response.raise_for_status()
    body = body["response"]
    if body["header"]["resultCode"] != "00":
        raise Refused(f"resultCode={body['header']['resultCode']}"[:60])
    items = body["body"]["items"]
    return items["item"] if isinstance(items, dict) else items


def _fetch_sky(
    client: httpx.Client, key: str, grid: tuple[int, int], day: datetime.date
) -> str | None:
    ymd = f"{day:%Y%m%d}"
    items = _items(
        client.get(
            KMA_URL,
            params={
                "serviceKey": key,
                "dataType": "JSON",
                "pageNo": "1",
                # 02시 발표분은 사흘치다. 그날 낮까지가 앞쪽 300줄 안에 든다.
                "numOfRows": "1000",
                "base_date": ymd,
                "base_time": "0200",
                "nx": str(grid[0]),
                "ny": str(grid[1]),
            },
        )
    )
    daytime = [i for i in items if i["fcstDate"] == ymd and int(i["fcstTime"][:2]) in DAYTIME]
    ptys = [int(float(i["fcstValue"])) for i in daytime if i["category"] == "PTY"]
    skies = [int(float(i["fcstValue"])) for i in daytime if i["category"] == "SKY"]
    return sky_of(ptys, skies)


def _fetch_dust(client: httpx.Client, key: str, sido: str, sigungu: str) -> str | None:
    items = _items(
        client.get(
            AIR_URL,
            params={
                "serviceKey": key,
                "returnType": "json",
                "pageNo": "1",
                "numOfRows": "1000",
                "sidoName": AIR_SIDO[sido],
                "ver": "1.0",
            },
        )
    )
    # 서울은 측정소 이름이 구 이름이다. 다른 곳은 대개 동 이름이라 시도 평균으로 간다.
    mine = [i for i in items if i.get("stationName") in (sigungu, sigungu[:-1])] or items
    return dust_of(_mean(mine, "pm10Value"), _mean(mine, "pm25Value"))


def _mean(items: list[dict], field: str) -> float | None:
    """점검 중인 측정소는 「-」 · 빈 값을 준다. 숫자만 평균한다."""
    values = []
    for item in items:
        try:
            values.append(float(item.get(field)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return mean(values) if values else None


def _fake(request: httpx.Request) -> httpx.Response:
    """mock 모드의 가짜 응답 — 맑음 · 보통. 서버 밖에서만 쓴다 (`_client`)."""
    ok = {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"}
    if request.url.path.endswith("getVilageFcst"):
        day = request.url.params["base_date"]
        items = [
            {"category": category, "fcstDate": day, "fcstTime": f"{hour:02d}00", "fcstValue": value}
            for hour in DAYTIME
            for category, value in (("SKY", "1"), ("PTY", "0"))
        ]
        return httpx.Response(
            200, json={"response": {"header": ok, "body": {"items": {"item": items}}}}
        )
    station = {"stationName": "가짜측정소", "pm10Value": "40", "pm25Value": "20"}
    return httpx.Response(200, json={"response": {"header": ok, "body": {"items": [station]}}})
