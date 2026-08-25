"""Board decorations that are supposed to go away.

A measurement, the highlight under a suggestion, the burst of a spell: all of
them are drawn to be looked at once and then forgotten. PlanarAlly has no notion
of a shape with a lifetime, so without something like this they simply pile up --
the ruler marks in particular were drawn on every `measure` and never removed,
so a session's worth of measurements ends up layered over the map.

Lifetime is counted in *turns*, not seconds, because that is the unit the table
thinks in: a Fire Bolt fizzles when the turn passes, a fog cloud outlasts several
of them. A zero-turn mark is cleared at the very next turn change.

Every one of these is drawn as a *temporary* shape: tracked per connection,
never written to the database, and dropped when the ghost disconnects. That has
a sharp edge -- removing one requires saying `temporary=True` as well, or the
call quietly does nothing, and counting rows in the database to check will
always report success because temporary shapes were never there to count.

Held in memory rather than in a DataBlock. A ghost restart therefore forgets
what it drew, so `sweep_orphans` exists to find them again by name -- these are
all shapes the ghost created and nobody else has any reason to make.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Every transient shape carries one of these as its name, so a restart can find
# and remove them without having remembered anything.
RULER_NAME = "ruler mark"
SUGGESTION_NAME = "suggested spot"
EFFECT_NAME = "spell effect"
ALL_NAMES = (RULER_NAME, SUGGESTION_NAME, EFFECT_NAME)


@dataclass
class Mark:
    uuids: list[str]
    turns_left: int
    label: str
    kind: str = EFFECT_NAME


_marks: list[Mark] = []


def add(uuids: list[str], *, turns: int = 1, label: str = "", kind: str = EFFECT_NAME) -> None:
    """Register shapes to be removed after `turns` turn changes."""
    if not uuids:
        return
    _marks.append(Mark(list(uuids), max(0, turns), label, kind))


def tracked(kind: str | None = None) -> list[Mark]:
    return [m for m in _marks if kind is None or m.kind == kind]


async def clear_kind(client, kind: str) -> None:
    """Remove everything of one kind right now.

    Used by the ruler: a new measurement replaces the old one rather than
    layering on top of it, which is what you want even mid-turn.
    """
    from . import scene

    doomed = [m for m in _marks if m.kind == kind]
    if not doomed:
        return
    _marks[:] = [m for m in _marks if m.kind != kind]
    uuids = [u for m in doomed for u in m.uuids]
    try:
        await scene.clear_shapes(client, uuids, temporary=True)
    except Exception:  # noqa: BLE001 - a stuck decoration is not worth an error
        log.exception("could not clear %s", kind)


async def tick(client) -> list[str]:
    """Count every mark down one turn and remove whatever has run out.

    Returns the labels of what expired, so the console can say "the fog
    disperses" rather than having things silently vanish from the board.
    """
    from . import scene

    expired: list[Mark] = []
    survivors: list[Mark] = []
    for mark in _marks:
        mark.turns_left -= 1
        (expired if mark.turns_left < 0 else survivors).append(mark)

    if not expired:
        _marks[:] = survivors
        return []

    _marks[:] = survivors
    uuids = [u for m in expired for u in m.uuids]
    try:
        await scene.clear_shapes(client, uuids, temporary=True)
    except Exception:  # noqa: BLE001
        log.exception("could not clear expired marks")
    return [m.label for m in expired if m.label]


async def sweep_orphans(client) -> int:
    """Delete transient shapes left behind by a previous run.

    The registry is in memory, so a ghost that was restarted has no idea what it
    drew before. Everything it draws is named from ALL_NAMES, and nothing else
    on the board has any reason to carry those names, so they can be found again.
    """
    from . import scene

    orphans = [
        uuid for uuid, shape in client.state.shapes.items()
        if shape.get("name") in ALL_NAMES
    ]
    if not orphans:
        return 0
    try:
        await scene.clear_shapes(client, orphans, temporary=False)
    except Exception:  # noqa: BLE001
        log.exception("could not sweep orphaned marks")
        return 0
    log.info("swept %d orphaned board marks", len(orphans))
    return len(orphans)
