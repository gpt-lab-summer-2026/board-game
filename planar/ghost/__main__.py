"""Run the ghost: connect to PlanarAlly, then serve the command console.

    server/.venv/bin/python -m ghost

The password is read from --password-file (default
~/.config/planarally-ghost/password) or the GHOST_PASSWORD environment
variable. It lives outside /tmp on purpose: /tmp is cleared on reboot, which
already ate one copy.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path

from . import narrate
from .client import GhostClient, GhostConfig
from .console import Console

DEFAULT_PASSWORD_FILE = Path.home() / ".config/planarally-ghost/password"


PLACEHOLDERS = {"the-password", "your-password", "password", "changeme", "<password>"}


def read_password(path: Path) -> str:
    env = os.environ.get("GHOST_PASSWORD")
    value = env.strip() if env else (path.read_text().strip() if path.is_file() else "")

    if not value:
        raise SystemExit(
            f"No ghost password. Put it in {path} (chmod 600) or set GHOST_PASSWORD."
        )
    # Copying an example verbatim is an easy mistake and otherwise surfaces as a
    # bare 401, which looks like a server problem rather than a typo.
    if value in PLACEHOLDERS:
        raise SystemExit(
            f"{path} still contains the placeholder {value!r}. Write the real "
            "password there, or run: server/.venv/bin/python -m ghost.reset_password"
        )
    return value


async def run(args: argparse.Namespace) -> None:
    cfg = GhostConfig(
        base_url=args.url,
        username=args.user,
        password=read_password(Path(args.password_file)),
        room_creator=args.room_creator,
        room_name=args.room,
        dry_run=args.dry_run,
    )
    client = GhostClient(cfg)
    await client.connect()
    await client.load_board()
    logging.info("board: %s", client.state.summary())
    logging.info("characters: %s", ", ".join(sorted(client.state.characters)) or "none")

    narrator = None if args.no_speech else narrate.try_build(voice=args.voice)
    console = Console(client, host=args.host, port=args.port, narrator=narrator)
    await console.start()

    # Wait for a signal rather than polling; the work happens in socket
    # callbacks and aiohttp handlers on this same loop.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    await console.stop()
    await client.close()


def main() -> None:
    p = argparse.ArgumentParser(description="PlanarAlly ghost player")
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--user", default="ghost")
    p.add_argument("--room-creator", default="sampo")
    p.add_argument("--room", default="sanpo")
    p.add_argument("--password-file", default=str(DEFAULT_PASSWORD_FILE))
    p.add_argument("--host", default="127.0.0.1", help="console bind address")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and plan, but emit nothing to the game",
    )
    p.add_argument("--no-speech", action="store_true", help="skip Kokoro narration")
    p.add_argument("--voice", default="af_heart")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
