"""Carrying out a parsed command against the live board.

Everything here returns narration lines as well as doing the thing. The pipeline
ends in text-to-speech, and a turn nobody can follow is worse than no automation
at all -- so each step says what it did and, when it stopped early, why.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field as dc_field

from . import deathsaves
from . import sheet
from . import battlefield
from .client import GhostClient
from .commands import Action, AttackKind, Intent, HELP_TEXT
from .grid import GridType
from .movement import StopReason, plan_move_into_reach, walk

log = logging.getLogger(__name__)

# 5e: melee reach is 5 ft, i.e. the adjacent cell. Ranged attacks are resolved
# from wherever the character is standing -- range bands are the DM's call, not
# something worth enforcing automatically.
MELEE_REACH_CELLS = 1


@dataclass
class Pending:
    """An action held back until the player confirms it."""

    intent: Intent
    actor_uuid: str
    target_uuid: str
    question: str


@dataclass
class Outcome:
    ok: bool
    lines: list[str] = dc_field(default_factory=list)
    """Only meaningful for movement: whether the mover got within reach."""
    reached: bool = True
    """Set when the ghost is waiting on a yes/no before it will act."""
    pending: "Pending | None" = None

    def say(self, line: str) -> "Outcome":
        self.lines.append(line)
        return self

    @property
    def text(self) -> str:
        return " ".join(self.lines)


async def execute(
    client: GhostClient,
    intent: Intent,
    *,
    as_player: str | None = None,
    accept_hazard: bool = False,
) -> Outcome:
    if intent.action is Action.HELP:
        return Outcome(True, HELP_TEXT.splitlines())

    actor_uuid = client.state.find_shape(intent.actor or "")
    if actor_uuid is None:
        return Outcome(False, [f"I can't find a character called {intent.actor!r}."])

    if intent.action is Action.DUPLICATE:
        return await _do_duplicate(client, actor_uuid, intent)

    if intent.action is Action.CONDITION:
        return await _do_condition(client, actor_uuid, intent)

    if intent.action is Action.DEATH_SAVE:
        name = _display_name(client, actor_uuid, intent.actor)
        return Outcome(True, await deathsaves.roll_save(client, actor_uuid, name))

    if intent.action is Action.HEAL:
        return await _do_heal(client, actor_uuid, intent)

    target_uuid = client.state.find_shape(intent.target or "")
    if target_uuid is None:
        return Outcome(False, [f"I can't find a target called {intent.target!r}."])
    if actor_uuid == target_uuid:
        return Outcome(False, [f"{intent.actor} can't target themselves."])

    actor_name = _display_name(client, actor_uuid, intent.actor)
    target_name = _display_name(client, target_uuid, intent.target)

    if intent.action is Action.MEASURE:
        return await _do_measure(client, actor_uuid, target_uuid, actor_name, target_name)

    if intent.action is Action.MOVE:
        return await _do_move(
            client, actor_uuid, target_uuid, actor_name, target_name, intent, accept_hazard
        )

    # Melee walks first. The movement narration has to survive into the
    # attack's outcome -- "it hit for 11" without "it crossed the lava to do
    # it" is exactly the half of the turn people need to hear.
    prefix: list[str] = []
    if intent.kind is AttackKind.MELEE:
        out = await _do_move(
            client, actor_uuid, target_uuid, actor_name, target_name, intent, accept_hazard
        )
        if not out.ok or out.pending is not None:
            return out
        if not out.reached:
            return out.say(f"{actor_name} is not in reach, so the attack is held.")
        prefix = out.lines
    return await _do_attack(
        client, actor_uuid, target_uuid, actor_name, target_name, intent, as_player,
        prefix=prefix,
    )


def _display_name(client: GhostClient, uuid: str, fallback: str | None) -> str:
    for name, u in client.state.characters.items():
        if u == uuid:
            return name
    return fallback or uuid[:8]


async def _build_field(client: GhostClient) -> battlefield.Battlefield:
    """A fresh cell view of the board, from state the ghost already holds."""
    shapes = ((client.state.shape_layer.get(u, "?"), s) for u, s in client.state.shapes.items())
    return battlefield.build(
        shapes,
        grid=GridType.parse(client.state.grid_type),
        unit_size=client.state.unit_size,
        hazard_uuids=client.state.hazard_uuids,
    )


async def _do_move(
    client, actor_uuid, target_uuid, actor_name, target_name, intent, accept_hazard=False
) -> Outcome:
    field = await _build_field(client)

    speed = 30.0
    actor_sheet = await sheet.read_sheet(client, actor_uuid)
    if actor_sheet is not None:
        speed = float(actor_sheet.get("speed") or 30)

    budget = field.cells_for_speed(speed)
    plan = plan_move_into_reach(
        field, actor_uuid, target_uuid, budget, MELEE_REACH_CELLS, allow_hazards=accept_hazard
    )

    out = Outcome(True, reached=plan.reached)

    if plan.needs_confirmation:
        # A safe route does not exist, but a dangerous one does. Describe it
        # and hand the decision back rather than making it.
        names = _hazard_names(field, plan.hazard_cells)
        through = f" through {names}" if names else " through dangerous terrain"
        feet = int(plan.steps * field.unit_size)
        out.pending = Pending(
            intent=intent, actor_uuid=actor_uuid, target_uuid=target_uuid,
            question=f"{actor_name} can only reach {target_name} by walking{through}",
        )
        return out.say(
            f"The only way for {actor_name} to reach {target_name} is {feet} feet"
            f"{through}. Walk into it? Say yes or no."
        )

    if plan.reason is StopReason.ALREADY_IN_REACH:
        return out.say(f"{actor_name} is already within reach of {target_name}.")

    if plan.steps:
        await walk(client, field, actor_uuid, plan)
        feet = int(plan.steps * field.unit_size)
        out.say(f"{actor_name} moves {feet} feet towards {target_name}.")
    else:
        out.say(f"{actor_name} doesn't move.")

    if plan.reached:
        return out
    if plan.reason is StopReason.HAZARD:
        return out.say("It stops at the edge of dangerous terrain rather than walking through.")
    if plan.reason is StopReason.OUT_OF_MOVEMENT:
        return out.say(f"That is all the movement {actor_name} has.")
    return out.say(f"There is no clear route to {target_name}.")


async def _apply_on_hit(client, target_uuid, target_name, applied, out) -> None:
    """Apply a weapon or cantrip's condition, rolling the save if it has one.

    A failed save is narrated as a failed save rather than silently applied:
    the table needs to hear the number to trust the outcome.
    """
    save_ability, dc = applied.get("save"), applied.get("dc")
    if save_ability and dc:
        target_sheet = await sheet.read_sheet(client, target_uuid)
        saves = (target_sheet or {}).get("derived", {}).get("saves", {})
        bonus = (saves.get(save_ability) or {}).get("bonus", 0)
        roll = await client.roll_dice(
            f"1d20{bonus:+d}" if bonus else "1d20", share_with="all", as_player=target_name
        )
        if roll.total >= dc:
            out.say(
                f"{target_name} saves against {applied['name'].lower()}: "
                f"{roll.total} versus DC {dc}."
            )
            return
        out.say(f"{target_name} fails the save, {roll.total} against DC {dc}.")

    try:
        await sheet.set_condition(client, target_uuid, applied["condition"], True)
    except (KeyError, sheet.CatalogueNotReady):
        # Worth saying, not worth aborting a resolved attack over.
        out.say(f"(couldn't record {applied['name'].lower()} on the sheet)")
        return
    out.say(f"{target_name} is now {applied['name'].lower()}.")


async def _do_condition(client, target_uuid: str, intent: Intent) -> Outcome:
    name = _display_name(client, target_uuid, intent.actor)
    condition = intent.condition or ""
    try:
        remaining = await sheet.set_condition(client, target_uuid, condition, intent.condition_on)
    except sheet.CatalogueNotReady as e:
        return Outcome(False, [str(e)])
    except KeyError as e:
        if str(e).strip("'") == condition:
            return Outcome(False, [f"I don't know a condition called {condition!r}."])
        return Outcome(False, [str(e).strip("'")])

    verb = "is now" if intent.condition_on else "is no longer"
    pretty = (await sheet.condition_names(client, [condition]))[0]
    out = Outcome(True, [f"{name} {verb} {pretty.lower()}."])
    if remaining:
        others = await sheet.condition_names(client, remaining)
        return out.say(f"Currently: {', '.join(others).lower()}.")
    return out.say("No conditions remaining.")


async def _do_heal(client, target_uuid: str, intent: Intent) -> Outcome:
    """Restore hit points, and bring anyone who was down back into the fight.

    A bare "heal atton" gives 1 point, because the reason you say it at the
    table is to get someone conscious and back in the order, not to pick a
    number.
    """
    name = _display_name(client, target_uuid, intent.actor)
    data = await sheet.read_sheet(client, target_uuid)
    if data is None:
        return Outcome(False, [f"{name} has no sheet, so there are no hit points to restore."])

    hp = data["hp"]
    amount = intent.heal_amount if intent.heal_amount is not None else 1
    healed = min(hp["max"], max(0, hp["current"]) + amount)
    await sheet.set_hp(client, target_uuid, current=healed)

    out = Outcome(True, [f"{name} is healed {amount}, now on {healed} of {hp['max']}."])
    if healed > 0:
        for line in await deathsaves.on_healed(client, target_uuid, name):
            out.say(line)
    return out


async def _do_duplicate(client, source_uuid: str, intent: Intent) -> Outcome:
    from . import characters

    source_name = _display_name(client, source_uuid, intent.actor)
    new_name = intent.target or _next_name(client, source_name)
    field = await _build_field(client)
    try:
        await characters.duplicate(client, source_uuid, new_name, field=field)
    except characters.DuplicateError as e:
        return Outcome(False, [str(e)])
    return Outcome(True, [f"Copied {source_name} as {new_name}, sheet and all."])


def _next_name(client, base: str) -> str:
    """'gobbo' -> 'gobbo 2'. A table with four goblins should not have to
    invent four names."""
    existing = {n.lower() for n in client.state.characters}
    n = 2
    while f"{base.lower()} {n}" in existing:
        n += 1
    return f"{base} {n}"


def _hazard_names(field, cells) -> str:
    """Name the hazards a route crosses, so the question is answerable.

    "walk through the lava pool?" is a decision; "walk through dangerous
    terrain?" is a shrug.
    """
    names: list[str] = []
    for cell in cells:
        name = field.names.get(cell)
        if name and name not in names:
            names.append(name)
    if not names:
        return ""
    if len(names) == 1:
        return f"the {names[0]}"
    return "the " + ", the ".join(names[:-1]) + f" and the {names[-1]}"


def _is_are(names: str) -> str:
    """Narration is read aloud, so it has to agree in number."""
    return "are" if " and " in names else "is"


async def _do_measure(client, actor_uuid, target_uuid, actor_name, target_name) -> Outcome:
    """The ruler, as a command.

    PlanarAlly's ruler tool is client-side, but it publishes what it draws as
    temporary shapes when "show public" is on -- so the ghost can draw the same
    line everyone else sees, not merely report a number.
    """
    from . import scene
    from .grid import distance

    field = await _build_field(client)
    a = field.occupants.get(actor_uuid)
    b = field.occupants.get(target_uuid)
    if a is None or b is None:
        return Outcome(False, ["I can't place both of those on the board."])

    cells = distance(a.cell, b.cell, field.grid)
    feet = int(cells * field.unit_size)
    out = Outcome(True)

    sight = "clear line of sight" if field.has_line_of_sight(a.cell, b.cell) else "no line of sight"
    out.say(f"{actor_name} to {target_name}: {feet} feet ({cells} cells), {sight}.")

    try:
        await scene.draw_ruler(client, field, a.cell, b.cell, f"{feet} ft")
    except Exception as e:  # noqa: BLE001 - the number is the point; the line is a bonus
        log.info("could not draw the ruler: %s", e)
    return out


async def _do_attack(
    client, actor_uuid, target_uuid, actor_name, target_name, intent, as_player, prefix
) -> Outcome:
    kind = (intent.kind or AttackKind.MELEE).value
    out = Outcome(True, list(prefix or []))

    # Ranged attacks and spells need to see what they are shooting at. Melee
    # doesn't need the check -- you are standing next to it.
    if intent.kind in (AttackKind.RANGED, AttackKind.CANTRIP):
        field = await _build_field(client)
        a, b = field.occupants.get(actor_uuid), field.occupants.get(target_uuid)
        if a is not None and b is not None and not field.has_line_of_sight(a.cell, b.cell):
            # Only name what actually stops sight. Everything on the line gets
            # indexed, hazards included, and reporting "the lava pool is in
            # the way" of a *view* is simply untrue -- you can see over it.
            between = [x for x in field.cells_between(a.cell, b.cell) if x in field.opaque]
            blockers = _hazard_names(field, between) or "something solid"
            return Outcome(
                False,
                [
                    *(prefix or []),
                    f"{actor_name} has no line of sight to {target_name} — "
                    f"{blockers} {_is_are(blockers)} in the way.",
                ],
            )

    target_sheet = await sheet.read_sheet(client, target_uuid)
    armour_class = int((target_sheet or {}).get("ac") or 0) or None

    rolls = await sheet.roll_attack(
        client, actor_uuid, kind, bias=intent.bias, as_player=as_player or actor_name
    )
    if rolls is None:
        return Outcome(False, [*(prefix or []), f"{actor_name} has no {kind} attack equipped."])

    to_hit, damage, attack = rolls.to_hit, rolls.damage, rolls.attack

    if to_hit is None:
        # A save-based cantrip: the target rolls, not the attacker.
        derived = ((await sheet.read_sheet(client, actor_uuid)) or {}).get("derived", {})
        cantrip = derived.get("cantrip") or {}
        dc, save = cantrip.get("saveDc"), (cantrip.get("save") or "").upper()
        return out.say(
            f"{actor_name} casts {cantrip.get('name', 'a cantrip')} at {target_name}: "
            f"DC {dc} {save} save, {damage.total} damage on a failure."
        )

    bias_note = "" if intent.bias == "normal" else f" with {intent.bias}"
    natural = to_hit.counted[0] if to_hit.counted else 0
    out.say(f"{actor_name} attacks {target_name}{bias_note}: {to_hit.total} to hit {to_hit.long_result()}.")

    if natural == 1:
        return out.say("A natural 1 -- it misses badly.")

    crit = natural == 20
    if armour_class is None:
        out.say(f"{target_name} has no armour class recorded, so that is the DM's call.")
        return out.say(f"Damage would be {damage.total}.")

    if not crit and to_hit.total < armour_class:
        return out.say(f"That misses AC {armour_class}.")

    total = damage.total
    if crit:
        # A critical doubles the dice, not the modifier.
        extra = await client.roll_dice(damage.notation, share_with="none", as_player=as_player or actor_name)
        total += sum(extra.counted)
        out.say(f"A nat 20: critically hit for {total} damage.")
    else:
        out.say(f"That hits AC {armour_class} for {total} damage.")

    # The condition rides on the hit rather than needing a second command --
    # nobody at a table says "I hit" and then "and now it is bleeding".
    applied = (attack or {}).get("applies")
    if applied:
        await _apply_on_hit(client, target_uuid, target_name, applied, out)

    if target_sheet is not None:
        # Whether they were already down decides what this hit means: damage at
        # 0 is an automatic death save failure, not a fresh knockdown.
        was_down = target_sheet.get("hp", {}).get("current", 1) <= 0

        hp = await sheet.damage(client, target_uuid, total)
        if hp["current"] <= 0:
            if was_down:
                for line in await deathsaves.on_damage_while_down(
                    client, target_uuid, target_name, critical=crit
                ):
                    out.say(line)
            else:
                for line in await deathsaves.on_dropped_to_zero(client, target_uuid, target_name):
                    out.say(line)
        else:
            out.say(f"{target_name} is on {hp['current']} of {hp['max']}.")
    return out
