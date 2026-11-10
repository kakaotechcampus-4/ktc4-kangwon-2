"""ADR-072: 트렌드 Rule · 응답 확인."""

import json
from datetime import date

import pytest

from ssuksak.planning.application.ports import OptionalContextResult, OptionalContextStatus
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.domain.teacher_memo import TEACHER_MEMO_EVIDENCE, without_memo_evidence
from ssuksak.planning.domain.trend import TREND_CONTEXT, TrendItem, TrendKind, select_trends, trend_kind
from ssuksak.planning.planner.trend import (
    lyric_hits,
    split_trend_applied,
    trend_name_hits,
    trend_share_excess,
    usable_trends,
    with_trend_evidence,
)

TODAY = date(2026, 11, 8)  # 2026-W45


def item(n: int, kind=TrendKind.GAME, week="2026-W44", day=1) -> TrendItem:
    return TrendItem(f"youtube:v{n}", kind, f"놀이 {n}", "", "꼬미쌤TV", week, date(2026, 10, day))


def test_kind_comes_from_title_then_channel():
    assert trend_kind("동요 '허수아비'｜가을 동요") is TrendKind.SONG
    assert trend_kind("떡 먹는 호랑이 접기｜미술놀이") is TrendKind.CRAFT
    assert trend_kind("병뚜껑 경주 게임") is TrendKind.GAME
    assert trend_kind("낙엽이 변신해요! - 가을 놀이 3가지") is TrendKind.PLAY
    assert trend_kind("[놀이음악] 가을 놀이음악") is None
    assert trend_kind("[10분 타이머] 정리 타이머", TrendKind.SONG) is None
    assert trend_kind("유령들이 찾아왔어요", TrendKind.SONG) is TrendKind.SONG
    assert trend_kind("유아 환경교육｜코알라 지키기") is None
    assert trend_kind("완벽 위장의 달인｜명탐정 피트｜[EBS놀이터]") is None  # 프로그램 꼬리표
    assert trend_kind("영어로 어떻게 말할까?ㅣKBS 방송") is None  # 「방송」의 「송」
    assert trend_kind("뽀요TV 시청자영상 | 694차 당첨자", TrendKind.SONG) is None


def test_select_keeps_recent_weeks_once_and_alternates_kinds():
    songs = [item(n, TrendKind.SONG, day=20) for n in range(10)]
    old = item(99, week="2026-W40")  # 4주 밖
    again = item(50, week="2026-W45")
    picked = select_trends([*songs, item(50), again, old, item(51, TrendKind.STORY)], TODAY, limit=4)
    assert [i.kind for i in picked] == [TrendKind.STORY, TrendKind.SONG, TrendKind.GAME, TrendKind.SONG]
    assert next(i for i in picked if i.trend_id == "youtube:v50").week == "2026-W45"
    assert all(i.trend_id != "youtube:v99" for i in picked)


def test_trend_applied_must_name_passed_addresses_and_trends():
    items = (item(1), item(2))
    addresses = ("together[0]", "together[1]")
    body = {"theme": "가을", "trend_applied": [{"address": "together[1]", "trend_id": "youtube:v2"}]}
    content, applied = split_trend_applied(json.dumps(body), addresses, items)
    assert json.loads(content) == {"theme": "가을"} and applied == {"together[1]": items[1]}
    for bad in (
        [{"address": "together[9]", "trend_id": "youtube:v1"}],
        [{"address": "together[0]", "trend_id": "youtube:nope"}],
        [{"address": "together[0]", "trend_id": "youtube:v1"}, {"address": "together[0]", "trend_id": "youtube:v2"}],
    ):
        with pytest.raises(InvalidDomainValueError):
            split_trend_applied(json.dumps({"trend_applied": bad}), addresses, items)
    with pytest.raises(InvalidDomainValueError):
        split_trend_applied(json.dumps({"theme": "가을"}), addresses, items)
    assert split_trend_applied('{"theme": "가을"}', None, items) == ('{"theme": "가을"}', {})


def test_share_excess_counts_each_list_in_address_order():
    addresses = tuple(f"{s}[{i}]" for s in ("together", "free_play") for i in range(4))
    applied = {a: item(1) for a in ("together[3]", "together[0]", "together[2]", "free_play[1]")}
    assert trend_share_excess(applied, addresses, lambda a: a.split("[")[0]) == ("together[3]",)


def test_name_hits_find_channel_words_except_the_teachers_memo():
    day = date(2026, 10, 1)
    pinkfong = TrendItem("youtube:p", TrendKind.SONG, "상어 가족", "", "핑크퐁", "2026-W44", day, ("핑크퐁", "아기상어"))
    ebs = TrendItem("youtube:e", TrendKind.PLAY, "숨바꼭질", "", "EBS 키즈", "2026-W44", day, ("EBS",))
    texts = {"together[0]": "아기 상어 율동", "together[1]": "ebs 체조 따라 하기", "free_play[0]": "상어 그림 그리기"}
    assert trend_name_hits(texts, (pinkfong, ebs)) == ("together[0]", "together[1]")
    assert trend_name_hits(texts, (pinkfong, ebs), memo="아기상어 율동을 넣어 주세요") == ("together[1]",)
    assert trend_name_hits(texts, ()) == ()
    with pytest.raises(InvalidDomainValueError):
        TrendItem("youtube:x", TrendKind.SONG, "t", "", "s", "2026-W44", day, (" ",))


def test_trend_evidence_is_a_marker_and_absent_context_means_no_trend():
    trend = item(1)
    evidence = with_trend_evidence((TEACHER_MEMO_EVIDENCE,), trend)
    assert evidence[-1].source_type is EvidenceSourceType.TREND and evidence[-1].source_version == "2026-W44"
    assert with_trend_evidence(evidence, trend) == evidence
    assert without_memo_evidence(evidence) == ()
    ok = OptionalContextResult(TREND_CONTEXT, OptionalContextStatus.AVAILABLE, (trend,))
    assert usable_trends((ok,)) == (trend,)
    assert usable_trends((OptionalContextResult(TREND_CONTEXT, OptionalContextStatus.ERROR),)) == ()
    assert usable_trends(()) == ()


# ADR-072 결정 12: 가사를 옮기지 않는다 — 따옴표 · 줄바꿈으로 묶인 글이 노래 가사 꼴이면 그 후보를 고쳐 쓴다.
LYRICS = {
    "곰 세 마리 — 반복 낱말": "곰 세 마리 율동: “곰 세 마리가 한 집에 있어 아빠곰 엄마곰 애기곰 아빠곰은 뚱뚱해 엄마곰은 날씬해 애기곰은 너무 귀여워”를 부른다.",
    "산토끼 — 같은 구절 반복": "산토끼 놀이: ‘산토끼 토끼야 어디를 가느냐 깡충깡충 뛰면서 어디를 가느냐’ 노래에 맞춰 뛴다.",
    "나비야 — 같은 낱말이 잇달아": "나비 놀이: 「나비야 나비야 이리 날아오너라 노랑나비 흰나비 춤을 추며 오너라」를 함께 부른다.",
    "생일 노래 — 줄바꿈": "생일 축하 놀이: 함께 부른다.\n생일 축하합니다\n생일 축하합니다\n사랑하는 우리 친구\n생일 축하합니다",
    "반짝반짝 — 곧은 따옴표": '별 놀이: "반짝반짝 작은 별 아름답게 비치네 동쪽 하늘에서도 서쪽 하늘에서도 반짝반짝 작은 별"을 부른다.',
}
NOT_LYRICS = {
    "노래 제목만": "곰 세 마리 율동: 동요 「곰 세 마리」에 맞춰 아빠 · 엄마 · 아기 곰 동작을 흉내 낸다.",
    "짧은 후렴": "나비 놀이: ‘나비야 나비야’ 부분에서 두 팔을 펄럭인다.",
    "교사 발문": "낙엽 놀이: “나뭇잎은 무슨 색일까? 빨간 나뭇잎과 노란 나뭇잎을 찾아볼까?” 하고 묻는다.",
    "따옴표 밖의 되풀이 설명": "낙엽 놀이: 낙엽을 모아 낙엽 왕관을 만들고, 낙엽 비를 뿌리고, 낙엽 왕관을 쓰고 낙엽 비 속을 걷는다.",
    "짝이 어긋난 따옴표": "도구 놀이: 3주 ‘도구를 움직이는 힘'에서는 도구를 움직이는 다양한 힘을 알아보고 도구를 움직이는 방법을 놀이로 표현해 본다. 4주 ‘안전한 도구 사용’",
    "여러 줄 순서": "낙엽 놀이: 순서\n1. 낙엽을 모은다\n2. 낙엽으로 모양을 만든다\n3. 종이에 붙인다",
}


@pytest.mark.parametrize("text", LYRICS.values(), ids=LYRICS.keys())
def test_lyric_hits_find_quoted_or_line_broken_lyrics(text):
    assert lyric_hits({"together[0]": text}) == ("together[0]",)


@pytest.mark.parametrize("text", NOT_LYRICS.values(), ids=NOT_LYRICS.keys())
def test_lyric_hits_leave_titles_questions_and_plain_prose(text):
    assert lyric_hits({"together[0]": text}) == ()


def test_lyric_hits_known_false_positive_and_misses():
    """결정적 검사의 한계를 고정한다. 바꾸려면 이 테스트를 같이 고친다(ADR-072 결정 12)."""
    # 오탐: 따옴표 안의 구령 · 말놀이도 같은 구절을 되풀이하면 가사로 본다 — 고쳐 쓰기 한 번이면 끝난다.
    chant = "걷기 놀이: “하나 둘 하나 둘 앞으로 걸어요 하나 둘 하나 둘 뒤로 걸어요”라고 말하며 걷는다."
    assert lyric_hits({"a": chant}) == ("a",)
    # 오탐: 짧은 줄 목록이 같은 머리말을 되풀이해도 가사로 본다(후보 글에 목록 줄바꿈이 드물어 두었다).
    listing = "영역:\n의사소통 - 듣기와 말하기 - 바른 태도로 듣고 말한다.\n의사소통 - 듣기와 말하기 - 생각을 말한다."
    assert lyric_hits({"a": listing}) == ("a",)
    # 곧은 작은따옴표는 보지 않는다 — 문단을 건너 짝이 지어진다. 그래서 그 안의 가사도 놓친다.
    apostrophe = "주제: '생활도구' 주제로 도구를 움직이는 힘을 알아보고, 도구를 움직이는 힘'에서는 도구를 움직이는 다양한 힘을 본다."
    assert lyric_hits({"a": apostrophe}) == ()
    # 놓침: 따옴표 · 줄바꿈 없이 본문에 풀어 쓴 가사.
    inline = "곰 놀이: 곰 세 마리가 한 집에 있어 아빠곰 엄마곰 애기곰 아빠곰은 뚱뚱해 엄마곰은 날씬해 하고 부른다."
    assert lyric_hits({"a": inline}) == ()
    # 놓침: 되풀이 없는 가사 한 줄, 20자 아래 인용.
    assert lyric_hits({"a": "노래: “학교 종이 땡땡땡 어서 모이자 선생님이 우리를 기다리신다”"}) == ()
    assert lyric_hits({"a": "노래: 「퐁당퐁당 돌을 던지자」"}) == ()
