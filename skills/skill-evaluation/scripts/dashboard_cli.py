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
from pathlib import Path
from urllib.parse import quote

from dashboard_state import create_campaign, ensure_state_root, regular_json


DEFAULT_STATE_ROOT = Path.home() / ".copilot" / "skill-evaluation-ui"
SERVICE_FIELDS = {"schema_version", "generation", "pid", "port", "started_at"}
STARTED_PROCESSES: dict[int, subprocess.Popen] = {}


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
    if not configured.exists():
        return False
    root = configured.resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
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
    for name in ("status", "stop"):
        command = commands.add_parser(name)
        command.add_argument("--state-root", type=Path)


def dispatch(args: argparse.Namespace) -> dict:
    if args.dashboard_command == "ensure":
        return ensure_dashboard(args.corpus, args.state_root)
    if args.dashboard_command == "open":
        return open_dashboard(args.corpus, args.state_root)
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
