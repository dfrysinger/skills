#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import base64
import signal
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dashboard_cli import (
    STARTED_PROCESSES,
    dispatch,
    register_dashboard,
    service_status,
    stop_service,
    task_progress_dashboard,
)
from dashboard_server import DashboardHTTPServer
from dashboard_state import (
    capture_skill_snapshot,
    create_campaign,
    emit_lineage_event,
    emit_task_progress_event,
    extension_records,
    register_session,
)
from holdout_dashboard import (
    create_authority,
    holdout_projection,
    import_receipt,
    sign_private_receipt,
)
from project_dashboard import (
    _ablation_qualifies_selected_revision,
    _ablation_projection,
    _snapshot_catalog,
    _task_phase,
    _task_safe_progress,
    _distributed_projection,
    _task_scorecard,
    archived_project_declaration,
    binding_fingerprint,
    canonical_project_declaration,
    project_declaration_fingerprint,
    project_index_projection,
    project_projection,
    reconciled_project,
    task_fingerprint,
    unassigned_projection,
)
from skill_eval import (
    RunLease,
    RunLeaseError,
    SuiteInfrastructureError,
    _run_suite_impl,
    add_case,
    digest,
    freeze_case,
    frozen_case_path,
    init_corpus,
    run_suite,
)


def write_plugin(root: Path, text: str = "# Example\n") -> Path:
    plugin = root / f"plugin-{uuid.uuid4().hex}"
    skill = plugin / "skills" / "example-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(text, encoding="utf-8")
    return plugin


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"

    def tearDown(self):
        try:
            stop_service(self.state_root)
        except (OSError, ValueError):
            pass
        self.temp.cleanup()

    def corpus(self, name: str, cases: tuple[str, ...] = ("case-one",)) -> Path:
        root = self.root / name
        init_corpus(root)
        for case_id in cases:
            add_case(root, case_id, "example-skill", ["candidate"])
            case_root = root / "cases" / case_id
            definition_path = case_root / "case.json"
            definition = json.loads(definition_path.read_text())
            definition["behavioral_claim"] = "The skill handles the example."
            definition["authority_kind"] = "synthetic"
            definition_path.write_text(
                json.dumps(definition, indent=2) + "\n"
            )
            (
                case_root / "evidence" / "candidate" / "product.md"
            ).write_text("candidate evidence\n", encoding="utf-8")
            (case_root / "judge-reference" / "gold.md").write_text(
                "hidden expected behavior\n",
                encoding="utf-8",
            )
            (case_root / "criteria.md").write_text(
                "candidate must handle the example\n",
                encoding="utf-8",
            )
            freeze_case(root, case_id, replace=False)
        return root

    def declaration(
        self,
        corpus: Path,
        *,
        project_id: str = "example-project",
        title: str = "Improve example skill",
        goal: str = "Pass the declared behavior checks.",
        supersedes: str | None = None,
        task_summary: str = "Handle the declared behavior.",
    ) -> dict:
        cases = json.loads((corpus / "corpus.json").read_text())["cases"]
        tasks = []
        bindings = []
        for index, case_id in enumerate(cases, start=1):
            task_id = f"task-{index}"
            tasks.append({
                "task_id": task_id,
                "title": f"Task {index}",
                "summary": task_summary,
                "qualification": {
                    "kind": "all_bound_cases",
                    "required_roles": ["development"],
                    "minimum_terminal_repetitions_per_case": 1,
                    "required_passes_per_case": 1,
                },
            })
            bindings.append({
                "binding_id": f"binding-{index}",
                "case_id": case_id,
                "case_revision": digest(
                    frozen_case_path(corpus, case_id) / "case-manifest.json"
                ),
                "task_id": task_id,
                "role": "development",
                "safe_progress": None,
            })
        return {
            "schema_version": 1,
            "supersedes": supersedes,
            "project_id": project_id,
            "title": title,
            "goal": goal,
            "target_skills": ["example-skill"],
            "tasks": tasks,
            "case_bindings": bindings,
            "holdout_requirements": [{
                "holdout_set_id": "transfer-v1",
                "summary": "Reserved transfer checks",
                "required_claim": "transfer",
                "task_ids": [item["task_id"] for item in tasks],
                "authority_id": "independent-evaluator",
            }],
        }

    def write_declaration(self, corpus: Path, value: dict) -> dict:
        canonical = canonical_project_declaration(value)
        (corpus / "evaluation-project.json").write_text(
            json.dumps(canonical, indent=2) + "\n",
            encoding="utf-8",
        )
        return canonical


class ProjectDeclarationTests(ProjectFixture):
    def test_two_corpora_merge_only_by_explicit_project_id(self):
        first = self.corpus("attempt-r1")
        second = self.corpus("attempt-r2")
        unrelated = self.corpus("attempt-r3")
        self.write_declaration(first, self.declaration(first))
        self.write_declaration(second, self.declaration(second))
        create_campaign(self.state_root, first)
        create_campaign(self.state_root, second)
        unrelated_registration = create_campaign(self.state_root, unrelated)

        index = project_index_projection(self.state_root)
        self.assertEqual(
            [item["project_id"] for item in index["projects"]],
            ["example-project"],
        )
        project = reconciled_project(self.state_root, "example-project")
        self.assertEqual(len(project["sources"]), 2)
        self.assertEqual(
            unassigned_projection(self.state_root)["campaigns"],
            [{
                "campaign_id": unrelated_registration["campaign_id"],
                "corpus_name": "attempt-r3",
                "target_skills": ["example-skill"],
            }],
        )

    def test_unavailable_corpus_does_not_recreate_or_break_project_index(self):
        corpus = self.corpus("unavailable-source")
        self.write_declaration(corpus, self.declaration(corpus))
        create_campaign(self.state_root, corpus)
        moved = self.root / "moved-source"
        corpus.rename(moved)

        index = project_index_projection(self.state_root)

        self.assertEqual(
            [item["project_id"] for item in index["projects"]],
            ["example-project"],
        )
        self.assertFalse(corpus.exists())
        projection = project_projection(self.state_root, "example-project")
        self.assertEqual(
            projection["selected_revision"]["status"],
            "conflicted",
        )

    def test_project_index_counts_regressed_tasks_separately(self):
        corpus = self.corpus("regressed-index")
        self.write_declaration(corpus, self.declaration(corpus))
        create_campaign(self.state_root, corpus)
        projection = {
            "project": {
                "project_id": "example-project",
                "title": "Improve example skill",
                "goal": "Pass the declared behavior checks.",
                "target_skills": ["example-skill"],
                "availability": "available",
            },
            "selected_revision": {"status": "available"},
            "tasks": [
                {"result": "passing"},
                {"result": "regressed"},
            ],
            "runs": [],
        }

        with mock.patch(
            "project_dashboard.project_projection",
            return_value=projection,
        ):
            index = project_index_projection(self.state_root)

        self.assertEqual(index["projects"][0]["task_counts"], {
            "passing": 1,
            "not_passing": 0,
            "regressed": 1,
            "unavailable": 0,
        })

    def test_conflicting_task_is_visible_and_excluded(self):
        first = self.corpus("first")
        second = self.corpus("second")
        self.write_declaration(first, self.declaration(first))
        self.write_declaration(
            second,
            self.declaration(second, task_summary="Different meaning."),
        )
        create_campaign(self.state_root, first)
        create_campaign(self.state_root, second)

        project = reconciled_project(self.state_root, "example-project")
        self.assertEqual(project["tasks"], [])
        self.assertEqual(project["conflicts"]["tasks"], ["task-1"])

    def test_revision_requires_exact_supersedes_and_preserves_archive(self):
        corpus = self.corpus("revision")
        initial = self.write_declaration(corpus, self.declaration(corpus))
        registration = create_campaign(self.state_root, corpus)
        initial_sha = project_declaration_fingerprint(initial)

        revised = self.declaration(
            corpus,
            supersedes=initial_sha,
            task_summary="Corrected project metadata.",
        )
        revised = self.write_declaration(corpus, revised)
        create_campaign(self.state_root, corpus)
        revised_sha = project_declaration_fingerprint(revised)
        self.assertNotEqual(initial_sha, revised_sha)
        self.assertEqual(
            archived_project_declaration(corpus, initial_sha),
            initial,
        )
        self.assertEqual(
            archived_project_declaration(corpus, revised_sha),
            revised,
        )
        self.assertEqual(
            reconciled_project(
                self.state_root,
                "example-project",
            )["sources"][0]["registration"]["campaign_id"],
            registration["campaign_id"],
        )

        stale = self.declaration(
            corpus,
            supersedes=initial_sha,
            task_summary="Another edit.",
        )
        self.write_declaration(corpus, stale)
        with self.assertRaisesRegex(ValueError, "stale revision"):
            create_campaign(self.state_root, corpus)

    def test_revision_omission_is_not_deletion(self):
        corpus = self.corpus("additive", ("case-one", "case-two"))
        initial = self.write_declaration(corpus, self.declaration(corpus))
        create_campaign(self.state_root, corpus)
        revised = self.declaration(
            corpus,
            supersedes=project_declaration_fingerprint(initial),
        )
        revised["tasks"] = revised["tasks"][:1]
        revised["case_bindings"] = revised["case_bindings"][:1]
        revised["holdout_requirements"][0]["task_ids"] = ["task-1"]
        self.write_declaration(corpus, revised)
        with self.assertRaisesRegex(ValueError, "omitted existing"):
            create_campaign(self.state_root, corpus)

    def test_missing_or_duplicate_case_bindings_fail_closed(self):
        corpus = self.corpus("invalid", ("case-one", "case-two"))
        missing = self.declaration(corpus)
        missing["case_bindings"] = missing["case_bindings"][:1]
        with self.assertRaisesRegex(
            ValueError,
            "every task requires|every corpus case",
        ):
            self.write_declaration(corpus, missing)
            create_campaign(self.state_root, corpus)

        duplicate = self.declaration(corpus)
        duplicate["case_bindings"][1]["case_id"] = "case-one"
        duplicate["case_bindings"][1]["case_revision"] = duplicate[
            "case_bindings"
        ][0]["case_revision"]
        with self.assertRaisesRegex(
            ValueError,
            "multiple tasks|every corpus case",
        ):
            self.write_declaration(corpus, duplicate)
            create_campaign(self.state_root, corpus)


class ProjectScorecardTests(ProjectFixture):
    def test_exact_revision_scorecard_never_pools_passes(self):
        corpus = self.corpus("scorecard", ("case-one", "case-two"))
        declaration = canonical_project_declaration(self.declaration(corpus))
        project = {
            "tasks": declaration["tasks"],
            "case_bindings": declaration["case_bindings"],
        }
        snapshot_a = "a" * 64
        snapshot_b = "b" * 64
        attempts = []
        for binding, snapshot in zip(
            declaration["case_bindings"],
            (snapshot_a, snapshot_b),
        ):
            task = next(
                item for item in declaration["tasks"]
                if item["task_id"] == binding["task_id"]
            )
            attempts.append({
                "row": {
                    "correctness": "PASS",
                    "population": {
                        "lineage_snapshot_id": snapshot,
                        "case_id": binding["case_id"],
                        "case_revision": binding["case_revision"],
                    },
                },
                "project": {
                    "binding_id": binding["binding_id"],
                    "binding_fingerprint": binding_fingerprint(binding),
                    "task_fingerprint": task_fingerprint(task),
                },
            })

        scorecard = _task_scorecard(
            project,
            {
                "snapshot_id": "revision-a",
                "snapshot_ids": [snapshot_a],
            },
            attempts,
        )
        self.assertEqual(
            [item["result"] for item in scorecard],
            ["passing", "unavailable"],
        )
        self.assertNotEqual(
            sum(item["result"] == "passing" for item in scorecard),
            2,
        )

    def test_error_and_invalid_rows_do_not_satisfy_repetitions(self):
        corpus = self.corpus("scorecard-errors")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]
        attempts = [
            {
                "row": {
                    "correctness": outcome,
                    "population": {
                        "lineage_snapshot_id": "a" * 64,
                        "case_id": binding["case_id"],
                        "case_revision": binding["case_revision"],
                    },
                },
                "project": {
                    "binding_id": binding["binding_id"],
                    "binding_fingerprint": binding_fingerprint(binding),
                    "task_fingerprint": task_fingerprint(task),
                },
            }
            for outcome in ("ERROR", "INVALID")
        ]

        scorecard = _task_scorecard(
            {
                "tasks": declaration["tasks"],
                "case_bindings": declaration["case_bindings"],
            },
            {"snapshot_id": "revision-a", "snapshot_ids": ["a" * 64]},
            attempts,
        )

        self.assertEqual(
            scorecard[0]["bindings"][0]["terminal_attempts"],
            0,
        )
        self.assertEqual(scorecard[0]["result"], "unavailable")

    def test_regression_and_effort_follow_exact_revision_history(self):
        corpus = self.corpus("regression")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]

        def attempt(snapshot: str, outcome: str, started: str, run: str):
            return {
                "campaign_id": "a" * 32,
                "row": {
                    "correctness": outcome,
                    "population": {
                        "lineage_snapshot_id": snapshot,
                        "case_id": binding["case_id"],
                        "case_revision": binding["case_revision"],
                    },
                    "started_at": started,
                    "elapsed_seconds": 10,
                    "run_path": run,
                    "attempt": 1,
                    "accounting": {},
                    "invocations": [],
                },
                "project": {
                    "binding_id": binding["binding_id"],
                    "binding_fingerprint": binding_fingerprint(binding),
                    "task_fingerprint": task_fingerprint(task),
                },
            }

        scorecard = _task_scorecard(
            {
                "tasks": declaration["tasks"],
                "case_bindings": declaration["case_bindings"],
            },
            {
                "snapshot_id": "revision-b",
                "snapshot_ids": ["b" * 64],
                "prior_revisions": [{
                    "snapshot_id": "revision-a",
                    "snapshot_ids": ["a" * 64],
                    "roles": ["integrated"],
                }],
                "known_revisions": [
                    {
                        "snapshot_id": "revision-a",
                        "snapshot_ids": ["a" * 64],
                        "roles": ["integrated"],
                    },
                    {
                        "snapshot_id": "revision-b",
                        "snapshot_ids": ["b" * 64],
                        "roles": ["integrated"],
                    },
                ],
            },
            [
                attempt(
                    "a" * 64,
                    "PASS",
                    "2026-01-01T00:00:00+00:00",
                    "runs/prior/case-one",
                ),
                attempt(
                    "b" * 64,
                    "FAIL",
                    "2026-01-02T00:00:00+00:00",
                    "runs/current/case-one",
                ),
            ],
        )

        self.assertEqual(scorecard[0]["result"], "regressed")
        self.assertEqual(
            scorecard[0]["timing"]["first_qualified_pass_at"],
            "2026-01-01T00:00:10+00:00",
        )
        self.assertEqual(scorecard[0]["effort"]["attempts"], 1)

    def test_equal_recorded_phase_disagreement_is_conflicted(self):
        corpus = self.corpus("phase")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]
        project = {
            "sources": [{
                "available": True,
                "corpus_root": corpus,
                "campaign": {"campaign_id": "a" * 32},
                "registration": {
                    "declaration_sha256": "e" * 64,
                },
            }],
        }

        def record(phase: str, event_id: str):
            return {
                "event_id": event_id,
                "event_type": "task_progress_recorded",
                "recorded_at": "2026-01-01T00:00:00+00:00",
                "subject": {
                    "snapshot_id": "s" * 64,
                    "case_id": binding["case_id"],
                    "case_revision": binding["case_revision"],
                },
                "payload": {
                    "task_id": task["task_id"],
                    "project_declaration_sha256": "d" * 64,
                    "phase": phase,
                },
            }

        with mock.patch(
            "project_dashboard.extension_records",
            return_value=(
                [
                    record("experimenting", "1" * 32),
                    record("delta_ablation", "2" * 32),
                ],
                [],
                [],
            ),
        ), mock.patch(
            "project_dashboard.archived_project_declaration",
            return_value=declaration,
        ):
            phase = _task_phase(
                project,
                {"snapshot_ids": ["s" * 64], "roles": []},
                task,
                "passing",
                [binding],
                [],
            )

        self.assertEqual(phase["status"], "conflicted")
        self.assertIsNone(phase["phase"])

    def test_passing_task_can_remain_in_delta_ablation(self):
        corpus = self.corpus("ablation-phase")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]
        project = {
            "sources": [{
                "available": True,
                "corpus_root": corpus,
                "campaign": {"campaign_id": "a" * 32},
                "registration": {
                    "declaration_sha256": "e" * 64,
                },
            }],
        }
        record = {
            "event_id": "1" * 32,
            "event_type": "task_progress_recorded",
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "subject": {
                "snapshot_id": "s" * 64,
                "case_id": binding["case_id"],
                "case_revision": binding["case_revision"],
            },
            "payload": {
                "task_id": task["task_id"],
                "project_declaration_sha256": "d" * 64,
                "phase": "delta_ablation",
            },
        }

        with mock.patch(
            "project_dashboard.extension_records",
            return_value=([record], [], []),
        ), mock.patch(
            "project_dashboard.archived_project_declaration",
            return_value=declaration,
        ):
            phase = _task_phase(
                project,
                {"snapshot_ids": ["s" * 64], "roles": []},
                task,
                "passing",
                [binding],
                [],
            )

        self.assertEqual(phase["status"], "available")
        self.assertEqual(phase["phase"], "delta_ablation")

    def test_passing_task_without_intent_is_not_candidate_pass(self):
        corpus = self.corpus("passing-no-intent")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]

        with mock.patch(
            "project_dashboard.extension_records",
            return_value=([], [], []),
        ):
            phase = _task_phase(
                {
                    "sources": [{
                        "available": True,
                        "corpus_root": corpus,
                    }],
                },
                {"snapshot_ids": ["s" * 64], "roles": []},
                task,
                "passing",
                [binding],
                [],
            )

        self.assertEqual(phase["status"], "available")
        self.assertEqual(phase["phase"], "not_started")

    def test_repository_safe_progress_reads_only_named_boolean_checks(self):
        corpus = self.corpus("safe-progress")
        declaration = self.declaration(corpus)
        declaration["case_bindings"][0]["safe_progress"] = {
            "kind": "repository_checks",
            "checks": ["regression", "target"],
        }
        declaration = canonical_project_declaration(declaration)
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]
        run = corpus / "runs" / "one" / "case-one"
        (run / "grading").mkdir(parents=True)
        (run / "grading" / "grading.json").write_text(json.dumps({
            "target": {"passed": True, "hidden": "not projected"},
            "regression": {"passed": False},
        }))
        attempts = [{
            "campaign_id": "a" * 32,
            "corpus_root": corpus,
            "row": {
                "correctness": "FAIL",
                "population": {
                    "lineage_snapshot_id": "s" * 64,
                    "case_id": binding["case_id"],
                    "case_revision": binding["case_revision"],
                },
                "run_path": "runs/one/case-one",
                "started_at": "2026-01-01T00:00:00+00:00",
                "elapsed_seconds": 1,
            },
            "project": {
                "binding_id": binding["binding_id"],
                "binding_fingerprint": binding_fingerprint(binding),
                "task_fingerprint": task_fingerprint(task),
            },
        }]

        progress = _task_safe_progress(
            task,
            [binding],
            {"snapshot_ids": ["s" * 64]},
            attempts,
            [],
        )

        self.assertEqual(progress["status"], "available")
        self.assertEqual((progress["passed"], progress["total"]), (1, 2))
        self.assertNotIn("hidden", json.dumps(progress))

    def test_prose_task_has_no_safe_progress_percentage(self):
        corpus = self.corpus("prose-progress")
        declaration = canonical_project_declaration(self.declaration(corpus))
        progress = _task_safe_progress(
            declaration["tasks"][0],
            declaration["case_bindings"],
            {"snapshot_ids": ["s" * 64]},
            [],
            [],
        )
        self.assertEqual(progress, {
            "status": "unavailable",
            "reason": "No safe subcheck breakdown.",
        })

    def test_task_progress_binds_current_project_task_and_phase(self):
        corpus = self.corpus("progress-command")
        declaration = self.write_declaration(
            corpus,
            self.declaration(corpus),
        )
        registration = create_campaign(self.state_root, corpus)
        session_id = str(uuid.uuid4())
        register_session(self.state_root, corpus, session_id, state="active")
        snapshot = capture_skill_snapshot(
            corpus,
            write_plugin(self.root),
            ["example-skill"],
        )

        task_progress_dashboard(
            corpus,
            session_id,
            "case-one",
            snapshot["snapshot_id"],
            "behavioral",
            "skill_defect",
            "Strict improvement",
            "Testing the next general revision.",
            phase="experimenting",
            root=self.state_root,
        )

        records, _, _ = extension_records(corpus)
        progress = next(
            item for item in records
            if item["event_type"] == "task_progress_recorded"
        )
        self.assertEqual(progress["payload"]["task_id"], "task-1")
        self.assertEqual(
            progress["payload"]["project_declaration_sha256"],
            project_declaration_fingerprint(declaration),
        )
        self.assertEqual(progress["payload"]["phase"], "experimenting")
        with self.assertRaisesRegex(ValueError, "does not match"):
            task_progress_dashboard(
                corpus,
                session_id,
                "case-one",
                snapshot["snapshot_id"],
                "behavioral",
                "skill_defect",
                "Strict improvement",
                "Invalid task identity.",
                task_id="wrong-task",
                root=self.state_root,
            )

    def test_distributed_experiment_uses_shared_compact_run_fields(self):
        corpus = self.corpus("distributed")
        declaration = canonical_project_declaration(self.declaration(corpus))
        binding = declaration["case_bindings"][0]
        project = {
            "case_bindings": declaration["case_bindings"],
            "sources": [{
                "available": True,
                "corpus_root": corpus,
                "campaign": {"campaign_id": "a" * 32},
            }],
        }
        activity = [{
            "attempt_id": "attempt-1",
            "case_id": binding["case_id"],
            "case_revision": binding["case_revision"],
            "snapshot_id": "s" * 64,
            "state": "terminal",
            "evaluator_result": "PASS",
        }]
        projection = {
            "items": [{
                "experiment_id": "experiment-1",
                "experiment_fingerprint": "e" * 64,
                "summary": "Test the general fix on the distributed runner.",
                "snapshot_id": "s" * 64,
                "route": "cloud",
                "planned_attempts": 1,
                "cost": {
                    "known_attempts": 0,
                    "total_attempts": 1,
                    "credits": None,
                    "premium_requests": None,
                    "complete": False,
                },
                "activity": activity,
            }],
        }
        declared = [{
            "event_type": "experiment_declared",
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "subject": {"experiment_id": "experiment-1"},
        }]
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value=projection,
        ), mock.patch(
            "project_dashboard.experiment_activity_records",
            return_value=(declared, [], []),
        ):
            runs, rows = _distributed_projection(project)

        self.assertEqual(
            [
                {
                    key: value for key, value in row.items()
                    if not key.startswith("_")
                }
                for row in rows
            ],
            activity,
        )
        self.assertEqual(runs[0]["launcher_kind"], "distributed_experiment")
        self.assertEqual(runs[0]["state"], "completed")
        self.assertEqual(runs[0]["passing_attempts"], 1)
        self.assertEqual(
            runs[0]["source_identity"]["experiment_fingerprint"],
            "e" * 64,
        )
        self.assertEqual(
            runs[0]["attempts"][0]["experiments"][0]["outcome"],
            "positive",
        )

    def test_distributed_attempt_awaiting_result_projects_checking(self):
        corpus = self.corpus("distributed-checking")
        declaration = canonical_project_declaration(self.declaration(corpus))
        binding = declaration["case_bindings"][0]
        project = {
            "target_skills": ["example-skill"],
            "case_bindings": declaration["case_bindings"],
            "sources": [{
                "available": True,
                "corpus_root": corpus,
                "campaign": {"campaign_id": "a" * 32},
            }],
        }
        activity = [{
            "attempt_id": "attempt-1",
            "case_id": binding["case_id"],
            "case_revision": binding["case_revision"],
            "snapshot_id": "s" * 64,
            "state": "cloud_completed_awaiting_result",
            "evaluator_result": None,
        }]
        projection = {
            "items": [{
                "experiment_id": "experiment-1",
                "experiment_fingerprint": "e" * 64,
                "summary": "Wait for the distributed result.",
                "snapshot_id": "s" * 64,
                "route": "cloud",
                "planned_attempts": 1,
                "cost": {
                    "known_attempts": 0,
                    "total_attempts": 1,
                    "credits": None,
                    "premium_requests": None,
                    "complete": False,
                },
                "activity": activity,
            }],
        }
        declared = [{
            "event_type": "experiment_declared",
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "subject": {"experiment_id": "experiment-1"},
        }]
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value=projection,
        ), mock.patch(
            "project_dashboard.experiment_activity_records",
            return_value=(declared, [], []),
        ):
            runs, _ = _distributed_projection(project)

        self.assertEqual(runs[0]["state"], "liveness_unavailable")
        experiment = runs[0]["attempts"][0]["experiments"][0]
        self.assertEqual(experiment["step"], "checking")
        self.assertIsNone(experiment["outcome"])

    def test_delta_ablation_reports_exact_size_and_maintained_wins(self):
        corpus = self.corpus("delta-ablation")
        declaration = self.write_declaration(
            corpus,
            self.declaration(corpus),
        )
        registration = create_campaign(self.state_root, corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            corpus,
            session_id,
        )
        writer = {
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        }
        baseline = capture_skill_snapshot(
            corpus,
            write_plugin(self.root, "# Example\nBaseline guidance.\n"),
            ["example-skill"],
        )
        exploratory = capture_skill_snapshot(
            corpus,
            write_plugin(
                self.root,
                "# Example\nPassing guidance with extra procedure.\n"
                "Keep authority.\n",
            ),
            ["example-skill"],
        )
        minimized = capture_skill_snapshot(
            corpus,
            write_plugin(self.root, "# Example\nKeep authority.\n"),
            ["example-skill"],
        )
        emit_lineage_event(
            corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=baseline["snapshot_id"],
            roles=["integrated", "published"],
            parents=[],
            summary="Published baseline",
            recorded_at="2026-01-01T00:00:00+00:00",
        )
        emit_lineage_event(
            corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=exploratory["snapshot_id"],
            roles=["integrated"],
            parents=[{
                "relation": "derived_from",
                "snapshot_id": baseline["snapshot_id"],
            }],
            summary="Exploratory pass",
            recorded_at="2026-01-01T00:01:00+00:00",
        )
        emit_lineage_event(
            corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=minimized["snapshot_id"],
            roles=["integrated"],
            parents=[{
                "relation": "derived_from",
                "snapshot_id": exploratory["snapshot_id"],
            }],
            summary="Minimized pass",
            recorded_at="2026-01-01T00:02:00+00:00",
        )
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]
        experiment = {
            "experiment_id": "delta-task-1",
            "experiment_kind": "delta_ablation",
            "ablation": {
                "project_id": declaration["project_id"],
                "project_declaration_sha256": (
                    project_declaration_fingerprint(declaration)
                ),
                "task_id": task["task_id"],
                "baseline_snapshot_id": baseline["snapshot_id"],
                "exploratory_snapshot_id": exploratory["snapshot_id"],
                "candidate_snapshots": [{
                    "treatment_id": "lean",
                    "snapshot_id": minimized["snapshot_id"],
                }],
                "maintained_tasks": [{
                    "task_id": task["task_id"],
                    "task_fingerprint": task_fingerprint(task),
                }],
                "instruction_changes": [
                    {
                        "instruction_id": "extra-procedure",
                        "disposition": "removed",
                        "reason": None,
                    },
                    {
                        "instruction_id": "preserve-authority",
                        "disposition": "restored",
                        "reason": "Its removal regressed the maintained task.",
                    },
                ],
            },
            "selection": {
                "status": "selected",
                "selected_treatment_id": "lean",
                "reasons": ["best-qualified"],
                "authority": "experiment_evaluator",
            },
            "treatments": [{
                "treatment_id": "lean",
                "selection_state": "selected",
                "target_skill_identities": [{
                    "name": "example-skill",
                    "evaluator_fingerprint": minimized["skills"][0][
                        "evaluator_skill_identity"
                    ],
                }],
            }],
            "activity": [{
                "treatment_id": "lean",
                "case_id": binding["case_id"],
                "case_revision": binding["case_revision"],
                "state": "terminal",
                "evaluator_result": "PASS",
                "repetition": 1,
            }],
        }
        project = reconciled_project(
            self.state_root,
            declaration["project_id"],
        )
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [experiment]},
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=True,
        ):
            delta, whole, invalid = _ablation_projection(
                self.state_root,
                project,
            )

        result = delta[task["task_id"]]
        self.assertFalse(invalid)
        self.assertIsNone(whole)
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(result["maintained_wins"]["passed"], 1)
        self.assertGreater(result["reduction"]["final"]["bytes"], 0)
        self.assertEqual(
            result["instruction_changes"]["restored"],
            [{
                "instruction_id": "preserve-authority",
                "reason": "Its removal regressed the maintained task.",
            }],
        )

        experiment["activity"][0]["evaluator_result"] = "FAIL"
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [experiment]},
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=True,
        ):
            regressed, _, _ = _ablation_projection(
                self.state_root,
                project,
            )
        self.assertEqual(
            regressed[task["task_id"]]["status"],
            "regressed",
        )
        self.assertIsNone(regressed[task["task_id"]]["final"])

        experiment["activity"][0]["evaluator_result"] = "PASS"
        whole_experiment = {
            **experiment,
            "experiment_id": "whole-skill-ablation",
            "experiment_kind": "whole_skill_ablation",
            "ablation": {
                "project_id": declaration["project_id"],
                "project_declaration_sha256": (
                    project_declaration_fingerprint(declaration)
                ),
                "arms": [{
                    "arm": "lean",
                    "treatment_id": "lean",
                    "snapshot_id": minimized["snapshot_id"],
                }],
                "maintained_tasks": [{
                    "task_id": task["task_id"],
                    "task_fingerprint": task_fingerprint(task),
                }],
            },
        }
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [experiment, whole_experiment]},
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=True,
        ):
            _, whole, invalid = _ablation_projection(
                self.state_root,
                project,
            )
        self.assertFalse(invalid)
        self.assertEqual(whole["arms"][0]["arm"], "lean")
        self.assertEqual(
            whole["arms"][0]["maintained_wins"]["passed"],
            1,
        )

        later = json.loads(json.dumps(experiment))
        later["experiment_id"] = "delta-task-1-later"
        declaration_records = [
            {
                "event_type": "experiment_declared",
                "recorded_at": "2026-01-01T00:00:00+00:00",
                "subject": {"experiment_id": experiment["experiment_id"]},
            },
            {
                "event_type": "experiment_declared",
                "recorded_at": "2026-01-02T00:00:00+00:00",
                "subject": {"experiment_id": later["experiment_id"]},
            },
        ]
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [experiment, later]},
        ), mock.patch(
            "project_dashboard.experiment_activity_records",
            return_value=(declaration_records, [], []),
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=True,
        ):
            latest, _, invalid = _ablation_projection(
                self.state_root,
                project,
            )
        self.assertFalse(invalid)
        self.assertEqual(
            latest[task["task_id"]]["experiment_id"],
            later["experiment_id"],
        )

        mismatched = json.loads(json.dumps(experiment))
        mismatched["treatments"][0]["target_skill_identities"][0][
            "evaluator_fingerprint"
        ] = "0" * 64
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [mismatched]},
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=True,
        ):
            rejected, _, invalid = _ablation_projection(
                self.state_root,
                project,
            )
        self.assertTrue(invalid)
        self.assertEqual(rejected, {})

        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [experiment]},
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=False,
        ):
            rejected, _, invalid = _ablation_projection(
                self.state_root,
                project,
            )
        self.assertTrue(invalid)
        self.assertEqual(rejected, {})

        catalog, _ = _snapshot_catalog(project)
        catalog[baseline["snapshot_id"]]["roles"] = ["integrated"]
        with mock.patch(
            "dashboard_projection.experiment_projection",
            return_value={"items": [experiment]},
        ), mock.patch(
            "project_dashboard._snapshot_catalog",
            return_value=(catalog, False),
        ), mock.patch(
            "project_dashboard._snapshot_task_passes",
            return_value=True,
        ):
            rejected, _, invalid = _ablation_projection(
                self.state_root,
                project,
            )
        self.assertTrue(invalid)
        self.assertEqual(rejected, {})

    def test_ablation_must_qualify_selected_revision_for_publication(self):
        ablation = {
            "status": "qualified",
            "final": {"revision_id": "a" * 64},
        }
        self.assertTrue(_ablation_qualifies_selected_revision(
            ablation,
            {"snapshot_id": "a" * 64},
        ))
        self.assertFalse(_ablation_qualifies_selected_revision(
            ablation,
            {"snapshot_id": "b" * 64},
        ))

    def test_distributed_safe_progress_uses_stage_identity(self):
        corpus = self.corpus("distributed-progress")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = {
            **declaration["case_bindings"][0],
            "safe_progress": {
                "kind": "distributed_product_stages",
                "checks": ["linux-final"],
            },
        }
        lineage = {"snapshot_ids": ["s" * 64]}
        activity = [{
            "case_id": binding["case_id"],
            "case_revision": binding["case_revision"],
            "snapshot_id": "s" * 64,
            "_expected_stage_kinds": ["linux-final"],
            "_completed_stage_kinds": [],
        }]

        progress = _task_safe_progress(
            task,
            [binding],
            lineage,
            [],
            activity,
        )
        self.assertEqual(progress["status"], "available")
        self.assertEqual(progress["passed"], 0)
        self.assertEqual(progress["total"], 1)

        binding["safe_progress"]["checks"] = ["unknown-stage"]
        unavailable = _task_safe_progress(
            task,
            [binding],
            lineage,
            [],
            activity,
        )
        self.assertEqual(unavailable["status"], "unavailable")

    def test_effort_includes_failed_ancestor_before_descendant_pass(self):
        corpus = self.corpus("effort-prefix")
        declaration = canonical_project_declaration(self.declaration(corpus))
        task = declaration["tasks"][0]
        binding = declaration["case_bindings"][0]

        def attempt(snapshot: str, outcome: str, started: str, run: str):
            return {
                "campaign_id": "a" * 32,
                "row": {
                    "correctness": outcome,
                    "population": {
                        "lineage_snapshot_id": snapshot,
                        "case_id": binding["case_id"],
                        "case_revision": binding["case_revision"],
                    },
                    "started_at": started,
                    "elapsed_seconds": 10,
                    "run_path": run,
                    "attempt": 1,
                    "accounting": {},
                    "invocations": [],
                },
                "project": {
                    "binding_id": binding["binding_id"],
                    "binding_fingerprint": binding_fingerprint(binding),
                    "task_fingerprint": task_fingerprint(task),
                },
            }

        scorecard = _task_scorecard(
            {
                "tasks": declaration["tasks"],
                "case_bindings": declaration["case_bindings"],
            },
            {
                "snapshot_id": "revision-b",
                "snapshot_ids": ["b" * 64],
                "prior_revisions": [{
                    "snapshot_id": "revision-a",
                    "snapshot_ids": ["a" * 64],
                    "roles": ["integrated"],
                }],
                "known_revisions": [
                    {
                        "snapshot_id": "revision-a",
                        "snapshot_ids": ["a" * 64],
                        "roles": ["integrated"],
                    },
                    {
                        "snapshot_id": "revision-b",
                        "snapshot_ids": ["b" * 64],
                        "roles": ["integrated"],
                    },
                ],
            },
            [
                attempt(
                    "a" * 64,
                    "FAIL",
                    "2026-01-01T00:00:00+00:00",
                    "runs/prior/case-one",
                ),
                attempt(
                    "b" * 64,
                    "PASS",
                    "2026-01-02T00:00:00+00:00",
                    "runs/current/case-one",
                ),
            ],
        )

        self.assertEqual(scorecard[0]["result"], "passing")
        self.assertEqual(scorecard[0]["effort"]["runs"], 2)
        self.assertEqual(scorecard[0]["effort"]["attempts"], 2)


class ProjectHoldoutTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
        except ImportError:
            self.skipTest("cryptography is unavailable")
        self.serialization = serialization
        self.private = Ed25519PrivateKey.generate()
        public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        create_authority(
            self.state_root,
            "independent-evaluator",
            base64.b64encode(public).decode("ascii"),
        )

    def signed(self, value: dict) -> dict:
        unsigned = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return {
            **value,
            "signature": base64.b64encode(
                self.private.sign(unsigned)
            ).decode("ascii"),
        }

    def started(self) -> dict:
        return self.signed({
            "schema_version": 1,
            "receipt_id": "started-1",
            "kind": "started",
            "authority_id": "independent-evaluator",
            "project_id": "example-project",
            "holdout_set_id": "transfer-v1",
            "candidate_revision": "c" * 64,
            "task_ids": ["task-1"],
            "claim": "transfer",
            "started_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T01:00:00+00:00",
            "nonce": "nonce-1",
        })

    def test_signed_chain_projects_only_aggregate_data(self):
        started = self.started()
        started_import = import_receipt(self.state_root, started)
        terminal = self.signed({
            "schema_version": 1,
            "receipt_id": "terminal-1",
            "kind": "terminal",
            "authority_id": "independent-evaluator",
            "project_id": "example-project",
            "holdout_set_id": "transfer-v1",
            "candidate_revision": "c" * 64,
            "task_ids": ["task-1"],
            "claim": "transfer",
            "started_receipt_sha256": started_import["receipt_sha256"],
            "completed_at": "2026-01-01T00:30:00+00:00",
            "infrastructure_state": "completed",
            "total_cases": 5,
            "passed_cases": 5,
            "failed_cases": 0,
            "candidate_tokens": 100,
            "judge_tokens": 20,
            "credits": 1.5,
            "accounting_complete": True,
            "qualified": True,
        })
        import_receipt(self.state_root, terminal)

        projection = holdout_projection(
            self.state_root,
            "example-project",
            [{
                "holdout_set_id": "transfer-v1",
                "summary": "Reserved transfer checks",
                "required_claim": "transfer",
                "task_ids": ["task-1"],
                "authority_id": "independent-evaluator",
            }],
            "c" * 64,
        )

        self.assertEqual(projection[0]["status"], "completed")
        self.assertTrue(projection[0]["qualification"])
        self.assertEqual(projection[0]["aggregate"]["passed_cases"], 5)
        self.assertNotIn("case_id", json.dumps(projection))

    def test_forgery_detail_replay_and_writable_registry_fail_closed(self):
        started = self.started()
        forged = {**started, "nonce": "changed"}
        with self.assertRaisesRegex(ValueError, "signature"):
            import_receipt(self.state_root, forged)
        detail = {
            **started,
            "case_id": "secret-case",
        }
        detail = self.signed({
            key: value for key, value in detail.items()
            if key != "signature"
        })
        with self.assertRaisesRegex(ValueError, "forbidden detail"):
            import_receipt(self.state_root, detail)
        import_receipt(self.state_root, started)
        with self.assertRaisesRegex(ValueError, "replayed"):
            import_receipt(self.state_root, started)

        registry = self.state_root / "holdout-authorities"
        os.chmod(registry, 0o777)
        projection = holdout_projection(
            self.state_root,
            "example-project",
            [{
                "holdout_set_id": "transfer-v1",
                "summary": "Reserved transfer checks",
                "required_claim": "transfer",
                "task_ids": ["task-1"],
                "authority_id": "independent-evaluator",
            }],
            "c" * 64,
        )
        self.assertEqual(projection[0]["status"], "invalid")

    def test_unknown_authority_and_late_terminal_are_rejected(self):
        unknown = {
            **self.started(),
            "authority_id": "unknown-evaluator",
        }
        unknown = self.signed({
            key: value for key, value in unknown.items()
            if key != "signature"
        })
        with self.assertRaisesRegex(ValueError, "holdout authority"):
            import_receipt(self.state_root, unknown)

        started = self.started()
        imported = import_receipt(self.state_root, started)
        late = self.signed({
            "schema_version": 1,
            "receipt_id": "terminal-late",
            "kind": "terminal",
            "authority_id": "independent-evaluator",
            "project_id": "example-project",
            "holdout_set_id": "transfer-v1",
            "candidate_revision": "c" * 64,
            "task_ids": ["task-1"],
            "claim": "transfer",
            "started_receipt_sha256": imported["receipt_sha256"],
            "completed_at": "2026-01-01T02:00:00+00:00",
            "infrastructure_state": "completed",
            "total_cases": 1,
            "passed_cases": 1,
            "failed_cases": 0,
            "candidate_tokens": None,
            "judge_tokens": None,
            "credits": None,
            "accounting_complete": False,
            "qualified": True,
        })
        with self.assertRaisesRegex(ValueError, "outside its lifetime"):
            import_receipt(self.state_root, late)

    def test_duplicate_terminal_is_rejected_and_expired_start_fails(self):
        started = self.signed({
            "schema_version": 1,
            "receipt_id": "started-expired",
            "kind": "started",
            "authority_id": "independent-evaluator",
            "project_id": "example-project",
            "holdout_set_id": "transfer-v1",
            "candidate_revision": "c" * 64,
            "task_ids": ["task-1"],
            "claim": "transfer",
            "started_at": "2020-01-01T00:00:00+00:00",
            "expires_at": "2020-01-01T01:00:00+00:00",
            "nonce": "expired-nonce",
        })
        imported = import_receipt(self.state_root, started)
        projection = holdout_projection(
            self.state_root,
            "example-project",
            [{
                "holdout_set_id": "transfer-v1",
                "summary": "Reserved transfer checks",
                "required_claim": "transfer",
                "task_ids": ["task-1"],
                "authority_id": "independent-evaluator",
            }],
            "c" * 64,
        )
        self.assertEqual(projection[0]["status"], "expired")
        self.assertEqual(projection[0]["infrastructure_state"], "failed")
        self.assertIsNone(projection[0]["qualification"])

        terminal_fields = {
            "schema_version": 1,
            "kind": "terminal",
            "authority_id": "independent-evaluator",
            "project_id": "example-project",
            "holdout_set_id": "transfer-v1",
            "candidate_revision": "c" * 64,
            "task_ids": ["task-1"],
            "claim": "transfer",
            "started_receipt_sha256": imported["receipt_sha256"],
            "completed_at": "2020-01-01T00:30:00+00:00",
            "infrastructure_state": "completed",
            "total_cases": 1,
            "passed_cases": 1,
            "failed_cases": 0,
            "candidate_tokens": None,
            "judge_tokens": None,
            "credits": None,
            "accounting_complete": False,
            "qualified": True,
        }
        import_receipt(self.state_root, self.signed({
            **terminal_fields,
            "receipt_id": "terminal-first",
        }))
        with self.assertRaisesRegex(ValueError, "already exists"):
            import_receipt(self.state_root, self.signed({
                **terminal_fields,
                "receipt_id": "terminal-second",
            }))

    def test_private_signer_returns_no_private_paths_or_case_detail(self):
        private_path = self.root / "private.key"
        private_bytes = self.private.private_bytes(
            encoding=self.serialization.Encoding.Raw,
            format=self.serialization.PrivateFormat.Raw,
            encryption_algorithm=self.serialization.NoEncryption(),
        )
        private_path.write_text(
            base64.b64encode(private_bytes).decode("ascii"),
            encoding="ascii",
        )
        os.chmod(private_path, 0o600)
        unsigned_path = self.root / "aggregate.json"
        unsigned = {
            key: value for key, value in self.started().items()
            if key != "signature"
        }
        unsigned_path.write_text(json.dumps(unsigned), encoding="utf-8")
        output = self.root / "signed.json"

        response = sign_private_receipt(
            private_path,
            unsigned_path,
            output,
        )

        self.assertNotIn(str(self.root), json.dumps(response))
        self.assertNotIn("case", json.dumps(response))

    def test_private_signer_rejects_symlink_and_hides_missing_key_path(self):
        private_path = self.root / "private.key"
        private_bytes = self.private.private_bytes(
            encoding=self.serialization.Encoding.Raw,
            format=self.serialization.PrivateFormat.Raw,
            encryption_algorithm=self.serialization.NoEncryption(),
        )
        private_path.write_text(base64.b64encode(private_bytes).decode())
        os.chmod(private_path, 0o600)
        symlink = self.root / "private-link"
        symlink.symlink_to(private_path)
        unsigned = self.root / "unsigned.json"
        unsigned.write_text("{}\n")

        with self.assertRaisesRegex(ValueError, "owner protected"):
            sign_private_receipt(
                symlink,
                unsigned,
                self.root / "signed.json",
            )

        missing = self.root / "secret-name.key"
        with self.assertRaises(ValueError) as raised:
            sign_private_receipt(
                missing,
                unsigned,
                self.root / "missing.json",
            )
        self.assertNotIn(str(missing), str(raised.exception))

    def test_private_sign_cli_preserves_symlink_for_validation(self):
        symlink = self.root / "private-link"
        with mock.patch(
            "dashboard_cli.sign_private_receipt",
            return_value={"schema_version": 1},
        ) as signer:
            dispatch(SimpleNamespace(
                dashboard_command="holdout-private-sign",
                private_key=symlink,
                unsigned_receipt=self.root / "unsigned.json",
                output=self.root / "signed.json",
            ))

        self.assertEqual(signer.call_args.args[0], symlink)

    def test_holdout_path_components_reject_parent_traversal(self):
        receipt = {
            key: value for key, value in self.started().items()
            if key != "signature"
        }
        receipt["project_id"] = ".."
        with self.assertRaisesRegex(ValueError, "project ID"):
            import_receipt(self.state_root, self.signed(receipt))


class ProjectLifecycleProjectionTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.corpus_root = self.corpus("lifecycle")
        self.declaration_value = self.write_declaration(
            self.corpus_root,
            self.declaration(self.corpus_root),
        )
        self.registration = create_campaign(
            self.state_root,
            self.corpus_root,
        )
        self.history_patch = mock.patch(
            "project_dashboard.evaluation_history.history",
            return_value={"attempts": []},
        )
        self.history_patch.start()

    def tearDown(self):
        self.history_patch.stop()
        super().tearDown()

    def start(self, name: str, *, expires_delta: int = 30) -> Path:
        root = self.corpus_root / "suite-runs" / name
        root.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        start = {
            "schema_version": 1,
            "run_id": name,
            "project_id": "example-project",
            "project_declaration_sha256": project_declaration_fingerprint(
                self.declaration_value
            ),
            "campaign_id": self.registration["campaign_id"],
            "launcher_kind": "local_suite",
            "run_goal": "Check the current project behavior.",
            "requested_plugin_path": "/requested/plugin",
            "treatment_reference": None,
            "arm": "skill",
            "task_ids": ["task-1"],
            "case_bindings": [{
                "binding_id": "binding-1",
                "binding_fingerprint": binding_fingerprint(
                    self.declaration_value["case_bindings"][0]
                ),
                "case_id": "case-one",
                "case_revision": self.declaration_value[
                    "case_bindings"
                ][0]["case_revision"],
                "task_id": "task-1",
            }],
            "planned_workers": 2,
            "planned_attempts": 1,
            "lease_generation": "c" * 64,
            "started_at": now.isoformat(),
        }
        (root / "suite-start.json").write_text(
            json.dumps(start, indent=2) + "\n"
        )
        renewed_at = (
            now
            if expires_delta > 0
            else now + timedelta(seconds=expires_delta - 10)
        )
        lease = {
            "schema_version": 1,
            "run_id": name,
            "generation": "c" * 64,
            "renewed_at": renewed_at.isoformat(),
            "expires_at": (
                now + timedelta(seconds=expires_delta)
            ).isoformat(),
        }
        (root / "run-lease.json").write_text(
            json.dumps(lease, indent=2) + "\n"
        )
        return root

    def test_suite_is_visible_before_final_artifacts_and_expires_honestly(self):
        active = self.start("active-suite")
        projection = project_projection(self.state_root, "example-project")
        row = next(item for item in projection["runs"] if item["run_id"] == active.name)
        self.assertEqual(row["state"], "active")
        self.assertEqual(len(row["attempts"]), 1)
        self.assertEqual(row["attempts"][0]["state"], "active")
        self.assertEqual(row["attempts"][0]["experiments"], [])

        lease = json.loads((active / "run-lease.json").read_text())
        lease["renewed_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        ).isoformat()
        lease["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        (active / "run-lease.json").write_text(json.dumps(lease, indent=2) + "\n")
        row = next(
            item
            for item in project_projection(
                self.state_root,
                "example-project",
            )["runs"]
            if item["run_id"] == active.name
        )
        self.assertEqual(row["state"], "liveness_lost")
        self.assertNotEqual(row["state"], "interrupted")

    def test_typed_setup_failure_does_not_create_task_result(self):
        failed = self.start("failed-suite")
        (failed / "suite-failure.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": failed.name,
            "stage": "launcher_setup",
            "error_type": "OSError",
            "message": "plugin snapshot failed",
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
        projection = project_projection(self.state_root, "example-project")
        row = next(item for item in projection["runs"] if item["run_id"] == failed.name)
        self.assertEqual(row["state"], "infrastructure_failed")
        self.assertEqual(row["failure_stage"], "launcher_setup")
        self.assertEqual(row["attempts"][0]["state"], "infrastructure_failed")
        self.assertEqual(row["attempts"][0]["experiments"], [])
        self.assertEqual(projection["tasks"][0]["result"], "unavailable")

    def test_immutable_result_outranks_expired_lease(self):
        completed = self.start("completed-suite", expires_delta=-10)
        for index in (1, 2):
            attempt_root = (
                self.corpus_root
                / "runs"
                / f"attempt-{index}"
                / "case-one"
            )
            attempt_root.mkdir(parents=True)
            (attempt_root / "attempt.json").write_text(json.dumps({
                "suite_owner": {
                    "suite_path": str(
                        completed.relative_to(self.corpus_root)
                    ),
                },
            }) + "\n")
        (completed / "suite-result.json").write_text(json.dumps({
            "schema_version": 1,
            "result": "FAIL",
            "duration_seconds": 12.5,
            "cases": [{
                "case_id": "case-one",
                "attempts": [
                    {
                        "attempt": 1,
                        "result": "PASS",
                        "timing": {"elapsed_seconds": 3.5},
                        "accounting": {
                            "total": {
                                "complete": True,
                                "credits": 2.5,
                                "observed_credits": 2.5,
                            },
                        },
                    },
                    {"attempt": 2, "result": "FAIL"},
                    {"attempt": 3, "result": "ERROR"},
                ],
            }],
        }, indent=2) + "\n")
        row = next(
            item
            for item in project_projection(
                self.state_root,
                "example-project",
            )["runs"]
            if item["run_id"] == completed.name
        )
        self.assertEqual(row["state"], "completed")
        self.assertEqual(row["started_attempts"], 2)
        self.assertEqual(row["completed_attempts"], 2)
        self.assertEqual(row["passing_attempts"], 1)
        self.assertEqual(row["failing_attempts"], 1)
        self.assertEqual(row["unavailable_attempts"], 1)
        experiments = row["attempts"][0]["experiments"]
        self.assertEqual(
            [item["outcome"] for item in experiments],
            ["positive", "negative", "failed"],
        )
        self.assertEqual(
            [item["step"] for item in experiments],
            ["complete", "complete", "failed"],
        )
        self.assertEqual(experiments[0]["task_ids"], ["task-1"])
        self.assertEqual(experiments[0]["skill_ids"], ["example-skill"])
        self.assertEqual(experiments[0]["duration_seconds"], 3.5)
        self.assertEqual(experiments[0]["cost"]["credits"], 2.5)

    def test_local_case_unavailable_outcome_has_complete_counts(self):
        run = self.corpus_root / "runs" / "local-case" / "case-one"
        run.mkdir(parents=True)
        binding = self.declaration_value["case_bindings"][0]
        start = {
            "schema_version": 1,
            "run_id": "local-case",
            "project_id": "example-project",
            "project_declaration_sha256": project_declaration_fingerprint(
                self.declaration_value
            ),
            "campaign_id": self.registration["campaign_id"],
            "launcher_kind": "local_case",
            "run_goal": "Check one project behavior.",
            "requested_plugin_path": "/requested/plugin",
            "treatment_reference": None,
            "arm": "skill",
            "task_ids": ["task-1"],
            "case_bindings": [{
                "binding_id": binding["binding_id"],
                "binding_fingerprint": binding_fingerprint(binding),
                "case_id": binding["case_id"],
                "case_revision": binding["case_revision"],
                "task_id": binding["task_id"],
            }],
            "planned_workers": 1,
            "planned_attempts": 1,
            "lease_generation": "d" * 64,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        (run / "attempt.json").write_text(
            json.dumps({"project_start": start}) + "\n"
        )
        (run / "repository-result.json").write_text(json.dumps({
            "execution_status": "INVALID",
            "behavioral_verdict": None,
        }) + "\n")
        unrelated = self.corpus_root / "runs" / "suite-child" / "case-one"
        unrelated.mkdir(parents=True)
        (unrelated / "attempt.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": "suite-child",
            "case_id": "case-one",
            "project_start": None,
            "suite_owner": {
                "suite_path": "suite-runs/another-suite",
            },
        }) + "\n")

        row = next(
            item
            for item in project_projection(
                self.state_root,
                "example-project",
            )["runs"]
            if item["run_id"] == "local-case"
        )

        self.assertEqual(row["completed_attempts"], 1)
        self.assertEqual(row["passing_attempts"], 0)
        self.assertEqual(row["failing_attempts"], 0)
        self.assertEqual(row["unavailable_attempts"], 1)
        self.assertEqual(
            row["attempts"][0]["experiments"][0]["outcome"],
            "failed",
        )

    def test_fingerprintless_attempt_remains_pre_project_history(self):
        run = self.corpus_root / "runs" / "legacy-run" / "case-one"
        run.mkdir(parents=True)
        (run / "attempt.json").write_text(json.dumps({
            "schema_version": 1,
            "run_id": "legacy-run",
            "case_id": "case-one",
        }) + "\n")
        self.history_patch.stop()
        with mock.patch(
            "project_dashboard.evaluation_history.history",
            return_value={
                "attempts": [{
                    "run_path": "runs/legacy-run/case-one",
                    "correctness": "PASS",
                }],
            },
        ):
            projection = project_projection(
                self.state_root,
                "example-project",
            )
        self.history_patch.start()
        self.assertEqual(projection["tasks"][0]["result"], "unavailable")
        self.assertEqual(
            projection["pre_project_history"],
            [{
                "campaign_id": self.registration["campaign_id"],
                "run_path": "runs/legacy-run/case-one",
                "correctness": "PASS",
            }],
        )


class ProjectLauncherLifecycleTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.corpus_root = self.corpus("launcher")
        self.write_declaration(
            self.corpus_root,
            self.declaration(self.corpus_root),
        )
        create_campaign(self.state_root, self.corpus_root)

    def test_project_run_requires_goal_and_setup_failure_is_durable(self):
        with mock.patch.dict(
            os.environ,
            {"SKILL_EVAL_DASHBOARD_STATE_ROOT": str(self.state_root)},
        ):
            with self.assertRaisesRegex(ValueError, "run goal"):
                run_suite(
                    self.corpus_root,
                    self.root / "releases" / "missing-plugin",
                    self.root / "missing-copilot",
                    "model",
                    "high",
                    "existing",
                    60,
                    workers=1,
                )
            with self.assertRaises(SuiteInfrastructureError):
                run_suite(
                    self.corpus_root,
                    self.root / "releases" / "missing-plugin",
                    self.root / "missing-copilot",
                    "model",
                    "high",
                    "existing",
                    60,
                    workers=1,
                    run_goal="Exercise the declared task.",
                )
        suites = sorted((self.corpus_root / "suite-runs").iterdir())
        self.assertEqual(len(suites), 1)
        self.assertTrue((suites[0] / "suite-start.json").is_file())
        failure = json.loads(
            (suites[0] / "suite-failure.json").read_text()
        )
        self.assertEqual(failure["stage"], "plugin_snapshot")
        self.assertFalse((suites[0] / "suite-result.json").exists())

    def test_initial_lease_failure_writes_typed_suite_failure(self):
        with mock.patch.dict(
            os.environ,
            {"SKILL_EVAL_DASHBOARD_STATE_ROOT": str(self.state_root)},
        ), mock.patch(
            "skill_eval.RunLease.start",
            side_effect=RunLeaseError("lease storage unavailable"),
        ):
            with self.assertRaisesRegex(RunLeaseError, "lease storage"):
                run_suite(
                    self.corpus_root,
                    write_plugin(self.root),
                    self.root / "missing-copilot",
                    "model",
                    "high",
                    "existing",
                    60,
                    workers=1,
                    run_goal="Exercise lease failure.",
                )
        suite = next((self.corpus_root / "suite-runs").iterdir())
        failure = json.loads((suite / "suite-failure.json").read_text())
        self.assertEqual(failure["stage"], "lease")
        self.assertIn("lease storage unavailable", failure["message"])

    def test_invalid_lease_configuration_writes_typed_suite_failure(self):
        with mock.patch.dict(
            os.environ,
            {
                "SKILL_EVAL_DASHBOARD_STATE_ROOT": str(self.state_root),
                "SKILL_EVAL_RUN_LEASE_SECONDS": "10",
                "SKILL_EVAL_RUN_LEASE_RENEW_SECONDS": "5",
            },
        ):
            with self.assertRaisesRegex(ValueError, "run lease renewal"):
                run_suite(
                    self.corpus_root,
                    write_plugin(self.root),
                    self.root / "missing-copilot",
                    "model",
                    "high",
                    "existing",
                    60,
                    workers=1,
                    run_goal="Exercise invalid lease configuration.",
                )
        suite = next((self.corpus_root / "suite-runs").iterdir())
        failure = json.loads((suite / "suite-failure.json").read_text())
        self.assertEqual(failure["stage"], "launcher_setup")
        self.assertEqual(failure["error_type"], "ValueError")

    def test_queued_case_does_not_start_after_lease_failure(self):
        corpus = self.corpus("queued", ("case-one", "case-two"))
        plugin = write_plugin(self.root)
        copilot = self.root / "copilot"
        copilot.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        copilot.chmod(0o700)
        suite_root = corpus / "suite-runs" / "queued-suite"
        suite_root.mkdir(parents=True)
        lease = RunLease(
            suite_root / "run-lease.json",
            "queued-suite",
            "e" * 64,
        )

        def fail_first_case(*_args, **_kwargs):
            with lease._state_lock:
                lease._failure = RunLeaseError("renewal failed")
            raise RuntimeError("first case failed")

        runtime = tempfile.TemporaryDirectory()
        try:
            with mock.patch(
                "skill_eval.tempfile.TemporaryDirectory",
                return_value=runtime,
            ), mock.patch(
                "skill_eval.copilot_identity",
                return_value={"sha256": "f" * 64, "version": "test"},
            ), mock.patch(
                "skill_eval.run_case",
                side_effect=fail_first_case,
            ) as run:
                with self.assertRaisesRegex(RunLeaseError, "renewal failed"):
                    _run_suite_impl(
                        corpus,
                        plugin,
                        copilot,
                        "model",
                        "high",
                        "existing",
                        60,
                        1,
                        ["case-one", "case-two"],
                        suite_root=suite_root,
                        lease=lease,
                    )
        finally:
            runtime.cleanup()

        self.assertEqual(run.call_count, 1)

    def test_terminal_suite_result_outranks_stop_lease_failure(self):
        def complete_suite(*_args, **kwargs):
            suite_root = kwargs["suite_root"]
            (suite_root / "suite-result.json").write_text(
                json.dumps({"schema_version": 1, "result": "PASS"}) + "\n"
            )
            return suite_root, True

        with mock.patch.dict(
            os.environ,
            {"SKILL_EVAL_DASHBOARD_STATE_ROOT": str(self.state_root)},
        ), mock.patch(
            "skill_eval._run_suite_impl",
            side_effect=complete_suite,
        ), mock.patch(
            "skill_eval.RunLease.stop",
            side_effect=RunLeaseError("renewal failed after completion"),
        ):
            suite_root, passed = run_suite(
                self.corpus_root,
                write_plugin(self.root),
                self.root / "copilot",
                "model",
                "high",
                "existing",
                60,
                workers=1,
                run_goal="Complete before the lease failure.",
            )

        self.assertTrue(passed)
        self.assertTrue((suite_root / "suite-result.json").is_file())
        self.assertFalse((suite_root / "suite-failure.json").exists())

    def test_healthy_lease_renews_atomically(self):
        path = self.root / "lease" / "run-lease.json"
        lease = RunLease(
            path,
            "run-one",
            "d" * 64,
            duration_seconds=0.4,
            renewal_seconds=0.05,
        )
        lease.start()
        first = json.loads(path.read_text())
        time.sleep(0.12)
        second = json.loads(path.read_text())
        lease.stop()
        self.assertGreater(
            datetime.fromisoformat(second["renewed_at"]),
            datetime.fromisoformat(first["renewed_at"]),
        )
        self.assertEqual(second["generation"], "d" * 64)


class ProjectCapabilityTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.first = self.corpus("first")
        self.second = self.corpus("second")
        self.write_declaration(
            self.first,
            self.declaration(self.first, project_id="first-project"),
        )
        self.write_declaration(
            self.second,
            self.declaration(self.second, project_id="second-project"),
        )
        create_campaign(self.state_root, self.first)
        create_campaign(self.state_root, self.second)
        self.generation = "a" * 32
        self.secret = "root-secret-for-tests-with-enough-entropy"
        self.server = DashboardHTTPServer(
            ("127.0.0.1", 0),
            self.state_root,
            self.generation,
            self.secret,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        super().tearDown()

    def request(self, path, *, authorization=None, method="GET", payload=None):
        request = urllib.request.Request(
            self.base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                **({"Authorization": authorization} if authorization else {}),
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_index_mints_child_and_wrong_project_fails_closed(self):
        status, opened = self.request(
            "/_control/open",
            authorization=f"Root {self.secret}",
            method="POST",
            payload={"scope": "project_index"},
        )
        self.assertEqual(status, 200)
        index_capability = opened["capability"]
        status, index = self.request(
            "/api/projects",
            authorization=f"Bearer {index_capability}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(index["projects"]), 2)

        status, child = self.request(
            "/api/projects/first-project/capability",
            authorization=f"Bearer {index_capability}",
            method="POST",
        )
        self.assertEqual(status, 200)
        project_capability = child["capability"]
        status, _ = self.request(
            "/api/project/first-project",
            authorization=f"Bearer {project_capability}",
        )
        self.assertEqual(status, 200)
        status, body = self.request(
            "/api/project/second-project",
            authorization=f"Bearer {project_capability}",
        )
        self.assertEqual(status, 403)
        self.assertEqual(body, {"error": "capability_scope"})
        status, _ = self.request(
            "/api/projects",
            authorization=f"Bearer {project_capability}",
        )
        self.assertEqual(status, 403)
        status, _ = self.request(
            "/api/unassigned",
            authorization=f"Bearer {project_capability}",
        )
        self.assertEqual(status, 403)

    def test_control_open_returns_typed_scope_refusal(self):
        with mock.patch(
            "dashboard_server.project_index_projection",
            side_effect=ValueError("project index unavailable"),
        ):
            status, value = self.request(
                "/_control/open",
                authorization=f"Root {self.secret}",
                method="POST",
                payload={"scope": "project_index"},
            )

        self.assertEqual(status, 404)
        self.assertEqual(value["error"], "scope_unavailable")


class ProjectOpenOnceTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.first = self.corpus("first")
        self.second = self.corpus("second")
        self.write_declaration(self.first, self.declaration(self.first))
        self.write_declaration(self.second, self.declaration(self.second))

    def test_open_once_race_browser_failure_and_service_restart(self):
        urls = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda item: register_dashboard(
                    item[0],
                    str(uuid.uuid4()),
                    self.state_root,
                    browser_open=lambda url: urls.append(url) or True,
                ),
                ((self.first, 1), (self.second, 2)),
            ))
        self.assertEqual(sum(item["opened"] for item in results), 1)
        self.assertEqual(len(urls), 1)

        service = service_status(self.state_root)["service"]
        os.kill(service["pid"], signal.SIGTERM)
        STARTED_PROCESSES.pop(service["pid"]).wait(timeout=5)
        urls.clear()
        restarted = register_dashboard(
            self.first,
            str(uuid.uuid4()),
            self.state_root,
            browser_open=lambda url: urls.append(url) or True,
        )
        self.assertTrue(restarted["opened"])
        self.assertEqual(len(urls), 1)

        service = service_status(self.state_root)["service"]
        os.kill(service["pid"], signal.SIGTERM)
        STARTED_PROCESSES.pop(service["pid"]).wait(timeout=5)
        with self.assertRaisesRegex(ValueError, "browser open failed"):
            register_dashboard(
                self.first,
                str(uuid.uuid4()),
                self.state_root,
                browser_open=lambda url: False,
            )
        retried = register_dashboard(
            self.second,
            str(uuid.uuid4()),
            self.state_root,
            browser_open=lambda url: True,
        )
        self.assertTrue(retried["opened"])

    def test_custom_state_registration_can_skip_service_and_browser(self):
        urls = []
        registered = register_dashboard(
            self.first,
            str(uuid.uuid4()),
            self.state_root,
            launch_service=False,
            browser_open=lambda url: urls.append(url) or True,
        )

        self.assertEqual(registered["project_id"], "example-project")
        self.assertFalse(registered["service_started"])
        self.assertFalse(registered["opened"])
        self.assertIsNone(registered["url"])
        self.assertEqual(urls, [])
        self.assertEqual(service_status(self.state_root)["status"], "stopped")

    def test_static_client_uses_only_session_storage(self):
        source = (
            Path(__file__).with_name("dashboard_static") / "dashboard.js"
        ).read_text(encoding="utf-8")
        self.assertIn("sessionStorage", source)
        self.assertIn("skill-eval-cap:", source)
        self.assertIn("window.history.replaceState", source)
        self.assertIn("Ready for first evaluation", source)
        self.assertIn("No evaluation runs yet", source)
        self.assertIn("renderProjectRuns", source)
        self.assertIn("Run attempt", source)
        self.assertIn("Positive or negative when complete", source)
        self.assertIn("Private final check", source)
        self.assertIn("No experiments launched", source)
        self.assertNotIn("No project-bound runs", source)
        self.assertIn("removeItem(capabilityStorageKey)", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("document.cookie", source)
        self.assertNotIn("?cap=", source)


if __name__ == "__main__":
    unittest.main()
