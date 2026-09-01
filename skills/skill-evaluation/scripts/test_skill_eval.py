#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from skill_eval import (
    add_case,
    freeze_case,
    frozen_case_path,
    init_corpus,
    parse_run,
    run_case,
    validate_judgment,
    verify_case,
)


class SkillEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "corpus"
        init_corpus(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_case(self, case_id: str = "example-case") -> Path:
        add_case(
            self.root,
            case_id,
            "example-skill",
            ["candidate-pass-1", "candidate-pass-2"],
        )
        case_dir = self.root / "cases" / case_id
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        definition["behavioral_claim"] = "The skill reacts to the supplied evidence."
        definition["authority_kind"] = "synthetic"
        definition_path.write_text(json.dumps(definition, indent=2) + "\n")
        (case_dir / "evidence" / "candidate-pass-1" / "product.md").write_text(
            "product evidence\n", encoding="utf-8"
        )
        (case_dir / "evidence" / "candidate-pass-2" / "proposal.md").write_text(
            "proposal evidence\n", encoding="utf-8"
        )
        (case_dir / "judge-reference" / "gold.md").write_text(
            "hidden correction\n", encoding="utf-8"
        )
        (case_dir / "criteria.md").write_text(
            "candidate must react correctly\n", encoding="utf-8"
        )
        return case_dir

    def test_freeze_and_verify(self) -> None:
        self.make_case()
        frozen = freeze_case(self.root, "example-case", replace=False)
        self.assertTrue((frozen / "case-manifest.json").is_file())
        self.assertGreater(verify_case(self.root, "example-case"), 0)

    def test_case_roots_are_independent(self) -> None:
        self.make_case("first-case")
        first = freeze_case(self.root, "first-case", replace=False)
        original = (first / "case-manifest.json").read_bytes()

        self.make_case("second-case")
        freeze_case(self.root, "second-case", replace=False)
        self.assertEqual(original, (first / "case-manifest.json").read_bytes())

    def test_replace_is_required(self) -> None:
        case_dir = self.make_case()
        original = freeze_case(self.root, "example-case", replace=False)
        with self.assertRaises(ValueError):
            freeze_case(self.root, "example-case", replace=False)
        (
            case_dir / "evidence" / "candidate-pass-1" / "product.md"
        ).write_text("revised evidence\n", encoding="utf-8")
        replacement = freeze_case(self.root, "example-case", replace=True)
        self.assertNotEqual(original, replacement)
        self.assertTrue((original / "case-manifest.json").is_file())

    def test_tampered_bundle_fails(self) -> None:
        self.make_case()
        freeze_case(self.root, "example-case", replace=False)
        packet = (
            frozen_case_path(self.root, "example-case")
            / "candidate-pass-1"
            / "product.md"
        )
        packet.write_text("changed\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_case(self.root, "example-case")

    def test_phase_id_cannot_escape_frozen_case(self) -> None:
        case_dir = self.make_case()
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        definition["phases"][0]["id"] = "../../outside"
        definition_path.write_text(json.dumps(definition, indent=2) + "\n")
        with self.assertRaises(ValueError):
            freeze_case(self.root, "example-case", replace=False)
        self.assertFalse((self.root / "outside").exists())

    def test_view_outside_workdir_is_rejected(self) -> None:
        workdir = Path(self.temp.name) / "workdir"
        workdir.mkdir()
        log = Path(self.temp.name) / "run.jsonl"
        events = [
            {
                "type": "tool.execution_start",
                "data": {
                    "toolName": "skill",
                    "arguments": {"skill": "example-skill"},
                    "model": "fake-model",
                },
            },
            {
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "outside-view",
                    "toolName": "view",
                    "arguments": {"path": "../criteria.md"},
                    "model": "fake-model",
                },
            },
            {
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "outside-view",
                    "success": True,
                    "model": "fake-model",
                },
            },
            {
                "type": "assistant.message",
                "data": {"content": "answer", "model": "fake-model"},
            },
            {"type": "result", "exitCode": 0},
        ]
        log.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            parse_run(
                log,
                skill="example-skill",
                expected_model="fake-model",
                cwd=workdir,
                require_skill=True,
            )

    def test_incomplete_judgment_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_judgment({"verdict": "PASS"}, "claude-opus-5")

    def test_empty_judge_reference_is_rejected(self) -> None:
        case_dir = self.make_case()
        (case_dir / "judge-reference" / "gold.md").unlink()
        with self.assertRaises(ValueError):
            freeze_case(self.root, "example-case", replace=False)

    def test_candidate_validation_failure_has_receipt(self) -> None:
        case_dir = self.make_case()
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        definition["phases"][0]["must_include"] = ["never-present"]
        definition_path.write_text(json.dumps(definition, indent=2) + "\n")
        freeze_case(self.root, "example-case", replace=False)

        plugin = Path(self.temp.name) / "failure-plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n"
            "description: Test examples. Use when evaluating an example.\n---\n"
            "# example-skill\n",
            encoding="utf-8",
        )
        fake = Path(self.temp.name) / "failure-copilot"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "if '--version' in sys.argv:\n"
            " print('fake-copilot 1.0')\n"
            " raise SystemExit(0)\n"
            "model=sys.argv[sys.argv.index('--model')+1]\n"
            "print(json.dumps({'type':'tool.execution_start','data':"
            "{'toolName':'skill','arguments':{'skill':'example-skill'},"
            "'model':model}}))\n"
            "print(json.dumps({'type':'assistant.message','data':"
            "{'content':'candidate-result','model':model}}))\n"
            "print(json.dumps({'type':'result','exitCode':0}))\n",
            encoding="utf-8",
        )
        os.chmod(fake, 0o755)

        with self.assertRaises(ValueError):
            run_case(
                self.root,
                "example-case",
                plugin,
                fake,
                "fake-model",
                "high",
                "existing",
                60,
            )
        receipts = list(
            (self.root / "runs").glob(
                "*/example-case/candidate-pass-1-failure-receipt.json"
            )
        )
        self.assertEqual(len(receipts), 1)

    def test_run_with_fake_copilot(self) -> None:
        case_dir = self.make_case()
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        for phase in definition["phases"]:
            phase["must_include"] = ["candidate-result"]
        definition_path.write_text(json.dumps(definition, indent=2) + "\n")
        freeze_case(self.root, "example-case", replace=False)

        plugin = Path(self.temp.name) / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n"
            "description: Test examples. Use when evaluating an example.\n---\n"
            "# example-skill\n",
            encoding="utf-8",
        )
        fake = Path(self.temp.name) / "fake-copilot"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "if '--version' in sys.argv:\n"
            " print('fake-copilot 1.0')\n"
            " raise SystemExit(0)\n"
            "prompt=sys.argv[sys.argv.index('-p')+1]\n"
            "model=sys.argv[sys.argv.index('--model')+1]\n"
            "if 'independent behavioral judge' in prompt:\n"
            " out=json.dumps({'verdict':'PASS','confidence':'HIGH',"
            "'matched':['claim'],'missed':[],'overcorrections':[],"
            "'generalized_skill_defect':None})\n"
            "else:\n"
            " print(json.dumps({'type':'tool.execution_start','data':"
            "{'toolName':'skill','arguments':{'skill':'example-skill'},"
            "'model':model}}))\n"
            " out='candidate-result'\n"
            "print(json.dumps({'type':'assistant.message','data':"
            "{'content':out,'model':model}}))\n"
            "print(json.dumps({'type':'result','exitCode':0}))\n",
            encoding="utf-8",
        )
        os.chmod(fake, 0o755)

        run = run_case(
            self.root,
            "example-case",
            plugin,
            fake,
            "fake-model",
            "high",
            "existing",
            60,
        )
        self.assertIn("**Result: PASS**", (run / "REPORT.md").read_text())
        self.assertEqual(
            json.loads((run / "judgment-claude-opus-5.json").read_text())[
                "verdict"
            ],
            "PASS",
        )
        self.assertTrue((run / "judge-claude-opus-5-receipt.json").is_file())
        self.assertFalse((run / "criteria.md").exists())
        identity = json.loads((run / "skill-identity.json").read_text())
        self.assertIn("target-plugin", identity["plugin_dir"])


if __name__ == "__main__":
    unittest.main()
