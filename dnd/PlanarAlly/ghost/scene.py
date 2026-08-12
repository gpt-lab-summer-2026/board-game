"""Putting things on the board: walls, hazards, lights, floors, rulers.

Everything here goes through `Shape.Add`, the same event the browser uses. Two
things about that handler are worth knowing before calling any of this
(`server/src/api/socket/shape/__init__.py`):

  - shapes are addressed by **floor name and layer name**, not id, and an
    unknown pair is logged and silently dropped;
  - `temporary: true` shapes are tracked per-connection and never written to the
    database. They vanish when the ghost disconnects, which is exactly what a
    ruler wants and exactly what a wall does not.

Test geometry defaults to temporary for that reason: it disappears on its own
and cannot leave litter in someone's saved campaign. Pass `permanent=True` when
you actually mean to build something.
"""
from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Any, Iterable

from .grid import Cell, GridType, cell_center, DEFAULT_GRID_SIZE

log = logging.getLogger(__name__)

DRAW_LAYER = "draw"
MAP_LAYER = "map"
TOKEN_LAYER = "tokens"


def new_uuid() -> str:
    return str(uuid_mod.uuid4())


def _core(
    *,
    x: float,
    y: float,
    name: str,
    fill: str = "#00000088",
    stroke: str = "#000000ff",
    blocks_vision: int = 0,
    blocks_movement: bool = False,
    size_x: int = 1,
    size_y: int = 1,
) -> dict[str, Any]:
    """The fields every shape needs, whatever its subtype.

    ApiCoreShape is not optional-friendly: pydantic validates the whole model,
    so a missing field is a rejected shape rather than a defaulted one.
    """
    return {
        "uuid": new_uuid(),
        "type_": "rect",
        "x": x,
        "y": y,
        "name": name,
        "name_visible": True,
        "fill_colour": fill,
        "stroke_colour": stroke,
        "vision_obstruction": blocks_vision,
        "movement_obstruction": blocks_movement,
        "draw_operator": "source-over",
        "options": "[]",
        "badge": 0,
        "show_badge": False,
        "default_edit_access": False,
        "default_vision_access": False,
        "is_invisible": False,
        "is_defeated": False,
        "default_movement_access": False,
        "is_locked": False,
        "angle": 0,
        "stroke_width": 2,
        "group": None,
        "ignore_zoom_size": False,
        "is_door": False,
        "is_teleport_zone": False,
        "custom_data": [],
        "owners": [],
        "trackers": [],
        "auras": [],
        "character": None,
        "odd_hex_orientation": False,
        "size_x": size_x,
        "size_y": size_y,
        "show_cells": False,
        "cell_fill_colour": None,
        "cell_stroke_colour": None,
        "cell_stroke_width": None,
        "notes": [],
        # Required by ApiCoreShape even for shapes that can never have any.
        "variants": [],
    }


async def _add(client, shape: dict[str, Any], floor: str, layer: str, temporary: bool) -> str:
    await client.emit(
        "Shape.Add",
        {"shape": shape, "floor": floor, "layer": layer, "temporary": temporary},
    )
    # Record it locally as well as sending it.
    #
    # The ghost would otherwise be blind to its own geometry: the server
    # broadcasts Shape.Add with skip_sid so the sender never hears its own, and
    # temporary shapes are never written to the database, so a later
    # Location.Load does not replay them either. Without this a wall the ghost
    # just built is invisible to its own pathfinding -- it walks straight
    # through it.
    if not client.cfg.dry_run:
        client.state.shapes[shape["uuid"]] = shape
        client.state.shape_layer[shape["uuid"]] = layer
    return shape["uuid"]


async def add_block(
    client,
    field,
    cells: Iterable[Cell],
    name: str,
    *,
    floor: str,
    blocks_vision: bool = True,
    blocks_movement: bool = True,
    fill: str = "#33333388",
    layer: str = MAP_LAYER,
    permanent: bool = False,
) -> list[str]:
    """One rect per cell, so the battlefield reads it cell-accurately.

    A single wide rect would be fewer shapes, but `size_x`/`size_y` are the only
    footprint information the ghost gets back over the socket, and a rect's real
    width lives in the opaque `options` blob. One shape per cell keeps what the
    ghost sees and what the players see in agreement.
    """
    made: list[str] = []
    half = DEFAULT_GRID_SIZE / 2
    for cell in cells:
        cx, cy = cell_center(cell, field.grid)
        shape = _core(
            x=cx - half,
            y=cy - half,
            name=name,
            fill=fill,
            blocks_vision=1 if blocks_vision else 0,
            blocks_movement=blocks_movement,
        )
        shape["width"] = DEFAULT_GRID_SIZE
        shape["height"] = DEFAULT_GRID_SIZE
        made.append(await _add(client, shape, floor, layer, temporary=not permanent))
    log.info("added %d cells of %r on %s/%s", len(made), name, floor, layer)
    return made


async def add_textured_block(
    client,
    field,
    cells: Iterable[Cell],
    texture: dict[str, Any],
    name: str,
    *,
    floor: str,
    blocks_vision: bool = True,
    blocks_movement: bool = True,
    layer: str = MAP_LAYER,
    permanent: bool = False,
) -> list[str]:
    """A wall built from an image rather than a flat colour.

    PlanarAlly shapes carry a single `fill_colour` and nothing else -- there
    is no pattern fill. Only `assetrect` draws an image, so a textured wall
    is an asset shape with the obstruction flags set, not a rect with a
    fancier fill. `texture` is an entry from `assets.find_texture`.
    """
    made: list[str] = []
    half = DEFAULT_GRID_SIZE / 2
    for cell in cells:
        cx, cy = cell_center(cell, field.grid)
        shape = _core(
            x=cx - half,
            y=cy - half,
            name=name,
            blocks_vision=1 if blocks_vision else 0,
            blocks_movement=blocks_movement,
        )
        shape["type_"] = "assetrect"
        shape["width"] = DEFAULT_GRID_SIZE
        shape["height"] = DEFAULT_GRID_SIZE
        shape["assetHash"] = texture["fileHash"]
        shape["assetId"] = texture["assetId"]
        shape["name_visible"] = False
        made.append(await _add(client, shape, floor, layer, temporary=not permanent))
    log.info("added %d textured cells of %r", len(made), name)
    return made


async def add_light(
    client,
    field,
    cell: Cell,
    name: str = "torch",
    *,
    floor: str,
    radius_feet: float = 20.0,
    dim_feet: float = 40.0,
    colour: str = "#ffd48aff",
    permanent: bool = False,
) -> str:
    """A token carrying a light aura.

    Light in PlanarAlly is an aura on a shape, not a shape in its own right --
    `value`/`dim` are the bright and dim radii, and `visionSource` is what makes
    it actually illuminate rather than just draw a circle.
    """
    cx, cy = cell_center(cell, field.grid)
    half = DEFAULT_GRID_SIZE / 2
    shape = _core(x=cx - half, y=cy - half, name=name, fill=colour, stroke=colour)
    shape["width"] = DEFAULT_GRID_SIZE
    shape["height"] = DEFAULT_GRID_SIZE
    # ApiAura is strict about all of this, and `Shape.Add` is fire-and-forget:
    # a rejected shape is logged server-side and the sender is told nothing. An
    # earlier version omitted `shape` and `flood_light` and passed floats for
    # `value`/`dim`, so the light was never created and nothing said so.
    shape["auras"] = [
        {
            "uuid": new_uuid(),
            "shape": shape["uuid"],
            "active": True,
            "vision_source": True,
            "visible": True,
            "name": name,
            # Radii are in the campaign's own units (feet here), not pixels
            # -- the DM types "20" in the aura UI and 20 is what is stored.
            # Converting to pixels made a 20ft torch light 28ft of corridor.
            "value": round(radius_feet),
            "dim": round(dim_feet),
            "colour": colour,
            "border_colour": "#00000000",
            "angle": 360,
            "direction": 0,
            "flood_light": False,
        }
    ]
    return await _add(client, shape, floor, TOKEN_LAYER, temporary=not permanent)


async def add_floor(client, name: str) -> None:
    """A new floor. Always permanent -- PlanarAlly has no temporary floors.

    Note what that means before calling this on a live campaign: the floor
    appears in everyone's floor selector immediately, and anything subsequently
    dragged onto it is at the mercy of `remove_floor` below.
    """
    await client.emit("Floor.Create", name)
    log.info("created floor %r", name)


async def remove_floor(client, name: str, *, force: bool = False) -> bool:
    """Delete a floor, refusing by default if anything is standing on it.

    Server-side this is `floor.delete_instance(recursive=True)`, and a shape's
    layer FK is nullable -- so peewee *nulls* it rather than cascading. The
    shapes are not deleted; they are stranded with `layer_id = NULL`, which
    renders nowhere, is never sent by `Location.Load`, and cannot be moved back
    because `Shapes.Layer.Change` refuses a shape that has no layer. The only
    way out is `ghost.repair_orphans`.

    This is how a character token got lost during testing. Hence the check.
    """
    on_it = [
        uuid
        for uuid, floor in getattr(client.state, "shape_floor", {}).items()
        if floor == name
    ]
    if on_it and not force:
        log.error(
            "refusing to remove floor %r: %d shape(s) on it would be stranded "
            "with no layer and no way back. Move them first, or pass force=True.",
            name, len(on_it),
        )
        return False

    await client.emit("Floor.Remove", name)
    log.info("removed floor %r", name)
    return True


RULER_START_COLOUR = "#82c8a0aa"
RULER_CELL_COLOUR = "#92bbed88"


async def draw_ruler(
    client,
    field,
    a: Cell,
    b: Cell,
    label: str,
    *,
    floor: str | None = None,
    grid_mode: bool = True,
) -> list[str]:
    """Draw a measurement everyone can see, counting cells like the ruler's grid mode.

    PlanarAlly's own ruler publishes its Line and Text as temporary shapes when
    "show public" is on, so those parts carry to other clients. **Its grid-mode
    cell highlighting does not** -- that is painted in a local
    `postDrawCallback` (`tools/variants/ruler.ts`) and never leaves the browser
    that drew it. On a projected table, where the projector is a separate
    client, the highlighted cells would simply be missing.

    So the highlight is rebuilt here as one translucent temporary rect per cell.
    Those do sync, which makes this strictly more useful than the built-in tool
    for this setup: everyone sees the same counted squares.
    """
    floor = floor or client.state.current_floor
    if floor is None:
        raise RuntimeError("no current floor known; load the board first")

    made: list[str] = []
    ax, ay = cell_center(a, field.grid)
    bx, by = cell_center(b, field.grid)
    half = DEFAULT_GRID_SIZE / 2

    if grid_mode:
        # Start cell tinted differently, the way PA distinguishes it locally.
        for index, cell in enumerate([a, *field.cells_between(a, b), b]):
            cx, cy = cell_center(cell, field.grid)
            tile = _core(
                x=cx - half,
                y=cy - half,
                name="ruler",
                fill=RULER_START_COLOUR if index == 0 else RULER_CELL_COLOUR,
                stroke="#00000000",
            )
            tile["width"] = DEFAULT_GRID_SIZE
            tile["height"] = DEFAULT_GRID_SIZE
            tile["name_visible"] = False
            made.append(await _add(client, tile, floor, DRAW_LAYER, temporary=True))

    line = _core(x=ax, y=ay, name="ruler", stroke="#ff0000ff")
    line["type_"] = "line"
    line["x2"] = bx
    line["y2"] = by
    line["line_width"] = 5
    line["ignore_zoom_size"] = True
    line["name_visible"] = False
    made.append(await _add(client, line, floor, DRAW_LAYER, temporary=True))

    text = _core(x=(ax + bx) / 2, y=(ay + by) / 2, name="ruler", fill="#000000ff")
    text["type_"] = "text"
    text["text"] = label
    text["font_size"] = 20
    text["ignore_zoom_size"] = True
    text["name_visible"] = False
    made.append(await _add(client, text, floor, DRAW_LAYER, temporary=True))
    return made


async def clear_shapes(client, uuids: Iterable[str], *, temporary: bool = False) -> None:
    """Remove shapes the ghost drew. Temporary ones also go on disconnect.

    The payload is `{uuids, temporary}` -- a bare list is accepted by the
    socket layer and then silently dropped when pydantic cannot build a
    TemporaryShapes from it, so a failed cleanup looks exactly like a
    successful one.
    """
    ids = list(uuids)
    if not ids:
        return
    await client.emit("Shapes.Remove", {"uuids": ids, "temporary": temporary})
    for uuid in ids:
        client.state.shapes.pop(uuid, None)
        client.state.shape_layer.pop(uuid, None)


def cells_in_line(start: Cell, dq: int, dr: int, count: int) -> list[Cell]:
    """A straight run of cells, for building walls without typing coordinates."""
    return [Cell(start.q + dq * i, start.r + dr * i) for i in range(count)]


def bounding_cells(field, pad: int = 2) -> tuple[Cell, Cell]:
    """The cell box the characters occupy, padded.

    Used to keep generated test geometry near the party instead of scattering
    it across a map someone has already built.
    """
    occupied = [o.cell for o in field.occupants.values()]
    if not occupied:
        return Cell(0, 0), Cell(0, 0)
    qs = [c.q for c in occupied]
    rs = [c.r for c in occupied]
    return Cell(min(qs) - pad, min(rs) - pad), Cell(max(qs) + pad, max(rs) + pad)
