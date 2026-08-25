"""What is true on the board right now, as facts rather than guesses.

The command translator upstream was being asked to judge things it had no way
of knowing -- whether a target was reachable, whether line of sight was blocked,
which of three goblins was closest, whether an area spell would catch an ally --
while being handed nothing but a list of names. An instruction to reason about
data that is absent does not produce caution; it produces invention, and an
invented distance parses into a perfectly valid command.

So this assembles the facts the ghost already holds -- shapes, sheets, sides,
the turn budget, the visibility geometry -- into one snapshot small enough to
paste into a prompt on every turn.

Nothing here is new information. It is the same data `actions.py` uses to
resolve a command, exposed before the command is written rather than after.
"""
from __future__ import annotations

import logging
from typing import Any

from . import deathsaves, sheet, turns
from .client import GhostClient
from .grid import distance as grid_distance

log = logging.getLogger(__name__)


async def snapshot(client: GhostClient) -> dict[str, Any]:
    """Everything worth telling a language model about the current board."""
    # Imported here, not at module scope: actions imports this module for the
    # suggestion engine, and a top-level import would close the loop.
    from .actions import _build_field

    field = await _build_field(client)

    factions = await _factions(client)
    budget = await turns.read_budget(client)

    people: dict[str, dict[str, Any]] = {}
    for name, uuid in sorted(client.state.characters.items()):
        occupant = field.occupants.get(uuid)
        data = await sheet.read_sheet(client, uuid)
        people[name] = {
            "uuid": uuid,
            "cell": None if occupant is None else [occupant.cell.q, occupant.cell.r],
            "side": _side(factions, uuid),
            **_sheet_facts(data),
        }

    # Pairwise distance and sight, which is the half the model most often had to
    # make up. Computed here because the geometry lives here.
    for name, entry in people.items():
        a = field.occupants.get(entry["uuid"])
        if a is None:
            entry["distance_ft"], entry["sight"] = {}, {}
            continue
        dists: dict[str, int] = {}
        sight: dict[str, bool] = {}
        for other, other_entry in people.items():
            if other == name:
                continue
            b = field.occupants.get(other_entry["uuid"])
            if b is None:
                continue
            dists[other] = int(grid_distance(a.cell, b.cell, field.grid) * field.unit_size)
            sight[other] = field.has_line_of_sight(a.cell, b.cell)
        entry["distance_ft"] = dists
        entry["sight"] = sight

    # Rage is not a catalogue condition, so it has to be added to the column by
    # hand -- and it must be, or the model running the monsters cannot see that
    # the barbarian is already raging and will spend a bonus action doing it
    # again.
    from . import features  # noqa: PLC0415 - circular at import time

    for name, entry in people.items():
        if await features.raging(client, entry["uuid"]):
            entry["conditions"] = [*entry.get("conditions", []), "raging"]

    active = budget.get("active")
    return {
        "grid": {"type": field.grid.name, "feet_per_cell": field.unit_size},
        "round": int(budget.get("round") or 0) + 1,
        "turn_of": _name_of(client, active) if active else None,
        "budget": {
            "action": bool(budget.get("action")),
            "bonus": bool(budget.get("bonus")),
            "movement_used_ft": int(budget.get("movementUsed") or 0),
            "speed_ft": int(budget.get("speed") or 30),
            # What is actually left, Dash included. Reporting speed and spend
            # separately made the model do the subtraction, and it got a Dashed
            # creature wrong every time because the bonus was invisible.
            "movement_left_ft": max(
                0,
                int(budget.get("speed") or 30)
                + int(budget.get("speedBonus") or 0)
                - int(budget.get("movementUsed") or 0),
            ),
            "dash_bonus_ft": int(budget.get("speedBonus") or 0),
        },
        "walls": len(field.blocked),
        "hazards": len(field.hazardous),
        "characters": people,
    }


def _sheet_facts(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {"hp": None, "ac": None, "speed_ft": 30, "class": None, "conditions": [], "spells": [], "slots": None}
    hp = data.get("hp") or {}
    derived = data.get("derived") or {}
    slots = (data.get("slots") or {}).get("1")
    return {
        "class": data.get("classId"),
        "level": data.get("level"),
        "hp": f"{hp.get('current', 0)}/{hp.get('max', 0)}",
        "ac": sheet.armour_class(data),
        "speed_ft": int(data.get("speed") or 30),
        "conditions": list(data.get("conditions") or []),
        "melee": (derived.get("melee") or {}).get("weapon"),
        "ranged": (derived.get("ranged") or {}).get("weapon"),
        "cantrip": (derived.get("cantrip") or {}).get("name"),
        "spells": [s.get("name") for s in (derived.get("spells") or [])],
        "slots": None if slots is None else f"{slots.get('max', 0) - slots.get('used', 0)}/{slots.get('max', 0)}",
    }


async def _factions(client: GhostClient) -> dict[str, Any]:
    data = await sheet._load(
        client, {"source": deathsaves.FACTIONS_SOURCE, "name": deathsaves.FACTIONS_BLOCK, "category": "room"}
    )
    return data if isinstance(data, dict) else {}


def _side(factions: dict[str, Any], uuid: str) -> str:
    """A shape's disposition towards the party, as one word."""
    if uuid in (factions.get("provoked") or []):
        return "hostile"
    faction_id = (factions.get("members") or {}).get(uuid)
    for faction in factions.get("factions") or []:
        if faction.get("id") == faction_id:
            return str(faction.get("disposition") or "unaligned")
    return "unaligned"


def _name_of(client: GhostClient, uuid: str) -> str | None:
    for name, u in client.state.characters.items():
        if u == uuid:
            return name
    return None


def render(state: dict[str, Any]) -> str:
    """The snapshot as a compact table.

    A table rather than the JSON, because the JSON of the same content is
    roughly three times the tokens and models read aligned columns perfectly
    well. Distances are listed one way only -- the matrix is symmetric, and
    printing both halves doubles the size to say the same thing twice.
    """
    lines: list[str] = []
    grid = state["grid"]
    lines.append(
        f"Round {state['round']}, {grid['feet_per_cell']:g} ft per cell"
        + (f", it is {state['turn_of']}'s turn" if state["turn_of"] else ", not in initiative")
    )
    b = state["budget"]
    if state["turn_of"]:
        lines.append(
            f"This turn: action {'spent' if b['action'] else 'available'}, "
            f"bonus {'spent' if b['bonus'] else 'available'}, "
            f"moved {b['movement_used_ft']} of "
            f"{b['speed_ft'] + b['dash_bonus_ft']} ft"
            + (" (dashed)" if b["dash_bonus_ft"] else "")
            + f", {b['movement_left_ft']} ft left"
        )

    lines.append("")
    lines.append(
        f"{'name':<12}{'side':<10}{'class':<10}{'hp':<8}{'ac':<4}{'spd':<5}{'conditions':<14}armed with"
    )
    for name, c in state["characters"].items():
        armed = ", ".join(x for x in (c.get("melee"), c.get("ranged"), c.get("cantrip")) if x) or "-"
        # `armed with` goes last and is never truncated: it is what the caller
        # reads to decide melee vs ranged vs cantrip, and clipping it to fit a
        # column turned a present cantrip into an absent one.
        lines.append(
            f"{name:<12}{c['side']:<10}{str(c.get('class') or '-'):<10}"
            f"{str(c.get('hp') or '-'):<8}{str(c.get('ac') or '-'):<4}{c['speed_ft']:<5}"
            f"{(', '.join(c['conditions']) or '-'):<14}{armed}"
        )

    casters = [(n, c) for n, c in state["characters"].items() if c.get("spells")]
    if casters:
        lines.append("")
        for name, c in casters:
            lines.append(f"{name} has slots {c.get('slots') or '-'} and knows: {', '.join(c['spells'])}")

    lines.append("")
    lines.append("distances in feet, and whether there is line of sight:")
    seen: set[frozenset[str]] = set()
    for name, c in state["characters"].items():
        for other, feet in sorted(c.get("distance_ft", {}).items(), key=lambda kv: kv[1]):
            pair = frozenset((name, other))
            if pair in seen:
                continue
            seen.add(pair)
            blocked = "" if c.get("sight", {}).get(other, True) else "  (no line of sight)"
            lines.append(f"  {name} to {other}: {feet} ft{blocked}")
    return "\n".join(lines)
