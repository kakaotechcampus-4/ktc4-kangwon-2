"""셀 복원 규칙 회귀 (L1).

PDF를 열지 않는다. 순수 함수와 좌표만 검증하므로 빠르고 결정론적이다.

여기 있는 Case는 전부 **실제 Corpus에서 확인된 것**이다. Monthly Quality Patch 1이
고친 결함과, 그때 확인한 "합치면 안 되는" 반례를 같이 고정한다.
"""

from __future__ import annotations

import pytest

from ssuksak.ingestion.cells import (
    Word,
    build_cells,
    is_terminal_line,
    rejoin_wrapped_lines,
    split_line_by_gap,
)


# ======================================================== 종결 판정


@pytest.mark.parametrize(
    "line",
    [
        "산책하기", "건너기", "무궁화 꽃이 피었습니다", "놀이를 해요.",
        "우리집에 왜 왔니?", "투호놀이", "동대문 놀이", "강강술래", "전통놀이체험",
    ],
)
def test_terminal_lines_are_recognized(line):
    assert is_terminal_line(line) is True


@pytest.mark.parametrize(
    "line",
    ["장화 신고 물웅덩이", "자연물로 여름 디저트", "선캡 쓰고 공원",
     "우리 동네 분수대", "물총을 쏴 종이컵", "산책하며 여름 곤충", "셀로판지로 여름"],
)
def test_incomplete_lines_are_not_terminal(line):
    assert is_terminal_line(line) is False


def test_bare_i_is_not_terminal_but_nori_is():
    """`물웅덩이`가 종결로 잡히면 wrap이 끊긴다. `놀이`만 예외다."""
    assert is_terminal_line("장화 신고 물웅덩이") is False
    assert is_terminal_line("모래놀이") is True


# ======================================================== wrap 재결합


def test_known_defect_boots_puddle():
    """Source 확정 결함 A: 한 Activity가 두 줄로 나뉘어 있었다."""
    assert rejoin_wrapped_lines(["장화 신고 물웅덩이", "건너기"]) == [
        "장화 신고 물웅덩이 건너기"
    ]


def test_known_defect_dessert():
    assert rejoin_wrapped_lines(["자연물로 여름 디저트", "만들기"]) == [
        "자연물로 여름 디저트 만들기"
    ]


def test_two_wrapped_activities_in_one_cell():
    assert rejoin_wrapped_lines(
        ["선캡 쓰고 공원", "산책하기", "장화 신고 물웅덩이", "건너기"]
    ) == ["선캡 쓰고 공원 산책하기", "장화 신고 물웅덩이 건너기"]


def test_vertical_list_is_not_merged():
    """세로로 나열된 별개 Activity를 합치면 안 된다 (False Merge 방지)."""
    assert rejoin_wrapped_lines(["투호놀이", "줄다리기를 해요", "동대문 놀이"]) == [
        "투호놀이", "줄다리기를 해요", "동대문 놀이",
    ]


def test_mixed_list_and_wrap():
    assert rejoin_wrapped_lines(
        ["무궁화 꽃이 피었습니다", "장화 신고 물웅덩이", "건너기", "강강술래"]
    ) == ["무궁화 꽃이 피었습니다", "장화 신고 물웅덩이 건너기", "강강술래"]


def test_unterminated_tail_is_preserved_not_guessed():
    assert rejoin_wrapped_lines(["자연물로 여름 디저트"]) == ["자연물로 여름 디저트"]


def test_blank_and_empty():
    assert rejoin_wrapped_lines(["장화 신고 물웅덩이", "   ", "건너기"]) == [
        "장화 신고 물웅덩이 건너기"
    ]
    assert rejoin_wrapped_lines([]) == []


# ======================================================== 구두점 · 하위 열


def test_punctuation_inside_activity_is_not_a_separator():
    """`우리집에 왜 왔니? 놀이를 해요.`는 하나의 Activity다 (Source 확정 결함 C)."""
    words = [
        Word(199.3, 440.0, 229.2, 452.0, "우리집에"),
        Word(232.0, 440.0, 250.0, 452.0, "왜"),
        Word(253.0, 440.0, 271.0, 452.0, "왔니?"),
        Word(273.6, 440.0, 299.4, 452.0, "놀이를"),
        Word(302.0, 440.0, 323.5, 452.0, "해요."),
    ]
    assert split_line_by_gap(words) == ["우리집에 왜 왔니? 놀이를 해요."]


def test_wide_gap_splits_sub_columns():
    words = [
        Word(133.3, 447.0, 165.7, 459.0, "무궁화"),
        Word(171.7, 447.0, 193.3, 459.0, "꽃이"),
        Word(199.3, 447.0, 253.3, 459.0, "피었습니다"),
        Word(277.3, 447.0, 331.3, 459.0, "모래사막을"),
        Word(337.3, 447.0, 380.5, 459.0, "구성해요"),
    ]
    assert split_line_by_gap(words) == ["무궁화 꽃이 피었습니다", "모래사막을 구성해요"]


def test_split_line_by_gap_handles_empty():
    assert split_line_by_gap([]) == []


# ======================================================== 셀 복원


def _grid_words() -> list[Word]:
    """2행 × 2열 표. 오른쪽 아래 셀의 항목이 두 줄로 wrap된 형태."""
    return [
        Word(12, 100, 60, 112, "바깥놀이"),
        Word(120, 100, 200, 112, "모래놀이"),
        Word(12, 150, 60, 162, "실내놀이"),
        Word(120, 150, 210, 162, "장화 신고 물웅덩이"),
        Word(120, 165, 160, 177, "건너기"),
    ]


_V = [(10.0, 90.0, 190.0), (110.0, 90.0, 190.0), (300.0, 90.0, 190.0)]
_H = [(90.0, 10.0, 300.0), (140.0, 10.0, 300.0), (190.0, 10.0, 300.0)]


def test_build_cells_recovers_label_and_body_as_separate_cells():
    """줄 기반이 잃던 것: label과 내용이 **서로 다른 셀**이다."""
    page = build_cells(page=1, words=_grid_words(),
                       vertical_rules=_V, horizontal_rules=_H)
    assert page.has_cells
    rows = page.rows()
    assert len(rows) == 2
    (_band, cols) = rows[0]
    assert cols[0].items == ("바깥놀이",)
    assert cols[1].items == ("모래놀이",)


def test_build_cells_rejoins_wrapped_body_inside_the_cell():
    page = build_cells(page=1, words=_grid_words(),
                       vertical_rules=_V, horizontal_rules=_H)
    (_band, cols) = page.rows()[1]
    assert cols[1].items == ("장화 신고 물웅덩이 건너기",)


def test_build_cells_without_rejoin_keeps_raw_lines():
    page = build_cells(page=1, words=_grid_words(), vertical_rules=_V,
                       horizontal_rules=_H, rejoin=False)
    (_band, cols) = page.rows()[1]
    assert cols[1].items == ("장화 신고 물웅덩이", "건너기")


def test_no_table_lines_yields_no_cells_and_does_not_guess():
    page = build_cells(page=1, words=_grid_words(),
                       vertical_rules=[], horizontal_rules=[])
    assert not page.has_cells
    assert page.cells == ()


def test_build_cells_is_deterministic():
    a = build_cells(page=1, words=_grid_words(), vertical_rules=_V,
                    horizontal_rules=_H)
    b = build_cells(page=1, words=list(reversed(_grid_words())),
                    vertical_rules=list(reversed(_V)),
                    horizontal_rules=list(reversed(_H)))
    assert a.rows() == b.rows()
