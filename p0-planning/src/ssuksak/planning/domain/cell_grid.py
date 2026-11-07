"""Split-tree operations shared by the monthly timetable and weekly activity grid."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import ClassVar, Generic, TypeVar

from .errors import InvalidDomainValueError
from .identifiers import ItemId
from .provenance import SplitAxis

Cell = TypeVar("Cell")


@dataclass(frozen=True, slots=True)
class CellGridNode(Generic[Cell]):
    cell: Cell | None = None
    split_id: ItemId | None = None
    axis: SplitAxis | None = None
    ratio: int | None = None
    children: tuple[CellGridNode[Cell], ...] = ()
    cell_type: ClassVar[type] = object

    def __post_init__(self) -> None:
        if self.cell is not None:
            if not isinstance(self.cell, self.cell_type) or (
                self.split_id, self.axis, self.ratio, self.children
            ) != (None, None, None, ()):
                raise InvalidDomainValueError("A grid leaf holds its cell only")
            return
        if (
            not isinstance(self.split_id, ItemId)
            or not isinstance(self.axis, SplitAxis)
            or type(self.ratio) is not int or not 10 <= self.ratio <= 90
            or not isinstance(self.children, tuple) or len(self.children) != 2
            or not all(isinstance(c, type(self)) for c in self.children)
        ):
            raise InvalidDomainValueError("A grid boundary needs split_id, axis, ratio and two parts")

    @property
    def depth(self) -> int:
        return 0 if self.cell is not None else 1 + max(c.depth for c in self.children)

    def narrowest(self, width: Fraction) -> Fraction:
        if self.cell is not None:
            return width
        first, second = self.children
        if self.axis is SplitAxis.VERTICAL:
            return min(first.narrowest(width), second.narrowest(width))
        part = width * self.ratio / 100
        return min(first.narrowest(part), second.narrowest(width - part))

    def leaves(self) -> tuple[Cell, ...]:
        return (self.cell,) if self.cell is not None else tuple(leaf for c in self.children for leaf in c.leaves())

    def boundaries(self):
        return () if self.cell is not None else (self, *(b for c in self.children for b in c.boundaries()))

    def rebuilt(self, visit: Callable):
        found = visit(self)
        if found is not None:
            return found
        if self.cell is not None:
            return self
        return replace(self, children=tuple(c.rebuilt(visit) for c in self.children))
