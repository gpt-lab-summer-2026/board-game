"""Turn-scoped bookkeeping: the action economy, and durations running out.

PlanarAlly already owns the round and turn counters and ticks its own initiative
effects, so none of that is reimplemented here. Two things it has no concept of
are filled in instead:

* the action economy -- whether the creature whose turn it is still has its
  action, bonus action, reaction and movement. The browser keeps this in the
  `pa-turnbudget` room DataBlock; the ghost reads and writes the same block so
  that a move made by voice shows up on the bar.
* durations on the character sheet. A `+2 AC until the end of your next turn`
  lives in the sheet mod's data, which PA's effect timer knows nothing about, so
  it is decremented here when a turn actually advances.

The trigger is the server's own `Initiative.Turn.Update` broadcast rather than a
timer, so the ghost stays in step with whatever the DM does in the browser.
"""
from __future__ import annotations

import logging
from typing import Any

from . import sheet
from .client import GAME_NAMESPACE, GhostClient

log = logging.getLogger(__name__)

BUDGET_SOURCE = "pa-turnbudget"
BUDGET_BLOCK = "budget"


def _name(client: GhostClient, uuid: str) -> str:
    """The character name for a shape, falling back to a short uuid."""
    for name, u in client.state.characters.items():
        if u == uuid:
            return name
    return uuid[:8]


def _repr() -> dict[str, Any]:
    return {"source": BUDGET_SOURCE, "name": BUDGET_BLOCK, "category": "room"}


def _blank() -> dict[str, Any]:
    return {
        "version": 1,
        "round": 0,
        "turn": 0,
        "active": None,
        "action": False,
        "bonus": False,
        "movementUsed": 0,
        "speed": 30,
        "speedBonus": 0,
        "reactions": {},
    }


async def read_budget(client: GhostClient) -> dict[str, Any]:
    data = await sheet._load(client, _repr())
    return data if isinstance(data, dict) else _blank()


async def write_budget(client: GhostClient, data: dict[str, Any]) -> None:
    await sheet._save(client, _repr(), data)


async def active_shape(client: GhostClient) -> str | None:
    """Whose turn it is, as the browser last recorded it."""
    return (await read_budget(client)).get("active")


async def sync_to_turn(client: GhostClient, round_: int, turn: int, active: str | None) -> None:
    """Reset the action economy because the turn has moved on.

    A port of the browser's `turnBudgetSystem.syncToTurn`. Both writers are
    idempotent on the same `(round, turn, active)` tuple, so an open DM tab and
    a headless ghost can do this at the same time without fighting.

    This is what makes `spend` and `spend_movement` work at all when nobody has
    a browser open: both refuse to book anything against a creature that is not
    the block's `active`, and until now `active` was written *only* by the
    browser. A ghost-only table therefore had an action economy that silently
    never recorded anything.
    """
    data = await read_budget(client)
    if data.get("round") == round_ and data.get("turn") == turn and data.get("active") == active:
        return

    reactions = dict(data.get("reactions") or {})
    # Reactions refresh at the start of the creature's *own* turn, not whenever
    # any turn ends, so only the incoming actor's is dropped.
    if active is not None:
        reactions.pop(active, None)

    data.update({
        "round": round_,
        "turn": turn,
        "active": active,
        "action": False,
        "bonus": False,
        "movementUsed": 0,
        "speedBonus": 0,
        "reactions": reactions,
    })
    await write_budget(client, data)


async def spend_movement(client: GhostClient, shape: str, feet: int, speed: int | None = None) -> None:
    """Book movement against the turn budget, if it is this creature's turn.

    Silently does nothing for anyone else: the ghost is routinely asked to walk a
    monster around out of combat, and that should not consume a budget that is
    being displayed for somebody else.
    """
    data = await read_budget(client)
    if data.get("active") != shape:
        return
    # Only the outer clamp, matching the browser's `spendMovement`. The inner
    # `max(0, feet)` this used to have was a mistranslation that silently
    # discarded every negative amount -- which is to say, every correction.
    data["movementUsed"] = max(0, int(data.get("movementUsed") or 0) + int(feet))
    if speed is not None:
        data["speed"] = speed
    await write_budget(client, data)


async def grant_speed(client: GhostClient, shape: str, feet: int) -> None:
    """Add to this turn's movement allowance, as Dash does.

    Separate from `spend_movement` because the two are not opposites. Spending
    is clamped at zero -- "moved -30 of 30" is not a thing -- so a Dash credited
    as negative spending vanished whenever the creature had not moved yet, which
    is the usual case. It has to raise the ceiling, not lower the floor.
    """
    data = await read_budget(client)
    if data.get("active") != shape:
        return
    data["speedBonus"] = max(0, int(data.get("speedBonus") or 0) + int(feet))
    await write_budget(client, data)


async def remaining_movement(client: GhostClient, shape: str, speed: float) -> float:
    """Feet this creature may still move, or its full speed if it is not its turn.

    The out-of-turn case is deliberate and matches `spend_movement`: the ghost is
    routinely asked to walk a monster around outside initiative, and metering
    that against a budget being displayed for somebody else would be wrong.

    Until now nothing called this, which is the whole bug: the counter went up
    and up while every mover kept budgeting from the sheet's full speed, so a
    creature with 30 feet of speed could move 30 feet per command, all turn.
    """
    data = await read_budget(client)
    if data.get("active") != shape:
        return speed
    allowance = speed + float(data.get("speedBonus") or 0)
    return max(0.0, allowance - float(data.get("movementUsed") or 0))


async def spend(client: GhostClient, shape: str, kind: str) -> bool:
    """Mark the action or bonus action as used. False if it was already gone."""
    if kind not in ("action", "bonus"):
        raise ValueError(f"not part of the action economy: {kind}")
    data = await read_budget(client)
    if data.get("active") != shape:
        return True
    if data.get(kind):
        return False
    data[kind] = True
    await write_budget(client, data)
    return True


async def has_reaction(client: GhostClient, shape: str) -> bool:
    data = await read_budget(client)
    used = (data.get("reactions") or {}).get(shape)
    return used is None or used < int(data.get("round") or 0)


async def use_reaction(client: GhostClient, shape: str) -> None:
    data = await read_budget(client)
    reactions = dict(data.get("reactions") or {})
    reactions[shape] = int(data.get("round") or 0)
    data["reactions"] = reactions
    await write_budget(client, data)


# -- durations ----------------------------------------------------------------


async def tick_durations(client: GhostClient, shapes: list[str]) -> list[str]:
    """Count down one turn on every sheet-held duration, and report expiries.

    Only modifiers with a round count are touched; a manual one is a standing
    decision ("this creature is behind a wall") and should not evaporate because
    a turn passed.
    """
    lines: list[str] = []
    for shape in shapes:
        data = await sheet.read_sheet(client, shape)
        if data is None:
            continue

        kept: list[dict[str, Any]] = []
        expired: list[str] = []
        for mod in data.get("acModifiers") or []:
            duration = mod.get("duration") or {}
            if duration.get("kind") != "rounds":
                kept.append(mod)
                continue
            remaining = int(duration.get("remaining") or 0) - 1
            if remaining <= 0:
                expired.append(mod.get("source") or "a modifier")
            else:
                mod["duration"] = {"kind": "rounds", "remaining": remaining}
                kept.append(mod)

        if not expired:
            continue

        data["acModifiers"] = kept
        # Keep the flat AC in step; the editor may not be open to recompute it.
        block = (data.get("derived") or {}).get("ac") or {}
        total_mods = sum(int(m.get("value") or 0) for m in kept)
        without = int(block.get("total") or data.get("ac") or 10) - int(block.get("modifiers") or 0)
        data["ac"] = without + total_mods
        if block:
            block["modifiers"] = total_mods
            block["total"] = data["ac"]

        await sheet.write_sheet(client, shape, data)
        lines.append(f"{_name(client, shape)}: {', '.join(expired)} wore off.")
    return lines
