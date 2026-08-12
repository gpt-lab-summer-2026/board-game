"""Dice rolling for the ghost.

PlanarAlly's server does not roll dice -- `Dice.Roll.Result` is a pure relay
(server/src/api/socket/dice.py). Whoever rolls does it locally and broadcasts
the outcome, so the ghost has to produce a result in exactly the shape the
client expects or every other player's browser throws while parsing it.

The receiving client does:

    const roll = JSON.parse(data.roll) as RollResult<Part>;
    const rollString = diceSystem.addToHistory(roll, data.player);
    toast.info(`${data.player} rolled ${rollString} and threw a ${roll.result}`)

and `addToHistory` concatenates `part.input` for each part. So `parts[].input`
is what shows as the notation and `result` is what shows as the total; both are
strings, and `result` is displayed verbatim rather than recomputed.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# e.g. "d20", "2d6", "1d8+3", "4d6-1", and the keep-highest/lowest form the
# character sheet emits for advantage and disadvantage: "2d20kh1+5", "2d20kl1".
DICE_RE = re.compile(
    r"""^\s*
    (?P<count>\d*)\s*[dD]\s*(?P<sides>\d+)
    (?:\s*[kK](?P<keep>[hHlL])(?P<keep_n>\d+))?
    \s*(?P<mod>[+-]\s*\d+)?
    \s*$""",
    re.VERBOSE,
)

MAX_DICE = 100  # a guard, not a rule: nothing sane rolls more


@dataclass
class Roll:
    notation: str
    rolls: list[int]
    modifier: int = 0
    """Dice actually counted towards the total. Differs from `rolls` only for
    keep-highest/lowest, where the discarded dice are still worth showing."""
    kept: list[int] | None = None
    total: int = field(init=False)

    def __post_init__(self) -> None:
        self.total = sum(self.counted) + self.modifier

    @property
    def counted(self) -> list[int]:
        return self.rolls if self.kept is None else self.kept

    def long_result(self) -> str:
        if self.kept is None:
            inner = ", ".join(str(r) for r in self.rolls)
        else:
            # Show the dropped dice struck through in brackets, because the
            # whole point of advantage is seeing what you avoided.
            remaining = list(self.kept)
            parts = []
            for r in self.rolls:
                if r in remaining:
                    remaining.remove(r)
                    parts.append(str(r))
                else:
                    parts.append(f"({r})")
            inner = ", ".join(parts)
        if self.modifier:
            return f"[{inner}] {self.modifier:+d}"
        return f"[{inner}]"

    def to_payload(self, player: str, share_with: str = "all") -> dict:
        """The exact dict `Dice.Roll.Result` expects, ready to emit."""
        import json

        result = {
            "result": str(self.total),
            "parts": [
                {
                    "input": self.notation,
                    "shortResult": str(self.total),
                    "longResult": self.long_result(),
                }
            ],
        }
        # `roll` is a JSON *string*, not a nested object -- the client calls
        # JSON.parse on it.
        return {
            "player": player,
            "roll": json.dumps(result),
            "shareWith": share_with,
        }


def roll(notation: str, rng: random.Random | None = None) -> Roll:
    """Roll standard dice notation: NdS with an optional +/- modifier."""
    match = DICE_RE.match(notation)
    if match is None:
        raise ValueError(
            f"can't parse {notation!r}; expected something like 1d20, 2d6 or 1d8+3"
        )
    count = int(match["count"] or 1)
    sides = int(match["sides"])
    modifier = int(match["mod"].replace(" ", "")) if match["mod"] else 0

    if count < 1 or count > MAX_DICE:
        raise ValueError(f"dice count {count} out of range (1-{MAX_DICE})")
    if sides < 2:
        raise ValueError(f"a {sides}-sided die makes no sense")

    r = rng or random.SystemRandom()
    rolls = [r.randint(1, sides) for _ in range(count)]

    kept: list[int] | None = None
    keep_suffix = ""
    if match["keep"]:
        keep_n = int(match["keep_n"])
        if keep_n < 1 or keep_n > count:
            raise ValueError(f"cannot keep {keep_n} of {count} dice")
        highest = match["keep"].lower() == "h"
        kept = sorted(rolls, reverse=highest)[:keep_n]
        keep_suffix = f"k{'h' if highest else 'l'}{keep_n}"

    # Normalise the notation so the toast reads consistently regardless of how
    # it was typed ("d20" and " 1 D 20 " both display as 1d20).
    canonical = f"{count}d{sides}{keep_suffix}" + (f"{modifier:+d}" if modifier else "")
    return Roll(notation=canonical, rolls=rolls, modifier=modifier, kept=kept)


def advantage(notation: str) -> str:
    """Rewrite a plain d20 roll as advantage: "1d20+5" -> "2d20kh1+5"."""
    return _rebias(notation, "kh")


def disadvantage(notation: str) -> str:
    return _rebias(notation, "kl")


def _rebias(notation: str, keep: str) -> str:
    match = DICE_RE.match(notation)
    if match is None:
        raise ValueError(f"can't parse {notation!r}")
    if int(match["sides"]) != 20:
        raise ValueError("advantage and disadvantage only apply to d20 rolls")
    mod = match["mod"].replace(" ", "") if match["mod"] else ""
    return f"2d20{keep}1{mod}"
