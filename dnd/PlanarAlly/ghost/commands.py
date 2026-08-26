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
    RETREAT = "retreat"
    MOVE_DIR = "move_dir"
    JUMP = "jump"
    USE_ITEM = "use_item"
    DASH = "dash"
    PROLOGUE = "prologue"
    STORY_RESET = "story_reset"
    TARGET = "target"
    CLEAR_TARGET = "clear_target"
    OPPORTUNITY = "opportunity"
    UNDO = "undo"
    RAGE = "rage"
    LONG_REST = "long_rest"
    LEVEL_UP = "level_up"
    RESUME = "resume"
    DM_AUTO = "dm_auto"
    TELEPORT = "teleport"
    SET_ROUND = "set_round"
    ROLL_INITIATIVE = "roll_initiative"
    CLEAR_INITIATIVE = "clear_initiative"
    END_COMBAT = "end_combat"
    NEXT_TURN = "next_turn"
    PREV_TURN = "prev_turn"
    WHOSE_TURN = "whose_turn"
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
    """Compass heading: north, southwest, and so on."""
    direction: str | None = None
    """Consumable name, as spoken."""
    item: str | None = None
    raw: str = ""


class ParseError(ValueError):
    """Raised with a message meant to be read aloud to the player."""


class ClarificationNeeded(ParseError):
    """The translator asked the player something instead of issuing a command.

    Subclasses ParseError deliberately: callers written before the two-channel
    contract existed catch ParseError and report "unclear", which is a poor
    answer but not a broken one. Callers that know about it read `.question`
    and put it to the player instead.
    """

    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


# Words that name *which* attack, as opposed to the fact that one is happening.
# Deliberately generous: this is spoken at a table, and a parser that only
# accepts the wording in the help text pushes every other phrasing out to the
# cluster for a two-second round trip -- or worse, refuses it.
_KIND_WORDS = {
    # melee
    "melee": AttackKind.MELEE, "close": AttackKind.MELEE, "adjacent": AttackKind.MELEE,
    "sword": AttackKind.MELEE, "blade": AttackKind.MELEE, "axe": AttackKind.MELEE,
    "staff": AttackKind.MELEE, "quarterstaff": AttackKind.MELEE, "mace": AttackKind.MELEE,
    "spear": AttackKind.MELEE, "rapier": AttackKind.MELEE, "dagger": AttackKind.MELEE,
    "claw": AttackKind.MELEE, "claws": AttackKind.MELEE, "bite": AttackKind.MELEE,
    "hooves": AttackKind.MELEE, "punch": AttackKind.MELEE, "unarmed": AttackKind.MELEE,
    "stab": AttackKind.MELEE, "stabs": AttackKind.MELEE,
    "slash": AttackKind.MELEE, "slashes": AttackKind.MELEE,
    "swing": AttackKind.MELEE, "swings": AttackKind.MELEE,
    "smack": AttackKind.MELEE, "smacks": AttackKind.MELEE,
    "clobber": AttackKind.MELEE, "clobbers": AttackKind.MELEE,
    # ranged
    "ranged": AttackKind.RANGED, "range": AttackKind.RANGED, "distance": AttackKind.RANGED,
    "bow": AttackKind.RANGED, "shortbow": AttackKind.RANGED, "longbow": AttackKind.RANGED,
    "crossbow": AttackKind.RANGED, "sling": AttackKind.RANGED, "javelin": AttackKind.RANGED,
    "arrow": AttackKind.RANGED, "bolt": AttackKind.RANGED, "shoot": AttackKind.RANGED,
    "shoots": AttackKind.RANGED, "fire": AttackKind.RANGED, "loose": AttackKind.RANGED,
    # cantrip / spell attack
    "cantrip": AttackKind.CANTRIP, "spell": AttackKind.CANTRIP, "cast": AttackKind.CANTRIP,
    "casts": AttackKind.CANTRIP, "magic": AttackKind.CANTRIP, "magical": AttackKind.CANTRIP,
    "arcane": AttackKind.CANTRIP, "zap": AttackKind.CANTRIP, "zaps": AttackKind.CANTRIP,
    "blast": AttackKind.CANTRIP, "blasts": AttackKind.CANTRIP, "bolt_spell": AttackKind.CANTRIP,
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


_ATTACK_VERBS = (
    "attack", "attacks", "strike", "strikes", "hit", "hits", "shoot", "shoots",
    "cast", "casts", "stab", "stabs", "slash", "slashes", "swing", "swings",
    "zap", "zaps", "blast", "blasts", "smack", "smacks", "clobber", "clobbers",
)
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
    r"^\s*(?P<a>.+?)\s+(?:tries\s+to\s+)?(?P<verb>grapples?|shoves?|disarms?|topples?|trips?)\s+(?P<b>.+?)\s*$",
    re.I,
)

# "elf casts magic missile on emo", "cast cure wounds on atton",
# "wizard casts burning hands"
_CAST_RE = re.compile(
    r"^\s*(?:(?P<who>.+?)\s+casts?|casts?)\s+(?P<spell>.+?)"
    r"(?:\s+(?:on|at|against|targeting)\s+(?P<target>.+?))?\s*$",
    re.I,
)

# "elf dashes", "cat takes the dash action", "elf dash"
_RAGE_RE = re.compile(r"^\s*(?P<a>.+?)\s+(?:rages|enters?\s+(?:a\s+)?rage|goes\s+berserk)\s*$", re.I)
_LEVEL_UP_RE = re.compile(r"^\s*(?:level\s+up\s+(?P<b>.+?)|(?P<a>.+?)\s+levels?\s+up)\s*$", re.I)
_LONG_REST = {"long rest", "take a long rest", "the party rests", "make camp", "rest for the night"}

_DASH_RE = re.compile(r"^\s*(?P<a>.+?)\s+(?:takes\s+the\s+)?dash(?:es|\s+action)?\s*$", re.I)

# "elf jumps towards hamster", "cat leaps at emo", "elf jumps north"
_JUMP_RE = re.compile(
    r"^\s*(?P<a>.+?)\s+(?:jumps?|leaps?|vaults?|springs?)\s+"
    # Preposition optional: "jumps at the goblin" and "jumps north" are the
    # same verb, and requiring one silently lost every bare direction.
    r"(?:towards?|at|to|onto|over\s+to)?\s*(?P<b>.+?)\s*$",
    re.I,
)

# "elf drinks a potion of healing", "cat throws a smokepowder bomb at emo",
# "elf uses alchemist's fire on hamster"
_ITEM_RE = re.compile(
    r"^\s*(?P<a>.+?)\s+(?:drinks?|quaffs?|throws?|lobs?|hurls?|uses?|applies)\s+"
    r"(?:an?\s+|the\s+)?(?P<item>.+?)"
    r"(?:\s+(?:on|at|against|towards?)\s+(?P<b>.+?))?\s*$",
    re.I,
)

# Spoken forms of the eight headings, including the abbreviations people
# actually say at a table.
DIRECTION_WORDS = {
    "north": "north", "n": "north", "up": "north",
    "south": "south", "s": "south", "down": "south",
    "east": "east", "e": "east", "right": "east",
    "west": "west", "w": "west", "left": "west",
    "northeast": "northeast", "north east": "northeast", "ne": "northeast",
    "northwest": "northwest", "north west": "northwest", "nw": "northwest",
    "southeast": "southeast", "south east": "southeast", "se": "southeast",
    "southwest": "southwest", "south west": "southwest", "sw": "southwest",
}

_DIR_ALT = "|".join(sorted((re.escape(w) for w in DIRECTION_WORDS), key=len, reverse=True))

# "elf moves north", "cat goes to the southwest", "elf steps east"
_DIRECTION_RE = re.compile(
    rf"^\s*(?P<a>.+?)\s+(?:moves?|goes|go|walks?|steps?|heads?|runs?)\s+"
    rf"(?:to\s+)?(?:the\s+)?(?P<dir>{_DIR_ALT})(?:wards?)?\s*$",
    re.I,
)

# "elf moves away from hamster", "elf retreats from the goblin",
# "back cat off from emo", "elf flees hamster"
_RETREAT_RE = re.compile(
    r"^\s*(?P<a>.+?)\s+(?:"
    r"(?:moves?|backs?|steps?|pulls?|gets?)\s+(?:away|back|off)\s+from"
    r"|retreats?\s+from|withdraws?\s+from|runs?\s+(?:away\s+)?from|flees?(?:\s+from)?"
    r"|disengages?\s+from"
    r")\s+(?P<b>.+?)"
    rf"(?:\s+(?:to|towards?|heading)\s+(?:the\s+)?(?P<dir>{_DIR_ALT})(?:wards?)?)?\s*$",
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


# The two channels the upstream translator answers on. Tolerated here so that a
# tagged line can be handed straight to `parse` without the caller having to
# know about the contract.
# Spoken several ways at a real table, and all of them mean the same thing.
# "end turn" is included deliberately: it is what people actually say, even
# though what it does is start the next one.
_NEXT_TURN = {
    "next turn", "end turn", "end of turn", "turn over", "done", "i'm done",
    "im done", "pass turn", "pass the turn", "next", "end my turn",
}
_PREV_TURN = {"previous turn", "prev turn", "last turn", "back a turn", "go back a turn"}
# Set the standing target, so the next few commands do not have to name it.
# Verb-first like `measure`, and matched before the actor-verb-target patterns
# for the same reason: nothing here is an actor.
_TARGET_RE = re.compile(
    r"^\s*(?:we(?:'re| are)?\s+)?(?:now\s+)?"
    r"(?:targeting|target|targetting|focus(?:ing)?\s+(?:on|fire\s+on)|aim(?:ing)?\s+at)"
    r"\s+(?P<t>.+?)\s*$",
    re.I,
)
# A reaction, so verb-first-ish and matched before the generic attack shapes --
# "hamster takes an opportunity attack on elf" also parses as a plain attack,
# and the plain reading would route it through `_do_move` and walk the hamster
# across the map after the creature that just fled it.
_OPPORTUNITY_RE = re.compile(
    r"^\s*(?P<a>.+?)\s+(?:takes?\s+)?(?:an?\s+|the\s+)?"
    r"(?:opportunity|attack\s+of\s+opportunity|reaction)\s*(?:attack)?\s*"
    r"(?:on|at|against)\s+(?P<t>.+?)\s*$",
    re.I,
)

_UNDO = {
    "undo", "undo that", "take that back", "scratch that", "revert",
    "undo the last thing", "put that back",
}
# Deliberately absent from HELP_TEXT. It is DM housekeeping the model never
# needs to produce, and every line in that text is spent on every cluster call --
# so it parses locally from an exact phrase and costs the prompt nothing.
_SET_ROUND_RE = re.compile(
    r"^\s*(?:set\s+|go\s+)?(?:back\s+to\s+)?round\s+(?:to\s+)?(?P<n>\d+|one)\s*$",
    re.I,
)
# Also absent from HELP_TEXT: a repair tool, not a move. Nothing about it obeys
# movement, terrain or the turn budget, which is exactly why the model should
# never be able to reach for it.
_TELEPORT_RE = re.compile(
    r"^\s*(?:teleport|place|put)\s+(?P<a>.+?)\s+(?:to|at)\s+"
    r"(?P<q>-?\d+)\s*[, ]\s*(?P<r>-?\d+)\s*$",
    re.I,
)
# Grammar-only, like the other housekeeping: the model has no business turning
# the monsters off.
_RESUME = {
    "resume", "continue", "carry on", "keep going", "go on", "pick up",
    "pick up where we left off", "play the monsters", "run the monsters",
    "resume combat", "your turn ghost", "take the enemy turns",
}
_DM_ON = {"dm auto on", "ghost runs the monsters", "monsters on", "dm on", "auto dm on"}
_DM_OFF = {"dm auto off", "i'll run the monsters", "monsters off", "dm off", "auto dm off"}
_RESET_ROUND = {"reset the round", "reset round", "restart the round count"}
_ROLL_INITIATIVE = {
    "roll initiative", "roll for initiative", "initiative", "roll initiatives",
    "start combat", "begin combat", "everyone roll initiative", "roll init",
}
_CLEAR_INITIATIVE = {"clear initiative", "reset initiative", "clear the tracker"}
_END_COMBAT = {"end combat", "combat over", "end the fight", "stop combat", "wipe initiative"}
_PROLOGUE = {
    "begin", "begin the story", "opening", "prologue", "tell the story",
    "set the scene", "story", "tell it again", "read the opening",
}
_STORY_RESET = {"reset the story", "forget the story", "new session"}
_CLEAR_TARGET = {
    "clear target", "clear the target", "stop targeting", "no target",
    "forget the target", "untarget", "drop target",
}
_WHOSE_TURN = {
    "whose turn", "whose turn is it", "who's turn", "whos turn", "who is up",
    "who's up", "turn order", "initiative order",
}

_CMD_TAG = re.compile(r"^\s*CMD\s*:\s*", re.I)
_ASK_TAG = re.compile(r"^\s*ASK\s*:\s*", re.I)


def parse(text: str) -> Intent:
    asked = _ASK_TAG.match(text or "")
    if asked:
        raise ClarificationNeeded(text[asked.end():].strip())
    raw = _CMD_TAG.sub("", text or "").strip()
    lowered = raw.lower()
    if not lowered:
        raise ParseError("Nothing to do -- say a command.")

    if lowered in {"help", "?", "commands"}:
        return Intent(Action.HELP, raw=raw)
    # Turn control is actorless, so it is matched here as whole phrases rather
    # than by a regex further down -- everything below this point expects to
    # pull a character name out of the string first.
    if lowered in _NEXT_TURN:
        return Intent(Action.NEXT_TURN, raw=raw)
    if lowered in _PREV_TURN:
        return Intent(Action.PREV_TURN, raw=raw)
    if lowered in _WHOSE_TURN:
        return Intent(Action.WHOSE_TURN, raw=raw)
    ported = _TELEPORT_RE.match(trimmed if False else raw)
    if ported:
        who = _clean(ported["a"].split())
        if who:
            # q and r ride on the two spare integer fields rather than adding a
            # pair of coordinates to every Intent for one command's sake.
            return Intent(Action.TELEPORT, actor=who, dc=int(ported["q"]),
                          heal_amount=int(ported["r"]), raw=raw)
    if lowered in _RESUME:
        return Intent(Action.RESUME, raw=raw)
    if lowered in _DM_ON:
        return Intent(Action.DM_AUTO, condition_on=True, raw=raw)
    if lowered in _DM_OFF:
        return Intent(Action.DM_AUTO, condition_on=False, raw=raw)
    if lowered in _LONG_REST:
        return Intent(Action.LONG_REST, raw=raw)
    if lowered in _RESET_ROUND:
        return Intent(Action.SET_ROUND, dc=1, raw=raw)
    numbered = _SET_ROUND_RE.match(lowered)
    if numbered:
        n = numbered["n"]
        # `dc` is the intent's general-purpose integer; a second one just for
        # this would be a field on every Intent for one command's sake.
        return Intent(Action.SET_ROUND, dc=1 if n == "one" else int(n), raw=raw)
    if lowered in _UNDO:
        return Intent(Action.UNDO, raw=raw)
    if lowered in _ROLL_INITIATIVE:
        return Intent(Action.ROLL_INITIATIVE, raw=raw)
    if lowered in _CLEAR_INITIATIVE:
        return Intent(Action.CLEAR_INITIATIVE, raw=raw)
    if lowered in _END_COMBAT:
        return Intent(Action.END_COMBAT, raw=raw)
    if lowered in _PROLOGUE:
        return Intent(Action.PROLOGUE, raw=raw)
    if lowered in _STORY_RESET:
        return Intent(Action.STORY_RESET, raw=raw)
    if lowered in _CLEAR_TARGET:
        return Intent(Action.CLEAR_TARGET, raw=raw)
    aimed = _TARGET_RE.match(raw)
    if aimed:
        who = _clean(aimed["t"].split())
        if who:
            return Intent(Action.TARGET, target=who, raw=raw)
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

    opp = _OPPORTUNITY_RE.match(trimmed)
    if opp:
        who, whom = _clean(opp["a"].split()), _clean(opp["t"].split())
        if who and whom:
            return Intent(Action.OPPORTUNITY, actor=who, target=whom,
                          kind=AttackKind.MELEE, bias=bias, raw=raw)

    raged = _RAGE_RE.match(trimmed)
    if raged:
        who = _clean(raged["a"].split())
        if who:
            return Intent(Action.RAGE, actor=who, raw=raw)

    levelled = _LEVEL_UP_RE.match(trimmed)
    if levelled:
        who = _clean((levelled["a"] or levelled["b"] or "").split())
        if who:
            return Intent(Action.LEVEL_UP, actor=who, raw=raw)

    dashed = _DASH_RE.match(trimmed)
    if dashed:
        who = _clean(dashed["a"].split())
        if not who:
            raise ParseError("Who is dashing?")
        return Intent(Action.DASH, actor=who, raw=raw)

    jumped = _JUMP_RE.match(trimmed)
    if jumped:
        actor = _clean(jumped["a"].split())
        target_word = _clean(jumped["b"].split())
        if not actor or not target_word:
            raise ParseError("Jump towards what?")
        heading = DIRECTION_WORDS.get(target_word)
        # "jumps north" is a direction; "jumps at the goblin" is a target. Both
        # are the same verb, so the object decides which.
        return Intent(
            Action.JUMP,
            actor=actor,
            target=None if heading else target_word,
            direction=heading,
            raw=raw,
        )

    fled = _RETREAT_RE.match(trimmed)
    if fled:
        actor = _clean(fled["a"].split())
        target = _clean(fled["b"].split())
        if not actor or not target:
            raise ParseError("Away from whom?")
        return Intent(
            Action.RETREAT,
            actor=actor,
            target=target,
            direction=DIRECTION_WORDS.get((fled["dir"] or "").lower()),
            raw=raw,
        )

    # After retreat: "elf moves away from hamster" also matches the bare
    # directional shape if "away from hamster" were ever a heading, and the
    # more specific reading is the right one.
    headed = _DIRECTION_RE.match(trimmed)
    if headed:
        actor = _clean(headed["a"].split())
        if not actor:
            raise ParseError("Who is moving?")
        return Intent(
            Action.MOVE_DIR,
            actor=actor,
            direction=DIRECTION_WORDS[headed["dir"].lower()],
            raw=raw,
        )

    used = _ITEM_RE.match(trimmed)
    if used:
        actor = _clean(used["a"].split())
        thing = _clean(used["item"].split())
        if actor and thing:
            return Intent(
                Action.USE_ITEM,
                actor=actor,
                target=_clean(used["b"].split()) if used["b"] else None,
                item=thing,
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
    # "elf cantrip on emo" names a kind and no verb -- and it is a shape the
    # help text advertises, so refusing it was a straight contradiction. Naming
    # which attack you want is stating that you are attacking.
    if verb_index is None and kind is not None:
        verb_index = next(i for i, w in enumerate(words) if w in _KIND_WORDS)
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
    # A targetless attack parses. It used to be a ParseError, which meant "elf
    # attacks" could never be completed from the standing target however clearly
    # it had just been set -- and worse, the failure sent the line off to the
    # translator as if it were prose. The console fills the target in and gives
    # a better refusal than this could if there is nothing to fill it from.

    # A bare "attack" carries no kind, and this used to be a ParseError asking
    # melee/ranged/cantrip. That dead-ended: the answer ("melee") arrives as a
    # line of its own with no actor in it, so it parses as nothing and the
    # clarification can never be completed -- "<actor> attacks <target>", the
    # most natural phrasing there is, was simply unusable.
    #
    # The parser was also the wrong place to decide. Guessing melee here would
    # send a wizard running at a dragon, but only because a parser cannot see
    # what the character carries or how far away the target is. The executor
    # can, so `kind=None` travels on and `_do_attack` resolves it against the
    # sheet and the board.

    return Intent(action=action, actor=actor, target=target, kind=kind, bias=bias, raw=raw)


HELP_TEXT = """Commands:
  <actor> melee attack on <target>      walk into reach, then strike
  <actor> ranged attack on <target>     shoot from where you stand
  <actor> cantrip on <target>           cast the equipped cantrip
  <actor> moves to <target>             walk towards without attacking
  <actor> moves away from <target> [to <dir>]   back off as far as movement allows
  <actor> moves <dir>                  north, southwest, ... as far as possible
  <actor> jumps to <target|dir>        a running jump, limited by Strength
  <actor> drinks/throws <item> [on <target>]   use a consumable
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
  <actor> grapples/shoves/topples <target>   a contested check
  <actor> dashes                       double movement for the turn
  <actor> rages                        barbarian: bonus melee damage, half damage taken
  long rest                            hit points, slots and rages back to full
  begin                                read the opening out loud
  targeting <name>                     remember who to aim at; later commands may omit the target
  clear target                         forget it again
  <actor> opportunity attack on <target>   a reaction: no movement, and it costs the reaction
  undo                                 put back whatever the last command changed
  resume                               ghost plays every enemy turn up to your character's
  roll initiative / end combat         start or finish combat for everyone on the board
  next turn                            end the current turn and start the next
  previous turn                        step the tracker back one
  whose turn                           read the order back without changing it
Add "with advantage" or "with disadvantage" to any attack.
When the only route crosses a hazard the ghost asks first: answer yes or no."""
