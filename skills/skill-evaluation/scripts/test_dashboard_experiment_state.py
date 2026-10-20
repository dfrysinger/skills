#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from dashboard_cli import (
    dispatch as dashboard_dispatch,
    experiment_declaration_dashboard,
    experiment_dispatch_dashboard,
    experiment_observation_dashboard,
    experiment_result_dashboard,
    experiment_selection_dashboard,
    experiment_stage_dashboard,
    parser as dashboard_parser,
)
from dashboard_projection import campaign_index_projection, campaign_projection
from dashboard_state import (
    EXPERIMENT_EVENT_TYPES,
    capture_skill_snapshot,
    compute_experiment_selection,
    create_campaign,
    emit_experiment_activity_event,
    emit_experiment_selection,
    experiment_activity_records,
    experiment_plan_fingerprint,
    register_session,
    validate_experiment_declaration,
    validate_experiment_activity_event,
    writer_directory,
)
from skill_eval import (
    add_case,
    digest,
    freeze_case,
    frozen_case_path,
    init_corpus,
)
from distributed_campaign import canonical_fingerprint, create_dispatch_binding


class DashboardExperimentStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"
        self.corpus = self.root / "corpus"
        init_corpus(self.corpus)
        add_case(self.corpus, "case-a", "example-skill", ["candidate"])
        definition_path = self.corpus / "cases" / "case-a" / "case.json"
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition["behavioral_claim"] = "The skill preserves evaluator authority."
        definition["authority_kind"] = "synthetic"
        definition_path.write_text(
            json.dumps(definition, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.corpus / "cases" / "case-a" / "criteria.md").write_text(
            "- The result preserves evaluator authority.\n",
            encoding="utf-8",
        )
        (
            self.corpus
            / "cases"
            / "case-a"
            / "evidence"
            / "candidate"
            / "input.md"
        ).write_text("candidate evidence\n", encoding="utf-8")
        (
            self.corpus
            / "cases"
            / "case-a"
            / "judge-reference"
            / "expected.md"
        ).write_text("Preserve evaluator authority.\n", encoding="utf-8")
        freeze_case(self.corpus, "case-a", replace=False)
        self.case_revision = digest(
            frozen_case_path(self.corpus, "case-a") / "case-manifest.json"
        )
        self.registration = create_campaign(self.state_root, self.corpus)
        self.plugin = self.root / "plugin"
        skill = self.plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        self.snapshot = capture_skill_snapshot(
            self.corpus,
            self.plugin,
            ["example-skill"],
        )
        session_id = str(uuid.uuid4())
        session, _ = register_session(self.state_root, self.corpus, session_id)
        self.session_writer = {
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        }
        self.coordinator_writer = {
            "kind": "distributed_coordinator",
            "id": "coordinator-a",
            "generation": "2" * 32,
        }
        self.evaluator_writer = {
            "kind": "experiment_evaluator",
            "id": "evaluator-a",
            "generation": "3" * 32,
        }

    def tearDown(self):
        self.temp.cleanup()

    def declaration_payload(self, *, tied: bool = False):
        case_revision = self.case_revision
        metrics = [{
            "name": "terminal_pass_rate",
            "direction": "descending",
        }]
        return {
            "title": "Candidate comparison",
            "summary": "Compare one candidate with one control",
            "snapshot_id": self.snapshot["snapshot_id"],
            "cases": [{
                "case_id": "case-a",
                "case_revision": case_revision,
            }],
            "candidate_model": "model-a",
            "candidate_timeout_seconds": 120,
            "target_os": "linux",
            "architecture": "x86_64",
            "route": "direct",
            "treatments": [
                {
                    "treatment_id": "candidate",
                    "role": "candidate",
                    "hypothesis": "Candidate improves terminal outcomes",
                    "snapshot_id": self.snapshot["snapshot_id"],
                    "treatment_identity": "b" * 64,
                    "content_fingerprint": "c" * 64,
                    "target_skill_identities": [{
                        "name": "example-skill",
                        "evaluator_fingerprint": self.snapshot["skills"][0][
                            "evaluator_skill_identity"
                        ],
                    }],
                    "provenance_ids": ["candidate-source"],
                },
                {
                    "treatment_id": "control",
                    "role": "control",
                    "hypothesis": "Control preserves the baseline",
                    "snapshot_id": self.snapshot["snapshot_id"],
                    "treatment_identity": "e" * 64,
                    "content_fingerprint": "f" * 64,
                    "target_skill_identities": [{
                        "name": "example-skill",
                        "evaluator_fingerprint": self.snapshot["skills"][0][
                            "evaluator_skill_identity"
                        ],
                    }],
                    "provenance_ids": ["control-source"],
                },
            ],
            "attempts": [
                {
                    "attempt_id": "attempt-candidate",
                    "case_id": "case-a",
                    "case_revision": case_revision,
                    "treatment_id": "candidate",
                    "repetition": 1,
                    "target_os": "linux",
                    "architecture": "x86_64",
                    "route": "direct",
                    "candidate_model": "model-a",
                    "snapshot_id": self.snapshot["snapshot_id"],
                },
                {
                    "attempt_id": "attempt-control",
                    "case_id": "case-a",
                    "case_revision": case_revision,
                    "treatment_id": "control",
                    "repetition": 1,
                    "target_os": "linux",
                    "architecture": "x86_64",
                    "route": "direct",
                    "candidate_model": "model-a",
                    "snapshot_id": self.snapshot["snapshot_id"],
                },
            ],
            "selection_rule": {
                "metrics": metrics,
                "coverage": [
                    {
                        "kind": "all_planned_attempts_terminal",
                        "value": None,
                    },
                    {
                        "kind": "field_present",
                        "value": "terminal_status",
                    },
                    {
                        "kind": "minimum_valid_repetitions_per_treatment",
                        "value": 1,
                    },
                ],
                "disqualifiers": [] if tied else [{
                    "kind": "product_failure",
                    "field": None,
                    "bound": None,
                }],
            },
        }

    def test_ablation_declaration_fields_fail_closed(self):
        payload = self.declaration_payload()
        payload["experiment_kind"] = "delta_ablation"
        payload["ablation"] = {
            "project_id": "example-project",
            "project_declaration_sha256": "1" * 64,
            "task_id": "task-1",
            "baseline_snapshot_id": "2" * 64,
            "exploratory_snapshot_id": "3" * 64,
            "candidate_snapshots": [{
                "treatment_id": "candidate",
                "snapshot_id": "4" * 64,
            }],
            "maintained_tasks": [{
                "task_id": "task-1",
                "task_fingerprint": "5" * 64,
            }],
            "instruction_changes": [{
                "instruction_id": "preserve-authority",
                "disposition": "restored",
                "reason": "Removing it regressed the maintained task.",
            }],
        }
        self.assertEqual(validate_experiment_declaration(payload), payload)
        self.assertEqual(
            experiment_plan_fingerprint(payload),
            experiment_plan_fingerprint(payload),
        )

        broken = json.loads(json.dumps(payload))
        broken["ablation"]["maintained_tasks"] = []
        with self.assertRaisesRegex(ValueError, "maintained tasks"):
            validate_experiment_declaration(broken)

        broken = json.loads(json.dumps(payload))
        broken["ablation"]["instruction_changes"][0]["reason"] = None
        with self.assertRaisesRegex(ValueError, "requires a reason"):
            validate_experiment_declaration(broken)

        broken = json.loads(json.dumps(payload))
        broken["ablation"]["candidate_snapshots"][0][
            "treatment_id"
        ] = "unknown"
        with self.assertRaisesRegex(ValueError, "candidate treatment"):
            validate_experiment_declaration(broken)

    def test_whole_skill_ablation_requires_declared_arm_treatments(self):
        payload = self.declaration_payload()
        payload["experiment_kind"] = "whole_skill_ablation"
        payload["ablation"] = {
            "project_id": "example-project",
            "project_declaration_sha256": "1" * 64,
            "arms": [{
                "arm": "lean",
                "treatment_id": "candidate",
                "snapshot_id": "2" * 64,
            }],
            "maintained_tasks": [{
                "task_id": "task-1",
                "task_fingerprint": "3" * 64,
            }],
        }
        self.assertEqual(validate_experiment_declaration(payload), payload)
        payload["ablation"]["arms"][0]["treatment_id"] = "undeclared"
        with self.assertRaisesRegex(ValueError, "arm treatment"):
            validate_experiment_declaration(payload)

    def publish_declaration(self, *, tied: bool = False, event_id: str = "4" * 32):
        payload = self.declaration_payload(tied=tied)
        return emit_experiment_activity_event(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.session_writer,
            event_type="experiment_declared",
            experiment_id="experiment-a",
            experiment_fingerprint=experiment_plan_fingerprint(payload),
            payload=payload,
            event_id=event_id,
            observed_at="2026-01-01T00:00:00+00:00",
            recorded_at="2026-01-01T00:00:01+00:00",
        )

    def result_payload(self, attempt: dict, *, passed: bool):
        return {
            "attempt": {
                key: attempt[key]
                for key in (
                    "attempt_id",
                    "case_id",
                    "case_revision",
                    "treatment_id",
                    "repetition",
                )
            },
            "execution": {
                "plan_fingerprint": self.plan_fingerprint,
                "candidate_model": "model-a",
                "candidate_timeout_seconds": 120,
                "treatment_fingerprint": (
                    "c" * 64 if attempt["treatment_id"] == "candidate" else "f" * 64
                ),
                "target_skill_identities": [{
                    "name": "example-skill",
                    "evaluator_fingerprint": self.snapshot["skills"][0][
                        "evaluator_skill_identity"
                    ],
                }],
                "target_os": "linux",
                "architecture": "x86_64",
                "route": "direct",
                "grading_route": "direct",
                "package_archive_sha256": "5" * 64,
                "candidate_package_archive_sha256": "6" * 64,
                "package_manifest_sha256": "7" * 64,
                "image_identity": "8" * 64,
                "dependency_identity": "9" * 64,
            },
            "terminal_status": "PASS" if passed else "FAIL",
            "summaries": {
                "candidate": "Candidate completed",
                "deterministic": "Deterministic checks completed",
                "product": "Product check completed",
                "judge": "Behavioral judgment completed",
            },
            "first_stage_id": f"stage-{attempt['attempt_id']}",
            "source_lineage": None,
            "candidate_rerun": False,
            "effective_result_id": f"result-{attempt['attempt_id']}",
            "selection_fields": {
                "terminal_status": "PASS" if passed else "FAIL",
                "deterministic_target_pass": passed,
                "deterministic_regression_pass": True,
                "product_pass": passed,
                "independent_behavioral_verdicts": [
                    "PASS" if passed else "FAIL",
                    "PASS" if passed else "FAIL",
                ],
            },
            "source_ids": [f"source-{attempt['attempt_id']}"],
        }

    def publish_results(self, declaration: dict, *, tied: bool = False):
        self.plan_fingerprint = declaration["subject"]["experiment_fingerprint"]
        results = []
        for index, attempt in enumerate(declaration["payload"]["attempts"], 5):
            passed = tied or attempt["treatment_id"] == "candidate"
            results.append(emit_experiment_activity_event(
                self.corpus,
                campaign_id=self.registration["campaign_id"],
                writer=self.coordinator_writer,
                event_type="distributed_result_recorded",
                experiment_id="experiment-a",
                experiment_fingerprint=self.plan_fingerprint,
                attempt_id=attempt["attempt_id"],
                payload=self.result_payload(attempt, passed=passed),
                event_id=str(index) * 32,
                observed_at=f"2026-01-01T00:01:0{index}+00:00",
                recorded_at=f"2026-01-01T00:01:1{index}+00:00",
            ))
        return results

    def adapter_artifacts(self, declaration: dict, attempt: dict, *, terminal: bool):
        root = self.root / f"adapter-{attempt['attempt_id']}-{'result' if terminal else 'stage'}"
        package_root = root / "package"
        package_root.mkdir(parents=True)
        target_skills = [{
            "skillName": "example-skill",
            "evaluatorFingerprint": self.snapshot["skills"][0][
                "evaluator_skill_identity"
            ],
        }]
        treatment_fingerprint = (
            "c" * 64 if attempt["treatment_id"] == "candidate" else "f" * 64
        )
        matrix_attempts = []
        jobs = []
        for planned in declaration["payload"]["attempts"]:
            planned_fingerprint = (
                "c" * 64
                if planned["treatment_id"] == "candidate"
                else "f" * 64
            )
            matrix_attempt = {
                "attemptId": planned["attempt_id"],
                "caseId": planned["case_id"],
                "caseRevision": planned["case_revision"],
                "treatmentId": planned["treatment_id"],
                "repetition": planned["repetition"],
                "candidateModel": planned["candidate_model"],
                "candidateTimeoutSeconds": 120,
                "treatmentFingerprint": planned_fingerprint,
                "targetSkillIdentities": target_skills,
                "targetOs": planned["target_os"],
                "architecture": planned["architecture"],
                "route": planned["route"],
                "gradingRoute": "direct",
            }
            matrix_attempts.append(matrix_attempt)
            jobs.append({
                **matrix_attempt,
                "imageId": "sha256:" + "8" * 64,
                "dependencySha256": "",
            })
        package = {
            "schemaVersion": 2,
            "campaignId": "proof-campaign",
            "experimentPlanSha256": self.plan_fingerprint,
        }
        package_path = package_root / "package-manifest.json"
        package_path.write_text(json.dumps(package), encoding="utf-8")
        manifest_sha = hashlib.sha256(package_path.read_bytes()).hexdigest()
        (package_root / "execution-matrix.json").write_text(
            json.dumps({
                "schemaVersion": 2,
                "campaignId": "proof-campaign",
                "experimentPlanSha256": self.plan_fingerprint,
                "attempts": matrix_attempts,
            }),
            encoding="utf-8",
        )
        expected_jobs = [
            {"jobName": "plan", "attemptId": None, "stage": "plan"},
            *[
                {
                    "jobName": f"macos-stage / {planned['attempt_id']}",
                    "attemptId": planned["attempt_id"],
                    "stage": "macos-stage",
                }
                for planned in declaration["payload"]["attempts"]
            ],
        ]
        plan = {
            "schemaVersion": 2,
            "experimentPlanSha256": self.plan_fingerprint,
            "packageArchiveSha256": "5" * 64,
            "candidatePackageArchiveSha256": "5" * 64,
            "packageManifestSha256": manifest_sha,
            "matrix": {"include": jobs},
            "expectedJobs": expected_jobs,
        }
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        run = {
            "repositoryId": 99,
            "repositoryFullName": "example/private-evals",
            "workflowId": 42,
            "workflowPath": ".github/workflows/distributed.yml",
            "workflowSha": "1" * 40,
            "headSha": "2" * 40,
            "headBranch": "proof",
            "event": "workflow_dispatch",
            "runId": 4242,
            "runAttempt": 1,
        }
        run_path = root / "run.json"
        run_path.write_text(json.dumps(run), encoding="utf-8")
        binding = create_dispatch_binding(plan, run)
        binding_path = root / "binding.json"
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        matrix_attempt = next(
            item for item in matrix_attempts
            if item["attemptId"] == attempt["attempt_id"]
        )
        identity = {
            "experimentPlanSha256": self.plan_fingerprint,
            "attemptId": matrix_attempt["attemptId"],
            "caseId": matrix_attempt["caseId"],
            "caseRevision": matrix_attempt["caseRevision"],
            "treatmentId": matrix_attempt["treatmentId"],
            "repetition": matrix_attempt["repetition"],
            "candidateModel": matrix_attempt["candidateModel"],
            "candidateTimeoutSeconds": 120,
            "treatmentFingerprint": treatment_fingerprint,
            "targetSkillIdentitiesFingerprint": canonical_fingerprint(target_skills),
            "targetOs": "linux",
            "architecture": "x86_64",
            "route": "direct",
            "gradingRoute": "direct",
            "packageArchiveSha256": "5" * 64,
            "candidatePackageArchiveSha256": "5" * 64,
            "packageManifestSha256": manifest_sha,
        }
        receipt = {
            "schemaVersion": 2,
            "caseId": attempt["case_id"],
            "caseRevision": attempt["case_revision"],
            "treatmentId": attempt["treatment_id"],
            "repetition": attempt["repetition"],
            "executionIdentity": identity,
            "executionIdentitySha256": canonical_fingerprint(identity),
            "candidate": {
                "candidateModel": "model-a",
                "treatmentFingerprint": treatment_fingerprint,
                "targetSkillIdentities": target_skills,
                "boundaryAudit": {"passed": True},
                "exitCode": 0,
            },
            "status": "PASS" if terminal else "PENDING_LINUX_FINALIZATION",
        }
        if terminal:
            receipt.update({
                "deterministic": {
                    "targetPassed": True,
                    "regressionPassed": True,
                },
                "product": {"passed": True},
                "judges": [
                    {"judgment": {"verdict": "PASS"}},
                    {"judgment": {"verdict": "PASS"}},
                ],
                "candidateRerun": False,
            })
        else:
            receipt.update({
                "candidateRerunRequired": False,
                "product": {"passed": True},
                "hostDeterministic": {
                    "targetPassed": True,
                    "regressionPassed": True,
                },
            })
        receipt_path = root / "receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        artifact_path = root / "retained.tar.gz"
        artifact_path.write_bytes(b"retained artifact")
        retention_path = root / "retention.json"
        retention_path.write_text(json.dumps({
            "schema_version": 1,
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "source_ids": [f"source-{attempt['attempt_id']}"],
        }), encoding="utf-8")
        observation_path = root / "observation.json"
        observation_path.write_text(json.dumps({
            "schema_version": 3,
            "repository": "example/private-evals",
            "host": "github.com",
            "non_atomic": True,
            "observations": [{
                "run": {
                    "id": 4242,
                    "workflow_id": 42,
                    "path": ".github/workflows/distributed.yml",
                    "event": "workflow_dispatch",
                    "head_sha": "2" * 40,
                    "head_branch": "proof",
                    "run_attempt": 1,
                    "status": "in_progress",
                    "conclusion": None,
                    "repository": {
                        "id": 99,
                        "full_name": "example/private-evals",
                        "private": True,
                    },
                },
                "provenance": {"source": "direct", "call": 1},
                "jobs": [
                    {
                        "id": index + 1,
                        "name": job["jobName"],
                        "status": "in_progress",
                        "conclusion": None,
                        "run_id": 4242,
                        "run_attempt": 1,
                        "head_sha": "2" * 40,
                        "started_at": "2026-01-01T00:00:00Z",
                        "completed_at": None,
                    }
                    for index, job in enumerate(expected_jobs)
                ],
                "jobs_provenance": {"source": "jobs", "calls": [2]},
            }],
            "calls": [{}, {}],
            "call_count": 2,
            "projected_response_bytes": 100,
            "client_wall_seconds": 0.1,
            "coverage": {
                "scope": "requested-runs-and-exact-jobs-only",
                "repository_enumerated": False,
            },
        }), encoding="utf-8")
        return {
            "package_root": package_root,
            "plan": plan_path,
            "run": run_path,
            "binding": binding_path,
            "receipt": receipt_path,
            "artifact": artifact_path,
            "retention": retention_path,
            "observation": observation_path,
        }

    def test_writer_ownership_is_exact_for_every_variant(self):
        owner_by_type = {
            "experiment_declared": "session",
            "cloud_dispatch_bound": "distributed_coordinator",
            "cloud_transport_observed": "cloud_observer",
            "distributed_stage_recorded": "distributed_coordinator",
            "distributed_result_recorded": "distributed_coordinator",
            "experiment_selection_recorded": "experiment_evaluator",
        }
        for event_type in EXPERIMENT_EVENT_TYPES:
            wrong_kind = (
                "cloud_observer"
                if owner_by_type[event_type] != "cloud_observer"
                else "experiment_evaluator"
            )
            event = {
                "schema_version": 1,
                "event_id": "a" * 32,
                "event_type": event_type,
                "campaign_id": self.registration["campaign_id"],
                "writer": {
                    "kind": wrong_kind,
                    "id": "wrong-owner",
                    "generation": "b" * 32,
                },
                "observed_at": "2026-01-01T00:00:00+00:00",
                "recorded_at": "2026-01-01T00:00:01+00:00",
                "subject": {
                    "experiment_id": "experiment-a",
                    "experiment_fingerprint": "c" * 64,
                    "attempt_id": None,
                    "run_binding_fingerprint": None,
                    "selection_rule_fingerprint": None,
                },
                "payload": {},
            }
            with self.subTest(event_type=event_type):
                with self.assertRaisesRegex(ValueError, "does not own"):
                    validate_experiment_activity_event(event)

    def test_selection_is_computed_exactly_and_premature_writes_nothing(self):
        declaration = self.publish_declaration()
        before = experiment_activity_records(self.corpus)[0]
        incomplete = emit_experiment_selection(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.evaluator_writer,
            declaration=declaration,
            terminal_results=[],
            event_id="7" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
            recorded_at="2026-01-01T00:02:01+00:00",
        )
        self.assertEqual(incomplete["status"], "selection_incomplete")
        self.assertEqual(experiment_activity_records(self.corpus)[0], before)

        results = self.publish_results(declaration)
        computed = compute_experiment_selection(declaration, results)
        self.assertEqual(computed["status"], "selected")
        self.assertEqual(computed["selected_treatment_id"], "candidate")
        self.assertEqual(
            computed["metrics"]["candidate"]["terminal_pass_rate"],
            {"numerator": 1, "denominator": 1},
        )

        with self.assertRaisesRegex(ValueError, "must be computed"):
            emit_experiment_activity_event(
                self.corpus,
                campaign_id=self.registration["campaign_id"],
                writer=self.evaluator_writer,
                event_type="experiment_selection_recorded",
                experiment_id="experiment-a",
                experiment_fingerprint=self.plan_fingerprint,
                payload={**computed, "selected_treatment_id": "control"},
            )

    def test_tie_is_no_selection_and_identical_rerun_is_byte_idempotent(self):
        declaration = self.publish_declaration(tied=True)
        results = self.publish_results(declaration, tied=True)
        kwargs = {
            "campaign_id": self.registration["campaign_id"],
            "writer": self.evaluator_writer,
            "declaration": declaration,
            "terminal_results": results,
            "event_id": "7" * 32,
            "observed_at": "2026-01-01T00:02:00+00:00",
            "recorded_at": "2026-01-01T00:02:01+00:00",
        }
        first = emit_experiment_selection(self.corpus, **kwargs)
        second = emit_experiment_selection(self.corpus, **kwargs)
        self.assertEqual(second, first)
        self.assertEqual(first["payload"]["status"], "no_selection")
        self.assertIsNone(first["payload"]["selected_treatment_id"])
        self.assertEqual(first["payload"]["reasons"], ["metric_tie"])

    def test_terminal_records_from_different_writers_remain_conflicted(self):
        declaration = self.publish_declaration()
        results = self.publish_results(declaration)
        for index, writer_id in enumerate(("evaluator-a", "evaluator-b"), 7):
            emit_experiment_selection(
                self.corpus,
                campaign_id=self.registration["campaign_id"],
                writer={
                    "kind": "experiment_evaluator",
                    "id": writer_id,
                    "generation": str(index) * 32,
                },
                declaration=declaration,
                terminal_results=results,
                event_id=str(index) * 32,
                observed_at=f"2026-01-01T00:02:0{index}+00:00",
                recorded_at=f"2026-01-01T00:02:1{index}+00:00",
            )
        records, conflicts, invalid = experiment_activity_records(self.corpus)
        self.assertEqual(
            len([
                item for item in records
                if item["event_type"] == "experiment_selection_recorded"
            ]),
            2,
        )
        self.assertEqual(
            {item["reason"] for item in conflicts},
            {"terminal_selection_conflicted"},
        )
        self.assertEqual(invalid, [])

    def test_malformed_foreign_and_altered_selection_are_isolated(self):
        declaration = self.publish_declaration()
        results = self.publish_results(declaration)
        selection = emit_experiment_selection(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.evaluator_writer,
            declaration=declaration,
            terminal_results=results,
            event_id="7" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
            recorded_at="2026-01-01T00:02:01+00:00",
        )
        root = writer_directory(self.corpus, self.evaluator_writer)
        extension = root / "extensions" / "experiment-activity-v1"
        (extension / f"{'8' * 32}.json").write_text(
            '{"schema_version":1,"broken":true}\n',
            encoding="utf-8",
        )
        foreign = {**selection, "event_id": "9" * 32, "campaign_id": "f" * 32}
        (extension / f"{'9' * 32}.json").write_text(
            json.dumps(foreign) + "\n",
            encoding="utf-8",
        )
        altered = json.loads(json.dumps(selection))
        altered["event_id"] = "a" * 32
        altered["payload"]["selected_treatment_id"] = "control"
        (extension / f"{'a' * 32}.json").write_text(
            json.dumps(altered) + "\n",
            encoding="utf-8",
        )

        records, _, invalid = experiment_activity_records(self.corpus)
        self.assertEqual(
            len([
                item for item in records
                if item["event_type"] == "experiment_selection_recorded"
            ]),
            1,
        )
        self.assertEqual(len(invalid), 3)
        self.assertIn("experiment_selection_invalid", {
            item["reason"] for item in invalid
        })
        self.assertEqual(
            len([
                item for item in records
                if item["event_type"] == "experiment_declared"
            ]),
            1,
        )

    def test_owner_selected_source_does_not_persist_paths_or_private_metadata(self):
        payload = self.declaration_payload()
        source = self.root / "PRIVATE-SOURCE-PATH.json"
        selected = {
            "schema_version": 1,
            "experiment_id": "experiment-a",
            "experiment_fingerprint": experiment_plan_fingerprint(payload),
            "payload": payload,
        }
        source.write_text(json.dumps(selected), encoding="utf-8")
        receipt = experiment_declaration_dashboard(
            self.corpus,
            source,
            session_id=self.session_writer["id"],
            event_id="4" * 32,
            observed_at="2026-01-01T00:00:00+00:00",
            root=self.state_root,
        )
        self.assertEqual(receipt["event_type"], "experiment_declared")
        encoded = json.dumps(experiment_activity_records(self.corpus))
        self.assertNotIn(str(source), encoded)
        for marker in (
            "repository",
            "workflow",
            "run_id",
            "url",
            "artifact_path",
        ):
            self.assertNotIn(marker, encoded)

        selected["repository"] = "private/repository"
        source.write_text(json.dumps(selected), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            experiment_declaration_dashboard(
                self.corpus,
                source,
                session_id=self.session_writer["id"],
                root=self.state_root,
            )

    def test_cli_routes_owner_selected_activity_and_selection(self):
        payload = self.declaration_payload()
        source = self.root / "declaration.json"
        source.write_text(json.dumps({
            "schema_version": 1,
            "experiment_id": "experiment-a",
            "experiment_fingerprint": experiment_plan_fingerprint(payload),
            "payload": payload,
        }), encoding="utf-8")
        args = dashboard_parser().parse_args([
            "dashboard",
            "experiment-declaration",
            str(self.corpus),
            str(source),
            "--session-id",
            self.session_writer["id"],
            "--event-id",
            "4" * 32,
            "--state-root",
            str(self.state_root),
        ])
        receipt = dashboard_dispatch(args)
        self.assertEqual(receipt["event_type"], "experiment_declared")

        selection_args = dashboard_parser().parse_args([
            "dashboard",
            "experiment-selection",
            str(self.corpus),
            "--declaration-event",
            receipt["event_id"],
            "--writer-id",
            self.evaluator_writer["id"],
            "--writer-generation",
            self.evaluator_writer["generation"],
            "--state-root",
            str(self.state_root),
        ])
        incomplete = dashboard_dispatch(selection_args)
        self.assertEqual(incomplete["status"], "selection_incomplete")

        declaration = next(
            item
            for item in experiment_activity_records(self.corpus)[0]
            if item["event_id"] == receipt["event_id"]
        )
        results = self.publish_results(declaration)
        terminal_args = dashboard_parser().parse_args([
            "dashboard",
            "experiment-selection",
            str(self.corpus),
            "--declaration-event",
            receipt["event_id"],
            "--writer-id",
            self.evaluator_writer["id"],
            "--writer-generation",
            self.evaluator_writer["generation"],
            "--event-id",
            "7" * 32,
            "--state-root",
            str(self.state_root),
        ])
        terminal = dashboard_dispatch(terminal_args)
        self.assertEqual(terminal["status"], "selected")
        self.assertEqual(terminal["event_type"], "experiment_selection_recorded")

    def test_validator_backed_adapters_build_events_from_owner_artifacts(self):
        declaration = self.publish_declaration()
        self.plan_fingerprint = declaration["subject"]["experiment_fingerprint"]
        stage_attempt, result_attempt = declaration["payload"]["attempts"]
        stage = self.adapter_artifacts(declaration, stage_attempt, terminal=False)
        result = self.adapter_artifacts(declaration, result_attempt, terminal=True)

        dispatch = experiment_dispatch_dashboard(
            self.corpus,
            stage["plan"],
            stage["run"],
            stage["binding"],
            experiment_id="experiment-a",
            opaque_source_id="dispatch-source",
            writer_id=self.coordinator_writer["id"],
            writer_generation=self.coordinator_writer["generation"],
            event_id="b" * 32,
            root=self.state_root,
        )
        self.assertEqual(dispatch["event_type"], "cloud_dispatch_bound")
        observation = experiment_observation_dashboard(
            self.corpus,
            stage["observation"],
            stage["plan"],
            stage["run"],
            stage["binding"],
            experiment_id="experiment-a",
            opaque_source_id="observer-source",
            writer_id="observer-a",
            writer_generation="c" * 32,
            event_id="c" * 32,
            root=self.state_root,
        )
        self.assertEqual(observation["event_type"], "cloud_transport_observed")
        stage_event = experiment_stage_dashboard(
            self.corpus,
            stage["package_root"],
            stage["plan"],
            stage["receipt"],
            stage["artifact"],
            stage["retention"],
            experiment_id="experiment-a",
            attempt_id=stage_attempt["attempt_id"],
            writer_id=self.coordinator_writer["id"],
            writer_generation=self.coordinator_writer["generation"],
            event_id="d" * 32,
            root=self.state_root,
        )
        self.assertEqual(stage_event["event_type"], "distributed_stage_recorded")
        result_event = experiment_result_dashboard(
            self.corpus,
            result["package_root"],
            result["plan"],
            result["receipt"],
            result["artifact"],
            result["retention"],
            experiment_id="experiment-a",
            attempt_id=result_attempt["attempt_id"],
            writer_id=self.coordinator_writer["id"],
            writer_generation=self.coordinator_writer["generation"],
            event_id="e" * 32,
            root=self.state_root,
        )
        self.assertEqual(result_event["event_type"], "distributed_result_recorded")

        tampered = json.loads(result["receipt"].read_text(encoding="utf-8"))
        tampered["executionIdentity"]["packageArchiveSha256"] = "0" * 64
        result["receipt"].write_text(json.dumps(tampered), encoding="utf-8")
        result["retention"].write_text(json.dumps({
            "schema_version": 1,
            "receipt_sha256": hashlib.sha256(
                result["receipt"].read_bytes()
            ).hexdigest(),
            "artifact_sha256": hashlib.sha256(
                result["artifact"].read_bytes()
            ).hexdigest(),
            "source_ids": ["tampered-source"],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "execution identity"):
            experiment_result_dashboard(
                self.corpus,
                result["package_root"],
                result["plan"],
                result["receipt"],
                result["artifact"],
                result["retention"],
                experiment_id="experiment-a",
                attempt_id=result_attempt["attempt_id"],
                writer_id=self.coordinator_writer["id"],
                writer_generation=self.coordinator_writer["generation"],
                root=self.state_root,
            )

    def test_dispatch_refuses_a_plan_that_differs_from_the_declaration(self):
        declaration = self.publish_declaration()
        self.plan_fingerprint = declaration["subject"]["experiment_fingerprint"]
        artifacts = self.adapter_artifacts(
            declaration,
            declaration["payload"]["attempts"][0],
            terminal=True,
        )
        plan = json.loads(artifacts["plan"].read_text(encoding="utf-8"))
        plan["matrix"]["include"][0]["caseId"] = "undeclared-case"
        artifacts["plan"].write_text(json.dumps(plan), encoding="utf-8")
        run = json.loads(artifacts["run"].read_text(encoding="utf-8"))
        artifacts["binding"].write_text(
            json.dumps(create_dispatch_binding(plan, run)),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "differs from its declaration"):
            experiment_dispatch_dashboard(
                self.corpus,
                artifacts["plan"],
                artifacts["run"],
                artifacts["binding"],
                experiment_id="experiment-a",
                opaque_source_id="dispatch-source",
                writer_id=self.coordinator_writer["id"],
                writer_generation=self.coordinator_writer["generation"],
                root=self.state_root,
            )

    def test_selection_refuses_result_subsets_and_invalidates_prior_selection(self):
        declaration = self.publish_declaration()
        results = self.publish_results(declaration)
        selected = emit_experiment_selection(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.evaluator_writer,
            declaration=declaration,
            terminal_results=results,
            event_id="7" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
        )
        duplicate = json.loads(json.dumps(results[0]))
        duplicate["event_id"] = "8" * 32
        emit_experiment_activity_event(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.coordinator_writer,
            event_type="distributed_result_recorded",
            experiment_id="experiment-a",
            experiment_fingerprint=self.plan_fingerprint,
            attempt_id=duplicate["subject"]["attempt_id"],
            payload=duplicate["payload"],
            event_id=duplicate["event_id"],
            observed_at="2026-01-01T00:03:00+00:00",
        )
        incomplete = experiment_selection_dashboard(
            self.corpus,
            declaration["event_id"],
            writer_id="evaluator-b",
            writer_generation="8" * 32,
            root=self.state_root,
        )
        self.assertEqual(incomplete["status"], "selection_incomplete")
        self.assertEqual(incomplete["reasons"], ["result_conflicted"])
        records, _, invalid = experiment_activity_records(self.corpus)
        self.assertNotIn(selected["event_id"], {
            item["event_id"] for item in records
        })
        self.assertIn("experiment_selection_invalid", {
            item["reason"] for item in invalid
        })
        projection = campaign_projection(
            self.state_root,
            self.registration["campaign_id"],
        )
        self.assertEqual(
            projection["experiments"]["items"][0]["selection"]["status"],
            "conflicted",
        )

    def test_conflicted_result_event_invalidates_prior_selection(self):
        declaration = self.publish_declaration()
        results = self.publish_results(declaration)
        selected = emit_experiment_selection(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.evaluator_writer,
            declaration=declaration,
            terminal_results=results,
            event_id="7" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
        )
        conflicting_payload = json.loads(json.dumps(results[0]["payload"]))
        conflicting_payload["terminal_status"] = "FAIL"
        conflicting_payload["selection_fields"]["terminal_status"] = "FAIL"
        with self.assertRaisesRegex(ValueError, "conflicts"):
            emit_experiment_activity_event(
                self.corpus,
                campaign_id=self.registration["campaign_id"],
                writer=self.coordinator_writer,
                event_type="distributed_result_recorded",
                experiment_id="experiment-a",
                experiment_fingerprint=self.plan_fingerprint,
                attempt_id=results[0]["subject"]["attempt_id"],
                payload=conflicting_payload,
                event_id=results[0]["event_id"],
                observed_at="2026-01-01T00:03:00+00:00",
            )
        records, conflicts, invalid = experiment_activity_records(self.corpus)
        self.assertIn(results[0]["event_id"], {
            item["event_id"] for item in conflicts
        })
        self.assertNotIn(selected["event_id"], {
            item["event_id"] for item in records
        })
        self.assertIn("experiment_selection_invalid", {
            item["reason"] for item in invalid
        })

    def test_cross_campaign_publication_is_refused_without_a_record(self):
        payload = self.declaration_payload()
        with self.assertRaisesRegex(ValueError, "campaign identity"):
            emit_experiment_activity_event(
                self.corpus,
                campaign_id="f" * 32,
                writer=self.session_writer,
                event_type="experiment_declared",
                experiment_id="experiment-a",
                experiment_fingerprint=experiment_plan_fingerprint(payload),
                payload=payload,
                event_id="4" * 32,
                observed_at="2026-01-01T00:00:00+00:00",
                recorded_at="2026-01-01T00:00:01+00:00",
            )
        self.assertEqual(experiment_activity_records(self.corpus), ([], [], []))

    def test_projection_separates_terminal_selection_and_unknown_cost(self):
        declaration = self.publish_declaration()
        results = self.publish_results(declaration)
        emit_experiment_selection(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.evaluator_writer,
            declaration=declaration,
            terminal_results=results,
            event_id="7" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
            recorded_at="2026-01-01T00:02:01+00:00",
        )

        projection = campaign_projection(
            self.state_root,
            self.registration["campaign_id"],
        )
        experiments = projection["experiments"]
        self.assertEqual(experiments["status"], "available")
        self.assertEqual(experiments["counts"]["terminal"], 2)
        self.assertEqual(projection["availability"]["cloud_activity"], "available")
        item = experiments["items"][0]
        self.assertEqual(item["selection"]["status"], "selected")
        self.assertEqual(
            item["selection"]["selected_treatment_id"],
            "candidate",
        )
        self.assertFalse(item["cost"]["complete"])
        self.assertIsNone(item["cost"]["credits"])
        self.assertEqual(
            {row["state"] for row in item["activity"]},
            {"terminal"},
        )
        self.assertEqual(
            len(projection["task_details"][0]["experiment_attempts"]),
            2,
        )
        encoded = json.dumps(projection, sort_keys=True)
        for private_field in (
            "repository",
            "workflow_path",
            "run_id",
            "artifact_path",
        ):
            self.assertNotIn(private_field, encoded)

        index = campaign_index_projection(self.state_root)
        self.assertEqual(index["cloud_counts"]["terminal"], 2)
        self.assertEqual(index["availability"]["cloud_activity"], "available")

    def test_projection_keeps_transport_stage_and_result_authority_distinct(self):
        declaration = self.publish_declaration()
        self.plan_fingerprint = declaration["subject"]["experiment_fingerprint"]
        jobs = sorted([
            {
                "job_name": "plan",
                "attempt_id": None,
                "stage_kind": "plan",
            },
            {
                "job_name": "linux-final / attempt-candidate",
                "attempt_id": "attempt-candidate",
                "stage_kind": "linux-final",
            },
            {
                "job_name": "linux-final / attempt-control",
                "attempt_id": "attempt-control",
                "stage_kind": "linux-final",
            },
        ], key=lambda item: item["job_name"])
        run_binding = "d" * 64
        emit_experiment_activity_event(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.coordinator_writer,
            event_type="cloud_dispatch_bound",
            experiment_id="experiment-a",
            experiment_fingerprint=self.plan_fingerprint,
            run_binding_fingerprint=run_binding,
            payload={
                "plan_fingerprint": self.plan_fingerprint,
                "package_archive_sha256": "5" * 64,
                "candidate_package_archive_sha256": "6" * 64,
                "package_manifest_sha256": "7" * 64,
                "workflow_revision_fingerprint": "8" * 64,
                "jobs": jobs,
                "opaque_source_id": "dispatch-source",
            },
            event_id="b" * 32,
            observed_at="2026-01-01T00:01:00+00:00",
            recorded_at="2026-01-01T00:01:01+00:00",
        )
        observer = {
            "kind": "cloud_observer",
            "id": "observer-a",
            "generation": "c" * 32,
        }
        emit_experiment_activity_event(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=observer,
            event_type="cloud_transport_observed",
            experiment_id="experiment-a",
            experiment_fingerprint=self.plan_fingerprint,
            run_binding_fingerprint=run_binding,
            payload={
                "observer_snapshot_fingerprint": "9" * 64,
                "observations": [
                    {
                        "source_index": index,
                        "job_name": job["job_name"],
                        "attempt_id": job["attempt_id"],
                        "stage_kind": job["stage_kind"],
                        "status": (
                            "completed"
                            if job["attempt_id"] != "attempt-control"
                            else "in_progress"
                        ),
                        "conclusion": (
                            "success"
                            if job["attempt_id"] != "attempt-control"
                            else None
                        ),
                        "started_at": "2026-01-01T00:01:00+00:00",
                        "completed_at": (
                            "2026-01-01T00:01:30+00:00"
                            if job["attempt_id"] != "attempt-control"
                            else None
                        ),
                    }
                    for index, job in enumerate(jobs)
                ],
                "coverage": {"expected": 3, "observed": 3},
                "non_atomic": True,
                "provenance": "exact-known-jobs",
                "call_count": 2,
                "projected_response_bytes": 1024,
                "client_wall_seconds": 1.5,
                "opaque_source_id": "observer-source",
            },
            event_id="c" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
            recorded_at="2026-01-01T00:02:01+00:00",
        )
        attempt = declaration["payload"]["attempts"][0]
        emit_experiment_activity_event(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=self.coordinator_writer,
            event_type="distributed_stage_recorded",
            experiment_id="experiment-a",
            experiment_fingerprint=self.plan_fingerprint,
            attempt_id=attempt["attempt_id"],
            payload={
                "attempt": {
                    key: attempt[key]
                    for key in (
                        "attempt_id",
                        "case_id",
                        "case_revision",
                        "treatment_id",
                        "repetition",
                    )
                },
                "execution": {
                    "plan_fingerprint": self.plan_fingerprint,
                    "candidate_model": "model-a",
                    "candidate_timeout_seconds": 120,
                    "treatment_fingerprint": "c" * 64,
                    "target_skill_identities": [{
                        "name": "example-skill",
                        "evaluator_fingerprint": self.snapshot["skills"][0][
                            "evaluator_skill_identity"
                        ],
                    }],
                    "target_os": "linux",
                    "architecture": "x86_64",
                    "route": "direct",
                    "grading_route": "direct",
                    "package_archive_sha256": "5" * 64,
                    "candidate_package_archive_sha256": "6" * 64,
                    "package_manifest_sha256": "7" * 64,
                    "image_identity": "8" * 64,
                    "dependency_identity": "9" * 64,
                },
                "stage_kind": "linux-final",
                "status": "PENDING_LINUX_FINALIZATION",
                "terminal": False,
                "candidate_rerun_required": False,
                "summaries": {
                    "candidate": "Complete",
                    "deterministic": "Complete",
                    "product": None,
                    "judge": None,
                },
                "retention_manifest_sha256": "a" * 64,
                "source_artifact_sha256": "b" * 64,
                "source_ids": ["stage-source"],
            },
            event_id="d" * 32,
            observed_at="2026-01-01T00:03:00+00:00",
            recorded_at="2026-01-01T00:03:01+00:00",
        )

        projection = campaign_projection(
            self.state_root,
            self.registration["campaign_id"],
        )
        rows = {
            item["attempt_id"]: item
            for item in projection["experiments"]["activity"]
        }
        self.assertEqual(
            rows["attempt-candidate"]["state"],
            "distributed_pending",
        )
        self.assertEqual(
            rows["attempt-candidate"]["transport_conclusions"],
            ["success"],
        )
        self.assertIsNone(rows["attempt-candidate"]["evaluator_result"])
        self.assertEqual(
            rows["attempt-control"]["state"],
            "cloud_nonterminal",
        )
        self.assertTrue(rows["attempt-control"]["non_atomic"])
        self.assertEqual(
            projection["experiments"]["counts"]["distributed_pending"],
            1,
        )
        self.assertEqual(
            projection["experiments"]["counts"]["cloud_nonterminal"],
            1,
        )

        emit_experiment_activity_event(
            self.corpus,
            campaign_id=self.registration["campaign_id"],
            writer=observer,
            event_type="cloud_transport_observed",
            experiment_id="experiment-a",
            experiment_fingerprint=self.plan_fingerprint,
            run_binding_fingerprint=run_binding,
            payload={
                "observer_snapshot_fingerprint": "e" * 64,
                "observations": [
                    {
                        "source_index": index,
                        "job_name": job["job_name"],
                        "attempt_id": job["attempt_id"],
                        "stage_kind": job["stage_kind"],
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-01-01T00:01:00+00:00",
                        "completed_at": "2026-01-01T00:03:30+00:00",
                    }
                    for index, job in enumerate(jobs)
                ],
                "coverage": {"expected": 3, "observed": 3},
                "non_atomic": True,
                "provenance": "exact-known-jobs",
                "call_count": 2,
                "projected_response_bytes": 1024,
                "client_wall_seconds": 1.5,
                "opaque_source_id": "observer-source-later",
            },
            event_id="e" * 32,
            observed_at="2026-01-01T00:04:00+00:00",
            recorded_at="2026-01-01T00:04:01+00:00",
        )
        updated = campaign_projection(
            self.state_root,
            self.registration["campaign_id"],
        )
        updated_rows = {
            item["attempt_id"]: item
            for item in updated["experiments"]["activity"]
        }
        self.assertEqual(
            updated_rows["attempt-control"]["state"],
            "cloud_completed_awaiting_result",
        )
        self.assertEqual(
            updated_rows["attempt-control"]["transport_statuses"],
            ["completed"],
        )


if __name__ == "__main__":
    unittest.main()
