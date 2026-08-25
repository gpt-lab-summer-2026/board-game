"""Everything a character can actually do right now, as a list.

The point is discoverability. The command grammar has grown to thirty-odd
shapes, and a player at a projected table cannot be expected to remember which
ones apply to them -- especially the ones that depend on what they are holding
or what they have prepared.

Assembled here rather than in the browser for the same reason the world state
is: the sheet, the catalogue and the rules for reading them already live on this
side. A panel that built its own list would be a second implementation of
"which cantrip does this wizard know", and the two would drift.

Every entry carries the exact command string, so the panel is a button that
posts text -- no second code path into the game, and anything the panel can do
can also be typed.
"""
from __future__ import annotations

import logging
from typing import Any

from . import sheet
from .client import GhostClient

log = logging.getLogger(__name__)

# Available to anybody, whatever they are carrying. `{a}` is filled with the
# character's name, `{t}` marks an entry that needs a target chosen first.
UNIVERSAL = [
    ("Move", "move", "{a} moves to {t}", True),
    ("Back away", "move", "{a} moves away from {t}", True),
    ("Jump", "move", "{a} jumps towards {t}", True),
    ("Dash", "move", "{a} dashes", False),
    ("Hide", "action", "{a} stealth check", False),
    ("Grapple", "action", "{a} grapples {t}", True),
    ("Shove", "action", "{a} shoves {t}", True),
    ("Topple", "action", "{a} topples {t}", True),
    ("Disarm", "action", "{a} disarms {t}", True),
    ("Measure", "info", "measure from {a} to {t}", True),
    # Actorless -- the template ignores {a} -- but it belongs on the panel next
    # to the actions it ends, not in a group of its own.
    ("End turn", "info", "next turn", False),
]

# The eight headings, offered as one group rather than eight buttons.
HEADINGS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


async def for_character(client: GhostClient, name: str) -> dict[str, Any]:
    """The action list for one character."""
    uuid = client.state.find_shape(name)
    if uuid is None:
        return {"character": name, "found": False, "groups": []}

    data = await sheet.read_sheet(client, uuid)
    derived = (data or {}).get("derived") or {}

    groups: list[dict[str, Any]] = []

    attacks: list[dict[str, Any]] = []
    for kind, label in (("melee", "Melee"), ("ranged", "Ranged")):
        block = derived.get(kind) or {}
        weapon = block.get("weapon")
        if weapon:
            attacks.append({
                "label": f"{label}: {weapon}",
                "command": f"{name} {kind} attack on {{t}}",
                "needsTarget": True,
                "detail": f"{block.get('attack', '')} / {block.get('damage', '')}",
            })
    cantrip = derived.get("cantrip") or {}
    if cantrip.get("name"):
        attacks.append({
            "label": cantrip["name"],
            "command": f"{name} cantrip on {{t}}",
            "needsTarget": True,
            "detail": cantrip.get("attack") or (
                f"DC {cantrip.get('saveDc')} {str(cantrip.get('save') or '').upper()}"
            ),
        })
    if attacks:
        groups.append({"name": "Attacks", "entries": attacks})

    spells = []
    slots = (data or {}).get("slots", {}).get("1") or {}
    for spell in derived.get("spells") or []:
        spells.append({
            "label": spell.get("name"),
            "command": f"{name} casts {spell.get('name')} on {{t}}",
            # A self-buff has nowhere to point; asking for a target would be
            # a question with no right answer.
            "needsTarget": spell.get("kind") not in ("buff",),
            "detail": spell.get("attack")
            or (f"DC {spell.get('saveDc')} {str(spell.get('save') or '').upper()}" if spell.get("save") else "")
            or (f"heals {spell.get('healing')}" if spell.get("healing") else ""),
        })
    if spells:
        left = int(slots.get("max", 0)) - int(slots.get("used", 0))
        groups.append({"name": f"Spells ({left} of {slots.get('max', 0)} slots)", "entries": spells})

    items = []
    catalogue_items = {i["id"]: i for i in ((await sheet.read_catalogue(client)) or {}).get("items", [])}
    for entry in (data or {}).get("inventory") or []:
        item = catalogue_items.get(entry.get("id"))
        if item is None or int(entry.get("quantity") or 0) <= 0:
            continue
        drink = item.get("kind") == "potion"
        items.append({
            "label": f"{item['name']} x{entry['quantity']}",
            "command": f"{name} {'drinks' if drink else 'throws'} {item['name']}"
                       + ("" if drink else " at {t}"),
            "needsTarget": not drink,
            "detail": item.get("kind"),
        })
    if items:
        groups.append({"name": "Items", "entries": items})

    groups.append({
        "name": "Actions",
        "entries": [
            {"label": label, "command": template.replace("{a}", name),
             "needsTarget": needs, "detail": group}
            for label, group, template, needs in UNIVERSAL
        ],
    })
    groups.append({
        "name": "Move in a direction",
        "entries": [
            {"label": h.title(), "command": f"{name} moves {h}", "needsTarget": False, "detail": ""}
            for h in HEADINGS
        ],
    })

    return {"character": name, "found": True, "groups": groups}
