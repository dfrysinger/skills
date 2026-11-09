"""Frozen data contract for a restored scheduled-workflow phase."""

from __future__ import annotations

import json
import hashlib
import os
import re
import stat
from pathlib import Path

from session_restore import permission_rules, relative_path

CLI_CONTINUATION_CAPABILITIES = [
    "tui-hints", "plan-mode", "memory", "cli-documentation", "ask-user",
    "interactive-mode", "system-notifications", "elicitation", "session-store",
]
CLI_CONTINUATION_PREAMBLE = "You are the GitHub Copilot CLI, a terminal assistant built by GitHub."

def _screen_input_tree(root, *, package=False, operational=False):
    owner_names = {"context-fixture.json", "completed-objective.json", "recorded-context.json",
                   "source-event.json", "continuation.json", "calibration-evidence"}
    if operational:
        owner_names |= {"operational.json", "schedule-events.json", "working-state"}
    for member in root.rglob("*"):
        parts = member.relative_to(root).parts
        if (member.is_symlink() or ".git" in parts
                or (package and (
                    parts[0] not in {"evaluator", "plugins", "owner"}
                    or (parts[0] == "owner" and len(parts) > 1 and parts[1] not in owner_names)))
                or any(re.search(r"(^|[-_.])(judge|criteria|diagnosis|work-order)([-_.]|$)", part, re.I)
                       for part in parts)):
            raise ValueError("Hidden evaluation input or aliased member in continuation inputs")


def operational_input(path: Path, config: dict | None = None) -> dict:
    from datetime import datetime
    from skill_eval import digest, directory_identity

    path = owner_file(path.parent, path.name)
    if path.stat().st_mode & 0o077:
        raise ValueError("Operational input must be owner-only")
    value = read_owner_json(path)
    _object(value, {"schema_version", "installed_plugins", "personal_skills", "custom_skills",
                    "source_aliases", "schedule_events"}, "operational input")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["installed_plugins"], list) or not value["installed_plugins"]
            or not isinstance(value["source_aliases"], list)):
        raise ValueError("Invalid operational input population")

    def tree(item, *, plugin=False):
        fields = {"path", "sha256"}
        if plugin:
            fields |= {"name", "marketplace", "installed_at"}
        _object(item, fields | ({"version"} if plugin and "version" in item else set()), "operational tree")
        if not _text(item["path"]):
            raise ValueError("Invalid operational root path")
        root = Path(item["path"])
        if (not root.is_absolute() or root.resolve() != root or not root.is_dir()
                or any(part.is_symlink() for part in (root, *root.parents))
                or root.stat().st_uid != os.getuid()):
            raise ValueError("Operational root must be owned and unaliased")
        _screen_input_tree(root)
        if (not isinstance(item["sha256"], str)
                or directory_identity(root)["sha256"] != item["sha256"]):
            raise ValueError("Operational tree binding changed")
        return root

    installed = []
    for item in value["installed_plugins"]:
        root = tree(item, plugin=True)
        if (not _text(item["name"]) or item["marketplace"] != ""
                or ("version" in item and not _text(item["version"]))
                or not isinstance(item["installed_at"], str)
                or datetime.fromisoformat(item["installed_at"].replace("Z", "+00:00")).tzinfo is None):
            raise ValueError("Invalid installed-plugin transport metadata")
        manifest = next((root / part / "plugin.json" for part in
                         (".plugin", ".", ".github/plugin", ".claude-plugin")
                         if (root / part / "plugin.json").is_file()), None)
        if manifest is not None:
            metadata = json.loads(manifest.read_text())
            if (not isinstance(metadata, dict) or item["name"] != metadata.get("name")
                    or item.get("version") != metadata.get("version")):
                raise ValueError("Installed transport metadata differs from source manifest")
        elif "version" in item:
            raise ValueError("Unmanifested source has no recovered version")
        installed.append({key: item[key] for key in ("name", "marketplace", "installed_at", "version") if key in item}
                         | {"enabled": True, "cache_path": str(root),
                            "source": {"source": "local", "path": str(root)}})
    if len({item["name"] for item in installed}) != len(installed):
        raise ValueError("Installed transport names must be distinct")
    for item in [value["personal_skills"], value["custom_skills"], *value["source_aliases"]]:
        tree(item)
    event_source = value["schedule_events"]
    _object(event_source, {"path", "sha256"}, "operational schedule source")
    events_path = owner_file(path.parent, event_source["path"])
    if events_path.stat().st_mode & 0o077 or digest(events_path) != event_source["sha256"]:
        raise ValueError("Operational schedule source binding changed")
    events = read_owner_json(events_path)
    if not isinstance(events, list) or not events:
        raise ValueError("Operational schedule events must be a nonempty array")
    active, ids, created = {}, set(), set()
    for event in events:
        _object(event, {"id", "timestamp", "type", "data"}, "source schedule event")
        if (not isinstance(event["id"], str) or re.fullmatch(
                r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", event["id"]) is None
                or event["id"] in ids or not isinstance(event["timestamp"], str)
                or datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).tzinfo is None):
            raise ValueError("Invalid source schedule event identity/time")
        ids.add(event["id"])
        data = event["data"]
        if event["type"] == "session.schedule_created":
            _object(data, {"id", "intervalMs", "prompt", "recurring", "origin"}, "source interval schedule")
            if (type(data["id"]) is not int or data["id"] < 1 or data["id"] in created
                    or type(data["intervalMs"]) is not int or data["intervalMs"] < 3600000
                    or data["recurring"] is not True or not _text(data["prompt"]) or not _text(data["origin"])):
                raise ValueError("Unsupported or unsafe source interval schedule")
            created.add(data["id"])
            active[data["id"]] = {key: data[key] for key in ("id", "intervalMs", "prompt", "recurring")}
        elif event["type"] == "session.schedule_cancelled":
            _object(data, {"id"}, "source cancelled schedule")
            if type(data["id"]) is not int or data["id"] not in active:
                raise ValueError("Unknown source schedule cancellation")
            del active[data["id"]]
        else:
            raise ValueError("Only native schedule creation/cancellation may be staged")
    if config is not None and (
            installed[0]["cache_path"] != config["plugin_path"]
            or value["personal_skills"]["path"] != str(Path(config["home"]) / "skills")
            or config.get("skill_directories") != [value["custom_skills"]["path"]]):
        raise ValueError("Operational loaded roots differ from selected native tiers")
    return {**value, "native_installed_plugins": installed, "events": events,
            "expected_schedules": [active[key] for key in sorted(active)],
            "binding": {
                "installed_plugins": [{key: value for key, value in item.items()
                                       if key not in {"cache_path", "source"}}
                                      | {"source_kind": "local", "sha256": source["sha256"]}
                                      for item, source in zip(installed, value["installed_plugins"])],
                "personal_skills": value["personal_skills"]["sha256"],
                "custom_skills": value["custom_skills"]["sha256"],
                "source_aliases": value["source_aliases"],
                "enableConfigDiscovery": True,
                "requestExtensions": False,
            },
            "limits": ["Registration names/timestamps are selected transport metadata, not recovered registration",
                       "Interval next-run clocks reset on resume; nextId is source-derived, not getter-observed",
                       "Owning import/setup/candidate/observe/cleanup watchdogs total less than one hour"]}


def continuation_entry(path: Path, config: dict) -> dict:
    from skill_eval import digest, directory_identity

    def owned(source):
        source = Path(source)
        source = owner_file(source.parent, source.name)
        if source.stat().st_mode & 0o077:
            raise ValueError("Continuation evidence must be owner-only")
        return source

    value = read_owner_json(owned(path))
    _object(value, {
        "schema_version", "purpose", "running_in_interactive_mode", "session_capabilities",
        "cli_preamble", "executable_path", "locale", "timeout_ms", "package_root",
        "workflow_commit", "workflow_sha256", "canary_receipt", "canary_checks",
    }, "historical continuation")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["purpose"] not in ("setup-canary", "historical")
            or value["running_in_interactive_mode"] is not True
            or value["session_capabilities"] != CLI_CONTINUATION_CAPABILITIES
            or value["cli_preamble"] != CLI_CONTINUATION_PREAMBLE
            or not isinstance(value["executable_path"], str)
            or any(not part or not Path(part).is_absolute()
                   for part in value["executable_path"].split(os.pathsep))
            or not isinstance(value["locale"], str)
            or re.fullmatch(r"[A-Za-z0-9_.@-]+", value["locale"]) is None
            or type(value["timeout_ms"]) is not int or not 1 <= value["timeout_ms"] <= 300000):
        raise ValueError("Invalid interactive continuation configuration")
    package = Path(value["package_root"])
    if (not package.is_absolute() or package.resolve() != package or not package.is_dir()
            or package.stat().st_uid != os.getuid()):
        raise ValueError("Continuation requires an owned clean input package")
    run_root = Path(config["cwd"]).parent
    if package.is_relative_to(run_root) or run_root.is_relative_to(package):
        raise ValueError("Continuation run must be disjoint from its frozen input package")
    for root in [package, Path(config["plugin_path"]),
                 *(Path(path) for path in config.get("skill_directories", []))]:
        _screen_input_tree(root, package=root == package, operational="operational_file" in config)
    workspace = os.getenv("GITHUB_WORKSPACE")
    if workspace and any(Path(workspace).rglob(".git")):
        raise ValueError("Continuation job must omit repository checkout")
    if (not isinstance(value["workflow_commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", value["workflow_commit"]) is None
            or not isinstance(value["workflow_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["workflow_sha256"]) is None
            or (os.getenv("GITHUB_WORKFLOW_SHA")
                and os.environ["GITHUB_WORKFLOW_SHA"] != value["workflow_commit"])):
        raise ValueError("Continuation selected workflow commit differs")
    scripts = Path(__file__).parent
    binding = {
        "source": {name: digest(scripts / name) for name in (
            "native_workflow.py", "native_workflow_probe.mjs", "session_restore.py", "skill_eval.py")},
        "runtime": {name: digest(Path(config[name])) for name in ("cli", "sdk")},
        "model": config["model"], "effort": config["effort"],
        "interactive": {name: value[name] for name in (
            "running_in_interactive_mode", "session_capabilities", "cli_preamble",
            "executable_path", "locale", "timeout_ms")},
        "workflow_sha256": value["workflow_sha256"],
        "evaluator_sha256": directory_identity(package / "evaluator")["sha256"],
        "plugin_sha256": directory_identity(Path(config["plugin_path"]))["sha256"],
        "personal_skills": [directory_identity(Path(root))["sha256"]
                            for root in config.get("skill_directories", [])],
        "personal_sha256": digest(Path(config["home"]) / "copilot-instructions.md"),
    }
    if "operational_file" in config:
        binding["operational"] = operational_input(Path(config["operational_file"]), config)["binding"]
    configuration_sha256 = hashlib.sha256(json.dumps(
        binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if value["purpose"] == "setup-canary":
        if value["canary_receipt"] is not None:
            raise ValueError("Setup-purpose canary must not substitute a historical admission receipt")
        checks = value["canary_checks"]
        _object(checks, {"file", "shell", "sql"}, "canary operations")
        _object(checks["file"], {"path", "sha256"}, "canary file")
        relative_path(checks["file"]["path"])
        if re.fullmatch(r"[0-9a-f]{64}", str(checks["file"]["sha256"])) is None:
            raise ValueError("Invalid canary file digest")
        _object(checks["shell"], {"command"}, "canary shell")
        _object(checks["sql"], {"query"}, "canary SQL")
        if any(not isinstance(item, str) or not item for item in
               (checks["shell"]["command"], checks["sql"]["query"])):
            raise ValueError("Canary operations require authored command/query")
    else:
        if value["canary_checks"] is not None:
            raise ValueError("Historical continuation must not include canary task checks")
        receipt = value["canary_receipt"]
        _object(receipt, {"status", "configuration_sha256", "interactive_identity",
                          "operation_witnesses", "exactly_once", "shutdown_errors"}, "interactive canary receipt")
        if (not isinstance(receipt, dict)
                or receipt.get("status") != "CONTINUATION_CANARY_OBSERVED"
                or receipt.get("configuration_sha256") != configuration_sha256
                or receipt.get("interactive_identity") is not True
                or receipt.get("operation_witnesses") is not True
                or receipt.get("exactly_once") is not True
                or receipt.get("shutdown_errors") != []):
            raise ValueError("Missing, mismatched or non-interactive continuation canary receipt")
    return {**value, "configuration_sha256": configuration_sha256, "binding": binding,
            "observed_package": directory_identity(package)}


PROFILE = "p01-scheduled-audit"
STATE_FIELDS = {
    "schema_version", "profile", "provenance", "goal", "mode", "todos",
    "dependencies", "schedules", "model", "effort", "unknowns",
}


def _object(value, fields, name):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} requires exactly {sorted(fields)}")


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and "\0" not in value


def _texts(value):
    return isinstance(value, list) and all(_text(item) for item in value)


def validate_state(state):
    _object(state, STATE_FIELDS, "native state")
    if (type(state["schema_version"]) is not int or state["schema_version"] != 1
            or state["profile"] != PROFILE
            or state["provenance"] not in {"historical-projection", "synthetic-calibration"}
            or state["mode"] not in {"interactive", "autopilot"}
            or not _text(state["model"]) or state["effort"] not in {"low", "medium", "high"}
            or not _texts(state["unknowns"]) or not state["unknowns"]):
        raise ValueError("unsupported native profile, model, mode or unknowns")
    goal = state["goal"]
    _object(goal, {"id", "objective", "status"}, "native goal")
    if (type(goal["id"]) is not int or not 1 <= goal["id"] < 2**31
            or not _text(goal["objective"])
            or goal["status"] not in {"active", "completed"}):
        raise ValueError("invalid native goal")
    rows = state["todos"]
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("native todos must be a bounded array")
    ids = set()
    for row in rows:
        _object(row, {"id", "title", "description", "status"}, "native todo")
        if (not all(_text(row[key]) for key in ("id", "title"))
                or not isinstance(row["description"], str) or "\0" in row["description"]
                or row["status"] not in {"pending", "in_progress", "done", "blocked"}
                or row["id"] in ids):
            raise ValueError("invalid or duplicated native todo")
        ids.add(row["id"])
    deps = state["dependencies"]
    if not isinstance(deps, list) or len(deps) > 200:
        raise ValueError("native dependencies must be a bounded array")
    edges = set()
    for dep in deps:
        _object(dep, {"todo_id", "depends_on"}, "native dependency")
        edge = (dep["todo_id"], dep["depends_on"])
        if (not all(isinstance(item, str) and item in ids for item in edge)
                or edge[0] == edge[1] or edge in edges):
            raise ValueError("invalid native dependency")
        edges.add(edge)
    schedules = state["schedules"]
    if not isinstance(schedules, list) or len(schedules) > 20:
        raise ValueError("native schedules must be a bounded array")
    schedule_ids = set()
    for entry in schedules:
        _object(entry, {"id", "interval", "prompt", "status"}, "native schedule")
        if (type(entry["id"]) is not int or not 1 <= entry["id"] < 2**31
                or entry["id"] in schedule_ids or not _text(entry["prompt"])
                or not isinstance(entry["interval"], str)
                or not re.fullmatch(r"[1-9][0-9]{0,5}[smhd]", entry["interval"])
                or entry["status"] not in {"active", "stopped"}):
            raise ValueError("invalid native schedule")
        schedule_ids.add(entry["id"])
    return state


def owner_file(packet: Path, relative: str) -> Path:
    path = packet / relative_path(relative)
    if (not path.is_file() or path.resolve() != path.absolute()
            or any(part.is_symlink() for part in (path, *path.parents))
            or not path.resolve().is_relative_to(packet.resolve())):
        raise ValueError("native owner input must be a regular unaliased packet file")
    if path.stat().st_uid != os.getuid() or path.stat().st_nlink != 1:
        raise ValueError("native packet input must be an owned single-link file")
    return path


def read_owner_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate native JSON field")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"invalid JSON constant {value}")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=reject_constant)


def phase_inputs(phase: dict, packet: Path):
    native = phase["native_workflow"]
    fields = {"profile", "state_file", "coordinates_file"}
    if isinstance(native, dict) and "candidate_permissions" in native:
        fields.add("candidate_permissions")
    _object(native, fields, "native_workflow")
    if native["profile"] != PROFILE:
        raise ValueError("unsupported native_workflow profile")
    if "candidate_permissions" in native:
        permission_rules(native["candidate_permissions"])
    paths = [owner_file(packet, native[key]) for key in ("state_file", "coordinates_file")]
    if paths[0] == paths[1]:
        raise ValueError("native owner files must be distinct")
    state = validate_state(read_owner_json(paths[0]))
    coordinates = read_owner_json(paths[1])
    _object(coordinates, {"evidence_paths", "limitations"}, "native coordinates")
    if (not _texts(coordinates["evidence_paths"]) or not coordinates["evidence_paths"]
            or not _texts(coordinates["limitations"])):
        raise ValueError("native coordinates require evidence paths and limitations")
    restoration = phase.get("session_restore", {})
    excluded = {native["state_file"], native["coordinates_file"],
                restoration.get("history_file"), restoration.get("personal_instructions_file")}
    for item in coordinates["evidence_paths"]:
        owner_file(packet, item)
        if item in excluded:
            raise ValueError("owner input cannot be candidate evidence")
    return state, coordinates, paths


def candidate_tools(permissions=None):
    tools = ["skill", "view", "sql", "manage_schedule"]
    if permissions is not None:
        permission_rules(permissions)
        if permissions["write_paths"]:
            tools.append("apply_patch")
        if permissions["shell_commands"]:
            tools.append("bash")
    return tools


def validate_native_workflow(definition: dict, root: Path, *, frozen=False):
    for index, phase in enumerate(definition["phases"]):
        if "native_workflow" not in phase:
            continue
        if (len(definition["phases"]) != 1 or index != 0 or phase.get("resume")
                or definition.get("case_type", "prose") != "prose"
                or "personal_instructions_file" not in phase.get("session_restore", {})):
            raise ValueError("native_workflow requires one restored personal-instruction prose phase")
        phase_inputs(phase, root / (phase["id"] if frozen else phase["evidence_dir"]))


def bind_model(state: dict, model: str, effort: str):
    if (model, effort) != (state["model"], state["effort"]):
        raise ValueError("caller model/effort does not match frozen native descriptor")


def render_coordinates(original: bytes, coordinates: dict, workdir: Path, goal: Path,
                       schedule_mapping: list[dict] | None = None) -> bytes:
    lines = ["", "", "Evaluation execution coordinates and limitations:",
             f"Owned native goal file: {goal}"]
    lines.extend(f"Evidence file: {workdir / item}" for item in coordinates["evidence_paths"])
    lines.extend(f"Schedule coordinate: source #{item['source_id']} -> owned #{item['native_id']}"
                 for item in (schedule_mapping or []) if item["source_id"] != item["native_id"])
    lines.extend(f"Limitation: {item}" for item in coordinates["limitations"])
    return original + ("\n".join(lines) + "\n").encode("utf-8")


def protect_owner_copy(source: Path, destination: Path):
    destination.write_bytes(source.read_bytes())
    destination.chmod(stat.S_IRUSR | stat.S_IWUSR)
