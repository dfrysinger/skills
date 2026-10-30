#!/usr/bin/env python3

from __future__ import annotations

import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from migrate_history import (
    _candidate_trace_audit,
    _cleanup_failed_migration,
    _normalize_manifest,
    _safe_extract,
    rollback,
)
from project_dashboard import project_index_projection
from skill_eval import digest, write_json


class MigrationManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        write_json(self.source, {"schema_version": 1})
        self.skill = self.root / "SKILL.md"
        self.skill.write_text("# Development loop\n", encoding="utf-8")
        self.package_root = self.root / "package"
        self.package_root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def reference(self, path: Path) -> dict:
        return {"path": str(path), "sha256": digest(path)}

    def manifest(self) -> dict:
        tasks = []
        for index in range(1, 9):
            source_key = f"c{index:02d}"
            repetitions = 2 if source_key == "c08" else 3
            required_passes = (
                2 if source_key in {"c04", "c05", "c06", "c08"} else 3
            )
            attempts = []
            for repetition in range(1, repetitions + 1):
                candidate_outcome = (
                    "FAIL"
                    if source_key == "c07" and repetition == 2
                    else "PASS"
                )
                attempts.append({
                    "attempt_id": (
                        f"r2850-h01-{source_key}-r{repetition}"
                    ),
                    "treatment_id": "h01-probe-interference-bracket",
                    "repetition": repetition,
                    "outcome": candidate_outcome,
                    "execution_state": "consumed_original",
                    "result_source": self.reference(self.source),
                    "proof_source": None,
                    "retained_archive": self.reference(self.source),
                    "terminal_timestamp": None,
                    "candidate_elapsed_seconds": None,
                    "usage_observations": [],
                    "complete_financial_cost": None,
                    "unknown_fields": ["cost"],
                })
                control_outcome = "UNEXECUTED_STOP"
                if source_key == "c01":
                    control_outcome = "PASS"
                elif source_key == "c02":
                    control_outcome = "FAIL" if repetition == 2 else "PASS"
                elif source_key == "c07" and repetition == 1:
                    control_outcome = "PASS"
                terminal = control_outcome in {"PASS", "FAIL"}
                attempts.append({
                    "attempt_id": (
                        f"r2850-b01-{source_key}-r{repetition}"
                    ),
                    "treatment_id": "b01-unchanged-parent",
                    "repetition": repetition,
                    "outcome": control_outcome,
                    "execution_state": (
                        "consumed_original" if terminal else "unexecuted_stop"
                    ),
                    "result_source": (
                        self.reference(self.source) if terminal else None
                    ),
                    "proof_source": None,
                    "retained_archive": (
                        self.reference(self.source) if terminal else None
                    ),
                    "terminal_timestamp": None,
                    "candidate_elapsed_seconds": None,
                    "usage_observations": [],
                    "complete_financial_cost": None,
                    "unknown_fields": ["cost"],
                })
            tasks.append({
                "source_case_key": source_key,
                "case_id": f"case-{index:02d}",
                "title": f"Task {index}",
                "summary": f"Historical task {index}.",
                "role": "development",
                "original_task_revision": f"{index:02x}" * 32,
                "execution_case_revision": f"{index:x}" * 64,
                "package_root": str(self.package_root),
                "archive": self.reference(self.source),
                "package_manifest": self.reference(self.source),
                "case_manifest": self.reference(self.source),
                "candidate_archive": self.reference(self.source),
                "candidate_task": self.reference(self.source),
                "qualification": {
                    "required_repetitions": repetitions,
                    "required_passes": required_passes,
                    "historical_threshold_met": source_key != "c07",
                },
                "attempts": attempts,
                "unknown_fields": [],
            })
        return {
            "schema_version": 1,
            "migration_id": "migration-test",
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "output_root": str(self.root / "output"),
            "state_root": str(self.root / "state"),
            "project": {
                "project_id": "migration-project",
                "title": "Migration project",
                "goal": "Preserve historical outcomes.",
                "target_skill": "development-loop",
            },
            "experiment": {
                "experiment_id": "general-probe-interference-comparison-r2850",
                "title": "Historical experiment",
                "summary": "One fixed historical population.",
                "candidate_model": "model-a",
                "candidate_timeout_seconds": 120,
                "target_os": "macos",
                "architecture": "arm64",
                "route": "local",
            },
            "treatments": [
                {
                    "treatment_id": "h01-probe-interference-bracket",
                    "role": "candidate",
                    "hypothesis": "Candidate improves behavior.",
                    "skill_file": str(self.skill),
                    "skill_file_sha256": digest(self.skill),
                },
                {
                    "treatment_id": "b01-unchanged-parent",
                    "role": "control",
                    "hypothesis": "Control preserves baseline behavior.",
                    "skill_file": str(self.skill),
                    "skill_file_sha256": digest(self.skill),
                },
            ],
            "tasks": tasks,
            "unknown_fields": [],
        }

    def write_manifest(self, value: dict) -> Path:
        path = self.root / "manifest.json"
        write_json(path, value)
        return path

    def test_exact_population_manifest_keeps_three_revision_namespaces(self):
        value = self.manifest()
        normalized = _normalize_manifest(self.write_manifest(value))
        task = normalized["manifest"]["tasks"][0]
        self.assertNotEqual(
            task["original_task_revision"],
            task["execution_case_revision"],
        )
        self.assertEqual(len(normalized["manifest"]["tasks"]), 8)

    def test_manifest_rejects_missing_task_and_rescue_attempts(self):
        value = self.manifest()
        value["tasks"].pop()
        with self.assertRaisesRegex(ValueError, "exactly eight tasks"):
            _normalize_manifest(self.write_manifest(value))

        value = self.manifest()
        rescue = dict(value["tasks"][0]["attempts"][0])
        rescue["attempt_id"] = (
            "r2850-h01-c01-r4"
        )
        rescue["repetition"] = 4
        value["tasks"][0]["attempts"].append(rescue)
        with self.assertRaisesRegex(ValueError, "fixed treatment population"):
            _normalize_manifest(self.write_manifest(value))

        value = self.manifest()
        value["tasks"][2]["attempts"] = [
            item for item in value["tasks"][2]["attempts"]
            if item["treatment_id"] != "b01-unchanged-parent"
            or item["repetition"] != 3
        ]
        with self.assertRaisesRegex(ValueError, "fixed treatment population"):
            _normalize_manifest(self.write_manifest(value))

    def test_manifest_rejects_threshold_conflict(self):
        value = self.manifest()
        value["tasks"][0]["attempts"][0]["outcome"] = "FAIL"
        with self.assertRaisesRegex(ValueError, "threshold conflicts"):
            _normalize_manifest(self.write_manifest(value))

    def test_safe_extract_rejects_link_members(self):
        source = self.root / "payload.txt"
        source.write_text("payload\n", encoding="utf-8")
        archive = self.root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(source, arcname="payload.txt")
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../outside"
            stream.addfile(link)
        with self.assertRaisesRegex(ValueError, "escapes its destination"):
            _safe_extract(archive, self.root / "extracted")

    def test_safe_extract_allows_bounded_internal_symbolic_link(self):
        source = self.root / "payload.txt"
        source.write_text("payload\n", encoding="utf-8")
        archive = self.root / "bounded.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(source, arcname="payload.txt")
            directory = tarfile.TarInfo("directory")
            directory.type = tarfile.DIRTYPE
            stream.addfile(directory)
            link = tarfile.TarInfo("directory/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../payload.txt"
            stream.addfile(link)
        destination = self.root / "bounded"
        _safe_extract(archive, destination)
        self.assertEqual((destination / "directory/link").read_text(), "payload\n")

    def test_candidate_trace_accepts_one_bound_export_footer(self):
        footer = (
            "Session exported to: "
            "/Users/runner/work/skill-evaluation/skill-evaluation/"
            "run-root/candidate-primary-transcript.md"
        )
        audit = _candidate_trace_audit(
            b'{"type":"session.start","data":{}}\n'
            + footer.encode()
            + b'\n{"type":"session.end","data":{}}\n',
            [],
            self.root,
        )
        self.assertEqual(audit["trace_event_count"], 2)
        self.assertEqual(audit["trace_footer_count"], 1)

    def test_candidate_trace_rejects_unbound_or_duplicate_footer(self):
        valid_footer = (
            b"Session exported to: "
            b"/Users/runner/work/skill-evaluation/skill-evaluation/"
            b"run-root/candidate-primary-transcript.md\n"
        )
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            _candidate_trace_audit(
                b'{"type":"session.start","data":{}}\n'
                b"Session exported to: /tmp/candidate-primary-transcript.md\n",
                [],
                self.root,
            )
        with self.assertRaisesRegex(ValueError, "export footer is invalid"):
            _candidate_trace_audit(
                b'{"type":"session.start","data":{}}\n'
                + valid_footer
                + valid_footer,
                [],
                self.root,
            )

    def test_failed_migration_cleanup_removes_partial_registration(self):
        output = self.root / "failed-output"
        output.mkdir()
        (output / "partial.txt").write_text("partial\n", encoding="utf-8")
        state = self.root / "failed-state"
        campaign_id = "a" * 32
        project_id = "development-loop-generalization"
        fingerprint = "b" * 64
        campaign = state / "campaigns" / f"{campaign_id}.json"
        campaign.parent.mkdir(parents=True)
        write_json(campaign, {"corpus_root": str(output.resolve())})
        project_root = state / "projects" / project_id
        project_root.mkdir(parents=True)
        write_json(project_root / f"{campaign_id}.json", {"project_id": project_id})
        declaration = (
            project_root
            / "declarations"
            / campaign_id
            / f"{fingerprint}.json"
        )
        declaration.parent.mkdir(parents=True)
        write_json(declaration, {"project_id": project_id})

        _cleanup_failed_migration(
            output,
            state,
            project_id,
            {"campaign_id": campaign_id},
            fingerprint,
        )

        self.assertFalse(output.exists())
        self.assertFalse(campaign.exists())
        self.assertFalse(project_root.exists())


class MigrationRollbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.state = self.root / "state"
        self.output.mkdir()
        self.state.mkdir()
        self.project_id = "migration-project"
        self.campaign_id = "a" * 32
        self.project_file = (
            self.state
            / "projects"
            / self.project_id
            / f"{self.campaign_id}.json"
        )
        self.project_file.parent.mkdir(parents=True)
        write_json(self.project_file, {"owned": True})
        self.campaign_file = self.state / "campaigns" / f"{self.campaign_id}.json"
        self.campaign_file.parent.mkdir()
        write_json(self.campaign_file, {"owned": True})
        self.output_file = self.output / "corpus.json"
        write_json(self.output_file, {"schema_version": 1, "cases": []})
        local_state = self.output / ".skill-evaluation-ui"
        local_state.mkdir()
        self.campaign_lock = local_state / "campaign.lock"
        self.campaign_lock.touch()
        self.receipt = local_state / "one-time-migration-receipt.json"
        write_json(self.receipt, {
            "schema_version": 1,
            "migration_id": "migration-test",
            "manifest_sha256": "f" * 64,
            "output_root": str(self.output),
            "state_root": str(self.state),
            "project_id": self.project_id,
            "campaign_id": self.campaign_id,
            "pre_migration_project_index": project_index_projection(
                self.root / "empty-state"
            ),
            "artifacts": [
                self.reference(self.project_file),
                self.reference(self.campaign_file),
                self.reference(self.output_file),
                self.reference(self.campaign_lock),
            ],
        })

    def tearDown(self):
        self.temp.cleanup()

    def reference(self, path: Path) -> dict:
        return {"path": str(path), "sha256": digest(path)}

    def test_rollback_refuses_foreign_project_artifact(self):
        foreign = self.project_file.parent / "foreign.json"
        write_json(foreign, {"foreign": True})
        with patch(
            "migrate_history.project_index_projection",
            return_value={
                "schema_version": 1,
                "projects": [{"project_id": self.project_id}],
            },
        ):
            with self.assertRaisesRegex(ValueError, "foreign project artifacts"):
                rollback(self.receipt)
        self.assertTrue(self.output.exists())

    def test_rollback_removes_only_receipt_owned_state(self):
        with patch(
            "migrate_history.project_index_projection",
            side_effect=[
                {
                    "schema_version": 1,
                    "projects": [{"project_id": self.project_id}],
                },
                {"schema_version": 1, "projects": []},
            ],
        ):
            result = rollback(self.receipt)
        self.assertTrue(result["rolled_back"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.project_file.parent.exists())
        self.assertFalse(self.campaign_file.exists())

    def test_rerun_and_rollback_refuse_foreign_output_artifacts(self):
        foreign = self.output / "foreign.txt"
        foreign.write_text("foreign\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "output inventory changed"):
            rollback(self.receipt)
        self.assertTrue(foreign.exists())


if __name__ == "__main__":
    unittest.main()
