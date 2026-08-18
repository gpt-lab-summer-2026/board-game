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
    DEATH_SAVE = "death_save"
    HEAL = "heal"
    AC_MODIFIER = "ac_modifier"
    SAVE = "save"
    CHECK = "check"
    CONTEST = "contest"
    CAST = "cast"
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
    """How much a heal restores; None means "just enough to be conscious"."""
    heal_amount: int | None = None
    """Signed change to armour class, for a temporary bonus or penalty."""
    ac_delta: int | None = None
    """What to call the AC modifier in the breakdown, e.g. "half cover"."""
    ac_source: str | None = None
    """Rounds the modifier lasts; None leaves it until someone clears it."""
    ac_rounds: int | None = None
    """Ability key for a saving throw, e.g. "dex"."""
    ability: str | None = None
    """Skill or ability name for a check."""
    skill: str | None = None
    """Difficulty class to beat; None means just report the roll."""
    dc: int | None = None
    """Which contest is being run: grapple, shove or disarm."""
    contest: str | None = None
    """Spell name, as spoken."""
    spell: str | None = None
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

# "with advantage", "at disadvantage", or the bare word on the end.
_BIAS_PHRASE = re.compile(r"\s*\b(?:with|at|having)?\s*\b(?:dis)?advantage\b\s*$", re.I)


def _bias_of(text: str) -> str:
    """Pick advantage or disadvantage out of a phrase, defaulting to neither.

    Word-boundary matched, because "disadvantage" contains "advantage" and a
    substring test would read every disadvantaged roll as an advantaged one.
    """
    for word in re.findall(r"[a-z]+", text):
        if word in _BIAS_WORDS:
            return _BIAS_WORDS[word]
    return "normal"


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

# "atton death save", "roll a death save for atton", "death saving throw atton"
_DEATH_SAVE_RE = re.compile(
    r"^\s*(?:(?:roll\s+)?(?:a\s+)?death\s+sav(?:e|ing\s+throw)\s+(?:for\s+)?(?P<b>.+?)"
    r"|(?P<a>.+?)\s+(?:rolls?\s+)?(?:a\s+)?death\s+sav(?:e|ing\s+throw))\s*$",
    re.I,
)

# "heal atton 5", "heal atton for 5 hit points"
_HEAL_RE = re.compile(
    r"^\s*(?:heal|heals|healing)\s+(?P<who>.+?)(?:\s+(?:for|by)?\s*(?P<amount>\d+))?"
    r"(?:\s+(?:hit\s+points?|hp))?\s*$",
    re.I,
)

# "give elf +2 ac for 2 rounds", "elf gets -1 ac from bane",
# "atton +5 ac shield spell for 1 round"
_AC_MOD_RE = re.compile(
    r"^\s*(?:give\s+)?(?P<who>.+?)\s+(?:gets?\s+|takes?\s+)?"
    r"(?P<delta>[+-]\s*\d+)\s*(?:to\s+)?(?:ac|armou?r\s+class)"
    r"(?:\s+(?:from|for|due\s+to)\s+(?P<source>(?!\d)[^,]+?))?"
    r"(?:\s+for\s+(?P<rounds>\d+)\s+rounds?)?\s*$",
    re.I,
)

# "clear ac modifiers from elf", "reset elf ac"
_AC_CLEAR_RE = re.compile(
    r"^\s*(?:clear|remove|reset)\s+(?:all\s+)?(?:ac|armou?r\s+class)\s*"
    r"(?:modifiers?|bonus(?:es)?)?\s*(?:from|on|for)?\s+(?P<who>.+?)\s*$"
    r"|^\s*(?:clear|remove|reset)\s+(?P<b>.+?)(?:'s)?\s+(?:ac|armou?r\s+class)"
    r"\s*(?:modifiers?|bonus(?:es)?)?\s*$",
    re.I,
)

# Abilities may be spoken in full or abbreviated.
ABILITY_WORDS = {
    "str": "str", "strength": "str",
    "dex": "dex", "dexterity": "dex",
    "con": "con", "constitution": "con",
    "int": "int", "intelligence": "int",
    "wis": "wis", "wisdom": "wis",
    "cha": "cha", "charisma": "cha",
}

# "elf dex save", "elf makes a dexterity saving throw dc 15",
# "roll a wisdom save for atton"
_SAVE_RE = re.compile(
    r"^\s*(?:roll\s+)?(?:a\s+)?(?:(?P<ab_first>[a-z]+)\s+sav(?:e|ing\s+throw)\s+(?:for\s+)?(?P<who_last>.+?)"
    r"|(?P<who_first>.+?)\s+(?:makes?\s+|rolls?\s+)?(?:a\s+)?(?P<ab_last>[a-z]+)\s+sav(?:e|ing\s+throw))"
    r"(?:\s+(?:against\s+|vs\.?\s+)?dc\s*(?P<dc>\d+))?\s*$",
    re.I,
)

# "elf stealth check", "atton makes an athletics check dc 12",
# "roll perception for cat"
_CHECK_RE = re.compile(
    r"^\s*(?:roll\s+)?(?:an?\s+)?(?:(?P<sk_first>[a-z][a-z ]*?)\s+check\s+for\s+(?P<who_last>.+?)"
    r"|(?P<who_first>.+?)\s+(?:makes?\s+|rolls?\s+)?(?:an?\s+)?(?P<sk_last>[a-z][a-z ]*?)\s+check)"
    r"(?:\s+(?:against\s+|vs\.?\s+)?dc\s*(?P<dc>\d+))?\s*$",
    re.I,
)

# "elf grapples gobbo", "atton shoves the goblin", "cat disarms emo"
_CONTEST_RE = re.compile(
    r"^\s*(?P<a>.+?)\s+(?:tries\s+to\s+)?(?P<verb>grapples?|shoves?|disarms?)\s+(?P<b>.+?)\s*$",
    re.I,
)

# "elf casts magic missile on emo", "cast cure wounds on atton",
# "wizard casts burning hands"
_CAST_RE = re.compile(
    r"^\s*(?:(?P<who>.+?)\s+casts?|casts?)\s+(?P<spell>.+?)"
    r"(?:\s+(?:on|at|against|targeting)\s+(?P<target>.+?))?\s*$",
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
    # Checked before conditions: "clear ac modifiers from elf" also matches the
    # generic "clear <condition> from <target>" shape, and would otherwise be
    # read as removing a condition literally named "ac modifiers".
    cleared = _AC_CLEAR_RE.match(lowered)
    if cleared:
        who = _clean((cleared["who"] or cleared["b"] or "").split())
        if not who:
            raise ParseError("Clear whose AC modifiers?")
        # A clear is the same intent with no delta: the executor reads
        # `ac_delta is None` as "remove everything" rather than needing a verb
        # of its own.
        return Intent(Action.AC_MODIFIER, actor=who, raw=raw)

    modded = _AC_MOD_RE.match(lowered)
    if modded:
        who = _clean(modded["who"].split())
        if not who:
            raise ParseError("Whose armour class?")
        delta = int(modded["delta"].replace(" ", ""))
        if delta == 0:
            raise ParseError("A modifier of +0 would not do anything.")
        return Intent(
            Action.AC_MODIFIER,
            actor=who,
            ac_delta=delta,
            ac_source=_clean(modded["source"].split()) if modded["source"] else None,
            ac_rounds=int(modded["rounds"]) if modded["rounds"] else None,
            raw=raw,
        )

    cond = _CONDITION_RE.match(lowered)
    if cond:
        return Intent(
            Action.CONDITION,
            actor=_clean(cond['who'].split()) or None,
            condition=_clean(cond['cond'].split()).replace(' ', '-') or None,
            condition_on=cond['apply'] is not None,
            raw=raw,
        )

    saved = _DEATH_SAVE_RE.match(lowered)
    if saved:
        who = _clean((saved["a"] or saved["b"] or "").split())
        if not who:
            raise ParseError("Death save for whom?")
        return Intent(Action.DEATH_SAVE, actor=who, raw=raw)

    # After the death-save branch on purpose: "elf death save" also matches the
    # generic "<who> <ability> save" shape, with "death" read as an ability.
    # "with advantage" is a modifier on the roll, not part of the sentence the
    # patterns below describe. Removing it once here beats an optional tail on
    # every pattern -- and the attack parser already ignores these words.
    bias = _bias_of(lowered)
    trimmed = _BIAS_PHRASE.sub("", lowered).strip()

    save_m = _SAVE_RE.match(trimmed)
    if save_m:
        word = (save_m["ab_first"] or save_m["ab_last"] or "").strip()
        ability = ABILITY_WORDS.get(word)
        if ability is not None:
            who = _clean((save_m["who_first"] or save_m["who_last"] or "").split())
            if not who:
                raise ParseError("Whose saving throw?")
            return Intent(
                Action.SAVE,
                actor=who,
                ability=ability,
                dc=int(save_m["dc"]) if save_m["dc"] else None,
                bias=bias,
                raw=raw,
            )

    check_m = _CHECK_RE.match(trimmed)
    if check_m:
        skill = _clean((check_m["sk_first"] or check_m["sk_last"] or "").split())
        who = _clean((check_m["who_first"] or check_m["who_last"] or "").split())
        if not who:
            raise ParseError("Whose check?")
        if not skill:
            raise ParseError("A check of what?")
        return Intent(
            Action.CHECK,
            actor=who,
            skill=ABILITY_WORDS.get(skill, skill),
            dc=int(check_m["dc"]) if check_m["dc"] else None,
            bias=bias,
            raw=raw,
        )

    contest_m = _CONTEST_RE.match(trimmed)
    if contest_m:
        actor = _clean(contest_m["a"].split())
        target = _clean(contest_m["b"].split())
        if not actor or not target:
            raise ParseError("A contest needs both sides.")
        return Intent(
            Action.CONTEST,
            actor=actor,
            target=target,
            contest=contest_m["verb"].rstrip("s").lower(),
            raw=raw,
        )

    cast_m = _CAST_RE.match(trimmed)
    if cast_m:
        who = _clean((cast_m["who"] or "").split())
        if not who:
            raise ParseError("Who is casting?")
        spell = _clean(cast_m["spell"].split())
        if not spell:
            raise ParseError("Cast what?")
        return Intent(
            Action.CAST,
            actor=who,
            target=_clean(cast_m["target"].split()) if cast_m["target"] else None,
            spell=spell,
            bias=bias,
            raw=raw,
        )

    healed = _HEAL_RE.match(lowered)
    if healed:
        who = _clean(healed["who"].split())
        if not who:
            raise ParseError("Heal whom?")
        return Intent(
            Action.HEAL,
            actor=who,
            heal_amount=int(healed["amount"]) if healed["amount"] else None,
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
  <actor> death save                   roll a death saving throw for a downed PC
  heal <actor> [for N]                 restore hit points; revived PCs rejoin the order
  give <actor> +N ac [from <what>] [for N rounds]   a temporary bonus or penalty
  clear ac modifiers from <actor>      drop every temporary AC change
  <actor> casts <spell> [on <target>]  spend a slot and resolve it
  <actor> <ability> save [dc N]        one saving throw
  <actor> <skill> check [dc N]         one ability or skill check
  <actor> grapples/shoves/disarms <target>   a contested check
Add "with advantage" or "with disadvantage" to any attack.
When the only route crosses a hazard the ghost asks first: answer yes or no."""
