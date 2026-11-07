"""계획안 codec 이 클래스의 타입 힌트를 한 번만 푸는지 본다.

되돌리는 값이 맞는지는 계획안 API 테스트들이 본다. 여기는 속도 회귀만 막는다 —
힌트를 매번 다시 풀던 때 backend 테스트 시간의 약 20% 가 거기였다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features.plans import codec


@dataclass(frozen=True)
class _Cell:
    name: str
    count: int | None = None


def test_a_class_hints_are_resolved_once_and_reused():
    before = codec._type_hints.cache_info()

    assert codec.from_jsonable(_Cell, {"name": "가", "count": 1}) == _Cell("가", 1)
    assert codec.from_jsonable(_Cell, {"name": "나"}) == _Cell("나")

    after = codec._type_hints.cache_info()
    assert after.misses - before.misses <= 1
    assert after.hits - before.hits >= 1
