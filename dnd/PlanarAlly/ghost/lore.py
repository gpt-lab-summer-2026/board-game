"""The story: an opening to set the scene, and character colour drip-fed after.

Written as data, not generated. The cluster could produce this on the fly, but
it should not: flavour that changes every time you hear it stops being the
character's and starts being noise, and a model improvising backstory mid-combat
will eventually contradict the sheet in front of the players. These lines are
fixed, they are checked against the character they belong to, and each one is
told once.

The drip is deliberately slow. A line after every action would bury the
mechanics the table actually needs to hear -- and every line is also several
seconds of synthesis on a Pi. `MIN_GAP` commands must pass between beats, so the
colour lands in the quiet moments rather than on top of the dice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import sheet
from .client import GhostClient

log = logging.getLogger(__name__)

STORE = "pa-lore"
BLOCK = "told"

# Commands that must pass between two beats. Three is roughly one beat per
# creature per round at this table, which reads as seasoning rather than a
# narrator talking over the fight.
MIN_GAP = 3


OPENING = (
    "The mine breathes cold air at your backs. Emo, Elf and the cat climb the last "
    "of the switchbacks with a satchel of raw gems -- enough, you had thought, to "
    "see the village through the winter. "
    "Then you crest the ridge, and the village is burning. "
    "Three goblins move between the houses with the unhurried confidence of "
    "creatures expecting no resistance. The doors are barred, the shutters are "
    "down, and whoever is still alive is holding their breath behind them. "
    "And something else is out there. Past the well, a hamster the size of a cart "
    "has stopped being anybody's problem but its own. It did not come with the "
    "goblins. It is not with them now. It simply wants everything on this hill to "
    "stop moving. "
    "You are three, you are tired, and you are already downhill of all of it."
)


@dataclass(frozen=True)
class Beat:
    """One line of colour, and what has to happen for it to be told.

    `character` None means anyone; `actions` empty means any action. Both empty
    would fire on the first thing that happens, which is why nothing in the
    table below leaves both blank.
    """

    key: str
    text: str
    character: str | None = None
    actions: frozenset[str] = field(default_factory=frozenset)

    def matches(self, actor: str | None, action: str) -> bool:
        if self.character is not None:
            if actor is None or actor.strip().lower() != self.character:
                return False
        if self.actions and action not in self.actions:
            return False
        return True

    @property
    def specificity(self) -> int:
        """Prefer the line written for this exact character doing this exact thing."""
        return (1 if self.character else 0) + (1 if self.actions else 0)


BEATS: list[Beat] = [
    # -- Emo: barbarian, and a career that predates the barbarian part ---------
    Beat(
        "emo-topple",
        "In his years as a career criminal, Emo learned that a do-gooder on their "
        "back is a do-gooder not shouting for the watch. The technique has not "
        "changed. Only the clientele.",
        "emo", frozenset({"contest"}),
    ),
    Beat(
        "emo-melee",
        "Emo does not fence. Emo settles.",
        "emo", frozenset({"attack"}),
    ),
    Beat(
        "emo-down",
        "Emo has been left for dead in nicer parts of the country than this, and "
        "has a strong record of disagreeing with the assessment.",
        "emo", frozenset({"death_save"}),
    ),
    Beat(
        "emo-move",
        "He walks like a man who has never once been the first to arrive somewhere "
        "and has always known the way out.",
        "emo", frozenset({"move", "move_dir", "retreat"}),
    ),
    # -- Elf: the wizard, and the reason there were gems to fetch --------------
    Beat(
        "elf-cast",
        "Elf reads the spell off the inside of her eyelids, the way you recite an "
        "address you have never once written down.",
        "elf", frozenset({"cast"}),
    ),
    Beat(
        "elf-measure",
        "Elf paces the distance without appearing to look at it. Wizards count. It "
        "is most of the job.",
        "elf", frozenset({"measure"}),
    ),
    Beat(
        "elf-retreat",
        "Every apprentice is taught that the second-best position is the one you "
        "are still alive in. Elf was a very good apprentice.",
        "elf", frozenset({"retreat", "move_dir"}),
    ),
    # -- The cat: nobody's companion, technically everybody's ------------------
    Beat(
        "cat-attack",
        "The cat has no opinion about gems, goblins, or the village. The cat has an "
        "opinion about the thing that moved.",
        "cat", frozenset({"attack"}),
    ),
    Beat(
        "cat-move",
        "It followed them down into the mine and it has followed them back out, and "
        "at no point has anyone established whose cat it is.",
        "cat", frozenset({"move", "move_dir"}),
    ),
    # -- The goblins -----------------------------------------------------------
    Beat(
        "freak-cast",
        "Freak learned magic the way a magpie learns locks: by watching, badly, and "
        "then trying it anyway. It has never stopped being surprised when it works.",
        "freak", frozenset({"cast", "attack"}),
    ),
    Beat(
        "gentelman-cast",
        "Gentelman has a name it chose for itself and a hat it did not. It insists "
        "on both, at length, to anyone it has not yet set on fire.",
        "gentelman", frozenset({"cast", "attack"}),
    ),
    Beat(
        "weirdo-cast",
        "Weirdo casts with its eyes shut. None of the others have asked why, and "
        "Weirdo has never volunteered.",
        "weirdo", frozenset({"cast", "attack"}),
    ),
    Beat(
        "goblins-plan",
        "They did not come here with a plan. They came here with a direction, and "
        "the village happened to be in it.",
        None, frozenset({"cast"}),
    ),
    # -- The hamster -----------------------------------------------------------
    Beat(
        "hamster-attack",
        "The hamster is not with the goblins. The hamster is not with anyone. "
        "Something woke it, and it has been settling that debt with whatever is "
        "nearest ever since.",
        "hamster", frozenset({"attack", "contest"}),
    ),
    Beat(
        "hamster-move",
        "It does not charge so much as arrive, the way weather arrives.",
        "hamster", frozenset({"move", "move_dir"}),
    ),
]


def _repr() -> dict[str, Any]:
    return {"source": STORE, "name": BLOCK, "category": "room"}


async def _told(client: GhostClient) -> dict[str, Any]:
    data = await sheet._load(client, _repr())
    return data if isinstance(data, dict) else {"keys": [], "since": 0, "opening": False}


async def _save(client: GhostClient, data: dict[str, Any]) -> None:
    await sheet._save(client, _repr(), data)


async def opening(client: GhostClient, *, force: bool = False) -> list[str]:
    """The prologue. Told once unless asked for again."""
    state = await _told(client)
    if state.get("opening") and not force:
        return ["The story has already been told. Say 'tell it again' to hear it."]
    state["opening"] = True
    # The prologue is long, and a beat immediately after it would be piling on.
    state["since"] = 0
    await _save(client, state)
    return [OPENING]


async def beat(client: GhostClient, actor: str | None, action: str) -> str | None:
    """A line of colour for what just happened, or None -- usually None.

    Persisted rather than kept in memory: the ghost is restarted often enough
    that an in-memory set would replay the whole backstory every time, which is
    precisely the thing that turns flavour into noise.
    """
    try:
        state = await _told(client)
    except Exception:  # noqa: BLE001 - colour is never worth failing a command over
        log.exception("could not read the lore block")
        return None

    told = set(state.get("keys") or [])
    since = int(state.get("since") or 0) + 1

    candidates = [b for b in BEATS if b.key not in told and b.matches(actor, action)]
    if not candidates or since <= MIN_GAP:
        state["since"] = since
        try:
            await _save(client, state)
        except Exception:  # noqa: BLE001
            log.exception("could not update the lore block")
        return None

    # Most specific wins, and the table order breaks ties -- so the line written
    # for "emo topples someone" beats the one written for "somebody casts".
    chosen = max(candidates, key=lambda b: b.specificity)
    told.add(chosen.key)
    state.update({"keys": sorted(told), "since": 0})
    try:
        await _save(client, state)
    except Exception:  # noqa: BLE001
        log.exception("could not update the lore block")
        return None
    return chosen.text


async def reset(client: GhostClient) -> list[str]:
    """Re-arm every beat, for the next session on the same board."""
    await _save(client, {"keys": [], "since": 0, "opening": False})
    return [f"The story is reset: {len(BEATS)} beats and the opening are unheard again."]


async def status(client: GhostClient) -> list[str]:
    state = await _told(client)
    told = len(state.get("keys") or [])
    return [
        f"Opening: {'told' if state.get('opening') else 'not yet'}. "
        f"Beats: {told} of {len(BEATS)} told."
    ]
