#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
from pathlib import Path

from dashboard_state import (
    capture_skill_snapshot,
    create_campaign,
    emit_experiment_activity_event,
    emit_lineage_event,
    experiment_plan_fingerprint,
    json_fingerprint,
    locked,
    regular_json,
)
from project_dashboard import (
    canonical_project_declaration,
    project_declaration_fingerprint,
    project_index_projection,
)
from skill_eval import (
    digest,
    freeze_case,
    frozen_case_path,
    init_corpus,
    read_json,
    verify_case,
    write_json,
)


SCHEMA_VERSION = 1
RECEIPT_NAME = "one-time-migration-receipt.json"
TERMINAL_OUTCOMES = {"PASS", "FAIL"}
EXPECTED_REPETITIONS = {
    "c01": 3,
    "c02": 3,
    "c03": 3,
    "c04": 3,
    "c05": 3,
    "c06": 3,
    "c07": 3,
    "c08": 2,
}
EXPECTED_REQUIRED_PASSES = {
    "c01": 3,
    "c02": 3,
    "c03": 3,
    "c04": 2,
    "c05": 2,
    "c06": 2,
    "c07": 3,
    "c08": 2,
}
EXPECTED_TREATMENTS = {
    "h01-probe-interference-bracket": "candidate",
    "b01-unchanged-parent": "control",
}
APPROVED_SOURCE_ALIASES = {
    ".claude/skills": "../skills",
    ".codex/skills": "../skills",
    ".github/skills": "../skills",
}
TRACE_AUDIT_RULE = {
    "schema_version": 1,
    "aliases": sorted(APPROVED_SOURCE_ALIASES),
    "forbidden_metadata_operations": [
        "core.symlinks",
        "find-type-l",
        "inode",
        "lstat",
        "readlink",
        "realpath",
        "stat-alias",
    ],
    "event_type": "tool.execution_start",
}
ALIAS_REFERENCE_SCAN_RULE = {
    "schema_version": 1,
    "aliases": sorted(APPROVED_SOURCE_ALIASES),
    "scope": "digest-admitted-hidden-authority-bytes",
}
EXPECTED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "migration_id",
    "recorded_at",
    "output_root",
    "state_root",
    "project",
    "experiment",
    "treatments",
    "tasks",
    "unknown_fields",
}
EXPECTED_PROJECT_FIELDS = {
    "project_id",
    "title",
    "goal",
    "target_skill",
}
EXPECTED_EXPERIMENT_FIELDS = {
    "experiment_id",
    "title",
    "summary",
    "candidate_model",
    "candidate_timeout_seconds",
    "target_os",
    "architecture",
    "route",
}
EXPECTED_TREATMENT_FIELDS = {
    "treatment_id",
    "role",
    "hypothesis",
    "skill_file",
    "skill_file_sha256",
}
EXPECTED_TASK_FIELDS = {
    "source_case_key",
    "case_id",
    "title",
    "summary",
    "role",
    "original_task_revision",
    "execution_case_revision",
    "package_root",
    "archive",
    "package_manifest",
    "case_manifest",
    "candidate_archive",
    "candidate_task",
    "qualification",
    "attempts",
    "unknown_fields",
}
EXPECTED_QUALIFICATION_FIELDS = {
    "required_repetitions",
    "required_passes",
    "historical_threshold_met",
}
EXPECTED_ATTEMPT_FIELDS = {
    "attempt_id",
    "treatment_id",
    "repetition",
    "outcome",
    "execution_state",
    "result_source",
    "proof_source",
    "retained_archive",
    "terminal_timestamp",
    "candidate_elapsed_seconds",
    "usage_observations",
    "complete_financial_cost",
    "unknown_fields",
}
EXPECTED_FILE_REFERENCE_FIELDS = {"path", "sha256"}


def _require_exact_fields(value: dict, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields are invalid")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is invalid")
    return value


def _require_sha256(value: object, label: str) -> str:
    text = _require_text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} is invalid")
    return text


def _file_reference(value: object, label: str) -> dict:
    _require_exact_fields(value, EXPECTED_FILE_REFERENCE_FIELDS, label)
    path = Path(_require_text(value["path"], f"{label} path")).expanduser()
    expected = _require_sha256(value["sha256"], f"{label} digest")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is unavailable")
    if digest(path) != expected:
        raise ValueError(f"{label} digest does not match")
    return {"path": path, "sha256": expected}


def _optional_file_reference(value: object, label: str) -> dict | None:
    if value is None:
        return None
    return _file_reference(value, label)


def _safe_relative_path(value: object, label: str) -> Path:
    text = _require_text(value, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} escapes its root")
    return path


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:*") as stream:
        members = stream.getmembers()
        symlinks = {
            Path(member.name)
            for member in members
            if member.issym()
        }
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.islnk()
                or member.isdev()
            ):
                raise ValueError("archive contains an unsafe member")
            resolved = (destination / path).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError("archive member escapes its destination")
            if any(
                symlink != path and symlink in path.parents
                for symlink in symlinks
            ):
                raise ValueError("archive member traverses a symbolic link")
            if member.issym():
                link = Path(member.linkname)
                if link.is_absolute():
                    raise ValueError("archive contains an unsafe member")
                target = (resolved.parent / link).resolve()
                if target != root and root not in target.parents:
                    raise ValueError("archive link escapes its destination")
        stream.extractall(destination, filter="data")


def _read_tar_json(archive: Path, names: tuple[str, ...], label: str) -> dict:
    with tarfile.open(archive, "r:*") as stream:
        for name in names:
            try:
                member = stream.getmember(name)
            except KeyError:
                continue
            if not member.isfile():
                raise ValueError(f"{label} is not a regular file")
            fileobj = stream.extractfile(member)
            if fileobj is None:
                raise ValueError(f"{label} is unavailable")
            value = json.load(io.TextIOWrapper(fileobj, encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"{label} is invalid")
            return value
    raise ValueError(f"{label} is missing")


def _read_tar_bytes(archive: Path, names: tuple[str, ...], label: str) -> bytes:
    with tarfile.open(archive, "r:*") as stream:
        for name in names:
            try:
                member = stream.getmember(name)
            except KeyError:
                continue
            if not member.isfile():
                raise ValueError(f"{label} is not a regular file")
            fileobj = stream.extractfile(member)
            if fileobj is None:
                raise ValueError(f"{label} is unavailable")
            return fileobj.read()
    raise ValueError(f"{label} is missing")


def _ordinary_tree_manifest(root: Path) -> list[dict]:
    records = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("materialized source tree contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("materialized source tree contains a special file")
        records.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": digest(path),
            "bytes": path.stat().st_size,
            "mode": path.stat().st_mode & 0o777,
        })
    return records


def _materialize_source_aliases(
    repository: Path,
    source_bundle_sha256: str,
) -> list[dict]:
    aliases = {
        path.relative_to(repository).as_posix(): path
        for path in repository.rglob("*")
        if path.is_symlink()
    }
    if set(aliases) - set(APPROVED_SOURCE_ALIASES):
        raise ValueError("packaged source contains an unapproved symbolic link")
    result = []
    for relative in sorted(aliases):
        path = aliases[relative]
        target_text = os.readlink(path)
        if target_text != APPROVED_SOURCE_ALIASES[relative]:
            raise ValueError("packaged source alias target changed")
        target = (path.parent / target_text).resolve()
        root = repository.resolve()
        if (
            target == root
            or root not in target.parents
            or not target.is_dir()
            or target.is_symlink()
        ):
            raise ValueError("packaged source alias target is invalid")
        target_manifest = _ordinary_tree_manifest(target)
        path.unlink()
        shutil.copytree(target, path, copy_function=shutil.copy2)
        materialized_manifest = _ordinary_tree_manifest(path)
        if materialized_manifest != target_manifest:
            raise ValueError("source alias materialization changed tree bytes")
        record = {
            "source_bundle_sha256": source_bundle_sha256,
            "alias_path": relative,
            "verified_relative_target": target_text,
            "operation": "materialize-relative-directory-symlink",
            "target_tree_manifest_sha256": json_fingerprint(target_manifest),
            "materialized_tree_manifest_sha256": json_fingerprint(
                materialized_manifest
            ),
            "ordinary_files": materialized_manifest,
        }
        record["reconstruction_manifest_sha256"] = json_fingerprint(record)
        result.append(record)
    if any(path.is_symlink() for path in repository.rglob("*")):
        raise ValueError("packaged source alias normalization is incomplete")
    return result


def _git_status_paths(value: object) -> list[str]:
    if not isinstance(value, str):
        raise ValueError("historical candidate status is invalid")
    result = []
    for line in value.splitlines():
        if len(line) < 4:
            raise ValueError("historical candidate status is invalid")
        payload = line[3:].strip()
        for item in payload.split(" -> "):
            normalized = item.strip().strip('"')
            if normalized:
                result.append(normalized)
    return result


def _metadata_operation_match(arguments: str, aliases: list[str]) -> bool:
    lowered = arguments.lower()
    if not aliases:
        return False
    if any(token in lowered for token in ("readlink", "lstat", "realpath")):
        return True
    if "core.symlinks" in lowered or "inode" in lowered:
        return True
    if re.search(r"\bfind\b[^\n]*\s-type\s+l\b", lowered):
        return True
    if re.search(r"\bstat\b", lowered):
        return True
    return False


def _candidate_trace_audit(
    trace_bytes: bytes,
    alias_paths: list[str],
    repository: Path,
) -> dict:
    event_count = 0
    tool_start_count = 0
    forbidden_matches = 0
    ordinary_accesses = []
    loaded_skills = {}
    footer_count = 0
    for raw in (line for line in trace_bytes.splitlines() if line.strip()):
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as error:
            footer = raw.decode("utf-8", errors="strict")
            if footer == (
                "Session exported to: "
                "/Users/runner/work/skill-evaluation/"
                "skill-evaluation/run-root/"
                "candidate-primary-transcript.md"
            ):
                footer_count += 1
                continue
            raise ValueError("candidate trace contains invalid JSON") from error
        if not isinstance(event, dict):
            raise ValueError("candidate trace event is invalid")
        event_count += 1
        event_type = event.get("type")
        data = event.get("data")
        if event_type == "tool.execution_start":
            tool_start_count += 1
            arguments = json.dumps(
                data.get("arguments") if isinstance(data, dict) else None,
                sort_keys=True,
            )
            observed_aliases = [
                alias for alias in alias_paths if alias in arguments
            ]
            if _metadata_operation_match(arguments, observed_aliases):
                forbidden_matches += 1
            elif observed_aliases:
                ordinary_accesses.extend({
                    "operation": (
                        data.get("toolName")
                        if isinstance(data, dict) else "unknown"
                    ),
                    "normalized_alias_path": alias,
                    "event_identifier": (
                        data.get("toolCallId")
                        if isinstance(data, dict) else None
                    ),
                } for alias in observed_aliases)
        elif event_type == "session.skills_loaded" and isinstance(data, dict):
            for skill in data.get("skills", []):
                if not isinstance(skill, dict):
                    continue
                source_path = skill.get("path")
                if not isinstance(source_path, str):
                    continue
                marker = "/workspaces/nexus/"
                if marker not in source_path:
                    continue
                relative = source_path.split(marker, 1)[1]
                if not any(
                    relative == alias or relative.startswith(f"{alias}/")
                    for alias in alias_paths
                ):
                    continue
                local = repository / _safe_relative_path(
                    relative,
                    "loaded skill path",
                )
                if not local.is_file() or local.is_symlink():
                    raise ValueError("loaded skill content is unavailable")
                loaded_skills[relative] = digest(local)
    if footer_count != 1:
        raise ValueError("candidate trace export footer is invalid")
    if forbidden_matches:
        raise ValueError("candidate trace observed source link metadata")
    return {
        "trace_event_count": event_count,
        "trace_footer_count": footer_count,
        "tool_execution_start_count": tool_start_count,
        "ordinary_alias_accesses": sorted(
            ordinary_accesses,
            key=lambda item: (
                item["normalized_alias_path"],
                item["event_identifier"] or "",
            ),
        ),
        "skills_loaded": [{
            "normalized_source_path": path,
            "loaded_content_sha256": loaded_skills[path],
        } for path in sorted(loaded_skills)],
    }


def _alias_correspondence(
    task: dict,
    repository: Path,
    case_manifest: dict,
    aliases: list[dict],
) -> dict | None:
    if not aliases:
        return None
    alias_paths = sorted(item["alias_path"] for item in aliases)
    hidden_artifacts = case_manifest["hiddenAuthority"]["artifacts"]
    hidden_inventory = sorted(
        ({
            "path": item["path"],
            "sha256": item["sha256"],
        } for item in hidden_artifacts),
        key=lambda item: item["path"],
    )
    grader_inventory = [
        item for item in hidden_inventory
        if "/grader/" in item["path"]
    ]
    alias_reference_matches = 0
    for item in hidden_artifacts:
        path = task["_package_root"] / _safe_relative_path(
            item["path"],
            "hidden authority path",
        )
        content = path.read_bytes()
        alias_reference_matches += sum(
            alias.encode("utf-8") in content for alias in alias_paths
        )
    if alias_reference_matches:
        raise ValueError("hidden authority references a source alias")

    attempts = []
    for attempt in task["attempts"]:
        if attempt["outcome"] not in TERMINAL_OUTCOMES:
            continue
        result_source = read_json(attempt["_result_source"]["path"])
        verification = result_source.get("verification")
        reconstruction = (
            verification.get("candidate_reconstruction")
            if isinstance(verification, dict) else None
        )
        if not isinstance(reconstruction, list) or not reconstruction:
            raise ValueError("historical candidate reconstruction is missing")
        touched_paths = sorted({
            path
            for record in reconstruction
            for path in _git_status_paths(record.get("originalStatus"))
        })
        alias_write_matches = [
            path for path in touched_paths
            if path == "skills"
            or path.startswith("skills/")
            or any(
                path == alias or path.startswith(f"{alias}/")
                for alias in alias_paths
            )
        ]
        if alias_write_matches:
            raise ValueError("historical candidate wrote through a source alias")

        archive = attempt["_retained_archive"]["path"]
        trace_path = "run-root/candidate-primary.jsonl"
        receipt_path = "run-root/macos-candidate-stage-receipt.json"
        trace_bytes = _read_tar_bytes(
            archive,
            (trace_path,),
            "candidate execution trace",
        )
        receipt_bytes = _read_tar_bytes(
            archive,
            (receipt_path,),
            "candidate execution receipt",
        )
        stage_receipt = json.loads(receipt_bytes)
        receipt_log_sha256 = (
            stage_receipt.get("candidate", {})
            .get("primary", {})
            .get("logSha256")
        )
        trace_sha256 = hashlib.sha256(trace_bytes).hexdigest()
        if receipt_log_sha256 != trace_sha256:
            raise ValueError("candidate trace receipt binding changed")

        trace_audit = _candidate_trace_audit(
            trace_bytes,
            alias_paths,
            repository,
        )
        attempts.append({
            "attempt_id": attempt["attempt_id"],
            "retained_archive_sha256": attempt["_retained_archive"]["sha256"],
            "source_result_sha256": attempt["_result_source"]["sha256"],
            "source_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "candidate_trace_path": trace_path,
            "candidate_trace_sha256": trace_sha256,
            "receipt_log_sha256": receipt_log_sha256,
            "trace_log_binding_verified": True,
            "trace_schema": "copilot-jsonl-events-v1",
            "trace_event_count": trace_audit["trace_event_count"],
            "trace_footer_count": trace_audit["trace_footer_count"],
            "tool_execution_start_count": (
                trace_audit["tool_execution_start_count"]
            ),
            "trace_audit_rule_sha256": json_fingerprint(TRACE_AUDIT_RULE),
            "forbidden_metadata_operation_match_count": 0,
            "alias_or_target_write_match_count": 0,
            "ordinary_alias_accesses": trace_audit["ordinary_alias_accesses"],
            "skills_loaded": trace_audit["skills_loaded"],
            "original_status_record_sha256": json_fingerprint(reconstruction),
            "touched_path_set_sha256": json_fingerprint(touched_paths),
            "hidden_authority_inventory_sha256": json_fingerprint(
                hidden_inventory
            ),
            "grader_inventory_sha256": json_fingerprint(grader_inventory),
            "alias_reference_scan_rule_sha256": json_fingerprint(
                ALIAS_REFERENCE_SCAN_RULE
            ),
            "grader_alias_reference_match_count": 0,
        })
    return {
        "schema_version": 1,
        "aliases": aliases,
        "attempts": attempts,
    }


def _normalize_manifest(path: Path) -> dict:
    manifest = read_json(path)
    _require_exact_fields(manifest, EXPECTED_TOP_LEVEL_FIELDS, "migration manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("migration manifest schema is unsupported")
    _require_text(manifest["migration_id"], "migration ID")
    _require_text(manifest["recorded_at"], "recorded timestamp")
    output_root = Path(
        _require_text(manifest["output_root"], "output root")
    ).expanduser()
    state_root = Path(
        _require_text(manifest["state_root"], "state root")
    ).expanduser()
    if output_root == state_root or output_root in state_root.parents:
        raise ValueError("output and state roots overlap")
    _require_exact_fields(manifest["project"], EXPECTED_PROJECT_FIELDS, "project")
    _require_exact_fields(
        manifest["experiment"],
        EXPECTED_EXPERIMENT_FIELDS,
        "experiment",
    )
    treatments = manifest["treatments"]
    if not isinstance(treatments, list) or len(treatments) != 2:
        raise ValueError("migration requires one candidate and one control")
    roles = set()
    treatment_ids = set()
    for treatment in treatments:
        _require_exact_fields(
            treatment,
            EXPECTED_TREATMENT_FIELDS,
            "treatment",
        )
        treatment_id = _require_text(
            treatment["treatment_id"],
            "treatment ID",
        )
        if treatment_id in treatment_ids:
            raise ValueError("treatment IDs must be unique")
        treatment_ids.add(treatment_id)
        role = treatment["role"]
        if role not in {"candidate", "control"}:
            raise ValueError("treatment role is invalid")
        roles.add(role)
        skill_file = _file_reference(
            {
                "path": treatment["skill_file"],
                "sha256": treatment["skill_file_sha256"],
            },
            f"{role} skill file",
        )
        treatment["_skill_path"] = skill_file["path"]
    if roles != {"candidate", "control"}:
        raise ValueError("migration requires candidate and control roles")
    if {
        item["treatment_id"]: item["role"] for item in treatments
    } != EXPECTED_TREATMENTS:
        raise ValueError("historical treatment identities changed")
    if (
        manifest["experiment"]["experiment_id"]
        != "general-probe-interference-comparison-r2850"
    ):
        raise ValueError("historical experiment identity changed")
    tasks = manifest["tasks"]
    if not isinstance(tasks, list) or len(tasks) != 8:
        raise ValueError("migration manifest must contain exactly eight tasks")
    case_ids = set()
    source_keys = set()
    attempt_ids = set()
    for task in tasks:
        _require_exact_fields(task, EXPECTED_TASK_FIELDS, "task")
        source_key = _require_text(task["source_case_key"], "source case key")
        case_id = _require_text(task["case_id"], "case ID")
        if source_key in source_keys or case_id in case_ids:
            raise ValueError("task identities must be unique")
        source_keys.add(source_key)
        case_ids.add(case_id)
        _require_sha256(
            task["original_task_revision"],
            "original task revision",
        )
        _require_sha256(
            task["execution_case_revision"],
            "execution case revision",
        )
        package_root = Path(
            _require_text(task["package_root"], "package root")
        ).expanduser()
        if not package_root.is_dir() or package_root.is_symlink():
            raise ValueError("package root is unavailable")
        task["_package_root"] = package_root
        for field in (
            "archive",
            "package_manifest",
            "case_manifest",
            "candidate_archive",
            "candidate_task",
        ):
            task[f"_{field}"] = _file_reference(
                task[field],
                f"{source_key} {field.replace('_', ' ')}",
            )
        qualification = task["qualification"]
        _require_exact_fields(
            qualification,
            EXPECTED_QUALIFICATION_FIELDS,
            f"{source_key} qualification",
        )
        required_repetitions = qualification["required_repetitions"]
        required_passes = qualification["required_passes"]
        if (
            not isinstance(required_repetitions, int)
            or required_repetitions < 1
            or not isinstance(required_passes, int)
            or required_passes < 1
            or required_passes > required_repetitions
            or not isinstance(qualification["historical_threshold_met"], bool)
        ):
            raise ValueError(f"{source_key} qualification is invalid")
        if (
            EXPECTED_REPETITIONS.get(source_key) != required_repetitions
            or EXPECTED_REQUIRED_PASSES.get(source_key) != required_passes
        ):
            raise ValueError(f"{source_key} historical threshold changed")
        attempts = task["attempts"]
        if not isinstance(attempts, list) or not attempts:
            raise ValueError(f"{source_key} attempts are invalid")
        treatment_repetitions: dict[str, set[int]] = {
            treatment_id: set() for treatment_id in treatment_ids
        }
        for attempt in attempts:
            _require_exact_fields(
                attempt,
                EXPECTED_ATTEMPT_FIELDS,
                f"{source_key} attempt",
            )
            attempt_id = _require_text(attempt["attempt_id"], "attempt ID")
            if attempt_id in attempt_ids:
                raise ValueError("attempt IDs must be globally unique")
            attempt_ids.add(attempt_id)
            treatment_id = attempt["treatment_id"]
            repetition = attempt["repetition"]
            if treatment_id not in treatment_ids:
                raise ValueError("attempt treatment is undeclared")
            if not isinstance(repetition, int) or repetition < 1:
                raise ValueError("attempt repetition is invalid")
            if repetition in treatment_repetitions[treatment_id]:
                raise ValueError("attempt repetition is duplicated")
            treatment_repetitions[treatment_id].add(repetition)
            outcome = attempt["outcome"]
            if outcome not in TERMINAL_OUTCOMES | {"UNEXECUTED_STOP"}:
                raise ValueError("attempt outcome is invalid")
            if outcome in TERMINAL_OUTCOMES:
                attempt["_result_source"] = _file_reference(
                    attempt["result_source"],
                    f"{attempt_id} result source",
                )
                attempt["_proof_source"] = _optional_file_reference(
                    attempt["proof_source"],
                    f"{attempt_id} proof source",
                )
                attempt["_retained_archive"] = _file_reference(
                    attempt["retained_archive"],
                    f"{attempt_id} retained archive",
                )
            elif any(
                attempt[field] is not None
                for field in ("result_source", "proof_source", "retained_archive")
            ):
                raise ValueError("unexecuted attempts cannot have terminal evidence")
            expected_attempt_id = (
                f"r2850-{treatment_id.split('-', 1)[0]}-"
                f"{source_key}-r{repetition}"
            )
            if attempt_id != expected_attempt_id:
                raise ValueError("historical attempt identity changed")
        expected_repetitions = set(range(1, required_repetitions + 1))
        if any(
            values != expected_repetitions
            for values in treatment_repetitions.values()
        ):
            raise ValueError(f"{source_key} fixed treatment population changed")
        candidate_id = next(
            item["treatment_id"]
            for item in treatments
            if item["role"] == "candidate"
        )
        candidate_attempts = [
            item for item in attempts if item["treatment_id"] == candidate_id
        ]
        if (
            len(candidate_attempts) != required_repetitions
            or any(item["outcome"] not in TERMINAL_OUTCOMES for item in candidate_attempts)
        ):
            raise ValueError(f"{source_key} candidate population is incomplete")
        passed = sum(item["outcome"] == "PASS" for item in candidate_attempts)
        if (passed >= required_passes) != qualification["historical_threshold_met"]:
            raise ValueError(f"{source_key} historical threshold conflicts")
    if source_keys != set(EXPECTED_REPETITIONS):
        raise ValueError("historical task population changed")
    all_attempts = [
        attempt for task in tasks for attempt in task["attempts"]
    ]
    candidate_id = next(
        item["treatment_id"]
        for item in treatments
        if item["role"] == "candidate"
    )
    control_id = next(
        item["treatment_id"]
        for item in treatments
        if item["role"] == "control"
    )
    candidate = [
        item for item in all_attempts
        if item["treatment_id"] == candidate_id
    ]
    control = [
        item for item in all_attempts
        if item["treatment_id"] == control_id
    ]
    if (
        len(all_attempts) != 46
        or len(candidate) != 23
        or sum(item["outcome"] == "PASS" for item in candidate) != 22
        or sum(item["outcome"] == "FAIL" for item in candidate) != 1
        or len(control) != 23
        or sum(item["outcome"] == "PASS" for item in control) != 6
        or sum(item["outcome"] == "FAIL" for item in control) != 1
        or sum(item["outcome"] == "UNEXECUTED_STOP" for item in control) != 16
    ):
        raise ValueError("historical 46-attempt population changed")
    return {
        "manifest": manifest,
        "manifest_path": path,
        "manifest_sha256": digest(path),
        "output_root": output_root,
        "state_root": state_root,
    }


def _verify_declared_package_files(task: dict) -> tuple[dict, dict]:
    package_manifest = read_json(task["_package_manifest"]["path"])
    case_manifest = read_json(task["_case_manifest"]["path"])
    if package_manifest.get("schemaVersion") != 1:
        raise ValueError("package manifest schema is unsupported")
    package_root = task["_package_root"]
    if task["_case_manifest"]["sha256"] != digest(
        package_root / "case-manifest.json"
    ):
        raise ValueError("outer case manifest does not match")
    if case_manifest.get("schemaVersion") != 1:
        raise ValueError("case manifest schema is unsupported")
    if (
        case_manifest.get("caseId") != task["case_id"]
        or case_manifest.get("caseRevision") != task["execution_case_revision"]
    ):
        raise ValueError("packaged case identity conflicts with the manifest")
    package_cases = package_manifest.get("cases")
    if not isinstance(package_cases, list):
        raise ValueError("package case index is invalid")
    expected_manifest = task["_case_manifest"]["path"].relative_to(
        task["_package_manifest"]["path"].parent
    ).as_posix()
    matching = [
        item for item in package_cases
        if isinstance(item, dict)
        and item.get("caseId") == task["case_id"]
        and item.get("caseRevision") == task["execution_case_revision"]
        and item.get("manifest") == expected_manifest
        and item.get("manifestSha256") == task["_case_manifest"]["sha256"]
    ]
    if len(matching) != 1:
        raise ValueError("package case index does not bind the selected case")
    candidate_task = case_manifest.get("candidateTask")
    if not isinstance(candidate_task, dict):
        raise ValueError("packaged candidate task is missing")
    candidate_task_path = package_root / _safe_relative_path(
        candidate_task.get("path"),
        "packaged candidate task path",
    )
    if (
        candidate_task_path != task["_candidate_task"]["path"]
        or candidate_task.get("sha256") != task["_candidate_task"]["sha256"]
    ):
        raise ValueError("packaged candidate task conflicts with the manifest")
    return package_manifest, case_manifest


def _copy_declared_authority(
    source_root: Path,
    destination_root: Path,
    case_manifest: dict,
) -> None:
    hidden_authority = case_manifest.get("hiddenAuthority")
    if not isinstance(hidden_authority, dict):
        raise ValueError("hidden authoring authority is missing")
    artifacts = hidden_authority.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("hidden authoring authority is missing")
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("hidden authoring authority is invalid")
        source_relative = _safe_relative_path(
            item.get("path"),
            "hidden authority path",
        )
        expected = _require_sha256(
            item.get("sha256"),
            "hidden authority digest",
        )
        source = source_root / source_relative
        if not source.is_file() or source.is_symlink() or digest(source) != expected:
            raise ValueError("hidden authority does not match its manifest")
        if source_relative.parts[:2] != ("hidden", "authority"):
            continue
        destination_relative = Path(*source_relative.parts[2:])
        if destination_relative.name in {
            "case-manifest.json",
            "bundle-manifest.json",
        }:
            continue
        destination = destination_root / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _reconstruct_task(corpus: Path, task: dict) -> dict:
    _, case_manifest = _verify_declared_package_files(task)
    case_root = corpus / "cases" / task["case_id"]
    if case_root.exists():
        raise ValueError("reconstructed task already exists")
    case_root.mkdir(parents=True)
    _copy_declared_authority(task["_package_root"], case_root, case_manifest)
    definition = read_json(case_root / "case.json")
    phases = definition.get("phases")
    if (
        not isinstance(phases, list)
        or len(phases) != 1
        or phases[0].get("resume") is not False
    ):
        raise ValueError("reconstructed task must have one non-resumed phase")
    phase = phases[0]
    prompt_path = _safe_relative_path(
        phase.get("prompt_file"),
        "phase prompt path",
    )
    prompt_destination = case_root / prompt_path
    prompt_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(task["_candidate_task"]["path"], prompt_destination)
    repository_task = definition.get("repository_task")
    if not isinstance(repository_task, dict):
        raise ValueError("repository task authority is missing")
    snapshot_path = _safe_relative_path(
        repository_task.get("snapshot_dir"),
        "repository snapshot path",
    )
    candidate_sources = case_manifest.get("candidateSources")
    if not isinstance(candidate_sources, list) or len(candidate_sources) != 1:
        raise ValueError("migration requires one packaged source workspace")
    packaged_source = candidate_sources[0]
    if not isinstance(packaged_source, dict):
        raise ValueError("packaged source identity is invalid")
    source_bundle = task["_package_root"] / _safe_relative_path(
        packaged_source.get("bundle"),
        "packaged source bundle path",
    )
    source_bundle_sha256 = _require_sha256(
        packaged_source.get("bundleSha256"),
        "packaged source bundle digest",
    )
    if (
        not source_bundle.is_file()
        or source_bundle.is_symlink()
        or digest(source_bundle) != source_bundle_sha256
    ):
        raise ValueError("packaged source bundle does not match its manifest")
    _safe_extract(source_bundle, case_root / snapshot_path)
    alias_normalizations = _materialize_source_aliases(
        case_root / snapshot_path,
        source_bundle_sha256,
    )
    alias_correspondence = _alias_correspondence(
        task,
        case_root / snapshot_path,
        case_manifest,
        alias_normalizations,
    )
    evidence_path = _safe_relative_path(
        phase.get("evidence_dir"),
        "phase evidence path",
    )
    evidence_root = case_root / evidence_path
    evidence_root.mkdir(parents=True, exist_ok=True)
    packaged_sources = []
    for source in candidate_sources:
        if not isinstance(source, dict):
            raise ValueError("packaged source identity is invalid")
        packaged_sources.append({
            "repository_id": _require_text(
                source.get("repositoryId"),
                "packaged repository ID",
            ),
            "commit": _require_text(
                source.get("commit"),
                "packaged source commit",
            ),
            "tree": _require_text(
                source.get("tree"),
                "packaged source tree",
            ),
            "bundle_path": _require_text(
                source.get("bundle"),
                "packaged source bundle path",
            ),
            "bundle_sha256": _require_sha256(
                source.get("bundleSha256"),
                "packaged source bundle digest",
            ),
        })
    write_json(evidence_root / "packaged-source-identity.json", {
        "schema_version": 1,
        "source_case_key": task["source_case_key"],
        "original_task_revision": task["original_task_revision"],
        "execution_case_revision": task["execution_case_revision"],
        "authoring_source_revision": repository_task["source_revision"],
        "packaged_sources": packaged_sources,
        "alias_normalizations": alias_normalizations,
    })
    corpus_manifest = read_json(corpus / "corpus.json")
    corpus_manifest["cases"].append(task["case_id"])
    corpus_manifest["cases"].sort()
    write_json(corpus / "corpus.json", corpus_manifest)
    frozen = freeze_case(corpus, task["case_id"], replace=False)
    verify_case(corpus, task["case_id"])
    revision = digest(frozen / "case-manifest.json")
    for record in alias_normalizations:
        record["reconstructed_frozen_revision"] = revision
    return {
        "case_id": task["case_id"],
        "case_revision": revision,
        "original_task_revision": task["original_task_revision"],
        "execution_case_revision": task["execution_case_revision"],
        "authoring_source_revision": repository_task["source_revision"],
        "packaged_sources": packaged_sources,
        "alias_normalizations": alias_normalizations,
        "alias_correspondence": alias_correspondence,
    }


def _skill_snapshot(corpus: Path, treatment: dict, staging: Path) -> dict:
    plugin = staging / treatment["role"] / "plugin"
    skill_root = plugin / "skills" / "development-loop"
    skill_root.mkdir(parents=True)
    shutil.copyfile(treatment["_skill_path"], skill_root / "SKILL.md")
    return capture_skill_snapshot(corpus, plugin, ["development-loop"])


def _event_id(migration_id: str, kind: str, subject: str) -> str:
    return hashlib.sha256(
        f"{migration_id}:{kind}:{subject}".encode("utf-8")
    ).hexdigest()[:32]


def _writer(migration_id: str, kind: str) -> dict:
    identifier = migration_id
    if kind == "session":
        value = hashlib.sha256(
            f"{migration_id}:session".encode("utf-8")
        ).hexdigest()
        identifier = (
            f"{value[:8]}-{value[8:12]}-{value[12:16]}-"
            f"{value[16:20]}-{value[20:32]}"
        )
    return {
        "kind": kind,
        "id": identifier,
        "generation": hashlib.sha256(
            f"{migration_id}:writer".encode("utf-8")
        ).hexdigest()[:32],
    }


def _experiment_payload(
    manifest: dict,
    snapshot: dict,
    reconstructed: dict[str, dict],
) -> tuple[dict, dict[str, dict]]:
    admitted_skills = [{
        "name": item["name"],
        "evaluator_fingerprint": item["evaluator_skill_identity"],
    } for item in snapshot["skills"]]
    treatment_records = []
    treatment_by_id = {}
    for treatment in manifest["treatments"]:
        record = {
            "treatment_id": treatment["treatment_id"],
            "role": treatment["role"],
            "hypothesis": treatment["hypothesis"],
            "snapshot_id": snapshot["snapshot_id"],
            "treatment_identity": json_fingerprint({
                "migration_id": manifest["migration_id"],
                "treatment_id": treatment["treatment_id"],
                "skill_file_sha256": treatment["skill_file_sha256"],
            }),
            "content_fingerprint": treatment["skill_file_sha256"],
            "target_skill_identities": admitted_skills,
            "provenance_ids": [
                f"historical-treatment-{treatment['treatment_id']}",
                f"skill-file-{treatment['skill_file_sha256']}",
            ],
        }
        record["provenance_ids"].sort()
        treatment_records.append(record)
        treatment_by_id[treatment["treatment_id"]] = record
    attempts = []
    for task in manifest["tasks"]:
        frozen = reconstructed[task["case_id"]]
        for attempt in task["attempts"]:
            attempts.append({
                "attempt_id": attempt["attempt_id"],
                "case_id": task["case_id"],
                "case_revision": frozen["case_revision"],
                "treatment_id": attempt["treatment_id"],
                "repetition": attempt["repetition"],
                "target_os": manifest["experiment"]["target_os"],
                "architecture": manifest["experiment"]["architecture"],
                "route": manifest["experiment"]["route"],
                "candidate_model": manifest["experiment"]["candidate_model"],
                "snapshot_id": snapshot["snapshot_id"],
            })
    attempts.sort(key=lambda item: item["attempt_id"])
    treatment_records.sort(key=lambda item: item["treatment_id"])
    cases = [{
        "case_id": task["case_id"],
        "case_revision": reconstructed[task["case_id"]]["case_revision"],
    } for task in manifest["tasks"]]
    cases.sort(key=lambda item: item["case_id"])
    payload = {
        "title": manifest["experiment"]["title"],
        "summary": manifest["experiment"]["summary"],
        "snapshot_id": snapshot["snapshot_id"],
        "cases": cases,
        "candidate_model": manifest["experiment"]["candidate_model"],
        "candidate_timeout_seconds": manifest["experiment"][
            "candidate_timeout_seconds"
        ],
        "target_os": manifest["experiment"]["target_os"],
        "architecture": manifest["experiment"]["architecture"],
        "route": manifest["experiment"]["route"],
        "treatments": treatment_records,
        "attempts": attempts,
        "selection_rule": {
            "metrics": [{
                "name": "terminal_pass_rate",
                "direction": "descending",
            }],
            "coverage": [
                {"kind": "all_planned_attempts_terminal", "value": None},
                {"kind": "field_present", "value": "terminal_status"},
                {
                    "kind": "minimum_valid_repetitions_per_treatment",
                    "value": 1,
                },
            ],
            "disqualifiers": [{
                "kind": "product_failure",
                "field": None,
                "bound": None,
            }],
        },
    }
    return payload, treatment_by_id


def _project_declaration(
    manifest: dict,
    reconstructed: dict[str, dict],
    experiment_fingerprint: str,
) -> dict:
    tasks = []
    bindings = []
    candidate_id = next(
        item["treatment_id"]
        for item in manifest["treatments"]
        if item["role"] == "candidate"
    )
    for task in manifest["tasks"]:
        task_id = task["source_case_key"]
        tasks.append({
            "task_id": task_id,
            "title": task["title"],
            "summary": task["summary"],
            "qualification": {
                "kind": "exact_experiment_population",
                "required_roles": [task["role"]],
                "experiment_id": manifest["experiment"]["experiment_id"],
                "experiment_fingerprint": experiment_fingerprint,
                "treatment_id": candidate_id,
                "required_passes_per_case": task["qualification"][
                    "required_passes"
                ],
            },
        })
        bindings.append({
            "binding_id": f"historical-{task_id}",
            "case_id": task["case_id"],
            "case_revision": reconstructed[task["case_id"]]["case_revision"],
            "task_id": task_id,
            "role": task["role"],
            "safe_progress": None,
        })
    project = manifest["project"]
    return canonical_project_declaration({
        "schema_version": 1,
        "supersedes": None,
        "project_id": project["project_id"],
        "title": project["title"],
        "goal": project["goal"],
        "target_skills": [project["target_skill"]],
        "tasks": tasks,
        "case_bindings": bindings,
        "holdout_requirements": [],
    })


def _result_package_identities(
    archive: Path,
    fallback_case_manifest_sha256: str,
) -> dict:
    package = _read_tar_json(
        archive,
        (
            "evidence/macos-stage/package-identity.json",
            "evidence/package-identity.json",
        ),
        "candidate package identity",
    )
    hidden = _read_tar_json(
        archive,
        (
            "evidence/macos-stage/hidden-package-identity.json",
            "evidence/hidden-package-identity.json",
        ),
        "full package identity",
    )
    try:
        case_manifest = _read_tar_bytes(
            archive,
            (
                "run-root/judge-input/gpt-6.1-sol/case/case-manifest.json",
                "run-root/judge-input/claude-sonnet-5.5/case/case-manifest.json",
            ),
            "execution case manifest",
        )
        case_manifest_sha256 = hashlib.sha256(case_manifest).hexdigest()
    except ValueError as error:
        if str(error) != "execution case manifest is missing":
            raise
        case_manifest_sha256 = fallback_case_manifest_sha256
    return {
        "package_archive_sha256": _require_sha256(
            hidden.get("sha256"),
            "full package identity",
        ),
        "candidate_package_archive_sha256": _require_sha256(
            package.get("sha256"),
            "candidate package identity",
        ),
        "package_manifest_sha256": case_manifest_sha256,
    }


def _result_payload(
    manifest: dict,
    task: dict,
    attempt: dict,
    reconstructed: dict,
    treatment: dict,
    plan_fingerprint: str,
) -> dict:
    source = read_json(attempt["_result_source"]["path"])
    if (
        source.get("attempt_id") != attempt["attempt_id"]
        or source.get("case_key") != task["source_case_key"]
        or source.get("outcome") != attempt["outcome"]
    ):
        raise ValueError("historical result identity conflicts with the manifest")
    verification = source.get("verification")
    if not isinstance(verification, dict):
        raise ValueError("historical result verification is missing")
    dispatches = source.get("strict_inventory", {}).get("dispatches")
    if not isinstance(dispatches, dict) or len(dispatches) != 1:
        raise ValueError("historical dispatch identity is ambiguous")
    dispatch = next(iter(dispatches.values()))
    historical_attempt = dispatch.get("attempt")
    if not isinstance(historical_attempt, dict):
        raise ValueError("historical dispatch attempt is missing")
    if historical_attempt.get("attemptId") != attempt["attempt_id"]:
        raise ValueError("historical dispatch attempt conflicts")
    package_identity = _result_package_identities(
        attempt["_retained_archive"]["path"],
        task["_case_manifest"]["sha256"],
    )
    image_identity = json_fingerprint({
        key: historical_attempt.get(key)
        for key in (
            "imageId",
            "imageSha256",
            "imageAsset",
            "imageRelease",
            "imageBytes",
        )
    })
    dependency_identity = json_fingerprint({
        key: historical_attempt.get(key)
        for key in (
            "dependencySha256",
            "dependencyAsset",
            "dependencyRelease",
            "dependencyBytes",
            "dependencyArchiveRoot",
            "dependencyWorkspace",
        )
    })
    judges = verification.get("judges")
    if not isinstance(judges, dict):
        raise ValueError("historical judge outcomes are incomplete")
    verdicts = [judges[name] for name in sorted(judges)]
    if any(item not in TERMINAL_OUTCOMES for item in verdicts):
        raise ValueError("historical judge outcome is invalid")
    passed = attempt["outcome"] == "PASS"
    selection_fields = {
        "terminal_status": attempt["outcome"],
        "deterministic_target_pass": verification.get("target_passed"),
        "deterministic_regression_pass": verification.get("regression_passed"),
        "product_pass": verification.get("product_passed"),
        "independent_behavioral_verdicts": verdicts,
    }
    if any(
        not isinstance(selection_fields[field], bool)
        for field in (
            "deterministic_target_pass",
            "deterministic_regression_pass",
            "product_pass",
        )
    ):
        raise ValueError("historical deterministic outcomes are incomplete")
    return {
        "attempt": {
            "attempt_id": attempt["attempt_id"],
            "case_id": task["case_id"],
            "case_revision": reconstructed["case_revision"],
            "treatment_id": attempt["treatment_id"],
            "repetition": attempt["repetition"],
        },
        "execution": {
            "plan_fingerprint": plan_fingerprint,
            "candidate_model": manifest["experiment"]["candidate_model"],
            "candidate_timeout_seconds": manifest["experiment"][
                "candidate_timeout_seconds"
            ],
            "treatment_fingerprint": treatment["content_fingerprint"],
            "target_skill_identities": treatment["target_skill_identities"],
            "target_os": manifest["experiment"]["target_os"],
            "architecture": manifest["experiment"]["architecture"],
            "route": manifest["experiment"]["route"],
            "grading_route": historical_attempt.get("gradingRoute"),
            **package_identity,
            "image_identity": image_identity,
            "dependency_identity": dependency_identity,
        },
        "terminal_status": attempt["outcome"],
        "summaries": {
            "candidate": (
                "Historical candidate execution completed"
                if passed else "Historical candidate execution did not pass"
            ),
            "deterministic": "Historical deterministic checks preserved",
            "product": "Historical product check preserved",
            "judge": (
                "Historical independent judgments preserved"
                if verdicts else None
            ),
        },
        "first_stage_id": f"historical-{attempt['attempt_id']}",
        "source_lineage": None,
        "candidate_rerun": bool(verification.get("candidate_rerun", False)),
        "effective_result_id": (
            f"historical-result-{attempt['attempt_id']}"
        ),
        "selection_fields": selection_fields,
        "source_ids": sorted([
            f"result-source-{attempt['_result_source']['sha256']}",
            f"retained-archive-{attempt['_retained_archive']['sha256']}",
        ] + (
            [f"proof-source-{attempt['_proof_source']['sha256']}"]
            if attempt["_proof_source"] is not None
            else []
        )),
    }


def _recorded_artifacts(output_root: Path, state_root: Path, project_id: str,
                        campaign_id: str, receipt_path: Path) -> list[dict]:
    roots = [
        output_root,
        state_root / "campaigns" / f"{campaign_id}.json",
        state_root / "projects" / project_id,
    ]
    paths = []
    for root in roots:
        if root.is_file():
            paths.append(root)
        elif root.is_dir():
            paths.extend(
                path for path in root.rglob("*")
                if path.is_file() and not path.is_symlink()
            )
    return [{
        "path": str(path),
        "sha256": digest(path),
    } for path in sorted(set(paths)) if path != receipt_path]


def _verify_receipt(receipt_path: Path, manifest_sha256: str) -> dict:
    receipt = read_json(receipt_path)
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("migration receipt schema is unsupported")
    if receipt.get("manifest_sha256") != manifest_sha256:
        raise ValueError("migration receipt belongs to different input")
    for artifact in receipt.get("artifacts", []):
        reference = _file_reference(artifact, "receipt artifact")
        if reference["path"] == receipt_path:
            raise ValueError("receipt cannot attest itself")
    output_root = Path(receipt.get("output_root", ""))
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("migration output root is unavailable")
    expected_output = {
        Path(item["path"])
        for item in receipt.get("artifacts", [])
        if Path(item["path"]).is_relative_to(output_root)
    } | {receipt_path}
    actual_output = set()
    for path in output_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("migration output contains a symlink")
        if path.is_file():
            actual_output.add(path)
    if actual_output != expected_output:
        raise ValueError("migration output inventory changed")
    return receipt


def _cleanup_failed_migration(
    output_root: Path,
    state_root: Path,
    project_id: str,
    registration: dict | None,
    project_fingerprint: str | None,
) -> None:
    if not output_root.exists():
        return
    with locked(output_root / ".skill-evaluation-ui" / "campaign.lock"):
        if registration is not None:
            campaign_id = registration["campaign_id"]
            project_root = state_root / "projects" / project_id
            with locked(state_root / "projects" / f"{project_id}.lock"):
                expected = {
                    project_root / f"{campaign_id}.json",
                }
                if project_fingerprint is not None:
                    expected.add(
                        project_root
                        / "declarations"
                        / campaign_id
                        / f"{project_fingerprint}.json"
                    )
                for path in expected:
                    if path.exists() and not path.is_symlink():
                        path.unlink()
                if project_root.exists():
                    for path in sorted(
                        (
                            item for item in project_root.rglob("*")
                            if item.is_dir()
                        ),
                        reverse=True,
                    ):
                        try:
                            path.rmdir()
                        except OSError:
                            pass
                    try:
                        project_root.rmdir()
                    except OSError:
                        pass
            campaign_path = state_root / "campaigns" / f"{campaign_id}.json"
            if campaign_path.exists():
                current = regular_json(
                    campaign_path,
                    "partial campaign registration",
                )
                if (
                    Path(current.get("corpus_root", "")).resolve()
                    == output_root.resolve()
                ):
                    campaign_path.unlink()
        shutil.rmtree(output_root)


def migrate(manifest_path: Path) -> dict:
    normalized = _normalize_manifest(manifest_path)
    manifest = normalized["manifest"]
    output_root = normalized["output_root"]
    state_root = normalized["state_root"]
    receipt_path = output_root / ".skill-evaluation-ui" / RECEIPT_NAME
    if receipt_path.is_file():
        return _verify_receipt(receipt_path, normalized["manifest_sha256"])
    if output_root.exists():
        raise ValueError("output root exists without a migration receipt")
    project_id = manifest["project"]["project_id"]
    project_root = state_root / "projects" / project_id
    if project_root.exists():
        raise ValueError("project registration already exists")
    pre_index = project_index_projection(state_root)
    staging = output_root.parent / f".{output_root.name}.migration-staging"
    if staging.exists():
        raise ValueError("migration staging path already exists")
    staging.mkdir(parents=True)
    registration = None
    project_fingerprint = None
    try:
        init_corpus(output_root)
        reconstructed = {
            task["case_id"]: _reconstruct_task(output_root, task)
            for task in manifest["tasks"]
        }
        create_campaign(staging / "state", output_root)
        candidate = next(
            item for item in manifest["treatments"]
            if item["role"] == "candidate"
        )
        snapshot = _skill_snapshot(output_root, candidate, staging)
        payload, treatments = _experiment_payload(
            manifest,
            snapshot,
            reconstructed,
        )
        plan_fingerprint = experiment_plan_fingerprint(payload)
        project = _project_declaration(
            manifest,
            reconstructed,
            plan_fingerprint,
        )
        project_fingerprint = project_declaration_fingerprint(project)
        write_json(output_root / "evaluation-project.json", project)
        registration = create_campaign(state_root, output_root)
        session_writer = _writer(manifest["migration_id"], "session")
        coordinator_writer = _writer(
            manifest["migration_id"],
            "distributed_coordinator",
        )
        emit_lineage_event(
            output_root,
            campaign_id=registration["campaign_id"],
            writer=session_writer,
            snapshot_id=snapshot["snapshot_id"],
            roles=["integrated"],
            parents=[],
            summary=(
                "Integrated the historically evaluated candidate as the "
                "qualification subject; no winner was selected"
            ),
            event_id=_event_id(
                manifest["migration_id"],
                "lineage",
                snapshot["snapshot_id"],
            ),
            observed_at=manifest["recorded_at"],
            recorded_at=manifest["recorded_at"],
        )
        emit_experiment_activity_event(
            output_root,
            campaign_id=registration["campaign_id"],
            writer=session_writer,
            event_type="experiment_declared",
            experiment_id=manifest["experiment"]["experiment_id"],
            experiment_fingerprint=plan_fingerprint,
            payload=payload,
            event_id=_event_id(
                manifest["migration_id"],
                "experiment",
                manifest["experiment"]["experiment_id"],
            ),
            observed_at=manifest["recorded_at"],
            recorded_at=manifest["recorded_at"],
        )
        terminal_count = 0
        for task in manifest["tasks"]:
            for attempt in task["attempts"]:
                if attempt["outcome"] not in TERMINAL_OUTCOMES:
                    continue
                result = _result_payload(
                    manifest,
                    task,
                    attempt,
                    reconstructed[task["case_id"]],
                    treatments[attempt["treatment_id"]],
                    plan_fingerprint,
                )
                emit_experiment_activity_event(
                    output_root,
                    campaign_id=registration["campaign_id"],
                    writer=coordinator_writer,
                    event_type="distributed_result_recorded",
                    experiment_id=manifest["experiment"]["experiment_id"],
                    experiment_fingerprint=plan_fingerprint,
                    attempt_id=attempt["attempt_id"],
                    payload=result,
                    event_id=_event_id(
                        manifest["migration_id"],
                        "result",
                        attempt["attempt_id"],
                    ),
                    observed_at=(
                        attempt["terminal_timestamp"]
                        or manifest["recorded_at"]
                    ),
                    recorded_at=manifest["recorded_at"],
                )
                terminal_count += 1
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "migration_id": manifest["migration_id"],
            "manifest_path": str(manifest_path),
            "manifest_sha256": normalized["manifest_sha256"],
            "output_root": str(output_root),
            "state_root": str(state_root),
            "project_id": project_id,
            "project_declaration_sha256": digest(
                output_root / "evaluation-project.json"
            ),
            "campaign_id": registration["campaign_id"],
            "snapshot_id": snapshot["snapshot_id"],
            "experiment_id": manifest["experiment"]["experiment_id"],
            "experiment_fingerprint": plan_fingerprint,
            "task_revisions": reconstructed,
            "terminal_results": terminal_count,
            "pre_migration_project_index": pre_index,
            "artifacts": [],
        }
        receipt["artifacts"] = _recorded_artifacts(
            output_root,
            state_root,
            project_id,
            registration["campaign_id"],
            receipt_path,
        )
        write_json(receipt_path, receipt)
        return receipt
    except Exception as error:
        try:
            _cleanup_failed_migration(
                output_root,
                state_root,
                project_id,
                registration,
                project_fingerprint,
            )
        except Exception as cleanup_error:
            raise RuntimeError(
                f"migration failed and cleanup was incomplete: "
                f"{cleanup_error}"
            ) from error
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def rollback(receipt_path: Path) -> dict:
    receipt = read_json(receipt_path)
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("migration receipt schema is unsupported")
    output_root = Path(receipt["output_root"])
    state_root = Path(receipt["state_root"])
    project_id = receipt["project_id"]
    campaign_id = receipt["campaign_id"]
    _verify_receipt(receipt_path, receipt["manifest_sha256"])
    project_root = state_root / "projects" / project_id
    campaign_path = state_root / "campaigns" / f"{campaign_id}.json"
    with locked(output_root / ".skill-evaluation-ui" / "campaign.lock"):
        with locked(state_root / "projects" / f"{project_id}.lock"):
            _verify_receipt(receipt_path, receipt["manifest_sha256"])
            pre_migration_ids = {
                item["project_id"]
                for item in receipt["pre_migration_project_index"]["projects"]
            }
            if project_id in pre_migration_ids:
                raise ValueError(
                    "migration project existed in the pre-migration index"
                )
            current_index = project_index_projection(state_root)
            current_ids = {
                item["project_id"] for item in current_index["projects"]
            }
            if project_id not in current_ids:
                raise ValueError("migration project is absent from the index")
            owned = {Path(item["path"]) for item in receipt["artifacts"]}
            for path in (project_root, campaign_path):
                if path.is_file() and path not in owned:
                    raise ValueError("rollback encountered a foreign registration")
                if path.is_dir():
                    foreign = [
                        item for item in path.rglob("*")
                        if (item.is_file() or item.is_symlink()) and item not in owned
                    ]
                    if foreign:
                        raise ValueError(
                            "rollback encountered foreign project artifacts"
                        )
            if campaign_path.exists():
                campaign_path.unlink()
            if project_root.exists():
                shutil.rmtree(project_root)
            remaining_ids = {
                item["project_id"]
                for item in project_index_projection(state_root)["projects"]
            }
            if remaining_ids != current_ids - {project_id}:
                raise ValueError(
                    "rollback changed an unrelated project registration"
                )
            shutil.rmtree(output_root)
    return {
        "schema_version": SCHEMA_VERSION,
        "migration_id": receipt["migration_id"],
        "rolled_back": True,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="One-time immutable skill-evaluation history migration",
    )
    subparsers = result.add_subparsers(dest="command", required=True)
    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--manifest", type=Path, required=True)
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--receipt", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "migrate":
        result = migrate(args.manifest)
    else:
        result = rollback(args.receipt)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
