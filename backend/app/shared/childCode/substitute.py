"""실명을 가명으로 바꾸고 되돌린다.

    mask    교사가 쓴 글 -> LLM 에 보낼 글
    unmask  LLM 이 준 글 -> 교사에게 보여줄 글

이름을 가진 아이가 여럿이면 긴 이름부터 바꾼다. "서준" 과 "서준호" 가 같은 반에
있을 때 짧은 쪽을 먼저 바꾸면 "서준호" 가 "민준호" 가 된다.
"""

import re

from .pool import SubstitutionError, has_final

__all__ = ["SubstitutionError", "mask", "unmask"]


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


def mask(text: str, names: dict[str, str]) -> str:
    """실명을 가명으로 바꾼다.

    names 는 {실명: 가명} 이다. children 테이블의 name -> code 를 그대로 넘긴다.
    비어 있으면 그대로 돌려준다 -- 계획안처럼 아이 이름이 없는 문서가 있다.
    """
    if not isinstance(text, str):
        raise SubstitutionError("치환 대상이 문자열이 아니다")
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
    return _replace(text, names)


def unmask(text: str, names: dict[str, str]) -> str:
    """가명을 실명으로 되돌린다. mask() 에 넘긴 것과 같은 표를 넘긴다.

    가명 두 개가 같은 실명을 가리키면 되돌릴 때 어느 쪽인지 알 수 없다.
    그 표는 애초에 잘못된 것이므로 여기서 막는다.
    """
    codes = list(names.values())
    if len(codes) != len(set(codes)):
        raise SubstitutionError("가명이 중복됐다. 되돌릴 수 없다")
    return _replace(text, {code: real for real, code in names.items()})
