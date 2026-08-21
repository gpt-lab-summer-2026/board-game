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

import logging

from . import turns
from .client import GAME_NAMESPACE, GhostClient

log = logging.getLogger(__name__)

FORWARD = 1
BACKWARD = -1


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
