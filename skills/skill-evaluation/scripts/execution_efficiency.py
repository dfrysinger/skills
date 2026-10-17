"""Read-only efficiency reporting over trusted coordinator projections."""

from __future__ import annotations

import json
import math
from pathlib import Path

from measurement import MeasurementError, number


CATEGORIES = {"coordination", "infrastructure", "execution", "reporting"}
OVERHEAD = {"coordination", "reporting"}
METRICS = {"outer_wall_per_decision", "overhead_work_per_decision",
           "overhead_wall_fraction", "total_work_per_decision"}
DEFAULT_POLICY = {
    "policy_id": "execution-efficiency-provisional-v1",
    "improvement_fraction": 0.2,
    "regression_multiplier": 1.25,
    "consecutive_complete_windows": 3,
    "unproductive_same_operation_cycles": 2,
    "routine_copies_target": 0,
    "quality_regressions_allowed": 0,
    "required_metrics": ["overhead_work_per_decision"],
    "require_baseline": False,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MeasurementError(message)


def obj(value: object, field: str) -> dict:
    require(isinstance(value, dict), f"{field} must be an object")
    return value


def fields(value: dict, required: set[str], field: str) -> None:
    require(required <= value.keys(), f"{field} missing fields: {sorted(required - value.keys())}")


def items(value: object, field: str) -> list:
    require(isinstance(value, list), f"{field} must be a list")
    return value


def text(value: object, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field} must be a nonempty string")
    return value


def boolean(value: object, field: str) -> bool:
    require(type(value) is bool, f"{field} must be boolean")
    return value


def integer(value: object, field: str, minimum: int = 0) -> int:
    number(value, field)
    require(type(value) is int and value >= minimum, f"{field} must be an integer >= {minimum}")
    return value


def numeric_tree(value: object, field: str) -> None:
    if type(value) in (int, float):
        number(value, field)
    elif isinstance(value, dict):
        for key, item in value.items():
            numeric_tree(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            numeric_tree(item, f"{field}[{index}]")


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise MeasurementError(f"nonfinite JSON constant: {value}")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                       parse_constant=invalid_constant)
    return obj(value, "JSON document")


def policy(value: dict | None) -> dict:
    result = dict(DEFAULT_POLICY)
    if value is not None:
        obj(value, "policy")
        require(not set(value) - set(result), "unknown policy fields")
        result.update(value)
    text(result["policy_id"], "policy_id")
    for field in ("improvement_fraction", "regression_multiplier"):
        require(number(result[field], field) is not None, f"{field} cannot be null")
    require(result["improvement_fraction"] < 1, "improvement_fraction must be below 1")
    require(result["regression_multiplier"] >= 1, "regression_multiplier must be >= 1")
    for field in ("consecutive_complete_windows", "unproductive_same_operation_cycles"):
        integer(result[field], field, 1)
    for field in ("routine_copies_target", "quality_regressions_allowed"):
        integer(result[field], field)
    required = items(result["required_metrics"], "required_metrics")
    require(bool(required) and all(isinstance(name, str) and name in METRICS for name in required),
            "required_metrics must name supported metrics")
    require(len(required) == len(set(required)), "duplicate required_metrics")
    boolean(result["require_baseline"], "require_baseline")
    return result


def identities(value: object, field: str) -> set[str]:
    names = [text(name, field) for name in items(value, field)]
    require(len(names) == len(set(names)), f"duplicate {field}")
    return set(names)


def records(value: object, expected: set[str], field: str) -> dict:
    result = {}
    for record in items(value, field):
        obj(record, field)
        identity = text(record.get("id"), f"{field}.id")
        require(identity in expected, f"unexpected {field} id: {identity}")
        require(identity not in result or json.dumps(result[identity], sort_keys=True) == json.dumps(record, sort_keys=True),
                f"conflicting {field} id: {identity}")
        result[identity] = record
    return result


def metric(value: float | None, reasons: list[str]) -> dict:
    return {"value": value, "exact": value is not None, "reasons": reasons}


def timing(value: object) -> tuple[dict, dict]:
    if value is None:
        return metric(None, ["outer_timing_missing"]), metric(None, ["outer_timing_missing"])
    value = obj(value, "outer_timing")
    fields(value, {"clock", "elapsed_seconds", "stages"}, "outer_timing")
    text(value.get("clock"), "outer_timing.clock")
    elapsed = number(value.get("elapsed_seconds"), "outer_timing.elapsed_seconds")
    stages = items(value.get("stages"), "outer_timing.stages")
    reasons = []
    if value["clock"] != "monotonic":
        reasons.append("foreign_clock")
    if elapsed is None:
        reasons.append("outer_elapsed_missing")
    cursor = 0
    overhead = 0
    for stage in stages:
        obj(stage, "stage")
        for field in ("elapsed_seconds", "start_seconds", "end_seconds"):
            number(stage.get(field), f"stage.{field}")
        if "clock" in stage and stage["clock"] != "monotonic":
            text(stage["clock"], "stage.clock")
            reasons.append("foreign_stage_clock")
        if "scope_id" in stage and stage["scope_id"] != value.get("scope_id"):
            text(stage["scope_id"], "stage.scope_id")
            reasons.append("foreign_stage_scope")
        category = stage.get("category")
        if category is not None:
            text(category, "stage.category")
        start, end = stage.get("start_seconds"), stage.get("end_seconds")
        if start is None or end is None:
            reasons.append("stage_offsets_missing")
            continue
        if start != cursor or end < start or elapsed is None or end > elapsed:
            reasons.append("stage_gap_overlap_or_uncontained")
        if category not in CATEGORIES:
            reasons.append("stage_category_unknown")
        if stage.get("elapsed_seconds") is not None and stage["elapsed_seconds"] != end - start:
            reasons.append("stage_duration_mismatch")
        if category in OVERHEAD:
            overhead += end - start
        cursor = end
    if cursor != elapsed:
        reasons.append("stages_do_not_cover_outer")
    if elapsed == 0:
        reasons.append("zero_outer_denominator")
    fraction = overhead / elapsed if not reasons else None
    wall_reasons = ["outer_elapsed_missing"] if elapsed is None else []
    if value["clock"] != "monotonic":
        wall_reasons.append("foreign_clock")
    return metric(elapsed if not wall_reasons else None, wall_reasons), metric(fraction, sorted(set(reasons)))


def snapshot(view: dict) -> dict:
    obj(view, "view")
    fields(view, {"schema_version", "scope_id", "source_fingerprint", "comparison_contract",
                  "expected_decision_ids", "decisions", "expected_work_ids", "work",
                  "outer_timing", "control"}, "view")
    require(type(view.get("schema_version")) is int and view["schema_version"] == 1,
            "schema_version must be 1")
    for field in ("scope_id", "source_fingerprint"):
        text(view.get(field), field)
    contract = obj(view.get("comparison_contract"), "comparison_contract")
    require(contract.get("comparison_mode") in ("retained_replay", "fresh_window"),
            "comparison_mode must be retained_replay or fresh_window")
    numeric_tree(contract, "comparison_contract")
    expected = identities(view.get("expected_decision_ids"), "expected_decision_ids")
    decisions = records(view.get("decisions"), expected, "decisions")
    useful, audits, unresolved = [], [], set(expected - decisions.keys())
    counts = {status: 0 for status in ("PASS", "FAIL", "PENDING", "INVALID", "UNKNOWN")}
    for identity, record in decisions.items():
        text(record.get("status"), "decision.status")
        require(record.get("class") in ("product", "audit"), "invalid decision class")
        require(record.get("status") in counts, "invalid decision status")
        provenance = obj(record.get("provenance"), "decision.provenance")
        for field in ("reference", "digest"):
            text(provenance.get(field), f"provenance.{field}")
        require(provenance.get("trust") in ("coordinator_projection", "candidate_reported"),
                "invalid provenance trust")
        if record["class"] == "audit":
            audits.append(identity)
        else:
            counts[record["status"]] += 1
            if record["status"] in ("PASS", "FAIL") and provenance["trust"] == "coordinator_projection":
                useful.append(identity)
            else:
                unresolved.add(identity)
    denominator_reasons = []
    if unresolved:
        denominator_reasons.append("product_decisions_unresolved")
    if not useful:
        denominator_reasons.append("no_useful_product_decisions")

    expected_work = identities(view.get("expected_work_ids"), "expected_work_ids")
    work = records(view.get("work"), expected_work, "work")
    missing_work = expected_work - work.keys()
    unknown_work = set(missing_work)
    sums = {name: 0 for name in CATEGORIES}
    purposes = {"recurring": 0, "repair_investment": 0}
    recurring_overhead = 0
    for identity, record in work.items():
        fields(record, {"id", "owner", "parent_id", "category", "seconds", "source_reference",
                        "inclusion", "purpose"}, "work")
        text(record.get("owner"), "work.owner")
        text(record.get("source_reference"), "work.source_reference")
        text(record.get("category"), "work.category")
        text(record.get("purpose"), "work.purpose")
        require(record.get("category") in CATEGORIES,
                f"invalid work category for {identity!r}: {record['category']!r}; "
                f"expected one of: {', '.join(sorted(CATEGORIES))}")
        require(record.get("inclusion") in ("leaf", "aggregate"), "invalid work inclusion")
        require(record.get("purpose") in purposes, "invalid work purpose")
        seconds = number(record.get("seconds"), "work.seconds")
        parent = record.get("parent_id")
        if parent is not None:
            text(parent, "work.parent_id")
            require(parent in work, "work parent must be present")
            require(work[parent].get("inclusion") == "aggregate", "work parent must be aggregate")
        if record["inclusion"] == "leaf":
            if seconds is None:
                unknown_work.add(identity)
            else:
                sums[record["category"]] += seconds
                purposes[record["purpose"]] += seconds
                if record["purpose"] == "recurring" and record["category"] in OVERHEAD:
                    recurring_overhead += seconds
        seen = {identity}
        while parent is not None:
            require(parent not in seen, "cyclic work parent links")
            seen.add(parent)
            parent = work[parent].get("parent_id")
            if parent is not None:
                require(isinstance(parent, str) and parent in work, "work parent must be present")
    for field, value in {**sums, **purposes}.items():
        number(value, f"work subtotal.{field}")
    wall, fraction = timing(view.get("outer_timing"))
    if view.get("outer_timing") is not None:
        timing_scope = view["outer_timing"].get("scope_id")
        if timing_scope is not None:
            text(timing_scope, "outer_timing.scope_id")
            if timing_scope != view["scope_id"]:
                wall = metric(None, ["foreign_outer_scope"])
                fraction = metric(None, ["foreign_outer_scope"])
    work_reasons = denominator_reasons + (["work_coverage_incomplete"] if unknown_work else [])
    overhead = sum(sums[name] for name in OVERHEAD)
    metrics = {
        "outer_wall_per_decision": metric(
            wall["value"] / len(useful) if not denominator_reasons and wall["exact"] else None,
            denominator_reasons + wall["reasons"]),
        "overhead_work_per_decision": metric(
            recurring_overhead / len(useful) if not work_reasons else None, work_reasons),
        "total_work_per_decision": metric(
            sum(sums.values()) / len(useful) if not work_reasons else None, work_reasons),
        "overhead_wall_fraction": fraction,
        "outer_wall_seconds": wall,
        "observed_leaf_work_seconds": sums,
        "observed_work_by_purpose_seconds": purposes,
        "observed_overhead_work_seconds": overhead,
        "observed_recurring_overhead_work_seconds": recurring_overhead,
    }
    for name in METRICS:
        number(metrics[name]["value"], name)
    return {
        "metrics": metrics,
        "coverage": {
            "expected_decision_ids": sorted(expected), "observed_decision_ids": sorted(decisions),
            "useful_product_ids": sorted(useful), "audit_ids": sorted(audits),
            "unresolved_decision_ids": sorted(unresolved), "product_status_counts": counts,
            "expected_work_ids": sorted(expected_work), "observed_work_ids": sorted(work),
            "unknown_work_ids": sorted(unknown_work), "excluded_aggregate_ids": sorted(
                identity for identity, record in work.items() if record["inclusion"] == "aggregate"),
        },
        "decisions": decisions,
        "quality_complete": not denominator_reasons,
    }


def comparison(view: dict, current: dict, baseline: dict | None, base: dict | None) -> dict:
    reasons = []
    integrity = False
    if baseline is None:
        reasons.append("baseline_missing")
    else:
        if json.dumps(view["comparison_contract"], sort_keys=True) != json.dumps(baseline["comparison_contract"], sort_keys=True):
            reasons.append("comparison_contract_mismatch")
        elif view["comparison_contract"]["comparison_mode"] == "retained_replay":
            def outcomes(value):
                return {key: (record["class"], record["status"], record["provenance"]["digest"])
                        for key, record in value["decisions"].items()
                        if record["provenance"]["trust"] == "coordinator_projection"}
            left, right = outcomes(current), outcomes(base)
            if (current["coverage"]["expected_decision_ids"] != base["coverage"]["expected_decision_ids"]
                    or any(left[key] != right[key] for key in left.keys() & right.keys())):
                reasons.append("retained_outcomes_changed")
                integrity = True
            if left.keys() != right.keys():
                reasons.append("retained_outcome_coverage_incomplete")
        if not current["quality_complete"] or not base["quality_complete"]:
            reasons.append("decision_coverage_incomplete")
    recurring_reasons = list(reasons)
    total_reasons = list(reasons)
    if base is not None:
        if (not current["metrics"]["overhead_work_per_decision"]["exact"]
                or not base["metrics"]["overhead_work_per_decision"]["exact"]):
            recurring_reasons.append("work_coverage_incomplete")
        if (not current["metrics"]["total_work_per_decision"]["exact"]
                or not base["metrics"]["total_work_per_decision"]["exact"]):
            total_reasons.append("total_investment_coverage_incomplete")
    ratio = None
    if not recurring_reasons:
        denominator = base["metrics"]["overhead_work_per_decision"]["value"]
        if denominator == 0:
            recurring_reasons.append("zero_baseline_denominator")
        else:
            ratio = current["metrics"]["overhead_work_per_decision"]["value"] / denominator
            number(ratio, "comparison.ratio")
    improvement, total_ratio = None, None
    if not total_reasons:
        denominator = base["metrics"]["total_work_per_decision"]["value"]
        if denominator == 0:
            total_reasons.append("zero_total_baseline_denominator")
        else:
            total_ratio = current["metrics"]["total_work_per_decision"]["value"] / denominator
            number(total_ratio, "comparison.total_work_ratio")
            improvement = 1 - total_ratio
            require(math.isfinite(improvement), "nonfinite derived total improvement")
    no_worse_wall = None
    if not reasons and base is not None:
        left = current["metrics"]["outer_wall_per_decision"]["value"]
        right = base["metrics"]["outer_wall_per_decision"]["value"]
        if left is not None and right is not None:
            no_worse_wall = left <= right
    return {
        "eligible": not recurring_reasons, "reasons": sorted(set(recurring_reasons)),
        "overhead_ratio": ratio, "integrity_violation": integrity,
        "total_eligible": not total_reasons, "total_reasons": sorted(set(total_reasons)),
        "total_improvement_fraction": improvement, "total_work_ratio": total_ratio,
        "no_worse_wall": no_worse_wall,
        "baseline_identity": None if baseline is None else {
            "scope_id": baseline["scope_id"], "source_fingerprint": baseline["source_fingerprint"]},
    }


def control(view: dict, rules: dict, *, history_allowed: bool = True) -> tuple[dict, list]:
    value = obj(view.get("control"), "control")
    triggers = {}
    for field in ("scope_hold", "open_repair"):
        triggers[field] = boolean(value.get(field), f"control.{field}")
    triggers["integrity"] = boolean(value.get("integrity_violation", False), "integrity_violation")
    triggers["quality_regression"] = (
        integer(value.get("quality_regressions", 0), "quality_regressions")
        > rules["quality_regressions_allowed"])
    signatures = [text(item, "recurrence_signature") for item in
                  items(value.get("recurrence_signatures", []), "recurrence_signatures")]
    triggers["recurrence"] = bool(signatures)
    copies = False
    for event in items(value.get("operation_materializations", []), "operation_materializations"):
        obj(event, "materialization")
        text(event.get("operation_id"), "operation_id")
        text(event.get("operation_digest"), "operation_digest")
        changed = boolean(event.get("implementation_changed"), "implementation_changed")
        count = integer(event.get("new_executable_copies"), "new_executable_copies")
        copies |= not changed and count > rules["routine_copies_target"]
    triggers["duplicate_copy"] = copies
    previous, length = None, 0
    for event in items(value.get("same_operation_cycles", []), "same_operation_cycles"):
        obj(event, "cycle")
        key = (text(event.get("operation_id"), "operation_id"),
               text(event.get("operation_digest"), "operation_digest"))
        text(event.get("evidence_reference"), "evidence_reference")
        evidence = boolean(event.get("new_decision_evidence"), "new_decision_evidence")
        length = 0 if evidence else length + 1 if key == previous else 1
        previous = key
    triggers["unproductive_cycle"] = length >= rules["unproductive_same_operation_cycles"]
    history = items(value.get("consecutive_windows", []), "consecutive_windows")
    require(history_allowed or not history, "nested window history is not allowed")
    return triggers, history


def audit(view: dict, baseline: dict | None = None, policy_override: dict | None = None) -> dict:
    rules = policy(policy_override)
    current = snapshot(view)
    base = snapshot(baseline) if baseline is not None else None
    if baseline is not None:
        control(baseline, rules, history_allowed=False)
    compared = comparison(view, current, baseline, base)
    triggers, history = control(view, rules)
    triggers["integrity"] |= compared["integrity_violation"]
    run = 0
    windows = []
    for prior in history:
        observed = snapshot(prior)
        flags, _ = control(prior, rules, history_allowed=False)
        matched = comparison(prior, observed, baseline, base)
        triggers["integrity"] |= matched["integrity_violation"]
        eligible = (matched["eligible"] and prior["comparison_contract"] == view["comparison_contract"]
                    and not any(fired for name, fired in flags.items()
                                if name not in ("scope_hold", "open_repair")))
        run = run + 1 if eligible and matched["overhead_ratio"] > rules["regression_multiplier"] else 0
        windows.append({"scope_id": prior["scope_id"], "eligible": eligible, "overhead_ratio": matched["overhead_ratio"]})
    require(len({prior["scope_id"] for prior in history} | {view["scope_id"]}) == len(history) + 1,
            "window scope identities must be unique")
    eligible = compared["eligible"] and not any(
        fired for name, fired in triggers.items() if name not in ("scope_hold", "open_repair"))
    run = run + 1 if eligible and compared["overhead_ratio"] > rules["regression_multiplier"] else 0
    windows.append({"scope_id": view["scope_id"], "eligible": eligible, "overhead_ratio": compared["overhead_ratio"]})
    triggers["quantified_regression"] = run >= rules["consecutive_complete_windows"]
    missing = [name for name in rules["required_metrics"] if not current["metrics"][name]["exact"]]
    if not current["quality_complete"]:
        missing.append("current_quality")
    if rules["require_baseline"] and not compared["eligible"]:
        missing.append("required_comparison")
    ready = not missing and not any(
        fired for name, fired in triggers.items() if name not in ("scope_hold", "open_repair"))
    code = 2 if any(triggers.values()) else 3 if missing else 0
    compared.update(
        windows=windows, consecutive_regression_windows=run,
        target_met=(compared["total_work_ratio"] is not None
                    and compared["total_work_ratio"] <= 1 - rules["improvement_fraction"]
                    and compared["overhead_ratio"] is not None
                    and compared["overhead_ratio"] <= 1 - rules["improvement_fraction"]
                    and compared["no_worse_wall"] is True
                    and ready),
    )
    return {
        "schema_version": 1, "scope_id": view["scope_id"],
        "source_fingerprint": view["source_fingerprint"],
        "trust": "coordinator_projection_not_authenticated_grading_or_billing",
        "policy": rules, "policy_provisional": rules == DEFAULT_POLICY,
        "metrics": current["metrics"], "coverage": current["coverage"],
        "comparison": compared, "triggers": triggers, "missing_decisive_measurement": missing,
        "drain_allowed": True, "reconciliation_ready": ready,
        "state": {0: "PROCEED", 2: "PAUSE_NEW_WORK", 3: "MEASUREMENT_REQUIRED"}[code],
        "exit_code": code, "authority": "advisory_only", "financial_claims_available": False,
    }


def command(view: Path, baseline: Path | None, policy_path: Path | None) -> int:
    try:
        result = audit(load(view), load(baseline) if baseline is not None else None,
                       load(policy_path) if policy_path is not None else None)
    except (MeasurementError, OSError, UnicodeError, json.JSONDecodeError) as error:
        result = {"schema_version": 1, "state": "ERROR", "exit_code": 1,
                  "error": str(error), "drain_allowed": True, "reconciliation_ready": False,
                  "authority": "advisory_only"}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return result["exit_code"]
