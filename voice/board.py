"""Board graph utilities for the Tampere-themed Afrikan Tähti variant.

Wraps cities.json: a dict of location name -> {"walking": [...], "water": [...],
"flying": [...]} adjacency lists. Unweighted (no distances), symmetric, no
dangling references -- already validated clean against the real file.
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass


@dataclass
class BoardGraph:
    adjacency: dict[str, dict[str, list[str]]]

    @classmethod
    def load(cls, path: str = "cities.json") -> "BoardGraph":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @property
    def cities(self) -> list[str]:
        return list(self.adjacency.keys())

    def neighbors(self, city: str, mode: str) -> list[str]:
        return self.adjacency[city].get(mode, [])

    def reachable_within(self, city: str, mode: str, hops: int) -> set[str]:
        """BFS along `mode` edges only, exactly `hops` steps (classic
        dice-and-move-that-many-spaces convention -- change to "up to hops"
        here if the real movement rule turns out to be different)."""
        frontier = {city}
        for _ in range(hops):
            frontier = {n for c in frontier for n in self.neighbors(c, mode)}
        return frontier

    def closest_match(self, spoken_name: str, cutoff: float = 0.6) -> str | None:
        """Fuzzy-match a possibly-mistranscribed name against self.cities --
        the safety net for whisper getting a Finnish name close-but-not-exact
        even with prompt biasing (see SttConfig.initial_prompt)."""
        matches = difflib.get_close_matches(spoken_name.lower(), self.cities, n=1, cutoff=cutoff)
        return matches[0] if matches else None
