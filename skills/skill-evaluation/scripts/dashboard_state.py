"""Validated create-once state for the local skill-evaluation dashboard."""

from __future__ import annotations

import json
import fcntl
import hashlib
import os
import re
import shutil
import stat
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
EXPERIMENT_EXTENSION_NAME = "experiment-activity-v1"
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
EXPERIMENT_EVENT_TYPES = {
    "experiment_declared",
    "cloud_dispatch_bound",
    "cloud_transport_observed",
    "distributed_stage_recorded",
    "distributed_result_recorded",
    "experiment_selection_recorded",
}
EXPERIMENT_WRITER_KINDS = {
    "experiment_declared": "session",
    "cloud_dispatch_bound": "distributed_coordinator",
    "cloud_transport_observed": "cloud_observer",
    "distributed_stage_recorded": "distributed_coordinator",
    "distributed_result_recorded": "distributed_coordinator",
    "experiment_selection_recorded": "experiment_evaluator",
}
EXPERIMENT_SUBJECT_FIELDS = {
    "experiment_id",
    "experiment_fingerprint",
    "attempt_id",
    "run_binding_fingerprint",
    "selection_rule_fingerprint",
}
EXPERIMENT_DECLARATION_FIELDS = {
    "title",
    "summary",
    "snapshot_id",
    "cases",
    "candidate_model",
    "candidate_timeout_seconds",
    "target_os",
    "architecture",
    "route",
    "treatments",
    "attempts",
    "selection_rule",
}
EXPERIMENT_CASE_FIELDS = {"case_id", "case_revision"}
EXPERIMENT_TREATMENT_FIELDS = {
    "treatment_id",
    "role",
    "hypothesis",
    "snapshot_id",
    "treatment_identity",
    "content_fingerprint",
    "target_skill_identities",
    "provenance_ids",
}
TARGET_SKILL_IDENTITY_FIELDS = {"name", "evaluator_fingerprint"}
EXPERIMENT_ATTEMPT_FIELDS = {
    "attempt_id",
    "case_id",
    "case_revision",
    "treatment_id",
    "repetition",
    "target_os",
    "architecture",
    "route",
    "candidate_model",
    "snapshot_id",
}
SELECTION_RULE_FIELDS = {"metrics", "coverage", "disqualifiers"}
SELECTION_METRIC_FIELDS = {"name", "direction"}
SELECTION_COVERAGE_FIELDS = {"kind", "value"}
SELECTION_DISQUALIFIER_FIELDS = {"kind", "field", "bound"}
SELECTION_METRICS = {
    "valid_terminal_repetition_count": "count",
    "terminal_pass_count": "count",
    "terminal_pass_rate": "rate",
    "deterministic_target_pass_count": "count",
    "deterministic_target_pass_rate": "rate",
    "deterministic_regression_pass_count": "count",
    "deterministic_regression_pass_rate": "rate",
    "product_pass_count": "count",
    "product_pass_rate": "rate",
    "unanimous_behavioral_pass_count": "count",
    "unanimous_behavioral_pass_rate": "rate",
    "invalid_or_missing_attempt_count": "count",
    "judge_disagreement_count": "count",
}
SELECTION_FIELDS = {
    "terminal_status",
    "deterministic_target_pass",
    "deterministic_regression_pass",
    "product_pass",
    "independent_behavioral_verdicts",
}
SELECTION_COVERAGE_KINDS = {
    "all_planned_attempts_terminal",
    "minimum_valid_repetitions_per_treatment",
    "field_present",
}
SELECTION_DISQUALIFIERS = {
    "invalid_attempt",
    "missing_required_field",
    "deterministic_regression_failure",
    "product_failure",
    "judge_disagreement_over_bound",
}
DISPATCH_PAYLOAD_FIELDS = {
    "plan_fingerprint",
    "package_archive_sha256",
    "candidate_package_archive_sha256",
    "package_manifest_sha256",
    "workflow_revision_fingerprint",
    "jobs",
    "opaque_source_id",
}
DISPATCH_JOB_FIELDS = {"job_name", "attempt_id", "stage_kind"}
CLOUD_OBSERVATION_FIELDS = {
    "observer_snapshot_fingerprint",
    "observations",
    "coverage",
    "non_atomic",
    "provenance",
    "call_count",
    "projected_response_bytes",
    "client_wall_seconds",
    "opaque_source_id",
}
CLOUD_OBSERVATION_ITEM_FIELDS = {
    "source_index",
    "job_name",
    "attempt_id",
    "stage_kind",
    "status",
    "conclusion",
    "started_at",
    "completed_at",
}
CLOUD_STATUSES = {
    "queued",
    "in_progress",
    "completed",
    "waiting",
    "requested",
    "pending",
}
CLOUD_CONCLUSIONS = {
    "success",
    "failure",
    "cancelled",
    "skipped",
    "neutral",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
}
COVERAGE_FIELDS = {"expected", "observed"}
EXECUTION_IDENTITY_FIELDS = {
    "plan_fingerprint",
    "candidate_model",
    "candidate_timeout_seconds",
    "treatment_fingerprint",
    "target_skill_identities",
    "target_os",
    "architecture",
    "route",
    "grading_route",
    "package_archive_sha256",
    "candidate_package_archive_sha256",
    "package_manifest_sha256",
    "image_identity",
    "dependency_identity",
}
ATTEMPT_IDENTITY_FIELDS = {
    "attempt_id",
    "case_id",
    "case_revision",
    "treatment_id",
    "repetition",
}
STAGE_PAYLOAD_FIELDS = {
    "attempt",
    "execution",
    "stage_kind",
    "status",
    "terminal",
    "candidate_rerun_required",
    "summaries",
    "retention_manifest_sha256",
    "source_artifact_sha256",
    "source_ids",
}
DISTRIBUTED_STAGE_STATUSES = {
    "PENDING_MACOS_PRODUCT",
    "PENDING_LINUX_FINALIZATION",
    "READY_FOR_FINALIZATION",
    "PASS",
    "FAIL",
}
RESULT_PAYLOAD_FIELDS = {
    "attempt",
    "execution",
    "terminal_status",
    "summaries",
    "first_stage_id",
    "source_lineage",
    "candidate_rerun",
    "effective_result_id",
    "selection_fields",
    "source_ids",
}
SUMMARY_FIELDS = {"candidate", "deterministic", "product", "judge"}
SOURCE_LINEAGE_FIELDS = {
    "source_id",
    "retained_archive_sha256",
    "candidate_reconstruction",
}
SELECTION_PAYLOAD_FIELDS = {
    "status",
    "selected_treatment_id",
    "eliminated_treatment_ids",
    "source_ids",
    "metrics",
    "reasons",
}
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


def parse_instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("timestamp must be an ISO-8601 string") from None
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def instant(value: str | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    parse_instant(value)
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
    projects = path / "projects"
    if projects.exists() and (projects.is_symlink() or not projects.is_dir()):
        raise ValueError(f"dashboard projects path must be a directory: {projects}")
    projects.mkdir(mode=0o700, exist_ok=True)
    os.chmod(projects, 0o700)
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
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    result = []
    plugin_fd = os.open(plugin_dir, directory_flags)
    skill_fd = plugin_fd
    try:
        for component in skill_root.relative_to(plugin_dir).parts:
            next_fd = os.open(component, directory_flags, dir_fd=skill_fd)
            if skill_fd != plugin_fd:
                os.close(skill_fd)
            skill_fd = next_fd

        def walk(directory_fd: int, prefix: str = "") -> None:
            for name in sorted(os.listdir(directory_fd)):
                relative = f"{prefix}/{name}" if prefix else name
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(entry.st_mode):
                    raise ValueError(f"snapshot capture refuses symlink: {relative}")
                if stat.S_ISDIR(entry.st_mode):
                    if name in {".git", "__pycache__"}:
                        continue
                    child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                    try:
                        if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                            raise ValueError(
                                f"snapshot capture refuses non-directory: {relative}"
                            )
                        walk(child_fd, relative)
                    finally:
                        os.close(child_fd)
                    continue
                if name == ".DS_Store" or name.endswith(".pyc"):
                    continue
                if not stat.S_ISREG(entry.st_mode):
                    raise ValueError(
                        f"snapshot capture refuses non-regular file: {relative}"
                    )
                file_fd = os.open(name, file_flags, dir_fd=directory_fd)
                try:
                    opened = os.fstat(file_fd)
                    if not stat.S_ISREG(opened.st_mode):
                        raise ValueError(
                            f"snapshot capture refuses non-regular file: {relative}"
                        )
                    with os.fdopen(os.dup(file_fd), "rb") as source:
                        content = source.read()
                    result.append((relative, content, opened.st_mode & 0o777))
                finally:
                    os.close(file_fd)

        walk(skill_fd)
    finally:
        if skill_fd != plugin_fd:
            os.close(skill_fd)
        os.close(plugin_fd)
    if not result or not any(path == "SKILL.md" for path, _, _ in result):
        raise ValueError(f"snapshot skill is missing SKILL.md: {skill_root}")
    result.sort(key=lambda item: item[0])
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
    validate_skill_snapshot(manifest)
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
    from project_dashboard import register_project_declaration

    register_project_declaration(
        state_root,
        corpus_root,
        registration["campaign_id"],
    )
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
    elif value.get("kind") in {
        "distributed_coordinator",
        "cloud_observer",
        "experiment_evaluator",
    }:
        validate_safe_id(value.get("id"), "dashboard writer ID")
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


def _exact_object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} is invalid")
    return value


def _sorted_unique_objects(
    value: object,
    fields: set[str],
    key,
    label: str,
) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{label} is invalid")
    rows = [_exact_object(item, fields, label) for item in value]
    keys = [key(item) for item in rows]
    if keys != sorted(set(keys)):
        raise ValueError(f"{label} is invalid")
    return rows


def _nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} is invalid")
    return value


def _positive_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} is invalid")
    return value


def _optional_instant(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    return instant(value)


def _validate_target_skill_identities(value: object) -> list[dict]:
    rows = _sorted_unique_objects(
        value,
        TARGET_SKILL_IDENTITY_FIELDS,
        lambda item: item["name"],
        "target skill identities",
    )
    if not rows:
        raise ValueError("target skill identities are invalid")
    for item in rows:
        validate_safe_id(item.get("name"), "target skill name")
        validate_sha256(
            item.get("evaluator_fingerprint"),
            "target skill evaluator fingerprint",
        )
    return rows


def validate_selection_rule(value: object) -> dict:
    rule = _exact_object(value, SELECTION_RULE_FIELDS, "selection rule")
    metrics = rule["metrics"]
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("selection metrics are invalid")
    names = []
    for item in metrics:
        _exact_object(item, SELECTION_METRIC_FIELDS, "selection metric")
        name = item.get("name")
        if name not in SELECTION_METRICS:
            raise ValueError("selection metric name is invalid")
        if item.get("direction") not in {"ascending", "descending"}:
            raise ValueError("selection metric direction is invalid")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("selection metrics are duplicated")

    coverage = rule["coverage"]
    if not isinstance(coverage, list) or not coverage:
        raise ValueError("selection coverage is invalid")
    normalized_coverage = []
    for item in coverage:
        _exact_object(item, SELECTION_COVERAGE_FIELDS, "selection coverage")
        kind = item.get("kind")
        if kind not in SELECTION_COVERAGE_KINDS:
            raise ValueError("selection coverage kind is invalid")
        selected = item.get("value")
        if kind == "all_planned_attempts_terminal":
            if selected is not None:
                raise ValueError("all-attempt coverage value is invalid")
        elif kind == "minimum_valid_repetitions_per_treatment":
            _positive_integer(selected, "minimum valid repetitions")
        elif selected not in SELECTION_FIELDS:
            raise ValueError("selection coverage field is invalid")
        normalized_coverage.append((kind, json.dumps(selected, sort_keys=True)))
    if normalized_coverage != sorted(set(normalized_coverage)):
        raise ValueError("selection coverage is invalid")

    disqualifiers = rule["disqualifiers"]
    if not isinstance(disqualifiers, list):
        raise ValueError("selection disqualifiers are invalid")
    normalized_disqualifiers = []
    for item in disqualifiers:
        _exact_object(
            item,
            SELECTION_DISQUALIFIER_FIELDS,
            "selection disqualifier",
        )
        kind = item.get("kind")
        if kind not in SELECTION_DISQUALIFIERS:
            raise ValueError("selection disqualifier kind is invalid")
        field = item.get("field")
        bound = item.get("bound")
        if kind == "missing_required_field":
            if field not in SELECTION_FIELDS or bound is not None:
                raise ValueError("missing-field disqualifier is invalid")
        elif kind == "judge_disagreement_over_bound":
            if field is not None:
                raise ValueError("judge-disagreement field is invalid")
            _nonnegative_integer(bound, "judge disagreement bound")
        elif field is not None or bound is not None:
            raise ValueError("selection disqualifier arguments are invalid")
        normalized_disqualifiers.append((
            kind,
            json.dumps(field, sort_keys=True),
            json.dumps(bound, sort_keys=True),
        ))
    if normalized_disqualifiers != sorted(set(normalized_disqualifiers)):
        raise ValueError("selection disqualifiers are invalid")
    return rule


def experiment_plan_fingerprint(payload: dict) -> str:
    validate_experiment_declaration(payload)
    identity = {
        key: payload[key]
        for key in EXPERIMENT_DECLARATION_FIELDS - {"title", "summary"}
    }
    return json_fingerprint(identity)


def selection_rule_fingerprint(rule: dict) -> str:
    return json_fingerprint(validate_selection_rule(rule))


def validate_experiment_declaration(value: object) -> dict:
    payload = _exact_object(
        value,
        EXPERIMENT_DECLARATION_FIELDS,
        "experiment declaration",
    )
    _bounded_text(payload.get("title"), "experiment title")
    _bounded_text(payload.get("summary"), "experiment summary")
    validate_sha256(payload.get("snapshot_id"), "experiment snapshot ID")
    _bounded_text(payload.get("candidate_model"), "candidate model")
    _positive_integer(
        payload.get("candidate_timeout_seconds"),
        "candidate timeout seconds",
    )
    for field in ("target_os", "architecture", "route"):
        validate_safe_id(payload.get(field), field.replace("_", " "))

    cases = _sorted_unique_objects(
        payload.get("cases"),
        EXPERIMENT_CASE_FIELDS,
        lambda item: item["case_id"],
        "experiment cases",
    )
    if not cases:
        raise ValueError("experiment cases are invalid")
    case_map = {}
    for item in cases:
        case_id = validate_safe_id(item.get("case_id"), "case ID")
        case_map[case_id] = validate_sha256(
            item.get("case_revision"),
            "case revision",
        )

    treatments = _sorted_unique_objects(
        payload.get("treatments"),
        EXPERIMENT_TREATMENT_FIELDS,
        lambda item: item["treatment_id"],
        "experiment treatments",
    )
    if not treatments:
        raise ValueError("experiment treatments are invalid")
    treatment_ids = set()
    control_count = 0
    for item in treatments:
        treatment_id = validate_safe_id(
            item.get("treatment_id"),
            "treatment ID",
        )
        treatment_ids.add(treatment_id)
        if item.get("role") not in {"control", "candidate"}:
            raise ValueError("experiment treatment role is invalid")
        control_count += item["role"] == "control"
        _bounded_text(item.get("hypothesis"), "treatment hypothesis")
        if item.get("snapshot_id") != payload["snapshot_id"]:
            raise ValueError("treatment snapshot does not match experiment")
        validate_sha256(
            item.get("treatment_identity"),
            "treatment identity",
        )
        validate_sha256(
            item.get("content_fingerprint"),
            "treatment content fingerprint",
        )
        _validate_target_skill_identities(item.get("target_skill_identities"))
        provenance_ids = item.get("provenance_ids")
        if (
            not isinstance(provenance_ids, list)
            or provenance_ids != sorted(set(provenance_ids))
        ):
            raise ValueError("treatment provenance IDs are invalid")
        for identifier in provenance_ids:
            validate_safe_id(identifier, "treatment provenance ID")
    if control_count != 1:
        raise ValueError("experiment requires exactly one control")

    attempts = _sorted_unique_objects(
        payload.get("attempts"),
        EXPERIMENT_ATTEMPT_FIELDS,
        lambda item: item["attempt_id"],
        "experiment attempts",
    )
    if not attempts:
        raise ValueError("experiment attempts are invalid")
    tuples = []
    repetitions = {treatment_id: set() for treatment_id in treatment_ids}
    for item in attempts:
        validate_safe_id(item.get("attempt_id"), "attempt ID")
        case_id = validate_safe_id(item.get("case_id"), "case ID")
        if (
            case_id not in case_map
            or item.get("case_revision") != case_map[case_id]
            or item.get("treatment_id") not in treatment_ids
            or item.get("target_os") != payload["target_os"]
            or item.get("architecture") != payload["architecture"]
            or item.get("route") != payload["route"]
            or item.get("candidate_model") != payload["candidate_model"]
            or item.get("snapshot_id") != payload["snapshot_id"]
        ):
            raise ValueError("experiment attempt tuple is inconsistent")
        repetition = _positive_integer(
            item.get("repetition"),
            "attempt repetition",
        )
        repetitions[item["treatment_id"]].add(repetition)
        tuples.append((
            case_id,
            item["treatment_id"],
            repetition,
        ))
    if len(tuples) != len(set(tuples)) or any(
        not values for values in repetitions.values()
    ):
        raise ValueError("experiment attempt repetitions are invalid")
    validate_selection_rule(payload.get("selection_rule"))
    return payload


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


def _experiment_extension_directory(corpus_root: Path, writer: dict) -> Path:
    root = writer_directory(corpus_root, writer) / "extensions"
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("dashboard event extensions path is invalid")
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    extension = root / EXPERIMENT_EXTENSION_NAME
    if extension.exists() and (extension.is_symlink() or not extension.is_dir()):
        raise ValueError("experiment activity extension path is invalid")
    extension.mkdir(mode=0o700, exist_ok=True)
    os.chmod(extension, 0o700)
    return extension


def _validate_safe_id_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or value != sorted(set(value)):
        raise ValueError(f"{label} is invalid")
    for item in value:
        validate_safe_id(item, label)
    return value


def _validate_summaries(value: object) -> dict:
    summaries = _exact_object(value, SUMMARY_FIELDS, "distributed summaries")
    for field in SUMMARY_FIELDS:
        _bounded_text(
            summaries.get(field),
            f"{field} summary",
            required=False,
        )
    return summaries


def _validate_attempt_identity(value: object) -> dict:
    attempt = _exact_object(value, ATTEMPT_IDENTITY_FIELDS, "attempt identity")
    validate_safe_id(attempt.get("attempt_id"), "attempt ID")
    validate_safe_id(attempt.get("case_id"), "case ID")
    validate_sha256(attempt.get("case_revision"), "case revision")
    validate_safe_id(attempt.get("treatment_id"), "treatment ID")
    _positive_integer(attempt.get("repetition"), "attempt repetition")
    return attempt


def _validate_execution_identity(value: object) -> dict:
    execution = _exact_object(
        value,
        EXECUTION_IDENTITY_FIELDS,
        "execution identity",
    )
    for field in (
        "plan_fingerprint",
        "treatment_fingerprint",
        "package_archive_sha256",
        "candidate_package_archive_sha256",
        "package_manifest_sha256",
        "image_identity",
        "dependency_identity",
    ):
        validate_sha256(execution.get(field), field.replace("_", " "))
    _bounded_text(execution.get("candidate_model"), "candidate model")
    _positive_integer(
        execution.get("candidate_timeout_seconds"),
        "candidate timeout seconds",
    )
    _validate_target_skill_identities(execution.get("target_skill_identities"))
    for field in ("target_os", "architecture", "route", "grading_route"):
        validate_safe_id(execution.get(field), field.replace("_", " "))
    return execution


def _validate_selection_fields(value: object) -> dict:
    fields = _exact_object(value, SELECTION_FIELDS, "selection fields")
    if fields.get("terminal_status") not in {"PASS", "FAIL"}:
        raise ValueError("selection terminal status is invalid")
    for field in (
        "deterministic_target_pass",
        "deterministic_regression_pass",
        "product_pass",
    ):
        if fields.get(field) is not None and type(fields[field]) is not bool:
            raise ValueError(f"selection {field} is invalid")
    verdicts = fields.get("independent_behavioral_verdicts")
    if (
        not isinstance(verdicts, list)
        or not verdicts
        or any(item not in {"PASS", "FAIL"} for item in verdicts)
    ):
        raise ValueError("independent behavioral verdicts are invalid")
    return fields


def validate_experiment_activity_event(value: dict) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != EXTENSION_EVENT_FIELDS
        or value.get("schema_version") != 1
    ):
        raise ValueError("unsupported experiment activity event")
    validate_hex_id(value.get("event_id"), "experiment activity event ID")
    event_type = value.get("event_type")
    if event_type not in EXPERIMENT_EVENT_TYPES:
        raise ValueError("experiment activity event type is invalid")
    validate_campaign_id(value.get("campaign_id"))
    writer = validate_writer(value.get("writer"))
    if writer["kind"] != EXPERIMENT_WRITER_KINDS[event_type]:
        raise ValueError("experiment activity writer does not own event type")
    instant(value.get("observed_at"))
    instant(value.get("recorded_at"))
    subject = _exact_object(
        value.get("subject"),
        EXPERIMENT_SUBJECT_FIELDS,
        "experiment activity subject",
    )
    validate_safe_id(subject.get("experiment_id"), "experiment ID")
    validate_sha256(
        subject.get("experiment_fingerprint"),
        "experiment fingerprint",
    )
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("experiment activity payload must be an object")

    if event_type == "experiment_declared":
        if any(subject[field] is not None for field in (
            "attempt_id",
            "run_binding_fingerprint",
            "selection_rule_fingerprint",
        )):
            raise ValueError("experiment declaration subject is invalid")
        validate_experiment_declaration(payload)
        if experiment_plan_fingerprint(payload) != subject["experiment_fingerprint"]:
            raise ValueError("experiment declaration fingerprint changed")
    elif event_type == "cloud_dispatch_bound":
        if (
            subject["attempt_id"] is not None
            or subject["run_binding_fingerprint"] is None
            or subject["selection_rule_fingerprint"] is not None
        ):
            raise ValueError("cloud dispatch subject is invalid")
        validate_sha256(
            subject["run_binding_fingerprint"],
            "run binding fingerprint",
        )
        _exact_object(payload, DISPATCH_PAYLOAD_FIELDS, "cloud dispatch payload")
        for field in (
            "plan_fingerprint",
            "package_archive_sha256",
            "candidate_package_archive_sha256",
            "package_manifest_sha256",
            "workflow_revision_fingerprint",
        ):
            validate_sha256(payload.get(field), field.replace("_", " "))
        if payload["plan_fingerprint"] != subject["experiment_fingerprint"]:
            raise ValueError("cloud dispatch plan fingerprint changed")
        jobs = _sorted_unique_objects(
            payload.get("jobs"),
            DISPATCH_JOB_FIELDS,
            lambda item: item["job_name"],
            "cloud dispatch jobs",
        )
        if not jobs:
            raise ValueError("cloud dispatch jobs are invalid")
        pairs = []
        for item in jobs:
            _bounded_text(item.get("job_name"), "cloud job name")
            attempt_id = item.get("attempt_id")
            if attempt_id is not None:
                validate_safe_id(attempt_id, "attempt ID")
            validate_safe_id(item.get("stage_kind"), "stage kind")
            pairs.append((attempt_id, item["stage_kind"]))
        if len(pairs) != len(set(pairs)):
            raise ValueError("cloud dispatch attempt stages are duplicated")
        validate_safe_id(payload.get("opaque_source_id"), "opaque source ID")
    elif event_type == "cloud_transport_observed":
        if (
            subject["attempt_id"] is not None
            or subject["run_binding_fingerprint"] is None
            or subject["selection_rule_fingerprint"] is not None
        ):
            raise ValueError("cloud observation subject is invalid")
        validate_sha256(
            subject["run_binding_fingerprint"],
            "run binding fingerprint",
        )
        _exact_object(
            payload,
            CLOUD_OBSERVATION_FIELDS,
            "cloud observation payload",
        )
        validate_sha256(
            payload.get("observer_snapshot_fingerprint"),
            "observer snapshot fingerprint",
        )
        observations = _sorted_unique_objects(
            payload.get("observations"),
            CLOUD_OBSERVATION_ITEM_FIELDS,
            lambda item: item["source_index"],
            "cloud observations",
        )
        names = []
        for item in observations:
            _nonnegative_integer(item.get("source_index"), "source index")
            _bounded_text(item.get("job_name"), "cloud job name")
            names.append(item["job_name"])
            if item.get("attempt_id") is not None:
                validate_safe_id(item["attempt_id"], "attempt ID")
            validate_safe_id(item.get("stage_kind"), "stage kind")
            if item.get("status") not in CLOUD_STATUSES:
                raise ValueError("cloud observation status is invalid")
            if (
                item.get("conclusion") is not None
                and item["conclusion"] not in CLOUD_CONCLUSIONS
            ):
                raise ValueError("cloud observation conclusion is invalid")
            _optional_instant(item.get("started_at"), "cloud started at")
            _optional_instant(item.get("completed_at"), "cloud completed at")
        if len(names) != len(set(names)):
            raise ValueError("cloud observation job names are duplicated")
        coverage = _exact_object(
            payload.get("coverage"),
            COVERAGE_FIELDS,
            "cloud observation coverage",
        )
        expected = _positive_integer(coverage.get("expected"), "expected jobs")
        observed = _nonnegative_integer(coverage.get("observed"), "observed jobs")
        if observed != expected or observed != len(observations):
            raise ValueError("cloud observation coverage is incomplete")
        if type(payload.get("non_atomic")) is not bool:
            raise ValueError("cloud observation non-atomic flag is invalid")
        _bounded_text(payload.get("provenance"), "cloud observation provenance")
        _positive_integer(payload.get("call_count"), "cloud call count")
        _nonnegative_integer(
            payload.get("projected_response_bytes"),
            "projected response bytes",
        )
        wall = payload.get("client_wall_seconds")
        if type(wall) not in {int, float} or wall < 0:
            raise ValueError("client wall seconds are invalid")
        validate_safe_id(payload.get("opaque_source_id"), "opaque source ID")
    elif event_type == "distributed_stage_recorded":
        if (
            subject["attempt_id"] is None
            or subject["run_binding_fingerprint"] is not None
            or subject["selection_rule_fingerprint"] is not None
        ):
            raise ValueError("distributed stage subject is invalid")
        _exact_object(payload, STAGE_PAYLOAD_FIELDS, "distributed stage payload")
        attempt = _validate_attempt_identity(payload.get("attempt"))
        if attempt["attempt_id"] != subject["attempt_id"]:
            raise ValueError("distributed stage attempt identity changed")
        execution = _validate_execution_identity(payload.get("execution"))
        if execution["plan_fingerprint"] != subject["experiment_fingerprint"]:
            raise ValueError("distributed stage plan fingerprint changed")
        validate_safe_id(payload.get("stage_kind"), "stage kind")
        if payload.get("status") not in DISTRIBUTED_STAGE_STATUSES:
            raise ValueError("distributed stage status is invalid")
        if type(payload.get("terminal")) is not bool:
            raise ValueError("distributed stage terminal flag is invalid")
        if payload["terminal"] != (payload["status"] in {"PASS", "FAIL"}):
            raise ValueError("distributed stage terminal status is inconsistent")
        if type(payload.get("candidate_rerun_required")) is not bool:
            raise ValueError("candidate rerun required flag is invalid")
        _validate_summaries(payload.get("summaries"))
        validate_sha256(
            payload.get("retention_manifest_sha256"),
            "retention manifest digest",
        )
        validate_sha256(
            payload.get("source_artifact_sha256"),
            "source artifact digest",
        )
        _validate_safe_id_list(payload.get("source_ids"), "stage source IDs")
    elif event_type == "distributed_result_recorded":
        if (
            subject["attempt_id"] is None
            or subject["run_binding_fingerprint"] is not None
            or subject["selection_rule_fingerprint"] is not None
        ):
            raise ValueError("distributed result subject is invalid")
        _exact_object(payload, RESULT_PAYLOAD_FIELDS, "distributed result payload")
        attempt = _validate_attempt_identity(payload.get("attempt"))
        if attempt["attempt_id"] != subject["attempt_id"]:
            raise ValueError("distributed result attempt identity changed")
        execution = _validate_execution_identity(payload.get("execution"))
        if execution["plan_fingerprint"] != subject["experiment_fingerprint"]:
            raise ValueError("distributed result plan fingerprint changed")
        if payload.get("terminal_status") not in {"PASS", "FAIL"}:
            raise ValueError("distributed result terminal status is invalid")
        _validate_summaries(payload.get("summaries"))
        validate_safe_id(payload.get("first_stage_id"), "first stage ID")
        lineage = payload.get("source_lineage")
        if lineage is not None:
            _exact_object(lineage, SOURCE_LINEAGE_FIELDS, "source lineage")
            validate_safe_id(lineage.get("source_id"), "source lineage ID")
            validate_sha256(
                lineage.get("retained_archive_sha256"),
                "retained archive digest",
            )
            if type(lineage.get("candidate_reconstruction")) is not bool:
                raise ValueError("candidate reconstruction flag is invalid")
        if payload.get("candidate_rerun") is not False:
            raise ValueError("distributed result cannot rerun the candidate")
        validate_safe_id(
            payload.get("effective_result_id"),
            "effective result ID",
        )
        fields = _validate_selection_fields(payload.get("selection_fields"))
        if fields["terminal_status"] != payload["terminal_status"]:
            raise ValueError("selection terminal status changed")
        _validate_safe_id_list(payload.get("source_ids"), "result source IDs")
    else:
        if (
            subject["attempt_id"] is not None
            or subject["run_binding_fingerprint"] is not None
            or subject["selection_rule_fingerprint"] is None
        ):
            raise ValueError("experiment selection subject is invalid")
        validate_sha256(
            subject["selection_rule_fingerprint"],
            "selection rule fingerprint",
        )
        _exact_object(payload, SELECTION_PAYLOAD_FIELDS, "selection payload")
        if payload.get("status") not in {"selected", "no_selection"}:
            raise ValueError("selection status is invalid")
        selected = payload.get("selected_treatment_id")
        if payload["status"] == "selected":
            validate_safe_id(selected, "selected treatment ID")
        elif selected is not None:
            raise ValueError("no-selection record selected a treatment")
        _validate_safe_id_list(
            payload.get("eliminated_treatment_ids"),
            "eliminated treatment IDs",
        )
        _validate_safe_id_list(payload.get("source_ids"), "selection source IDs")
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("selection metrics are invalid")
        for treatment_id, values in metrics.items():
            validate_safe_id(treatment_id, "selection treatment ID")
            if not isinstance(values, dict) or not set(values).issubset(
                SELECTION_METRICS
            ):
                raise ValueError("selection metric values are invalid")
            for metric, metric_value in values.items():
                if SELECTION_METRICS[metric] == "count":
                    _nonnegative_integer(metric_value, "selection count")
                else:
                    rate = _exact_object(
                        metric_value,
                        {"numerator", "denominator"},
                        "selection rate",
                    )
                    numerator = _nonnegative_integer(
                        rate.get("numerator"),
                        "selection rate numerator",
                    )
                    denominator = _positive_integer(
                        rate.get("denominator"),
                        "selection rate denominator",
                    )
                    if numerator > denominator:
                        raise ValueError("selection rate is invalid")
        reasons = payload.get("reasons")
        if not isinstance(reasons, list) or reasons != sorted(set(reasons)):
            raise ValueError("selection reasons are invalid")
        for reason in reasons:
            validate_safe_id(reason, "selection reason")
    return value


def emit_experiment_activity_event(
    corpus_root: Path,
    *,
    campaign_id: str,
    writer: dict,
    event_type: str,
    experiment_id: str,
    experiment_fingerprint: str,
    payload: dict,
    attempt_id: str | None = None,
    run_binding_fingerprint: str | None = None,
    selection_rule_fingerprint_value: str | None = None,
    event_id: str | None = None,
    observed_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    if event_type == "experiment_selection_recorded":
        raise ValueError("experiment selection must be computed")
    event = validate_experiment_activity_event({
        "schema_version": 1,
        "event_id": event_id or uuid.uuid4().hex,
        "event_type": event_type,
        "campaign_id": campaign_id,
        "writer": writer,
        "observed_at": instant(observed_at),
        "recorded_at": instant(recorded_at),
        "subject": {
            "experiment_id": experiment_id,
            "experiment_fingerprint": experiment_fingerprint,
            "attempt_id": attempt_id,
            "run_binding_fingerprint": run_binding_fingerprint,
            "selection_rule_fingerprint": selection_rule_fingerprint_value,
        },
        "payload": payload,
    })
    registration = local_campaign_registration(corpus_root)
    if registration["campaign_id"] != event["campaign_id"]:
        raise ValueError("experiment activity campaign identity changed")
    if event_type == "experiment_declared":
        snapshot = read_skill_snapshot(corpus_root, payload["snapshot_id"])
        admitted_skills = [
            {
                "name": item["name"],
                "evaluator_fingerprint": item["evaluator_skill_identity"],
            }
            for item in snapshot["skills"]
        ]
        for treatment in payload["treatments"]:
            if treatment["target_skill_identities"] != admitted_skills:
                raise ValueError(
                    "experiment target skill identities changed"
                )
    enable_live_state(corpus_root)
    return _publish_writer_record(
        _experiment_extension_directory(corpus_root, writer),
        event,
        validate_experiment_activity_event,
        label="experiment activity event",
    )


def _result_metric_values(results: list[dict], missing: int) -> dict:
    count = len(results)
    fields = [item["payload"]["selection_fields"] for item in results]
    pass_count = sum(item["terminal_status"] == "PASS" for item in fields)
    target_count = sum(item["deterministic_target_pass"] is True for item in fields)
    regression_count = sum(
        item["deterministic_regression_pass"] is True for item in fields
    )
    product_count = sum(item["product_pass"] is True for item in fields)
    unanimous_count = sum(
        all(verdict == "PASS" for verdict in item["independent_behavioral_verdicts"])
        for item in fields
    )
    disagreement_count = sum(
        len(set(item["independent_behavioral_verdicts"])) > 1
        for item in fields
    )

    def rate(numerator: int) -> dict:
        return {"numerator": numerator, "denominator": count}

    return {
        "valid_terminal_repetition_count": count,
        "terminal_pass_count": pass_count,
        "terminal_pass_rate": rate(pass_count),
        "deterministic_target_pass_count": target_count,
        "deterministic_target_pass_rate": rate(target_count),
        "deterministic_regression_pass_count": regression_count,
        "deterministic_regression_pass_rate": rate(regression_count),
        "product_pass_count": product_count,
        "product_pass_rate": rate(product_count),
        "unanimous_behavioral_pass_count": unanimous_count,
        "unanimous_behavioral_pass_rate": rate(unanimous_count),
        "invalid_or_missing_attempt_count": missing,
        "judge_disagreement_count": disagreement_count,
    }


def _metric_compare(left: object, right: object, kind: str) -> int:
    if kind == "count":
        return (left > right) - (left < right)
    left_rate = left
    right_rate = right
    left_scaled = left_rate["numerator"] * right_rate["denominator"]
    right_scaled = right_rate["numerator"] * left_rate["denominator"]
    return (left_scaled > right_scaled) - (left_scaled < right_scaled)


def compute_experiment_selection(
    declaration: dict,
    terminal_results: list[dict],
) -> dict:
    declaration = validate_experiment_activity_event(declaration)
    if declaration["event_type"] != "experiment_declared":
        raise ValueError("selection requires an experiment declaration")
    payload = declaration["payload"]
    rule = validate_selection_rule(payload["selection_rule"])
    expected = {
        item["attempt_id"]: item
        for item in payload["attempts"]
    }
    treatments_by_id = {
        item["treatment_id"]: item
        for item in payload["treatments"]
    }
    by_attempt = {}
    for result in terminal_results:
        result = validate_experiment_activity_event(result)
        if result["event_type"] != "distributed_result_recorded":
            raise ValueError("selection source is not a terminal result")
        subject = result["subject"]
        if (
            result["campaign_id"] != declaration["campaign_id"]
            or subject["experiment_id"] != declaration["subject"]["experiment_id"]
            or subject["experiment_fingerprint"]
            != declaration["subject"]["experiment_fingerprint"]
            or subject["attempt_id"] not in expected
        ):
            raise ValueError("selection source belongs to another experiment")
        attempt = result["payload"]["attempt"]
        planned = expected[subject["attempt_id"]]
        if any(
            attempt[field] != planned[field]
            for field in ATTEMPT_IDENTITY_FIELDS
        ):
            raise ValueError("selection source attempt identity changed")
        execution = result["payload"]["execution"]
        treatment = treatments_by_id[planned["treatment_id"]]
        if (
            execution["candidate_model"] != planned["candidate_model"]
            or execution["candidate_timeout_seconds"]
            != payload["candidate_timeout_seconds"]
            or execution["treatment_fingerprint"]
            != treatment["content_fingerprint"]
            or execution["target_skill_identities"]
            != treatment["target_skill_identities"]
            or execution["target_os"] != planned["target_os"]
            or execution["architecture"] != planned["architecture"]
            or execution["route"] != planned["route"]
        ):
            raise ValueError("selection source execution identity changed")
        if subject["attempt_id"] in by_attempt:
            raise ValueError("selection source attempt is duplicated")
        by_attempt[subject["attempt_id"]] = result

    treatments = treatments_by_id
    treatment_results = {treatment_id: [] for treatment_id in treatments}
    planned_counts = {treatment_id: 0 for treatment_id in treatments}
    for attempt in expected.values():
        planned_counts[attempt["treatment_id"]] += 1
    for attempt_id, result in by_attempt.items():
        treatment_results[expected[attempt_id]["treatment_id"]].append(result)

    incomplete_reasons = set()
    if any(not results for results in treatment_results.values()):
        incomplete_reasons.add("no_valid_repetitions")
    for coverage in rule["coverage"]:
        kind = coverage["kind"]
        if kind == "all_planned_attempts_terminal":
            if set(expected) != set(by_attempt):
                incomplete_reasons.add("missing_terminal_results")
        elif kind == "minimum_valid_repetitions_per_treatment":
            if any(
                len(results) < coverage["value"]
                for results in treatment_results.values()
            ):
                incomplete_reasons.add("minimum_valid_repetitions_not_met")
        elif kind == "field_present":
            field = coverage["value"]
            if any(
                result["payload"]["selection_fields"][field] is None
                for result in by_attempt.values()
            ):
                incomplete_reasons.add(f"required_field_missing.{field}")
    if incomplete_reasons:
        return {
            "status": "selection_incomplete",
            "reasons": sorted(incomplete_reasons),
        }

    metrics = {
        treatment_id: _result_metric_values(
            results,
            planned_counts[treatment_id] - len(results),
        )
        for treatment_id, results in treatment_results.items()
    }
    eliminated_reasons = {}
    for treatment_id, results in treatment_results.items():
        reasons = set()
        fields = [item["payload"]["selection_fields"] for item in results]
        for disqualifier in rule["disqualifiers"]:
            kind = disqualifier["kind"]
            if (
                kind == "invalid_attempt"
                and metrics[treatment_id]["invalid_or_missing_attempt_count"] > 0
            ):
                reasons.add("invalid_attempt")
            elif kind == "missing_required_field" and any(
                item[disqualifier["field"]] is None for item in fields
            ):
                reasons.add("missing_required_field")
            elif kind == "deterministic_regression_failure" and any(
                item["deterministic_regression_pass"] is False for item in fields
            ):
                reasons.add("deterministic_regression_failure")
            elif kind == "product_failure" and any(
                item["product_pass"] is False for item in fields
            ):
                reasons.add("product_failure")
            elif (
                kind == "judge_disagreement_over_bound"
                and metrics[treatment_id]["judge_disagreement_count"]
                > disqualifier["bound"]
            ):
                reasons.add("judge_disagreement_over_bound")
        if reasons:
            eliminated_reasons[treatment_id] = sorted(reasons)

    eligible = sorted(set(treatments) - set(eliminated_reasons))
    selected = None
    outcome_reasons = set()
    if not eligible:
        status = "no_selection"
        outcome_reasons.add("all_treatments_disqualified")
    else:
        leaders = eligible
        for metric in rule["metrics"]:
            if len(leaders) == 1:
                break
            name = metric["name"]
            direction = metric["direction"]
            best = leaders[0]
            for treatment_id in leaders[1:]:
                comparison = _metric_compare(
                    metrics[treatment_id][name],
                    metrics[best][name],
                    SELECTION_METRICS[name],
                )
                if (
                    direction == "descending" and comparison > 0
                ) or (
                    direction == "ascending" and comparison < 0
                ):
                    best = treatment_id
            leaders = [
                treatment_id
                for treatment_id in leaders
                if _metric_compare(
                    metrics[treatment_id][name],
                    metrics[best][name],
                    SELECTION_METRICS[name],
                ) == 0
            ]
        if len(leaders) == 1:
            status = "selected"
            selected = leaders[0]
            for treatment_id in eligible:
                if treatment_id != selected:
                    eliminated_reasons[treatment_id] = ["lower_ranked"]
        else:
            status = "no_selection"
            outcome_reasons.add("metric_tie")

    for reasons in eliminated_reasons.values():
        outcome_reasons.update(reasons)
    declared_metrics = [item["name"] for item in rule["metrics"]]
    return {
        "status": status,
        "selected_treatment_id": selected,
        "eliminated_treatment_ids": sorted(eliminated_reasons),
        "source_ids": sorted(
            [declaration["event_id"]]
            + [item["event_id"] for item in by_attempt.values()]
        ),
        "metrics": {
            treatment_id: {
                metric: values[metric]
                for metric in declared_metrics
            }
            for treatment_id, values in sorted(metrics.items())
        },
        "reasons": sorted(outcome_reasons),
    }


def emit_experiment_selection(
    corpus_root: Path,
    *,
    campaign_id: str,
    writer: dict,
    declaration: dict,
    terminal_results: list[dict],
    event_id: str | None = None,
    observed_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    if writer.get("kind") != "experiment_evaluator":
        raise ValueError("experiment selection writer is invalid")
    computed = compute_experiment_selection(declaration, terminal_results)
    if computed["status"] == "selection_incomplete":
        return computed
    subject = declaration["subject"]
    event = validate_experiment_activity_event({
        "schema_version": 1,
        "event_id": event_id or uuid.uuid4().hex,
        "event_type": "experiment_selection_recorded",
        "campaign_id": campaign_id,
        "writer": writer,
        "observed_at": instant(observed_at),
        "recorded_at": instant(recorded_at),
        "subject": {
            "experiment_id": subject["experiment_id"],
            "experiment_fingerprint": subject["experiment_fingerprint"],
            "attempt_id": None,
            "run_binding_fingerprint": None,
            "selection_rule_fingerprint": selection_rule_fingerprint(
                declaration["payload"]["selection_rule"]
            ),
        },
        "payload": computed,
    })
    registration = local_campaign_registration(corpus_root)
    if registration["campaign_id"] != event["campaign_id"]:
        raise ValueError("experiment selection campaign identity changed")
    enable_live_state(corpus_root)
    return _publish_writer_record(
        _experiment_extension_directory(corpus_root, writer),
        event,
        validate_experiment_activity_event,
        label="experiment activity event",
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
            except (OSError, ValueError, json.JSONDecodeError):
                invalid.append({
                    "source": (
                        f"events/{writer.name}/extensions/{EXTENSION_NAME}/"
                        f"{path.name}"
                    ),
                    "reason": "extension_event_invalid",
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
                except (OSError, ValueError, json.JSONDecodeError):
                    invalid.append({
                        "source": (
                            f"events/{writer.name}/extensions/{EXTENSION_NAME}/"
                            f"conflicts/{path.name}"
                        ),
                        "reason": "extension_conflict_invalid",
                    })
    records.sort(key=lambda item: (
        parse_instant(item["observed_at"]),
        parse_instant(item["recorded_at"]),
        item["event_id"],
    ))
    return records, conflicts, invalid


def experiment_activity_records(
    corpus_root: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    root = local_dashboard_root(corpus_root) / "events"
    if not root.exists():
        return [], [], []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("dashboard events path is invalid")
    campaign_id = local_campaign_registration(corpus_root)["campaign_id"]
    records = []
    conflicts = []
    invalid = []
    for writer_root in sorted(root.iterdir()):
        if (
            writer_root.is_symlink()
            or not writer_root.is_dir()
            or not SHA256_RE.fullmatch(writer_root.name)
        ):
            raise ValueError("dashboard event writer directory is invalid")
        extension = (
            writer_root
            / "extensions"
            / EXPERIMENT_EXTENSION_NAME
        )
        if not extension.exists():
            continue
        if extension.is_symlink() or not extension.is_dir():
            raise ValueError("experiment activity extension path is invalid")
        for path in sorted(extension.glob("*.json")):
            source = (
                f"events/{writer_root.name}/extensions/"
                f"{EXPERIMENT_EXTENSION_NAME}/{path.name}"
            )
            try:
                event = validate_experiment_activity_event(
                    regular_json(path, "experiment activity event")
                )
                expected_writer = hashlib.sha256(
                    json.dumps(
                        event["writer"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                if (
                    path.stem != event["event_id"]
                    or expected_writer != writer_root.name
                    or event["campaign_id"] != campaign_id
                ):
                    raise ValueError(
                        "experiment activity source identity disagrees"
                    )
                records.append(event)
            except (OSError, ValueError, json.JSONDecodeError):
                invalid.append({
                    "source": source,
                    "reason": "experiment_activity_event_invalid",
                })
        conflict_root = extension / "conflicts"
        if conflict_root.exists():
            if conflict_root.is_symlink() or not conflict_root.is_dir():
                raise ValueError(
                    "experiment activity conflicts path is invalid"
                )
            for path in sorted(conflict_root.glob("*.json")):
                source = (
                    f"events/{writer_root.name}/extensions/"
                    f"{EXPERIMENT_EXTENSION_NAME}/conflicts/{path.name}"
                )
                try:
                    event = validate_experiment_activity_event(
                        regular_json(path, "experiment activity conflict")
                    )
                    expected_writer = hashlib.sha256(
                        json.dumps(
                            event["writer"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    if (
                        expected_writer != writer_root.name
                        or event["campaign_id"] != campaign_id
                    ):
                        raise ValueError(
                            "experiment activity conflict identity disagrees"
                        )
                    conflicts.append({
                        "event_id": event["event_id"],
                        "event_type": event["event_type"],
                        "writer": event["writer"],
                        "source": source,
                        "reason": "event_id_reused",
                    })
                except (OSError, ValueError, json.JSONDecodeError):
                    invalid.append({
                        "source": source,
                        "reason": "experiment_activity_conflict_invalid",
                    })

    by_id = {item["event_id"]: item for item in records}
    conflicted_event_ids = {item["event_id"] for item in conflicts}
    admitted_records = []
    for event in records:
        if event["event_type"] != "experiment_selection_recorded":
            admitted_records.append(event)
            continue
        source_ids = event["payload"]["source_ids"]
        try:
            sources = [by_id[identifier] for identifier in source_ids]
        except KeyError:
            sources = []
        declarations = [
            item
            for item in sources
            if item["event_type"] == "experiment_declared"
        ]
        results = [
            item
            for item in sources
            if item["event_type"] == "distributed_result_recorded"
        ]
        experiment_results = [
            item
            for item in records
            if (
                item["event_type"] == "distributed_result_recorded"
                and item["subject"]["experiment_id"]
                == event["subject"]["experiment_id"]
                and item["subject"]["experiment_fingerprint"]
                == event["subject"]["experiment_fingerprint"]
            )
        ]
        result_attempts = [
            item["subject"]["attempt_id"] for item in experiment_results
        ]
        valid = False
        if (
            len(declarations) == 1
            and len(sources) == 1 + len(results)
            and len(result_attempts) == len(set(result_attempts))
            and not conflicted_event_ids.intersection(source_ids)
            and set(source_ids)
            == {
                declarations[0]["event_id"],
                *(item["event_id"] for item in experiment_results),
            }
        ):
            try:
                computed = compute_experiment_selection(
                    declarations[0],
                    experiment_results,
                )
                valid = (
                    computed.get("status") != "selection_incomplete"
                    and computed == event["payload"]
                    and event["subject"]["selection_rule_fingerprint"]
                    == selection_rule_fingerprint(
                        declarations[0]["payload"]["selection_rule"]
                    )
                )
            except ValueError:
                valid = False
        if valid:
            admitted_records.append(event)
        else:
            invalid.append({
                "source": None,
                "reason": "experiment_selection_invalid",
                "event_id": event["event_id"],
            })
    records = admitted_records

    selections = {}
    for event in records:
        if event["event_type"] != "experiment_selection_recorded":
            continue
        key = (
            event["subject"]["experiment_id"],
            event["subject"]["experiment_fingerprint"],
            event["subject"]["selection_rule_fingerprint"],
        )
        selections.setdefault(key, []).append(event)
    for events in selections.values():
        writers = {
            json.dumps(
                item["writer"],
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in events
        }
        payloads = {
            json.dumps(
                item["payload"],
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in events
        }
        if len(events) > 1 and (len(writers) > 1 or len(payloads) > 1):
            for event in events:
                conflicts.append({
                    "event_id": event["event_id"],
                    "event_type": event["event_type"],
                    "writer": event["writer"],
                    "source": None,
                    "reason": "terminal_selection_conflicted",
                })
    records.sort(key=lambda item: (
        parse_instant(item["observed_at"]),
        parse_instant(item["recorded_at"]),
        item["event_id"],
    ))
    conflicts.sort(key=lambda item: (
        item["event_type"],
        item["event_id"],
        item["reason"],
    ))
    invalid.sort(key=lambda item: item.get("source") or item.get("event_id", ""))
    return records, conflicts, invalid
