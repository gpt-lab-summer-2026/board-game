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
