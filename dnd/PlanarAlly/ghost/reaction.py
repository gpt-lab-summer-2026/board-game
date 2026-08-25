"""Shield: the one reaction that changes a hit that has already been rolled.

Kept apart from `actions` because it is the only thing in the system that
reaches *backwards*. Every other rule reads the board, decides, and writes; this
one waits for a number to exist and then argues with it.

Who decides is the whole design:

* A player's character is asked. Shield costs a slot and a reaction, and whether
  a 14 is worth burning both is the sort of judgement that belongs to the person
  playing the wizard -- and it is a judgement they can only make once they have
  seen the roll, which is why the question comes mid-attack rather than before.
* A monster decides for itself, on the rule that makes it worth casting at all:
  spend it exactly when +5 turns the hit into a miss. Never on a roll that
  misses anyway, never on one that beats AC 5 over.

Both halves refuse the same three ways -- no Shield prepared, no slot, no
reaction left -- so a creature cannot Shield twice in a round or out of nothing.
"""
from __future__ import annotations

import logging

from . import sheet, turns
from .client import GhostClient

log = logging.getLogger(__name__)

SHIELD_AC = 5
SHIELD_ROUNDS = 1
_SHIELD_NAMES = {"shield"}


def _prepared_shield(data: dict | None) -> dict | None:
    """The Shield entry off a sheet, or None.

    Matched by name against the derived spell list rather than by id, because
    the derived block is what the ghost reads everywhere else and an id lookup
    would be a second source of truth for the same question.
    """
    for spell in ((data or {}).get("derived") or {}).get("spells") or []:
        if str(spell.get("name", "")).strip().lower() in _SHIELD_NAMES:
            return spell
    return None


async def available(client: GhostClient, uuid: str) -> bool:
    """Could this creature cast Shield right now?"""
    data = await sheet.read_sheet(client, uuid)
    spell = _prepared_shield(data)
    if spell is None:
        return False
    if int((data.get("hp") or {}).get("current", 0)) <= 0:
        return False
    level = str(int(spell.get("level") or 1))
    slot = ((data.get("slots") or {}).get(level)) or {}
    if int(slot.get("max", 0)) - int(slot.get("used", 0)) <= 0:
        return False
    return await turns.has_reaction(client, uuid)


async def would_save(client: GhostClient, uuid: str, to_hit: int, armour_class: int) -> bool:
    """Would +5 turn this particular hit into a miss?

    The only case worth spending on. A roll that already misses needs nothing,
    and one that clears AC by six or more is not stopped by five.
    """
    if not (armour_class <= to_hit < armour_class + SHIELD_AC):
        return False
    return await available(client, uuid)


async def cast(client: GhostClient, uuid: str, name: str | None) -> list[str]:
    """Spend the slot and the reaction, and put the +5 on the sheet.

    The modifier is written as a normal timed AC modifier rather than applied to
    `ac` directly, so it shows up in the sheet's breakdown, expires on the
    ghost's own duration tick, and can be cleared by hand if the table decides
    something else happened.
    """
    data = await sheet.read_sheet(client, uuid)
    spell = _prepared_shield(data)
    if spell is None:
        return []
    who = name or "it"
    ok, left = await sheet.spend_slot(client, uuid, int(spell.get("level") or 1))
    if not ok:
        return [f"{who} has no slot left for Shield."]
    await turns.use_reaction(client, uuid)
    total = await sheet.set_ac_modifier(client, uuid, SHIELD_AC, "Shield", SHIELD_ROUNDS)
    return [f"{who} casts Shield as a reaction ({left} slot(s) left): AC {total} until its next turn."]


async def worth_it_against(client: GhostClient, uuid: str, damage: int) -> bool:
    """For damage that no AC can dodge -- Magic Missile and its kin.

    Shield stops those outright, so there is no roll to compare against and the
    question becomes "is this hit big enough to be worth a slot". Half of what
    is left, or anything lethal. A monster burning its last slot to avoid three
    damage is the kind of play that reads as a bug.
    """
    if not await available(client, uuid):
        return False
    data = await sheet.read_sheet(client, uuid)
    current = int(((data or {}).get("hp") or {}).get("current", 0))
    if current <= 0:
        return False
    return damage >= current or damage * 2 >= current
