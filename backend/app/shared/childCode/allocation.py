"""등록 전 반 전체 치환표를 검증한다. 이미 발급한 가명은 변경하지 않는다.

행은 (실명, 가명, 부르는 이름) 이다. 부르는 이름은 외자 아이만 가진다 -- 없으면 None.
"""

from collections.abc import Iterable

from .names import bare_syllables, name_variants, one_syllable
from .pool import CallNameNeeded, PseudonymPool, SubstitutionError, has_final
from .substitute import NameTable, mask

Row = tuple[str, str, str | None]


def _forms(name: str, call: str | None) -> list[str]:
    """글에서 그 아이를 찾을 표기. 부르는 이름이 있으면 그것까지."""
    return [*name_variants(name), *([call] if call else [])]


def _table(rows: Iterable[Row]) -> NameTable:
    rows = list(rows)
    return NameTable({n: c for n, c, _ in rows}, [(n, k) for n, _, k in rows if k])


def check_class(rows: Iterable[Row]) -> None:
    """반 명단으로 표를 만들고 아이마다 모든 표기가 가려지는지 본다. 못 하면 SubstitutionError."""
    rows = list(rows)
    table = _table(rows)
    for name, _, call in rows:
        for form in _forms(name, call):
            mask(form, table)


def allocate_for_class(
    pool: PseudonymPool,
    real_name: str,
    existing: Iterable[Row],
    call_name: str | None = None,
) -> str:
    rows = list(existing)
    names = [name for name, _, _ in rows] + [real_name]
    # dict로 바꾸기 전에 검사한다. 완전히 같은 실명은 dict에서 사라진다.
    if len(names) != len(set(names)):
        raise SubstitutionError("같은 이름이 이미 등록되어 있습니다.")
    variants = {v for n, _, k in [*rows, (real_name, "", call_name)] for v in _forms(n, k)}
    taken = {code for _, code, _ in rows} | variants
    # 한 글자 실명 등 가명 안에 실명이 남는 경우도 mask()가 거부한다.
    while True:
        code = pool.allocate(real_name, taken)
        if not any(variant in code for variant in variants):
            break
        taken.add(code)
    check_class([*rows, (real_name, code, call_name)])
    return code


def _refuse_bare_syllables(rows: list[Row], text: str) -> None:
    """부르는 이름이 없는 외자 아이의 글자가 글에 홀로 서 있으면 LLM 을 부르지 않는다.

    「민이가」 는 등록 이름(김민)으로도, 성을 뗀 이름으로도 안 걸린다. 한 글자를 그대로
    치환하면 「고민」 · 「민속놀이」 까지 바뀐다. 그래서 낱말로 홀로 설 때만 막고,
    부르는 이름을 적게 한다(ADR-004 보완).
    """
    syllables = {s for name, _, call in rows if not call and (s := one_syllable(name))}
    found = bare_syllables(text, syllables)
    if found:
        quoted = " · ".join(f"『{s}』" for s in found)
        josa = "이" if has_final(found[-1]) else "가"
        raise CallNameNeeded(
            f"{quoted}{josa} 아이 이름이면 아이 명단에서 부르는 이름을 적어 주세요. "
            "이름이 아니면 그 말을 바꿔 적어 주세요."
        )


def table_for_text(
    pool: PseudonymPool,
    own: Iterable[Row],
    others: Iterable[Row],
    text: str,
) -> NameTable | None:
    """원 전체 아이 가운데 글에 나온 아이만으로, 이번 호출 한 번에 쓸 치환표를 만든다.

    own     글을 쓴 반의 (실명, 가명, 부르는 이름)
    others  같은 원 다른 반의 (실명, 가명, 부르는 이름)

    가명은 반 안에서만 유일하다(UNIQUE(class_id, code)). 다른 반 아이와 가명이 같거나,
    가명이 글에 나온 다른 아이 이름과 겹치면 이번 호출에서만 Pool 에서 새로 뽑는다.
    저장된 가명은 바꾸지 않는다.

    우리 반 두 아이가 같은 표기(김하나 · 박하나 -> 하나)를 쓰면 어느 아이인지 몰라 에러다.
    다른 반 아이의 표기가 먼저 넣은 아이와 겹치면 그 아이는 넣지 않는다 — 겹친 표기가 이미
    가려지므로 이름이 나가지 않는다. 마지막에 글에 나온 아이 이름이 하나도 안 남았는지 본다.
    부르는 이름이 없는 외자 아이의 글자가 홀로 서 있으면 CallNameNeeded 다.
    """
    own, others = list(own), list(others)
    _refuse_bare_syllables(own + others, text)

    def named(rows):
        return [r for r in rows if any(v in text for v in _forms(r[0], r[2]))]

    mine, theirs = named(own), named(others)
    if not mine and not theirs:
        return None
    variants = {v for name, _, call in mine + theirs for v in _forms(name, call)}
    picked = list(mine)
    claimed = {v for name, _, call in mine for v in _forms(name, call)}
    for name, code, call in theirs:
        if claimed.isdisjoint(_forms(name, call)):
            picked.append((name, code, call))
            claimed.update(_forms(name, call))
    names: dict[str, str] = {}
    calls: list[tuple[str, str]] = []
    taken = variants | {code for _, code, _ in picked}
    for name, code, call in picked:
        if code in names.values() or any(v in code for v in variants):
            code = pool.allocate(name, taken)
            while any(v in code for v in variants):
                taken.add(code)
                code = pool.allocate(name, taken)
            taken.add(code)
        names.setdefault(name, code)
        if call:
            calls.append((name, call))
    table = NameTable(names, calls)
    masked = mask(text, table)
    left = sorted(v for v in variants if v in masked)
    if left:
        raise SubstitutionError(f"치환 후에도 실명이 남았다: {', '.join(left)}")
    return table
