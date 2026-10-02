"""반 전체 가명 invariant. HTTP·DB와 분리해서 양방향 충돌을 검증한다."""

import pytest

from app.shared.childCode import NameTable, PseudonymPool, SubstitutionError, load_pool, mask
from app.shared.childCode.allocation import allocate_for_class


@pytest.mark.parametrize(
    "names",
    [
        ["박서준", "김하윤"],
        ["김하윤", "박서준"],
        ["박민준"],
        ["박태겸", "김하윤", "이승석", "최가람"],
    ],
)
def test_every_accepted_roster_can_mask_every_child(names):
    rows = []
    for name in names:
        rows.append((name, allocate_for_class(load_pool(), name, rows)))
        table = NameTable(dict(rows))
        for registered, _ in rows:
            assert registered not in mask(f"{registered}이 블록을 쌓았다.", table)


def test_skip_multiple_existing_name_candidates():
    pool = PseudonymPool(["서준", "민준", "태겸", "하윤", "예준"], [])
    rows = [("박서준", "태겸"), ("김민준", "하윤")]
    assert allocate_for_class(pool, "이승석", rows) == "예준"


def test_reverse_collision_does_not_reassign_existing_code():
    rows = [("김하윤", "민준")]
    with pytest.raises(SubstitutionError):
        allocate_for_class(load_pool(), "박민준", rows)
    assert rows == [("김하윤", "민준")]
    NameTable(dict(rows))


@pytest.mark.parametrize(
    "names",
    [
        ("박서준", "박서준"),
        ("박민준", "김민준"),
        ("서준", "박서준"),
    ],
)
def test_ambiguous_names_are_rejected_before_dictionary_collapse(names):
    rows = [(names[0], allocate_for_class(load_pool(), names[0], []))]
    with pytest.raises(SubstitutionError):
        allocate_for_class(load_pool(), names[1], rows)


def test_exhaustion_after_excluding_own_name_is_explicit():
    with pytest.raises(SubstitutionError):
        allocate_for_class(PseudonymPool(["민준"], []), "박민준", [])


def test_legacy_invalid_roster_cannot_accept_more_children():
    with pytest.raises(SubstitutionError):
        allocate_for_class(load_pool(), "이태겸", [("박서준", "민준"), ("김하윤", "서준")])


def test_name_inside_a_pseudonym_is_also_excluded():
    assert allocate_for_class(PseudonymPool(["민준", "도현"], []), "민", []) == "도현"
