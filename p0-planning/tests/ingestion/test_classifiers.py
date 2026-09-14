"""연령 · Section · Setting · 대체안 분리 회귀 (L1).

Case는 전부 실제 Corpus 원문이다. `docs/analysis/activity-v0-2-1-setting-audit.md`가
전수 재검증하며 확정한 규칙을 고정한다.
"""

from __future__ import annotations

import pytest

from ssuksak.ingestion.classifiers import (
    classify_age_page,
    classify_section,
    classify_setting,
    extract_position_tag,
    row_label_setting,
    split_alternatives,
)
from ssuksak.ingestion.models import AgeEvidenceType, Setting, SourceSection


# ======================================================== 연령


def test_single_age_page():
    ages, kind = classify_age_page("< 7월 4세 놀이 이야기 >\n생활주제 여름  연령 4세")
    assert ages == (4,)
    assert kind is AgeEvidenceType.SINGLE_AGE_PAGE


def test_range_is_not_single_age():
    ages, kind = classify_age_page("햇살반 놀이계획안 (만3~5세)")
    assert ages == (3, 4, 5)
    assert kind is AgeEvidenceType.MIXED_AGE_PAGE


def test_enumerated_ages_is_not_single_age():
    ages, kind = classify_age_page("만4,5세 월간보육계획안")
    assert ages == (4, 5)
    assert kind is AgeEvidenceType.MIXED_AGE_PAGE


def test_mixed_word_blocks_single_age_even_with_one_number():
    ages, kind = classify_age_page("혼합연령반 만4세")
    assert ages == (4,)
    assert kind is AgeEvidenceType.MIXED_AGE_PAGE


def test_two_separate_single_ages_on_one_page_is_not_single():
    ages, kind = classify_age_page("만 3세 동백반 … 만 5세 누리반")
    assert ages == (3, 5)
    assert kind is AgeEvidenceType.MIXED_AGE_PAGE


def test_age_unknown():
    ages, kind = classify_age_page("유아반 월간계획안")
    assert ages == ()
    assert kind is AgeEvidenceType.AGE_UNKNOWN


def test_infant_ages_are_out_of_p0_target():
    ages, _ = classify_age_page("만0세 만1세 만2세 만3세")
    assert ages == (3,)


# ======================================================== Section


@pytest.mark.parametrize(
    "label,expected",
    [
        ("바깥놀이", SourceSection.OUTDOOR_PLAY),
        ("실외놀이", SourceSection.OUTDOOR_PLAY),
        ("바 깥", SourceSection.OUTDOOR_PLAY),
        ("산책", SourceSection.OUTDOOR_PLAY),
        ("대체활동", SourceSection.INDOOR_ALTERNATIVE),
        ("실내대체", SourceSection.INDOOR_ALTERNATIVE),
        ("소주제", SourceSection.WEEK_EXPERIENCE),
        ("교사의 기대", SourceSection.WEEK_EXPERIENCE),
        ("주제 선정 배경", SourceSection.WEEK_EXPERIENCE),
        ("안전교육", SourceSection.SAFETY_EDUCATION),
        ("비상대응훈련", SourceSection.SAFETY_EDUCATION),
        ("실내놀이", SourceSection.INDOOR_PLAY),
        ("기본생활습관", SourceSection.DAILY_ROUTINE),
        ("행사", SourceSection.EVENT),
        ("생활주제", SourceSection.THEME),
        ("놀이주제", SourceSection.THEME),
        ("알 수 없는 라벨", SourceSection.UNKNOWN),
        ("", SourceSection.UNKNOWN),
    ],
)
def test_classify_section(label, expected):
    assert classify_section(label) is expected


def test_pure_alternative_label_is_indoor_alternative():
    assert classify_section("대체활동") is SourceSection.INDOOR_ALTERNATIVE
    assert classify_section("실내대체") is SourceSection.INDOOR_ALTERNATIVE


@pytest.mark.parametrize("label", ["바깥놀이 (대체활동)", "바깥놀이 [대체활동]",
                                   "바깥놀이 / 대체활동"])
def test_merged_outdoor_and_alternative_label_is_an_outdoor_row(label):
    """`바깥놀이 (대체활동)`은 두 줄짜리 병합 행 label이고 윗줄이 바깥놀이다.

    실내대체를 먼저 보면 서진어린이집 월간계획안 5건의 바깥놀이 항목이 통째로
    사라진다. 어느 항목이 대체안인지는 항목 단위로 판정한다.
    """
    assert classify_section(label) is SourceSection.OUTDOOR_PLAY


# ======================================================== 행 label setting


def test_row_label_outdoor_wins_over_alt_in_merged_label():
    """`바깥놀이 [대체활동]`은 **두 줄짜리 병합 행 label**이다. 바깥놀이 행이다."""
    assert row_label_setting("바깥놀이 [대체활동]") is Setting.OUTDOOR


def test_row_label_indoor_alone():
    assert row_label_setting("실내놀이") is Setting.INDOOR


def test_indoor_outdoor_combined_label_is_not_evidence():
    """`실내외 놀이`는 실내와 실외를 함께 가리킨다. 어느 쪽 근거도 아니다."""
    assert row_label_setting("실내외 놀이") is None


def test_vertical_merged_label_fragment():
    assert row_label_setting("이 실외놀이") is Setting.OUTDOOR


# ======================================================== Setting


@pytest.mark.parametrize(
    "item,row_label,expected",
    [
        ("모래놀이", "바깥놀이", Setting.OUTDOOR),
        ("씨름", "실내놀이", Setting.INDOOR),
        ("[실내대체] 몸으로 자음 모음표현하기", "바깥놀이", Setting.INDOOR_ALTERNATIVE),
        ("대체) 부채로 휴지떼기", "바깥놀이", Setting.INDOOR_ALTERNATIVE),
        ("［대체］달팽이 끈으로 우리 동네 길 만들기", "바깥", Setting.INDOOR_ALTERNATIVE),
        ("♥바깥놀이-비석치기", "♥전통부채", Setting.OUTDOOR),
        ("<바깥놀이> 팽이놀이", "흥미 예상 놀이", Setting.OUTDOOR),
        ("<실내놀이> 실팽이놀이", "흥미 예상 놀이", Setting.INDOOR),
        ("무엇인가", "알 수 없는 라벨", Setting.UNKNOWN),
    ],
)
def test_classify_setting(item, row_label, expected):
    assert classify_setting(item, row_label=row_label) is expected


def test_paengi_nori_is_outdoor_not_indoor():
    """Patch 1의 우려는 `실팽이 놀이` 부분문자열 오탐이었다 (setting audit §1)."""
    assert classify_setting("<바깥놀이> 팽이놀이(대체활동: 팽이가움직여요.)",
                            row_label="흥미 예상 놀이") is Setting.OUTDOOR


# ======================================================== 태그 열 레이아웃


@pytest.mark.parametrize(
    "raw,text,setting",
    [
        ("우리 동네 마트 [바깥] 방문하기", "우리 동네 마트 방문하기", Setting.OUTDOOR),
        ("장바구니에 공 [대체] 넣기", "장바구니에 공 넣기", Setting.INDOOR_ALTERNATIVE),
        ("겨울 풍경 [바깥] 찾기", "겨울 풍경 찾기", Setting.OUTDOOR),
        ("모래놀이", "모래놀이", None),
    ],
)
def test_extract_position_tag(raw, text, setting):
    """태그 전용 열 + wrap 때문에 태그가 항목 가운데로 들어간 표를 바로잡는다."""
    assert extract_position_tag(raw) == (text, setting)


def test_content_bearing_alt_bracket_is_not_stripped():
    """`(대체활동: X)` 안의 글자는 대체안 자체다. 지우면 안 된다."""
    raw = "팽이놀이(대체활동: 팽이가움직여요.)"
    assert extract_position_tag(raw) == (raw, None)


# ======================================================== 대체안 분리


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<대체놀이> 여우야, 여우야 뭐하니?",
         [("여우야, 여우야 뭐하니?", True)]),
        ("무궁화 꽃이 피었습니다. 【대체활동 : 강강술래를 해요】",
         [("무궁화 꽃이 피었습니다", False), ("강강술래를 해요", True)]),
        ("쓰레기를 분리수거해요(보물찾기) 대체활동 – 바다 지킴이 장애물 놀이",
         [("쓰레기를 분리수거해요(보물찾기)", False), ("바다 지킴이 장애물 놀이", True)]),
        ("동대문놀이(대체활동: 동대문놀이)",
         [("동대문놀이", False), ("동대문놀이", True)]),
        ("숨어있는 봄을 찾아라 [대체놀이] 봄노래에 맞춰 걸어보기",
         [("숨어있는 봄을 찾아라", False), ("봄노래에 맞춰 걸어보기", True)]),
        ("훌라후프 징검다리를 건너요(대체)",
         [("훌라후프 징검다리를 건너요", False)]),
        ("산책하며 여름 곤충 찾기", [("산책하며 여름 곤충 찾기", False)]),
    ],
)
def test_split_alternatives(raw, expected):
    assert split_alternatives(raw) == expected


def test_daechero_is_not_an_alternative_marker():
    """`대체로`는 부사다. 대체안 표시가 아니다."""
    assert split_alternatives("대체로 좋은 날씨예요") == [("대체로 좋은 날씨예요", False)]


def test_split_alternatives_empty():
    assert split_alternatives("") == []


def test_weak_outdoor_token_only_counts_in_a_short_label():
    """`산책` `텃밭`은 다른 행 label 안에도 흔히 나온다.

    경상남도청어린이집 연간계획안의 행사 행 label이 병합되며 `텃밭`을 포함해
    연간 목표 문장이 outdoor 후보가 된 실제 오탐이 있었다.
    """
    assert classify_section("텃밭") is SourceSection.OUTDOOR_PLAY
    assert classify_section("나들이") is SourceSection.OUTDOOR_PLAY
    assert classify_section(
        "4월 m식목일 기념 모종심기/가족 과 함께 하는 텃밭 이야기"
    ) is SourceSection.UNKNOWN


def test_outdoor_row_label_denominator_uses_baseline_vocabulary():
    """Outdoor Loss 분모는 줄 기반 baseline과 같은 어휘로 센다."""
    from ssuksak.ingestion.classifiers import is_outdoor_row_label

    assert is_outdoor_row_label("바깥놀이") is True
    assert is_outdoor_row_label("실외놀이") is True
    assert is_outdoor_row_label("바깥놀이 (대체활동)") is True
    assert is_outdoor_row_label("실내놀이") is False
    assert is_outdoor_row_label("텃밭") is False        # baseline 분모에 없다
    assert is_outdoor_row_label("") is False
