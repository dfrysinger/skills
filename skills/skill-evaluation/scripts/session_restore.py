"""Native historical-session import for the existing evaluation executors."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sqlite3
import subprocess
import uuid
from pathlib import Path, PurePosixPath


FIELDS = {"history_file", "source_session_id", "cutoff_event_id", "skill_context", "limitations"}
OPTIONAL_FIELDS = {"personal_instructions_file"}


def semantic_projection(records: list[dict]) -> list[dict]:
    """Validate and project public root records without importing a native session."""
    if (not isinstance(records, list) or not records
            or records[0].get("type") != "session" or records[0].get("version") != 1
            or not isinstance(records[0].get("externalId"), str)
            or not isinstance(records[0].get("createdAt"), str)):
        raise ValueError("Invalid public semantic session header")
    result, ids, calls, completed = [], set(), set(), set()
    for record in records[1:]:
        if (not isinstance(record, dict) or not isinstance(record.get("id"), str)
                or record["id"] in ids or record.get("agentId")
                or record.get("parentToolCallId")):
            raise ValueError("Invalid, duplicate or non-root semantic record")
        ids.add(record["id"])
        kind = record.get("type")
        if kind == "message":
            parts = record.get("content")
            if (record.get("role") not in {"user", "assistant"} or not isinstance(parts, list)
                    or any(not isinstance(part, dict) or set(part) != {"type", "text"}
                           or part["type"] != "text" or not isinstance(part["text"], str)
                           for part in parts)):
                raise ValueError("Unsupported public message content")
            projected = {"type": kind, "role": record["role"],
                         "content": "".join(part["text"] for part in parts)}
        elif kind == "tool-call":
            if (not isinstance(record.get("name"), str)
                    or not isinstance(record.get("arguments"), (dict, str))):
                raise ValueError("Invalid public tool request")
            calls.add(record["id"])
            projected = {"type": kind, "id": record["id"], "name": record["name"],
                         "arguments": record["arguments"]}
        elif kind == "tool-result":
            call_id = record.get("toolCallId")
            if (call_id not in calls or call_id in completed
                    or type(record.get("success")) is not bool
                    or not isinstance(record.get("content"), str)):
                raise ValueError("Invalid, reordered or duplicate public tool result")
            completed.add(call_id)
            projected = {"type": kind, "toolCallId": call_id, "success": record["success"],
                         "content": record["content"]}
        else:
            raise ValueError("Unsupported public semantic record")
        result.append(projected)
    if calls != completed:
        raise ValueError("Incomplete public tool request/result correspondence")
    return result


def public_import_records(records: list[dict]) -> list[dict]:
    """Add required importer error metadata without changing source semantics."""
    projection = semantic_projection(records)
    encoded = [dict(record) for record in records]
    for record in encoded:
        if record["type"] == "tool-result" and not record["success"]:
            if record.get("error") is None:
                record["error"] = {"message": record["content"]}
            elif (not isinstance(record["error"], dict)
                  or record["error"].get("message") != record["content"]):
                raise ValueError("Public failed-result error differs from source content")
    if semantic_projection(encoded) != projection:
        raise ValueError("Public import encoding changed source semantics")
    return encoded


SNAPSHOT_COLUMNS = {
    "todos": ["id", "title", "description", "status", "created_at", "updated_at"],
    "todo_deps": ["todo_id", "depends_on"],
    "live_proof_receipts": ["claim_id", "status", "scenario", "artifact_path",
                            "candidate_identity", "running_identity", "updated_at"],
}


def compile_task_snapshot(snapshot: dict) -> dict:
    """Compile explicit source rows; an in-memory check is not native consumption."""
    if (not isinstance(snapshot, dict) or set(snapshot) != {"schemas", "rows", "queries"}
            or set(snapshot["schemas"]) != set(SNAPSHOT_COLUMNS)
            or set(snapshot["rows"]) != set(SNAPSHOT_COLUMNS)
            or not isinstance(snapshot["queries"], list) or len(snapshot["queries"]) != 4):
        raise ValueError("Invalid historical task snapshot shape")
    def quote(value):
        if value is None:
            return "NULL"
        if not isinstance(value, str) or "\0" in value:
            raise ValueError("Snapshot values must be explicit text or NULL")
        return "'" + value.replace("'", "''") + "'"

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        for table, columns in SNAPSHOT_COLUMNS.items():
            schema = snapshot["schemas"][table]
            if not isinstance(schema, str) or not re.match(
                    rf"^\s*CREATE TABLE (?:IF NOT EXISTS )?{table}\s*\(", schema, re.I):
                raise ValueError("Snapshot schema must create only its declared table")
            connection.execute(schema)
            info = connection.execute(f"PRAGMA table_info({table})").fetchall()
            if [row[1] for row in info] != columns or any(row[2].upper() != "TEXT" for row in info):
                raise ValueError("Snapshot columns/types differ from the source contract")
            primary = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
            expected_primary = columns if table == "todo_deps" else columns[:1]
            if primary != expected_primary:
                raise ValueError("Snapshot primary keys differ from the source contract")
            required = {"todos": {"title"}, "todo_deps": set(columns),
                        "live_proof_receipts": {"status", "scenario", "artifact_path"}}[table]
            if {row[1] for row in info if row[3]} != required:
                raise ValueError("Snapshot NOT NULL constraints differ from source")
        foreign = connection.execute("PRAGMA foreign_key_list(todo_deps)").fetchall()
        if ({(row[2], row[3], row[4]) for row in foreign}
                != {("todos", "todo_id", "id"), ("todos", "depends_on", "id")}
                or len(foreign) != 2):
            raise ValueError("Snapshot foreign keys differ from source")
        try:
            connection.execute("INSERT INTO todos(id,title,status) VALUES('check','check','invalid')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise ValueError("Snapshot status CHECK is missing")
        transaction = ["BEGIN;"]
        comparisons = []
        counts = {}
        for table, columns in SNAPSHOT_COLUMNS.items():
            rows = snapshot["rows"][table]
            if not isinstance(rows, list) or not rows:
                raise ValueError("Historical snapshot tables must have explicit rows")
            values = []
            for ordinal, row in enumerate(rows, 1):
                if not isinstance(row, dict) or set(row) != set(columns):
                    raise ValueError("Snapshot row omits or adds columns")
                encoded = ",".join(quote(row[column]) for column in columns)
                statement = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({encoded});"
                connection.execute(statement)
                transaction.append(statement)
                values.append(f"({ordinal},{encoded})")
            counts[table] = len(rows)
            fields = "ordinal," + ",".join(columns)
            actual = "rowid," + ",".join(columns)
            comparisons.append(
                f"WITH expected({fields}) AS (VALUES {','.join(values)}), "
                f"missing AS (SELECT * FROM expected EXCEPT SELECT {actual} FROM {table}), "
                f"extra AS (SELECT {actual} FROM {table} EXCEPT SELECT * FROM expected) "
                "SELECT * FROM missing UNION ALL SELECT * FROM extra")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Snapshot foreign key violations")
        for query in snapshot["queries"]:
            if (not isinstance(query, dict) or set(query) != {"query", "expected_text", "expected_rows"}
                    or not isinstance(query["query"], str)
                    or not re.match(r"^\s*(SELECT|WITH)\b", query["query"], re.I)
                    or not isinstance(query["expected_text"], str)
                    or type(query["expected_rows"]) is not int or query["expected_rows"] < 0):
                raise ValueError("Invalid source query readback")
            connection.set_authorizer(lambda action, *args:
                sqlite3.SQLITE_OK if action in {
                    sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                    sqlite3.SQLITE_RECURSIVE,
                } else sqlite3.SQLITE_DENY)
            try:
                if len(connection.execute(query["query"]).fetchall()) != query["expected_rows"]:
                    raise ValueError("Source query row count differs from snapshot")
            finally:
                connection.set_authorizer(None)
        schemas = dict(connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table'").fetchall())
        transaction.append("COMMIT;")
        return {"schemas": schemas, "transaction": "\n".join(transaction),
                "comparisons": comparisons, "row_counts": counts, "queries": snapshot["queries"],
                "source": snapshot}
    except sqlite3.Error as error:
        raise ValueError(f"Invalid historical snapshot SQL: {error}") from error
    finally:
        connection.close()


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
        if (not isinstance(restoration, dict) or not FIELDS <= set(restoration)
                or set(restoration) - FIELDS - OPTIONAL_FIELDS):
            raise ValueError("session_restore requires exactly its declared fields")
        if "personal_instructions_file" in restoration:
            if definition.get("case_type", "prose") != "prose":
                raise ValueError("personal instructions are supported only for restored read-only cases")
            relative = relative_path(restoration["personal_instructions_file"])
            packet = root / (phase["id"] if frozen else phase["evidence_dir"])
            source = packet / relative
            if (source.is_symlink() or not source.is_file()
                    or not source.resolve().is_relative_to(packet.resolve())):
                raise ValueError("personal instructions must be a regular file beneath their packet")
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
    plugin_dir: str | None = None,
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
    if plugin_dir is not None:
        command[1:1] = ["--plugin-dir", plugin_dir]
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
