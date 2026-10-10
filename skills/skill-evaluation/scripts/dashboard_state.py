"""Validated create-once state for the local skill-evaluation dashboard."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from skill_eval import load_corpus, read_json


CAMPAIGN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CAMPAIGN_FIELDS = {
    "schema_version",
    "campaign_id",
    "corpus_root",
    "corpus_device",
    "corpus_inode",
    "corpus_name",
    "target_skills",
}


def validate_campaign_id(value: str) -> str:
    if not isinstance(value, str) or not CAMPAIGN_ID_RE.fullmatch(value):
        raise ValueError("campaign ID must be 32 lowercase hexadecimal characters")
    return value


def ensure_state_root(path: Path) -> Path:
    path = path.expanduser()
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError(f"dashboard state root must be a directory: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    campaigns = path / "campaigns"
    if campaigns.exists() and (campaigns.is_symlink() or not campaigns.is_dir()):
        raise ValueError(f"dashboard campaigns path must be a directory: {campaigns}")
    campaigns.mkdir(mode=0o700, exist_ok=True)
    os.chmod(campaigns, 0o700)
    return path.resolve()


def regular_json(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def target_skills(corpus_root: Path) -> list[str]:
    corpus = load_corpus(corpus_root)
    result = set()
    for case_id in corpus["cases"]:
        if not isinstance(case_id, str):
            raise ValueError("corpus case IDs must be strings")
        definition = regular_json(
            corpus_root / "cases" / case_id / "case.json",
            f"case {case_id}",
        )
        if definition.get("case_id") != case_id:
            raise ValueError(f"case identity mismatch: {case_id}")
        skill = definition.get("target_skill")
        if not isinstance(skill, str) or not skill:
            raise ValueError(f"case target skill is unavailable: {case_id}")
        result.add(skill)
    return sorted(result)


def corpus_identity(corpus_root: Path, campaign_id: str) -> dict:
    corpus_root = corpus_root.expanduser().resolve()
    if corpus_root.is_symlink() or not corpus_root.is_dir():
        raise ValueError(f"corpus root must be a directory: {corpus_root}")
    stat = corpus_root.stat()
    return {
        "schema_version": 1,
        "campaign_id": validate_campaign_id(campaign_id),
        "corpus_root": str(corpus_root),
        "corpus_device": stat.st_dev,
        "corpus_inode": stat.st_ino,
        "corpus_name": corpus_root.name,
        "target_skills": target_skills(corpus_root),
    }


def validate_registration(value: dict) -> dict:
    if set(value) != CAMPAIGN_FIELDS or value.get("schema_version") != 1:
        raise ValueError("unsupported dashboard campaign registration")
    validate_campaign_id(value.get("campaign_id"))
    if (
        not isinstance(value.get("corpus_root"), str)
        or not Path(value["corpus_root"]).is_absolute()
        or type(value.get("corpus_device")) is not int
        or type(value.get("corpus_inode")) is not int
        or not isinstance(value.get("corpus_name"), str)
        or not isinstance(value.get("target_skills"), list)
        or not all(isinstance(item, str) and item for item in value["target_skills"])
        or value["target_skills"] != sorted(set(value["target_skills"]))
    ):
        raise ValueError("malformed dashboard campaign registration")
    return value


def write_exclusive(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def campaign_registration(state_root: Path, campaign_id: str) -> dict:
    root = ensure_state_root(state_root)
    path = root / "campaigns" / f"{validate_campaign_id(campaign_id)}.json"
    value = validate_registration(regular_json(path, "campaign registration"))
    if value["campaign_id"] != campaign_id:
        raise ValueError("campaign filename and identity disagree")
    return value


def create_campaign(state_root: Path, corpus_root: Path) -> dict:
    state_root = ensure_state_root(state_root)
    corpus_root = corpus_root.expanduser().resolve()
    load_corpus(corpus_root)
    local_root = corpus_root / ".skill-evaluation-ui"
    if local_root.exists() and (local_root.is_symlink() or not local_root.is_dir()):
        raise ValueError(f"dashboard corpus state must be a directory: {local_root}")
    local_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(local_root, 0o700)
    local_path = local_root / "campaign.json"
    if local_path.exists():
        existing = validate_registration(regular_json(local_path, "corpus campaign"))
        expected = corpus_identity(corpus_root, existing["campaign_id"])
        if existing != expected:
            raise ValueError("create-once campaign identity changed")
        registration = existing
    else:
        registration = corpus_identity(corpus_root, uuid.uuid4().hex)
        try:
            write_exclusive(local_path, registration)
        except FileExistsError:
            registration = validate_registration(
                regular_json(local_path, "corpus campaign")
            )
            if registration != corpus_identity(
                corpus_root,
                registration["campaign_id"],
            ):
                raise ValueError("create-once campaign identity changed")

    global_path = (
        state_root / "campaigns" / f"{registration['campaign_id']}.json"
    )
    if global_path.exists():
        if validate_registration(
            regular_json(global_path, "campaign registration")
        ) != registration:
            raise ValueError("global campaign registration changed")
    else:
        try:
            write_exclusive(global_path, registration)
        except FileExistsError:
            if validate_registration(
                regular_json(global_path, "campaign registration")
            ) != registration:
                raise ValueError("global campaign registration changed")
    return registration
