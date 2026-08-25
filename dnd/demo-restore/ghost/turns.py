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


async def spend_movement(client: GhostClient, shape: str, feet: int, speed: int | None = None) -> None:
    """Book movement against the turn budget, if it is this creature's turn.

    Silently does nothing for anyone else: the ghost is routinely asked to walk a
    monster around out of combat, and that should not consume a budget that is
    being displayed for somebody else.
    """
    data = await read_budget(client)
    if data.get("active") != shape:
        return
    data["movementUsed"] = max(0, int(data.get("movementUsed") or 0) + max(0, feet))
    if speed is not None:
        data["speed"] = speed
    await write_budget(client, data)


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
