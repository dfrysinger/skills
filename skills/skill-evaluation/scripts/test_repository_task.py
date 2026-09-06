#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import repository_task as repository
import skill_eval as evaluator


class RepositoryTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            dir=Path(__file__).parent if os.environ.get("SKILL_EVAL_TEST_IMAGE") else None)
        self.root = Path(self.temp.name) / "corpus"
        evaluator.init_corpus(self.root)
        self.image = "sha256:" + "1" * 64

    def tearDown(self):
        self.temp.cleanup()

    def make_case(self, name="example"):
        evaluator.add_case(self.root, name, "example-skill", ["candidate"],
                           case_type="repository-task")
        case = self.root / "cases" / name
        definition = evaluator.read_json(case / "case.json")
        definition.update(authority_kind="synthetic", behavioral_claim="Repair addition.")
        task = definition["repository_task"]
        task.update(image=self.image, source_revision="synthetic-v1")
        task["admission"]["base_target_failure"]["output_contains"] = "wrong addition"
        evaluator.write_json(case / "case.json", definition)
        (case / "repository" / "code.py").write_text("def add(a, b): return a - b\n")
        (case / "repository" / "remove.txt").write_text("delete me\n")
        (case / "repository" / "mode.sh").write_text("#!/bin/sh\nexit 0\n")
        (case / "repository" / "mode.sh").chmod(0o755)
        (case / "repository" / ".gitignore").write_text("ignored.txt\n")
        (case / "evidence" / "candidate" / "task.md").write_text("Fix addition.\n")
        (case / "criteria.md").write_text("Preserve subtraction outside the requested function.\n")
        (case / "judge-reference" / "provenance.json").write_text('{"kind":"synthetic"}\n')
        (case / "judge-reference" / "grader" / "target.py").write_text(
            "import sys\nsys.path.insert(0, '/workspace/repo')\n"
            "from code import add\nassert add(2, 3) == 5, 'wrong addition'\n"
            "print('TARGET_CHECKS_PASSED')\n"
        )
        (case / "judge-reference" / "grader" / "regression.py").write_text(
            "from pathlib import Path\n"
            "assert Path('/workspace/repo/mode.sh').is_file()\n"
            "print('REGRESSION_CHECKS_PASSED')\n"
        )
        (case / "judge-reference" / "reference.patch").write_text(
            "diff --git a/code.py b/code.py\n--- a/code.py\n+++ b/code.py\n"
            "@@ -1 +1 @@\n-def add(a, b): return a - b\n+def add(a, b): return a + b\n"
        )
        return case

    def freeze(self):
        self.make_case()
        return evaluator.freeze_case(self.root, "example", False)

    def test_scaffold_and_parser(self):
        self.make_case()
        arguments = evaluator.parser().parse_args([
            "run", str(self.root), "--case", "example", "--plugin-dir", "/plugin",
            "--arm", "baseline",
        ])
        self.assertEqual(arguments.arm, "baseline")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            evaluator.add_case(self.root, "multiple", "s", ["one", "two"],
                               case_type="repository-task")

    def test_freeze_modes_tamper_and_case_independence(self):
        frozen = self.freeze()
        root_bytes = (frozen / "case-manifest.json").read_bytes()
        self.make_case("second")
        evaluator.freeze_case(self.root, "second", False)
        self.assertEqual((frozen / "case-manifest.json").read_bytes(), root_bytes)
        self.assertGreater(evaluator.verify_case(self.root, "example"), 0)
        self.assertEqual((frozen / "repository" / "mode.sh").stat().st_mode & 0o777, 0o755)
        (frozen / "repository" / "mode.sh").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode mismatch"):
            evaluator.verify_case(self.root, "example")

    def test_hidden_grader_tamper_rejected(self):
        frozen = self.freeze()
        (frozen / "judge-reference" / "grader" / "target.py").write_text("print('PASS')")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            evaluator.verify_case(self.root, "example")

    def test_snapshot_git_and_symlinks_rejected(self):
        case = self.make_case()
        (case / "repository" / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "Git metadata"):
            evaluator.freeze_case(self.root, "example", False)
        (case / "repository" / ".git").rmdir()
        (case / "repository" / "link").symlink_to("code.py")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            evaluator.freeze_case(self.root, "example", False)

    def test_image_and_completion_contract_required(self):
        case = self.make_case()
        definition = evaluator.read_json(case / "case.json")
        task = definition["repository_task"]
        task["image"] = "mutable:latest"
        with self.assertRaisesRegex(ValueError, "pinned"):
            repository.validate_definition(definition, case)
        task["image"] = self.image
        task["grading"]["target"]["success_output_contains"] = ""
        with self.assertRaisesRegex(ValueError, "success_output_contains"):
            repository.validate_definition(definition, case)

    def test_hidden_packet_cannot_be_repository_snapshot(self):
        case = self.make_case()
        definition = evaluator.read_json(case / "case.json")
        definition["repository_task"]["snapshot_dir"] = "judge-reference"
        with self.assertRaisesRegex(ValueError, "overlap"):
            repository.validate_definition(definition, case)

    def test_export_ignores_candidate_git_and_preserves_all_changes(self):
        frozen = self.freeze()
        candidate = Path(self.temp.name) / "candidate"
        evaluator.copy_packet(frozen / "repository", candidate)
        (candidate / ".git").mkdir()
        (candidate / ".git" / "HEAD").write_text("malicious baseline\n")
        (candidate / ".git" / "config").write_text("[diff]\nexternal = false\n")
        (candidate / "ignored.txt").write_text("must be captured\n")
        (candidate / "new.bin").write_bytes(b"\x00\xff\x01\x00")
        (candidate / "remove.txt").unlink()
        (candidate / "mode.sh").chmod(0o644)
        (candidate / "code.py").write_text("def add(a, b): return a + b\n")
        patch = Path(self.temp.name) / "candidate.patch"
        repository.export_patch(frozen, candidate, patch)
        self.assertIn(b"GIT binary patch", patch.read_bytes())
        self.assertNotIn(b"malicious baseline", patch.read_bytes())
        fresh = Path(self.temp.name) / "fresh"
        evaluator.copy_packet(frozen / "repository", fresh)
        repository.apply_patch(fresh, patch)
        self.assertEqual((fresh / "new.bin").read_bytes(), b"\x00\xff\x01\x00")
        self.assertEqual((fresh / "ignored.txt").read_text(), "must be captured\n")
        self.assertFalse((fresh / "remove.txt").exists())
        self.assertEqual((fresh / "mode.sh").stat().st_mode & 0o777, 0o644)
        self.assertFalse((fresh / ".git").exists())

    def test_empty_patch_is_valid(self):
        frozen = self.freeze()
        candidate = Path(self.temp.name) / "candidate"
        evaluator.copy_packet(frozen / "repository", candidate)
        patch = Path(self.temp.name) / "empty.patch"
        repository.export_patch(frozen, candidate, patch)
        self.assertEqual(patch.read_bytes(), b"")
        repository.apply_patch(candidate, patch)

    def test_completion_marker_without_zero_exit_is_not_success(self):
        log = Path(self.temp.name) / "check.log"
        log.write_text("TARGET_CHECKS_PASSED")
        command = {"success_output_contains": "TARGET_CHECKS_PASSED"}
        record = {"exit_code": 1, "timed_out": False, "log": log.name}
        self.assertFalse(repository.completed_check(record, command, log.parent))
        record["exit_code"] = 0
        self.assertTrue(repository.completed_check(record, command, log.parent))
        log.write_text("")
        self.assertFalse(repository.completed_check(record, command, log.parent))

    def test_partial_timeout_log_is_exact(self):
        log = Path(self.temp.name) / "partial.log"
        with mock.patch("repository_task.subprocess.run", side_effect=subprocess.TimeoutExpired(
            ["example"], 1, output=b"partial\xff\n"
        )):
            record = repository.command_result(["example"], log, 1)
        self.assertTrue(record["timed_out"])
        self.assertIsNone(record["exit_code"])
        self.assertEqual(log.read_bytes(), b"partial\xff\n")
        self.assertEqual(record["raw_log_sha256"], evaluator.digest(log))

    def test_candidate_tools_and_baseline(self):
        baseline = repository.candidate_command("fake", "high", "task", "baseline")
        skill = repository.candidate_command("fake", "high", "task", "skill")
        self.assertNotIn("--plugin-dir", baseline)
        self.assertIn("--plugin-dir", skill)
        self.assertIn("--allow-tool=shell", skill)
        self.assertIn("--secret-env-vars=COPILOT_GITHUB_TOKEN", skill)
        self.assertIn("--no-remote-export", skill)
        tools = next(item for item in baseline if item.startswith("--available-tools="))
        self.assertNotIn("session_store_sql", tools)
        self.assertNotIn("web_fetch", tools)
        self.assertNotIn("skill", tools)

    def test_repository_parser_allows_toolchain_reads_without_prose_claim(self):
        log = Path(self.temp.name) / "trajectory.jsonl"
        events = [
            {"type": "tool.execution_start", "data": {
                "toolName": "view", "toolCallId": "v", "arguments": {"path": "/plugin/skills/s/SKILL.md"},
                "model": "fake"}},
            {"type": "tool.execution_complete", "data": {"toolCallId": "v", "success": True}},
            {"type": "assistant.message", "data": {"content": "done", "model": "fake"}},
            {"type": "result", "exitCode": 0, "usage": {"premiumRequests": 0.33}},
        ]
        log.write_text("\n".join(json.dumps(event) for event in events))
        result = evaluator.parse_run(
            log, skill="s", expected_model="fake", cwd=Path("/workspace/repo"),
            require_skill=False, boundary="docker-local-packets",
        )
        self.assertEqual(result["usage"]["premiumRequests"], 0.33)
        self.assertIsNone(result["input_tokens"])
        self.assertEqual(result["tool_calls"], 1)
        with self.assertRaisesRegex(ValueError, "escaped"):
            evaluator.parse_run(log, skill="s", expected_model="fake", cwd=Path("/workspace/repo"),
                                require_skill=False)

    def test_skill_arm_requires_successful_tool_completion_not_cli_exit(self):
        log = self.root / "trajectory.jsonl"
        events = [
            {"type": "tool.execution_start", "data": {
                "toolName": "skill", "toolCallId": "s", "arguments": {"skill": "example-skill"},
                "model": "fake"}},
            {"type": "tool.execution_complete", "data": {"toolCallId": "s", "success": False}},
            {"type": "assistant.message", "data": {"content": "done", "model": "fake"}},
            {"type": "result", "exitCode": 0},
        ]
        log.write_text("\n".join(json.dumps(event) for event in events))
        kwargs = dict(skill="example-skill", expected_model="fake", cwd=Path("/workspace/repo"),
                      require_skill=True, boundary="docker-local-packets")
        with self.assertRaisesRegex(ValueError, "must invoke"):
            evaluator.parse_run(log, **kwargs)
        events[1]["data"]["success"] = True
        log.write_text("\n".join(json.dumps(event) for event in events))
        self.assertTrue(evaluator.parse_run(log, **kwargs)["skill_loaded"])

    def test_harness_snapshot_contains_every_module(self):
        destination = Path(self.temp.name) / "harness"
        identity = evaluator.harness_identity(destination)
        self.assertEqual({item["path"] for item in identity["modules"]},
                         {"skill_eval.py", "repository_task.py", "measurement.py",
                          "quality_review.py", "evaluation_history.py"})
        for module in identity["modules"]:
            self.assertEqual(evaluator.digest(destination / module["path"]), module["sha256"])

    def test_custom_repository_judge_prompt_gets_required_json_contract(self):
        case = self.make_case()
        custom_prompt = "Apply this custom repository-specific judgment criterion.\n"
        (case / "prompts" / "judge.md").write_text(custom_prompt, encoding="utf-8")
        frozen = evaluator.freeze_case(self.root, "example", False)
        run_root = Path(self.temp.name) / "run"
        run_root.mkdir()
        for name in ("skill-identity.json", "copilot-identity.json", "harness-identity.json"):
            (run_root / name).write_text("{}\n", encoding="utf-8")
        captured_prompts = []
        judgment = {
            "verdict": "PASS",
            "confidence": "HIGH",
            "matched": ["criterion"],
            "missed": [],
            "overcorrections": [],
            "generalized_skill_defect": None,
        }

        def fake_run_copilot(**kwargs):
            captured_prompts.append(kwargs["prompt"])
            kwargs["log"].write_text("{}\n", encoding="utf-8")
            return ["fake-copilot", "-p", kwargs["prompt"]]

        with (
            mock.patch("skill_eval.run_copilot", side_effect=fake_run_copilot),
            mock.patch(
                "skill_eval.parse_run",
                return_value={
                    "answer": json.dumps(judgment),
                    "models": ["claude-opus-5"],
                    "result_exit_code": 0,
                    "viewed_paths": [],
                },
            ),
        ):
            evaluator.run_judges(
                frozen=frozen,
                definition=evaluator.read_json(frozen / "case.json"),
                run_root=run_root,
                pinned_plugin=Path(self.temp.name) / "plugin",
                copilot=Path(self.temp.name) / "copilot",
                home_mode="existing",
                timeout_seconds=60,
                candidate_artifacts=[],
            )

        self.assertEqual(len(captured_prompts), 2)
        for prompt in captured_prompts:
            self.assertIn(custom_prompt.rstrip(), prompt)
            self.assertEqual(prompt.count("Return only JSON with:"), 1)
            self.assertIn("Assess supported scope and process", prompt)

    def test_missing_auth_is_invalid_with_receipt(self):
        frozen = self.freeze()
        run = Path(self.temp.name) / "run"
        run.mkdir()
        admission = run / "admission.json"
        admission.write_text("{}")
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("repository_task.image_identity", return_value={"id": self.image}),
            mock.patch("repository_task.require_admission", return_value=admission),
        ):
            result = repository.execute_repository(
                self.root, "example", frozen, run, run / "plugin", "fake", "high", 1, "baseline")
        self.assertEqual(result["execution_status"], "INVALID")
        self.assertEqual(result["failure_kind"], "authentication")
        self.assertTrue((run / "execution-result.json").is_file())

    def test_missing_image_admission_is_invalid(self):
        self.freeze()
        with mock.patch("repository_task.image_identity",
                        side_effect=repository.InfrastructureError("missing image")):
            path = repository.validate_repository_case(self.root, "example")
        self.assertEqual(evaluator.read_json(path / "admission-receipt.json")["status"], "INVALID")

    def fake_execution(self, *, timeout=False, grades=None, cli_failure=False):
        frozen = self.freeze()
        run = self.root / "runs" / "fake"
        run.mkdir()
        admission = self.root / "admission.json"
        admission.write_text("{}")
        owner = self

        class FakeContainer:
            def __init__(self, image, mounts, artifacts, **kwargs):
                self.artifacts = artifacts
                self.source = mounts[0][0]
                self.stopped = False
                self.created = True
                owner.assertEqual([item[1] for item in mounts], ["/workspace/repo", "/evidence"])
                artifacts.mkdir(parents=True)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stopped = True

            def stop(self):
                self.stopped = True

            def usage_events(self, session_id):
                owner.assertTrue(self.stopped)
                return None

            def execute(self, command, label, **kwargs):
                log = self.artifacts / f"{label}.log"
                if label == "cli-version":
                    log.write_text("copilot test")
                    return {"exit_code": 0, "log": log.name}
                owner.assertTrue(kwargs["token"])
                (self.source / "code.py").write_text("def add(a, b): return a + b\n")
                (self.source / ".git" / "HEAD").write_text("candidate tampering\n")
                events = [
                    {"type": "assistant.message", "data": {"content": "fixed", "model": "fake"}},
                    {"type": "result", "exitCode": 0, "usage": {"premiumRequests": 0.33}},
                ]
                log.write_text("\n".join(json.dumps(event) for event in events))
                return {
                    "exit_code": None if timeout else 1 if cli_failure else 0,
                    "timed_out": timeout, "log": log.name,
                    "raw_log_sha256": evaluator.digest(log),
                }

        with (
            mock.patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "nonsecret-test-sentinel"}),
            mock.patch("repository_task.image_identity", return_value={"id": self.image}),
            mock.patch("repository_task.require_admission", return_value=admission),
            mock.patch("repository_task.Container", FakeContainer),
            mock.patch("repository_task.grade", side_effect=grades or [
                {"target": {"passed": True}, "regression": {"passed": True}}]) as grade,
        ):
            result = repository.execute_repository(
                self.root, "example", frozen, run, run / "plugin", "fake", "high", 1, "baseline")
        return result, run, grade

    def test_candidate_timeout_scored_fail_and_patch_retained(self):
        result, run, grade = self.fake_execution(timeout=True)
        self.assertEqual(result["execution_status"], "FAIL", result)
        self.assertEqual(result["failure_kind"], "candidate_timeout")
        usage = evaluator.read_json(run / "measurements" / "candidate.json")
        self.assertEqual(usage["outcome"], "timed_out")
        self.assertEqual(usage["session_id"], result["candidate_session_id"])
        self.assertEqual(usage["premium_requests"], 0.33)
        self.assertEqual(usage["completeness"], "partial")
        self.assertIn(b"return a + b", (run / "candidate.patch").read_bytes())
        self.assertEqual(result["patch_sha256"], evaluator.digest(run / "candidate.patch"))
        self.assertTrue((run / "candidate" / "trajectory.log").is_file())
        grade.assert_not_called()

    def test_candidate_cli_error_retains_patch_but_is_invalid(self):
        result, run, grade = self.fake_execution(cli_failure=True)
        self.assertEqual(result["execution_status"], "INVALID", result)
        self.assertTrue((run / "candidate.patch").is_file())
        usage = evaluator.read_json(run / "measurements" / "candidate.json")
        self.assertEqual(usage["outcome"], "failed")
        self.assertEqual(usage["premium_requests"], 0.33)
        grade.assert_not_called()

    def test_candidate_setup_breakage_during_grading_is_scored(self):
        broken = {"target": {"passed": False, "setup_ok": False},
                  "regression": {"passed": False, "setup_ok": False}}
        healthy = {"target": {"passed": True}, "regression": {"passed": True}}
        result, run, grade = self.fake_execution(grades=[broken, healthy])
        self.assertEqual(result["execution_status"], "FAIL", result)
        self.assertEqual(result["failure_kind"], "candidate_grading")
        self.assertEqual(grade.call_count, 2)

    def test_unhealthy_fresh_control_is_invalid_not_candidate_failure(self):
        broken = {"target": {"passed": False}, "regression": {"passed": False}}
        result, run, grade = self.fake_execution(grades=[broken, broken])
        self.assertEqual(result["execution_status"], "INVALID", result)
        self.assertEqual(result["failure_kind"], "grading_environment")

    def test_execution_preserves_reported_usage_and_exact_artifact_hashes(self):
        result, run, grade = self.fake_execution()
        self.assertEqual(result["execution_status"], "PASS", result)
        self.assertEqual(result["usage"], {"premiumRequests": 0.33})
        self.assertIsNone(result["input_tokens"])
        for item in result["artifacts"]:
            self.assertEqual(evaluator.digest(run / item["path"]), item["sha256"])

    def test_repository_judgment_does_not_rewrite_execution_artifact(self):
        self.freeze()
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("example")
        original = []

        def execute(root, case_id, frozen, run, *args, **kwargs):
            result = {"execution_status": "PASS", "behavioral_verdict": None, "failure_kind": None}
            evaluator.write_json(run / "execution-result.json", result)
            original.append(evaluator.digest(run / "execution-result.json"))
            return result

        def judges(**kwargs):
            for name in ("claude-opus-5", "gpt-5.6-terra"):
                evaluator.write_json(kwargs["run_root"] / f"judgment-{name}.json", {"verdict": "FAIL"})

        with (
            mock.patch("repository_task.execute_repository", side_effect=execute),
            mock.patch("skill_eval.run_judges", side_effect=judges),
            mock.patch("skill_eval.copilot_identity", return_value={"version": "fake"}),
        ):
            run = evaluator.run_case(self.root, "example", plugin, Path("/fake"),
                                     "fake", "high", "existing", 1)
        self.assertEqual(evaluator.digest(run / "execution-result.json"), original[0])
        final = evaluator.read_json(run / "repository-result.json")
        self.assertEqual(final["execution_status"], "PASS")
        self.assertEqual(final["behavioral_verdict"], "FAIL")

    def test_quality_failure_preserves_correctness_and_full_timing(self):
        frozen = self.freeze()
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("example")
        original = []
        clock = [0.0]

        def execute(root, case_id, frozen, run, *args, **kwargs):
            timer = kwargs["timeline"]
            clock[0] = 2
            timer.switch("candidate")
            clock[0] = 5
            timer.switch("deterministic_grading")
            clock[0] = 8
            result = {"execution_status": "PASS", "behavioral_verdict": None, "failure_kind": None}
            evaluator.write_json(run / "execution-result.json", result)
            original.append(evaluator.digest(run / "execution-result.json"))
            return result

        def judges(**kwargs):
            clock[0] = 11
            raise ValueError("synthetic behavioral failure")

        def quality(**kwargs):
            clock[0] = 13
            return {"complete": False, "reviewers": [{"status": "failed"}]}

        with (
            mock.patch("skill_eval.time.monotonic", side_effect=lambda: clock[0]),
            mock.patch("repository_task.execute_repository", side_effect=execute),
            mock.patch("skill_eval.run_judges", side_effect=judges),
            mock.patch("quality_review.review_repository", side_effect=quality) as review,
            mock.patch("skill_eval.copilot_identity", return_value={"version": "fake"}),
        ):
            run = evaluator.run_case(self.root, "example", plugin, Path("/fake"),
                                     "fake", "high", "existing", 1, quality_review=True)
        review.assert_called_once()
        self.assertEqual(evaluator.digest(run / "execution-result.json"), original[0])
        result = evaluator.read_json(run / "repository-result.json")
        self.assertEqual(result["execution_status"], "PASS")
        self.assertIn("behavioral_error", result)
        self.assertFalse(result["quality_assessment"]["complete"])
        timing = evaluator.read_json(run / "timing.json")
        self.assertEqual(timing["elapsed_seconds"], 13)
        self.assertEqual([stage["name"] for stage in timing["stages"]],
                         ["preparation", "candidate", "deterministic_grading",
                          "behavioral_judging", "quality_review", "cleanup"])
        self.assertEqual(timing["stages"][3]["status"], "failed")
        self.assertEqual(timing["stages"][4]["status"], "failed")

    def test_run_setup_failure_retains_timing_and_zero_uninvoked_spend(self):
        self.freeze()
        with mock.patch("skill_eval.snapshot_plugin", side_effect=ValueError("bad plugin")):
            run = evaluator.run_case(self.root, "example", self.root / "missing", Path("/fake"),
                                     "fake", "high", "existing", 1)
        self.assertEqual(evaluator.read_json(run / "execution-result.json")["execution_status"], "INVALID")
        timing = evaluator.read_json(run / "timing.json")
        self.assertEqual(timing["stages"][0]["status"], "failed")
        self.assertEqual(timing["stages"][-1]["name"], "cleanup")
        self.assertEqual(evaluator.read_json(run / "accounting.json")["total"]["credits"], 0)

    def test_suite_pass_at_one_does_not_use_retry_or_behavioral_verdict(self):
        self.freeze()
        plugin = Path(self.temp.name) / "plugin"
        plugin.mkdir()
        cli = Path(self.temp.name) / "cli"
        cli.write_text("fake")
        attempts = []

        def fake_run(*args, **kwargs):
            run = self.root / "runs" / str(len(attempts))
            run.mkdir()
            status = "FAIL" if not attempts else "PASS"
            evaluator.write_json(run / "execution-result.json", {
                "execution_status": status, "behavioral_verdict": "PASS"})
            attempts.append(run)
            return run

        with (
            mock.patch("skill_eval.run_case", side_effect=fake_run),
            mock.patch("skill_eval.copilot_identity", return_value={"version": "fake"}),
        ):
            path, passed = evaluator.run_suite(
                self.root, plugin, cli, "fake", "high", "existing", 1, 1, max_attempts=2)
        result = evaluator.read_json(path / "suite-result.json")
        self.assertTrue(passed)
        self.assertEqual(result["repository_executable"]["pass_at_1"], 0)
        self.assertEqual(result["repository_executable"]["valid_first_attempts"], 1)
        self.assertEqual(len(result["cases"][0]["attempts"]), 2)

    def test_suite_invalid_first_attempt_is_not_replaced_by_retry(self):
        self.freeze()
        plugin = self.root / "plugin"
        plugin.mkdir()
        cli = self.root / "cli"
        cli.write_text("fake")
        calls = []

        def fake_run(*args, **kwargs):
            run = self.root / "runs" / str(len(calls))
            run.mkdir()
            status = "INVALID" if not calls else "PASS"
            evaluator.write_json(run / "execution-result.json", {
                "execution_status": status, "behavioral_verdict": "PASS"})
            calls.append(kwargs)
            return run

        with (
            mock.patch("skill_eval.run_case", side_effect=fake_run),
            mock.patch("skill_eval.copilot_identity", return_value={"version": "fake"}),
        ):
            path, passed = evaluator.run_suite(
                self.root, plugin, cli, "fake", "high", "existing", 1, 1, max_attempts=2)
        summary = evaluator.read_json(path / "suite-result.json")["repository_executable"]
        self.assertTrue(passed)
        self.assertIsNone(summary["pass_at_1"])
        self.assertEqual(summary["coverage"], 0)
        self.assertEqual(summary["invalid_first_attempts"], 1)
        self.assertEqual(calls[0]["expected_revision"], calls[1]["expected_revision"])

    def test_suite_behavioral_failure_does_not_lower_executable_pass_at_one(self):
        self.freeze()
        plugin = self.root / "plugin"
        plugin.mkdir()
        cli = self.root / "cli"
        cli.write_text("fake")
        run = self.root / "runs" / "attempt"
        run.mkdir()
        evaluator.write_json(run / "execution-result.json", {
            "execution_status": "PASS", "behavioral_verdict": "FAIL"})
        with (
            mock.patch("skill_eval.run_case", return_value=run),
            mock.patch("skill_eval.copilot_identity", return_value={"version": "fake"}),
        ):
            path, passed = evaluator.run_suite(
                self.root, plugin, cli, "fake", "high", "existing", 1, 1)
        result = evaluator.read_json(path / "suite-result.json")
        self.assertFalse(passed)
        self.assertEqual(result["repository_executable"]["pass_at_1"], 1)
        self.assertEqual(result["cases"][0]["behavioral_verdict"], "FAIL")


@unittest.skipUnless(os.environ.get("SKILL_EVAL_TEST_IMAGE"), "set SKILL_EVAL_TEST_IMAGE for offline Docker smoke")
class DockerRepositoryTests(RepositoryTaskTests):
    def setUp(self):
        super().setUp()
        self.image = os.environ["SKILL_EVAL_TEST_IMAGE"]

    def test_real_admission_and_hidden_grader_survives_candidate_test_edit(self):
        frozen = self.freeze()
        path = repository.validate_repository_case(self.root, "example")
        receipt = evaluator.read_json(path / "admission-receipt.json")
        self.assertEqual(receipt["status"], "PASS", receipt)
        candidate = self.root / "candidate"
        evaluator.copy_packet(frozen / "repository", candidate)
        (candidate / "target.py").write_text("print('TARGET_CHECKS_PASSED')")
        patch = self.root / "bad.patch"
        repository.export_patch(frozen, candidate, patch)
        task = evaluator.read_json(frozen / "case.json")["repository_task"]
        result = repository.grade(frozen, task, self.root / "bad-grading", patch)
        self.assertFalse(result["target"]["passed"])
        self.assertTrue(result["regression"]["passed"])

    def test_candidate_mounts_hide_sibling_and_grader_and_timeout_stops_writer(self):
        frozen = self.freeze()
        source = self.root / "candidate"
        evidence = self.root / "evidence"
        evaluator.copy_packet(frozen / "repository", source)
        evaluator.copy_packet(frozen / "candidate", evidence)
        secret = self.root / "hidden-sentinel.txt"
        secret.write_text("not candidate evidence")
        artifacts = self.root / "candidate-container"
        with repository.Container(self.image, [
            (source, "/workspace/repo", True), (evidence, "/evidence", False),
        ], artifacts, network=True) as container:
            boundary = container.execute({
                "argv": ["python3", "-c",
                         "from pathlib import Path; "
                         f"assert not Path({str(secret)!r}).exists(); "
                         "assert not Path('/grader').exists(); "
                         "assert not Path('/plugin').exists(); "
                         "assert not Path('/var/run/docker.sock').exists(); "
                         "assert Path('/evidence/task.md').is_file(); print('PACKETS_ISOLATED')"],
                "timeout_seconds": 10,
            }, "probe")
            self.assertEqual(boundary["exit_code"], 0)
            self.assertIn("PACKETS_ISOLATED", (artifacts / "probe.log").read_text())
            timeout = container.execute({
                "argv": ["python3", "-c",
                         "import time; from pathlib import Path; print('START', flush=True); "
                         "time.sleep(3); Path('/workspace/repo/late').write_text('bad')"],
                "timeout_seconds": 1,
            }, "timeout")
            self.assertTrue(timeout["timed_out"])
            self.assertTrue(container.stopped)
        self.assertFalse((source / "late").exists())
        self.assertEqual((artifacts / "timeout.log").read_bytes(), b"START\n")
        self.assertEqual(timeout["raw_log_sha256"], evaluator.digest(artifacts / "timeout.log"))

    def test_candidate_broken_setup_and_fresh_reference_control(self):
        case = self.make_case()
        definition = evaluator.read_json(case / "case.json")
        definition["repository_task"]["grading"]["setup"] = [{
            "argv": ["python3", "-c", "from pathlib import Path; assert Path('remove.txt').exists()"],
            "timeout_seconds": 10,
        }]
        evaluator.write_json(case / "case.json", definition)
        frozen = evaluator.freeze_case(self.root, "example", False)
        admission = repository.validate_repository_case(self.root, "example")
        self.assertEqual(evaluator.read_json(admission / "admission-receipt.json")["status"], "PASS")
        candidate = self.root / "candidate"
        evaluator.copy_packet(frozen / "repository", candidate)
        (candidate / "remove.txt").unlink()
        patch = self.root / "broken.patch"
        repository.export_patch(frozen, candidate, patch)
        task = definition["repository_task"]
        grades = repository.grade(frozen, task, self.root / "candidate-grades", patch)
        self.assertTrue(all(not item["setup_ok"] and item["check"] is None for item in grades.values()))
        control = repository.grade(
            frozen, task, self.root / "control", frozen / task["admission"]["reference_patch"])
        self.assertTrue(all(item["passed"] for item in control.values()))

    def test_synthetic_docker_candidate_patch_and_grading_end_to_end(self):
        frozen = self.freeze()
        admission = repository.validate_repository_case(self.root, "example")
        self.assertEqual(evaluator.read_json(admission / "admission-receipt.json")["status"], "PASS")
        run = self.root / "runs" / "synthetic-docker"
        run.mkdir()
        script = (
            "import json; from pathlib import Path; "
            "assert not Path('/grader').exists(); assert not Path('/plugin').exists(); "
            "assert not Path('/var/run/docker.sock').exists(); "
            "Path('code.py').write_text('def add(a, b): return a + b\\n'); "
            "Path('.git/HEAD').write_text('candidate changed Git\\n'); "
            "Path('ignored.txt').write_text('new source\\n'); "
            "print(json.dumps({'type':'assistant.message','data':{'content':'fixed','model':'synthetic'}})); "
            "print(json.dumps({'type':'result','exitCode':0,'usage':{'premiumRequests':0}}))"
        )
        with (
            mock.patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "nonsecret-synthetic-test"}),
            mock.patch("repository_task.candidate_command", return_value=["python3", "-c", script]),
        ):
            result = repository.execute_repository(
                self.root, "example", frozen, run, run / "unused-plugin",
                "synthetic", "high", 15, "baseline")
        self.assertEqual(result["execution_status"], "PASS", result)
        self.assertIn(b"ignored.txt", (run / "candidate.patch").read_bytes())
        self.assertNotIn(b"candidate changed Git", (run / "candidate.patch").read_bytes())
        self.assertEqual(result["candidate_cli"]["image_id"], self.image)
        for artifact in result["artifacts"]:
            self.assertEqual(evaluator.digest(run / artifact["path"]), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
