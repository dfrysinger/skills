"""Lifecycle commands for the local skill-evaluation dashboard."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from distributed_campaign import (
    canonical_fingerprint,
    validate_dispatch_binding,
)
from dashboard_state import (
    capture_skill_snapshot,
    create_campaign,
    emit_experiment_activity_event,
    emit_experiment_selection,
    emit_lineage_event,
    emit_task_progress_event,
    ensure_state_root,
    experiment_activity_records,
    mark_session_opened,
    read_session,
    register_session,
    regular_json,
    selection_rule_fingerprint,
    session_event,
    update_session,
)


DEFAULT_STATE_ROOT = Path.home() / ".copilot" / "skill-evaluation-ui"
SERVICE_FIELDS = {"schema_version", "generation", "pid", "port", "started_at"}
STARTED_PROCESSES: dict[int, subprocess.Popen] = {}
EXPERIMENT_DECLARATION_SOURCE_FIELDS = {
    "schema_version",
    "experiment_id",
    "experiment_fingerprint",
    "payload",
}
RETENTION_MANIFEST_FIELDS = {
    "schema_version",
    "receipt_sha256",
    "artifact_sha256",
    "source_ids",
}


def state_root(value: Path | None = None) -> Path:
    configured = value or Path(
        os.environ.get(
            "SKILL_EVAL_DASHBOARD_STATE_ROOT",
            str(DEFAULT_STATE_ROOT),
        )
    )
    return ensure_state_root(configured)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
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
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def startup_lock(root: Path):
    path = root / "startup.lock"
    with path.open("a+", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def validate_service(value: dict) -> dict:
    if set(value) != SERVICE_FIELDS or value.get("schema_version") != 1:
        raise ValueError("unsupported dashboard service receipt")
    if (
        not isinstance(value.get("generation"), str)
        or len(value["generation"]) != 32
        or type(value.get("pid")) is not int
        or value["pid"] < 1
        or type(value.get("port")) is not int
        or not 0 < value["port"] < 65536
        or not isinstance(value.get("started_at"), str)
    ):
        raise ValueError("malformed dashboard service receipt")
    return value


def read_service(root: Path) -> dict | None:
    path = root / "service.json"
    if not path.exists():
        return None
    return validate_service(regular_json(path, "service receipt"))


def read_root_secret(root: Path) -> str:
    path = root / "root-secret"
    if path.is_symlink() or not path.is_file():
        raise ValueError("dashboard root secret is unavailable")
    if path.stat().st_mode & 0o077:
        raise ValueError("dashboard root secret permissions are too broad")
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 40:
        raise ValueError("dashboard root secret is malformed")
    return value


def control_request(
    service: dict,
    secret: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    timeout: float = 2,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{service['port']}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Root {secret}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("dashboard control response must be an object")
    return value


def healthy_service(root: Path) -> dict | None:
    try:
        service = read_service(root)
        if service is None:
            return None
        health = control_request(
            service,
            read_root_secret(root),
            "/_control/health",
        )
        if (
            health.get("generation") != service["generation"]
            or health.get("pid") != service["pid"]
            or health.get("port") != service["port"]
        ):
            return None
        return service
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return None


def write_root_secret(root: Path) -> Path:
    path = root / "root-secret"
    temporary = root / f".root-secret.{os.getpid()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(32) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def start_service(root: Path, port: int = 0) -> dict:
    generation = secrets.token_hex(16)
    secret_path = write_root_secret(root)
    startup = root / f".startup-{generation}.json"
    log = root / f"service-{generation}.log"
    command = [
        sys.executable,
        str(Path(__file__).with_name("dashboard_server.py")),
        "--state-root",
        str(root),
        "--generation",
        generation,
        "--root-secret-file",
        str(secret_path),
        "--port",
        str(port),
        "--startup-file",
        str(startup),
    ]
    with log.open("ab", buffering=0) as output:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    deadline = time.monotonic() + 8
    started = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            process.wait()
            raise ValueError(f"dashboard service exited; see {log}")
        if startup.is_file():
            started = regular_json(startup, "dashboard startup receipt")
            break
        time.sleep(0.05)
    startup.unlink(missing_ok=True)
    if not isinstance(started, dict):
        process.terminate()
        raise ValueError(f"dashboard service did not start; see {log}")
    service = validate_service({
        "schema_version": 1,
        "generation": started.get("generation"),
        "pid": started.get("pid"),
        "port": started.get("port"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    if (
        service["generation"] != generation
        or service["pid"] != process.pid
    ):
        process.terminate()
        raise ValueError("dashboard startup identity mismatch")
    health = control_request(service, read_root_secret(root), "/_control/health")
    if health.get("generation") != generation or health.get("pid") != process.pid:
        process.terminate()
        raise ValueError("dashboard authenticated health mismatch")
    atomic_json(root / "service.json", service)
    STARTED_PROCESSES[process.pid] = process
    return service


def ensure_service(root: Path) -> tuple[dict, bool]:
    root = state_root(root)
    with startup_lock(root):
        try:
            previous = read_service(root)
        except ValueError:
            previous = None
        service = healthy_service(root)
        if service is not None:
            return service, False
        preferred_port = previous["port"] if previous else 0
        if preferred_port:
            for host in ("127.0.0.1", "0.0.0.0"):
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        probe.bind((host, preferred_port))
                    except OSError:
                        preferred_port = 0
                        break
        service = start_service(root, preferred_port)
        return service, True


def ensure_dashboard(
    corpus: Path,
    root: Path | None = None,
) -> dict:
    root = state_root(root)
    registration = create_campaign(root, corpus)
    service, started = ensure_service(root)
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "service_started": started,
        "url": (
            f"http://127.0.0.1:{service['port']}"
            f"/campaign/{registration['campaign_id']}"
        ),
        "opened": False,
    }


def open_dashboard(
    corpus: Path,
    root: Path | None = None,
    *,
    browser_open=webbrowser.open,
) -> dict:
    root = state_root(root)
    ensured = ensure_dashboard(corpus, root)
    service = healthy_service(root)
    if service is None:
        raise ValueError("dashboard service is unavailable after ensure")
    opened = control_request(
        service,
        read_root_secret(root),
        "/_control/open",
        method="POST",
        payload={"campaign_id": ensured["campaign_id"]},
    )
    capability = opened.get("capability")
    route = opened.get("route")
    if not isinstance(capability, str) or not isinstance(route, str):
        raise ValueError("dashboard open response is malformed")
    browser_url = (
        f"http://127.0.0.1:{service['port']}{route}"
        f"#cap={quote(capability, safe='')}"
    )
    if not browser_open(browser_url):
        raise ValueError("browser open failed; run dashboard open again")
    return {
        **ensured,
        "url": f"http://127.0.0.1:{service['port']}{route}",
        "opened": True,
    }


def register_dashboard(
    corpus: Path,
    session_id: str,
    root: Path | None = None,
    *,
    browser_open=webbrowser.open,
) -> dict:
    root = state_root(root)
    session, created = register_session(root, corpus, session_id)
    service, started = ensure_service(root)
    opened = False
    if session["opened_at"] is None:
        response = control_request(
            service,
            read_root_secret(root),
            "/_control/open",
            method="POST",
            payload={"campaign_id": session["campaign_id"]},
        )
        capability = response.get("capability")
        route = response.get("route")
        if not isinstance(capability, str) or not isinstance(route, str):
            raise ValueError("dashboard open response is malformed")
        browser_url = (
            f"http://127.0.0.1:{service['port']}{route}"
            f"#cap={quote(capability, safe='')}"
        )
        if not browser_open(browser_url):
            raise ValueError("browser open failed; run dashboard register again")
        session, opened = mark_session_opened(
            corpus,
            session_id,
            session["writer_generation"],
        )
    return {
        "schema_version": 1,
        "campaign_id": session["campaign_id"],
        "session_id": session["session_id"],
        "writer_generation": session["writer_generation"],
        "session_created": created,
        "service_started": started,
        "url": (
            f"http://127.0.0.1:{service['port']}"
            f"/campaign/{session['campaign_id']}"
        ),
        "opened": opened,
    }


def heartbeat_dashboard(
    corpus: Path,
    session_id: str,
    state: str,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    session = read_session(corpus, session_id)
    if session is None or session["campaign_id"] != registration["campaign_id"]:
        raise ValueError("dashboard session is not registered")
    updated = update_session(
        corpus,
        session_id,
        session["writer_generation"],
        heartbeat_at=datetime.now(timezone.utc).isoformat(),
        state=state,
    )
    return {
        "schema_version": 1,
        "campaign_id": updated["campaign_id"],
        "session_id": updated["session_id"],
        "state": updated["state"],
        "heartbeat_at": updated["heartbeat_at"],
    }


def assignment_dashboard(
    corpus: Path,
    session_id: str,
    event_type: str,
    case_id: str,
    summary: str,
    *,
    skill_identity: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    session = read_session(corpus, session_id)
    if session is None or session["campaign_id"] != registration["campaign_id"]:
        raise ValueError("dashboard session is not registered")
    from skill_eval import digest, frozen_case_path

    revision = digest(frozen_case_path(corpus, case_id) / "case-manifest.json")
    event = session_event(
        corpus,
        session_id,
        session["writer_generation"],
        event_type=event_type,
        case_id=case_id,
        case_revision=revision,
        skill_identity=skill_identity,
        summary=summary,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "session_id": session_id,
        "event_id": event["event_id"],
        "event_type": event["event_type"],
    }


def lineage_snapshot_dashboard(
    corpus: Path,
    session_id: str,
    plugin_dir: Path,
    skills: list[str],
    roles: list[str],
    summary: str,
    *,
    parents: list[dict] | None = None,
    provenance_kind: str | None = None,
    source_revision: str | None = None,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    session = read_session(corpus, session_id)
    if session is None or session["campaign_id"] != registration["campaign_id"]:
        raise ValueError("dashboard session is not registered")
    snapshot = capture_skill_snapshot(corpus, plugin_dir, skills)
    event = emit_lineage_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        },
        snapshot_id=snapshot["snapshot_id"],
        roles=roles,
        parents=parents or [],
        summary=summary,
        provenance_kind=provenance_kind,
        source_revision=source_revision,
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "session_id": session_id,
        "snapshot_id": snapshot["snapshot_id"],
        "event_id": event["event_id"],
        "roles": event["payload"]["roles"],
    }


def task_progress_dashboard(
    corpus: Path,
    session_id: str,
    case_id: str,
    snapshot_id: str,
    frontier: str,
    classification: str,
    movement: str,
    summary: str,
    *,
    uptake: list[dict] | None = None,
    blocker: str | None = None,
    next_action: str | None = None,
    comparison_snapshot_id: str | None = None,
    sources: list[dict] | None = None,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    session = read_session(corpus, session_id)
    if session is None or session["campaign_id"] != registration["campaign_id"]:
        raise ValueError("dashboard session is not registered")
    from skill_eval import digest, frozen_case_path

    revision = digest(frozen_case_path(corpus, case_id) / "case-manifest.json")
    event = emit_task_progress_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        },
        snapshot_id=snapshot_id,
        case_id=case_id,
        case_revision=revision,
        frontier=frontier,
        classification=classification,
        movement=movement,
        summary=summary,
        uptake=uptake,
        blocker=blocker,
        next_action=next_action,
        comparison_snapshot_id=comparison_snapshot_id,
        sources=sources,
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "session_id": session_id,
        "case_id": case_id,
        "case_revision": revision,
        "snapshot_id": snapshot_id,
        "event_id": event["event_id"],
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is unavailable")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _safe_source_ids(value: object) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) != len(set(value))
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 160
            or not all(character.isalnum() or character in "._-" for character in item)
            for item in value
        )
    ):
        raise ValueError("retention source IDs are invalid")
    return sorted(value)


def _declaration(
    corpus: Path,
    experiment_id: str,
    experiment_fingerprint: str,
) -> dict:
    records, conflicts, _ = experiment_activity_records(corpus)
    conflicted = {item["event_id"] for item in conflicts}
    declarations = [
        item
        for item in records
        if (
            item["event_type"] == "experiment_declared"
            and item["subject"]["experiment_id"] == experiment_id
            and item["subject"]["experiment_fingerprint"] == experiment_fingerprint
            and item["event_id"] not in conflicted
        )
    ]
    if len(declarations) != 1:
        raise ValueError("experiment declaration is unavailable or conflicted")
    return declarations[0]


def experiment_declaration_dashboard(
    corpus: Path,
    source: Path,
    *,
    session_id: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    session = read_session(corpus, session_id)
    if session is None or session["campaign_id"] != registration["campaign_id"]:
        raise ValueError("dashboard session is not registered")
    selected = regular_json(source, "experiment declaration source")
    if (
        set(selected) != EXPERIMENT_DECLARATION_SOURCE_FIELDS
        or selected.get("schema_version") != 1
    ):
        raise ValueError("unsupported experiment declaration source")
    event = emit_experiment_activity_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        },
        event_type="experiment_declared",
        experiment_id=selected["experiment_id"],
        experiment_fingerprint=selected["experiment_fingerprint"],
        payload=selected["payload"],
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "experiment_id": event["subject"]["experiment_id"],
    }


def _validated_dispatch(
    plan_path: Path,
    run_path: Path,
    binding_path: Path,
    declaration: dict,
) -> tuple[dict, dict, dict]:
    plan = regular_json(plan_path, "distributed plan")
    run = regular_json(run_path, "private dispatch run")
    binding = regular_json(binding_path, "dispatch binding")
    validate_dispatch_binding(binding, plan, run)
    _validate_plan_against_declaration(plan, declaration)
    return plan, run, binding


def _validate_plan_against_declaration(plan: dict, declaration: dict) -> None:
    declared_attempts = {
        item["attempt_id"]: item
        for item in declaration["payload"]["attempts"]
    }
    declared_treatments = {
        item["treatment_id"]: item
        for item in declaration["payload"]["treatments"]
    }
    jobs = plan.get("matrix", {}).get("include")
    _require(isinstance(jobs, list) and jobs, "distributed plan has no attempts")
    seen = set()
    for job in jobs:
        attempt_id = job.get("attemptId")
        _require(
            isinstance(attempt_id, str)
            and attempt_id not in seen
            and attempt_id in declared_attempts,
            "distributed plan attempt is undeclared or duplicated",
        )
        seen.add(attempt_id)
        declared = declared_attempts[attempt_id]
        expected = {
            "caseId": declared["case_id"],
            "caseRevision": declared["case_revision"],
            "treatmentId": declared["treatment_id"],
            "repetition": declared["repetition"],
            "candidateModel": declared["candidate_model"],
            "candidateTimeoutSeconds": declaration["payload"][
                "candidate_timeout_seconds"
            ],
            "targetOs": declared["target_os"],
            "architecture": declared["architecture"],
            "route": declared["route"],
        }
        _require(
            all(job.get(key) == value for key, value in expected.items()),
            "distributed plan attempt differs from its declaration",
        )
        treatment = declared_treatments[declared["treatment_id"]]
        _require(
            job.get("treatmentFingerprint")
            == treatment["content_fingerprint"]
            and job.get("targetSkillIdentities")
            == [
                {
                    "skillName": item["name"],
                    "evaluatorFingerprint": item["evaluator_fingerprint"],
                }
                for item in treatment["target_skill_identities"]
            ],
            "distributed plan treatment differs from its declaration",
        )


def experiment_dispatch_dashboard(
    corpus: Path,
    plan_path: Path,
    run_path: Path,
    binding_path: Path,
    *,
    experiment_id: str,
    opaque_source_id: str,
    writer_id: str,
    writer_generation: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    plan = regular_json(plan_path, "distributed plan")
    fingerprint = plan.get("experimentPlanSha256")
    declaration = _declaration(corpus, experiment_id, fingerprint)
    plan, run, binding = _validated_dispatch(
        plan_path,
        run_path,
        binding_path,
        declaration,
    )
    fingerprint = binding["experimentPlanSha256"]
    jobs = sorted([
        {
            "job_name": item["jobName"],
            "attempt_id": item["attemptId"],
            "stage_kind": item["stage"],
        }
        for item in binding["expectedJobs"]
    ], key=lambda item: item["job_name"])
    workflow_revision_fingerprint = canonical_fingerprint({
        "workflowPath": run["workflowPath"],
        "workflowSha": run["workflowSha"],
    })
    event = emit_experiment_activity_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "distributed_coordinator",
            "id": writer_id,
            "generation": writer_generation,
        },
        event_type="cloud_dispatch_bound",
        experiment_id=experiment_id,
        experiment_fingerprint=fingerprint,
        run_binding_fingerprint=binding["runBindingFingerprint"],
        payload={
            "plan_fingerprint": fingerprint,
            "package_archive_sha256": binding["packageIdentity"][
                "packageArchiveSha256"
            ],
            "candidate_package_archive_sha256": binding["packageIdentity"][
                "candidatePackageArchiveSha256"
            ],
            "package_manifest_sha256": binding["packageIdentity"][
                "packageManifestSha256"
            ],
            "workflow_revision_fingerprint": workflow_revision_fingerprint,
            "jobs": jobs,
            "opaque_source_id": opaque_source_id,
        },
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "experiment_id": experiment_id,
    }


def _validated_observer_output(
    observation_path: Path,
    plan: dict,
    run: dict,
    binding: dict,
) -> tuple[dict, list[dict]]:
    observed = regular_json(observation_path, "exact-known-jobs observation")
    expected_top = {
        "schema_version",
        "repository",
        "host",
        "non_atomic",
        "observations",
        "calls",
        "call_count",
        "projected_response_bytes",
        "client_wall_seconds",
        "coverage",
    }
    _require(
        set(observed) == expected_top and observed.get("schema_version") == 3,
        "unsupported exact-known-jobs observation",
    )
    _require(observed["repository"] == run["repositoryFullName"], "observer repository changed")
    _require(observed["non_atomic"] is True, "observer non-atomic flag changed")
    _require(
        observed["coverage"] == {
            "scope": "requested-runs-and-exact-jobs-only",
            "repository_enumerated": False,
        },
        "observer coverage changed",
    )
    _require(
        isinstance(observed["observations"], list)
        and len(observed["observations"]) == 1,
        "observer must contain one exact run",
    )
    snapshot = observed["observations"][0]
    _require(
        isinstance(snapshot, dict)
        and set(snapshot) == {"run", "provenance", "jobs", "jobs_provenance"},
        "observer run snapshot is invalid",
    )
    run_observation = snapshot["run"]
    repository = run_observation.get("repository")
    _require(
        isinstance(repository, dict)
        and set(repository) == {"id", "full_name", "private"}
        and type(repository.get("private")) is bool,
        "observer repository record is invalid",
    )
    expected_run = {
        "id": run["runId"],
        "workflow_id": run["workflowId"],
        "path": run["workflowPath"],
        "event": run["event"],
        "head_sha": run["headSha"],
        "head_branch": run["headBranch"],
        "run_attempt": run["runAttempt"],
        "repository": {
            "id": run["repositoryId"],
            "full_name": run["repositoryFullName"],
            "private": repository["private"],
        },
    }
    _require(
        all(run_observation.get(key) == value for key, value in expected_run.items()),
        "observer run binding changed",
    )
    _require(
        run_observation.get("status")
        in {"queued", "in_progress", "completed", "waiting", "requested", "pending"},
        "observer run status is invalid",
    )
    expected_jobs = {
        item["jobName"]: item for item in binding["expectedJobs"]
    }
    jobs = snapshot["jobs"]
    _require(
        isinstance(jobs, list)
        and {item.get("name") for item in jobs} == set(expected_jobs)
        and len(jobs) == len(expected_jobs),
        "observer job-name set differs from dispatch binding",
    )
    projected = []
    for source_index, item in enumerate(sorted(jobs, key=lambda value: value["name"])):
        expected = expected_jobs[item["name"]]
        _require(
            item.get("run_id") == run["runId"]
            and item.get("run_attempt") == 1
            and item.get("head_sha") == run["headSha"],
            "observer job binding changed",
        )
        status = item.get("status")
        conclusion = item.get("conclusion")
        _require(
            status
            in {"queued", "in_progress", "completed", "waiting", "requested", "pending"},
            "observer job status is invalid",
        )
        _require(
            (status == "completed" and isinstance(conclusion, str) and conclusion)
            or (status != "completed" and conclusion is None),
            "observer job conclusion is invalid",
        )
        projected.append({
            "source_index": source_index,
            "job_name": item["name"],
            "attempt_id": expected["attemptId"],
            "stage_kind": expected["stage"],
            "status": status,
            "conclusion": conclusion,
            "started_at": item.get("started_at"),
            "completed_at": item.get("completed_at"),
        })
    _require(
        observed.get("call_count") == len(observed.get("calls", []))
        and type(observed.get("projected_response_bytes")) is int
        and observed["projected_response_bytes"] >= 0
        and type(observed.get("client_wall_seconds")) in {int, float}
        and observed["client_wall_seconds"] >= 0,
        "observer accounting is invalid",
    )
    return observed, projected


def experiment_observation_dashboard(
    corpus: Path,
    observation_path: Path,
    plan_path: Path,
    run_path: Path,
    binding_path: Path,
    *,
    experiment_id: str,
    opaque_source_id: str,
    writer_id: str,
    writer_generation: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    plan = regular_json(plan_path, "distributed plan")
    fingerprint = plan.get("experimentPlanSha256")
    declaration = _declaration(corpus, experiment_id, fingerprint)
    plan, run, binding = _validated_dispatch(
        plan_path,
        run_path,
        binding_path,
        declaration,
    )
    fingerprint = binding["experimentPlanSha256"]
    records, conflicts, _ = experiment_activity_records(corpus)
    conflicted = {item["event_id"] for item in conflicts}
    dispatches = [
        item
        for item in records
        if (
            item["event_type"] == "cloud_dispatch_bound"
            and item["subject"]["experiment_id"] == experiment_id
            and item["subject"]["experiment_fingerprint"] == fingerprint
            and item["subject"]["run_binding_fingerprint"]
            == binding["runBindingFingerprint"]
            and item["event_id"] not in conflicted
        )
    ]
    if len(dispatches) != 1:
        raise ValueError("cloud dispatch binding is unavailable or conflicted")
    observed, observations = _validated_observer_output(
        observation_path,
        plan,
        run,
        binding,
    )
    event = emit_experiment_activity_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "cloud_observer",
            "id": writer_id,
            "generation": writer_generation,
        },
        event_type="cloud_transport_observed",
        experiment_id=experiment_id,
        experiment_fingerprint=fingerprint,
        run_binding_fingerprint=binding["runBindingFingerprint"],
        payload={
            "observer_snapshot_fingerprint": _sha256(
                observation_path,
                "exact-known-jobs observation",
            ),
            "observations": observations,
            "coverage": {
                "expected": len(binding["expectedJobs"]),
                "observed": len(observations),
            },
            "non_atomic": True,
            "provenance": "exact-known-jobs",
            "call_count": observed["call_count"],
            "projected_response_bytes": observed["projected_response_bytes"],
            "client_wall_seconds": observed["client_wall_seconds"],
            "opaque_source_id": opaque_source_id,
        },
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "experiment_id": experiment_id,
    }


def _package_attempt(
    package_root: Path,
    plan: dict,
    declaration: dict,
    attempt_id: str,
) -> tuple[dict, dict, dict]:
    manifest_path = package_root / "package-manifest.json"
    matrix_path = package_root / "execution-matrix.json"
    package = regular_json(manifest_path, "distributed package manifest")
    matrix = regular_json(matrix_path, "distributed execution matrix")
    _require(
        package.get("schemaVersion") == 2
        and matrix.get("schemaVersion") == 2
        and package.get("campaignId") == matrix.get("campaignId")
        and package.get("experimentPlanSha256") == plan.get("experimentPlanSha256")
        and matrix.get("experimentPlanSha256") == plan.get("experimentPlanSha256"),
        "distributed package plan identity changed",
    )
    _require(
        _sha256(manifest_path, "distributed package manifest")
        == plan.get("packageManifestSha256"),
        "distributed package manifest digest changed",
    )
    attempts = [
        item for item in matrix.get("attempts", [])
        if isinstance(item, dict) and item.get("attemptId") == attempt_id
    ]
    jobs = [
        item for item in plan.get("matrix", {}).get("include", [])
        if isinstance(item, dict) and item.get("attemptId") == attempt_id
    ]
    if len(attempts) != 1 or len(jobs) != 1:
        raise ValueError("distributed attempt is unavailable or duplicated")
    attempt = attempts[0]
    job = jobs[0]
    _validate_plan_against_declaration(plan, declaration)
    for key in (
        "attemptId",
        "caseId",
        "caseRevision",
        "treatmentId",
        "repetition",
        "candidateModel",
        "candidateTimeoutSeconds",
        "treatmentFingerprint",
        "targetSkillIdentities",
        "targetOs",
        "architecture",
        "route",
        "gradingRoute",
    ):
        _require(job.get(key) == attempt.get(key), "distributed plan attempt identity changed")
    return package, attempt, job


def _receipt_projection(
    package_root: Path,
    plan: dict,
    declaration: dict,
    receipt_path: Path,
    retained_artifact: Path,
    retention_manifest_path: Path,
    attempt_id: str,
    *,
    terminal: bool,
) -> tuple[dict, dict, dict, dict]:
    package, attempt, job = _package_attempt(
        package_root,
        plan,
        declaration,
        attempt_id,
    )
    receipt = regular_json(receipt_path, "distributed receipt")
    retention = regular_json(retention_manifest_path, "retention manifest")
    _require(
        set(retention) == RETENTION_MANIFEST_FIELDS
        and retention.get("schema_version") == 1,
        "unsupported retention manifest",
    )
    receipt_sha = _sha256(receipt_path, "distributed receipt")
    artifact_sha = _sha256(retained_artifact, "retained artifact")
    _require(
        retention["receipt_sha256"] == receipt_sha
        and retention["artifact_sha256"] == artifact_sha,
        "retention manifest digest mismatch",
    )
    source_ids = _safe_source_ids(retention["source_ids"])
    identity = {
        "experimentPlanSha256": plan["experimentPlanSha256"],
        "attemptId": attempt["attemptId"],
        "caseId": attempt["caseId"],
        "caseRevision": attempt["caseRevision"],
        "treatmentId": attempt["treatmentId"],
        "repetition": attempt["repetition"],
        "candidateModel": attempt["candidateModel"],
        "candidateTimeoutSeconds": attempt["candidateTimeoutSeconds"],
        "treatmentFingerprint": attempt["treatmentFingerprint"],
        "targetSkillIdentitiesFingerprint": canonical_fingerprint(
            attempt["targetSkillIdentities"]
        ),
        "targetOs": attempt["targetOs"],
        "architecture": attempt["architecture"],
        "route": attempt["route"],
        "gradingRoute": attempt["gradingRoute"],
        "packageArchiveSha256": plan["packageArchiveSha256"],
        "candidatePackageArchiveSha256": plan[
            "candidatePackageArchiveSha256"
        ],
        "packageManifestSha256": plan["packageManifestSha256"],
    }
    _require(
        receipt.get("schemaVersion") == 2
        and receipt.get("executionIdentity") == identity
        and receipt.get("executionIdentitySha256")
        == canonical_fingerprint(identity),
        "distributed receipt execution identity changed",
    )
    for key in ("caseId", "caseRevision", "treatmentId", "repetition"):
        _require(receipt.get(key) == attempt[key], "distributed receipt attempt identity changed")
    status = receipt.get("status")
    _require(
        status in {
            "PENDING_MACOS_PRODUCT",
            "PENDING_LINUX_FINALIZATION",
            "READY_FOR_FINALIZATION",
            "PASS",
            "FAIL",
        },
        "distributed receipt status is invalid",
    )
    _require(
        terminal == (status in {"PASS", "FAIL"}),
        "distributed receipt terminal status changed",
    )
    candidate = receipt.get("candidate")
    if status == "READY_FOR_FINALIZATION":
        _require(
            candidate is None
            and receipt.get("qualification") == "NOT_EVALUATED"
            and type(receipt.get("productPassed")) is bool,
            "distributed finalization preflight is invalid",
        )
    else:
        _require(
            isinstance(candidate, dict)
            and candidate.get("candidateModel") == attempt["candidateModel"]
            and candidate.get("treatmentFingerprint")
            == attempt["treatmentFingerprint"]
            and candidate.get("targetSkillIdentities")
            == attempt["targetSkillIdentities"]
            and candidate.get("boundaryAudit", {}).get("passed") is True,
            "distributed candidate execution identity changed",
        )
    deterministic = (
        receipt.get("deterministic")
        or receipt.get("hostedDeterministic")
        or receipt.get("hostDeterministic")
    )
    product = receipt.get("product")
    judges = receipt.get("judges", [])
    if terminal:
        _require(
            isinstance(deterministic, dict)
            and type(deterministic.get("targetPassed")) is bool
            and type(deterministic.get("regressionPassed")) is bool
            and isinstance(product, dict)
            and type(product.get("passed")) is bool
            and isinstance(judges, list)
            and judges,
            "terminal distributed receipt evidence is incomplete",
        )
        _require(
            receipt.get("candidateRerun", False) is False,
            "terminal distributed receipt reran the candidate",
        )
        verdicts = []
        for judge in judges:
            verdict = (
                judge.get("judgment", {}).get("verdict")
                if isinstance(judge, dict)
                else None
            )
            _require(
                verdict in {"PASS", "FAIL", "UNANSWERABLE"},
                "distributed judge verdict is invalid",
            )
            verdicts.append("PASS" if verdict == "PASS" else "FAIL")
        expected_status = (
            "PASS"
            if candidate.get("exitCode", 0) == 0
            and deterministic["targetPassed"]
            and deterministic["regressionPassed"]
            and product["passed"]
            else "FAIL"
        )
        _require(status == expected_status, "distributed terminal status changed")
    else:
        verdicts = []
        if status != "READY_FOR_FINALIZATION":
            _require(
                receipt.get("candidateRerunRequired") is False,
                "distributed stage requires a candidate rerun",
            )
    image_id = job.get("imageId", "")
    if image_id:
        _require(
            isinstance(image_id, str)
            and image_id.startswith("sha256:")
            and len(image_id) == 71,
            "distributed image identity is invalid",
        )
        image_identity = image_id.removeprefix("sha256:")
    else:
        image_identity = canonical_fingerprint({"image": None})
    dependency = job.get("dependencySha256", "")
    if dependency:
        _require(
            isinstance(dependency, str) and len(dependency) == 64,
            "distributed dependency identity is invalid",
        )
        dependency_identity = dependency
    else:
        dependency_identity = canonical_fingerprint({"dependency": None})
    execution = {
        "plan_fingerprint": plan["experimentPlanSha256"],
        "candidate_model": attempt["candidateModel"],
        "candidate_timeout_seconds": attempt["candidateTimeoutSeconds"],
        "treatment_fingerprint": attempt["treatmentFingerprint"],
        "target_skill_identities": [
            {
                "name": item["skillName"],
                "evaluator_fingerprint": item["evaluatorFingerprint"],
            }
            for item in attempt["targetSkillIdentities"]
        ],
        "target_os": attempt["targetOs"],
        "architecture": attempt["architecture"],
        "route": attempt["route"],
        "grading_route": attempt["gradingRoute"],
        "package_archive_sha256": plan["packageArchiveSha256"],
        "candidate_package_archive_sha256": plan[
            "candidatePackageArchiveSha256"
        ],
        "package_manifest_sha256": plan["packageManifestSha256"],
        "image_identity": image_identity,
        "dependency_identity": dependency_identity,
    }
    attempt_projection = {
        "attempt_id": attempt["attemptId"],
        "case_id": attempt["caseId"],
        "case_revision": attempt["caseRevision"],
        "treatment_id": attempt["treatmentId"],
        "repetition": attempt["repetition"],
    }
    summaries = {
        "candidate": (
            "Candidate receipt validated"
            if candidate is not None
            else None
        ),
        "deterministic": (
            "Deterministic checks validated"
            if isinstance(deterministic, dict)
            else None
        ),
        "product": (
            "Product check validated"
            if isinstance(product, dict)
            else "Product preflight validated"
            if status == "READY_FOR_FINALIZATION"
            else None
        ),
        "judge": "Behavioral judgments validated" if judges else None,
    }
    return {
        "receipt": receipt,
        "receipt_sha256": receipt_sha,
        "artifact_sha256": artifact_sha,
        "retention_manifest_sha256": _sha256(
            retention_manifest_path,
            "retention manifest",
        ),
        "source_ids": source_ids,
        "attempt": attempt_projection,
        "execution": execution,
        "summaries": summaries,
        "deterministic": deterministic,
        "product": product,
        "verdicts": verdicts,
    }, package, attempt, job


def _stage_kind(receipt: dict, plan: dict, attempt_id: str) -> str:
    status = receipt["status"]
    split = (
        plan["candidatePackageArchiveSha256"]
        != plan["packageArchiveSha256"]
    )
    stage_kind = {
        "PENDING_MACOS_PRODUCT": "macos-stage",
        "PENDING_LINUX_FINALIZATION": (
            "macos-product" if split else "macos-stage"
        ),
        "READY_FOR_FINALIZATION": "linux-finalize",
    }[status]
    expected = [
        item
        for item in plan.get("expectedJobs", [])
        if (
            item.get("attemptId") == attempt_id
            and item.get("stage") == stage_kind
        )
    ]
    _require(
        len(expected) == 1,
        "distributed stage is absent from the dispatch plan",
    )
    return stage_kind


def experiment_stage_dashboard(
    corpus: Path,
    package_root: Path,
    plan_path: Path,
    receipt_path: Path,
    retained_artifact: Path,
    retention_manifest_path: Path,
    *,
    experiment_id: str,
    attempt_id: str,
    writer_id: str,
    writer_generation: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    plan = regular_json(plan_path, "distributed plan")
    fingerprint = plan.get("experimentPlanSha256")
    declaration = _declaration(corpus, experiment_id, fingerprint)
    projected, _, _, _ = _receipt_projection(
        package_root,
        plan,
        declaration,
        receipt_path,
        retained_artifact,
        retention_manifest_path,
        attempt_id,
        terminal=False,
    )
    receipt = projected["receipt"]
    stage_kind = _stage_kind(receipt, plan, attempt_id)
    event = emit_experiment_activity_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "distributed_coordinator",
            "id": writer_id,
            "generation": writer_generation,
        },
        event_type="distributed_stage_recorded",
        experiment_id=experiment_id,
        experiment_fingerprint=fingerprint,
        attempt_id=attempt_id,
        payload={
            "attempt": projected["attempt"],
            "execution": projected["execution"],
            "stage_kind": stage_kind,
            "status": receipt["status"],
            "terminal": False,
            "candidate_rerun_required": False,
            "summaries": projected["summaries"],
            "retention_manifest_sha256": projected[
                "retention_manifest_sha256"
            ],
            "source_artifact_sha256": projected["artifact_sha256"],
            "source_ids": projected["source_ids"],
        },
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "experiment_id": experiment_id,
    }


def experiment_result_dashboard(
    corpus: Path,
    package_root: Path,
    plan_path: Path,
    receipt_path: Path,
    retained_artifact: Path,
    retention_manifest_path: Path,
    *,
    experiment_id: str,
    attempt_id: str,
    writer_id: str,
    writer_generation: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    plan = regular_json(plan_path, "distributed plan")
    fingerprint = plan.get("experimentPlanSha256")
    declaration = _declaration(corpus, experiment_id, fingerprint)
    projected, _, _, _ = _receipt_projection(
        package_root,
        plan,
        declaration,
        receipt_path,
        retained_artifact,
        retention_manifest_path,
        attempt_id,
        terminal=True,
    )
    receipt = projected["receipt"]
    lineage = receipt.get("sourceLineage")
    source_lineage = None
    if lineage is not None:
        _require(
            isinstance(lineage, dict)
            and lineage.get("candidateRerun") is False
            and isinstance(lineage.get("sourceRetainedArchiveSha256"), str)
            and len(lineage["sourceRetainedArchiveSha256"]) == 64
            and isinstance(lineage.get("candidateReconstruction"), list),
            "distributed source lineage is invalid",
        )
        source_lineage = {
            "source_id": canonical_fingerprint(lineage),
            "retained_archive_sha256": lineage[
                "sourceRetainedArchiveSha256"
            ],
            "candidate_reconstruction": True,
        }
    event = emit_experiment_activity_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "distributed_coordinator",
            "id": writer_id,
            "generation": writer_generation,
        },
        event_type="distributed_result_recorded",
        experiment_id=experiment_id,
        experiment_fingerprint=fingerprint,
        attempt_id=attempt_id,
        payload={
            "attempt": projected["attempt"],
            "execution": projected["execution"],
            "terminal_status": receipt["status"],
            "summaries": projected["summaries"],
            "first_stage_id": (
                source_lineage["retained_archive_sha256"]
                if source_lineage is not None
                else projected["artifact_sha256"]
            ),
            "source_lineage": source_lineage,
            "candidate_rerun": False,
            "effective_result_id": projected["receipt_sha256"],
            "selection_fields": {
                "terminal_status": receipt["status"],
                "deterministic_target_pass": projected["deterministic"][
                    "targetPassed"
                ],
                "deterministic_regression_pass": projected["deterministic"][
                    "regressionPassed"
                ],
                "product_pass": projected["product"]["passed"],
                "independent_behavioral_verdicts": projected["verdicts"],
            },
            "source_ids": projected["source_ids"],
        },
        event_id=event_id,
        observed_at=observed_at,
    )
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "experiment_id": experiment_id,
    }


def experiment_selection_dashboard(
    corpus: Path,
    declaration_event_id: str,
    *,
    writer_id: str,
    writer_generation: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    records, conflicts, _ = experiment_activity_records(corpus)
    conflicted_ids = {item["event_id"] for item in conflicts}
    by_id = {item["event_id"]: item for item in records}
    if declaration_event_id in conflicted_ids:
        raise ValueError("experiment selection source is conflicted")
    try:
        declaration = by_id[declaration_event_id]
    except KeyError:
        raise ValueError("experiment selection source is unavailable") from None
    results = [
        item
        for item in records
        if (
            item["event_type"] == "distributed_result_recorded"
            and item["subject"]["experiment_id"]
            == declaration["subject"]["experiment_id"]
            and item["subject"]["experiment_fingerprint"]
            == declaration["subject"]["experiment_fingerprint"]
            and item["event_id"] not in conflicted_ids
        )
    ]
    attempt_ids = [item["subject"]["attempt_id"] for item in results]
    if len(attempt_ids) != len(set(attempt_ids)):
        return {
            "schema_version": 1,
            "status": "selection_incomplete",
            "reasons": ["result_conflicted"],
        }
    selection = emit_experiment_selection(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": "experiment_evaluator",
            "id": writer_id,
            "generation": writer_generation,
        },
        declaration=declaration,
        terminal_results=results,
        event_id=event_id,
        observed_at=observed_at,
    )
    if selection.get("status") == "selection_incomplete":
        return {
            "schema_version": 1,
            **selection,
        }
    return {
        "schema_version": 1,
        "campaign_id": registration["campaign_id"],
        "event_id": selection["event_id"],
        "event_type": selection["event_type"],
        "experiment_id": selection["subject"]["experiment_id"],
        "status": selection["payload"]["status"],
    }


def service_status(root: Path | None = None) -> dict:
    root = state_root(root)
    service = healthy_service(root)
    return {
        "schema_version": 1,
        "status": "running" if service else "stopped",
        "service": service,
    }


def stop_service(root: Path | None = None) -> dict:
    root = state_root(root)
    with startup_lock(root):
        service = healthy_service(root)
        if service is None:
            return {"schema_version": 1, "stopped": False}
        os.kill(service["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if healthy_service(root) is None:
                break
            time.sleep(0.05)
        else:
            raise ValueError("dashboard service did not stop")
        (root / "service.json").unlink(missing_ok=True)
        (root / "root-secret").unlink(missing_ok=True)
        process = STARTED_PROCESSES.pop(service["pid"], None)
        if process is not None:
            process.wait(timeout=5)
        return {
            "schema_version": 1,
            "stopped": True,
            "generation": service["generation"],
        }


def invalidate_on_boundary_violation(path: Path) -> bool:
    configured = Path(
        os.environ.get(
            "SKILL_EVAL_DASHBOARD_STATE_ROOT",
            str(DEFAULT_STATE_ROOT),
        )
    ).expanduser()
    resolved = path.resolve()
    roots = []
    if configured.exists():
        roots.append(configured.resolve())
    roots.extend(
        parent
        for parent in resolved.parents
        if (parent / "service.json").is_file()
        and not (parent / "service.json").is_symlink()
        and (parent / "root-secret").is_file()
        and not (parent / "root-secret").is_symlink()
    )
    root = next(
        (
            candidate
            for candidate in roots
            if resolved == candidate or resolved.is_relative_to(candidate)
        ),
        None,
    )
    if root is None:
        return False
    stopped = stop_service(root)
    if not stopped["stopped"]:
        (root / "service.json").unlink(missing_ok=True)
        (root / "root-secret").unlink(missing_ok=True)
    return True


def configure_parser(sub: argparse._SubParsersAction) -> None:
    dashboard = sub.add_parser("dashboard")
    commands = dashboard.add_subparsers(dest="dashboard_command", required=True)
    for name in ("ensure", "open"):
        command = commands.add_parser(name)
        command.add_argument("corpus", type=Path)
        command.add_argument("--state-root", type=Path)
    register = commands.add_parser("register")
    register.add_argument("corpus", type=Path)
    register.add_argument("--session-id", required=True)
    register.add_argument("--state-root", type=Path)
    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("corpus", type=Path)
    heartbeat.add_argument("--session-id", required=True)
    heartbeat.add_argument(
        "--state",
        choices=("active", "blocked", "idle"),
        default="active",
    )
    heartbeat.add_argument("--state-root", type=Path)
    event = commands.add_parser("event")
    event.add_argument("corpus", type=Path)
    event.add_argument("--session-id", required=True)
    event.add_argument(
        "--event-type",
        choices=(
            "assignment_started",
            "assignment_blocked",
            "assignment_completed",
        ),
        required=True,
    )
    event.add_argument("--case", required=True)
    event.add_argument("--summary", required=True)
    event.add_argument("--skill-identity")
    event.add_argument("--state-root", type=Path)
    lineage = commands.add_parser("lineage-snapshot")
    lineage.add_argument("corpus", type=Path)
    lineage.add_argument("--session-id", required=True)
    lineage.add_argument("--plugin-dir", type=Path, required=True)
    lineage.add_argument("--skill", action="append", required=True)
    lineage.add_argument(
        "--role",
        action="append",
        choices=("original", "published", "integrated", "experimental", "released"),
        required=True,
    )
    lineage.add_argument(
        "--parent",
        action="append",
        nargs=2,
        metavar=("RELATION", "SNAPSHOT_ID"),
    )
    lineage.add_argument("--summary", required=True)
    lineage.add_argument("--provenance-kind")
    lineage.add_argument("--source-revision")
    lineage.add_argument("--event-id")
    lineage.add_argument("--observed-at")
    lineage.add_argument("--state-root", type=Path)
    progress = commands.add_parser("task-progress")
    progress.add_argument("corpus", type=Path)
    progress.add_argument("--session-id", required=True)
    progress.add_argument("--case", required=True)
    progress.add_argument("--snapshot", required=True)
    progress.add_argument(
        "--frontier",
        choices=(
            "admission",
            "candidate",
            "executable",
            "behavioral",
            "quality",
            "qualification",
            "release",
            "unknown",
        ),
        required=True,
    )
    progress.add_argument(
        "--classification",
        choices=(
            "skill_defect",
            "instruction_interaction",
            "execution_variance",
            "packet_defect",
            "harness_defect",
            "grading_defect",
            "authority_limit",
            "product_limit",
            "unknown",
        ),
        required=True,
    )
    progress.add_argument(
        "--movement",
        choices=(
            "Conquered",
            "Strict improvement",
            "Mixed",
            "No signal",
            "Regression",
            "Unknown",
        ),
        required=True,
    )
    progress.add_argument("--summary", required=True)
    progress.add_argument(
        "--uptake",
        action="append",
        nargs=3,
        metavar=("RULE_ID", "STATUS", "SUMMARY"),
    )
    progress.add_argument("--blocker")
    progress.add_argument("--next-action")
    progress.add_argument("--comparison-snapshot")
    progress.add_argument(
        "--source",
        action="append",
        nargs=2,
        metavar=("KIND", "ID"),
    )
    progress.add_argument("--event-id")
    progress.add_argument("--observed-at")
    progress.add_argument("--state-root", type=Path)
    declaration = commands.add_parser("experiment-declaration")
    declaration.add_argument("corpus", type=Path)
    declaration.add_argument("source", type=Path)
    declaration.add_argument("--session-id", required=True)
    declaration.add_argument("--event-id")
    declaration.add_argument("--observed-at")
    declaration.add_argument("--state-root", type=Path)
    dispatch = commands.add_parser("experiment-dispatch")
    dispatch.add_argument("corpus", type=Path)
    dispatch.add_argument("plan", type=Path)
    dispatch.add_argument("run", type=Path)
    dispatch.add_argument("binding", type=Path)
    dispatch.add_argument("--experiment-id", required=True)
    dispatch.add_argument("--opaque-source-id", required=True)
    dispatch.add_argument("--writer-id", required=True)
    dispatch.add_argument("--writer-generation", required=True)
    dispatch.add_argument("--event-id")
    dispatch.add_argument("--observed-at")
    dispatch.add_argument("--state-root", type=Path)
    observation = commands.add_parser("experiment-observation")
    observation.add_argument("corpus", type=Path)
    observation.add_argument("observation", type=Path)
    observation.add_argument("plan", type=Path)
    observation.add_argument("run", type=Path)
    observation.add_argument("binding", type=Path)
    observation.add_argument("--experiment-id", required=True)
    observation.add_argument("--opaque-source-id", required=True)
    observation.add_argument("--writer-id", required=True)
    observation.add_argument("--writer-generation", required=True)
    observation.add_argument("--event-id")
    observation.add_argument("--observed-at")
    observation.add_argument("--state-root", type=Path)
    for name in ("experiment-stage", "experiment-result"):
        receipt = commands.add_parser(name)
        receipt.add_argument("corpus", type=Path)
        receipt.add_argument("package_root", type=Path)
        receipt.add_argument("plan", type=Path)
        receipt.add_argument("receipt", type=Path)
        receipt.add_argument("retained_artifact", type=Path)
        receipt.add_argument("retention_manifest", type=Path)
        receipt.add_argument("--experiment-id", required=True)
        receipt.add_argument("--attempt-id", required=True)
        receipt.add_argument("--writer-id", required=True)
        receipt.add_argument("--writer-generation", required=True)
        receipt.add_argument("--event-id")
        receipt.add_argument("--observed-at")
        receipt.add_argument("--state-root", type=Path)
    selection = commands.add_parser("experiment-selection")
    selection.add_argument("corpus", type=Path)
    selection.add_argument("--declaration-event", required=True)
    selection.add_argument("--writer-id", required=True)
    selection.add_argument("--writer-generation", required=True)
    selection.add_argument("--event-id")
    selection.add_argument("--observed-at")
    selection.add_argument("--state-root", type=Path)
    for name in ("status", "stop"):
        command = commands.add_parser(name)
        command.add_argument("--state-root", type=Path)


def dispatch(args: argparse.Namespace) -> dict:
    if args.dashboard_command == "ensure":
        return ensure_dashboard(args.corpus, args.state_root)
    if args.dashboard_command == "open":
        return open_dashboard(args.corpus, args.state_root)
    if args.dashboard_command == "register":
        return register_dashboard(
            args.corpus,
            args.session_id,
            args.state_root,
        )
    if args.dashboard_command == "heartbeat":
        return heartbeat_dashboard(
            args.corpus,
            args.session_id,
            args.state,
            args.state_root,
        )
    if args.dashboard_command == "event":
        return assignment_dashboard(
            args.corpus,
            args.session_id,
            args.event_type,
            args.case,
            args.summary,
            skill_identity=args.skill_identity,
            root=args.state_root,
        )
    if args.dashboard_command == "lineage-snapshot":
        return lineage_snapshot_dashboard(
            args.corpus,
            args.session_id,
            args.plugin_dir.expanduser().resolve(),
            args.skill,
            args.role,
            args.summary,
            parents=[
                {"relation": relation, "snapshot_id": snapshot_id}
                for relation, snapshot_id in (args.parent or [])
            ],
            provenance_kind=args.provenance_kind,
            source_revision=args.source_revision,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "task-progress":
        return task_progress_dashboard(
            args.corpus,
            args.session_id,
            args.case,
            args.snapshot,
            args.frontier,
            args.classification,
            args.movement,
            args.summary,
            uptake=[
                {"rule_id": rule_id, "status": status, "summary": summary}
                for rule_id, status, summary in (args.uptake or [])
            ],
            blocker=args.blocker,
            next_action=args.next_action,
            comparison_snapshot_id=args.comparison_snapshot,
            sources=[
                {"kind": kind, "id": identifier}
                for kind, identifier in (args.source or [])
            ],
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "experiment-declaration":
        return experiment_declaration_dashboard(
            args.corpus,
            args.source.expanduser().resolve(),
            session_id=args.session_id,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "experiment-dispatch":
        return experiment_dispatch_dashboard(
            args.corpus,
            args.plan.expanduser().resolve(),
            args.run.expanduser().resolve(),
            args.binding.expanduser().resolve(),
            experiment_id=args.experiment_id,
            opaque_source_id=args.opaque_source_id,
            writer_id=args.writer_id,
            writer_generation=args.writer_generation,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "experiment-observation":
        return experiment_observation_dashboard(
            args.corpus,
            args.observation.expanduser().resolve(),
            args.plan.expanduser().resolve(),
            args.run.expanduser().resolve(),
            args.binding.expanduser().resolve(),
            experiment_id=args.experiment_id,
            opaque_source_id=args.opaque_source_id,
            writer_id=args.writer_id,
            writer_generation=args.writer_generation,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "experiment-stage":
        return experiment_stage_dashboard(
            args.corpus,
            args.package_root.expanduser().resolve(),
            args.plan.expanduser().resolve(),
            args.receipt.expanduser().resolve(),
            args.retained_artifact.expanduser().resolve(),
            args.retention_manifest.expanduser().resolve(),
            experiment_id=args.experiment_id,
            attempt_id=args.attempt_id,
            writer_id=args.writer_id,
            writer_generation=args.writer_generation,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "experiment-result":
        return experiment_result_dashboard(
            args.corpus,
            args.package_root.expanduser().resolve(),
            args.plan.expanduser().resolve(),
            args.receipt.expanduser().resolve(),
            args.retained_artifact.expanduser().resolve(),
            args.retention_manifest.expanduser().resolve(),
            experiment_id=args.experiment_id,
            attempt_id=args.attempt_id,
            writer_id=args.writer_id,
            writer_generation=args.writer_generation,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "experiment-selection":
        return experiment_selection_dashboard(
            args.corpus,
            args.declaration_event,
            writer_id=args.writer_id,
            writer_generation=args.writer_generation,
            event_id=args.event_id,
            observed_at=args.observed_at,
            root=args.state_root,
        )
    if args.dashboard_command == "status":
        return service_status(args.state_root)
    if args.dashboard_command == "stop":
        return stop_service(args.state_root)
    raise ValueError(f"unsupported dashboard command: {args.dashboard_command}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    configure_parser(result.add_subparsers(dest="command", required=True))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(["dashboard", *(argv or sys.argv[1:])])
    try:
        print(json.dumps(dispatch(args), indent=2, allow_nan=False))
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"skill-evaluation dashboard: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
