"""Safe read-only projections for the skill-evaluation dashboard."""

from __future__ import annotations

from pathlib import Path

import evaluation_history
from dashboard_state import campaign_registration, ensure_state_root, regular_json
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
    attempts = [safe_attempt(row) for row in report["attempts"]]
    populations = [safe_population(row) for row in report["populations"]]
    cases = [safe_case(corpus_root, case_id, attempts) for case_id in corpus["cases"]]
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
        "interpretation": report["interpretation"],
        "availability": {
            "completed_history": "available",
            "live_sessions": "unavailable",
            "live_attempts": "unavailable",
            "cloud_activity": "unavailable",
            "lineage": "unavailable",
            "experiments": "unavailable",
            "ablation": "unavailable",
        },
    }


def campaign_index_projection(state_root: Path) -> dict:
    root = ensure_state_root(state_root)
    campaigns = []
    for path in sorted((root / "campaigns").glob("*.json")):
        if path.is_symlink():
            raise ValueError(f"campaign registration must be regular: {path}")
        campaign_id = path.stem
        projection = campaign_projection(root, campaign_id)
        campaigns.append(projection["campaign"])
    return {
        "schema_version": 1,
        "campaigns": campaigns,
        "availability": {
            "live_sessions": "unavailable",
            "cloud_activity": "unavailable",
        },
    }
