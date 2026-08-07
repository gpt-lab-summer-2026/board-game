"""JSON status endpoint + transcript push for the voice loop.

Runs a tiny stdlib-only HTTP server in a background thread so the process
listening to the mic can publish what it heard to whatever is displaying the
board. Turn-based status updates don't need websockets -- a client polls
/status for those.

Recognized commands are different: the point of going hands-free is that
nothing else prompts the browser to check in, so a poll interval directly
trades off against how long a player waits after speaking. broadcast_transcript
pushes over a websocket instead, on a second port, so a completed utterance
reaches the browser the moment it's transcribed. broadcast_status pushes over
the same socket, for the *live* pipeline state ("waiting for the wake word",
"recording now") -- without it, a player has no way to know when the system
is actually listening versus when it's their turn to speak but nothing has
noticed yet.

The same websocket carries traffic the other way too: the browser sends a
{"type": "current_player", "player": ...} message whenever whose turn it is
changes. play_game.py has no model of turn state of its own -- once "roll the
dice" and "move to X" are two separate utterances instead of one, only the
browser (which runs the actual turn logic) knows when a turn really ends, so
this is how it learns who to gate the mic to next. get_current_player() is
what play_game.py's main loop reads back.

This used to also serve static files straight out of the repo root, which was
a bad idea twice over: it put an index.html at the root that collided with
Vite's entry point (and got resolved the wrong way in a merge, leaving the
React app unable to mount), and since the server binds 0.0.0.0 it handed any
device on the LAN the whole repository -- .git/config, voice/*.py, the 2.3GB
model file. The React app is the UI now, so the static serving is gone and
this is a JSON API only.

Still unauthenticated: fine on a home network, not something to expose further.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import websockets
from websockets.sync.server import serve as ws_serve

log = logging.getLogger(__name__)


class UiServer:
    def __init__(self, port: int = 8765, ws_port: int = 8766):
        self._lock = threading.Lock()
        self._message = "Waiting for a player to speak..."
        self._event: dict | None = None
        self._current_player: str | None = None
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

        self._ws_clients: set = set()
        self._ws_lock = threading.Lock()
        self._wsd = ws_serve(self._handle_ws, "0.0.0.0", ws_port)
        self._ws_thread = threading.Thread(target=self._wsd.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ws_thread.start()
        log.info("Status server listening on http://0.0.0.0:%d/status", self._httpd.server_port)
        log.info("Transcript websocket listening on ws://0.0.0.0:%d", self._wsd.socket.getsockname()[1])

    def set_message(self, text: str, event: dict | None = None) -> None:
        """event is a generic structured signal (e.g. {"type": "square_landed",
        "square_type": "large_gem"}) for a frontend to react to beyond plain
        text -- this module makes no assumptions about how it's rendered."""
        with self._lock:
            self._message = text
            self._event = event

    def get_status(self) -> dict:
        with self._lock:
            return {"message": self._message, "event": self._event}

    def broadcast_transcript(self, player: str, text: str, phase: str = "playing",
                              event: str | None = None) -> None:
        """Push a just-transcribed command to every connected browser.

        phase/event let the browser tell setup-time voice traffic (enrolling a new
        player, or an already-enrolled voice speaking again to say "begin") apart
        from an ordinary in-game command -- see src/voice/transcript.ts."""
        self._broadcast({"kind": "transcript", "player": player, "text": text,
                          "phase": phase, "event": event})

    def broadcast_status(self, status: str, player: str | None = None) -> None:
        """Push a live pipeline status ("waiting for the wake word", "recording now",
        "transcribing...") so the UI can show the player when it's actually their
        moment to talk, not just the eventual result -- see src/voice/transcript.ts."""
        self._broadcast({"kind": "status", "status": status, "player": player})

    def _broadcast(self, payload: dict) -> None:
        """Fire-and-forget to every connected browser: a client that isn't listening
        right now (page not open yet, mid-reconnect) simply misses it, the same as
        if the player had spoken to an empty room."""
        encoded = json.dumps(payload)
        with self._ws_lock:
            clients = list(self._ws_clients)
        for client in clients:
            try:
                client.send(encoded)
            except websockets.exceptions.ConnectionClosed:
                pass  # _handle_ws's own finally block discards it from _ws_clients

    def get_current_player(self) -> str | None:
        """Whoever the browser last said is up -- see _handle_ws. None before the
        browser has sent anything, e.g. before a game has actually started."""
        with self._lock:
            return self._current_player

    def _handle_ws(self, client) -> None:
        with self._ws_lock:
            self._ws_clients.add(client)
        try:
            for raw in client:
                self._handle_ws_message(raw)
        except websockets.exceptions.ConnectionClosed:
            pass  # a closed tab/dropped connection is routine, not an error to log
        finally:
            with self._ws_lock:
                self._ws_clients.discard(client)

    def _handle_ws_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Ignoring malformed websocket message: %r", raw)
            return
        if msg.get("type") == "current_player":
            player = msg.get("player")
            with self._lock:
                self._current_player = player
            log.info("Browser reports current player: %s", player)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._wsd.shutdown()


def _build_handler(server: UiServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # route stdlib's request logging through ours
            log.debug(fmt, *args)

        def do_GET(self):
            # Split off any query string: a polling client cache-busting with
            # /status?t=123 was previously falling through to a 404.
            if urlsplit(self.path).path != "/status":
                self.send_error(404)
                return
            body = json.dumps(server.get_status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # The board UI is served by Vite on another port, so it needs this.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

    return Handler
