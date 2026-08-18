"""Reading and writing character sheets from the ghost.

The character editor mod stores everything in PlanarAlly DataBlocks, which are
plain socket events -- so the ghost gets at exactly the same data the browser
does, without a browser. That is the whole point of putting the sheet in a
DataBlock rather than in component state.

Deliberately, none of the 5e arithmetic lives here. The mod computes attack and
damage notation and writes it into `sheet["derived"]`; this module reads those
strings and hands them to `ghost.dice`. Two implementations of the same rules
would drift, and the first symptom would be a voice-rolled attack quietly using
the wrong modifier.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .client import GAME_NAMESPACE, GhostClient

log = logging.getLogger(__name__)

class CatalogueNotReady(RuntimeError):
    """The room catalogue has not been migrated by a browser client yet."""


SOURCE = "scc"
SHEET_BLOCK = "sheet"
CATALOGUE_BLOCK = "catalogue"


def _repr(name: str, shape: str | None = None) -> dict[str, Any]:
    if shape is None:
        return {"source": SOURCE, "name": name, "category": "room"}
    return {"source": SOURCE, "name": name, "category": "shape", "shape": shape}


async def _load(client: GhostClient, repr_: dict[str, Any], timeout: float = 10) -> dict[str, Any] | None:
    # DataBlock.Load answers with the row or None; the payload's `data` is a
    # JSON *string*, not a nested object.
    raw = await client.sio.call("DataBlock.Load", repr_, namespace=GAME_NAMESPACE, timeout=timeout)
    if raw is None:
        return None
    return json.loads(raw["data"])


async def _save(client: GhostClient, repr_: dict[str, Any], data: dict[str, Any]) -> None:
    """Write a block, creating it only if it does not exist yet.

    Order matters, and getting it wrong is silent and destructive.
    `DataBlock.Create` performs no uniqueness check -- it just inserts --
    while `DataBlock.Load`/`Save` resolve with `get_or_none`, which returns
    the *first* matching row. An earlier version tried Create first and fell
    back to Save, which inserted a fresh row on every single write: reads
    kept returning the original while every ghost update piled up in rows
    nothing ever looked at. Fifteen of them, before it was noticed.

    So: check, then write.
    """
    payload = {**repr_, "data": json.dumps(data)}
    if client.cfg.dry_run:
        log.warning("[dry-run] would write %s", repr_["name"])
        return

    existing = await client.sio.call(
        "DataBlock.Load", repr_, namespace=GAME_NAMESPACE, timeout=10
    )
    if existing is None:
        await client.sio.call("DataBlock.Create", payload, namespace=GAME_NAMESPACE, timeout=10)
    else:
        await client.sio.emit("DataBlock.Save", payload, namespace=GAME_NAMESPACE)


async def read_sheet(client: GhostClient, shape: str) -> dict[str, Any] | None:
    """A character's sheet, or None if nobody has opened its tab yet."""
    return await _load(client, _repr(SHEET_BLOCK, shape))


async def read_catalogue(client: GhostClient) -> dict[str, Any] | None:
    """The campaign's weapons/races/backgrounds/classes.

    Worth reading before parsing a voice command: it is the authoritative list
    of what "attack with the longsword" can mean in this campaign, so the
    intent layer can validate against it instead of a hardcoded copy.
    """
    return await _load(client, _repr(CATALOGUE_BLOCK))


async def write_sheet(client: GhostClient, shape: str, sheet: dict[str, Any]) -> None:
    await _save(client, _repr(SHEET_BLOCK, shape), sheet)


def armour_class(sheet: dict[str, Any] | None) -> int | None:
    """The AC to beat, preferring the itemised breakdown over the bare number.

    `derived.ac.total` is what the mod computes from armour, Dexterity and any
    temporary modifiers; `ac` is the same number written back to the top level so
    the AC tracker can render it. Reading the breakdown first means a bonus that
    arrived after the last full save -- half cover, a shield spell -- still counts,
    and the flat field remains the fallback for sheets written before v0.12.0.
    """
    if not sheet:
        return None
    derived = sheet.get("derived") or {}
    block = derived.get("ac") or {}
    total = block.get("total")
    if total is None:
        total = sheet.get("ac")
    try:
        value = int(total or 0)
    except (TypeError, ValueError):
        return None
    return value or None


@dataclass
class AttackResult:
    """What an attack produced, plus the descriptor it came from.

    The descriptor is returned rather than kept private because the caller
    needs `applies` to know what condition the blow inflicts. Reaching for
    a variable that only existed inside this function is what broke every
    attack between v0.6.0 and now.
    """

    to_hit: Any | None
    damage: Any
    attack: dict[str, Any]

    def __iter__(self):
        """Still unpacks as (to_hit, damage) for older call sites."""
        return iter((self.to_hit, self.damage))


ATTACK_KINDS = ("melee", "ranged", "cantrip")

# Which key on the derived attack to roll. The sheet stores all three ready to
# use, so "roll that with advantage" costs no arithmetic here.
_BIAS_KEY = {
    "normal": "attack",
    "advantage": "attackAdvantage",
    "disadvantage": "attackDisadvantage",
}


async def roll_attack(
    client: GhostClient,
    shape: str,
    kind: str = "melee",
    bias: str = "normal",
    as_player: str | None = None,
    share_with: str = "all",
):
    """Roll a character's attack and damage, announced under their own name.

    `kind` is melee, ranged or cantrip; `bias` is normal, advantage or
    disadvantage. Returns (attack, damage), or None when nothing of that kind
    is equipped.

    A save-based cantrip has no attack roll at all -- it is the target who
    rolls -- so only the damage is returned, paired with None.
    """
    if kind not in ATTACK_KINDS:
        raise ValueError(f"unknown attack kind {kind!r}; expected one of {ATTACK_KINDS}")
    if bias not in _BIAS_KEY:
        raise ValueError(f"unknown bias {bias!r}; expected one of {tuple(_BIAS_KEY)}")

    sheet = await read_sheet(client, shape)
    if sheet is None:
        raise KeyError(f"no sheet for shape {shape}; open its Character tab once first")

    attack = sheet.get("derived", {}).get(kind)
    if attack is None:
        return None

    name = attack.get("weapon") or attack.get("name") or kind

    notation = attack.get(_BIAS_KEY[bias])
    if notation is None:
        # Save-based cantrip: report the DC rather than inventing a to-hit.
        damage = await client.roll_dice(attack["damage"], share_with=share_with, as_player=as_player)
        log.info(
            "%s: DC %s %s save, %s damage",
            name, attack.get("saveDc"), (attack.get("save") or "").upper(), damage.total,
        )
        return AttackResult(None, damage, attack)

    to_hit = await client.roll_dice(notation, share_with=share_with, as_player=as_player)
    damage = await client.roll_dice(attack["damage"], share_with=share_with, as_player=as_player)
    log.info(
        "%s (%s%s): %s to hit, %s damage",
        name, kind, "" if bias == "normal" else f", {bias}", to_hit.total, damage.total,
    )
    return AttackResult(to_hit, damage, attack)


# 5e's skill list, keyed to the ability each one uses. Duplicated from the mod's
# data.ts rather than shared, because the two live in different runtimes; the
# authority is the sheet's `derived.skills`, and this table is only the fallback
# for a sheet written before skills existed.
SKILL_ABILITY = {
    "acrobatics": "dex", "animal handling": "wis", "arcana": "int", "athletics": "str",
    "deception": "cha", "history": "int", "insight": "wis", "intimidation": "cha",
    "investigation": "int", "medicine": "wis", "nature": "int", "perception": "wis",
    "performance": "cha", "persuasion": "cha", "religion": "int",
    "sleight of hand": "dex", "stealth": "dex", "survival": "wis",
}

ABILITY_NAMES = {
    "str": "Strength", "dex": "Dexterity", "con": "Constitution",
    "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma",
}


def signed(value: int) -> str:
    """+3 / -1, for reading a modifier out loud."""
    return f"+{value}" if value >= 0 else str(value)


def _ability_mod(score: int) -> int:
    return (int(score) - 10) // 2


def _bias_notation(bonus: int, bias: str) -> str:
    """1d20 with the modifier, or the two-dice forms for (dis)advantage."""
    sign = "+" if bonus >= 0 else "-"
    tail = f"{sign}{abs(bonus)}"
    if bias == "advantage":
        return f"2d20kh1{tail}"
    if bias == "disadvantage":
        return f"2d20kl1{tail}"
    return f"1d20{tail}"


def save_bonus(sheet: dict[str, Any] | None, ability: str) -> int:
    """A saving throw bonus, preferring what the mod worked out."""
    if not sheet:
        return 0
    saves = (sheet.get("derived") or {}).get("saves") or {}
    entry = saves.get(ability)
    if isinstance(entry, dict) and entry.get("bonus") is not None:
        return int(entry["bonus"])
    return _ability_mod((sheet.get("abilities") or {}).get(ability, 10))


def skill_bonus(sheet: dict[str, Any] | None, skill: str) -> tuple[int, str]:
    """A skill bonus and the ability it keys off."""
    key = skill.strip().lower()
    ability = SKILL_ABILITY.get(key, "str")
    if not sheet:
        return 0, ability
    skills = (sheet.get("derived") or {}).get("skills") or {}
    entry = skills.get(key.replace(" ", "-"))
    if isinstance(entry, dict) and entry.get("bonus") is not None:
        return int(entry["bonus"]), str(entry.get("ability") or ability)
    return _ability_mod((sheet.get("abilities") or {}).get(ability, 10)), ability


async def roll_save(
    client: GhostClient,
    shape: str,
    ability: str,
    *,
    bias: str = "normal",
    as_player: str | None = None,
):
    """Roll one saving throw. Returns the dice result."""
    data = await read_sheet(client, shape)
    bonus = save_bonus(data, ability)
    return await client.roll_dice(
        _bias_notation(bonus, bias), share_with="all", as_player=as_player
    ), bonus


async def roll_check(
    client: GhostClient,
    shape: str,
    skill: str,
    *,
    bias: str = "normal",
    as_player: str | None = None,
):
    """Roll one ability or skill check. Returns (result, bonus, ability)."""
    data = await read_sheet(client, shape)
    if skill in ABILITY_NAMES:
        # A raw ability check: the modifier only, never proficiency. Using the
        # saving-throw bonus here would quietly add proficiency for the two
        # abilities the class is proficient in.
        ability = skill
        bonus = _ability_mod(((data or {}).get("abilities") or {}).get(skill, 10))
    else:
        bonus, ability = skill_bonus(data, skill)
    result = await client.roll_dice(
        _bias_notation(bonus, bias), share_with="all", as_player=as_player
    )
    return result, bonus, ability


# -- spell slots ---------------------------------------------------------------


async def spend_slot(client: GhostClient, shape: str, level: int = 1) -> tuple[bool, int]:
    """Burn one spell slot. Returns (succeeded, slots left).

    A creature with no slot table at all -- a monster, or a martial -- is let
    through rather than blocked: the table's own ruling on whether a goblin
    shaman has slots should not be overridden by an empty dict.
    """
    data = await read_sheet(client, shape)
    if data is None:
        return True, 0
    slots = data.get("slots") or {}
    entry = slots.get(str(level))
    if not isinstance(entry, dict):
        return True, 0

    used = int(entry.get("used") or 0)
    maximum = int(entry.get("max") or 0)
    if used >= maximum:
        return False, 0

    entry["used"] = used + 1
    data["slots"] = {**slots, str(level): entry}
    await write_sheet(client, shape, data)
    return True, maximum - entry["used"]


def find_prepared(sheet: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    """Match a spoken spell name against what the character has prepared."""
    if not sheet:
        return None
    wanted = name.strip().lower()
    spells = (sheet.get("derived") or {}).get("spells") or []
    for spell in spells:
        if str(spell.get("name", "")).lower() == wanted:
            return spell
    # A partial match, so "magic missile" still finds it when the speaker adds
    # a word: "cast magic missiles".
    for spell in spells:
        label = str(spell.get("name", "")).lower()
        if label and (label in wanted or wanted in label):
            return spell
    return None


async def set_ac_modifier(
    client: GhostClient, shape: str, value: int, source: str, rounds: int | None
) -> int:
    """Attach a temporary AC change and return the new total."""
    import uuid as _uuid

    data = await read_sheet(client, shape)
    if data is None:
        return 0
    mods = list(data.get("acModifiers") or [])
    mods.append({
        "id": str(_uuid.uuid4()),
        "source": source,
        "value": value,
        "duration": {"kind": "rounds", "remaining": rounds} if rounds else {"kind": "manual"},
    })
    data["acModifiers"] = mods

    block = (data.get("derived") or {}).get("ac") or {}
    total_mods = sum(int(m.get("value") or 0) for m in mods)
    without = int(block.get("total") or data.get("ac") or 10) - int(block.get("modifiers") or 0)
    data["ac"] = without + total_mods
    if block:
        block["modifiers"] = total_mods
        block["total"] = data["ac"]

    await write_sheet(client, shape, data)
    return data["ac"]


async def set_condition(
    client: GhostClient, shape: str, condition: str, on: bool = True
) -> list[str]:
    """Apply or clear a condition. Returns the resulting list.

    Conditions live on the sheet, not in PlanarAlly -- the game has no such
    concept. The catalogue is the vocabulary, so an unknown id is refused
    rather than invented: 'poisonned' should be a question, not a new
    condition nobody can look up.
    """
    catalogue = await read_catalogue(client) or {}
    known = {c["id"]: c for c in catalogue.get("conditions", [])}
    if not known:
        # The condition vocabulary is seeded by the mod's catalogue
        # migration, which runs in the browser. Until a client has loaded
        # the new version there is nothing to validate against, and
        # inventing a second copy of the list here is exactly the drift the
        # rest of this file avoids.
        raise CatalogueNotReady(
            "the campaign catalogue has no conditions yet -- reload the game "
            "tab once so the mod can seed them"
        )
    if condition not in known:
        raise KeyError(condition)

    sheet_data = await read_sheet(client, shape)
    if sheet_data is None:
        raise KeyError(f"no sheet for shape {shape}; open its Character tab once first")

    conditions = list(sheet_data.get("conditions") or [])
    if on and condition not in conditions:
        conditions.append(condition)
    elif not on and condition in conditions:
        conditions.remove(condition)
    sheet_data["conditions"] = conditions
    await write_sheet(client, shape, sheet_data)

    # Unconscious is the only one PA models itself.
    if known[condition].get("impliesDefeated"):
        await client.emit("Shape.Options.Defeated.Set", {"shape": shape, "value": on})
    return conditions


async def condition_names(client: GhostClient, ids: list[str]) -> list[str]:
    catalogue = await read_catalogue(client) or {}
    lookup = {c["id"]: c["name"] for c in catalogue.get("conditions", [])}
    return [lookup.get(i, i) for i in ids]


async def cantrip_at_close_range(client: GhostClient, shape: str) -> bool:
    """Whether this character's cantrip takes disadvantage next to an enemy.

    Exposed so the intent layer can ask the question rather than hardcoding the
    rule: the mod already decided it (melee spell attacks are exempt).
    """
    sheet = await read_sheet(client, shape)
    cantrip = (sheet or {}).get("derived", {}).get("cantrip")
    return bool(cantrip and cantrip.get("closeRangeDisadvantage"))


async def set_hp(
    client: GhostClient,
    shape: str,
    current: int | None = None,
    max_hp: int | None = None,
    temp: int | None = None,
) -> dict[str, Any]:
    """Change a character's hit points, in the sheet and on the token.

    Both halves are needed. The sheet is what the editor and the ghost read;
    the tracker is what everyone actually *sees* on the token. Writing only one
    of them leaves the table looking at a stale number.
    """
    sheet = await read_sheet(client, shape)
    if sheet is None:
        raise KeyError(f"no sheet for shape {shape}; open its Character tab once first")

    hp = sheet["hp"]
    if current is not None:
        hp["current"] = current
    if max_hp is not None:
        hp["max"] = max_hp
    if temp is not None:
        hp["temp"] = temp

    await write_sheet(client, shape, sheet)

    tracker_id = sheet.get("trackerIds", {}).get("hp")
    if tracker_id is not None:
        await client.emit(
            "Shape.Options.Tracker.Update",
            {
                "shape": shape,
                "uuid": tracker_id,
                "value": hp["current"] + hp["temp"],
                "maxvalue": hp["max"],
            },
        )
    else:
        log.warning("no HP tracker for %s; the sheet was updated but the token was not", shape)

    return hp


async def damage(client: GhostClient, shape: str, amount: int) -> dict[str, Any]:
    """Apply damage, spending temporary hit points first as 5e does."""
    sheet = await read_sheet(client, shape)
    if sheet is None:
        raise KeyError(f"no sheet for shape {shape}")

    hp = sheet["hp"]
    absorbed = min(hp.get("temp", 0), amount)
    return await set_hp(
        client,
        shape,
        current=max(0, hp["current"] - (amount - absorbed)),
        temp=hp.get("temp", 0) - absorbed,
    )
