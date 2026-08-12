"""Walking a token towards something, and knowing when to stop.

The rules the caller asked for, in order of precedence:

  1. stop once in reach of the target (there is no point walking further);
  2. stop when the movement budget runs out;
  3. stop before stepping into dangerous terrain.

Hazards are handled in two passes. First the search runs with hazard cells
excluded, so a safe way round is always preferred and taken silently. Only when
that finds nothing does it run again with hazards allowed -- and then it does
*not* walk. It returns the route it would take and the caller asks the player
whether to accept it. Deciding on someone's behalf to walk them through a fire
is not a decision an automated mover gets to make.

Blocked cells (PlanarAlly's `movement_obstruction`, i.e. walls) are routed
around in both passes, because going around a wall is what walking is.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field as dc_field
from enum import Enum

from .battlefield import Battlefield
from .grid import Cell, distance, neighbours

log = logging.getLogger(__name__)


class StopReason(str, Enum):
    ALREADY_IN_REACH = "already_in_reach"
    ARRIVED = "arrived"
    OUT_OF_MOVEMENT = "out_of_movement"
    HAZARD = "hazard"
    NEEDS_CONFIRMATION = "needs_confirmation"
    NO_PATH = "no_path"

    def describe(self) -> str:
        return {
            StopReason.ALREADY_IN_REACH: "already within reach",
            StopReason.ARRIVED: "moved into reach",
            StopReason.OUT_OF_MOVEMENT: "ran out of movement",
            StopReason.HAZARD: "stopped short of dangerous terrain",
            StopReason.NEEDS_CONFIRMATION: "the only way through is dangerous",
            StopReason.NO_PATH: "could not find a way through",
        }[self]


@dataclass
class MovePlan:
    path: list[Cell]
    """Cells actually walked, excluding the starting cell."""
    reason: StopReason
    reached: bool
    """Set when a hazard is what kept the character from getting closer."""
    blocked_by_hazard: bool = False
    """Hazard cells this route would cross. Non-empty only when asking."""
    hazard_cells: list[Cell] = dc_field(default_factory=list)

    @property
    def steps(self) -> int:
        return len(self.path)

    @property
    def needs_confirmation(self) -> bool:
        return self.reason is StopReason.NEEDS_CONFIRMATION


def plan_move_into_reach(
    field: Battlefield,
    mover_uuid: str,
    target_uuid: str,
    budget_cells: int,
    reach_cells: int = 1,
    allow_hazards: bool = False,
) -> MovePlan:
    """Walk `mover` to within `reach` of `target`, preferring safety.

    Two passes: a hazard-free search first, and only if that cannot arrive, a
    second that allows hazards and returns NEEDS_CONFIRMATION rather than
    moving. `allow_hazards=True` skips straight to the second and does commit,
    which is what the caller passes once the player has said yes.
    """
    if not allow_hazards:
        safe = _search(field, mover_uuid, target_uuid, budget_cells, reach_cells, hazards_ok=False)
        if safe.reached or safe.reason is StopReason.ALREADY_IN_REACH:
            return safe
        if not safe.blocked_by_hazard:
            return safe

        # A hazard is what's in the way. Is there a route at all if we accept it?
        risky = _search(field, mover_uuid, target_uuid, budget_cells, reach_cells, hazards_ok=True)
        if not risky.reached:
            # Even walking through the fire doesn't get there; report the safe
            # partial progress instead of offering a pointless risk.
            return safe
        return MovePlan(
            risky.path,
            StopReason.NEEDS_CONFIRMATION,
            reached=False,
            blocked_by_hazard=True,
            hazard_cells=[c for c in risky.path if c in field.hazardous],
        )

    return _search(field, mover_uuid, target_uuid, budget_cells, reach_cells, hazards_ok=True)


def _search(
    field: Battlefield,
    mover_uuid: str,
    target_uuid: str,
    budget_cells: int,
    reach_cells: int,
    hazards_ok: bool,
) -> MovePlan:
    """Breadth-first walk.

    BFS rather than A*: the boards are small, BFS on an unweighted grid is
    already optimal, and it makes "how far did I get" trivially available for
    the partial-progress case below.
    """
    mover = field.occupants.get(mover_uuid)
    target = field.occupants.get(target_uuid)
    if mover is None or target is None:
        return MovePlan([], StopReason.NO_PATH, reached=False)

    start, goal = mover.cell, target.cell
    if distance(start, goal, field.grid) <= reach_cells:
        return MovePlan([], StopReason.ALREADY_IN_REACH, reached=True)

    ignore = {mover_uuid, target_uuid}
    came_from: dict[Cell, Cell | None] = {start: None}
    depth: dict[Cell, int] = {start: 0}
    queue: deque[Cell] = deque([start])

    # Best fallback: whatever legal cell got us closest, in case the target is
    # unreachable. Walking most of the way and saying so beats not moving.
    best: tuple[int, int, Cell] = (distance(start, goal, field.grid), 0, start)
    hazard_blocked = False
    arrival: Cell | None = None

    while queue:
        cell = queue.popleft()
        if distance(cell, goal, field.grid) <= reach_cells and cell != start:
            arrival = cell
            break

        if depth[cell] >= budget_cells:
            continue

        for nxt in neighbours(cell, field.grid):
            if nxt in came_from:
                continue
            if not hazards_ok and nxt in field.hazardous:
                # Remember that a hazard is why we didn't come this way; it
                # changes the explanation the player hears.
                hazard_blocked = True
                continue
            if not field.is_free(nxt, ignore=ignore):
                continue

            came_from[nxt] = cell
            depth[nxt] = depth[cell] + 1
            queue.append(nxt)

            d = distance(nxt, goal, field.grid)
            if (d, depth[nxt]) < (best[0], best[1]):
                best = (d, depth[nxt], nxt)

    if arrival is not None:
        return MovePlan(_trace(came_from, arrival), StopReason.ARRIVED, reached=True)

    # Didn't get there. Say why, most specific explanation first.
    end = best[2]
    path = _trace(came_from, end)
    if not path:
        reason = StopReason.HAZARD if hazard_blocked else StopReason.NO_PATH
        return MovePlan([], reason, reached=False, blocked_by_hazard=hazard_blocked)

    if len(path) >= budget_cells:
        reason = StopReason.OUT_OF_MOVEMENT
    elif hazard_blocked:
        reason = StopReason.HAZARD
    else:
        reason = StopReason.NO_PATH
    return MovePlan(path, reason, reached=False, blocked_by_hazard=hazard_blocked)


def _trace(came_from: dict[Cell, Cell | None], end: Cell) -> list[Cell]:
    path: list[Cell] = []
    node: Cell | None = end
    while node is not None and came_from.get(node) is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


async def walk(client, field: Battlefield, uuid: str, plan: MovePlan, step_delay: float = 0.25) -> None:
    """Move the token along the path, one cell at a time.

    Stepwise rather than one jump to the destination: at a table, watching the
    figure walk is how everyone follows what just happened, and it also means a
    mistake is visible before it finishes rather than after.
    """
    from .grid import cell_center

    for cell in plan.path:
        x, y = cell_center(cell, field.grid)
        await client.move_shape(uuid, x, y)
        if step_delay:
            await asyncio.sleep(step_delay)

    if plan.path:
        occupant = field.occupants.get(uuid)
        if occupant is not None:
            field.occupied.pop(occupant.cell, None)
            occupant.cell = plan.path[-1]
            field.occupied[occupant.cell] = uuid
