"""Making new characters from existing ones.

Duplicating a character is three steps, and PlanarAlly has no single event for
it:

  1. add a new `assetrect` shape pointing at the same asset;
  2. `Character.Create` against that shape -- it refuses anything that is not
     an assetrect with an asset, and refuses a shape that is already a
     character;
  3. copy the character sheet DataBlock across, keyed to the new shape's uuid.

Step 3 is the one that makes this worth having. Everything else is
click-and-drag work a DM can already do; retyping a statblock is not.
"""
from __future__ import annotations

import logging
from typing import Any

from . import sheet
from . import scene
from .grid import Cell, GridType, cell_center, neighbours

log = logging.getLogger(__name__)

TOKEN_LAYER = "tokens"


class DuplicateError(RuntimeError):
    """Raised with a message meant to be read back to the player."""


def _free_cell_near(field, cell: Cell) -> Cell:
    """Somewhere to put the copy that isn't on top of the original."""
    for candidate in neighbours(cell, field.grid):
        if field.is_free(candidate):
            return candidate
    # Every neighbour taken: stack it and let the DM sort it out rather than
    # searching outwards forever.
    return cell


async def duplicate(
    client,
    source_uuid: str,
    new_name: str,
    *,
    field=None,
    copy_sheet: bool = True,
) -> str:
    """Copy a character, sheet and all. Returns the new shape's uuid."""
    source = client.state.shapes.get(source_uuid)
    if source is None:
        raise DuplicateError("I can't find that character on the board.")
    if source.get("type_") != "assetrect":
        raise DuplicateError(
            "Only characters made from an asset can be duplicated -- "
            "PlanarAlly refuses to make a character out of anything else."
        )
    if any(name.lower() == new_name.lower() for name in client.state.characters):
        raise DuplicateError(f"There is already a character called {new_name!r}.")

    floor = client.state.shape_floor.get(source_uuid) or client.state.current_floor
    if floor is None:
        raise DuplicateError("I don't know which floor to put it on.")

    # Clone the whole payload so size, vision, auras and image all carry over,
    # then replace everything that must be unique.
    copy: dict[str, Any] = dict(source)
    copy["uuid"] = scene.new_uuid()
    copy["name"] = new_name
    # A shape that still points at the original character is rejected by
    # Character.Create ("Shape is already associated with a character").
    copy["character"] = None
    copy["trackers"] = []
    copy["notes"] = []
    copy["owners"] = []
    # Auras carry their own ids and a back-reference to their shape.
    copy["auras"] = [
        {**aura, "uuid": scene.new_uuid(), "shape": copy["uuid"]}
        for aura in (source.get("auras") or [])
    ]

    if field is not None:
        origin = field.occupants.get(source_uuid)
        if origin is not None:
            cx, cy = cell_center(_free_cell_near(field, origin.cell), field.grid)
            copy["x"] = cx - float(source.get("width") or 0) / 2
            copy["y"] = cy - float(source.get("height") or 0) / 2

    await scene._add(client, copy, floor, TOKEN_LAYER, temporary=False)
    await client.emit("Character.Create", {"shape": copy["uuid"], "name": new_name})

    if copy_sheet:
        original = await sheet.read_sheet(client, source_uuid)
        if original is not None:
            fresh = dict(original)
            # Trackers belong to the token they were made for; leaving the old
            # ids in place would point the copy's HP at the original's bar.
            fresh["trackerIds"] = {"hp": None, "ac": None}
            await sheet.write_sheet(client, copy["uuid"], fresh)
            log.info("copied sheet from %s to %s", source_uuid[:8], copy["uuid"][:8])

    log.info("duplicated %r as %r", source.get("name"), new_name)
    return copy["uuid"]
