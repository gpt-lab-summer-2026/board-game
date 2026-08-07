"""JSON status endpoint for the voice loop.

Runs a tiny stdlib-only HTTP server in a background thread so the process
listening to the mic can publish what it heard to whatever is displaying the
board. Turn-based updates don't need websockets -- a client polls /status.

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

log = logging.getLogger(__name__)


class UiServer:
    def __init__(self, port: int = 8765):
        self._lock = threading.Lock()
        self._message = "Waiting for a player to speak..."
        self._event: dict | None = None
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()
        log.info("Status server listening on http://0.0.0.0:%d/status", self._httpd.server_port)

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

    def stop(self) -> None:
        self._httpd.shutdown()


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
