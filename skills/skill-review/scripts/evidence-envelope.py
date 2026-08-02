#!/usr/bin/env python3
"""Validate and atomically update local agent-created skill evidence."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
DESTINATIONS = {"instruction", "factual_memory", "skill", "support_file", "discard"}
CREATORS = {"skill-review", "skill-create", "memory-curator"}
EVIDENCE_KINDS = {
    "successful-procedure",
    "failure-recovery",
    "owner-correction",
    "independent-recurrence",
}
INDEPENDENCE = {"verified", "unverified"}
EVALUATION_STATES = {
    "not_evaluated",
    "pending",
    "pass",
    "regression",
    "inconclusive",
    "waived",
}
WAIVER_CLASSES = {"documentation-only", "reference-only", "deterministic-helper"}
VERIFICATIONS = {"current-source", "deterministic-check", "session-evidence", "owner-policy"}
TASK_KEY_RE = re.compile(r"^(?:task|platform):[A-Za-z0-9._:-]{8,}$")


class EnvelopeError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EnvelopeError(f"{field} must be a non-empty ISO timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvelopeError(f"{field} must be an ISO timestamp") from exc
    return value


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnvelopeError(f"{field} must be non-empty text")
    return value


def validate_envelope(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise EnvelopeError("envelope must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise EnvelopeError(f"schema_version must be {SCHEMA_VERSION}")
    require_text(data.get("skill"), "skill")
    if data.get("created_by") not in CREATORS:
        raise EnvelopeError("created_by is invalid")
    require_text(data.get("source_session_id"), "source_session_id")
    require_text(data.get("source_mode"), "source_mode")
    require_text(data.get("review_prompt_version"), "review_prompt_version")
    parse_timestamp(data.get("created_at"), "created_at")

    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise EnvelopeError("evidence must be a non-empty list")
    task_keys: set[str] = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise EnvelopeError(f"evidence[{index}] must be an object")
        task_key = require_text(item.get("task_key"), f"evidence[{index}].task_key")
        if not TASK_KEY_RE.fullmatch(task_key):
            raise EnvelopeError(f"evidence[{index}].task_key is invalid")
        if task_key in task_keys:
            raise EnvelopeError(f"duplicate task_key: {task_key}")
        task_keys.add(task_key)
        require_text(item.get("session_id"), f"evidence[{index}].session_id")
        parse_timestamp(item.get("observed_at"), f"evidence[{index}].observed_at")
        if item.get("independence") not in INDEPENDENCE:
            raise EnvelopeError(f"evidence[{index}].independence is invalid")
        if item.get("evidence_kind") not in EVIDENCE_KINDS:
            raise EnvelopeError(f"evidence[{index}].evidence_kind is invalid")
        require_text(item.get("summary"), f"evidence[{index}].summary")

    if data["source_session_id"] != evidence[0]["session_id"]:
        raise EnvelopeError("source_session_id must mirror the first evidence session_id")

    routing = data.get("routing")
    if not isinstance(routing, dict) or routing.get("destination") not in DESTINATIONS:
        raise EnvelopeError("routing.destination is invalid")
    require_text(routing.get("reason"), "routing.reason")

    claims = data.get("claims")
    if not isinstance(claims, list):
        raise EnvelopeError("claims must be a list")
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise EnvelopeError(f"claims[{index}] must be an object")
        require_text(claim.get("claim"), f"claims[{index}].claim")
        if claim.get("verification") not in VERIFICATIONS:
            raise EnvelopeError(f"claims[{index}].verification is invalid")
        parse_timestamp(claim.get("last_verified_at"), f"claims[{index}].last_verified_at")

    evaluation = data.get("evaluation")
    if not isinstance(evaluation, dict) or evaluation.get("status") not in EVALUATION_STATES:
        raise EnvelopeError("evaluation.status is invalid")
    if evaluation["status"] in {"pass", "regression", "inconclusive"}:
        parse_timestamp(evaluation.get("evaluated_at"), "evaluation.evaluated_at")
        require_text(evaluation.get("candidate_id"), "evaluation.candidate_id")
        require_text(evaluation.get("run_id"), "evaluation.run_id")
        require_text(evaluation.get("receipt_sha256"), "evaluation.receipt_sha256")
        require_text(evaluation.get("case_manifest_sha256"), "evaluation.case_manifest_sha256")
        require_text(evaluation.get("model"), "evaluation.model")
        require_text(evaluation.get("source_case"), "evaluation.source_case")
        require_text(evaluation.get("sibling_case"), "evaluation.sibling_case")
    if evaluation["status"] == "waived":
        parse_timestamp(evaluation.get("evaluated_at"), "evaluation.evaluated_at")
        require_text(evaluation.get("candidate_id"), "evaluation.candidate_id")
        require_text(evaluation.get("receipt_sha256"), "evaluation.receipt_sha256")
        if evaluation.get("waiver_class") not in WAIVER_CLASSES:
            raise EnvelopeError("evaluation.waiver_class is invalid")
        require_text(evaluation.get("waiver_reason"), "evaluation.waiver_reason")
    return data


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise EnvelopeError(f"cannot read valid JSON from {path}: {exc}") from exc


def legacy_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    if "schema_version" in data and data["schema_version"] != 1:
        return data
    session_id = require_text(data.get("source_session_id"), "source_session_id")
    created_at = parse_timestamp(data.get("created_at"), "created_at")
    migrated = dict(data)
    migrated.update(
        {
            "schema_version": SCHEMA_VERSION,
            "created_by": data.get("created_by", "skill-review"),
            "source_session_id": session_id,
            "source_mode": data.get("source_mode", "legacy"),
            "review_prompt_version": data.get("review_prompt_version", "skill-review-1"),
            "evidence": [
                {
                    "task_key": f"task:{uuid.uuid4()}",
                    "session_id": session_id,
                    "observed_at": created_at,
                    "independence": "unverified",
                    "evidence_kind": "successful-procedure",
                    "summary": "Legacy provenance migrated without inferred task independence",
                }
            ],
            "routing": {
                "destination": "skill",
                "reason": "Legacy agent-created skill provenance",
            },
            "claims": data.get("claims", []),
            "evaluation": data.get(
                "evaluation",
                {
                    "status": "not_evaluated",
                    "evaluated_at": None,
                    "candidate_id": None,
                    "model": None,
                    "source_case": None,
                    "sibling_case": None,
                    "waiver_class": None,
                    "waiver_reason": None,
                },
            ),
        }
    )
    return migrated


def atomic_write(path: Path, data: dict[str, Any], directory_fd: int | None = None) -> None:
    own_lock = directory_fd is None
    if own_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
    assert directory_fd is not None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
            os.fsync(directory_fd)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    finally:
        if own_lock:
            os.close(directory_fd)


def make_evaluation() -> dict[str, Any]:
    return {
        "status": "not_evaluated",
        "evaluated_at": None,
        "candidate_id": None,
        "model": None,
        "source_case": None,
        "sibling_case": None,
        "waiver_class": None,
        "waiver_reason": None,
    }


def upsert(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file)
    timestamp = args.observed_at or now_iso()
    item = {
        "task_key": args.task_key,
        "session_id": args.session_id,
        "observed_at": timestamp,
        "independence": args.independence,
        "evidence_kind": args.evidence_kind,
        "summary": args.summary,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        if path.exists():
            data = legacy_to_v2(load_json(path))
            if data.get("skill") != args.skill:
                raise EnvelopeError("existing envelope skill does not match requested skill")
            if not any(entry.get("task_key") == args.task_key for entry in data.get("evidence", [])):
                data.setdefault("evidence", []).append(item)
            data["routing"] = {"destination": args.destination, "reason": args.reason}
            data.setdefault("claims", [])
            data.setdefault("evaluation", make_evaluation())
            data.setdefault("review_prompt_version", args.prompt_version)
            data.setdefault("source_mode", args.source_mode)
            data.setdefault("created_by", args.created_by)
            data["schema_version"] = SCHEMA_VERSION
            data["source_session_id"] = data["evidence"][0]["session_id"]
        else:
            data = {
                "schema_version": SCHEMA_VERSION,
                "skill": args.skill,
                "created_by": args.created_by,
                "source_session_id": args.session_id,
                "source_mode": args.source_mode,
                "review_prompt_version": args.prompt_version,
                "created_at": timestamp,
                "evidence": [item],
                "routing": {"destination": args.destination, "reason": args.reason},
                "claims": [],
                "evaluation": make_evaluation(),
            }
        validate_envelope(data)
        atomic_write(path, data, directory_fd)
        return data
    finally:
        os.close(directory_fd)


def set_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file)
    receipt = load_json(Path(args.receipt))
    receipt_bytes = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    if Path(args.receipt).name != f"{receipt_sha}.json":
        raise EnvelopeError("evaluation receipt path is not content-addressed")
    status = receipt.get("status")
    if status not in EVALUATION_STATES - {"not_evaluated", "pending"}:
        raise EnvelopeError("evaluation receipt status is invalid")
    if receipt.get("kind") == "evaluation":
        evaluation = {
            "status": status,
            "evaluated_at": receipt.get("evaluated_at"),
            "candidate_id": receipt.get("candidate_id"),
            "run_id": receipt.get("run_id"),
            "receipt_sha256": receipt_sha,
            "case_manifest_sha256": receipt.get("case_manifest_sha256"),
            "model": receipt.get("runtime", {}).get("model"),
            "source_case": receipt.get("source_case_id"),
            "sibling_case": receipt.get("sibling_case_id"),
            "waiver_class": None,
            "waiver_reason": None,
        }
    elif receipt.get("kind") == "waiver":
        evaluation = {
            "status": status,
            "evaluated_at": receipt.get("evaluated_at"),
            "candidate_id": receipt.get("candidate_id"),
            "run_id": None,
            "receipt_sha256": receipt_sha,
            "case_manifest_sha256": None,
            "model": None,
            "source_case": None,
            "sibling_case": None,
            "waiver_class": receipt.get("waiver_class"),
            "waiver_reason": receipt.get("waiver_reason"),
        }
    else:
        raise EnvelopeError("evaluation receipt kind is invalid")
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        data = legacy_to_v2(load_json(path))
        data["evaluation"] = evaluation
        validate_envelope(data)
        atomic_write(path, data, directory_fd)
        return data
    finally:
        os.close(directory_fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("file")

    upsert_parser = subparsers.add_parser("upsert")
    upsert_parser.add_argument("file")
    upsert_parser.add_argument("--skill", required=True)
    upsert_parser.add_argument("--created-by", choices=sorted(CREATORS), default="skill-review")
    upsert_parser.add_argument("--session-id", required=True)
    upsert_parser.add_argument("--source-mode", required=True)
    upsert_parser.add_argument("--prompt-version", default="skill-review-2")
    upsert_parser.add_argument("--task-key", required=True)
    upsert_parser.add_argument("--independence", choices=sorted(INDEPENDENCE), required=True)
    upsert_parser.add_argument("--evidence-kind", choices=sorted(EVIDENCE_KINDS), required=True)
    upsert_parser.add_argument("--summary", required=True)
    upsert_parser.add_argument("--destination", choices=sorted(DESTINATIONS), required=True)
    upsert_parser.add_argument("--reason", required=True)
    upsert_parser.add_argument("--observed-at")
    evaluation_parser = subparsers.add_parser("set-evaluation")
    evaluation_parser.add_argument("file")
    evaluation_parser.add_argument("receipt")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate":
            data = validate_envelope(legacy_to_v2(load_json(Path(args.file))))
        elif args.command == "upsert":
            data = upsert(args)
        else:
            data = set_evaluation(args)
        verified = {
            entry["task_key"]
            for entry in data["evidence"]
            if entry["independence"] == "verified"
        }
        print(
            json.dumps(
                {
                    "schema_version": data["schema_version"],
                    "skill": data["skill"],
                    "evidence_count": len(data["evidence"]),
                    "verified_task_count": len(verified),
                }
            )
        )
        return 0
    except EnvelopeError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
