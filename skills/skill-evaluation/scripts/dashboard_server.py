"""Loopback-only read-only server for the skill-evaluation dashboard."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dashboard_projection import (
    campaign_projection,
    session_projection,
)
from dashboard_state import (
    ensure_state_root,
    validate_campaign_id,
    validate_safe_id,
    validate_session_id,
)
from project_dashboard import (
    campaign_project_registration,
    project_index_projection,
    project_projection,
    unassigned_projection,
)


STATIC_ROOT = Path(__file__).with_name("dashboard_static")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        state_root: Path,
        generation: str,
        root_secret: str,
    ):
        super().__init__(address, DashboardHandler)
        self.state_root = ensure_state_root(state_root)
        self.generation = generation
        self.root_secret = root_secret
        self.capabilities: dict[str, str] = {}

    def mint_capability(self, scope: str) -> str:
        capability = f"{self.generation}.{secrets.token_urlsafe(32)}"
        self.capabilities[capability] = scope
        return capability


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def security_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def response(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, status: HTTPStatus, value: object) -> None:
        self.response(
            status,
            json.dumps(value, separators=(",", ":"), allow_nan=False).encode(),
            "application/json; charset=utf-8",
        )

    def refusal(self, status: HTTPStatus, code: str) -> None:
        self.json_response(status, {"error": code})

    def parsed_path(self) -> str | None:
        parsed = urlsplit(self.path)
        if parsed.query:
            self.refusal(HTTPStatus.BAD_REQUEST, "query_not_supported")
            return None
        try:
            path = unquote(parsed.path, errors="strict")
        except UnicodeError:
            self.refusal(HTTPStatus.BAD_REQUEST, "malformed_path")
            return None
        if "\0" in path or ".." in Path(path).parts:
            self.refusal(HTTPStatus.BAD_REQUEST, "invalid_path")
            return None
        return path

    def authorization(self, scheme: str) -> str | None:
        value = self.headers.get("Authorization")
        prefix = f"{scheme} "
        if not value or not value.startswith(prefix):
            return None
        return value[len(prefix):]

    def root_authorized(self) -> bool:
        supplied = self.authorization("Root")
        return supplied is not None and hmac.compare_digest(
            supplied,
            self.server.root_secret,
        )

    def browser_scope(self) -> tuple[bool, str | None]:
        supplied = self.authorization("Bearer")
        if supplied is None:
            self.refusal(HTTPStatus.UNAUTHORIZED, "capability_required")
            return False, None
        prefix, separator, _ = supplied.partition(".")
        if separator and prefix != self.server.generation:
            self.refusal(HTTPStatus.UNAUTHORIZED, "generation_replaced")
            return False, None
        for capability, scope in self.server.capabilities.items():
            if hmac.compare_digest(supplied, capability):
                return True, scope
        self.refusal(HTTPStatus.UNAUTHORIZED, "invalid_capability")
        return False, None

    def control_health(self) -> None:
        if not self.root_authorized():
            self.refusal(HTTPStatus.UNAUTHORIZED, "root_auth_required")
            return
        self.json_response(HTTPStatus.OK, {
            "schema_version": 1,
            "generation": self.server.generation,
            "pid": os.getpid(),
            "port": self.server.server_port,
        })

    def control_open(self) -> None:
        if not self.root_authorized():
            self.refusal(HTTPStatus.UNAUTHORIZED, "root_auth_required")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.refusal(HTTPStatus.BAD_REQUEST, "invalid_content_length")
            return
        if length < 0 or length > 4096:
            self.refusal(HTTPStatus.BAD_REQUEST, "invalid_content_length")
            return
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except (UnicodeError, json.JSONDecodeError):
            self.refusal(HTTPStatus.BAD_REQUEST, "invalid_json")
            return
        if not isinstance(request, dict):
            self.refusal(HTTPStatus.BAD_REQUEST, "invalid_open_request")
            return
        if set(request) == {"campaign_id"}:
            campaign_id = request["campaign_id"]
            if campaign_id is None:
                scope = "project_index"
            else:
                try:
                    validate_campaign_id(campaign_id)
                    if campaign_project_registration(
                        self.server.state_root,
                        campaign_id,
                    ) is not None:
                        self.refusal(
                            HTTPStatus.FORBIDDEN,
                            "campaign_is_project_assigned",
                        )
                        return
                    campaign_projection(self.server.state_root, campaign_id)
                except (OSError, ValueError):
                    self.refusal(HTTPStatus.NOT_FOUND, "campaign_unavailable")
                    return
                scope = "unassigned"
        elif set(request) == {"scope"} and isinstance(request["scope"], str):
            scope = request["scope"]
        else:
            self.refusal(HTTPStatus.BAD_REQUEST, "invalid_open_request")
            return
        try:
            if scope == "project_index":
                project_index_projection(self.server.state_root)
                route = "/"
            elif scope == "unassigned":
                unassigned_projection(self.server.state_root)
                route = "/unassigned"
            elif scope.startswith("project:"):
                project_id = scope.removeprefix("project:")
                validate_safe_id(project_id, "project ID")
                project_projection(self.server.state_root, project_id)
                route = f"/project/{project_id}"
            else:
                self.refusal(HTTPStatus.BAD_REQUEST, "invalid_open_scope")
                return
        except (OSError, ValueError):
            self.refusal(HTTPStatus.NOT_FOUND, "scope_unavailable")
            return
        capability = self.server.mint_capability(scope)
        self.json_response(HTTPStatus.OK, {
            "schema_version": 1,
            "generation": self.server.generation,
            "route": route,
            "capability": capability,
            "scope": scope,
        })

    def child_project_capability(self, path: str, scope: str) -> None:
        if scope != "project_index":
            self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
            return
        project_id = path.removeprefix("/api/projects/").removesuffix(
            "/capability"
        )
        try:
            validate_safe_id(project_id, "project ID")
            projects = project_index_projection(self.server.state_root)["projects"]
        except (OSError, ValueError):
            self.refusal(HTTPStatus.NOT_FOUND, "project_unavailable")
            return
        if project_id not in {item["project_id"] for item in projects}:
            self.refusal(HTTPStatus.NOT_FOUND, "project_unavailable")
            return
        child_scope = f"project:{project_id}"
        self.json_response(HTTPStatus.OK, {
            "schema_version": 1,
            "generation": self.server.generation,
            "route": f"/project/{project_id}",
            "scope": child_scope,
            "capability": self.server.mint_capability(child_scope),
        })

    def api_response(self, path: str) -> None:
        authorized, scope = self.browser_scope()
        if not authorized:
            return
        try:
            if path == "/api/index":
                self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
                return
            if path == "/api/projects":
                if scope != "project_index":
                    self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
                    return
                value = project_index_projection(self.server.state_root)
            elif path == "/api/unassigned":
                if scope != "unassigned":
                    self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
                    return
                value = unassigned_projection(self.server.state_root)
            elif path.startswith("/api/project/"):
                project_id = validate_safe_id(
                    path.removeprefix("/api/project/"),
                    "project ID",
                )
                if scope != f"project:{project_id}":
                    self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
                    return
                value = project_projection(self.server.state_root, project_id)
            elif "/session/" in path and path.startswith("/api/campaign/"):
                remainder = path.removeprefix("/api/campaign/")
                campaign_part, separator, session_part = remainder.partition(
                    "/session/"
                )
                if not separator:
                    raise ValueError("dashboard session route is malformed")
                campaign_id = validate_campaign_id(campaign_part)
                session_id = validate_session_id(session_part)
                if scope != "unassigned" or campaign_project_registration(
                    self.server.state_root,
                    campaign_id,
                ) is not None:
                    self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
                    return
                value = session_projection(
                    self.server.state_root,
                    campaign_id,
                    session_id,
                )
            elif path.startswith("/api/campaign/"):
                campaign_id = validate_campaign_id(path.removeprefix("/api/campaign/"))
                if scope != "unassigned" or campaign_project_registration(
                    self.server.state_root,
                    campaign_id,
                ) is not None:
                    self.refusal(HTTPStatus.FORBIDDEN, "capability_scope")
                    return
                value = campaign_projection(self.server.state_root, campaign_id)
            else:
                self.refusal(HTTPStatus.NOT_FOUND, "route_not_found")
                return
        except (OSError, ValueError) as error:
            self.refusal(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                f"projection_unavailable:{type(error).__name__}",
            )
            return
        self.json_response(HTTPStatus.OK, value)

    def static_response(self, path: str) -> None:
        if (
            path in {"/", "/index.html", "/unassigned"}
            or path.startswith("/project/")
            or path.startswith("/campaign/")
        ):
            file = STATIC_ROOT / "index.html"
            content_type = "text/html; charset=utf-8"
        elif path == "/dashboard.css":
            file = STATIC_ROOT / "dashboard.css"
            content_type = "text/css; charset=utf-8"
        elif path == "/dashboard.js":
            file = STATIC_ROOT / "dashboard.js"
            content_type = "text/javascript; charset=utf-8"
        else:
            self.refusal(HTTPStatus.NOT_FOUND, "route_not_found")
            return
        if file.is_symlink() or not file.is_file():
            self.refusal(HTTPStatus.INTERNAL_SERVER_ERROR, "static_asset_unavailable")
            return
        self.response(HTTPStatus.OK, file.read_bytes(), content_type)

    def do_GET(self) -> None:
        path = self.parsed_path()
        if path is None:
            return
        if path == "/_control/health":
            self.control_health()
        elif path.startswith("/api/"):
            self.api_response(path)
        elif path.startswith("/_control/"):
            self.refusal(HTTPStatus.NOT_FOUND, "route_not_found")
        else:
            self.static_response(path)

    def do_POST(self) -> None:
        path = self.parsed_path()
        if path is None:
            return
        if path == "/_control/open":
            self.control_open()
        elif (
            path.startswith("/api/projects/")
            and path.endswith("/capability")
        ):
            authorized, scope = self.browser_scope()
            if authorized:
                self.child_project_capability(path, scope)
        else:
            self.refusal(HTTPStatus.NOT_FOUND, "route_not_found")


def serve(
    state_root: Path,
    generation: str,
    root_secret: str,
    port: int = 0,
    startup_file: Path | None = None,
) -> None:
    server = DashboardHTTPServer(
        ("127.0.0.1", port),
        state_root,
        generation,
        root_secret,
    )
    if startup_file is not None:
        startup_file.write_text(
            json.dumps({
                "schema_version": 1,
                "generation": generation,
                "pid": os.getpid(),
                "port": server.server_port,
            }) + "\n",
            encoding="utf-8",
        )
    stop = threading.Event()

    def terminate(signum: int, frame: object) -> None:
        if not stop.is_set():
            stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--state-root", type=Path, required=True)
    result.add_argument("--generation", required=True)
    result.add_argument("--root-secret-file", type=Path, required=True)
    result.add_argument("--port", type=int, default=0)
    result.add_argument("--startup-file", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.root_secret_file.is_symlink() or not args.root_secret_file.is_file():
        raise ValueError("dashboard root secret file is unavailable")
    if args.root_secret_file.stat().st_mode & 0o077:
        raise ValueError("dashboard root secret permissions are too broad")
    root_secret = args.root_secret_file.read_text(encoding="utf-8").strip()
    serve(
        args.state_root,
        args.generation,
        root_secret,
        args.port,
        args.startup_file,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
