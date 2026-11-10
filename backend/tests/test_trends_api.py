"""교사가 보는 트렌드 — `GET /api/trends` (api-spec.md §3-2 · ADR-016)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.features.trends import router as trends_router
from app.main import app

client = TestClient(app)
CENTER = {
    "name": "트렌드 어린이집",
    "director_name": "김원장",
    "region_sido": "강원특별자치도",
    "region_sigungu": "춘천시",
}


@pytest.fixture
def own_center(db_session, teacher):
    """이 교사의 원 id.

    `create_center` 는 `center_id IS NULL` 일 때만 붙인다 — 이미 원이 있는 교사가
    POST 하면 행만 생기고 붙지는 않는다. 그래서 **응답 id 가 아니라 /auth/me 를 본다.**
    """
    client.post("/api/centers", json=CENTER)
    center_id = client.get("/api/auth/me").json()["center_id"]
    assert center_id, "원이 붙지 않았다"
    return center_id


@pytest.fixture
def collected(tmp_path, monkeypatch):
    """그 주 파일을 흉내 낸다. 저장소 파일을 건드리지 않는다."""

    def write(week: str, items: list[dict]):
        path = tmp_path / f"{week}.json"
        path.write_text(
            json.dumps({"collected_on": "2026-10-17", "count": len(items), "items": items}),
            encoding="utf-8",
        )
        monkeypatch.setattr(trends_router, "COLLECTED_DIR", tmp_path)
        return path

    return write


def raw(
    source_id: str,
    title: str,
    published_at: str,
    description: str = "본문",
    origin: str = "꼬미쌤TV",
    source: str = "youtube",
):
    return {
        "source": source,
        "source_id": source_id,
        "title": title,
        "description": description,
        "url": f"https://youtu.be/{source_id}",
        "published_at": published_at,
        "origin": origin,
        "facts": {},
    }


def enable(center_id: int):
    assert (
        client.put(f"/api/centers/{center_id}/settings", json={"trends_enabled": True}).status_code
        == 200
    )


def test_꺼져_있으면_403(own_center, collected):
    """빈 목록이 아니라 403 이다. 「없다」와 「껐다」는 화면이 다르다."""
    collected("2026-W42", [raw("a", "놀이", "2026-10-16")])
    response = client.get("/api/trends")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TRENDS_DISABLED"


def test_켜면_그_주_자료를_준다(own_center, collected):
    collected("2026-W42", [raw("a", "가을 놀이", "2026-10-16", "낙엽을 모아요\n던져요\n버릴 줄")])
    enable(own_center)
    body = client.get("/api/trends").json()
    assert body["week"] == "2026-W42"
    assert body["items"][0]["title"] == "가을 놀이"
    # 설명은 앞 두 줄만. 교사 화면은 제목 아래 두 줄이 전부다
    assert body["items"][0]["summary"] == "낙엽을 모아요 던져요"


def test_새것부터_준다(own_center, collected):
    collected(
        "2026-W42",
        [raw("a", "옛것", "2026-10-01"), raw("b", "새것", "2026-10-16")],
    )
    enable(own_center)
    assert [i["title"] for i in client.get("/api/trends").json()["items"]] == ["새것", "옛것"]


def test_가장_최근_주를_준다(own_center, collected):
    collected("2026-W41", [raw("a", "지난주", "2026-10-09")])
    collected("2026-W42", [raw("b", "이번주", "2026-10-16")])
    enable(own_center)
    body = client.get("/api/trends").json()
    assert body["week"] == "2026-W42"
    assert [i["title"] for i in body["items"]] == ["이번주"]


def test_수집이_아직_안_돌았으면_빈_목록(own_center, tmp_path, monkeypatch):
    """오류가 아니다. 켰는데 아직 모은 게 없을 뿐이다."""
    monkeypatch.setattr(trends_router, "COLLECTED_DIR", tmp_path)
    enable(own_center)
    assert client.get("/api/trends").json() == {"week": "", "items": []}


def test_원이_없으면_404(db_session, teacher, collected):
    collected("2026-W42", [raw("a", "놀이", "2026-10-16")])
    assert client.get("/api/trends").status_code == 404


def test_승인_목록에_없는_출처는_보이지_않는다(own_center, collected):
    """ADR-016 4단: 승인 목록에서 뺀 채널 · 언론사의 지난 자료가 화면에 남지 않는다.

    생성 쪽과 같은 대조다.
    """
    collected(
        "2026-W42",
        [
            raw("a", "승인 채널", "2026-10-16"),
            raw("b", "빠진 채널", "2026-10-16", origin="승인 안 된 채널"),
            raw("c", "승인 언론사", "2026-10-15", origin="ibabynews.com", source="naver_news"),
            raw("d", "빠진 언론사", "2026-10-15", origin="example.com", source="naver_news"),
            raw("e", "도메인을 채널로", "2026-10-15", origin="ibabynews.com"),
            raw("f", "모르는 소스", "2026-10-15", source="instagram"),
        ],
    )
    enable(own_center)
    titles = [i["title"] for i in client.get("/api/trends").json()["items"]]
    assert titles == ["승인 채널", "승인 언론사"]
