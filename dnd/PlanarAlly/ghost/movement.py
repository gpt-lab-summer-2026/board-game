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
import math
from collections import deque
from collections.abc import Iterator
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
    """False when a requested compass heading could not be honoured."""
    heading_honoured: bool = True

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


# Screen conventions, not map ones: PlanarAlly's y grows downward, so north is
# negative y. Diagonals are normalised so a northeast step is not sqrt(2) times
# more "northeast" than a north step is "north" when the two are compared.
_R2 = 0.7071067811865476
COMPASS: dict[str, tuple[float, float]] = {
    "north": (0.0, -1.0),
    "south": (0.0, 1.0),
    "east": (1.0, 0.0),
    "west": (-1.0, 0.0),
    "northeast": (_R2, -_R2),
    "northwest": (-_R2, -_R2),
    "southeast": (_R2, _R2),
    "southwest": (-_R2, _R2),
}


def _reachable(
    field: Battlefield,
    mover_uuid: str,
    budget_cells: int,
    ignore: set[str],
    allow_hazards: bool,
) -> tuple[dict[Cell, Cell | None], dict[Cell, int], bool]:
    """Flood every cell within the movement budget.

    Shared by the two goal-less searches below. Walking towards something can
    stop the moment it arrives; walking away or walking north has no arrival
    condition, so the whole budget has to be explored before anything can be
    scored.
    """
    mover = field.occupants.get(mover_uuid)
    if mover is None:
        return {}, {}, False

    start = mover.cell
    came_from: dict[Cell, Cell | None] = {start: None}
    depth: dict[Cell, int] = {start: 0}
    queue: deque[Cell] = deque([start])
    hazard_blocked = False

    while queue:
        cell = queue.popleft()
        if depth[cell] >= budget_cells:
            continue
        for nxt in neighbours(cell, field.grid):
            if nxt in came_from:
                continue
            if not allow_hazards and nxt in field.hazardous:
                hazard_blocked = True
                continue
            if not field.is_free(nxt, ignore=ignore):
                continue
            came_from[nxt] = cell
            depth[nxt] = depth[cell] + 1
            queue.append(nxt)

    return came_from, depth, hazard_blocked


def _heading_gain(field: Battlefield, start: Cell, cell: Cell, heading: tuple[float, float]) -> float:
    """How far `cell` lies along `heading` from `start`, in world units."""
    from .grid import cell_center

    ax, ay = cell_center(start, field.grid)
    bx, by = cell_center(cell, field.grid)
    return (bx - ax) * heading[0] + (by - ay) * heading[1]


# cos 45 degrees: the displacement must lie within 45 degrees of the heading.
# A bare "projection is positive" test is not enough -- it accepts anything in
# the whole forward half-plane, so "west" happily returned a cell 43 west and
# 175 *north*, and "southwest" accepted a north-westerly cell on a +3.5 gain
# because west is half of southwest. On a projected board that reads as the
# ghost ignoring the direction it was given.
_SECTOR_COS = 0.7071067811865476


def _in_sector(
    field: Battlefield, start: Cell, cell: Cell, heading: tuple[float, float]
) -> bool:
    """True when `cell` really lies in the named direction from `start`."""
    from .grid import cell_center

    ax, ay = cell_center(start, field.grid)
    bx, by = cell_center(cell, field.grid)
    dx, dy = bx - ax, by - ay
    span = math.hypot(dx, dy)
    if span <= 0:
        return False
    return (dx * heading[0] + dy * heading[1]) / span >= _SECTOR_COS


def plan_direction(
    field: Battlefield,
    mover_uuid: str,
    heading: tuple[float, float],
    budget_cells: int,
    allow_hazards: bool = False,
) -> MovePlan:
    """Walk as far as possible in a compass direction.

    Scored on displacement along the heading rather than on reaching any
    particular cell, so a wall in the way produces the best available progress
    -- sliding along it -- instead of a refusal.
    """
    mover = field.occupants.get(mover_uuid)
    if mover is None:
        return MovePlan([], StopReason.NO_PATH, reached=False)

    start = mover.cell
    came_from, depth, hazard_blocked = _reachable(
        field, mover_uuid, budget_cells, {mover_uuid}, allow_hazards
    )

    best_cell, best = start, (0.0, 0)
    for cell in came_from:
        if cell == start:
            continue
        if not _in_sector(field, start, cell, heading):
            continue
        gain = _heading_gain(field, start, cell, heading)
        # Ties broken towards the shorter walk: two cells equally far north are
        # the same outcome, and the nearer one wastes less of the turn.
        if (gain, -depth[cell]) > (best[0], -best[1]):
            best, best_cell = (gain, depth[cell]), cell

    if best_cell == start or best[0] <= 0:
        reason = StopReason.HAZARD if hazard_blocked else StopReason.NO_PATH
        return MovePlan([], reason, reached=False, blocked_by_hazard=hazard_blocked)

    path = _trace(came_from, best_cell)
    reason = StopReason.OUT_OF_MOVEMENT if len(path) >= budget_cells else StopReason.ARRIVED
    return MovePlan(path, reason, reached=True, blocked_by_hazard=hazard_blocked)


def plan_retreat(
    field: Battlefield,
    mover_uuid: str,
    threat_uuids: list[str],
    budget_cells: int,
    allow_hazards: bool = False,
    heading: tuple[float, float] | None = None,
) -> MovePlan:
    """Get away from one or more threats, as far as the budget allows.

    A different search from `plan_move_into_reach`, not a reversed one. Walking
    towards something has a goal cell and stops on arrival; walking away has no
    goal at all -- every reachable cell is a candidate and the question is which
    one is best. So this floods the whole budget and then scores.

    The score is the distance to the *nearest* threat, not the sum: backing away
    from two goblins means maximising the closest one, or you get a cell that is
    miles from one and adjacent to the other.

    A `heading` narrows it to one side of the board -- "away from hamster to the
    southwest". It is a filter rather than a term in the score, because a player
    who names a direction means that direction; blending it with clearance would
    quietly send them north because north happened to be two feet safer. If
    nothing in that direction is reachable the filter is dropped and the caller
    is told, which beats refusing to move at all.
    """
    mover = field.occupants.get(mover_uuid)
    if mover is None:
        return MovePlan([], StopReason.NO_PATH, reached=False)

    threats = [field.occupants[u].cell for u in threat_uuids if u in field.occupants]
    if not threats:
        return MovePlan([], StopReason.NO_PATH, reached=False)

    start = mover.cell
    ignore = {mover_uuid, *threat_uuids}

    def clearance(cell: Cell) -> int:
        return min(distance(cell, t, field.grid) for t in threats)

    # Standing still is the baseline: if nothing beats it, do not shuffle about
    # for no gain.
    came_from, depth, hazard_blocked = _reachable(
        field, mover_uuid, budget_cells, ignore, allow_hazards
    )

    def pick(require_heading: bool) -> tuple[Cell, tuple[int, int]]:
        cell_best, score_best = start, (clearance(start), 0)
        for cell in came_from:
            if cell == start:
                continue
            if require_heading and heading is not None:
                if not _in_sector(field, start, cell, heading):
                    continue
            # Further away wins; on a tie take the shorter walk, so a character
            # does not jog around the room to end up equally safe.
            if (clearance(cell), -depth[cell]) > (score_best[0], -score_best[1]):
                cell_best, score_best = cell, (clearance(cell), depth[cell])
        return cell_best, score_best

    best_cell, best_score = pick(require_heading=heading is not None)
    honoured = True
    if best_cell == start and heading is not None:
        best_cell, best_score = pick(require_heading=False)
        honoured = best_cell == start

    if best_cell == start:
        reason = StopReason.HAZARD if hazard_blocked else StopReason.NO_PATH
        return MovePlan([], reason, reached=False, blocked_by_hazard=hazard_blocked)

    path = _trace(came_from, best_cell)
    reason = StopReason.OUT_OF_MOVEMENT if len(path) >= budget_cells else StopReason.ARRIVED
    return MovePlan(
        path, reason, reached=True, blocked_by_hazard=hazard_blocked, heading_honoured=honoured
    )


def _trace(came_from: dict[Cell, Cell | None], end: Cell) -> list[Cell]:
    path: list[Cell] = []
    node: Cell | None = end
    while node is not None and came_from.get(node) is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


# How fast a token crosses the board, in feet of game distance per real second.
# A 30 ft move therefore takes about two seconds -- brisk enough not to hold up
# a turn, slow enough that everyone watching a projection can follow which
# figure moved and where it went.
FEET_PER_SECOND = 15.0

# Position updates per second while gliding. Twelve is smooth enough to read as
# motion and cheap enough for a Raspberry Pi driving a projector; the cost of
# raising it is one socket emit per frame per moving token.
FRAMES_PER_SECOND = 12.0


def _lerp_path(
    points: list[tuple[float, float]], frames: int
) -> Iterator[tuple[float, float]]:
    """Walk a polyline in `frames` even steps.

    Even in *distance*, not in segments: a diagonal hex step is longer than an
    orthogonal one, and pacing per segment would make the token visibly speed up
    and slow down on an otherwise straight route.
    """
    if frames < 1 or len(points) < 2:
        yield from points[1:]
        return

    spans = [
        math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)
    ]
    total = sum(spans)
    if total <= 0:
        yield points[-1]
        return

    for frame in range(1, frames + 1):
        travelled = total * frame / frames
        for index, span in enumerate(spans):
            if travelled <= span or index == len(spans) - 1:
                fraction = 1.0 if span <= 0 else min(1.0, travelled / span)
                ax, ay = points[index]
                bx, by = points[index + 1]
                yield ax + (bx - ax) * fraction, ay + (by - ay) * fraction
                break
            travelled -= span


async def walk(
    client,
    field: Battlefield,
    uuid: str,
    plan: MovePlan,
    *,
    feet_per_second: float = FEET_PER_SECOND,
    fps: float = FRAMES_PER_SECOND,
) -> None:
    """Glide the token along the path in real time.

    Cell-by-cell hops were readable but read as teleporting between squares;
    interpolating between the cell centres makes it look like walking, which is
    what everyone around a projected board is actually watching for.

    The duration is derived from the distance rather than fixed per cell, so a
    creature crossing the room takes visibly longer than one stepping aside --
    and a Dash covering twice the ground takes twice as long.
    """
    from .grid import cell_anchor

    if not plan.path:
        return

    # Anchors, not centres. The shape's current x/y is a top-left corner, so
    # interpolating from it towards a run of cell *centres* also put a half-cell
    # jump at the start of every walk.
    start = client.state.shapes.get(uuid) or {}
    points: list[tuple[float, float]] = []
    if start.get("x") is not None and start.get("y") is not None:
        points.append((float(start["x"]), float(start["y"])))
    points.extend(cell_anchor(cell, field.grid) for cell in plan.path)

    feet = plan.steps * field.unit_size
    seconds = max(0.2, feet / feet_per_second) if feet_per_second > 0 else 0.0
    frames = max(1, int(round(seconds * fps)))
    interval = seconds / frames if frames else 0.0

    for x, y in _lerp_path(points, frames):
        await client.move_shape(uuid, x, y)
        if interval:
            await asyncio.sleep(interval)

    # Land exactly on the destination: the last interpolated frame is within a
    # rounding error of it, and a token parked half a pixel off its cell centre
    # will fail an occupancy test later.
    final_x, final_y = cell_anchor(plan.path[-1], field.grid)
    await client.move_shape(uuid, final_x, final_y)

    occupant = field.occupants.get(uuid)
    if occupant is not None:
        field.occupied.pop(occupant.cell, None)
        occupant.cell = plan.path[-1]
        field.occupied[occupant.cell] = uuid
