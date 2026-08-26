#!/usr/bin/env python3
"""Refill the consumables a long rest does not bring back.

Hit points, spell slots and rages all return on a long rest; potions and
grenades do not, because they were drunk and thrown. Over a few demo runs the
packs empty out and `<actor> drinks <potion>` starts being refused for a reason
that has nothing to do with the rules being demonstrated.

Run from the PlanarAlly directory with its venv, with the server up:

    server/.venv/bin/python ../tools/restock.py
    server/.venv/bin/python ../tools/restock.py --show

Quantities are the loadout these sheets were built with. Editing LOADOUT here is
the way to change what everyone carries at the start of a demo.
"""
import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, ".")
from ghost.client import GhostClient, GhostConfig  # noqa: E402
from ghost import sheet  # noqa: E402

# character -> {catalogue item id: quantity to hold}
LOADOUT = {
    "elf": {"healing-potion": 2},
    "emo": {"greater-healing-potion": 2, "smokepowder-bomb": 1},
    "freak": {"greater-healing-potion": 1},
    "gentelman": {"healing-potion": 1, "alchemists-fire": 1},
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="report what is carried, change nothing")
    args = ap.parse_args()

    pw = pathlib.Path(os.path.expanduser("~/.config/planarally-ghost/password")).read_text().strip()
    c = GhostClient(GhostConfig(password=pw))
    await c.connect(); await c.load_board(); await asyncio.sleep(2)

    catalogue = {i.get("id"): i for i in await sheet._catalogue_items(c)}
    for name in sorted(set(LOADOUT) | set(c.state.characters)):
        uuid = c.state.find_shape(name)
        if uuid is None:
            continue
        data = await sheet.read_sheet(c, uuid)
        if data is None:
            print(f"{name:11} no sheet")
            continue

        inventory = list(data.get("inventory") or [])
        held = {e.get("id"): int(e.get("quantity") or 0) for e in inventory}
        wanted = LOADOUT.get(name, {})

        if args.show:
            shown = ", ".join(
                f"{(catalogue.get(i) or {}).get('name', i)} x{n}" for i, n in held.items()
            ) or "nothing"
            print(f"{name:11} {shown}")
            continue

        changed = []
        for item_id, qty in wanted.items():
            if item_id not in catalogue:
                print(f"{name:11} no catalogue item {item_id!r}; skipped")
                continue
            if held.get(item_id, 0) >= qty:
                continue
            for entry in inventory:
                if entry.get("id") == item_id:
                    entry["quantity"] = qty
                    break
            else:
                inventory.append({"id": item_id, "quantity": qty})
            changed.append(f"{(catalogue[item_id]).get('name', item_id)} -> {qty}")

        if changed:
            data["inventory"] = inventory
            await sheet.write_sheet(c, uuid, data)
            print(f"{name:11} {', '.join(changed)}")
        else:
            print(f"{name:11} already stocked")

    await asyncio.sleep(1)
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
