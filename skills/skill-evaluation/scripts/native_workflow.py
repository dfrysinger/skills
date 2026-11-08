"""Frozen data contract for a restored scheduled-workflow phase."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from session_restore import relative_path


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
    _object(native, {"profile", "state_file", "coordinates_file"}, "native_workflow")
    if native["profile"] != PROFILE:
        raise ValueError("unsupported native_workflow profile")
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
