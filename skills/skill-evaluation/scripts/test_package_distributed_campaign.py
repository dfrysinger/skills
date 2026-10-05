import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("package_distributed_campaign.py")
SPEC = importlib.util.spec_from_file_location("package_distributed_campaign", SCRIPT)
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


class PackageDistributedCampaignTests(unittest.TestCase):
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
            for suffix in ("one", "two"):
                receipt = packager.package_campaign(
                    source,
                    root / f"full-{suffix}",
                    root / f"candidate-{suffix}",
                    root / f"full-{suffix}.tar.gz",
                    root / f"candidate-{suffix}.tar.gz",
                    root / f"receipt-{suffix}.json",
                    root / f"completion-{suffix}.json",
                    ["cases/*/*/hidden"],
                )
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
            with tarfile.open(root / "candidate-one.tar.gz", "r:gz") as archive:
                names = archive.getnames()
            self.assertFalse(any("/hidden" in name for name in names))

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
