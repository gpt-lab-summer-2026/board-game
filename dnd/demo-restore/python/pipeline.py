"""The bits between the model and the board.

`main.py`, `speak.py` and `listen.py` are the source of truth for the voice loop
and are not touched by this module. What lives here is everything that has to
happen to a model's reply *before* it is allowed to move a token:

    reply  ->  route()      which channel did it answer on
           ->  guard.check() did it name someone the player never said
           ->  parse()       is it a command the ghost understands
           ->  narrate()     turn the ghost's result into a sentence

Each step is separately testable and none of them needs a microphone.
"""
from __future__ import annotations

import os
import sys

from config import ASK_PREFIX, CMD_PREFIX, CLUSTER_CHAT, SYSTEM_PROMPT_NARRATION
from ghost_client import getReq, post_to_cluster
import guard

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import ClarificationNeeded, ParseError, parse  # noqa: E402

NARRATION_MODEL = "qwen3.6:latest"


def route(reply: str) -> tuple[str, str]:
    """Split a model reply into (channel, payload).

    Channels are "cmd", "ask" and "untagged". An untagged reply is deliberately
    *not* treated as a command: executing a line that arrived without the tag is
    how a stray sentence reaches the board.
    """
    text = (reply or "").strip()
    if text.upper().startswith(ASK_PREFIX.upper()):
        return "ask", text[len(ASK_PREFIX):].strip()
    if text.upper().startswith(CMD_PREFIX.upper()):
        return "cmd", text[len(CMD_PREFIX):].strip()
    return "untagged", text


def vet(reply: str, said: str, characters: list[str] | None = None) -> tuple[str, str]:
    """Decide what to do with one model reply.

    Returns (action, payload) where action is:
      "post"  -- payload is a command that is safe to send to the ghost
      "say"   -- payload is something to read to the player and then wait
      "retry" -- payload is what to say before listening again

    The order matters. The name check runs *before* parsing, because a
    hallucinated name produces a perfectly well-formed command and parsing it
    would report success.
    """
    channel, payload = route(reply)

    if channel == "ask":
        return "say", payload
    if channel == "untagged":
        return "retry", "I didn't catch that, say it again?"

    ok, why = guard.check(payload, said, characters if characters is not None else getReq())
    if not ok:
        return "say", why

    try:
        parse(payload)
    except ClarificationNeeded as e:
        return "say", e.question
    except ParseError as e:
        return "retry", str(e)
    return "post", payload


def narrate(result_text: str, llm=None) -> str:
    """Turn the ghost's mechanical result into a sentence or two.

    Uses SYSTEM_PROMPT_NARRATION, which existed but was never reached -- both
    branches of the loop called the *command* translator for narration, so the
    narrator was being asked to emit a command line.

    Stateless on purpose: the mechanical result is the whole input. Handing it
    the conversation history invites it to narrate things that were discussed
    and never happened.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_NARRATION},
        {"role": "user", "content": result_text},
    ]

    if CLUSTER_CHAT:
        try:
            res = post_to_cluster(
                os.getenv("cluster_url"),
                {
                    "model": NARRATION_MODEL,
                    "stream": False,
                    "think": False,
                    "options": {"num_ctx": 4096, "temperature": 0.4},
                    "messages": messages,
                },
            )
            return res["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001 - narration is decoration, not the game
            print("narration failed: ", e)
            return result_text

    if llm is None:
        return result_text
    out = llm.create_chat_completion(messages=messages, max_tokens=80)
    return out["choices"][0]["message"]["content"].strip()


def lines_of(response: dict) -> str:
    """The ghost's answer as one string, for narration and for printing."""
    try:
        return " ".join(response["entries"][0]["lines"])
    except (KeyError, IndexError, TypeError):
        return ""
