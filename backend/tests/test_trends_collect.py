"""트렌드 수집 (ADR-016).

망을 타지 않는다. 녹화한 응답을 넣는다 — 진짜로 부르면 결과가 그날 유행에 따라
달라져서 무엇을 확인한 것인지 고정할 수가 없다.
"""

import json
from datetime import date

import pytest

from app.features.trends.approved import (
    ApprovalError,
    ApprovedChannel,
    ApprovedOutlet,
    parse,
)
from app.features.trends.collect import collect
from app.features.trends.item import RawItem, load, save, week_label
from app.features.trends.sources import naver_news, youtube_uploads

CHANNEL = ApprovedChannel(name="EBS키즈", channel_id="UC_ebs", uploads_playlist_id="UU_ebs")
OUTLET = ApprovedOutlet(name="베이비뉴스", domain="ibabynews.com")


def fake(responses: dict[str, dict]):
    """url 의 끝부분으로 응답을 고른다. 부른 적 없는 주소면 테스트가 터진다."""

    def _fetch(url, params, headers):
        for key, body in responses.items():
            if url.endswith(key):
                return body
        raise AssertionError(f"준비 안 된 호출: {url}")

    return _fetch


def test_승인_채널의_업로드를_가져온다():
    fetch = fake(
        {
            "/playlistItems": {
                "items": [
                    {
                        "snippet": {
                            "title": "공룡 발굴 놀이",
                            "description": "모래에서 공룡 뼈를 찾아요",
                            "publishedAt": "2026-09-18T07:00:00Z",
                        },
                        "contentDetails": {"videoId": "vid1"},
                    }
                ]
            },
            "/videos": {
                "items": [
                    {
                        "id": "vid1",
                        "status": {"madeForKids": True},
                        "statistics": {"viewCount": "5000"},
                    }
                ]
            },
        }
    )
    items = youtube_uploads(fetch, "key", [CHANNEL])

    assert len(items) == 1
    assert items[0].title == "공룡 발굴 놀이"
    assert items[0].url == "https://www.youtube.com/watch?v=vid1"
    assert items[0].published_at == "2026-09-18"
    assert items[0].origin == "EBS키즈"
    assert items[0].facts["made_for_kids"] is True
    assert items[0].facts["view_count"] == 5000


def test_아동용_표시가_없으면_None_이다():
    """「아동용이 아니다」와 「모른다」는 다르다. False 로 바꾸지 않는다."""
    fetch = fake(
        {
            "/playlistItems": {
                "items": [
                    {
                        "snippet": {
                            "title": "제목",
                            "description": "",
                            "publishedAt": "2026-09-18T07:00:00Z",
                        },
                        "contentDetails": {"videoId": "vid1"},
                    }
                ]
            },
            "/videos": {"items": [{"id": "vid1", "status": {}, "statistics": {}}]},
        }
    )
    items = youtube_uploads(fetch, "key", [CHANNEL])

    assert items[0].facts["made_for_kids"] is None
    assert items[0].facts["view_count"] is None


def test_승인_안_된_언론사_기사는_버린다():
    fetch = fake(
        {
            "news.json": {
                "items": [
                    {
                        "title": "유아 <b>공룡</b> 놀이 인기",
                        "description": "&quot;요즘&quot; 공룡이 인기",
                        "originallink": "https://www.ibabynews.com/news/1",
                        "pubDate": "Mon, 22 Sep 2026 10:00:00 +0900",
                    },
                    {
                        "title": "출처 모를 기사",
                        "description": "",
                        "originallink": "https://spam.example.com/1",
                        "pubDate": "Mon, 22 Sep 2026 10:00:00 +0900",
                    },
                ]
            }
        }
    )
    items = naver_news(fetch, "id", "secret", ["유아 놀이"], [OUTLET])

    assert len(items) == 1
    assert items[0].origin == "ibabynews.com"
    assert items[0].published_at == "2026-09-22"


def test_기사_제목의_태그와_이스케이프를_푼다():
    """네이버는 검색어에 <b> 를 감고 따옴표를 HTML 로 바꿔서 준다."""
    fetch = fake(
        {
            "news.json": {
                "items": [
                    {
                        "title": "유아 <b>공룡</b> 놀이",
                        "description": "&quot;공룡&quot; 인기",
                        "originallink": "https://ibabynews.com/news/1",
                        "pubDate": "Mon, 22 Sep 2026 10:00:00 +0900",
                    }
                ]
            }
        }
    )
    items = naver_news(fetch, "id", "secret", ["유아 놀이"], [OUTLET])

    assert items[0].title == "유아 공룡 놀이"
    assert items[0].description == '"공룡" 인기'


def test_같은_기사가_여러_검색어에_걸려도_한_번만_담는다():
    body = {
        "items": [
            {
                "title": "기사",
                "description": "",
                "originallink": "https://ibabynews.com/news/1",
                "pubDate": "Mon, 22 Sep 2026 10:00:00 +0900",
            }
        ]
    }
    items = naver_news(fake({"news.json": body}), "id", "secret", ["가", "나"], [OUTLET])

    assert len(items) == 1


def test_한_소스가_죽어도_나머지는_모은다():
    """트렌드는 부가 기능이다. 유튜브가 죽었다고 뉴스까지 멈출 이유가 없다."""

    def fetch(url, params, headers):
        if "/playlistItems" in url:
            raise RuntimeError("quota exceeded")
        return {
            "items": [
                {
                    "title": "기사",
                    "description": "",
                    "originallink": "https://ibabynews.com/news/1",
                    "pubDate": "Mon, 22 Sep 2026 10:00:00 +0900",
                }
            ]
        }

    result = collect(
        fetch,
        parse(
            {
                "youtube_channels": [
                    {"name": "EBS키즈", "channel_id": "UC_ebs", "uploads_playlist_id": "UU_ebs"}
                ],
                "news_outlets": [{"name": "베이비뉴스", "domain": "ibabynews.com"}],
                "news_queries": ["유아 놀이"],
            }
        ),
        youtube_key="key",
        naver_id="id",
        naver_secret="secret",
    )

    assert len(result.items) == 1
    assert len(result.failures) == 1
    assert "youtube" in result.failures[0]


def test_키가_없으면_그_소스만_건너뛴다():
    result = collect(
        fake({}),
        parse(
            {
                "youtube_channels": [
                    {"name": "EBS키즈", "channel_id": "UC_ebs", "uploads_playlist_id": "UU_ebs"}
                ]
            }
        ),
        youtube_key=None,
        naver_id=None,
        naver_secret=None,
    )

    assert result.items == []
    assert "YOUTUBE_API_KEY" in result.failures[0]


def test_승인_목록의_빈_값을_거부한다():
    """빈 채로 두면 수집은 도는데 0건이고 원인이 안 보인다."""
    with pytest.raises(ApprovalError, match="channel_id"):
        parse(
            {
                "youtube_channels": [
                    {"name": "EBS키즈", "channel_id": "", "uploads_playlist_id": "UU"}
                ]
            }
        )


def test_승인_목록의_중복을_거부한다():
    with pytest.raises(ApprovalError, match="중복"):
        parse(
            {
                "news_outlets": [
                    {"name": "가", "domain": "ibabynews.com"},
                    {"name": "나", "domain": "IBabyNews.com"},
                ]
            }
        )


def test_저장한_것을_그대로_읽는다(tmp_path):
    items = [
        RawItem(
            source="youtube",
            source_id="vid1",
            title="공룡 발굴 놀이",
            description="모래놀이",
            url="https://www.youtube.com/watch?v=vid1",
            published_at="2026-09-18",
            origin="EBS키즈",
            facts={"made_for_kids": True},
        )
    ]
    path = save(items, date(2026, 9, 23), tmp_path)

    assert path.name == "2026-W39.json"
    assert load(path) == items
    # 한글이 \uXXXX 로 박히면 PR diff 를 사람이 못 읽는다. 그게 승인 절차다.
    assert "공룡 발굴 놀이" in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == 1


def test_주_번호는_월요일에_바뀐다():
    """월요일 새벽에 돈다. 일요일과 월요일이 같은 파일이면 결과가 섞인다."""
    assert week_label(date(2026, 9, 20)) == "2026-W38"  # 일
    assert week_label(date(2026, 9, 21)) == "2026-W39"  # 월
