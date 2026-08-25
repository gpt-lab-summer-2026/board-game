"""A cell-level view of the board: who is where, what blocks, what hurts.

Built from the shapes the ghost already receives over the socket, so it needs no
extra round-trips. It is a snapshot -- rebuild it before planning a move.

A note on hazards. PlanarAlly has no concept of dangerous terrain: shapes carry
`movement_obstruction` (a wall) and `vision_obstruction`, and nothing else about
what standing somewhere costs you. So this file *defines* one, two ways:

  - explicitly, via a room DataBlock listing shape uuids, which is exact and
    survives renaming;
  - by name keyword ("lava", "fire", "spikes"...), which needs no setup and is
    how a DM would naturally label a hazard they drew.

The keyword list is a convenience, not a rule; a shape called "campfire" will
match "fire" and be treated as dangerous. That is the right failure direction
for an automated mover -- refusing to walk somewhere is recoverable, walking a
character into a fire pit is not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from .grid import Cell, GridType, cell_center, cell_from_point

log = logging.getLogger(__name__)

DEFAULT_HAZARD_KEYWORDS = (
    "lava",
    "fire",
    "flame",
    "acid",
    "spike",
    "trap",
    "pit",
    "chasm",
    "poison",
    "caltrop",
    "hazard",
    "difficult",
)

# Layers whose contents are scenery rather than obstacles. Tokens live on
# "tokens"; the fog layers are bookkeeping and must never count as terrain.
NON_TERRAIN_LAYERS = {"fow", "fow-players", "grid"}

# Fraction of a cell between line-of-sight samples.
DEFAULT_SAMPLE_FRACTION = 0.25

# 5e's largest creature category is Gargantuan at 4x4 cells.
MAX_TOKEN_CELLS = 4
# A sanity ceiling for terrain, so a full-board background image does not
# expand into tens of thousands of cells.
MAX_TERRAIN_CELLS = 60


@dataclass
class Occupant:
    uuid: str
    name: str
    cell: Cell
    is_defeated: bool = False


@dataclass
class Battlefield:
    grid: GridType
    """Feet (or whatever unit the campaign uses) represented by one cell."""
    unit_size: float = 5.0
    blocked: set[Cell] = field(default_factory=set)
    hazardous: set[Cell] = field(default_factory=set)
    """Cells that stop sight. PlanarAlly's `vision_obstruction`."""
    opaque: set[Cell] = field(default_factory=set)
    occupants: dict[str, Occupant] = field(default_factory=dict)
    """cell -> uuid of whoever is standing there."""
    occupied: dict[Cell, str] = field(default_factory=dict)
    """cell -> the name of whatever terrain is there, so the ghost can say
    "the lava pool" rather than "dangerous terrain"."""
    names: dict[Cell, str] = field(default_factory=dict)

    def cells_for_speed(self, speed_feet: float) -> int:
        if self.unit_size <= 0:
            return 0
        return int(speed_feet // self.unit_size)

    def is_free(self, cell: Cell, ignore: Iterable[str] = ()) -> bool:
        """Can something stand here? Hazards are passable, just unwise."""
        if cell in self.blocked:
            return False
        other = self.occupied.get(cell)
        return other is None or other in set(ignore)

    def cells_between(self, a: Cell, b: Cell) -> list[Cell]:
        """Every cell the straight line from a to b passes through.

        Sampled in pixel space rather than walked in cell space, because the
        two hex orientations have different pixel geometry and a single
        sampling loop gets all three grid types right. The step is a quarter
        of a cell, which is fine enough that nothing thinner than a cell can
        slip between samples.
        """
        ax, ay = cell_center(a, self.grid)
        bx, by = cell_center(b, self.grid)
        dx, dy = bx - ax, by - ay
        span = max(abs(dx), abs(dy))
        if span == 0:
            return []

        steps = max(1, int(span / (DEFAULT_SAMPLE_FRACTION * self.cell_pixels)))
        seen: list[Cell] = []
        for i in range(1, steps):
            t = i / steps
            cell = cell_from_point(ax + dx * t, ay + dy * t, self.grid)
            if cell != a and cell != b and (not seen or seen[-1] != cell):
                seen.append(cell)
        return seen

    @property
    def cell_pixels(self) -> float:
        from .grid import DEFAULT_GRID_SIZE

        return DEFAULT_GRID_SIZE

    def has_line_of_sight(self, a: Cell, b: Cell) -> bool:
        """Can something at `a` see `b`?

        Only terrain counts. Creatures do not block line of sight in 5e -- they
        grant cover, which is a modifier the DM applies, not a veto the ghost
        should be making on its own.
        """
        return not any(cell in self.opaque for cell in self.cells_between(a, b))


def _covered_cells(shape: dict[str, Any], grid: GridType, *, is_token: bool) -> list[Cell]:
    """Every cell a shape occupies.

    Tokens and terrain are read differently, and conflating them was a real
    bug. A creature occupies grid cells: one, or the handful an explicitly
    oversized creature declares. Its *artwork* is unrelated -- token images
    routinely overflow their cell, and deriving a footprint from pixels made a
    104px portrait block six cells and one shape with a stale `size_x` of 23
    swallow three hundred.

    Terrain is the opposite: a DM drags a rect across ten cells and means it.
    There the pixel dimensions are the only honest source.
    """
    from .grid import DEFAULT_GRID_SIZE

    x, y = float(shape.get("x", 0) or 0), float(shape.get("y", 0) or 0)
    size_x = int(shape.get("size_x") or shape.get("sizeX") or 0)
    size_y = int(shape.get("size_y") or shape.get("sizeY") or 0)

    if is_token:
        # A gargantuan creature is 4x4. Anything beyond that is not a footprint,
        # it is a number that ended up in the field by accident, and honouring
        # it would wreck every path on the board.
        size_x = size_x if 1 <= size_x <= MAX_TOKEN_CELLS else 1
        size_y = size_y if 1 <= size_y <= MAX_TOKEN_CELLS else 1
    else:
        if size_x <= 0:
            size_x = max(1, round(float(shape.get("width") or 0) / DEFAULT_GRID_SIZE))
        if size_y <= 0:
            size_y = max(1, round(float(shape.get("height") or 0) / DEFAULT_GRID_SIZE))
        # Even terrain gets a ceiling: a background map image is one shape
        # spanning the whole board, and expanding it cell by cell would build a
        # set with tens of thousands of entries on every rebuild.
        size_x = min(size_x, MAX_TERRAIN_CELLS)
        size_y = min(size_y, MAX_TERRAIN_CELLS)

    if size_x <= 1 and size_y <= 1:
        return [cell_from_point(x + DEFAULT_GRID_SIZE / 2, y + DEFAULT_GRID_SIZE / 2, grid)]

    # Sample the *middle* of each covered cell, not the shape's corner.
    #
    # PlanarAlly gives a rect's x/y as its top-left. On a square grid that
    # corner floors into the shape's own cell, so reading the corner worked by
    # luck. On hex it does not: a half-cell offset from a hex's centre lands in
    # a neighbouring hex, and a pillar registered one cell from where it was
    # drawn.
    step = DEFAULT_GRID_SIZE
    cells: list[Cell] = []
    for ix in range(size_x):
        for iy in range(size_y):
            cell = cell_from_point(x + (ix + 0.5) * step, y + (iy + 0.5) * step, grid)
            if cell not in cells:
                cells.append(cell)
    return cells


def _get(shape: dict[str, Any], *names: str, default: Any = None) -> Any:
    for n in names:
        if n in shape:
            return shape[n]
    return default


def build(
    shapes_by_layer: Iterable[tuple[str, dict[str, Any]]],
    grid: GridType,
    unit_size: float = 5.0,
    hazard_uuids: Iterable[str] = (),
    hazard_keywords: Iterable[str] = DEFAULT_HAZARD_KEYWORDS,
) -> Battlefield:
    field_ = Battlefield(grid=grid, unit_size=unit_size)
    hazard_set = set(hazard_uuids)
    keywords = tuple(k.lower() for k in hazard_keywords)

    for layer, shape in shapes_by_layer:
        uuid = shape.get("uuid")
        if uuid is None or layer in NON_TERRAIN_LAYERS:
            continue

        name = str(_get(shape, "name", default="") or "")
        is_token = layer == "tokens"
        cells = _covered_cells(shape, grid, is_token=is_token)
        if is_token:
            defeated = bool(_get(shape, "isDefeated", "is_defeated", default=False))
            occupant = Occupant(uuid=uuid, name=name, cell=cells[0], is_defeated=defeated)
            field_.occupants[uuid] = occupant
            # A downed creature is not something you have to walk around.
            if not defeated:
                for cell in cells:
                    field_.occupied[cell] = uuid

        if bool(_get(shape, "movementObstruction", "movement_obstruction", default=False)):
            field_.blocked.update(cells)

        # vision_obstruction is an enum: 0 none, 1 complete, 2 behind.
        # Anything non-zero stops sight for our purposes.
        if int(_get(shape, "visionObstruction", "vision_obstruction", default=0) or 0) != 0:
            field_.opaque.update(cells)

        lowered = name.lower()
        if uuid in hazard_set or any(k in lowered for k in keywords):
            field_.hazardous.update(cells)

        # Only name things that actually matter to movement or sight. The
        # ghost draws its own ruler as translucent tiles on the draw layer;
        # without this filter they get reported as obstacles, and the player
        # is told the ruler is in the way.
        matters = (
            cells[0] in field_.blocked
            or cells[0] in field_.opaque
            or cells[0] in field_.hazardous
        )
        if name and not is_token and matters:
            for cell in cells:
                field_.names.setdefault(cell, name)

    log.debug(
        "battlefield: %d occupants, %d blocked, %d hazardous, %d opaque cells",
        len(field_.occupants), len(field_.blocked), len(field_.hazardous), len(field_.opaque),
    )
    return field_
