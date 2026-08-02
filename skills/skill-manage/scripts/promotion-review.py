#!/usr/bin/env python3
"""Create and verify a complete public-safety inventory for skill promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

MANIFEST = ".promotion-reviewed.json"
EXCLUDED = {".agent-created", ".agent-created.json", MANIFEST}
PRIVATE_PATTERNS = {
    "explicit private sentinel": re.compile(r"\b(?:PRIVATE_SENTINEL|BEGIN PRIVATE|TASK-SPECIFIC PRIVATE)\b", re.I),
    "credential-shaped token": re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._-]{20,})"
    ),
    "private URL": re.compile(r"https?://[^\s/]*(?:\.internal|\.corp|localhost)(?:[/:][^\s]*)?", re.I),
    "conversation transcript": re.compile(r"(?m)^(?:User|Assistant|Human):\s+\S"),
}


class ReviewError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(skill_dir: Path) -> list[dict[str, Any]]:
    if not (skill_dir / "SKILL.md").is_file():
        raise ReviewError(f"missing SKILL.md in {skill_dir}")
    files: list[dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir).as_posix()
        if relative in EXCLUDED:
            continue
        if path.name in EXCLUDED:
            raise ReviewError(f"{relative}: reserved promotion sidecar must be at skill root")
        content = path.read_bytes()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            for label, pattern in PRIVATE_PATTERNS.items():
                if pattern.search(text):
                    raise ReviewError(f"{relative}: blocked {label}")
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "public_safe": True,
            }
        )
    return files


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def approve(skill_dir: Path, reviewers: list[str]) -> None:
    cleaned = [reviewer.strip() for reviewer in reviewers if reviewer.strip()]
    if len(set(cleaned)) < 2:
        raise ReviewError("two distinct independent reviewer identities are required")
    atomic_write(
        skill_dir / MANIFEST,
        {
            "schema_version": 1,
            "reviewers": cleaned,
            "files": inventory(skill_dir),
        },
    )


def verify(skill_dir: Path) -> None:
    manifest_path = skill_dir / MANIFEST
    try:
        manifest = json.load(manifest_path.open(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"missing or malformed {MANIFEST}: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise ReviewError("promotion review schema_version must be 1")
    reviewers = manifest.get("reviewers")
    if not isinstance(reviewers, list) or len(set(reviewers)) < 2:
        raise ReviewError("promotion review requires two distinct reviewers")
    current = inventory(skill_dir)
    if manifest.get("files") != current:
        raise ReviewError("promotion inventory is stale or incomplete")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("skill_dir")
    approve_parser.add_argument("--reviewer", action="append", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("skill_dir")
    args = parser.parse_args()
    try:
        skill_dir = Path(args.skill_dir).resolve()
        if args.command == "approve":
            approve(skill_dir, args.reviewer)
            print(skill_dir / MANIFEST)
        else:
            verify(skill_dir)
            print(f"promotion review valid: {skill_dir}")
        return 0
    except ReviewError as exc:
        print(f"REFUSED: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
