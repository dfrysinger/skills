#!/usr/bin/env python3
"""SQLite-backed compare-and-swap writer lease."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path


def lock_path() -> Path:
    state = Path(os.environ.get("SKILLS_STATE_DIR", Path.home() / ".copilot/skill-state"))
    return Path(os.environ.get("SKILLS_LOCK_DIR", state / "daemon.lock"))


def now() -> int:
    return int(os.environ.get("SKILLS_NOW_EPOCH", time.time()))


def stale_secs() -> int:
    return int(os.environ.get("SKILLS_LOCK_STALE_SECS", 7200))


def process_identity(pid: int) -> str:
    result = subprocess.run(
        ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    return " ".join(result.stdout.split())


def process_matches(pid: int | None, identity: str | None) -> bool:
    if not pid or not identity:
        return False
    return process_identity(pid) == identity


def migrate_legacy_directory(path: Path) -> bool:
    """Return False while a live/young legacy lock still blocks migration."""
    if not path.is_dir():
        return True
    renewed = int(path.stat().st_mtime)
    for field in ("renewed", "started", "start"):
        stamp = path / field
        if not stamp.exists():
            continue
        try:
            renewed = int(stamp.read_text().strip())
            break
        except (OSError, ValueError):
            continue
    pid_path = path / "pid"
    try:
        pid = int(pid_path.read_text().strip()) if pid_path.exists() else None
    except (OSError, ValueError):
        pid = None
    identity_path = path / "process_identity"
    try:
        identity = identity_path.read_text().strip() if identity_path.exists() else None
    except OSError:
        identity = None
    if pid is not None and identity and process_matches(pid, identity):
        print(f"legacy lock held by live pid={pid}", file=sys.stderr)
        return False
    if pid is not None and not identity:
        try:
            os.kill(pid, 0)
            if now() - renewed < stale_secs():
                print(f"young legacy lock may be held by live pid={pid}", file=sys.stderr)
                return False
        except OSError:
            pass
    age = now() - renewed
    if age < stale_secs():
        print(
            f"legacy/partial lock age {age}s is below {stale_secs()}s; refusing to reclaim",
            file=sys.stderr,
        )
        return False
    archived = path.with_name(f"{path.name}.legacy-{now()}")
    suffix = 0
    while archived.exists():
        suffix += 1
        archived = path.with_name(f"{path.name}.legacy-{now()}-{suffix}")
    path.rename(archived)
    print(f"archived stale legacy lock at {archived}", file=sys.stderr)
    return True


def connect() -> sqlite3.Connection:
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not migrate_legacy_directory(path):
        raise BlockingIOError
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS writer_lock (
          singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
          token TEXT NOT NULL,
          mode TEXT NOT NULL,
          owner TEXT NOT NULL,
          started INTEGER NOT NULL,
          renewed INTEGER NOT NULL,
          pid INTEGER,
          process_identity TEXT
        )
        """
    )
    return connection


def blocked(row: sqlite3.Row, current: int) -> bool:
    age = current - int(row["renewed"])
    if row["mode"] == "process" and process_matches(row["pid"], row["process_identity"]):
        print(f"lock held by live process pid={row['pid']} owner={row['owner']}", file=sys.stderr)
        return True
    if age < stale_secs():
        print(
            f"lock owner is not provably live but lease age {age}s is below {stale_secs()}s",
            file=sys.stderr,
        )
        return True
    return False


def acquire(args: argparse.Namespace) -> int:
    if args.mode not in {"process", "session"}:
        return 2
    if args.mode == "process" and (not args.pid or not args.process_identity):
        return 2
    token = str(uuid.uuid4())
    current = now()
    try:
        con = connect()
    except BlockingIOError:
        return 1
    except sqlite3.DatabaseError as error:
        print(f"lock database invalid: {error}", file=sys.stderr)
        return 2
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM writer_lock WHERE singleton=1").fetchone()
        if row is not None and blocked(row, current):
            con.rollback()
            return 1
        con.execute("DELETE FROM writer_lock WHERE singleton=1")
        con.execute(
            """
            INSERT INTO writer_lock
              (singleton, token, mode, owner, started, renewed, pid, process_identity)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token,
                args.mode,
                args.owner,
                current,
                current,
                args.pid if args.mode == "process" else None,
                args.process_identity if args.mode == "process" else None,
            ),
        )
        con.commit()
    finally:
        con.close()
    print(token)
    return 0


def validate_owner(row: sqlite3.Row | None, args: argparse.Namespace) -> bool:
    if row is None or row["token"] != args.token:
        return False
    if row["mode"] == "session":
        return now() - int(row["renewed"]) < stale_secs()
    return (
        args.pid == row["pid"]
        and args.process_identity == row["process_identity"]
        and process_matches(row["pid"], row["process_identity"])
    )


def assert_or_renew(args: argparse.Namespace, renew: bool) -> int:
    try:
        con = connect()
    except (BlockingIOError, sqlite3.DatabaseError):
        return 1
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM writer_lock WHERE singleton=1").fetchone()
        if not validate_owner(row, args):
            con.rollback()
            return 1
        if renew:
            con.execute(
                "UPDATE writer_lock SET renewed=? WHERE singleton=1 AND token=?",
                (now(), args.token),
            )
        con.commit()
        return 0
    finally:
        con.close()


def release(args: argparse.Namespace) -> int:
    try:
        con = connect()
    except (BlockingIOError, sqlite3.DatabaseError):
        return 1
    try:
        con.execute("BEGIN IMMEDIATE")
        cursor = con.execute(
            "DELETE FROM writer_lock WHERE singleton=1 AND token=?",
            (args.token,),
        )
        con.commit()
        return 0 if cursor.rowcount == 1 else 1
    finally:
        con.close()


def seed(args: argparse.Namespace) -> int:
    path = lock_path()
    if path.is_dir():
        raise SystemExit("seed refuses to replace a lock directory")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM writer_lock")
        con.execute(
            """
            INSERT INTO writer_lock
              (singleton, token, mode, owner, started, renewed, pid, process_identity)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.token,
                args.mode,
                args.owner,
                args.started,
                args.renewed,
                args.pid,
                args.process_identity,
            ),
        )
        con.commit()
    finally:
        con.close()
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    acquire_parser = sub.add_parser("acquire")
    acquire_parser.add_argument("--mode", required=True)
    acquire_parser.add_argument("--owner", required=True)
    acquire_parser.add_argument("--pid", type=int)
    acquire_parser.add_argument("--process-identity")
    acquire_parser.set_defaults(func=acquire)

    for name, func in (("assert", lambda a: assert_or_renew(a, False)), ("renew", lambda a: assert_or_renew(a, True))):
        command = sub.add_parser(name)
        command.add_argument("token")
        command.add_argument("--pid", type=int)
        command.add_argument("--process-identity")
        command.set_defaults(func=func)

    release_parser = sub.add_parser("release")
    release_parser.add_argument("token")
    release_parser.set_defaults(func=release)

    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("--token", default="seed-token")
    seed_parser.add_argument("--mode", choices=("process", "session"), required=True)
    seed_parser.add_argument("--owner", default="test-owner")
    seed_parser.add_argument("--started", type=int, required=True)
    seed_parser.add_argument("--renewed", type=int, required=True)
    seed_parser.add_argument("--pid", type=int)
    seed_parser.add_argument("--process-identity")
    seed_parser.set_defaults(func=seed)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    raise SystemExit(args.func(args))
