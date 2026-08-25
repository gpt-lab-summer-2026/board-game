"""Moving the initiative tracker by voice.

The one thing that stopped a table playing hands-off: someone still had to
click. Everything else the ghost can already resolve, but the turn only moved
when a human reached for the browser -- and with turn ownership enforced, that
meant every other character was locked out until they did.

Three protocol facts shape all of this, and each one is a way to ship something
that looks right and does nothing:

* `Initiative.Turn.Update` is re-broadcast with `skip_sid`, so the ghost never
  hears its own. Whatever the socket handler does on a human's turn change has
  to be done explicitly here too, hence the `on_turn_advanced` calls.
* the server's `update_initiative_turn` does `Initiative.get(location=...)` with
  no guard and indexes `json_data[turn]`, so on a location that has never had
  initiative it raises *inside the handler* and dies silently -- no error
  reaches the client. Every emit below is gated on a non-empty cached order.
* wrap-around is two emits, not one, mirroring the browser's `nextTurn`: the
  round is bumped first with `processEffects: false`, then the turn is set to 0
  with effects on, so a round boundary does not tick every effect twice.
"""
from __future__ import annotations

import asyncio
import logging

from . import dice, lore, sheet, turns
from .client import GAME_NAMESPACE, GhostClient

log = logging.getLogger(__name__)

FORWARD = 1
BACKWARD = -1
# InitiativeDirection.NULL -- neither forwards nor backwards, which is what a
# jump to a specific turn is. Using FORWARD here would be a lie the effect
# processor would act on if effects were ever enabled for these calls.
NULL = 0


def _name(client: GhostClient, uuid: str | None) -> str:
    if uuid is None:
        return "nobody"
    for name, u in client.state.characters.items():
        if u == uuid:
            return name
    return uuid[:8]


async def _emit_turn(client: GhostClient, turn: int, direction: int, effects: bool) -> None:
    await client.sio.emit(
        "Initiative.Turn.Update",
        {"turn": turn, "direction": direction, "processEffects": effects},
        namespace=GAME_NAMESPACE,
    )


async def _emit_round(client: GhostClient, round_: int, direction: int, effects: bool) -> None:
    await client.sio.emit(
        "Initiative.Round.Update",
        {"round": round_, "direction": direction, "processEffects": effects},
        namespace=GAME_NAMESPACE,
    )


async def advance(client: GhostClient, *, forward: bool = True) -> list[str]:
    """Move the turn on (or back), and report who is up.

    Returns the lines to narrate. An empty order returns a refusal rather than
    emitting, for the silent-death reason in the module docstring.
    """
    init = client.state.initiative
    if not init.order:
        return ["Nobody is in the initiative order yet."]

    count = len(init.order)
    direction = FORWARD if forward else BACKWARD
    wrapped = False

    if forward:
        if init.turn >= count - 1:
            wrapped = True
            init.round += 1
            await _emit_round(client, init.round, direction, effects=False)
            init.turn = 0
        else:
            init.turn += 1
    else:
        if init.turn == 0:
            wrapped = True
            init.round = max(1, init.round - 1)
            await _emit_round(client, init.round, direction, effects=False)
            init.turn = count - 1
        else:
            init.turn -= 1

    await _emit_turn(client, init.turn, direction, effects=True)

    active = init.current
    await turns.sync_to_turn(client, init.round, init.turn, active)

    # Only forwards. A step back is a correction, and neither `tick_durations`
    # nor `ephemera.tick` can un-tick -- running them would burn a round off
    # every active effect for the privilege of undoing a misclick.
    if forward:
        await client.on_turn_advanced()

    who = _name(client, active)
    # +1 to match what the turn bar shows. PA stores the round zero-indexed and
    # `TurnOrderBar.vue` renders `round + 1`, so narrating the raw counter would
    # announce a round one behind the number on screen.
    lines = [f"Round {init.round + 1}, {who}'s turn."] if wrapped else [f"{who}'s turn."]
    if not forward:
        lines.append("Durations were left alone; stepping back does not un-tick them.")
    return lines


async def whose_turn(client: GhostClient) -> list[str]:
    """Report the order without changing it."""
    init = client.state.initiative
    if not init.order:
        return ["Nobody is in the initiative order yet."]
    names = ", ".join(_name(client, u) for u in init.order)
    return [
        f"Round {init.round + 1}. It is {_name(client, init.current)}'s turn.",
        f"Order: {names}.",
    ]


# Sort order, matching the client's `InitiativeSort`: 0 Down (descending, the
# 5e default), 1 Up, 2 Manual.
SORT_DOWN = 0


async def roll(client: GhostClient) -> list[str]:
    """Roll initiative for everyone on the board and start combat.

    Rolled *locally* with `dice.roll` rather than `client.roll_dice`. The latter
    posts a shared dice toast per call, so seven tokens means seven toasts in
    everybody's log before the fight has begun; one summary line says the same
    thing. Individual rolls are still logged server-side, so a disputed result
    is recoverable.

    Emitted as `Initiative.Add` with the value inline. The obvious alternative --
    add, then `Initiative.Value.Set` -- is wrong twice over: the server runs
    handlers through `start_background_task`, so a burst from one socket is not
    order-guaranteed, and `set_initiative_value` indexes `json_data[turn]`
    unguarded on a table that is still empty.
    """
    names = sorted(client.state.characters)
    if not names:
        return ["There is nobody on the board to roll for."]

    rolled: list[tuple[int, int, str, str]] = []
    for name in names:
        uuid = client.state.characters[name]
        data = await sheet.read_sheet(client, uuid)
        modifier = sheet.ability_mod(data, "dex")
        result = dice.roll(f"1d20{'+' if modifier >= 0 else '-'}{abs(modifier)}")
        rolled.append((result.total, modifier, name, uuid))

    # Highest first; ties go to the better Dexterity, then alphabetically so the
    # same rolls always produce the same order. The server's sort is stable, so
    # the order emitted here is the order that survives `Sort.Set`.
    rolled.sort(key=lambda r: (-r[0], -r[1], r[2]))

    for total, _mod, _name, uuid in rolled:
        await client.sio.emit(
            "Initiative.Add",
            {
                "shape": uuid,
                "initiative": total,
                # Visible to players, unlike PlanarAlly's own default. This table
                # plays off one projector, and an order only the DM can see is an
                # order nobody at the table can see.
                "isVisible": True,
                "isGroup": False,
                "effects": [],
            },
            namespace=GAME_NAMESPACE,
        )

    # Only now: `set_initiative_sort` does an unguarded `Initiative.get` and
    # indexes `json_data[turn]`, so sending it before anything exists raises
    # inside the handler and dies silently, with no error reaching the client.
    await client.sio.emit("Initiative.Sort.Set", SORT_DOWN, namespace=GAME_NAMESPACE)
    await client.sio.emit("Initiative.Active.Set", True, namespace=GAME_NAMESPACE)

    # Sort.Set is the one initiative event the server echoes *without* skip_sid,
    # so it comes back as an `Initiative.Set` that overwrites the cache below.
    # Wait for it rather than race it.
    await asyncio.sleep(0.4)

    # And then undo what sorting did to the turn. `set_initiative_sort` calls
    # `get_turn_order(json_data, active_participant["shape"])` to keep whoever
    # was acting still acting across a re-sort -- correct for a mid-combat
    # reorder, wrong for a fresh roll, where it left the tracker pointing at
    # whoever happened to be up in the previous fight. Measured: turn 4 out of 7
    # when the summary had just announced the creature at index 0.
    await _emit_round(client, 0, NULL, effects=False)
    await _emit_turn(client, 0, NULL, effects=False)

    # A fresh combat: nobody has spent anything, whatever the old bank says.
    await turns.clear_spent(client)

    init = client.state.initiative
    init.order = [uuid for _t, _m, _n, uuid in rolled]
    init.turn = 0
    init.round = 0
    init.is_active = True
    await turns.sync_to_turn(client, init.round, init.turn, init.current)

    order = ", ".join(f"{name} {total}" for total, _m, name, _u in rolled)
    lines = [f"Initiative: {order}.", f"{rolled[0][2]} is up first."]

    # The prologue belongs here if it has not been heard: "before the first turn
    # launches" is exactly this moment, and it is the only trigger in the system
    # that means it unambiguously.
    told = await lore.opening(client)
    if told and not told[0].startswith("The story has already"):
        lines = told + lines
    return lines


async def clear(client: GhostClient) -> list[str]:
    """Null everyone's rolled value, keeping the order, round and turn.

    Narrower than it sounds, and the line below says so because the first
    version did not: `clear_initiatives` walks the entries setting
    `initiative = None` and saves. It does not drop effects, does not reorder,
    and does not touch the round or the turn. Use `end combat` to actually stop.
    """
    if not client.state.initiative.order:
        return ["There is no initiative to clear."]
    await client.sio.emit("Initiative.Clear", namespace=GAME_NAMESPACE)
    return [
        "Initiative values cleared. The order, the round and the turn are unchanged "
        "-- say 'roll initiative' to re-roll, or 'end combat' to stop."
    ]


async def end_combat(client: GhostClient) -> list[str]:
    """Wipe the order entirely and take the tracker off screen."""
    if not client.state.initiative.order:
        return ["Combat is not running."]
    await client.sio.emit("Initiative.Wipe", namespace=GAME_NAMESPACE)
    await client.sio.emit("Initiative.Active.Set", False, namespace=GAME_NAMESPACE)
    client.state.initiative.clear()
    await turns.sync_to_turn(client, 0, 0, None)
    return ["Combat over. The order is wiped."]


async def set_round(client: GhostClient, number: int) -> list[str]:
    """Put the round counter back without touching the order.

    Separate from `roll` because re-rolling to get a clean round number would
    also shuffle everyone, which is a much bigger thing to do by accident. The
    stored counter is zero-based and the bar renders `round + 1`, so "round 1"
    is 0 on the wire.
    """
    if not client.state.initiative.order:
        return ["There is no initiative to renumber."]
    stored = max(0, int(number) - 1)
    init = client.state.initiative
    await _emit_round(client, stored, NULL, effects=False)
    init.round = stored
    await turns.clear_spent(client)
    await turns.sync_to_turn(client, init.round, init.turn, init.current)
    return [f"Round {stored + 1}. It is {_name(client, init.current)}'s turn."]
