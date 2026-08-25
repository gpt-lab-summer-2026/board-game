"""Proposing a better place to stand.

The difference between refusing and helping. "No line of sight" is a true and
useless answer; "no line of sight from there -- twelve feet east and you would
have it, and nothing threatens that square" is the same geometry turned into a
move somebody can accept.

Everything here is a search over cells the ghost can already reason about. It
adds no new knowledge: reachability is the same flood the mover uses, sight is
the same visibility check an attack is tested against, and threat comes from the
faction table. What is new is asking the question *before* the command fails
rather than reporting after it.

The division of labour is deliberate. The ghost picks the cell; the language
model only words it. A proposal is precisely where a plausible invention would
do the most damage, because it is a suggestion the player is being invited to
trust -- so nothing upstream is allowed to originate one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .battlefield import Battlefield
from .grid import Cell, distance, neighbours
from .movement import _reachable, _trace

log = logging.getLogger(__name__)

# 5e melee reach: the adjacent cell.
REACH_CELLS = 1


@dataclass
class Spot:
    """A cell worth moving to, and why."""

    cell: Cell
    steps: int
    path: list[Cell]
    feet: int
    threatened: bool
    """Distance to the thing being aimed at, in feet."""
    range_ft: int

    def describe(self, actor: str, target: str) -> str:
        safety = "" if self.threatened else ", and nothing threatens it"
        return (
            f"{actor} could move {self.feet} feet to a spot "
            f"{self.range_ft} feet from {target} with a clear shot{safety}"
        )


def hostile_cells(field: Battlefield, sides: dict[str, str], of_interest: str) -> set[Cell]:
    """Every cell within reach of something hostile to `of_interest`.

    "Threatened" in 5e means standing where something can hit you without
    moving, which is what makes leaving provoke an opportunity attack. Built as
    one set rather than tested per candidate, because the search below asks the
    question for every reachable cell.
    """
    mine = sides.get(of_interest, "unaligned")
    threatened: set[Cell] = set()
    for uuid, occupant in field.occupants.items():
        if uuid == of_interest:
            continue
        if not _hostile_to(sides.get(uuid, "unaligned"), mine):
            continue
        threatened.add(occupant.cell)
        threatened.update(neighbours(occupant.cell, field.grid))
    return threatened


def _hostile_to(theirs: str, mine: str) -> bool:
    """Whether a creature of disposition `theirs` menaces one of `mine`.

    Only party-versus-hostile counts. Two neutrals ignoring each other should
    not paint half the board as dangerous, and an unaligned token -- which is
    everything until somebody opens the Sides panel -- threatens nobody, so an
    unconfigured campaign gets silence rather than noise.
    """
    if mine == "party":
        return theirs == "hostile"
    if mine == "hostile":
        return theirs == "party"
    return False


def spot_with_sight(
    field: Battlefield,
    mover_uuid: str,
    target_uuid: str,
    budget_cells: int,
    sides: dict[str, str] | None = None,
    *,
    max_range_cells: int | None = None,
) -> Spot | None:
    """The nearest reachable cell that can see the target.

    Ranked cheapest-first, and among equally cheap cells the safest, then the
    closest to the target. Cost leads because a suggestion that eats the whole
    turn is rarely the one somebody wants; safety beats range because being shot
    at on the way is worse than a slightly longer shot.
    """
    mover = field.occupants.get(mover_uuid)
    target = field.occupants.get(target_uuid)
    if mover is None or target is None:
        return None

    threatened = hostile_cells(field, sides or {}, mover_uuid) if sides else set()
    came_from, depth, _ = _reachable(
        field, mover_uuid, budget_cells, {mover_uuid, target_uuid}, allow_hazards=False
    )

    best: tuple[int, int, int] | None = None
    best_cell: Cell | None = None
    for cell in came_from:
        if cell == mover.cell:
            continue
        if not field.has_line_of_sight(cell, target.cell):
            continue
        reach = distance(cell, target.cell, field.grid)
        if max_range_cells is not None and reach > max_range_cells:
            continue
        score = (depth[cell], 1 if cell in threatened else 0, reach)
        if best is None or score < best:
            best, best_cell = score, cell

    if best_cell is None:
        return None

    path = _trace(came_from, best_cell)
    return Spot(
        cell=best_cell,
        steps=len(path),
        path=path,
        feet=int(len(path) * field.unit_size),
        threatened=best_cell in threatened,
        range_ft=int(distance(best_cell, target.cell, field.grid) * field.unit_size),
    )


def spot_in_reach(
    field: Battlefield,
    mover_uuid: str,
    target_uuid: str,
    budget_cells: int,
    sides: dict[str, str] | None = None,
) -> Spot | None:
    """The cheapest reachable cell adjacent to the target, for a melee that fell short."""
    return spot_with_sight(
        field, mover_uuid, target_uuid, budget_cells, sides, max_range_cells=REACH_CELLS
    )


def caught_in_area(
    field: Battlefield,
    cells: set[Cell] | list[Cell],
    sides: dict[str, str],
    caster_uuid: str,
) -> list[str]:
    """Friendly creatures standing in an area, by shape uuid.

    Friendly means on the caster's own side -- the check that turns "cast
    fireball" into "that would catch two of yours as well". The caster is
    included: standing inside your own Burning Hands is a mistake worth being
    told about.
    """
    mine = sides.get(caster_uuid, "unaligned")
    if mine == "unaligned":
        return []
    inside = set(cells)
    hit: list[str] = []
    for uuid, occupant in field.occupants.items():
        if occupant.cell not in inside:
            continue
        theirs = sides.get(uuid, "unaligned")
        if theirs == mine or (mine == "party" and theirs == "friendly"):
            hit.append(uuid)
    return hit
