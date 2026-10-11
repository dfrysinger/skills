"""Safe read-only projections for the skill-evaluation dashboard."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import evaluation_history
from dashboard_state import (
    campaign_registration,
    ensure_state_root,
    event_records,
    live_state_enabled,
    regular_json,
    session_records,
)
from skill_eval import load_corpus


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
        "interpretation": report["interpretation"],
        "availability": {
            "completed_history": "available",
            "live_sessions": "available" if live["available"] else "unavailable",
            "live_attempts": "available" if live["available"] else "unavailable",
            "cloud_activity": "unavailable",
            "lineage": "unavailable",
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
