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
            "/search/v1/news": {
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
            "/search/v1/news": {
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
    items = naver_news(fake({"/search/v1/news": body}), "id", "secret", ["가", "나"], [OUTLET])

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


def test_뉴스는_API_HUB_주소와_헤더로_부른다():
    """네이버가 2026 에 검색 API 를 네이버 클라우드 플랫폼으로 옮겼다.

    옛 주소(openapi.naver.com)와 옛 헤더(X-Naver-Client-*)로 부르면 새 키로는
    401 errorCode 024 가 온다. 되돌아가면 뉴스가 통째로 0건이 되는데, 수집은
    「하나가 죽어도 나머지는 계속한다」라서 조용히 유튜브만 모은다.
    """
    seen: dict[str, object] = {}

    def _fetch(url, params, headers):
        seen["url"] = url
        seen["headers"] = dict(headers)
        return {"items": []}

    naver_news(_fetch, "id", "secret", ["가"], [OUTLET])
    assert seen["url"] == "https://naverapihub.apigw.ntruss.com/search/v1/news"
    assert seen["headers"] == {
        "X-NCP-APIGW-API-KEY-ID": "id",
        "X-NCP-APIGW-API-KEY": "secret",
    }


def test_설명에서_링크와_해시태그_줄을_버린다():
    """유튜브 설명은 놀이 서술 뒤에 구독 안내·SNS 링크·해시태그 더미가 붙는다.

    실측 315건에서 설명이 전체 글자의 92% 였고 링크가 1,069개였다. 그대로 두면
    사람이 읽는 승인 PR 이 매주 수천 줄이 되고 3단 Judge 토큰도 그만큼 나간다.
    **낱말이 아니라 줄 단위로만 버린다** — 원문을 고치면 「왜 걸렀나」를 설명 못 한다.
    """
    from app.features.trends.sources import _body

    kept = _body(
        "신문지로 공을 만들어요\n"
        "바구니에 던지면 됩니다\n"
        "\n"
        "#어린이집 #유치원\n"
        "------------------\n"
        "알짜닷컴 : http://www.aalzza.com\n"
    )
    assert kept == "신문지로 공을 만들어요\n바구니에 던지면 됩니다"


def test_링크가_붙어_있어도_동작_설명은_남긴다():
    """위험한 동작과 링크가 한 줄에 같이 오는 경우가 있다.

    줄을 통째로 버리면 그 동작이 승인 PR 에서 사라져, 사람도 3단 Judge 도 못 본다.
    링크만 걷어낸다 — 영상 주소는 RawItem.url 에 따로 있다.
    """
    from app.features.trends.sources import _body

    assert _body("아이를 높은 곳에서 밀어 떨어뜨려요 https://example.com/demo") == (
        "아이를 높은 곳에서 밀어 떨어뜨려요"
    )
    # 안내 줄은 링크를 빼면 남는 글이 거의 없다 — 그건 버린다
    assert _body("알짜닷컴 : http://www.aalzza.com") == ""


def test_설명을_길다고_자르지_않는다():
    """3단이 보는 것은 놀이 서술 전체다 (ADR-016).

    위험한 동작(밀기·목·숨 참기·높은 곳)은 설명 뒤쪽에 나온다. 읽기 편하자고
    뒤를 자르면 사람도 Judge 도 그 뒤를 못 본다.
    """
    from app.features.trends.sources import _body

    long_text = "앞쪽 설명\n" * 200 + "마지막에 높은 곳에서 뛰어내려요"
    assert _body(long_text).endswith("마지막에 높은 곳에서 뛰어내려요")


def test_실패_기록에_키를_적지_않는다():
    """유튜브는 키를 주소에 담는다(`?key=...`).

    httpx 오류 메시지에 그 주소가 통째로 들어 있어서, 실패 기록을 그대로 옮기면
    Actions 로그·PR 본문·서버 cron 로그에 키가 적힌다. 한 번 적히면 지워도
    기록이 남으므로 만드는 자리에서 가린다.
    """
    from app.features.trends.collect import _safe

    hidden = _safe(
        RuntimeError(
            "Client error '403' for url "
            "'https://www.googleapis.com/youtube/v3/videos?id=a&key=AIzaSyREAL_SECRET'"
        )
    )
    assert "AIzaSyREAL_SECRET" not in hidden
    assert "key=***" in hidden
    assert "403" in hidden  # 무엇이 실패했는지는 남아야 한다


def test_해시태그_줄_검사가_역추적으로_멈추지_않는다():
    """`(?:#\\S+\\s*)+` 같은 정규식은 `#a#a#a…` 한 줄에 역추적이 터진다.

    수집은 15분 timeout 안에서 돌고, 설명 한 줄 때문에 그 주 수집이 통째로
    날아가면 안 된다. 낱말로 쪼개 한 번만 훑는 방식인지 시간으로 지킨다.
    """
    import time

    from app.features.trends.sources import _body

    started = time.monotonic()
    _body("#a" * 200 + " 놀이")
    assert time.monotonic() - started < 1.0
