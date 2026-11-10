"""실명을 가명으로 바꾸고 되돌린다.

    mask               교사가 쓴 글 -> LLM 에 보낼 글
    unmask_as_written  LLM 이 새로 쓴 글 -> 교사에게 보여줄 글(원문에 적힌 표기로)
    unmask_from        원문에서 그대로 옮긴 글 -> 원문 그 글자로

두 방향이 같은 표를 써야 한다. 따로 넘기면 한쪽만 고치는 날이 오고,
그날 실명이 나간다. 그래서 NameTable 하나로 묶는다.
"""

import re
from collections.abc import Iterable

from .names import call_suffix, name_variants
from .pool import SubstitutionError, has_final

__all__ = ["NameTable", "SubstitutionError", "mask", "unmask", "unmask_as_written", "unmask_from"]


class NameTable:
    """한 번의 LLM 호출에 등장할 수 있는 아이들의 실명 <-> 가명 표.

    입력은 {등록 실명: 가명} 이다. children 테이블의 name -> code 를 그대로 넘긴다.
    치환할 때는 성을 뗀 이름까지 찾는다. 되돌릴 때는 원문에 적힌 표기로 돌린다(unmask_as_written).

    `calls` 는 (등록 실명, 부르는 이름) 이다. 부르는 이름은 가명에 같은 꼴을 붙여 바꾸고
    그 꼴 그대로 되돌린다 -- 김민 · 민이 · 가람 이면 "민이가" -> "가람이가" -> "민이가".
    """

    def __init__(self, names: dict[str, str], calls: Iterable[tuple[str, str]] = ()) -> None:
        masking: dict[str, str] = {}
        restoring: dict[str, str] = {}

        def claim(variant: str, code: str) -> None:
            # 두 아이의 이름이 겹치면(김하나·박하나 -> 둘 다 "하나") 어느 쪽인지 알 수 없다.
            if variant in masking and masking[variant] != code:
                raise SubstitutionError(
                    f"같은 표기를 두 아이가 쓴다: {variant}. "
                    "이 호출에서는 전체 이름만 치환하도록 표를 좁힌다"
                )
            masking[variant] = code

        for real, code in names.items():
            if not real or not code:
                raise SubstitutionError("실명 또는 가명이 비어 있다")
            if real == code:
                raise SubstitutionError(f"가명이 실명과 같다: {code}")
            if has_final(real) != has_final(code):
                # 받침이 다르면 복원할 때 조사가 틀어진다. "박서준이" -> "민준서가" -> "박서준가"
                raise SubstitutionError(
                    f"받침이 다른 가명이다: {real} -> {code}. PseudonymPool.allocate() 로 발급한다"
                )
            if code in restoring:
                raise SubstitutionError(f"가명이 중복됐다: {code}. 되돌릴 수 없다")
            restoring[code] = real
            for variant in name_variants(real):
                claim(variant, code)
        for real, call in calls:
            if real not in names:
                raise SubstitutionError("부르는 이름의 아이가 표에 없다")
            try:
                form = names[real] + call_suffix(real, call)
            except ValueError as exc:
                raise SubstitutionError(str(exc)) from exc
            if restoring.setdefault(form, call) not in (call, real):
                raise SubstitutionError(f"가명이 중복됐다: {form}. 되돌릴 수 없다")
            claim(call, form)
        # 가명이 다른 아이의 표기와 겹치면 복원할 때 누구인지 알 수 없다.
        # 박민준 -> "도현" 인데 최도현이 같은 반에 있으면, 치환 결과의 "도현" 이
        # 박민준의 가명인지 최도현의 실명인지 구분되지 않는다.
        collided = sorted(set(restoring) & set(masking))
        if collided:
            raise SubstitutionError(
                f"가명이 다른 아이의 이름과 겹친다: {', '.join(collided)}. "
                "PseudonymPool.allocate() 에 그 반의 이름도 taken 으로 넘긴다"
            )
        self._masking = masking
        self._restoring = restoring

    def __len__(self) -> int:
        return len(self._restoring)

    @property
    def masking(self) -> dict[str, str]:
        return dict(self._masking)

    @property
    def restoring(self) -> dict[str, str]:
        return dict(self._restoring)


def _replace(text: str, table: dict[str, str]) -> str:
    """긴 열쇠부터 한 번에 바꾼다.

    하나씩 순서대로 바꾸면 앞에서 넣은 가명을 뒤 규칙이 또 바꾼다.
    정규식 하나로 묶어 한 번만 훑는다.
    """
    if not table:
        return text
    keys = sorted(table, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    return pattern.sub(lambda m: table[m.group(0)], text)


def mask(text: str, table: NameTable) -> str:
    """실명을 가명으로 바꾼다.

    표가 비어 있으면 그대로 돌려준다 -- 계획안처럼 아이 이름이 없는 문서가 있다.
    바꾼 뒤에 실명이 남아 있으면 에러를 낸다. 조용히 내보내지 않는다.
    """
    if not isinstance(text, str):
        raise SubstitutionError("치환 대상이 문자열이 아니다")
    if not isinstance(table, NameTable):
        raise SubstitutionError("NameTable 을 넘긴다")
    masked = _replace(text, table.masking)
    leaked = [name for name in table.masking if name in masked]
    if leaked:
        # 가명이 실명을 부분 문자열로 품는 경우 등. 여기서 멈춘다.
        raise SubstitutionError(f"치환 후에도 실명이 남았다: {', '.join(leaked)}")
    return masked


def unmask(text: str, table: NameTable) -> str:
    """가명을 등록된 실명으로 되돌린다. mask() 에 넘긴 것과 같은 표를 넘긴다.

    LLM 이 쓴 글에는 쓰지 않는다 — 원문 낱말이 이름과 겹쳐 가려졌던 자리에 사실에 없던
    전체 이름을 만든다. 그때는 unmask_as_written 을 쓴다.
    """
    if not isinstance(table, NameTable):
        raise SubstitutionError("NameTable 을 넘긴다")
    return _replace(text, table.restoring)


def unmask_as_written(text: str, table: NameTable, original: str) -> str:
    """LLM 이 쓴 글의 가명을, 교사가 원문에 적은 표기로 되돌린다.

    원 전체 아이로 표를 만들면 다른 반 「김하늘」의 성 뗀 이름 「하늘」이 원문 「하늘을 보며」와
    겹쳐 가명이 된다. unmask 로 되돌리면 그 자리가 「김하늘」이 되어, 사실에 없던 다른 반 아이의
    전체 이름이 문서에 들어간다. 그래서 아이마다 원문에 실제로 적힌 표기 가운데 가장 긴 것으로
    되돌린다(name_variants 는 긴 것부터). 원문에 그 아이의 표기가 하나도 없으면 가명을 그대로 둔다
    — 등록 실명을 새로 만들어 넣는 것이 바로 막으려는 일이다.

    한계: 한 아이를 한 가지 표기로만 되돌린다. 「김하늘이 하늘을 보며」처럼 같은 아이가 원문에
    두 표기로 적혔으면 둘 다 「김하늘」이 된다. 글이 틀어질 뿐 새 이름이 생기지는 않는다.
    """
    if not isinstance(table, NameTable):
        raise SubstitutionError("NameTable 을 넘긴다")
    # 그 가명으로 가린 표기들(등록 이름 · 성 뗀 이름 · 부르는 이름) 가운데 원문에 있는 가장 긴 것.
    forms: dict[str, list[str]] = {}
    for variant, code in table.masking.items():
        forms.setdefault(code, []).append(variant)
    as_written = {
        code: next(
            (v for v in sorted(forms.get(code, ()), key=len, reverse=True) if v in original), code
        )
        for code in table.restoring
    }
    return _replace(text, as_written)


def unmask_from(text: str, table: NameTable, original: str) -> str:
    """원문에서 그대로 옮겨 온 글을, 원문에 적혀 있던 표기 그대로 되돌린다.

    unmask 는 가명을 등록 실명으로 돌린다. 주제 칸의 「여름」이 김여름의 이름과 같아 가려졌으면
    unmask 는 「김여름」을 돌려준다. 옮겨 온 글이니 가명 자리에 그 아이의 표기를 넣어 원문에서
    찾고, 찾은 글자를 그대로 준다. 원문에서 못 찾으면(모델이 글을 고쳐 옮겼으면)
    unmask_as_written 과 같다.
    """
    restoring = table.restoring
    if not any(code in text for code in restoring):
        return text
    codes = sorted(restoring, key=len, reverse=True)
    parts = re.split("(" + "|".join(map(re.escape, codes)) + ")", text)

    def spot(index: int, part: str) -> str:
        if index % 2 == 0:
            return re.escape(part)
        forms = [variant for variant, code in table.masking.items() if code == part]
        options = sorted({part, *forms}, key=len, reverse=True)
        return "(?:" + "|".join(map(re.escape, options)) + ")"

    found = re.search("".join(spot(i, p) for i, p in enumerate(parts)), original)
    return found[0] if found else unmask_as_written(text, table, original)
