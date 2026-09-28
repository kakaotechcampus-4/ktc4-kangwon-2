"""계획안 도메인 객체를 JSON 으로 바꾸고 되돌린다.

**손으로 클래스마다 적지 않는다.** `YearlyPlan` 은 중첩 dataclass 가 열 몇 개에
frozenset · tuple · Enum · datetime 이 섞여 있다. 클래스마다 변환 함수를 적으면
p0-planning 에 칸이 하나 늘 때마다 여기도 고쳐야 하고, **안 고치면 조용히 값이
사라진다.** 계획안에서 사라지면 안 되는 것이 감사 기록과 근거다.

그래서 타입 힌트를 읽어서 돌린다. 도메인이 바뀌어도 이 파일은 안 바뀐다.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import types
import typing
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")

_ATOMS = (str, int, float, bool, type(None))


def to_jsonable(value: Any) -> Any:
    """도메인 값 -> json.dumps 가 먹는 값.

    frozenset 은 **정렬해서** 담는다. 순서가 흔들리면 같은 계획안인데 DB 의 바이트가
    달라지고, 골든 비교와 「바뀌었나」 판정이 매번 다르게 나온다.
    """
    if isinstance(value, _ATOMS):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (frozenset, set)):
        return sorted(to_jsonable(item) for item in value)
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    raise TypeError(f"계획안에 담을 수 없는 값이다: {type(value).__name__}")


def from_jsonable(annotation: Any, value: Any) -> Any:
    """`to_jsonable` 의 반대. 어떤 타입으로 되돌릴지는 타입 힌트가 정한다."""
    origin = typing.get_origin(annotation)

    # `X | None` · Optional[X]
    if origin in (typing.Union, types.UnionType):
        options = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        if value is None:
            return None
        if len(options) != 1:
            raise TypeError(f"되돌릴 타입을 고를 수 없다: {annotation}")
        return from_jsonable(options[0], value)

    if origin in (frozenset, set):
        (inner,) = typing.get_args(annotation) or (Any,)
        return origin(from_jsonable(inner, item) for item in value)

    if origin in (tuple, list):
        args = typing.get_args(annotation)
        # tuple[X, ...] 은 같은 타입이 여러 개다. tuple[X, Y] 는 자리마다 타입이 다르다.
        if origin is tuple and args and args[-1] is not Ellipsis:
            return tuple(from_jsonable(arg, item) for arg, item in zip(args, value, strict=True))
        inner = args[0] if args else Any
        return origin(from_jsonable(inner, item) for item in value)

    if origin is dict:
        _, inner = typing.get_args(annotation) or (str, Any)
        return {key: from_jsonable(inner, item) for key, item in value.items()}

    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            return annotation(value)
        if annotation is dt.datetime:
            return dt.datetime.fromisoformat(value)
        if annotation is dt.date:
            return dt.date.fromisoformat(value)
        if dataclasses.is_dataclass(annotation):
            # 문자열로 적힌 타입 힌트(`from __future__ import annotations`)를 실제 타입으로
            # 푼다. 안 풀면 아래 재귀가 str 을 타입으로 알고 그대로 돌려준다.
            hints = typing.get_type_hints(annotation)
            kwargs = {
                f.name: from_jsonable(hints[f.name], value[f.name])
                for f in dataclasses.fields(annotation)
                if f.name in value
            }
            return annotation(**kwargs)

    return value
