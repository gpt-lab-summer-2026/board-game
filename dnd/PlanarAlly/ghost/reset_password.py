"""Reset the ghost service account's password.

    server/.venv/bin/python -m ghost.reset_password

Generates a fresh random password, writes it to
~/.config/planarally-ghost/password (0600), and updates the bcrypt hash in
PlanarAlly's database. Only ever touches the row named `ghost` -- the account
this tooling created for itself -- and refuses to run against any other user.

Deliberately a script you run rather than something the assistant does for you:
rewriting a password hash in someone's database is not a thing that should
happen as a side effect of a conversation.
"""
from __future__ import annotations

import argparse
import secrets
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "server/data/planar.sqlite"
DEFAULT_FILE = Path.home() / ".config/planarally-ghost/password"

# The service account. Anything else is someone's real login.
ALLOWED_USER = "ghost"


def _warn_if_run_as_a_file() -> None:
    """`python ghost/reset_password.py` half-works and then fails oddly.

    The script lives in a package and is meant to be run with `-m`. Run as a
    plain path it may pick up the wrong interpreter and will not resolve its
    sibling modules, so it is worth naming the correct invocation up front.
    """
    if __package__:
        return
    print(
        "Note: run this as a module, from the PlanarAlly directory:\n"
        "    server/.venv/bin/python -m ghost.reset_password\n",
        file=sys.stderr,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--file", default=str(DEFAULT_FILE))
    p.add_argument("--user", default=ALLOWED_USER)
    args = p.parse_args()
    _warn_if_run_as_a_file()

    if args.user != ALLOWED_USER:
        print(f"refusing: this only resets the {ALLOWED_USER!r} service account", file=sys.stderr)
        return 2

    try:
        import bcrypt
    except ImportError:
        # There are two virtualenvs in this tree and only the server's has
        # bcrypt, so "run it with the other python" needs to be the literal
        # command rather than a hint.
        print(
            "bcrypt is not installed in this interpreter.\n\n"
            "Run it from the PlanarAlly directory with the server's venv:\n"
            "    cd ~/board-game/dnd/PlanarAlly\n"
            "    server/.venv/bin/python -m ghost.reset_password\n",
            file=sys.stderr,
        )
        return 2

    db = Path(args.db)
    if not db.is_file():
        print(f"no database at {db}", file=sys.stderr)
        return 2

    password = secrets.token_urlsafe(16)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    con = sqlite3.connect(db)
    with con:
        rows = con.execute(
            "update user set password_hash = ? where name = ?", (hashed, args.user)
        ).rowcount
    con.close()

    if rows == 0:
        print(f"no user named {args.user!r} in {db}", file=sys.stderr)
        return 1

    dest = Path(args.file)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(password)
    dest.chmod(0o600)

    print(f"reset {args.user!r} and wrote the new password to {dest} (0600)")
    print("the password is not printed; the ghost reads it from that file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
