"""Death saving throws for downed player characters.

At 0 hit points a player character is dying, not dead: three successes on a d20
stabilise them, three failures kill them, and a natural 20 puts them back on
their feet with 1 hit point. Monsters skip all of it and simply die -- nobody at
the table rolls death saves for a goblin.

Two rules here are the user's, not 5e's:

* A dead character is **not removed from the board**. Re-adding a token and its
  sheet afterwards is a chore, so the corpse stays at 0/max where it fell.
* A dead character **leaves the turn order** and comes back automatically the
  moment anything heals it above 0.

Whether a token is a player character comes from the Sides panel's faction
block, not from "does it have a sheet" -- an NPC with a full stat block is still
an NPC, and would otherwise start rolling saves.

State lives in its own room DataBlock so a reconnecting ghost, or a second one,
picks up mid-fight counters instead of starting everyone at zero successes.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import GAME_NAMESPACE, GhostClient
from .dice import roll
from .sheet import _load, _save, read_sheet, set_hp

log = logging.getLogger(__name__)

SAVES_SOURCE = "pa-deathsaves"
SAVES_BLOCK = "state"

FACTIONS_SOURCE = "pa-factions"
FACTIONS_BLOCK = "factions"

DEATH_SAVE_DC = 10
SAVES_TO_STABILISE = 3
SAVES_TO_DIE = 3


def _room_repr(source: str, name: str) -> dict[str, Any]:
    return {"source": source, "name": name, "category": "room"}


# -- faction lookup -----------------------------------------------------------


async def is_player_character(client: GhostClient, shape: str) -> bool:
    """True when the token belongs to a faction the table plays as.

    Unaligned tokens are not player characters: if a side has not been assigned
    in the Sides panel, the safe reading is "monster", because the failure mode
    is a goblin lingering on death saves rather than a PC dying unrolled.
    """
    data = await _load(client, _room_repr(FACTIONS_SOURCE, FACTIONS_BLOCK))
    if data is None:
        return False

    faction_id = (data.get("members") or {}).get(shape)
    if faction_id is None:
        return False

    for faction in data.get("factions") or []:
        if faction.get("id") == faction_id:
            return faction.get("disposition") == "party"
    return False


# -- save state ---------------------------------------------------------------


async def _read_all(client: GhostClient) -> dict[str, Any]:
    data = await _load(client, _room_repr(SAVES_SOURCE, SAVES_BLOCK))
    if data is None:
        return {"version": 1, "saves": {}}
    data.setdefault("saves", {})
    return data


async def _write(client: GhostClient, data: dict[str, Any]) -> None:
    await _save(client, _room_repr(SAVES_SOURCE, SAVES_BLOCK), data)


def _blank() -> dict[str, Any]:
    return {"successes": 0, "failures": 0, "dead": False, "stable": False}


async def get_state(client: GhostClient, shape: str) -> dict[str, Any]:
    return (await _read_all(client)).get("saves", {}).get(shape) or _blank()


async def _set_state(client: GhostClient, shape: str, state: dict[str, Any] | None) -> None:
    data = await _read_all(client)
    if state is None:
        data["saves"].pop(shape, None)
    else:
        data["saves"][shape] = state
    await _write(client, data)


async def is_dying(client: GhostClient, shape: str) -> bool:
    state = await get_state(client, shape)
    return not state["dead"] and (state["successes"] > 0 or state["failures"] > 0 or state["stable"] is False)


# -- turn order ---------------------------------------------------------------


async def _leave_turn_order(client: GhostClient, shape: str) -> None:
    """Drop a corpse out of initiative, leaving the token on the board."""
    if client.cfg.dry_run:
        log.warning("[dry-run] would remove %s from initiative", shape)
        return
    await client.sio.emit("Initiative.Remove", shape, namespace=GAME_NAMESPACE)


async def _rejoin_turn_order(client: GhostClient, shape: str) -> None:
    """Put a revived character back in the order, with no value.

    No initiative is rolled for them: where someone comes back in is a table
    call, and the DM can type a number or re-roll the layer from the initiative
    panel.
    """
    if client.cfg.dry_run:
        log.warning("[dry-run] would re-add %s to initiative", shape)
        return
    await client.sio.emit(
        "Initiative.Add",
        {"shape": shape, "isVisible": True, "isGroup": False, "effects": []},
        namespace=GAME_NAMESPACE,
    )


# -- the flow -----------------------------------------------------------------


async def on_dropped_to_zero(client: GhostClient, shape: str, name: str) -> list[str]:
    """A token just hit 0 hit points. Returns lines for the ghost to say."""
    if not await is_player_character(client, shape):
        return [f"{name} drops to 0 hit points and dies."]

    await _set_state(client, shape, _blank())
    return [f"{name} drops to 0 hit points and is dying. Death saves on their turn."]


async def on_damage_while_down(client: GhostClient, shape: str, name: str, *, critical: bool = False) -> list[str]:
    """Damage taken at 0 hit points: an automatic failure, two on a critical."""
    state = await get_state(client, shape)
    if state["dead"]:
        return []

    state["failures"] = min(SAVES_TO_DIE, state["failures"] + (2 if critical else 1))
    state["stable"] = False

    if state["failures"] >= SAVES_TO_DIE:
        state["dead"] = True
        await _set_state(client, shape, state)
        await _leave_turn_order(client, shape)
        return [f"{name} is hit while down and dies."]

    await _set_state(client, shape, state)
    hits = "two failures" if critical else "a failure"
    return [f"{name} is hit while down: {hits}, {state['failures']} of {SAVES_TO_DIE}."]


async def roll_save(client: GhostClient, shape: str, name: str) -> list[str]:
    """Roll one death saving throw and apply the result."""
    state = await get_state(client, shape)
    if state["dead"]:
        return [f"{name} is already dead."]
    if state["stable"]:
        return [f"{name} is stable."]

    result = roll("1d20")
    die = result.rolls[0]

    if die == 20:
        # Straight back up, at 1 hit point, and the counters reset.
        await _set_state(client, shape, None)
        await set_hp(client, shape, current=1)
        return [f"{name} rolls a natural 20 and comes back up with 1 hit point."]

    if die == 1:
        state["failures"] = min(SAVES_TO_DIE, state["failures"] + 2)
    elif die >= DEATH_SAVE_DC:
        state["successes"] = min(SAVES_TO_STABILISE, state["successes"] + 1)
    else:
        state["failures"] = min(SAVES_TO_DIE, state["failures"] + 1)

    if state["failures"] >= SAVES_TO_DIE:
        state["dead"] = True
        await _set_state(client, shape, state)
        await _leave_turn_order(client, shape)
        return [f"{name} rolls {die} and dies. The body stays where it fell."]

    if state["successes"] >= SAVES_TO_STABILISE:
        state["stable"] = True
        await _set_state(client, shape, state)
        return [f"{name} rolls {die} and stabilises, unconscious at 0 hit points."]

    await _set_state(client, shape, state)
    outcome = "a success" if die >= DEATH_SAVE_DC else ("two failures" if die == 1 else "a failure")
    return [
        f"{name} rolls {die}: {outcome}. "
        f"{state['successes']} of {SAVES_TO_STABILISE} successes, {state['failures']} of {SAVES_TO_DIE} failures."
    ]


async def on_healed(client: GhostClient, shape: str, name: str) -> list[str]:
    """Anything that puts a character above 0 clears the dying state."""
    state = await get_state(client, shape)
    if state == _blank():
        return []

    was_dead = state["dead"]
    await _set_state(client, shape, None)
    await _rejoin_turn_order(client, shape)

    if was_dead:
        return [f"{name} is back from the dead and rejoins the order."]
    return [f"{name} is back on their feet and rejoins the order."]


async def is_dead(client: GhostClient, shape: str) -> bool:
    return (await get_state(client, shape))["dead"]


async def current_hp(client: GhostClient, shape: str) -> int | None:
    sheet = await read_sheet(client, shape)
    if sheet is None:
        return None
    return sheet.get("hp", {}).get("current")
