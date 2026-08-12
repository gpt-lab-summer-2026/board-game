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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--file", default=str(DEFAULT_FILE))
    p.add_argument("--user", default=ALLOWED_USER)
    args = p.parse_args()

    if args.user != ALLOWED_USER:
        print(f"refusing: this only resets the {ALLOWED_USER!r} service account", file=sys.stderr)
        return 2

    try:
        import bcrypt
    except ImportError:
        print("bcrypt is missing; run this with server/.venv/bin/python", file=sys.stderr)
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
