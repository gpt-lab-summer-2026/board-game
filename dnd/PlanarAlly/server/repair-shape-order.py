import shutil
import sys
from datetime import datetime, timezone

from peewee import SQL

from src.db.all import Layer, Shape
from src.utils import SAVE_PATH


def run(fix: bool = False):
    """Report - and optionally repair - layers whose shape indices are duplicate or non-contiguous.

    A layer's shapes are meant to carry indices 0..n-1, one each; the index *is* the
    render order.  Duplicates are silent corruption: two shapes sharing an index are
    drawn in whatever order the database happens to return them, so the stacking can
    change between refreshes and differ between players.

    Repair preserves the order you currently see.  Shapes are sorted by (index, rowid)
    - the same ordering the server hands to clients today - and then renumbered, so a
    tie is broken the way it most recently rendered rather than arbitrarily.
    """
    broken: list[tuple[Layer, list[Shape]]] = []

    for layer in Layer.select():
        shapes = list(layer.shapes.order_by(Shape.index, SQL("rowid")))
        if [s.index for s in shapes] != list(range(len(shapes))):
            broken.append((layer, shapes))

    if not broken:
        print("All layers have contiguous, unique shape indices. Nothing to do.")
        return

    for layer, shapes in broken:
        indices = [s.index for s in shapes]
        duplicates = {i for i in indices if indices.count(i) > 1}
        print(f"Layer {layer.id} ({layer.name}) on floor {layer.floor.name}: {len(shapes)} shapes")
        print(f"  indices    : {indices}")
        print(f"  duplicated : {sorted(duplicates) if duplicates else 'none (gaps only)'}")
        for new_index, shape in enumerate(shapes):
            if shape.index != new_index:
                print(f"    {shape.index:>3} -> {new_index:<3}  {shape.name or shape.type_}")
        print()

    if not fix:
        print("Run with the `fix` argument to renumber these layers.")
        return

    backup = f"{SAVE_PATH}.{datetime.now(timezone.utc):%Y%m%d%H%M%S}.bak"
    shutil.copy(SAVE_PATH, backup)
    print(f"Backed up the database to {backup}")

    repaired = 0
    for _layer, shapes in broken:
        for new_index, shape in enumerate(shapes):
            if shape.index != new_index:
                shape.index = new_index
                shape.save()
                repaired += 1

    print(f"Renumbered {repaired} shapes across {len(broken)} layer(s).")
    print("Reload any open game tabs so every client picks up the repaired order.")


if __name__ == "__main__":
    run(fix=len(sys.argv) > 1 and sys.argv[1] == "fix")
