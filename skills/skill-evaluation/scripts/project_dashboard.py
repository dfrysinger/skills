"""Validated project declarations and project-level dashboard projections."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import evaluation_history
from dashboard_state import (
    atomic_json,
    campaign_registration,
    ensure_state_root,
    extension_records,
    locked,
    parse_instant,
    read_skill_snapshot,
    regular_json,
    validate_campaign_id,
    validate_safe_id,
    validate_sha256,
    write_exclusive,
)
from skill_eval import digest, frozen_case_path, json_fingerprint, load_corpus


PROJECT_FILE = "evaluation-project.json"
PROJECT_FIELDS = {
    "schema_version",
    "supersedes",
    "project_id",
    "title",
    "goal",
    "target_skills",
    "tasks",
    "case_bindings",
    "holdout_requirements",
}
TASK_FIELDS = {"task_id", "title", "summary", "qualification"}
QUALIFICATION_FIELDS = {
    "kind",
    "required_roles",
    "minimum_terminal_repetitions_per_case",
    "required_passes_per_case",
}
BINDING_FIELDS = {
    "binding_id",
    "case_id",
    "case_revision",
    "task_id",
    "role",
    "safe_progress",
}
HOLDOUT_FIELDS = {
    "holdout_set_id",
    "summary",
    "required_claim",
    "task_ids",
    "authority_id",
}
PROJECT_REGISTRATION_FIELDS = {
    "schema_version",
    "project_id",
    "campaign_id",
    "declaration_sha256",
}
RUN_START_FIELDS = {
    "schema_version",
    "run_id",
    "project_id",
    "project_declaration_sha256",
    "campaign_id",
    "launcher_kind",
    "run_goal",
    "requested_plugin_path",
    "treatment_reference",
    "arm",
    "task_ids",
    "case_bindings",
    "planned_workers",
    "planned_attempts",
    "lease_generation",
    "started_at",
}
RUN_LEASE_FIELDS = {
    "schema_version",
    "run_id",
    "generation",
    "renewed_at",
    "expires_at",
}
SUITE_FAILURE_FIELDS = {
    "schema_version",
    "run_id",
    "stage",
    "error_type",
    "message",
    "failed_at",
}
PROJECT_ROLES = {"published", "integrated", "released"}


def _bounded_text(value: object, label: str, limit: int = 400) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} is invalid")
    return value


def _positive_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} is invalid")
    return value


def _sorted_unique_strings(
    value: object,
    label: str,
    *,
    allowed: set[str] | None = None,
) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) for item in value)
        or value != sorted(set(value))
        or (allowed is not None and set(value) - allowed)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _exact_object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} is invalid")
    return value


def _canonical_rows(
    value: object,
    fields: set[str],
    identifier: str,
    label: str,
) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{label} is invalid")
    rows = [_exact_object(item, fields, label) for item in value]
    identifiers = [item.get(identifier) for item in rows]
    for item in identifiers:
        validate_safe_id(item, identifier.replace("_", " "))
    if identifiers != sorted(set(identifiers)):
        raise ValueError(f"{label} must be sorted with unique IDs")
    return rows


def canonical_project_declaration(value: object) -> dict:
    declaration = _exact_object(value, PROJECT_FIELDS, "project declaration")
    if declaration.get("schema_version") != 1:
        raise ValueError("unsupported project declaration schema")
    validate_sha256(declaration.get("supersedes"), "project supersedes")
    validate_safe_id(declaration.get("project_id"), "project ID")
    title = _bounded_text(declaration.get("title"), "project title", 160)
    goal = _bounded_text(declaration.get("goal"), "project goal", 600)
    target_skills = _sorted_unique_strings(
        declaration.get("target_skills"),
        "project target skills",
    )
    for skill in target_skills:
        validate_safe_id(skill, "target skill")

    tasks = _canonical_rows(
        declaration.get("tasks"),
        TASK_FIELDS,
        "task_id",
        "project tasks",
    )
    if not tasks:
        raise ValueError("project tasks are empty")
    normalized_tasks = []
    for task in tasks:
        qualification = _exact_object(
            task.get("qualification"),
            QUALIFICATION_FIELDS,
            "task qualification",
        )
        if qualification.get("kind") != "all_bound_cases":
            raise ValueError("unsupported task qualification kind")
        roles = _sorted_unique_strings(
            qualification.get("required_roles"),
            "qualification roles",
            allowed={"development", "regression"},
        )
        minimum = _positive_integer(
            qualification.get("minimum_terminal_repetitions_per_case"),
            "minimum terminal repetitions",
        )
        required = _positive_integer(
            qualification.get("required_passes_per_case"),
            "required passes",
        )
        if required > minimum:
            raise ValueError("required passes exceed terminal repetitions")
        normalized_tasks.append({
            "task_id": task["task_id"],
            "title": _bounded_text(task.get("title"), "task title", 160),
            "summary": _bounded_text(task.get("summary"), "task summary", 400),
            "qualification": {
                "kind": "all_bound_cases",
                "required_roles": roles,
                "minimum_terminal_repetitions_per_case": minimum,
                "required_passes_per_case": required,
            },
        })

    bindings = _canonical_rows(
        declaration.get("case_bindings"),
        BINDING_FIELDS,
        "binding_id",
        "project case bindings",
    )
    if not bindings:
        raise ValueError("project case bindings are empty")
    task_ids = {item["task_id"] for item in normalized_tasks}
    normalized_bindings = []
    bound_cases = {}
    for binding in bindings:
        validate_safe_id(binding.get("case_id"), "case ID")
        validate_sha256(binding.get("case_revision"), "case revision")
        validate_safe_id(binding.get("task_id"), "task ID")
        if binding["task_id"] not in task_ids:
            raise ValueError("case binding references an unknown task")
        if binding.get("role") not in {"development", "regression"}:
            raise ValueError("case binding role is invalid")
        if binding.get("safe_progress") is not None:
            raise ValueError(
                "safe progress declarations are not supported in Slice A"
            )
        prior = bound_cases.setdefault(binding["case_id"], binding["task_id"])
        if prior != binding["task_id"]:
            raise ValueError("one case is bound to multiple tasks")
        normalized_bindings.append({
            "binding_id": binding["binding_id"],
            "case_id": binding["case_id"],
            "case_revision": binding["case_revision"],
            "task_id": binding["task_id"],
            "role": binding["role"],
            "safe_progress": None,
        })

    required_cases = {
        binding["task_id"]
        for binding in normalized_bindings
        if binding["role"]
        in next(
            item["qualification"]["required_roles"]
            for item in normalized_tasks
            if item["task_id"] == binding["task_id"]
        )
    }
    if required_cases != task_ids:
        raise ValueError("every task requires at least one bound case")

    holdouts = _canonical_rows(
        declaration.get("holdout_requirements"),
        HOLDOUT_FIELDS,
        "holdout_set_id",
        "project holdout requirements",
    )
    normalized_holdouts = []
    for holdout in holdouts:
        referenced_tasks = _sorted_unique_strings(
            holdout.get("task_ids"),
            "holdout task IDs",
        )
        if set(referenced_tasks) - task_ids:
            raise ValueError("holdout requirement references an unknown task")
        validate_safe_id(holdout.get("authority_id"), "holdout authority ID")
        normalized_holdouts.append({
            "holdout_set_id": holdout["holdout_set_id"],
            "summary": _bounded_text(
                holdout.get("summary"),
                "holdout summary",
                400,
            ),
            "required_claim": _bounded_text(
                holdout.get("required_claim"),
                "holdout required claim",
                160,
            ),
            "task_ids": referenced_tasks,
            "authority_id": holdout["authority_id"],
        })

    return {
        "schema_version": 1,
        "supersedes": declaration["supersedes"],
        "project_id": declaration["project_id"],
        "title": title,
        "goal": goal,
        "target_skills": target_skills,
        "tasks": normalized_tasks,
        "case_bindings": normalized_bindings,
        "holdout_requirements": normalized_holdouts,
    }


def project_declaration_fingerprint(declaration: dict) -> str:
    return json_fingerprint(canonical_project_declaration(declaration))


def task_fingerprint(task: dict) -> str:
    return json_fingerprint(task)


def binding_fingerprint(binding: dict) -> str:
    return json_fingerprint(binding)


def project_declaration_path(corpus_root: Path) -> Path:
    return corpus_root.expanduser().resolve() / PROJECT_FILE


def load_project_declaration(corpus_root: Path) -> dict | None:
    path = project_declaration_path(corpus_root)
    if not path.exists():
        return None
    return canonical_project_declaration(
        regular_json(path, "evaluation project declaration")
    )


def _project_archive_root(corpus_root: Path, *, create: bool) -> Path:
    root = (
        corpus_root.expanduser().resolve()
        / ".skill-evaluation-ui"
        / "projects"
    )
    if not create:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("project archive path is unavailable")
        return root
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("project archive path is invalid")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def archived_project_declaration(corpus_root: Path, fingerprint: str) -> dict:
    validate_sha256(fingerprint, "project declaration fingerprint")
    path = (
        _project_archive_root(corpus_root, create=False)
        / "declarations"
        / f"{fingerprint}.json"
    )
    declaration = canonical_project_declaration(
        regular_json(path, "archived project declaration")
    )
    if project_declaration_fingerprint(declaration) != fingerprint:
        raise ValueError("archived project declaration fingerprint changed")
    return declaration


def _validate_additive_revision(previous: dict, current: dict) -> None:
    for field in ("project_id", "title", "goal", "target_skills"):
        if previous[field] != current[field]:
            raise ValueError(f"project revision changed immutable field: {field}")
    for field, identifier in (
        ("tasks", "task_id"),
        ("case_bindings", "binding_id"),
        ("holdout_requirements", "holdout_set_id"),
    ):
        previous_ids = {item[identifier] for item in previous[field]}
        current_ids = {item[identifier] for item in current[field]}
        missing = sorted(previous_ids - current_ids)
        if missing:
            raise ValueError(
                f"project revision omitted existing {identifier}: {missing}"
            )


def register_project_declaration(
    state_root: Path,
    corpus_root: Path,
    campaign_id: str,
) -> dict | None:
    declaration = load_project_declaration(corpus_root)
    if declaration is None:
        return None
    state_root = ensure_state_root(state_root)
    campaign_id = validate_campaign_id(campaign_id)
    archive = _project_archive_root(corpus_root, create=True)
    declarations = archive / "declarations"
    declarations.mkdir(mode=0o700, exist_ok=True)
    fingerprint = project_declaration_fingerprint(declaration)
    current_path = archive / "current.json"
    with locked(archive / "project.lock"):
        prior = None
        if current_path.exists():
            pointer = regular_json(current_path, "current project declaration")
            if set(pointer) != {"schema_version", "declaration_sha256"}:
                raise ValueError("current project declaration pointer is invalid")
            prior_fingerprint = validate_sha256(
                pointer.get("declaration_sha256"),
                "current project declaration fingerprint",
            )
            prior = archived_project_declaration(corpus_root, prior_fingerprint)
            if fingerprint != prior_fingerprint:
                if declaration["supersedes"] != prior_fingerprint:
                    raise ValueError(
                        "project declaration supersedes stale revision"
                    )
                _validate_additive_revision(prior, declaration)
        elif declaration["supersedes"] is not None:
            raise ValueError("initial project declaration cannot supersede")

        corpus = load_corpus(corpus_root)
        actual_skills = sorted({
            regular_json(
                corpus_root / "cases" / case_id / "case.json",
                f"case {case_id}",
            ).get("target_skill")
            for case_id in corpus["cases"]
        })
        if actual_skills != declaration["target_skills"]:
            raise ValueError("project target skills do not match corpus cases")
        bound_cases = [
            item["case_id"] for item in declaration["case_bindings"]
        ]
        if sorted(bound_cases) != sorted(corpus["cases"]):
            raise ValueError(
                "every corpus case must have exactly one project binding"
            )
        for binding in declaration["case_bindings"]:
            actual = digest(
                frozen_case_path(corpus_root, binding["case_id"])
                / "case-manifest.json"
            )
            if binding["case_revision"] != actual:
                raise ValueError(
                    f"project binding revision changed: "
                    f"{binding['binding_id']}"
                )

        archived = declarations / f"{fingerprint}.json"
        if archived.exists():
            existing = canonical_project_declaration(
                regular_json(archived, "archived project declaration")
            )
            if existing != declaration:
                raise ValueError("project declaration fingerprint conflicts")
        else:
            write_exclusive(archived, declaration)
        atomic_json(current_path, {
            "schema_version": 1,
            "declaration_sha256": fingerprint,
        })

    registration = {
        "schema_version": 1,
        "project_id": declaration["project_id"],
        "campaign_id": campaign_id,
        "declaration_sha256": fingerprint,
    }
    project_root = state_root / "projects" / declaration["project_id"]
    if project_root.exists() and (
        project_root.is_symlink() or not project_root.is_dir()
    ):
        raise ValueError("project registration path is invalid")
    project_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with locked(state_root / "projects" / f"{declaration['project_id']}.lock"):
        global_archive = (
            project_root
            / "declarations"
            / campaign_id
            / f"{fingerprint}.json"
        )
        if global_archive.exists():
            existing = canonical_project_declaration(
                regular_json(global_archive, "registered project declaration")
            )
            if existing != declaration:
                raise ValueError("registered project declaration changed")
        else:
            write_exclusive(global_archive, declaration)
        path = project_root / f"{campaign_id}.json"
        if path.exists():
            existing = validate_project_registration(
                regular_json(path, "project registration")
            )
            if existing["project_id"] != declaration["project_id"]:
                raise ValueError("project registration identity changed")
            atomic_json(path, registration)
        else:
            write_exclusive(path, registration)
    return registration


def validate_project_registration(value: dict) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != PROJECT_REGISTRATION_FIELDS
        or value.get("schema_version") != 1
    ):
        raise ValueError("unsupported project registration")
    validate_safe_id(value.get("project_id"), "project ID")
    validate_campaign_id(value.get("campaign_id"))
    validate_sha256(
        value.get("declaration_sha256"),
        "project declaration fingerprint",
    )
    return value


def project_registrations(state_root: Path, project_id: str) -> list[dict]:
    validate_safe_id(project_id, "project ID")
    root = ensure_state_root(state_root) / "projects" / project_id
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("project registration path is invalid")
    result = []
    for path in sorted(root.glob("*.json")):
        registration = validate_project_registration(
            regular_json(path, "project registration")
        )
        if path.stem != registration["campaign_id"]:
            raise ValueError("project registration filename changed")
        result.append(registration)
    return result


def campaign_project_registration(
    state_root: Path,
    campaign_id: str,
) -> dict | None:
    root = ensure_state_root(state_root) / "projects"
    if not root.exists():
        return None
    matches = []
    for project_root in sorted(root.iterdir()):
        if not project_root.is_dir() or project_root.is_symlink():
            continue
        path = project_root / f"{validate_campaign_id(campaign_id)}.json"
        if path.exists():
            matches.append(validate_project_registration(
                regular_json(path, "project registration")
            ))
    if len(matches) > 1:
        raise ValueError("campaign belongs to multiple projects")
    return matches[0] if matches else None


def project_binding_for_case(
    corpus_root: Path,
    case_id: str,
) -> tuple[dict, str, dict, dict] | None:
    declaration = load_project_declaration(corpus_root)
    if declaration is None:
        return None
    matches = [
        item for item in declaration["case_bindings"]
        if item["case_id"] == case_id
    ]
    if len(matches) != 1:
        raise ValueError("project case binding is unavailable")
    binding = matches[0]
    actual_revision = digest(
        frozen_case_path(corpus_root, case_id) / "case-manifest.json"
    )
    if binding["case_revision"] != actual_revision:
        raise ValueError("project case binding revision changed")
    task = next(
        item for item in declaration["tasks"]
        if item["task_id"] == binding["task_id"]
    )
    return (
        declaration,
        project_declaration_fingerprint(declaration),
        task,
        binding,
    )


def project_run_binding(
    corpus_root: Path,
    case_ids: list[str],
    run_goal: str | None,
) -> dict | None:
    declaration = load_project_declaration(corpus_root)
    if declaration is None:
        return None
    goal = _bounded_text(run_goal, "run goal", 400)
    bindings = []
    tasks = set()
    for case_id in case_ids:
        resolved = project_binding_for_case(corpus_root, case_id)
        if resolved is None:
            raise ValueError("project declaration disappeared")
        _, fingerprint, task, binding = resolved
        bindings.append({
            "binding_id": binding["binding_id"],
            "binding_fingerprint": binding_fingerprint(binding),
            "case_id": binding["case_id"],
            "case_revision": binding["case_revision"],
            "task_id": binding["task_id"],
        })
        tasks.add(task["task_id"])
    return {
        "project_id": declaration["project_id"],
        "project_declaration_sha256": fingerprint,
        "run_goal": goal,
        "task_ids": sorted(tasks),
        "case_bindings": sorted(bindings, key=lambda item: item["binding_id"]),
    }


def validate_run_start(value: dict) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != RUN_START_FIELDS
        or value.get("schema_version") != 1
    ):
        raise ValueError("unsupported project run start")
    validate_safe_id(value.get("run_id"), "run ID")
    validate_safe_id(value.get("project_id"), "project ID")
    validate_sha256(
        value.get("project_declaration_sha256"),
        "project declaration fingerprint",
    )
    validate_campaign_id(value.get("campaign_id"))
    if value.get("launcher_kind") not in {"local_case", "local_suite"}:
        raise ValueError("project launcher kind is invalid")
    _bounded_text(value.get("run_goal"), "run goal", 400)
    if not isinstance(value.get("requested_plugin_path"), str):
        raise ValueError("requested plugin path is invalid")
    if value.get("treatment_reference") is not None and not isinstance(
        value["treatment_reference"],
        str,
    ):
        raise ValueError("treatment reference is invalid")
    if not isinstance(value.get("arm"), str) or not value["arm"]:
        raise ValueError("run arm is invalid")
    _sorted_unique_strings(value.get("task_ids"), "run task IDs")
    bindings = value.get("case_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("run case bindings are invalid")
    for binding in bindings:
        if set(binding) != {
            "binding_id",
            "binding_fingerprint",
            "case_id",
            "case_revision",
            "task_id",
        }:
            raise ValueError("run case binding is invalid")
        validate_safe_id(binding.get("binding_id"), "binding ID")
        validate_sha256(
            binding.get("binding_fingerprint"),
            "binding fingerprint",
        )
        validate_safe_id(binding.get("case_id"), "case ID")
        validate_sha256(binding.get("case_revision"), "case revision")
        validate_safe_id(binding.get("task_id"), "task ID")
    if type(value.get("planned_workers")) is not int or value["planned_workers"] < 1:
        raise ValueError("planned workers are invalid")
    if type(value.get("planned_attempts")) is not int or value["planned_attempts"] < 1:
        raise ValueError("planned attempts are invalid")
    validate_sha256(value.get("lease_generation"), "lease generation")
    parse_instant(value.get("started_at"))
    return value


def validate_run_lease(value: dict, *, start: dict | None = None) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != RUN_LEASE_FIELDS
        or value.get("schema_version") != 1
    ):
        raise ValueError("unsupported project run lease")
    validate_safe_id(value.get("run_id"), "run ID")
    validate_sha256(value.get("generation"), "lease generation")
    renewed = parse_instant(value.get("renewed_at"))
    expires = parse_instant(value.get("expires_at"))
    if expires <= renewed:
        raise ValueError("run lease expiry must follow renewal")
    if start is not None and (
        value["run_id"] != start["run_id"]
        or value["generation"] != start["lease_generation"]
    ):
        raise ValueError("run lease identity changed")
    return value


def validate_suite_failure(value: dict, *, start: dict | None = None) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != SUITE_FAILURE_FIELDS
        or value.get("schema_version") != 1
    ):
        raise ValueError("unsupported suite failure")
    validate_safe_id(value.get("run_id"), "run ID")
    if value.get("stage") not in {
        "lease",
        "plugin_snapshot",
        "launcher_setup",
        "attempt_start",
        "reporting",
    }:
        raise ValueError("suite failure stage is invalid")
    _bounded_text(value.get("error_type"), "suite failure error type", 160)
    _bounded_text(value.get("message"), "suite failure message", 400)
    parse_instant(value.get("failed_at"))
    if start is not None and value["run_id"] != start["run_id"]:
        raise ValueError("suite failure run identity changed")
    return value


def _declaration_for_registration(
    state_root: Path,
    registration: dict,
) -> tuple[dict, dict]:
    campaign = campaign_registration(state_root, registration["campaign_id"])
    path = (
        ensure_state_root(state_root)
        / "projects"
        / registration["project_id"]
        / "declarations"
        / registration["campaign_id"]
        / f"{registration['declaration_sha256']}.json"
    )
    declaration = canonical_project_declaration(
        regular_json(path, "registered project declaration")
    )
    if (
        project_declaration_fingerprint(declaration)
        != registration["declaration_sha256"]
    ):
        raise ValueError("registered project declaration fingerprint changed")
    return campaign, declaration


def reconciled_project(
    state_root: Path,
    project_id: str,
) -> dict:
    registrations = project_registrations(state_root, project_id)
    if not registrations:
        raise ValueError("project is unavailable")
    sources = []
    declarations = []
    for registration in registrations:
        campaign, declaration = _declaration_for_registration(
            state_root,
            registration,
        )
        if declaration["project_id"] != project_id:
            raise ValueError("project registration declaration changed")
        corpus_root = Path(campaign["corpus_root"])
        try:
            corpus_stat = corpus_root.stat()
            source_available = (
                corpus_root.is_dir()
                and not corpus_root.is_symlink()
                and corpus_stat.st_dev == campaign["corpus_device"]
                and corpus_stat.st_ino == campaign["corpus_inode"]
            )
        except OSError:
            source_available = False
        sources.append({
            "campaign": campaign,
            "registration": registration,
            "corpus_root": corpus_root,
            "available": source_available,
        })
        declarations.append(declaration)

    immutable_fields = ("schema_version", "project_id", "title", "goal", "target_skills")
    project_conflicts = [
        field
        for field in immutable_fields
        if len({
            json.dumps(item[field], sort_keys=True, separators=(",", ":"))
            for item in declarations
        }) != 1
    ]

    def merge(field: str, identifier: str) -> tuple[list[dict], list[str]]:
        grouped = {}
        for declaration in declarations:
            for item in declaration[field]:
                grouped.setdefault(item[identifier], set()).add(
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                )
        conflicts = sorted(
            identifier_value
            for identifier_value, values in grouped.items()
            if len(values) != 1
        )
        values = [
            json.loads(next(iter(grouped[identifier_value])))
            for identifier_value in sorted(grouped)
            if identifier_value not in conflicts
        ]
        return values, conflicts

    tasks, task_conflicts = merge("tasks", "task_id")
    bindings, binding_conflicts = merge("case_bindings", "binding_id")
    holdouts, holdout_conflicts = merge(
        "holdout_requirements",
        "holdout_set_id",
    )
    conflicted_tasks = set(task_conflicts)
    conflicted_tasks.update(
        item["task_id"]
        for declaration in declarations
        for item in declaration["case_bindings"]
        if item["binding_id"] in binding_conflicts
    )
    bindings = [
        item for item in bindings
        if item["task_id"] not in conflicted_tasks
    ]
    tasks = [
        item for item in tasks
        if item["task_id"] not in conflicted_tasks
    ]
    return {
        "project_id": project_id,
        "title": declarations[0]["title"],
        "goal": declarations[0]["goal"],
        "target_skills": declarations[0]["target_skills"],
        "sources": sources,
        "tasks": tasks,
        "case_bindings": bindings,
        "holdout_requirements": holdouts,
        "conflicts": {
            "project_fields": project_conflicts,
            "tasks": sorted(conflicted_tasks),
            "bindings": binding_conflicts,
            "holdouts": holdout_conflicts,
        },
        "available": not project_conflicts,
    }


def _project_lineage(project: dict) -> dict:
    snapshots = {}
    snapshot_revisions = {}
    revision_skills = {}
    parent_snapshots = {}
    roles = {}
    conflicts = []
    for source in project["sources"]:
        if not source["available"]:
            conflicts.append(source["campaign"]["campaign_id"])
            continue
        corpus_root = source["corpus_root"]
        records, record_conflicts, invalid = extension_records(corpus_root)
        if record_conflicts or invalid:
            conflicts.append(source["campaign"]["campaign_id"])
        for record in records:
            if record["event_type"] != "lineage_declared":
                continue
            snapshot_id = record["subject"]["snapshot_id"]
            try:
                manifest = read_skill_snapshot(corpus_root, snapshot_id)
            except (OSError, ValueError, json.JSONDecodeError):
                conflicts.append(snapshot_id)
                continue
            identity = json_fingerprint(manifest["skills"])
            if snapshot_id in snapshots and snapshots[snapshot_id] != identity:
                conflicts.append(snapshot_id)
                continue
            snapshots[snapshot_id] = identity
            snapshot_revisions.setdefault(identity, set()).add(snapshot_id)
            revision_skills[identity] = [
                item["name"] for item in manifest["skills"]
            ]
            declared_parents = {
                (item["relation"], item["snapshot_id"])
                for item in record["payload"]["parents"]
            }
            if (
                snapshot_id in parent_snapshots
                and parent_snapshots[snapshot_id] != declared_parents
            ):
                conflicts.append(snapshot_id)
                continue
            parent_snapshots[snapshot_id] = declared_parents
            roles.setdefault(identity, set()).update(record["payload"]["roles"])

    children = {}
    for child_snapshot, declared in parent_snapshots.items():
        child = snapshots.get(child_snapshot)
        for _, parent_snapshot in declared:
            parent = snapshots.get(parent_snapshot)
            if child is None or parent is None:
                conflicts.append(child_snapshot)
            else:
                children.setdefault(parent, set()).add(child)

    def has_descendant(snapshot_id: str, candidates: set[str]) -> bool:
        pending = list(children.get(snapshot_id, set()))
        seen = set()
        while pending:
            child = pending.pop()
            if child in seen:
                continue
            seen.add(child)
            if child in candidates:
                return True
            pending.extend(children.get(child, set()))
        return False

    candidates = {
        revision_id
        for revision_id, snapshot_roles in roles.items()
        if snapshot_roles & PROJECT_ROLES
        and revision_skills[revision_id] == project["target_skills"]
    }
    tips = sorted(
        revision_id
        for revision_id in candidates
        if not has_descendant(revision_id, candidates)
    )
    return {
        "status": (
            "conflicted"
            if conflicts or len(tips) > 1
            else "available"
            if len(tips) == 1
            else "unavailable"
        ),
        "snapshot_id": tips[0] if len(tips) == 1 and not conflicts else None,
        "snapshot_ids": (
            sorted(snapshot_revisions[tips[0]])
            if len(tips) == 1 and not conflicts
            else []
        ),
        "conflicts": sorted(set(conflicts)),
    }


def _terminal_attempts(project: dict) -> tuple[list[dict], list[dict]]:
    assigned = []
    pre_project = []
    for source in project["sources"]:
        if not source["available"]:
            continue
        corpus_root = source["corpus_root"]
        report = evaluation_history.history(corpus_root)
        for row in report["attempts"]:
            run_path = row.get("run_path")
            if not run_path:
                continue
            attempt_path = corpus_root / run_path / "attempt.json"
            if attempt_path.is_symlink() or not attempt_path.is_file():
                pre_project.append({
                    "campaign_id": source["campaign"]["campaign_id"],
                    "run_path": run_path,
                    "correctness": row["correctness"],
                })
                continue
            attempt = regular_json(attempt_path, "project attempt")
            project_binding = attempt.get("project")
            if not isinstance(project_binding, dict):
                pre_project.append({
                    "campaign_id": source["campaign"]["campaign_id"],
                    "run_path": run_path,
                    "correctness": row["correctness"],
                })
                continue
            try:
                declaration = archived_project_declaration(
                    corpus_root,
                    project_binding["declaration_sha256"],
                )
            except (KeyError, OSError, ValueError, json.JSONDecodeError):
                continue
            if declaration["project_id"] != project["project_id"]:
                continue
            assigned.append({
                "campaign_id": source["campaign"]["campaign_id"],
                "corpus_root": corpus_root,
                "row": row,
                "attempt": attempt,
                "declaration": declaration,
                "project": project_binding,
            })
    return assigned, pre_project


def _task_scorecard(
    project: dict,
    lineage: dict,
    attempts: list[dict],
) -> list[dict]:
    selected_snapshots = set(lineage["snapshot_ids"])
    result = []
    for task in project["tasks"]:
        task_id = task["task_id"]
        qualification = task["qualification"]
        bindings = [
            item for item in project["case_bindings"]
            if item["task_id"] == task_id
            and item["role"] in qualification["required_roles"]
        ]
        binding_rows = []
        for binding in bindings:
            matching = []
            for item in attempts:
                project_binding = item["project"]
                if (
                    not selected_snapshots
                    or item["row"]["population"].get("lineage_snapshot_id")
                    not in selected_snapshots
                    or project_binding.get("binding_id") != binding["binding_id"]
                    or project_binding.get("binding_fingerprint")
                    != binding_fingerprint(binding)
                    or project_binding.get("task_fingerprint")
                    != task_fingerprint(task)
                    or item["row"]["population"]["case_id"]
                    != binding["case_id"]
                    or item["row"]["population"]["case_revision"]
                    != binding["case_revision"]
                ):
                    continue
                matching.append(item["row"])
            terminal_rows = [
                item
                for item in matching
                if item["correctness"]
                in {"PASS", "FAIL", "UNANSWERABLE", "BLOCKED"}
            ]
            terminal = len(terminal_rows)
            passing = sum(
                item["correctness"] == "PASS"
                for item in terminal_rows
            )
            binding_rows.append({
                "binding_id": binding["binding_id"],
                "case_id": binding["case_id"],
                "terminal_attempts": terminal,
                "passing_attempts": passing,
                "qualified": (
                    terminal
                    >= qualification["minimum_terminal_repetitions_per_case"]
                    and passing >= qualification["required_passes_per_case"]
                ),
            })
        complete = (
            bool(selected_snapshots)
            and bool(bindings)
            and all(
                item["terminal_attempts"]
                >= qualification["minimum_terminal_repetitions_per_case"]
                for item in binding_rows
            )
        )
        passing = complete and all(item["qualified"] for item in binding_rows)
        result.append({
            "task_id": task_id,
            "title": task["title"],
            "summary": task["summary"],
            "result": (
                "passing"
                if passing
                else "not_passing"
                if complete
                else "unavailable"
            ),
            "bindings": binding_rows,
        })
    return result


def _suite_started_attempts(corpus_root: Path, suite_root: Path) -> int:
    suite_path = str(suite_root.relative_to(corpus_root))
    count = 0
    for path in sorted((corpus_root / "runs").glob("*/*/attempt.json")):
        try:
            owner = regular_json(path, "attempt").get("suite_owner")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(owner, dict) and owner.get("suite_path") == suite_path:
            count += 1
    return count


def _run_projection(source: dict) -> list[dict]:
    if not source["available"]:
        return []
    corpus_root = source["corpus_root"]
    runs = []
    for launcher_kind, root_name, start_name in (
        ("local_suite", "suite-runs", "suite-start.json"),
        ("local_case", "runs", "attempt.json"),
    ):
        root = corpus_root / root_name
        if not root.exists():
            continue
        paths = (
            sorted(root.glob(f"*/{start_name}"))
            if launcher_kind == "local_suite"
            else sorted(root.glob(f"*/*/{start_name}"))
        )
        for path in paths:
            try:
                raw = regular_json(path, "project run start")
                start = (
                    validate_run_start(raw)
                    if launcher_kind == "local_suite"
                    else raw.get("project_start")
                )
                if launcher_kind == "local_case":
                    start = validate_run_start(start)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if start["project_id"] != source["registration"]["project_id"]:
                continue
            run_root = path.parent
            lease_path = run_root / "run-lease.json"
            failure_path = run_root / (
                "suite-failure.json"
                if launcher_kind == "local_suite"
                else "attempt-failure-receipt.json"
            )
            result_path = run_root / (
                "suite-result.json"
                if launcher_kind == "local_suite"
                else "execution-result.json"
            )
            repository_result = run_root / "repository-result.json"
            report = run_root / "REPORT.md"
            terminal = (
                result_path.is_file()
                or repository_result.is_file()
                or (launcher_kind == "local_case" and report.is_file())
            )
            failure = failure_path.is_file()
            lease = None
            if lease_path.is_file():
                lease = validate_run_lease(
                    regular_json(lease_path, "project run lease"),
                    start=start,
                )
            state = "completed" if terminal else "infrastructure_failed" if failure else "active"
            if not terminal and not failure and lease is not None:
                if parse_instant(lease["expires_at"]) <= datetime.now(timezone.utc):
                    state = "liveness_lost"
            elif not terminal and not failure and lease is None:
                state = "liveness_unavailable"
            row = {
                "run_id": start["run_id"],
                "launcher_kind": launcher_kind,
                "started_at": start["started_at"],
                "run_goal": start["run_goal"],
                "task_ids": start["task_ids"],
                "planned_workers": start["planned_workers"],
                "planned_attempts": start["planned_attempts"],
                "started_attempts": (
                    1
                    if launcher_kind == "local_case"
                    else _suite_started_attempts(corpus_root, run_root)
                ),
                "state": state,
            }
            if launcher_kind == "local_suite" and result_path.is_file():
                result_value = regular_json(result_path, "suite result")
                attempts = [
                    attempt
                    for case in result_value.get("cases", [])
                    for attempt in case.get("attempts", [])
                ]
                row.update({
                    "completed_attempts": sum(
                        attempt.get("result") != "ERROR"
                        for attempt in attempts
                    ),
                    "passing_attempts": sum(
                        attempt.get("result") == "PASS"
                        for attempt in attempts
                    ),
                    "failing_attempts": sum(
                        attempt.get("result") not in {"PASS", "ERROR"}
                        for attempt in attempts
                    ),
                    "unavailable_attempts": sum(
                        attempt.get("result") == "ERROR"
                        for attempt in attempts
                    ),
                    "duration_seconds": result_value.get("duration_seconds"),
                })
            elif launcher_kind == "local_case" and terminal:
                row["completed_attempts"] = 1
                outcome = None
                if repository_result.is_file():
                    value = regular_json(
                        repository_result,
                        "repository result",
                    )
                    outcome = (
                        "PASS"
                        if value.get("execution_status") == "PASS"
                        and value.get("behavioral_verdict") == "PASS"
                        else "FAIL"
                    )
                elif result_path.is_file():
                    value = regular_json(result_path, "execution result")
                    outcome = value.get("execution_status")
                else:
                    verdicts = [
                        regular_json(path, "judgment").get("verdict")
                        for path in sorted(run_root.glob("judgment-*.json"))
                    ]
                    if verdicts:
                        outcome = (
                            "PASS"
                            if all(item == "PASS" for item in verdicts)
                            else "UNANSWERABLE"
                            if "FAIL" not in verdicts
                            and "UNANSWERABLE" in verdicts
                            else "FAIL"
                        )
                if outcome is not None:
                    row["passing_attempts"] = int(outcome == "PASS")
                    row["failing_attempts"] = int(outcome != "PASS")
            if failure:
                try:
                    failure_value = regular_json(
                        failure_path,
                        "project run failure",
                    )
                    if launcher_kind == "local_suite":
                        failure_value = validate_suite_failure(
                            failure_value,
                            start=start,
                        )
                    row["failure_stage"] = failure_value.get("stage", "attempt")
                except (OSError, ValueError, json.JSONDecodeError):
                    row["failure_stage"] = "unavailable"
            runs.append(row)
    return runs


def project_projection(state_root: Path, project_id: str) -> dict:
    project = reconciled_project(state_root, project_id)
    lineage = _project_lineage(project) if project["available"] else {
        "status": "unavailable",
        "snapshot_id": None,
        "snapshot_ids": [],
        "conflicts": [],
    }
    attempts, pre_project = _terminal_attempts(project)
    tasks = (
        _task_scorecard(project, lineage, attempts)
        if project["available"]
        else []
    )
    runs = [
        row
        for source in project["sources"]
        for row in _run_projection(source)
    ]
    runs.sort(key=lambda item: (item["started_at"], item["run_id"]), reverse=True)
    return {
        "schema_version": 1,
        "project": {
            "project_id": project_id,
            "title": project["title"],
            "goal": project["goal"],
            "target_skills": project["target_skills"],
            "availability": "available" if project["available"] else "conflicted",
        },
        "selected_revision": lineage,
        "tasks": tasks,
        "runs": runs,
        "pre_project_history": pre_project,
        "conflicts": project["conflicts"],
        "unsupported": {
            "task_phase": False,
            "safe_progress": False,
            "holdout_execution": False,
            "ablation": False,
            "distributed_runs": False,
        },
    }


def project_index_projection(state_root: Path) -> dict:
    root = ensure_state_root(state_root)
    projects_root = root / "projects"
    projects = []
    if projects_root.exists():
        for path in sorted(projects_root.iterdir()):
            if path.name.endswith(".lock") or not path.is_dir() or path.is_symlink():
                continue
            try:
                projection = project_projection(root, path.name)
            except (OSError, ValueError, json.JSONDecodeError):
                projects.append({
                    "project_id": path.name,
                    "title": path.name,
                    "goal": "Project data is unavailable.",
                    "target_skills": [],
                    "availability": "unavailable",
                    "selected_revision": {
                        "status": "unavailable",
                        "snapshot_id": None,
                        "snapshot_ids": [],
                        "conflicts": [],
                    },
                    "task_counts": {
                        "passing": 0,
                        "not_passing": 0,
                        "unavailable": 0,
                    },
                    "active_runs": 0,
                })
                continue
            projects.append({
                **projection["project"],
                "selected_revision": projection["selected_revision"],
                "task_counts": {
                    "passing": sum(
                        item["result"] == "passing"
                        for item in projection["tasks"]
                    ),
                    "not_passing": sum(
                        item["result"] == "not_passing"
                        for item in projection["tasks"]
                    ),
                    "unavailable": sum(
                        item["result"] == "unavailable"
                        for item in projection["tasks"]
                    ),
                },
                "active_runs": sum(
                    item["state"] == "active"
                    for item in projection["runs"]
                ),
            })
    return {"schema_version": 1, "projects": projects}


def unassigned_projection(state_root: Path) -> dict:
    root = ensure_state_root(state_root)
    campaigns = []
    for path in sorted((root / "campaigns").glob("*.json")):
        registration = campaign_registration(root, path.stem)
        if campaign_project_registration(root, registration["campaign_id"]) is None:
            campaigns.append({
                "campaign_id": registration["campaign_id"],
                "corpus_name": registration["corpus_name"],
                "target_skills": registration["target_skills"],
            })
    return {"schema_version": 1, "campaigns": campaigns}
