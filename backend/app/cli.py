"""Command-line helpers used by the installer.

    python -m app.cli create-admin [--username admin]
    python -m app.cli reset-password <username>
"""

import argparse
import secrets
import sys

from sqlalchemy import select

from .db import get_db
from .models import User
from .security import hash_password


def _password() -> str:
    return secrets.token_urlsafe(12)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lpr-importer")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="create the first admin account if none exists")
    create.add_argument("--username", default="admin")
    reset = sub.add_parser("reset-password", help="set a new random password for a local account")
    reset.add_argument("username")
    args = parser.parse_args(argv)

    db = next(get_db())
    if args.command == "create-admin":
        if db.scalar(select(User).where(User.role == "admin")):
            print("An admin account already exists; nothing to do.")
            return 0
        password = _password()
        db.add(User(username=args.username, display_name="Administrator", role="admin", password_hash=hash_password(password)))
        db.commit()
        print(f"Admin account created.\n  username: {args.username}\n  password: {password}")
        return 0

    user = db.scalar(select(User).where(User.username == args.username))
    if user is None or user.auth_source != "local":
        print("No local account with that username.", file=sys.stderr)
        return 1
    password = _password()
    user.password_hash = hash_password(password)
    db.commit()
    print(f"New password for {user.username}: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
