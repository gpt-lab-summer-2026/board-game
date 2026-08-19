"""Carrying out a parsed command against the live board.

Everything here returns narration lines as well as doing the thing. The pipeline
ends in text-to-speech, and a turn nobody can follow is worse than no automation
at all -- so each step says what it did and, when it stopped early, why.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field as dc_field
from typing import Any

from . import deathsaves
from . import ephemera
from . import sheet
from . import turns
from . import battlefield
from .client import GhostClient
from .commands import Action, AttackKind, Intent, HELP_TEXT
from .grid import GridType, distance as grid_distance
from .movement import (
    COMPASS,
    MovePlan,
    StopReason,
    plan_direction,
    plan_move_into_reach,
    plan_retreat,
    walk,
)

log = logging.getLogger(__name__)

# 5e: melee reach is 5 ft, i.e. the adjacent cell. Ranged attacks are resolved
# from wherever the character is standing -- range bands are the DM's call, not
# something worth enforcing automatically.
MELEE_REACH_CELLS = 1


@dataclass
class Pending:
    """An action held back until the player confirms it.

    Two shapes now. The original: an intent the ghost is willing to carry out
    once somebody accepts the risk -- walking through fire. The second: a
    *counter-proposal*, where the thing asked for cannot be done and the ghost
    has found something adjacent to it that can. `move_to` carries the route,
    and `then` the action to take on arrival, so "you have no shot from there,
    step twelve feet east and take it?" is one yes.

    `marker_uuids` are the temporary shapes drawn to show where "there" is.
    Whoever resolves the question is responsible for clearing them, on yes and
    on no alike -- a marker left on the board outlives the question it was
    asking and becomes scenery nobody can explain.
    """

    intent: Intent
    actor_uuid: str
    target_uuid: str
    question: str
    move_to: list = dc_field(default_factory=list)
    then: "Intent | None" = None
    marker_uuids: list[str] = dc_field(default_factory=list)


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

    if intent.action is Action.AC_MODIFIER:
        return await _do_ac_modifier(client, actor_uuid, intent)

    if intent.action is Action.SAVE:
        return await _do_save(client, actor_uuid, intent, as_player)

    if intent.action is Action.CHECK:
        return await _do_check(client, actor_uuid, intent, as_player)

    if intent.action is Action.DASH:
        return await _do_dash(client, actor_uuid, intent)

    if intent.action is Action.MOVE_DIR:
        return await _do_move_direction(client, actor_uuid, intent)

    if intent.action is Action.USE_ITEM:
        item_target = None
        if intent.target:
            item_target = client.state.find_shape(intent.target)
            if item_target is None:
                return Outcome(False, [f"I can't find a target called {intent.target!r}."])
        return await _do_use_item(client, actor_uuid, item_target, intent, as_player)

    if intent.action is Action.JUMP and intent.direction:
        return await _do_jump(client, actor_uuid, None, intent)

    if intent.action is Action.CAST:
        # Resolved before the mandatory lookup below: a self-buff like Shield
        # and an area spell like Burning Hands are cast with no target at all,
        # and refusing them for want of one would be wrong.
        spell_target = None
        if intent.target:
            spell_target = client.state.find_shape(intent.target)
            if spell_target is None:
                return Outcome(False, [f"I can't find a target called {intent.target!r}."])
        return await _do_cast(client, actor_uuid, spell_target, intent, as_player)

    target_uuid = client.state.find_shape(intent.target or "")
    if target_uuid is None:
        return Outcome(False, [f"I can't find a target called {intent.target!r}."])
    if actor_uuid == target_uuid:
        return Outcome(False, [f"{intent.actor} can't target themselves."])

    actor_name = _display_name(client, actor_uuid, intent.actor)
    target_name = _display_name(client, target_uuid, intent.target)

    if intent.action is Action.JUMP:
        return await _do_jump(client, actor_uuid, target_uuid, intent)

    if intent.action is Action.RETREAT:
        return await _do_retreat(client, actor_uuid, target_uuid, actor_name, target_name, intent)

    if intent.action is Action.CONTEST:
        return await _do_contest(client, actor_uuid, target_uuid, intent, as_player)

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


# How long a spell's mark stays on the board, in turns. Instantaneous spells get
# one turn so the table can see where the Fire Bolt went before it is gone;
# anything with concentration or a stated duration lingers.
def effect_turns(spell: dict) -> int:
    if spell.get("concentration"):
        return 10
    duration = str(spell.get("duration") or "").lower()
    if "minute" in duration:
        return 10
    if "hour" in duration:
        return 60
    if duration:
        return 2
    return 1


# Colour by damage type, so a glance at the board says what happened. Falls back
# to a neutral wash rather than picking something arbitrary and wrong.
EFFECT_COLOURS = {
    "fire": "#ff7a3355", "cold": "#7ad7ff55", "lightning": "#ffe14d55",
    "thunder": "#c9a6ff55", "radiant": "#fff2b055", "force": "#b0c4ff55",
    "acid": "#9cff7a55", "poison": "#8fd18f55", "necrotic": "#6b5b7b55",
}


async def _draw_spell_effect(client, spell: dict, centre_uuid: str | None) -> None:
    """Put the spell on the board for as long as it lasts.

    Only ever decoration -- the geometry that decides who is hit is computed
    separately and is not read back off these shapes. Drawing were it to fail
    must not cost anybody a spell slot, hence the broad catch.
    """
    if centre_uuid is None:
        return
    from . import scene

    try:
        field = await _build_field(client)
        centre = field.occupants.get(centre_uuid)
        if centre is None:
            return

        area = spell.get("area") or {}
        size_ft = int(area.get("size") or 0)
        radius = max(0, int(size_ft // field.unit_size)) if size_ft else 0
        # The whole footprint, not just the cells that happen to be occupied:
        # the point of drawing it is to show the ground it covers.
        # Capped for the same reason the ruler's highlight is: each cell is a
        # separate synced shape on the draw layer, and a big radius on a hex
        # grid grows quadratically -- a 30 ft burst at 7 ft per cell is 61 of
        # them.
        cells = (_cells_within(field, centre.cell, radius) if radius else [centre.cell])[:24]

        colour = EFFECT_COLOURS.get(str(spell.get("damageType") or ""), "#b0b0b055")
        drawn = await scene.add_block(
            client, field, cells, ephemera.EFFECT_NAME,
            floor=client.state.current_floor,
            blocks_vision=False, blocks_movement=False,
            fill=colour, layer="draw",
        )
        ephemera.add(
            drawn,
            turns=effect_turns(spell),
            label=f"{spell.get('name')} fades",
            kind=ephemera.EFFECT_NAME,
        )
    except Exception:  # noqa: BLE001 - a missing picture must not cost a slot
        log.exception("could not draw the spell effect")


def _cells_within(field, centre, radius: int) -> list:
    """Every cell within `radius` of `centre`, footprint and all."""
    from .grid import neighbours

    seen = {centre}
    frontier = [centre]
    for _ in range(radius):
        nxt = []
        for cell in frontier:
            for n in neighbours(cell, field.grid):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
        frontier = nxt
    return list(seen)


async def _friendly_fire_warning(client, caster_uuid, target_uuid, spell) -> str | None:
    """A line to say when an area spell would also catch your own side.

    Returns None when the spell has no area, when sides have not been assigned,
    or when only enemies are in it -- silence is the right output for the normal
    case, and a warning that fires on every cast stops being read.
    """
    from . import suggest

    area = spell.get("area")
    if not area:
        return None

    field = await _build_field(client)
    origin = field.occupants.get(target_uuid) or field.occupants.get(caster_uuid)
    if origin is None:
        return None

    # Approximated as a disc of the stated size. A true cone needs a facing,
    # which nothing on the board records; over-reporting who is in the blast is
    # the safe direction for a warning to be wrong in.
    radius = max(1, int(int(area.get("size") or 0) / max(field.unit_size, 1)))
    covered = {
        cell for cell in field.occupied
        if grid_distance(cell, origin.cell, field.grid) <= radius
    }

    sides = await _sides(client)
    friends = suggest.caught_in_area(field, covered, sides, caster_uuid)
    friends = [u for u in friends if u != target_uuid]
    if not friends:
        return None

    names = ", ".join(_display_name(client, u, None) for u in friends)
    return (
        f"That {area.get('size')} ft {area.get('shape')} would also catch {names}. "
        f"Say yes to cast it anyway, or move first."
    )


async def _offer_a_better_spot(
    client, field, actor_uuid, target_uuid, actor_name, target_name,
    intent: Intent, refusal: str, prefix,
) -> Outcome:
    """Turn "you cannot" into "not from there -- from here?".

    Held as a Pending rather than done, because moving somebody is not what they
    asked for. The marker is drawn now so that "here" is a place on the board
    and not a number in a sentence; it is cleared when the question resolves
    either way.
    """
    from . import suggest

    lines = [*(prefix or []), refusal]

    speed = 30.0
    actor_sheet = await sheet.read_sheet(client, actor_uuid)
    if actor_sheet is not None:
        speed = float(actor_sheet.get("speed") or 30)

    sides = await _sides(client)
    spot = suggest.spot_with_sight(
        field, actor_uuid, target_uuid, field.cells_for_speed(speed), sides
    )
    if spot is None:
        return Outcome(False, [*lines, f"There is nowhere within {int(speed)} feet with a clear shot."])

    markers = await _mark(client, field, spot)
    question = spot.describe(actor_name, target_name) + ". Move there and attack?"
    return Outcome(
        True,
        [*lines, question],
        pending=Pending(
            intent=intent,
            actor_uuid=actor_uuid,
            target_uuid=target_uuid,
            question=question,
            move_to=spot.path,
            then=intent,
            marker_uuids=markers,
        ),
    )


async def _sides(client) -> dict[str, str]:
    """shape uuid -> disposition, for the threat and friendly-fire checks."""
    from . import worldstate

    factions = await worldstate._factions(client)
    return {
        uuid: worldstate._side(factions, uuid)
        for uuid in client.state.shapes
    }


async def _mark(client, field, spot) -> list[str]:
    """Paint the proposed cell, so "there" is somewhere you can point at."""
    from . import scene

    floor = client.state.current_floor
    if floor is None:
        return []
    try:
        return await scene.add_block(
            client, field, [spot.cell], ephemera.SUGGESTION_NAME,
            floor=floor, blocks_vision=False, blocks_movement=False,
            fill="#82c8a077", layer="draw",
        )
    except Exception:  # noqa: BLE001 - a missing marker must not lose the suggestion
        log.exception("could not draw the suggestion marker")
        return []


# 5e: a running jump clears your Strength score in feet, and half that from a
# standing start. There is no running-start concept on the board, so the full
# distance is used and the DM can rule otherwise.
def jump_feet(strength: int) -> int:
    return max(5, int(strength))


async def _do_use_item(client, actor_uuid, target_uuid, intent: Intent, as_player) -> Outcome:
    """Drink it, throw it, or drop it -- and spend the charge either way.

    The count comes off before anything is resolved. A grenade that went off and
    is still in your pack because the damage roll raised is a worse bug than one
    that is spent on a fumble, and the two are indistinguishable afterwards.
    """
    name = _display_name(client, actor_uuid, intent.actor)
    data = await sheet.read_sheet(client, actor_uuid)
    if data is None:
        return Outcome(False, [f"{name} has no sheet, so nothing to carry."])

    carried, entry = await sheet.find_carried(client, data, intent.item or "")
    if carried is None:
        have = await sheet.carried_names(client, data)
        return Outcome(
            False,
            [f"{name} is not carrying {intent.item!r}. Carrying: {have or 'nothing'}."],
        )

    left = await sheet.spend_item(client, actor_uuid, entry["id"])
    label = carried.get("name") or intent.item
    out = Outcome(True, [f"{name} uses {label} ({left} left)."])

    if carried.get("healing"):
        drinker = target_uuid or actor_uuid
        drinker_name = _display_name(client, drinker, intent.target) if target_uuid else name
        roll = await client.roll_dice(carried["healing"], share_with="all", as_player=as_player or name)
        before = ((await sheet.read_sheet(client, drinker)) or {}).get("hp", {}).get("current", 0)
        after = await sheet.heal(client, drinker, roll.total)
        for line in await deathsaves.on_healed(client, drinker, drinker_name):
            out.say(line)
        # The roll and the healing are different numbers once the cap bites.
        # Reporting the roll read as an off-by-one every time somebody topped up.
        restored = after["current"] - max(0, before)
        wasted = roll.total - restored
        tail = f" ({roll.total} rolled, {wasted} wasted)" if wasted > 0 else ""
        return out.say(f"{drinker_name} regains {restored}, now on {after['current']}{tail}.")

    if target_uuid is None:
        return out.say(f"{label} needs somewhere to go -- name a target.")

    target_name = _display_name(client, target_uuid, intent.target)
    field = await _build_field(client)

    # Everything caught, not just the named target: an area item that only ever
    # hit what it was aimed at would be indistinguishable from a dart.
    victims = [target_uuid]
    radius_ft = int(carried.get("area") or 0)
    if radius_ft:
        centre = field.occupants.get(target_uuid)
        if centre is not None:
            radius = max(1, int(radius_ft // field.unit_size))
            victims = [
                uuid for uuid, occ in field.occupants.items()
                if grid_distance(occ.cell, centre.cell, field.grid) <= radius
            ]
            if len(victims) > 1:
                out.say(f"The {radius_ft} ft burst catches {len(victims)} creatures.")

    damage_roll = None
    if carried.get("damage"):
        damage_roll = await client.roll_dice(carried["damage"], share_with="all", as_player=as_player or name)

    for victim in victims:
        victim_name = _display_name(client, victim, None)
        amount = damage_roll.total if damage_roll else 0
        if carried.get("save"):
            ability = carried["save"]
            dc = int(carried.get("saveDc") or 13)
            result, _ = await sheet.roll_save(client, victim, ability, as_player=victim_name)
            made = result.total >= dc
            out.say(
                f"{victim_name} rolls {result.total} against DC {dc} {ability.upper()}: "
                f"{'saves' if made else 'fails'}."
            )
            if made:
                amount = amount // 2
        if amount > 0:
            await _land(client, victim, victim_name, amount, out)
        if carried.get("applies") and not (carried.get("save") and amount == 0):
            applies = dict(carried["applies"])
            applies.setdefault("dc", int(carried.get("saveDc") or 13))
            applies["name"] = await sheet.condition_label(client, applies.get("condition", ""))
            await _apply_on_hit(client, victim, victim_name, applies, out)

    return out


async def _do_jump(client, actor_uuid: str, target_uuid: str | None, intent: Intent) -> Outcome:
    """Cover ground in one leap, over anything in between.

    Distinct from walking in the way that matters: a jump ignores what is on the
    floor between take-off and landing, so it crosses a pit or a caltrop field
    that a walk would have to go round. It cannot cross a wall -- that is a
    climb -- so the landing cell still has to be reachable in a straight line
    with nothing solid in the way.
    """
    from . import suggest
    from .grid import cell_center, cell_from_point

    name = _display_name(client, actor_uuid, intent.actor)
    field = await _build_field(client)
    mover = field.occupants.get(actor_uuid)
    if mover is None:
        return Outcome(False, [f"{name} is not on the board."])

    data = await sheet.read_sheet(client, actor_uuid)
    strength = int(((data or {}).get("abilities") or {}).get("str") or 10)
    reach_ft = jump_feet(strength)
    reach_cells = max(1, int(reach_ft // field.unit_size))

    # Candidate landings: in a straight line towards the target or heading, no
    # further than the jump allows, and clear to land on.
    if target_uuid is not None:
        goal = field.occupants.get(target_uuid)
        if goal is None:
            return Outcome(False, ["That target is not on the board."])
        aim = goal.cell
    else:
        heading = COMPASS.get(intent.direction or "")
        if heading is None:
            return Outcome(False, [f"{intent.direction!r} is not a direction I know."])
        ax, ay = cell_center(mover.cell, field.grid)
        # Aim well past the jump's limit so the line has cells to offer; the
        # distance check below is what actually bounds it.
        aim = cell_from_point(
            ax + heading[0] * reach_ft * 4, ay + heading[1] * reach_ft * 4, field.grid
        )

    line = field.cells_between(mover.cell, aim)
    landing = None
    for cell in line:
        if grid_distance(mover.cell, cell, field.grid) > reach_cells:
            break
        if cell in field.blocked:
            break  # a wall stops a jump; going over it is a climb
        if field.is_free(cell, ignore={actor_uuid, target_uuid or ""}):
            landing = cell

    if landing is None:
        return Outcome(True, [f"{name} has nowhere to land within {reach_ft} feet."])

    feet = int(grid_distance(mover.cell, landing, field.grid) * field.unit_size)
    await walk(client, field, actor_uuid, MovePlan([landing], StopReason.ARRIVED, reached=True))
    await turns.spend_movement(client, actor_uuid, feet, int((data or {}).get("speed") or 30))

    out = Outcome(True, [
        f"{name} jumps {feet} feet (Strength {strength} allows {reach_ft}), "
        f"clearing whatever was underneath."
    ])
    if target_uuid is not None:
        gap = int(grid_distance(landing, field.occupants[target_uuid].cell, field.grid) * field.unit_size)
        out.say(f"That lands {gap} feet from {_display_name(client, target_uuid, intent.target)}.")
    return out


async def _do_dash(client, actor_uuid: str, intent: Intent) -> Outcome:
    """Trade the action for a second helping of movement.

    Implemented by crediting the turn budget rather than by moving anything: a
    Dash does not decide where you go, it decides how far you may. The credit is
    a negative spend, which is what keeps "moved 15 of 30" reading correctly
    after it.
    """
    name = _display_name(client, actor_uuid, intent.actor)
    data = await sheet.read_sheet(client, actor_uuid)
    speed = int((data or {}).get("speed") or 30)

    spent = await turns.spend(client, actor_uuid, "action")
    if not spent:
        return Outcome(False, [f"{name} has already used its action this turn."])

    await turns.spend_movement(client, actor_uuid, -speed, speed)
    return Outcome(True, [f"{name} dashes: another {speed} feet of movement this turn."])


async def _do_move_direction(client, actor_uuid: str, intent: Intent) -> Outcome:
    """Walk as far as possible along a compass heading."""
    name = _display_name(client, actor_uuid, intent.actor)
    heading = COMPASS.get(intent.direction or "")
    if heading is None:
        return Outcome(False, [f"{intent.direction!r} is not a direction I know."])

    field = await _build_field(client)
    speed = 30.0
    actor_sheet = await sheet.read_sheet(client, actor_uuid)
    if actor_sheet is not None:
        speed = float(actor_sheet.get("speed") or 30)

    plan = plan_direction(field, actor_uuid, heading, field.cells_for_speed(speed))
    if not plan.path:
        blocker = "something dangerous" if plan.blocked_by_hazard else "a wall"
        return Outcome(True, [f"{name} can't go {intent.direction} -- {blocker} is in the way."])

    await walk(client, field, actor_uuid, plan)
    feet = int(plan.steps * field.unit_size)
    await turns.spend_movement(client, actor_uuid, feet, int(speed))

    out = Outcome(True, [f"{name} moves {feet} feet {intent.direction}."])
    if plan.reason is StopReason.OUT_OF_MOVEMENT:
        out.say(f"That is all the movement {name} has.")
    return out


async def _do_retreat(
    client, actor_uuid, target_uuid, actor_name, target_name, intent
) -> Outcome:
    """Back away from a threat, as far as this turn's movement allows."""
    field = await _build_field(client)

    speed = 30.0
    actor_sheet = await sheet.read_sheet(client, actor_uuid)
    if actor_sheet is not None:
        speed = float(actor_sheet.get("speed") or 30)

    before = field.occupants.get(actor_uuid)
    threat = field.occupants.get(target_uuid)
    if before is None or threat is None:
        return Outcome(False, [f"{actor_name} or {target_name} is not on the board."])
    gap_before = grid_distance(before.cell, threat.cell, field.grid)

    heading = COMPASS.get(intent.direction or "")
    plan = plan_retreat(
        field, actor_uuid, [target_uuid], field.cells_for_speed(speed), heading=heading
    )
    if not plan.path:
        if plan.blocked_by_hazard:
            return Outcome(
                True,
                [f"{actor_name} is boxed in -- every way back from {target_name} crosses something dangerous."],
            )
        return Outcome(True, [f"{actor_name} has nowhere to go; {target_name} has it cornered."])

    await walk(client, field, actor_uuid, plan)
    feet = int(plan.steps * field.unit_size)
    await turns.spend_movement(client, actor_uuid, feet, int(speed))

    gap_after = grid_distance(plan.path[-1], threat.cell, field.grid)
    which_way = f" to the {intent.direction}" if intent.direction and plan.heading_honoured else ""
    out = Outcome(True, [
        f"{actor_name} backs {feet} feet away from {target_name}{which_way}, "
        f"opening the gap from {int(gap_before * field.unit_size)} to "
        f"{int(gap_after * field.unit_size)} feet."
    ])
    if intent.direction and not plan.heading_honoured:
        out.say(f"Nothing to the {intent.direction} was reachable, so it went the other way.")
    # Worth saying out loud: leaving a threatened square is what provokes, and
    # the ghost is not going to roll someone else's reaction unasked.
    if gap_before <= MELEE_REACH_CELLS:
        out.say(f"That leaves {target_name}'s reach, so it may take an opportunity attack.")
    if plan.reason is StopReason.OUT_OF_MOVEMENT:
        out.say(f"That is all the movement {actor_name} has.")
    return out


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
        # Book it against the turn budget so the bar agrees with the board. A
        # no-op when it is not this creature's turn, which is the common case
        # for shuffling monsters around outside combat.
        speed = (await sheet.read_sheet(client, actor_uuid) or {}).get("speed")
        await turns.spend_movement(client, actor_uuid, feet, speed)
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
    # Weapons and cantrips arrive here pre-resolved by the mod's deriveApplies,
    # which adds a display name and a DC. Catalogue items carry the raw
    # `{condition}` block instead, so neither is guaranteed.
    label = str(applied.get("name") or applied.get("condition") or "it")
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
                f"{target_name} saves against {label.lower()}: "
                f"{roll.total} versus DC {dc}."
            )
            return
        out.say(f"{target_name} fails the save, {roll.total} against DC {dc}.")

    try:
        await sheet.set_condition(client, target_uuid, applied["condition"], True)
    except (KeyError, sheet.CatalogueNotReady):
        # Worth saying, not worth aborting a resolved attack over.
        out.say(f"(couldn't record {label.lower()} on the sheet)")
        return
    out.say(f"{target_name} is now {label.lower()}.")


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


SKILL_LABEL = {
    "str": "Strength", "dex": "Dexterity", "con": "Constitution",
    "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma",
}


def _verdict(total: int, dc: int | None) -> str:
    """The clause that closes a roll, with or without a DC to beat."""
    if dc is None:
        return "."
    return f" against DC {dc} -- {'success' if total >= dc else 'failure'}."


async def _do_save(client, actor_uuid: str, intent: Intent, as_player: str | None) -> Outcome:
    name = _display_name(client, actor_uuid, intent.actor)
    ability = intent.ability or "dex"
    result, bonus = await sheet.roll_save(
        client, actor_uuid, ability, bias=intent.bias, as_player=as_player or name
    )
    label = SKILL_LABEL.get(ability, ability.upper())
    how = "" if intent.bias == "normal" else f" with {intent.bias}"
    return Outcome(
        True,
        [
            f"{name} rolls a {label} save{how}: {result.total} "
            f"({sheet.signed(bonus)}){_verdict(result.total, intent.dc)}"
        ],
    )


async def _do_check(client, actor_uuid: str, intent: Intent, as_player: str | None) -> Outcome:
    name = _display_name(client, actor_uuid, intent.actor)
    skill = intent.skill or "str"
    result, bonus, ability = await sheet.roll_check(
        client, actor_uuid, skill, bias=intent.bias, as_player=as_player or name
    )
    label = SKILL_LABEL.get(skill, skill.title())
    how = "" if intent.bias == "normal" else f" with {intent.bias}"
    return Outcome(
        True,
        [
            f"{name} rolls {label} ({ability.upper()}){how}: "
            f"{result.total} ({sheet.signed(bonus)}){_verdict(result.total, intent.dc)}"
        ],
    )


# Which skill each side rolls. 5e lets the defender pick Acrobatics instead of
# Athletics; the ghost takes the better of the two rather than asking, because
# a prompt in the middle of a grapple is worse than a favourable reading.
CONTESTS = {
    "grapple": ("athletics", ("athletics", "acrobatics"), "grappled"),
    "shove": ("athletics", ("athletics", "acrobatics"), "prone"),
    # Same contest, the word people actually use for it.
    "topple": ("athletics", ("athletics", "acrobatics"), "prone"),
    "trip": ("athletics", ("athletics", "acrobatics"), "prone"),
    "disarm": ("athletics", ("athletics", "acrobatics"), None),
}


async def _do_contest(
    client, actor_uuid: str, target_uuid: str, intent: Intent, as_player: str | None
) -> Outcome:
    """Resolve a grapple, shove or disarm as opposed checks."""
    kind = intent.contest or "grapple"
    attacker_skill, defender_options, applies = CONTESTS[kind]

    actor_name = _display_name(client, actor_uuid, intent.actor)
    target_name = _display_name(client, target_uuid, intent.target)

    attack_roll, attack_bonus, _ = await sheet.roll_check(
        client, actor_uuid, attacker_skill, bias=intent.bias, as_player=as_player or actor_name
    )

    # The defender's better option, decided before rolling so only one die is
    # thrown -- rolling both and picking would be two rolls in the log for one
    # contest, which reads as a bug at the table.
    target_sheet = await sheet.read_sheet(client, target_uuid)
    best = max(defender_options, key=lambda s: sheet.skill_bonus(target_sheet, s)[0])
    defend_roll, defend_bonus, _ = await sheet.roll_check(
        client, target_uuid, best, as_player=target_name
    )

    out = Outcome(True, [
        f"{actor_name} tries to {kind} {target_name}: "
        f"{attack_roll.total} ({sheet.signed(attack_bonus)} {attacker_skill.title()}) "
        f"against {defend_roll.total} ({sheet.signed(defend_bonus)} {best.title()})."
    ])

    # Ties go to the defender: 5e resolves a tied contest as no change.
    if attack_roll.total <= defend_roll.total:
        return out.say(f"{target_name} holds firm.")

    if applies is None:
        return out.say(f"{target_name} is disarmed.")

    await sheet.set_condition(client, target_uuid, applies, True)
    return out.say(f"{target_name} is {applies}.")


async def _do_cast(
    client, actor_uuid: str, target_uuid: str | None, intent: Intent, as_player: str | None
) -> Outcome:
    """Cast a prepared levelled spell, spending a slot."""
    actor_name = _display_name(client, actor_uuid, intent.actor)
    caster = await sheet.read_sheet(client, actor_uuid)
    spell = sheet.find_prepared(caster, intent.spell or "")

    if spell is None:
        # "casts" was already a cantrip verb before levelled spells existed, so
        # fall back to the equipped cantrip rather than rejecting a phrasing
        # that used to work. Only when the name actually matches it: silently
        # firing a cantrip at somebody who asked for Magic Missile would be
        # worse than saying no.
        equipped = ((caster or {}).get("derived") or {}).get("cantrip") or {}
        spoken = (intent.spell or "").lower()
        label = str(equipped.get("name", "")).lower()
        if label and (label in spoken or spoken in label):
            if target_uuid is None:
                return Outcome(False, [f"{equipped.get('name')} needs a target."])
            return await _do_attack(
                client, actor_uuid, target_uuid, actor_name,
                _display_name(client, target_uuid, intent.target),
                Intent(Action.ATTACK, actor=intent.actor, target=intent.target,
                       kind=AttackKind.CANTRIP, bias=intent.bias, raw=intent.raw),
                as_player,
            )
        return Outcome(
            False,
            [
                f"{actor_name} has not prepared {intent.spell!r}. "
                f"Prepared: {_prepared_list(caster) or 'nothing'}."
            ],
        )

    ok, left = await sheet.spend_slot(client, actor_uuid, int(spell.get("level") or 1))
    if not ok:
        return Outcome(False, [f"{actor_name} has no level {spell.get('level')} slots left."])

    name = spell.get("name") or intent.spell
    out = Outcome(True, [f"{actor_name} casts {name} ({left} slot(s) left)."])
    await _draw_spell_effect(client, spell, target_uuid or actor_uuid)
    target_name = _display_name(client, target_uuid, intent.target) if target_uuid else None

    kind = spell.get("kind")

    if kind == "buff":
        bonus = spell.get("acBonus")
        subject = target_uuid or actor_uuid
        subject_name = target_name or actor_name
        if bonus:
            total = await sheet.set_ac_modifier(
                client, subject, int(bonus["value"]), name, bonus.get("rounds")
            )
            return out.say(f"{subject_name} is now AC {total}.")
        return out.say(f"{subject_name} is affected for {spell.get('duration') or 'the duration'}.")

    if kind == "heal":
        if target_uuid is None:
            return out.say(f"{name} needs a target.")
        roll = await client.roll_dice(spell["healing"], share_with="all", as_player=as_player or actor_name)
        before = ((await sheet.read_sheet(client, target_uuid)) or {}).get("hp", {}).get("current", 0)
        healed = await sheet.heal(client, target_uuid, roll.total)
        for line in await deathsaves.on_healed(client, target_uuid, target_name or "the target"):
            out.say(line)
        restored = healed["current"] - max(0, before)
        wasted = roll.total - restored
        tail = f" ({roll.total} rolled, {wasted} wasted)" if wasted > 0 else ""
        return out.say(f"{target_name} regains {restored} hit points, now on {healed['current']}{tail}.")

    if target_uuid is None:
        return out.say(f"{name} needs a target.")

    if kind == "save":
        # Area spells do not care whose side anybody is on, so check before the
        # slot is gone. Asking afterwards would be a report of a mistake rather
        # than a chance to avoid one.
        warning = await _friendly_fire_warning(client, actor_uuid, target_uuid, spell)
        if warning is not None:
            return out.say(warning)

        dc = spell.get("saveDc")
        ability = spell.get("save") or "dex"
        damage = await client.roll_dice(spell["damage"], share_with="all", as_player=as_player or actor_name)
        result, _ = await sheet.roll_save(client, target_uuid, ability, as_player=target_name)
        made = result.total >= int(dc or 0)
        amount = damage.total
        if made and spell.get("halfOnSave"):
            amount = damage.total // 2
        elif made:
            amount = 0
        out.say(
            f"{target_name} rolls {result.total} against DC {dc} {ability.upper()}: "
            f"{'saves' if made else 'fails'}."
        )
        return await _land(client, target_uuid, target_name, amount, out)

    if kind == "auto":
        damage = await client.roll_dice(spell["damage"], share_with="all", as_player=as_player or actor_name)
        out.say(f"{name} strikes automatically.")
        return await _land(client, target_uuid, target_name, damage.total, out)

    # An attack-roll spell.
    notation = spell.get(
        {"advantage": "attackAdvantage", "disadvantage": "attackDisadvantage"}.get(intent.bias, "attack")
    )
    to_hit = await client.roll_dice(notation, share_with="all", as_player=as_player or actor_name)
    armour_class = sheet.armour_class(await sheet.read_sheet(client, target_uuid))
    damage = await client.roll_dice(spell["damage"], share_with="all", as_player=as_player or actor_name)
    if armour_class is None:
        return out.say(f"{to_hit.total} to hit -- {target_name} has no AC on file, so call it at the table.")
    if to_hit.total < armour_class:
        return out.say(f"{to_hit.total} misses AC {armour_class}.")
    out.say(f"{to_hit.total} hits AC {armour_class}.")
    return await _land(client, target_uuid, target_name, damage.total, out)


async def _land(client, target_uuid: str, target_name: str | None, amount: int, out: Outcome) -> Outcome:
    """Apply damage and report, including anyone dropped to zero."""
    if amount <= 0:
        return out.say(f"{target_name} takes no damage.")
    after = await sheet.damage(client, target_uuid, amount)
    out.say(f"{target_name} takes {amount}, down to {after['current']}.")
    if after["current"] <= 0:
        for line in await deathsaves.on_dropped_to_zero(client, target_uuid, target_name or "it"):
            out.say(line)
    return out


def _prepared_list(caster: dict[str, Any] | None) -> str:
    spells = ((caster or {}).get("derived") or {}).get("spells") or []
    return ", ".join(str(s.get("name")) for s in spells)


async def _do_ac_modifier(client, target_uuid: str, intent: Intent) -> Outcome:
    """Add or clear a temporary change to armour class.

    The modifier is written onto the sheet rather than applied to `ac` directly
    so that it stays visible and removable: "AC 17" tells nobody why, whereas
    "+2 half cover" can be cleared when the creature steps out from behind the
    wall. `deriveSheet` in the mod folds the list back into `ac`, and the ghost
    reads the total through `sheet.armour_class`.
    """
    name = _display_name(client, target_uuid, intent.actor)
    data = await sheet.read_sheet(client, target_uuid)
    if data is None:
        return Outcome(False, [f"{name} has no sheet, so there is no armour class to change."])

    existing = list(data.get("acModifiers") or [])

    if intent.ac_delta is None:
        if not existing:
            return Outcome(True, [f"{name} has no temporary armour class changes."])
        data["acModifiers"] = []
        await _write_ac(client, target_uuid, data)
        dropped = ", ".join(m.get("source") or "unnamed" for m in existing)
        return Outcome(True, [f"Cleared {len(existing)} modifier(s) from {name}: {dropped}."])

    source = intent.ac_source or ("cover" if intent.ac_delta > 0 else "penalty")
    duration: dict[str, Any] = (
        {"kind": "rounds", "remaining": intent.ac_rounds}
        if intent.ac_rounds
        else {"kind": "manual"}
    )
    existing.append(
        {
            "id": str(uuid.uuid4()),
            "source": source,
            "value": intent.ac_delta,
            "duration": duration,
        }
    )
    data["acModifiers"] = existing
    total = await _write_ac(client, target_uuid, data)

    lasts = f" for {intent.ac_rounds} round(s)" if intent.ac_rounds else ""
    sign = "+" if intent.ac_delta > 0 else ""
    return Outcome(True, [f"{name} takes {sign}{intent.ac_delta} AC from {source}{lasts}, now AC {total}."])


async def _write_ac(client, shape: str, data: dict[str, Any]) -> int:
    """Persist modifiers and keep the flat `ac` in step.

    The mod recomputes `ac` from armour whenever the editor saves, but the editor
    may not be open -- so the ghost has to do the same sum itself or the token's
    AC tracker would keep showing the old number until someone clicked the tab.
    Only the modifier total is recomputed here; the armour and Dexterity part is
    taken from the breakdown the mod already wrote.
    """
    block = (data.get("derived") or {}).get("ac") or {}
    modifiers = sum(int(m.get("value") or 0) for m in data.get("acModifiers") or [])
    without_mods = int(block.get("total") or data.get("ac") or 10) - int(block.get("modifiers") or 0)
    total = without_mods + modifiers

    data["ac"] = total
    if block:
        block["modifiers"] = modifiers
        block["total"] = total

    await sheet.write_sheet(client, shape, data)
    return total


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
        # One measurement on the board at a time, and gone by the next turn.
        # These used to be drawn and never removed, so a session accumulated
        # every line anyone had ever measured.
        await ephemera.clear_kind(client, ephemera.RULER_NAME)
        drawn = await scene.draw_ruler(client, field, a.cell, b.cell, f"{feet} ft")
        ephemera.add(drawn, turns=1, label="", kind=ephemera.RULER_NAME)
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
            refusal = (
                f"{actor_name} has no line of sight to {target_name} — "
                f"{blockers} {_is_are(blockers)} in the way."
            )
            # A refusal is true and useless on its own. The same geometry that
            # says "no" also knows where "yes" is, so offer it.
            return await _offer_a_better_spot(
                client, field, actor_uuid, target_uuid, actor_name, target_name,
                intent, refusal, prefix,
            )

    target_sheet = await sheet.read_sheet(client, target_uuid)
    armour_class = sheet.armour_class(target_sheet)

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
