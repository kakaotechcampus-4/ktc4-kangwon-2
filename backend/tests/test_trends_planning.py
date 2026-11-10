"""ADR-072: 생성이 읽는 트렌드 — 꺼짐 · 없음 · 깨짐은 트렌드 없이, 넘기는 것만 넘긴다."""

from datetime import date

from ssuksak.planning.application.ports import OptionalContextStatus
from ssuksak.planning.domain.trend import TrendKind

from app.features.trends.item import RawItem, save
from app.features.trends.planning import TrendContextProvider, book_words_for, theme_words

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


def book(isbn: str, title: str, description: str = "가짜 소개") -> RawItem:
    return RawItem("data4library", isbn, title, description, "", "2001-01-01", "도서관 정보나루")


def books(tmp_path, items, status="APPROVED"):
    # 그림책 목록 파일은 주 파일과 모양이 같고 사람이 승인한 status 가 붙는다.
    import json

    path = save(items, date(2026, 11, 2), tmp_path / "books")
    body = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**body, "status": status}), encoding="utf-8")
    return path


def test_books_matching_a_week_theme_word_come_first_in_the_story_queue(tmp_path):
    """2026-11-10 보완: 주 주제 2자 이상 낱말이 제목에 있는 그림책만, 동화 줄에서 유튜브 앞."""
    path = books(
        tmp_path,
        [
            book("9780000000001", "가짜 낙엽 그림책", "첫 줄\n" + "소개" * 150),
            book("9780000000002", "가짜 바다 그림책"),  # 주제 낱말 없음
            book("9780000000003", "가짜 산 그림책"),  # 「산」은 한 글자라 대조하지 않는다
        ],
    )
    save([raw("s", "가짜 동화 읽어주기")], date(2026, 10, 26), tmp_path)
    result = TrendContextProvider(
        enabled=True,
        today=TODAY,
        directory=tmp_path,
        book_words=theme_words("낙엽을 · 산 놀이"),
        books_file=path,
    ).fetch("trend")
    stories = [i for i in result.value if i.kind is TrendKind.STORY]
    assert [i.trend_id for i in stories] == ["data4library:9780000000001", "youtube:s"]
    first = stories[0]
    assert first.source_name == "도서관 정보나루" and first.week == "2026-W45"
    assert first.summary.startswith("첫 줄 소개") and len(first.summary) == 200
    # 조사는 떼고 일반어 · 한 글자는 뺀다
    assert theme_words("우리 동네와 가을과 열매를 · 산 놀이") == ("동네", "가을", "열매")


def test_books_need_words_and_never_break_generation(tmp_path):
    path = books(tmp_path, [book("9780000000001", "가짜 낙엽 그림책")])

    def fetch(books_file=path, **kwargs):
        options = {"enabled": True, "book_words": ("낙엽",), **kwargs}
        return TrendContextProvider(
            today=TODAY, directory=tmp_path, books_file=books_file, **options
        ).fetch("trend")

    # 유튜브 주 파일이 없어도 맞는 그림책만으로 AVAILABLE
    assert fetch().status is OptionalContextStatus.AVAILABLE
    # 낱말이 없으면(놀이 중심 월간) · 원이 껐으면 그림책을 넘기지 않는다
    assert fetch(book_words=()).status is OptionalContextStatus.UNAVAILABLE
    assert fetch(enabled=False).status is OptionalContextStatus.UNAVAILABLE
    # 그림책 파일이 없거나 깨져도 유튜브 트렌드는 그대로
    save([raw("a", "병뚜껑 경주 게임")], date(2026, 10, 26), tmp_path)
    assert [i.trend_id for i in fetch(books_file=tmp_path / "none.json").value] == ["youtube:a"]
    # 승인 전(PENDING_HUMAN_REVIEW) 목록은 쓰지 않는다(CLAUDE.md §8)
    pending = books(
        tmp_path / "p", [book("9780000000001", "가짜 낙엽 그림책")], "PENDING_HUMAN_REVIEW"
    )
    assert [i.trend_id for i in fetch(books_file=pending).value] == ["youtube:a"]
    path.write_text("{broken", encoding="utf-8")
    assert [i.trend_id for i in fetch().value] == ["youtube:a"]


def test_related_word_groups_widen_book_words_only_when_approved(tmp_path):
    """관련 낱말 묶음: APPROVED 일 때만, 묶음 이름(한 글자도) · 묶음 낱말이 주제에 있으면 넓힌다."""
    import json

    path = tmp_path / "related.json"
    groups = [
        {"name": "봄", "words": ["새싹", "나비", "꽃"]},
        {"name": "가을", "words": ["가을", "낙엽", "열매"]},
        {"name": "우주", "words": ["우주", "로켓"]},
    ]
    path.write_text(json.dumps({"status": "APPROVED", "groups": groups}), encoding="utf-8")
    assert book_words_for("봄 열매", path) == ("열매", "새싹", "나비", "가을", "낙엽")
    path.write_text(
        json.dumps({"status": "PENDING_HUMAN_REVIEW", "groups": groups}), encoding="utf-8"
    )
    assert book_words_for("봄 열매", path) == ("열매",)
    path.write_text("{broken", encoding="utf-8")
    assert book_words_for("봄 열매", path) == ("열매",)
    assert book_words_for("봄 열매", tmp_path / "none.json") == ("열매",)
