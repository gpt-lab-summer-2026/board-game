"""Authoritative game state for the Tampere Afrikan Tähti variant.

Gemma3 (voice/llm.py) only parses player speech into a structured action --
this module is where that action actually takes effect. Square effects and
the city-square layout are placeholder data pending the user's real numbers;
everything reads from SQUARE_MONEY_DELTA / the square_types dict passed in,
so swapping in real data later is a one-line change, not a refactor.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .board import BoardGraph

SQUARE_TYPES = ["empty", "robber", "horseshoe", "small_gem", "medium_gem",
                "large_gem", "winning_gem"]

# PLACEHOLDER effects -- replace once real balance numbers exist.
SQUARE_MONEY_DELTA = {
    "empty": 0,
    "robber": -50,
    "horseshoe": 0,
    "small_gem": 20,
    "medium_gem": 50,
    "large_gem": 100,
    "winning_gem": 0,  # winning_gem's effect is the win check, not money
}


@dataclass
class PlayerState:
    name: str
    position: str
    balance: int = 0
    carrying_winning_gem: bool = False


@dataclass
class MoveOutcome:
    player: str
    destination: str
    square_type: str
    money_delta: int
    picked_up_gem: bool
    won: bool


class GameEngine:
    def __init__(self, board: BoardGraph, players: list[str], start_city: str,
                 square_types: dict[str, str]):
        if start_city not in board.cities:
            raise ValueError(f"start_city {start_city!r} is not on the board")
        self.board = board
        self.start_city = start_city
        self.square_types = square_types
        self.players = [PlayerState(name=p, position=start_city) for p in players]
        self._turn_idx = 0
        # Tracked at the engine level, not per-player: once claimed, landing on the
        # same city again must not let a second player "pick up" the same gem too.
        self._gem_claimed = False

    @property
    def current_player(self) -> PlayerState:
        return self.players[self._turn_idx]

    def plausible_destinations(self) -> list[str]:
        """Union of reachable cities across every mode and dice value 1-6, from
        the current player's position -- an informational hint for the LLM
        prompt about what's nearby. NOT a hard constraint: the schema's
        destination enum stays the full city list; real reachability is
        checked in apply_move() once dice_value+mode are both known."""
        city = self.current_player.position
        result: set[str] = set()
        for mode in ("walking", "water", "flying"):
            for hops in range(1, 7):
                result |= self.board.reachable_within(city, mode, hops)
        result.discard(city)
        return sorted(result)

    def apply_move(self, destination: str, mode: str, dice_value: int) -> MoveOutcome:
        """Re-validates reachability -- defense in depth, never trust the caller's
        pick alone even though voice/llm.py's IntentParser._validate() should
        already have caught an inconsistent dice/destination/mode combo before
        ever calling this. Raises ValueError if it's still wrong; that's a
        contract violation at this point, not a normal "ask the player again"
        case (that path is handled upstream via ParsedIntent(action="unclear"))."""
        player = self.current_player
        legal = self.board.reachable_within(player.position, mode, dice_value)
        if destination not in legal:
            raise ValueError(
                f"{destination!r} is not reachable from {player.position!r} via "
                f"{mode!r} in exactly {dice_value} hops"
            )

        player.position = destination
        square_type = self.square_types.get(destination, "empty")
        money_delta = SQUARE_MONEY_DELTA[square_type]
        player.balance += money_delta

        picked_up_gem = False
        won = False
        if square_type == "winning_gem" and not self._gem_claimed:
            self._gem_claimed = True
            player.carrying_winning_gem = True
            picked_up_gem = True
        elif player.carrying_winning_gem and destination == self.start_city:
            won = True

        outcome = MoveOutcome(player=player.name, destination=destination,
                               square_type=square_type, money_delta=money_delta,
                               picked_up_gem=picked_up_gem, won=won)
        if not won:
            self._turn_idx = (self._turn_idx + 1) % len(self.players)
        return outcome


def placeholder_square_types(board: BoardGraph, start_city: str, seed: int) -> dict[str, str]:
    """Every city "empty" except one random non-start city set to "winning_gem" --
    just enough to exercise the full pipeline before the real 7-piece layout exists."""
    rng = random.Random(seed)
    candidates = [c for c in board.cities if c != start_city]
    winning_city = rng.choice(candidates)
    return {city: ("winning_gem" if city == winning_city else "empty") for city in board.cities}
