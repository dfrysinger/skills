"""Fail-closed aggregate holdout authority and receipt handling."""

from __future__ import annotations

import base64
import json
import os
import stat
from datetime import timedelta
from pathlib import Path

from dashboard_state import (
    ensure_state_root,
    instant,
    locked,
    parse_instant,
    regular_json,
    validate_safe_id,
    validate_sha256,
    write_exclusive,
)
from skill_eval import digest, json_fingerprint


AUTHORITY_FIELDS = {
    "schema_version",
    "authority_id",
    "public_key",
    "created_at",
}
COMMON_RECEIPT_FIELDS = {
    "schema_version",
    "receipt_id",
    "kind",
    "authority_id",
    "project_id",
    "holdout_set_id",
    "candidate_revision",
    "task_ids",
    "claim",
    "signature",
}
STARTED_FIELDS = COMMON_RECEIPT_FIELDS | {
    "started_at",
    "expires_at",
    "nonce",
}
TERMINAL_FIELDS = COMMON_RECEIPT_FIELDS | {
    "started_receipt_sha256",
    "completed_at",
    "infrastructure_state",
    "total_cases",
    "passed_cases",
    "failed_cases",
    "candidate_tokens",
    "judge_tokens",
    "credits",
    "accounting_complete",
    "qualified",
}
FORBIDDEN_DETAIL_FIELDS = {
    "case",
    "case_id",
    "case_ids",
    "cases",
    "prompt",
    "prompts",
    "criterion",
    "criteria",
    "output",
    "outputs",
    "per_case",
    "failure_details",
    "behavioral_failures",
    "private_path",
}
INFRASTRUCTURE_STATES = {"completed", "failed", "unavailable"}
MAX_RECEIPT_LIFETIME = timedelta(hours=24)


def _validate_path_component(value: object, label: str) -> str:
    validate_safe_id(value, label)
    if value in {".", ".."}:
        raise ValueError(f"{label} is invalid")
    return value


def _protected_directory(path: Path, *, create: bool) -> Path:
    existed = path.exists()
    if create and not existed:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    mode = path.lstat().st_mode
    if (
        path.is_symlink()
        or not stat.S_ISDIR(mode)
        or stat.S_IMODE(mode) & 0o077
    ):
        raise ValueError("holdout registry is not owner protected")
    return path


def _public_key(value: str):
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("holdout public key is invalid") from error
    if len(raw) != 32:
        raise ValueError("holdout public key is invalid")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as error:
        raise ValueError("Ed25519 verification is unavailable") from error
    return Ed25519PublicKey.from_public_bytes(raw)


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _unsigned(receipt: dict) -> dict:
    return {
        key: value for key, value in receipt.items()
        if key != "signature"
    }


def _validate_aggregate_shape(receipt: dict) -> None:
    pending = [receipt]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if set(value) & FORBIDDEN_DETAIL_FIELDS:
                raise ValueError("holdout receipt contains forbidden detail")
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def authority_root(state_root: Path, *, create: bool) -> Path:
    return _protected_directory(
        ensure_state_root(state_root) / "holdout-authorities",
        create=create,
    )


def create_authority(
    state_root: Path,
    authority_id: str,
    public_key: str,
) -> dict:
    _validate_path_component(authority_id, "holdout authority ID")
    _public_key(public_key)
    value = {
        "schema_version": 1,
        "authority_id": authority_id,
        "public_key": public_key,
        "created_at": instant(),
    }
    write_exclusive(
        authority_root(state_root, create=True) / f"{authority_id}.json",
        value,
    )
    return value


def load_authority(state_root: Path, authority_id: str) -> dict:
    _validate_path_component(authority_id, "holdout authority ID")
    path = authority_root(state_root, create=False) / f"{authority_id}.json"
    value = regular_json(path, "holdout authority")
    if set(value) != AUTHORITY_FIELDS or value.get("schema_version") != 1:
        raise ValueError("holdout authority is invalid")
    if value.get("authority_id") != authority_id:
        raise ValueError("holdout authority identity changed")
    _public_key(value.get("public_key"))
    parse_instant(value.get("created_at"))
    return value


def validate_receipt_shape(receipt: object) -> dict:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ValueError("holdout receipt is invalid")
    _validate_aggregate_shape(receipt)
    kind = receipt.get("kind")
    expected = STARTED_FIELDS if kind == "started" else (
        TERMINAL_FIELDS if kind == "terminal" else None
    )
    if expected is None or set(receipt) != expected:
        raise ValueError("holdout receipt fields are invalid")
    for field, label in (
        ("receipt_id", "holdout receipt ID"),
        ("authority_id", "holdout authority ID"),
        ("project_id", "project ID"),
        ("holdout_set_id", "holdout set ID"),
    ):
        _validate_path_component(receipt.get(field), label)
    validate_sha256(receipt.get("candidate_revision"), "candidate revision")
    task_ids = receipt.get("task_ids")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or task_ids != sorted(set(task_ids))
    ):
        raise ValueError("holdout task IDs are invalid")
    for task_id in task_ids:
        validate_safe_id(task_id, "task ID")
    if (
        not isinstance(receipt.get("claim"), str)
        or not receipt["claim"].strip()
        or len(receipt["claim"]) > 160
    ):
        raise ValueError("holdout claim is invalid")
    try:
        signature = base64.b64decode(receipt.get("signature"), validate=True)
    except (TypeError, ValueError) as error:
        raise ValueError("holdout signature is invalid") from error
    if len(signature) != 64:
        raise ValueError("holdout signature is invalid")
    if kind == "started":
        started = parse_instant(receipt.get("started_at"))
        expires = parse_instant(receipt.get("expires_at"))
        if expires <= started or expires - started > MAX_RECEIPT_LIFETIME:
            raise ValueError("holdout receipt lifetime is invalid")
        validate_safe_id(receipt.get("nonce"), "holdout nonce")
    else:
        validate_sha256(
            receipt.get("started_receipt_sha256"),
            "started receipt fingerprint",
        )
        parse_instant(receipt.get("completed_at"))
        if receipt.get("infrastructure_state") not in INFRASTRUCTURE_STATES:
            raise ValueError("holdout infrastructure state is invalid")
        for field in ("total_cases", "passed_cases", "failed_cases"):
            if type(receipt.get(field)) is not int or receipt[field] < 0:
                raise ValueError("holdout aggregate counts are invalid")
        if receipt["total_cases"] < 1:
            raise ValueError("holdout aggregate counts are invalid")
        if receipt["passed_cases"] + receipt["failed_cases"] > receipt[
            "total_cases"
        ]:
            raise ValueError("holdout aggregate counts are invalid")
        for field in ("candidate_tokens", "judge_tokens"):
            value = receipt.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("holdout token accounting is invalid")
        credits = receipt.get("credits")
        if credits is not None and (
            not isinstance(credits, (int, float)) or credits < 0
        ):
            raise ValueError("holdout credit accounting is invalid")
        if (
            type(receipt.get("accounting_complete")) is not bool
            or type(receipt.get("qualified")) is not bool
        ):
            raise ValueError("holdout terminal flags are invalid")
        if receipt["accounting_complete"] and (
            credits is None
            or receipt["candidate_tokens"] is None
            or receipt["judge_tokens"] is None
        ):
            raise ValueError("complete holdout accounting is missing")
        if receipt["qualified"] and (
            receipt["infrastructure_state"] != "completed"
            or receipt["passed_cases"] != receipt["total_cases"]
            or receipt["failed_cases"] != 0
        ):
            raise ValueError("holdout qualification contradicts aggregates")
    return receipt


def verify_receipt(state_root: Path, receipt: object) -> dict:
    receipt = validate_receipt_shape(receipt)
    authority = load_authority(state_root, receipt["authority_id"])
    signature = base64.b64decode(receipt["signature"], validate=True)
    try:
        _public_key(authority["public_key"]).verify(
            signature,
            _canonical_bytes(_unsigned(receipt)),
        )
    except Exception as error:
        raise ValueError("holdout signature verification failed") from error
    return receipt


def _receipt_root(
    state_root: Path,
    project_id: str,
    holdout_set_id: str,
    *,
    create: bool,
) -> Path:
    _validate_path_component(project_id, "project ID")
    _validate_path_component(holdout_set_id, "holdout set ID")
    return _protected_directory(
        ensure_state_root(state_root)
        / "holdout-receipts"
        / project_id
        / holdout_set_id,
        create=create,
    )


def import_receipt(state_root: Path, receipt: object) -> dict:
    receipt = verify_receipt(state_root, receipt)
    root = _receipt_root(
        state_root,
        receipt["project_id"],
        receipt["holdout_set_id"],
        create=True,
    )
    with locked(root / "holdout.lock"):
        existing_receipts = [
            verify_receipt(
                state_root,
                regular_json(path, "holdout receipt"),
            )
            for path in sorted(root.glob("*.json"))
        ]
        if receipt["kind"] == "started":
            if any(
                candidate["kind"] == "started"
                and candidate["authority_id"] == receipt["authority_id"]
                and candidate["nonce"] == receipt["nonce"]
                for candidate in existing_receipts
            ):
                raise ValueError("holdout started receipt nonce was replayed")
        else:
            started = None
            for path in sorted(root.glob("*.json")):
                candidate = verify_receipt(
                    state_root,
                    regular_json(path, "holdout receipt"),
                )
                if candidate["kind"] == "started" and digest(path) == receipt[
                    "started_receipt_sha256"
                ]:
                    started = candidate
                if (
                    candidate["kind"] == "terminal"
                    and candidate["started_receipt_sha256"]
                    == receipt["started_receipt_sha256"]
                ):
                    raise ValueError("holdout terminal receipt already exists")
            if started is None:
                raise ValueError("holdout started receipt is unavailable")
            for field in (
                "authority_id",
                "project_id",
                "holdout_set_id",
                "candidate_revision",
                "task_ids",
                "claim",
            ):
                if receipt[field] != started[field]:
                    raise ValueError(
                        "holdout receipt transition changed identity"
                    )
            completed = parse_instant(receipt["completed_at"])
            if (
                completed < parse_instant(started["started_at"])
                or completed > parse_instant(started["expires_at"])
            ):
                raise ValueError(
                    "holdout receipt completed outside its lifetime"
                )
        path = root / f"{receipt['receipt_id']}.json"
        write_exclusive(path, receipt)
    return {
        "schema_version": 1,
        "receipt_sha256": digest(path),
        "kind": receipt["kind"],
    }


def holdout_projection(
    state_root: Path,
    project_id: str,
    requirements: list[dict],
    candidate_revision: str | None,
) -> list[dict]:
    result = []
    for requirement in requirements:
        base = {
            "holdout_set_id": requirement["holdout_set_id"],
            "summary": requirement["summary"],
            "required_claim": requirement["required_claim"],
            "task_ids": requirement["task_ids"],
            "authority_id": requirement["authority_id"],
            "candidate_revision": candidate_revision,
        }
        if candidate_revision is None:
            result.append({
                **base,
                "status": "unavailable",
                "infrastructure_state": "unavailable",
                "qualification": None,
                "aggregate": None,
                "accounting": None,
            })
            continue
        try:
            root = _receipt_root(
                state_root,
                project_id,
                requirement["holdout_set_id"],
                create=False,
            )
        except (FileNotFoundError, ValueError):
            result.append({
                **base,
                "status": "unavailable",
                "infrastructure_state": "unavailable",
                "qualification": None,
                "aggregate": None,
                "accounting": None,
            })
            continue
        started = {}
        terminals = {}
        invalid = False
        for path in sorted(root.glob("*.json")):
            try:
                receipt = verify_receipt(
                    state_root,
                    regular_json(path, "holdout receipt"),
                )
            except (OSError, ValueError, json.JSONDecodeError):
                invalid = True
                continue
            if (
                receipt["project_id"] != project_id
                or receipt["holdout_set_id"]
                != requirement["holdout_set_id"]
                or receipt["authority_id"] != requirement["authority_id"]
                or receipt["candidate_revision"] != candidate_revision
                or receipt["task_ids"] != requirement["task_ids"]
                or receipt["claim"] != requirement["required_claim"]
            ):
                continue
            fingerprint = digest(path)
            if receipt["kind"] == "started":
                started[fingerprint] = receipt
            else:
                terminals.setdefault(
                    receipt["started_receipt_sha256"],
                    [],
                ).append(receipt)
        if any(len(items) != 1 for items in terminals.values()):
            invalid = True
        completed = [
            terminals[fingerprint][0]
            for fingerprint in started
            if fingerprint in terminals and len(terminals[fingerprint]) == 1
        ]
        now = parse_instant(instant())
        active = [
            receipt
            for fingerprint, receipt in started.items()
            if fingerprint not in terminals
            and parse_instant(receipt["expires_at"]) > now
        ]
        expired = [
            receipt
            for fingerprint, receipt in started.items()
            if fingerprint not in terminals
            and parse_instant(receipt["expires_at"]) <= now
        ]
        if invalid or len(completed) > 1 or len(active) > 1:
            result.append({
                **base,
                "status": "invalid",
                "infrastructure_state": "unavailable",
                "qualification": None,
                "aggregate": None,
                "accounting": None,
            })
        elif completed:
            terminal = completed[0]
            result.append({
                **base,
                "status": "completed",
                "infrastructure_state": terminal["infrastructure_state"],
                "qualification": terminal["qualified"],
                "aggregate": {
                    "total_cases": terminal["total_cases"],
                    "passed_cases": terminal["passed_cases"],
                    "failed_cases": terminal["failed_cases"],
                    "completed_at": terminal["completed_at"],
                },
                "accounting": {
                    "candidate_tokens": terminal["candidate_tokens"],
                    "judge_tokens": terminal["judge_tokens"],
                    "credits": terminal["credits"],
                    "complete": terminal["accounting_complete"],
                },
            })
        elif active:
            result.append({
                **base,
                "status": "active",
                "infrastructure_state": "unavailable",
                "qualification": None,
                "aggregate": {
                    "started_at": active[0]["started_at"],
                    "expires_at": active[0]["expires_at"],
                },
                "accounting": None,
            })
        elif expired:
            latest = max(
                expired,
                key=lambda item: parse_instant(item["expires_at"]),
            )
            result.append({
                **base,
                "status": "expired",
                "infrastructure_state": "failed",
                "qualification": None,
                "aggregate": {
                    "started_at": latest["started_at"],
                    "expires_at": latest["expires_at"],
                },
                "accounting": None,
            })
        else:
            result.append({
                **base,
                "status": "unavailable",
                "infrastructure_state": "unavailable",
                "qualification": None,
                "aggregate": None,
                "accounting": None,
            })
    return result


def sign_private_receipt(
    private_key_path: Path,
    unsigned_receipt_path: Path,
    output_path: Path,
) -> dict:
    try:
        mode = private_key_path.lstat().st_mode
    except OSError as error:
        raise ValueError("holdout private key is unavailable") from error
    if (
        private_key_path.is_symlink()
        or not stat.S_ISREG(mode)
        or stat.S_IMODE(mode) & 0o077
    ):
        raise ValueError("holdout private key is not owner protected")
    try:
        private_bytes = base64.b64decode(
            private_key_path.read_text(encoding="ascii").strip(),
            validate=True,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("holdout private key is invalid") from error
    if len(private_bytes) != 32:
        raise ValueError("holdout private key is invalid")
    unsigned = regular_json(unsigned_receipt_path, "unsigned holdout receipt")
    if "signature" in unsigned:
        raise ValueError("unsigned holdout receipt contains a signature")
    candidate = {**unsigned, "signature": base64.b64encode(b"\0" * 64).decode()}
    validate_receipt_shape(candidate)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError as error:
        raise ValueError("Ed25519 signing is unavailable") from error
    signature = Ed25519PrivateKey.from_private_bytes(private_bytes).sign(
        _canonical_bytes(unsigned)
    )
    receipt = {
        **unsigned,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_exclusive(output_path, receipt)
    return {
        "schema_version": 1,
        "receipt_sha256": digest(output_path),
        "receipt_fingerprint": json_fingerprint(receipt),
    }
