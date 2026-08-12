"""Turning "elf ranged attack on goblin" into something the ghost can do.

Deterministic, not model-driven, and that is deliberate. The board-game half of
this project already learned the lesson the hard way: a 4B model asked to pick
between two similar proper nouns reliably loses to lexical similarity, and the
fix was to let exact string matching win wherever it applies. Character names
are exactly that case -- they are a known, short, closed set.

So the grammar below handles the phrasings a table actually uses, and anything
it cannot parse is *reported as unparsed* rather than guessed at. The SLM stage
in the pipeline belongs in front of this, normalising free speech into one of
these shapes; `parse` is then the thing that decides what actually happens. A
mis-parse that says "I didn't understand" costs a repeat; a mis-parse that
attacks the wrong creature costs the game.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Action(str, Enum):
    ATTACK = "attack"
    MOVE = "move"
    MEASURE = "measure"
    DUPLICATE = "duplicate"
    CONDITION = "condition"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    HELP = "help"


class AttackKind(str, Enum):
    MELEE = "melee"
    RANGED = "ranged"
    CANTRIP = "cantrip"


@dataclass
class Intent:
    action: Action
    actor: str | None = None
    target: str | None = None
    kind: AttackKind | None = None
    bias: str = "normal"
    condition: str | None = None
    condition_on: bool = True
    raw: str = ""


class ParseError(ValueError):
    """Raised with a message meant to be read aloud to the player."""


_KIND_WORDS = {
    "melee": AttackKind.MELEE,
    "close": AttackKind.MELEE,
    "sword": AttackKind.MELEE,
    "claw": AttackKind.MELEE,
    "claws": AttackKind.MELEE,
    "bite": AttackKind.MELEE,
    "ranged": AttackKind.RANGED,
    "range": AttackKind.RANGED,
    "bow": AttackKind.RANGED,
    "shoot": AttackKind.RANGED,
    "shoots": AttackKind.RANGED,
    "fire": AttackKind.RANGED,
    "cantrip": AttackKind.CANTRIP,
    "spell": AttackKind.CANTRIP,
    "cast": AttackKind.CANTRIP,
    "casts": AttackKind.CANTRIP,
}

_BIAS_WORDS = {
    "advantage": "advantage",
    "disadvantage": "disadvantage",
}

_ATTACK_VERBS = ("attack", "attacks", "strike", "strikes", "hit", "hits", "shoot", "shoots", "cast", "casts")
_MOVE_VERBS = ("move", "moves", "walk", "walks", "go", "goes", "approach", "approaches")
_MEASURE_VERBS = ("measure", "distance", "range", "far", "ruler")

# "measure from X to Y", "how far is X from Y", "distance X to Y"
# "duplicate gobbo as gobbo two" / "copy the goblin as goblin 2"
# "apply prone to gobbo", "gobbo is poisoned", "clear prone from gobbo"
_CONDITION_RE = re.compile(
    r"^\s*(?:(?P<apply>apply|give|set)|(?P<clear>clear|remove|cure|end))\s+"
    r"(?P<cond>[\w\' -]+?)\s+(?:to|on|from)\s+(?P<who>.+?)\s*$",
    re.I,
)

_DUPLICATE_RE = re.compile(
    r"^\s*(?:duplicate|copy|clone)\s+(?P<a>.+?)(?:\s+(?:as|called|named)\s+(?P<b>.+?))?\s*$",
    re.I,
)

_MEASURE_RE = re.compile(
    r"^\s*(?:measure|distance|ruler|how\s+far(?:\s+is)?)\s+"
    r"(?:from\s+|between\s+)?(?P<a>.+?)\s+(?:to|from|and)\s+(?P<b>.+?)\s*$",
    re.I,
)

# Answers to a held question. Kept generous because these arrive by voice,
# where "yeah" and "go on" are as likely as "yes".
_YES = {"yes", "y", "yeah", "yep", "do it", "go", "go on", "confirm", "walk", "ok", "okay"}
_NO = {"no", "n", "nope", "cancel", "stop", "abort", "nevermind", "never mind"}

# "<actor> <stuff> <verb> ... (on|at|against|towards) <target>"
_TARGET_SPLIT = re.compile(r"\b(?:on|at|against|toward|towards|to)\b", re.I)
_FILLER = {"the", "a", "an", "please", "and", "with", "his", "her", "their", "its"}


def _clean(words: Iterable[str]) -> str:
    return " ".join(w for w in words if w not in _FILLER).strip()


def parse(text: str) -> Intent:
    raw = text.strip()
    lowered = raw.lower()
    if not lowered:
        raise ParseError("Nothing to do -- say a command.")

    if lowered in {"help", "?", "commands"}:
        return Intent(Action.HELP, raw=raw)
    if lowered in _YES:
        return Intent(Action.CONFIRM, raw=raw)
    if lowered in _NO:
        return Intent(Action.CANCEL, raw=raw)

    # Measuring reads verb-first ("measure from the elf to the goblin"), which
    # is the opposite order to every other command, so it gets its own pattern
    # rather than being bent through the actor-verb-target logic below.
    cond = _CONDITION_RE.match(lowered)
    if cond:
        return Intent(
            Action.CONDITION,
            actor=_clean(cond['who'].split()) or None,
            condition=_clean(cond['cond'].split()).replace(' ', '-') or None,
            condition_on=cond['apply'] is not None,
            raw=raw,
        )

    duped = _DUPLICATE_RE.match(lowered)
    if duped:
        source = _clean(duped['a'].split())
        # Without an explicit name, number it; a table with four goblins
        # does not want to invent names for them.
        target = _clean((duped['b'] or '').split()) or None
        if not source:
            raise ParseError("Duplicate who? Try 'duplicate gobbo as gobbo two'.")
        return Intent(Action.DUPLICATE, actor=source, target=target, raw=raw)

    measured = _MEASURE_RE.match(lowered)
    if measured:
        return Intent(
            Action.MEASURE,
            actor=_clean(measured["a"].split()) or None,
            target=_clean(measured["b"].split()) or None,
            raw=raw,
        )

    words = re.findall(r"[\w'-]+", lowered)

    bias = "normal"
    for w in list(words):
        if w in _BIAS_WORDS:
            bias = _BIAS_WORDS[w]
            words.remove(w)

    kind = next((_KIND_WORDS[w] for w in words if w in _KIND_WORDS), None)

    verb_index = next(
        (i for i, w in enumerate(words) if w in _ATTACK_VERBS or w in _MOVE_VERBS or w in _MEASURE_VERBS),
        None,
    )
    if verb_index is None:
        raise ParseError(
            f"I couldn't find an action in {raw!r}. Try 'elf ranged attack on goblin'."
        )
    verb = words[verb_index]
    if verb in _MEASURE_VERBS:
        action = Action.MEASURE
    elif verb in _MOVE_VERBS:
        action = Action.MOVE
    else:
        action = Action.ATTACK

    # Everything before the verb, minus the words that described the attack
    # kind, is the actor. "elf ranged attack on goblin" -> actor "elf".
    before = [w for w in words[:verb_index] if w not in _KIND_WORDS and w not in _MEASURE_VERBS]
    after = words[verb_index + 1 :]

    # The target follows a preposition where there is one; otherwise it is
    # simply whatever trails the verb ("elf attacks goblin").
    tail = " ".join(after)
    parts = _TARGET_SPLIT.split(tail, maxsplit=1)
    target_words = (parts[1] if len(parts) > 1 else parts[0]).split()
    # A kind word can trail the verb too: "attack the goblin in melee".
    target_words = [w for w in target_words if w not in _KIND_WORDS]

    actor = _clean(before) or None
    target = _clean(target_words) or None

    if actor is None:
        raise ParseError(f"Who is acting? I heard {raw!r}.")
    if target is None:
        raise ParseError(f"{actor} needs a target. Try '{actor} melee attack on goblin'.")

    if action is Action.ATTACK and kind is None:
        # "cast"/"shoot" already imply a kind; a bare "attack" does not, and
        # guessing melee would send a wizard running at a dragon.
        raise ParseError(
            f"Melee, ranged or cantrip? Try '{actor} ranged attack on {target}'."
        )

    return Intent(action=action, actor=actor, target=target, kind=kind, bias=bias, raw=raw)


HELP_TEXT = """Commands:
  <actor> melee attack on <target>      walk into reach, then strike
  <actor> ranged attack on <target>     shoot from where you stand
  <actor> cantrip on <target>           cast the equipped cantrip
  <actor> moves to <target>             walk towards without attacking
  measure from <actor> to <target>      distance and line of sight, drawn on the map
  duplicate <actor> [as <name>]         copy a character, sheet and all
  apply <condition> to <target>         prone, poisoned, stunned, ...
  clear <condition> from <target>       remove it again
Add "with advantage" or "with disadvantage" to any attack.
When the only route crosses a hazard the ghost asks first: answer yes or no."""
