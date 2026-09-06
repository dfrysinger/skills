#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib


SCRIPT = Path(__file__).with_name("validate-live-proof.py")
SPEC = importlib.util.spec_from_file_location("validate_live_proof", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_png(path: Path, pixels: list[tuple[int, int, int]]) -> None:
    width = len(pixels)
    raw = b"\x00" + b"".join(bytes(pixel) for pixel in pixels)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        MODULE.PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class ValidateLiveProofTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.worktree = self.root / "repo"
        self.worktree.mkdir()
        subprocess.run(["git", "-C", str(self.worktree), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(self.worktree), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.worktree), "config", "user.name", "Test"],
            check=True,
        )
        (self.worktree / "app.txt").write_text("candidate\n")
        subprocess.run(["git", "-C", str(self.worktree), "add", "app.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(self.worktree), "commit", "-qm", "candidate"],
            check=True,
        )
        self.capture = self.root / "proof.png"
        write_png(self.capture, [(0, 0, 0), (255, 255, 255)])
        self.receipt_path = self.root / "receipt.json"
        self.receipt = {
            "schemaVersion": 1,
            "id": "example-flow",
            "candidate": MODULE.candidate_snapshot(str(self.worktree)),
            "running": {
                "identity": "pid=123 build=example",
                "candidateMatchEvidence": "Runtime marker returned candidate-only value.",
            },
            "scenario": {
                "trigger": "Press the repair button and submit the seeded prompt.",
                "terminalState": "The repaired dashboard renders after navigation.",
                "forbiddenOutcomes": ["loading remains visible", "dashboard is missing"],
                "forbiddenOutcomeEvidence": [
                    {
                        "kind": "runtime",
                        "source": "Final DOM snapshot contains neither forbidden message.",
                    }
                ],
                "checkpoints": [
                    {
                        "name": "trigger",
                        "expected": "Repair chat opens for the dashboard enterprise.",
                        "observed": "Repair chat opened for Avocado Corp.",
                        "evidence": [
                            {
                                "kind": "runtime",
                                "source": "bridge snapshot at checkpoint 1",
                            }
                        ],
                        "result": "PASS",
                    },
                    {
                        "name": "terminal",
                        "expected": "Repaired dashboard renders persisted figures.",
                        "observed": "Dashboard rendered all saved headline figures.",
                        "evidence": [
                            {"kind": "artifact", "source": str(self.capture)}
                        ],
                        "result": "PASS",
                    },
                ],
            },
            "visual": {
                "required": True,
                "captures": [
                    {
                        "path": str(self.capture),
                        "opened": True,
                        "claim": "The dashboard shows two populated headline cards.",
                        "width": 2,
                        "height": 1,
                        "pixelSpread": "PASS",
                    }
                ],
            },
            "manualWorkaround": False,
            "unverified": [],
            "status": "PASS",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self, receipt: dict[str, object] | None = None) -> None:
        self.receipt_path.write_text(json.dumps(receipt or self.receipt))
        MODULE.validate_receipt(str(self.receipt_path))

    def assert_rejected(self, receipt: dict[str, object], message: str) -> None:
        self.receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(MODULE.ReceiptError, message):
            MODULE.validate_receipt(str(self.receipt_path))

    def test_accepts_complete_current_receipt(self) -> None:
        self.validate()

    def test_scope_specific_fingerprints_do_not_define_one_campaign(self) -> None:
        (self.worktree / "other.txt").write_text("independent component\n")
        narrow = MODULE.candidate_snapshot(str(self.worktree), reuse_inputs=["app.txt"])
        broad = MODULE.candidate_snapshot(
            str(self.worktree), reuse_inputs=["app.txt", "other.txt"]
        )
        self.assertEqual(narrow["worktree"], broad["worktree"])
        self.assertEqual(narrow["head"], broad["head"])
        self.assertNotEqual(narrow["fingerprint"], broad["fingerprint"])
        self.assertEqual(MODULE._validate_candidate(narrow), narrow)
        self.assertEqual(MODULE._validate_candidate(broad), broad)

    def test_rejects_stale_candidate(self) -> None:
        (self.worktree / "app.txt").write_text("changed after proof\n")
        self.assert_rejected(self.receipt, "candidate is stale")

    def test_rejects_missing_interaction_evidence(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["scenario"]["checkpoints"][0]["evidence"] = []
        self.assert_rejected(receipt, "evidence must contain")

    def test_rejects_tests_only_evidence(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["scenario"]["checkpoints"][0]["evidence"] = [
            {"kind": "test", "source": "focused unit test passed"}
        ]
        self.assert_rejected(receipt, "kind must be one of")

    def test_rejects_partial_flow(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["scenario"]["checkpoints"] = receipt["scenario"]["checkpoints"][:1]
        self.assert_rejected(receipt, "trigger and terminal")

    def test_rejects_uninspected_capture(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["visual"]["captures"][0]["opened"] = False
        self.assert_rejected(receipt, "opened must be true")

    def test_rejects_blank_capture(self) -> None:
        write_png(self.capture, [(0, 0, 0), (0, 0, 0)])
        self.assert_rejected(self.receipt, "visually blank")

    def test_rejects_manual_workaround(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["manualWorkaround"] = True
        self.assert_rejected(receipt, "manualWorkaround")

    def test_rejects_unverified_acceptance_criteria(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["unverified"] = ["reload persistence"]
        self.assert_rejected(receipt, "unverified")

    def test_rejects_non_pass_terminal_state(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["status"] = "INCONCLUSIVE"
        self.assert_rejected(receipt, "status must be PASS")

    def prepare_reuse(self, inputs: list[str] | None = None) -> None:
        self.inputs = inputs or ["app.txt"]
        self.receipt["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), reuse_inputs=self.inputs
        )
        self.coverage = {
            name: "Measured input closure documented in the scenario inventory."
            for name in MODULE.INPUT_CLASSES
        }
        self.receipt["reuseCoverageEvidence"] = self.coverage.copy()
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.source_bytes = self.receipt_path.read_bytes()
        self.reuse_path = self.root / "reuse.json"

    def reuse_record(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "sourceReceiptSha256": MODULE._hash_file(self.receipt_path),
            "candidate": MODULE.candidate_snapshot(str(self.worktree), reuse_inputs=self.inputs),
            "checkedCorrespondenceEvidence": self.coverage.copy(),
        }

    def validate_reuse(self, record: dict[str, object] | None = None) -> dict[str, object]:
        self.reuse_path.write_text(json.dumps(record or self.reuse_record()))
        return MODULE.validate_receipt(str(self.receipt_path), str(self.reuse_path))

    def test_reuses_across_commit_and_worktree_without_rewriting_execution(self) -> None:
        self.prepare_reuse()
        (self.worktree / "unrelated.txt").write_text("independent component\n")
        subprocess.run(["git", "-C", str(self.worktree), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.worktree), "commit", "-qm", "unrelated"], check=True
        )
        moved = self.root / "other-worktree"
        subprocess.run(
            ["git", "-C", str(self.worktree), "worktree", "add", "-q", "--detach", str(moved)],
            check=True,
        )
        self.worktree = moved
        record = self.reuse_record()
        with self.assertRaisesRegex(MODULE.ReceiptError, "candidate is stale"):
            MODULE.validate_receipt(str(self.receipt_path))
        snapshot = subprocess.run(
            ["python3", str(SCRIPT), "fingerprint", "--worktree", str(moved),
             "--reuse-input", "app.txt"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(snapshot.stdout), record["candidate"])
        result = self.validate_reuse(record)
        self.assertEqual(result["candidate"], record["candidate"]["fingerprint"])
        self.assertEqual(result["reusedFrom"]["candidate"], self.receipt["candidate"]["fingerprint"])
        self.assertEqual(self.receipt_path.read_bytes(), self.source_bytes)
        completed = subprocess.run(
            ["python3", str(SCRIPT), "validate", str(self.receipt_path), "--reuse", str(self.reuse_path)],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(completed.stdout), result)

    def test_reuses_unchanged_dirty_input_after_commit(self) -> None:
        (self.worktree / "app.txt").write_text("dirty but exercised\n")
        self.prepare_reuse()
        subprocess.run(["git", "-C", str(self.worktree), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.worktree), "commit", "-qm", "record exercised code"], check=True
        )
        self.validate_reuse()

    def test_reuses_with_unrelated_dirty_and_untracked_changes(self) -> None:
        (self.worktree / "other.txt").write_text("unrelated\n")
        self.prepare_reuse()
        (self.worktree / "other.txt").write_text("unrelated successor\n")
        self.validate_reuse()

    def test_rejects_changed_inputs_even_with_fresh_target_fingerprint(self) -> None:
        scope = self.worktree / "inputs"
        scope.mkdir()
        for name in MODULE.INPUT_CLASSES:
            (scope / name).write_text("original\n")
        self.prepare_reuse(["app.txt", "inputs"])
        for name in MODULE.INPUT_CLASSES:
            with self.subTest(input_class=name):
                path = scope / name
                path.write_text("changed\n")
                with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
                    self.validate_reuse()
                path.write_text("original\n")
        (self.worktree / "app.txt").write_text("changed runtime\n")
        with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
            self.validate_reuse()

    def test_rejects_added_deleted_and_mode_changed_scoped_files(self) -> None:
        scope = self.worktree / "inputs"
        scope.mkdir()
        path = scope / "runtime.txt"
        path.write_text("runtime\n")
        self.prepare_reuse(["inputs"])
        original_mode = path.stat().st_mode
        for change in ("add", "delete", "mode"):
            with self.subTest(change=change):
                added = scope / "new.txt"
                if change == "add":
                    added.write_text("new dependency\n")
                elif change == "delete":
                    path.unlink()
                else:
                    path.chmod(0o755)
                with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
                    self.validate_reuse()
                if change == "add":
                    added.unlink()
                elif change == "delete":
                    path.write_text("runtime\n")
                path.chmod(original_mode)

    def test_rejects_ignored_input_changes_and_scope_removal(self) -> None:
        (self.worktree / ".gitignore").write_text("runtime.env\n")
        runtime = self.worktree / "runtime.env"
        runtime.write_text("original\n")
        self.prepare_reuse()
        self.receipt["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), additional_inputs=["runtime.env"], reuse_inputs=self.inputs
        )
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.assertIn("runtime.env", [
            item["path"] for item in self.receipt["candidate"]["reuseInputs"]
        ])
        accepted = self.reuse_record()
        accepted["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), additional_inputs=["runtime.env"], reuse_inputs=self.inputs
        )
        self.validate_reuse(accepted)
        record = self.reuse_record()
        with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
            self.validate_reuse(record)
        runtime.write_text("changed\n")
        record["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), additional_inputs=["runtime.env"], reuse_inputs=self.inputs
        )
        with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
            self.validate_reuse(record)

    def test_rejects_new_ignored_file_in_scoped_directory(self) -> None:
        scope = self.worktree / "inputs"
        scope.mkdir()
        (self.worktree / ".gitignore").write_text("inputs/\n")
        self.prepare_reuse(["inputs"])
        (scope / "generated.txt").write_text("new ignored input\n")
        with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
            self.validate_reuse()

    def test_output_exclusions_do_not_hide_reuse_input_changes(self) -> None:
        with self.assertRaisesRegex(MODULE.ReceiptError, "excluded output is tracked"):
            MODULE.candidate_snapshot(str(self.worktree), excluded_outputs=["app.txt"])
        scope = self.worktree / "inputs"
        scope.mkdir()
        (scope / "generated.txt").write_text("original\n")
        self.prepare_reuse(["inputs"])
        self.receipt["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), excluded_outputs=["inputs"], reuse_inputs=self.inputs
        )
        self.receipt_path.write_text(json.dumps(self.receipt))
        (scope / "generated.txt").write_text("changed\n")
        record = self.reuse_record()
        record["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), excluded_outputs=["inputs"], reuse_inputs=self.inputs
        )
        with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
            self.validate_reuse(record)

    def test_rejects_missing_scope_and_symlinks(self) -> None:
        (self.worktree / "linked").symlink_to(self.worktree, target_is_directory=True)
        scope = self.worktree / "inputs"
        scope.mkdir()
        (scope / "linked.txt").symlink_to(self.worktree / "app.txt")
        for value in ("missing", "../app.txt", "linked/app.txt", "inputs"):
            with self.subTest(path=value), self.assertRaises(MODULE.ReceiptError):
                MODULE.candidate_snapshot(str(self.worktree), reuse_inputs=[value])

    def test_rejects_missing_coverage_and_changed_source_receipt(self) -> None:
        self.prepare_reuse()
        for name in MODULE.INPUT_CLASSES:
            with self.subTest(input_class=name):
                record = self.reuse_record()
                del record["checkedCorrespondenceEvidence"][name]
                with self.assertRaisesRegex(MODULE.ReceiptError, "checkedCorrespondenceEvidence"):
                    self.validate_reuse(record)
        record = self.reuse_record()
        self.receipt_path.write_bytes(self.source_bytes + b"\n")
        with self.assertRaisesRegex(MODULE.ReceiptError, "source receipt hash"):
            self.validate_reuse(record)

    def test_rejects_receipt_without_execution_time_scope(self) -> None:
        self.prepare_reuse()
        del self.receipt["candidate"]["reuseInputs"]
        self.receipt_path.write_text(json.dumps(self.receipt))
        with self.assertRaisesRegex(MODULE.ReceiptError, "execution-time reuseInputs"):
            self.validate_reuse()

    def test_rejects_stale_reuse_target(self) -> None:
        self.prepare_reuse()
        record = self.reuse_record()
        (self.worktree / "app.txt").write_text("changed after correspondence\n")
        with self.assertRaisesRegex(MODULE.ReceiptError, "candidate is stale"):
            self.validate_reuse(record)

    def test_reuse_does_not_relax_original_receipt_gates(self) -> None:
        self.prepare_reuse()
        for field, value, message in (
            ("status", "FAIL", "status must be PASS"),
            ("manualWorkaround", True, "manualWorkaround"),
            ("unverified", ["missing claim"], "unverified"),
            ("reuseCoverageEvidence", {}, "reuseCoverageEvidence"),
        ):
            with self.subTest(field=field):
                receipt = copy.deepcopy(self.receipt)
                receipt[field] = value
                self.receipt_path.write_text(json.dumps(receipt))
                with self.assertRaisesRegex(MODULE.ReceiptError, message):
                    self.validate_reuse()
        receipt = copy.deepcopy(self.receipt)
        receipt["scenario"]["checkpoints"][0]["evidence"][0]["kind"] = "test"
        self.receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(MODULE.ReceiptError, "kind must be one of"):
            self.validate_reuse()
        self.receipt_path.write_bytes(self.source_bytes)
        write_png(self.capture, [(0, 0, 0), (0, 0, 0)])
        with self.assertRaisesRegex(MODULE.ReceiptError, "visually blank"):
            self.validate_reuse()

    def test_direct_validation_still_checks_scoped_ignored_inputs(self) -> None:
        (self.worktree / ".gitignore").write_text("runtime.env\n")
        runtime = self.worktree / "runtime.env"
        runtime.write_text("original\n")
        self.prepare_reuse(["app.txt", "runtime.env"])
        self.validate()
        runtime.write_text("changed\n")
        self.assert_rejected(self.receipt, "candidate is stale")

    def prepare_legacy(
        self, inputs: list[str] | None = None,
        additional: list[str] | None = None, excluded: list[str] | None = None,
    ) -> dict[str, object]:
        self.inputs = inputs or ["app.txt"]
        self.receipt["candidate"] = MODULE.candidate_snapshot(
            str(self.worktree), excluded_outputs=excluded, additional_inputs=additional
        )
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.source_bytes = self.receipt_path.read_bytes()
        self.original_worktree = self.worktree
        target = self.root / "target"
        subprocess.run(
            ["git", "-C", str(self.worktree), "worktree", "add", "-q", "--detach", str(target)],
            check=True,
        )
        shutil.copytree(
            self.worktree, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git")
        )
        self.worktree = target
        self.coverage = {
            name: "Checked against the original recorded inputs and scenario evidence."
            for name in MODULE.INPUT_CLASSES
        }
        self.reuse_path = self.root / "reuse.json"
        record = self.reuse_record()
        record["candidate"] = MODULE.candidate_snapshot(
            str(target), excluded, additional, self.inputs
        )
        record["deriveLegacyBaseline"] = True
        record["legacyCoverageEvidence"] = self.coverage.copy()
        return record

    def test_derives_legacy_baseline_without_rewriting_execution(self) -> None:
        record = self.prepare_legacy()
        (self.worktree / "unrelated.txt").write_text("independent change\n")
        subprocess.run(["git", "-C", str(self.worktree), "add", "unrelated.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(self.worktree), "commit", "-qm", "unrelated"], check=True
        )
        record["candidate"] = self.reuse_record()["candidate"]
        result = self.validate_reuse(record)
        self.assertEqual(result["legacyBaseline"], {
            "origin": "derived-during-validation",
            "reuseInputs": record["candidate"]["reuseInputs"],
        })
        self.assertEqual(result["reusedFrom"]["candidate"], self.receipt["candidate"]["fingerprint"])
        self.assertEqual(self.receipt_path.read_bytes(), self.source_bytes)
        completed = subprocess.run(
            ["python3", str(SCRIPT), "validate", str(self.receipt_path), "--reuse", str(self.reuse_path)],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(completed.stdout), result)

    def test_legacy_accepts_retained_dirty_untracked_and_recorded_ignored_inputs(self) -> None:
        (self.worktree / "app.txt").write_text("original dirty code\n")
        (self.worktree / "fixture.txt").write_text("original untracked fixture\n")
        (self.worktree / ".gitignore").write_text("runtime.env\n")
        (self.worktree / "runtime.env").write_text("recorded runtime identity\n")
        record = self.prepare_legacy(
            ["app.txt", "fixture.txt"], additional=["runtime.env"]
        )
        self.validate_reuse(record)
        (self.original_worktree / "runtime.env").write_text("runtime changed\n")
        with self.assertRaisesRegex(MODULE.ReceiptError, "candidate is stale"):
            self.validate_reuse(record)

    def test_legacy_rejects_changed_source_even_outside_requested_scope(self) -> None:
        record = self.prepare_legacy()
        (self.original_worktree / "unrelated.txt").write_text("source no longer exact\n")
        with self.assertRaisesRegex(MODULE.ReceiptError, "candidate is stale"):
            self.validate_reuse(record)

    def test_legacy_rejects_changed_target_inputs_with_fresh_fingerprint(self) -> None:
        record = self.prepare_legacy()
        (self.worktree / "app.txt").write_text("new executable content\n")
        record["candidate"] = self.reuse_record()["candidate"]
        record["legacyBaseline"] = {
            "origin": "derived-during-validation",
            "reuseInputs": record["candidate"]["reuseInputs"],
        }
        with self.assertRaisesRegex(MODULE.ReceiptError, "reuse inputs changed"):
            self.validate_reuse(record)

    def test_legacy_rejects_missing_or_redirected_source(self) -> None:
        record = self.prepare_legacy()
        original = self.original_worktree
        moved = self.root / "moved"
        original.rename(moved)
        with self.assertRaisesRegex(MODULE.ReceiptError, "git .* failed|does not exist"):
            self.validate_reuse(record)
        original.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.ReceiptError, "moved or was redirected"):
            self.validate_reuse(record)

    def test_legacy_rejects_unrecorded_ignored_runtime_input(self) -> None:
        (self.worktree / ".gitignore").write_text("runtime.env\n")
        (self.worktree / "runtime.env").write_text("unverified runtime identity\n")
        record = self.prepare_legacy(["app.txt", "runtime.env"])
        with self.assertRaisesRegex(MODULE.ReceiptError, "not covered by the original fingerprint"):
            self.validate_reuse(record)

    def test_legacy_rejects_unrecorded_excluded_input(self) -> None:
        (self.worktree / "generated.txt").write_text("unverified generated input\n")
        record = self.prepare_legacy(["app.txt", "generated.txt"], excluded=["generated.txt"])
        with self.assertRaisesRegex(MODULE.ReceiptError, "not covered by the original fingerprint"):
            self.validate_reuse(record)

    def test_legacy_rejects_missing_coverage_and_failed_original_scenario(self) -> None:
        record = self.prepare_legacy()
        for name in MODULE.INPUT_CLASSES:
            with self.subTest(input_class=name):
                incomplete = copy.deepcopy(record)
                del incomplete["legacyCoverageEvidence"][name]
                with self.assertRaisesRegex(MODULE.ReceiptError, "legacyCoverageEvidence"):
                    self.validate_reuse(incomplete)
        self.receipt["scenario"]["checkpoints"][0]["result"] = "FAIL"
        self.receipt_path.write_text(json.dumps(self.receipt))
        record["sourceReceiptSha256"] = MODULE._hash_file(self.receipt_path)
        with self.assertRaisesRegex(MODULE.ReceiptError, "result must be PASS"):
            self.validate_reuse(record)


if __name__ == "__main__":
    unittest.main()
