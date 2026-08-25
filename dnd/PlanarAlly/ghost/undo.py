"""Putting back whatever the last command changed.

Voice needs this more than a mouse does. A misheard command is not a rare event
-- "Freak attack scapped" is in the transcripts -- and when a mis-parse moves a
token or spends a slot, the only recovery until now was to reach for the
browser, which is the thing the whole project exists to avoid.

Snapshot-based rather than a log of compensating actions. Recording an inverse
for every mutation means every future mutation has to remember to add one, and
the one that forgets fails silently and late. Reading the state back and writing
it again cannot drift: whatever the command did to these sheets, this puts them
where they were.

What it deliberately does not cover, because a snapshot of two creatures cannot
see it:

* shapes that were *created* -- a duplicated character, a ruler mark, a spell
  effect. Undo does not delete them.
* the initiative order, and the round and turn counters.
* dice that were rolled, and narration already spoken. Both are out in the
  world; the board is what can be put back.

Single-step on purpose. A stack invites "undo undo undo" as a way of rewinding a
fight, which is a different feature with different failure modes -- and one the
table can already do by simply saying what should happen instead.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import sheet, turns
from .client import GhostClient

log = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """Enough of the board to put one command back."""

    label: str
    """uuid -> the whole character sheet as it was."""
    sheets: dict[str, dict[str, Any]] = field(default_factory=dict)
    """uuid -> (x, y) in PlanarAlly world units."""
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    """The turn budget block as it was."""
    budget: dict[str, Any] | None = None
    """Display names, so the report can say "elf" rather than a uuid."""
    names: dict[str, str] = field(default_factory=dict)


async def capture(client: GhostClient, uuids: list[str], label: str) -> Snapshot | None:
    """Read back everything the command about to run might change.

    Never raises. A snapshot that could not be taken is reported as "nothing to
    undo" later, which is a worse outcome than undo working but a much better
    one than the command itself failing because the safety net could not be
    strung up first.
    """
    snap = Snapshot(label=label)
    try:
        for uuid in dict.fromkeys(u for u in uuids if u):
            data = await sheet.read_sheet(client, uuid)
            if data is not None:
                snap.sheets[uuid] = data
            shape = client.state.shapes.get(uuid)
            if shape is not None and shape.get("x") is not None:
                snap.positions[uuid] = (float(shape["x"]), float(shape["y"]))
            for name, u in client.state.characters.items():
                if u == uuid:
                    snap.names[uuid] = name
        snap.budget = await turns.read_budget(client)
    except Exception:  # noqa: BLE001
        log.exception("could not snapshot before %r", label)
        return None
    return snap


def _name(snap: Snapshot, uuid: str) -> str:
    return snap.names.get(uuid, uuid[:8])


async def restore(client: GhostClient, snap: Snapshot) -> list[str]:
    """Write the snapshot back, reporting only what had actually changed.

    Comparing before writing is what makes the report trustworthy: saying "elf
    is back on 8 hit points" when the elf was never hurt trains the table to
    ignore the line.
    """
    changed: list[str] = []

    for uuid, before in snap.sheets.items():
        try:
            now = await sheet.read_sheet(client, uuid)
        except Exception:  # noqa: BLE001
            log.exception("could not re-read sheet %s", uuid)
            continue
        if now == before:
            continue
        try:
            await sheet.write_sheet(client, uuid, before)
        except Exception:  # noqa: BLE001
            log.exception("could not restore sheet %s", uuid)
            continue
        name = _name(snap, uuid)
        hp_before = (before.get("hp") or {}).get("current")
        hp_now = ((now or {}).get("hp") or {}).get("current")
        if hp_before != hp_now:
            changed.append(f"{name} back to {hp_before} hit points")
        else:
            changed.append(f"{name}'s sheet restored")

    for uuid, (x, y) in snap.positions.items():
        shape = client.state.shapes.get(uuid)
        if shape is None:
            continue
        if abs(float(shape.get("x", x)) - x) < 0.01 and abs(float(shape.get("y", y)) - y) < 0.01:
            continue
        try:
            await client.move_shape(uuid, x, y)
        except Exception:  # noqa: BLE001
            log.exception("could not move %s back", uuid)
            continue
        changed.append(f"{_name(snap, uuid)} back where it was")

    if snap.budget is not None:
        try:
            now = await turns.read_budget(client)
            if now != snap.budget:
                await turns.write_budget(client, snap.budget)
                changed.append("the turn budget restored")
        except Exception:  # noqa: BLE001
            log.exception("could not restore the turn budget")

    if not changed:
        return [f"Nothing to put back from {snap.label!r} -- the board had not changed."]
    return [f"Undid {snap.label!r}: " + ", ".join(changed) + "."]
