"""Native historical-session import for the existing evaluation executors."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import uuid
from pathlib import Path, PurePosixPath


FIELDS = {"history_file", "source_session_id", "cutoff_event_id", "skill_context", "limitations"}


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("restoration requires a relative file path")
    path = PurePosixPath(value)
    if (path.is_absolute() or ".." in path.parts or path.as_posix() != value
            or value == "." or any(char in value for char in "\\\0\r\n")):
        raise ValueError("restoration file path must stay beneath its packet")
    return value


def validate_restoration(definition: dict, root: Path, *, frozen: bool = False) -> None:
    for index, phase in enumerate(definition["phases"]):
        if "session_restore" not in phase:
            continue
        if index != 0 or phase.get("resume"):
            raise ValueError("session_restore is allowed only on the first phase")
        restoration = phase["session_restore"]
        if not isinstance(restoration, dict) or set(restoration) != FIELDS:
            raise ValueError("session_restore requires exactly its declared fields")
        if any(not isinstance(restoration[key], str) or not restoration[key].strip()
               for key in ("source_session_id", "cutoff_event_id")):
            raise ValueError("restoration source and cutoff must be nonempty strings")
        if restoration["skill_context"] not in ("before-target-load", "recorded-target-context"):
            raise ValueError("restoration skill context must be before-target-load or recorded-target-context")
        clean_context = restoration["skill_context"] == "before-target-load"
        if (not isinstance(restoration["limitations"], list)
                or any(not isinstance(item, str) or not item.strip()
                       for item in restoration["limitations"])):
            raise ValueError("restoration limitations must be a string array")
        relative = relative_path(restoration["history_file"])
        packet = root / (phase["id"] if frozen else phase["evidence_dir"])
        history = packet / relative
        if (history.is_symlink() or not history.is_file()
                or not history.resolve().is_relative_to(packet.resolve())):
            raise ValueError("restoration history must be a regular file beneath its packet")
        target = definition["target_skill"]
        context = re.compile(
            rf'<skill-context\b[^>]*\bname=["\'](?:[^"\']*:)?{re.escape(target)}["\']'
        )
        header = None
        with history.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("restoration records must be JSON objects")
                if header is None:
                    header = record
                    if (header.get("type") != "session" or header.get("version") != 1
                            or header.get("externalId") != restoration["source_session_id"]):
                        raise ValueError("restoration header does not match source session")
                    continue
                if record.get("id") == restoration["cutoff_event_id"]:
                    raise ValueError("restoration history includes its excluded cutoff event")
                arguments = record.get("arguments", {})
                if (clean_context and record.get("type") == "tool-call"
                        and record.get("name") in {"skill", "functions.skill"}
                        and isinstance(arguments, dict)
                        and str(arguments.get("skill", "")).split(":")[-1] == target):
                    raise ValueError("restoration history contains a target-skill invocation")
                if clean_context and context.search(json.dumps(record, ensure_ascii=False).replace('\\"', '"')):
                    raise ValueError("restoration history contains old target-skill context")
        if header is None:
            raise ValueError("restoration history is empty")


def permission_rules(profile: object, *, workdir: str = "/workspace/repo") -> list[str]:
    if not isinstance(profile, dict) or set(profile) != {"write_paths", "shell_commands"}:
        raise ValueError("candidate_permissions requires write_paths and shell_commands")
    if any(not isinstance(profile[key], list)
           or any(not isinstance(value, str) or not value for value in profile[key])
           for key in profile):
        raise ValueError("candidate_permissions fields must be string arrays")
    rules = []
    for value in profile["write_paths"]:
        relative_path(value)
        if any(char in value for char in "*?[]{}(),") or any(ord(char) < 32 for char in value):
            raise ValueError("candidate write permissions require literal file paths")
        rules.append(f"--allow-tool=write({PurePosixPath(workdir) / value})")
    for value in profile["shell_commands"]:
        if (any(char in value for char in "*?[]{}(),;&|<>`$\\\r\n")
                or any(ord(char) < 32 for char in value)):
            raise ValueError("candidate shell permissions require literal simple commands")
        tokens = shlex.split(value)
        if (not tokens or any(token.startswith(("--allow-", "--deny-", "--trust-", "--skip-permission"))
                              or token in {"--yolo", "--no-ask-user"} for token in tokens)):
            raise ValueError("candidate shell permissions cannot change permission policy")
        rules.append(f"--allow-tool=shell({value})")
    return rules


def import_session(
    restoration: dict, history: Path, *, copilot: str, workdir: str,
    execute, receipt_path: Path, cli_identity: dict, import_path: str | None = None,
) -> str:
    receipt = {
        "schema_version": 1,
        "status": "FAIL",
        "source_session_id": restoration["source_session_id"],
        "cutoff_event_id": restoration["cutoff_event_id"],
        "skill_context": restoration["skill_context"],
        "limitations": restoration["limitations"],
        "history_sha256": hashlib.sha256(history.read_bytes()).hexdigest(),
        "cli_identity": cli_identity,
    }
    command = [
        copilot, "sessions", "import", import_path or str(history),
        "--working-directory", workdir, "--output", "json",
    ]
    receipt["command"] = command
    try:
        exit_code, output = execute(command)
        receipt.update(exit_code=exit_code, output=output)
        result = json.loads(output)
        receipt["native_result"] = result
        if (exit_code != 0 or not isinstance(result, dict) or result.get("ok") is not True
                or result.get("code") != "session_imported"):
            raise ValueError("native session import did not succeed")
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or str(uuid.UUID(session_id)) != session_id:
            raise ValueError("native session import returned an invalid session ID")
        receipt.update(status="PASS", session_id=session_id)
        return session_id
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as error:
        receipt["error"] = str(error)
        raise ValueError(f"native session import failed: {error}") from error
    finally:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
