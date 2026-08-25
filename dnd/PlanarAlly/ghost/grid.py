"""Grid maths, ported from the client's `core/grid`.

The ghost has to reason about the same board the players see, which means
agreeing with PlanarAlly exactly about which pixel belongs to which cell. These
formulas are a direct port of `client/src/core/grid/index.ts`; if that file
changes, this one is wrong and tokens will land a cell off.

Square grids are simple. Hex grids are defined by the radius of the hexagon's
outer circle, chosen as DEFAULT_GRID_SIZE / sqrt(3) so that a pointy hex is as
wide as a square cell and a flat hex is as tall as one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

DEFAULT_GRID_SIZE = 50.0
SQRT3 = math.sqrt(3)
DEFAULT_HEX_RADIUS = DEFAULT_GRID_SIZE / SQRT3


class GridType(str, Enum):
    SQUARE = "SQUARE"
    POINTY_HEX = "POINTY_HEX"
    FLAT_HEX = "FLAT_HEX"

    @classmethod
    def parse(cls, value: str | None) -> "GridType":
        try:
            return cls(str(value).upper())
        except ValueError:
            return cls.SQUARE


@dataclass(frozen=True)
class Cell:
    """Axial coordinates. For square grids q/r are just column/row."""

    q: int
    r: int


def _axial_round(q: float, r: float) -> Cell:
    """Round fractional axial coords to the nearest hex.

    Done in cube space (x + y + z == 0) and then repaired along whichever axis
    moved furthest, which is the standard trick -- rounding q and r
    independently picks the wrong hex near the edges.
    """
    x, z = q, r
    y = -x - z
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)

    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return Cell(int(rx), int(rz))


def cell_from_point(x: float, y: float, grid: GridType) -> Cell:
    if grid is GridType.SQUARE:
        return Cell(math.floor(x / DEFAULT_GRID_SIZE), math.floor(y / DEFAULT_GRID_SIZE))
    radius = DEFAULT_HEX_RADIUS
    if grid is GridType.POINTY_HEX:
        q = ((SQRT3 / 3) * x - (1 / 3) * (y - radius)) / radius
        r = ((2 / 3) * (y - radius)) / radius
    else:  # FLAT_HEX
        q = ((2 / 3) * (x - radius)) / radius
        r = ((-1 / 3) * (x - radius) + (SQRT3 / 3) * y) / radius
    return _axial_round(q, r)


def cell_center(cell: Cell, grid: GridType) -> tuple[float, float]:
    if grid is GridType.SQUARE:
        half = DEFAULT_GRID_SIZE / 2
        return (cell.q * 2 * half + half, cell.r * 2 * half + half)
    radius = DEFAULT_HEX_RADIUS
    if grid is GridType.POINTY_HEX:
        return (
            radius * (SQRT3 * cell.q + (SQRT3 / 2) * cell.r),
            radius * ((3 / 2) * cell.r + 1),
        )
    return (
        radius * ((3 / 2) * cell.q + 1),
        radius * ((SQRT3 / 2) * cell.q + SQRT3 * cell.r),
    )


# The six axial directions are the same for both hex orientations; only the
# pixel projection differs.
_HEX_NEIGHBOURS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
# Eight for square, because 5e lets you move diagonally for the same cost.
_SQUARE_NEIGHBOURS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


def cell_anchor(cell: Cell, grid: GridType) -> tuple[float, float]:
    """Where a one-cell shape's x/y must be for it to sit on `cell`.

    PlanarAlly stores a shape's position as its top-left corner, not its centre,
    and `battlefield._covered_cells` reads it back that way -- adding half a grid
    square to find the middle. Anything that writes a position therefore has to
    write the corner, or it lands half a cell off.

    On a square grid that error was invisible: half a square from a square's
    centre still floors into the same square. On hex it is not, because half a
    grid square from a hex's centre is inside the *next* hex. Every token the
    ghost moved read back exactly one cell away from where it had been put,
    which made repeated "moves to" appear to stall two cells short of its
    target while the pathfinder was working perfectly.
    """
    cx, cy = cell_center(cell, grid)
    half = DEFAULT_GRID_SIZE / 2
    return cx - half, cy - half


def neighbours(cell: Cell, grid: GridType) -> list[Cell]:
    offsets = _SQUARE_NEIGHBOURS if grid is GridType.SQUARE else _HEX_NEIGHBOURS
    return [Cell(cell.q + dq, cell.r + dr) for dq, dr in offsets]


def distance(a: Cell, b: Cell, grid: GridType) -> int:
    """Distance in cells -- i.e. in movement steps, not pixels."""
    if grid is GridType.SQUARE:
        # Chebyshev: a diagonal costs the same as a straight step, which is
        # 5e's default rule (the optional rule alternates 5/10ft instead).
        return max(abs(a.q - b.q), abs(a.r - b.r))
    dq, dr = a.q - b.q, a.r - b.r
    return (abs(dq) + abs(dq + dr) + abs(dr)) // 2
