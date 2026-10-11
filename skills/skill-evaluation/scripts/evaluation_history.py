"""Regenerable history from original run artifacts, without a mutable index."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import measurement
from skill_eval import digest, directory_identity, load_corpus, read_json, resolve_under


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


def validated_lineage_identity(value: dict, plugin: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "campaign_id",
        "snapshot_id",
        "plugin_identity",
        "skills",
    } or value.get("schema_version") != 1:
        raise ValueError("malformed lineage identity")
    for field in ("campaign_id", "snapshot_id", "plugin_identity"):
        item = value.get(field)
        expected_length = 32 if field == "campaign_id" else 64
        if (
            not isinstance(item, str)
            or len(item) != expected_length
            or any(character not in "0123456789abcdef" for character in item)
        ):
            raise ValueError(f"lineage {field} is invalid")
    if value["plugin_identity"] != plugin.get("sha256"):
        raise ValueError("lineage and plugin identity disagree")
    skills = value.get("skills")
    if (
        not isinstance(skills, list)
        or not skills
        or [item.get("name") for item in skills]
        != sorted({item.get("name") for item in skills})
    ):
        raise ValueError("lineage skills are invalid")
    for skill in skills:
        if not isinstance(skill, dict) or set(skill) != {
            "name",
            "evaluator_skill_identity",
        }:
            raise ValueError("lineage skill is invalid")
        name = skill.get("name")
        identity = skill.get("evaluator_skill_identity")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(identity, str)
            or len(identity) != 64
        ):
            raise ValueError("lineage skill identity is invalid")
        prefix = f"skills/{name}/"
        files = [
            {
                "path": item["path"][len(prefix):],
                "sha256": item["sha256"],
            }
            for item in plugin["files"]
            if item["path"].startswith(prefix)
        ]
        files.sort(key=lambda item: item["path"])
        if (
            not files
            or fingerprint({"name": name, "files": files}) != identity
        ):
            raise ValueError("lineage skill does not match pinned plugin")
    return value


def cost_summary(rows: list[dict], role: str = "total") -> dict:
    costs = [row["accounting"].get(role, {}) for row in rows]
    known = [cost["observed_credits"] for cost in costs if cost.get("observed_credits") is not None]
    premiums = [
        cost["observed_premium_requests"]
        for cost in costs
        if cost.get("observed_premium_requests") is not None
    ]
    complete = all(cost.get("complete") and cost.get("credits") is not None for cost in costs)
    premium_complete = all(
        cost.get("complete") and cost.get("premium_requests") is not None
        for cost in costs
    )
    return {
        "credits": sum(cost["credits"] for cost in costs) if complete else None,
        "observed_credits": sum(known) if known or not rows else None,
        "premium_requests": (
            sum(cost["premium_requests"] for cost in costs)
            if premium_complete
            else None
        ),
        "observed_premium_requests": (
            sum(premiums) if premiums or not rows else None
        ),
        "complete": complete, "attempts": len(rows),
        "complete_attempts": sum(bool(cost.get("complete")) for cost in costs),
        "known_subtotal_attempts": len(known),
        "known_premium_attempts": len(premiums),
        "complete_premium_attempts": sum(
            bool(cost.get("complete") and cost.get("premium_requests") is not None)
            for cost in costs
        ),
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
    if result.get("behavioral_verdict") not in {None, behavioral}:
        raise ValueError(f"repository summary changed behavioral correctness: {run_path}")
    status = execution.get("execution_status")
    if execution and status not in {"PASS", "FAIL", "INVALID", "BLOCKED"}:
        raise ValueError(f"invalid execution status: {run_path}")
    if not status:
        status = "ERROR" if any(item.get("status") == "FAILED" for item in receipts) else behavioral or "ERROR"
    skill = optional(path / "skill-identity.json")
    treatment = optional(path / "treatment-identity.json")
    compatibility = optional(path / "compatibility.json")
    arm = attempt.get("arm", execution.get("arm", suite.get("arm", "skill")))
    treatment_artifacts_verified = False
    if treatment:
        if treatment.get("schema_version") != 1 or not isinstance(treatment.get("descriptor"), dict):
            raise ValueError("malformed treatment identity")
        if treatment.get("fingerprint") != fingerprint(treatment["descriptor"]):
            raise ValueError("treatment fingerprint mismatch")
        if attempt.get("treatment_fingerprint") not in {None, treatment["fingerprint"]}:
            raise ValueError("attempt and treatment identity disagree")
        if attempt.get("treatment_id") not in {None, treatment["descriptor"]["id"]}:
            raise ValueError("attempt and treatment id disagree")
        unexecuted = (
            status == "BLOCKED" and execution.get("failure_kind") == "incompatible_treatment"
            or status == "INVALID" and execution.get("failure_kind") == "run_setup"
        )
        descriptor_path = path / "treatment.json"
        if not unexecuted and treatment.get("descriptor_sha256") is not None:
            if not descriptor_path.is_file() or digest(descriptor_path) != treatment["descriptor_sha256"]:
                raise ValueError("treatment descriptor artifact mismatch")
        if not unexecuted and treatment.get("source_identity") is not None:
            if directory_identity(path / "sandcastle-treatment") != treatment["source_identity"]:
                raise ValueError("Sandcastle treatment snapshot mismatch")
        if not unexecuted and treatment.get("adapter_identity") is not None:
            if directory_identity(path / "sandcastle-adapter") != treatment["adapter_identity"]:
                raise ValueError("Sandcastle adapter snapshot mismatch")
        treatment_artifacts_verified = not unexecuted
    else:
        legacy = {
            "schema_version": 1,
            "id": "legacy-baseline" if arm == "baseline" else "legacy-skill",
            "runner": {"kind": "direct-copilot"},
            "entry_skill": skill.get("name") if arm == "skill" else None,
            "intervention_policy": "legacy-case-contract",
            "compatibility": {},
            "source": {"kind": "legacy-evaluator"},
            "adapter": {"digest": None, "description": "legacy evaluator behavior"},
        }
        treatment = {"descriptor": legacy, "fingerprint": fingerprint(legacy)}
    if compatibility and compatibility.get("status") not in {"ADMITTED", "BLOCKED"}:
        raise ValueError("invalid compatibility result")
    if compatibility and compatibility.get("treatment_id") != treatment["descriptor"]["id"]:
        raise ValueError("compatibility and treatment identity disagree")
    harness = optional(path / "harness-identity.json")
    plugin = optional(path / "plugin-identity.json")
    if plugin and (
        not isinstance(plugin.get("files"), list)
        or not isinstance(plugin.get("sha256"), str)
        or plugin["sha256"] != fingerprint(plugin["files"])
    ):
        raise ValueError("malformed plugin identity")
    lineage = optional(path / "lineage-identity.json")
    if lineage:
        lineage = validated_lineage_identity(lineage, plugin)
    suite_lineage = suite.get("lineage_identity")
    if owner and bool(lineage) != bool(suite_lineage):
        raise ValueError("suite and run lineage availability disagree")
    if owner and suite_lineage and lineage != suite_lineage:
        raise ValueError("suite and run lineage identity disagree")
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
        comparable = json.loads(json.dumps(summary))
        for session in comparable.get("sessions", []):
            session.setdefault("subrole", session.get("role"))
        if calculated != comparable:
            raise ValueError(f"accounting does not match invocation evidence: {run_path}")
        summary = comparable
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
        "arm": arm,
        "treatment_id": treatment["descriptor"]["id"],
        "treatment_identity": treatment["fingerprint"],
        "runner_kind": treatment["descriptor"]["runner"]["kind"],
        "adapter_digest": treatment["descriptor"].get("adapter", {}).get("digest"),
        "entry_skill": treatment["descriptor"].get("entry_skill"),
        "intervention_policy": treatment["descriptor"].get("intervention_policy"),
        "compatibility_requirements": treatment["descriptor"].get("compatibility", {}),
        "compatibility_status": compatibility.get(
            "status", attempt.get("compatibility_status", "unknown")
        ),
        "skill_identity": fingerprint({"name": skill.get("name"), "files": skill["files"]})
                          if "files" in skill else None,
        "plugin_identity": plugin.get("sha256"),
        "lineage_snapshot_id": lineage.get("snapshot_id"),
        "lineage_campaign_id": lineage.get("campaign_id"),
        "lineage_skills": lineage.get("skills", []),
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
        "treatment_artifacts_verified": treatment_artifacts_verified,
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


def validated_lineage_suite(
    suite_path: str,
    suite: dict,
    lineage_identity: dict,
    rows: list[dict],
) -> dict:
    suite_rows = [row for row in rows if row["suite_path"] == suite_path]
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("lineage suite cases are invalid")
    case_map = {}
    for case in cases:
        case_id = case.get("case_id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id or case_id in case_map:
            raise ValueError("lineage suite case identities are invalid")
        case_map[case_id] = case
    row_case_ids = {row["population"]["case_id"] for row in suite_rows}
    if set(case_map) != row_case_ids:
        raise ValueError("lineage suite case membership disagrees with run artifacts")

    expected_revisions = suite.get("case_revisions")
    if not isinstance(expected_revisions, dict) or set(expected_revisions) != set(case_map):
        raise ValueError("lineage suite revisions are invalid")
    derived_cases = []
    for case_id, case in sorted(case_map.items()):
        case_rows = sorted(
            (
                row for row in suite_rows
                if row["population"]["case_id"] == case_id
            ),
            key=lambda row: row["attempt"],
        )
        attempts = case.get("attempts")
        if not isinstance(attempts, list) or len(attempts) != len(case_rows):
            raise ValueError("lineage suite attempts disagree with run artifacts")
        attempts_by_ordinal = {
            item.get("attempt"): item
            for item in attempts
            if isinstance(item, dict) and type(item.get("attempt")) is int
        }
        if set(attempts_by_ordinal) != {row["attempt"] for row in case_rows}:
            raise ValueError("lineage suite attempt ordinals disagree with run artifacts")
        for row in case_rows:
            claim = attempts_by_ordinal[row["attempt"]]
            if claim.get("run_path") != row["run_path"]:
                raise ValueError("lineage suite attempt path disagrees with run artifact")
            if claim.get("result") != row["correctness"]:
                raise ValueError("lineage suite attempt result disagrees with run artifact")
            if (
                "execution_status" in claim
                and claim["execution_status"] != row["correctness"]
            ):
                raise ValueError("lineage suite execution result disagrees with run artifact")
            if (
                "behavioral_verdict" in claim
                and claim["behavioral_verdict"] != row["behavioral_verdict"]
            ):
                raise ValueError("lineage suite behavioral result disagrees with run artifact")

        revisions = {
            row["population"]["case_revision"]
            for row in case_rows
            if row["run_path"] is not None
        }
        if revisions != {expected_revisions[case_id]}:
            raise ValueError("lineage suite case revision disagrees with run artifacts")
        successful = next(
            (
                row for row in case_rows
                if row["correctness"] == "PASS"
                and (
                    row["population"]["case_type"] != "repository-task"
                    or row["behavioral_verdict"] == "PASS"
                )
            ),
            None,
        )
        completed = [row for row in case_rows if row["correctness"] != "ERROR"]
        final = successful or (completed[-1] if completed else None)
        expected_result = (
            "PASS" if successful else
            final["correctness"] if final is not None else "FAIL"
        )
        expected_run_path = final["run_path"] if final is not None else None
        expected_behavioral = (
            final["behavioral_verdict"]
            if final is not None
            and final["population"]["case_type"] == "repository-task"
            else None
        )
        if (
            case.get("result") != expected_result
            or case.get("run_path") != expected_run_path
            or case.get("behavioral_verdict") != expected_behavioral
            or case.get("attempt_count") != len(case_rows)
            or case.get("passed_after_retry")
            != bool(successful and successful["attempt"] > 1)
        ):
            raise ValueError("lineage suite case result disagrees with run artifacts")
        derived_cases.append({
            "case_id": case_id,
            "result": expected_result,
            "behavioral_verdict": expected_behavioral,
        })

    completed_rows = [row for row in suite_rows if row["run_path"] is not None]
    if not completed_rows:
        raise ValueError("lineage suite has no validated run artifacts")
    contract_checks = {
        "model": "model",
        "effort": "effort",
        "arm": "arm",
        "quality_review": "quality_review",
        "timeout_seconds": "timeout_seconds",
    }
    for suite_field, population_field in contract_checks.items():
        values = {
            row["population"][population_field]
            for row in completed_rows
        }
        if values != {suite.get(suite_field)}:
            raise ValueError(f"lineage suite {suite_field} disagrees with run artifacts")
    harness = suite.get("harness_identity")
    harness_identity = (
        fingerprint(harness["modules"])
        if isinstance(harness, dict) and isinstance(harness.get("modules"), list)
        else None
    )
    if {
        row["population"]["harness_identity"]
        for row in completed_rows
    } != {harness_identity}:
        raise ValueError("lineage suite harness disagrees with run artifacts")
    treatment = suite.get("treatment")
    if isinstance(treatment, dict):
        treatment_identity = fingerprint(treatment)
        if {
            row["population"]["treatment_identity"]
            for row in completed_rows
        } != {treatment_identity}:
            raise ValueError("lineage suite treatment disagrees with run artifacts")

    derived_result = (
        "PASS"
        if all(
            case["result"] == "PASS"
            and (
                next(
                    row["population"]["case_type"]
                    for row in completed_rows
                    if row["population"]["case_id"] == case["case_id"]
                ) != "repository-task"
                or case["behavioral_verdict"] == "PASS"
            )
            for case in derived_cases
        )
        else "FAIL"
    )
    if suite.get("result") != derived_result:
        raise ValueError("lineage suite result disagrees with run artifacts")
    if derived_result == "PASS" and suite.get("failures") != []:
        raise ValueError("passing lineage suite retains failures")
    return {
        "suite_path": suite_path,
        "result": derived_result,
        "lineage_identity": lineage_identity,
        "case_revisions": dict(sorted(expected_revisions.items())),
        "cases": derived_cases,
        "contract": {
            field: suite.get(field)
            for field in (
                "model",
                "effort",
                "arm",
                "treatment",
                "quality_review",
                "timeout_seconds",
                "harness_identity",
            )
        },
    }


def _history(root: Path, *, case_id: str | None = None, arm: str | None = None,
             model: str | None = None) -> dict:
    root = root.resolve()
    load_corpus(root)
    paths: dict[Path, tuple[dict | None, dict]] = {}
    missing = []
    lineage_suite_sources = []
    for suite_file in sorted((root / "suite-runs").glob("*/suite-result.json")):
        suite = object_file(suite_file)
        if not isinstance(suite.get("cases"), list):
            raise ValueError(f"invalid suite cases: {suite_file}")
        suite_path = suite_file.parent.relative_to(root).as_posix()
        suite_lineage = optional(suite_file.parent / "lineage-identity.json")
        embedded_lineage = suite.get("lineage_identity")
        if bool(suite_lineage) != bool(embedded_lineage):
            raise ValueError("suite lineage artifact and result disagree")
        if suite_lineage:
            suite_plugin = optional(suite_file.parent / "plugin-identity.json")
            suite_lineage = validated_lineage_identity(
                suite_lineage,
                suite_plugin,
            )
            if suite_lineage != embedded_lineage:
                raise ValueError("suite lineage artifact changed")
            lineage_suite_sources.append(
                (suite_path, suite, suite_lineage)
            )
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
                "plugin_identity": None,
                "lineage_snapshot_id": None, "lineage_campaign_id": None,
                "lineage_skills": [],
                "treatment_id": suite.get("treatment", {}).get("id", "unknown")
                                if isinstance(suite.get("treatment"), dict) else "unknown",
                "treatment_identity": fingerprint(suite["treatment"])
                                      if isinstance(suite.get("treatment"), dict) else None,
                "runner_kind": suite.get("treatment", {}).get("runner", {}).get("kind")
                               if isinstance(suite.get("treatment"), dict) else None,
                "adapter_digest": suite.get("treatment", {}).get("adapter", {}).get("digest")
                                  if isinstance(suite.get("treatment"), dict) else None,
                "entry_skill": suite.get("treatment", {}).get("entry_skill")
                               if isinstance(suite.get("treatment"), dict) else None,
                "intervention_policy": suite.get("treatment", {}).get("intervention_policy")
                                       if isinstance(suite.get("treatment"), dict) else None,
                "compatibility_requirements": suite.get("treatment", {}).get("compatibility", {})
                                              if isinstance(suite.get("treatment"), dict) else {},
                "compatibility_status": "unknown",
                "harness_identity": None, "model": suite.get("model"), "effort": suite.get("effort"),
                "timeout_seconds": suite.get("timeout_seconds"), "max_attempts": owner["max_attempts"],
                "image": None, "quality_review": suite.get("quality_review", False), "evaluator_models": [],
            },
            "accounting": {}, "accounting_available": False, "measurement_errors": [],
            "invocations": [], "quality": None, "started_at": None, "elapsed_seconds": None,
            "legacy_execution_elapsed_seconds": None, "timing_status": "unavailable",
            "behavioral_verdict": None,
        })
    lineage_suites = [
        validated_lineage_suite(suite_path, suite, lineage, rows)
        for suite_path, suite, lineage in lineage_suite_sources
    ]
    rows = [row for row in rows if (case_id is None or row["population"]["case_id"] == case_id)
            and (arm is None or row["population"]["arm"] == arm)
            and (model is None or row["population"]["model"] == model)]
    rows.sort(key=lambda row: (row["experiment_id"], row["attempt"]))
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(fingerprint(row["population"]), []).append(row)
    return {
        "schema_version": 1, "attempts": rows,
        "lineage_suites": lineage_suites,
        "populations": [
            {"identity": identity, "population": items[0]["population"], **population_summary(items)}
            for identity, items in sorted(groups.items())
        ],
        "interpretation": "AI credits are reported in cents. Unknowns are not zero. "
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

    rows_by_population: dict[str, list[dict]] = {}
    for row in report["attempts"]:
        rows_by_population.setdefault(fingerprint(row["population"]), []).append(row)
    lines = ["# Evaluation history", "", report["interpretation"], "",
             "## Population scorecard", "",
             "First outcomes are passes / valid / requested originals. Behavioral outcomes are "
             "reported passes / judged / requested originals, not release qualification. "
             "AI credits are exact / observed totals. Spending and known trial-wall sums include "
             "retries, failures and invalid attempts; the sum is not parallel campaign elapsed time "
             "or billed runner time. Compare only matched populations; numbered details follow.", "",
             "| Population | First outcomes | Behavioral originals | AI credits | "
             "Known trial-wall sum (s) | Timed attempts |",
             "| --- | --- | --- | --- | --- | --- |"]
    for ordinal, group in enumerate(report["populations"], 1):
        rows = rows_by_population[group["identity"]]
        first = [row for row in rows if row["attempt"] == 1]
        judged = [row for row in first if row["behavioral_verdict"] in {"PASS", "FAIL", "UNANSWERABLE"}]
        timed = [row["elapsed_seconds"] for row in rows if row["elapsed_seconds"] is not None]
        wall_sum = measurement.number(sum(timed), "summed trial wall seconds") if timed else None
        population = group["population"]
        label = f"{ordinal}: " + " / ".join(
            str(population[field]) if population[field] is not None else "unknown"
            for field in ("case_id", "treatment_id", "model")
        )
        cost = group["total_spend"]
        lines.append("| " + " | ".join(map(cell, (
            label,
            f"{group['first_attempt_passes']} / {group['valid_first_attempts']} / {group['first_attempts']}",
            f"{sum(row['behavioral_verdict'] == 'PASS' for row in judged)} / {len(judged)} / {len(first)}",
            f"{cell(cost['credits'])} / {cell(cost['observed_credits'])}",
            wall_sum, f"{len(timed)} / {len(rows)}",
        ))) + " |")
    lines += ["",
             "| Attempt | Treatment | Result | Behavioral | Quality | Wall seconds | "
             "Candidate credits | Evaluator credits | Intervention | Compatibility |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["attempts"]:
        candidate = row["accounting"].get("candidate", {})
        evaluator = row["accounting"].get("evaluation", {})
        quality = row["quality"]
        quality_label = (
            ("complete: " if quality["complete"] else "incomplete: ")
            + ", ".join(item.get("judgment", item["status"]) for item in quality["reviewers"])
            if quality else "unavailable")
        lines.append("| " + " | ".join(map(cell, (
            row["run_path"] or f"{row['experiment_id']} attempt {row['attempt']}",
            row["population"]["treatment_id"], row["correctness"], row["behavioral_verdict"],
            quality_label, row["elapsed_seconds"],
            f"{cell(candidate.get('credits'))} / {cell(candidate.get('observed_credits'))}",
            f"{cell(evaluator.get('credits'))} / {cell(evaluator.get('observed_credits'))}",
            row["population"]["intervention_policy"],
            row["population"]["compatibility_status"],
        ))) + " |")
    for ordinal, group in enumerate(report["populations"], 1):
        lines += ["", f"## Population `{group['identity']}`", "",
                  f"Scorecard population {ordinal}.", "",
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
