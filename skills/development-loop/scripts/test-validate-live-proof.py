#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
