"""Validated project declarations and project-level dashboard projections."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import evaluation_history
from dashboard_state import (
    atomic_json,
    campaign_registration,
    ensure_state_root,
    experiment_activity_records,
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
SAFE_PROGRESS_FIELDS = {"kind", "checks"}
SAFE_PROGRESS_KINDS = {
    "repository_checks",
    "distributed_product_stages",
}
REPOSITORY_PROGRESS_CHECKS = {"regression", "target"}


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
        safe_progress = binding.get("safe_progress")
        if safe_progress is not None:
            safe_progress = _exact_object(
                safe_progress,
                SAFE_PROGRESS_FIELDS,
                "safe progress declaration",
            )
            if safe_progress.get("kind") not in SAFE_PROGRESS_KINDS:
                raise ValueError("safe progress reader kind is invalid")
            checks = _sorted_unique_strings(
                safe_progress.get("checks"),
                "safe progress checks",
            )
            for check in checks:
                validate_safe_id(check, "safe progress check")
            if (
                safe_progress["kind"] == "repository_checks"
                and set(checks) != REPOSITORY_PROGRESS_CHECKS
            ):
                raise ValueError(
                    "repository safe progress checks are invalid"
                )
            safe_progress = {
                "kind": safe_progress["kind"],
                "checks": checks,
            }
        prior = bound_cases.setdefault(binding["case_id"], binding["task_id"])
        if prior != binding["task_id"]:
            raise ValueError("one case is bound to multiple tasks")
        normalized_bindings.append({
            "binding_id": binding["binding_id"],
            "case_id": binding["case_id"],
            "case_revision": binding["case_revision"],
            "task_id": binding["task_id"],
            "role": binding["role"],
            "safe_progress": safe_progress,
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
    selected = tips[0] if len(tips) == 1 and not conflicts else None
    prior_revisions = []
    if selected is not None:
        prior_revisions = sorted(
            revision_id
            for revision_id in snapshot_revisions
            if revision_id != selected
            and has_descendant(revision_id, {selected})
        )
    return {
        "status": (
            "conflicted"
            if conflicts or len(tips) > 1
            else "available"
            if len(tips) == 1
            else "unavailable"
        ),
        "snapshot_id": selected,
        "snapshot_ids": (
            sorted(snapshot_revisions[selected])
            if selected is not None
            else []
        ),
        "roles": sorted(roles.get(selected, set())) if selected else [],
        "prior_revisions": [
            {
                "snapshot_id": revision_id,
                "snapshot_ids": sorted(snapshot_revisions[revision_id]),
                "roles": sorted(roles.get(revision_id, set())),
            }
            for revision_id in prior_revisions
        ],
        "known_revisions": [
            {
                "snapshot_id": revision_id,
                "snapshot_ids": sorted(snapshot_ids),
                "roles": sorted(roles.get(revision_id, set())),
            }
            for revision_id, snapshot_ids in sorted(snapshot_revisions.items())
            if revision_skills.get(revision_id) == project["target_skills"]
        ],
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


def _attempt_completed_at(row: dict) -> datetime | None:
    started_at = row.get("started_at")
    elapsed = row.get("elapsed_seconds")
    if not isinstance(started_at, str) or not isinstance(elapsed, (int, float)):
        return None
    if elapsed < 0:
        return None
    return parse_instant(started_at) + timedelta(seconds=elapsed)


def _matching_task_attempts(
    task: dict,
    bindings: list[dict],
    snapshot_ids: set[str],
    attempts: list[dict],
) -> list[dict]:
    binding_by_id = {item["binding_id"]: item for item in bindings}
    matching = []
    for item in attempts:
        row = item["row"]
        project_binding = item["project"]
        binding = binding_by_id.get(project_binding.get("binding_id"))
        if (
            binding is None
            or row["population"].get("lineage_snapshot_id") not in snapshot_ids
            or project_binding.get("binding_fingerprint")
            != binding_fingerprint(binding)
            or project_binding.get("task_fingerprint") != task_fingerprint(task)
            or row["population"]["case_id"] != binding["case_id"]
            or row["population"]["case_revision"] != binding["case_revision"]
        ):
            continue
        matching.append(item)
    return matching


def _qualification_state(
    task: dict,
    bindings: list[dict],
    matching: list[dict],
) -> tuple[list[dict], bool, bool]:
    qualification = task["qualification"]
    binding_rows = []
    for binding in bindings:
        rows = [
            item["row"]
            for item in matching
            if item["project"].get("binding_id") == binding["binding_id"]
            and item["row"]["correctness"]
            in {"PASS", "FAIL", "UNANSWERABLE", "BLOCKED"}
        ]
        terminal = len(rows)
        passing = sum(item["correctness"] == "PASS" for item in rows)
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
    complete = bool(bindings) and all(
        item["terminal_attempts"]
        >= qualification["minimum_terminal_repetitions_per_case"]
        for item in binding_rows
    )
    return binding_rows, complete, complete and all(
        item["qualified"] for item in binding_rows
    )


def _first_qualified_prefix(
    task: dict,
    bindings: list[dict],
    matching: list[dict],
) -> tuple[str | None, list[dict] | None]:
    terminal = [
        item
        for item in matching
        if item["row"]["correctness"]
        in {"PASS", "FAIL", "UNANSWERABLE", "BLOCKED"}
    ]
    if any(_attempt_completed_at(item["row"]) is None for item in terminal):
        return None, None
    terminal.sort(key=lambda item: (
        _attempt_completed_at(item["row"]),
        item["row"].get("run_path") or "",
        item["row"].get("attempt") or 0,
    ))
    prefix = []
    for item in terminal:
        prefix.append(item)
        _, _, passing = _qualification_state(task, bindings, prefix)
        if passing:
            completed = _attempt_completed_at(item["row"])
            return completed.isoformat() if completed else None, prefix
    return None, None


def _token_summary(rows: list[dict], role: str) -> dict:
    records = [
        record
        for row in rows
        for record in row.get("invocations", [])
        if (
            record.get("role") == "candidate"
            if role == "candidate"
            else record.get("role") != "candidate"
        )
    ]
    latest = {}
    for record in records:
        key = record.get("session_id")
        if not isinstance(key, str):
            continue
        prior = latest.get(key)
        if prior is None or record.get("completed_at", "") > prior.get(
            "completed_at", ""
        ):
            latest[key] = record
    totals = {"input_tokens": 0, "output_tokens": 0}
    complete = bool(latest) or not rows
    known = 0
    for record in latest.values():
        selected = record.get("selected_observation")
        observations = record.get("observations")
        observation = (
            observations[selected]
            if isinstance(observations, list)
            and type(selected) is int
            and 0 <= selected < len(observations)
            else None
        )
        metrics = (
            observation.get("raw", {}).get("modelMetrics")
            if isinstance(observation, dict)
            else None
        )
        if (
            record.get("completeness") != "complete"
            or not isinstance(metrics, dict)
        ):
            complete = False
            continue
        known += 1
        for values in metrics.values():
            usage = values.get("usage") if isinstance(values, dict) else None
            if not isinstance(usage, dict):
                continue
            totals["input_tokens"] += usage.get("inputTokens", 0)
            totals["output_tokens"] += usage.get("outputTokens", 0)
    return {
        **({
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
        } if complete else {
            "input_tokens": None,
            "output_tokens": None,
        }),
        "complete": complete,
        "known_sessions": known,
        "total_sessions": len(latest),
    }


def _effort_summary(rows: list[dict]) -> dict:
    attempt_rows = [
        {
            **item["row"],
            "accounting": item["row"].get("accounting", {}),
            "invocations": item["row"].get("invocations", []),
        }
        for item in rows
    ]
    return {
        "runs": len({
            row.get("suite_path") or row.get("run_path")
            for row in attempt_rows
            if row.get("suite_path") or row.get("run_path")
        }),
        "attempts": len(attempt_rows),
        "candidate_tokens": _token_summary(attempt_rows, "candidate"),
        "judge_tokens": _token_summary(attempt_rows, "judge"),
        "candidate_cost": evaluation_history.cost_summary(
            attempt_rows,
            "candidate",
        ),
        "judge_cost": evaluation_history.cost_summary(
            attempt_rows,
            "evaluation",
        ),
        "total_cost": evaluation_history.cost_summary(attempt_rows),
        "retry_dependent": any(
            (row.get("attempt") or 1) > 1 and row.get("correctness") == "PASS"
            for row in attempt_rows
        ),
    }


def _task_phase(
    project: dict,
    lineage: dict,
    task: dict,
    task_result: str,
    bindings: list[dict],
    attempts: list[dict],
) -> dict:
    selected_snapshots = set(lineage.get("snapshot_ids", []))
    current_bindings = {
        (binding["case_id"], binding["case_revision"]): binding
        for binding in bindings
    }
    records = []
    invalid = False
    for source in project["sources"]:
        if not source["available"]:
            continue
        source_records, conflicts, rejected = extension_records(
            source["corpus_root"]
        )
        invalid = invalid or bool(conflicts or rejected)
        for record in source_records:
            if record["event_type"] != "task_progress_recorded":
                continue
            payload = record["payload"]
            subject = record["subject"]
            if (
                "task_id" not in payload
                or payload["task_id"] != task["task_id"]
                or subject["snapshot_id"] not in selected_snapshots
                or (subject["case_id"], subject["case_revision"])
                not in current_bindings
                or payload["phase"] is None
            ):
                continue
            try:
                declaration = archived_project_declaration(
                    source["corpus_root"],
                    payload["project_declaration_sha256"],
                )
            except (OSError, ValueError, json.JSONDecodeError):
                invalid = True
                continue
            declared_tasks = [
                item for item in declaration["tasks"]
                if item["task_id"] == task["task_id"]
            ]
            declared_bindings = [
                item for item in declaration["case_bindings"]
                if item["task_id"] == task["task_id"]
                and item["case_id"] == subject["case_id"]
                and item["case_revision"] == subject["case_revision"]
            ]
            current_binding = current_bindings[
                (subject["case_id"], subject["case_revision"])
            ]
            if (
                len(declared_tasks) != 1
                or task_fingerprint(declared_tasks[0])
                != task_fingerprint(task)
                or len(declared_bindings) != 1
                or binding_fingerprint(declared_bindings[0])
                != binding_fingerprint(current_binding)
            ):
                continue
            records.append(record)
    selected_attempts = _matching_task_attempts(
        task,
        bindings,
        selected_snapshots,
        attempts,
    ) if selected_snapshots else []
    if (
        task_result == "unavailable"
        and any(
            item["row"]["correctness"] == "PASS"
            for item in selected_attempts
        )
    ):
        return {
            "status": "available",
            "phase": "candidate_pass",
            "authority": "evaluator",
            "recorded_at": None,
        }
    if (
        task_result == "unavailable"
        and any(
            item["row"]["correctness"]
            in {"PASS", "FAIL", "UNANSWERABLE", "BLOCKED"}
            for item in selected_attempts
        )
    ):
        return {
            "status": "available",
            "phase": "qualifying",
            "authority": "evaluator",
            "recorded_at": None,
        }
    if records:
        latest_at = max(parse_instant(item["recorded_at"]) for item in records)
        latest = [
            item for item in records
            if parse_instant(item["recorded_at"]) == latest_at
        ]
        phases = sorted({item["payload"]["phase"] for item in latest})
        if len(phases) != 1:
            return {
                "status": "conflicted",
                "phase": None,
                "authority": "session_intent",
                "recorded_at": latest_at.isoformat(),
            }
        return {
            "status": "available",
            "phase": phases[0],
            "authority": "session_intent",
            "recorded_at": latest_at.isoformat(),
        }
    return {
        "status": "conflicted" if invalid else "available",
        "phase": None if invalid else "not_started",
        "authority": None if invalid else "project",
        "recorded_at": None,
    }


def _valid_repository_checks(path: Path) -> dict[str, bool] | None:
    try:
        value = regular_json(path, "repository grading")
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if set(value) != REPOSITORY_PROGRESS_CHECKS:
        return None
    result = {}
    for name in sorted(REPOSITORY_PROGRESS_CHECKS):
        row = value.get(name)
        if not isinstance(row, dict) or type(row.get("passed")) is not bool:
            return None
        result[name] = row["passed"]
    return result


def _task_safe_progress(
    task: dict,
    bindings: list[dict],
    lineage: dict,
    attempts: list[dict],
    distributed_activity: list[dict],
) -> dict:
    declarations = [item.get("safe_progress") for item in bindings]
    if not declarations or any(item is None for item in declarations):
        return {
            "status": "unavailable",
            "reason": "No safe subcheck breakdown.",
        }
    identities = {
        json.dumps(item, sort_keys=True, separators=(",", ":"))
        for item in declarations
    }
    if len(identities) != 1:
        return {
            "status": "conflicted",
            "reason": "Safe progress declarations disagree.",
        }
    declaration = declarations[0]
    checks = declaration["checks"]
    selected_snapshots = set(lineage.get("snapshot_ids", []))
    evidence = []
    if declaration["kind"] == "repository_checks":
        matching = _matching_task_attempts(
            task,
            bindings,
            selected_snapshots,
            attempts,
        ) if selected_snapshots else []
        for binding in bindings:
            candidates = [
                item for item in matching
                if item["project"].get("binding_id") == binding["binding_id"]
                and item["row"].get("run_path")
            ]
            candidates.sort(key=lambda item: (
                _attempt_completed_at(item["row"]) or datetime.min.replace(
                    tzinfo=timezone.utc
                ),
                item["row"]["run_path"],
            ), reverse=True)
            valid = None
            for item in candidates:
                valid = _valid_repository_checks(
                    item["corpus_root"]
                    / item["row"]["run_path"]
                    / "grading"
                    / "grading.json"
                )
                if valid is not None:
                    evidence.append({
                        "binding_id": binding["binding_id"],
                        "checks": valid,
                    })
                    break
            if valid is None:
                return {
                    "status": "unavailable",
                    "reason": "Declared repository checks are incomplete.",
                }
    else:
        for binding in bindings:
            rows = [
                item for item in distributed_activity
                if item["case_id"] == binding["case_id"]
                and item["case_revision"] == binding["case_revision"]
                and item["snapshot_id"] in selected_snapshots
            ]
            expected = {
                stage
                for item in rows
                for stage in item.get("_expected_stage_kinds", [])
            }
            if any(check not in expected for check in checks):
                return {
                    "status": "unavailable",
                    "reason": "Declared distributed stages are incomplete.",
                }
            by_check = {}
            for check in checks:
                by_check[check] = any(
                    check in item.get("_completed_stage_kinds", [])
                    for item in rows
                )
            if not rows:
                return {
                    "status": "unavailable",
                    "reason": "Declared distributed stages are incomplete.",
                }
            evidence.append({
                "binding_id": binding["binding_id"],
                "checks": by_check,
            })
    total = len(bindings) * len(checks)
    passed = sum(
        value
        for item in evidence
        for value in item["checks"].values()
    )
    return {
        "status": "available",
        "kind": declaration["kind"],
        "checks": checks,
        "passed": passed,
        "total": total,
        "evidence": evidence,
    }


def _task_scorecard(
    project: dict,
    lineage: dict,
    attempts: list[dict],
) -> list[dict]:
    selected_snapshots = set(lineage["snapshot_ids"])
    known_revisions = lineage.get("known_revisions") or [{
        "snapshot_id": lineage.get("snapshot_id"),
        "snapshot_ids": lineage.get("snapshot_ids", []),
        "roles": [],
    }]
    prior_ids = {
        item["snapshot_id"] for item in lineage.get("prior_revisions", [])
    }
    result = []
    for task in project["tasks"]:
        task_id = task["task_id"]
        qualification = task["qualification"]
        bindings = [
            item for item in project["case_bindings"]
            if item["task_id"] == task_id
            and item["role"] in qualification["required_roles"]
        ]
        current = _matching_task_attempts(
            task,
            bindings,
            selected_snapshots,
            attempts,
        ) if selected_snapshots else []
        binding_rows, complete, passing = _qualification_state(
            task,
            bindings,
            current,
        )
        prior_passing = False
        journey_attempts = []
        first_qualified = None
        for revision in known_revisions:
            revision_matching = _matching_task_attempts(
                task,
                bindings,
                set(revision["snapshot_ids"]),
                attempts,
            )
            journey_attempts.extend(revision_matching)
            _, revision_complete, revision_passing = _qualification_state(
                task,
                bindings,
                revision_matching,
            )
            if (
                revision["snapshot_id"] in prior_ids
                and revision_complete
                and revision_passing
            ):
                prior_passing = True
            qualified_at, _ = _first_qualified_prefix(
                task,
                bindings,
                revision_matching,
            )
            if qualified_at is not None and (
                first_qualified is None
                or parse_instant(qualified_at) < parse_instant(first_qualified)
            ):
                first_qualified = qualified_at
        unique_journey = {
            (
                item.get("campaign_id"),
                item["row"].get("run_path"),
                item["row"].get("attempt"),
            ): item
            for item in journey_attempts
        }
        journey_attempts = list(unique_journey.values())
        completed = [
            (
                _attempt_completed_at(item["row"]),
                item,
            )
            for item in journey_attempts
        ]
        observed_passes = [
            (instant, item)
            for instant, item in completed
            if instant is not None and item["row"]["correctness"] == "PASS"
        ]
        first_run = min(
            (
                parse_instant(item["row"]["started_at"])
                for item in journey_attempts
                if isinstance(item["row"].get("started_at"), str)
            ),
            default=None,
        )
        bounded_rows = [
            item
            for completed_at, item in completed
            if (
                first_qualified is None
                or completed_at is not None
                and completed_at <= parse_instant(first_qualified)
            )
        ]
        result.append({
            "task_id": task_id,
            "title": task["title"],
            "summary": task["summary"],
            "result": (
                "passing"
                if passing
                else "regressed"
                if complete and prior_passing
                else "not_passing"
                if complete
                else "unavailable"
            ),
            "bindings": binding_rows,
            "timing": {
                "first_run_at": first_run.isoformat() if first_run else None,
                "first_observed_pass_at": (
                    min(observed_passes, key=lambda item: item[0])[0].isoformat()
                    if observed_passes else None
                ),
                "first_qualified_pass_at": first_qualified,
                "elapsed_seconds": (
                    (
                        parse_instant(first_qualified) - first_run
                    ).total_seconds()
                    if first_run and first_qualified
                    else None
                ),
            },
            "effort": _effort_summary(bounded_rows),
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


def _attempt_outcome_counts(outcome: str | None) -> dict:
    return {
        "passing_attempts": int(outcome == "PASS"),
        "failing_attempts": int(outcome in {"FAIL", "UNANSWERABLE"}),
        "unavailable_attempts": int(
            outcome not in {"PASS", "FAIL", "UNANSWERABLE"}
        ),
    }


def _experiment_cost(accounting: object) -> dict:
    return evaluation_history.cost_summary([{
        "accounting": accounting if isinstance(accounting, dict) else {},
    }])


def _experiment_targets(
    project: dict,
    task_by_case: dict[str, set[str]],
    case_id: str,
    fallback_task_ids: list[str],
) -> dict:
    return {
        "skill_ids": project.get("target_skills", []),
        "task_ids": sorted(task_by_case.get(case_id, set(fallback_task_ids))),
    }


def _completed_experiment(
    project: dict,
    task_by_case: dict[str, set[str]],
    fallback_task_ids: list[str],
    case_id: str,
    attempt: dict,
) -> dict:
    correctness = attempt.get("correctness", attempt.get("result"))
    complete = correctness in {"PASS", "FAIL", "UNANSWERABLE"}
    timing = attempt.get("timing", {})
    return {
        "experiment_id": (
            attempt.get("run_path")
            or attempt.get("attempt_id")
            or f"{case_id}:attempt-{attempt.get('attempt', 1)}"
        ),
        "case_id": case_id,
        "attempt": attempt.get("attempt", attempt.get("repetition", 1)),
        **_experiment_targets(
            project,
            task_by_case,
            case_id,
            fallback_task_ids,
        ),
        "step": "complete" if complete else "failed",
        "outcome": (
            "positive"
            if correctness == "PASS"
            else "negative"
            if correctness in {"FAIL", "UNANSWERABLE"}
            else "failed"
        ),
        "duration_seconds": (
            attempt.get("elapsed_seconds")
            if isinstance(attempt.get("elapsed_seconds"), (int, float))
            else timing.get("elapsed_seconds")
            if isinstance(timing, dict)
            else None
        ),
        "cost": _experiment_cost(attempt.get("accounting")),
    }


def _local_attempt_index(
    corpus_root: Path,
) -> tuple[dict[str, list[tuple[Path, dict]]], dict[str, list[tuple[Path, dict]]]]:
    by_suite: dict[str, list[tuple[Path, dict]]] = {}
    by_run: dict[str, list[tuple[Path, dict]]] = {}
    for path in sorted((corpus_root / "runs").glob("*/*/attempt.json")):
        try:
            attempt = regular_json(path, "project attempt")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        owner = attempt.get("suite_owner")
        if isinstance(owner, dict) and isinstance(owner.get("suite_path"), str):
            by_suite.setdefault(owner["suite_path"], []).append((path, attempt))
        project_start = attempt.get("project_start")
        if (
            isinstance(project_start, dict)
            and isinstance(project_start.get("run_id"), str)
        ):
            by_run.setdefault(project_start["run_id"], []).append((path, attempt))
    return by_suite, by_run


def _active_local_experiments(
    corpus_root: Path,
    project: dict,
    task_by_case: dict[str, set[str]],
    start: dict,
    terminal_paths: set[str],
    candidates: list[tuple[Path, dict]],
) -> list[dict]:
    experiments = []
    for path, attempt in candidates:
        run_path = path.parent.relative_to(corpus_root).as_posix()
        if run_path in terminal_paths:
            continue
        case_id = attempt.get("case_id")
        if not isinstance(case_id, str):
            continue
        checking = (
            (path.parent / "execution-result.json").is_file()
            or (path.parent / "repository-result.json").is_file()
            or (path.parent / "REPORT.md").is_file()
            or any(path.parent.glob("judgment-*.json"))
        )
        experiments.append({
            "experiment_id": run_path,
            "case_id": case_id,
            "attempt": (
                attempt.get("suite_owner", {}).get("attempt", 1)
                if isinstance(attempt.get("suite_owner"), dict)
                else 1
            ),
            **_experiment_targets(
                project,
                task_by_case,
                case_id,
                start["task_ids"],
            ),
            "step": "checking" if checking else "running",
            "outcome": None,
            "duration_seconds": None,
            "cost": _experiment_cost({}),
        })
    return experiments


def _run_projection(
    source: dict,
    project: dict,
    assigned_attempts: list[dict],
) -> list[dict]:
    if not source["available"]:
        return []
    corpus_root = source["corpus_root"]
    task_by_case: dict[str, set[str]] = {}
    for binding in project["case_bindings"]:
        task_by_case.setdefault(binding["case_id"], set()).add(
            binding["task_id"]
        )
    attempts_by_suite, attempts_by_run = _local_attempt_index(corpus_root)
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
                "_task_fingerprints": {},
            }
            suite_path = (
                run_root.relative_to(corpus_root).as_posix()
                if launcher_kind == "local_suite"
                else None
            )
            matching_attempts = [
                item["row"]
                for item in assigned_attempts
                if (
                    item["row"].get("suite_path") == suite_path
                    if suite_path is not None
                    else item["row"].get("run_path")
                    == run_root.relative_to(corpus_root).as_posix()
                )
            ]
            terminal_paths = {
                item["run_path"]
                for item in matching_attempts
                if isinstance(item.get("run_path"), str)
            }
            experiments = [
                _completed_experiment(
                    project,
                    task_by_case,
                    start["task_ids"],
                    item["population"]["case_id"],
                    item,
                )
                for item in matching_attempts
            ]
            if not terminal:
                candidates = (
                    attempts_by_suite.get(suite_path, [])
                    if suite_path is not None
                    else attempts_by_run.get(start["run_id"], [])
                )
                experiments.extend(_active_local_experiments(
                    corpus_root,
                    project,
                    task_by_case,
                    start,
                    terminal_paths,
                    candidates,
                ))
            try:
                run_declaration = archived_project_declaration(
                    corpus_root,
                    start["project_declaration_sha256"],
                )
                row["_task_fingerprints"] = {
                    item["task_id"]: task_fingerprint(item)
                    for item in run_declaration["tasks"]
                    if item["task_id"] in start["task_ids"]
                }
            except (OSError, ValueError, json.JSONDecodeError):
                row["_task_fingerprints"] = {}
            if launcher_kind == "local_suite" and result_path.is_file():
                result_value = regular_json(result_path, "suite result")
                result_attempts = [
                    attempt
                    for case in result_value.get("cases", [])
                    for attempt in case.get("attempts", [])
                ]
                experiments = [
                    _completed_experiment(
                        project,
                        task_by_case,
                        start["task_ids"],
                        case["case_id"],
                        attempt,
                    )
                    for case in result_value.get("cases", [])
                    for attempt in case.get("attempts", [])
                ]
                row.update({
                    "completed_attempts": sum(
                        attempt.get("result") != "ERROR"
                        for attempt in result_attempts
                    ),
                    "passing_attempts": sum(
                        attempt.get("result") == "PASS"
                        for attempt in result_attempts
                    ),
                    "failing_attempts": sum(
                        attempt.get("result") not in {"PASS", "ERROR"}
                        for attempt in result_attempts
                    ),
                    "unavailable_attempts": sum(
                        attempt.get("result") == "ERROR"
                        for attempt in result_attempts
                    ),
                    "duration_seconds": result_value.get("duration_seconds"),
                    "cost": result_value.get("accounting", {}).get("total"),
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
                        value.get("behavioral_verdict")
                        if value.get("execution_status") == "PASS"
                        else value.get("execution_status")
                    )
                elif result_path.is_file():
                    value = regular_json(result_path, "execution result")
                    outcome = (
                        value.get("behavioral_verdict")
                        if value.get("execution_status") == "PASS"
                        else value.get("execution_status")
                    )
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
                row.update(_attempt_outcome_counts(outcome))
                if matching_attempts:
                    row["duration_seconds"] = matching_attempts[0].get(
                        "elapsed_seconds"
                    )
                    row["cost"] = _experiment_cost(
                        matching_attempts[0].get("accounting")
                    )
                if not experiments:
                    raw_attempt = regular_json(
                        run_root / "attempt.json",
                        "project attempt",
                    )
                    case_id = raw_attempt.get("case_id", run_root.name)
                    experiments = [{
                        "experiment_id": (
                            run_root.relative_to(corpus_root).as_posix()
                        ),
                        "case_id": case_id,
                        "attempt": 1,
                        **_experiment_targets(
                            project,
                            task_by_case,
                            case_id,
                            start["task_ids"],
                        ),
                        "step": "failed",
                        "outcome": "failed",
                        "duration_seconds": None,
                        "cost": _experiment_cost({}),
                    }]
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
            row["attempts"] = [{
                "attempt_id": f"{start['run_id']}:launch-1",
                "attempt": 1,
                "started_at": start["started_at"],
                "state": state,
                "duration_seconds": row.get("duration_seconds"),
                "cost": row.get("cost"),
                "experiments": experiments,
            }]
            runs.append(row)
    return runs


def _distributed_projection(project: dict) -> tuple[list[dict], list[dict]]:
    from dashboard_projection import experiment_projection

    bindings = {
        (item["case_id"], item["case_revision"]): item
        for item in project["case_bindings"]
    }
    runs = []
    all_activity = []
    for source in project["sources"]:
        if not source["available"]:
            continue
        projection = experiment_projection(
            source["corpus_root"],
            source["campaign"]["campaign_id"],
        )
        records, _, _ = experiment_activity_records(source["corpus_root"])
        experiment_times = {}
        expected_stages = {}
        completed_stages = {}
        for record in records:
            if record["event_type"] == "experiment_declared":
                experiment_times[
                    record["subject"]["experiment_id"]
                ] = record["recorded_at"]
            elif record["event_type"] == "cloud_dispatch_bound":
                for job in record["payload"]["jobs"]:
                    attempt_id = job["attempt_id"]
                    if attempt_id is not None:
                        expected_stages.setdefault(attempt_id, set()).add(
                            job["stage_kind"]
                        )
            elif (
                record["event_type"] == "distributed_stage_recorded"
                and record["payload"]["status"] != "FAIL"
            ):
                completed_stages.setdefault(
                    record["subject"]["attempt_id"],
                    set(),
                ).add(record["payload"]["stage_kind"])
        for item in projection["items"]:
            activity = [
                {
                    **row,
                    "_expected_stage_kinds": sorted(
                        expected_stages.get(row["attempt_id"], set())
                    ),
                    "_completed_stage_kinds": sorted(
                        completed_stages.get(row["attempt_id"], set())
                    ),
                }
                for row in item["activity"]
                if (row["case_id"], row["case_revision"]) in bindings
            ]
            if not activity:
                continue
            all_activity.extend(activity)
            task_ids = sorted({
                bindings[(row["case_id"], row["case_revision"])]["task_id"]
                for row in activity
            })
            terminal = [
                row for row in activity if row["state"] == "terminal"
            ]
            started = [
                row for row in activity if row["state"] != "planned"
            ]
            conflicted = any(row["state"] == "conflicted" for row in activity)
            active = any(row["state"] in {
                "cloud_nonterminal",
                "distributed_pending",
            } for row in activity)
            awaiting = any(
                row["state"] == "cloud_completed_awaiting_result"
                for row in activity
            )
            state = (
                "conflicted"
                if conflicted
                else "completed"
                if len(terminal) == len(activity)
                else "active"
                if active
                else "liveness_unavailable"
                if awaiting
                else "planned"
            )
            runs.append({
                "run_id": (
                    f"distributed:{source['campaign']['campaign_id']}:"
                    f"{item['experiment_id']}"
                ),
                "launcher_kind": "distributed_experiment",
                "source_identity": {
                    "campaign_id": source["campaign"]["campaign_id"],
                    "experiment_id": item["experiment_id"],
                    "experiment_fingerprint": item[
                        "experiment_fingerprint"
                    ],
                    "route": item["route"],
                },
                "selected_revision": item["snapshot_id"],
                "started_at": experiment_times.get(item["experiment_id"]),
                "run_goal": item["summary"],
                "task_ids": task_ids,
                "planned_workers": item["planned_attempts"],
                "planned_attempts": len(activity),
                "started_attempts": len(started),
                "completed_attempts": len(terminal),
                "passing_attempts": sum(
                    row["evaluator_result"] == "PASS" for row in terminal
                ),
                "failing_attempts": sum(
                    row["evaluator_result"] == "FAIL" for row in terminal
                ),
                "unavailable_attempts": sum(
                    row["evaluator_result"] not in {"PASS", "FAIL"}
                    for row in terminal
                ),
                "state": state,
                "cost": item["cost"],
                "attempts": [{
                    "attempt_id": f"{item['experiment_id']}:launch-1",
                    "attempt": 1,
                    "started_at": experiment_times.get(item["experiment_id"]),
                    "state": state,
                    "duration_seconds": None,
                    "cost": item["cost"],
                    "experiments": [{
                        "experiment_id": row["attempt_id"],
                        "case_id": row["case_id"],
                        "attempt": row.get("repetition", 1),
                        "skill_ids": project.get("target_skills", []),
                        "task_ids": sorted({
                            bindings[
                                (row["case_id"], row["case_revision"])
                            ]["task_id"]
                        }),
                        "step": (
                            "complete"
                            if row["state"] == "terminal"
                            and row["evaluator_result"]
                            in {"PASS", "FAIL", "UNANSWERABLE"}
                            else "failed"
                            if row["state"] in {"terminal", "conflicted"}
                            else "checking"
                            if row["state"]
                            == "cloud_completed_awaiting_result"
                            else "running"
                            if row["state"] in {
                                "cloud_nonterminal",
                                "distributed_pending",
                            }
                            else "setting_up"
                        ),
                        "outcome": (
                            "positive"
                            if row["evaluator_result"] == "PASS"
                            else "negative"
                            if row["evaluator_result"]
                            in {"FAIL", "UNANSWERABLE"}
                            else "failed"
                            if row["state"] in {"terminal", "conflicted"}
                            else None
                        ),
                        "duration_seconds": None,
                        "cost": row.get("cost", {
                            "credits": None,
                            "observed_credits": None,
                            "complete": False,
                        }),
                    } for row in activity],
                }],
            })
    return runs, all_activity


def _snapshot_catalog(project: dict) -> tuple[dict[str, dict], bool]:
    catalog = {}
    invalid = False
    for source in project["sources"]:
        if not source["available"]:
            continue
        records, conflicts, rejected = extension_records(source["corpus_root"])
        invalid = invalid or bool(conflicts or rejected)
        lineage_records = [
            item for item in records
            if item["event_type"] == "lineage_declared"
        ]
        for record in lineage_records:
            snapshot_id = record["subject"]["snapshot_id"]
            try:
                manifest = read_skill_snapshot(
                    source["corpus_root"],
                    snapshot_id,
                )
            except (OSError, ValueError, json.JSONDecodeError):
                invalid = True
                continue
            entry = {
                "snapshot_id": snapshot_id,
                "revision_id": json_fingerprint(manifest["skills"]),
                "manifest": manifest,
                "parents": sorted(
                    item["snapshot_id"]
                    for item in record["payload"]["parents"]
                ),
                "roles": sorted(record["payload"]["roles"]),
            }
            existing = catalog.get(snapshot_id)
            if existing is not None:
                if any(
                    existing[key] != entry[key]
                    for key in (
                        "snapshot_id",
                        "revision_id",
                        "manifest",
                        "parents",
                    )
                ):
                    invalid = True
                    continue
                existing["roles"] = sorted(set(
                    existing["roles"] + entry["roles"]
                ))
            else:
                catalog[snapshot_id] = entry
    return catalog, invalid


def _snapshot_descends(
    catalog: dict[str, dict],
    child_snapshot_id: str,
    ancestor_snapshot_id: str,
) -> bool:
    pending = [child_snapshot_id]
    seen = set()
    while pending:
        snapshot_id = pending.pop()
        if snapshot_id in seen:
            continue
        seen.add(snapshot_id)
        if snapshot_id == ancestor_snapshot_id:
            return True
        entry = catalog.get(snapshot_id)
        if entry is not None:
            pending.extend(entry["parents"])
    return False


def _snapshot_size(entry: dict, target_skills: list[str]) -> dict | None:
    skills = {
        item["name"]: item for item in entry["manifest"]["skills"]
    }
    if sorted(skills) != target_skills:
        return None
    files = [
        file
        for skill_name in target_skills
        for file in skills[skill_name]["files"]
    ]
    return {
        "snapshot_id": entry["snapshot_id"],
        "revision_id": entry["revision_id"],
        "bytes": sum(item["bytes"] for item in files),
        "lines": sum(
            item["lines"] for item in files if item["lines"] is not None
        ),
        "files": len(files),
    }


def _snapshot_target_skill_identities(
    entry: dict,
    target_skills: list[str],
) -> list[dict] | None:
    skills = {
        item["name"]: item for item in entry["manifest"]["skills"]
    }
    if sorted(skills) != target_skills:
        return None
    return [
        {
            "name": name,
            "evaluator_fingerprint": skills[name][
                "evaluator_skill_identity"
            ],
        }
        for name in target_skills
    ]


def _size_reduction(before: dict, after: dict | None) -> dict | None:
    if after is None:
        return None
    removed = before["bytes"] - after["bytes"]
    return {
        "bytes": removed,
        "percent": (
            round((removed / before["bytes"]) * 100, 1)
            if before["bytes"]
            else 0.0
        ),
    }


def _snapshot_task_passes(
    project: dict,
    catalog: dict[str, dict],
    entry: dict,
    task_id: str,
    attempts: list[dict],
) -> bool:
    lineage = {
        "snapshot_id": entry["revision_id"],
        "snapshot_ids": sorted(
            snapshot_id
            for snapshot_id, candidate in catalog.items()
            if candidate["revision_id"] == entry["revision_id"]
        ),
        "prior_revisions": [],
    }
    scorecard = _task_scorecard(project, lineage, attempts)
    task = next(
        (item for item in scorecard if item["task_id"] == task_id),
        None,
    )
    return task is not None and task["result"] == "passing"


def _maintained_task_results(
    declaration: dict,
    maintained_tasks: list[dict],
    activity: list[dict],
    treatment_id: str,
) -> dict:
    definitions = {
        item["task_id"]: item for item in declaration["tasks"]
    }
    bindings = declaration["case_bindings"]
    rows = []
    for maintained in maintained_tasks:
        definition = definitions.get(maintained["task_id"])
        if (
            definition is None
            or task_fingerprint(definition)
            != maintained["task_fingerprint"]
        ):
            rows.append({
                "task_id": maintained["task_id"],
                "status": "unavailable",
            })
            continue
        rule = definition["qualification"]
        required = [
            item for item in bindings
            if item["task_id"] == maintained["task_id"]
            and item["role"] in rule["required_roles"]
        ]
        statuses = []
        for binding in required:
            attempts = [
                item for item in activity
                if item["treatment_id"] == treatment_id
                and item["case_id"] == binding["case_id"]
                and item["case_revision"] == binding["case_revision"]
                and item["state"] == "terminal"
            ]
            if (
                len(attempts)
                < rule["minimum_terminal_repetitions_per_case"]
            ):
                statuses.append("unavailable")
            elif sum(
                item["evaluator_result"] == "PASS" for item in attempts
            ) < rule["required_passes_per_case"]:
                statuses.append("failed")
            else:
                statuses.append("passed")
        status = (
            "unavailable"
            if not required or "unavailable" in statuses
            else "failed"
            if "failed" in statuses
            else "passed"
        )
        rows.append({
            "task_id": maintained["task_id"],
            "status": status,
        })
    return {
        "passed": sum(item["status"] == "passed" for item in rows),
        "failed": sum(item["status"] == "failed" for item in rows),
        "unavailable": sum(
            item["status"] == "unavailable" for item in rows
        ),
        "total": len(rows),
        "tasks": rows,
    }


def _ablation_projection(
    state_root: Path,
    project: dict,
) -> tuple[dict[str, dict], dict | None, bool]:
    from dashboard_projection import experiment_projection
    from holdout_dashboard import holdout_projection

    catalog, invalid = _snapshot_catalog(project)
    attempts, _ = _terminal_attempts(project)
    current_tasks = {
        item["task_id"]: item for item in project["tasks"]
    }
    experiments = []
    for source in project["sources"]:
        if not source["available"]:
            continue
        records, conflicts, rejected = experiment_activity_records(
            source["corpus_root"]
        )
        invalid = invalid or bool(conflicts or rejected)
        declared_at = {
            item["subject"]["experiment_id"]: item["recorded_at"]
            for item in records
            if item["event_type"] == "experiment_declared"
        }
        projection = experiment_projection(
            source["corpus_root"],
            source["campaign"]["campaign_id"],
        )
        for item in projection["items"]:
            if item["experiment_kind"] == "treatment_search":
                continue
            ablation = item["ablation"]
            if ablation["project_id"] != project["project_id"]:
                continue
            try:
                declaration = archived_project_declaration(
                    source["corpus_root"],
                    ablation["project_declaration_sha256"],
                )
            except (OSError, ValueError, json.JSONDecodeError):
                invalid = True
                continue
            if declaration["project_id"] != project["project_id"]:
                invalid = True
                continue
            maintained = ablation["maintained_tasks"]
            if any(
                task_id not in current_tasks
                or task_fingerprint(current_tasks[task_id])
                != maintained_row["task_fingerprint"]
                for maintained_row in maintained
                for task_id in [maintained_row["task_id"]]
            ):
                continue
            experiments.append({
                "item": item,
                "ablation": ablation,
                "declaration": declaration,
                "declared_at": declared_at.get(item["experiment_id"]),
            })

    delta_candidates: dict[str, list[dict]] = {}
    whole_candidates = []
    for experiment in experiments:
        item = experiment["item"]
        ablation = experiment["ablation"]
        if item["experiment_kind"] == "delta_ablation":
            task_id = ablation["task_id"]
            baseline = catalog.get(ablation["baseline_snapshot_id"])
            exploratory = catalog.get(ablation["exploratory_snapshot_id"])
            candidates = [
                {
                    **row,
                    "entry": catalog.get(row["snapshot_id"]),
                }
                for row in ablation["candidate_snapshots"]
            ]
            if (
                task_id not in current_tasks
                or baseline is None
                or exploratory is None
                or any(row["entry"] is None for row in candidates)
                or not _snapshot_descends(
                    catalog,
                    exploratory["snapshot_id"],
                    baseline["snapshot_id"],
                )
                or any(
                    not _snapshot_descends(
                        catalog,
                        row["snapshot_id"],
                        exploratory["snapshot_id"],
                    )
                    for row in candidates
                )
            ):
                invalid = True
                continue
            before = _snapshot_size(exploratory, project["target_skills"])
            candidate_sizes = [
                {
                    "treatment_id": row["treatment_id"],
                    "size": _snapshot_size(
                        row["entry"],
                        project["target_skills"],
                    ),
                    "target_skill_identities": (
                        _snapshot_target_skill_identities(
                            row["entry"],
                            project["target_skills"],
                        )
                    ),
                }
                for row in candidates
            ]
            treatments = {
                row["treatment_id"]: row for row in item["treatments"]
            }
            if (
                before is None
                or not set(baseline["roles"]) & {"published", "released"}
                or not _snapshot_task_passes(
                    project,
                    catalog,
                    exploratory,
                    task_id,
                    attempts,
                )
                or any(
                    row["size"] is None
                    or row["target_skill_identities"] is None
                    or row["treatment_id"] not in treatments
                    or treatments[row["treatment_id"]][
                        "target_skill_identities"
                    ] != row["target_skill_identities"]
                    for row in candidate_sizes
                )
            ):
                invalid = True
                continue
            candidate_sizes.sort(
                key=lambda row: (
                    row["size"]["bytes"],
                    row["treatment_id"],
                )
            )
            current = candidate_sizes[0]
            selected_treatment = item["selection"].get(
                "selected_treatment_id"
            )
            selected = next(
                (
                    row for row in candidate_sizes
                    if row["treatment_id"] == selected_treatment
                ),
                None,
            )
            maintained = (
                _maintained_task_results(
                    experiment["declaration"],
                    ablation["maintained_tasks"],
                    item["activity"],
                    selected_treatment,
                )
                if selected is not None
                else {
                    "passed": 0,
                    "failed": 0,
                    "unavailable": len(ablation["maintained_tasks"]),
                    "total": len(ablation["maintained_tasks"]),
                    "tasks": [
                        {
                            "task_id": row["task_id"],
                            "status": "unavailable",
                        }
                        for row in ablation["maintained_tasks"]
                    ],
                }
            )
            qualified = (
                selected is not None
                and maintained["passed"] == maintained["total"]
            )
            changes = ablation["instruction_changes"]
            delta_candidates.setdefault(task_id, []).append({
                "status": (
                    "qualified"
                    if qualified
                    else "regressed"
                    if selected is not None and maintained["failed"]
                    else "active"
                ),
                "experiment_id": item["experiment_id"],
                "declared_at": experiment["declared_at"],
                "baseline": _snapshot_size(
                    baseline,
                    project["target_skills"],
                ),
                "exploratory": before,
                "current": current["size"],
                "final": selected["size"] if qualified else None,
                "reduction": {
                    "current": _size_reduction(before, current["size"]),
                    "final": _size_reduction(
                        before,
                        selected["size"] if qualified else None,
                    ),
                },
                "maintained_wins": maintained,
                "instruction_changes": {
                    "removed": sum(
                        row["disposition"] == "removed" for row in changes
                    ),
                    "retained": sum(
                        row["disposition"] == "retained" for row in changes
                    ),
                    "restored": [
                        {
                            "instruction_id": row["instruction_id"],
                            "reason": row["reason"],
                        }
                        for row in changes
                        if row["disposition"] == "restored"
                    ],
                },
                "selection": item["selection"],
            })
        else:
            arms = []
            for row in ablation["arms"]:
                entry = catalog.get(row["snapshot_id"])
                size = (
                    _snapshot_size(entry, project["target_skills"])
                    if entry is not None
                    else None
                )
                if size is None:
                    invalid = True
                    arms = []
                    break
                treatment = next(
                    (
                        treatment for treatment in item["treatments"]
                        if treatment["treatment_id"]
                        == row["treatment_id"]
                    ),
                    None,
                )
                if (
                    treatment is None
                    or treatment["target_skill_identities"]
                    != _snapshot_target_skill_identities(
                        entry,
                        project["target_skills"],
                    )
                ):
                    invalid = True
                    arms = []
                    break
                maintained = _maintained_task_results(
                    experiment["declaration"],
                    ablation["maintained_tasks"],
                    item["activity"],
                    row["treatment_id"],
                )
                holdouts = holdout_projection(
                    state_root,
                    project["project_id"],
                    project["holdout_requirements"],
                    size["revision_id"],
                )
                holdout_qualification = (
                    None
                    if not holdouts
                    or any(record["status"] != "completed" for record in holdouts)
                    else all(
                        record["qualification"] is True for record in holdouts
                    )
                )
                repetitions = [
                    activity["repetition"]
                    for activity in item["activity"]
                    if activity["treatment_id"] == row["treatment_id"]
                    and activity["state"] == "terminal"
                    and activity["evaluator_result"] == "PASS"
                ]
                arms.append({
                    "arm": row["arm"],
                    "treatment_id": row["treatment_id"],
                    "size": size,
                    "maintained_wins": maintained,
                    "holdout_qualification": holdout_qualification,
                    "retry_dependent": bool(repetitions)
                    and min(repetitions) > 1,
                    "selection_state": next(
                        treatment["selection_state"]
                        for treatment in item["treatments"]
                        if treatment["treatment_id"] == row["treatment_id"]
                    ),
                })
            if arms:
                whole_candidates.append({
                    "status": item["selection"]["status"],
                    "experiment_id": item["experiment_id"],
                    "declared_at": experiment["declared_at"],
                    "arms": sorted(arms, key=lambda row: row["arm"]),
                    "selection": item["selection"],
                })

    delta = {}
    for task_id, rows in delta_candidates.items():
        rows.sort(
            key=lambda row: (
                row["declared_at"] or "",
                row["experiment_id"],
            ),
            reverse=True,
        )
        if len(rows) > 1 and rows[0]["declared_at"] == rows[1]["declared_at"]:
            invalid = True
            continue
        delta[task_id] = rows[0]
    whole = None
    if whole_candidates:
        whole_candidates.sort(
            key=lambda row: (
                row["declared_at"] or "",
                row["experiment_id"],
            ),
            reverse=True,
        )
        if (
            len(whole_candidates) > 1
            and whole_candidates[0]["declared_at"]
            == whole_candidates[1]["declared_at"]
        ):
            invalid = True
        else:
            whole = whole_candidates[0]
    return delta, whole, invalid


def _ablation_qualifies_selected_revision(
    ablation: dict | None,
    lineage: dict,
) -> bool:
    return (
        ablation is not None
        and ablation["status"] == "qualified"
        and ablation["final"]["revision_id"] == lineage.get("snapshot_id")
    )


def project_projection(state_root: Path, project_id: str) -> dict:
    from holdout_dashboard import holdout_projection

    project = reconciled_project(state_root, project_id)
    lineage = _project_lineage(project) if project["available"] else {
        "status": "unavailable",
        "snapshot_id": None,
        "snapshot_ids": [],
        "roles": [],
        "prior_revisions": [],
        "known_revisions": [],
        "conflicts": [],
    }
    attempts, pre_project = _terminal_attempts(project)
    distributed_runs, distributed_activity = (
        _distributed_projection(project)
        if project["available"]
        else ([], [])
    )
    tasks = (
        _task_scorecard(project, lineage, attempts)
        if project["available"]
        else []
    )
    holdouts = holdout_projection(
        state_root,
        project_id,
        project["holdout_requirements"],
        lineage.get("snapshot_id"),
    ) if project["available"] else []
    delta_ablation, whole_skill_ablation, ablation_invalid = (
        _ablation_projection(state_root, project)
        if project["available"]
        else ({}, None, False)
    )
    local_runs = [
        row
        for source in project["sources"]
        for row in _run_projection(
            source,
            project,
            [
                item
                for item in attempts
                if item["campaign_id"]
                == source["campaign"]["campaign_id"]
            ],
        )
    ]
    for task in tasks:
        definition = next(
            item for item in project["tasks"]
            if item["task_id"] == task["task_id"]
        )
        bindings = [
            item for item in project["case_bindings"]
            if item["task_id"] == task["task_id"]
            and item["role"] in definition["qualification"]["required_roles"]
        ]
        task["phase"] = _task_phase(
            project,
            lineage,
            definition,
            task["result"],
            bindings,
            attempts,
        )
        task["safe_progress"] = _task_safe_progress(
            definition,
            bindings,
            lineage,
            attempts,
            distributed_activity,
        )
        task["ablation"] = delta_ablation.get(task["task_id"])
        task_holdouts = [
            item for item in holdouts
            if task["task_id"] in item["task_ids"]
        ]
        if (
            task["phase"]["phase"] != "published"
            and any(item["status"] == "active" for item in task_holdouts)
        ):
            task["phase"] = {
                "status": "available",
                "phase": "holdout_validation",
                "authority": "holdout_receipt",
                "recorded_at": None,
            }
        elif (
            task["phase"]["phase"] != "published"
            and             task["result"] == "passing"
            and _ablation_qualifies_selected_revision(
                task["ablation"],
                lineage,
            )
            and all(
                item["status"] == "completed"
                and item["qualification"] is True
                for item in task_holdouts
            )
        ):
            task["phase"] = {
                "status": "available",
                "phase": "ready_to_publish",
                "authority": "holdout_receipt",
                "recorded_at": None,
            }
        if (
            task["result"] == "passing"
            and task["ablation"] is not None
            and task["ablation"]["status"] == "qualified"
            and task["phase"]["phase"] == "ready_to_publish"
            and set(lineage.get("roles", [])) & {"published", "released"}
        ):
            task["phase"] = {
                "status": "available",
                "phase": "published",
                "authority": "lineage",
                "recorded_at": None,
            }
        qualified_at = task["timing"]["first_qualified_pass_at"]
        bounded_runs = [
            run for run in local_runs + distributed_runs
            if task["task_id"] in run["task_ids"]
            and (
                run["launcher_kind"] == "distributed_experiment"
                or run.get("_task_fingerprints", {}).get(task["task_id"])
                == task_fingerprint(definition)
            )
            and (
                qualified_at is None
                or run.get("started_at") is None
                or parse_instant(run["started_at"])
                <= parse_instant(qualified_at)
            )
        ]
        task["effort"]["infrastructure_failures"] = sum(
            run["state"] in {
                "infrastructure_failed",
                "liveness_lost",
                "liveness_unavailable",
                "conflicted",
            }
            for run in bounded_runs
        )
    runs = local_runs + distributed_runs
    for run in runs:
        run.pop("_task_fingerprints", None)
    runs.sort(
        key=lambda item: (item.get("started_at") or "", item["run_id"]),
        reverse=True,
    )
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
        "holdouts": holdouts,
        "whole_skill_ablation": whole_skill_ablation,
        "pre_project_history": pre_project,
        "conflicts": {
            **project["conflicts"],
            "ablation": ablation_invalid,
        },
        "unsupported": {
            "task_phase": True,
            "safe_progress": True,
            "holdout_execution": True,
            "ablation": True,
            "distributed_runs": True,
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
                        "regressed": 0,
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
                    "regressed": sum(
                        item["result"] == "regressed"
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
