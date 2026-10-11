"""Validated create-once state for the local skill-evaluation dashboard."""

from __future__ import annotations

import json
import fcntl
import hashlib
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from skill_eval import load_corpus, read_json


CAMPAIGN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
HEX_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CAMPAIGN_FIELDS = {
    "schema_version",
    "campaign_id",
    "corpus_root",
    "corpus_device",
    "corpus_inode",
    "corpus_name",
    "target_skills",
}
SESSION_STATES = {"active", "blocked", "idle"}
SESSION_FIELDS = {
    "schema_version",
    "campaign_id",
    "session_id",
    "writer_generation",
    "registered_at",
    "heartbeat_at",
    "state",
    "case_id",
    "case_revision",
    "skill_identity",
    "summary",
    "last_event_id",
    "opened_at",
}
EVENT_TYPES = {
    "assignment_started",
    "assignment_blocked",
    "assignment_completed",
    "attempt_planned",
    "attempt_started",
    "attempt_artifact_available",
}
EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "event_type",
    "campaign_id",
    "writer",
    "emitted_at",
    "recorded_at",
    "entity",
    "payload",
}
WRITER_FIELDS = {"kind", "id", "generation"}
ENTITY_FIELDS = {"case_id", "case_revision"}
ASSIGNMENT_PAYLOAD_FIELDS = {"skill_identity", "state", "summary"}
ATTEMPT_PLANNED_FIELDS = {
    "model",
    "effort",
    "arm",
    "treatment_identity",
    "suite_id",
}
ATTEMPT_STARTED_FIELDS = {"planned_event_id", "run_path"}
ARTIFACT_PAYLOAD_FIELDS = {"run_path", "artifact", "sha256"}
ALLOWLISTED_LIVE_ARTIFACTS = {
    "attempt.json",
    "execution-result.json",
    "repository-result.json",
    "accounting.json",
    "timing.json",
}
LIVE_STATE = {"schema_version": 1, "live_contract": 1}


def validate_campaign_id(value: str) -> str:
    if not isinstance(value, str) or not CAMPAIGN_ID_RE.fullmatch(value):
        raise ValueError("campaign ID must be 32 lowercase hexadecimal characters")
    return value


def validate_session_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError):
        raise ValueError("session ID must be a lowercase UUID") from None
    if str(parsed) != value:
        raise ValueError("session ID must be a lowercase UUID")
    return value


def validate_hex_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not HEX_ID_RE.fullmatch(value):
        raise ValueError(f"{label} must be 32 lowercase hexadecimal characters")
    return value


def validate_sha256(value: str | None, label: str) -> str | None:
    if value is not None and (
        not isinstance(value, str) or not SHA256_RE.fullmatch(value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def validate_safe_id(value: str | None, label: str) -> str | None:
    if value is not None and (
        not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def instant(value: str | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("timestamp must be an ISO-8601 string") from None
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
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


def local_dashboard_root(corpus_root: Path) -> Path:
    root = corpus_root.expanduser().resolve() / ".skill-evaluation-ui"
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"dashboard corpus state must be a directory: {root}")
    return root


def enable_live_state(corpus_root: Path) -> None:
    root = local_dashboard_root(corpus_root)
    path = root / "live.json"
    if path.exists():
        if regular_json(path, "dashboard live contract") != LIVE_STATE:
            raise ValueError("unsupported dashboard live contract")
        return
    try:
        write_exclusive(path, LIVE_STATE)
    except FileExistsError:
        if regular_json(path, "dashboard live contract") != LIVE_STATE:
            raise ValueError("unsupported dashboard live contract")


def live_state_enabled(corpus_root: Path) -> bool:
    path = local_dashboard_root(corpus_root) / "live.json"
    if not path.exists():
        return False
    return regular_json(path, "dashboard live contract") == LIVE_STATE


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError(f"dashboard state parent must be a directory: {path.parent}")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(path: Path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


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
    with locked(local_root / "campaign.lock"):
        if local_path.exists():
            existing = validate_registration(
                regular_json(local_path, "corpus campaign")
            )
            expected = corpus_identity(corpus_root, existing["campaign_id"])
            stable_fields = CAMPAIGN_FIELDS - {"target_skills"}
            if any(existing[field] != expected[field] for field in stable_fields):
                raise ValueError("create-once campaign identity changed")
            registration = {
                **existing,
                "target_skills": sorted(
                    set(existing["target_skills"]) | set(expected["target_skills"])
                ),
            }
            if registration != existing:
                atomic_json(local_path, registration)
        else:
            registration = corpus_identity(corpus_root, uuid.uuid4().hex)
            write_exclusive(local_path, registration)

        global_path = (
            state_root / "campaigns" / f"{registration['campaign_id']}.json"
        )
        if global_path.exists():
            global_registration = validate_registration(
                regular_json(global_path, "campaign registration")
            )
            stable_fields = CAMPAIGN_FIELDS - {"target_skills"}
            if any(
                global_registration[field] != registration[field]
                for field in stable_fields
            ):
                raise ValueError("global campaign registration changed")
            if global_registration != registration:
                atomic_json(global_path, registration)
        else:
            write_exclusive(global_path, registration)
    return registration


def validate_session(value: dict) -> dict:
    if set(value) != SESSION_FIELDS or value.get("schema_version") != 1:
        raise ValueError("unsupported dashboard session registration")
    validate_campaign_id(value.get("campaign_id"))
    validate_session_id(value.get("session_id"))
    validate_hex_id(value.get("writer_generation"), "writer generation")
    instant(value.get("registered_at"))
    instant(value.get("heartbeat_at"))
    if value.get("opened_at") is not None:
        instant(value["opened_at"])
    if value.get("state") not in SESSION_STATES:
        raise ValueError("dashboard session state is invalid")
    validate_safe_id(value.get("case_id"), "case ID")
    validate_sha256(value.get("case_revision"), "case revision")
    validate_sha256(value.get("skill_identity"), "skill identity")
    if value.get("case_id") is None and value.get("case_revision") is not None:
        raise ValueError("case revision requires a case ID")
    if value.get("summary") is not None and (
        not isinstance(value["summary"], str)
        or not value["summary"].strip()
        or len(value["summary"]) > 240
    ):
        raise ValueError("dashboard session summary is invalid")
    if value.get("last_event_id") is not None:
        validate_hex_id(value["last_event_id"], "last event ID")
    return value


def session_path(corpus_root: Path, session_id: str) -> Path:
    return local_dashboard_root(corpus_root) / "sessions" / (
        f"{validate_session_id(session_id)}.json"
    )


def read_session(corpus_root: Path, session_id: str) -> dict | None:
    path = session_path(corpus_root, session_id)
    if not path.exists():
        return None
    return validate_session(regular_json(path, "dashboard session"))


def register_session(
    state_root: Path,
    corpus_root: Path,
    session_id: str,
    *,
    state: str = "active",
    now: str | None = None,
) -> tuple[dict, bool]:
    registration = create_campaign(state_root, corpus_root)
    corpus_root = corpus_root.expanduser().resolve()
    session_id = validate_session_id(session_id)
    timestamp = instant(now)
    path = session_path(corpus_root, session_id)
    lock = path.with_suffix(".lock")
    with locked(lock):
        existing = read_session(corpus_root, session_id)
        if existing is None:
            value = {
                "schema_version": 1,
                "campaign_id": registration["campaign_id"],
                "session_id": session_id,
                "writer_generation": uuid.uuid4().hex,
                "registered_at": timestamp,
                "heartbeat_at": timestamp,
                "state": state,
                "case_id": None,
                "case_revision": None,
                "skill_identity": None,
                "summary": None,
                "last_event_id": None,
                "opened_at": None,
            }
            created = True
        else:
            if existing["campaign_id"] != registration["campaign_id"]:
                raise ValueError("session campaign identity changed")
            value = {**existing, "heartbeat_at": timestamp, "state": state}
            created = False
        validate_session(value)
        atomic_json(path, value)
        enable_live_state(corpus_root)
        return value, created


def update_session(
    corpus_root: Path,
    session_id: str,
    writer_generation: str,
    **changes,
) -> dict:
    path = session_path(corpus_root, session_id)
    with locked(path.with_suffix(".lock")):
        current = read_session(corpus_root, session_id)
        if current is None:
            raise ValueError("dashboard session is not registered")
        if current["writer_generation"] != validate_hex_id(
            writer_generation,
            "writer generation",
        ):
            raise ValueError("dashboard session generation changed")
        unknown = set(changes) - {
            "heartbeat_at",
            "state",
            "case_id",
            "case_revision",
            "skill_identity",
            "summary",
            "last_event_id",
            "opened_at",
        }
        if unknown:
            raise ValueError("unsupported dashboard session update")
        value = {**current, **changes}
        validate_session(value)
        atomic_json(path, value)
        return value


def validate_writer(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != WRITER_FIELDS:
        raise ValueError("dashboard event writer is malformed")
    if value.get("kind") == "session":
        validate_session_id(value.get("id"))
    elif value.get("kind") == "evaluator":
        validate_hex_id(value.get("id"), "evaluator writer ID")
    else:
        raise ValueError("dashboard event writer kind is invalid")
    validate_hex_id(value.get("generation"), "writer generation")
    return value


def validate_run_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("dashboard run path must be a string")
    parts = Path(value).parts
    if len(parts) != 3 or parts[0] not in {"runs", "treatment-admission-runs"}:
        raise ValueError("dashboard run path is invalid")
    if any(validate_safe_id(part, "run path component") is None for part in parts):
        raise ValueError("dashboard run path is invalid")
    return value


def validate_event(value: dict) -> dict:
    if set(value) != EVENT_FIELDS or value.get("schema_version") != 1:
        raise ValueError("unsupported dashboard event")
    validate_hex_id(value.get("event_id"), "event ID")
    if value.get("event_type") not in EVENT_TYPES:
        raise ValueError("dashboard event type is invalid")
    validate_campaign_id(value.get("campaign_id"))
    validate_writer(value.get("writer"))
    instant(value.get("emitted_at"))
    instant(value.get("recorded_at"))
    entity = value.get("entity")
    if not isinstance(entity, dict) or set(entity) != ENTITY_FIELDS:
        raise ValueError("dashboard event entity is malformed")
    validate_safe_id(entity.get("case_id"), "case ID")
    validate_sha256(entity.get("case_revision"), "case revision")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("dashboard event payload must be an object")
    event_type = value["event_type"]
    if event_type.startswith("assignment_"):
        if set(payload) != ASSIGNMENT_PAYLOAD_FIELDS:
            raise ValueError("assignment event payload is malformed")
        validate_sha256(payload.get("skill_identity"), "skill identity")
        if payload.get("state") not in SESSION_STATES:
            raise ValueError("assignment event state is invalid")
        if (
            not isinstance(payload.get("summary"), str)
            or not payload["summary"].strip()
            or len(payload["summary"]) > 240
        ):
            raise ValueError("assignment event summary is invalid")
    elif event_type == "attempt_planned":
        if set(payload) != ATTEMPT_PLANNED_FIELDS:
            raise ValueError("attempt planned payload is malformed")
        for field in ("model", "effort", "arm", "treatment_identity"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                raise ValueError(f"attempt planned {field} is invalid")
        if payload.get("suite_id") is not None:
            validate_safe_id(payload["suite_id"], "suite ID")
    elif event_type == "attempt_started":
        if set(payload) != ATTEMPT_STARTED_FIELDS:
            raise ValueError("attempt started payload is malformed")
        validate_hex_id(payload.get("planned_event_id"), "planned event ID")
        validate_run_path(payload.get("run_path"))
    else:
        if set(payload) != ARTIFACT_PAYLOAD_FIELDS:
            raise ValueError("artifact event payload is malformed")
        validate_run_path(payload.get("run_path"))
        if payload.get("artifact") not in ALLOWLISTED_LIVE_ARTIFACTS:
            raise ValueError("dashboard artifact is not allowlisted")
        validate_sha256(payload.get("sha256"), "artifact digest")
    return value


def writer_directory(corpus_root: Path, writer: dict) -> Path:
    writer = validate_writer(writer)
    identifier = hashlib.sha256(
        json.dumps(writer, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    events = local_dashboard_root(corpus_root) / "events"
    if events.exists() and (events.is_symlink() or not events.is_dir()):
        raise ValueError(f"dashboard events path is invalid: {events}")
    events.mkdir(mode=0o700, exist_ok=True)
    os.chmod(events, 0o700)
    root = events / identifier
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError(f"dashboard event writer path is invalid: {root}")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def emit_event(
    corpus_root: Path,
    *,
    campaign_id: str,
    writer: dict,
    event_type: str,
    case_id: str,
    case_revision: str,
    payload: dict,
    event_id: str | None = None,
    emitted_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    event = validate_event({
        "schema_version": 1,
        "event_id": event_id or uuid.uuid4().hex,
        "event_type": event_type,
        "campaign_id": campaign_id,
        "writer": writer,
        "emitted_at": instant(emitted_at),
        "recorded_at": instant(recorded_at),
        "entity": {
            "case_id": case_id,
            "case_revision": case_revision,
        },
        "payload": payload,
    })
    enable_live_state(corpus_root)
    root = writer_directory(corpus_root, writer)
    path = root / f"{event['event_id']}.json"
    encoded = (json.dumps(event, indent=2) + "\n").encode()
    try:
        write_exclusive(path, event)
    except FileExistsError:
        if path.is_symlink() or not path.is_file():
            raise ValueError("dashboard event destination is invalid") from None
        existing = path.read_bytes()
        if existing == encoded:
            return validate_event(json.loads(existing))
        conflicts = root / "conflicts"
        if conflicts.exists() and (conflicts.is_symlink() or not conflicts.is_dir()):
            raise ValueError("dashboard event conflict path is invalid") from None
        conflicts.mkdir(mode=0o700, exist_ok=True)
        digest = hashlib.sha256(encoded).hexdigest()
        conflict = conflicts / f"{event['event_id']}-{digest}.json"
        try:
            write_exclusive(conflict, event)
        except FileExistsError:
            pass
        raise ValueError("dashboard event ID conflicts with different content") from None
    return event


def mark_session_opened(
    corpus_root: Path,
    session_id: str,
    writer_generation: str,
    *,
    opened_at: str | None = None,
) -> tuple[dict, bool]:
    path = session_path(corpus_root, session_id)
    with locked(path.with_suffix(".lock")):
        current = read_session(corpus_root, session_id)
        if current is None:
            raise ValueError("dashboard session is not registered")
        if current["writer_generation"] != writer_generation:
            raise ValueError("dashboard session generation changed")
        if current["opened_at"] is not None:
            return current, False
        value = {**current, "opened_at": instant(opened_at)}
        validate_session(value)
        atomic_json(path, value)
        return value, True


def session_event(
    corpus_root: Path,
    session_id: str,
    writer_generation: str,
    *,
    event_type: str,
    case_id: str,
    case_revision: str,
    skill_identity: str | None,
    summary: str,
    event_id: str | None = None,
    emitted_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    path = session_path(corpus_root, session_id)
    with locked(path.with_suffix(".lock")):
        current = read_session(corpus_root, session_id)
        if current is None:
            raise ValueError("dashboard session is not registered")
        if current["writer_generation"] != writer_generation:
            raise ValueError("dashboard session generation changed")
        if current["campaign_id"] is None:
            raise ValueError("dashboard session campaign is unavailable")
        event_state = {
            "assignment_started": "active",
            "assignment_blocked": "blocked",
            "assignment_completed": "idle",
        }.get(event_type)
        if event_state is None:
            raise ValueError("session writers may emit assignment events only")
        event = emit_event(
            corpus_root,
            campaign_id=current["campaign_id"],
            writer={
                "kind": "session",
                "id": session_id,
                "generation": writer_generation,
            },
            event_type=event_type,
            case_id=case_id,
            case_revision=case_revision,
            payload={
                "skill_identity": skill_identity,
                "state": event_state,
                "summary": summary,
            },
            event_id=event_id,
            emitted_at=emitted_at,
            recorded_at=recorded_at,
        )
        value = {
            **current,
            "heartbeat_at": event["recorded_at"],
            "state": event_state,
            "case_id": None if event_state == "idle" else case_id,
            "case_revision": None if event_state == "idle" else case_revision,
            "skill_identity": None if event_state == "idle" else skill_identity,
            "summary": summary,
            "last_event_id": event["event_id"],
        }
        validate_session(value)
        atomic_json(path, value)
        return event


def session_records(corpus_root: Path) -> list[dict]:
    root = local_dashboard_root(corpus_root) / "sessions"
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("dashboard sessions path is invalid")
    result = []
    for path in sorted(root.glob("*.json")):
        if path.stem != validate_session_id(path.stem):
            raise ValueError("dashboard session filename is invalid")
        value = validate_session(regular_json(path, "dashboard session"))
        if value["session_id"] != path.stem:
            raise ValueError("dashboard session filename and identity disagree")
        result.append(value)
    return result


def event_records(corpus_root: Path) -> tuple[list[dict], list[dict]]:
    root = local_dashboard_root(corpus_root) / "events"
    if not root.exists():
        return [], []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("dashboard events path is invalid")
    events = []
    conflicts = []
    for writer in sorted(root.iterdir()):
        if writer.is_symlink() or not writer.is_dir() or not SHA256_RE.fullmatch(
            writer.name
        ):
            raise ValueError("dashboard event writer directory is invalid")
        for path in sorted(writer.glob("*.json")):
            event = validate_event(regular_json(path, "dashboard event"))
            if path.stem != event["event_id"]:
                raise ValueError("dashboard event filename and identity disagree")
            events.append(event)
        conflict_root = writer / "conflicts"
        if conflict_root.exists():
            if conflict_root.is_symlink() or not conflict_root.is_dir():
                raise ValueError("dashboard event conflicts path is invalid")
            for path in sorted(conflict_root.glob("*.json")):
                event = validate_event(regular_json(path, "dashboard event conflict"))
                conflicts.append({
                    "event_id": event["event_id"],
                    "writer": event["writer"],
                    "source": (
                        f"events/{writer.name}/conflicts/{path.name}"
                    ),
                })
    events.sort(key=lambda item: (item["recorded_at"], item["event_id"]))
    return events, conflicts
