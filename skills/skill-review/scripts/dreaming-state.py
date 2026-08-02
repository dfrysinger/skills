#!/usr/bin/env python3
"""Crash-recoverable cadence and per-run records for the dreaming daemon."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

WEEK_SECONDS = 7 * 24 * 60 * 60


def state_root() -> Path:
    base = Path(os.environ.get("SKILLS_STATE_DIR", Path.home() / ".copilot/skill-state"))
    return Path(os.environ.get("DREAMING_STATE_DIR", base / "dreaming"))


def now_epoch() -> int:
    return int(os.environ.get("DREAMING_NOW_EPOCH", time.time()))


def iso(epoch: int | None = None) -> str:
    return datetime.fromtimestamp(epoch or now_epoch(), timezone.utc).isoformat()


def bucket(epoch: int | None = None) -> int:
    return (epoch or now_epoch()) // WEEK_SECONDS


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return {} if default is None else default
    with path.open() as handle:
        return json.load(handle)


def read_json_tolerant(path: Path, default: dict) -> dict:
    try:
        value = read_json(path, default)
        return value if isinstance(value, dict) else default
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def parse_legacy_timestamp(path: Path, keys: tuple[str, ...]) -> int | None:
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    for key in keys:
        value = data.get(key)
        if not value:
            continue
        try:
            return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
    return None


def cadence_path() -> Path:
    return state_root() / "cadence.json"


def run_path(run_id: str) -> Path:
    return state_root() / "runs" / f"{run_id}.json"


def ledger_path() -> Path:
    return state_root() / "ledger.jsonl"


def ensure_seed(args: argparse.Namespace) -> None:
    path = cadence_path()
    if path.exists():
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError("cadence state must be a JSON object")
        print(json.dumps(value))
        return
    candidates = [
        parse_legacy_timestamp(Path(args.curator), ("last_run_at",)),
        parse_legacy_timestamp(Path(args.memory), ("last_run_at",)),
    ]
    latest = max((value for value in candidates if value is not None), default=now_epoch())
    value = {
        "last_success_bucket": bucket(latest),
        "last_success_at": iso(latest),
        "committing_run_id": None,
        "seeded_at": iso(),
    }
    atomic_json(path, value)
    print(json.dumps(value))


def seed(args: argparse.Namespace) -> None:
    value = {
        "last_success_bucket": args.bucket,
        "last_success_at": iso(args.epoch),
        "committing_run_id": args.run_id,
        "seeded_at": iso(),
    }
    atomic_json(cadence_path(), value)


def due(args: argparse.Namespace) -> None:
    try:
        cadence = read_json(cadence_path(), {"last_success_bucket": -1})
        if not isinstance(cadence, dict):
            raise TypeError("cadence state must be a JSON object")
        last_bucket = int(cadence.get("last_success_bucket", -1))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"cadence state invalid: {error}", file=sys.stderr)
        raise SystemExit(3)
    raise SystemExit(0 if bucket(args.epoch) > last_bucket else 1)


def parse_passes(path: str | None) -> list[dict]:
    if not path:
        return []
    passes = []
    with open(path) as handle:
        for raw in handle:
            fields = raw.rstrip("\n").split("\t")
            fields += [""] * (6 - len(fields))
            passes.append(
                {
                    "name": fields[0],
                    "status": fields[1],
                    "started_at": fields[2] or None,
                    "ended_at": fields[3] or None,
                    "log_path": fields[4] or None,
                    "reason": fields[5] or None,
                }
            )
    return passes


def append_ledger(record: dict) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        for line in handle:
            try:
                if json.loads(line).get("run_id") == record["run_id"]:
                    return
            except json.JSONDecodeError:
                continue
        handle.seek(0, os.SEEK_END)
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record(args: argparse.Namespace) -> None:
    if args.cadence_neutral and args.status != "ok":
        raise SystemExit("--cadence-neutral requires --status ok")
    cadence = read_json_tolerant(
        cadence_path(),
        {"last_success_bucket": -1, "last_success_at": None},
    )
    value = {
        "run_id": args.run_id,
        "started_at": args.started_at,
        "ended_at": args.ended_at or iso(),
        "status": args.status,
        "reason": args.reason,
        "passes": parse_passes(args.passes_file),
        "bucket_at_start": bucket(args.start_epoch),
        "last_success_bucket_before": cadence.get("last_success_bucket", -1),
        "last_success_at_before": cadence.get("last_success_at"),
        "last_success_bucket_after": cadence.get("last_success_bucket", -1),
        "last_success_at_after": cadence.get("last_success_at"),
        "cadence_committed": args.status != "ok" or args.cadence_neutral,
    }
    atomic_json(run_path(args.run_id), value)
    if value["cadence_committed"]:
        append_ledger(value)


def commit_success(args: argparse.Namespace) -> None:
    path = run_path(args.run_id)
    value = read_json(path)
    if value.get("status") != "ok":
        raise SystemExit(f"run {args.run_id} is not a successful pending result")
    cadence = {
        "last_success_bucket": int(value.get("bucket_at_start", bucket(args.completed_epoch))),
        "last_success_at": iso(args.completed_epoch),
        "committing_run_id": args.run_id,
        "seeded_at": read_json(cadence_path()).get("seeded_at"),
    }
    atomic_json(cadence_path(), cadence)
    value["cadence_committed"] = True
    value["last_success_bucket_after"] = cadence["last_success_bucket"]
    value["last_success_at_after"] = cadence["last_success_at"]
    atomic_json(path, value)
    append_ledger(value)


def repair(_: argparse.Namespace) -> None:
    root = state_root()
    cadence = read_json(cadence_path())
    committed_id = cadence.get("committing_run_id")
    for path in sorted((root / "runs").glob("*.json")) if (root / "runs").exists() else []:
        value = read_json(path)
        if value.get("run_id") == committed_id and value.get("status") == "ok":
            if not value.get("cadence_committed"):
                value["cadence_committed"] = True
                value["last_success_bucket_after"] = cadence.get("last_success_bucket")
                value["last_success_at_after"] = cadence.get("last_success_at")
                atomic_json(path, value)
        if value.get("cadence_committed"):
            append_ledger(value)


def latest(_: argparse.Namespace) -> None:
    paths = sorted((state_root() / "runs").glob("*.json"))
    if not paths:
        raise SystemExit(1)
    print(json.dumps(read_json(paths[-1])))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    ensure = sub.add_parser("ensure-seed")
    ensure.add_argument("--curator", required=True)
    ensure.add_argument("--memory", required=True)
    ensure.set_defaults(func=ensure_seed)

    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("--bucket", type=int, required=True)
    seed_parser.add_argument("--epoch", type=int, default=now_epoch())
    seed_parser.add_argument("--run-id")
    seed_parser.set_defaults(func=seed)

    due_parser = sub.add_parser("due")
    due_parser.add_argument("--epoch", type=int, default=now_epoch())
    due_parser.set_defaults(func=due)

    record_parser = sub.add_parser("record")
    record_parser.add_argument("--run-id", required=True)
    record_parser.add_argument("--status", choices=("ok", "skipped", "aborted"), required=True)
    record_parser.add_argument("--reason", required=True)
    record_parser.add_argument("--started-at", required=True)
    record_parser.add_argument("--ended-at")
    record_parser.add_argument("--start-epoch", type=int, required=True)
    record_parser.add_argument("--passes-file")
    record_parser.add_argument("--cadence-neutral", action="store_true")
    record_parser.set_defaults(func=record)

    commit = sub.add_parser("commit-success")
    commit.add_argument("--run-id", required=True)
    commit.add_argument("--completed-epoch", type=int, default=now_epoch())
    commit.set_defaults(func=commit_success)

    sub.add_parser("repair").set_defaults(func=repair)
    sub.add_parser("latest").set_defaults(func=latest)
    sub.add_parser("bucket").set_defaults(func=lambda _: print(bucket()))
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    arguments.func(arguments)
