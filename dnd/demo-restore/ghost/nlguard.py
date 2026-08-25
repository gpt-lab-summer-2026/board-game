"""Refusing commands the player did not actually ask for.

Lives in the ghost package because both callers are downstream of it: the voice
loop in ../python and the in-game console, which now talks to the cluster
itself. One copy, so a threshold tuned for one is tuned for both.

The translator hallucinates names. Not often, and less with the board table in
front of it, but "kill emo" still came back as `hamster melee attack on emo` --
a character the player never mentioned, in a command that parses cleanly and
would have executed on the board. Prompt wording reduces this; it does not
remove it, and the failure is silent, which is the worst kind.

So every name the model puts in a command is checked back against what the
player actually said. This is deterministic and cheap, and it cannot be talked
out of by a confident model. It only ever *rejects* -- it never rewrites a
command into something else, because guessing what they meant is the mistake it
exists to catch.
"""
from __future__ import annotations

import difflib
import re

# Loose enough for a speech-to-text mangling ("gobbo" heard as "gobo"), tight
# enough that "hamster" does not match "emo".
# Calibrated, not guessed: across mangled-but-said names the lowest score was
# 0.667 ("kat" for "cat") and across never-said names the highest was 0.500
# ("emo" against "elf moves north"). 0.60 sits between with room either side.
_SIMILARITY = 0.60


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _mentioned(name: str, said: str) -> bool:
    """Did the player plausibly say this character's name?

    Compares against single words and adjacent pairs, so a two-word name like
    "gobel 2" can match even though neither half alone would.
    """
    words = _tokens(said)
    target = " ".join(_tokens(name))
    if not target:
        return False
    if target in " ".join(words):
        return True

    candidates = list(words) + [f"{a} {b}" for a, b in zip(words, words[1:])]
    return any(
        difflib.SequenceMatcher(None, target, c).ratio() >= _SIMILARITY for c in candidates
    )


def unrequested_names(command: str, said: str, characters: list[str]) -> list[str]:
    """Characters named in the command that the player never mentioned."""
    in_command = [c for c in characters if c.lower() in command.lower()]
    return [c for c in in_command if not _mentioned(c, said)]


def check(command: str, said: str, characters: list[str]) -> tuple[bool, str]:
    """(accepted, reason). Reason is a question to put back to the player."""
    invented = unrequested_names(command, said, characters)
    if invented:
        joined = " and ".join(invented)
        return False, f"You didn't say {joined} -- who did you mean?"
    return True, ""


# Commands where one character is spending their turn doing something. The rest
# -- measuring, applying a condition, healing, adjusting AC -- are the DM's
# bookkeeping and belong to whoever is running the table, not to whoever is up.
TURN_BOUND_ACTIONS = {
    "attack", "move", "move_dir", "retreat", "cast", "contest", "check", "save",
}


def wrong_turn(action: str, actor: str | None, active: str | None) -> str | None:
    """Reject an action taken by someone whose turn it is not.

    A far better answer to the hallucinated-actor problem than name matching:
    when the initiative order says it is the elf's turn, `hamster melee attack
    on emo` is wrong no matter how confidently it was produced, and no amount of
    string similarity was ever going to establish that.

    Returns the reason to read back, or None if the action is allowed. Silent
    when nobody is up, because out of initiative anyone may do anything.
    """
    if active is None or actor is None:
        return None
    if action not in TURN_BOUND_ACTIONS:
        return None
    if actor.strip().lower() == active.strip().lower():
        return None
    return f"It is {active}'s turn, not {actor}'s. Did you mean {active}?"
