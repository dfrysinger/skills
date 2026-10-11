import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("package_distributed_campaign.py")
SPEC = importlib.util.spec_from_file_location("package_distributed_campaign", SCRIPT)
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


class PackageDistributedCampaignTests(unittest.TestCase):
    def test_v2_treatment_inventory_is_verified_before_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            treatment = source / "treatments/baseline/instructions.md"
            hidden = source / "cases/example/revision/hidden/authority/criteria.md"
            treatment.parent.mkdir(parents=True)
            hidden.parent.mkdir(parents=True)
            treatment.write_text("baseline\n")
            hidden.write_text("criteria\n")
            treatment_sha = packager.sha256(treatment)
            treatment_fingerprint = packager.canonical_fingerprint({
                "targetSkillIdentities": [
                    {
                        "skillName": "example-skill",
                        "evaluatorFingerprint": "c" * 64,
                    }
                ],
                "files": [
                    {
                        "path": "treatments/baseline/instructions.md",
                        "sha256": treatment_sha,
                    }
                ],
            })
            manifest = {
                "schemaVersion": 2,
                "campaignId": "example-campaign",
                "experimentPlanSha256": "a" * 64,
                "treatmentInventory": {
                    "baseline": {
                        "treatmentFingerprint": treatment_fingerprint,
                        "targetSkillIdentities": [
                            {
                                "skillName": "example-skill",
                                "evaluatorFingerprint": "c" * 64,
                            }
                        ],
                        "files": [
                            {
                                "path": "treatments/baseline/instructions.md",
                                "sha256": treatment_sha,
                            }
                        ],
                    }
                },
            }
            (source / "package-manifest.json").write_text(json.dumps(manifest) + "\n")

            receipt = packager.package_campaign(
                source,
                root / "full",
                root / "candidate",
                root / "full.tar.gz",
                root / "candidate.tar.gz",
                root / "receipt.json",
                root / "completion.json",
                ["cases/*/*/hidden"],
            )

            self.assertEqual(receipt["schemaVersion"], 2)
            self.assertEqual(receipt["experimentPlanSha256"], "a" * 64)
            self.assertEqual(
                receipt["treatmentInventory"]["baseline"]["files"][0],
                {
                    "path": "treatments/baseline/instructions.md",
                    "sha256": treatment_sha,
                },
            )
            completion = json.loads((root / "completion.json").read_text())
            self.assertEqual(completion["schemaVersion"], 2)
            self.assertEqual(completion["experimentPlanSha256"], "a" * 64)

            for output in (
                root / "full-refused",
                root / "candidate-refused",
                root / "full-refused.tar.gz",
                root / "candidate-refused.tar.gz",
                root / "receipt-refused.json",
                root / "completion-refused.json",
            ):
                self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "removes treatment inventory"):
                packager.package_campaign(
                    source,
                    root / "full-refused",
                    root / "candidate-refused",
                    root / "full-refused.tar.gz",
                    root / "candidate-refused.tar.gz",
                    root / "receipt-refused.json",
                    root / "completion-refused.json",
                    ["treatments"],
                )
            self.assertFalse((root / "full-refused").exists())

    def test_v2_treatment_inventory_rejects_symlink_escape_and_digest_mismatch(self):
        scenarios = ("symlink", "symlink-directory", "escape", "digest")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()
                treatment = source / "treatment.md"
                treatment.write_text("baseline\n")
                path = "treatment.md"
                digest_value = packager.sha256(treatment)
                if scenario == "symlink":
                    treatment.unlink()
                    treatment.symlink_to(root / "outside")
                elif scenario == "symlink-directory":
                    outside = root / "outside"
                    outside.mkdir()
                    (outside / "treatment.md").write_text("baseline\n")
                    link = source / "linked"
                    link.symlink_to(outside, target_is_directory=True)
                    path = "linked/treatment.md"
                    digest_value = packager.sha256(outside / "treatment.md")
                elif scenario == "escape":
                    path = "../outside"
                else:
                    digest_value = "f" * 64
                files = [{"path": path, "sha256": digest_value}]
                skills = [{
                    "skillName": "example-skill",
                    "evaluatorFingerprint": "c" * 64,
                }]
                (source / "package-manifest.json").write_text(json.dumps({
                    "schemaVersion": 2,
                    "campaignId": "example-campaign",
                    "experimentPlanSha256": "a" * 64,
                    "treatmentInventory": {
                        "baseline": {
                            "treatmentFingerprint": packager.canonical_fingerprint({
                                "targetSkillIdentities": skills,
                                "files": files,
                            }),
                            "targetSkillIdentities": skills,
                            "files": files,
                        }
                    },
                }))
                with self.assertRaises(ValueError):
                    packager.package_campaign(
                        source,
                        root / "full",
                        root / "candidate",
                        root / "full.tar.gz",
                        root / "candidate.tar.gz",
                        root / "receipt.json",
                        root / "completion.json",
                        ["hidden"],
                    )
                self.assertFalse((root / "full").exists())

    def test_builds_deterministic_split_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "cases/example/revision/candidate").mkdir(parents=True)
            (source / "cases/example/revision/hidden/authority").mkdir(parents=True)
            (source / "package-manifest.json").write_text(
                json.dumps({"campaignId": "example-campaign"}) + "\n"
            )
            (source / "cases/example/revision/candidate/task.md").write_text("task\n")
            (source / "cases/example/revision/hidden/authority/criteria.md").write_text(
                "criteria\n"
            )

            receipts = []
            (source / "task-link").symlink_to("cases/example/revision/candidate/task.md")
            (source / "cases/example/revision/candidate/task.md").chmod(0o755)
            for suffix, workers in (("one", 1), ("two", 4)):
                result = subprocess.run(
                    [
                        sys.executable, "-B", str(SCRIPT),
                        "--source", str(source),
                        "--full-root", str(root / f"full-{suffix}"),
                        "--candidate-root", str(root / f"candidate-{suffix}"),
                        "--full-archive", str(root / f"full-{suffix}.tar.gz"),
                        "--candidate-archive", str(root / f"candidate-{suffix}.tar.gz"),
                        "--receipt", str(root / f"receipt-{suffix}.json"),
                        "--completion", str(root / f"completion-{suffix}.json"),
                        "--hidden-pattern", "cases/*/*/hidden",
                        "--hash-workers", str(workers),
                    ],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["hashWorkers"], workers)
                receipts.append(receipt)

            self.assertEqual(
                receipts[0]["full"]["archiveSha256"],
                receipts[1]["full"]["archiveSha256"],
            )
            self.assertEqual(
                receipts[0]["candidate"]["archiveSha256"],
                receipts[1]["candidate"]["archiveSha256"],
            )
            self.assertEqual(
                receipts[0]["packageManifestSha256"],
                receipts[1]["packageManifestSha256"],
            )
            for payload in ("full", "candidate"):
                self.assertEqual(
                    receipts[0][payload]["inventorySha256"],
                    receipts[1][payload]["inventorySha256"],
                )
                self.assertEqual(
                    receipts[0][payload]["treeSha256"],
                    receipts[1][payload]["treeSha256"],
                )
            with tarfile.open(root / "candidate-one.tar.gz", "r:gz") as archive:
                names = archive.getnames()
            self.assertFalse(any("/hidden" in name for name in names))

    def test_parallel_hashing_propagates_file_read_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").write_text("data")
            with mock.patch.object(
                packager, "sha256", side_effect=PermissionError("unreadable input")
            ):
                for function in (packager.inventory, packager.tree_sha256):
                    with self.assertRaisesRegex(PermissionError, "unreadable input"):
                        function(root, workers=4)

    def test_invalid_hash_worker_count_creates_no_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for workers in (0, 33, True):
                with self.assertRaisesRegex(ValueError, "hash workers"):
                    packager.package_campaign(
                        root / "source", root / "full", root / "candidate",
                        root / "full.tar.gz", root / "candidate.tar.gz",
                        root / "receipt.json", root / "completion.json", ["hidden"],
                        hash_workers=workers,
                    )
            command = [
                sys.executable, "-B", str(SCRIPT), "--source", str(root / "source"),
                "--full-root", str(root / "full"), "--candidate-root", str(root / "candidate"),
                "--full-archive", str(root / "full.tar.gz"),
                "--candidate-archive", str(root / "candidate.tar.gz"),
                "--receipt", str(root / "receipt.json"),
                "--completion", str(root / "completion.json"), "--hash-workers", "0",
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid choice", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_refuses_missing_hidden_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "package-manifest.json").write_text(
                json.dumps({"campaignId": "example-campaign"}) + "\n"
            )
            with self.assertRaisesRegex(ValueError, "removed no files"):
                packager.package_campaign(
                    source,
                    root / "full",
                    root / "candidate",
                    root / "full.tar.gz",
                    root / "candidate.tar.gz",
                    root / "receipt.json",
                    root / "completion.json",
                    ["cases/*/*/hidden"],
                )


if __name__ == "__main__":
    unittest.main()
