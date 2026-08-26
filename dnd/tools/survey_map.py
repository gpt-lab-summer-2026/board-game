#!/usr/bin/env python3
"""Recompute autoplay's START_CELLS against the walls as they are now.

Run from the PlanarAlly directory with its venv, with the server up:

    server/.venv/bin/python ../tools/survey_map.py

Prints a START_CELLS block to paste into autoplay.py, and writes the full
geometry to map.json for the wall-comparison picture.

The placement rule, in one sentence: rasterise the wall polygons, flood-fill the
reachable floor inside their bounding box from a cell known to be on the map,
then give each creature the free cell nearest its corner that is at least three
cells from everyone already placed.
"""
import asyncio, json, os, pathlib, sys

sys.path.insert(0, ".")
from ghost.client import GhostClient, GhostConfig  # noqa: E402
from ghost import actions  # noqa: E402
from ghost.grid import Cell, cell_center  # noqa: E402

NEIGHBOURS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]
# corner (x fraction, y fraction); y runs DOWN, so a small y is the top
CORNERS = [
    ("elf", 0.88, 0.08), ("emo", 0.80, 0.16), ("cat", 0.90, 0.24),
    ("freak", 0.10, 0.80), ("gentelman", 0.18, 0.90), ("weirdo", 0.06, 0.96),
    ("hamster", 0.90, 0.90),
]
SPACING = 3
# How many of a cell's six neighbours must be free for a creature to start
# there. A cell can be unblocked and still be a corner pocket with three walls
# around it -- which is where the cat first landed, and on the board it read as
# the token having been placed inside the masonry. Requiring all six keeps
# every starting position somewhere a creature can actually move out of.
OPENNESS = 6


def hex_distance(a: Cell, b: Cell) -> int:
    return max(abs(a.q - b.q), abs(a.r - b.r), abs((a.q + a.r) - (b.q + b.r)))


async def main() -> None:
    pw = pathlib.Path(os.path.expanduser("~/.config/planarally-ghost/password")).read_text().strip()
    c = GhostClient(GhostConfig(password=pw))
    await c.connect(); await c.load_board(); await asyncio.sleep(2)
    f = await actions._build_field(c)

    if not f.blocked:
        print("no walls found -- is the ghost reading the right board?"); return
    wall_px = [cell_center(x, f.grid) for x in f.blocked]
    wx = [p[0] for p in wall_px]; wy = [p[1] for p in wall_px]

    start = f.occupants[c.state.find_shape("cat")].cell
    seen = {start}; stack = [start]
    while stack:
        cur = stack.pop()
        for dq, dr in NEIGHBOURS:
            n = Cell(cur.q + dq, cur.r + dr)
            if n in seen or n in f.blocked:
                continue
            x, y = cell_center(n, f.grid)
            if not (min(wx) <= x <= max(wx) and min(wy) <= y <= max(wy)):
                continue
            seen.add(n); stack.append(n)

    pts = {cell: cell_center(cell, f.grid) for cell in seen}
    xs = [p[0] for p in pts.values()]; ys = [p[1] for p in pts.values()]
    print(f"walls: {len(f.blocked)} cells blocked, {len(f.opaque)} opaque")
    print(f"floor: {len(seen)} reachable cells inside the walls\n")

    taken: list[Cell] = []; placed = {}
    for name, fx, fy in CORNERS:
        tx = min(xs) + (max(xs) - min(xs)) * fx
        ty = min(ys) + (max(ys) - min(ys)) * fy
        for cell, (x, y) in sorted(pts.items(), key=lambda kv: (kv[1][0] - tx) ** 2 + (kv[1][1] - ty) ** 2):
            open_sides = sum(
                1 for dq, dr in NEIGHBOURS if Cell(cell.q + dq, cell.r + dr) not in f.blocked
            )
            if open_sides < OPENNESS:
                continue
            if all(hex_distance(cell, t) >= SPACING for t in taken):
                taken.append(cell); placed[name] = (cell.q, cell.r); break

    print("START_CELLS = {")
    for name, (q, r) in placed.items():
        print(f'    "{name}": ({q}, {r}),')
    print("}")

    polys = []
    for u, s in c.state.shapes.items():
        if s.get("type_") == "polygon":
            v = s.get("vertices")
            if isinstance(v, str):
                v = json.loads(v)
            polys.append({"name": s.get("name"), "open": bool(s.get("open_polygon", True)),
                          "vision": int(s.get("vision_obstruction") or 0),
                          "move": bool(s.get("movement_obstruction")),
                          "pts": [[float(p[0]), float(p[1])] for p in v]})
    out = pathlib.Path(__file__).resolve().parent / "map.json"
    out.write_text(json.dumps({
        "polygons": polys,
        "blocked_px": [[round(p[0]), round(p[1])] for p in wall_px],
        "opaque_px": [[round(cell_center(x, f.grid)[0]), round(cell_center(x, f.grid)[1])] for x in f.opaque],
        "floor_px": [[round(p[0]), round(p[1])] for p in pts.values()],
        "placements_px": {n: [round(pts[Cell(*qr)][0]), round(pts[Cell(*qr)][1])] for n, qr in placed.items()},
        "placements": placed,
    }))
    print(f"\ngeometry -> {out}")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
