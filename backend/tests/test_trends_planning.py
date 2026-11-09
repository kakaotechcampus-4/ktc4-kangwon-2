"""ADR-072: 생성이 읽는 트렌드 — 꺼짐 · 없음 · 깨짐은 트렌드 없이, 넘기는 것만 넘긴다."""

from datetime import date

from ssuksak.planning.application.ports import OptionalContextStatus
from ssuksak.planning.domain.trend import TrendKind

from app.features.trends.item import RawItem, save
from app.features.trends.planning import TrendContextProvider

TODAY = date(2026, 11, 8)  # W45 — W44 파일이 4주 안이다


def raw(
    n: str, title: str, origin: str = "꼬미쌤TV", source: str = "youtube", description: str = ""
) -> RawItem:
    return RawItem(source, n, title, description, f"https://x/{n}", "2026-10-20", origin)


def provider(tmp_path, items, enabled=True):
    save(items, date(2026, 10, 26), tmp_path)  # 2026-W44.json
    return TrendContextProvider(enabled=enabled, today=TODAY, directory=tmp_path)


def test_passes_only_approved_youtube_items(tmp_path):
    result = provider(
        tmp_path,
        [
            raw("a", "병뚜껑 경주 게임", description="재미있는 게임\nhttps://link\n두 번째 줄"),
            raw("b", "가을 놀이음악", origin="꼬미쌤TV"),
            raw("c", "유령들이 찾아왔어요", origin="핑크퐁"),
            raw("d", "[10분 타이머] 정리", origin="타이머 놀이터"),
            raw("e", "만들기 놀이", origin="승인 안 된 채널"),
            raw("f", "유아 놀이 유행", origin="ibabynews.com", source="naver_news"),
            raw("g", "커터로 자르는 만들기 놀이"),  # 2단 표시는 수집 PR 에서 본다
            raw("h", "환경교육 코알라 지키기"),
        ],
    ).fetch("trend")
    assert result.status is OptionalContextStatus.AVAILABLE
    assert {(i.trend_id, i.kind) for i in result.value} == {
        ("youtube:a", TrendKind.GAME),
        ("youtube:c", TrendKind.SONG),
        ("youtube:g", TrendKind.CRAFT),
    }
    game = next(i for i in result.value if i.trend_id == "youtube:a")
    assert (
        game.summary == "재미있는 게임 두 번째 줄"
        and game.week == "2026-W44"
        and game.source_name == "꼬미쌤TV"
    )


def test_disabled_missing_or_broken_files_fall_back_without_raising(tmp_path):
    assert (
        provider(tmp_path, [raw("a", "게임")], enabled=False).fetch("trend").status
        is OptionalContextStatus.UNAVAILABLE
    )
    empty = TrendContextProvider(enabled=True, today=TODAY, directory=tmp_path / "none")
    assert empty.fetch("trend").status is OptionalContextStatus.UNAVAILABLE
    (tmp_path / "2026-W45.json").write_text("{broken", encoding="utf-8")
    broken = TrendContextProvider(enabled=True, today=TODAY, directory=tmp_path)
    assert broken.fetch("trend").status is OptionalContextStatus.ERROR


def test_songs_only_from_song_channels(tmp_path):
    """ADR-072 결정 12: 노래는 승인 파일에서 채널 종류가 동요인 채널 것만 노래로 넘긴다 — 제목 낱말로 정하지 않는다."""
    result = provider(
        tmp_path,
        [
            raw("a", "가을 동요 부르기"),  # 꼬미쌤TV — 종류 없음
            raw("b", "신나는 노래 놀이", origin="EBS 키즈"),
            raw("c", "동요 메들리", origin="꿈꾸는미술 DreamingArts"),  # 종류 만들기
            raw("d", "상어 가족 동요", origin="핑크퐁"),  # 종류 동요
            raw("e", "숫자 송", origin="핑크퐁"),  # 제목 낱말 없음 → 채널 종류
            raw("f", "가을 율동 체조"),  # 율동은 신체다 — 노래가 아니다
        ],
    ).fetch("trend")
    assert {(i.trend_id, i.kind) for i in result.value} == {
        ("youtube:d", TrendKind.SONG),
        ("youtube:e", TrendKind.SONG),
        ("youtube:f", TrendKind.MOVEMENT),
    }
