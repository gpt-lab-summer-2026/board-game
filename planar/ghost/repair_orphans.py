"""Reattach shapes that lost their layer.

    server/.venv/bin/python -m ghost.repair_orphans            # show only
    server/.venv/bin/python -m ghost.repair_orphans --apply    # fix

A shape's `layer` FK is declared `on_delete="CASCADE"` but `null=True`, and
peewee's `delete_instance(recursive=True)` nulls nullable FKs rather than
cascading. So deleting a floor does not delete the shapes that were on it --
it strands them. The row survives with `layer_id = NULL`, which means:

  - it renders nowhere and is invisible in the client;
  - `Location.Load` never sends it, so the ghost cannot see it either;
  - `Shapes.Layer.Change` refuses to move it ("Attempt to layer-move shape
    without layer"), so there is no in-app route back.

Hence a direct repair. It only ever *assigns* a layer to shapes that have none;
it never moves, deletes or edits anything else.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "server/data/planar.sqlite"


def main() -> int:
    p = argparse.ArgumentParser(description="Reattach layerless shapes.")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--floor", default="ground", help="floor to reattach onto")
    p.add_argument("--layer", default="tokens", help="layer to reattach onto")
    p.add_argument("--apply", action="store_true", help="actually write; otherwise dry run")
    args = p.parse_args()

    db = Path(args.db)
    if not db.is_file():
        print(f"no database at {db}", file=sys.stderr)
        return 2

    con = sqlite3.connect(db)
    target = con.execute(
        "select l.id from layer l join floor f on l.floor_id = f.id "
        "where f.name = ? and l.name = ?",
        (args.floor, args.layer),
    ).fetchone()
    if target is None:
        print(f"no layer {args.layer!r} on floor {args.floor!r}", file=sys.stderr)
        return 2

    orphans = con.execute(
        "select s.uuid, coalesce(c.name, s.name, '?') "
        "from shape s left join character c on c.id = s.character_id "
        "where s.layer_id is null"
    ).fetchall()

    if not orphans:
        print("no layerless shapes; nothing to do")
        return 0

    print(f"{len(orphans)} layerless shape(s):")
    for uuid, name in orphans:
        print(f"  {name:16} {uuid}")
    print(f"\nwould attach to {args.floor}/{args.layer} (layer id {target[0]})")

    if not args.apply:
        print("\ndry run -- pass --apply to write")
        return 0

    with con:
        n = con.execute(
            "update shape set layer_id = ? where layer_id is null", (target[0],)
        ).rowcount
    con.close()
    print(f"\nreattached {n} shape(s). Reload the game tab.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
