from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import native_workflow
import skill_eval
import test_skill_eval


def state_profile():
    return {
        "schema_version": 1, "profile": "p01-scheduled-audit",
        "provenance": "synthetic-calibration",
        "goal": {"id": 7, "objective": "Synthetic first audit", "status": "active"},
        "mode": "autopilot", "model": "fixture-model", "effort": "medium",
        "todos": [{"id": "a", "title": "Read state", "description": "", "status": "pending"},
                  {"id": "b", "title": "Report state", "description": "", "status": "blocked"}],
        "dependencies": [],
        "schedules": [{"id": 42, "interval": "4h", "prompt": "Synthetic wake", "status": "active"}],
        "unknowns": ["Descriptions/dependencies/full database are unknown; empty values are execution defaults"],
    }


class NativeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "corpus"
        skill_eval.init_corpus(self.root)
        self.case = test_skill_eval.SkillEvalTests.make_case(self)
        self.definition = skill_eval.read_json(self.case / "case.json")
        self.definition["phases"] = self.definition["phases"][:1]
        self.phase = self.definition["phases"][0]
        self.packet = self.case / self.phase["evidence_dir"]
        self.source_id = str(uuid.uuid4())
        self.phase["session_restore"] = {
            "history_file": "history.jsonl", "source_session_id": self.source_id,
            "cutoff_event_id": str(uuid.uuid4()), "skill_context": "recorded-target-context",
            "limitations": ["Synthetic context calibration"],
            "personal_instructions_file": "personal.md",
        }
        self.phase["native_workflow"] = {
            "profile": "p01-scheduled-audit", "state_file": "state.json",
            "coordinates_file": "coordinates.json",
        }
        skill_eval.write_json(self.packet / "state.json", state_profile())
        self.coordinates = {"evidence_paths": ["product.md"], "limitations": ["Offline synthetic environment"]}
        skill_eval.write_json(self.packet / "coordinates.json", self.coordinates)
        (self.packet / "personal.md").write_text("Synthetic personal instructions.\n")
        (self.packet / "history.jsonl").write_text(
            json.dumps({"type": "session", "version": 1, "externalId": self.source_id}) + "\n"
            + json.dumps({"type": "message", "id": "old-skill", "role": "user", "content": [
                {"type": "text", "text": '<skill-context name="example-skill">Recorded old skill.</skill-context>'}
            ]}) + "\n")
        self.original = b"Original wording {NATIVE_GOAL_PATH}\r\nDo not correct me.\r\n"
        (self.case / self.phase["prompt_file"]).write_bytes(self.original)
        skill_eval.write_json(self.case / "case.json", self.definition)
        self.sdk = self.base / "sdk" / "index.js"
        self.sdk.parent.mkdir()
        self.sdk.write_text("Diagnostic SDK path only; never executed.\n")
        self.cli = self.base / "copilot"
        self.cli.write_text("#!/usr/bin/env python3\nprint('fixture-cli')\n")
        self.cli.chmod(0o755)
        self.plugin = self.base / "plugin"
        (self.plugin / "skills/example-skill").mkdir(parents=True)
        (self.plugin / "skills/example-skill/SKILL.md").write_text(
            "---\nname: example-skill\ndescription: Synthetic skill.\n---\nInspect evidence.\n")
        self.imported = str(uuid.uuid4())
        self.operations = []
        self.candidate_error = None
        self.observation_error = None
        self.cleanup_error = None

    def tearDown(self):
        self.temp.cleanup()

    def freeze(self):
        skill_eval.freeze_case(self.root, "example-case", replace=False)

    def test_continuation_skill_char_budget_validation_binding_and_receipt(self):
        package = self.base / "input"
        (package / "evaluator").mkdir(parents=True)
        (package / "evaluator" / "generic.py").write_text("pass\n")
        home = self.base / "home"
        home.mkdir()
        (home / "copilot-instructions.md").write_text("Synthetic instructions\n")
        cwd = self.base / "run" / "cwd"
        cwd.mkdir(parents=True)
        path = self.base / "continuation.json"
        value = {
            "schema_version": 1, "purpose": "setup-canary", "running_in_interactive_mode": True,
            "session_capabilities": native_workflow.CLI_CONTINUATION_CAPABILITIES,
            "cli_preamble": native_workflow.CLI_CONTINUATION_PREAMBLE,
            "executable_path": "/usr/bin:/bin", "locale": "C.UTF-8", "timeout_ms": 10000,
            "package_root": str(package), "workflow_commit": "a" * 40, "workflow_sha256": "b" * 64,
            "canary_receipt": None,
            "canary_checks": {"file": {"path": "result.txt", "sha256": "c" * 64},
                              "shell": {"command": "printf synthetic"},
                              "sql": {"query": "SELECT 7"}},
        }
        config = {"cwd": str(cwd), "home": str(home), "plugin_path": str(self.plugin),
                  "cli": str(self.cli), "sdk": str(self.sdk), "model": "fixture-model", "effort": "medium"}

        def entry():
            path.write_text(json.dumps(value))
            path.chmod(0o600)
            return native_workflow.continuation_entry(path, config)

        with mock.patch.dict("os.environ", {"GITHUB_WORKSPACE": "", "GITHUB_WORKFLOW_SHA": ""}):
            omitted = entry()
            self.assertNotIn("skill_char_budget", omitted)
            self.assertEqual(omitted["binding"]["interactive"], {
                key: value[key] for key in ("running_in_interactive_mode", "session_capabilities",
                                           "cli_preamble", "executable_path", "locale", "timeout_ms")})
            for timeout_ms, watchdog in ((10000, 360), (300000, 360), (600000, 660)):
                with self.subTest(timeout_ms=timeout_ms):
                    value["timeout_ms"] = timeout_ms
                    selected = entry()
                    if timeout_ms != omitted["timeout_ms"]:
                        self.assertNotEqual(selected["configuration_sha256"], omitted["configuration_sha256"])
                    with mock.patch("skill_eval.subprocess.run",
                                    side_effect=subprocess.TimeoutExpired("node", watchdog)) as run:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            skill_eval._native_workflow_probe("candidate", {
                                **config, "continuation_file": str(path),
                                "output": str(self.base / "candidate.json"),
                            })
                    self.assertEqual(run.call_args.kwargs["timeout"], watchdog)
            for operation, watchdog in (("setup", 390), ("observe", 360), ("cleanup", 360)):
                with self.subTest(operation=operation):
                    with mock.patch("skill_eval.subprocess.run",
                                    side_effect=subprocess.TimeoutExpired("node", watchdog)) as run:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            skill_eval._native_workflow_probe(operation, {
                                **config, "continuation_file": str(path),
                                "output": str(self.base / f"{operation}.json"),
                            })
                    self.assertEqual(run.call_args.kwargs["timeout"], watchdog)
            value["timeout_ms"] = 600001
            with self.assertRaisesRegex(ValueError, "interactive continuation configuration"):
                entry()
            value["timeout_ms"] = omitted["timeout_ms"]
            hashes = {omitted["configuration_sha256"]}
            for budget in (1, 15000, 50000, 4294967295):
                with self.subTest(budget=budget):
                    value["skill_char_budget"] = budget
                    selected = entry()
                    self.assertEqual(selected["skill_char_budget"], budget)
                    expected = copy.deepcopy(omitted["binding"])
                    expected["interactive"]["skill_char_budget"] = budget
                    self.assertEqual(selected["binding"], expected)
                    self.assertNotIn(selected["configuration_sha256"], hashes)
                    hashes.add(selected["configuration_sha256"])
            for budget in (True, False, 0, -1, 1.0, 1.5, "50000", None, [], {}, 4294967296):
                with self.subTest(invalid=budget):
                    value["skill_char_budget"] = budget
                    with self.assertRaisesRegex(ValueError, "skill_char_budget"):
                        entry()
            value["skill_char_budget"] = 50000
            canary = entry()
            value.update(purpose="historical", canary_checks=None, canary_receipt={
                "status": "CONTINUATION_CANARY_OBSERVED",
                "configuration_sha256": canary["configuration_sha256"],
                "interactive_identity": True, "operation_witnesses": True,
                "exactly_once": True, "shutdown_errors": [],
            })
            self.assertEqual(entry()["configuration_sha256"], canary["configuration_sha256"])
            value["skill_char_budget"] = 15000
            with self.assertRaisesRegex(ValueError, "canary receipt"):
                entry()
            del value["skill_char_budget"]
            with self.assertRaisesRegex(ValueError, "canary receipt"):
                entry()
            value.update(purpose="setup-canary", canary_receipt=None,
                         canary_checks=omitted["canary_checks"])
            self.assertEqual(entry()["configuration_sha256"], omitted["configuration_sha256"])
            value["unexpected"] = 1
            with self.assertRaisesRegex(ValueError, "requires exactly"):
                entry()
            del value["unexpected"]
            del value["timeout_ms"]
            with self.assertRaisesRegex(ValueError, "requires exactly"):
                entry()

    def test_schema_and_owner_inputs_refuse_authority_paths_and_missing_restoration(self):
        native_workflow.validate_native_workflow(self.definition, self.case)
        for field in ("query", "code", "runtime", "home", "session_id", "grant"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                native_workflow.validate_state({**state_profile(), field: "unsupported"})
        for change in ({"state_file": "../state.json"}, {"coordinates_file": "/outside"},
                       {"profile": "other"}, {"state_file": "product.md"}, {"code": "execute"}):
            changed = copy.deepcopy(self.definition)
            changed["phases"][0]["native_workflow"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                native_workflow.validate_native_workflow(changed, self.case)
        changed = copy.deepcopy(self.definition)
        del changed["phases"][0]["session_restore"]
        with self.assertRaises(ValueError):
            native_workflow.validate_native_workflow(changed, self.case)
        (self.packet / "coordinates.json").write_text(
            '{"evidence_paths":["product.md"],"limitations":[],"limitations":[]}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            native_workflow.phase_inputs(self.phase, self.packet)

    def test_coordinate_rendering_preserves_original_bytes_and_does_not_substitute_user_words(self):
        goal = self.base / "owned-goal.json"
        rendered = native_workflow.render_coordinates(self.original, self.coordinates, self.packet, goal)
        self.assertTrue(rendered.startswith(self.original))
        self.assertIn(b"{NATIVE_GOAL_PATH}", rendered)
        self.assertIn(b"Evaluation execution coordinates and limitations:", rendered)
        self.assertIn(str(goal).encode(), rendered)
        self.assertNotIn(b"recover", rendered)

    def test_optional_permissions_are_validated_and_reach_the_sdk_and_event_consumers(self):
        permissions = {"write_paths": ["target.txt"], "shell_commands": ["python3 -I check.py"]}
        self.phase["native_workflow"]["candidate_permissions"] = permissions
        (self.packet / "target.txt").write_text("pending\n")
        (self.packet / "check.py").write_text("print('Fixture checker')\n")
        self.coordinates["evidence_paths"].extend(["target.txt", "check.py"])
        skill_eval.write_json(self.packet / "coordinates.json", self.coordinates)
        skill_eval.write_json(self.case / "case.json", self.definition)
        self.expected_permissions = permissions
        self.freeze()
        result = self.run_native()
        calls = skill_eval.read_json(result / f"{self.phase['id']}-native-owner" / "actual-candidate-calls.json")
        self.assertEqual([item["start"]["toolName"] for item in calls["calls"]], ["view", "apply_patch", "bash"])
        phase_result = skill_eval.read_json(result / f"{self.phase['id']}-native-owner" / "phase-result.json")
        self.assertEqual(phase_result["status"], "NATIVE_EXECUTION_OBSERVED")

    def test_invalid_optional_permissions_are_rejected_before_freezing_or_sdk_invocation(self):
        for permissions in [
            None, {}, {"write_paths": ["../outside"], "shell_commands": []},
            {"write_paths": ["*.txt"], "shell_commands": []},
            {"write_paths": [], "shell_commands": ["copilot '--yolo'"]},
            {"write_paths": [], "shell_commands": ["python3 '"]},
            {"write_paths": [], "shell_commands": ["python3 -I check.py"], "grant": True},
        ]:
            with self.subTest(permissions=permissions):
                self.phase["native_workflow"]["candidate_permissions"] = permissions
                with self.assertRaises(ValueError):
                    native_workflow.phase_inputs(self.phase, self.packet)
        self.assertEqual(self.operations, [])

    def test_freeze_verification_checks_profile_and_preserves_recorded_skill_history(self):
        self.freeze()
        frozen = skill_eval.frozen_case_path(self.root, "example-case")
        skill_eval.verify_case(self.root, "example-case")
        self.assertIn("Recorded old skill", (frozen / self.phase["id"] / "history.jsonl").read_text())
        (frozen / self.phase["id"] / "state.json").write_text("{}")
        with self.assertRaises(ValueError):
            skill_eval.verify_case(self.root, "example-case")

    def _import(self, restoration, history, **kwargs):
        cwd = Path(kwargs["workdir"])
        self.assertNotEqual(self.imported, restoration["source_session_id"])
        self.assertIn("Recorded old skill", history.read_text())
        for name in ("history.jsonl", "personal.md", "state.json", "coordinates.json",
                     "alias-state.json", "alias-personal.md"):
            self.assertFalse((cwd / name).exists(), name)
        home = Path(kwargs["receipt_path"]).parent / "candidate-home"
        (home / "session-state" / self.imported).mkdir(parents=True)
        (home / "session-state" / self.imported / "events.jsonl").write_text(
            json.dumps({"id": "imported-user", "type": "user.message",
                        "data": {"content": "Recorded old skill"}}) + "\n")
        return self.imported

    def _discover(self, **kwargs):
        path = kwargs["prefix"].with_suffix(".json")
        skill_eval.write_json(path, {"diagnostic": True})
        return path

    def _probe(self, operation, config):
        self.operations.append(operation)
        goal = Path(config["home"]) / "session-state" / config["session_id"] / "autopilot-objective.json"
        source = skill_eval.read_json(Path(config["state_file"]))
        if operation == "setup":
            goal.write_text(json.dumps({"version": 1, "nextId": 8, "current": source["goal"]}))
            result = {"status": "SETUP_OBSERVED", "source_projection": source,
                      "schedule_mapping": [{"source_id": 42, "native_id": 1}]}
        elif operation == "cleanup":
            if self.cleanup_error:
                raise ValueError(self.cleanup_error)
            result = {"status": "CLEANED", "cleanup": {
                "todos": {"rows": []}, "schedules": {"entries": []}, "dependencies_empty": True}}
        else:
            if self.observation_error:
                raise ValueError(self.observation_error)
            result = {"status": "OBSERVED", "goal_path": str(goal)}
        skill_eval.write_json(Path(config["output"]), result)
        return result

    def _candidate(self, config, *, cli_version, preflight_only=False):
        self.assertEqual(config["model"], "fixture-model")
        self.assertEqual(config["effort"], "medium")
        if hasattr(self, "expected_permissions"):
            self.assertEqual(config["candidate_permissions"], self.expected_permissions)
        else:
            self.assertNotIn("candidate_permissions", config)
        self.assertEqual(Path(config["state_file"]).stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(config["state_file"]).with_name("coordinates.json").stat().st_mode & 0o777, 0o600)
        for name in ("home", "os_home"):
            self.assertEqual(Path(config[name]).stat().st_mode & 0o777, 0o700)
        prompt = Path(config["prompt_path"]).read_bytes()
        self.assertTrue(prompt.startswith(self.original))
        self.assertIn(b"Schedule coordinate: source #42 -> owned #1", prompt)
        if self.candidate_error:
            raise ValueError(self.candidate_error)
        goal = Path(config["home"]) / "session-state" / config["session_id"] / "autopilot-objective.json"
        events = [
            {"type": "tool.execution_start", "data": {"toolName": "view", "toolCallId": "owner",
                                                      "arguments": {"path": str(goal)}}},
            {"type": "tool.execution_complete", "data": {"toolCallId": "owner", "success": True}},
        ]
        answer = {"type": "assistant.message", "id": "answer", "data": {
            "content": "Actual synthetic diagnostic answer.", "originatingMessageId": "sent"}}
        idle = {"type": "session.idle", "id": "idle", "data": {"aborted": False}}
        if not preflight_only:
            events.extend([
                {"type": "assistant.turn_start", "data": {"model": config["model"]}},
                {"type": "tool.execution_start", "data": {"toolName": "view", "toolCallId": "candidate",
                                                          "arguments": {"path": str(goal)}}},
                {"type": "tool.execution_complete", "data": {"toolCallId": "candidate", "success": True}},
                answer, idle,
            ])
            for tool_name in ("apply_patch", "bash") if hasattr(self, "expected_permissions") else ():
                events[-2:-2] = [
                    {"type": "tool.execution_start", "data": {
                        "toolName": tool_name, "toolCallId": tool_name, "arguments": {}}},
                    {"type": "tool.execution_complete", "data": {"toolCallId": tool_name, "success": True}},
                ]
        Path(config["event_log"]).write_text("".join(json.dumps(event) + "\n" for event in events))
        result = {
            "status": "PREFLIGHT_OBSERVED" if preflight_only else "CANDIDATE_OBSERVED",
            "profile": config["profile"], "source_projection": state_profile(),
            "model_configuration": {"modelId": config["model"], "reasoningEffort": config["effort"]},
            "session_id": config["session_id"], "model_send_calls": 0 if preflight_only else 1,
            "firsterror": None, "shutdown_errors": [], "model_message_id": "sent",
            "preflight": [{"tool_call_id": "owner"}],
        }
        if not preflight_only:
            result.update(model_result=answer, model_completion_event=idle)
        skill_eval.write_json(Path(config["output"]), result)
        return result

    def run_native(self, *, preflight=False):
        with ExitStack() as stack:
            stack.enter_context(mock.patch("session_restore.import_session", side_effect=self._import))
            stack.enter_context(mock.patch("skill_eval.discover_personal_instructions", side_effect=self._discover))
            stack.enter_context(mock.patch("skill_eval._native_workflow_probe", side_effect=self._probe))
            stack.enter_context(mock.patch("skill_eval._run_native_candidate", side_effect=self._candidate))
            ordinary = stack.enter_context(mock.patch("skill_eval.run_copilot"))
            judges = stack.enter_context(mock.patch("skill_eval.run_judges", return_value=[
                {"model": "judge-a", "verdict": "PASS"}, {"model": "judge-b", "verdict": "PASS"}]))
            result = skill_eval.run_case(
                self.root, "example-case", self.plugin, self.cli, "fixture-model", "medium", "isolated", 60,
                native_workflow_sdk=self.sdk, native_preflight_only=preflight)
            ordinary.assert_not_called()
            if preflight:
                judges.assert_not_called()
            else:
                judges.assert_called_once()
            return result

    def test_native_phase_reuses_restore_receipts_outputs_and_normal_judges_with_owner_exclusion(self):
        (self.packet / "alias-state.json").write_bytes((self.packet / "state.json").read_bytes())
        (self.packet / "alias-personal.md").write_bytes((self.packet / "personal.md").read_bytes())
        self.freeze()
        result = self.run_native()
        receipt = skill_eval.read_json(result / f"{self.phase['id']}-receipt.json")
        self.assertEqual(receipt["observed_models"], ["fixture-model"])
        self.assertEqual(receipt["effort"], "medium")
        self.assertFalse(receipt["skill_invoked"])
        owner = result / f"{self.phase['id']}-native-owner"
        calls = skill_eval.read_json(owner / "actual-candidate-calls.json")
        self.assertEqual([call["start"]["toolCallId"] for call in calls["calls"]], ["candidate"])
        self.assertEqual(self.operations, ["setup", "observe", "cleanup"])
        self.assertIn("Actual synthetic", (result / f"{self.phase['id']}-output.md").read_text())

    def test_preparation_only_has_no_answer_output_receipt_or_judges(self):
        self.freeze()
        result = self.run_native(preflight=True)
        prepared = skill_eval.read_json(result / "preparation-result.json")
        self.assertEqual(prepared["status"], "PREPARATION_ONLY")
        self.assertEqual(prepared["model_send_calls"], 0)
        self.assertEqual(prepared["judge_calls"], 0)
        self.assertFalse((result / f"{self.phase['id']}-output.md").exists())
        self.assertFalse((result / f"{self.phase['id']}-receipt.json").exists())
        self.assertEqual(skill_eval.result_from_run(result), "PREPARATION_ONLY")
        self.assertEqual(self.operations, ["setup", "observe", "cleanup"])

    def test_model_mismatch_and_missing_sdk_refuse_before_import_or_any_execution(self):
        self.freeze()
        with mock.patch("session_restore.import_session") as imported, mock.patch("skill_eval.run_copilot") as model:
            for sdk, requested_model, effort in ((self.sdk, "wrong", "medium"),
                                                (self.sdk, "fixture-model", "high"),
                                                (None, "fixture-model", "medium")):
                with self.subTest(sdk=sdk, model=requested_model, effort=effort), self.assertRaises(ValueError):
                    skill_eval.run_case(
                        self.root, "example-case", self.plugin, self.cli, requested_model, effort, "isolated", 60,
                        native_workflow_sdk=sdk)
            imported.assert_not_called()
            model.assert_not_called()
        ordinary = {"phases": [{"id": "ordinary"}]}
        with self.assertRaisesRegex(ValueError, "preflight"):
            skill_eval._validate_native_selection(ordinary, self.base, self.sdk, "fixture", "high", "isolated", True)

    def test_candidate_error_cleans_owned_profile_and_preserves_first_error_over_cleanup(self):
        self.freeze()
        self.candidate_error = "first candidate error"
        self.observation_error = "second observation error"
        self.cleanup_error = "second cleanup error"
        with self.assertRaisesRegex(ValueError, "first candidate error"):
            self.run_native()
        owner = next((self.root / "runs").glob("*/example-case/*-native-owner"))
        result = skill_eval.read_json(owner / "phase-result.json")
        self.assertEqual(result["firsterror"], "first candidate error")
        self.assertEqual(result["observation_error"], "second observation error")
        self.assertEqual(result["cleanup_error"], "second cleanup error")
        self.assertEqual(self.operations, ["setup", "observe", "cleanup"])

    def test_observation_error_still_cleans_and_cannot_be_reported_as_success(self):
        self.freeze()
        self.observation_error = "cold observation error"
        with self.assertRaisesRegex(ValueError, "cold observation error"):
            self.run_native()
        owner = next((self.root / "runs").glob("*/example-case/*-native-owner"))
        result = skill_eval.read_json(owner / "phase-result.json")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["firsterror"], "cold observation error")
        self.assertEqual(result["observation_error"], "cold observation error")
        self.assertEqual(result["cleanup_error"], None)
        self.assertEqual(self.operations, ["setup", "observe", "cleanup"])

    def test_interrupted_owned_setup_preserves_first_error_and_cleans_with_empty_receipt(self):
        self.freeze()
        original_probe = self._probe
        first = subprocess.TimeoutExpired(["node", "setup"], 300)

        def interrupted(operation, config):
            if operation != "setup":
                return original_probe(operation, config)
            self.operations.append(operation)
            namespace = Path(config["home"]) / "session-state" / config["session_id"]
            (namespace / "native-profile-mapping.json").write_text("[]")
            Path(config["output"]).write_text("")
            raise first

        with mock.patch.object(self, "_probe", side_effect=interrupted):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                self.run_native()
        self.assertIs(caught.exception, first)
        owner = next((self.root / "runs").glob("*/example-case/*-native-owner"))
        result = skill_eval.read_json(owner / "phase-result.json")
        self.assertEqual(result["firsterror"], str(first))
        self.assertEqual(result["cleanup_error"], None)
        self.assertEqual(self.operations, ["setup", "cleanup"])

    def test_interrupted_candidate_receipt_does_not_skip_owned_cleanup(self):
        self.freeze()
        first = subprocess.TimeoutExpired(["node", "candidate"], 360)

        def interrupted(config, **kwargs):
            Path(config["output"]).write_text("")
            raise first

        with mock.patch.object(self, "_candidate", side_effect=interrupted):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                self.run_native()
        self.assertIs(caught.exception, first)
        owner = next((self.root / "runs").glob("*/example-case/*-native-owner"))
        result = skill_eval.read_json(owner / "phase-result.json")
        self.assertEqual(result["firsterror"], str(first))
        self.assertEqual(self.operations, ["setup", "observe", "cleanup"])

    def test_source_measurement_uses_descriptor_and_existing_role_aggregation(self):
        events = self.base / "session-state" / self.imported / "events.jsonl"
        events.parent.mkdir(parents=True)
        events.write_text("")
        config = {
            "home": str(self.base), "session_id": self.imported,
            "output": str(self.base / "audit-native-owner/candidate.json"), "profile": "p01-scheduled-audit",
            "model": "fixture-model", "effort": "medium",
            "prompt_path": str(self.base / "audit-prompt.md"), "event_log": str(self.base / "audit-raw.jsonl"),
        }

        def candidate(operation, config):
            events.write_text(json.dumps({"type": "session.shutdown", "data": {
                "totalNanoAiu": 3_250_000_000, "totalPremiumRequests": 1,
            }}) + "\n")
            return {"status": "CANDIDATE_OBSERVED"}

        with mock.patch("skill_eval._native_workflow_probe", side_effect=candidate):
            skill_eval._run_native_candidate(config, cli_version="fixture")
        records = [skill_eval.read_json(path) for path in (self.base / "measurements").glob("*.json")]
        accounting = skill_eval.measurement.accounting(records)
        self.assertEqual(accounting["candidate"]["sessions"], 1)
        self.assertEqual(accounting["candidate"]["credits"], 3.25)
        self.assertEqual(accounting["candidate"]["premium_requests"], 1)
        self.assertTrue(accounting["candidate"]["complete"])
        self.assertEqual(records[0]["requested_model"], "fixture-model")
        self.assertEqual(records[0]["effort"], "medium")

    def test_run_suite_forwards_preflight_and_retains_typed_not_behavioral_result(self):
        self.freeze()
        with mock.patch("skill_eval.run_case") as run:
            result = self.base / "corpus" / "runs" / "diagnostic"
            result.mkdir(parents=True)
            skill_eval.write_json(result / "preparation-result.json", {
                "status": "PREPARATION_ONLY", "model_send_calls": 0, "judge_calls": 0})
            run.return_value = result
            suite, complete = skill_eval.run_suite(
                self.root, self.plugin, self.cli, "fixture-model", "medium", "isolated", 60, workers=1,
                native_workflow_sdk=self.sdk, native_preflight_only=True)
        self.assertTrue(complete)
        self.assertEqual(run.call_args.kwargs["native_workflow_sdk"], self.sdk)
        self.assertTrue(run.call_args.kwargs["native_preflight_only"])
        self.assertEqual(skill_eval.read_json(suite / "suite-result.json")["result"], "PREPARATION_ONLY")

    def test_cli_native_flags_are_optional_on_both_existing_commands(self):
        for command, positional in (("run", ["--case", "example-case"]), ("run-suite", [])):
            args = [command, str(self.root), *positional, "--plugin-dir", str(self.plugin)]
            ordinary = skill_eval.parser().parse_args(args)
            self.assertIsNone(ordinary.native_workflow_sdk)
            self.assertFalse(ordinary.native_preflight_only)
            selected = skill_eval.parser().parse_args(args + [
                "--native-workflow-sdk", str(self.sdk), "--native-preflight-only"])
            self.assertEqual(selected.native_workflow_sdk, self.sdk)
            self.assertTrue(selected.native_preflight_only)

    def test_native_parser_requires_descriptor_effort_and_excludes_all_owner_calls(self):
        cwd = self.base / "workdir"
        cwd.mkdir()
        home = self.base / "candidate-home"
        goal = home / "session-state" / self.imported / "autopilot-objective.json"
        goal.parent.mkdir(parents=True)
        goal.write_text("{}")
        home.chmod(0o700)
        os_home = self.base / "candidate-os-home"
        os_home.mkdir(mode=0o700)
        (self.packet / "state.json").chmod(0o600)
        (self.packet / "coordinates.json").chmod(0o600)
        config = {
            "home": str(home), "session_id": self.imported, "output": str(self.base / "candidate.json"),
            "os_home": str(os_home),
            "profile": "p01-scheduled-audit", "state_file": str(self.packet / "state.json"),
            "model": "fixture-model", "effort": "medium",
            "prompt_path": str(self.base / "prompt.md"), "event_log": str(self.base / "raw.jsonl"),
        }
        (self.base / "prompt.md").write_bytes(native_workflow.render_coordinates(
            self.original, self.coordinates, cwd, goal, [{"source_id": 42, "native_id": 1}]))
        receipt = self._candidate(config, cli_version="fixture")
        receipt["owner_tool_call_ids"] = ["candidate"]
        parsed = skill_eval.parse_run(
            Path(config["event_log"]), skill="example-skill", expected_model="fixture-model",
            cwd=cwd, require_skill=None, native_workflow_goal=goal,
            native_sdk_completion=receipt, expected_effort="medium")
        self.assertEqual(parsed["tool_calls"], 0)
        self.assertEqual(parsed["owned_native_reads"], [])
        with self.assertRaisesRegex(ValueError, "model/effort"):
            skill_eval.parse_run(
                Path(config["event_log"]), skill="example-skill", expected_model="fixture-model",
                cwd=cwd, require_skill=None, native_workflow_goal=goal,
                native_sdk_completion=receipt, expected_effort="high")

if __name__ == "__main__":
    unittest.main()
