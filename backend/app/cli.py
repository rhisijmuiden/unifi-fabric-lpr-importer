"""Command-line helpers used by the installer.

    python -m app.cli create-admin [--username admin]
    python -m app.cli reset-password <username>
    python -m app.cli backup [--kind full|incremental]
    python -m app.cli restore [--protocol scp --host nas.local ...] [--file backup.lprbak ...]
"""

import argparse
import getpass
import secrets
import sys
from pathlib import Path

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
    run = sub.add_parser("backup", help="make a backup on every enabled backup location now")
    run.add_argument("--kind", choices=["full", "incremental"], default="full")
    restore = sub.add_parser("restore", help="restore a backup from a remote location or from files (asks for what is missing)")
    restore.add_argument("--protocol", choices=["ftp", "ftps", "scp"])
    restore.add_argument("--host")
    restore.add_argument("--port", type=int)
    restore.add_argument("--username")
    restore.add_argument("--auth", choices=["password", "key"], help="scp: password or this server's SSH key")
    restore.add_argument("--remote-path")
    restore.add_argument("--implicit-tls", action="store_true", help="ftps: implicit TLS (port 990)")
    restore.add_argument("--no-verify-tls", action="store_true", help="ftps: accept self-signed certificates")
    restore.add_argument("--name", help="backup to restore (default: ask, newest first)")
    restore.add_argument("--file", action="append", type=Path, help="local backup file; repeat for a full backup plus its incrementals")
    restore.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)

    db = next(get_db())
    if args.command == "backup":
        return _backup(db, args)
    if args.command == "restore":
        return _restore(db, args)
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


def _ask(prompt: str, default: str = "") -> str:
    value = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return value or default


def _print_job(job) -> int:
    for entry in job.log:
        print(("  ok  " if entry.get("ok") else "  !!  ") + entry["message"])
    print("Done." if job.status == "done" and not job.failed else "Failed.")
    return 0 if job.status == "done" and not job.failed else 1


def _backup(db, args) -> int:
    from .services import backup, jobs

    actor = jobs.Actor("system", "command line")
    job = jobs.start(db, "backup", actor, {"kind": args.kind}, lambda ctx: backup.run_backup(ctx, args.kind), inline=True)
    return _print_job(job)


def _restore(db, args) -> int:
    from .services import backup, jobs, remote

    conn = None
    if args.file:
        blobs = {f.name: f.read_bytes() for f in args.file}
        names = list(blobs)
        fetch = blobs.__getitem__
        source = "file"
    else:
        protocol = args.protocol or _ask("Protocol (ftp, ftps, scp)", "scp")
        if protocol not in remote.PROTOCOLS:
            print("Unknown protocol.", file=sys.stderr)
            return 1
        cfg = remote.TargetConfig(
            protocol=protocol,
            host=args.host or _ask("Server"),
            port=args.port or int(_ask("Port", str(990 if args.implicit_tls else remote.DEFAULT_PORTS[protocol]))),
            username=args.username or _ask("Username"),
            remote_path=args.remote_path or _ask("Folder on the server", "lpr-importer"),
            ftps_implicit=args.implicit_tls,
            verify_tls=not args.no_verify_tls,
        )
        if protocol == "scp":
            cfg.auth_method = args.auth or _ask("Sign in with password or key", "password")
        if cfg.auth_method == "key":
            cfg.private_key, public = backup.ssh_key(db)
            print(f"This server's SSH public key (add it to ~/.ssh/authorized_keys on {cfg.host}):\n  {public}")
        else:
            cfg.password = getpass.getpass("Password: ")
        try:
            conn = remote.connect(cfg)
            if conn.host_key:
                print(f"Host key of {cfg.host}: {conn.host_key}")
                if not args.yes and _ask("Is this the right server? (yes/no)", "no").lower() not in ("y", "yes", "j", "ja"):
                    return 1
            names = [f.name for f in conn.list()]
        except remote.RemoteError as exc:
            print(f"Could not connect: {exc}", file=sys.stderr)
            return 1
        fetch = conn.download
        source = f"{protocol}://{cfg.host}/{cfg.remote_path}"

    try:
        items = [i for i in backup.catalog([remote.RemoteFile(n) for n in names]) if i["restorable"]]
        if not items:
            print("No complete backups found.", file=sys.stderr)
            return 1
        name = args.name
        if not name:
            for i, item in enumerate(items[:30], 1):
                print(f"  {i:2}. {item['created_at'][:16].replace('T', ' ')} UTC  {item['kind']:<11}  {item['name']}")
            choice = _ask("Backup to restore", "1")
            name = items[int(choice) - 1]["name"] if choice.isdigit() and 0 < int(choice) <= len(items) else choice
        passphrase = getpass.getpass("Backup passphrase: ")
        if not args.yes:
            print("All data of this installation will be replaced by the backup.")
            if _ask("Type RESTORE to continue") != "RESTORE":
                return 1
        print("Restoring, this can take a while...")
        actor = jobs.Actor("system", "command line")
        job = jobs.start(
            db, "restore", actor, {"name": name, "location": source},
            lambda ctx: backup.run_restore(ctx, name, names, fetch, passphrase, source), inline=True,
        )
        return _print_job(job)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
