"""Class features that change how damage is worked out: Rage and Sneak Attack.

Both are the same shape of problem and neither fits anywhere that already
exists. They are not spells, not conditions, and not items -- they are rules
that sit *inside* the damage calculation and change the number, which is why
they live together here rather than being scattered across `actions`.

Rage state is kept in a room block rather than as a condition, because
`sheet.set_condition` validates against the catalogue's vocabulary and refuses
anything not in it -- correctly, since "poisonned" should be a question rather
than a new condition nobody can look up. Inventing a "raging" entry to get
around that would put a rule in the vocabulary table, where the next person to
read it would not expect one. The board table shows it instead.
"""
from __future__ import annotations

import logging
from typing import Any

from . import sheet
from .client import GhostClient
from .grid import distance as grid_distance

log = logging.getLogger(__name__)

STORE = "pa-features"
BLOCK = "state"

# 5e: two rages a day at levels 1-2, ten rounds each, +2 damage until level 9.
RAGE_USES = 2
RAGE_ROUNDS = 10
RAGE_DAMAGE = 2

PHYSICAL = {"bludgeoning", "piercing", "slashing"}

# Reach for "threatened": one cell, the same number melee uses everywhere else.
THREAT_CELLS = 1


def _repr() -> dict[str, Any]:
    return {"source": STORE, "name": BLOCK, "category": "room"}


async def _load(client: GhostClient) -> dict[str, Any]:
    data = await sheet._load(client, _repr())
    return data if isinstance(data, dict) else {}


async def _save(client: GhostClient, data: dict[str, Any]) -> None:
    await sheet._save(client, _repr(), data)


def _entry(state: dict[str, Any], uuid: str) -> dict[str, Any]:
    return dict(state.get(uuid) or {})


# ---- Rage -------------------------------------------------------------------


async def raging(client: GhostClient, uuid: str) -> bool:
    return int(_entry(await _load(client), uuid).get("rageRounds") or 0) > 0


async def rages_left(client: GhostClient, uuid: str) -> int:
    return max(0, RAGE_USES - int(_entry(await _load(client), uuid).get("rageUsed") or 0))


async def start_rage(client: GhostClient, uuid: str, name: str) -> list[str]:
    """Spend a use and start raging. The caller has already spent the bonus action."""
    state = await _load(client)
    entry = _entry(state, uuid)
    used = int(entry.get("rageUsed") or 0)
    if used >= RAGE_USES:
        return [f"{name} has no rages left until a long rest."]
    entry["rageUsed"] = used + 1
    entry["rageRounds"] = RAGE_ROUNDS
    state[uuid] = entry
    await _save(client, state)
    return [
        f"{name} rages: +{RAGE_DAMAGE} melee damage and half damage from weapons, "
        f"for {RAGE_ROUNDS} rounds ({RAGE_USES - used - 1} left today)."
    ]


async def stop_rage(client: GhostClient, uuid: str) -> None:
    state = await _load(client)
    entry = _entry(state, uuid)
    if not entry.get("rageRounds"):
        return
    entry["rageRounds"] = 0
    state[uuid] = entry
    await _save(client, state)


async def damage_type_of(client: GhostClient, attack: dict[str, Any] | None) -> str | None:
    """What kind of damage this attack deals.

    The sheet's derived attack block does not carry a damage type -- it has the
    weapon's *name*, the dice and the to-hit, because nothing needed the type
    until resistance existed. Rather than bump the mod and re-derive every
    sheet, the type is looked back up in the catalogue the weapon came from.

    Falls back to None, which `resisted` treats as "not physical" -- so an
    unknown weapon is never quietly halved.
    """
    if attack is None:
        return None
    stated = attack.get("damageType")
    if stated:
        return str(stated)
    weapon = str(attack.get("weapon") or "").strip().lower()
    if not weapon:
        return None
    catalogue = await sheet.read_catalogue(client) or {}
    for entry in catalogue.get("weapons") or []:
        if str(entry.get("name", "")).strip().lower() == weapon:
            return entry.get("damageType")
    return None


def resisted(amount: int, damage_type: str | None, is_raging: bool) -> int:
    """Halve physical damage for a raging creature, rounding down as 5e does.

    Only the three weapon types. A raging barbarian is as flammable as anyone
    else, and quietly halving fire damage is the kind of wrong that never gets
    noticed because it always looks plausible.
    """
    if not is_raging or amount <= 0:
        return amount
    if str(damage_type or "").strip().lower() not in PHYSICAL:
        return amount
    return amount // 2


async def tick(client: GhostClient) -> list[str]:
    """Count rages down a round. Called on the same beat as every other duration."""
    state = await _load(client)
    lines: list[str] = []
    changed = False
    for uuid, entry in list(state.items()):
        rounds = int((entry or {}).get("rageRounds") or 0)
        if rounds <= 0:
            continue
        rounds -= 1
        state[uuid] = {**entry, "rageRounds": rounds}
        changed = True
        if rounds == 0:
            name = next((n for n, u in client.state.characters.items() if u == uuid), "it")
            lines.append(f"{name}'s rage ends")
    if changed:
        await _save(client, state)
    return lines


# ---- Sneak Attack -----------------------------------------------------------


def sneak_dice(level: int) -> int:
    """1d6 at levels 1-2, and a die every two levels after."""
    return max(1, (max(1, int(level)) + 1) // 2)


def threatened_by(
    field, uuid: str, sides: dict[str, str], melee: dict[str, bool],
    *, ignore: str | None = None,
) -> str | None:
    """Who is threatening this creature, or None.

    One definition, three consumers, because in 5e it is one condition: an enemy
    with a melee weapon inside its reach. That is what gives ranged attacks
    disadvantage, what lets a rogue sneak attack, and what makes leaving provoke
    an opportunity attack -- so deriving it three times invites three subtly
    different answers to the same question.

    `melee` says who is actually carrying something to threaten with; a creature
    with no melee attack is standing next to you, not menacing you. `ignore`
    drops one uuid, which is how a rogue asks "is my mark threatened by somebody
    *other than me*".
    """
    subject = field.occupants.get(uuid)
    if subject is None:
        return None
    theirs = sides.get(uuid)
    for other, occupant in field.occupants.items():
        if other == uuid or other == ignore:
            continue
        if sides.get(other) == theirs:
            continue
        if occupant.is_defeated or not melee.get(other, False):
            continue
        if grid_distance(occupant.cell, subject.cell, field.grid) <= THREAT_CELLS:
            return occupant.name or other[:8]
    return None


async def melee_armed(client: GhostClient, uuids) -> dict[str, bool]:
    """uuid -> does it have a melee attack at all.

    Read once per resolution rather than per pair: `threatened_by` is asked
    about every creature on the board and a sheet read each time would be a
    round trip per pair.
    """
    armed: dict[str, bool] = {}
    for uuid in uuids:
        data = await sheet.read_sheet(client, uuid)
        armed[uuid] = bool(((data or {}).get("derived") or {}).get("melee"))
    return armed


# ---- Rest -------------------------------------------------------------------


async def long_rest(client: GhostClient, uuid: str) -> None:
    """Everything this module tracks, back to the start of the day."""
    state = await _load(client)
    if uuid not in state:
        return
    state[uuid] = {**state[uuid], "rageUsed": 0, "rageRounds": 0}
    await _save(client, state)
