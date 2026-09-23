"""실명을 가명으로 바꾸고 되돌린다.

    mask    교사가 쓴 글 -> LLM 에 보낼 글
    unmask  LLM 이 준 글 -> 교사에게 보여줄 글

두 방향이 같은 표를 써야 한다. 따로 넘기면 한쪽만 고치는 날이 오고,
그날 실명이 나간다. 그래서 NameTable 하나로 묶는다.
"""

import re

from .names import name_variants
from .pool import SubstitutionError, has_final

__all__ = ["NameTable", "SubstitutionError", "mask", "unmask"]


class NameTable:
    """한 번의 LLM 호출에 등장할 수 있는 아이들의 실명 <-> 가명 표.

    입력은 {등록 실명: 가명} 이다. children 테이블의 name -> code 를 그대로 넘긴다.
    치환할 때는 성을 뗀 이름까지 찾고, 되돌릴 때는 등록 실명으로 돌린다.
    """

    def __init__(self, names: dict[str, str]) -> None:
        masking: dict[str, str] = {}
        restoring: dict[str, str] = {}
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
                # 두 아이의 이름이 겹치면(김하나·박하나 -> 둘 다 "하나") 어느 쪽인지 알 수 없다.
                if variant in masking and masking[variant] != code:
                    raise SubstitutionError(
                        f"같은 표기를 두 아이가 쓴다: {variant}. "
                        "이 호출에서는 전체 이름만 치환하도록 표를 좁힌다"
                    )
                masking[variant] = code
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
    """가명을 등록된 실명으로 되돌린다. mask() 에 넘긴 것과 같은 표를 넘긴다."""
    if not isinstance(table, NameTable):
        raise SubstitutionError("NameTable 을 넘긴다")
    return _replace(text, table.restoring)
