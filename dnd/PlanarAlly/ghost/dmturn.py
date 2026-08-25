"""The ghost running the monsters.

D&D has one person deciding what the goblins do, and at this table that person
was also the one holding the microphone for their own character. Voice commands
belong to the players; everything on the other side of the board should take its
own turn.

The shape of it matters more than the cleverness. A model asked "what does the
goblin do?" will happily answer with something the goblin cannot do -- a spell
with no slots left, an attack on a creature behind a wall, a move it has no
movement for. So the model never writes a command here. The board enumerates
every *legal* option first, using the same action book the on-screen panel is
built from, and the model's entire job is to pick a number out of that list. The
reply is checked back against the list before anything happens.

That keeps the judgement where a model is actually good -- "which of these six
things is the best idea right now" -- and keeps the legality where code is good.
A cluster that is slow, unreachable or confused degrades to a deterministic
heuristic rather than to a goblin casting a spell it does not have.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import aiohttp

from . import actionbook, sheet, worldstate
from .client import GhostClient

log = logging.getLogger(__name__)

# The disposition the players hold. Everything else is the ghost's to run.
PLAYER_SIDE = "party"

MODEL = os.getenv("GHOST_DM_MODEL", os.getenv("GHOST_MODEL", "llama3.3:70b"))
TIMEOUT = float(os.getenv("GHOST_DM_TIMEOUT", "60"))

# How many options to put in front of the model. Enumerating every spell against
# every target on a seven-creature board is a long list for one decision, and a
# long list is where a model starts picking by position rather than by merit.
MAX_OPTIONS = 24

# Entries the action panel offers a person that are not a monster's turn.
_NOT_A_TURN = {"Measure", "End turn"}


async def sides(client: GhostClient) -> dict[str, str]:
    factions = await worldstate._factions(client)
    return {u: worldstate._side(factions, u) for u in client.state.shapes}


async def controlled(client: GhostClient, uuid: str | None) -> bool:
    """Is this creature the ghost's to run?

    Anything not on the players' side, and still standing. A downed monster is
    left alone -- it has death saves or it is simply out, and either way the
    ghost stepping in to act for it would be inventing a rule.
    """
    if uuid is None:
        return False
    if (await sides(client)).get(uuid) == PLAYER_SIDE:
        return False
    data = await sheet.read_sheet(client, uuid)
    if data is None:
        return False
    return int((data.get("hp") or {}).get("current", 0)) > 0


def _name_of(client: GhostClient, uuid: str) -> str | None:
    for name, u in client.state.characters.items():
        if u == uuid:
            return name
    return None


async def options(client: GhostClient, uuid: str) -> list[str]:
    """Every command this creature could legally issue right now.

    Built from `actionbook.for_character`, which is the same list the action
    panel shows -- so what the ghost can choose for a monster is exactly what a
    player can choose for a character, and a capability added in one place shows
    up in both.
    """
    me = _name_of(client, uuid)
    if me is None:
        return []

    disposition = await sides(client)
    enemies: list[str] = []
    for name, other in client.state.characters.items():
        if other == uuid or disposition.get(other) != PLAYER_SIDE:
            continue
        data = await sheet.read_sheet(client, other)
        if data is None or int((data.get("hp") or {}).get("current", 0)) <= 0:
            continue
        enemies.append(name)

    book = await actionbook.for_character(client, me)
    commands: list[str] = []
    for group in book.get("groups") or []:
        # Compass moves are a wall of eight near-identical lines that crowd out
        # everything else; a monster that wants to reposition can move towards
        # or away from somebody, which is what it actually means.
        if group.get("name") == "Move in a direction":
            continue
        for entry in group.get("entries") or []:
            # Not choices a monster should be able to make with its turn. The
            # action book is built for a person clicking, and a person clicking
            # "Measure" has not spent their turn -- a monster picking it has.
            if entry.get("label") in _NOT_A_TURN:
                continue
            command = str(entry.get("command") or "")
            if not command:
                continue
            if entry.get("needsTarget"):
                for enemy in enemies:
                    commands.append(command.replace("{t}", enemy))
            elif "{t}" not in command:
                commands.append(command)

    # Stable, de-duplicated, and capped.
    seen: list[str] = []
    for c in commands:
        if c not in seen:
            seen.append(c)
    return seen[:MAX_OPTIONS]


async def beast_choice(client: GhostClient, uuid: str, options_: list[str]) -> str | None:
    """A target for something that does not plan, only picks.

    The hamster has no spells and no ranged attack; asking a 70B model which of
    "claw the elf" and "claw the cat" is wiser costs two seconds to answer a
    question with a short arithmetic answer. So creatures with nothing to choose
    *between* get scored here instead, and the cluster is left for the ones with
    an actual decision.

    Distance dominates, because that is what a beast is doing -- going for what
    is nearest. Wounded and lightly armoured targets pull it sideways, which is
    the difference between "nearest" and "best nearby": a hamster that walks
    past a dying elf to maul a healthy barbarian looks broken even though
    "nearest" said so.
    """
    me = _name_of(client, uuid)
    if me is None:
        return None
    state = await worldstate.snapshot(client)
    mine = (state.get("characters") or {}).get(me) or {}
    distances = mine.get("distance_ft") or {}
    sight = mine.get("sight") or {}
    disposition = await sides(client)

    best: tuple[float, str] | None = None
    for name, entry in (state.get("characters") or {}).items():
        if name == me:
            continue
        if disposition.get((entry or {}).get("uuid")) != PLAYER_SIDE:
            continue
        current, _, maximum = str(entry.get("hp") or "0/0").partition("/")
        try:
            hp_now, hp_max = int(current), max(1, int(maximum))
        except ValueError:
            continue
        if hp_now <= 0:
            continue

        feet = float(distances.get(name, 9999))
        # Distance in cells rather than feet, so the weights below do not have
        # to be retuned for a different grid scale.
        cells = feet / max(1.0, float((state.get("grid") or {}).get("feet_per_cell") or 5))
        score = cells
        # A target already down to a third pulls about two cells closer.
        score -= 3.0 * (1.0 - hp_now / hp_max)
        # So does one that is easy to hit, mildly.
        score += 0.15 * (int(entry.get("ac") or 10) - 10)
        # Something it cannot see is a guess, not a target.
        if not sight.get(name, True):
            score += 6.0
        if best is None or score < best[0]:
            best = (score, name)

    if best is None:
        return None
    target = best[1]
    for option in options_:
        if "melee attack on " + target in option:
            return option
    for option in options_:
        if "moves to " + target in option:
            return option
    return None


def _is_beast(options_: list[str]) -> bool:
    """Nothing to decide between: no spells, no cantrip, no ranged attack."""
    return not any(
        k in o for o in options_ for k in (" casts ", " cantrip on ", " ranged attack on ", " throws ")
    )


def _fallback(options_: list[str]) -> str | None:
    """What to do when the cluster cannot be asked.

    Ordered by how much a monster wants to do it, not by how clever it is:
    hurt somebody, then close the distance, then anything at all. Deliberately
    boring -- a predictable goblin is much easier to debug than a surprising
    one, and this path exists for the moments when something is already wrong.
    """
    for verb in ("casts", "cantrip on", "melee attack on", "ranged attack on",
                 "moves to", "throws"):
        for option in options_:
            if verb in option:
                return option
    return options_[0] if options_ else None


_PICK = re.compile(r"\b(\d{1,2})\b")


async def choose(client: GhostClient, uuid: str, options_: list[str]) -> tuple[str | None, str]:
    """Ask the cluster to pick one option. Returns (command, why)."""
    from .translate import cluster_url  # noqa: PLC0415 - avoids an import cycle

    if not options_:
        return None, "nothing it could do"
    if len(options_) == 1:
        return options_[0], "the only thing it could do"

    if _is_beast(options_):
        picked = await beast_choice(client, uuid, options_)
        if picked is not None:
            return picked, "scored locally -- it has nothing to choose between"

    url = cluster_url()
    if url is None:
        return _fallback(options_), "no cluster configured"

    me = _name_of(client, uuid) or "the creature"
    board = worldstate.render(await worldstate.snapshot(client))
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(options_, 1))

    prompt = (
        f"You are running {me}, a hostile creature in a D&D combat, against the "
        f"party. Choose what it does on its turn.\n\n"
        f"THE BOARD RIGHT NOW\n{board}\n\n"
        f"{me} may do exactly one of these:\n{numbered}\n\n"
        "Reply with the number alone. Nothing else -- no reasoning, no "
        "punctuation, no restatement of the option.\n\n"
        "Choose well, the way a person running this monster would:\n"
        "- Attack something you can actually reach or see. The table above has "
        "every distance and says when there is no line of sight.\n"
        "- Prefer finishing a badly hurt enemy over spreading damage around.\n"
        "- Spend a spell slot when it is worth more than a weapon hit; keep it "
        "when the fight is nearly over.\n"
        "- Close the distance if nothing is in range.\n"
        f"- {me} is a monster, not a tactician with perfect information. Simple "
        "and aggressive beats clever."
    )

    body = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "options": {"num_ctx": 32768, "temperature": 0.3},
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    return _fallback(options_), f"cluster said {resp.status}"
                payload = json.loads(await resp.text())
    except Exception as exc:  # noqa: BLE001 - a dead cluster must not stall the turn
        log.warning("dm turn: cluster unreachable: %s", exc)
        return _fallback(options_), "cluster unreachable"

    reply = str((payload.get("message") or {}).get("content") or "").strip()
    found = _PICK.search(reply)
    if not found:
        log.warning("dm turn: no number in %r", reply[:80])
        return _fallback(options_), "the model did not answer with a number"
    index = int(found.group(1))
    if not 1 <= index <= len(options_):
        # The check that makes this safe: an out-of-range pick is a pick of
        # nothing, not a command to go and interpret.
        log.warning("dm turn: %d is outside 1..%d", index, len(options_))
        return _fallback(options_), f"the model picked {index}, which is not on the list"
    return options_[index - 1], "chosen"
