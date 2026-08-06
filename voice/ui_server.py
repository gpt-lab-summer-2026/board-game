"""Local web UI: a text box showing the latest game-response message.

Runs a tiny stdlib-only HTTP server in a background thread, so the same
process listening to the mic can also drive a browser tab open on a screen
next to the board. No websockets -- the page just polls /status once a
second, which is plenty responsive for turn-based updates.

Binds to 0.0.0.0 so a phone/tablet on the same LAN can open it too. There's
no auth on this -- fine for a home network, not something to expose further.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent  # repo root: index.html, script.js, style.css
_CONTENT_TYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css"}


class UiServer:
    def __init__(self, port: int = 8765):
        self._lock = threading.Lock()
        self._message = "Waiting for a player to speak..."
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()
        log.info("UI server listening on http://0.0.0.0:%d", self._httpd.server_port)

    def set_message(self, text: str) -> None:
        with self._lock:
            self._message = text

    def get_message(self) -> str:
        with self._lock:
            return self._message

    def stop(self) -> None:
        self._httpd.shutdown()


def _build_handler(server: UiServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # route stdlib's request logging through ours
            log.debug(fmt, *args)

        def do_GET(self):
            if self.path == "/status":
                body = json.dumps({"message": server.get_message()}).encode()
                self._send(200, "application/json", body)
                return

            requested = (STATIC_DIR / (self.path.lstrip("/") or "index.html")).resolve()
            if requested != STATIC_DIR and STATIC_DIR not in requested.parents:
                self.send_error(403)  # path escaped STATIC_DIR (e.g. "../../etc/passwd")
                return
            if not requested.is_file():
                self.send_error(404)
                return
            content_type = _CONTENT_TYPES.get(requested.suffix, "application/octet-stream")
            self._send(200, content_type, requested.read_bytes())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler
