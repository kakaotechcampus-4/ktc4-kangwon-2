"""규칙 데이터 파일이 규칙 엔진이 기대하는 모양인지 본다.

코드가 아니라 데이터를 검사한다. 사람이 손으로 고치는 파일이라
오타 하나가 조용히 잘못된 계획안을 만든다.
"""

from pathlib import Path

import pytest
import yaml

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def _load(name: str) -> dict:
    return yaml.safe_load((RESOURCES / name).read_text(encoding="utf-8"))


def test_법정_안전교육_합계가_44시간이다():
    # 아동복지법 시행령 별표 6. 숫자가 바뀌면 법이 바뀐 것이므로 근거를 다시 확인해야 한다.
    rules = _load("rules/legal_safety_education.yaml")
    assert len(rules) == 6
    assert sum(r["annual_hours"] for r in rules.values()) == 44


@pytest.mark.parametrize("key", ["label", "cycle_months", "annual_hours"])
def test_법정_안전교육_항목에_빠진_필드가_없다(key):
    for name, rule in _load("rules/legal_safety_education.yaml").items():
        assert key in rule, f"{name} 에 {key} 가 없다"


def test_안전_플래그가_3에서_5세_범위다():
    # activities.age_min · age_max 가 3~5 만 허용한다(CheckConstraint).
    # Pool 이 그 밖 값을 담으면 어떤 활동도 통과하지 못한다.
    for name, flag in _load("rules/safety_flags.yaml").items():
        assert 3 <= flag["min_age"] <= 5, f"{name} 의 min_age 가 범위 밖이다"
        assert flag["label"] and flag["supervision"]


def _has_final(name: str) -> bool:
    """마지막 글자에 받침이 있나. 조사가 여기에 붙는다 (ADR-004)."""
    return (ord(name[-1]) - 0xAC00) % 28 != 0


def test_가명_Pool_이_받침으로_바르게_나뉘어_있다():
    pool = _load("pseudonyms.yaml")
    assert [n for n in pool["with_final"] if not _has_final(n)] == []
    assert [n for n in pool["without_final"] if _has_final(n)] == []


def test_가명_Pool_에_중복이_없다():
    # 같은 반 안에서 code 가 중복되면 UNIQUE(class_id, code) 에 걸려 등록이 실패한다.
    pool = _load("pseudonyms.yaml")
    names = pool["with_final"] + pool["without_final"]
    assert len(names) == len(set(names))


def test_가명_Pool_이_한_반_정원을_감당한다():
    # 정원 20명이 모두 같은 받침 쪽이어도 모자라지 않아야 한다.
    pool = _load("pseudonyms.yaml")
    assert len(pool["with_final"]) >= 20
    assert len(pool["without_final"]) >= 20
