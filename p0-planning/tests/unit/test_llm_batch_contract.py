"""Batch Structured Output Contract 단위 테스트.

거부해야 하는 것: period 누락 · extra period · duplicate period ·
period_key mismatch · theme_id mismatch · blank value · schema violation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ssuksak.shared.llm.batch import (
    BatchReconcileError,
    BatchViolation,
    PolishedThemeOut,
    ThemeBatchPolishItem,
    ThemeBatchPolishRequest,
    ThemeBatchPolishResponse,
    reconcile_batch,
)

EXPECTED = {"2026-03": "t_march", "2026-04": "t_april", "2027-02": "t_feb"}


def _out(period_key: str, theme_id: str, value: str = "표현") -> PolishedThemeOut:
    return PolishedThemeOut(period_key=period_key, theme_id=theme_id, value=value)


def _response(*items: PolishedThemeOut) -> ThemeBatchPolishResponse:
    return ThemeBatchPolishResponse(themes=list(items))


# ------------------------------------------------------------------ 정상


def test_valid_batch_returns_period_to_value_map():
    response = _response(
        _out("2026-03", "t_march", "3월 표현"),
        _out("2026-04", "t_april", "4월 표현"),
        _out("2027-02", "t_feb", "2월 표현"),
    )
    result = reconcile_batch(response, EXPECTED)

    assert result == {
        "2026-03": "3월 표현",
        "2026-04": "4월 표현",
        "2027-02": "2월 표현",
    }


def test_reconcile_returns_only_values_not_theme_ids():
    """theme_id는 호출자가 Rule 결과에서 가져오므로 반환하지 않는다."""
    response = _response(
        _out("2026-03", "t_march"), _out("2026-04", "t_april"), _out("2027-02", "t_feb")
    )
    result = reconcile_batch(response, EXPECTED)
    assert all(isinstance(v, str) for v in result.values())
    assert set(result) == set(EXPECTED)


def test_order_does_not_matter():
    response = _response(
        _out("2027-02", "t_feb"), _out("2026-04", "t_april"), _out("2026-03", "t_march")
    )
    assert set(reconcile_batch(response, EXPECTED)) == set(EXPECTED)


# ------------------------------------------------------------------ 거부


def test_missing_period_is_rejected():
    response = _response(_out("2026-03", "t_march"), _out("2026-04", "t_april"))
    with pytest.raises(BatchReconcileError) as exc:
        reconcile_batch(response, EXPECTED)
    assert exc.value.violation is BatchViolation.MISSING_PERIOD
    assert "2027-02" in exc.value.detail


def test_extra_period_is_rejected():
    response = _response(
        _out("2026-03", "t_march"),
        _out("2026-04", "t_april"),
        _out("2027-02", "t_feb"),
        _out("2026-05", "t_may"),
    )
    with pytest.raises(BatchReconcileError) as exc:
        reconcile_batch(response, EXPECTED)
    assert exc.value.violation is BatchViolation.EXTRA_PERIOD
    assert exc.value.period_key == "2026-05"


def test_duplicate_period_is_rejected():
    response = _response(
        _out("2026-03", "t_march"),
        _out("2026-03", "t_march"),
        _out("2026-04", "t_april"),
    )
    with pytest.raises(BatchReconcileError) as exc:
        reconcile_batch(response, EXPECTED)
    assert exc.value.violation is BatchViolation.DUPLICATE_PERIOD
    assert exc.value.period_key == "2026-03"


def test_theme_id_mismatch_is_rejected():
    response = _response(
        _out("2026-03", "t_march"),
        _out("2026-04", "SWAPPED"),
        _out("2027-02", "t_feb"),
    )
    with pytest.raises(BatchReconcileError) as exc:
        reconcile_batch(response, EXPECTED)
    assert exc.value.violation is BatchViolation.THEME_ID_MISMATCH
    assert exc.value.period_key == "2026-04"


def test_period_key_mismatch_surfaces_as_extra_period():
    """요청에 없던 period_key는 extra로 잡힌다."""
    response = _response(_out("2099-12", "t_march"))
    with pytest.raises(BatchReconcileError) as exc:
        reconcile_batch(response, EXPECTED)
    assert exc.value.violation is BatchViolation.EXTRA_PERIOD


def test_blank_value_is_rejected_by_reconcile_defence_in_depth():
    """스키마를 우회해 들어온 공백 값도 reconcile이 잡는다."""
    blank = PolishedThemeOut.model_construct(
        period_key="2026-03", theme_id="t_march", value="   "
    )
    response = ThemeBatchPolishResponse.model_construct(themes=[blank])

    with pytest.raises(BatchReconcileError) as exc:
        reconcile_batch(response, EXPECTED)
    assert exc.value.violation is BatchViolation.BLANK_VALUE
    assert exc.value.period_key == "2026-03"


# ------------------------------------------------------- Schema 위반


def test_schema_rejects_blank_value():
    with pytest.raises(ValidationError):
        PolishedThemeOut(period_key="2026-03", theme_id="t", value="   ")


def test_schema_rejects_blank_theme_id():
    with pytest.raises(ValidationError):
        PolishedThemeOut(period_key="2026-03", theme_id="  ", value="v")


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-03", "2026/03", "2026-3", ""])
def test_schema_rejects_malformed_period_key(bad: str):
    with pytest.raises(ValidationError):
        PolishedThemeOut(period_key=bad, theme_id="t", value="v")


def test_schema_forbids_extra_fields_on_item():
    """스키마 밖 필드로 정책을 밀어 넣지 못하게 한다."""
    with pytest.raises(ValidationError):
        PolishedThemeOut.model_validate(
            {
                "period_key": "2026-03",
                "theme_id": "t",
                "value": "v",
                "applicable_months": [3],
            }
        )


def test_schema_forbids_extra_fields_on_envelope():
    with pytest.raises(ValidationError):
        ThemeBatchPolishResponse.model_validate(
            {"themes": [], "note": "무언가"}
        )


def test_schema_rejects_empty_theme_list():
    with pytest.raises(ValidationError):
        ThemeBatchPolishResponse(themes=[])


def test_schema_rejects_more_than_twelve_items():
    items = [_out(f"2026-{m:02d}", f"t{m}") for m in range(1, 13)]
    items.append(_out("2027-01", "t13"))
    with pytest.raises(ValidationError):
        ThemeBatchPolishResponse(themes=items)


def test_schema_rejects_coerced_types():
    """`"9"` → `9` 같은 조용한 변환을 허용하지 않는다."""
    with pytest.raises(ValidationError):
        PolishedThemeOut.model_validate(
            {"period_key": "2026-03", "theme_id": 123, "value": "v"}
        )


# ------------------------------------------------------- 요청 DTO


def test_request_expected_map_is_period_to_theme():
    request = ThemeBatchPolishRequest(
        task="polish_yearly_theme_labels",
        school_year=2026,
        ages=(3,),
        items=(
            ThemeBatchPolishItem(period_key="2026-03", theme_id="a", label="A"),
            ThemeBatchPolishItem(period_key="2026-04", theme_id="b", label="B"),
        ),
    )
    assert request.expected == {"2026-03": "a", "2026-04": "b"}


def test_request_item_has_no_candidate_field():
    """방어 1: 후보 배열을 담는 필드가 존재하지 않는다."""
    item = ThemeBatchPolishItem(period_key="2026-03", theme_id="a", label="A")
    for forbidden in ("candidates", "eligible_theme_ids", "options", "alternatives"):
        assert not hasattr(item, forbidden)


def test_duplicate_theme_id_across_periods_is_allowed():
    """비인접 월의 동일 theme_id 허용 정책과 정합해야 한다.

    period_key로 키를 잡기 때문에 정당한 중복이 오탐되지 않는다.
    """
    expected = {"2026-03": "same", "2026-06": "same"}
    response = _response(_out("2026-03", "same", "3월"), _out("2026-06", "same", "6월"))

    result = reconcile_batch(response, expected)
    assert result == {"2026-03": "3월", "2026-06": "6월"}
