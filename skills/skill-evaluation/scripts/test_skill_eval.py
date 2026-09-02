#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skill_eval import (
    add_case,
    freeze_case,
    frozen_case_path,
    init_corpus,
    parse_run,
    run_case,
    run_suite,
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

    def test_resumed_phase_can_reuse_loaded_skill_context(self) -> None:
        workdir = Path(self.temp.name) / "resumed-workdir"
        workdir.mkdir()
        log = Path(self.temp.name) / "resumed.jsonl"
        log.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "assistant.message",
                            "data": {
                                "content": "resumed answer",
                                "model": "fake-model",
                            },
                        }
                    ),
                    json.dumps({"type": "result", "exitCode": 0}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = parse_run(
            log,
            skill="example-skill",
            expected_model="fake-model",
            cwd=workdir,
            require_skill=None,
        )
        self.assertFalse(result["skill_loaded"])

    def test_judge_cannot_invoke_target_skill(self) -> None:
        workdir = Path(self.temp.name) / "judge-workdir"
        workdir.mkdir()
        log = Path(self.temp.name) / "judge.jsonl"
        log.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool.execution_start",
                            "data": {
                                "toolName": "skill",
                                "arguments": {"skill": "example-skill"},
                                "model": "fake-model",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "assistant.message",
                            "data": {
                                "content": "judge answer",
                                "model": "fake-model",
                            },
                        }
                    ),
                    json.dumps({"type": "result", "exitCode": 0}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "must not invoke"):
            parse_run(
                log,
                skill="example-skill",
                expected_model="fake-model",
                cwd=workdir,
                require_skill=False,
            )

    def test_incomplete_judgment_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_judgment({"verdict": "PASS"}, "claude-opus-5")

    def test_bare_unanswerable_judgment_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "decisive missing evidence"):
            validate_judgment(
                {
                    "verdict": "UNANSWERABLE",
                    "confidence": "HIGH",
                    "matched": [],
                    "missed": [],
                    "overcorrections": [],
                    "generalized_skill_defect": None,
                },
                "gpt-5.6-terra",
            )

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
        (case_dir / "prompts" / "judge.md").write_text(
            "Act as an independent behavioral judge for the `example-skill` skill.\n",
            encoding="utf-8",
        )
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
        self.assertIn(
            "never return\na bare `UNANSWERABLE`",
            (run / "judge-claude-opus-5-prompt.md").read_text(),
        )
        self.assertFalse((run / "criteria.md").exists())
        identity = json.loads((run / "skill-identity.json").read_text())
        self.assertIn("target-plugin", identity["plugin_dir"])

    def test_run_suite_with_fake_copilot(self) -> None:
        for case_id in ("first-case", "second-case"):
            case_dir = self.make_case(case_id)
            definition_path = case_dir / "case.json"
            definition = json.loads(definition_path.read_text())
            definition["cohort"] = "regression"
            for phase in definition["phases"]:
                phase["must_include"] = ["candidate-result"]
            definition_path.write_text(json.dumps(definition, indent=2) + "\n")
            freeze_case(self.root, case_id, replace=False)

        plugin = Path(self.temp.name) / "suite-plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n"
            "description: Test examples. Use when evaluating an example.\n---\n"
            "# example-skill\n",
            encoding="utf-8",
        )
        fake = Path(self.temp.name) / "suite-copilot"
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

        with mock.patch(
            "skill_eval.copilot_identity",
            return_value={"version": "fake-copilot 1.0"},
        ) as identity:
            suite_root, passed = run_suite(
                self.root,
                plugin,
                fake,
                "fake-model",
                "high",
                "existing",
                60,
                workers=2,
            )
        identity.assert_called_once()
        self.assertNotEqual(identity.call_args.args[0], fake)
        self.assertTrue(passed)
        report = (suite_root / "SUITE-REPORT.md").read_text()
        self.assertIn("**Result: PASS**", report)
        self.assertIn("`first-case`", report)
        self.assertIn("`second-case`", report)
        result = json.loads((suite_root / "suite-result.json").read_text())
        self.assertEqual(len(result["cases"]), 2)
        self.assertEqual(result["failures"], [])
        harnesses = [
            json.loads((self.root / item["run_path"] / "harness-identity.json").read_text())
            for item in result["cases"]
        ]
        self.assertEqual(len({item["sha256"] for item in harnesses}), 1)
        self.assertEqual(
            Path(harnesses[0]["path"]).parent.resolve(),
            suite_root.resolve(),
        )

    def test_run_suite_rejects_invalid_selection(self) -> None:
        plugin = Path(self.temp.name) / "unused-plugin"
        copilot = Path(self.temp.name) / "unused-copilot"
        common = (plugin, copilot, "fake-model", "high", "existing", 60)

        with self.assertRaisesRegex(ValueError, "contains no cases"):
            run_suite(self.root, *common, workers=1)

        self.make_case("known-case")
        with self.assertRaisesRegex(ValueError, "workers must be positive"):
            run_suite(self.root, *common, workers=0)
        with self.assertRaisesRegex(ValueError, "max attempts must be positive"):
            run_suite(self.root, *common, workers=1, max_attempts=0)
        with self.assertRaisesRegex(ValueError, "must be unique"):
            run_suite(
                self.root,
                *common,
                workers=1,
                case_ids=["known-case", "known-case"],
            )
        with self.assertRaisesRegex(ValueError, "unknown suite cases"):
            run_suite(
                self.root,
                *common,
                workers=1,
                case_ids=["missing-case"],
            )

    def test_run_suite_retries_behavioral_failures(self) -> None:
        self.make_case("retry-case")
        freeze_case(self.root, "retry-case", replace=False)
        plugin = Path(self.temp.name) / "retry-plugin"
        plugin.mkdir()
        copilot = Path(self.temp.name) / "retry-copilot"
        copilot.write_text("fake\n", encoding="utf-8")
        attempts = 0

        def fake_run_case(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            run_root = self.root / "runs" / f"retry-{attempts}" / "retry-case"
            run_root.mkdir(parents=True)
            verdict = "FAIL" if attempts == 1 else "PASS"
            for model in ("claude-opus-5", "gpt-5-6-terra"):
                (run_root / f"judgment-{model}.json").write_text(
                    json.dumps({"verdict": verdict}) + "\n",
                    encoding="utf-8",
                )
            return run_root

        with (
            mock.patch(
                "skill_eval.copilot_identity",
                return_value={"version": "fake-copilot 1.0"},
            ),
            mock.patch("skill_eval.run_case", side_effect=fake_run_case),
        ):
            suite_root, passed = run_suite(
                self.root,
                plugin,
                copilot,
                "fake-model",
                "high",
                "existing",
                60,
                workers=1,
                max_attempts=2,
            )

        self.assertTrue(passed)
        result = json.loads((suite_root / "suite-result.json").read_text())
        self.assertEqual(result["cases"][0]["attempt_count"], 2)
        self.assertEqual(
            [item["result"] for item in result["cases"][0]["attempts"]],
            ["FAIL", "PASS"],
        )
        self.assertIn("Cases passing after retry: 1", (suite_root / "SUITE-REPORT.md").read_text())

    def test_run_suite_reports_unfrozen_case_error(self) -> None:
        self.make_case("frozen-case")
        freeze_case(self.root, "frozen-case", replace=False)
        self.make_case("unfrozen-case")
        plugin = Path(self.temp.name) / "report-plugin"
        plugin.mkdir()
        copilot = Path(self.temp.name) / "report-copilot"
        copilot.write_text("fake\n", encoding="utf-8")

        def fake_run_case(root, case_id, *args, **kwargs):
            if case_id == "unfrozen-case":
                raise FileNotFoundError("not frozen")
            run_root = root / "runs" / "reported" / case_id
            run_root.mkdir(parents=True)
            for model in ("claude-opus-5", "gpt-5-6-terra"):
                (run_root / f"judgment-{model}.json").write_text(
                    json.dumps({"verdict": "PASS"}) + "\n",
                    encoding="utf-8",
                )
            return run_root

        with (
            mock.patch(
                "skill_eval.copilot_identity",
                return_value={"version": "fake-copilot 1.0"},
            ),
            mock.patch("skill_eval.run_case", side_effect=fake_run_case),
        ):
            suite_root, passed = run_suite(
                self.root,
                plugin,
                copilot,
                "fake-model",
                "high",
                "existing",
                60,
                workers=2,
            )

        self.assertFalse(passed)
        report = (suite_root / "SUITE-REPORT.md").read_text()
        self.assertIn("Cases completed: 1", report)
        self.assertIn("Execution failures: 1", report)

    def test_run_suite_keeps_last_completed_attempt_after_error(self) -> None:
        self.make_case("partial-case")
        freeze_case(self.root, "partial-case", replace=False)
        plugin = Path(self.temp.name) / "partial-plugin"
        plugin.mkdir()
        copilot = Path(self.temp.name) / "partial-copilot"
        copilot.write_text("fake\n", encoding="utf-8")
        attempts = 0

        def fake_run_case(root, case_id, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise RuntimeError("transient failure")
            run_root = root / "runs" / "partial" / case_id
            run_root.mkdir(parents=True)
            for model in ("claude-opus-5", "gpt-5-6-terra"):
                (run_root / f"judgment-{model}.json").write_text(
                    json.dumps({"verdict": "UNANSWERABLE"}) + "\n",
                    encoding="utf-8",
                )
            return run_root

        with (
            mock.patch(
                "skill_eval.copilot_identity",
                return_value={"version": "fake-copilot 1.0"},
            ),
            mock.patch("skill_eval.run_case", side_effect=fake_run_case),
        ):
            suite_root, passed = run_suite(
                self.root,
                plugin,
                copilot,
                "fake-model",
                "high",
                "existing",
                60,
                workers=1,
                max_attempts=2,
            )

        self.assertFalse(passed)
        result = json.loads((suite_root / "suite-result.json").read_text())
        self.assertEqual(result["cases"][0]["result"], "UNANSWERABLE")
        self.assertEqual(
            result["cases"][0]["run_path"],
            "runs/partial/partial-case",
        )


if __name__ == "__main__":
    unittest.main()
