"""Validated create-once state for the local skill-evaluation dashboard."""

from __future__ import annotations

import json
import fcntl
import hashlib
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from skill_eval import json_fingerprint, load_corpus, read_json


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
SNAPSHOT_FIELDS = {"schema_version", "campaign_id", "snapshot_id", "skills"}
SNAPSHOT_SKILL_FIELDS = {
    "name",
    "sha256",
    "evaluator_skill_identity",
    "files",
}
SNAPSHOT_FILE_FIELDS = {
    "path",
    "sha256",
    "mode",
    "bytes",
    "text",
    "lines",
}
EXTENSION_NAME = "skill-lineage-v1"
EXTENSION_EVENT_TYPES = {"lineage_declared", "task_progress_recorded"}
EXTENSION_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "event_type",
    "campaign_id",
    "writer",
    "observed_at",
    "recorded_at",
    "subject",
    "payload",
}
EXTENSION_SUBJECT_FIELDS = {"snapshot_id", "case_id", "case_revision"}
LINEAGE_PAYLOAD_FIELDS = {
    "roles",
    "parents",
    "summary",
    "provenance_kind",
    "source_revision",
}
LINEAGE_ROLES = {"original", "published", "integrated", "experimental", "released"}
LINEAGE_RELATIONS = {"derived_from", "integrates", "releases"}
PROGRESS_PAYLOAD_FIELDS = {
    "frontier",
    "classification",
    "movement",
    "summary",
    "uptake",
    "blocker",
    "next_action",
    "comparison_snapshot_id",
    "sources",
}
PROGRESS_FRONTIERS = {
    "admission",
    "candidate",
    "executable",
    "behavioral",
    "quality",
    "qualification",
    "release",
    "unknown",
}
PROGRESS_CLASSIFICATIONS = {
    "skill_defect",
    "instruction_interaction",
    "execution_variance",
    "packet_defect",
    "harness_defect",
    "grading_defect",
    "authority_limit",
    "product_limit",
    "unknown",
}
PROGRESS_MOVEMENTS = {
    "Conquered",
    "Strict improvement",
    "Mixed",
    "No signal",
    "Regression",
    "Unknown",
}
UPTAKE_STATUSES = {"OBSERVED", "PARTIAL", "ABSENT", "NOT_APPLICABLE"}


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


def local_campaign_registration(corpus_root: Path) -> dict:
    return validate_registration(
        regular_json(
            local_dashboard_root(corpus_root) / "campaign.json",
            "corpus campaign",
        )
    )


def _snapshot_root(corpus_root: Path) -> Path:
    root = local_dashboard_root(corpus_root) / "snapshots"
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError(f"dashboard snapshots path is invalid: {root}")
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _refuse_symlink_ancestry(path: Path, boundary: Path, label: str) -> None:
    current = boundary
    try:
        relative = path.relative_to(boundary)
    except ValueError:
        raise ValueError(f"{label} escapes its boundary: {path}") from None
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} refuses symlink ancestry: {current}")


def _snapshot_files(
    skill_root: Path,
    plugin_dir: Path,
) -> list[tuple[str, bytes, int]]:
    _refuse_symlink_ancestry(skill_root, plugin_dir, "snapshot capture")
    if skill_root.is_symlink() or not skill_root.is_dir():
        raise ValueError(f"snapshot skill root must be a directory: {skill_root}")
    result = []
    for root, directories, names in os.walk(skill_root):
        for name in [*directories, *names]:
            path = Path(root) / name
            if path.is_symlink():
                raise ValueError(f"snapshot capture refuses symlink: {path}")
        directories[:] = sorted(
            name for name in directories if name not in {".git", "__pycache__"}
        )
        for name in sorted(names):
            if name == ".DS_Store" or name.endswith(".pyc"):
                continue
            path = Path(root) / name
            if not path.is_file():
                raise ValueError(f"snapshot capture refuses non-regular file: {path}")
            result.append((
                path.relative_to(skill_root).as_posix(),
                path.read_bytes(),
                path.stat().st_mode & 0o777,
            ))
    if not result or not any(path == "SKILL.md" for path, _, _ in result):
        raise ValueError(f"snapshot skill is missing SKILL.md: {skill_root}")
    return result


def _snapshot_file_record(path: str, content: bytes, mode: int) -> dict:
    try:
        decoded = content.decode("utf-8")
        is_text = "\x00" not in decoded
    except UnicodeDecodeError:
        decoded = ""
        is_text = False
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "mode": mode,
        "bytes": len(content),
        "text": is_text,
        "lines": len(decoded.splitlines()) if is_text else None,
    }


def _snapshot_identity(manifest: dict) -> str:
    return json_fingerprint({
        "schema_version": manifest["schema_version"],
        "campaign_id": manifest["campaign_id"],
        "skills": manifest["skills"],
    })


def _write_snapshot_file(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if path.exists():
            os.chmod(path, mode)


def capture_skill_snapshot(
    corpus_root: Path,
    plugin_dir: Path,
    skills: list[str],
) -> dict:
    registration = local_campaign_registration(corpus_root)
    plugin_dir = plugin_dir.expanduser().absolute()
    if plugin_dir.is_symlink() or not plugin_dir.is_dir():
        raise ValueError(f"snapshot plugin must be a directory: {plugin_dir}")
    skill_names = sorted(set(skills))
    if (
        not skill_names
        or len(skill_names) != len(skills)
        or any(validate_safe_id(skill, "skill name") != skill for skill in skill_names)
        or not set(skill_names).issubset(set(registration["target_skills"]))
    ):
        raise ValueError("snapshot skills must be unique campaign target skills")

    captured = []
    skill_records = []
    for skill_name in skill_names:
        files = _snapshot_files(
            plugin_dir / "skills" / skill_name,
            plugin_dir,
        )
        records = [
            _snapshot_file_record(path, content, mode)
            for path, content, mode in files
        ]
        evaluator_files = [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in records
        ]
        skill_records.append({
            "name": skill_name,
            "sha256": json_fingerprint(records),
            "evaluator_skill_identity": json_fingerprint({
                "name": skill_name,
                "files": evaluator_files,
            }),
            "files": records,
        })
        captured.append((skill_name, files))

    manifest = {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "snapshot_id": None,
        "skills": skill_records,
    }
    manifest["snapshot_id"] = _snapshot_identity(manifest)
    root = _snapshot_root(corpus_root)
    destination = root / manifest["snapshot_id"]
    if destination.exists():
        existing = read_skill_snapshot(corpus_root, manifest["snapshot_id"])
        if existing != manifest:
            raise ValueError("snapshot identity conflicts with different content")
        return existing

    staging = root / f".{manifest['snapshot_id']}.{uuid.uuid4().hex}.tmp"
    staging.mkdir(mode=0o700)
    try:
        for skill_name, files in captured:
            for relative, content, mode in files:
                _write_snapshot_file(
                    staging / "files" / skill_name / relative,
                    content,
                    mode,
                )
        manifest_path = staging / "manifest.json"
        descriptor = os.open(
            manifest_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.rename(staging, destination)
        except OSError:
            if not destination.exists():
                raise
            existing = read_skill_snapshot(corpus_root, manifest["snapshot_id"])
            if existing != manifest:
                raise ValueError(
                    "snapshot identity conflicts with different content"
                ) from None
            shutil.rmtree(staging)
            return existing
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return read_skill_snapshot(corpus_root, manifest["snapshot_id"])


def validate_skill_snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != SNAPSHOT_FIELDS:
        raise ValueError("unsupported skill snapshot")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported skill snapshot")
    validate_campaign_id(value.get("campaign_id"))
    validate_sha256(value.get("snapshot_id"), "snapshot ID")
    skills = value.get("skills")
    if (
        not isinstance(skills, list)
        or not skills
        or [item.get("name") for item in skills]
        != sorted({item.get("name") for item in skills})
    ):
        raise ValueError("skill snapshot skills are invalid")
    for skill in skills:
        if not isinstance(skill, dict) or set(skill) != SNAPSHOT_SKILL_FIELDS:
            raise ValueError("skill snapshot entry is invalid")
        validate_safe_id(skill.get("name"), "skill name")
        validate_sha256(skill.get("sha256"), "snapshot skill digest")
        validate_sha256(
            skill.get("evaluator_skill_identity"),
            "evaluator skill identity",
        )
        files = skill.get("files")
        if (
            not isinstance(files, list)
            or not files
            or [item.get("path") for item in files]
            != sorted({item.get("path") for item in files})
        ):
            raise ValueError("skill snapshot files are invalid")
        for item in files:
            if not isinstance(item, dict) or set(item) != SNAPSHOT_FILE_FIELDS:
                raise ValueError("skill snapshot file is invalid")
            relative = Path(item.get("path", ""))
            if (
                relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or relative.as_posix() != item["path"]
            ):
                raise ValueError("skill snapshot path is invalid")
            validate_sha256(item.get("sha256"), "snapshot file digest")
            if (
                type(item.get("mode")) is not int
                or item["mode"] < 0
                or item["mode"] > 0o777
                or type(item.get("bytes")) is not int
                or item["bytes"] < 0
                or type(item.get("text")) is not bool
                or (
                    item["lines"] is not None
                    and (type(item["lines"]) is not int or item["lines"] < 0)
                )
                or (item["text"] is False and item["lines"] is not None)
            ):
                raise ValueError("skill snapshot file metadata is invalid")
        evaluator_files = [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in files
        ]
        if skill["sha256"] != json_fingerprint(files):
            raise ValueError("snapshot skill digest does not match files")
        if skill["evaluator_skill_identity"] != json_fingerprint({
            "name": skill["name"],
            "files": evaluator_files,
        }):
            raise ValueError("evaluator skill identity does not match files")
    if value["snapshot_id"] != _snapshot_identity(value):
        raise ValueError("snapshot ID does not match manifest")
    return value


def read_skill_snapshot(corpus_root: Path, snapshot_id: str) -> dict:
    snapshot_id = validate_sha256(snapshot_id, "snapshot ID")
    root = _snapshot_root(corpus_root) / snapshot_id
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"skill snapshot must be a directory: {root}")
    manifest = validate_skill_snapshot(
        regular_json(root / "manifest.json", "skill snapshot manifest")
    )
    registration = local_campaign_registration(corpus_root)
    if (
        manifest["campaign_id"] != registration["campaign_id"]
        or manifest["snapshot_id"] != snapshot_id
    ):
        raise ValueError("skill snapshot campaign or filename disagrees")
    expected = set()
    for skill in manifest["skills"]:
        for item in skill["files"]:
            relative = Path("files") / skill["name"] / item["path"]
            expected.add(relative.as_posix())
            path = root / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"snapshot file must be regular: {path}")
            content = path.read_bytes()
            if (
                hashlib.sha256(content).hexdigest() != item["sha256"]
                or len(content) != item["bytes"]
                or path.stat().st_mode & 0o777 != item["mode"]
            ):
                raise ValueError(f"snapshot file does not match manifest: {path}")
    actual = set()
    files_root = root / "files"
    if files_root.is_symlink() or not files_root.is_dir():
        raise ValueError("snapshot files root must be a directory")
    for path in files_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"snapshot files refuse symlink: {path}")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError(f"snapshot files refuse non-regular entry: {path}")
    if actual != expected:
        raise ValueError("snapshot files do not match manifest membership")
    return manifest


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


def _publish_writer_record(
    root: Path,
    value: dict,
    validator,
    *,
    label: str,
) -> dict:
    event_id = validate_hex_id(value.get("event_id"), f"{label} ID")
    path = root / f"{event_id}.json"
    encoded = (json.dumps(value, indent=2) + "\n").encode()
    try:
        write_exclusive(path, value)
    except FileExistsError:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} destination is invalid") from None
        existing = path.read_bytes()
        if existing == encoded:
            return validator(json.loads(existing))
        conflicts = root / "conflicts"
        if conflicts.exists() and (conflicts.is_symlink() or not conflicts.is_dir()):
            raise ValueError(f"{label} conflict path is invalid") from None
        conflicts.mkdir(mode=0o700, exist_ok=True)
        digest = hashlib.sha256(encoded).hexdigest()
        conflict = conflicts / f"{event_id}-{digest}.json"
        try:
            write_exclusive(conflict, value)
        except FileExistsError:
            pass
        raise ValueError(f"{label} ID conflicts with different content") from None
    return value


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
    return _publish_writer_record(
        root,
        event,
        validate_event,
        label="dashboard event",
    )


def _bounded_text(value: object, label: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError(f"{label} is invalid")
    return value


def validate_extension_event(value: dict) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != EXTENSION_EVENT_FIELDS
        or value.get("schema_version") != 1
    ):
        raise ValueError("unsupported lineage extension event")
    validate_hex_id(value.get("event_id"), "lineage extension event ID")
    if value.get("event_type") not in EXTENSION_EVENT_TYPES:
        raise ValueError("lineage extension event type is invalid")
    validate_campaign_id(value.get("campaign_id"))
    validate_writer(value.get("writer"))
    instant(value.get("observed_at"))
    instant(value.get("recorded_at"))
    subject = value.get("subject")
    if not isinstance(subject, dict) or set(subject) != EXTENSION_SUBJECT_FIELDS:
        raise ValueError("lineage extension subject is invalid")
    validate_sha256(subject.get("snapshot_id"), "snapshot ID")
    validate_safe_id(subject.get("case_id"), "case ID")
    validate_sha256(subject.get("case_revision"), "case revision")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("lineage extension payload must be an object")

    if value["event_type"] == "lineage_declared":
        if set(payload) != LINEAGE_PAYLOAD_FIELDS:
            raise ValueError("lineage declaration payload is invalid")
        roles = payload.get("roles")
        if (
            not isinstance(roles, list)
            or not roles
            or roles != sorted(set(roles))
            or not set(roles).issubset(LINEAGE_ROLES)
        ):
            raise ValueError("lineage declaration roles are invalid")
        parents = payload.get("parents")
        if not isinstance(parents, list):
            raise ValueError("lineage declaration parents are invalid")
        normalized = []
        for parent in parents:
            if not isinstance(parent, dict) or set(parent) != {
                "snapshot_id",
                "relation",
            }:
                raise ValueError("lineage declaration parent is invalid")
            validate_sha256(parent.get("snapshot_id"), "parent snapshot ID")
            if parent.get("relation") not in LINEAGE_RELATIONS:
                raise ValueError("lineage declaration relation is invalid")
            normalized.append((parent["snapshot_id"], parent["relation"]))
        if normalized != sorted(set(normalized)):
            raise ValueError("lineage declaration parents are invalid")
        _bounded_text(payload.get("summary"), "lineage declaration summary")
        _bounded_text(
            payload.get("provenance_kind"),
            "lineage provenance kind",
            required=False,
        )
        _bounded_text(
            payload.get("source_revision"),
            "lineage source revision",
            required=False,
        )
        if subject["case_id"] is not None or subject["case_revision"] is not None:
            raise ValueError("lineage declaration cannot target a case")
    else:
        if set(payload) != PROGRESS_PAYLOAD_FIELDS:
            raise ValueError("task progress payload is invalid")
        if (
            subject["case_id"] is None
            or subject["case_revision"] is None
            or payload.get("frontier") not in PROGRESS_FRONTIERS
            or payload.get("classification") not in PROGRESS_CLASSIFICATIONS
            or payload.get("movement") not in PROGRESS_MOVEMENTS
        ):
            raise ValueError("task progress classification is invalid")
        _bounded_text(payload.get("summary"), "task progress summary")
        _bounded_text(payload.get("blocker"), "task progress blocker", required=False)
        _bounded_text(
            payload.get("next_action"),
            "task progress next action",
            required=False,
        )
        validate_sha256(
            payload.get("comparison_snapshot_id"),
            "comparison snapshot ID",
        )
        uptake = payload.get("uptake")
        if not isinstance(uptake, list):
            raise ValueError("task progress uptake is invalid")
        rule_ids = []
        for item in uptake:
            if not isinstance(item, dict) or set(item) != {
                "rule_id",
                "status",
                "summary",
            }:
                raise ValueError("task progress uptake row is invalid")
            rule_ids.append(validate_safe_id(item.get("rule_id"), "rule ID"))
            if item.get("status") not in UPTAKE_STATUSES:
                raise ValueError("task progress uptake status is invalid")
            _bounded_text(item.get("summary"), "task progress uptake summary")
        if rule_ids != sorted(set(rule_ids)):
            raise ValueError("task progress uptake rows are invalid")
        sources = payload.get("sources")
        if not isinstance(sources, list):
            raise ValueError("task progress sources are invalid")
        source_ids = []
        for item in sources:
            if not isinstance(item, dict) or set(item) != {"kind", "id"}:
                raise ValueError("task progress source is invalid")
            if item.get("kind") not in {
                "attempt",
                "report",
                "session_event",
                "review_receipt",
            }:
                raise ValueError("task progress source kind is invalid")
            source_ids.append((
                item["kind"],
                validate_safe_id(item.get("id"), "source ID"),
            ))
        if source_ids != sorted(set(source_ids)):
            raise ValueError("task progress sources are invalid")
    return value


def _extension_directory(corpus_root: Path, writer: dict) -> Path:
    root = writer_directory(corpus_root, writer) / "extensions"
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("dashboard event extensions path is invalid")
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    extension = root / EXTENSION_NAME
    if extension.exists() and (extension.is_symlink() or not extension.is_dir()):
        raise ValueError("lineage extension path is invalid")
    extension.mkdir(mode=0o700, exist_ok=True)
    os.chmod(extension, 0o700)
    return extension


def emit_extension_event(
    corpus_root: Path,
    *,
    campaign_id: str,
    writer: dict,
    event_type: str,
    snapshot_id: str,
    case_id: str | None,
    case_revision: str | None,
    payload: dict,
    event_id: str | None = None,
    observed_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    event = validate_extension_event({
        "schema_version": 1,
        "event_id": event_id or uuid.uuid4().hex,
        "event_type": event_type,
        "campaign_id": campaign_id,
        "writer": writer,
        "observed_at": instant(observed_at),
        "recorded_at": instant(recorded_at),
        "subject": {
            "snapshot_id": snapshot_id,
            "case_id": case_id,
            "case_revision": case_revision,
        },
        "payload": payload,
    })
    registration = local_campaign_registration(corpus_root)
    if registration["campaign_id"] != event["campaign_id"]:
        raise ValueError("lineage extension campaign identity changed")
    read_skill_snapshot(corpus_root, event["subject"]["snapshot_id"])
    enable_live_state(corpus_root)
    return _publish_writer_record(
        _extension_directory(corpus_root, writer),
        event,
        validate_extension_event,
        label="lineage extension event",
    )


def emit_lineage_event(
    corpus_root: Path,
    *,
    campaign_id: str,
    writer: dict,
    snapshot_id: str,
    roles: list[str],
    parents: list[dict],
    summary: str,
    provenance_kind: str | None = None,
    source_revision: str | None = None,
    event_id: str | None = None,
    observed_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    snapshot = read_skill_snapshot(corpus_root, snapshot_id)
    registration = local_campaign_registration(corpus_root)
    declared_roles = set(roles)
    if declared_roles - {"experimental"} and (
        [item["name"] for item in snapshot["skills"]]
        != registration["target_skills"]
    ):
        raise ValueError("campaign lineage roles require every target skill")
    for parent in parents:
        if parent.get("snapshot_id") == snapshot_id:
            raise ValueError("lineage snapshot cannot parent itself")
        read_skill_snapshot(corpus_root, parent.get("snapshot_id"))
    return emit_extension_event(
        corpus_root,
        campaign_id=campaign_id,
        writer=writer,
        event_type="lineage_declared",
        snapshot_id=snapshot_id,
        case_id=None,
        case_revision=None,
        payload={
            "roles": sorted(roles),
            "parents": sorted(
                parents,
                key=lambda item: (item["snapshot_id"], item["relation"]),
            ),
            "summary": summary,
            "provenance_kind": provenance_kind,
            "source_revision": source_revision,
        },
        event_id=event_id,
        observed_at=observed_at,
        recorded_at=recorded_at,
    )


def emit_task_progress_event(
    corpus_root: Path,
    *,
    campaign_id: str,
    writer: dict,
    snapshot_id: str,
    case_id: str,
    case_revision: str,
    frontier: str,
    classification: str,
    movement: str,
    summary: str,
    uptake: list[dict] | None = None,
    blocker: str | None = None,
    next_action: str | None = None,
    comparison_snapshot_id: str | None = None,
    sources: list[dict] | None = None,
    event_id: str | None = None,
    observed_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    if comparison_snapshot_id is not None:
        read_skill_snapshot(corpus_root, comparison_snapshot_id)
    return emit_extension_event(
        corpus_root,
        campaign_id=campaign_id,
        writer=writer,
        event_type="task_progress_recorded",
        snapshot_id=snapshot_id,
        case_id=case_id,
        case_revision=case_revision,
        payload={
            "frontier": frontier,
            "classification": classification,
            "movement": movement,
            "summary": summary,
            "uptake": sorted(
                uptake or [],
                key=lambda item: item["rule_id"],
            ),
            "blocker": blocker,
            "next_action": next_action,
            "comparison_snapshot_id": comparison_snapshot_id,
            "sources": sorted(
                sources or [],
                key=lambda item: (item["kind"], item["id"]),
            ),
        },
        event_id=event_id,
        observed_at=observed_at,
        recorded_at=recorded_at,
    )


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


def extension_records(
    corpus_root: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    root = local_dashboard_root(corpus_root) / "events"
    if not root.exists():
        return [], [], []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("dashboard events path is invalid")
    records = []
    conflicts = []
    invalid = []
    for writer in sorted(root.iterdir()):
        if writer.is_symlink() or not writer.is_dir() or not SHA256_RE.fullmatch(
            writer.name
        ):
            raise ValueError("dashboard event writer directory is invalid")
        extension = writer / "extensions" / EXTENSION_NAME
        if not extension.exists():
            continue
        if extension.is_symlink() or not extension.is_dir():
            raise ValueError("lineage extension path is invalid")
        for path in sorted(extension.glob("*.json")):
            try:
                event = validate_extension_event(
                    regular_json(path, "lineage extension event")
                )
                if path.stem != event["event_id"]:
                    raise ValueError(
                        "lineage extension filename and identity disagree"
                    )
                records.append(event)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                invalid.append({
                    "source": (
                        f"events/{writer.name}/extensions/{EXTENSION_NAME}/"
                        f"{path.name}"
                    ),
                    "reason": str(error),
                })
        conflict_root = extension / "conflicts"
        if conflict_root.exists():
            if conflict_root.is_symlink() or not conflict_root.is_dir():
                raise ValueError("lineage extension conflicts path is invalid")
            for path in sorted(conflict_root.glob("*.json")):
                try:
                    event = validate_extension_event(
                        regular_json(path, "lineage extension event conflict")
                    )
                    conflicts.append({
                        "event_id": event["event_id"],
                        "writer": event["writer"],
                        "source": (
                            f"events/{writer.name}/extensions/{EXTENSION_NAME}/"
                            f"conflicts/{path.name}"
                        ),
                    })
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    invalid.append({
                        "source": (
                            f"events/{writer.name}/extensions/{EXTENSION_NAME}/"
                            f"conflicts/{path.name}"
                        ),
                        "reason": str(error),
                    })
    records.sort(key=lambda item: (item["observed_at"], item["event_id"]))
    return records, conflicts, invalid
