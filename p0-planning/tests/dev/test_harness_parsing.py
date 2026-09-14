"""Harness 입력 파싱 테스트. 순수 함수만 다루며 I/O가 없다."""

from __future__ import annotations

import pytest

from ssuksak.dev.parsing import (
    HarnessInputError,
    parse_age_mode,
    parse_ages,
    parse_menu_choice,
    parse_period_key,
    parse_school_year,
    semantic_key_for_period,
)
from ssuksak.planning.application.dto import AgeMode


# ------------------------------------------------------------ school_year


def test_school_year_parses_digits():
    assert parse_school_year("2026") == 2026
    assert parse_school_year(" 2027 ") == 2027


def test_school_year_uses_default_on_blank():
    assert parse_school_year("", default=2026) == 2026
    assert parse_school_year("   ", default=2026) == 2026


def test_school_year_blank_without_default_is_rejected():
    with pytest.raises(HarnessInputError):
        parse_school_year("")


@pytest.mark.parametrize("bad", ["abc", "20x6", "1999", "2101", "-2026"])
def test_school_year_rejects_invalid(bad: str):
    with pytest.raises(HarnessInputError):
        parse_school_year(bad)


# -------------------------------------------------------------------- ages


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3", {3}),
        ("4", {4}),
        ("5", {5}),
        ("3,4", {3, 4}),
        ("3, 4, 5", {3, 4, 5}),
        (" 3 4 ", {3, 4}),
        ("4,4", {4}),
    ],
)
def test_ages_parsing(raw: str, expected: set[int]):
    assert parse_ages(raw) == frozenset(expected)


@pytest.mark.parametrize("bad", ["", "   ", "abc", "3,x", "삼"])
def test_ages_rejects_non_numeric(bad: str):
    with pytest.raises(HarnessInputError):
        parse_ages(bad)


@pytest.mark.parametrize("bad", ["2", "6", "0", "2,3", "3,4,5,6"])
def test_ages_rejects_unsupported_ages(bad: str):
    """P0 지원 연령은 Rule 계층의 SUPPORTED_AGES를 따른다."""
    with pytest.raises(HarnessInputError, match="지원"):
        parse_ages(bad)


# --------------------------------------------------------------- age_mode


def test_age_mode_blank_returns_none():
    assert parse_age_mode("", frozenset({3})) is None
    assert parse_age_mode("  ", frozenset({3, 4})) is None


@pytest.mark.parametrize("raw", ["SINGLE", "single", " Single "])
def test_single_mode_accepted_with_one_age(raw: str):
    assert parse_age_mode(raw, frozenset({3})) is AgeMode.SINGLE


@pytest.mark.parametrize("raw", ["MIXED", "mixed", " Mixed "])
def test_mixed_mode_accepted_with_two_ages(raw: str):
    assert parse_age_mode(raw, frozenset({3, 4})) is AgeMode.MIXED


def test_mixed_mode_with_one_age_is_rejected():
    with pytest.raises(HarnessInputError, match="2개 이상"):
        parse_age_mode("MIXED", frozenset({4}))


def test_single_mode_with_two_ages_is_rejected():
    with pytest.raises(HarnessInputError, match="1개"):
        parse_age_mode("SINGLE", frozenset({3, 4}))


def test_unknown_mode_is_rejected():
    with pytest.raises(HarnessInputError):
        parse_age_mode("BOTH", frozenset({3, 4}))


# ------------------------------------------------------------ period_key


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3", "2026-03"),
        ("03", "2026-03"),
        ("12", "2026-12"),
        ("1", "2027-01"),
        ("2", "2027-02"),
        ("2026-04", "2026-04"),
        ("2026-4", "2026-04"),
        ("2027-02", "2027-02"),
    ],
)
def test_period_key_normalization(raw: str, expected: str):
    """1·2월이 다음 해로 넘어가는 학년도 규칙을 Rule 계층에서 가져온다."""
    assert parse_period_key(raw, 2026) == expected


@pytest.mark.parametrize("bad", ["", "   ", "abc", "0", "13", "-1"])
def test_period_key_rejects_invalid(bad: str):
    with pytest.raises(HarnessInputError):
        parse_period_key(bad, 2026)


@pytest.mark.parametrize("bad", ["2025-04", "2028-01", "2026-01", "2027-03"])
def test_period_key_rejects_out_of_school_year(bad: str):
    """학년도 밖의 명시적 period_key는 거부한다."""
    with pytest.raises(HarnessInputError, match="학년도"):
        parse_period_key(bad, 2026)


def test_period_key_follows_school_year():
    assert parse_period_key("1", 2030) == "2031-01"
    assert parse_period_key("3", 2030) == "2030-03"


# ----------------------------------------------------------- semantic_key


@pytest.mark.parametrize(
    "period_key,expected",
    [
        ("2026-03", "yearly.month.03.theme"),
        ("2026-10", "yearly.month.10.theme"),
        ("2027-01", "yearly.month.01.theme"),
    ],
)
def test_semantic_key_for_period(period_key: str, expected: str):
    assert semantic_key_for_period(period_key) == expected


# ------------------------------------------------------------------ menu


def test_menu_choice_accepts_allowed():
    assert parse_menu_choice("3", ("0", "1", "3")) == "3"
    assert parse_menu_choice(" 0 ", ("0", "1")) == "0"


@pytest.mark.parametrize("bad", ["", "  ", "9", "x", "10"])
def test_menu_choice_rejects_unknown(bad: str):
    with pytest.raises(HarnessInputError):
        parse_menu_choice(bad, ("0", "1", "2"))
