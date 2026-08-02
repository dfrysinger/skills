#!/usr/bin/env python3
"""Transactional run manifest and whole-run rollback for live curation."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_TOOL = Path(
    os.environ.get(
        "CURATOR_LOCK_TOOL",
        SCRIPT_DIR.parent.parent / "skill-review/scripts/daemon-lock.py",
    )
)
SCANNER = Path(
    os.environ.get("CURATOR_DEPENDENCY_SCANNER", SCRIPT_DIR / "scheduled-skill-deps.py")
)
RESTORE_TOOL = Path(
    os.environ.get(
        "CURATOR_RESTORE_TOOL",
        SCRIPT_DIR.parent.parent / "skill-manage/scripts/restore-skill.sh",
    )
)
TRAILER = os.environ.get(
    "SKILLS_COAUTHOR_TRAILER",
    "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
)
PUBLIC_MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
)


class RunError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=text, check=False)
    if check and result.returncode:
        stderr = result.stderr.strip() if text else ""
        raise RunError(f"{' '.join(command)} failed: {stderr}")
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-C", str(root), *args], check=check).stdout.strip()


def roots() -> dict[str, Path]:
    return {
        "public": Path(
            os.environ.get("SKILLS_REPO_ROOT", Path.home() / "code/skills")
        ).resolve(),
        "local": Path(
            os.environ.get("SKILLS_LOCAL_ROOT", Path.home() / ".copilot/skills")
        ).resolve(),
    }


def archive_state_dir() -> Path:
    return Path(
        os.environ.get(
            "SKILLS_STATE_DIR", Path.home() / ".copilot/skill-state/skill-review"
        )
    ).resolve()


def runs_dir() -> Path:
    return Path(
        os.environ.get(
            "SKILLS_CURATOR_RUNS_DIR", archive_state_dir() / "curator-runs"
        )
    ).resolve()


def ledger_path() -> Path:
    return archive_state_dir() / "ledger.jsonl"


def manifest_path(run_id: str) -> Path:
    if not re_safe_id(run_id):
        raise RunError(f"invalid run id: {run_id}")
    return runs_dir() / f"{run_id}.json"


def re_safe_id(value: str) -> bool:
    return bool(value) and all(ch.isalnum() or ch in "._-" for ch in value)


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_manifest(run_id: str) -> tuple[Path, dict[str, Any]]:
    path = manifest_path(run_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunError(f"cannot load run manifest {path}: {error}") from error
    if payload.get("run_id") != run_id or payload.get("schema_version") != 1:
        raise RunError(f"invalid run manifest identity: {path}")
    return path, payload


def root_identity(path: Path) -> dict[str, str]:
    if not path.is_dir():
        raise RunError(f"managed root does not exist: {path}")
    top = Path(git(path, "rev-parse", "--show-toplevel")).resolve()
    if top != path:
        raise RunError(f"configured root {path} resolves to git root {top}")
    git_dir_raw = git(path, "rev-parse", "--git-dir")
    git_dir = (path / git_dir_raw).resolve() if not Path(git_dir_raw).is_absolute() else Path(git_dir_raw).resolve()
    return {
        "path": str(path),
        "git_dir": str(git_dir),
        "initial_head": git(path, "rev-parse", "HEAD"),
    }


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dirty_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        output = run(["git", "-C", str(root), *args], text=False).stdout
        paths.update(
            item.decode("utf-8", "surrogateescape")
            for item in output.split(b"\0")
            if item
        )
    return paths


def path_fingerprint(root: Path, relative: str) -> dict[str, Any]:
    target = root / relative
    if target.is_symlink():
        worktree = {"type": "symlink", "sha256": hash_bytes(os.readlink(target).encode())}
    elif target.is_file():
        worktree = {"type": "file", "sha256": hash_bytes(target.read_bytes())}
    elif target.is_dir():
        worktree = {"type": "directory"}
    else:
        worktree = {"type": "absent"}
    return {
        "path": relative,
        "worktree": worktree,
        "index": git(root, "ls-files", "--stage", "--", relative, check=False),
        "status": git(root, "status", "--porcelain=v1", "--", relative, check=False),
    }


def dirty_snapshot(root: Path) -> list[dict[str, Any]]:
    return [path_fingerprint(root, path) for path in sorted(dirty_paths(root))]


def overlaps(left: str, right: str) -> bool:
    left_path = Path(left)
    right_path = Path(right)
    return left_path == right_path or left_path in right_path.parents or right_path in left_path.parents


def validate_relative_path(root_name: str, value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise RunError(f"unsafe operation path: {value}")
    if root_name == "public":
        if len(path.parts) < 2 or path.parts[0] not in {
            "skills",
            ".claude-plugin",
            ".codex-plugin",
        }:
            raise RunError(f"public operation path is outside allowed scopes: {value}")
    elif len(path.parts) < 1:
        raise RunError(f"local operation path is invalid: {value}")
    return path.as_posix()


def scanner_inventory() -> dict[str, Any]:
    result = run([str(SCANNER), "--inventory"], check=False)
    if result.returncode:
        raise RunError(f"scheduled dependency enumeration failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RunError(f"scheduled dependency inventory is malformed: {error}") from error
    if payload.get("complete") is not True or not isinstance(payload.get("skills"), list):
        raise RunError("scheduled dependency inventory is incomplete")
    return payload


def normalize_plan(plan: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise RunError("plan.operations must be a non-empty array")
    skills = {item["name"]: item for item in inventory["skills"]}
    operations: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_operations, 1):
        if not isinstance(raw, dict):
            raise RunError(f"plan operation {index} must be an object")
        kind = raw.get("kind")
        if kind == "archive":
            name = raw.get("skill")
            if not isinstance(name, str) or name not in skills:
                raise RunError(f"archive operation {index} names no live skill")
            row = skills[name]
            if row["pinned"] or row["implicit_pin"]:
                raise RunError(f"archive operation {index} targets pinned skill: {name}")
            root_name = row["root"]
            root = roots()[root_name]
            relative = Path(row["path"]).relative_to(
                root / "skills" if root_name == "public" else root
            )
            path = (
                Path("skills") / relative
                if root_name == "public"
                else relative
            ).as_posix()
            paths = [path]
            if root_name == "public":
                paths.extend(PUBLIC_MANIFESTS)
            operation = {
                "op_id": f"op-{index:03d}",
                "kind": "archive",
                "root": root_name,
                "skill": name,
                "absorbed_into": raw.get("absorbed_into"),
                "paths": paths,
                "status": "planned",
            }
        elif kind == "commit":
            root_name = raw.get("root")
            action = raw.get("action")
            if root_name not in {"public", "local"} or action not in {"patch", "create"}:
                raise RunError(f"commit operation {index} has invalid root/action")
            raw_paths = raw.get("paths")
            if not isinstance(raw_paths, list) or not raw_paths:
                raise RunError(f"commit operation {index} requires paths")
            operation = {
                "op_id": f"op-{index:03d}",
                "kind": "commit",
                "root": root_name,
                "action": action,
                "skill": raw.get("skill"),
                "paths": sorted(
                    {validate_relative_path(root_name, str(path)) for path in raw_paths}
                ),
                "status": "planned",
            }
        else:
            raise RunError(f"plan operation {index} has invalid kind: {kind}")
        for left_index, left in enumerate(operation["paths"]):
            for right in operation["paths"][left_index + 1 :]:
                if overlaps(left, right):
                    raise RunError(
                        f"operation {index} has overlapping paths: {left}, {right}"
                    )
        operations.append(operation)
    return operations


def verify_dirty_disjoint(
    root_records: dict[str, dict[str, Any]], operations: list[dict[str, Any]]
) -> None:
    for root_name, record in root_records.items():
        operation_paths = [
            path
            for operation in operations
            if operation["root"] == root_name
            for path in operation["paths"]
        ]
        for dirty in record["initial_dirty"]:
            for planned in operation_paths:
                if overlaps(dirty["path"], planned):
                    raise RunError(
                        f"planned path {planned} overlaps pre-existing dirty path "
                        f"{dirty['path']} in {root_name}"
                    )


def lock_command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([str(LOCK_TOOL), *args], check=check)


def acquire_lock(owner: str) -> str:
    result = lock_command("acquire", "--mode", "session", "--owner", owner, check=False)
    if result.returncode:
        raise RunError(f"writer lease unavailable: {result.stderr.strip()}")
    return result.stdout.strip()


def renew_lock(manifest: dict[str, Any]) -> None:
    result = lock_command("renew", manifest["lock_token"], check=False)
    if result.returncode:
        raise RunError("writer lease is no longer owned by this run")
    manifest["lock_renewed_at"] = now_iso()


def release_lock(manifest: dict[str, Any]) -> None:
    if lock_command("release", manifest["lock_token"], check=False).returncode:
        raise RunError("could not release writer lease")


def verify_root_records(manifest: dict[str, Any]) -> dict[str, Path]:
    current_roots = roots()
    seen_git_dirs: set[str] = set()
    for name, record in manifest["roots"].items():
        path = current_roots[name]
        identity = root_identity(path)
        if identity["path"] != record["path"] or identity["git_dir"] != record["git_dir"]:
            raise RunError(f"{name} root identity changed")
        if identity["git_dir"] in seen_git_dirs:
            raise RunError("managed roots resolve to the same git repository")
        seen_git_dirs.add(identity["git_dir"])
        if run(
            [
                "git",
                "-C",
                str(path),
                "cat-file",
                "-e",
                f"{record['initial_head']}^{{commit}}",
            ],
            check=False,
        ).returncode:
            raise RunError(f"{name} starting commit is missing or rewritten")
    return current_roots


def snapshot_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    if not path.is_file() or path.is_symlink():
        raise RunError(f"state effect is not a regular file: {path}")
    data = path.read_bytes()
    return {
        "path": str(path),
        "exists": True,
        "sha256": hash_bytes(data),
        "bytes_b64": base64.b64encode(data).decode(),
    }


def snapshot_effects(operation: dict[str, Any]) -> dict[str, Any]:
    effects: dict[str, Any] = {"ledger": snapshot_file(ledger_path())}
    if operation["kind"] == "archive":
        name = operation["skill"]
        state = archive_state_dir()
        effects["retirement"] = snapshot_file(state / "retired" / f"{name}.json")
        effects["tombstone"] = snapshot_file(state / "tombstones" / f"{name}.json")
        if operation["root"] == "public":
            public_root = roots()["public"]
            for relative in PUBLIC_MANIFESTS:
                effects[f"manifest:{relative}"] = snapshot_file(public_root / relative)
    return effects


def verify_initial_dirty(manifest: dict[str, Any], current_roots: dict[str, Path]) -> None:
    for name, record in manifest["roots"].items():
        for expected in record["initial_dirty"]:
            actual = path_fingerprint(current_roots[name], expected["path"])
            if actual != expected:
                raise RunError(
                    f"pre-existing dirty path changed during run: {name}:{expected['path']}"
                )


def verify_dirty_state(
    manifest: dict[str, Any],
    current_roots: dict[str, Path],
    allowed: dict[str, list[str]] | None = None,
) -> None:
    verify_initial_dirty(manifest, current_roots)
    allowed = allowed or {}
    for name, root in current_roots.items():
        initial = {
            item["path"] for item in manifest["roots"][name]["initial_dirty"]
        }
        permitted = allowed.get(name, [])
        for current in dirty_paths(root):
            if current in initial:
                continue
            if current in permitted:
                continue
            raise RunError(f"undeclared dirty path: {name}:{current}")


def find_planned_operation(
    manifest: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    if any(operation["status"] == "intent" for operation in manifest["operations"]):
        raise RunError("the preceding mutation intent is still incomplete")
    operation = next(
        (
            item
            for item in manifest["operations"]
            if item["status"] == "planned"
        ),
        None,
    )
    if operation is None:
        raise RunError("no planned operation remains")
    if operation["kind"] != args.kind or operation["root"] != args.root:
        raise RunError(f"next planned operation is {operation['op_id']}")
    if args.skill and operation.get("skill") != args.skill:
        raise RunError(f"next planned operation is {operation['op_id']}")
    if args.action and operation.get("action") != args.action:
        raise RunError(f"next planned operation is {operation['op_id']}")
    if args.paths:
        supplied = sorted(
            {validate_relative_path(args.root, path) for path in args.paths}
        )
        if operation["paths"] != supplied:
            raise RunError(f"next planned operation is {operation['op_id']}")
    return operation


def expected_head(manifest: dict[str, Any], root_name: str) -> str:
    head = manifest["roots"][root_name]["initial_head"]
    for operation in manifest["operations"]:
        if operation["root"] == root_name and operation["status"] == "complete":
            head = operation["commit"]
    return head


def command_begin(args: argparse.Namespace) -> int:
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunError(f"cannot load plan: {error}") from error
    inventory = scanner_inventory()
    operations = normalize_plan(plan, inventory)
    configured_roots = roots()
    root_records = {
        name: {
            **root_identity(path),
            "initial_dirty": dirty_snapshot(path),
        }
        for name, path in configured_roots.items()
    }
    if root_records["public"]["git_dir"] == root_records["local"]["git_dir"]:
        raise RunError("managed roots resolve to the same git repository")
    verify_dirty_disjoint(root_records, operations)
    run_id = args.run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    path = manifest_path(run_id)
    if path.exists():
        raise RunError(f"run already exists: {run_id}")
    token = acquire_lock(f"skill-curator:{run_id}")
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "active",
        "started_at": now_iso(),
        "report": str(Path(args.report).resolve()),
        "plan": str(Path(args.plan).resolve()),
        "lock_token": token,
        "lock_renewed_at": now_iso(),
        "roots": root_records,
        "dependency_freeze": inventory,
        "operations": operations,
    }
    try:
        atomic_write(path, payload)
    except Exception:
        lock_command("release", token, check=False)
        raise
    print(run_id)
    return 0


def command_renew(args: argparse.Namespace) -> int:
    path, manifest = load_manifest(args.run)
    if manifest["status"] != "active":
        raise RunError(f"cannot renew run in status {manifest['status']}")
    verify_root_records(manifest)
    renew_lock(manifest)
    atomic_write(path, manifest)
    return 0


def command_intent(args: argparse.Namespace) -> int:
    path, manifest = load_manifest(args.run)
    if manifest["status"] != "active":
        raise RunError(f"cannot add intent to run in status {manifest['status']}")
    current_roots = verify_root_records(manifest)
    renew_lock(manifest)
    verify_dirty_state(manifest, current_roots)
    operation = find_planned_operation(manifest, args)
    current_head = git(current_roots[operation["root"]], "rev-parse", "HEAD")
    if current_head != expected_head(manifest, operation["root"]):
        raise RunError(f"unexpected commit appeared in {operation['root']} root")
    operation["status"] = "intent"
    operation["intent_at"] = now_iso()
    operation["before_head"] = git(current_roots[operation["root"]], "rev-parse", "HEAD")
    operation["effects_before"] = snapshot_effects(operation)
    atomic_write(path, manifest)
    print(operation["op_id"])
    return 0


def operation_by_id(manifest: dict[str, Any], op_id: str) -> dict[str, Any]:
    for operation in manifest["operations"]:
        if operation["op_id"] == op_id:
            return operation
    raise RunError(f"unknown operation: {op_id}")


def commit_paths(root: Path, commit: str) -> list[str]:
    output = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    return [line for line in output.splitlines() if line]


def record_ledger_effect(operation: dict[str, Any]) -> dict[str, Any]:
    before = operation["effects_before"]["ledger"]
    path = Path(before["path"])
    current = path.read_bytes() if path.exists() else b""
    previous = base64.b64decode(before.get("bytes_b64", "")) if before["exists"] else b""
    if not current.startswith(previous):
        raise RunError("ledger changed non-append-only during operation")
    appended = current[len(previous) :]
    return {
        "path": str(path),
        "offset": len(previous),
        "bytes_b64": base64.b64encode(appended).decode(),
        "sha256": hash_bytes(appended),
    }


def complete_operation(
    path: Path, manifest: dict[str, Any], operation: dict[str, Any]
) -> None:
    current_roots = verify_root_records(manifest)
    renew_lock(manifest)
    if operation["status"] != "intent":
        raise RunError(f"operation is not awaiting completion: {operation['op_id']}")
    root = current_roots[operation["root"]]
    head = git(root, "rev-parse", "HEAD")
    if head == operation["before_head"]:
        raise RunError("operation produced no commit")
    count = int(git(root, "rev-list", "--count", f"{operation['before_head']}..{head}"))
    if count != 1:
        raise RunError("operation must produce exactly one commit")
    changed = commit_paths(root, head)
    for changed_path in changed:
        declared = (
            any(overlaps(changed_path, allowed) for allowed in operation["paths"])
            if operation["kind"] == "archive"
            else changed_path in operation["paths"]
        )
        if not declared:
            raise RunError(
                f"operation commit touched undeclared path: {operation['root']}:{changed_path}"
            )
    operation["commit"] = head
    operation["changed_paths"] = changed
    operation["effects_after"] = snapshot_effects(operation)
    operation["ledger_effect"] = record_ledger_effect(operation)
    operation["status"] = "complete"
    operation["completed_at"] = now_iso()
    verify_dirty_state(manifest, current_roots)
    atomic_write(path, manifest)


def command_complete(args: argparse.Namespace) -> int:
    path, manifest = load_manifest(args.run)
    if manifest["status"] != "active":
        raise RunError(f"cannot complete operation in status {manifest['status']}")
    operation = operation_by_id(manifest, args.op)
    complete_operation(path, manifest, operation)
    print(operation["commit"])
    return 0


def command_commit(args: argparse.Namespace) -> int:
    path, manifest = load_manifest(args.run)
    if manifest["status"] != "active":
        raise RunError(f"cannot commit operation in status {manifest['status']}")
    operation = operation_by_id(manifest, args.op)
    if operation["kind"] != "commit" or operation["status"] != "intent":
        raise RunError("scoped commit requires a commit intent")
    current_roots = verify_root_records(manifest)
    renew_lock(manifest)
    root = current_roots[operation["root"]]
    verify_dirty_state(
        manifest,
        current_roots,
        {operation["root"]: operation["paths"]},
    )
    message = Path(args.message_file).read_text(encoding="utf-8").rstrip()
    if TRAILER not in message:
        message = f"{message}\n\n{TRAILER}"
    message_path = Path(tempfile.mkstemp(prefix="curator-commit.", suffix=".txt")[1])
    try:
        message_path.write_text(f"{message}\n", encoding="utf-8")
        git(root, "add", "--", *operation["paths"])
        result = run(
            [
                "git",
                "-C",
                str(root),
                "commit",
                "--only",
                "-F",
                str(message_path),
                "--",
                *operation["paths"],
            ],
            check=False,
        )
        if result.returncode:
            git(root, "reset", "-q", "--", *operation["paths"], check=False)
            raise RunError(f"scoped curator commit failed: {result.stderr.strip()}")
    finally:
        message_path.unlink(missing_ok=True)
    complete_operation(path, manifest, operation)
    print(operation["commit"])
    return 0


def command_finish(args: argparse.Namespace) -> int:
    path, manifest = load_manifest(args.run)
    if manifest["status"] != "active":
        raise RunError(f"cannot finish run in status {manifest['status']}")
    incomplete = [
        operation["op_id"]
        for operation in manifest["operations"]
        if operation["status"] != "complete"
    ]
    if incomplete:
        raise RunError(f"run has incomplete operations: {', '.join(incomplete)}")
    current_roots = verify_root_records(manifest)
    for root_name, root in current_roots.items():
        if git(root, "rev-parse", "HEAD") != expected_head(manifest, root_name):
            raise RunError(f"unexpected commit appeared in {root_name} root")
    verify_dirty_state(manifest, current_roots)
    renew_lock(manifest)
    manifest["status"] = "complete"
    manifest["finished_at"] = now_iso()
    atomic_write(path, manifest)
    release_lock(manifest)
    return 0


def ensure_rollback_lock(manifest: dict[str, Any]) -> None:
    if lock_command("renew", manifest["lock_token"], check=False).returncode == 0:
        manifest["lock_renewed_at"] = now_iso()
        return
    manifest["lock_token"] = acquire_lock(f"skill-curator-rollback:{manifest['run_id']}")
    manifest["lock_renewed_at"] = now_iso()


def validate_rollback_dirty(
    manifest: dict[str, Any], current_roots: dict[str, Path]
) -> None:
    verify_initial_dirty(manifest, current_roots)
    active_paths = {
        name: {
            path
            for operation in manifest["operations"]
            if operation["root"] == name and operation["status"] == "intent"
            for path in operation["paths"]
        }
        for name in current_roots
    }
    for name, root in current_roots.items():
        initial = {
            item["path"] for item in manifest["roots"][name]["initial_dirty"]
        }
        for current in dirty_paths(root):
            if current in initial:
                continue
            if any(overlaps(current, allowed) for allowed in active_paths[name]):
                continue
            raise RunError(f"unexpected dirty path blocks rollback: {name}:{current}")


def infer_interrupted_commit(root: Path, operation: dict[str, Any]) -> str | None:
    head = git(root, "rev-parse", "HEAD")
    if head == operation["before_head"]:
        return None
    count = int(git(root, "rev-list", "--count", f"{operation['before_head']}..{head}"))
    if count != 1:
        raise RunError(
            f"cannot infer interrupted operation {operation['op_id']}: history advanced by {count} commits"
        )
    for changed in commit_paths(root, head):
        if not any(overlaps(changed, allowed) for allowed in operation["paths"]):
            raise RunError(
                f"interrupted operation commit touched undeclared path: {changed}"
            )
    return head


def remove_empty_new_parents(root: Path, target: Path, before_head: str) -> None:
    parent = target.parent
    while parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent_relative = parent.relative_to(root).as_posix()
        if run(
            [
                "git",
                "-C",
                str(root),
                "cat-file",
                "-e",
                f"{before_head}:{parent_relative}",
            ],
            check=False,
        ).returncode == 0:
            break
        parent.rmdir()
        parent = parent.parent


def remove_uncommitted_operation(root: Path, operation: dict[str, Any]) -> None:
    for relative in operation["paths"]:
        existed = (
            run(
                [
                    "git",
                    "-C",
                    str(root),
                    "cat-file",
                    "-e",
                    f"{operation['before_head']}:{relative}",
                ],
                check=False,
            ).returncode
            == 0
        )
        if existed:
            git(root, "reset", "-q", "--", relative, check=False)
            target = (root / relative).resolve()
            try:
                target.relative_to(root)
            except ValueError as error:
                raise RunError(f"unsafe cleanup path: {target}") from error
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            remove_empty_new_parents(root, target, operation["before_head"])
            git(root, "checkout", operation["before_head"], "--", relative)
        else:
            git(root, "reset", "-q", "--", relative, check=False)
            target = (root / relative).resolve()
            try:
                target.relative_to(root)
            except ValueError as error:
                raise RunError(f"unsafe cleanup path: {target}") from error
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            remove_empty_new_parents(root, target, operation["before_head"])


def restore_snapshot(snapshot: dict[str, Any], expected_after: dict[str, Any] | None) -> None:
    path = Path(snapshot["path"])
    if expected_after and expected_after.get("exists") and path.exists():
        if hash_bytes(path.read_bytes()) != expected_after["sha256"]:
            raise RunError(f"state effect changed after operation: {path}")
    if snapshot["exists"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(snapshot["bytes_b64"])
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    elif path.exists():
        path.unlink()


def validate_effects_after(operation: dict[str, Any]) -> None:
    for name, expected in operation.get("effects_after", {}).items():
        if name == "ledger":
            continue
        path = Path(expected["path"])
        if expected["exists"]:
            if not path.is_file() or hash_bytes(path.read_bytes()) != expected["sha256"]:
                raise RunError(f"recorded state effect is missing or changed: {path}")
        elif path.exists():
            raise RunError(f"unexpected state effect appeared after operation: {path}")


def scoped_revert(root: Path, operation: dict[str, Any], commit: str) -> str:
    with tempfile.TemporaryDirectory(prefix="curator-revert.") as temporary:
        index = Path(temporary) / "index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(index)
        seeded = subprocess.run(
            ["git", "-C", str(root), "read-tree", "HEAD"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if seeded.returncode:
            raise RunError(f"cannot seed isolated revert index: {seeded.stderr.strip()}")
        result = subprocess.run(
            ["git", "-C", str(root), "revert", "--no-edit", commit],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            subprocess.run(
                ["git", "-C", str(root), "revert", "--abort"],
                env=environment,
                capture_output=True,
                check=False,
            )
            git(root, "checkout", "HEAD", "--", *operation["paths"], check=False)
            raise RunError(f"git revert failed for {commit}: {result.stderr.strip()}")
    # The isolated index protects unrelated staged work. Bring only this
    # operation's paths in the real index forward to the new HEAD.
    git(root, "reset", "-q", "HEAD", "--", *operation["paths"])
    return git(root, "rev-parse", "HEAD")


def reverse_ledger(operation: dict[str, Any]) -> None:
    effect = operation.get("ledger_effect")
    if not effect:
        return
    added = base64.b64decode(effect["bytes_b64"])
    if not added:
        return
    path = Path(effect["path"])
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        current = handle.read()
        offset = effect["offset"]
        if current[offset : offset + len(added)] != added:
            raise RunError(f"recorded ledger effect is missing or changed: {path}")
        updated = current[:offset] + current[offset + len(added) :]
        handle.seek(0)
        handle.write(updated)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def reverse_operation(
    manifest_path_value: Path,
    manifest: dict[str, Any],
    operation: dict[str, Any],
    current_roots: dict[str, Path],
) -> None:
    root = current_roots[operation["root"]]
    commit = operation.get("commit")
    if operation["status"] == "intent":
        commit = infer_interrupted_commit(root, operation)
        if commit is None:
            remove_uncommitted_operation(root, operation)
            operation["status"] = "rolled_back"
            operation["rolled_back_at"] = now_iso()
            atomic_write(manifest_path_value, manifest)
            return
        operation["commit"] = commit
        operation["changed_paths"] = commit_paths(root, commit)
        operation["effects_after"] = snapshot_effects(operation)
        operation["ledger_effect"] = record_ledger_effect(operation)
    if operation["status"] not in {"complete", "intent"} or not commit:
        return
    if run(
        ["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
    ).returncode:
        raise RunError(f"operation commit is missing: {commit}")
    if run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
    ).returncode:
        raise RunError(f"operation commit is no longer in current history: {commit}")

    if operation["kind"] == "archive":
        validate_effects_after(operation)
        environment = os.environ.copy()
        environment.pop("SKILLS_CURATOR_RUN_ID", None)
        environment["SKILLS_CURATOR_ROLLBACK"] = manifest["run_id"]
        environment["SKILLS_RESTORE_GIT_ROOT"] = str(root)
        environment["SKILLS_RESTORE_SRC_REL"] = operation["paths"][0]
        environment["SKILLS_RESTORE_SHA"] = operation["before_head"]
        with tempfile.TemporaryDirectory(prefix="curator-manifests.") as temporary:
            if operation["root"] == "public":
                snapshot_root = Path(temporary)
                for relative in PUBLIC_MANIFESTS:
                    snapshot = operation["effects_before"][f"manifest:{relative}"]
                    if not snapshot["exists"]:
                        raise RunError(f"pre-archive manifest was missing: {relative}")
                    target = snapshot_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(base64.b64decode(snapshot["bytes_b64"]))
                environment["SKILLS_RESTORE_MANIFEST_SNAPSHOT"] = temporary
            result = subprocess.run(
                [str(RESTORE_TOOL), operation["skill"]],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode:
            raise RunError(
                f"archive rollback failed for {operation['skill']}: {result.stderr.strip()}"
            )
    else:
        scoped_revert(root, operation, commit)

    reverse_ledger(operation)
    after = operation.get("effects_after", {})
    for name, snapshot in operation["effects_before"].items():
        if name == "ledger":
            continue
        restore_snapshot(snapshot, None)
    operation["status"] = "rolled_back"
    operation["rollback_commit"] = git(root, "rev-parse", "HEAD")
    operation["rolled_back_at"] = now_iso()
    atomic_write(manifest_path_value, manifest)
    verify_dirty_state(manifest, current_roots)


def command_rollback(args: argparse.Namespace) -> int:
    path, manifest = load_manifest(args.run)
    if manifest["status"] == "rolled_back":
        return 0
    if manifest["status"] not in {"active", "complete", "rollback_failed", "rolling_back"}:
        raise RunError(f"cannot rollback run in status {manifest['status']}")
    current_roots = verify_root_records(manifest)
    ensure_rollback_lock(manifest)
    atomic_write(path, manifest)
    validate_rollback_dirty(manifest, current_roots)
    manifest["status"] = "rolling_back"
    manifest.setdefault("rollback_started_at", now_iso())
    atomic_write(path, manifest)
    try:
        for operation in reversed(manifest["operations"]):
            if operation["status"] in {"complete", "intent"}:
                renew_lock(manifest)
                reverse_operation(path, manifest, operation, current_roots)
        manifest["status"] = "rolled_back"
        manifest["rolled_back_at"] = now_iso()
        atomic_write(path, manifest)
        release_lock(manifest)
        return 0
    except Exception:
        manifest["status"] = "rollback_failed"
        manifest["rollback_failed_at"] = now_iso()
        atomic_write(path, manifest)
        raise


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin")
    begin.add_argument("--plan", required=True)
    begin.add_argument("--report", required=True)
    begin.add_argument("--run-id")
    begin.set_defaults(func=command_begin)

    renew = sub.add_parser("renew")
    renew.add_argument("--run", required=True)
    renew.set_defaults(func=command_renew)

    intent = sub.add_parser("intent")
    intent.add_argument("--run", required=True)
    intent.add_argument("--kind", choices=("archive", "commit"), required=True)
    intent.add_argument("--root", choices=("public", "local"), required=True)
    intent.add_argument("--skill")
    intent.add_argument("--action", choices=("patch", "create"))
    intent.add_argument("--paths", nargs="*")
    intent.set_defaults(func=command_intent)

    complete = sub.add_parser("complete")
    complete.add_argument("--run", required=True)
    complete.add_argument("--op", required=True)
    complete.set_defaults(func=command_complete)

    commit = sub.add_parser("commit")
    commit.add_argument("--run", required=True)
    commit.add_argument("--op", required=True)
    commit.add_argument("--message-file", required=True)
    commit.set_defaults(func=command_commit)

    finish = sub.add_parser("finish")
    finish.add_argument("--run", required=True)
    finish.set_defaults(func=command_finish)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--run", required=True)
    rollback.set_defaults(func=command_rollback)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except (RunError, OSError, ValueError, KeyError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
