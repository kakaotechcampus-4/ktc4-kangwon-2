"""가명 목록을 읽고 하나 꺼낸다.

받침으로 두 묶음이다. 조사가 이름 마지막 글자의 받침에 붙기 때문에,
받침이 다른 이름으로 바꾸면 복원할 때 조사가 틀어진다.

    원본   박서준이 블록을 쌓았다      "준" 받침 ㄴ  -> 이
    가명   민준서가 블록을 쌓았다      "서" 받침 X   -> 가
    복원   박서준가 블록을 쌓았다      틀어졌다

그래서 원본과 같은 묶음에서 뽑는다.
"""

from functools import lru_cache
from pathlib import Path

import yaml


class SubstitutionError(Exception):
    """치환할 수 없다. 이 예외가 나면 LLM 을 호출하지 않는다 (ADR-004)."""


_POOL_PATH = Path(__file__).resolve().parents[3] / "resources" / "pseudonyms.yaml"

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3
_FINAL_COUNT = 28


def has_final(name: str) -> bool:
    """마지막 글자에 받침이 있나. 한글이 아니면 받침 없음으로 본다."""
    if not name:
        raise ValueError("이름이 비어 있다")
    last = ord(name[-1])
    if not _HANGUL_START <= last <= _HANGUL_END:
        return False
    return (last - _HANGUL_START) % _FINAL_COUNT != 0


class PseudonymPool:
    """resources/pseudonyms.yaml 을 감싼다.

    발급은 한 반 안에서만 유일하면 된다 -- 실제 유일성은 DB 의
    UNIQUE(class_id, code) 가 지킨다 (docs/api-spec.md 2-1).
    여기서는 이미 쓰인 코드를 받아서 겹치지 않는 것을 고른다.
    """

    def __init__(self, with_final: list[str], without_final: list[str]) -> None:
        self._groups = {True: list(with_final), False: list(without_final)}
        for names in self._groups.values():
            if len(names) != len(set(names)):
                raise ValueError("가명 목록에 중복이 있다")

    def allocate(self, real_name: str, taken: set[str]) -> str:
        """원본과 받침이 같은 가명 중 아직 안 쓴 것을 준다.

        taken 은 같은 반에서 이미 발급된 코드다. 목록이 동나면 에러를 낸다 --
        임의로 다른 묶음에서 꺼내면 조사가 틀어진다.
        """
        group = self._groups[has_final(real_name)]
        for name in group:
            if name not in taken:
                return name
        raise SubstitutionError(
            f"가명이 모자란다. 받침 {'있는' if has_final(real_name) else '없는'} "
            f"이름 {len(group)}개를 다 썼다. resources/pseudonyms.yaml 에 추가한다"
        )

    def __len__(self) -> int:
        return sum(len(names) for names in self._groups.values())


@lru_cache(maxsize=1)
def load_pool() -> PseudonymPool:
    data = yaml.safe_load(_POOL_PATH.read_text(encoding="utf-8"))
    return PseudonymPool(data["with_final"], data["without_final"])
