"""Regenerable history from original run artifacts, without a mutable index."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import measurement
from skill_eval import digest, load_corpus, read_json, resolve_under


def object_file(path: Path) -> dict:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"history artifact must be an object: {path}")
    return value


def optional(path: Path) -> dict:
    return object_file(path) if path.is_file() else {}


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def cost_summary(rows: list[dict], role: str = "total") -> dict:
    costs = [row["accounting"].get(role, {}) for row in rows]
    known = [cost["observed_credits"] for cost in costs if cost.get("observed_credits") is not None]
    complete = all(cost.get("complete") and cost.get("credits") is not None for cost in costs)
    return {
        "credits": sum(cost["credits"] for cost in costs) if complete else None,
        "observed_credits": sum(known) if known or not rows else None,
        "complete": complete, "attempts": len(rows),
        "complete_attempts": sum(bool(cost.get("complete")) for cost in costs),
        "known_subtotal_attempts": len(known),
    }


def population_summary(rows: list[dict]) -> dict:
    first = [row for row in rows if row["attempt"] == 1]
    retries = [row for row in rows if row["attempt"] > 1]
    invalid = [row for row in rows if row["correctness"] in {"INVALID", "ERROR"}]
    unsuccessful = [row for row in rows if row["correctness"] != "PASS"]
    successes = sum(row["correctness"] == "PASS" for row in first)
    valid = sum(row["correctness"] in {"PASS", "FAIL", "UNANSWERABLE"} for row in first)
    first_cost = cost_summary(first)
    experiments: dict[str, list[dict]] = {}
    for row in rows:
        experiments.setdefault(row["experiment_id"], []).append(row)
    return {
        "attempts": len(rows), "first_attempts": len(first), "first_attempt_passes": successes,
        "valid_first_attempts": valid, "invalid_first_attempts": len(first) - valid,
        "pass_at_1": successes / valid if valid else None,
        "execution_coverage": valid / len(first) if first else None,
        "eventual_executable_passes": sum(any(row["correctness"] == "PASS" for row in items)
                                        for items in experiments.values()),
        "retry_assisted_executable_passes": sum(
            not any(row["attempt"] == 1 and row["correctness"] == "PASS" for row in items)
            and any(row["attempt"] > 1 and row["correctness"] == "PASS" for row in items)
            for items in experiments.values()),
        "candidate_spend": cost_summary(rows, "candidate"),
        "evaluation_spend": cost_summary(rows, "evaluation"),
        "total_spend": cost_summary(rows), "first_attempt_spend": first_cost,
        "retry_spend": cost_summary(retries), "invalid_spend": cost_summary(invalid),
        "unsuccessful_spend": cost_summary(unsuccessful),
        "credits_per_successful_first_attempt": first_cost["credits"] / successes
            if successes and first_cost["complete"] else None,
        "ratio_population": "all requested first attempts, including failed and invalid attempts",
    }


def run_row(root: Path, path: Path, owner: dict | None, suite: dict) -> dict:
    run_path = path.relative_to(root).as_posix()
    attempt = optional(path / "attempt.json")
    if "run_id" in attempt and attempt["run_id"] != path.parent.name:
        raise ValueError("run directory and attempt identity disagree")
    context = optional(path / "run-context.json")
    stored_owner = attempt.get("suite_owner")
    if stored_owner:
        if owner and stored_owner != owner:
            raise ValueError(f"conflicting suite attempt ownership: {run_path}")
        owner = stored_owner
    if owner:
        if type(owner.get("attempt")) is not int or owner["attempt"] < 1:
            raise ValueError("history suite ordinal must be a positive integer")
        if not isinstance(owner.get("suite_path"), str) or not owner["suite_path"].startswith("suite-runs/"):
            raise ValueError("invalid suite ownership path")
    execution = optional(path / "execution-result.json")
    result = optional(path / "repository-result.json")
    if execution and result and result.get("execution_status") != execution.get("execution_status"):
        raise ValueError(f"repository summary changed executable correctness: {run_path}")
    receipts = [object_file(file) for file in sorted(path.glob("*-receipt.json"))]
    candidate_receipts = [item for item in receipts if "phase" in item]
    evidence = execution or next(iter(candidate_receipts), {})
    case_id = attempt.get("case_id", execution.get("case_id", owner.get("case_id") if owner else path.name))
    if owner and owner["case_id"] != case_id:
        raise ValueError("suite attempt case identity mismatch")
    revision = context.get("case_revision", evidence.get(
        "case_revision", suite.get("case_revisions", {}).get(case_id)))
    judgments = [object_file(file) for file in sorted(path.glob("judgment-*.json"))]
    for judgment in judgments:
        if judgment.get("verdict") not in {"PASS", "FAIL", "UNANSWERABLE"}:
            raise ValueError(f"invalid historical behavioral judgment: {run_path}")
    behavioral = "PASS" if judgments and all(item["verdict"] == "PASS" for item in judgments) else (
        "FAIL" if any(item["verdict"] == "FAIL" for item in judgments)
        else "UNANSWERABLE" if judgments else None)
    if any(item.get("status") == "FAILED" and str(item.get("stage", "")).startswith("judge:")
           for item in receipts):
        behavioral = None
    status = execution.get("execution_status")
    if execution and status not in {"PASS", "FAIL", "INVALID"}:
        raise ValueError(f"invalid execution status: {run_path}")
    if not status:
        status = "ERROR" if any(item.get("status") == "FAILED" for item in receipts) else behavioral or "ERROR"
    skill = optional(path / "skill-identity.json")
    harness = optional(path / "harness-identity.json")
    quality = optional(path / "quality" / "assessment.json")
    if quality:
        from quality_review import validate_review
        if (quality.get("schema_version") != 1 or type(quality.get("complete")) is not bool
                or not isinstance(quality.get("reviewers"), list)):
            raise ValueError("malformed quality assessment")
        if quality.get("case_revision") != revision or quality.get("patch_sha256") != execution.get("patch_sha256"):
            raise ValueError("quality assessment is bound to a different case or patch")
        if quality.get("patch_sha256") is not None and digest(path / "candidate.patch") != quality["patch_sha256"]:
            raise ValueError("quality patch digest mismatch")
        if "packet" in quality:
            if digest(path / "quality" / "prompt.md") != quality.get("prompt_sha256"):
                raise ValueError("quality prompt digest mismatch")
            for item in quality["packet"]:
                source = resolve_under(path / "quality" / "packet", item["path"])
                if digest(source) != item["sha256"]:
                    raise ValueError("quality packet digest mismatch")
        for reviewer in quality["reviewers"]:
            if not isinstance(reviewer.get("status"), str) or reviewer["status"] not in {
                "completed", "failed", "not_run",
            }:
                raise ValueError("invalid quality reviewer outcome")
            if reviewer.get("status") == "completed":
                validate_review({key: reviewer.get(key) for key in ("judgment", "summary", "findings")},
                                path / "quality" / "packet")
        complete = bool(quality.get("expected_models")) and (
            [item.get("model") for item in quality["reviewers"]] == quality["expected_models"]
            and all(item.get("status") == "completed" for item in quality["reviewers"]))
        if quality["complete"] != complete:
            raise ValueError("quality completeness disagrees with reviewer outcomes")
    records = [object_file(file) for file in sorted((path / "measurements").glob("*.json"))]
    summary = optional(path / "accounting.json")
    if summary:
        if "error" in summary:
            raise ValueError(f"measurement error in {run_path}: {summary['error']}")
        calculated = measurement.accounting(records)
        if calculated != summary:
            raise ValueError(f"accounting does not match invocation evidence: {run_path}")
    elif records:
        summary = measurement.accounting(records)
    timing = optional(path / "timing.json")
    if timing:
        if timing.get("schema_version") != 1 or not isinstance(timing.get("stages"), list):
            raise ValueError("malformed timing artifact")
        measurement.number(timing.get("elapsed_seconds"), "elapsed_seconds")
        for stage in timing["stages"]:
            measurement.number(stage.get("elapsed_seconds"), "stage elapsed_seconds")
    population = {
        "case_id": case_id, "case_revision": revision,
        "case_type": context.get("case_type", execution.get("case_type", "prose")),
        "arm": attempt.get("arm", execution.get("arm", suite.get("arm", "skill"))),
        "skill_identity": fingerprint({"name": skill.get("name"), "files": skill["files"]})
                          if "files" in skill else None,
        "harness_identity": fingerprint(harness["modules"]) if "modules" in harness else harness.get("sha256"),
        "model": attempt.get("model", evidence.get("model", suite.get("model"))),
        "effort": attempt.get("effort", evidence.get("effort", suite.get("effort"))),
        "timeout_seconds": attempt.get("timeout_seconds", evidence.get("timeout_seconds", suite.get("timeout_seconds"))),
        "max_attempts": owner.get("max_attempts") if owner else 1,
        "image": execution.get("image"),
        "quality_review": attempt.get("quality_review", bool(quality)),
        "evaluator_models": context.get("judge_models", sorted({
            record["requested_model"] for record in records if record["role"] != "candidate"})),
    }
    return {
        "run_path": run_path, "attempt": owner["attempt"] if owner else 1,
        "suite_path": owner["suite_path"] if owner else None,
        "experiment_id": f"{owner['suite_path']}/{case_id}" if owner else run_path,
        "population": population, "correctness": status,
        "behavioral_verdict": result.get("behavioral_verdict", behavioral),
        "accounting": summary, "accounting_available": bool(summary),
        "measurement_errors": [error for record in records for error in record["errors"]],
        "invocations": records, "quality": quality or None,
        "started_at": timing.get("started_at", attempt.get("started_at")),
        "elapsed_seconds": timing.get("elapsed_seconds"),
        "legacy_execution_elapsed_seconds": execution.get("elapsed_seconds"),
        "timing_status": timing.get("status", "unavailable"),
    }


def _history(root: Path, *, case_id: str | None = None, arm: str | None = None,
             model: str | None = None) -> dict:
    root = root.resolve()
    load_corpus(root)
    paths: dict[Path, tuple[dict | None, dict]] = {}
    missing = []
    for suite_file in sorted((root / "suite-runs").glob("*/suite-result.json")):
        suite = object_file(suite_file)
        if not isinstance(suite.get("cases"), list):
            raise ValueError(f"invalid suite cases: {suite_file}")
        suite_path = suite_file.parent.relative_to(root).as_posix()
        for case in suite["cases"]:
            if not isinstance(case, dict) or not isinstance(case.get("attempts"), list):
                raise ValueError("invalid suite attempt list")
            ordinals = set()
            for item in case["attempts"]:
                ordinal = item.get("attempt")
                if type(ordinal) is not int or ordinal < 1 or ordinal in ordinals:
                    raise ValueError("invalid or duplicate suite attempt ordinal")
                ordinals.add(ordinal)
                owner = {"suite_path": suite_path, "case_id": case["case_id"],
                         "attempt": ordinal, "max_attempts": suite.get("max_attempts")}
                if not item.get("run_path"):
                    if item.get("result") != "ERROR":
                        raise ValueError("completed suite attempt has no run artifact")
                    missing.append((owner, suite))
                    continue
                path = resolve_under(root, item["run_path"])
                if not path.is_relative_to(root / "runs") or not path.is_dir():
                    raise ValueError("suite references an unavailable run")
                if path in paths:
                    raise ValueError("one run is owned by multiple suite attempts")
                paths[path] = (owner, suite)
    for path in sorted((root / "runs").glob("*/*")):
        if path.is_dir():
            resolved = path.resolve()
            if not resolved.is_relative_to(root / "runs"):
                raise ValueError("run history path escapes corpus")
            paths.setdefault(resolved, (None, {}))
    rows = [run_row(root, path, owner, suite) for path, (owner, suite) in sorted(paths.items())]
    owned = set()
    session_owners = {}
    for row in rows:
        for invocation in row["invocations"]:
            session = invocation["session_id"]
            prior = session_owners.setdefault(session, row["run_path"])
            if prior != row["run_path"]:
                raise ValueError("one session is attributed to multiple attempts")
        if row["suite_path"]:
            key = (row["experiment_id"], row["attempt"])
            if key in owned:
                raise ValueError("multiple runs claim the same suite attempt")
            owned.add(key)
    for owner, suite in missing:
        if (f"{owner['suite_path']}/{owner['case_id']}", owner["attempt"]) in owned:
            continue
        rows.append({
            "run_path": None, "attempt": owner["attempt"], "suite_path": owner["suite_path"],
            "experiment_id": f"{owner['suite_path']}/{owner['case_id']}", "correctness": "ERROR",
            "population": {
                "case_id": owner["case_id"], "case_revision": suite.get("case_revisions", {}).get(owner["case_id"]),
                "case_type": "unknown", "arm": suite.get("arm"), "skill_identity": None,
                "harness_identity": None, "model": suite.get("model"), "effort": suite.get("effort"),
                "timeout_seconds": suite.get("timeout_seconds"), "max_attempts": owner["max_attempts"],
                "image": None, "quality_review": suite.get("quality_review", False), "evaluator_models": [],
            },
            "accounting": {}, "accounting_available": False, "measurement_errors": [],
            "invocations": [], "quality": None, "started_at": None, "elapsed_seconds": None,
            "legacy_execution_elapsed_seconds": None, "timing_status": "unavailable",
            "behavioral_verdict": None,
        })
    rows = [row for row in rows if (case_id is None or row["population"]["case_id"] == case_id)
            and (arm is None or row["population"]["arm"] == arm)
            and (model is None or row["population"]["model"] == model)]
    rows.sort(key=lambda row: (row["experiment_id"], row["attempt"]))
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(fingerprint(row["population"]), []).append(row)
    return {
        "schema_version": 1, "attempts": rows,
        "populations": [
            {"identity": identity, "population": items[0]["population"], **population_summary(items)}
            for identity, items in sorted(groups.items())
        ],
        "interpretation": "Costs are AI credits, not currency. Unknowns are not zero. "
                          "Breakdowns and resumed cumulative phases are not additive. "
                          "Compare only matched populations; quality does not change correctness.",
    }


def history(root: Path, *, case_id: str | None = None, arm: str | None = None,
            model: str | None = None) -> dict:
    try:
        return _history(root, case_id=case_id, arm=arm, model=model)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"malformed history artifact: {error}") from error


def markdown(report: dict) -> str:
    def cell(value: object) -> str:
        return ("unknown" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")

    lines = ["# Evaluation history", "", report["interpretation"], "",
             "| Attempt | Result | Behavioral | Credits (exact / observed) | Wall seconds | Quality |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in report["attempts"]:
        cost = row["accounting"].get("total", {})
        quality = row["quality"]
        quality_label = (
            ("complete: " if quality["complete"] else "incomplete: ")
            + ", ".join(item.get("judgment", item["status"]) for item in quality["reviewers"])
            if quality else "unavailable")
        lines.append("| " + " | ".join(map(cell, (
            row["run_path"] or f"{row['experiment_id']} attempt {row['attempt']}",
            row["correctness"], row["behavioral_verdict"],
            f"{cell(cost.get('credits'))} / {cell(cost.get('observed_credits'))}",
            row["elapsed_seconds"], quality_label,
        ))) + " |")
    for group in report["populations"]:
        lines += ["", f"## Population `{group['identity']}`", "",
                  "```json", json.dumps(group["population"], indent=2), "```", "",
                  f"- First-attempt passes: {group['first_attempt_passes']} / "
                  f"{group['valid_first_attempts']} valid; {group['invalid_first_attempts']} invalid/error.",
                  f"- Eventual executable passes: {group['eventual_executable_passes']}; "
                  f"retry-assisted: {group['retry_assisted_executable_passes']}.",
                  f"- Complete credit coverage: {group['total_spend']['complete_attempts']} / {group['attempts']}.",
                  f"- Credits per successful first attempt: {cell(group['credits_per_successful_first_attempt'])}."]
        for field in ("candidate_spend", "evaluation_spend", "first_attempt_spend",
                      "retry_spend", "invalid_spend", "unsuccessful_spend"):
            cost = group[field]
            lines.append(f"- {field}: exact {cell(cost['credits'])}; observed subtotal "
                         f"{cell(cost['observed_credits'])}; complete: {cost['complete']}.")
    if any(row["measurement_errors"] for row in report["attempts"]):
        lines += ["", "Measurement capture errors are present; see invocation evidence in JSON history."]
    return "\n".join(lines) + "\n"
