"""Native historical-session import for the existing evaluation executors."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shlex
import sqlite3
import subprocess
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath


FIELDS = {"history_file", "source_session_id", "cutoff_event_id", "skill_context", "limitations"}
OPTIONAL_FIELDS = {"personal_instructions_file"}

RECORDED_INTERNAL_FIELDS = {
    "__copilotAutoApprovalHumanMessageIndex", "__copilotMessageSource",
}
RECORDED_ASSISTANT_FIELDS = {
    "reasoning_opaque": "reasoningOpaque", "reasoning_text": "reasoningText",
    "encrypted_content": "encryptedContent", "serverTools": "serverTools",
    "providerId": "providerId", "reasoningBlocks": "reasoningBlocks",
    "apiCallId": "apiCallId", "phase": "phase", "outputTokens": "outputTokens",
}


def completed_objective_state(store: dict) -> dict:
    return _objective_state(store, "completed")


def active_objective_state(store: dict) -> dict:
    return _objective_state(store, "active")


NORMALIZED_ACTIVE_CANARY = "public-command-normalized-active-v1"
CAPPED_PUBLIC_RESUME = "capped-public-resume-v1"


def normalized_active_canary(store: dict, source: str) -> None:
    active_objective_state(store)
    if (not re.fullmatch(r"/synthetic/[0-9a-f-]{36}/events\.jsonl", source)
            or store["current"]["continuationCount"] != 0
            or store["current"].get("creditLimit") != {
                "credits": 100, "creditsUsed": 0, "creditsUsedNanoAiu": "0"}):
        raise ValueError("Normalized active treatment requires the capped synthetic canary")


def capped_public_resume(store: dict, source: str, provenance: str) -> None:
    active_objective_state(store)
    synthetic = provenance == "synthetic-continuation-canary"
    if (provenance not in ("synthetic-continuation-canary", "source-bound-adapted-public-resume")
            or not isinstance(source, str) or not source.startswith("/")
            or not source.endswith("/events.jsonl")
            or (synthetic and not re.fullmatch(r"/synthetic/[0-9a-f-]{36}/events\.jsonl", source))
            or (not synthetic and source.startswith("/synthetic/"))
            or "creditLimit" in store["current"]):
        raise ValueError("Adapted capped public resume requires an initially uncapped active objective and matching provenance")


def _objective_state(store: dict, status: str) -> dict:
    required = {"id", "objective", "status", "autopilotOrigin", "continuationCount", "turnCount",
                "tokenCount", "creditCountNanoAiu", "resumeCount", "createdAt", "updatedAt"}
    optional = {"completionSummary", "pauseReason"}
    if status == "active":
        optional.add("creditLimit")
    current = store.get("current") if isinstance(store, dict) else None
    if (not isinstance(store, dict) or set(store) != {"version", "nextId", "current"}
            or type(store["version"]) is not int or store["version"] != 1
            or not isinstance(current, dict) or not required <= current.keys()
            or current.keys() - required - optional
            or current["status"] != status
            or not isinstance(current["objective"], str) or not current["objective"]
            or current["autopilotOrigin"] not in (None, "objective", "user")
            or any(type(value) is not int or not 1 <= value <= 2**53 - 1
                   for value in (store["nextId"], current["id"]))
            or store["nextId"] <= current["id"]
            or any(type(current[key]) is not int or not 0 <= current[key] <= 2**53 - 1
                   for key in ("continuationCount", "turnCount", "tokenCount", "resumeCount"))
            or not isinstance(current["creditCountNanoAiu"], str)
            or re.fullmatch(r"[0-9]+", current["creditCountNanoAiu"]) is None
            or int(current["creditCountNanoAiu"]) > 2**63 - 1
            or any(not isinstance(current[key], str)
                   for key in ("completionSummary", "pauseReason") if key in current)
            or (status == "active" and any(current.get(key)
                                          for key in ("completionSummary", "pauseReason")))):
        raise ValueError(f"Invalid {status} native objective store")
    for key in ("createdAt", "updatedAt"):
        value = current[key]
        try:
            if (not isinstance(value, str) or "T" not in value
                    or datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"Invalid {status} native objective timestamp") from None
    state = {key: current[key] for key in
             ("id", "objective", "status", "turnCount", "creditCountNanoAiu",
              "completionSummary", "pauseReason") if key in current}
    state["creditCountNanoAiu"] = str(int(current["creditCountNanoAiu"]))
    if "creditLimit" in current:
        limit = current["creditLimit"]
        if (not isinstance(limit, dict)
                or set(limit) - {"credits"} != {"creditsUsed", "creditsUsedNanoAiu"}
                or not isinstance(limit["creditsUsedNanoAiu"], str)
                or re.fullmatch(r"[0-9]+", limit["creditsUsedNanoAiu"]) is None
                or int(limit["creditsUsedNanoAiu"]) > 2**63 - 1
                or type(limit["creditsUsed"]) not in (int, float)
                or limit["creditsUsed"] != int(limit["creditsUsedNanoAiu"]) / 10**9
                or ("credits" in limit and (
                    type(limit["credits"]) not in (int, float)
                    or not math.isfinite(limit["credits"])
                    or not 0 < limit["credits"] <= (2**63 - 1) / 10**9))):
            raise ValueError("Invalid active native objective credit limit")
        state["creditLimit"] = {**limit, "creditsUsedNanoAiu": str(int(limit["creditsUsedNanoAiu"]))}
    return state


def recorded_autopilot_request(request: dict, event: dict, trigger: dict, store: dict) -> dict:
    active_objective_state(store)
    keys = {"event_id", "source_line_sha256", "current_datetime", "prompt", "source",
            "displayPrompt", "requiredTool", "agentMode", "objective_id", "objective_sha256"}
    current = store["current"]
    data = event.get("data", {})
    if (not isinstance(request, dict) or set(request) != keys
            or request["event_id"] != trigger["event_id"]
            or re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",
                            str(request["event_id"])) is None
            or request["source_line_sha256"] != trigger["source_line_sha256"]
            or event.get("type") != "user.message" or event.get("id") != request["event_id"]
            or event.get("timestamp") != trigger["timestamp"]
            or event.get("agentId") or data.get("parentToolCallId")
            or data.get("attachments") or data.get("source") != "autopilot"
            or data.get("delivery") != "idle" or data.get("agentMode") != "autopilot"
            or data.get("content") != "" or trigger["content"] != ""
            or request["source"] != "autopilot" or request["displayPrompt"] != ""
            or request["requiredTool"] != "task_complete" or request["agentMode"] != "autopilot"
            or type(request["objective_id"]) is not int or request["objective_id"] != current["id"]
            or request["objective_sha256"] != hashlib.sha256(current["objective"].encode()).hexdigest()
            or not isinstance(request["prompt"], str) or not request["prompt"].strip()
            or current["objective"] not in request["prompt"]
            or not isinstance(request["current_datetime"], str)
            or re.fullmatch(r"[0-9T:.+Z-]+", request["current_datetime"]) is None
            or data.get("transformedContent") != (
                f'<current_datetime>{request["current_datetime"]}</current_datetime>'
                + "\n\n" + request["prompt"])):
        raise ValueError("Recorded autopilot request/source/active objective correspondence differs")
    try:
        if datetime.fromisoformat(request["current_datetime"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ValueError("Invalid recorded autopilot datetime") from None
    return {key: request[key] for key in ("prompt", "source", "displayPrompt", "requiredTool", "agentMode")}


def recorded_field_digests(value: dict) -> dict:
    return {key: hashlib.sha256(json.dumps(
        item, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest() for key, item in value.items()}


def recorded_native_payloads(context: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Encode a materialized projection, not invented original event history."""
    keys = {
        "source", "source_cutoff_offset", "last_source_event", "source_bytes_consumed",
        "source_events_consumed", "compactions_consumed", "reader", "mode",
        "selected_model", "reasoning_effort", "context_tier", "original_user_messages",
        "invoked_skills", "chat_messages", "system_context_messages", "handoff_context",
    }
    if (not isinstance(context, dict) or set(context) != keys
            or context["handoff_context"] is not None
            or not isinstance(context["original_user_messages"], list)
            or any(not isinstance(value, str) for value in context["original_user_messages"])
            or not isinstance(context["chat_messages"], list) or len(context["chat_messages"]) < 2
            or not isinstance(context["system_context_messages"], list)
            or not isinstance(context["invoked_skills"], list)):
        raise ValueError("Unsupported recorded projection shape or handoff context")
    payloads, bindings, omitted = [], [], []

    def append(kind, data, collection, index, original):
        payloads.append({"type": kind, "data": data})
        bindings.append({
            "collection": collection, "index": index,
            "source_field_sha256": recorded_field_digests(original),
            "native_field_sha256": recorded_field_digests(data),
        })

    for index, skill in enumerate(context["invoked_skills"]):
        if (not isinstance(skill, dict) or not {
                "name", "path", "content", "allowedTools", "source", "invokedAtTurn"} <= skill.keys()
                or skill.keys() - {
                    "name", "path", "content", "allowedTools", "source", "invokedAtTurn",
                    "disableModelInvocation"}
                or any(not isinstance(skill[key], str) for key in ("name", "path", "content", "source"))
                or not skill["name"] or not isinstance(skill["allowedTools"], list)
                or any(not isinstance(tool, str) for tool in skill["allowedTools"])
                or ("disableModelInvocation" in skill and type(skill["disableModelInvocation"]) is not bool)
                or type(skill["invokedAtTurn"]) is not int or not 0 <= skill["invokedAtTurn"] < 2**53):
            raise ValueError("Unsupported recorded skill fields")
        append("skill.invoked", dict(skill), "invoked_skills", index, skill)
    names = [skill["name"] for skill in context["invoked_skills"]]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate retained recorded skill identity")
    for index, message in enumerate(context["system_context_messages"]):
        if (not isinstance(message, dict) or message.get("role") != "system"
                or not isinstance(message.get("content"), str)
                or message.keys() - {"role", "content", "metadata", "contentBlocks", "name"}):
            raise ValueError("Unsupported recorded system fields")
        append("system.message", dict(message), "system_context_messages", index, message)

    calls, completed = set(), set()
    for index, message in enumerate(context["chat_messages"]):
        if not isinstance(message, dict):
            raise ValueError("Invalid recorded message")
        role = message.get("role")
        content = message.get("content")
        retained = {key: value for key, value in message.items() if key not in RECORDED_INTERNAL_FIELDS}
        internal = {key: value for key, value in message.items() if key in RECORDED_INTERNAL_FIELDS}
        if internal:
            omitted.append({"collection": "chat_messages", "index": index,
                            "field_sha256": recorded_field_digests(internal),
                            "reason": "Runtime annotations removed before primary-model serialization"})
        if index == len(context["chat_messages"]) - 1:
            if (role != "user" or not isinstance(content, str)
                    or retained.keys() - {"role", "content", "copilotResponsesReasoning"}):
                raise ValueError("Recorded cutoff must end with one separate user trigger")
            continue
        if role == "developer":
            if set(retained) != {"role", "content"} or not isinstance(content, str) or not content.strip():
                raise ValueError("Unsupported recorded developer fields")
            append("instruction.update", {
                "authority": "host", "boundary": "nextModelRequest",
                "lifetime": "persistent", "fallback": "reject", "content": content,
            }, "chat_messages", index, message)
        elif role == "user":
            if (not isinstance(content, str)
                    or retained.keys() - {"role", "content", "copilotResponsesReasoning"}):
                raise ValueError("Unsupported recorded user fields")
            data = {"content": "", "transformedContent": content, "source": "system"}
            if "copilotResponsesReasoning" in retained:
                data["responsesReasoning"] = retained["copilotResponsesReasoning"]
            append("user.message", data, "chat_messages", index, message)
        elif role == "assistant":
            if ("content" not in retained or content == ""
                    or content is not None and not isinstance(content, str)
                    or retained.keys() - {"role", "content", "tool_calls"} - RECORDED_ASSISTANT_FIELDS.keys()
                    or ("tool_calls" in retained and (
                        not isinstance(retained["tool_calls"], list) or not retained["tool_calls"]))
                    or any(retained[key] is None for key in RECORDED_ASSISTANT_FIELDS if key in retained)
                    or any(not isinstance(retained[key], str) or not retained[key]
                           for key in ("reasoning_opaque", "reasoning_text", "encrypted_content")
                           if key in retained)):
                raise ValueError("Unsupported recorded assistant fields")
            data = {"content": content or ""}
            data.update({native: retained[source] for source, native in RECORDED_ASSISTANT_FIELDS.items()
                         if source in retained})
            requests = []
            for call in retained.get("tool_calls", []):
                if (not isinstance(call, dict) or set(call) != {"id", "type", call.get("type")}
                        or call["type"] not in {"function", "custom"}
                        or not isinstance(call["id"], str) or not call["id"] or call["id"] in calls):
                    raise ValueError("Unsupported or duplicate recorded tool call")
                body = call[call["type"]]
                argument_key = "arguments" if call["type"] == "function" else "input"
                if (not isinstance(body, dict) or set(body) != {"name", argument_key}
                        or not isinstance(body["name"], str)
                        or not isinstance(body[argument_key], str)):
                    raise ValueError("Unsupported recorded tool argument representation")
                calls.add(call["id"])
                requests.append({"toolCallId": call["id"], "type": call["type"],
                                 "name": body["name"], "arguments": body[argument_key]})
            if requests:
                data["toolRequests"] = requests
            append("assistant.message", data, "chat_messages", index, message)
        elif role == "tool":
            call_id = retained.get("tool_call_id")
            if (set(retained) != {"role", "content", "tool_call_id"} or not isinstance(content, str)
                    or call_id not in calls or call_id in completed):
                raise ValueError("Unsupported, orphaned or duplicate recorded tool result")
            completed.add(call_id)
            # The projection stores model text, not the original execution status.
            append("tool.execution_complete", {
                "toolCallId": call_id, "success": True, "result": {"content": content},
            }, "chat_messages", index, message)
        else:
            raise ValueError("Unsupported recorded message role")
    if calls != completed:
        raise ValueError("Incomplete recorded tool-call/result population")
    return payloads, bindings, omitted


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
            content = record.get("content")
            if record.get("success") is False and content is None:
                error = record.get("error")
                content = error.get("message") if isinstance(error, dict) else None
            if (call_id not in calls or call_id in completed
                    or type(record.get("success")) is not bool
                    or not isinstance(content, str)):
                raise ValueError("Invalid, reordered or duplicate public tool result")
            completed.add(call_id)
            projected = {"type": kind, "toolCallId": call_id, "success": record["success"],
                         "content": content}
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
            content = record.get("content")
            if content is None:
                content = record["error"]["message"]
            if record.get("error") is None:
                record["error"] = {"message": content}
            elif (not isinstance(record["error"], dict)
                  or record["error"].get("message") != content):
                raise ValueError("Public failed-result error differs from source content")
            record.pop("content", None)
    if semantic_projection(encoded) != projection:
        raise ValueError("Public import encoding changed source semantics")
    return encoded


SNAPSHOT_COLUMNS = {
    "todos": ["id", "title", "description", "status", "created_at", "updated_at"],
    "todo_deps": ["todo_id", "depends_on"],
    "live_proof_receipts": ["claim_id", "status", "scenario", "artifact_path",
                            "candidate_identity", "running_identity", "updated_at"],
}
OPERATIONAL_SNAPSHOT_COLUMNS = {
    **SNAPSHOT_COLUMNS,
    "session_state": ["key", "value"],
    "remote_v1_app_normal_answer_prior_ledger": [
        *SNAPSHOT_COLUMNS["live_proof_receipts"], "archived_at"],
}


def compile_task_snapshot(snapshot: dict) -> dict:
    """Compile explicit source rows; an in-memory check is not native consumption."""
    if (not isinstance(snapshot, dict) or set(snapshot) != {"schemas", "rows", "queries"}
            or not isinstance(snapshot["schemas"], dict) or not isinstance(snapshot["rows"], dict)
            or set(snapshot["schemas"]) not in (set(SNAPSHOT_COLUMNS), set(OPERATIONAL_SNAPSHOT_COLUMNS))
            or set(snapshot["rows"]) != set(snapshot["schemas"])
            or not isinstance(snapshot["queries"], list) or not snapshot["queries"]):
        raise ValueError("Invalid historical task snapshot shape")
    tables = {table: columns for table, columns in OPERATIONAL_SNAPSHOT_COLUMNS.items()
              if table in snapshot["schemas"]}
    def quote(value):
        if value is None:
            return "NULL"
        if not isinstance(value, str) or "\0" in value:
            raise ValueError("Snapshot values must be explicit text or NULL")
        return "'" + value.replace("'", "''") + "'"

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        for table, columns in tables.items():
            schema = snapshot["schemas"][table]
            if not isinstance(schema, str) or not re.match(
                    rf"^\s*CREATE TABLE (?:IF NOT EXISTS )?{table}\s*\(", schema, re.I):
                raise ValueError("Snapshot schema must create only its declared table")
            connection.execute(schema)
            info = connection.execute(f"PRAGMA table_info({table})").fetchall()
            archived = table == "remote_v1_app_normal_answer_prior_ledger"
            types = ["TEXT"] * len(columns)
            if archived:
                types[-1] = ""
            if [row[1] for row in info] != columns or [row[2].upper() for row in info] != types:
                raise ValueError("Snapshot columns/types differ from the source contract")
            primary = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
            expected_primary = [] if archived else columns if table == "todo_deps" else columns[:1]
            if primary != expected_primary:
                raise ValueError("Snapshot primary keys differ from the source contract")
            required = {"todos": {"title"}, "todo_deps": set(columns),
                        "live_proof_receipts": {"status", "scenario", "artifact_path"},
                        "session_state": set(), "remote_v1_app_normal_answer_prior_ledger": set()}[table]
            if {row[1] for row in info if row[3]} != required:
                raise ValueError("Snapshot NOT NULL constraints differ from source")
            if table not in SNAPSHOT_COLUMNS:
                if (connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
                        or any(row[3] != "pk" for row in connection.execute(f"PRAGMA index_list({table})"))):
                    raise ValueError("Snapshot keys differ from source")
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
        for table, columns in tables.items():
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
                statements = []
                pending = ""
                for character in query["query"]:
                    pending += character
                    if character == ";" and sqlite3.complete_statement(pending):
                        statements.append(pending)
                        pending = ""
                if pending.strip():
                    statements.append(pending)
                returned_rows = sum(len(connection.execute(statement).fetchall())
                                    for statement in statements)
                if returned_rows != query["expected_rows"]:
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
