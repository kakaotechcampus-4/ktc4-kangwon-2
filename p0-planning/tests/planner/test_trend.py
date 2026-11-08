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
    split_trend_applied,
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
