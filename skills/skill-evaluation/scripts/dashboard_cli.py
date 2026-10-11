"""Lifecycle commands for the local skill-evaluation dashboard."""

from __future__ import annotations

import argparse
import fcntl
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
    session_event,
    update_session,
)


DEFAULT_STATE_ROOT = Path.home() / ".copilot" / "skill-evaluation-ui"
SERVICE_FIELDS = {"schema_version", "generation", "pid", "port", "started_at"}
STARTED_PROCESSES: dict[int, subprocess.Popen] = {}
EXPERIMENT_ACTIVITY_SOURCE_FIELDS = {
    "schema_version",
    "event_type",
    "experiment_id",
    "experiment_fingerprint",
    "attempt_id",
    "run_binding_fingerprint",
    "payload",
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


def experiment_activity_dashboard(
    corpus: Path,
    source: Path,
    *,
    writer_kind: str,
    writer_id: str,
    writer_generation: str,
    event_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> dict:
    registration = create_campaign(state_root(root), corpus)
    selected = regular_json(source, "experiment activity source")
    if (
        set(selected) != EXPERIMENT_ACTIVITY_SOURCE_FIELDS
        or selected.get("schema_version") != 1
    ):
        raise ValueError("unsupported experiment activity source")
    event = emit_experiment_activity_event(
        corpus,
        campaign_id=registration["campaign_id"],
        writer={
            "kind": writer_kind,
            "id": writer_id,
            "generation": writer_generation,
        },
        event_type=selected["event_type"],
        experiment_id=selected["experiment_id"],
        experiment_fingerprint=selected["experiment_fingerprint"],
        attempt_id=selected["attempt_id"],
        run_binding_fingerprint=selected["run_binding_fingerprint"],
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


def experiment_selection_dashboard(
    corpus: Path,
    declaration_event_id: str,
    result_event_ids: list[str],
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
    selected_ids = [declaration_event_id, *result_event_ids]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("experiment selection source IDs are duplicated")
    by_id = {item["event_id"]: item for item in records}
    if any(identifier in conflicted_ids for identifier in selected_ids):
        raise ValueError("experiment selection source is conflicted")
    try:
        declaration = by_id[declaration_event_id]
        results = [by_id[identifier] for identifier in result_event_ids]
    except KeyError:
        raise ValueError("experiment selection source is unavailable") from None
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
    activity = commands.add_parser("experiment-activity")
    activity.add_argument("corpus", type=Path)
    activity.add_argument("source", type=Path)
    activity.add_argument(
        "--writer-kind",
        choices=(
            "session",
            "distributed_coordinator",
            "cloud_observer",
        ),
        required=True,
    )
    activity.add_argument("--writer-id", required=True)
    activity.add_argument("--writer-generation", required=True)
    activity.add_argument("--event-id")
    activity.add_argument("--observed-at")
    activity.add_argument("--state-root", type=Path)
    selection = commands.add_parser("experiment-selection")
    selection.add_argument("corpus", type=Path)
    selection.add_argument("--declaration-event", required=True)
    selection.add_argument("--result-event", action="append", default=[])
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
    if args.dashboard_command == "experiment-activity":
        return experiment_activity_dashboard(
            args.corpus,
            args.source.expanduser().resolve(),
            writer_kind=args.writer_kind,
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
            args.result_event,
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
