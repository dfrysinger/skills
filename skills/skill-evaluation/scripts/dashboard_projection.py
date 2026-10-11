"""Safe read-only projections for the skill-evaluation dashboard."""

from __future__ import annotations

import difflib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import evaluation_history
from dashboard_state import (
    campaign_registration,
    ensure_state_root,
    event_records,
    extension_records,
    live_state_enabled,
    parse_instant,
    read_skill_snapshot,
    regular_json,
    session_records,
)
from skill_eval import digest, frozen_case_path, load_corpus


OUTCOMES = ("PASS", "FAIL", "UNANSWERABLE", "INVALID", "BLOCKED", "ERROR")
COST_FIELDS = {
    "credits",
    "observed_credits",
    "premium_requests",
    "observed_premium_requests",
    "complete",
    "attempts",
    "complete_attempts",
    "known_subtotal_attempts",
    "known_premium_attempts",
    "complete_premium_attempts",
    "sessions",
    "known_credit_sessions",
    "complete_credit_sessions",
}
POPULATION_FIELDS = {
    "case_id",
    "case_revision",
    "case_type",
    "arm",
    "treatment_id",
    "treatment_identity",
    "runner_kind",
    "adapter_digest",
    "entry_skill",
    "intervention_policy",
    "compatibility_requirements",
    "compatibility_status",
    "skill_identity",
    "plugin_identity",
    "lineage_snapshot_id",
    "lineage_campaign_id",
    "lineage_skills",
    "harness_identity",
    "model",
    "effort",
    "timeout_seconds",
    "max_attempts",
    "image",
    "quality_review",
    "evaluator_models",
}
DEFAULT_STALE_SECONDS = 120


def safe_cost(value: object) -> dict:
    if not isinstance(value, dict) or set(value) - COST_FIELDS:
        raise ValueError("history cost summary has unsupported fields")
    return {field: value[field] for field in sorted(value)}


def safe_population_identity(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != POPULATION_FIELDS:
        raise ValueError("history population identity has unsupported fields")
    return {field: value[field] for field in sorted(POPULATION_FIELDS)}


def safe_quality(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get("complete")) is not bool:
        raise ValueError("history quality summary is malformed")
    reviewers = value.get("reviewers")
    if not isinstance(reviewers, list):
        raise ValueError("history quality reviewers are malformed")
    result = []
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            raise ValueError("history quality reviewer is malformed")
        status = reviewer.get("status")
        judgment = reviewer.get("judgment")
        if status not in {"completed", "failed", "not_run"}:
            raise ValueError("history quality reviewer status is invalid")
        if judgment is not None and not isinstance(judgment, str):
            raise ValueError("history quality judgment is invalid")
        result.append({
            "model": reviewer.get("model"),
            "status": status,
            "judgment": judgment,
        })
    return {"complete": value["complete"], "reviewers": result}


def safe_attempt(row: dict) -> dict:
    correctness = row.get("correctness")
    if correctness not in OUTCOMES:
        raise ValueError("history attempt outcome is invalid")
    population = safe_population_identity(row.get("population"))
    accounting = row.get("accounting")
    if not isinstance(accounting, dict):
        raise ValueError("history accounting is malformed")
    source_id = row.get("run_path")
    if source_id is None:
        source_id = f"{row['experiment_id']} attempt {row['attempt']}"
    elif (
        not isinstance(source_id, str)
        or not source_id.startswith("runs/")
        or ".." in Path(source_id).parts
    ):
        raise ValueError("history source path is invalid")
    return {
        "source": {"authority": "immutable-artifact", "id": source_id},
        "attempt": row.get("attempt"),
        "experiment_id": row.get("experiment_id"),
        "suite_id": row.get("suite_path"),
        "population": population,
        "correctness": correctness,
        "behavioral_verdict": row.get("behavioral_verdict"),
        "treatment_artifacts_verified": bool(
            row.get("treatment_artifacts_verified")
        ),
        "accounting_available": bool(row.get("accounting_available")),
        "candidate_spend": safe_cost(accounting.get("candidate", {}))
        if accounting else None,
        "evaluation_spend": safe_cost(accounting.get("evaluation", {}))
        if accounting else None,
        "total_spend": safe_cost(accounting.get("total", {}))
        if accounting else None,
        "measurement_error_count": len(row.get("measurement_errors", [])),
        "quality": safe_quality(row.get("quality")),
        "started_at": row.get("started_at"),
        "elapsed_seconds": row.get("elapsed_seconds"),
        "legacy_execution_elapsed_seconds": row.get(
            "legacy_execution_elapsed_seconds"
        ),
        "timing_status": row.get("timing_status"),
    }


def safe_population(row: dict) -> dict:
    result = {
        "identity": row.get("identity"),
        "population": safe_population_identity(row.get("population")),
    }
    for field in (
        "attempts",
        "first_attempts",
        "first_attempt_passes",
        "valid_first_attempts",
        "invalid_first_attempts",
        "pass_at_1",
        "execution_coverage",
        "eventual_executable_passes",
        "retry_assisted_executable_passes",
        "credits_per_successful_first_attempt",
        "ratio_population",
    ):
        result[field] = row.get(field)
    for field in (
        "candidate_spend",
        "evaluation_spend",
        "total_spend",
        "first_attempt_spend",
        "retry_spend",
        "invalid_spend",
        "unsuccessful_spend",
    ):
        result[field] = safe_cost(row.get(field))
    return result


def safe_case(corpus_root: Path, case_id: str, attempts: list[dict]) -> dict:
    case_path = corpus_root / "cases" / case_id / "case.json"
    definition = regular_json(case_path, f"case {case_id}")
    if definition.get("case_id") != case_id:
        raise ValueError(f"case identity mismatch: {case_id}")
    target_skill = definition.get("target_skill")
    if not isinstance(target_skill, str) or not target_skill:
        raise ValueError(f"case target skill is unavailable: {case_id}")
    case_type = (
        "repository-task"
        if (case_path.parent / "repository").is_dir()
        else "prose"
    )
    outcomes = {
        outcome: sum(
            row["correctness"] == outcome
            and row["population"]["case_id"] == case_id
            for row in attempts
        )
        for outcome in OUTCOMES
    }
    return {
        "case_id": case_id,
        "case_type": case_type,
        "target_skill": target_skill,
        "status": "not_run" if not any(outcomes.values()) else "has_results",
        "outcomes": outcomes if any(outcomes.values()) else None,
        "source": {
            "authority": "immutable-artifact",
            "id": f"cases/{case_id}/case.json",
        },
    }


def case_revisions(corpus_root: Path, case_ids: list[str]) -> dict[str, str | None]:
    result = {}
    for case_id in case_ids:
        try:
            manifest = frozen_case_path(corpus_root, case_id) / "case-manifest.json"
            result[case_id] = (
                digest(manifest)
                if manifest.is_file() and not manifest.is_symlink()
                else None
            )
        except (OSError, ValueError, json.JSONDecodeError):
            result[case_id] = None
    return result


def snapshot_manifests(corpus_root: Path) -> tuple[dict[str, dict], list[dict]]:
    root = corpus_root / ".skill-evaluation-ui" / "snapshots"
    if not root.exists():
        return {}, []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("dashboard snapshots path is invalid")
    snapshots = {}
    invalid = []
    for path in sorted(root.iterdir()):
        if path.name.startswith("."):
            continue
        try:
            manifest = read_skill_snapshot(corpus_root, path.name)
            snapshots[manifest["snapshot_id"]] = manifest
        except (OSError, ValueError, json.JSONDecodeError):
            invalid.append({
                "source": f"snapshots/{path.name}",
                "reason": "snapshot_invalid",
            })
    return snapshots, invalid


def snapshot_file_map(manifest: dict) -> dict[tuple[str, str], dict]:
    return {
        (skill["name"], item["path"]): item
        for skill in manifest["skills"]
        for item in skill["files"]
    }


def snapshot_file_bytes(
    corpus_root: Path,
    snapshot_id: str,
    skill: str,
    path: str,
) -> bytes:
    source = (
        corpus_root
        / ".skill-evaluation-ui"
        / "snapshots"
        / snapshot_id
        / "files"
        / skill
        / path
    )
    if source.is_symlink() or not source.is_file():
        raise ValueError("snapshot comparison file is unavailable")
    return source.read_bytes()


def compare_snapshots(
    corpus_root: Path,
    before: dict,
    after: dict,
) -> dict:
    before_files = snapshot_file_map(before)
    after_files = snapshot_file_map(after)
    changes = []
    totals = {
        "added_files": 0,
        "removed_files": 0,
        "modified_files": 0,
        "unchanged_files": 0,
        "added_lines": 0,
        "removed_lines": 0,
        "byte_delta": 0,
        "binary_changes": 0,
    }
    for key in sorted(set(before_files) | set(after_files)):
        old = before_files.get(key)
        new = after_files.get(key)
        if old is None:
            status = "added"
            totals["added_files"] += 1
        elif new is None:
            status = "removed"
            totals["removed_files"] += 1
        elif old["sha256"] == new["sha256"] and old["mode"] == new["mode"]:
            status = "unchanged"
            totals["unchanged_files"] += 1
        else:
            status = "modified"
            totals["modified_files"] += 1
        if status == "unchanged":
            continue
        old_bytes = (
            snapshot_file_bytes(
                corpus_root,
                before["snapshot_id"],
                key[0],
                key[1],
            )
            if old is not None
            else b""
        )
        new_bytes = (
            snapshot_file_bytes(
                corpus_root,
                after["snapshot_id"],
                key[0],
                key[1],
            )
            if new is not None
            else b""
        )
        totals["byte_delta"] += len(new_bytes) - len(old_bytes)
        text = bool((old is None or old["text"]) and (new is None or new["text"]))
        diff = None
        if text:
            old_lines = old_bytes.decode("utf-8").splitlines(keepends=True)
            new_lines = new_bytes.decode("utf-8").splitlines(keepends=True)
            generated = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=(
                    f"{key[0]}/{key[1]}@{before['snapshot_id'][:12]}"
                ),
                tofile=(
                    f"{key[0]}/{key[1]}@{after['snapshot_id'][:12]}"
                ),
                lineterm="\n",
            ))
            diff = "".join(generated)
            totals["added_lines"] += sum(
                line.startswith("+") and not line.startswith("+++")
                for line in generated
            )
            totals["removed_lines"] += sum(
                line.startswith("-") and not line.startswith("---")
                for line in generated
            )
        else:
            totals["binary_changes"] += 1
        changes.append({
            "skill": key[0],
            "path": key[1],
            "status": status,
            "before": old,
            "after": new,
            "binary": not text,
            "diff": diff,
        })
    return {
        "from_snapshot_id": before["snapshot_id"],
        "to_snapshot_id": after["snapshot_id"],
        "summary": totals,
        "files": changes,
    }


def graph_reaches(
    edges: dict[str, set[str]],
    start: str,
    target: str,
) -> bool:
    pending = [start]
    seen = set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        pending.extend(edges.get(node, set()))
    return False


def descendant_exists(
    node: str,
    candidates: set[str],
    children: dict[str, set[str]],
) -> bool:
    pending = list(children.get(node, set()))
    seen = set()
    while pending:
        child = pending.pop()
        if child in seen:
            continue
        seen.add(child)
        if child in candidates:
            return True
        pending.extend(children.get(child, set()))
    return False


def role_projection(
    role: str,
    candidates: set[str],
    children: dict[str, set[str]],
    *,
    authority: str,
) -> dict:
    tips = sorted(
        snapshot
        for snapshot in candidates
        if not descendant_exists(snapshot, candidates, children)
    )
    if len(tips) == 1:
        return {
            "status": "available",
            "snapshot_id": tips[0],
            "authority": authority,
        }
    return {
        "status": "conflicted" if tips else "unavailable",
        "snapshot_id": None,
        "snapshot_ids": tips,
        "authority": authority,
    }


def lineage_projection(
    corpus_root: Path,
    registration: dict,
    corpus: dict,
    report: dict,
    attempts: list[dict],
    sessions: list[dict],
    live_attempts: list[dict],
) -> tuple[dict, list[dict], list[dict]]:
    snapshots, invalid = snapshot_manifests(corpus_root)
    records, record_conflicts, invalid_records = extension_records(corpus_root)
    invalid.extend(invalid_records)
    records = [
        record
        for record in records
        if record["campaign_id"] == registration["campaign_id"]
    ]
    declarations = []
    progress_records = []
    target_skills = registration["target_skills"]
    for record in records:
        snapshot_id = record["subject"]["snapshot_id"]
        snapshot = snapshots.get(snapshot_id)
        if snapshot is None:
            invalid.append({
                "source": f"event:{record['event_id']}",
                "reason": "referenced snapshot is unavailable",
            })
            continue
        if record["event_type"] == "lineage_declared":
            payload = record["payload"]
            if (
                set(payload["roles"]) - {"experimental"}
                and [item["name"] for item in snapshot["skills"]] != target_skills
            ):
                invalid.append({
                    "source": f"event:{record['event_id']}",
                    "reason": "campaign role snapshot does not cover target skills",
                })
                continue
            missing_parent = next(
                (
                    parent["snapshot_id"]
                    for parent in payload["parents"]
                    if parent["snapshot_id"] not in snapshots
                ),
                None,
            )
            if missing_parent is not None:
                invalid.append({
                    "source": f"event:{record['event_id']}",
                    "reason": f"parent snapshot is unavailable: {missing_parent}",
                })
                continue
            declarations.append(record)
        else:
            progress_records.append(record)

    edges: dict[str, set[str]] = {}
    for record in declarations:
        edges.setdefault(record["subject"]["snapshot_id"], set()).update(
            parent["snapshot_id"]
            for parent in record["payload"]["parents"]
        )
    cyclic_records = {
        record["event_id"]
        for record in declarations
        if any(
            graph_reaches(
                edges,
                parent["snapshot_id"],
                record["subject"]["snapshot_id"],
            )
            for parent in record["payload"]["parents"]
        )
    }
    if cyclic_records:
        kept = []
        for record in declarations:
            if record["event_id"] in cyclic_records:
                invalid.append({
                    "source": f"event:{record['event_id']}",
                    "reason": "lineage declaration participates in a cycle",
                })
            else:
                kept.append(record)
        declarations = kept
        edges = {}
        for record in declarations:
            edges.setdefault(record["subject"]["snapshot_id"], set()).update(
                parent["snapshot_id"]
                for parent in record["payload"]["parents"]
            )

    children: dict[str, set[str]] = {}
    for child, parents in edges.items():
        for parent in parents:
            children.setdefault(parent, set()).add(child)
    role_candidates = {role: set() for role in (
        "original",
        "published",
        "integrated",
        "experimental",
        "released",
    )}
    parents_by_snapshot = {}
    summaries = {}
    for record in declarations:
        snapshot_id = record["subject"]["snapshot_id"]
        role_candidates_snapshot = record["payload"]["roles"]
        for role in role_candidates_snapshot:
            role_candidates[role].add(snapshot_id)
        parents_by_snapshot.setdefault(snapshot_id, []).extend(
            record["payload"]["parents"]
        )
        summaries[snapshot_id] = record["payload"]["summary"]

    current_revisions = case_revisions(corpus_root, corpus["cases"])
    passing = set()
    for suite in report.get("lineage_suites", []):
        lineage = suite["lineage_identity"]
        snapshot = snapshots.get(lineage["snapshot_id"])
        if (
            lineage["campaign_id"] == registration["campaign_id"]
            and snapshot is not None
            and [item["name"] for item in snapshot["skills"]] == target_skills
            and suite["result"] == "PASS"
            and suite["case_revisions"] == current_revisions
            and {
                item["case_id"] for item in suite["cases"]
            } == set(corpus["cases"])
            and all(item["result"] == "PASS" for item in suite["cases"])
        ):
            passing.add(lineage["snapshot_id"])

    roles = {
        role: role_projection(
            role,
            candidates,
            children,
            authority="workflow-declaration",
        )
        for role, candidates in role_candidates.items()
    }
    roles["passing"] = role_projection(
        "passing",
        passing,
        children,
        authority="immutable-suite",
    )
    associated = (
        roles["integrated"]["snapshot_id"]
        if roles["integrated"]["status"] == "available"
        else roles["released"]["snapshot_id"]
        if roles["released"]["status"] == "available"
        else None
    )

    pairs = set()
    for child, parents in edges.items():
        pairs.update((parent, child) for parent in parents)
    for before_role, after_role in (
        ("original", "integrated"),
        ("published", "integrated"),
        ("integrated", "released"),
    ):
        before = roles[before_role]
        after = roles[after_role]
        if before["status"] == after["status"] == "available":
            if before["snapshot_id"] != after["snapshot_id"]:
                pairs.add((before["snapshot_id"], after["snapshot_id"]))
    comparisons = [
        compare_snapshots(corpus_root, snapshots[before], snapshots[after])
        for before, after in sorted(pairs)
    ]
    comparisons_by_pair = {
        (item["from_snapshot_id"], item["to_snapshot_id"]): item
        for item in comparisons
    }

    tasks = []
    attention = []
    for case_id in corpus["cases"]:
        revision = current_revisions[case_id]
        relevant_attempts = [
            row for row in attempts
            if row["population"]["case_id"] == case_id
            and row["population"]["case_revision"] == revision
        ]
        latest_attempt = max(
            relevant_attempts,
            key=lambda item: (
                item.get("started_at") or "",
                item["source"]["id"],
            ),
            default=None,
        )
        task_sessions = [
            item for item in sessions if item["case_id"] == case_id
        ]
        task_live_attempts = [
            item for item in live_attempts if item["case_id"] == case_id
        ]
        matching = [
            record for record in progress_records
            if record["subject"] == {
                "snapshot_id": associated,
                "case_id": case_id,
                "case_revision": revision,
            }
        ] if associated is not None and revision is not None else []
        progress = {
            "status": "unavailable",
            "snapshot_id": associated,
            "case_revision": revision,
        }
        if matching:
            newest = max(parse_instant(record["observed_at"]) for record in matching)
            current = [
                record for record in matching
                if parse_instant(record["observed_at"]) == newest
            ]
            payloads = {
                evaluation_history.fingerprint(record["payload"])
                for record in current
            }
            if len(payloads) > 1:
                progress = {
                    "status": "conflicted",
                    "snapshot_id": associated,
                    "case_revision": revision,
                    "event_ids": sorted(record["event_id"] for record in current),
                }
            else:
                record = sorted(current, key=lambda item: item["event_id"])[0]
                payload = record["payload"]
                progress = {
                    "status": "available",
                    "snapshot_id": associated,
                    "case_revision": revision,
                    "event_id": record["event_id"],
                    "observed_at": record["observed_at"],
                    "frontier": payload["frontier"],
                    "classification": payload["classification"],
                    "movement": payload["movement"],
                    "summary": payload["summary"],
                    "uptake": payload["uptake"],
                    "blocker": payload["blocker"],
                    "next_action": payload["next_action"],
                    "sources": payload["sources"],
                    "comparison_snapshot_id": payload["comparison_snapshot_id"],
                }
        comparison = None
        if progress.get("status") == "available":
            comparison_id = progress.get("comparison_snapshot_id")
            if comparison_id is not None:
                comparison = comparisons_by_pair.get((comparison_id, associated))
                if comparison is None and comparison_id in snapshots:
                    comparison = compare_snapshots(
                        corpus_root,
                        snapshots[comparison_id],
                        snapshots[associated],
                    )
        tasks.append({
            "case_id": case_id,
            "case_revision": revision,
            "associated_snapshot_id": associated,
            "outcome": latest_attempt["correctness"] if latest_attempt else None,
            "attempts": relevant_attempts,
            "sessions": task_sessions,
            "live_attempts": task_live_attempts,
            "progress": progress,
            "comparison": comparison,
        })
        if progress.get("status") == "available" and progress.get("blocker"):
            attention.append({
                "priority": 0,
                "kind": "blocked",
                "case_id": case_id,
                "summary": progress["blocker"],
            })
        elif progress.get("status") == "conflicted":
            attention.append({
                "priority": 1,
                "kind": "conflicted",
                "case_id": case_id,
                "summary": "Current progress records conflict",
            })
        elif latest_attempt and latest_attempt["correctness"] in {
            "FAIL",
            "UNANSWERABLE",
        }:
            attention.append({
                "priority": 2,
                "kind": "failing",
                "case_id": case_id,
                "summary": f"Current outcome is {latest_attempt['correctness']}",
            })
        elif any(
            item["state"] == "stale"
            for item in [*task_sessions, *task_live_attempts]
        ):
            attention.append({
                "priority": 3,
                "kind": "stale",
                "case_id": case_id,
                "summary": "Active local work is stale",
            })
        elif progress.get("status") == "unavailable" and (
            latest_attempt
            and latest_attempt["correctness"] in {"FAIL", "UNANSWERABLE"}
            or any(
                item["state"] in {"active", "blocked", "stale"}
                for item in [*task_sessions, *task_live_attempts]
            )
        ):
            attention.append({
                "priority": 4,
                "kind": "missing_progress",
                "case_id": case_id,
                "summary": "Current work has no task-progress record",
            })
    attention.sort(key=lambda item: (item["priority"], item["case_id"]))
    for item in attention:
        item.pop("priority")

    snapshot_rows = []
    for snapshot_id, manifest in sorted(snapshots.items()):
        snapshot_rows.append({
            "snapshot_id": snapshot_id,
            "skills": [
                {
                    "name": skill["name"],
                    "sha256": skill["sha256"],
                    "evaluator_skill_identity": skill["evaluator_skill_identity"],
                    "file_count": len(skill["files"]),
                    "bytes": sum(item["bytes"] for item in skill["files"]),
                    "lines": sum(
                        item["lines"] or 0 for item in skill["files"]
                    ),
                }
                for skill in manifest["skills"]
            ],
            "roles": sorted(
                role for role, candidates in role_candidates.items()
                if snapshot_id in candidates
            ) + (["passing"] if snapshot_id in passing else []),
            "parents": sorted(
                parents_by_snapshot.get(snapshot_id, []),
                key=lambda item: (item["snapshot_id"], item["relation"]),
            ),
            "summary": summaries.get(snapshot_id),
        })
    available = bool(snapshot_rows or records or invalid or record_conflicts)
    return {
        "status": "available" if available else "unavailable",
        "roles": roles,
        "snapshots": snapshot_rows,
        "comparisons": comparisons,
        "conflicts": record_conflicts,
        "invalid": invalid,
    }, tasks, attention


def unavailable_projection(registration: dict, reason: str) -> dict:
    return {
        "schema_version": 1,
        "campaign": {
            "campaign_id": registration["campaign_id"],
            "corpus_name": registration["corpus_name"],
            "target_skills": registration["target_skills"],
            "availability": "unavailable",
            "unavailable_reason": reason,
        },
        "cases": [],
        "attempts": [],
        "populations": [],
        "sessions": [],
        "live_attempts": [],
        "events": [],
        "conflicts": [],
        "lineage": {
            "status": "unavailable",
            "roles": {},
            "snapshots": [],
            "comparisons": [],
            "conflicts": [],
            "invalid": [],
        },
        "task_details": [],
        "attention": [],
        "availability": {
            "completed_history": "unavailable",
            "live_sessions": "unavailable",
            "live_attempts": "unavailable",
            "cloud_activity": "unavailable",
            "lineage": "unavailable",
            "experiments": "unavailable",
            "ablation": "unavailable",
        },
    }


def stale_seconds() -> int:
    raw = os.environ.get(
        "SKILL_EVAL_DASHBOARD_STALE_SECONDS",
        str(DEFAULT_STALE_SECONDS),
    )
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("dashboard stale threshold must be an integer") from None
    if value < 1:
        raise ValueError("dashboard stale threshold must be positive")
    return value


def age_seconds(timestamp: str, now: datetime) -> float:
    observed = datetime.fromisoformat(timestamp)
    return max(0.0, (now - observed).total_seconds())


def safe_session(row: dict, now: datetime) -> dict:
    age = age_seconds(row["heartbeat_at"], now)
    state = row["state"]
    if state != "idle" and age > stale_seconds():
        state = "stale"
    return {
        "session_id": row["session_id"],
        "writer_generation": row["writer_generation"],
        "registered_at": row["registered_at"],
        "heartbeat_at": row["heartbeat_at"],
        "state": state,
        "reported_state": row["state"],
        "case_id": row["case_id"],
        "case_revision": row["case_revision"],
        "skill_identity": row["skill_identity"],
        "summary": row["summary"],
        "last_event_id": row["last_event_id"],
        "opened": row["opened_at"] is not None,
        "age_seconds": age,
        "authority": "live-event",
        "source": f"sessions/{row['session_id']}.json",
    }


def safe_event(row: dict) -> dict:
    payload = row["payload"]
    if row["event_type"].startswith("assignment_"):
        safe_payload = {
            "skill_identity": payload["skill_identity"],
            "state": payload["state"],
            "summary": payload["summary"],
        }
    elif row["event_type"] == "attempt_planned":
        safe_payload = {
            field: payload[field]
            for field in (
                "model",
                "effort",
                "arm",
                "treatment_identity",
                "suite_id",
            )
        }
    elif row["event_type"] == "attempt_started":
        safe_payload = {
            "planned_event_id": payload["planned_event_id"],
            "run_path": payload["run_path"],
        }
    else:
        safe_payload = {
            "run_path": payload["run_path"],
            "artifact": payload["artifact"],
            "sha256": payload["sha256"],
        }
    return {
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "writer": row["writer"],
        "emitted_at": row["emitted_at"],
        "recorded_at": row["recorded_at"],
        "entity": row["entity"],
        "payload": safe_payload,
        "authority": "live-event",
        "source": f"event:{row['event_id']}",
    }


def live_projection(
    corpus_root: Path,
    campaign_id: str,
    completed_attempts: list[dict],
) -> dict:
    if not live_state_enabled(corpus_root):
        return {
            "sessions": [],
            "live_attempts": [],
            "events": [],
            "conflicts": [],
            "available": False,
        }
    now = datetime.now(timezone.utc)
    raw_events, conflicts = event_records(corpus_root)
    conflicted_writers = {
        (
            item["writer"]["kind"],
            item["writer"]["id"],
            item["writer"]["generation"],
        )
        for item in conflicts
    }
    sessions = []
    for row in session_records(corpus_root):
        if row["campaign_id"] != campaign_id:
            continue
        item = safe_session(row, now)
        if (
            "session",
            row["session_id"],
            row["writer_generation"],
        ) in conflicted_writers:
            item["state"] = "conflicted"
        sessions.append(item)
    events = [
        safe_event(row)
        for row in raw_events
        if row["campaign_id"] == campaign_id
    ]
    planned = {
        (
            row["writer"]["kind"],
            row["writer"]["id"],
            row["writer"]["generation"],
            row["event_id"],
        ): row
        for row in raw_events
        if row["campaign_id"] == campaign_id
        and row["event_type"] == "attempt_planned"
    }
    completed_sources = {
        row["source"]["id"]
        for row in completed_attempts
        if row["source"]["id"].startswith(("runs/", "treatment-admission-runs/"))
    }
    live_attempts = []
    for row in raw_events:
        if row["campaign_id"] != campaign_id or row["event_type"] != "attempt_started":
            continue
        plan = planned.get((
            row["writer"]["kind"],
            row["writer"]["id"],
            row["writer"]["generation"],
            row["payload"]["planned_event_id"],
        ))
        if (
            plan is None
            or plan["writer"] != row["writer"]
            or plan["entity"] != row["entity"]
        ):
            raise ValueError("attempt started event has no matching plan")
        run_path = row["payload"]["run_path"]
        superseded = (
            run_path in completed_sources
            or terminal_run(corpus_root, run_path)
        )
        skill_identity = None
        identity_path = corpus_root / run_path / "skill-identity.json"
        if identity_path.exists():
            identity = regular_json(identity_path, "live skill identity")
            if (
                isinstance(identity.get("name"), (str, type(None)))
                and isinstance(identity.get("files"), list)
            ):
                skill_identity = evaluation_history.fingerprint({
                    "name": identity.get("name"),
                    "files": identity["files"],
                })
        age = age_seconds(row["recorded_at"], now)
        state = (
            "conflicted"
            if (
                row["writer"]["kind"],
                row["writer"]["id"],
                row["writer"]["generation"],
            ) in conflicted_writers
            else "superseded"
            if superseded
            else "stale"
            if age > stale_seconds()
            else "active"
        )
        live_attempts.append({
            "event_id": row["event_id"],
            "planned_event_id": plan["event_id"],
            "case_id": row["entity"]["case_id"],
            "case_revision": row["entity"]["case_revision"],
            "writer": row["writer"],
            "run_path": run_path,
            "model": plan["payload"]["model"],
            "effort": plan["payload"]["effort"],
            "arm": plan["payload"]["arm"],
            "treatment_identity": plan["payload"]["treatment_identity"],
            "suite_id": plan["payload"]["suite_id"],
            "skill_identity": skill_identity,
            "location": "local",
            "platform": os.uname().sysname.lower(),
            "state": state,
            "age_seconds": age,
            "authority": (
                "immutable-artifact" if superseded else "live-event"
            ),
            "source": (
                run_path if superseded else f"event:{row['event_id']}"
            ),
        })
    return {
        "sessions": sessions,
        "live_attempts": live_attempts,
        "events": events,
        "conflicts": conflicts,
        "available": True,
    }


def terminal_run(corpus_root: Path, run_path: str) -> bool:
    run = corpus_root / run_path
    report = run / "REPORT.md"
    if report.is_file() and not report.is_symlink():
        return True
    attempt = run / "attempt.json"
    if attempt.exists() or attempt.is_symlink():
        failure = run / "attempt-failure-receipt.json"
        return failure.is_file() and not failure.is_symlink()
    return any(
        artifact.is_file() and not artifact.is_symlink()
        for artifact in run.glob("*-failure-receipt.json")
    )


def historical_run(corpus_root: Path, run_path: str) -> bool:
    if terminal_run(corpus_root, run_path):
        return True
    run = corpus_root / run_path
    attempt = run / "attempt.json"
    execution = run / "execution-result.json"
    return (
        not attempt.exists()
        and not attempt.is_symlink()
        and execution.is_file()
        and not execution.is_symlink()
    )


def terminal_history(corpus_root: Path, report: dict) -> tuple[list[dict], list[dict]]:
    attempts = []
    for row in report["attempts"]:
        run_path = row.get("run_path")
        if run_path is None:
            attempts.append(row)
            continue
        if historical_run(corpus_root, run_path):
            attempts.append(row)
    groups: dict[str, list[dict]] = {}
    for row in attempts:
        groups.setdefault(
            evaluation_history.fingerprint(row["population"]),
            [],
        ).append(row)
    populations = [
        {
            "identity": identity,
            "population": rows[0]["population"],
            **evaluation_history.population_summary(rows),
        }
        for identity, rows in sorted(groups.items())
    ]
    return attempts, populations


def campaign_projection(state_root: Path, campaign_id: str) -> dict:
    registration = campaign_registration(state_root, campaign_id)
    corpus_root = Path(registration["corpus_root"])
    if not corpus_root.is_dir() or corpus_root.is_symlink():
        return unavailable_projection(registration, "corpus_root_unavailable")
    stat = corpus_root.stat()
    if (
        stat.st_dev != registration["corpus_device"]
        or stat.st_ino != registration["corpus_inode"]
    ):
        return unavailable_projection(registration, "corpus_identity_changed")
    corpus = load_corpus(corpus_root)
    report = evaluation_history.history(corpus_root)
    terminal_attempt_rows, terminal_population_rows = terminal_history(
        corpus_root,
        report,
    )
    attempts = [safe_attempt(row) for row in terminal_attempt_rows]
    populations = [safe_population(row) for row in terminal_population_rows]
    cases = [safe_case(corpus_root, case_id, attempts) for case_id in corpus["cases"]]
    live = live_projection(
        corpus_root,
        registration["campaign_id"],
        attempts,
    )
    lineage, task_details, attention = lineage_projection(
        corpus_root,
        registration,
        corpus,
        report,
        attempts,
        live["sessions"],
        live["live_attempts"],
    )
    return {
        "schema_version": 1,
        "campaign": {
            "campaign_id": registration["campaign_id"],
            "corpus_name": registration["corpus_name"],
            "target_skills": registration["target_skills"],
            "availability": "available",
            "unavailable_reason": None,
        },
        "cases": cases,
        "attempts": attempts,
        "populations": populations,
        "sessions": live["sessions"],
        "live_attempts": live["live_attempts"],
        "events": live["events"],
        "conflicts": live["conflicts"],
        "lineage": lineage,
        "task_details": task_details,
        "attention": attention,
        "interpretation": report["interpretation"],
        "availability": {
            "completed_history": "available",
            "live_sessions": "available" if live["available"] else "unavailable",
            "live_attempts": "available" if live["available"] else "unavailable",
            "cloud_activity": "unavailable",
            "lineage": lineage["status"],
            "experiments": "unavailable",
            "ablation": "unavailable",
        },
    }


def campaign_index_projection(state_root: Path) -> dict:
    root = ensure_state_root(state_root)
    campaigns = []
    session_counts = {
        "active": 0,
        "stale": 0,
        "blocked": 0,
        "idle": 0,
        "conflicted": 0,
    }
    active_attempts = 0
    live_campaigns = 0
    for path in sorted((root / "campaigns").glob("*.json")):
        if path.is_symlink():
            raise ValueError(f"campaign registration must be regular: {path}")
        campaign_id = path.stem
        projection = campaign_projection(root, campaign_id)
        campaign = {
            **projection["campaign"],
            "session_counts": {
                state: sum(
                    item["state"] == state
                    for item in projection["sessions"]
                )
                for state in session_counts
            },
            "active_attempts": sum(
                item["state"] == "active"
                for item in projection["live_attempts"]
            ),
        }
        campaigns.append(campaign)
        if projection["availability"]["live_sessions"] == "available":
            live_campaigns += 1
        for state in session_counts:
            session_counts[state] += campaign["session_counts"][state]
        active_attempts += campaign["active_attempts"]
    return {
        "schema_version": 1,
        "campaigns": campaigns,
        "session_counts": session_counts,
        "active_attempts": active_attempts,
        "availability": {
            "live_sessions": "available" if live_campaigns else "unavailable",
            "cloud_activity": "unavailable",
        },
    }


def session_projection(
    state_root: Path,
    campaign_id: str,
    session_id: str,
) -> dict:
    campaign = campaign_projection(state_root, campaign_id)
    matches = [
        item for item in campaign["sessions"]
        if item["session_id"] == session_id
    ]
    if len(matches) != 1:
        raise ValueError("dashboard session is unavailable")
    return {
        "schema_version": 1,
        "campaign": campaign["campaign"],
        "session": matches[0],
        "assignments": [
            item for item in campaign["events"]
            if item["writer"]["kind"] == "session"
            and item["writer"]["id"] == session_id
        ],
        "attempts": [
            item for item in campaign["live_attempts"]
            if (
                item["case_id"],
                item["case_revision"],
            ) == (
                matches[0]["case_id"],
                matches[0]["case_revision"],
            )
        ],
        "availability": campaign["availability"],
    }
