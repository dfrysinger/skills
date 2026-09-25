#!/usr/bin/env python3
"""Plan and run a sealed distributed skill-evaluation campaign."""

from __future__ import annotations

import argparse
import copy
import contextlib
import hashlib
import importlib.util
import json
import os
import platform
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath


PACKAGE_ARCHIVE_SHA256 = os.environ.get(
    "DISTRIBUTED_EVAL_PACKAGE_ARCHIVE_SHA256",
    "0" * 64,
)
PACKAGE_MANIFEST_SHA256 = os.environ.get(
    "DISTRIBUTED_EVAL_PACKAGE_MANIFEST_SHA256",
    "0" * 64,
)
CANDIDATE_PACKAGE_ARCHIVE_SHA256 = os.environ.get(
    "CANDIDATE_PACKAGE_SHA256",
) or PACKAGE_ARCHIVE_SHA256
CAMPAIGN_ID = os.environ.get(
    "DISTRIBUTED_EVAL_CAMPAIGN_ID",
    "skill-evaluation-campaign",
)
IDENTITY_KEYS = (
    "attemptId",
    "caseId",
    "caseRevision",
    "treatmentId",
    "repetition",
)
SECRET_ENV_NAMES = (
    "COPILOT_GITHUB_TOKEN",
    "COPILOT_EVAL_MODEL_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "AZURE_DEVOPS_EXT_PAT",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"Expected a JSON object: {path}")
    return value


def read_json_list(path: Path) -> list:
    value = json.loads(path.read_text())
    require(isinstance(value, list), f"Expected a JSON array: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_tree(workspace: Path, revision: str = "HEAD") -> str:
    value = subprocess.check_output(
        ["git", "rev-parse", f"{revision}^{{tree}}"],
        cwd=workspace,
        text=True,
    ).strip()
    require(re.fullmatch(r"[0-9a-f]{40,64}", value) is not None, "Invalid Git tree identity")
    return value


def apply_candidate_patch(workspace: Path, patch: Path) -> bool:
    if patch.stat().st_size == 0:
        return False
    subprocess.run(
        ["git", "apply", "--binary", str(patch.resolve())],
        cwd=workspace,
        check=True,
    )
    return True


def run_candidate_with_public_github(
    runner, *, before_copilot=None, **kwargs
) -> dict:
    original_run_command = runner.run_command
    prepared = False

    def run_command_with_public_github(command, **command_kwargs):
        nonlocal prepared
        environment = command_kwargs.get("environment")
        if command and command[0] == "copilot" and environment is not None:
            if before_copilot is not None and not prepared:
                before_copilot()
                prepared = True
            environment = environment.copy()
            environment.pop("GH_HOST", None)
            command_kwargs["environment"] = environment
        return original_run_command(command, **command_kwargs)

    runner.run_command = run_command_with_public_github
    try:
        return runner.run_candidate(**kwargs)
    finally:
        runner.run_command = original_run_command


def remove_sealed_tree(root: Path) -> None:
    if not root.exists():
        return
    if platform.system() == "Darwin":
        subprocess.run(["chmod", "-RN", str(root)], check=True)
    shutil.rmtree(root)


def make_container_workspace_writable(candidate_root: Path) -> None:
    workspaces = candidate_root / "workspaces"
    for root, directories, files in os.walk(workspaces):
        for name in directories:
            path = Path(root) / name
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        for name in files:
            path = Path(root) / name
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    workspaces.chmod(
        workspaces.stat().st_mode
        | stat.S_IWUSR
        | stat.S_IWGRP
        | stat.S_IWOTH
    )


def make_container_workspace_roots_writable(candidate_root: Path) -> None:
    workspaces = candidate_root / "workspaces"
    for workspace in workspaces.iterdir():
        if workspace.is_dir() and not workspace.is_symlink():
            workspace.chmod(
                workspace.stat().st_mode
                | stat.S_IWUSR
                | stat.S_IWGRP
                | stat.S_IWOTH
            )


def synchronize_grading_git_identity(candidate_root: Path, sources: list[dict]) -> list[dict]:
    expected = {record["workspace"]: record["resultTree"] for record in sources}
    workspaces = candidate_root / "workspaces"
    receipts = []
    for workspace in sorted(workspaces.iterdir()):
        if not (workspace / ".git").is_dir():
            continue
        require(workspace.name in expected, f"Missing captured source identity: {workspace.name}")
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
        listing = subprocess.check_output(["git", "ls-files", "-z"], cwd=workspace)
        require(listing, f"Git reported no tracked grading files: {workspace.name}")
        tree = subprocess.check_output(
            ["git", "write-tree"], cwd=workspace, text=True
        ).strip()
        require(
            tree == expected[workspace.name],
            f"Grading Git tree differs from captured candidate: {workspace.name}",
        )
        receipts.append(
            {
                "workspace": workspace.name,
                "trackedFiles": listing.count(b"\0"),
                "tree": tree,
            }
        )
    require(set(expected) == {record["workspace"] for record in receipts},
            "Grading Git identity does not cover every captured workspace")
    return receipts


def verify_candidate_trees(candidate_root: Path, sources: list[dict]) -> None:
    for source in sources:
        workspace = source["workspace"]
        repository = candidate_root / "workspaces" / workspace
        require((repository / ".git").is_dir(), f"{workspace}: candidate Git metadata is missing")
        subprocess.run(["git", "add", "-A"], cwd=repository, check=True)
        actual_tree = subprocess.check_output(
            ["git", "write-tree"], cwd=repository, text=True
        ).strip()
        require(
            actual_tree == source["resultTree"],
            f"{workspace}: candidate tree changed after candidate capture",
        )


@contextlib.contextmanager
def dependency_environment(
    dependency_sources: dict[str, Path],
    candidate_root: Path | None = None,
    run_root: Path | None = None,
    cargo_fetch_workspace: Path | None = None,
):
    cargo_homes = {
        (source / "cargo-home").resolve()
        for source in dependency_sources.values()
        if (source / "cargo-home").is_dir()
    }
    if candidate_root is not None:
        cargo_homes.update(
            path.resolve()
            for path in (candidate_root / "workspaces").glob("*/.cargo-home")
            if path.is_dir()
        )
        git_sources = [
            path.resolve()
            for path in (candidate_root / "workspaces").glob("*/.cargo-git")
            if path.is_dir()
        ]
        require(len(git_sources) <= 1, "Multiple scaffolded Cargo Git caches are ambiguous")
        if git_sources:
            require(run_root is not None, "Cargo Git provisioning requires a run root")
            ambient_registry = Path.home() / ".cargo/registry"
            overlay = run_root / "dependency-runtime/cargo-home"
            require(not overlay.exists(), "Cargo dependency overlay already exists")
            overlay.mkdir(parents=True)
            if ambient_registry.is_dir():
                shutil.copytree(git_sources[0], overlay / "git", symlinks=True)
                os.symlink(ambient_registry, overlay / "registry", target_is_directory=True)
            else:
                require(
                    cargo_fetch_workspace is not None,
                    "Trusted Cargo dependency workspace is required",
                )
                workspace = cargo_fetch_workspace.resolve()
                require(
                    (workspace / "Cargo.toml").is_file()
                    and (workspace / "Cargo.lock").is_file(),
                    "Cargo dependency fetch requires a locked workspace",
                )
                for ancestor in workspace.parents:
                    for config_name in (".cargo/config", ".cargo/config.toml"):
                        require(
                            not (ancestor / config_name).exists(),
                            f"Cargo fetch ancestor config is not allowed: "
                            f"{ancestor / config_name}",
                        )
                trusted_git = workspace / ".cargo-git"
                require(
                    trusted_git.is_dir(),
                    "Trusted Cargo dependency workspace lacks the sealed Git cache",
                )
                shutil.copytree(trusted_git, overlay / "git", symlinks=True)
                log = run_root / "dependency-logs/cargo-fetch.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                fetch_home = run_root / "dependency-runtime/cargo-fetch-home"
                fetch_home.mkdir()
                environment = {
                    name: os.environ[name]
                    for name in (
                        "PATH",
                        "TMPDIR",
                        "SSL_CERT_FILE",
                        "SSL_CERT_DIR",
                        "RUSTUP_HOME",
                        "RUSTUP_TOOLCHAIN",
                    )
                    if name in os.environ
                }
                owner_home = Path.home()
                rustup_home = Path(
                    environment.get("RUSTUP_HOME", owner_home / ".rustup")
                ).resolve()
                if rustup_home.is_dir():
                    environment["RUSTUP_HOME"] = str(rustup_home)
                    if "RUSTUP_TOOLCHAIN" not in environment:
                        settings = rustup_home / "settings.toml"
                        require(settings.is_file(), "Rustup settings are missing")
                        match = re.search(
                            r'^default_toolchain\s*=\s*"([^"]+)"\s*$',
                            settings.read_text(),
                            flags=re.MULTILINE,
                        )
                        require(
                            match is not None,
                            "Rustup default toolchain is missing",
                        )
                        environment["RUSTUP_TOOLCHAIN"] = match.group(1)
                environment.update(
                    {
                        "CARGO_HOME": str(overlay),
                        "CARGO_NET_OFFLINE": "false",
                        "CARGO_NET_GIT_FETCH_WITH_CLI": "false",
                        "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
                        "GIT_CONFIG_GLOBAL": "/dev/null",
                        "GIT_CONFIG_SYSTEM": "/dev/null",
                        "GIT_TERMINAL_PROMPT": "0",
                        "HOME": str(fetch_home),
                    }
                )
                with log.open("wb") as output:
                    completed = subprocess.run(
                        ["cargo", "fetch", "--locked"],
                        cwd=workspace,
                        env=environment,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                require(completed.returncode == 0, "Locked Cargo dependency fetch failed")
                require(
                    (overlay / "registry").is_dir(),
                    "Locked Cargo dependency fetch produced no registry cache",
                )
                write_json(
                    run_root / "dependency-logs/cargo-fetch.json",
                    {
                        "argv": ["cargo", "fetch", "--locked"],
                        "cwd": str(workspace),
                        "exitCode": completed.returncode,
                        "cargoLockSha256": sha256(workspace / "Cargo.lock"),
                        "cargoManifestSha256": sha256(workspace / "Cargo.toml"),
                        "log": log.name,
                        "logSha256": sha256(log),
                    },
                )
            cargo_homes.add(overlay.resolve())
    cargo_homes = sorted(cargo_homes)
    require(len(cargo_homes) <= 1, "Multiple dependency Cargo homes are ambiguous")
    previous = os.environ.get("CARGO_HOME")
    if cargo_homes:
        os.environ["CARGO_HOME"] = str(cargo_homes[0])
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CARGO_HOME", None)
        else:
            os.environ["CARGO_HOME"] = previous


@contextlib.contextmanager
def pythonpath_environment(paths: list[Path]):
    previous = os.environ.get("PYTHONPATH")
    if paths:
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(path) for path in paths] + ([previous] if previous else [])
        )
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = previous


def safe_name(value: str, label: str = "name") -> str:
    require(
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is not None,
        f"Unsafe {label}: {value!r}",
    )
    return value


def check_sha256(value: str, label: str) -> str:
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
        f"Invalid {label} SHA256",
    )
    return value


def normalize_machine() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in {"arm64", "aarch64"} else machine


def attempt_identity(attempt: dict) -> dict:
    return {key: attempt[key] for key in IDENTITY_KEYS}


def identity_tuple(attempt: dict) -> tuple:
    return tuple(attempt[key] for key in IDENTITY_KEYS)


def validate_attempt(attempt: dict) -> None:
    require(isinstance(attempt, dict), "Attempt must be an object")
    safe_name(attempt.get("attemptId"), "attempt id")
    safe_name(attempt.get("caseId"), "case id")
    check_sha256(attempt.get("caseRevision"), "case revision")
    safe_name(attempt.get("treatmentId"), "treatment id")
    require(type(attempt.get("repetition")) is int and attempt["repetition"] >= 1,
            "Attempt repetition must be positive")
    require(
        type(attempt.get("candidateTimeoutSeconds")) is int
        and attempt["candidateTimeoutSeconds"] > 0,
        "Attempt candidate timeout must be positive",
    )


def load_package(
    package_root: Path,
    expected_manifest_sha256: str | None = None,
) -> tuple[dict, dict, dict[str, dict]]:
    if expected_manifest_sha256 is None:
        expected_manifest_sha256 = PACKAGE_MANIFEST_SHA256
    manifest_path = package_root / "package-manifest.json"
    matrix_path = package_root / "execution-matrix.json"
    require(manifest_path.is_file() and matrix_path.is_file(), "Package root is incomplete")
    require(
        sha256(manifest_path) == check_sha256(expected_manifest_sha256, "package manifest"),
        "Package manifest SHA256 mismatch",
    )
    manifest = read_json(manifest_path)
    matrix = read_json(matrix_path)
    require(manifest.get("campaignId") == CAMPAIGN_ID, "Unexpected package campaign")
    require(matrix.get("campaignId") == CAMPAIGN_ID, "Unexpected matrix campaign")
    require(manifest.get("schemaVersion") == 1, "Unsupported package manifest schema")
    require(matrix.get("schemaVersion") == 1, "Unsupported execution matrix schema")
    attempts = matrix.get("attempts")
    require(isinstance(attempts, list) and attempts, "Execution matrix is empty")
    by_id: dict[str, dict] = {}
    identities: set[tuple] = set()
    for attempt in attempts:
        validate_attempt(attempt)
        attempt_id = attempt["attemptId"]
        require(attempt_id not in by_id, f"Duplicate matrix attempt id: {attempt_id}")
        identity = identity_tuple(attempt)
        require(identity not in identities, f"Duplicate matrix attempt identity: {attempt_id}")
        by_id[attempt_id] = attempt
        identities.add(identity)
    return manifest, matrix, by_id


def case_records(package_root: Path, package: dict) -> dict[str, dict]:
    result = {}
    for record in package.get("cases", []):
        case_id = safe_name(record.get("caseId"), "package case id")
        require(case_id not in result, f"Duplicate package case: {case_id}")
        check_sha256(record.get("caseRevision"), "package case revision")
        relative = PurePosixPath(record.get("manifest", ""))
        require(relative.parts and not relative.is_absolute() and ".." not in relative.parts,
                f"Unsafe case manifest path: {relative}")
        path = package_root / relative
        require(path.is_file(), f"Case manifest is missing: {case_id}")
        require(
            sha256(path) == check_sha256(record.get("manifestSha256"), "case manifest"),
            f"Case manifest digest mismatch: {case_id}",
        )
        case = read_json(path)
        require(case.get("caseId") == case_id, f"Case id mismatch: {case_id}")
        require(
            case.get("caseRevision") == record["caseRevision"],
            f"Case revision mismatch: {case_id}",
        )
        result[case_id] = case
    require(result, "Package has no cases")
    return result


def validate_completion_manifest(
    path: Path,
    by_id: dict[str, dict],
    *,
    expected_file_sha256: str | None = None,
) -> tuple[dict, set[str]]:
    if expected_file_sha256 is not None:
        require(
            sha256(path) == check_sha256(expected_file_sha256, "completion manifest"),
            "Completion manifest SHA256 mismatch",
        )
    value = read_json(path)
    return value, validate_completion_manifest_from_value(value, by_id)


def validate_image_manifest(
    path: Path,
    *,
    expected_file_sha256: str | None = None,
) -> tuple[dict, dict[str, dict]]:
    if expected_file_sha256 is not None:
        require(
            sha256(path) == check_sha256(expected_file_sha256, "image manifest"),
            "Image manifest SHA256 mismatch",
        )
    value = read_json(path)
    require(value.get("schemaVersion") == 1, "Unsupported image manifest schema")
    assets = value.get("assets")
    require(isinstance(assets, list), "Image manifest assets must be a list")
    by_image: dict[str, dict] = {}
    for asset in assets:
        require(isinstance(asset, dict), "Image asset must be an object")
        image_id = asset.get("imageId")
        require(
            isinstance(image_id, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is not None,
            "Invalid image id",
        )
        require(image_id not in by_image, f"Duplicate image asset: {image_id}")
        safe_name(asset.get("release"), "image release")
        safe_name(asset.get("asset"), "image asset")
        check_sha256(asset.get("sha256"), "image asset")
        require(type(asset.get("bytes")) is int and 0 < asset["bytes"] < 2_000_000_000,
                f"Invalid image asset size: {image_id}")
        by_image[image_id] = asset
    return value, by_image


def validate_dependency_manifest(path: Path) -> tuple[dict, dict[str, dict]]:
    value = read_json(path)
    require(value.get("schemaVersion") == 1, "Unsupported dependency manifest schema")
    records = value.get("dependencies")
    require(isinstance(records, list), "Dependency manifest dependencies must be a list")
    by_case = {}
    workspaces = set()
    for record in records:
        require(isinstance(record, dict), "Dependency record must be an object")
        workspace = safe_name(record.get("workspace"), "dependency workspace")
        require(workspace not in workspaces, f"Duplicate dependency workspace: {workspace}")
        workspaces.add(workspace)
        require(record.get("status") in {"READY", "PENDING"}, "Invalid dependency status")
        root = record.get("archiveRoot")
        require(root == "." or safe_name(root, "dependency archive root"), "Invalid archive root")
        locks = record.get("locks")
        require(isinstance(locks, list) and locks, f"Dependency locks missing: {workspace}")
        for lock in locks:
            relative = PurePosixPath(lock.get("path", ""))
            require(
                relative.parts and not relative.is_absolute() and ".." not in relative.parts,
                f"Unsafe dependency lock path: {workspace}",
            )
            check_sha256(lock.get("sha256"), f"{workspace} lock")
        cache_paths = record.get("cachePaths")
        require(
            isinstance(cache_paths, list) and cache_paths,
            f"Dependency cache paths missing: {workspace}",
        )
        for cache_path in cache_paths:
            relative = PurePosixPath(cache_path)
            require(
                relative.parts and not relative.is_absolute() and ".." not in relative.parts,
                f"Unsafe dependency cache path: {workspace}",
            )
        cases = record.get("cases")
        require(isinstance(cases, list) and cases, f"Dependency cases missing: {workspace}")
        for case_id in cases:
            safe_name(case_id, "dependency case id")
            require(case_id not in by_case, f"Case has multiple dependency archives: {case_id}")
            by_case[case_id] = record
        if record["status"] == "READY":
            safe_name(record.get("release"), "dependency release")
            safe_name(record.get("asset"), "dependency asset")
            check_sha256(record.get("sha256"), "dependency archive")
            require(
                type(record.get("bytes")) is int and 0 < record["bytes"] < 2_000_000_000,
                f"Invalid dependency archive size: {workspace}",
            )
        else:
            require(
                isinstance(record.get("reason"), str) and record["reason"].strip(),
                f"Pending dependency requires a reason: {workspace}",
            )
    return value, by_case


def build_plan(
    package_root: Path,
    completion_path: Path,
    image_manifest_path: Path,
    dependency_manifest_path: Path,
    *,
    completion_sha256: str | None = None,
    image_manifest_sha256: str | None = None,
    expected_manifest_sha256: str = PACKAGE_MANIFEST_SHA256,
    selected_attempt_id: str | None = None,
) -> dict:
    package, matrix, by_id = load_package(package_root, expected_manifest_sha256)
    _, excluded = validate_completion_manifest(
        completion_path, by_id, expected_file_sha256=completion_sha256
    )
    cases = case_records(package_root, package)
    _, images = validate_image_manifest(
        image_manifest_path, expected_file_sha256=image_manifest_sha256
    )
    _, dependencies = validate_dependency_manifest(dependency_manifest_path)
    jobs = []
    for attempt in matrix["attempts"]:
        if attempt["attemptId"] in excluded:
            continue
        if selected_attempt_id and attempt["attemptId"] != selected_attempt_id:
            continue
        case = cases.get(attempt["caseId"])
        require(case is not None, f"Attempt case absent from package: {attempt['attemptId']}")
        require(
            case["caseRevision"] == attempt["caseRevision"],
            f"Attempt case revision mismatch: {attempt['attemptId']}",
        )
        target = case.get("runtime", {}).get("platform")
        require(isinstance(target, dict), f"Missing runtime platform: {attempt['caseId']}")
        require(target.get("architecture") == "arm64", "Only sealed arm64 cases are supported")
        os_name = target.get("os")
        require(os_name in {"linux", "macos"}, f"Unsupported target OS: {os_name}")
        route = "full-linux" if os_name == "linux" else "macos-native-stage"
        grading = case.get("grading", {})
        grading_route = (
            "hosted-final"
            if route == "full-linux"
            else "linux-container-final"
            if grading.get("execution") == "container"
            else "macos-host-final"
        )
        image_id = ""
        image_release = ""
        image_asset = ""
        image_sha256 = ""
        image_bytes = 0
        if grading.get("execution") == "container":
            image_id = grading.get("image", "")
            require(image_id in images, f"No release asset for grading image: {image_id}")
            asset = images[image_id]
            image_release = asset["release"]
            image_asset = asset["asset"]
            image_sha256 = asset["sha256"]
            image_bytes = asset["bytes"]
        elif grading.get("execution") != "host":
            raise ValueError(f"Unsupported grading execution: {attempt['caseId']}")
        dependency = dependencies.get(attempt["caseId"])
        dependency_fields = {
            "dependencyWorkspace": "",
            "dependencyRelease": "",
            "dependencyAsset": "",
            "dependencySha256": "",
            "dependencyBytes": 0,
            "dependencyArchiveRoot": "",
        }
        if dependency is not None:
            require(
                os_name == "macos",
                f"Linux dependency archives are not supported: {attempt['caseId']}",
            )
            require(
                dependency["status"] == "READY",
                f"Dependency archive is not ready for {attempt['caseId']}: "
                f"{dependency.get('reason', 'missing sealed asset identity')}",
            )
            dependency_fields = {
                "dependencyWorkspace": dependency["workspace"],
                "dependencyRelease": dependency["release"],
                "dependencyAsset": dependency["asset"],
                "dependencySha256": dependency["sha256"],
                "dependencyBytes": dependency["bytes"],
                "dependencyArchiveRoot": dependency["archiveRoot"],
            }
        jobs.append(
            {
                **attempt_identity(attempt),
                "candidateTimeoutSeconds": attempt["candidateTimeoutSeconds"],
                "route": route,
                "gradingRoute": grading_route,
                "targetOs": os_name,
                "imageId": image_id,
                "imageRelease": image_release if image_id else "",
                "imageAsset": image_asset,
                "imageSha256": image_sha256,
                "imageBytes": image_bytes,
                **dependency_fields,
            }
        )
    if selected_attempt_id:
        safe_name(selected_attempt_id, "selected attempt id")
        require(selected_attempt_id in by_id, f"Unknown selected attempt: {selected_attempt_id}")
        require(len(jobs) == 1, f"Selected attempt is completed, excluded, or unavailable: {selected_attempt_id}")
    macos_jobs = [job for job in jobs if job["targetOs"] == "macos"]
    linux_jobs = [job for job in jobs if job["targetOs"] == "linux"]
    if CANDIDATE_PACKAGE_ARCHIVE_SHA256 != PACKAGE_ARCHIVE_SHA256:
        require(
            not linux_jobs,
            "Split candidate packages currently support only macOS attempts",
        )
        require(
            all(not job["dependencyAsset"] for job in macos_jobs),
            "Split candidate packages do not yet support external dependency archives",
        )
    return {
        "schemaVersion": 1,
        "campaignId": CAMPAIGN_ID,
        "packageArchiveSha256": PACKAGE_ARCHIVE_SHA256,
        "candidatePackageArchiveSha256": CANDIDATE_PACKAGE_ARCHIVE_SHA256,
        "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
        "excludedCount": len(excluded),
        "remainingCount": len(jobs),
        "matrix": {"include": jobs},
        "macosCount": len(macos_jobs),
        "linuxCount": len(linux_jobs),
        "macosMatrix": {"include": macos_jobs},
        "linuxMatrix": {"include": linux_jobs},
    }


def safe_extract(archive: Path, destination: Path, expected_sha256: str) -> dict:
    require(archive.is_file(), f"Archive is missing: {archive}")
    require(sha256(archive) == check_sha256(expected_sha256, "archive"), "Archive SHA256 mismatch")
    require(not destination.exists(), f"Extraction destination exists: {destination}")
    seen: set[str] = set()
    members = 0
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            require(path.parts and not path.is_absolute() and ".." not in path.parts,
                    f"Unsafe archive path: {path}")
            require(str(path) not in seen, f"Duplicate archive member: {path}")
            require(
                member.isdir() or member.isfile() or member.issym() or member.islnk(),
                f"Unsupported archive member: {path}",
            )
            if member.issym() or member.islnk():
                target = PurePosixPath(member.linkname)
                require(not target.is_absolute(), f"Absolute archive link: {path}")
                require(".." not in target.parts, f"Unsafe archive link target: {path}")
                link_base = path.parent if member.issym() else PurePosixPath()
                resolved = PurePosixPath(
                    posixpath.normpath(str(link_base.joinpath(target)))
                )
                require(".." not in resolved.parts, f"Escaping archive link: {path}")
            seen.add(str(path))
            members += 1
    destination.mkdir(parents=True)
    try:
        subprocess.run(
            ["tar", "--no-same-owner", "-xzpf", str(archive), "-C", str(destination)],
            check=True,
        )
        root = destination.resolve()
        for extracted in destination.rglob("*"):
            require(
                os.path.commonpath((root, extracted.resolve())) == str(root),
                f"Extracted path escapes destination: {extracted.relative_to(destination)}",
            )
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return {"sha256": sha256(archive), "bytes": archive.stat().st_size, "members": members}


def load_runner(package_root: Path):
    path = package_root / "runtime/run-attempt.py"
    require(path.is_file(), "Sealed evaluation runner is missing")
    spec = importlib.util.spec_from_file_location("sealed_evaluation_runner", path)
    require(spec is not None and spec.loader is not None, "Cannot load sealed runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_attempt(
    package_root: Path,
    attempt_id: str,
    supplied_identity: dict | None = None,
) -> tuple[dict, dict, dict]:
    package, _, by_id = load_package(package_root)
    safe_name(attempt_id, "attempt id")
    require(attempt_id in by_id, f"Unknown attempt: {attempt_id}")
    attempt = by_id[attempt_id]
    if supplied_identity is not None:
        require(
            attempt_identity(attempt) == supplied_identity,
            f"Dispatched attempt identity mismatch: {attempt_id}",
        )
    cases = case_records(package_root, package)
    case = cases[attempt["caseId"]]
    return package, attempt, case


def parse_dependency_sources(values: list[str]) -> dict[str, Path]:
    result = {}
    for item in values:
        name, separator, path = item.partition("=")
        require(separator == "=" and safe_name(name, "workspace") and path,
                f"Invalid dependency source: {item}")
        require(name not in result, f"Duplicate dependency source: {name}")
        result[name] = Path(path)
    return result


HOSTED_REDUNDANT_ROOT_CHOWN = (
    'if [ "$(id -u)" = 0 ]; then '
    "chown -R 0:0 /workspace/repo /workspace/capture; fi && "
)
HOSTED_CONTAINER_SAFE_DIRECTORY = (
    'mkdir -p "$HOME" && '
    "git config --file /workspace/capture/home/.gitconfig "
    "--add safe.directory /workspace/repo && "
)


def adapt_hosted_container_case(case: dict) -> tuple[dict, list[dict]]:
    adapted = copy.deepcopy(case)
    grading = adapted["grading"]
    adaptations = []
    if platform.system() != "Linux" or grading["execution"] != "container":
        return adapted, adaptations
    for phase in ("candidateSetup", "setup"):
        for index, command in enumerate(grading[phase]):
            argv = command.get("argv")
            if (
                isinstance(argv, list)
                and len(argv) == 3
                and argv[:2] == ["sh", "-c"]
                and HOSTED_REDUNDANT_ROOT_CHOWN in argv[2]
            ):
                argv[2] = argv[2].replace(
                    HOSTED_REDUNDANT_ROOT_CHOWN,
                    HOSTED_CONTAINER_SAFE_DIRECTORY,
                    1,
                )
                adaptations.append(
                    {
                        "phase": phase,
                        "index": index,
                        "reason": (
                            "The hosted container user namespace rejects recursive chown "
                            "on the bind-mounted workspace; host write permissions satisfy "
                            "the setup contract and Git is scoped to the exact mounted repo."
                        ),
                    }
                )
    return adapted, adaptations


def dependency_record(manifest_path: Path, workspace: str) -> dict:
    _, by_case = validate_dependency_manifest(manifest_path)
    matches = {
        id(record): record
        for record in by_case.values()
        if record["workspace"] == workspace
    }
    require(len(matches) == 1, f"Unknown dependency workspace: {workspace}")
    return next(iter(matches.values()))


def dependency_metadata(root: Path) -> str:
    records = []
    for path in [root, *sorted(root.rglob("*"))]:
        stat = path.lstat()
        kind = "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file"
        records.append(
            {
                "path": "." if path == root else path.relative_to(root).as_posix(),
                "kind": kind,
                "mode": stat.st_mode & 0o777,
                "bytes": stat.st_size if kind == "file" else None,
                "target": os.readlink(path) if path.is_symlink() else None,
            }
        )
    payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def dependency_path_metadata(root: Path) -> str:
    records = []
    for path in [root, *sorted(root.rglob("*"))]:
        stat = path.lstat()
        kind = "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file"
        records.append(
            {
                "path": "." if path == root else path.relative_to(root).as_posix(),
                "kind": kind,
                "bytes": stat.st_size if kind == "file" else None,
                "target": os.readlink(path) if path.is_symlink() else None,
            }
        )
    payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def dependency_content_sha256(root: Path) -> str:
    records = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            kind = "symlink"
            value = hashlib.sha256(os.readlink(path).encode()).hexdigest()
        elif path.is_file():
            kind = "file"
            value = sha256(path)
        else:
            continue
        records.append({"path": relative, "kind": kind, "sha256": value})
    payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def prepare_writable_dependency_sources(
    dependency_sources: dict[str, Path],
    run_root: Path,
) -> tuple[dict[str, Path], list[dict]]:
    runtime_sources = {}
    receipts = []
    for workspace, source in sorted(dependency_sources.items()):
        source = source.resolve()
        writable_caches = [
            name for name in ("node_modules", "target") if (source / name).is_dir()
        ]
        if not writable_caches:
            runtime_sources[workspace] = source
            continue
        destination = run_root / "dependency-runtime" / workspace / "source"
        require(not destination.exists(), f"Dependency runtime clone exists: {workspace}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_metadata = dependency_metadata(source)
        source_paths = dependency_path_metadata(source)
        source_content = dependency_content_sha256(source)
        subprocess.run(["cp", "-cR", str(source), str(destination)], check=True)
        require(
            dependency_path_metadata(destination) == source_paths,
            f"Dependency runtime clone differs before writable preparation: {workspace}",
        )
        require(
            dependency_content_sha256(destination) == source_content,
            f"Dependency runtime clone content differs: {workspace}",
        )
        subprocess.run(["chmod", "-RN", str(destination)], check=True)
        subprocess.run(["chmod", "-R", "u+rwX", str(destination)], check=True)
        require(
            dependency_path_metadata(destination) == source_paths,
            f"Dependency runtime clone paths changed during writable preparation: {workspace}",
        )
        runtime_sources[workspace] = destination
        receipts.append(
            {
                "workspace": workspace,
                "source": str(source),
                "runtimeSource": str(destination),
                "writableCaches": writable_caches,
                "sourceMetadataSha256Before": source_metadata,
                "sourcePathMetadataSha256": source_paths,
                "sourceContentSha256Before": source_content,
                "runtimePathMetadataSha256": dependency_path_metadata(destination),
                "runtimeContentSha256": dependency_content_sha256(destination),
                "copyCommand": ["cp", "-cR"],
                "sourceVerification": "pending",
            }
        )
    return runtime_sources, receipts


def verify_dependency_sources_unchanged(receipts: list[dict]) -> None:
    for receipt in receipts:
        source_after = dependency_metadata(Path(receipt["source"]))
        require(
            source_after == receipt["sourceMetadataSha256Before"],
            f"Sealed dependency source changed during execution: {receipt['workspace']}",
        )
        source_content_after = dependency_content_sha256(Path(receipt["source"]))
        require(
            source_content_after == receipt["sourceContentSha256Before"],
            f"Sealed dependency source content changed during execution: {receipt['workspace']}",
        )
        receipt["sourceMetadataSha256After"] = source_after
        receipt["sourceContentSha256After"] = source_content_after
        receipt["sourceVerification"] = "unchanged"


def dependency_acl_commands(root: Path) -> list[list[str]]:
    acl = (
        "everyone deny write,append,delete,delete_child,add_file,add_subdirectory,"
        "writeattr,writeextattr,chown,file_inherit,directory_inherit"
    )
    return [["chmod", "-R", "+a", acl, str(root)]]


def download_release_asset(
    repository: str,
    release: str,
    asset: str,
    destination: Path,
    attempts: int = 5,
    expected_sha256: str | None = None,
) -> None:
    require(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is not None,
        f"Unsafe repository: {repository!r}",
    )
    safe_name(release, "release")
    safe_name(asset, "asset")
    require(1 <= attempts <= 5, "Download attempts must be between 1 and 5")
    if expected_sha256 is not None:
        expected_sha256 = check_sha256(expected_sha256, "release asset")
    destination = destination.resolve()
    require(not destination.exists(), f"Download destination exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for index in range(attempts):
        with tempfile.TemporaryDirectory(
            prefix=f".{asset}.download-",
            dir=destination.parent,
        ) as temporary:
            completed = subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    release,
                    "--repo",
                    repository,
                    "--pattern",
                    asset,
                    "--dir",
                    temporary,
                ],
                check=False,
            )
            downloaded = Path(temporary) / asset
            if (
                completed.returncode == 0
                and downloaded.is_file()
                and (
                    expected_sha256 is None
                    or sha256(downloaded) == expected_sha256
                )
            ):
                os.replace(downloaded, destination)
                return
        if index + 1 < attempts:
            time.sleep(min(30, 2 ** (index + 1)))
    raise RuntimeError(f"Failed to download release asset after {attempts} attempts: {asset}")


def seal_tree(root: Path, evidence_path: Path) -> dict:
    require(platform.system() == "Darwin", "ACL sealing requires macOS")
    require(root.is_dir(), f"Seal root is missing: {root}")
    before = dependency_metadata(root)
    commands = dependency_acl_commands(root)
    for command in commands:
        subprocess.run(command, check=True)
    after = dependency_metadata(root)
    require(before == after, "ACL seal changed bytes, paths, or POSIX modes")
    receipt = {
        "schemaVersion": 1,
        "root": str(root),
        "metadataSha256Before": before,
        "metadataSha256After": after,
        "aclCommands": len(commands),
        "posixModesChanged": False,
        "bytesChanged": False,
    }
    write_json(evidence_path, receipt)
    return receipt


def unpack_dependency(
    manifest_path: Path,
    workspace: str,
    release: str,
    archive: Path,
    destination: Path,
    evidence_path: Path,
) -> dict:
    require(platform.system() == "Darwin", "Dependency ACL sealing requires macOS")
    record = dependency_record(manifest_path, safe_name(workspace, "dependency workspace"))
    require(record["status"] == "READY", f"Dependency archive is not ready: {workspace}")
    require(record["release"] == safe_name(release, "dependency release"),
            "Dependency release mismatch")
    require(record["asset"] == archive.name, "Dependency asset name mismatch")
    require(archive.stat().st_size == record["bytes"], "Dependency archive size mismatch")
    require(sha256(archive) == record["sha256"], "Dependency archive SHA256 mismatch")
    extraction = safe_extract(archive, destination, record["sha256"])
    source = destination if record["archiveRoot"] == "." else destination / record["archiveRoot"]
    require(source.is_dir(), "Dependency archive root is missing")
    for lock in record["locks"]:
        path = source / lock["path"]
        require(path.is_file(), f"Dependency lock is missing: {lock['path']}")
        require(sha256(path) == lock["sha256"], f"Dependency lock mismatch: {lock['path']}")
    expected_caches = set(record["cachePaths"])
    for relative in expected_caches:
        require((source / relative).is_dir(), f"Dependency cache is missing: {relative}")
    for known_cache in {"node_modules", "target"} - expected_caches:
        require(
            not (source / known_cache).exists(),
            f"Unexpected dependency cache is present: {known_cache}",
        )
    seal = seal_tree(source, evidence_path)
    receipt = {
        "schemaVersion": 1,
        "workspace": workspace,
        "release": record["release"],
        "asset": record["asset"],
        "archive": extraction,
        "archiveRoot": record["archiveRoot"],
        "source": str(source),
        "locks": record["locks"],
        "cachePaths": record["cachePaths"],
        "metadataSha256Before": seal["metadataSha256Before"],
        "metadataSha256After": seal["metadataSha256After"],
        "aclCommands": seal["aclCommands"],
        "posixModesChanged": False,
        "bytesChanged": False,
    }
    write_json(evidence_path, receipt)
    return receipt


def parse_judge_output(text: str) -> dict:
    expected = {
        "verdict",
        "confidence",
        "matched",
        "missed",
        "overcorrections",
        "generalized_skill_defect",
    }
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        objects = []
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                objects.append((index, end, candidate))
        contract_objects = [
            candidate for _, _, candidate in objects if set(candidate) == expected
        ]
        require(
            len(contract_objects) == 1 or (not contract_objects and len(objects) == 1),
            "Judge output must contain exactly one contract JSON object",
        )
        value = contract_objects[0] if contract_objects else objects[0][2]
    require(isinstance(value, dict), "Judge output must be a JSON object")
    require(set(value) == expected, "Judge output fields do not match the contract")
    require(value["verdict"] in {"PASS", "FAIL", "UNANSWERABLE"}, "Invalid judge verdict")
    require(value["confidence"] in {"LOW", "MEDIUM", "HIGH"}, "Invalid judge confidence")
    for name in ("matched", "missed", "overcorrections"):
        require(
            isinstance(value[name], list)
            and all(isinstance(item, str) and item.strip() for item in value[name]),
            f"Invalid judge {name}",
        )
    require(
        value["generalized_skill_defect"] is None
        or (
            isinstance(value["generalized_skill_defect"], str)
            and value["generalized_skill_defect"].strip()
        ),
        "Invalid generalized skill defect",
    )
    return value


def secure_run_judge(runner, *, case_root: Path, candidate_root: Path, run_root: Path,
                     model: str, timeout: int) -> dict:
    judge_root = run_root / "judge" / model
    judge_root.mkdir(parents=True)
    judge_inputs = run_root / "judge-input"
    judge_inputs.mkdir(exist_ok=True)
    criteria = judge_inputs / "criteria.md"
    shutil.copy2(case_root / "hidden/authority/criteria.md", criteria)
    prompt = (case_root / "hidden/authority/prompts/judge.md").read_text()
    prompt += (
        "\n\nInspect these exact local artifacts before deciding:\n"
        f"- hidden criteria: {criteria}\n"
        f"- candidate task: {candidate_root / 'task.md'}\n"
        f"- candidate transcript: {run_root / 'candidate-transcript.md'}\n"
        f"- candidate source deltas: {run_root / 'candidate-source'}\n"
        f"- deterministic receipt and logs: {run_root / 'deterministic'}\n"
        f"- product receipt and evidence: {run_root / 'product'}\n"
        "The historical reference is context, not a required implementation shape. "
        "Judge observable product correctness and sound engineering; accept any equivalent implementation."
    )
    environment = os.environ.copy()
    environment.pop("GH_HOST", None)
    credential_fragments = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "CREDENTIAL",
        "PRIVATE_KEY",
        "API_KEY",
    )
    for name in list(environment):
        if any(fragment in name.upper() for fragment in credential_fragments):
            environment.pop(name)
    environment["COPILOT_GITHUB_TOKEN"] = runner.load_copilot_model_token()
    environment["COPILOT_HOME"] = str(judge_root / "home")
    raw_output = judge_root / "judgment.raw.txt"
    format_errors = []
    for format_attempt in (1, 2):
        attempt_prompt = prompt
        if format_errors:
            attempt_prompt += (
                "\n\nYour previous response was rejected only because its output format "
                f"was invalid: {format_errors[-1]}. Re-evaluate the same evidence and "
                "return exactly one JSON object with no prose, markdown, or extra fields. "
                "The exact fields are verdict, confidence, matched, missed, "
                "overcorrections, and generalized_skill_defect. matched, missed, and "
                "overcorrections must be arrays of non-empty strings. verdict must be "
                "exactly PASS, FAIL, or UNANSWERABLE. confidence must be exactly LOW, "
                "MEDIUM, or HIGH. generalized_skill_defect must be null or a non-empty "
                "string."
            )
        command = [
            "copilot",
            "-C",
            str(run_root),
            "-p",
            attempt_prompt,
            "--model",
            model,
            "--reasoning-effort",
            "high",
            "--allow-all-tools",
            "--secret-env-vars",
            ",".join(SECRET_ENV_NAMES),
            "--no-custom-instructions",
            "--disable-builtin-mcps",
            "--no-auto-update",
            "--output-format",
            "text",
            "--silent",
            "--log-level",
            "error",
        ]
        execution = runner.run_command(
            command,
            cwd=run_root,
            environment=environment,
            log=raw_output,
            timeout=timeout,
        )
        require(execution.get("exitCode") == 0, f"Judge failed: {model}")
        require(not execution.get("timedOut"), f"Judge timed out: {model}")
        try:
            judgment = parse_judge_output(raw_output.read_text(encoding="utf-8"))
        except ValueError as error:
            if format_attempt == 2:
                raise
            format_errors.append(str(error))
            raw_output.replace(judge_root / "judgment.attempt-1.raw.txt")
            (judge_root / "judgment.attempt-1.error.txt").write_text(
                f"{error}\n", encoding="utf-8"
            )
            continue
        write_json(judge_root / "judgment.json", judgment)
        safe_execution = {
            key: execution[key]
            for key in (
                "argv",
                "cwd",
                "exitCode",
                "timedOut",
                "elapsedSeconds",
                "log",
                "logSha256",
            )
            if key in execution
        }
        return {
            **safe_execution,
            "judgment": judgment,
            "formatAttempts": format_attempt,
            "priorFormatErrors": format_errors,
        }
    raise AssertionError("unreachable")


def materialize_candidate(runner, package_root: Path, case_id: str, candidate_root: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(Path(runner.__file__).resolve().parent / "materialize-candidate.py"),
            str(package_root),
            case_id,
            str(candidate_root),
        ],
        check=True,
    )


def prepare_case_python_dependencies(
    dependency_sources: dict[str, Path],
    run_root: Path,
    case: dict,
    case_root: Path,
) -> list[Path]:
    if not dependency_sources:
        return []
    return prepare_python_dependencies(
        dependency_sources,
        run_root,
        scaffold_python_distributions(case, case_root),
    )


def apply_scaffold(runner, case: dict, case_root: Path, candidate_root: Path) -> None:
    scaffold = case["grading"].get("scaffold")
    if scaffold is None:
        return
    archive = case_root / scaffold["path"]
    require(runner.sha256(archive) == scaffold["sha256"], "Grading scaffold digest mismatch")
    with tarfile.open(archive, "r:gz") as stream:
        runner.extract_archive_with_modes(stream, candidate_root / "workspaces")


def prepare_container_grading_tree(
    runner,
    case: dict,
    case_root: Path,
    candidate_root: Path,
) -> None:
    runner.detach_cache_symlinks(candidate_root)
    make_container_workspace_writable(candidate_root)
    apply_scaffold(runner, case, case_root, candidate_root)
    make_container_workspace_roots_writable(candidate_root)


def case_root_for(runner, package_root: Path, case_id: str) -> tuple[dict, Path, dict]:
    return runner.load_case(package_root, case_id)


def run_hosted(
    package_root: Path,
    attempt_id: str,
    run_root: Path,
    supplied_identity: dict,
) -> dict:
    package_root = package_root.resolve()
    run_root = run_root.resolve()
    require(platform.system() == "Linux", "Hosted stage requires Linux")
    require(normalize_machine() == "arm64", "Hosted stage requires arm64")
    require(not run_root.exists(), "Refusing to overwrite attempt")
    require(
        os.environ.get("COPILOT_EVAL_MODEL_TOKEN"),
        "COPILOT_EVAL_MODEL_TOKEN is required",
    )
    package, attempt, indexed_case = select_attempt(package_root, attempt_id, supplied_identity)
    runner = load_runner(package_root)
    loaded_package, case_root, case = case_root_for(
        runner, package_root, attempt["caseId"]
    )
    require(loaded_package == package and case == indexed_case, "Sealed runner case view mismatch")
    require(
        case["runtime"]["platform"]["architecture"] == "arm64",
        "Hosted stage only supports sealed arm64 cases",
    )
    target_os = case["runtime"]["platform"]["os"]
    require(target_os == "linux", "Direct hosted execution is limited to Linux-native cases")
    route = "full-linux"

    run_root.mkdir(parents=True)
    try:
        candidate_root = run_root / "candidate"
        materialize_candidate(runner, package_root, attempt["caseId"], candidate_root)
        baselines = runner.baseline_commits(candidate_root)
        baseline_trees = {
            name: git_tree(candidate_root / "workspaces" / name, commit)
            for name, commit in baselines.items()
        }
        runner.write_json(run_root / "dependencies.json", [])
        candidate = run_candidate_with_public_github(
            runner,
            package_root=package_root,
            package=package,
            case=case,
            candidate_root=candidate_root,
            treatment_id=attempt["treatmentId"],
            run_root=run_root,
            timeout=attempt["candidateTimeoutSeconds"],
        )
        runner.write_json(run_root / "candidate-receipt.json", candidate)
        sources = runner.capture_candidate(
            candidate_root, baselines, run_root / "candidate-source"
        )
        for source in sources:
            source["baselineTree"] = baseline_trees[source["workspace"]]
        grading_git_identity = synchronize_grading_git_identity(candidate_root, sources)
        apply_scaffold(runner, case, case_root, candidate_root)
        product = runner.run_product(case, case_root, candidate_root, run_root)
        if case["grading"]["execution"] == "container":
            prepare_container_grading_tree(
                runner, case, case_root, candidate_root
            )
        deterministic_case, setup_adaptations = adapt_hosted_container_case(case)
        deterministic = runner.run_deterministic(
            deterministic_case, case_root, candidate_root, run_root, baselines
        )
        deterministic["hostedSetupAdaptations"] = setup_adaptations

        judges = []
        authority = runner.read_json(case_root / "hidden/authority/case.json")
        for model in authority["judge"]["models"]:
            judges.append(
                {
                    "model": model,
                    **secure_run_judge(
                        runner,
                        case_root=case_root,
                        candidate_root=candidate_root,
                        run_root=run_root,
                        model=model,
                        timeout=1800,
                    ),
                }
            )
        receipt = {
            "schemaVersion": 1,
            **attempt_identity(attempt),
            "route": route,
            "gradingRoute": "hosted-final",
            "packageArchiveSha256": PACKAGE_ARCHIVE_SHA256,
            "packageManifestSha256": runner.sha256(
                package_root / "package-manifest.json"
            ),
            "candidate": candidate,
            "sources": sources,
            "gradingGitIdentity": grading_git_identity,
            "hostedDeterministic": deterministic,
            "product": product,
            "judges": judges,
            "terminal": True,
            "status": (
                "PASS"
                if candidate.get("exitCode", 0) == 0
                and deterministic["targetPassed"]
                and deterministic["regressionPassed"]
                and product.get("passed", False)
                else "FAIL"
            ),
        }
        runner.write_json(run_root / "hosted-stage-receipt.json", receipt)
        final = {
            "schemaVersion": 1,
            "caseId": attempt["caseId"],
            "caseRevision": attempt["caseRevision"],
            "treatmentId": attempt["treatmentId"],
            "repetition": attempt["repetition"],
            "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
            "candidate": candidate,
            "sources": sources,
            "gradingGitIdentity": grading_git_identity,
            "deterministic": deterministic,
            "product": product,
            "judges": judges,
            "status": receipt["status"],
        }
        runner.write_json(run_root / "attempt-receipt.json", final)
        return receipt
    except BaseException as error:
        write_json(
            run_root / "hosted-stage-error.json",
            {
                "schemaVersion": 1,
                **attempt_identity(attempt),
                "errorType": type(error).__name__,
                "message": str(error),
                "resumableBoundary": getattr(error, "resumable_boundary", None),
                "recordedAtEpoch": time.time(),
            },
        )
        raise


def run_macos_candidate_stage(
    package_root: Path,
    attempt_id: str,
    run_root: Path,
    supplied_identity: dict,
    dependency_sources: list[str],
    candidate_package_archive_sha256: str,
) -> dict:
    package_root = package_root.resolve()
    run_root = run_root.resolve()
    require(platform.system() == "Darwin", "macOS stage requires Darwin")
    require(normalize_machine() == "arm64", "macOS stage requires arm64")
    require(not run_root.exists(), "Refusing to overwrite attempt")
    require(
        os.environ.get("COPILOT_EVAL_MODEL_TOKEN"),
        "COPILOT_EVAL_MODEL_TOKEN is required",
    )
    package, attempt, indexed_case = select_attempt(package_root, attempt_id, supplied_identity)
    runner = load_runner(package_root)
    loaded_package, case_root, case = case_root_for(runner, package_root, attempt["caseId"])
    require(loaded_package == package and case == indexed_case, "Sealed runner case view mismatch")
    require(case["runtime"]["platform"]["os"] == "macos", "Attempt is not macOS-targeted")
    require(case["runtime"]["platform"]["architecture"] == "arm64", "Attempt is not arm64")
    require(
        candidate_package_archive_sha256 == PACKAGE_ARCHIVE_SHA256
        or not dependency_sources,
        "Split candidate stages do not support external dependency archives",
    )

    run_root.mkdir(parents=True)
    try:
        candidate_root = run_root / "candidate"
        materialize_candidate(runner, package_root, attempt["caseId"], candidate_root)
        baselines = runner.baseline_commits(candidate_root)
        baseline_trees = {
            name: git_tree(candidate_root / "workspaces" / name, commit)
            for name, commit in baselines.items()
        }
        dependencies = parse_dependency_sources(dependency_sources)
        runtime_dependencies, runtime_dependency_receipt = (
            prepare_writable_dependency_sources(dependencies, run_root)
        )
        dependency_receipt = runner.link_dependencies(
            candidate_root, runtime_dependencies
        )
        runner.write_json(run_root / "dependencies.json", dependency_receipt)
        runner.write_json(run_root / "dependency-runtime.json", runtime_dependency_receipt)
        python_paths = prepare_case_python_dependencies(
            dependencies,
            run_root,
            case,
            case_root,
        )
        with pythonpath_environment(python_paths):
            candidate = run_candidate_with_public_github(
                runner,
                before_copilot=(
                    lambda: remove_sealed_tree(package_root)
                    if candidate_package_archive_sha256 != PACKAGE_ARCHIVE_SHA256
                    else None
                ),
                package_root=package_root,
                package=package,
                case=case,
                candidate_root=candidate_root,
                treatment_id=attempt["treatmentId"],
                run_root=run_root,
                timeout=attempt["candidateTimeoutSeconds"],
            )
        runner.write_json(run_root / "candidate-receipt.json", candidate)
        sources = runner.capture_candidate(
            candidate_root, baselines, run_root / "candidate-source"
        )
        for source in sources:
            source["baselineTree"] = baseline_trees[source["workspace"]]
        grading_git_identity = synchronize_grading_git_identity(candidate_root, sources)
        verify_dependency_sources_unchanged(runtime_dependency_receipt)
        runner.write_json(
            run_root / "dependency-runtime.json",
            runtime_dependency_receipt,
        )
        receipt = {
            "schemaVersion": 2,
            **attempt_identity(attempt),
            "route": "macos-candidate-stage",
            "candidatePackageArchiveSha256": candidate_package_archive_sha256,
            "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
            "candidate": candidate,
            "sources": sources,
            "gradingGitIdentity": grading_git_identity,
            "runtimeDependencies": {
                workspace: str(path)
                for workspace, path in sorted(runtime_dependencies.items())
            },
            "pythonPaths": [str(path) for path in python_paths],
            "deterministicExecution": case["grading"]["execution"],
            "candidateRerunRequired": False,
            "terminal": False,
            "status": "PENDING_MACOS_PRODUCT",
        }
        runner.write_json(run_root / "macos-candidate-stage-receipt.json", receipt)
        return receipt
    except BaseException as error:
        write_json(
            run_root / "macos-stage-error.json",
            {
                "schemaVersion": 1,
                **attempt_identity(attempt),
                "errorType": type(error).__name__,
                "message": str(error),
                "recordedAtEpoch": time.time(),
            },
        )
        raise


def run_macos_product_stage(
    package_root: Path,
    attempt_id: str,
    run_root: Path,
    supplied_identity: dict,
) -> dict:
    package_root = package_root.resolve()
    run_root = run_root.resolve()
    require(platform.system() == "Darwin", "macOS stage requires Darwin")
    require(normalize_machine() == "arm64", "macOS stage requires arm64")
    require(run_root.is_dir(), "Candidate stage is missing")
    package, attempt, indexed_case = select_attempt(
        package_root, attempt_id, supplied_identity
    )
    runner = load_runner(package_root)
    loaded_package, case_root, case = case_root_for(
        runner, package_root, attempt["caseId"]
    )
    require(
        loaded_package == package and case == indexed_case,
        "Sealed runner case view mismatch",
    )
    candidate_stage = read_json(run_root / "macos-candidate-stage-receipt.json")
    require(
        candidate_stage.get("route") == "macos-candidate-stage",
        "Candidate stage receipt is invalid",
    )
    require(
        {key: candidate_stage.get(key) for key in IDENTITY_KEYS}
        == attempt_identity(attempt),
        "Candidate stage attempt identity mismatch",
    )
    require(
        candidate_stage.get("packageManifestSha256") == PACKAGE_MANIFEST_SHA256,
        "Candidate stage package manifest mismatch",
    )
    require(
        candidate_stage.get("candidatePackageArchiveSha256")
        == CANDIDATE_PACKAGE_ARCHIVE_SHA256,
        "Candidate stage package archive mismatch",
    )
    candidate = candidate_stage["candidate"]
    require(
        candidate.get("boundaryAudit", {}).get("passed") is True,
        "Candidate crossed the hidden package boundary",
    )
    candidate_root = run_root / "candidate"
    if candidate_root.exists():
        verify_candidate_trees(candidate_root, candidate_stage["sources"])
        baselines = runner.baseline_commits(candidate_root)
    else:
        candidate_root, baselines, _ = restore_candidate_sources(
            runner, package_root, attempt, run_root, candidate_stage
        )
    runtime_dependencies = {}
    for workspace, value in candidate_stage.get("runtimeDependencies", {}).items():
        safe_name(workspace, "dependency workspace")
        path = Path(value).resolve()
        require(path.is_dir(), f"Dependency runtime is missing: {workspace}")
        runtime_dependencies[workspace] = path
    python_paths = [Path(value).resolve() for value in candidate_stage.get("pythonPaths", [])]
    require(
        all(path.is_dir() for path in python_paths),
        "Python dependency runtime is missing",
    )
    if candidate_stage["candidatePackageArchiveSha256"] != PACKAGE_ARCHIVE_SHA256:
        require(
            not runtime_dependencies and not python_paths,
            "Split candidate stage unexpectedly retained external dependencies",
        )
    apply_scaffold(runner, case, case_root, candidate_root)
    cargo_fetch_workspace = None
    if (
        list((candidate_root / "workspaces").glob("*/.cargo-git"))
        and not (Path.home() / ".cargo/registry").is_dir()
    ):
        trusted_root = run_root / "dependency-runtime/trusted-candidate"
        materialize_candidate(runner, package_root, attempt["caseId"], trusted_root)
        apply_scaffold(runner, case, case_root, trusted_root)
        trusted_workspaces = [
            path.parent
            for path in (trusted_root / "workspaces").glob("*/.cargo-git")
            if path.is_dir()
        ]
        require(
            len(trusted_workspaces) == 1,
            "Trusted Cargo dependency workspace is ambiguous",
        )
        cargo_fetch_workspace = trusted_workspaces[0]
    with pythonpath_environment(python_paths):
        with dependency_environment(
            runtime_dependencies,
            candidate_root,
            run_root,
            cargo_fetch_workspace,
        ):
            product = runner.run_product(case, case_root, candidate_root, run_root)
            if case["grading"]["execution"] == "container":
                prepare_container_grading_tree(runner, case, case_root, candidate_root)
            host_deterministic = {
                "skipped": True,
                "reason": "container deterministic grading is assigned to Linux finalization",
            }
            if case["grading"]["execution"] == "host":
                host_deterministic = runner.run_deterministic(
                    case, case_root, candidate_root, run_root, baselines
                )
                (run_root / "deterministic").rename(run_root / "host-deterministic")
    verify_dependency_sources_unchanged(
        read_json_list(run_root / "dependency-runtime.json")
    )
    receipt = {
        "schemaVersion": 2,
        **attempt_identity(attempt),
        "route": "macos-native-stage",
        "candidatePackageArchiveSha256": candidate_stage[
            "candidatePackageArchiveSha256"
        ],
        "packageArchiveSha256": PACKAGE_ARCHIVE_SHA256,
        "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
        "candidate": candidate,
        "sources": candidate_stage["sources"],
        "gradingGitIdentity": candidate_stage["gradingGitIdentity"],
        "product": product,
        "hostDeterministic": host_deterministic,
        "deterministicExecution": case["grading"]["execution"],
        "candidateRerunRequired": False,
        "terminal": False,
        "status": "PENDING_LINUX_FINALIZATION",
    }
    runner.write_json(run_root / "macos-stage-receipt.json", receipt)
    return receipt


def run_macos_stage(
    package_root: Path,
    attempt_id: str,
    run_root: Path,
    supplied_identity: dict,
    dependency_sources: list[str],
) -> dict:
    candidate = run_macos_candidate_stage(
        package_root,
        attempt_id,
        run_root,
        supplied_identity,
        dependency_sources,
        PACKAGE_ARCHIVE_SHA256,
    )
    require(candidate["packageManifestSha256"] == PACKAGE_MANIFEST_SHA256, "Package changed")
    return run_macos_product_stage(
        package_root,
        attempt_id,
        run_root,
        supplied_identity,
    )


def normalized_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def distribution_record(value: str) -> tuple[str, str]:
    require(value.endswith(".dist-info"), f"Invalid distribution metadata directory: {value}")
    parts = value[:-10].rsplit("-", 1)
    require(len(parts) == 2 and all(parts), f"Invalid distribution metadata directory: {value}")
    name, version = parts
    return normalized_distribution(name), version


def exact_requirements(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        require(separator and name and version, f"Requirement is not exactly pinned: {line}")
        normalized = normalized_distribution(name)
        require(normalized not in result, f"Duplicate Python requirement: {normalized}")
        result[normalized] = version
    require(result, "Python requirements lock is empty")
    return result


def scaffold_python_distributions(case: dict, case_root: Path) -> dict[str, str]:
    scaffold = case.get("grading", {}).get("scaffold")
    if scaffold is None:
        return {}
    archive = case_root / scaffold["path"]
    records = {}
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            parts = PurePosixPath(member.name).parts
            if len(parts) != 4 or parts[1:3] != ("vendor", "python"):
                continue
            metadata = parts[3]
            if not metadata.endswith(".dist-info"):
                continue
            name, version = distribution_record(metadata)
            require(
                name not in records or records[name] == version,
                f"Conflicting scaffold Python distribution: {name}",
            )
            records[name] = version
    return records


def prepare_python_dependencies(
    dependency_sources: dict[str, Path],
    run_root: Path,
    expected_distributions: dict[str, str],
) -> list[Path]:
    targets = []
    receipts = []
    for workspace, source in sorted(dependency_sources.items()):
        requirements = source / "requirements.lock.txt"
        wheels = source / "wheels"
        if not requirements.exists() and not wheels.exists():
            continue
        require(requirements.is_file(), f"{workspace}: Python requirements lock is missing")
        require(wheels.is_dir(), f"{workspace}: Python wheelhouse is missing")
        locked_distributions = exact_requirements(requirements)
        require(
            locked_distributions == expected_distributions,
            f"{workspace}: Python dependency versions differ from the sealed scaffold",
        )
        target = run_root / "dependency-runtime" / workspace / "python"
        target.mkdir(parents=True)
        log = run_root / "dependency-logs" / f"{workspace}-pip-install.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            "--find-links",
            str(wheels),
            "--requirement",
            str(requirements),
            "--target",
            str(target),
        ]
        with log.open("wb") as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
        require(completed.returncode == 0, f"{workspace}: offline Python dependency install failed")
        installed_distributions = dict(
            distribution_record(path.name)
            for path in target.glob("*.dist-info")
            if path.is_dir()
        )
        require(
            installed_distributions == expected_distributions,
            f"{workspace}: installed Python dependencies differ from the sealed scaffold",
        )
        targets.append(target)
        receipts.append(
            {
                "workspace": workspace,
                "requirementsSha256": sha256(requirements),
                "distributions": installed_distributions,
                "target": str(target),
                "python": sys.version,
                "log": str(log.relative_to(run_root)),
                "logSha256": sha256(log),
            }
        )
    write_json(run_root / "python-dependencies.json", receipts)
    return targets


def validate_product_evidence(run_root: Path, stage: dict) -> None:
    product_root = run_root / "product"
    receipt_path = product_root / "receipt.json"
    require(receipt_path.is_file(), "macOS product receipt is missing")
    receipt = read_json(receipt_path)
    require(receipt == stage.get("product"), "macOS product receipt differs from stage identity")
    for record in receipt.get("evidenceFiles", []):
        relative = PurePosixPath(record.get("path", ""))
        require(
            relative.parts and not relative.is_absolute() and ".." not in relative.parts,
            "Unsafe product evidence path",
        )
        path = product_root / relative
        require(path.is_file(), f"Product evidence is missing: {relative}")
        require(sha256(path) == record.get("sha256"), f"Product evidence digest mismatch: {relative}")


def validate_stage_dispatch(
    evidence_path: Path,
    attempt: dict,
    source_run_id: str | None = None,
    source_sha: str | None = None,
) -> dict:
    dispatch = read_json(evidence_path)
    require(dispatch.get("schemaVersion") == 1, "Unsupported stage dispatch evidence")
    dispatched_attempt = dispatch.get("attempt")
    require(isinstance(dispatched_attempt, dict), "Stage dispatch attempt is missing")
    require(
        {key: dispatched_attempt.get(key) for key in IDENTITY_KEYS}
        == attempt_identity(attempt),
        "Stage dispatch attempt identity mismatch",
    )
    controls = dispatch.get("controls", {})
    expected_controls = {
        "PACKAGE_RELEASE": os.environ.get("PACKAGE_RELEASE", ""),
        "PACKAGE_ASSET": os.environ.get("PACKAGE_ASSET", ""),
        "COMPLETION_RELEASE": os.environ.get("COMPLETION_RELEASE", ""),
        "COMPLETION_ASSET": os.environ.get("COMPLETION_ASSET", ""),
        "COMPLETION_SHA256": os.environ.get("COMPLETION_SHA256", ""),
        "CANDIDATE_PACKAGE_RELEASE": os.environ.get("CANDIDATE_PACKAGE_RELEASE", ""),
        "CANDIDATE_PACKAGE_ASSET": os.environ.get("CANDIDATE_PACKAGE_ASSET", ""),
        "CANDIDATE_PACKAGE_SHA256": os.environ.get("CANDIDATE_PACKAGE_SHA256", ""),
    }
    require(
        all(controls.get(key, "") == value for key, value in expected_controls.items()),
        "Stage dispatch controls mismatch",
    )
    github = dispatch.get("github", {})
    require(
        github.get("GITHUB_SERVER_URL") == os.environ.get("GITHUB_SERVER_URL"),
        "Stage artifact came from another GitHub host",
    )
    require(
        github.get("GITHUB_REPOSITORY") == os.environ.get("GITHUB_REPOSITORY"),
        "Stage artifact came from another repository",
    )
    current_run_id = os.environ.get("GITHUB_RUN_ID")
    current_sha = os.environ.get("GITHUB_SHA")
    current_workflow_sha = os.environ.get("GITHUB_WORKFLOW_SHA")
    expected_run_id = source_run_id or current_run_id
    expected_sha = source_sha or current_sha
    expected_workflow_sha = source_sha or current_workflow_sha
    require(bool(source_run_id) == bool(source_sha),
            "Stage source run and revision must be supplied together")
    require(
        isinstance(expected_run_id, str) and expected_run_id.isdigit(),
        "Invalid stage source run",
    )
    require(
        isinstance(expected_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", expected_sha) is not None,
        "Invalid stage source revision",
    )
    require(github.get("GITHUB_RUN_ID") == expected_run_id,
            "Stage artifact belongs to another workflow run")
    require(github.get("GITHUB_SHA") == expected_sha,
            "Stage artifact belongs to another source revision")
    require(github.get("GITHUB_WORKFLOW_SHA") == expected_workflow_sha,
            "Stage artifact belongs to another workflow revision")
    require(github.get("GITHUB_RUN_ATTEMPT") == "1", "Stage artifact is not first-outcome lineage")
    workflow_path = Path(
        os.environ.get(
            "DISTRIBUTED_EVAL_WORKFLOW_PATH",
            ".github/workflows/distributed-campaign.yml",
        )
    ).resolve()
    for name, current in (
        ("workflow.yml", workflow_path),
        ("distributed_campaign.py", Path(__file__).resolve()),
    ):
        retained = evidence_path.parent / name
        require(retained.is_file(), f"Stage carrier file is missing: {name}")
        if expected_run_id == current_run_id:
            require(sha256(retained) == sha256(current), f"Stage carrier file changed: {name}")
    return dispatch


def finalize_linux(
    package_root: Path,
    attempt_id: str,
    run_root: Path,
    dispatch_evidence: Path,
    supplied_identity: dict,
    source_run_id: str | None = None,
    source_sha: str | None = None,
) -> dict:
    package_root = package_root.resolve()
    run_root = run_root.resolve()
    require(platform.system() == "Linux", "Linux finalization requires Linux")
    require(normalize_machine() == "arm64", "Linux finalization requires arm64")
    require(
        os.environ.get("COPILOT_EVAL_MODEL_TOKEN"),
        "COPILOT_EVAL_MODEL_TOKEN is required",
    )
    package, attempt, indexed_case = select_attempt(package_root, attempt_id, supplied_identity)
    stage = read_json(run_root / "macos-stage-receipt.json")
    require(stage.get("route") == "macos-native-stage", "Artifact is not a macOS stage")
    require({key: stage.get(key) for key in IDENTITY_KEYS} == attempt_identity(attempt),
            "macOS stage attempt identity mismatch")
    require(stage.get("packageArchiveSha256") == PACKAGE_ARCHIVE_SHA256
            and stage.get("packageManifestSha256") == PACKAGE_MANIFEST_SHA256,
            "macOS stage package identity mismatch")
    require(
        stage.get("candidatePackageArchiveSha256")
        == CANDIDATE_PACKAGE_ARCHIVE_SHA256,
        "macOS stage candidate package identity mismatch",
    )
    require(stage.get("candidateRerunRequired") is False, "Stage requests a candidate rerun")
    validate_stage_dispatch(dispatch_evidence, attempt, source_run_id, source_sha)
    validate_product_evidence(run_root, stage)
    runner = load_runner(package_root)
    loaded_package, case_root, case = case_root_for(runner, package_root, attempt["caseId"])
    require(loaded_package == package and case == indexed_case, "Sealed runner case view mismatch")
    candidate_root, baselines, reconstruction = restore_candidate_sources(
        runner, package_root, attempt, run_root, stage
    )
    if case["grading"]["execution"] == "container":
        prepare_container_grading_tree(runner, case, case_root, candidate_root)
        deterministic = runner.run_deterministic(
            case, case_root, candidate_root, run_root, baselines
        )
    else:
        apply_scaffold(runner, case, case_root, candidate_root)
        require(case["grading"]["execution"] == "host", "Unsupported deterministic execution")
        host_root = run_root / "host-deterministic"
        require(host_root.is_dir(), "macOS host deterministic evidence is missing")
        deterministic = read_json(host_root / "receipt.json")
        require(deterministic == stage.get("hostDeterministic"),
                "macOS host deterministic receipt mismatch")
        validate_hosted_deterministic_directory(host_root, deterministic)
    judges = []
    authority = runner.read_json(case_root / "hidden/authority/case.json")
    for model in authority["judge"]["models"]:
        judges.append(
            {
                "model": model,
                **secure_run_judge(
                    runner,
                    case_root=case_root,
                    candidate_root=candidate_root,
                    run_root=run_root,
                    model=model,
                    timeout=1800,
                ),
            }
        )
    candidate = stage["candidate"]
    require(
        candidate.get("boundaryAudit", {}).get("passed") is True,
        "Candidate crossed the hidden package boundary",
    )
    product = stage["product"]
    receipt = {
        "schemaVersion": 1,
        "caseId": attempt["caseId"],
        "caseRevision": attempt["caseRevision"],
        "treatmentId": attempt["treatmentId"],
        "repetition": attempt["repetition"],
        "candidatePackageArchiveSha256": stage["candidatePackageArchiveSha256"],
        "packageArchiveSha256": stage["packageArchiveSha256"],
        "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
        "candidate": candidate,
        "sources": stage["sources"],
        "gradingGitIdentity": stage.get("gradingGitIdentity", []),
        "candidateReconstruction": reconstruction,
        "deterministic": deterministic,
        "product": product,
        "judges": judges,
        "candidateRerun": False,
        "status": (
            "PASS"
            if candidate.get("exitCode", 0) == 0
            and deterministic["targetPassed"]
            and deterministic["regressionPassed"]
            and product["passed"]
            else "FAIL"
        ),
    }
    runner.write_json(run_root / "attempt-receipt.json", receipt)
    return receipt


def restore_candidate_sources(
    runner,
    package_root: Path,
    attempt: dict,
    run_root: Path,
    stage: dict | None = None,
) -> tuple[Path, dict, list[dict]]:
    candidate_root = run_root / "candidate"
    require(not candidate_root.exists(), "Candidate reconstruction destination exists")
    materialize_candidate(runner, package_root, attempt["caseId"], candidate_root)
    baselines = runner.baseline_commits(candidate_root)
    if stage is None:
        stage = read_json(run_root / "hosted-stage-receipt.json")
    records = stage.get("sources")
    require(isinstance(records, list) and records, "Hosted source records are missing")
    seen = set()
    reconstruction = []
    for record in records:
        name = safe_name(record.get("workspace"), "source workspace")
        require(name not in seen and name in baselines, f"Unexpected source workspace: {name}")
        expected_tree = record.get("baselineTree")
        require(
            isinstance(expected_tree, str)
            and re.fullmatch(r"[0-9a-f]{40,64}", expected_tree) is not None,
            f"Invalid baseline tree: {name}",
        )
        require(
            git_tree(candidate_root / "workspaces" / name, baselines[name]) == expected_tree,
            f"Baseline tree mismatch: {name}",
        )
        patch = run_root / "candidate-source" / record["patch"]
        status = run_root / "candidate-source" / record["status"]
        safe_name(record["patch"], "source patch")
        safe_name(record["status"], "source status")
        require(sha256(patch) == record.get("patchSha256"), f"Patch digest mismatch: {name}")
        require(sha256(status) == record.get("statusSha256"), f"Status digest mismatch: {name}")
        workspace = candidate_root / "workspaces" / name
        apply_candidate_patch(workspace, patch)
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
        tree = subprocess.check_output(["git", "write-tree"], cwd=workspace, text=True).strip()
        require(tree == record.get("resultTree"), f"Candidate result tree mismatch: {name}")
        actual_status = subprocess.check_output(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=workspace,
            text=True,
        )
        original_status = status.read_text()
        reconstruction.append(
            {
                "workspace": name,
                "resultTree": tree,
                "originalStatus": original_status,
                "originalStatusSha256": hashlib.sha256(
                    original_status.encode()
                ).hexdigest(),
                "reconstructedStatus": actual_status,
                "reconstructedStatusSha256": hashlib.sha256(
                    actual_status.encode()
                ).hexdigest(),
                "statusPreserved": actual_status == original_status,
            }
        )
        seen.add(name)
    require(seen == set(baselines), "Hosted source records do not cover every workspace")
    write_json(
        run_root / "candidate-reconstruction.json",
        {"schemaVersion": 1, "sources": reconstruction},
    )
    return candidate_root, baselines, reconstruction


def recover_retained_candidate_sources(
    runner,
    package_root: Path,
    case_id: str,
    run_root: Path,
) -> tuple[Path, dict, list[dict], list[dict]]:
    candidate_root = run_root / "candidate"
    require(not candidate_root.exists(), "Retained artifact unexpectedly includes candidate tree")
    materialize_candidate(runner, package_root, case_id, candidate_root)
    baselines = runner.baseline_commits(candidate_root)
    source_root = run_root / "candidate-source"
    expected_files = {
        filename
        for name in baselines
        for filename in (f"{name}.patch", f"{name}.status.txt")
    }
    actual_files = {path.name for path in source_root.iterdir() if path.is_file()}
    require(actual_files == expected_files, "Retained candidate source file set mismatch")

    sources = []
    reconstruction = []
    for name, baseline in sorted(baselines.items()):
        workspace = candidate_root / "workspaces" / name
        patch = source_root / f"{name}.patch"
        status = source_root / f"{name}.status.txt"
        baseline_tree = git_tree(workspace, baseline)
        apply_candidate_patch(workspace, patch)
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
        result_tree = subprocess.check_output(
            ["git", "write-tree"], cwd=workspace, text=True
        ).strip()
        actual_status = subprocess.check_output(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=workspace,
            text=True,
        )
        original_status = status.read_text()
        sources.append(
            {
                "workspace": name,
                "baselineCommit": baseline,
                "baselineTree": baseline_tree,
                "resultTree": result_tree,
                "patch": patch.name,
                "patchSha256": sha256(patch),
                "status": status.name,
                "statusSha256": sha256(status),
            }
        )
        reconstruction.append(
            {
                "workspace": name,
                "resultTree": result_tree,
                "originalStatus": original_status,
                "originalStatusSha256": hashlib.sha256(
                    original_status.encode()
                ).hexdigest(),
                "reconstructedStatus": actual_status,
                "reconstructedStatusSha256": hashlib.sha256(
                    actual_status.encode()
                ).hexdigest(),
                "statusPreserved": actual_status == original_status,
            }
        )
    write_json(
        run_root / "candidate-reconstruction.json",
        {"schemaVersion": 1, "sources": reconstruction},
    )
    return candidate_root, baselines, sources, reconstruction


def validate_linux_resume_plan(source_plan: Path, attempt: dict) -> dict:
    plan = read_json(source_plan)
    require(plan.get("schemaVersion") == 1, "Unsupported source plan schema")
    require(plan.get("campaignId") == CAMPAIGN_ID, "Source plan campaign mismatch")
    require(
        plan.get("packageArchiveSha256") == PACKAGE_ARCHIVE_SHA256,
        "Source plan package archive mismatch",
    )
    require(
        plan.get("packageManifestSha256") == PACKAGE_MANIFEST_SHA256,
        "Source plan package manifest mismatch",
    )
    require(plan.get("remainingCount") == 1, "Source plan must contain one attempt")
    require(plan.get("macosCount") == 0, "Source plan unexpectedly contains macOS work")
    require(plan.get("linuxCount") == 1, "Source plan must contain one Linux attempt")
    include = plan.get("linuxMatrix", {}).get("include", [])
    require(isinstance(include, list) and len(include) == 1, "Invalid source Linux matrix")
    source_attempt = include[0]
    require(
        {key: source_attempt.get(key) for key in IDENTITY_KEYS}
        == attempt_identity(attempt),
        "Source plan attempt identity mismatch",
    )
    require(source_attempt.get("route") == "full-linux", "Source plan route mismatch")
    return plan


def validate_linux_resume_failure(error_path: Path, attempt: dict) -> dict:
    error = read_json(error_path)
    require(error.get("schemaVersion") == 1, "Unsupported source failure schema")
    require(
        {key: error.get(key) for key in IDENTITY_KEYS} == attempt_identity(attempt),
        "Source failure attempt identity mismatch",
    )
    require(
        error.get("resumableBoundary") == "candidate-setup",
        "Source attempt did not fail at the resumable infrastructure boundary",
    )
    return error


def resume_hosted_linux(
    package_root: Path,
    attempt_id: str,
    run_root: Path,
    source_plan: Path,
    source_archive_evidence: Path,
    supplied_identity: dict,
    source_run_id: str,
    source_sha: str,
) -> dict:
    package_root = package_root.resolve()
    run_root = run_root.resolve()
    require(platform.system() == "Linux", "Hosted resume requires Linux")
    require(normalize_machine() == "arm64", "Hosted resume requires arm64")
    require(run_root.is_dir(), "Retained Linux attempt is missing")
    require(os.environ.get("COPILOT_EVAL_MODEL_TOKEN"), "COPILOT_EVAL_MODEL_TOKEN is required")
    require(source_run_id.isdigit(), "Invalid source run ID")
    require(
        re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None,
        "Invalid source workflow Git SHA",
    )
    package, attempt, indexed_case = select_attempt(package_root, attempt_id, supplied_identity)
    runner = load_runner(package_root)
    loaded_package, case_root, case = case_root_for(
        runner, package_root, attempt["caseId"]
    )
    require(loaded_package == package and case == indexed_case, "Sealed runner case view mismatch")
    require(case["runtime"]["platform"]["os"] == "linux", "Resume requires a Linux-native case")
    validate_linux_resume_plan(source_plan, attempt)
    source_archive = read_json(source_archive_evidence)
    check_sha256(source_archive.get("sha256", ""), "source retained archive")

    candidate = runner.read_json(run_root / "candidate-receipt.json")
    require(candidate.get("exitCode") == 0, "Source candidate did not complete successfully")
    product = runner.read_json(run_root / "product/receipt.json")
    require(product.get("passed") is True, "Source product proof did not pass")
    validate_product_evidence(run_root, {"product": product})
    require(not (run_root / "attempt-receipt.json").exists(), "Source attempt is already complete")
    validate_linux_resume_failure(
        run_root / "hosted-stage-error.json",
        attempt,
    )

    candidate_root, baselines, sources, reconstruction = (
        recover_retained_candidate_sources(
            runner, package_root, attempt["caseId"], run_root
        )
    )
    apply_scaffold(runner, case, case_root, candidate_root)
    if case["grading"]["execution"] == "container":
        runner.detach_cache_symlinks(candidate_root)
        make_container_workspace_writable(candidate_root)
    predecessor_deterministic = run_root / "deterministic"
    require(predecessor_deterministic.is_dir(), "Source deterministic evidence is missing")
    predecessor_deterministic.rename(run_root / "deterministic-predecessor")
    deterministic_case, setup_adaptations = adapt_hosted_container_case(case)
    deterministic = runner.run_deterministic(
        deterministic_case, case_root, candidate_root, run_root, baselines
    )
    deterministic["hostedSetupAdaptations"] = setup_adaptations

    judges = []
    authority = runner.read_json(case_root / "hidden/authority/case.json")
    for model in authority["judge"]["models"]:
        judges.append(
            {
                "model": model,
                **secure_run_judge(
                    runner,
                    case_root=case_root,
                    candidate_root=candidate_root,
                    run_root=run_root,
                    model=model,
                    timeout=1800,
                ),
            }
        )
    status = (
        "PASS"
        if deterministic["targetPassed"]
        and deterministic["regressionPassed"]
        and product["passed"]
        else "FAIL"
    )
    lineage = {
        "candidateRerun": False,
        "sourceRunId": source_run_id,
        "sourceSha": source_sha,
        "sourceRetainedArchiveSha256": source_archive["sha256"],
        "candidateReconstruction": reconstruction,
    }
    receipt = {
        "schemaVersion": 1,
        **attempt_identity(attempt),
        "route": "full-linux-resumed",
        "gradingRoute": "hosted-final",
        "packageArchiveSha256": PACKAGE_ARCHIVE_SHA256,
        "packageManifestSha256": runner.sha256(package_root / "package-manifest.json"),
        "candidate": candidate,
        "sources": sources,
        "hostedDeterministic": deterministic,
        "product": product,
        "judges": judges,
        "sourceLineage": lineage,
        "terminal": True,
        "status": status,
    }
    runner.write_json(run_root / "hosted-stage-receipt.json", receipt)
    final = {
        "schemaVersion": 1,
        "caseId": attempt["caseId"],
        "caseRevision": attempt["caseRevision"],
        "treatmentId": attempt["treatmentId"],
        "repetition": attempt["repetition"],
        "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
        "candidate": candidate,
        "sources": sources,
        "deterministic": deterministic,
        "product": product,
        "judges": judges,
        "sourceLineage": lineage,
        "status": status,
    }
    runner.write_json(run_root / "attempt-receipt.json", final)
    return receipt


def validate_hosted_deterministic_directory(evidence: Path, receipt: dict) -> None:
    receipt_path = evidence / "receipt.json"
    require(receipt_path.is_file(), "Hosted deterministic receipt is missing")
    require(
        read_json(receipt_path) == receipt,
        "Hosted deterministic receipt differs from stage identity",
    )
    for result in receipt.get("results", []):
        log_name = result.get("log")
        if log_name is None:
            continue
        safe_name(log_name, "deterministic log")
        log = evidence / log_name
        require(log.is_file(), f"Hosted deterministic log is missing: {log_name}")
        require(
            sha256(log) == result.get("logSha256"),
            f"Hosted deterministic log digest mismatch: {log_name}",
        )


def verify_image_asset(
    manifest_path: Path,
    manifest_sha256: str | None,
    release: str,
    image_id: str,
    asset_name: str,
    archive: Path,
) -> dict:
    _, images = validate_image_manifest(
        manifest_path, expected_file_sha256=manifest_sha256
    )
    require(image_id in images, f"Image is absent from manifest: {image_id}")
    record = images[image_id]
    require(record["release"] == safe_name(release, "image release"), "Image release mismatch")
    require(record["asset"] == safe_name(asset_name, "image asset"), "Image asset name mismatch")
    require(archive.stat().st_size == record["bytes"], "Image asset size mismatch")
    require(sha256(archive) == record["sha256"], "Image asset SHA256 mismatch")
    return record


def freeze_completion(
    package_root: Path,
    ledger_path: Path,
    output: Path,
    excluded_states: set[str],
) -> dict:
    _, _, by_id = load_package(package_root)
    ledger = read_json(ledger_path)
    completed = []
    excluded = []
    for attempt_id, record in sorted(ledger.items()):
        safe_name(attempt_id, "ledger attempt id")
        require(isinstance(record, dict), f"Ledger entry must be an object: {attempt_id}")
        require(record.get("attemptId") == attempt_id, f"Ledger key/id mismatch: {attempt_id}")
        require(attempt_id in by_id, f"Ledger contains unknown attempt: {attempt_id}")
        if "packageManifestSha256" in record:
            require(
                record["packageManifestSha256"] == PACKAGE_MANIFEST_SHA256,
                f"Ledger package identity mismatch: {attempt_id}",
            )
        identity = attempt_identity(by_id[attempt_id])
        require(
            record.get("caseId") == identity["caseId"]
            and record.get("treatmentId") == identity["treatmentId"]
            and record.get("repetition") == identity["repetition"],
            f"Ledger attempt identity mismatch: {attempt_id}",
        )
        state = record.get("state")
        if state == "COMPLETE":
            require(record.get("outcome") in {"PASS", "FAIL"},
                    f"Completed ledger entry lacks terminal outcome: {attempt_id}")
            evidence = record.get("retainedEvidence", {})
            completed.append(
                {
                    **identity,
                    "outcome": record["outcome"],
                    "retainedEvidenceSha256": evidence.get("sha256"),
                }
            )
        elif state in excluded_states:
            excluded.append(
                {
                    **identity,
                    "reason": f"reserved by local matrix in state {state} at dispatch freeze",
                }
            )
    value = {
        "schemaVersion": 1,
        "campaignId": CAMPAIGN_ID,
        "packageArchiveSha256": PACKAGE_ARCHIVE_SHA256,
        "candidatePackageArchiveSha256": CANDIDATE_PACKAGE_ARCHIVE_SHA256,
        "packageManifestSha256": PACKAGE_MANIFEST_SHA256,
        "sourceLedgerSha256": sha256(ledger_path),
        "completedAttempts": completed,
        "excludedAttempts": excluded,
    }
    validate_completion_manifest_from_value(value, by_id)
    write_json(output, value)
    return value


def validate_completion_manifest_from_value(
    value: dict, by_id: dict[str, dict]
) -> set[str]:
    require(value.get("schemaVersion") == 1, "Unsupported completion manifest schema")
    require(value.get("campaignId") == CAMPAIGN_ID, "Completion campaign mismatch")
    require(
        value.get("packageArchiveSha256") == PACKAGE_ARCHIVE_SHA256,
        "Completion package archive identity mismatch",
    )
    require(
        value.get("packageManifestSha256") == PACKAGE_MANIFEST_SHA256,
        "Completion package manifest identity mismatch",
    )
    require(
        value.get("candidatePackageArchiveSha256", value.get("packageArchiveSha256"))
        == CANDIDATE_PACKAGE_ARCHIVE_SHA256,
        "Completion candidate package archive identity mismatch",
    )
    if "sourceLedgerSha256" in value:
        check_sha256(value["sourceLedgerSha256"], "source ledger")
    excluded: set[str] = set()
    for field, completed in (("completedAttempts", True), ("excludedAttempts", False)):
        records = value.get(field)
        require(isinstance(records, list), f"{field} must be a list")
        for record in records:
            require(isinstance(record, dict), f"{field} entry must be an object")
            attempt_id = safe_name(record.get("attemptId"), "completion attempt id")
            require(attempt_id not in excluded, f"Duplicate completion/exclusion: {attempt_id}")
            require(attempt_id in by_id, f"Unknown completion/exclusion attempt: {attempt_id}")
            expected = attempt_identity(by_id[attempt_id])
            actual = {key: record.get(key) for key in IDENTITY_KEYS}
            require(actual == expected, f"Attempt identity mismatch: {attempt_id}")
            if completed:
                require(record.get("outcome") in {"PASS", "FAIL"},
                        f"Completed attempt lacks terminal outcome: {attempt_id}")
                check_sha256(
                    record.get("retainedEvidenceSha256"),
                    f"completed attempt {attempt_id} evidence",
                )
            else:
                require(
                    isinstance(record.get("reason"), str) and record["reason"].strip(),
                    f"Excluded attempt lacks a reason: {attempt_id}",
                )
            excluded.add(attempt_id)
    return excluded


def verify_loaded_image(image_id: str) -> dict:
    output = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}} {{.Architecture}} {{.Os}}", image_id],
        text=True,
    ).strip()
    require(output == f"{image_id} arm64 linux", "Loaded image identity/platform mismatch")
    return {"imageId": image_id, "inspection": output}


def retained_files(run_root: Path, evidence_root: Path) -> list[tuple[Path, str]]:
    records = []
    for root, prefix in ((evidence_root, "evidence"), (run_root, "run-root")):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            parts = relative.parts
            if prefix == "run-root" and (
                (parts and parts[0] in {"candidate", "candidate-home", "dependency-runtime"})
                or (len(parts) >= 3 and parts[0] == "judge" and parts[2] == "home")
            ):
                continue
            require(not path.is_symlink(), f"Refusing to retain symlink: {path}")
            records.append((path, f"{prefix}/{relative.as_posix()}"))
    return records


def create_retained_archive(
    run_root: Path,
    evidence_root: Path,
    output: Path,
) -> dict:
    require(not output.exists(), f"Retention archive exists: {output}")
    files = retained_files(run_root, evidence_root)
    require(files, "No evidence exists to retain")
    manifest = {
        "schemaVersion": 1,
        "files": [
            {"path": archive_name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path, archive_name in files
        ],
    }
    manifest_path = evidence_root / "retention-manifest.json"
    write_json(manifest_path, manifest)
    files = retained_files(run_root, evidence_root)
    with tarfile.open(output, "w:gz") as stream:
        for path, archive_name in files:
            stream.add(path, arcname=archive_name, recursive=False)
    checksum = output.with_name(output.name + ".sha256")
    checksum.write_text(f"{sha256(output)}  {output.name}\n")
    return {"archive": str(output), "sha256": sha256(output), "files": len(files)}


def retained_archive_sha256(archive: Path, checksum_path: Path) -> str:
    require(archive.is_file() and checksum_path.is_file(), "Retained artifact is incomplete")
    fields = checksum_path.read_text().strip().split()
    require(
        len(fields) == 2 and fields[1] == archive.name,
        "Retained artifact checksum record is invalid",
    )
    expected = check_sha256(fields[0], "retained artifact")
    require(sha256(archive) == expected, "Retained artifact SHA256 mismatch")
    return expected


def artifact_name(attempt_id: str, run_id: str, run_attempt: str, kind: str = "final") -> str:
    safe_name(attempt_id, "attempt id")
    require(kind in {"macos", "final", "fallback"}, "Invalid artifact kind")
    require(re.fullmatch(r"[1-9][0-9]*", str(run_id)) is not None, "Invalid run id")
    require(re.fullmatch(r"[1-9][0-9]*", str(run_attempt)) is not None, "Invalid run attempt")
    return f"distributed-eval-{kind}-{attempt_id}-{run_id}-{run_attempt}"


def supplied_identity(args) -> dict:
    return {
        "attemptId": args.attempt_id,
        "caseId": args.case_id,
        "caseRevision": args.case_revision,
        "treatmentId": args.treatment_id,
        "repetition": args.repetition,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-dispatch")
    for name in (
        "package_release",
        "package_asset",
        "completion_release",
        "completion_asset",
    ):
        validate.add_argument(f"--{name.replace('_', '-')}", required=True)
    validate.add_argument("--completion-sha256", required=True)
    validate.add_argument("--max-parallel", type=int, required=True)

    unpack = commands.add_parser("unpack-package")
    unpack.add_argument("--archive", type=Path, required=True)
    unpack.add_argument("--destination", type=Path, required=True)

    plan = commands.add_parser("plan")
    plan.add_argument("--package-root", type=Path, required=True)
    plan.add_argument("--completion", type=Path, required=True)
    plan.add_argument("--completion-sha256", required=True)
    plan.add_argument("--image-manifest", type=Path, required=True)
    plan.add_argument("--dependency-manifest", type=Path, required=True)
    plan.add_argument("--attempt-id")
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--github-output", type=Path)

    freeze = commands.add_parser("freeze-completion")
    freeze.add_argument("--package-root", type=Path, required=True)
    freeze.add_argument("--ledger", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--exclude-state", action="append", default=["RUNNING"])

    verify_image = commands.add_parser("verify-image")
    verify_image.add_argument("--manifest", type=Path, required=True)
    verify_image.add_argument("--manifest-sha256")
    verify_image.add_argument("--release", required=True)
    verify_image.add_argument("--image-id", required=True)
    verify_image.add_argument("--asset", required=True)
    verify_image.add_argument("--archive", type=Path, required=True)

    dependency = commands.add_parser("unpack-dependency")
    dependency.add_argument("--manifest", type=Path, required=True)
    dependency.add_argument("--workspace", required=True)
    dependency.add_argument("--release", required=True)
    dependency.add_argument("--archive", type=Path, required=True)
    dependency.add_argument("--destination", type=Path, required=True)
    dependency.add_argument("--evidence", type=Path, required=True)

    download = commands.add_parser("download-release")
    download.add_argument("--repository", required=True)
    download.add_argument("--release", required=True)
    download.add_argument("--asset", required=True)
    download.add_argument("--destination", type=Path, required=True)
    download.add_argument("--attempts", type=int, default=5)
    download.add_argument("--sha256")

    seal = commands.add_parser("seal-tree")
    seal.add_argument("--root", type=Path, required=True)
    seal.add_argument("--evidence", type=Path, required=True)

    unpack_retained = commands.add_parser("unpack-retained")
    unpack_retained.add_argument("--archive", type=Path, required=True)
    unpack_retained.add_argument("--checksum", type=Path, required=True)
    unpack_retained.add_argument("--destination", type=Path, required=True)

    loaded = commands.add_parser("verify-loaded-image")
    loaded.add_argument("--image-id", required=True)

    hosted = commands.add_parser("run-hosted")
    hosted.add_argument("--package-root", type=Path, required=True)
    hosted.add_argument("--attempt-id", required=True)
    hosted.add_argument("--case-id", required=True)
    hosted.add_argument("--case-revision", required=True)
    hosted.add_argument("--treatment-id", required=True)
    hosted.add_argument("--repetition", type=int, required=True)
    hosted.add_argument("--run-root", type=Path, required=True)

    resume_hosted = commands.add_parser("resume-hosted-linux")
    resume_hosted.add_argument("--package-root", type=Path, required=True)
    resume_hosted.add_argument("--attempt-id", required=True)
    resume_hosted.add_argument("--case-id", required=True)
    resume_hosted.add_argument("--case-revision", required=True)
    resume_hosted.add_argument("--treatment-id", required=True)
    resume_hosted.add_argument("--repetition", type=int, required=True)
    resume_hosted.add_argument("--run-root", type=Path, required=True)
    resume_hosted.add_argument("--source-plan", type=Path, required=True)
    resume_hosted.add_argument("--source-archive-evidence", type=Path, required=True)
    resume_hosted.add_argument("--source-run-id", required=True)
    resume_hosted.add_argument("--source-sha", required=True)

    macos = commands.add_parser("run-macos-stage")
    macos.add_argument("--package-root", type=Path, required=True)
    macos.add_argument("--attempt-id", required=True)
    macos.add_argument("--case-id", required=True)
    macos.add_argument("--case-revision", required=True)
    macos.add_argument("--treatment-id", required=True)
    macos.add_argument("--repetition", type=int, required=True)
    macos.add_argument("--run-root", type=Path, required=True)
    macos.add_argument("--dependency-source", action="append", default=[])

    macos_candidate = commands.add_parser("run-macos-candidate-stage")
    macos_candidate.add_argument("--package-root", type=Path, required=True)
    macos_candidate.add_argument("--attempt-id", required=True)
    macos_candidate.add_argument("--case-id", required=True)
    macos_candidate.add_argument("--case-revision", required=True)
    macos_candidate.add_argument("--treatment-id", required=True)
    macos_candidate.add_argument("--repetition", type=int, required=True)
    macos_candidate.add_argument("--run-root", type=Path, required=True)
    macos_candidate.add_argument("--candidate-package-sha256", required=True)
    macos_candidate.add_argument("--dependency-source", action="append", default=[])

    macos_product = commands.add_parser("run-macos-product-stage")
    macos_product.add_argument("--package-root", type=Path, required=True)
    macos_product.add_argument("--attempt-id", required=True)
    macos_product.add_argument("--case-id", required=True)
    macos_product.add_argument("--case-revision", required=True)
    macos_product.add_argument("--treatment-id", required=True)
    macos_product.add_argument("--repetition", type=int, required=True)
    macos_product.add_argument("--run-root", type=Path, required=True)

    finalize = commands.add_parser("finalize-linux")
    finalize.add_argument("--package-root", type=Path, required=True)
    finalize.add_argument("--attempt-id", required=True)
    finalize.add_argument("--case-id", required=True)
    finalize.add_argument("--case-revision", required=True)
    finalize.add_argument("--treatment-id", required=True)
    finalize.add_argument("--repetition", type=int, required=True)
    finalize.add_argument("--run-root", type=Path, required=True)
    finalize.add_argument("--dispatch-evidence", type=Path, required=True)
    finalize.add_argument("--source-run-id")
    finalize.add_argument("--source-sha")

    retain = commands.add_parser("retain")
    retain.add_argument("--run-root", type=Path, required=True)
    retain.add_argument("--evidence", type=Path, required=True)
    retain.add_argument("--output", type=Path, required=True)

    artifact = commands.add_parser("artifact-name")
    artifact.add_argument("--attempt-id", required=True)
    artifact.add_argument("--run-id", required=True)
    artifact.add_argument("--run-attempt", required=True)
    artifact.add_argument("--kind", choices=("macos", "final", "fallback"), default="final")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "validate-dispatch":
        for field in (
            "package_release",
            "package_asset",
            "completion_release",
            "completion_asset",
        ):
            safe_name(getattr(args, field), field.replace("_", " "))
        check_sha256(args.completion_sha256, "completion manifest")
        require(1 <= args.max_parallel <= 256, "max-parallel must be between 1 and 256")
    elif args.command == "unpack-package":
        identity = safe_extract(args.archive, args.destination, PACKAGE_ARCHIVE_SHA256)
        require(
            sha256(args.destination / "package-manifest.json") == PACKAGE_MANIFEST_SHA256,
            "Package manifest SHA256 mismatch",
        )
        print(json.dumps(identity, sort_keys=True))
    elif args.command == "plan":
        value = build_plan(
            args.package_root,
            args.completion,
            args.image_manifest,
            args.dependency_manifest,
            completion_sha256=args.completion_sha256,
            selected_attempt_id=args.attempt_id,
        )
        write_json(args.output, value)
        if args.github_output:
            with args.github_output.open("a") as stream:
                stream.write(f"matrix={json.dumps(value['matrix'], separators=(',', ':'))}\n")
                stream.write(f"remaining={value['remainingCount']}\n")
                stream.write(f"macos_matrix={json.dumps(value['macosMatrix'], separators=(',', ':'))}\n")
                stream.write(f"macos_count={value['macosCount']}\n")
                stream.write(f"linux_matrix={json.dumps(value['linuxMatrix'], separators=(',', ':'))}\n")
                stream.write(f"linux_count={value['linuxCount']}\n")
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "freeze-completion":
        value = freeze_completion(
            args.package_root,
            args.ledger,
            args.output,
            set(args.exclude_state),
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "verify-image":
        value = verify_image_asset(
            args.manifest,
            args.manifest_sha256,
            args.release,
            args.image_id,
            args.asset,
            args.archive,
        )
        print(json.dumps(value, sort_keys=True))
    elif args.command == "verify-loaded-image":
        print(json.dumps(verify_loaded_image(args.image_id), sort_keys=True))
    elif args.command == "unpack-dependency":
        print(json.dumps(
            unpack_dependency(
                args.manifest,
                args.workspace,
                args.release,
                args.archive,
                args.destination,
                args.evidence,
            ),
            sort_keys=True,
        ))
    elif args.command == "download-release":
        download_release_asset(
            args.repository,
            args.release,
            args.asset,
            args.destination,
            args.attempts,
            args.sha256,
        )
    elif args.command == "seal-tree":
        print(json.dumps(seal_tree(args.root, args.evidence), sort_keys=True))
    elif args.command == "unpack-retained":
        expected = retained_archive_sha256(args.archive, args.checksum)
        print(json.dumps(safe_extract(args.archive, args.destination, expected), sort_keys=True))
    elif args.command == "run-hosted":
        value = run_hosted(
            args.package_root,
            args.attempt_id,
            args.run_root,
            supplied_identity(args),
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "resume-hosted-linux":
        value = resume_hosted_linux(
            args.package_root,
            args.attempt_id,
            args.run_root,
            args.source_plan,
            args.source_archive_evidence,
            supplied_identity(args),
            args.source_run_id,
            args.source_sha,
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "run-macos-stage":
        value = run_macos_stage(
            args.package_root,
            args.attempt_id,
            args.run_root,
            supplied_identity(args),
            args.dependency_source,
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "run-macos-candidate-stage":
        check_sha256(args.candidate_package_sha256, "candidate package archive")
        value = run_macos_candidate_stage(
            args.package_root,
            args.attempt_id,
            args.run_root,
            supplied_identity(args),
            args.dependency_source,
            args.candidate_package_sha256,
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "run-macos-product-stage":
        value = run_macos_product_stage(
            args.package_root,
            args.attempt_id,
            args.run_root,
            supplied_identity(args),
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "finalize-linux":
        value = finalize_linux(
            args.package_root,
            args.attempt_id,
            args.run_root,
            args.dispatch_evidence,
            supplied_identity(args),
            args.source_run_id,
            args.source_sha,
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    elif args.command == "retain":
        print(json.dumps(
            create_retained_archive(args.run_root, args.evidence, args.output),
            sort_keys=True,
        ))
    elif args.command == "artifact-name":
        print(artifact_name(args.attempt_id, args.run_id, args.run_attempt, args.kind))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
