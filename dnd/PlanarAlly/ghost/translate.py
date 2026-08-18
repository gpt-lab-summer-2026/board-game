"""Turning what somebody said into a command the ghost understands.

Until now this lived only in the voice loop, so the in-game console accepted
exact command syntax and nothing else -- you could say "back the elf off to the
southwest" into a microphone but not type it into the panel on the board. This
puts the same translation behind the console, which means one prompt, one guard,
and one place where a hallucinated command gets stopped.

The order is deliberate. An exact command never reaches the cluster at all: it
parses locally in microseconds, and paying a two-second round trip to be told
what we already knew would make the fast path the slow one.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import aiohttp

from . import nlguard, worldstate
from .client import GhostClient
from .commands import HELP_TEXT

log = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3.6:latest"
CMD_PREFIX = "CMD:"
ASK_PREFIX = "ASK:"

_CMD_TAG = re.compile(rf"^\s*{CMD_PREFIX}\s*", re.I)
_ASK_TAG = re.compile(rf"^\s*{ASK_PREFIX}\s*", re.I)

# The voice loop keeps its configuration in a .env beside itself. Reading it
# here rather than duplicating the setting means changing the cluster address in
# one place still changes it everywhere.
VOICE_ENV = Path(__file__).resolve().parents[2] / "python/.env"


def cluster_url() -> str | None:
    """Where the model lives, from the environment or the voice loop's .env."""
    direct = os.getenv("GHOST_CLUSTER_URL") or os.getenv("cluster_url")
    if direct:
        return direct.strip()
    try:
        for line in VOICE_ENV.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "cluster_url":
                return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def build_prompt(board: str, characters: list[str], active: str | None) -> str:
    """The system prompt: the contract, the grammar, and the facts."""
    turn_rule = (
        f"\n- It is {active}'s turn. Unless the player names somebody else explicitly,"
        f" {active} is the one acting. An action by anyone else will be refused,"
        f" so ask rather than guessing."
        if active
        else ""
    )
    return f"""You are a command translator for a tabletop D&D game running on PlanarAlly.
A player will describe what they want to do, in their own words. Rewrite what
they said into exactly one line, and output nothing else: no explanation, no
markdown, no quotation marks.

Every line you output must start with one of these two tags:

{CMD_PREFIX} <command>   a command from the list below, ready to execute
{ASK_PREFIX} <question>   one short question back to the player

Valid command shapes:
{HELP_TEXT}

THE BOARD RIGHT NOW
{board or "(unavailable -- say so rather than guessing)"}

Rules:
- Use the exact character names in the table. Never invent, translate or
  nickname them.
- The table above is the only source of distances, hit points, line of sight
  and sides. Never estimate any of them and never state a number that is not
  in it.
- Name the acting character and, for anything with a target, the target. Do not
  fill in a missing name from the table however obvious it looks: a wrong target
  executes silently. Missing name means ask.{turn_rule}
- A bare "attack" needs a kind. Take it from what the character is armed with in
  the table.
- If the player is answering a yes/no question, output {CMD_PREFIX} yes or {CMD_PREFIX} no.

Ask instead of commanding when several characters match, when the pair is marked
"(no line of sight)" and the action needs sight, or when nothing in the command
list fits. Do not ask about anything the table already answers.

Examples:
Player: "get the elf away from the hamster, off to the southwest"
You: {CMD_PREFIX} elf moves away from hamster to southwest

Player: "have the ranger shoot the orc"
You: {CMD_PREFIX} ranger ranged attack on orc

Player: "shoot it"
You: {ASK_PREFIX} Which character is shooting, and at what?

Current characters: {", ".join(characters)}."""


async def translate(
    client: GhostClient, said: str, *, model: str = DEFAULT_MODEL, timeout: float = 120
) -> dict[str, Any]:
    """Ask the cluster for a command. Returns {channel, payload, raw}.

    `channel` is "cmd", "ask" or "untagged". An untagged reply is never promoted
    to a command: a line that arrived without the tag is a line the model wrote
    without following the contract, and executing it is how a stray sentence
    reaches the board.
    """
    url = cluster_url()
    if not url:
        return {"channel": "error", "payload": "No cluster configured.", "raw": ""}

    state = await worldstate.snapshot(client)
    prompt = build_prompt(
        worldstate.render(state), sorted(client.state.characters), state.get("turn_of")
    )

    body = {
        "model": model,
        "stream": False,
        "think": False,
        # Low but not zero: the questions read better with a little slack, and
        # the commands are pinned down by the grammar anyway.
        "options": {"num_ctx": 32768, "temperature": 0.2},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": said},
        ],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    return {"channel": "error", "payload": f"Cluster said {resp.status}.", "raw": text}
                payload = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - the board must survive a dead cluster
        log.warning("cluster unreachable: %s", exc)
        return {"channel": "error", "payload": f"Cluster unreachable: {exc}", "raw": ""}

    reply = str((payload.get("message") or {}).get("content") or "").strip()
    if _ASK_TAG.match(reply):
        return {"channel": "ask", "payload": _ASK_TAG.sub("", reply).strip(), "raw": reply}
    if _CMD_TAG.match(reply):
        return {"channel": "cmd", "payload": _CMD_TAG.sub("", reply).strip(), "raw": reply}
    return {"channel": "untagged", "payload": reply, "raw": reply}


def vet_names(command: str, said: str, characters: list[str]) -> str | None:
    """A reason to refuse this command, or None. See nlguard."""
    ok, why = nlguard.check(command, said, characters)
    return None if ok else why
