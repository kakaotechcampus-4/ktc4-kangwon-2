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


def table_for_text(
    pool: PseudonymPool,
    own: Iterable[tuple[str, str]],
    others: Iterable[tuple[str, str]],
    text: str,
) -> NameTable | None:
    """원 전체 아이 가운데 글에 나온 아이만으로, 이번 호출 한 번에 쓸 치환표를 만든다.

    own     글을 쓴 반의 (실명, 가명)
    others  같은 원 다른 반의 (실명, 가명)

    가명은 반 안에서만 유일하다(UNIQUE(class_id, code)). 다른 반 아이와 가명이 같거나,
    가명이 글에 나온 다른 아이 이름과 겹치면 이번 호출에서만 Pool 에서 새로 뽑는다.
    저장된 가명은 바꾸지 않는다.

    우리 반 두 아이가 같은 표기(김하나 · 박하나 -> 하나)를 쓰면 어느 아이인지 몰라 에러다.
    다른 반 아이의 표기가 먼저 넣은 아이와 겹치면 그 아이는 넣지 않는다 — 겹친 표기가 이미
    가려지므로 이름이 나가지 않는다. 마지막에 글에 나온 아이 이름이 하나도 안 남았는지 본다.
    """

    def named(rows):
        return [(n, c) for n, c in rows if any(v in text for v in name_variants(n))]

    mine, theirs = named(own), named(others)
    if not mine and not theirs:
        return None
    variants = {v for name, _ in mine + theirs for v in name_variants(name)}
    picked = list(mine)
    claimed = {v for name, _ in mine for v in name_variants(name)}
    for name, code in theirs:
        if claimed.isdisjoint(name_variants(name)):
            picked.append((name, code))
            claimed.update(name_variants(name))
    names: dict[str, str] = {}
    taken = variants | {code for _, code in picked}
    for name, code in picked:
        if code in names.values() or any(v in code for v in variants):
            code = pool.allocate(name, taken)
            while any(v in code for v in variants):
                taken.add(code)
                code = pool.allocate(name, taken)
            taken.add(code)
        names.setdefault(name, code)
    table = NameTable(names)
    masked = mask(text, table)
    left = sorted(v for v in variants if v in masked)
    if left:
        raise SubstitutionError(f"치환 후에도 실명이 남았다: {', '.join(left)}")
    return table
