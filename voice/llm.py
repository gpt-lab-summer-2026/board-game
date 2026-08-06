"""Gemma3 intent parsing via a locally-launched llama-server.

Gemma3's only job here is turning a (noisy, English-transcribed) voice
command into a structured action -- it never adjudicates game rules itself.
Every field of that structured output is grammar-constrained (a bounded enum
or ranged integer), so a hallucinated city/mode is structurally impossible,
not just discouraged by prompting. voice/game_engine.py is what actually
applies the result.

Measured latency on this Pi: ~25-31s per call, cold or "warm" -- prompt
caching (cache_prompt, on by default) barely helps in practice here: repeat
calls sharing an identical system prompt still show cache_n close to 0 in
the response `timings`, rather than reusing the ~300-token shared prefix.
This is well above this project's original ~8-15s estimate (which assumed
caching would work as it does for plain single-turn completions); flagging
as a real, measured finding rather than chasing the cause further here --
gemma's chat template merges the system message into the first user turn
(see common/chat.cpp), which is one plausible reason the "prefix" isn't
staying prefix-stable across requests with different trailing user content.
Whoever picks this back up: worth trying the raw /completion endpoint with
a hand-built prompt string instead of /v1/chat/completions, to see if
bypassing the chat-template layer restores expected cache behavior.
"""
from __future__ import annotations

import collections
import json
import logging
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .board import BoardGraph
from .config import LlmConfig

log = logging.getLogger(__name__)


class LlamaServerError(RuntimeError):
    """Any failure launching/health-checking/running the llama-server subprocess."""


class LlamaServerProcess:
    def __init__(self, cfg: LlmConfig):
        self.cfg = cfg
        self.base_url = f"http://{cfg.host}:{cfg.port}"
        self._proc: subprocess.Popen | None = None
        self._stderr_tail: collections.deque = collections.deque(maxlen=60)
        self._pump_thread: threading.Thread | None = None

    def start(self) -> None:
        self._preflight()
        argv = [
            self.cfg.server_binary,
            "-m", self.cfg.model_path,
            "--host", self.cfg.host,
            "--port", str(self.cfg.port),
            "-c", str(self.cfg.ctx_size),
            "-t", str(self.cfg.threads),
            "-tb", str(self.cfg.threads),
            "-np", "1",           # single slot: one turn at a time
            "--no-webui",
            "-fa", "auto",
        ]
        log.info("Launching llama-server: %s", " ".join(argv))
        self._proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, text=True)
        self._pump_thread = threading.Thread(target=self._pump_stderr, daemon=True)
        self._pump_thread.start()
        self._wait_until_ready()

    def stop(self, grace_s: float = 5.0) -> None:
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            log.warning("llama-server didn't exit within %.0fs, killing", grace_s)
            self._proc.kill()
            self._proc.wait()
        self._proc = None

    def __enter__(self) -> "LlamaServerProcess":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _preflight(self) -> None:
        binary = Path(self.cfg.server_binary)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise LlamaServerError(f"llama-server binary not found or not executable: {binary}")
        model = Path(self.cfg.model_path)
        if not model.is_file():
            raise LlamaServerError(f"model file not found: {model}")
        # fail fast on a port collision instead of waiting for llama-server's own bind error.
        # SO_REUSEADDR matters here: without it, this throwaway check can false-positive
        # against a leftover TIME_WAIT socket from the PREVIOUS server's own connections
        # (e.g. our own health-check requests) even after that server has fully exited.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((self.cfg.host, self.cfg.port))
            except OSError as e:
                raise LlamaServerError(
                    f"port {self.cfg.port} on {self.cfg.host} is already in use "
                    f"(another llama-server instance running?): {e}"
                ) from e

    def _pump_stderr(self) -> None:
        for line in self._proc.stderr:
            line = line.rstrip()
            self._stderr_tail.append(line)
            log.debug("[llama-server] %s", line)

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.cfg.startup_timeout_s
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise LlamaServerError(
                    f"llama-server exited early (code {self._proc.returncode}) during "
                    f"startup. Last output:\n" + "\n".join(self._stderr_tail)
                )
            try:
                r = requests.get(f"{self.base_url}/health", timeout=1.0)
                if r.status_code == 200:
                    log.info("llama-server ready at %s", self.base_url)
                    return
            except requests.RequestException:
                pass  # not listening yet
            time.sleep(0.5)
        self.stop()
        raise LlamaServerError(
            f"llama-server did not become healthy within {self.cfg.startup_timeout_s:.0f}s. "
            f"Last output:\n" + "\n".join(self._stderr_tail)
        )


@dataclass
class ParsedIntent:
    action: str                        # "move" | "other" | "unclear"
    destination: str | None = None
    mode: str | None = None
    dice_value: int | None = None
    other_intent: str | None = None
    unclear_reason: str | None = None  # populated whenever action == "unclear"


SYSTEM_PROMPT = """\
You are the intent-recognition layer for a Tampere-themed board game. A \
player has just spoken a voice command; a speech-to-text system already \
transcribed it, imperfectly, into English text. Your only job is to map \
that transcript onto ONE of the allowed structured actions below. You must \
pick only from the candidates given to you in each request -- never invent \
a city, mode, or value that isn't listed.

Players often state their move and their dice roll together in one \
sentence (e.g. "dice roll is four, I'm flying to Vapriikki"). When they do, \
report destination, mode, AND dice_value together under action "move" -- \
never split this into a separate dice declaration.

If the transcript could reasonably mean more than one of the listed \
candidates, or doesn't match any of them, or the dice/mode/destination \
don't describe one consistent move, set action to "unclear" and pick the \
single unclear_reason that best explains why, instead of guessing.

Reply with ONLY the JSON object described by the schema. No other text.
"""

UNCLEAR_REASONS = ["", "ambiguous_destination", "ambiguous_mode", "invalid_dice_value",
                    "inconsistent_move", "no_match", "not_this_turn"]


def build_schema(cities: list[str], modes: list[str], actions: list[str],
                  other_intents: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(actions)},
            "destination": {"type": "string", "enum": [*cities, ""]},
            "mode": {"type": "string", "enum": [*modes, ""]},
            "dice_value": {"type": "integer", "minimum": 0, "maximum": 6},  # 0 == n/a
            "other_intent": {"type": "string", "enum": [*other_intents, ""]},
            "unclear_reason": {"type": "string", "enum": UNCLEAR_REASONS},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


def build_user_block(transcript: str, current_city: str, hint_destinations: list[str],
                      modes: list[str], other_intents: list[str],
                      prior_attempt: str | None = None) -> str:
    lines = [
        f"Current city: {current_city}",
        f"Cities likely reachable this turn (a hint, not the full valid list -- "
        f"any real city name is an acceptable answer): "
        f"{', '.join(hint_destinations) or '(none)'}",
        f"Available transport modes: {', '.join(modes)}",
    ]
    if other_intents:
        lines.append(f"Other recognized intents this turn: {', '.join(other_intents)}")
    if prior_attempt:
        lines.append(f"(Follow-up: the player was already asked to clarify after "
                      f"saying {prior_attempt!r}.)")
    lines.append(f'Player said: "{transcript}"')
    return "\n".join(lines)


class IntentParser:
    def __init__(self, cfg: LlmConfig, base_url: str, board: BoardGraph):
        self.cfg = cfg
        self.base_url = base_url
        self.board = board
        self._session = requests.Session()

    def parse(self, transcript: str, current_city: str, hint_destinations: list[str],
              modes: tuple[str, ...] = ("walking", "water", "flying"),
              actions: tuple[str, ...] = ("move", "other", "unclear"),
              other_intents: tuple[str, ...] = (),
              prior_attempt: str | None = None) -> ParsedIntent:
        cities = self.board.cities
        schema = build_schema(cities, list(modes), list(actions), list(other_intents))
        body = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_block(
                    transcript, current_city, hint_destinations, list(modes),
                    list(other_intents), prior_attempt)},
            ],
            "temperature": self.cfg.temperature,
            "top_p": self.cfg.top_p,
            "max_tokens": self.cfg.max_tokens,
            "response_format": {"type": "json_object", "schema": schema},
        }
        try:
            resp = self._session.post(f"{self.base_url}/v1/chat/completions",
                                       json=body, timeout=self.cfg.request_timeout_s)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as e:
            log.warning("llama-server call failed: %s", e)
            return ParsedIntent(action="unclear", unclear_reason="llm_request_failed")

        return self._validate(content, current_city, cities, list(modes), list(actions))

    def _validate(self, content: str, current_city: str, cities: list[str],
                   modes: list[str], actions: list[str]) -> ParsedIntent:
        """Re-checks the model's output against the same candidate lists (plus,
        for "move", actual board reachability) after parsing -- even though the
        grammar should already guarantee structural validity. The one gap a
        grammar doesn't close is truncation at max_tokens before reaching an
        accepting state; this is the actual reliability guarantee, the grammar
        just makes it the common case. Doing the reachability check HERE (not
        just in GameEngine.apply_move()) means an inconsistent dice/mode/
        destination combo comes back as a normal, gracefully-handled "unclear"
        result -- not an exception the caller has to catch as control flow."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            log.warning("llm returned unparsable JSON: %r", content)
            return ParsedIntent(action="unclear", unclear_reason="no_match")

        action = data.get("action")
        if action not in actions:
            return ParsedIntent(action="unclear", unclear_reason="no_match")

        if action == "move":
            dest, mode, dice = data.get("destination"), data.get("mode"), data.get("dice_value")
            if dest not in cities:
                return ParsedIntent(action="unclear", unclear_reason="ambiguous_destination")
            if mode not in modes:
                return ParsedIntent(action="unclear", unclear_reason="ambiguous_mode")
            if not isinstance(dice, int) or not (1 <= dice <= 6):
                return ParsedIntent(action="unclear", unclear_reason="invalid_dice_value")
            if dest not in self.board.reachable_within(current_city, mode, dice):
                return ParsedIntent(action="unclear", unclear_reason="inconsistent_move")
            return ParsedIntent(action="move", destination=dest, mode=mode, dice_value=dice)

        if action == "other":
            return ParsedIntent(action="other", other_intent=data.get("other_intent") or None)

        reason = data.get("unclear_reason")
        return ParsedIntent(action="unclear",
                             unclear_reason=reason if reason in UNCLEAR_REASONS else "no_match")


CLARIFY_TEXT = {
    "ambiguous_destination": "I didn't catch which spot you meant. Could you say the name again?",
    "ambiguous_mode": "Did you mean to walk, take the water route, or fly there?",
    "invalid_dice_value": "I didn't catch the dice number -- what did you roll, and where to?",
    "inconsistent_move": "That destination doesn't match the dice roll and route you gave. Could you repeat your move?",
    "no_match": "Sorry, I didn't understand that. Could you repeat your move?",
    "not_this_turn": "That's not something you can do right now. What's your move?",
    "llm_request_failed": "Sorry, something went wrong on my end. Could you repeat your move?",
}
