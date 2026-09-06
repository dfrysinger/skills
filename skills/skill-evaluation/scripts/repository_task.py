"""Concrete Docker execution for frozen, editable repository tasks."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import measurement

from skill_eval import (
    copy_packet, digest, frozen_case_path, read_json, resolve_under,
    utc_stamp, verify_case, write_json,
)


IMAGE_RE = re.compile(r"^(?:sha256:[0-9a-f]{64}|[^\s]+@sha256:[0-9a-f]{64})$")
LOCAL_TOOLS = (
    "view,glob,rg,edit,create,apply_patch,bash,read_bash,stop_bash,list_bash,"
    "task,read_agent,write_agent,list_agents,sql"
)


class InfrastructureError(RuntimeError):
    """The executor could not establish or maintain its Docker environment."""


class CandidateStateError(ValueError):
    """Candidate output cannot be represented as an ordinary source patch."""


def scaffold_repository(case_dir: Path) -> None:
    definition = read_json(case_dir / "case.json")
    definition["case_type"] = "repository-task"
    definition["repository_task"] = {
        "snapshot_dir": "repository",
        "source_revision": "replace-source-revision",
        "provenance_file": "judge-reference/provenance.json",
        "image": "replace-with-pinned-image",
        "candidate_setup": [],
        "grading": {
            "setup": [],
            "target": {
                "argv": ["python3", "/grader/target.py"],
                "timeout_seconds": 60,
                "success_output_contains": "TARGET_CHECKS_PASSED",
            },
            "regression": {
                "argv": ["python3", "/grader/regression.py"],
                "timeout_seconds": 60,
                "success_output_contains": "REGRESSION_CHECKS_PASSED",
            },
        },
        "admission": {
            "reference_patch": "judge-reference/reference.patch",
            "base_target_failure": {
                "exit_code": 1,
                "output_contains": "replace-with-intended-failure",
            },
        },
    }
    (case_dir / "repository").mkdir()
    (case_dir / "judge-reference" / "grader").mkdir()
    (case_dir / definition["phases"][0]["prompt_file"]).write_text(
        "Read /evidence and implement the requested change in /workspace/repo.\n"
        "Use local source and evidence, not source-origin answers from the network.\n"
        "Report the change and the checks actually performed.\n", encoding="utf-8",
    )
    write_json(case_dir / "case.json", definition)


def ordinary_files(root: Path, *, skip_git: bool = False,
                   runtime_links: dict[str, str] | None = None) -> list[Path]:
    files = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        if skip_git:
            names[:] = [name for name in names if name != ".git"]
            filenames = [name for name in filenames if name != ".git"]
        for name in [*names, *filenames]:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                if runtime_links is not None and runtime_links.get(relative) == os.readlink(path):
                    continue
                raise ValueError(f"unsupported repository filesystem entry: {path}")
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"unsupported repository filesystem entry: {path}")
            if name == ".git":
                raise ValueError(f"Git metadata is not repository evidence: {path}")
            if stat.S_ISREG(mode):
                files.append(path)
    return sorted(files)


def observe_setup_links(frozen: Path, source: Path) -> list[dict[str, str]]:
    frozen_paths = {
        path.relative_to(frozen / "repository")
        for path in ordinary_files(frozen / "repository")
    }
    links = []
    for directory, names, filenames in os.walk(source, followlinks=False):
        names[:] = [name for name in names if name != ".git"]
        filenames = [name for name in filenames if name != ".git"]
        for name in [*names, *filenames]:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                relative = path.relative_to(source)
                if any(
                    frozen_path == relative or frozen_path.is_relative_to(relative)
                    for frozen_path in frozen_paths
                ):
                    raise ValueError(
                        f"setup-created symlink overlaps frozen source: {relative}"
                    )
                links.append({"path": relative.as_posix(), "target": os.readlink(path)})
            elif not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"unsupported repository filesystem entry: {path}")
    return links


def validate_command(command: dict, *, graded: bool = False) -> None:
    if not isinstance(command, dict):
        raise ValueError("command must be an object")
    argv = command.get("argv")
    timeout = command.get("timeout_seconds")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(value, str) and value and "\0" not in value for value in argv
    ):
        raise ValueError("command argv must be a nonempty string array")
    if type(timeout) is not int or timeout <= 0:
        raise ValueError("command timeout_seconds must be a positive integer")
    if graded and not (
        isinstance(command.get("success_output_contains"), str)
        and command["success_output_contains"].strip()
    ):
        raise ValueError("graded commands require nonempty success_output_contains")


def validate_definition(definition: dict, root: Path, *, frozen: bool = False) -> None:
    phases = definition.get("phases")
    if not isinstance(phases, list) or len(phases) != 1 or not isinstance(phases[0], dict):
        raise ValueError("repository tasks require one non-resumed phase")
    if phases[0].get("resume") or not all(
        isinstance(phases[0].get(field), str) and phases[0][field]
        for field in ("id", "evidence_dir", "prompt_file")
    ):
        raise ValueError("repository tasks require one non-resumed phase")
    if phases[0]["id"] in {"repository", "judge-reference", "prompts"}:
        raise ValueError("repository task phase uses a reserved packet name")
    task = definition.get("repository_task")
    if not isinstance(task, dict) or not all(
        isinstance(task.get(field), str) and task[field]
        for field in ("snapshot_dir", "source_revision", "provenance_file", "image")
    ):
        raise ValueError("repository_task requires snapshot_dir, source_revision, provenance_file and image")
    if not isinstance(task.get("grading"), dict) or not all(
        field in task["grading"] for field in ("setup", "target", "regression")
    ):
        raise ValueError("repository_task grading requires setup, target and regression")
    admission = task.get("admission")
    if not isinstance(admission, dict) or not isinstance(admission.get("reference_patch"), str):
        raise ValueError("repository_task admission requires reference_patch")
    if not isinstance(admission.get("base_target_failure"), dict):
        raise ValueError("repository_task admission requires base_target_failure")
    if "candidate_setup" not in task:
        raise ValueError("repository_task requires candidate_setup")
    if not IMAGE_RE.fullmatch(task.get("image", "")):
        raise ValueError("repository task image must be pinned to sha256")
    revision = task.get("source_revision")
    if not isinstance(revision, str) or not revision or revision.startswith("replace"):
        raise ValueError("repository task needs an immutable source_revision")
    repository = resolve_under(root, "repository" if frozen else task["snapshot_dir"])
    if not repository.is_dir() or not ordinary_files(repository):
        raise ValueError("repository snapshot must contain ordinary source files")
    if not frozen and (repository / "bundle-manifest.json").exists():
        raise ValueError("bundle-manifest.json is reserved for the freezer")
    judge_root = resolve_under(root, "judge-reference" if frozen else definition["judge"]["evidence_dir"])
    candidate_roots = [repository, resolve_under(
        root, phases[0]["id"] if frozen else phases[0]["evidence_dir"])]
    for candidate_root in candidate_roots:
        if candidate_root.is_relative_to(judge_root) or judge_root.is_relative_to(candidate_root):
            raise ValueError("candidate and hidden judge packet directories must not overlap")
    for field in (task["provenance_file"], task["admission"]["reference_patch"]):
        path = resolve_under(root, field)
        if not path.is_relative_to(judge_root) or not path.is_file():
            raise ValueError(f"repository authority must be inside the hidden judge packet: {field}")
    if not (judge_root / "grader").is_dir() or not ordinary_files(judge_root / "grader"):
        raise ValueError("repository task requires hidden grader entrypoints")
    for commands in (task["candidate_setup"], task["grading"]["setup"]):
        if not isinstance(commands, list):
            raise ValueError("setup must be a command array")
        for command in commands:
            validate_command(command)
    for name in ("target", "regression"):
        validate_command(task["grading"][name], graded=True)
    failure = task["admission"]["base_target_failure"]
    if type(failure.get("exit_code")) is not int or failure["exit_code"] <= 0:
        raise ValueError("base target failure requires a positive exit code")
    if not isinstance(failure.get("output_contains"), str) or not failure["output_contains"].strip():
        raise ValueError("base target failure requires nonempty output_contains")


def command_result(command: list[str], log: Path, timeout: int) -> dict:
    started_at = measurement.instant()
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        output, code = completed.stdout, completed.returncode
    except subprocess.TimeoutExpired as error:
        output, code, timed_out = error.output or b"", None, True
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(output)
    result = {
        "command": command, "exit_code": code, "timed_out": timed_out,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "log": log.name, "raw_log_sha256": digest(log),
        "started_at": started_at, "completed_at": measurement.instant(),
    }
    write_json(log.with_suffix(".receipt.json"), result)
    return result


def image_identity(image: str) -> dict:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InfrastructureError("Docker image inspection unavailable") from error
    if result.returncode:
        raise InfrastructureError(f"pinned Docker image unavailable: {image}")
    record = json.loads(result.stdout)[0]
    if image.startswith("sha256:") and record["Id"] != image:
        raise InfrastructureError("resolved image ID differs from pinned image")
    return {"requested": image, "id": record["Id"], "repo_digests": record.get("RepoDigests", [])}


class Container:
    def __init__(self, image: str, mounts: list[tuple[Path, str, bool]], artifacts: Path,
                 *, network: bool = False):
        self.image = image
        self.mounts = mounts
        self.artifacts = artifacts
        self.network = network
        self.name = f"skill-eval-{uuid.uuid4().hex}"
        self.created = False
        self.stopped = False

    def checked(self, command: list[str], label: str) -> bytes:
        log = self.artifacts / f"{label}.log"
        result = command_result(command, log, 30)
        if result["exit_code"] != 0:
            raise InfrastructureError(f"Docker {label} failed; see {log}")
        return log.read_bytes()

    def __enter__(self) -> Container:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        command = [
            "docker", "create", "--name", self.name, "--network",
            "bridge" if self.network else "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--workdir", "/workspace/repo",
            "--env", "HOME=/tmp/eval-home", "--env", "COPILOT_HOME=/tmp/eval-home",
            "--env", "CI=true", "--env", "BASH_ENV=", "--env", "ENV=",
            "--entrypoint", "sleep",
        ]
        for source, destination, writable in self.mounts:
            if "," in str(source):
                raise ValueError("Docker bind source cannot contain a comma")
            command += ["--mount", f"type=bind,src={source.resolve()},dst={destination}"
                        + ("" if writable else ",readonly")]
        command += [self.image, "infinity"]
        try:
            self.checked(command, "create")
            self.created = True
            self.checked(["docker", "start", self.name], "start")
            # Select only mount/network state: never persist Docker environment inspection.
            inspected = self.checked([
                "docker", "inspect", "--format",
                '{"mounts":{{json .Mounts}},"network":{{json .HostConfig.NetworkMode}}}',
                self.name,
            ], "boundary")
            boundary = json.loads(inspected)
            actual = {(item["Destination"], item["RW"]) for item in boundary["mounts"]}
            expected = {(dest, writable) for _, dest, writable in self.mounts}
            if actual != expected or len(boundary["mounts"]) != len(expected):
                raise InfrastructureError("unexpected Docker mounts (including image volumes)")
            if boundary["network"] != ("bridge" if self.network else "none"):
                raise InfrastructureError("unexpected Docker network mode")
            write_json(self.artifacts / "boundary.json", boundary)
        except (OSError, ValueError, InfrastructureError):
            if self.created:
                self.close()
            raise
        return self

    def execute(self, command: dict, label: str, *, token: bool = False) -> dict:
        argv = ["docker", "exec"]
        if token:
            argv += ["--env", "COPILOT_GITHUB_TOKEN"]
        argv += [self.name, *command["argv"]]
        result = command_result(argv, self.artifacts / f"{label}.log", command["timeout_seconds"])
        if result["timed_out"]:
            self.stop()
        else:
            running = self.checked([
                "docker", "inspect", "--format", "{{.State.Running}}", self.name,
            ], f"{label}-health").strip()
            if running != b"true":
                raise InfrastructureError("container stopped unexpectedly during execution")
        return result

    def stop(self) -> None:
        if not self.stopped:
            self.checked(["docker", "kill", self.name], "stop")
            self.stopped = True

    def close(self) -> None:
        self.checked(["docker", "rm", "--force", self.name], "remove")
        self.stopped = True

    def usage_events(self, session_id: str) -> bytes | None:
        return measurement.container_events(self.name, session_id, stopped=self.stopped)

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def git(repository: Path, arguments: list[str], *, input_bytes: bytes | None = None) -> bytes:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(repository.parent),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(repository.parent.resolve()),
        "GIT_AUTHOR_NAME": "Evaluation", "GIT_AUTHOR_EMAIL": "evaluation@localhost",
        "GIT_COMMITTER_NAME": "Evaluation", "GIT_COMMITTER_EMAIL": "evaluation@localhost",
    }
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.autocrlf=false",
         "-c", "core.fileMode=true", "-C", str(repository), *arguments],
        env=env, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=60, check=False,
    )
    if result.returncode:
        raise ValueError(f"trusted Git operation failed: {result.stderr.decode('utf-8', errors='replace')}")
    return result.stdout


def copy_source(source: Path, destination: Path,
                runtime_links: dict[str, str] | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in ordinary_files(source, skip_git=True, runtime_links=runtime_links):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def export_patch(frozen: Path, candidate: Path, patch: Path,
                 setup_links: list[dict[str, str]] | None = None) -> None:
    runtime_links = {
        item["path"]: item["target"]
        for item in setup_links or []
    }
    with tempfile.TemporaryDirectory(prefix="skill-eval-export-") as directory:
        trusted = Path(directory) / "repository"
        copy_packet(frozen / "repository", trusted)
        git(trusted, ["init", "--quiet"])
        # Disable attributes so candidate filter/diff drivers cannot affect the export.
        attributes = trusted / ".git" / "info" / "attributes"
        attributes.write_text("* -filter !diff -text -ident -working-tree-encoding\n", encoding="utf-8")
        git(trusted, ["add", "--all", "--force"])
        git(trusted, ["commit", "--quiet", "--allow-empty", "-m", "Frozen base"])
        for entry in trusted.iterdir():
            if entry.name != ".git":
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
        try:
            copy_source(candidate, trusted, runtime_links)
        except (PermissionError, ValueError) as error:
            raise CandidateStateError(f"candidate source export failed: {error}") from error
        git(trusted, ["add", "--all", "--force"])
        patch.write_bytes(git(trusted, ["diff", "--cached", "--binary", "--full-index",
                                        "--no-ext-diff", "--no-renames", "HEAD", "--"]))


def apply_patch(repository: Path, patch: Path) -> None:
    if patch.stat().st_size:
        git(repository, ["apply", "--binary", "--whitespace=nowarn", "-"], input_bytes=patch.read_bytes())
    ordinary_files(repository)


def completed_check(record: dict, command: dict, artifacts: Path) -> bool:
    return (
        record["exit_code"] == 0 and not record["timed_out"]
        and command["success_output_contains"] in
        (artifacts / record["log"]).read_text(encoding="utf-8", errors="replace")
    )


def grade(frozen: Path, task: dict, artifacts: Path, patch: Path | None = None) -> dict:
    results = {}
    artifacts.mkdir(parents=True, exist_ok=True)
    for name in ("target", "regression"):
        stage = artifacts / name
        with tempfile.TemporaryDirectory(prefix=".grader-", dir=artifacts) as directory:
            repository = Path(directory) / "repository"
            copy_packet(frozen / "repository", repository)
            if patch is not None:
                apply_patch(repository, patch)
            mounts = [
                (repository, "/workspace/repo", True),
                (frozen / "judge-reference" / "grader", "/grader", False),
            ]
            with Container(task["image"], mounts, stage) as container:
                setup_results = []
                for index, command in enumerate(task["grading"]["setup"]):
                    record = container.execute(command, f"setup-{index}")
                    setup_results.append(record)
                    if record["exit_code"] != 0:
                        break
                setup_ok = all(item["exit_code"] == 0 for item in setup_results)
                check = container.execute(task["grading"][name], "check") if setup_ok else None
                results[name] = {
                    "setup": setup_results, "setup_ok": setup_ok, "check": check,
                    "passed": bool(check and completed_check(check, task["grading"][name], stage)),
                }
    write_json(artifacts / "grading.json", results)
    return results


def check_candidate_setup(frozen: Path, task: dict, artifacts: Path,
                          patch: Path | None = None) -> dict:
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".setup-", dir=artifacts) as directory:
        source = Path(directory) / "repository"
        copy_packet(frozen / "repository", source)
        if patch is not None:
            apply_patch(source, patch)
        records = []
        if task["candidate_setup"]:
            with Container(task["image"], [(source, "/workspace/repo", True)], artifacts) as container:
                for index, command in enumerate(task["candidate_setup"]):
                    record = container.execute(command, f"setup-{index}")
                    records.append(record)
                    if record["exit_code"] != 0:
                        raise InfrastructureError("candidate setup failed during admission")
        links = observe_setup_links(frozen, source)
        write_json(artifacts / "setup-runtime-links.json", {
            "schema_version": 1,
            "links": links,
        })
        exported_patch = artifacts / "candidate.patch"
        export_patch(frozen, source, exported_patch, links)
        return {
            "commands": records,
            "runtime_links": links,
            "patch": {
                "path": exported_patch.name,
                "sha256": digest(exported_patch),
            },
        }


def harness_sources() -> list[dict]:
    directory = Path(__file__).resolve().parent
    return [
        {"path": name, "sha256": digest(directory / name)}
        for name in ("skill_eval.py", "repository_task.py", "measurement.py",
                     "quality_review.py", "evaluation_history.py")
    ]


def admission_binding(frozen: Path, image: dict) -> dict:
    return {
        "case_revision": digest(frozen / "case-manifest.json"),
        "image": image, "harness_modules": harness_sources(),
    }


def validate_repository_case(root: Path, case_id: str) -> Path:
    verify_case(root, case_id)
    frozen = frozen_case_path(root, case_id)
    definition = read_json(frozen / "case.json")
    if definition.get("case_type") != "repository-task":
        raise ValueError("validate-case requires a repository-task case")
    task = definition["repository_task"]
    artifacts = root / "admission-runs" / f"{utc_stamp()}-{uuid.uuid4().hex[:8]}" / case_id
    artifacts.mkdir(parents=True)
    receipt = {"status": "INVALID", "case_id": case_id}
    try:
        receipt.update(admission_binding(frozen, image_identity(task["image"])))
        setup_base = check_candidate_setup(frozen, task, artifacts / "candidate-setup-base")
        setup_reference = check_candidate_setup(
            frozen, task, artifacts / "candidate-setup-reference",
            frozen / task["admission"]["reference_patch"],
        )
        base = grade(
            frozen, task, artifacts / "base",
            artifacts / "candidate-setup-base" / setup_base["patch"]["path"],
        )
        reference = grade(
            frozen, task, artifacts / "reference",
            artifacts / "candidate-setup-reference" / setup_reference["patch"]["path"],
        )
        failure = task["admission"]["base_target_failure"]
        check = base["target"]["check"]
        intended_failure = bool(
            check and not check["timed_out"] and check["exit_code"] == failure["exit_code"]
            and failure["output_contains"] in
            (artifacts / "base" / "target" / check["log"]).read_text(encoding="utf-8", errors="replace")
        )
        valid = (
            intended_failure and all(item["setup_ok"] for item in base.values())
            and base["regression"]["passed"] and all(item["passed"] for item in reference.values())
        )
        receipt.update(status="PASS" if valid else "INVALID",
                       base=base, reference=reference, intended_base_failure=intended_failure,
                       candidate_setup_base=setup_base, candidate_setup_reference=setup_reference)
        if not valid:
            receipt["failure_kind"] = "case_admission"
    except (OSError, ValueError, InfrastructureError, subprocess.TimeoutExpired) as error:
        receipt.update(failure_kind="admission_infrastructure", error_type=type(error).__name__,
                       error=str(error))
    receipt["artifacts"] = [
        {"path": path.relative_to(artifacts).as_posix(), "sha256": digest(path)}
        for path in sorted(artifacts.rglob("*")) if path.is_file()
    ]
    write_json(artifacts / "admission-receipt.json", receipt)
    return artifacts


def require_admission(root: Path, case_id: str, binding: dict) -> Path:
    for path in sorted((root / "admission-runs").glob(f"*/{case_id}/admission-receipt.json"), reverse=True):
        receipt = read_json(path)
        if receipt.get("status") == "PASS" and all(receipt.get(key) == value for key, value in binding.items()):
            for artifact in receipt["artifacts"]:
                if digest(resolve_under(path.parent, artifact["path"])) != artifact["sha256"]:
                    raise ValueError("admission artifact digest mismatch")
            # Admission logs remain part of the evidence, not just an unchecked PASS bit.
            for arm in ("base", "reference"):
                for name in ("target", "regression"):
                    records = receipt[arm][name]["setup"] + [receipt[arm][name]["check"]]
                    for record in records:
                        log = path.parent / arm / name / record["log"]
                        if digest(log) != record["raw_log_sha256"]:
                            raise ValueError("admission log digest mismatch")
            return path
    raise ValueError("matching successful admission required; run validate-case")


def candidate_command(model: str, effort: str, prompt: str, arm: str,
                      session_id: str | None = None) -> list[str]:
    tools = LOCAL_TOOLS + (",skill" if arm == "skill" else "")
    command = [
        "copilot", "-C", "/workspace/repo", "-p", prompt,
        "--model", model, "--effort", effort,
        f"--available-tools={tools}", "--allow-all-tools", "--allow-tool=shell",
        "--allow-all-paths", "--no-custom-instructions", "--disable-builtin-mcps",
        "--no-remote", "--no-remote-export", "--no-auto-update", "--no-bash-env",
        "--no-ask-user", "--no-color", "--output-format", "json", "--log-level", "error",
        "--secret-env-vars=COPILOT_GITHUB_TOKEN", "--session-id",
        measurement.session_uuid(session_id or str(uuid.uuid4())),
    ]
    if arm == "skill":
        command += ["--plugin-dir", "/plugin"]
    return command


def execute_repository(
    root: Path, case_id: str, frozen: Path, run_root: Path, plugin: Path,
    model: str, effort: str, timeout_seconds: int, arm: str,
    *, timeline: measurement.Timeline | None = None,
) -> dict:
    from skill_eval import parse_run, validate_candidate

    started = time.monotonic()
    owned_timeline = timeline is None
    timeline = timeline or measurement.Timeline()
    task = read_json(frozen / "case.json")["repository_task"]
    definition = read_json(frozen / "case.json")
    result = {
        "schema_version": 1, "case_id": case_id, "case_type": "repository-task",
        "case_revision": digest(frozen / "case-manifest.json"),
        "arm": arm, "execution_status": "INVALID", "failure_kind": None,
        "behavioral_verdict": None, "patch_sha256": None, "usage": None,
        "input_tokens": None, "output_tokens": None, "tool_calls": None,
        "network": "enabled", "credential_filter": "cli-secret-env-vars",
        "remote_history_isolation": "not_enforced", "contamination": "not_assessed",
        "model": model, "effort": effort, "timeout_seconds": timeout_seconds,
        "home_mode": "isolated",
    }
    stage = "admission"
    patch = run_root / "candidate.patch"
    setup_links: list[dict[str, str]] = []
    candidate_started = False
    try:
        image = image_identity(task["image"])
        result["image"] = image
        admission = require_admission(root, case_id, admission_binding(frozen, image))
        result["admission_receipt_sha256"] = digest(admission)
        stage = "authentication"
        if not os.environ.get("COPILOT_GITHUB_TOKEN"):
            raise ValueError("repository execution requires caller-supplied COPILOT_GITHUB_TOKEN")
        phase = definition["phases"][0]
        prompt = (
            (frozen / phase["prompt_file"]).read_text(encoding="utf-8")
            + "\nRead the task and context in /evidence. Work in /workspace/repo.\n"
            + "Do not retrieve source-origin answers or historical solutions from the network.\n"
        )
        if arm == "skill":
            prompt = f"Invoke the `{definition['target_skill']}` skill unchanged.\n\n" + prompt
        prompt_path = run_root / "candidate-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix=".candidate-", dir=run_root) as directory:
            temporary = Path(directory)
            repository = temporary / "repository"
            evidence = temporary / "evidence"
            copy_packet(frozen / "repository", repository)
            copy_packet(frozen / phase["id"], evidence)
            git(repository, ["init", "--quiet"])
            git(repository, ["add", "--all", "--force"])
            git(repository, ["commit", "--quiet", "--allow-empty", "-m", "Frozen task source"])
            mounts = [(repository, "/workspace/repo", True), (evidence, "/evidence", False)]
            if arm == "skill":
                mounts.append((plugin, "/plugin", False))
            stage = "candidate_infrastructure"
            container = Container(task["image"], mounts, run_root / "candidate", network=True)
            try:
                with container:
                    identity = container.execute(
                        {"argv": ["copilot", "--version"], "timeout_seconds": 30}, "cli-version")
                    if identity["exit_code"] != 0:
                        raise InfrastructureError("candidate CLI unavailable in execution image")
                    result["candidate_cli"] = {
                        "version": (run_root / "candidate" / identity["log"]).read_text().strip(),
                        "image_id": image["id"],
                    }
                    stage = "candidate_setup"
                    for index, command in enumerate(task["candidate_setup"]):
                        record = container.execute(command, f"setup-{index}")
                        if record["exit_code"] != 0:
                            raise ValueError("candidate setup failed before candidate execution")
                    stage = "candidate_setup_observation"
                    setup_links = observe_setup_links(frozen, repository)
                    write_json(run_root / "candidate" / "setup-runtime-links.json", {
                        "schema_version": 1,
                        "links": setup_links,
                    })
                    stage = "candidate"
                    timeline.switch("candidate")
                    session_id = str(uuid.uuid4())
                    result["candidate_session_id"] = session_id
                    command = candidate_command(model, effort, prompt, arm, session_id)
                    invoked_at, invoked_clock = measurement.instant(), time.monotonic()
                    outcome = "failed"
                    try:
                        candidate_started = True
                        record = container.execute(
                            {"argv": command, "timeout_seconds": timeout_seconds}, "trajectory", token=True)
                        result["candidate"] = record
                        if record["timed_out"]:
                            outcome = "timed_out"
                            result.update(execution_status="FAIL", failure_kind="candidate_timeout")
                        elif record["exit_code"] != 0:
                            raise ValueError("candidate CLI failed; inspect retained trajectory")
                        else:
                            outcome = "completed"
                            parsed = parse_run(
                                run_root / "candidate" / "trajectory.log",
                                skill=definition["target_skill"], expected_model=model,
                                cwd=Path("/workspace/repo"), require_skill=arm == "skill",
                                boundary="docker-local-packets",
                            )
                            result.update({key: parsed[key] for key in
                                           ("usage", "tool_calls", "input_tokens", "output_tokens")})
                            result["observed_models"] = parsed["models"]
                            result["skill_invoked"] = parsed["skill_loaded"]
                            validate_candidate(parsed["answer"], phase)
                            (run_root / "candidate-output.md").write_text(parsed["answer"] + "\n", encoding="utf-8")
                    except KeyboardInterrupt:
                        outcome = "interrupted"
                        raise
                    finally:
                        timeline.switch("cleanup", status=outcome)
                        try:
                            container.stop()
                        finally:
                            measurement.collect(
                                destination=run_root / "measurements" / "candidate.json",
                                session_id=session_id, role="candidate", phase=phase["id"],
                                model=model, effort=effort, cli_version=result["candidate_cli"]["version"],
                                log=run_root / "candidate" / "trajectory.log",
                                capture=lambda: container.usage_events(session_id),
                                source="container_eventfile", started_at=invoked_at,
                                started_clock=invoked_clock, outcome=outcome,
                            )
            finally:
                # Export only after the context has stopped/removed its sole writer.
                if container.created and not container.stopped:
                    raise InfrastructureError("candidate stop could not be confirmed; patch not exported")
                if candidate_started:
                    export_patch(frozen, repository, patch, setup_links)
                    result["patch_sha256"] = digest(patch)
            if result["failure_kind"] != "candidate_timeout":
                stage = "grading"
                timeline.switch("deterministic_grading")
                grades = grade(frozen, task, run_root / "grading", patch)
                if all(item["passed"] for item in grades.values()):
                    result.update(execution_status="PASS", failure_kind=None)
                else:
                    # Fresh controls distinguish a changed repository from broken infrastructure.
                    control = grade(frozen, task, run_root / "grading-control",
                                    admission.parent / "candidate-setup-reference" / "candidate.patch")
                    healthy = all(item["passed"] for item in control.values())
                    result.update(
                        execution_status="FAIL" if healthy else "INVALID",
                        failure_kind="candidate_grading" if healthy else "grading_environment",
                    )
    except CandidateStateError as error:
        timeline.end_stage("failed")
        result.update(execution_status="FAIL", failure_kind="candidate_output",
                      error_type=type(error).__name__, error=str(error))
    except (OSError, ValueError, InfrastructureError, subprocess.TimeoutExpired) as error:
        timeline.end_stage("failed")
        result.update(execution_status="INVALID", failure_kind=stage,
                      error_type=type(error).__name__, error=str(error))
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if owned_timeline:
        measurement.write_once(run_root / "execution-timing.json", timeline.finish(
            "failed" if result["execution_status"] == "INVALID" else "completed"))
    result["artifacts"] = [
        {"path": path.relative_to(run_root).as_posix(), "sha256": digest(path)}
        for path in sorted(run_root.rglob("*"))
        if path.is_file() and "target-plugin" not in path.relative_to(run_root).parts
    ]
    write_json(run_root / "execution-result.json", result)
    return result
