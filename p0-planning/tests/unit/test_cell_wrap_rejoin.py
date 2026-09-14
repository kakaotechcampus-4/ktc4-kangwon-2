"""Cell wrap 재결합 Parser Regression (Monthly Quality Patch 1).

v0.2.0을 만든 추출은 `pdftotext -layout`의 **줄** 단위로 동작해 셀 안 줄바꿈을
Activity 구분자로 오판했다. 수정 규칙은 `analysis/tools/cell_extract.py`에 있고,
여기서는 그 규칙이 **wrap과 list를 구분하는지**를 고정한다.

이 테스트는 PDF를 열지 않는다. 순수 함수만 검증하므로 빠르고 결정론적이다.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parents[2] / "analysis" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from cell_extract import (  # noqa: E402
    is_terminal_line,
    rejoin_wrapped_lines,
    split_line_by_gap,
)


# ======================================================== 종결 판정


@pytest.mark.parametrize(
    "line",
    [
        "산책하기",            # -기
        "건너기",
        "무궁화 꽃이 피었습니다",  # -다
        "놀이를 해요.",          # -요 + 마침표
        "우리집에 왜 왔니?",      # 물음표
        "투호놀이",             # 명사 '놀이'
        "동대문 놀이",
        "강강술래",             # 명사 '래'
        "전통놀이체험",          # 명사 '체험'
    ],
)
def test_terminal_lines_are_recognized(line):
    assert is_terminal_line(line) is True


@pytest.mark.parametrize(
    "line",
    [
        "장화 신고 물웅덩이",     # 명사 종결이지만 bare '이'는 종결이 아니다
        "자연물로 여름 디저트",
        "선캡 쓰고 공원",
        "우리 동네 분수대",
        "물총을 쏴 종이컵",
        "산책하며 여름 곤충",
        "셀로판지로 여름",
    ],
)
def test_incomplete_lines_are_not_terminal(line):
    assert is_terminal_line(line) is False


def test_bare_i_is_not_terminal_but_nori_is():
    """`물웅덩이`가 종결로 잡히면 wrap이 끊긴다. `놀이`만 예외다."""
    assert is_terminal_line("장화 신고 물웅덩이") is False
    assert is_terminal_line("모래놀이") is True


# ======================================================== wrap 재결합


def test_known_defect_case_a_boots_puddle():
    """Source 확정 결함 A: 한 Activity가 두 줄로 나뉘어 있었다."""
    assert rejoin_wrapped_lines(["장화 신고 물웅덩이", "건너기"]) == [
        "장화 신고 물웅덩이 건너기"
    ]


def test_known_defect_case_b_dessert():
    assert rejoin_wrapped_lines(["자연물로 여름 디저트", "만들기"]) == [
        "자연물로 여름 디저트 만들기"
    ]


def test_two_wrapped_activities_in_one_cell():
    """한 셀에 wrap된 Activity가 둘 있어도 각각 복원된다."""
    assert rejoin_wrapped_lines(
        ["선캡 쓰고 공원", "산책하기", "장화 신고 물웅덩이", "건너기"]
    ) == ["선캡 쓰고 공원 산책하기", "장화 신고 물웅덩이 건너기"]


def test_vertical_list_is_not_merged():
    """세로로 나열된 별개 Activity를 합치면 안 된다 (False Positive 방지)."""
    assert rejoin_wrapped_lines(["투호놀이", "줄다리기를 해요", "동대문 놀이"]) == [
        "투호놀이",
        "줄다리기를 해요",
        "동대문 놀이",
    ]


def test_mixed_list_and_wrap():
    assert rejoin_wrapped_lines(
        ["무궁화 꽃이 피었습니다", "장화 신고 물웅덩이", "건너기", "강강술래"]
    ) == ["무궁화 꽃이 피었습니다", "장화 신고 물웅덩이 건너기", "강강술래"]


def test_unterminated_tail_is_preserved_not_guessed():
    """마지막까지 종결되지 않으면 있는 그대로 남긴다. 추측해 채우지 않는다."""
    assert rejoin_wrapped_lines(["자연물로 여름 디저트"]) == ["자연물로 여름 디저트"]


def test_blank_lines_are_ignored():
    assert rejoin_wrapped_lines(["장화 신고 물웅덩이", "   ", "건너기"]) == [
        "장화 신고 물웅덩이 건너기"
    ]


def test_empty_input():
    assert rejoin_wrapped_lines([]) == []


# ======================================================== 구두점 보존


def test_punctuation_inside_activity_is_not_a_separator():
    """`우리집에 왜 왔니? 놀이를 해요.`는 하나의 Activity다 (Source 확정 결함 C)."""
    words = [
        (199.3, 440.0, 229.2, 452.0, "우리집에"),
        (232.0, 440.0, 250.0, 452.0, "왜"),
        (253.0, 440.0, 271.0, 452.0, "왔니?"),
        (273.6, 440.0, 299.4, 452.0, "놀이를"),
        (302.0, 440.0, 323.5, 452.0, "해요."),
    ]
    assert split_line_by_gap(words) == ["우리집에 왜 왔니? 놀이를 해요."]


def test_wide_gap_splits_sub_columns():
    """괄선 없는 좌/우 하위 열은 큰 간격으로 나뉜다."""
    words = [
        (133.3, 447.0, 165.7, 459.0, "무궁화"),
        (171.7, 447.0, 193.3, 459.0, "꽃이"),
        (199.3, 447.0, 253.3, 459.0, "피었습니다"),
        (277.3, 447.0, 331.3, 459.0, "모래사막을"),
        (337.3, 447.0, 380.5, 459.0, "구성해요"),
    ]
    assert split_line_by_gap(words) == ["무궁화 꽃이 피었습니다", "모래사막을 구성해요"]


def test_split_line_by_gap_handles_empty():
    assert split_line_by_gap([]) == []
