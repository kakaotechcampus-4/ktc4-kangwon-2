"""등록 전 반 전체 치환표를 검증한다. 이미 발급한 가명은 변경하지 않는다."""

from collections.abc import Iterable

from .names import name_variants
from .pool import PseudonymPool, SubstitutionError
from .substitute import NameTable, mask


def allocate_for_class(
    pool: PseudonymPool, real_name: str, existing: Iterable[tuple[str, str]]
) -> str:
    rows = list(existing)
    names = [name for name, _ in rows] + [real_name]
    # dict로 바꾸기 전에 검사한다. 완전히 같은 실명은 dict에서 사라진다.
    if len(names) != len(set(names)):
        raise SubstitutionError("같은 이름이 이미 등록되어 있습니다.")
    variants = {variant for name in names for variant in name_variants(name)}
    taken = {code for _, code in rows} | variants
    # 한 글자 실명 등 가명 안에 실명이 남는 경우도 mask()가 거부한다.
    while True:
        code = pool.allocate(real_name, taken)
        if not any(variant in code for variant in variants):
            break
        taken.add(code)
    table = NameTable(dict([*rows, (real_name, code)]))
    for name in names:
        mask(name, table)
    return code
