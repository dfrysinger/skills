"""Bounded, invocation-owned usage evidence and monotonic attempt timing."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import selectors
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator


MAPPING = {
    "id": "copilot-sdk-nano-aiu-1e9",
    "source_revision": "d3755535869e97d2bcf5aa6a5b8c35de79f5a7d8",
    "nano_aiu_per_credit": 1_000_000_000,
}
MAX_EVENT_BYTES = 32 * 1024 * 1024
NUMBERS = {
    "totalNanoAiu", "totalPremiumRequests", "premiumRequests",
    "totalApiDurationMs", "sessionDurationMs",
}
TOKENS = {"inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens", "reasoningTokens"}


class MeasurementError(ValueError):
    """Usage evidence is malformed or could not be captured safely."""


def instant() -> str:
    return datetime.now(timezone.utc).isoformat()


def number(value: object, field: str) -> int | float | None:
    if value is None:
        return None
    if (type(value) not in (int, float) or value < 0
            or (isinstance(value, float) and not math.isfinite(value))
            or (isinstance(value, int) and value.bit_length() > 1023)):
        raise MeasurementError(f"invalid nonnegative finite number: {field}")
    return value


def write_once(path: Path, value: dict) -> None:
    encoded = json.dumps(value, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


class Timeline:
    """Sequential stage boundaries; the outer interval is authoritative wall time."""

    def __init__(self) -> None:
        self.started_at = instant()
        self.started_clock = time.monotonic()
        self.stages: list[dict] = []
        self.active: dict | None = None
        self.switch("preparation")

    def switch(self, name: str, status: str = "completed") -> None:
        self.end_stage(status)
        self.active = {"name": name, "started_at": instant(), "started_clock": time.monotonic()}

    def end_stage(self, status: str) -> None:
        if self.active is not None:
            stage = self.active
            stage.update(completed_at=instant(), elapsed_seconds=time.monotonic() - stage.pop("started_clock"),
                         status=status)
            self.stages.append(stage)
            self.active = None

    def finish(self, status: str) -> dict:
        self.end_stage(status)
        return {
            "schema_version": 1, "started_at": self.started_at, "completed_at": instant(),
            "elapsed_seconds": time.monotonic() - self.started_clock,
            "clock": "monotonic", "status": status, "stages": self.stages,
        }


def session_uuid(value: str) -> str:
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError) as error:
        raise MeasurementError("invalid owned session UUID") from error
    if value != parsed:
        raise MeasurementError("owned session UUID must be canonical")
    return parsed


@contextmanager
def host_events(home: Path, session_id: str) -> Iterator[BinaryIO | None]:
    """Open the exact file beneath an anchored home without following child links."""
    session_uuid(session_id)
    if home.is_symlink():
        raise MeasurementError("telemetry home must not be a symlink")
    root = home.resolve()
    descriptors = []
    try:
        try:
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(fd)
            for component in ("session-state", session_id):
                fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                descriptors.append(fd)
            fd = os.open("events.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            descriptors.append(fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise MeasurementError("telemetry must be one regular, unlinked file")
        except FileNotFoundError:
            yield None
            return
        with os.fdopen(os.dup(fd), "rb") as stream:
            yield stream
    except OSError as error:
        raise MeasurementError("telemetry containment/type/read check failed") from error
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


@contextmanager
def archive_events(content: BinaryIO | bytes) -> Iterator[BinaryIO]:
    source = io.BytesIO(content) if isinstance(content, bytes) else content
    try:
        with tarfile.open(fileobj=source, mode="r:") as archive:
            member = archive.next()
            if (member is None or member.name != "events.jsonl"
                    or member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE)
                    or member.linkname or member.sparse is not None or member.size < 0):
                raise MeasurementError("telemetry archive requires one regular events.jsonl")
            if archive.next() is not None:
                raise MeasurementError("telemetry archive has multiple entries")
            end = member.offset_data + member.size
            source.seek(0, os.SEEK_END)
            size = source.tell()
            padding = (-end) % tarfile.BLOCKSIZE
            if size < end + padding + 2 * tarfile.BLOCKSIZE or size % tarfile.BLOCKSIZE:
                raise MeasurementError("telemetry archive has truncated data or padding")
            source.seek(end)
            while chunk := source.read(65536):
                if any(chunk):
                    raise MeasurementError("telemetry archive has nonzero trailing data")
            stream = archive.extractfile(member)
            if stream is None:
                raise MeasurementError("telemetry archive has no file data")
            with stream:
                yield stream
    except (tarfile.TarError, OSError) as error:
        raise MeasurementError("invalid telemetry archive") from error


@contextmanager
def bounded_command(
    command: list[str], *, timeout: float = 30,
) -> Iterator[tuple[int, BinaryIO, bytes]]:
    """Spool stdout in an owned scope; bound stderr and the capture deadline."""
    errors = bytearray()
    with tempfile.TemporaryFile(prefix="skill-eval-telemetry-", mode="w+b") as output:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                    deadline = time.monotonic() + timeout
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise MeasurementError("telemetry copy timed out")
                        for key, _ in selector.select(min(remaining, 0.25)):
                            limit = 65536 if key.data == "stdout" else 65536 - len(errors) + 1
                            chunk = os.read(key.fileobj.fileno(), min(65536, limit))
                            if not chunk:
                                selector.unregister(key.fileobj)
                            elif key.data == "stdout":
                                output.write(chunk)
                            else:
                                errors.extend(chunk)
                                if len(errors) > 65536:
                                    raise MeasurementError("telemetry copy stderr exceeds byte limit")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise MeasurementError("telemetry copy timed out")
                    code = process.wait(timeout=remaining)
            except (MeasurementError, OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
                raise
        output.seek(0)
        yield code, output, bytes(errors)


@contextmanager
def container_events(
    container: str, session_id: str, *, stopped: bool,
) -> Iterator[BinaryIO | None]:
    session_uuid(session_id)
    if not stopped:
        raise MeasurementError("telemetry writer must be stopped before capture")
    path = f"/tmp/eval-home/session-state/{session_id}/events.jsonl"
    with bounded_command(["docker", "cp", f"{container}:{path}", "-"]) as (code, output, errors):
        if code:
            # An absent eventfile is supported. Other Docker failures are measurement errors.
            missing = f"Could not find the file {path} in container {container}".encode()
            if not output.read(1) and missing in errors:
                yield None
                return
            raise MeasurementError("owned telemetry docker cp failed")
        with archive_events(output) as stream:
            yield stream


def raw_records(stream: BinaryIO, *, grammar: str) -> Iterator[bytes]:
    """Bound raw records before decoding, retaining the caller's line grammar."""
    separators = re.compile(
        b"\n" if grammar == "native" else b"\r\n|[\n\r\v\f\x1c-\x1e]|\xc2\x85|\xe2\x80[\xa8\xa9]"
    )
    pending = bytearray()
    carry = b""
    while True:
        chunk = stream.read(65536)
        data = carry + chunk
        # A UTF-8 separator or CRLF may straddle two reads.
        safe_end = max(0, len(data) - 3) if chunk else len(data)
        start = 0
        for match in separators.finditer(data):
            if match.start() >= safe_end:
                break
            pending.extend(data[start:match.end()])
            if len(pending) > MAX_EVENT_BYTES:
                raise MeasurementError("telemetry record exceeds byte limit")
            yield bytes(pending)
            pending.clear()
            start = match.end()
        end = max(start, safe_end)
        pending.extend(data[start:end])
        if len(pending) > MAX_EVENT_BYTES:
            raise MeasurementError("telemetry record exceeds byte limit")
        carry = data[end:]
        if not chunk:
            if pending:
                yield bytes(pending)
            break


def jsonl_records(
    content: BinaryIO | bytes, *, grammar: str,
) -> Iterator[tuple[bytes, dict | None]]:
    if grammar not in {"native", "telemetry"}:
        raise ValueError("unknown event grammar")

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate native event field")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite native event value")

    stream = io.BytesIO(content) if isinstance(content, bytes) else content
    options = {"object_pairs_hook": unique_fields, "parse_constant": reject_constant} if grammar == "native" else {}
    try:
        for index, raw in enumerate(raw_records(stream, grammar=grammar), 1):
            text = raw.decode("utf-8")
            if grammar == "telemetry":
                lines = text.splitlines()
                text = lines[0] if lines else ""
                if not text.strip():
                    yield raw, None
                    continue
            try:
                event = json.loads(text, **options)
            except (ValueError, RecursionError) as error:
                raise MeasurementError(f"invalid {grammar} event JSON at record {index}") from error
            if not isinstance(event, dict):
                raise MeasurementError(f"{grammar} event must be an object")
            yield raw, event
    except (UnicodeError, OSError) as error:
        raise MeasurementError(f"corrupt or unreadable {grammar} JSONL") from error


def snapshot_events(content: BinaryIO | None) -> tuple[int, str]:
    if content is None:
        raise MeasurementError("missing resumed session event prefix")
    length = 0
    digest = hashlib.sha256()
    for raw, _ in jsonl_records(content, grammar="telemetry"):
        length += len(raw)
        digest.update(raw)
    return length, digest.hexdigest()


def verify_prefix(content: BinaryIO | None, snapshot: tuple[int, str]) -> None:
    if content is None:
        raise MeasurementError("missing resumed session event prefix")
    remaining, expected = snapshot
    digest = hashlib.sha256()
    while remaining:
        chunk = content.read(min(65536, remaining))
        if not chunk:
            raise MeasurementError("resumed session event prefix truncated")
        digest.update(chunk)
        remaining -= len(chunk)
    if digest.hexdigest() != expected:
        raise MeasurementError("resumed session event prefix changed")


def filtered_metrics(value: object, *, agents: bool = False) -> dict:
    if not isinstance(value, dict):
        raise MeasurementError("usage breakdown must be an object")
    result = {}
    for name, metrics in value.items():
        if not isinstance(name, str) or not isinstance(metrics, dict):
            raise MeasurementError("usage breakdown entries must be named objects")
        selected = {key: number(metrics[key], key) for key in NUMBERS if key in metrics}
        if "usage" in metrics:
            usage = metrics["usage"]
            if not isinstance(usage, dict):
                raise MeasurementError("token usage must be an object")
            selected["usage"] = {key: number(usage[key], key) for key in TOKENS if key in usage}
        if agents and "modelMetrics" in metrics:
            selected["modelMetrics"] = filtered_metrics(metrics["modelMetrics"])
        result[name] = selected
    return result


def observations(content: BinaryIO | bytes | None, source: str, *, terminal: bool) -> list[dict]:
    if content is None:
        return []
    result = []
    try:
        for _, event in jsonl_records(content, grammar="telemetry"):
            if event is None:
                continue
            kind = event.get("type")
            if not isinstance(kind, str):
                raise MeasurementError("telemetry event type must be a string")
            if kind in {"user.message", "session.resume", "assistant.turn_start"}:
                for prior in result:
                    prior["terminal"] = False
            if kind not in {"session.shutdown", "session.usage_checkpoint", "result"}:
                continue
            data = event.get("usage") if kind == "result" else event.get("data")
            if data is None and kind == "result":
                continue
            if not isinstance(data, dict):
                raise MeasurementError("telemetry usage must be an object")
            raw = {key: number(data[key], key) for key in NUMBERS if key in data}
            for field in ("modelMetrics", "agentMetrics"):
                if field in data:
                    raw[field] = filtered_metrics(data[field], agents=field == "agentMetrics")
            result.append({
                "source": source, "event_type": kind, "raw": raw,
                "scope": "session_cumulative", "unit": "nano_aiu / premium_requests / milliseconds / tokens",
                "terminal": terminal and kind == "session.shutdown",
            })
    except MeasurementError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise MeasurementError("structurally corrupt telemetry JSONL") from error
    return result


def collect(
    *, destination: Path, session_id: str, role: str, phase: str, model: str,
    effort: str, cli_version: str | None, log: Path, capture, source: str,
    started_at: str, started_clock: float, outcome: str,
) -> dict:
    """Retain only usage; identity is supplied by the evaluator, never the source."""
    session_uuid(session_id)
    observed = []
    errors = []
    for name, reader, terminal in (
        (source, capture, True),
        ("invocation_stdout", lambda: stdout_events(log), False),
    ):
        try:
            with reader() as content:
                observed.extend(observations(content, name, terminal=terminal))
        except (MeasurementError, OSError, subprocess.TimeoutExpired) as error:
            # Do not retain source bytes or Docker stderr in a measurement error.
            errors.append({"source": name, "type": type(error).__name__,
                           "message": str(error) if isinstance(error, MeasurementError) else "capture unavailable"})
    ranked = sorted(enumerate(observed), key=lambda item: (
        3 if item[1]["terminal"] else 1 if item[1]["event_type"] == "result" else 2,
        item[1]["source"] != "invocation_stdout", item[0],
    ))
    selected = ranked[-1][0] if ranked else None
    observation = observed[selected] if selected is not None else None
    raw = observation["raw"] if observation else {}
    nano = raw.get("totalNanoAiu")
    premium = raw.get("totalPremiumRequests", raw.get("premiumRequests"))
    complete = bool(observation and observation["terminal"] and not errors)
    record = {
        "schema_version": 1, "invocation_id": destination.stem,
        "session_id": session_id, "role": role, "phase": phase,
        "requested_model": model, "effort": effort, "cli_version": cli_version,
        "source": source, "observed_at": instant(), "scope": "session_cumulative",
        "started_at": started_at, "completed_at": instant(),
        "elapsed_seconds": time.monotonic() - started_clock, "outcome": outcome,
        "mapping": MAPPING, "observations": observed, "selected_observation": selected,
        "credits": nano / MAPPING["nano_aiu_per_credit"] if nano is not None else None,
        "premium_requests": premium,
        "completeness": "error" if errors else "complete" if complete else "partial" if observed else "unknown",
        "errors": errors,
        "trust": "candidate-controlled; not tamper-proof billing" if source == "container_eventfile"
                 else "owned CLI eventfile; not billing reconciliation",
        "breakdowns_additive": False,
    }
    write_once(destination, record)
    return record


@contextmanager
def stdout_events(log: Path) -> Iterator[BinaryIO | None]:
    if not log.is_file():
        yield None
        return
    with log.open("rb") as stream:
        yield stream


def accounting(records: list[dict]) -> dict:
    """Latest cumulative observation per owned session; never sum resumed phases."""
    sessions: dict[str, list[dict]] = {}
    ids = set()
    for record in records:
        validate_record(record)
        if record.get("schema_version") != 1 or record.get("scope") != "session_cumulative":
            raise MeasurementError("unsupported invocation measurement")
        session_uuid(record["session_id"])
        if record["invocation_id"] in ids:
            raise MeasurementError("duplicate invocation identity")
        ids.add(record["invocation_id"])
        if record.get("role") not in {"candidate", "behavioral_judge", "quality_judge"}:
            raise MeasurementError("unknown invocation role")
        if record.get("completeness") not in {"complete", "partial", "unknown", "error"}:
            raise MeasurementError("invalid measurement completeness")
        number(record.get("credits"), "credits")
        number(record.get("premium_requests"), "premium_requests")
        number(record["elapsed_seconds"], "elapsed_seconds")
        sessions.setdefault(record["session_id"], []).append(record)
    totals = {}
    session_records = []
    for session, items in sorted(sessions.items()):
        roles = {item["role"] for item in items}
        if len(roles) != 1:
            raise MeasurementError("session assigned to multiple spending roles")
        items.sort(key=lambda item: (item["started_at"], item["invocation_id"]))
        latest = items[-1]
        # A failed resumed phase may have no fresh counters. Older observed spend is
        # still real, but terminal coverage no longer covers the entire session.
        known = [item for item in items if item.get("credits") is not None]
        premiums = [item for item in items if item.get("premium_requests") is not None]
        if any(b["credits"] < a["credits"] for a, b in zip(known, known[1:])):
            raise MeasurementError("session cumulative credits decreased")
        if any(b["premium_requests"] < a["premium_requests"] for a, b in zip(premiums, premiums[1:])):
            raise MeasurementError("session cumulative premium requests decreased")
        complete = latest["completeness"] == "complete" and all(
            item["completeness"] != "error" for item in items)
        session_records.append({
            "session_id": session, "role": latest["role"],
            "invocations": [item["invocation_id"] for item in items],
            "credits": known[-1]["credits"] if known else None,
            "premium_requests": premiums[-1]["premium_requests"] if premiums else None,
            "complete": complete,
            "credits_complete": complete and latest.get("credits") is not None,
            "premium_complete": complete and latest.get("premium_requests") is not None,
            "latest_completeness": latest["completeness"],
        })
    for role in ("candidate", "evaluation", "total"):
        selected = [item for item in session_records if role == "total"
                    or (item["role"] == "candidate") == (role == "candidate")]
        known = [item["credits"] for item in selected if item["credits"] is not None]
        premiums = [item["premium_requests"] for item in selected if item["premium_requests"] is not None]
        observed_credits = number(sum(known), "aggregate credits") if known or not selected else None
        observed_premiums = number(sum(premiums), "aggregate premium requests") if premiums or not selected else None
        complete = all(item["credits_complete"] for item in selected)
        totals[role] = {
            "credits": observed_credits if complete else None,
            "observed_credits": observed_credits,
            "premium_requests": observed_premiums if len(premiums) == len(selected)
                                and all(item["premium_complete"] for item in selected) else None,
            "observed_premium_requests": observed_premiums,
            "complete": complete, "sessions": len(selected),
            "known_credit_sessions": len(known),
            "complete_credit_sessions": sum(item["credits_complete"] for item in selected),
        }
    return {
        "schema_version": 1, "sessions": session_records, **totals,
        "errors": [{"invocation_id": record["invocation_id"], **error}
                   for record in records for error in record["errors"]],
    }


def validate_record(record: dict) -> None:
    if record.get("mapping") != MAPPING:
        raise MeasurementError("unknown credit mapping in measurement")
    if not isinstance(record.get("observations"), list) or not isinstance(record.get("errors"), list):
        raise MeasurementError("measurement observations/errors must be arrays")
    for field in ("invocation_id", "session_id", "role", "phase", "requested_model", "effort",
                  "started_at", "completed_at", "observed_at", "source"):
        if not isinstance(record.get(field), str) or not record[field]:
            raise MeasurementError(f"missing measurement identity: {field}")
    for field in ("started_at", "completed_at", "observed_at"):
        try:
            timestamp = datetime.fromisoformat(record[field])
        except ValueError as error:
            raise MeasurementError("invalid measurement timestamp") from error
        if timestamp.tzinfo is None:
            raise MeasurementError("measurement timestamp must include UTC offset")
    if record.get("elapsed_seconds") is None:
        raise MeasurementError("measurement duration is required")
    selected = record.get("selected_observation")
    observed = record["observations"]
    for item in observed:
        if not isinstance(item, dict) or not isinstance(item.get("raw"), dict):
            raise MeasurementError("invalid retained usage observation")
        if not isinstance(item.get("event_type"), str) or item["event_type"] not in {
            "session.shutdown", "session.usage_checkpoint", "result",
        }:
            raise MeasurementError("unknown retained usage event")
        raw = item["raw"]
        if set(raw) - NUMBERS - {"modelMetrics", "agentMetrics"}:
            raise MeasurementError("non-allowlisted retained usage field")
        for key in NUMBERS & raw.keys():
            number(raw[key], key)
        for key in ("modelMetrics", "agentMetrics"):
            if key in raw and filtered_metrics(raw[key], agents=key == "agentMetrics") != raw[key]:
                raise MeasurementError("non-allowlisted retained usage breakdown")
        if type(item.get("terminal")) is not bool or item.get("scope") != "session_cumulative":
            raise MeasurementError("invalid retained usage coverage")
    if selected is None:
        if observed or record.get("credits") is not None or record.get("premium_requests") is not None:
            raise MeasurementError("usage totals have no selected source")
        chosen = {}
    elif type(selected) is not int or selected < 0 or selected >= len(observed):
        raise MeasurementError("invalid selected usage source")
    else:
        chosen = observed[selected]
        raw = chosen["raw"]
        nano = raw.get("totalNanoAiu")
        expected = nano / MAPPING["nano_aiu_per_credit"] if nano is not None else None
        if record.get("credits") != expected or record.get("premium_requests") != raw.get(
            "totalPremiumRequests", raw.get("premiumRequests")
        ):
            raise MeasurementError("normalized totals disagree with selected source")
    expected_status = "error" if record["errors"] else "complete" if chosen.get(
        "terminal") else "partial" if observed else "unknown"
    if record.get("completeness") != expected_status:
        raise MeasurementError("measurement completeness disagrees with source")
