#!/usr/bin/env python3
"""Create and validate fail-closed live-proof receipt identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib


SCHEMA_VERSION = 1
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EVIDENCE_KINDS = {"runtime", "artifact", "query", "human-confirmation"}


class ReceiptError(ValueError):
    pass


def _git(worktree: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ReceiptError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _relative_path(value: str, *, field: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise ReceiptError(f"{field} must be a non-empty worktree-relative path")
    return path.as_posix()


def _is_excluded(path: str, excluded: tuple[str, ...]) -> bool:
    return any(path == item or path.startswith(f"{item}/") for item in excluded)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_symlink():
        digest.update(b"symlink\0")
        digest.update(os.readlink(path).encode())
    else:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def candidate_snapshot(
    worktree_value: str,
    excluded_outputs: list[str] | None = None,
    additional_inputs: list[str] | None = None,
) -> dict[str, object]:
    worktree = Path(worktree_value).expanduser().resolve()
    if not worktree.is_dir():
        raise ReceiptError(f"candidate worktree does not exist: {worktree}")
    if _git(worktree, "rev-parse", "--is-inside-work-tree").strip() != b"true":
        raise ReceiptError(f"candidate is not a git worktree: {worktree}")

    excluded = tuple(
        sorted(
            _relative_path(value, field="excluded output")
            for value in (excluded_outputs or [])
        )
    )
    for value in excluded:
        tracked = subprocess.run(
            ["git", "-C", str(worktree), "ls-files", "--error-unmatch", "--", value],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if tracked.returncode == 0:
            raise ReceiptError(f"excluded output is tracked and can affect the candidate: {value}")

    head = _git(worktree, "rev-parse", "HEAD").decode().strip()
    digest = hashlib.sha256()
    digest.update(f"live-proof-candidate-v{SCHEMA_VERSION}\0{head}\0".encode())
    digest.update(_git(worktree, "diff", "--binary", "--no-ext-diff", "HEAD", "--"))

    untracked = _git(
        worktree, "ls-files", "--others", "--exclude-standard", "-z"
    ).split(b"\0")
    for raw_path in sorted(item for item in untracked if item):
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        if _is_excluded(relative, excluded):
            continue
        path = worktree / relative
        digest.update(b"untracked\0")
        digest.update(raw_path)
        digest.update(b"\0")
        digest.update(_hash_file(path).encode())
        digest.update(b"\0")

    additional_records: list[dict[str, str]] = []
    for value in additional_inputs or []:
        relative = _relative_path(value, field="additional input")
        path = worktree / relative
        if not path.is_file() and not path.is_symlink():
            raise ReceiptError(f"additional input does not exist: {relative}")
        file_hash = _hash_file(path)
        additional_records.append({"path": relative, "sha256": file_hash})
        digest.update(b"additional\0")
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(file_hash.encode())
        digest.update(b"\0")

    return {
        "worktree": str(worktree),
        "head": head,
        "fingerprint": f"sha256:{digest.hexdigest()}",
        "excludedOutputs": list(excluded),
        "additionalInputs": additional_records,
    }


def _require_string(value: object, field: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ReceiptError(f"{field} must be a non-empty string")
    return value.strip()


def _require_string_list(value: object, field: str, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ReceiptError(f"{field} must contain at least {minimum} item(s)")
    return [_require_string(item, f"{field}[]") for item in value]


def _require_evidence(value: object, field: str) -> None:
    if not isinstance(value, list) or not value:
        raise ReceiptError(f"{field} must contain direct runtime evidence")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ReceiptError(f"{field}[{index}] must be an evidence object")
        if item.get("kind") not in EVIDENCE_KINDS:
            allowed = ", ".join(sorted(EVIDENCE_KINDS))
            raise ReceiptError(f"{field}[{index}].kind must be one of: {allowed}")
        _require_string(item.get("source"), f"{field}[{index}].source")


def _png_pixels(path: Path) -> tuple[int, int, bool]:
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ReceiptError(f"capture is too large to validate safely: {path}")
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ReceiptError(f"capture must be a PNG: {path}")

    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        if payload_end + 4 > len(data):
            raise ReceiptError(f"capture has a truncated PNG chunk: {path}")
        payload = data[payload_start:payload_end]
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        offset = payload_end + 4

    if not width or not height or width > 20000 or height > 20000:
        raise ReceiptError(f"capture has invalid dimensions: {path}")
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    if bit_depth != 8 or color_type not in channels_by_type or interlace != 0:
        raise ReceiptError(
            f"capture uses unsupported PNG encoding; use non-interlaced 8-bit RGB/RGBA: {path}"
        )

    channels = channels_by_type[color_type]
    stride = width * channels
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ReceiptError(f"capture PNG data could not be decoded: {path}: {error}") from error
    if len(raw) != height * (stride + 1):
        raise ReceiptError(f"capture PNG row data has an unexpected size: {path}")

    previous = bytearray(stride)
    first_pixel: bytes | None = None
    has_spread = False
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        encoded = raw[cursor : cursor + stride]
        cursor += stride
        row = bytearray(stride)
        for index, byte in enumerate(encoded):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                value = byte
            elif filter_type == 1:
                value = (byte + left) & 0xFF
            elif filter_type == 2:
                value = (byte + up) & 0xFF
            elif filter_type == 3:
                value = (byte + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = left + up - upper_left
                distances = (
                    abs(predictor - left),
                    abs(predictor - up),
                    abs(predictor - upper_left),
                )
                nearest = (left, up, upper_left)[distances.index(min(distances))]
                value = (byte + nearest) & 0xFF
            else:
                raise ReceiptError(f"capture uses an invalid PNG filter: {path}")
            row[index] = value
        for index in range(0, stride, channels):
            pixel = bytes(row[index : index + channels])
            if first_pixel is None:
                first_pixel = pixel
            elif pixel != first_pixel:
                has_spread = True
                break
        previous = row
        if has_spread:
            break
    return width, height, has_spread


def validate_receipt(path_value: str) -> dict[str, object]:
    receipt_path = Path(path_value).expanduser().resolve()
    try:
        receipt = json.loads(receipt_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ReceiptError(f"receipt could not be read as JSON: {error}") from error
    if not isinstance(receipt, dict):
        raise ReceiptError("receipt root must be an object")
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        raise ReceiptError(f"schemaVersion must be {SCHEMA_VERSION}")
    receipt_id = _require_string(receipt.get("id"), "id")
    if receipt.get("status") != "PASS":
        raise ReceiptError("status must be PASS to open the completion gate")
    if receipt.get("manualWorkaround") is not False:
        raise ReceiptError("manualWorkaround must be false")
    if receipt.get("unverified") != []:
        raise ReceiptError("unverified must be an empty array")

    candidate = receipt.get("candidate")
    if not isinstance(candidate, dict):
        raise ReceiptError("candidate must be an object")
    excluded = candidate.get("excludedOutputs", [])
    additional = candidate.get("additionalInputs", [])
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        raise ReceiptError("candidate.excludedOutputs must be an array of paths")
    if not isinstance(additional, list) or not all(isinstance(item, dict) for item in additional):
        raise ReceiptError("candidate.additionalInputs must be an array of objects")
    additional_paths = [
        _require_string(item.get("path"), "candidate.additionalInputs[].path")
        for item in additional
    ]
    current = candidate_snapshot(
        _require_string(candidate.get("worktree"), "candidate.worktree"),
        excluded,
        additional_paths,
    )
    for field in ("head", "fingerprint", "excludedOutputs", "additionalInputs"):
        if candidate.get(field) != current[field]:
            raise ReceiptError(f"candidate is stale: {field} no longer matches")

    running = receipt.get("running")
    if not isinstance(running, dict):
        raise ReceiptError("running must be an object")
    _require_string(running.get("identity"), "running.identity")
    _require_string(
        running.get("candidateMatchEvidence"),
        "running.candidateMatchEvidence",
        minimum=12,
    )

    scenario = receipt.get("scenario")
    if not isinstance(scenario, dict):
        raise ReceiptError("scenario must be an object")
    _require_string(scenario.get("trigger"), "scenario.trigger")
    _require_string(scenario.get("terminalState"), "scenario.terminalState")
    _require_string_list(
        scenario.get("forbiddenOutcomes"), "scenario.forbiddenOutcomes"
    )
    _require_evidence(
        scenario.get("forbiddenOutcomeEvidence"), "scenario.forbiddenOutcomeEvidence"
    )
    checkpoints = scenario.get("checkpoints")
    if not isinstance(checkpoints, list) or len(checkpoints) < 2:
        raise ReceiptError("scenario.checkpoints must contain trigger and terminal checkpoints")
    for index, checkpoint in enumerate(checkpoints):
        if not isinstance(checkpoint, dict):
            raise ReceiptError(f"scenario.checkpoints[{index}] must be an object")
        prefix = f"scenario.checkpoints[{index}]"
        _require_string(checkpoint.get("name"), f"{prefix}.name")
        _require_string(checkpoint.get("expected"), f"{prefix}.expected")
        _require_string(checkpoint.get("observed"), f"{prefix}.observed")
        _require_evidence(checkpoint.get("evidence"), f"{prefix}.evidence")
        if checkpoint.get("result") != "PASS":
            raise ReceiptError(f"{prefix}.result must be PASS")

    visual = receipt.get("visual")
    if not isinstance(visual, dict) or not isinstance(visual.get("required"), bool):
        raise ReceiptError("visual.required must be a boolean")
    captures = visual.get("captures")
    if not isinstance(captures, list):
        raise ReceiptError("visual.captures must be an array")
    if visual["required"] and not captures:
        raise ReceiptError("visual proof is required but no captures were recorded")
    for index, capture in enumerate(captures):
        if not isinstance(capture, dict):
            raise ReceiptError(f"visual.captures[{index}] must be an object")
        prefix = f"visual.captures[{index}]"
        capture_value = _require_string(capture.get("path"), f"{prefix}.path")
        capture_path = Path(capture_value).expanduser()
        if not capture_path.is_absolute():
            capture_path = (receipt_path.parent / capture_path).resolve()
        if not capture_path.is_file():
            raise ReceiptError(f"{prefix}.path does not exist: {capture_path}")
        if capture.get("opened") is not True:
            raise ReceiptError(f"{prefix}.opened must be true")
        _require_string(capture.get("claim"), f"{prefix}.claim", minimum=12)
        if capture.get("pixelSpread") != "PASS":
            raise ReceiptError(f"{prefix}.pixelSpread must be PASS")
        width, height, has_spread = _png_pixels(capture_path)
        if not has_spread:
            raise ReceiptError(f"{prefix} is visually blank (no pixel spread)")
        if capture.get("width") != width or capture.get("height") != height:
            raise ReceiptError(f"{prefix} dimensions do not match the PNG")

    return {"id": receipt_id, "candidate": current["fingerprint"], "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    fingerprint_parser = subparsers.add_parser(
        "fingerprint", help="print a candidate identity JSON object"
    )
    fingerprint_parser.add_argument("--worktree", required=True)
    fingerprint_parser.add_argument("--exclude", action="append", default=[])
    fingerprint_parser.add_argument("--additional-input", action="append", default=[])

    validate_parser = subparsers.add_parser(
        "validate", help="fail unless a receipt is a current PASS"
    )
    validate_parser.add_argument("receipt")

    args = parser.parse_args()
    try:
        if args.command == "fingerprint":
            result = candidate_snapshot(
                args.worktree, args.exclude, args.additional_input
            )
        else:
            result = validate_receipt(args.receipt)
    except ReceiptError as error:
        print(f"LIVE_PROOF FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
