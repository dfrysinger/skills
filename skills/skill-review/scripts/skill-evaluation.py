#!/usr/bin/env python3
"""Prepare, score, and verify source/sibling skill evaluations."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
RUNNER_VERSION = "skill-evaluation-runner-1"
PROMPT_VERSION = "skill-evaluation-prompt-1"
COMPARATOR_VERSION = "skill-evaluation-comparator-1"
CASE_FILE = ".skill-evaluation-cases.json"
LOCAL_SIDECARS = {
    ".agent-created",
    ".agent-created.json",
    ".promotion-reviewed.json",
    CASE_FILE,
    ".pinned",
}
STATUS_ALLOWLIST = {"pass", "waived"}
WAIVER_CLASSES = {"documentation-only", "reference-only", "deterministic-helper"}
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,}$")


class EvaluationError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{field} must be non-empty text")
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"{path} must contain a JSON object")
    return value


def atomic_write(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
            os.fsync(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    finally:
        os.close(directory_fd)


def inventory(skill_dir: Path, destination: Path | None = None) -> list[dict[str, Any]]:
    if not (skill_dir / "SKILL.md").is_file():
        raise EvaluationError(f"missing SKILL.md in {skill_dir}")
    files: list[dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        relative = path.relative_to(skill_dir).as_posix()
        if path.is_symlink():
            raise EvaluationError(f"{relative}: symlinks are not valid evaluation inputs")
        if path.is_dir():
            continue
        if not path.is_file():
            raise EvaluationError(f"{relative}: runtime input must be a regular file")
        if relative in LOCAL_SIDECARS:
            continue
        if path.name in LOCAL_SIDECARS:
            raise EvaluationError(f"{relative}: reserved evaluation sidecar must be at skill root")
        content = path.read_bytes()
        files.append({"path": relative, "sha256": digest(content), "size": len(content)})
        if destination is not None:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            os.chmod(target, path.stat().st_mode & 0o777)
    return files


def candidate_id(skill_dir: Path) -> tuple[str, list[dict[str, Any]]]:
    files = inventory(skill_dir)
    return f"sha256:{digest(canonical(files))}", files


def validate_patterns(value: Any, field: str, required: bool = False) -> list[dict[str, str]]:
    if not isinstance(value, list) or (required and not value):
        raise EvaluationError(f"{field} must be {'a non-empty' if required else 'an'} list")
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EvaluationError(f"{field}[{index}] must be an object")
        item_id = require_text(item.get("id"), f"{field}[{index}].id")
        pattern = require_text(item.get("pattern"), f"{field}[{index}].pattern")
        if item_id in seen:
            raise EvaluationError(f"{field} has duplicate id {item_id}")
        seen.add(item_id)
        try:
            re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            raise EvaluationError(f"{field}[{index}].pattern is invalid: {exc}") from exc
        result.append({"id": item_id, "pattern": pattern})
    return result


def validate_case(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationError(f"{field} must be an object")
    task_id = require_text(value.get("task_id"), f"{field}.task_id")
    if not TASK_ID_RE.fullmatch(task_id):
        raise EvaluationError(f"{field}.task_id is invalid")
    return {
        "task_id": task_id,
        "prompt": require_text(value.get("prompt"), f"{field}.prompt"),
        "required_regex": validate_patterns(
            value.get("required_regex"), f"{field}.required_regex", required=True
        ),
        "forbidden_regex": validate_patterns(
            value.get("forbidden_regex", []), f"{field}.forbidden_regex"
        ),
        "friction_regex": validate_patterns(
            value.get("friction_regex", []), f"{field}.friction_regex"
        ),
    }


def load_cases(path: Path) -> tuple[dict[str, Any], str]:
    raw = load_json(path)
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise EvaluationError(f"case manifest schema_version must be {SCHEMA_VERSION}")
    value = {
        "schema_version": SCHEMA_VERSION,
        "source": validate_case(raw.get("source"), "source"),
        "sibling": validate_case(raw.get("sibling"), "sibling"),
    }
    if value["source"]["task_id"] == value["sibling"]["task_id"]:
        raise EvaluationError("source and sibling task_id values must differ")
    return value, digest(canonical(value))


def cli_version(copilot: str) -> str:
    result = subprocess.run(
        [copilot, "--version"], check=True, capture_output=True, text=True, timeout=30
    )
    return require_text(result.stdout.strip(), "Copilot CLI version")


def runtime_contract(candidate: str, cases_sha: str, model: str, cli: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate,
        "case_manifest_sha256": cases_sha,
        "model": model,
        "cli_version": cli,
        "runner_version": RUNNER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "comparator_version": COMPARATOR_VERSION,
        "flags": [
            "--effort=low",
            "--available-tools=skill,view",
            "--allow-tool=skill,view",
            "--no-custom-instructions",
            "--disable-builtin-mcps",
            "--disallow-temp-dir",
            "--no-remote",
            "--no-color",
            "--output-format=json",
            "--log-level=error",
        ],
        "working_directory": "fresh-empty-directory",
        "baseline_plugin": None,
        "candidate_plugin": "immutable-candidate-snapshot",
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    run_dir = Path(args.run_dir).resolve()
    plugin = Path(args.plugin_dir).resolve()
    cases_path = Path(args.cases or skill_dir / CASE_FILE).resolve()
    if args.model == "auto":
        raise EvaluationError("evaluation requires an explicit non-auto model")
    cases, cases_sha = load_cases(cases_path)
    name_match = re.search(
        r"(?m)^name:\s*([a-z0-9][a-z0-9-]*)\s*$",
        (skill_dir / "SKILL.md").read_text(encoding="utf-8"),
    )
    if not name_match:
        raise EvaluationError("SKILL.md must contain a simple kebab-case name")
    name = name_match.group(1)
    destination = plugin / "skills" / name
    destination.mkdir(parents=True, exist_ok=True)
    files = inventory(skill_dir, destination)
    current_id = f"sha256:{digest(canonical(files))}"
    copilot = os.environ.get("COPILOT_BIN", str(Path.home() / ".local/bin/copilot"))
    contract = runtime_contract(current_id, cases_sha, args.model, cli_version(copilot))
    run_id = f"sha256:{digest(canonical(contract))}"
    atomic_write(
        plugin / ".claude-plugin" / "plugin.json",
        {
            "name": "skill-evaluation-candidate",
            "version": "0.0.0",
            "skills": [f"./skills/{name}"],
        },
        mode=0o644,
    )
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "skill": name,
        "skill_path": str(skill_dir),
        "cases_path": str(cases_path),
        "candidate_inventory": files,
        "candidate_id": current_id,
        "case_manifest_sha256": cases_sha,
        "source_case_id": f"sha256:{digest(canonical(cases['source']))}",
        "sibling_case_id": f"sha256:{digest(canonical(cases['sibling']))}",
        "run_id": run_id,
        "runtime": contract,
        "cases": cases,
    }
    atomic_write(run_dir / "metadata.json", metadata)
    for case_name in ("source", "sibling"):
        (run_dir / f"{case_name}.prompt").write_text(
            cases[case_name]["prompt"].rstrip()
            + "\n\nAnswer the task directly. Do not discuss this evaluation.\n",
            encoding="utf-8",
        )
    return metadata


def parse_run(path: Path, skill: str, require_skill: bool, expected_model: str) -> dict[str, Any]:
    messages: list[str] = []
    result_event: dict[str, Any] | None = None
    loaded = False
    models: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {"valid": False, "error": str(exc)}
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return {"valid": False, "error": "non-JSON output in structured run log"}
        event_type = event.get("type")
        data = event.get("data", {})
        if not isinstance(data, dict):
            return {"valid": False, "error": f"{event_type} data must be an object"}
        if event_type == "assistant.message" and isinstance(data.get("content"), str):
            if isinstance(data.get("model"), str):
                models.add(data["model"])
            if data["content"].strip():
                messages.append(data["content"])
        elif event_type == "tool.execution_start":
            if isinstance(data.get("model"), str):
                models.add(data["model"])
            arguments = data.get("arguments")
            loaded = (
                loaded
                or data.get("toolName") == "skill"
                and isinstance(arguments, dict)
                and arguments.get("skill") == skill
            )
        elif event_type == "result":
            result_event = event
    if result_event is None or result_event.get("exitCode") != 0:
        return {"valid": False, "error": "missing successful result event"}
    if not messages:
        return {"valid": False, "error": "missing final assistant message"}
    if models != {expected_model}:
        return {
            "valid": False,
            "error": f"run used model identities {sorted(models)!r}, expected {expected_model!r}",
        }
    if loaded != require_skill:
        expected = "load" if require_skill else "not load"
        return {"valid": False, "error": f"candidate skill must {expected} in this run"}
    return {"valid": True, "answer": messages[-1], "skill_loaded": loaded}


def score(run: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    if not run.get("valid"):
        return {**run, "passed": False, "friction_count": None}
    answer = run["answer"]
    required = {
        item["id"]: bool(re.search(item["pattern"], answer, re.MULTILINE))
        for item in case["required_regex"]
    }
    forbidden = {
        item["id"]: len(re.findall(item["pattern"], answer, re.MULTILINE))
        for item in case["forbidden_regex"]
    }
    friction = {
        item["id"]: len(re.findall(item["pattern"], answer, re.MULTILINE))
        for item in case["friction_regex"]
    }
    return {
        **run,
        "required": required,
        "forbidden": forbidden,
        "friction": friction,
        "passed": all(required.values()) and not any(forbidden.values()),
        "friction_count": sum(friction.values()),
    }


def evaluation_dir() -> Path:
    root = Path(os.environ.get("SKILLS_STATE_DIR", str(Path.home() / ".copilot/skill-state")))
    return root / "skill-review" / "evaluations"


def latest_key(skill_path: str) -> str:
    return digest(str(Path(skill_path).resolve()).encode())


def write_receipt(receipt: dict[str, Any]) -> tuple[Path, str]:
    receipt_bytes = canonical(receipt)
    receipt_sha = digest(receipt_bytes)
    path = evaluation_dir() / "receipts" / f"{receipt_sha}.json"
    if path.exists():
        existing = load_json(path)
        if canonical(existing) != receipt_bytes:
            raise EvaluationError("content-addressed receipt collision")
    else:
        atomic_write(path, receipt)
    atomic_write(
        evaluation_dir() / "latest" / f"{latest_key(receipt['skill_path'])}.json",
        {
            "schema_version": SCHEMA_VERSION,
            "skill_path": receipt["skill_path"],
            "receipt_sha256": receipt_sha,
            "receipt_path": str(path),
        },
    )
    return path, receipt_sha


def update_envelope(skill_dir: Path, receipt_path: Path) -> None:
    envelope = skill_dir / ".agent-created.json"
    if not envelope.exists():
        return
    helper = Path(__file__).with_name("evidence-envelope.py")
    subprocess.run(
        [str(helper), "set-evaluation", str(envelope), str(receipt_path)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    metadata = load_json(run_dir / "metadata.json")
    cases = metadata["cases"]
    runs = {
        "source_baseline": score(
            parse_run(
                run_dir / "source-baseline.jsonl",
                metadata["skill"],
                False,
                metadata["runtime"]["model"],
            ),
            cases["source"],
        ),
        "source_candidate": score(
            parse_run(
                run_dir / "source-candidate.jsonl",
                metadata["skill"],
                True,
                metadata["runtime"]["model"],
            ),
            cases["source"],
        ),
        "sibling_baseline": score(
            parse_run(
                run_dir / "sibling-baseline.jsonl",
                metadata["skill"],
                False,
                metadata["runtime"]["model"],
            ),
            cases["sibling"],
        ),
        "sibling_candidate": score(
            parse_run(
                run_dir / "sibling-candidate.jsonl",
                metadata["skill"],
                True,
                metadata["runtime"]["model"],
            ),
            cases["sibling"],
        ),
    }
    valid = all(run["valid"] for run in runs.values())
    source_before = runs["source_baseline"]
    source_after = runs["source_candidate"]
    sibling_before = runs["sibling_baseline"]
    sibling_after = runs["sibling_candidate"]
    source_improved = bool(valid and not source_before["passed"] and source_after["passed"])
    sibling_regressed = bool(
        valid
        and sibling_before["passed"]
        and (
            not sibling_after["passed"]
            or sibling_after["friction_count"] > sibling_before["friction_count"]
        )
    )
    if valid and (not source_after["passed"] or sibling_regressed):
        status = "regression"
    elif valid and sibling_before["passed"] and source_improved and not sibling_regressed:
        status = "pass"
    else:
        status = "inconclusive"
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "evaluation",
        "status": status,
        "evaluated_at": now_iso(),
        "skill": metadata["skill"],
        "skill_path": metadata["skill_path"],
        "candidate_id": metadata["candidate_id"],
        "candidate_inventory": metadata["candidate_inventory"],
        "run_id": metadata["run_id"],
        "case_manifest_sha256": metadata["case_manifest_sha256"],
        "cases_path": metadata["cases_path"],
        "source_case_id": metadata["source_case_id"],
        "sibling_case_id": metadata["sibling_case_id"],
        "runtime": metadata["runtime"],
        "source_improved": source_improved,
        "sibling_regressed": sibling_regressed,
        "runs": runs,
    }
    receipt_path, receipt_sha = write_receipt(receipt)
    update_envelope(Path(metadata["skill_path"]), receipt_path)
    return {"status": status, "receipt": str(receipt_path), "receipt_sha256": receipt_sha}


def verify_receipt_bytes(pointer: dict[str, Any]) -> tuple[dict[str, Any], str]:
    path = Path(require_text(pointer.get("receipt_path"), "receipt_path"))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvaluationError(f"cannot read receipt: {exc}") from exc
    receipt_sha = digest(canonical(json.loads(raw)))
    if receipt_sha != pointer.get("receipt_sha256") or path.name != f"{receipt_sha}.json":
        raise EvaluationError("receipt hash or content-addressed path does not match")
    receipt = json.loads(raw)
    if not isinstance(receipt, dict):
        raise EvaluationError("receipt must be a JSON object")
    return receipt, receipt_sha


def gate(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    pointer_path = evaluation_dir() / "latest" / f"{latest_key(str(skill_dir))}.json"
    pointer = load_json(pointer_path)
    if pointer.get("skill_path") != str(skill_dir):
        raise EvaluationError("latest evaluation pointer belongs to another skill path")
    receipt, receipt_sha = verify_receipt_bytes(pointer)
    if receipt.get("status") not in STATUS_ALLOWLIST:
        raise EvaluationError(f"evaluation status {receipt.get('status')!r} is not allowed")
    current_id, _ = candidate_id(skill_dir)
    if receipt.get("candidate_id") != current_id:
        raise EvaluationError("evaluation is stale for the current candidate inventory")
    if receipt.get("kind") == "evaluation":
        cases, cases_sha = load_cases(Path(receipt["cases_path"]))
        if cases_sha != receipt.get("case_manifest_sha256"):
            raise EvaluationError("evaluation case manifest changed after the run")
        expected = runtime_contract(
            current_id,
            cases_sha,
            receipt["runtime"]["model"],
            receipt["runtime"]["cli_version"],
        )
        if receipt.get("runtime") != expected:
            raise EvaluationError("evaluation runtime contract is malformed")
        if receipt.get("run_id") != f"sha256:{digest(canonical(expected))}":
            raise EvaluationError("evaluation run_id does not match runtime inputs")
        if receipt.get("source_case_id") != f"sha256:{digest(canonical(cases['source']))}":
            raise EvaluationError("source case identity changed")
        if receipt.get("sibling_case_id") != f"sha256:{digest(canonical(cases['sibling']))}":
            raise EvaluationError("sibling case identity changed")
    elif receipt.get("kind") == "waiver":
        anchor_sha = require_text(
            receipt.get("waived_from_receipt_sha256"),
            "waived_from_receipt_sha256",
        )
        anchor_pointer = {
            "receipt_path": str(evaluation_dir() / "receipts" / f"{anchor_sha}.json"),
            "receipt_sha256": anchor_sha,
        }
        anchor, _ = verify_receipt_bytes(anchor_pointer)
        verify_evaluation_anchor(anchor, skill_dir)
        if (
            receipt.get("base_candidate_id") != anchor.get("candidate_id")
            or receipt.get("base_run_id") != anchor.get("run_id")
        ):
            raise EvaluationError("waiver does not bind its passing evaluation")
    else:
        raise EvaluationError("receipt kind is invalid")
    envelope_path = skill_dir / ".agent-created.json"
    if envelope_path.exists():
        envelope = load_json(envelope_path)
        evaluation = envelope.get("evaluation", {})
        if (
            evaluation.get("status") != receipt.get("status")
            or evaluation.get("candidate_id") != current_id
            or evaluation.get("receipt_sha256") != receipt_sha
        ):
            raise EvaluationError("evidence envelope does not mirror the current receipt")
    return {"status": receipt["status"], "candidate_id": current_id, "receipt_sha256": receipt_sha}


def verify_evaluation_anchor(receipt: dict[str, Any], skill_dir: Path) -> None:
    if (
        receipt.get("kind") != "evaluation"
        or receipt.get("status") != "pass"
        or receipt.get("skill_path") != str(skill_dir)
    ):
        raise EvaluationError("waiver anchor must be a passing evaluation for this skill")
    files = receipt.get("candidate_inventory")
    if not isinstance(files, list):
        raise EvaluationError("waiver anchor is missing candidate inventory")
    if receipt.get("candidate_id") != f"sha256:{digest(canonical(files))}":
        raise EvaluationError("waiver anchor candidate inventory is malformed")
    cases, cases_sha = load_cases(Path(receipt["cases_path"]))
    expected = runtime_contract(
        receipt["candidate_id"],
        cases_sha,
        receipt["runtime"]["model"],
        receipt["runtime"]["cli_version"],
    )
    if (
        receipt.get("case_manifest_sha256") != cases_sha
        or receipt.get("runtime") != expected
        or receipt.get("run_id") != f"sha256:{digest(canonical(expected))}"
        or receipt.get("source_case_id")
        != f"sha256:{digest(canonical(cases['source']))}"
        or receipt.get("sibling_case_id")
        != f"sha256:{digest(canonical(cases['sibling']))}"
    ):
        raise EvaluationError("waiver anchor evaluation contract is stale or malformed")


def waive(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    base_path = Path(args.base_receipt).resolve()
    if base_path.parent != (evaluation_dir() / "receipts").resolve():
        raise EvaluationError("base receipt must come from the evaluation receipt store")
    base_sha = base_path.stem
    base, verified_base_sha = verify_receipt_bytes(
        {"receipt_path": str(base_path), "receipt_sha256": base_sha}
    )
    verify_evaluation_anchor(base, skill_dir)
    current_id, current_files = candidate_id(skill_dir)
    before = {item["path"]: item for item in base["candidate_inventory"]}
    after = {item["path"]: item for item in current_files}
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    if not changed:
        raise EvaluationError("waiver requires an actual candidate change")
    if "SKILL.md" in changed:
        raise EvaluationError("SKILL.md changes cannot be waived")
    waiver_class = args.waiver_class
    if waiver_class in {"documentation-only", "reference-only"}:
        raise EvaluationError(f"{waiver_class} cannot waive runtime-visible skill files")
    if not all(path.startswith("scripts/") for path in changed):
        raise EvaluationError("deterministic-helper waivers may change only scripts/")
    if not args.test_script:
        raise EvaluationError("deterministic-helper waiver requires --test-script")
    test_path = (skill_dir / args.test_script).resolve()
    try:
        test_relative = test_path.relative_to(skill_dir).as_posix()
    except ValueError as exc:
        raise EvaluationError("test script must remain inside the skill") from exc
    if not test_relative.startswith("scripts/") or test_relative in changed:
        raise EvaluationError("test script must be an unchanged scripts/ file")
    if before.get(test_relative) != after.get(test_relative):
        raise EvaluationError("test script must match the base snapshot exactly")
    result = subprocess.run(
        [str(test_path)],
        cwd=skill_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise EvaluationError("deterministic helper test command failed")
    try:
        attestation = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EvaluationError("helper test must emit one JSON attestation") from exc
    expected_files = {path: after[path]["sha256"] for path in changed}
    if not isinstance(attestation, dict) or attestation != {
        "status": "pass",
        "verified_files": expected_files,
    }:
        raise EvaluationError("helper test attestation does not bind every changed file")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "waiver",
        "status": "waived",
        "evaluated_at": now_iso(),
        "skill": skill_dir.name,
        "skill_path": str(skill_dir),
        "candidate_id": current_id,
        "base_candidate_id": base["candidate_id"],
        "base_run_id": base["run_id"],
        "waived_from_receipt_sha256": verified_base_sha,
        "changed_paths": changed,
        "waiver_class": waiver_class,
        "waiver_reason": require_text(args.reason, "waiver reason"),
        "test_script": test_relative,
        "test_attestation": attestation,
    }
    receipt_path, receipt_sha = write_receipt(receipt)
    update_envelope(skill_dir, receipt_path)
    return {"status": "waived", "receipt": str(receipt_path), "receipt_sha256": receipt_sha}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("skill_dir")
    prepare_parser.add_argument("--cases")
    prepare_parser.add_argument("--model", required=True)
    prepare_parser.add_argument("--run-dir", required=True)
    prepare_parser.add_argument("--plugin-dir", required=True)
    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--run-dir", required=True)
    gate_parser = commands.add_parser("gate")
    gate_parser.add_argument("skill_dir")
    waive_parser = commands.add_parser("waive")
    waive_parser.add_argument("skill_dir")
    waive_parser.add_argument("--base-receipt", required=True)
    waive_parser.add_argument("--waiver-class", choices=sorted(WAIVER_CLASSES), required=True)
    waive_parser.add_argument("--reason", required=True)
    waive_parser.add_argument("--test-script")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = {
            "prepare": prepare,
            "finalize": finalize,
            "gate": gate,
            "waive": waive,
        }[args.command](args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (EvaluationError, KeyError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"REFUSED: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
