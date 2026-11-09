#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock
import measurement
import skill_eval

from skill_eval import (
    add_case,
    compatibility_result,
    digest,
    directory_identity,
    freeze_case,
    frozen_case_path,
    init_corpus,
    parse_native_run,
    load_treatment,
    parse_run,
    run_case,
    run_copilot,
    run_suite,
    require_treatment_admission,
    treatment_admission_binding,
    validate_judgment,
    verify_case,
)


class CopilotInvocationTests(unittest.TestCase):
    def test_native_grants_are_exact_owned_and_default_is_unchanged(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            session_id = str(uuid.uuid4())
            home = root / "candidate-home"
            goal = home / "session-state" / session_id / "autopilot-objective.json"
            goal.parent.mkdir(parents=True)
            goal.write_text("{}")
            arguments = dict(
                copilot=root / "copilot", plugin_dir=root / "plugin", cwd=root,
                prompt="synthetic", model="fixture", effort="high", log=root / "raw.jsonl",
                session_id=session_id, resume=True, home_mode="isolated", run_home=home,
                timeout_seconds=300, allow_skill=True)
            with (
                mock.patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "synthetic"}),
                mock.patch("skill_eval.measurement.collect"),
                mock.patch("skill_eval.subprocess.run", return_value=subprocess.CompletedProcess(
                    [], 0, stdout="")) as execute,
            ):
                default = run_copilot(**arguments)
                explicit_default = run_copilot(**arguments, native_diagnostic_goal=None)
                self.assertEqual(default, explicit_default)
                native = run_copilot(**arguments, native_diagnostic_goal=goal)
                self.assertNotIn("--experimental", native)
                self.assertEqual(
                    [flag for flag in native if flag.startswith("--allow-tool=")],
                    ["--allow-tool=skill,sql,manage_schedule",
                     f"--allow-tool=view({root}/**)", f"--allow-tool=view({goal})"])
                self.assertIn("--available-tools=skill,view,sql,manage_schedule", native)
                self.assertEqual(
                    [flag for flag in default if not flag.startswith(("--allow-tool=", "--available-tools="))],
                    [flag for flag in native if not flag.startswith(("--allow-tool=", "--available-tools="))])
                for invalid in (root / "foreign.json", goal.parent / "alias.json"):
                    invalid.write_text("{}") if invalid.name == "foreign.json" else invalid.symlink_to(goal)
                    execute.reset_mock()
                    with self.assertRaises(ValueError):
                        run_copilot(**arguments, native_diagnostic_goal=invalid)
                    execute.assert_not_called()

    def test_personal_instruction_mode_changes_only_instruction_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for enabled in (False, True):
                with (
                    self.subTest(enabled=enabled),
                    mock.patch.dict(os.environ, {
                        "COPILOT_GITHUB_TOKEN": "synthetic-token",
                        "COPILOT_CUSTOM_INSTRUCTIONS_DIRS": "/synthetic/ambient",
                    }),
                    mock.patch("skill_eval.subprocess.run", return_value=subprocess.CompletedProcess(
                        [], 0, stdout="fixture\n")) as execute,
                    mock.patch("skill_eval.measurement.collect"),
                ):
                    run_copilot(
                        copilot=root / "copilot", plugin_dir=root / "plugin", cwd=root,
                        prompt="synthetic prompt", model="fixture-model", effort="high",
                        log=root / "raw.jsonl", session_id=str(uuid.uuid4()), resume=False,
                        home_mode="isolated", run_home=root / "candidate-home",
                        timeout_seconds=10, allow_skill=True, personal_instructions=enabled,
                    )
                    command = execute.call_args.args[0]
                    env = execute.call_args.kwargs["env"]
                    self.assertEqual("--no-custom-instructions" in command, not enabled)
                    self.assertIn("--available-tools=skill,view", command)
                    self.assertIn("--allow-tool=skill,view", command)
                    self.assertIn("--disable-builtin-mcps", command)
                    if enabled:
                        self.assertNotIn("COPILOT_CUSTOM_INSTRUCTIONS_DIRS", env)
                        self.assertEqual(Path(env["HOME"]).parent, root)
                        self.assertNotEqual(env["HOME"], env["COPILOT_HOME"])
                        self.assertEqual(list(Path(env["HOME"]).iterdir()), [])
                    else:
                        self.assertEqual(env["COPILOT_CUSTOM_INSTRUCTIONS_DIRS"], "/synthetic/ambient")

    def test_fresh_and_resumed_prompts_do_not_wait_for_parent_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copilot = root / "copilot"
            copilot.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print('EOF' if sys.stdin.read() == '' else 'UNEXPECTED INPUT', flush=True)\n"
            )
            copilot.chmod(0o755)
            read_fd, write_fd = os.pipe()
            original_run = subprocess.run

            def run_with_open_parent_input(command, **kwargs):
                self.assertNotIn("--no-remote", command)
                self.assertIn("--no-custom-instructions", command)
                self.assertIn("--available-tools=view", command)
                kwargs.setdefault("stdin", read_fd)
                return original_run(command, **kwargs)

            try:
                os.write(write_fd, b"unrelated parent input\n")
                for resume in (False, True):
                    with (
                        self.subTest(resume=resume),
                        mock.patch("skill_eval.subprocess.run", side_effect=run_with_open_parent_input),
                        mock.patch("skill_eval.measurement.collect") as collect,
                    ):
                        log = root / f"output-{resume}.jsonl"
                        run_copilot(
                            copilot=copilot, plugin_dir=root, cwd=root,
                            prompt="public prompt", model="test-model", effort="high",
                            log=log, session_id=str(uuid.uuid4()), resume=resume,
                            home_mode="existing", run_home=root / "unused-home",
                            timeout_seconds=10, allow_skill=False,
                        )
                        self.assertEqual(log.read_text(), "EOF\n")
                        self.assertEqual(collect.call_args.kwargs["outcome"], "completed")
            finally:
                os.close(read_fd)
                os.close(write_fd)


class NativeWorkflowDiagnosticTests(unittest.TestCase):
    def test_recovery_checks_do_not_require_a_model_side_denial(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            log = root / "raw.jsonl"
            operations = [
                ("sql", {"query": "UPDATE todos SET status='done' WHERE id='native-workflow-fixture'"}),
                ("manage_schedule", {"action": "list"}),
                ("manage_schedule", {"action": "stop", "id": 1}),
                ("manage_schedule", {"action": "list"}),
            ]
            for omitted in (None, 0, 2):
                events = []
                for index, (name, arguments) in enumerate(operations):
                    if index == omitted:
                        continue
                    events.extend([
                        {"type": "tool.execution_start", "data": {
                            "toolName": name, "toolCallId": str(index), "arguments": arguments}},
                        {"type": "tool.execution_complete", "data": {
                            "toolCallId": str(index), "success": True}},
                    ])
                log.write_text("".join(json.dumps(event) + "\n" for event in events))
                result = skill_eval._native_diagnostic_calls(log, root, root.parent / "sibling")
                self.assertEqual(all(result["checks"].values()), omitted is None)
                self.assertFalse(result["observations"]["denied_sibling"])
                owned = skill_eval._native_diagnostic_calls(
                    log, root, root.parent / "sibling", owner_call_ids={"0", "1", "2", "3"})
                self.assertFalse(owned["checks"]["native_sql_update"])
                self.assertFalse(owned["checks"]["schedule_list_stop_relist"])

    def test_schedule_relist_requires_each_prior_completion_before_next_start(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            log = root / "raw.jsonl"
            actions = [{"action": "list"}, {"action": "stop", "id": 1}, {"action": "list"}]
            sequences = [
                ([(0, True), (0, False), (1, True), (1, False), (2, True), (2, False)], True),
                ([(0, True), (1, True), (0, False), (1, False), (2, True), (2, False)], False),
                ([(0, True), (0, False), (1, True), (2, True), (1, False), (2, False)], False),
            ]
            for sequence, expected in sequences:
                with self.subTest(sequence=sequence):
                    events = [
                        {"type": "tool.execution_start" if start else "tool.execution_complete",
                         "data": {"toolName": "manage_schedule", "toolCallId": str(index),
                                  "arguments": actions[index]} if start else {
                                      "toolCallId": str(index), "success": True}}
                        for index, start in sequence
                    ]
                    log.write_text("".join(json.dumps(event) + "\n" for event in events))
                    result = skill_eval._native_diagnostic_calls(log, root, root / "sibling")
                    self.assertEqual(result["checks"]["schedule_list_stop_relist"], expected)
                    self.assertTrue(result["checks"]["all_calls_completed"])

    def test_native_candidate_wrapper_uses_real_prefix_and_measurement_capture(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            session_id = str(uuid.uuid4())
            home = root / "candidate-home"
            events = home / "session-state" / session_id / "events.jsonl"
            events.parent.mkdir(parents=True)
            prefix = json.dumps({"type": "user.message", "data": {"content": "Synthetic prior context"}}) + "\n"
            events.write_text(prefix)
            config = {
                "home": str(home), "session_id": session_id,
                "output": str(root / "candidate.json"),
            }
            blocked = {"status": "PREMODEL_BLOCKED", "model_send_calls": 0, "firsterror": "synthetic stop"}

            def candidate(operation, selected):
                self.assertEqual(operation, "candidate")
                self.assertEqual(selected, config)
                with events.open("a") as stream:
                    stream.write(json.dumps({"type": "session.shutdown", "data": {
                        "totalNanoAiu": 0, "totalPremiumRequests": 0, "modelMetrics": {}}}) + "\n")
                return blocked

            with mock.patch("skill_eval._native_workflow_probe", side_effect=candidate) as native:
                self.assertEqual(skill_eval._run_native_candidate(config, cli_version="fixture"), blocked)
                native.assert_called_once()
            record = json.loads((root / "candidate-raw.measurement.json").read_text())
            self.assertEqual(record["outcome"], "failed")
            self.assertEqual(record["errors"], [])
            self.assertEqual(record["credits"], 0)
            self.assertEqual(record["premium_requests"], 0)
            self.assertTrue(events.read_text().startswith(prefix))

    def test_sdk_parser_requires_owned_completion_and_actual_completed_turn(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            goal = root / "candidate-home/session-state" / str(uuid.uuid4()) / "autopilot-objective.json"
            goal.parent.mkdir(parents=True)
            goal.write_text("{}")
            log = root / "raw.jsonl"
            events = [
                {"id": "start", "type": "assistant.turn_start", "data": {"model": "fixture"}},
                {"id": "message", "type": "assistant.message",
                 "data": {"content": "answer", "originatingMessageId": "send"}},
                {"id": "idle", "type": "session.idle", "data": {"mode": "autopilot"}},
            ]
            completion = {
                "session_id": goal.parent.name, "status": "CANDIDATE_OBSERVED",
                "model_send_calls": 1, "firsterror": None, "shutdown_errors": [],
                "model_message_id": "send", "model_result": events[1],
                "model_completion_event": events[2],
            }
            arguments = dict(skill="unattended-run", expected_model="fixture", cwd=root,
                             require_skill=None, native_diagnostic_goal=goal)
            log.write_text("".join(json.dumps(event) + "\n" for event in events))
            with self.assertRaisesRegex(ValueError, "missing successful result"):
                parse_run(log, **arguments)
            parsed = parse_run(log, **arguments, native_sdk_completion=completion)
            self.assertEqual(parsed["answer"], "answer")
            self.assertEqual(parsed["result_source"], "sdk_session_idle")
            log.write_text("".join(json.dumps(event) + "\n" for event in
                                   [*events, {"type": "result", "exitCode": 0}]))
            with self.assertRaisesRegex(ValueError, "unexpected CLI result"):
                parse_run(log, **arguments, native_sdk_completion=completion)
            for incomplete in (
                events[1:], events[:-1], [events[1], events[0], events[2]],
                [events[2], events[0], events[1]],
                [events[0], events[1], {"id": "loop-idle", "type": "assistant.idle", "data": {}}],
            ):
                log.write_text("".join(json.dumps(event) + "\n" for event in incomplete))
                with self.assertRaisesRegex(ValueError, "missing completed SDK"):
                    parse_run(log, **arguments, native_sdk_completion=completion)
            log.write_text("".join(json.dumps(event) + "\n" for event in events))
            for delta in ({"status": "PREMODEL_BLOCKED"}, {"model_send_calls": 0},
                          {"session_id": str(uuid.uuid4())}, {"shutdown_errors": ["error"]},
                          {"model_message_id": "foreign"},
                          {"model_completion_event": {**events[2], "data": {"aborted": True}}}):
                with self.assertRaisesRegex(ValueError, "completed owned native"):
                    parse_run(log, **arguments, native_sdk_completion={**completion, **delta})
            altered = {**events[1], "data": {**events[1]["data"], "content": "altered"}}
            log.write_text("".join(json.dumps(event) + "\n" for event in [events[0], altered, events[2]]))
            with self.assertRaisesRegex(ValueError, "receipt differs"):
                parse_run(log, **arguments, native_sdk_completion=completion)
            child = {"id": "child", "type": "assistant.message", "agentId": "child-agent",
                     "data": {"content": "child answer", "model": "child-model"}}
            log.write_text("".join(json.dumps(event) + "\n" for event in [*events[:2], child, events[2]]))
            self.assertEqual(
                parse_run(log, **arguments, native_sdk_completion=completion)["answer"], "answer")
            error = {"id": "error", "type": "session.error", "data": {"message": "native error"}}
            log.write_text("".join(json.dumps(event) + "\n" for event in [*events, error]))
            with self.assertRaisesRegex(ValueError, "native SDK session error"):
                parse_run(log, **arguments, native_sdk_completion=completion)
            with self.assertRaisesRegex(ValueError, "completed owned native"):
                parse_run(log, **{**arguments, "native_diagnostic_goal": None},
                          native_sdk_completion=completion)

    def test_owner_preflight_reads_cannot_satisfy_candidate_actions(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            workdir = root / "workdir"
            workdir.mkdir()
            goal = root / "candidate-home/session-state" / str(uuid.uuid4()) / "autopilot-objective.json"
            goal.parent.mkdir(parents=True)
            goal.write_text("{}")
            sibling = root / "sibling"
            log = root / "raw.jsonl"

            def view(call_id, path, success):
                return [
                    {"type": "tool.execution_start", "data": {
                        "toolName": "view", "toolCallId": call_id, "arguments": {"path": str(path)}}},
                    {"type": "tool.execution_complete", "data": {
                        "toolCallId": call_id, "success": success}},
                ]

            message = {"id": "answer", "type": "assistant.message",
                       "data": {"content": "answer", "originatingMessageId": "send"}}
            idle = {"id": "idle", "type": "session.idle", "data": {"mode": "autopilot"}}
            start = {"id": "start", "type": "assistant.turn_start", "data": {"model": "fixture"}}
            owner_calls = {"owner-goal", "owner-sibling"}
            completion = {
                "session_id": goal.parent.name, "status": "CANDIDATE_OBSERVED",
                "model_send_calls": 1, "firsterror": None, "shutdown_errors": [],
                "model_message_id": "send", "model_result": message, "model_completion_event": idle,
                "preflight": [{"tool_call_id": call_id} for call_id in owner_calls],
            }
            owner_events = [*view("owner-goal", goal, True), *view("owner-sibling", sibling, False)]
            arguments = dict(skill="unattended-run", expected_model="fixture", cwd=workdir,
                             require_skill=None, native_diagnostic_goal=goal, native_sdk_completion=completion)
            for candidate_reads in (False, True):
                model_events = ([*view("model-goal", goal, True), *view("model-sibling", sibling, False)]
                                if candidate_reads else [])
                events = [*owner_events, start, *model_events, message, idle]
                log.write_text("".join(json.dumps(event) + "\n" for event in events))
                parsed = parse_run(log, **arguments)
                self.assertEqual(parsed["owned_native_reads"], [str(goal)] if candidate_reads else [])
                self.assertEqual(parsed["tool_calls"], 2 if candidate_reads else 0)
                calls = skill_eval._native_diagnostic_calls(
                    log, workdir, sibling, owner_call_ids=owner_calls)
                self.assertEqual(calls["observations"]["denied_sibling"], candidate_reads)

    def test_candidate_probe_preserves_blocked_receipt_and_rejects_false_completion(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            config = {
                "cli": str(root / "copilot"), "sdk": str(root / "index.js"),
                "home": str(root / "candidate-home"), "os_home": str(root / "candidate-os-home"),
                "cwd": str(root), "session_id": str(uuid.uuid4()), "output": str(root / "candidate.json"),
            }
            base = {
                "cli": config["cli"], "sdk": config["sdk"], "session_id": config["session_id"],
                "connection": {"path": config["cli"]}, "runtime_identity": {"version": "1.0.97-2"},
                "shutdown_errors": [], "status": "CANDIDATE_OBSERVED", "firsterror": None,
                "model_send_calls": 1,
                "checks": {key: True for key in ("effective_tools", "instruction_correspondence",
                          "cold_state", "permission_traversal", "prefix_preserved")},
            }
            cases = [
                ({}, 0, True),
                ({"status": "PREMODEL_BLOCKED", "model_send_calls": 0,
                  "firsterror": "permission traversal absent", "checks": {}}, 1, True),
                ({"status": "PREMODEL_BLOCKED"}, 1, False),
                ({"model_send_calls": 0}, 0, False),
                ({"checks": {}}, 0, False),
                ({}, 1, False),
            ]
            for index, (delta, returncode, accepted) in enumerate(cases):
                selected = {**config, "output": str(root / f"candidate-{index}.json")}
                receipt = {**base, **delta}

                def execute(command, **kwargs):
                    Path(selected["output"]).write_text(json.dumps(receipt))
                    return subprocess.CompletedProcess(command, returncode, stdout=b"", stderr=b"")

                with (
                    self.subTest(delta=delta, returncode=returncode),
                    mock.patch("skill_eval.subprocess.run", side_effect=execute),
                    mock.patch("skill_eval.personal_instruction_environment", return_value={}),
                ):
                    if accepted:
                        self.assertEqual(skill_eval._native_workflow_probe("candidate", selected), receipt)
                    else:
                        with self.assertRaises(ValueError):
                            skill_eval._native_workflow_probe("candidate", selected)

    def test_exact_goal_parser_exception_keeps_other_outside_reads_closed(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            cwd = root / "workdir"
            cwd.mkdir()
            goal = root / "candidate-home/session-state" / str(uuid.uuid4()) / "autopilot-objective.json"
            goal.parent.mkdir(parents=True)
            goal.write_text("{}")
            log = root / "raw.jsonl"

            def events(path, success):
                return [
                    {"type": "tool.execution_start", "data": {"toolName": "view",
                     "toolCallId": "view", "arguments": {"path": str(path)}}},
                    {"type": "tool.execution_complete", "data": {"toolCallId": "view", "success": success}},
                    {"type": "assistant.message", "data": {"model": "fixture", "content": "answer"}},
                    {"type": "result", "exitCode": 0},
                ]

            arguments = dict(skill="unattended-run", expected_model="fixture", cwd=cwd,
                             require_skill=None, native_diagnostic_goal=goal)
            log.write_text("".join(json.dumps(item) + "\n" for item in events(goal, True)))
            parsed = parse_run(log, **arguments)
            self.assertEqual(parsed["owned_native_reads"], [str(goal)])
            self.assertEqual(parsed["viewed_paths"], [])
            sibling = root / "sibling"
            log.write_text("".join(json.dumps(item) + "\n" for item in events(sibling, False)))
            self.assertEqual(parse_run(log, **arguments)["owned_native_reads"], [])
            log.write_text("".join(json.dumps(item) + "\n" for item in events(sibling, True)))
            with mock.patch("dashboard_cli.invalidate_on_boundary_violation") as invalidate:
                with self.assertRaisesRegex(ValueError, "escaped evaluation workdir"):
                    parse_run(log, **arguments)
                invalidate.assert_called_once_with(sibling)

    def test_fixed_driver_setup_failure_never_runs_candidate_or_judges_and_keeps_first_error(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            corpus = root / "corpus"
            init_corpus(corpus)
            case_id = "native-workflow-caller-diagnostic"
            add_case(corpus, case_id, "unattended-run", ["candidate"])
            case = corpus / "cases" / case_id
            definition = json.loads((case / "case.json").read_text())
            definition["authority_kind"] = "synthetic"
            definition["behavioral_claim"] = "Synthetic caller correspondence only."
            (case / "criteria.md").write_text("Not judged in the diagnostic.")
            (case / "judge-reference/fixture.md").write_text("Synthetic unused judge reference.")
            source = str(uuid.uuid4())
            definition["phases"][0]["session_restore"] = {
                "history_file": "history.jsonl", "source_session_id": source,
                "cutoff_event_id": str(uuid.uuid4()), "skill_context": "before-target-load",
                "limitations": ["Synthetic diagnostic only."], "personal_instructions_file": "personal.md",
            }
            (case / "case.json").write_text(json.dumps(definition))
            packet = case / "evidence/candidate"
            (packet / "history.jsonl").write_text(
                json.dumps({"type": "session", "version": 1, "externalId": source}) + "\n"
                + json.dumps({"type": "message", "role": "user", "content": [
                    {"type": "text", "text": "Prior marker NATIVE_CONTEXT_" + "a" * 32}]}) + "\n")
            (packet / "personal.md").write_text("Synthetic personal instruction.\n")
            (packet / "plan.md").write_text("# Synthetic native workflow plan\n- pending task\n")
            (case / "prompts/candidate.md").write_text(
                "Synthetic operation {NATIVE_GOAL_PATH} {NATIVE_DENIED_PATH}")
            freeze_case(corpus, case_id, False)
            plugin = root / "plugin"
            (plugin / "skills/unattended-run").mkdir(parents=True)
            (plugin / "skills/unattended-run/SKILL.md").write_text("synthetic")
            cli, sdk = root / "copilot", root / "index.js"
            cli.write_text("synthetic")
            sdk.write_text("synthetic")
            real_digest = skill_eval.digest
            revisions = corpus / "frozen" / case_id / "revisions"
            external_revisions = root / "external-revisions"
            revisions.rename(external_revisions)
            revisions.symlink_to(external_revisions, target_is_directory=True)
            try:
                verify_case(corpus, case_id)
                selected = frozen_case_path(corpus, case_id)
                before = directory_identity(selected)
                with (
                    mock.patch("skill_eval.copilot_identity") as identity,
                    mock.patch("skill_eval._native_workflow_probe") as native,
                    mock.patch("skill_eval._run_native_candidate") as candidate,
                ):
                    result = skill_eval._run_native_workflow_diagnostic(
                        corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                        sdk=sdk, run_root=selected / "diagnostic-output")
                    self.assertIn("overlaps original input", result["firsterror"])
                    self.assertFalse((selected / "diagnostic-output").exists())
                    self.assertEqual(directory_identity(selected), before)
                    identity.assert_not_called()
                    native.assert_not_called()
                    candidate.assert_not_called()
            finally:
                revisions.unlink()
                external_revisions.rename(revisions)
            for source_root in (case, frozen_case_path(corpus, case_id), plugin):
                run_root = source_root / "diagnostic-output"
                before = directory_identity(source_root)
                with (
                    self.subTest(source_root=source_root),
                    mock.patch("skill_eval.copilot_identity") as identity,
                    mock.patch("skill_eval._native_workflow_probe") as native,
                    mock.patch("skill_eval._run_native_candidate") as candidate,
                ):
                    result = skill_eval._run_native_workflow_diagnostic(
                        corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                        sdk=sdk, run_root=run_root)
                    self.assertIn("overlaps original input", result["firsterror"])
                    self.assertFalse(run_root.exists())
                    self.assertEqual(directory_identity(source_root), before)
                    identity.assert_not_called()
                    native.assert_not_called()
                    candidate.assert_not_called()

            def pinned_digest(path):
                return ("d336d72bd0f597d39c1c75732e5eb5b07cd43e65e81b45f90413ee86e69cb406"
                        if path == sdk else real_digest(path))

            def probe(operation, config):
                if operation == "setup":
                    raise ValueError("first setup error")
                if operation == "observe":
                    raise ValueError("later observe error")
                raise ValueError("later cleanup error")

            with (
                mock.patch("skill_eval.digest", side_effect=pinned_digest),
                mock.patch("skill_eval.copilot_identity", return_value={"version": "1.0.97", "sha256": "synthetic"}),
                mock.patch("skill_eval.discover_personal_instructions"),
                mock.patch("session_restore.import_session", return_value=str(uuid.uuid4())),
                mock.patch("skill_eval._native_workflow_probe", side_effect=probe) as native,
                mock.patch("skill_eval._run_native_candidate") as candidate,
                mock.patch("skill_eval.run_judges") as judges,
            ):
                result = skill_eval._run_native_workflow_diagnostic(
                    corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                    sdk=sdk, run_root=root / "run")
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["firsterror"], "first setup error")
                self.assertIsNone(result["cleanup"])
                self.assertEqual([call.args[0] for call in native.call_args_list], ["setup"])
                candidate.assert_not_called()
                judges.assert_not_called()
                retained = (root / "run/diagnostic-result.json").read_bytes()
                skill_eval._run_native_workflow_diagnostic(
                    corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                    sdk=sdk, run_root=root / "run")
                self.assertEqual((root / "run/diagnostic-result.json").read_bytes(), retained)
            imported_id = str(uuid.uuid4())

            def discover(**kwargs):
                receipt = kwargs["prefix"].with_suffix(".json")
                receipt.write_text("{}")
                return receipt

            def native_setup(operation, config):
                if operation == "cleanup":
                    raise ValueError("cleanup after candidate")
                goal = Path(config["home"]) / "session-state" / imported_id / "autopilot-objective.json"
                goal.parent.mkdir(parents=True, exist_ok=True)
                goal.write_text("{}")
                return {
                    "goal_path": str(goal), "goal": {"state": {"id": 17, "status": "completed"}},
                    "mode": "autopilot", "schedule_ids": [1], "schedules": {"entries": [{"id": 1}]},
                    "todos": {"rows": [{"id": "native-workflow-fixture", "title": "Synthetic pending work",
                               "description": "Owned diagnostic fixture", "status": "pending"}]},
                }

            with (
                mock.patch("skill_eval.digest", side_effect=pinned_digest),
                mock.patch("skill_eval.copilot_identity", return_value={"version": "1.0.97"}),
                mock.patch("skill_eval.discover_personal_instructions", side_effect=discover),
                mock.patch("session_restore.import_session", return_value=imported_id),
                mock.patch("skill_eval._native_workflow_probe", side_effect=native_setup) as native,
                mock.patch("skill_eval._run_native_candidate",
                           side_effect=ValueError("first candidate error")) as candidate,
                mock.patch("skill_eval.run_judges") as judges,
            ):
                result = skill_eval._run_native_workflow_diagnostic(
                    corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                    sdk=sdk, run_root=root / "candidate-failed-run")
                self.assertEqual(result["firsterror"], "first candidate error")
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual([call.args[0] for call in native.call_args_list], ["setup", "observe", "cleanup"])
                candidate.assert_called_once()
                judges.assert_not_called()
            blocked = {
                "status": "PREMODEL_BLOCKED", "firsterror": "native permission callback absent",
                "model_send_calls": 0, "checks": {"permission_traversal": False},
            }
            with (
                mock.patch("skill_eval.digest", side_effect=pinned_digest),
                mock.patch("skill_eval.copilot_identity", return_value={"version": "1.0.97"}),
                mock.patch("skill_eval.discover_personal_instructions", side_effect=discover),
                mock.patch("session_restore.import_session", return_value=imported_id),
                mock.patch("skill_eval._native_workflow_probe", side_effect=native_setup) as native,
                mock.patch("skill_eval._run_native_candidate", return_value=blocked),
                mock.patch("skill_eval.run_copilot") as cli_candidate,
                mock.patch("skill_eval.parse_run") as parser,
                mock.patch("skill_eval.run_judges") as judges,
            ):
                result = skill_eval._run_native_workflow_diagnostic(
                    corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                    sdk=sdk, run_root=root / "premodel-blocked-run")
                self.assertEqual(result["firsterror"], blocked["firsterror"])
                self.assertEqual(result["candidate"], blocked)
                self.assertEqual(result["accounting"]["candidate_model_send_calls"], 0)
                self.assertFalse(result["checks"]["sdk_preflight"])
                self.assertEqual([call.args[0] for call in native.call_args_list],
                                 ["setup", "observe", "cleanup"])
                cli_candidate.assert_not_called()
                parser.assert_not_called()
                judges.assert_not_called()

            for scenario in ("missing-skill", "denied-skill", "loaded", "missing-preflight",
                             "wrong-preflight-path", "failed-preflight"):
                def observed_candidate(config, **kwargs):
                    cwd = Path(config["cwd"])
                    goal = Path(config["home"]) / "session-state" / imported_id / "autopilot-objective.json"
                    events = [{"id": "start", "type": "assistant.turn_start",
                               "data": {"model": "gpt-5.6-sol-fast"}}]
                    if scenario != "missing-skill":
                        events.extend([
                            {"type": "tool.execution_start", "data": {
                                "toolName": "skill", "toolCallId": "load",
                                "arguments": {"skill": "unattended-run"}}},
                            {"type": "tool.execution_complete", "data": {
                                "toolCallId": "load", "success": scenario != "denied-skill"}},
                        ])
                    message = {"id": "answer", "type": "assistant.message", "data": {
                        "content": "NATIVE_CONTEXT_" + "a" * 32, "originatingMessageId": "send"}}
                    idle = {"id": "idle", "type": "session.idle", "data": {"mode": "autopilot"}}
                    events.extend([message, idle])
                    (Path(config["output"]).parent / "candidate-raw.jsonl").write_text(
                        "".join(json.dumps(event) + "\n" for event in events))
                    preflight = [{
                        "name": "sibling", "path": str(cwd.parent / "synthetic-denied-sibling.txt"),
                        "tool_call_id": "owner-sibling", "result": {"resultType": "rejected"},
                    }]
                    if scenario == "missing-preflight":
                        preflight = []
                    elif scenario == "wrong-preflight-path":
                        preflight[0]["path"] = str(cwd / "plan.md")
                    elif scenario == "failed-preflight":
                        preflight[0]["result"]["resultType"] = "failure"
                    return {
                        "session_id": imported_id, "status": "CANDIDATE_OBSERVED",
                        "model_send_calls": 1, "firsterror": None, "shutdown_errors": [],
                        "model_message_id": "send", "model_result": message,
                        "model_completion_event": idle, "preflight": preflight,
                        "checks": {key: True for key in ("effective_tools", "instruction_correspondence",
                                   "cold_state", "permission_traversal", "prefix_preserved")},
                    }

                with (
                    self.subTest(scenario=scenario),
                    mock.patch("skill_eval.digest", side_effect=pinned_digest),
                    mock.patch("skill_eval.copilot_identity", return_value={"version": "1.0.97"}),
                    mock.patch("skill_eval.discover_personal_instructions", side_effect=discover),
                    mock.patch("session_restore.import_session", return_value=imported_id),
                    mock.patch("skill_eval._native_workflow_probe", side_effect=native_setup),
                    mock.patch("skill_eval._run_native_candidate", side_effect=observed_candidate),
                ):
                    result = skill_eval._run_native_workflow_diagnostic(
                        corpus=corpus, case_id=case_id, plugin_dir=plugin, copilot=cli,
                        sdk=sdk, run_root=root / f"observed-{scenario}")
                    if scenario in {"missing-skill", "denied-skill"}:
                        self.assertIn("must invoke target skill", result["firsterror"])
                    elif scenario == "loaded":
                        self.assertTrue(result["parsed"]["skill_loaded"])
                    else:
                        self.assertIn("owner preflight rejection", result["firsterror"])


def historical_snapshot_fixture():
    return {
        "schemas": {
            "todos": "CREATE TABLE todos (id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT,"
                     "status TEXT DEFAULT 'pending' CHECK(status IN ('pending','in_progress','done','blocked')),"
                     "created_at TEXT DEFAULT (datetime('now')),updated_at TEXT DEFAULT (datetime('now')))",
            "todo_deps": "CREATE TABLE todo_deps (todo_id TEXT NOT NULL,depends_on TEXT NOT NULL,"
                         "PRIMARY KEY(todo_id,depends_on),FOREIGN KEY(todo_id) REFERENCES todos(id),"
                         "FOREIGN KEY(depends_on) REFERENCES todos(id))",
            "live_proof_receipts": "CREATE TABLE IF NOT EXISTS live_proof_receipts (claim_id TEXT PRIMARY KEY,"
                                   "status TEXT NOT NULL,scenario TEXT NOT NULL,artifact_path TEXT NOT NULL,"
                                   "candidate_identity TEXT,running_identity TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        },
        "rows": {
            "todos": [
                {"id": "one", "title": "Synthetic 'quoted' title", "description": None, "status": "done",
                 "created_at": "2001-01-01 01:02:03", "updated_at": None},
                {"id": "two", "title": "Synthetic task", "description": "", "status": "blocked",
                 "created_at": None, "updated_at": "2001-01-02 01:02:03"},
            ],
            "todo_deps": [{"todo_id": "two", "depends_on": "one"}],
            "live_proof_receipts": [{"claim_id": "synthetic", "status": "BLOCKED", "scenario": "Synthetic only",
                                     "artifact_path": "synthetic.json", "candidate_identity": None,
                                     "running_identity": None, "updated_at": "2001-01-01 01:02:03"}],
        },
        "queries": [{"query": query, "expected_text": "Synthetic SQL text", "expected_rows": count}
                    for query, count in [
                        ("SELECT * FROM todos ORDER BY rowid", 2),
                        ("SELECT * FROM todo_deps ORDER BY rowid", 1),
                        ("SELECT * FROM live_proof_receipts ORDER BY rowid", 1),
                        ("SELECT id FROM todos WHERE status='pending'", 0)]],
    }


class HistoricalSnapshotTests(unittest.TestCase):
    def test_explicit_nulls_quotes_timestamps_and_order_roundtrip(self):
        from contextlib import closing
        import sqlite3
        from session_restore import compile_task_snapshot
        source = historical_snapshot_fixture()
        compiled = compile_task_snapshot(source)
        with closing(sqlite3.connect(":memory:")) as database:
            database.execute("PRAGMA foreign_keys=ON")
            for schema in source["schemas"].values():
                database.execute(schema)
            database.executescript(compiled["transaction"])
            self.assertEqual(database.execute("SELECT title,description,created_at,updated_at FROM todos ORDER BY rowid").fetchall(),
                             [("Synthetic 'quoted' title", None, "2001-01-01 01:02:03", None),
                              ("Synthetic task", "", None, "2001-01-02 01:02:03")])
            for query in compiled["comparisons"]:
                self.assertEqual(database.execute(query).fetchall(), [])
            database.execute("UPDATE todos SET updated_at='changed' WHERE id='one'")
            self.assertTrue(database.execute(compiled["comparisons"][0]).fetchall())

    def test_refuses_missing_columns_bad_keys_checks_foreign_keys_and_writing_queries(self):
        from session_restore import compile_task_snapshot
        import copy
        for failure in ("column", "key", "check", "foreign", "write", "count"):
            with self.subTest(failure=failure):
                source = copy.deepcopy(historical_snapshot_fixture())
                if failure == "column":
                    del source["rows"]["todos"][0]["created_at"]
                elif failure == "key":
                    source["schemas"]["todos"] = source["schemas"]["todos"].replace(" PRIMARY KEY", "")
                elif failure == "check":
                    source["schemas"]["todos"] = source["schemas"]["todos"].replace(
                        " CHECK(status IN ('pending','in_progress','done','blocked'))", "")
                elif failure == "foreign":
                    source["rows"]["todo_deps"][0]["depends_on"] = "missing"
                elif failure == "write":
                    source["queries"][0]["query"] = "WITH x AS (SELECT 1) DELETE FROM todos"
                else:
                    source["queries"][0]["expected_rows"] = 999
                with self.assertRaises(ValueError):
                    compile_task_snapshot(source)


class NativeContextCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.fixture = self.root / "fixture.json"
        self.messages = [
            {"role": "user", "content": "Prior value is prior-only"},
            {"role": "assistant", "content": "Prior context acknowledged"},
            {"role": "user", "content": "Latest value is latest-only"},
            {"role": "assistant", "content": "Update acknowledged"},
        ]
        self.expected = {"summary_value": "summary-only", "latest_value": "latest-only"}
        self.fixture.write_text(json.dumps({
            "schema_version": 1, "provenance": "synthetic-calibration",
            "messages": self.messages, "summary": "Summary value is summary-only; latest was superseded",
            "prompt": "Return summary_value and latest_value as JSON.",
            "expected": self.expected,
        }))
        self.fixture.chmod(0o600)
        self.plugin = self.root / "plugin"
        self.plugin.mkdir()
        (self.plugin / "fixture.txt").write_text("Synthetic pinned plugin input")
        self.cli = self.root / "copilot"
        self.cli.write_text("Synthetic never-executed CLI")
        self.sdk = self.root / "sdk/index.js"
        self.sdk.parent.mkdir()
        self.sdk.write_text("Synthetic never-imported SDK")
        schema = self.sdk.parent / "generated/session-events.d.ts"
        schema.parent.mkdir()
        schema.write_text(
            'export interface CompactionCompleteEvent {\n'
            'type: "session.compaction_complete";\nid: string;\nparentId: string | null;\n'
            'timestamp: string;\ndata: CompactionCompleteData;\n}\n'
            'export interface CompactionCompleteData {\nsuccess: boolean;\nsummaryContent?: string;\n}\n')
        self.run = self.root / "run"
        self.session_id = str(uuid.uuid4())
        self.order = []
        self.journal = None

    def import_double(self, restoration, history, **kwargs):
        self.order.append("import-exit")
        home = Path(kwargs["receipt_path"]).parents[1] / "candidate-home"
        self.journal = home / "session-state" / self.session_id / "events.jsonl"
        self.journal.parent.mkdir(parents=True)
        events = [{"id": str(uuid.uuid4()), "type": "session.start", "parentId": None,
                   "timestamp": "2026-01-01T00:00:00Z", "data": {"sessionId": self.session_id}}]
        messages = [json.loads(line) for line in history.read_text().splitlines()][1:]
        for message in messages:
            parts = message["content"]
            self.assertIsInstance(parts, list)
            self.assertEqual(len(parts), 1)
            self.assertEqual(set(parts[0]), {"type", "text"})
            self.assertEqual(parts[0]["type"], "text")
            self.assertIsInstance(parts[0]["text"], str)
            self.assertTrue(parts[0]["text"])
            events.append({
                "id": str(uuid.uuid4()), "type": message["role"] + ".message", "parentId": events[-1]["id"],
                "timestamp": "2026-01-01T00:00:00Z", "data": {"content": parts[0]["text"]},
            })
        self.journal.write_text("".join(json.dumps(event) + "\n" for event in events))
        skill_eval.write_json(kwargs["receipt_path"], {
            "status": "PASS", "session_id": self.session_id, "exit_code": 0,
            "history_sha256": digest(history),
        })
        return self.session_id

    def arguments(self):
        return dict(fixture_file=self.fixture, plugin_dir=self.plugin, copilot=self.cli,
                    sdk=self.sdk, run_root=self.run, model="fixture-model", effort="low")

    def candidate_double(self, config, **kwargs):
        self.order.append("candidate-return")
        self.assertNotIn("expected", config)
        self.assertNotIn("expected_file", config)
        self.assertEqual(list(Path(config["cwd"]).iterdir()), [])
        self.assertEqual(Path(config["prompt_path"]).read_text(), "Return summary_value and latest_value as JSON.")
        self.assertEqual(set(json.loads(Path(config["context_fixture_file"]).read_text())),
                         {"schema_version", "summary_event_id", "summary_sha256", "post_event_ids"})
        if kwargs["preflight_only"]:
            return {"status": "PREFLIGHT_OBSERVED", "model_send_calls": 0}
        message = {"id": "answer", "type": "assistant.message",
                   "data": {"content": json.dumps(self.expected), "originatingMessageId": "send"}}
        idle = {"id": "idle", "type": "session.idle", "data": {"aborted": False}}
        return {"status": "CANDIDATE_OBSERVED", "model_send_calls": 1, "firsterror": None,
                "shutdown_errors": [], "model_message_id": "send", "model_result": message,
                "model_completion_event": idle, "candidate_events": [message, idle], "model_event_start_index": 0}

    def probe_double(self, operation, config):
        self.order.append(operation)
        staged = (self.run / "owner/journal-staged.jsonl").read_bytes()
        self.assertEqual(self.journal.read_bytes(), staged)
        events = [json.loads(line) for line in staged.splitlines()]
        self.assertEqual(events[3]["type"], "session.compaction_complete")
        self.assertEqual(events[4]["parentId"], events[3]["id"])
        self.assertFalse((self.journal.parent / "autopilot-objective.json").exists())
        return {"status": {"setup": "SETUP_OBSERVED", "observe": "OBSERVED", "cleanup": "CLEANED"}[operation]}

    def patches(self, stack):
        real_digest = skill_eval.digest
        stack.enter_context(mock.patch("skill_eval.digest", side_effect=lambda path:
            "d336d72bd0f597d39c1c75732e5eb5b07cd43e65e81b45f90413ee86e69cb406"
            if path == self.sdk else real_digest(path)))
        stack.enter_context(mock.patch("skill_eval.copilot_identity", return_value={"version": "1.0.97"}))
        stack.enter_context(mock.patch("session_restore.import_session", side_effect=self.import_double))
        native = stack.enter_context(mock.patch("skill_eval._native_workflow_probe", side_effect=self.probe_double))
        candidate = stack.enter_context(mock.patch("skill_eval._run_native_candidate", side_effect=self.candidate_double))
        stack.enter_context(mock.patch("skill_eval.subprocess.run", side_effect=AssertionError("Real process prohibited")))
        stack.enter_context(mock.patch("skill_eval.run_judges", side_effect=AssertionError("Judge prohibited")))
        return native, candidate

    def test_coordinator_imports_then_stages_then_helper_then_owner_oracle(self):
        from contextlib import ExitStack
        real_oracle = skill_eval._native_context_oracle
        def oracle(candidate, expected):
            self.order.append("oracle")
            return real_oracle(candidate, expected)
        with ExitStack() as stack:
            self.patches(stack)
            stack.enter_context(mock.patch("skill_eval._native_context_oracle", side_effect=oracle))
            result = skill_eval._run_native_context_calibration(**self.arguments(), model_send=True)
        self.assertEqual(result["status"], "CALIBRATION_OBSERVED", result["firsterror"])
        self.assertEqual(self.order, ["import-exit", "setup", "candidate-return", "oracle", "observe", "cleanup"])
        before = [json.loads(line) for line in (self.run / "owner/journal-before.jsonl").read_bytes().splitlines()]
        after = [json.loads(line) for line in self.journal.read_bytes().splitlines()]
        self.assertEqual([event["data"] for event in before], [event["data"] for event in after if event["type"] != "session.compaction_complete"])
        self.assertEqual([event["id"] for event in before], [event["id"] for event in after if event["type"] != "session.compaction_complete"])
        retained = (self.run / "context-result.json").read_bytes()
        again = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertIn("must be new", again["firsterror"])
        self.assertEqual((self.run / "context-result.json").read_bytes(), retained)

    def test_synthetic_import_seed_has_current_utc_session_and_message_timestamps(self):
        from contextlib import ExitStack
        before = skill_eval.datetime.now(skill_eval.timezone.utc)
        def import_with_timestamps(restoration, history, **kwargs):
            records = [json.loads(line) for line in history.read_text().splitlines()]
            self.assertEqual(len(records), 5)
            self.assertIn("createdAt", records[0])
            timestamps = [records[0]["createdAt"]]
            for record in records[1:]:
                self.assertIn("timestamp", record)
                timestamps.append(record["timestamp"])
            parsed = [skill_eval.datetime.fromisoformat(value) for value in timestamps]
            after = skill_eval.datetime.now(skill_eval.timezone.utc)
            for instant in parsed:
                self.assertIsNotNone(instant.tzinfo)
                self.assertEqual(instant.utcoffset(), skill_eval.timezone.utc.utcoffset(instant))
                self.assertLessEqual(before, instant)
                self.assertLessEqual(instant, after)
            self.assertEqual(parsed, sorted(parsed))
            return self.import_double(restoration, history, **kwargs)
        with ExitStack() as stack:
            self.patches(stack)
            importer = stack.enter_context(mock.patch("session_restore.import_session", side_effect=import_with_timestamps))
            result = skill_eval._run_native_context_calibration(**self.arguments())
        importer.assert_called_once()
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])

    def test_synthetic_import_seed_uses_text_parts_without_changing_fixture_strings(self):
        from contextlib import ExitStack
        fixture_before = self.fixture.read_bytes()
        def import_with_text_parts(restoration, history, **kwargs):
            records = [json.loads(line) for line in history.read_text().splitlines()][1:]
            self.assertEqual(
                [(record["role"], record["content"]) for record in records],
                [(message["role"], [{"type": "text", "text": message["content"]}])
                 for message in self.messages])
            return self.import_double(restoration, history, **kwargs)
        with ExitStack() as stack:
            self.patches(stack)
            importer = stack.enter_context(mock.patch("session_restore.import_session", side_effect=import_with_text_parts))
            result = skill_eval._run_native_context_calibration(**self.arguments())
        importer.assert_called_once()
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual(self.fixture.read_bytes(), fixture_before)

    def test_zero_model_default_never_calls_oracle(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            oracle = stack.enter_context(mock.patch("skill_eval._native_context_oracle"))
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        oracle.assert_not_called()
        self.assertEqual(self.order, ["import-exit", "setup", "candidate-return", "observe", "cleanup"])

    def test_unknown_envelope_order_schema_and_import_exit_refuse_before_helper(self):
        from contextlib import ExitStack
        for fault in ("schema", "envelope", "order", "time", "receipt"):
            with self.subTest(fault=fault), ExitStack() as stack:
                self.run = self.root / fault
                native, candidate = self.patches(stack)
                original = self.import_double
                def broken(*args, **kwargs):
                    session_id = original(*args, **kwargs)
                    if fault == "schema":
                        (self.sdk.parent / "generated/session-events.d.ts").write_text("Unknown schema")
                    elif fault == "receipt":
                        receipt = json.loads(kwargs["receipt_path"].read_text())
                        receipt["exit_code"] = 1
                        kwargs["receipt_path"].write_text(json.dumps(receipt))
                    else:
                        events = [json.loads(line) for line in self.journal.read_text().splitlines()]
                        if fault == "envelope":
                            events[1]["unexpected"] = True
                        elif fault == "time":
                            events[1]["timestamp"] = "2025-01-01T00:00:00Z"
                        else:
                            events[1]["parentId"] = None
                        self.journal.write_text("".join(json.dumps(event) + "\n" for event in events))
                    self.original_invalid_bytes = self.journal.read_bytes()
                    return session_id
                stack.enter_context(mock.patch("session_restore.import_session", side_effect=broken))
                # Restore the synthetic schema after the schema-negative subcase.
                if fault != "schema":
                    (self.sdk.parent / "generated/session-events.d.ts").write_text(
                        'export interface CompactionCompleteEvent {\n'
                        'type: "session.compaction_complete";\nid: string;\nparentId: string | null;\n'
                        'timestamp: string;\ndata: CompactionCompleteData;\n}\n'
                        'export interface CompactionCompleteData {\nsuccess: boolean;\nsummaryContent?: string;\n}\n')
                result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["setup_error_code"], "NATIVE_CONTEXT_SETUP_UNSUPPORTED")
                self.assertEqual(result["status"], "FAILED")
                native.assert_not_called()
                candidate.assert_not_called()
                self.assertEqual(self.journal.read_bytes(), self.original_invalid_bytes)

    def test_setup_and_candidate_failure_preserve_first_error_without_retry(self):
        from contextlib import ExitStack
        for fault in ("setup", "candidate"):
            with self.subTest(fault=fault), ExitStack() as stack:
                self.run = self.root / fault
                native, candidate = self.patches(stack)
                if fault == "setup":
                    native.side_effect = ValueError("first setup failure")
                else:
                    candidate.side_effect = ValueError("first candidate failure")
                    native.side_effect = lambda operation, config: (
                        {"status": "SETUP_OBSERVED"} if operation == "setup"
                        else (_ for _ in ()).throw(ValueError("later cleanup failure")))
                result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["firsterror"], f"first {fault} failure")
                if fault == "setup":
                    candidate.assert_not_called()
                    self.assertEqual(native.call_count, 1)
                else:
                    self.assertEqual(candidate.call_count, 1)
                    self.assertEqual([call.args[0] for call in native.call_args_list], ["setup", "observe", "cleanup"])

    def test_fixture_extra_keys_and_value_leak_refuse_before_import(self):
        from contextlib import ExitStack
        original = json.loads(self.fixture.read_text())
        for fault in ("extra", "leak"):
            with self.subTest(fault=fault), ExitStack() as stack:
                self.patches(stack)
                importer = stack.enter_context(mock.patch("session_restore.import_session"))
                invalid = {**original}
                if fault == "extra":
                    invalid["state_file"] = "forbidden"
                else:
                    invalid["prompt"] += " " + self.expected["summary_value"]
                self.fixture.write_text(json.dumps(invalid))
                result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertIn("Invalid fixed synthetic", result["firsterror"])
                self.assertFalse(self.run.exists())
                importer.assert_not_called()

    def test_oracle_failure_retains_independent_observe_and_cleanup_errors(self):
        from contextlib import ExitStack
        timeout = subprocess.TimeoutExpired(["node", "native-probe", "cleanup"], 360)
        def probe(operation, config):
            if operation == "setup":
                return self.probe_double(operation, config)
            if operation == "observe":
                raise ValueError("independent observe failure")
            raise timeout
        def wrong_answer(config, **kwargs):
            packet = self.candidate_double(config, **kwargs)
            packet["model_result"]["data"]["content"] = json.dumps({
                **self.expected, "summary_value": "wrong"})
            return packet
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            native.side_effect = probe
            candidate.side_effect = wrong_answer
            result = skill_eval._run_native_context_calibration(**self.arguments(), model_send=True)
        self.assertEqual(result["firsterror"], "Context recall did not return the tested summary/latest values")
        self.assertEqual(result["operation_errors"], {
            "observe": {"type": "ValueError", "message": "independent observe failure"},
            "cleanup": {"type": "TimeoutExpired", "message": str(timeout)},
        })
        self.assertEqual([call.args[0] for call in native.call_args_list], ["setup", "observe", "cleanup"])
        self.assertEqual(json.loads((self.run / "context-result.json").read_text()), result)

    def test_owner_oracle_rejects_tools_wrong_values_and_bad_root_correlation(self):
        packet = self.candidate_double_for_oracle()
        result = skill_eval._native_context_oracle(packet, self.expected)
        self.assertTrue(result["tested_values_available"])
        for fault in ("tool", "root-error", "wrong-value", "wrong-id", "aborted", "child", "idle-first"):
            with self.subTest(fault=fault):
                invalid = json.loads(json.dumps(packet))
                if fault == "tool":
                    invalid["candidate_events"].insert(0, {"type": "tool.execution_start", "data": {}})
                elif fault == "root-error":
                    invalid["candidate_events"].append({"type": "session.error", "data": {"message": "native error"}})
                elif fault == "wrong-value":
                    invalid["model_result"]["data"]["content"] = "{}"
                    invalid["candidate_events"][0] = invalid["model_result"]
                elif fault == "wrong-id":
                    invalid["model_message_id"] = "other"
                elif fault == "aborted":
                    invalid["model_completion_event"]["data"]["aborted"] = True
                    invalid["candidate_events"][1] = invalid["model_completion_event"]
                elif fault == "child":
                    invalid["model_result"]["agentId"] = "child"
                    invalid["candidate_events"][0] = invalid["model_result"]
                else:
                    invalid["candidate_events"].reverse()
                with self.assertRaises(ValueError):
                    skill_eval._native_context_oracle(invalid, self.expected)
        packet["candidate_events"].insert(0, {"type": "tool.execution_start", "data": {"toolCallId": "owner-only"}})
        packet["model_event_start_index"] = 1
        self.assertTrue(skill_eval._native_context_oracle(packet, self.expected)["zero_candidate_tools"])

    def test_caller_rejects_extra_helper_config_before_any_process(self):
        with mock.patch("skill_eval.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "fixed native context coordinator fields"):
                skill_eval._native_workflow_probe("candidate", {
                    "profile": "native-context-calibration", "expected_file": str(self.fixture)})
        process.assert_not_called()

    def test_context_receipt_requires_summary_order_and_initialized_context(self):
        fields = ["cli", "sdk", "home", "os_home", "cwd", "output", "prompt_path", "event_log",
                  "plugin_path", "prefix_file", "context_fixture_file"]
        config = {key: str(self.root / key) for key in fields}
        config.update(profile="native-context-calibration", session_id=self.session_id,
                      model="fixture-model", effort="low")
        base = {
            "cli": config["cli"], "sdk": config["sdk"], "session_id": self.session_id,
            "profile": config["profile"], "connection": {"path": config["cli"]},
            "runtime_identity": {"version": "1.0.97"}, "shutdown_errors": [],
            "status": "PREFLIGHT_OBSERVED", "model_send_calls": 0, "firsterror": None,
            "context_initialized": True,
            "checks": {key: True for key in (
                "effective_tools", "instruction_correspondence", "cold_state", "permission_traversal",
                "prefix_preserved", "imported_prefix_correspondence", "context_summary_order")},
        }
        for fault in ("none", "summary", "initialized"):
            with self.subTest(fault=fault):
                selected = {**config, "output": str(self.root / f"{fault}.json")}
                receipt = json.loads(json.dumps(base))
                if fault == "summary":
                    receipt["checks"]["context_summary_order"] = False
                if fault == "initialized":
                    receipt["context_initialized"] = False
                def execute(command, **kwargs):
                    Path(selected["output"]).write_text(json.dumps(receipt))
                    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
                with (
                    mock.patch("skill_eval.subprocess.run", side_effect=execute),
                    mock.patch("skill_eval.personal_instruction_environment", return_value={}),
                ):
                    if fault == "none":
                        self.assertEqual(skill_eval._native_workflow_probe("preflight", selected), receipt)
                    else:
                        with self.assertRaisesRegex(ValueError, "conditional model execution"):
                            skill_eval._native_workflow_probe("preflight", selected)

    def candidate_double_for_oracle(self):
        message = {"id": "answer", "type": "assistant.message", "data": {
            "content": json.dumps({**self.expected, "prior_value": "diagnostic-retention"}),
            "originatingMessageId": "send"}}
        idle = {"id": "idle", "type": "session.idle", "data": {"aborted": False}}
        return {"status": "CANDIDATE_OBSERVED", "model_send_calls": 1, "firsterror": None,
                "shutdown_errors": [], "model_message_id": "send", "model_result": message,
                "model_completion_event": idle, "candidate_events": [message, idle], "model_event_start_index": 0}

    def test_historical_preflight_accepts_nullable_caches_only_with_truthful_operation_witnesses(self):
        fields = ["cli", "sdk", "home", "os_home", "cwd", "output", "prompt_path", "event_log",
                  "plugin_path", "prefix_file", "context_fixture_file"]
        config = {key: str(self.root / key) for key in fields}
        config.update(profile="native-historical-context", session_id=self.session_id,
                      model="fixture-model", effort="low",
                      candidate_permissions={"write_paths": ["target.txt"],
                                             "shell_commands": ["python3 -I check.py"]})
        base = {
            "cli": config["cli"], "sdk": config["sdk"], "session_id": self.session_id,
            "profile": config["profile"], "connection": {"path": config["cli"]},
            "runtime_identity": {"version": "1.0.97"}, "shutdown_errors": [],
            "status": "PREFLIGHT_OBSERVED", "model_send_calls": 0, "firsterror": None,
            "effective_tools": {"tools": None},
            "context": {"getContextAttribution": {"contextAttribution": None}},
            "context_initialized": False, "editable_restored": True,
            "editable_preflight": [{} for _ in range(6)],
            "checks": {key: True for key in (
                "instruction_correspondence", "cold_state", "permission_traversal",
                "prefix_preserved", "imported_prefix_correspondence", "context_summary_order",
                "editable_permission_traversal")},
        }
        base["checks"]["effective_tools"] = None
        base["checks"].update(prefix_preservation_scope="preflight_snapshot",
                              terminal_prefix_preserved=None)
        for fault in ("none", "tools", "context", "callback", "restored", "count", "summary", "send",
                      "scope", "terminal", "missing_terminal", "prefix"):
            with self.subTest(fault=fault):
                selected = {**config, "output": str(self.root / f"historical-{fault}.json")}
                receipt = json.loads(json.dumps(base))
                if fault == "tools":
                    receipt["checks"]["effective_tools"] = True
                elif fault == "context":
                    receipt["context_initialized"] = True
                elif fault == "callback":
                    receipt["checks"]["editable_permission_traversal"] = False
                elif fault == "restored":
                    receipt["editable_restored"] = False
                elif fault == "count":
                    receipt["editable_preflight"].pop()
                elif fault == "summary":
                    receipt["checks"]["context_summary_order"] = False
                elif fault == "send":
                    receipt["model_send_calls"] = 1
                elif fault == "scope":
                    receipt["checks"]["prefix_preservation_scope"] = "whole_namespace"
                elif fault == "terminal":
                    receipt["checks"]["terminal_prefix_preserved"] = True
                elif fault == "missing_terminal":
                    del receipt["checks"]["terminal_prefix_preserved"]
                elif fault == "prefix":
                    receipt["checks"]["prefix_preserved"] = False
                def execute(command, **kwargs):
                    Path(selected["output"]).write_text(json.dumps(receipt))
                    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
                with (
                    mock.patch("skill_eval.subprocess.run", side_effect=execute),
                    mock.patch("skill_eval.personal_instruction_environment", return_value={}),
                ):
                    if fault == "none":
                        self.assertEqual(skill_eval._native_workflow_probe("preflight", selected), receipt)
                    else:
                        with self.assertRaises(ValueError):
                            skill_eval._native_workflow_probe("preflight", selected)


class NativeHistoricalContextTests(unittest.TestCase):
    arguments = NativeContextCalibrationTests.arguments
    patches = NativeContextCalibrationTests.patches

    def setUp(self):
        NativeContextCalibrationTests.setUp(self)
        timestamp = "2001-01-01T00:00:00Z"
        records = [{"type": "session", "version": 1, "externalId": "synthetic-source", "createdAt": timestamp},
                   {"type": "message", "id": "user", "role": "user",
                    "content": [{"type": "text", "text": "Synthetic request"}]},
                   {"type": "message", "id": "assistant", "role": "assistant",
                    "content": [{"type": "text", "text": "Synthetic tool group"}]},
                   {"type": "tool-call", "id": "call-one", "name": "view", "arguments": {"path": "synthetic.txt"}},
                   {"type": "tool-call", "id": "call-two", "name": "sql", "arguments": {"query": "SELECT 1"}},
                   {"type": "tool-result", "id": "result-one", "toolCallId": "call-one",
                    "success": False, "content": "Synthetic preserved failure"},
                   {"type": "tool-result", "id": "result-two", "toolCallId": "call-two",
                    "success": True, "content": "Synthetic result"},
                   {"type": "message", "id": "final", "role": "assistant",
                    "content": [{"type": "text", "text": "Synthetic final"}]}]
        skills = []
        for index in range(8):
            content = f"Synthetic historical body {index}"
            skills.append({
                "actor_scope": "child" if index == 6 else "root",
                "position": "post-compaction" if index == 7 else "pre-compaction",
                "source_event": {"type": "skill.invoked", "id": f"synthetic-skill-{index}",
                                 "timestamp": timestamp, "data": {"name": f"synthetic-{index}",
                                 "content": content, "path": f"synthetic/{index}/SKILL.md", "allowedTools": []}},
                "body_sha256": hashlib.sha256(content.encode()).hexdigest(),
                **({"records_before": 5} if index == 7 else {}),
            })
        self.historical = {
            "schema_version": 2, "provenance": "source-bound-historical", "records": records,
            "source_mapping": [{"event_id": f"synthetic-group-{index}", "native_type": kind,
                                "record_indices": indices, "timestamp": timestamp}
                               for index, (kind, indices) in enumerate([
                                   ("user.message", [1]), ("assistant.message", [2, 3, 4]),
                                   ("tool.execution_complete", [5]), ("tool.execution_complete", [6]),
                                   ("assistant.message", [7])])],
            "summary": "Synthetic native summary", "summary_timestamp": timestamp,
            "skill_events": skills, "snapshot": historical_snapshot_fixture(),
            "required_tools": ["skill", "view", "sql", "manage_schedule", "bash", "apply_patch", "rg", "task", "task_complete"],
            "limitations": ["Synthetic fixtures only; no native consumption claimed"],
            "restoration": {"source_session_id": "synthetic-source", "cutoff_event_id": "excluded-trigger",
                            "skill_context": "recorded-target-context"},
            "personal_instructions": "Synthetic historical personal instructions",
            "candidate_permissions": {"write_paths": [], "shell_commands": []},
        }
        self.fixture.write_text(json.dumps(self.historical))
        with (self.sdk.parent / "generated/session-events.d.ts").open("a") as stream:
            stream.write('export interface SkillInvokedEvent {\ntype: "skill.invoked";\n}\n'
                         'export interface SkillInvokedData {\nname: string;\npath: string;\ncontent: string;\n}\n')

    def import_double(self, restoration, history, **kwargs):
        self.order.append("import-exit")
        self.assertEqual(restoration["skill_context"], "recorded-target-context")
        from session_restore import semantic_projection
        self.assertEqual(
            semantic_projection([json.loads(line) for line in history.read_text().splitlines()]),
            semantic_projection(self.historical["records"]))
        home = Path(kwargs["receipt_path"]).parents[1] / "candidate-home"
        self.journal = home / "session-state" / self.session_id / "events.jsonl"
        self.journal.parent.mkdir(parents=True)
        imported_at = "2002-01-01T00:00:00Z"
        events = [{"id": str(uuid.uuid4()), "type": "session.start", "parentId": None,
                   "timestamp": imported_at, "data": {"sessionId": self.session_id,
                   "startTime": self.historical["records"][0]["createdAt"]}}]
        native_data = [
            {"content": "Synthetic request"},
            {"content": "Synthetic tool group", "toolRequests": [
                {"toolCallId": "native-one", "name": "view", "arguments": {"path": "synthetic.txt"}},
                {"toolCallId": "native-two", "name": "sql", "arguments": {"query": "SELECT 1"}}]},
            {"toolCallId": "native-one", "success": False, "error": {"message": "Synthetic preserved failure"}},
            {"toolCallId": "native-two", "success": True, "result": {"content": "Synthetic result"}},
            {"content": "Synthetic final"},
        ]
        for group, data in zip(self.historical["source_mapping"], native_data):
            events.append({"id": str(uuid.uuid4()), "type": group["native_type"], "parentId": events[-1]["id"],
                           "timestamp": imported_at, "data": data})
            for request in data.get("toolRequests", []):
                events.append({"id": str(uuid.uuid4()), "type": "tool.execution_start",
                               "parentId": events[-1]["id"], "timestamp": imported_at,
                               "data": {"toolCallId": request["toolCallId"], "toolName": request["name"],
                                        "arguments": request["arguments"]}})
        self.mutate_import(events)
        for previous, event in zip(events, events[1:]):
            event["parentId"] = previous["id"]
        self.journal.write_text("".join(json.dumps(event) + "\n" for event in events))
        skill_eval.write_json(kwargs["receipt_path"], {
            "status": "PASS", "session_id": self.session_id, "exit_code": 0, "history_sha256": digest(history)})
        return self.session_id

    def mutate_import(self, events):
        pass

    def probe_double(self, operation, config):
        self.order.append(operation)
        self.assertEqual(config["profile"], "native-historical-context")
        staged = json.loads(Path(config["prefix_file"]).read_text())
        self.assertEqual([item["data"]["name"] for item in staged if item["type"] == "skill.invoked"],
                         [f"synthetic-{index}" for index in [0, 1, 2, 3, 4, 5, 7]])
        later = next(index for index, item in enumerate(staged) if item["data"].get("name") == "synthetic-7")
        self.assertEqual(staged[later - 1]["data"]["error"]["message"], "Synthetic preserved failure")
        self.assertEqual(staged[later + 1]["data"]["result"]["content"], "Synthetic result")
        for previous, event in zip(staged, staged[1:]):
            self.assertEqual(event["parentId"], previous["id"])
        return {"status": {"setup": "SETUP_OBSERVED", "observe": "OBSERVED", "cleanup": "CLEANED"}[operation]}

    def candidate_double(self, config, **kwargs):
        self.assertTrue(kwargs["preflight_only"])
        self.order.append("preflight")
        return {"status": "PREFLIGHT_OBSERVED", "model_send_calls": 0}

    def test_source_bound_staging_is_before_sdk_and_keeps_child_out_and_error_intact(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual(self.order, ["import-exit", "setup", "preflight", "observe", "cleanup"])
        self.assertEqual(result["locator"]["tool_call_ids"], {"call-one": "native-one", "call-two": "native-two"})
        self.assertEqual(len(result["locator"]["correspondence"]), 7)

    def test_pristine_preparation_uses_fresh_source_at_the_native_consumer_seam(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            calibration = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(calibration["status"], "CONTEXT_SETUP_OBSERVED")
        calibration_session_id = self.session_id
        calibration_root = self.run
        calibration_journal = self.journal
        with calibration_journal.open("a") as stream:
            stream.write(json.dumps({"type": "session.warning",
                                     "data": {"warningType": "interrupted_tools"}}) + "\n")
        preserved = {path: path.read_bytes() for path in (
            calibration_journal, calibration_root / "context-result.json",
            calibration_root / "owner/identities.json")}
        self.run = self.root / "pristine"
        self.session_id = str(uuid.uuid4())
        self.order = []
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(
                **self.arguments(), source_preparation_only=True,
                calibration_root=calibration_root)
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual(self.order, ["import-exit", "setup", "observe", "cleanup"])
        candidate.assert_not_called()
        self.assertNotIn("candidate", result)
        selected = native.call_args_list[0].args[1]
        self.assertEqual(Path(selected["home"]), self.run / "candidate-home")
        self.assertEqual(selected["session_id"], self.session_id)
        self.assertNotEqual(selected["session_id"], calibration_session_id)
        self.assertEqual(Path(selected["prefix_file"]), self.run / "owner/imported-prefix.json")
        self.assertEqual(result["source_preparation_only"], True)
        self.assertTrue(all(path.read_bytes() == data for path, data in preserved.items()))

    def test_pristine_preparation_refuses_destination_overlap_before_import(self):
        from contextlib import ExitStack
        calibration = self.root / "calibration"
        calibration.mkdir()
        for destination in (calibration, calibration / "nested", self.root):
            with self.subTest(destination=destination), ExitStack() as stack:
                native, candidate = self.patches(stack)
                imported = stack.enter_context(mock.patch("session_restore.import_session"))
                result = skill_eval._run_native_context_calibration(
                    **{**self.arguments(), "run_root": destination},
                    source_preparation_only=True, calibration_root=calibration)
                self.assertEqual(result["status"], "FAILED")
                native.assert_not_called()
                candidate.assert_not_called()
                imported.assert_not_called()
        self.assertEqual(list(calibration.iterdir()), [])

    def test_pristine_preparation_refuses_instrumented_input_and_model_send(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            calibration = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(calibration["status"], "CONTEXT_SETUP_OBSERVED")
        calibration_root = self.run
        for failure in ("instrumented", "model", "alias"):
            with self.subTest(failure=failure), ExitStack() as stack:
                selected = {**self.arguments(), "run_root": self.root / f"pristine-{failure}",
                            "source_preparation_only": True, "calibration_root": calibration_root}
                if failure == "instrumented":
                    selected["fixture_file"] = calibration_root / "owner/imported-prefix.json"
                elif failure == "model":
                    selected["model_send"] = True
                else:
                    alias = self.root / "calibration-alias"
                    alias.symlink_to(calibration_root, target_is_directory=True)
                    selected["calibration_root"] = alias
                native, candidate = self.patches(stack)
                imported = stack.enter_context(mock.patch("session_restore.import_session"))
                result = skill_eval._run_native_context_calibration(**selected)
                self.assertEqual(result["status"], "FAILED")
                self.assertFalse(selected["run_root"].exists())
                native.assert_not_called()
                candidate.assert_not_called()
                imported.assert_not_called()

    def test_pristine_preparation_refuses_reusing_calibration_session_id(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            calibration = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(calibration["status"], "CONTEXT_SETUP_OBSERVED")
        calibration_root = self.run
        self.run = self.root / "pristine"
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(
                **self.arguments(), source_preparation_only=True,
                calibration_root=calibration_root)
        self.assertEqual(result["status"], "FAILED")
        native.assert_not_called()
        candidate.assert_not_called()

    def test_pristine_preparation_refuses_copying_calibration_as_a_skill_input(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            calibration = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(calibration["status"], "CONTEXT_SETUP_OBSERVED")
        calibration_root = self.run
        self.session_id = str(uuid.uuid4())
        for input_name in ("plugin_dir", "personal_skill_dir"):
            with self.subTest(input_name=input_name), ExitStack() as stack:
                destination = self.root / f"pristine-{input_name}"
                native, candidate = self.patches(stack)
                imported = stack.enter_context(mock.patch(
                    "session_restore.import_session", side_effect=self.import_double))
                result = skill_eval._run_native_context_calibration(
                    **{**self.arguments(), "run_root": destination, input_name: calibration_root},
                    source_preparation_only=True, calibration_root=calibration_root)
                self.assertEqual(result["status"], "FAILED")
                self.assertFalse(destination.exists())
                native.assert_not_called()
                candidate.assert_not_called()
                imported.assert_not_called()

    def test_separate_personal_definitions_are_snapshotted_and_forwarded(self):
        from contextlib import ExitStack
        personal = self.root / "personal"
        personal.mkdir()
        definition = personal / "synthetic-personal"
        definition.mkdir()
        original = "---\nname: synthetic-personal\n---\nSynthetic personal definition.\n"
        (definition / "SKILL.md").write_text(original)
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(
                **self.arguments(), personal_skill_dir=personal)
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        copied = self.run / "pinned-personal-skills"
        self.assertEqual((copied / "synthetic-personal/SKILL.md").read_text(), original)
        self.assertEqual(native.call_args_list[0].args[1]["skill_directories"], [str(copied)])
        self.assertEqual(candidate.call_args.args[0]["skill_directories"], [str(copied)])
        self.assertIn("personal_skills", json.loads((self.run / "owner/identities.json").read_text()))

    def test_freeform_tool_arguments_are_preserved_through_staging(self):
        from contextlib import ExitStack
        patch = "*** Begin Patch\n*** Add File: synthetic.txt\n+sample\n*** End Patch"
        self.historical["records"][3].update(name="apply_patch", arguments=patch)
        self.fixture.write_text(json.dumps(self.historical))

        def mutate(events):
            events[2]["data"]["toolRequests"][0].update(name="apply_patch", arguments=patch)
            next(event for event in events if event["type"] == "tool.execution_start")["data"].update(
                toolName="apply_patch", arguments=patch)

        self.mutate_import = mutate
        with ExitStack() as stack:
            self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        staged = json.loads((self.run / "owner" / "imported-prefix.json").read_text())
        request = next(request for event in staged for request in event["data"].get("toolRequests", [])
                       if request["name"] == "apply_patch")
        self.assertEqual(request["arguments"], patch)

    def test_failed_result_import_encoding_preserves_source_without_mutating_fixture(self):
        from contextlib import ExitStack
        original = json.loads(json.dumps(self.historical["records"]))
        original_import = self.import_double

        def checked_import(restoration, history, **kwargs):
            records = [json.loads(line) for line in history.read_text().splitlines()]
            failed = next(record for record in records
                          if record["type"] == "tool-result" and not record["success"])
            self.assertEqual(failed.get("error"), {"message": "Synthetic preserved failure"},
                             "Failed public import result requires the exact source error object")
            self.assertNotIn("content", failed)
            self.assertEqual(self.historical["records"], original)
            return original_import(restoration, history, **kwargs)

        self.import_double = checked_import
        with ExitStack() as stack:
            self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual(self.historical["records"], original)
        from session_restore import public_import_records
        changed_error = json.loads(json.dumps(original))
        changed_error[5]["error"] = {"message": "Different failure"}
        with self.assertRaisesRegex(ValueError, "error differs from source"):
            public_import_records(changed_error)

    def test_import_scaffold_is_preserved_without_inventing_source_timestamps(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        staged = json.loads((self.run / "owner/imported-prefix.json").read_text())
        starts = [event for event in staged if event["type"] == "tool.execution_start"]
        self.assertEqual(len(starts), 2)
        self.assertTrue(all(event["timestamp"] == "2002-01-01T00:00:00Z" for event in starts))
        self.assertEqual(staged[0]["timestamp"], "2002-01-01T00:00:00Z")
        self.assertEqual(staged[0]["data"]["startTime"], self.historical["records"][0]["createdAt"])
        correspondence = result["locator"]["correspondence"]
        self.assertTrue(all(item["source_timestamp"] == "2001-01-01T00:00:00Z"
                            and item["imported_timestamp"] == "2002-01-01T00:00:00Z"
                            for item in correspondence))
        source_ids = {item["native_event_id"] for item in correspondence}
        self.assertTrue(all(event["timestamp"] == "2001-01-01T00:00:00Z"
                            for event in staged if event["id"] in source_ids))

    def test_missing_changed_or_child_import_starts_refuse_before_helper(self):
        from contextlib import ExitStack
        for failure in ("missing", "arguments", "child", "duplicate", "reordered"):
            with self.subTest(failure=failure):
                self.run = self.root / f"run-start-{failure}"
                def mutate(events):
                    event = next(event for event in events if event["type"] == "tool.execution_start")
                    if failure == "missing":
                        events.remove(event)
                    elif failure == "arguments":
                        event["data"]["arguments"] = {"path": "different.txt"}
                    elif failure == "child":
                        event["data"]["agentId"] = "synthetic-child"
                    elif failure == "duplicate":
                        events.append({**event, "id": str(uuid.uuid4())})
                    else:
                        events.remove(event)
                        result_index = next(index for index, result in enumerate(events)
                                            if result["type"] == "tool.execution_complete")
                        events.insert(result_index + 1, event)
                self.mutate_import = mutate
                with ExitStack() as stack:
                    native, candidate = self.patches(stack)
                    result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["status"], "FAILED")
                self.assertIn("tool start", result["firsterror"])
                native.assert_not_called()
                candidate.assert_not_called()

    def test_missing_source_timestamp_refuses_before_import(self):
        from contextlib import ExitStack
        del self.historical["source_mapping"][0]["timestamp"]
        self.fixture.write_text(json.dumps(self.historical))
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            imported = stack.enter_context(mock.patch("session_restore.import_session"))
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("source grouping", result["firsterror"])
        imported.assert_not_called()
        native.assert_not_called()
        candidate.assert_not_called()

    def test_changed_role_error_grouping_or_creation_time_blocks_helper(self):
        from contextlib import ExitStack
        for failure in ("role", "error", "request", "time"):
            with self.subTest(failure=failure):
                self.run = self.root / f"run-{failure}"
                def mutate(events):
                    if failure == "role":
                        events[2]["type"] = "user.message"
                    elif failure == "error":
                        next(event for event in events
                             if event["type"] == "tool.execution_complete")["data"]["success"] = True
                    elif failure == "request":
                        events[2]["data"]["toolRequests"].reverse()
                    else:
                        events[0]["data"]["startTime"] = "2000-01-01T00:00:00Z"
                self.mutate_import = mutate
                with ExitStack() as stack:
                    native, candidate = self.patches(stack)
                    result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["setup_error_code"], "NATIVE_CONTEXT_SETUP_UNSUPPORTED")
                native.assert_not_called()
                candidate.assert_not_called()

    def test_historical_send_and_ambiguous_boundary_refuse(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments(), model_send=True)
        self.assertIn("forbids model sends", result["firsterror"])
        self.assertTrue(result["claim"].startswith("Historical setup observations only"))
        native.assert_not_called()
        candidate.assert_not_called()
        self.historical["skill_events"][-1]["records_before"] = 3
        self.fixture.write_text(json.dumps(self.historical))
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertIn("boundary", result["firsterror"])
        native.assert_not_called()

    def test_child_actor_or_duplicate_source_group_cannot_be_flattened(self):
        from contextlib import ExitStack
        import copy
        original = copy.deepcopy(self.historical)
        for failure in ("child", "group"):
            with self.subTest(failure=failure):
                self.historical = copy.deepcopy(original)
                if failure == "child":
                    self.historical["skill_events"][6]["actor_scope"] = "root"
                else:
                    self.historical["source_mapping"][1]["record_indices"].append(4)
                self.fixture.write_text(json.dumps(self.historical))
                with ExitStack() as stack:
                    native, candidate = self.patches(stack)
                    imported = stack.enter_context(mock.patch("session_restore.import_session"))
                    result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["status"], "FAILED")
                imported.assert_not_called()
                native.assert_not_called()
                candidate.assert_not_called()

    def test_setup_failure_retains_first_error_and_owned_shutdown_receipt(self):
        from contextlib import ExitStack
        def failed_setup(operation, config):
            skill_eval.write_json(Path(config["output"]), {
                "status": "ERROR", "error": {"message": "Synthetic first setup error"},
                "shutdown_errors": [{"message": "Synthetic later shutdown error"}], "model_calls": 0,
            })
            raise ValueError("Synthetic first setup error")
        with ExitStack() as stack:
            _, candidate = self.patches(stack)
            native = stack.enter_context(mock.patch("skill_eval._native_workflow_probe", side_effect=failed_setup))
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["firsterror"], "Synthetic first setup error")
        self.assertEqual(result["setup"]["shutdown_errors"][0]["message"], "Synthetic later shutdown error")
        self.assertEqual(native.call_count, 1)
        candidate.assert_not_called()


class NativeRecordedContextTests(unittest.TestCase):
    arguments = NativeContextCalibrationTests.arguments
    patches = NativeContextCalibrationTests.patches

    def setUp(self):
        NativeContextCalibrationTests.setUp(self)
        self.source_id, self.trigger_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.context = {
            "source": f"/synthetic/{self.source_id}/events.jsonl", "source_cutoff_offset": 100,
            "last_source_event": self.trigger_id, "source_bytes_consumed": 200,
            "source_events_consumed": 12, "compactions_consumed": 2,
            "reader": "Synthetic recorded reader", "mode": "recorded/live projection",
            "selected_model": "fixture-model", "reasoning_effort": "low", "context_tier": None,
            "original_user_messages": ["Synthetic original request", "Synthetic trigger"],
            "handoff_context": None,
            "invoked_skills": [
                {"name": f"synthetic-{index}", "path": f"synthetic/{index}/SKILL.md",
                 "content": f"Synthetic body {index}", "allowedTools": [], "source": "plugin",
                 "invokedAtTurn": index + 1000}
                for index in range(22)],
            "system_context_messages": [
                {"role": "system", "content": "Synthetic system", "metadata": {"source": "fixture"}}],
            "chat_messages": [
                {"role": "developer", "content": "Synthetic developer"},
                {"role": "user", "content": "Wrapped synthetic original",
                 "copilotResponsesReasoning": {"effort": "low"}, "__copilotAutoApprovalHumanMessageIndex": 147},
                {"role": "assistant", "content": None, "reasoning_opaque": "synthetic opaque",
                 "encrypted_content": "synthetic encrypted", "reasoningBlocks": [{"type": "synthetic"}],
                 "providerId": "synthetic-provider", "serverTools": {"items": []}, "apiCallId": "synthetic-api",
                 "phase": "commentary", "tool_calls": [
                     {"id": "synthetic-call", "type": "function",
                      "function": {"name": "view", "arguments": '{ "path": "synthetic.txt" }'}},
                     {"id": "custom_synthetic", "type": "custom",
                      "custom": {"name": "apply_patch", "input": "synthetic input"}}]},
                {"role": "tool", "tool_call_id": "synthetic-call", "content": "Synthetic result",
                 "__copilotMessageSource": {"kind": "tool", "name": "view"}},
                {"role": "tool", "tool_call_id": "custom_synthetic", "content": "Synthetic failure text"},
                {"role": "assistant", "content": "Synthetic final"},
                {"role": "user", "content": "Wrapped Synthetic trigger",
                 "copilotResponsesReasoning": {"effort": "low"}, "__copilotAutoApprovalHumanMessageIndex": 161},
            ],
        }
        self.canonical = self.root / "recorded.json"
        self.canonical.write_text(json.dumps(self.context, indent=2) + "\n")
        self.canonical.chmod(0o600)
        self.source_event = {
            "id": self.trigger_id, "type": "user.message", "timestamp": "2026-01-01T00:00:00Z",
            "data": {"content": "Synthetic trigger", "transformedContent": "Wrapped Synthetic trigger"},
        }
        self.source_event_path = self.root / "source-events/trigger.jsonl"
        self.source_event_path.parent.mkdir()
        self.source_event_path.write_bytes((json.dumps(self.source_event) + "\n").encode())
        self.source_event_path.chmod(0o600)
        self.recorded = {
            "schema_version": 3, "provenance": "source-bound-historical",
            "recorded_context": {"path": self.canonical.name, "sha256": digest(self.canonical),
                                 "reader_revision": "1" * 40, "original_runtime_revision": "2" * 40,
                                 "cutoff_offset": 100},
            "consumer": {"cli_version": "1.0.97", "cli_sha256": digest(self.cli),
                         "sdk_sha256": "d336d72bd0f597d39c1c75732e5eb5b07cd43e65e81b45f90413ee86e69cb406"},
            "restoration": {"source_session_id": self.source_id, "cutoff_event_id": self.trigger_id,
                            "skill_context": "recorded-target-context"},
            "trigger": {"event_id": self.trigger_id, "timestamp": "2026-01-01T00:00:00Z",
                        "content": "Synthetic trigger", "source_line_sha256": digest(self.source_event_path),
                        "source_event_path": "source-events/trigger.jsonl"},
            "snapshot": historical_snapshot_fixture(), "required_tools": ["skill", "view", "sql", "manage_schedule"],
            "personal_instructions": "Synthetic personal", "candidate_permissions": {
                "write_paths": [], "shell_commands": []},
            "limitations": ["Synthetic unit fixture only; no native consumption"],
        }
        self.fixture.write_text(json.dumps(self.recorded))
        schemas = {
            "SkillInvoked": ("skill.invoked", "name path content allowedTools source invokedAtTurn"),
            "SystemMessage": ("system.message", "role content metadata"),
            "InstructionUpdate": ("instruction.update", "authority boundary lifetime fallback content"),
            "UserMessage": ("user.message", "content transformedContent source responsesReasoning"),
            "AssistantMessage": ("assistant.message",
                                 "content messageId reasoningOpaque encryptedContent reasoningBlocks "
                                 "serverTools providerId apiCallId phase toolRequests"),
            "ToolExecutionStart": ("tool.execution_start", "toolCallId toolName arguments"),
            "ToolExecutionComplete": ("tool.execution_complete", "toolCallId success result"),
        }
        with (self.sdk.parent / "generated/session-events.d.ts").open("a") as stream:
            for name, (kind, fields) in schemas.items():
                stream.write(f'export interface {name}Event {{\ntype: "{kind}";\ndata: {name}Data;\n}}\n')
                stream.write(f"export interface {name}Data {{\n")
                stream.writelines(f"{field}?: unknown;\n" for field in fields.split())
                stream.write("}\n")

    def import_double(self, restoration, history, **kwargs):
        from session_restore import semantic_projection

        self.order.append("import-exit")
        seed = [json.loads(line) for line in history.read_text().splitlines()]
        self.assertEqual(len(seed), 1)
        self.assertEqual(set(seed[0]), {"type", "version", "externalId", "createdAt", "title"})
        self.assertEqual(seed[0]["type"], "session")
        self.assertEqual(seed[0]["externalId"], self.source_id)
        self.assertEqual(seed[0]["title"], "owned-recorded-context")
        self.assertEqual(semantic_projection(seed), [])
        home = Path(kwargs["receipt_path"]).parents[1] / "candidate-home"
        self.journal = home / "session-state" / self.session_id / "events.jsonl"
        self.journal.parent.mkdir(parents=True)
        self.journal.write_text(json.dumps({
            "id": str(uuid.uuid4()), "parentId": None, "type": "session.start",
            "timestamp": seed[0]["createdAt"], "data": {"sessionId": self.session_id},
        }) + "\n")
        skill_eval.write_json(kwargs["receipt_path"], {
            "status": "PASS", "session_id": self.session_id, "exit_code": 0, "history_sha256": digest(history)})
        return self.session_id

    def probe_double(self, operation, config, *, consumer):
        self.assertEqual(consumer, self.recorded["consumer"])
        self.order.append(operation)
        self.assertEqual(self.journal.read_bytes(), (self.run / "owner/journal-staged.jsonl").read_bytes())
        self.assertEqual((self.run / "owner/canonical-recorded-context.json").read_bytes(), self.canonical.read_bytes())
        self.assertEqual((self.run / "owner/source-trigger-event.jsonl").read_bytes(),
                         self.source_event_path.read_bytes())
        goal = self.journal.with_name("autopilot-objective.json")
        if "completed_objective" in self.recorded:
            self.assertEqual(goal.read_bytes(), self.completed_path.read_bytes())
            self.assertEqual(goal.stat().st_mode & 0o777, 0o600)
        else:
            self.assertFalse(goal.exists())
        return {"status": {"setup": "SETUP_OBSERVED", "observe": "OBSERVED", "cleanup": "CLEANED"}[operation]}

    def add_completed_objective(self):
        store = {
            "version": 1, "nextId": 40,
            "current": {"id": 37, "objective": "Synthetic completed objective", "status": "completed",
                        "autopilotOrigin": "objective", "continuationCount": 2, "turnCount": 9,
                        "tokenCount": 456, "creditCountNanoAiu": "123456789012345", "resumeCount": 3,
                        "createdAt": "2001-01-01T01:02:03.004Z", "updatedAt": "2002-02-02T03:04:05.006Z",
                        "completionSummary": "Synthetic completion"},
        }
        self.completed_path = self.root / "completed-objective.json"
        self.completed_path.write_text(json.dumps(store, indent=2) + "\n")
        self.completed_path.chmod(0o600)
        self.recorded["completed_objective"] = {
            "path": self.completed_path.name, "sha256": digest(self.completed_path)}
        self.fixture.write_text(json.dumps(self.recorded))
        return store

    def test_completed_objective_is_copied_exactly_before_any_resume(self):
        from contextlib import ExitStack
        store = self.add_completed_objective()
        original = self.completed_path.read_bytes()
        calibration = self.root / "prior-completed-calibration"
        (calibration / "owner").mkdir(parents=True)
        skill_eval.write_json(calibration / "owner/identities.json", {"session_id": str(uuid.uuid4())})
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(
                **self.arguments(), source_preparation_only=True, calibration_root=calibration)
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual([call.args[0] for call in native.call_args_list], ["setup", "observe", "cleanup"])
        descriptor = result["locator"]["completed_objective"]
        self.assertEqual(Path(descriptor["path"]).read_bytes(), original)
        self.assertEqual(descriptor["sha256"], self.recorded["completed_objective"]["sha256"])
        self.assertEqual(json.loads(self.journal.with_name("autopilot-objective.json").read_bytes()), store)
        self.assertEqual(self.completed_path.read_bytes(), original)
        candidate.assert_not_called()

    def test_completed_objective_rejects_active_malformed_or_unbound_source(self):
        from session_restore import completed_objective_state
        store = self.add_completed_objective()
        self.assertEqual(completed_objective_state(store), {
            key: store["current"][key] for key in
            ("id", "objective", "status", "turnCount", "creditCountNanoAiu", "completionSummary")})
        for fault in ("active", "paused", "version", "null", "missing-counter", "counter",
                      "id", "nextId", "credits", "timestamp", "unknown", "hash", "mode", "escape"):
            with self.subTest(fault=fault):
                fixture = json.loads(json.dumps(self.recorded))
                changed = json.loads(json.dumps(store))
                if fault in ("active", "paused"):
                    changed["current"]["status"] = fault
                elif fault == "version":
                    changed["version"] = 2
                elif fault == "null":
                    changed["current"] = None
                elif fault == "missing-counter":
                    del changed["current"]["resumeCount"]
                elif fault == "counter":
                    changed["current"]["tokenCount"] = -1
                elif fault == "id":
                    changed["current"]["id"] = True
                elif fault == "nextId":
                    changed["nextId"] = changed["current"]["id"]
                elif fault == "credits":
                    changed["current"]["creditCountNanoAiu"] = "not-a-decimal"
                elif fault == "timestamp":
                    changed["current"]["updatedAt"] = "not-a-time"
                elif fault == "unknown":
                    changed["current"]["unexpected"] = "Synthetic extra field"
                self.completed_path.write_text(json.dumps(changed))
                fixture["completed_objective"]["sha256"] = (
                    "0" * 64 if fault == "hash" else digest(self.completed_path))
                if fault == "mode":
                    self.completed_path.chmod(0o644)
                if fault == "escape":
                    fixture["completed_objective"]["path"] = "../completed-objective.json"
                try:
                    with self.assertRaises(ValueError):
                        skill_eval._validate_historical_context_fixture(fixture, root=self.root)
                finally:
                    self.completed_path.chmod(0o600)

    def test_completed_objective_refuses_occupied_or_escaped_native_destinations(self):
        from contextlib import ExitStack
        self.add_completed_objective()
        original_import = self.import_double
        for fault in ("occupied", "symlink", "namespace-symlink"):
            with self.subTest(fault=fault), ExitStack() as stack:
                self.run = self.root / f"destination-{fault}"
                target = self.root / f"outside-{fault}.json"
                target.write_text("Synthetic untouched destination")
                def import_with_existing_destination(restoration, history, **kwargs):
                    session = original_import(restoration, history, **kwargs)
                    goal = self.journal.with_name("autopilot-objective.json")
                    if fault == "occupied":
                        goal.write_text("Synthetic occupied goal")
                    elif fault == "symlink":
                        goal.symlink_to(target)
                    else:
                        escaped = self.root / "escaped-namespace"
                        self.journal.parent.rename(escaped)
                        self.journal.parent.symlink_to(escaped, target_is_directory=True)
                    return session
                self.import_double = import_with_existing_destination
                native, candidate = self.patches(stack)
                result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["status"], "FAILED")
                self.assertRegex(result["firsterror"], "destination must be absent|unaliased single-link")
                self.assertEqual(target.read_text(), "Synthetic untouched destination")
                if fault == "occupied":
                    self.assertEqual(self.journal.with_name("autopilot-objective.json").read_text(),
                                     "Synthetic occupied goal")
                elif fault == "symlink":
                    self.assertTrue(self.journal.with_name("autopilot-objective.json").is_symlink())
                else:
                    self.assertFalse((self.root / "escaped-namespace/autopilot-objective.json").exists())
                self.assertFalse((self.run / "owner/journal-staged.jsonl").exists())
                native.assert_not_called()
                candidate.assert_not_called()

    def test_source_preparation_passes_original_103_consumer_to_all_receipt_checks(self):
        from contextlib import ExitStack
        banner = "GitHub Copilot CLI 1.0.103.\nRun 'copilot update' to check for updates."
        self.recorded["consumer"]["cli_version"] = banner
        self.fixture.write_text(json.dumps(self.recorded))
        calibration = self.root / "prior-calibration"
        (calibration / "owner").mkdir(parents=True)
        skill_eval.write_json(calibration / "owner/identities.json", {"session_id": str(uuid.uuid4())})
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            stack.enter_context(mock.patch("skill_eval.copilot_identity", return_value={"version": banner}))
            result = skill_eval._run_native_context_calibration(
                **self.arguments(), source_preparation_only=True, calibration_root=calibration)
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual(self.order, ["import-exit", "setup", "observe", "cleanup"])
        self.assertEqual([call.args[0] for call in native.call_args_list], ["setup", "observe", "cleanup"])
        for call in native.call_args_list:
            self.assertEqual(call.kwargs, {"consumer": self.recorded["consumer"]})
        candidate.assert_not_called()
        self.assertIn("behavioral admission unproved", result["claim"])

    def runtime_receipt_fixture(self, operation, name):
        fields = ["home", "os_home", "cwd", "prompt_path", "event_log",
                  "plugin_path", "prefix_file", "context_fixture_file"]
        config = {key: str(self.root / key) for key in fields}
        config.update(cli=str(self.cli), sdk=str(self.sdk), output=str(self.root / f"{name}.json"),
                      profile="native-historical-context", session_id=self.session_id,
                      model="fixture-model", effort="low",
                      candidate_permissions={"write_paths": [], "shell_commands": []})
        receipt = {
            "cli": config["cli"], "sdk": config["sdk"], "session_id": self.session_id,
            "profile": config["profile"], "connection": {"path": config["cli"]},
            "runtime_identity": {"version": "1.0.103", "protocolVersion": 3},
            "shutdown_errors": [], "model_calls": 0,
            "status": {"setup": "SETUP_OBSERVED", "observe": "OBSERVED", "cleanup": "CLEANED"}[operation],
        }
        consumer = {"cli_version": "GitHub Copilot CLI 1.0.103.\nRun 'copilot update' to check for updates.",
                    "cli_sha256": digest(self.cli), "sdk_sha256": digest(self.sdk)}
        return config, receipt, consumer

    def test_selected_103_receipts_and_legacy_97_receipts_keep_distinct_pins(self):
        for operation in ("setup", "observe", "cleanup"):
            for variant in ("103-banner", "103-token", "97-legacy", "97-legacy-suffix"):
                with self.subTest(operation=operation, variant=variant):
                    config, receipt, consumer = self.runtime_receipt_fixture(operation, f"{operation}-{variant}")
                    if variant == "103-token":
                        consumer["cli_version"] = "1.0.103"
                    if variant.startswith("97"):
                        consumer = None
                        receipt["runtime_identity"]["version"] = (
                            "1.0.97-2" if variant.endswith("suffix") else "1.0.97")
                    def execute(command, **kwargs):
                        Path(config["output"]).write_text(json.dumps(receipt))
                        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
                    with (
                        mock.patch("skill_eval.subprocess.run", side_effect=execute) as process,
                        mock.patch("skill_eval.personal_instruction_environment", return_value={}),
                    ):
                        self.assertEqual(skill_eval._native_workflow_probe(
                            operation, config, **({"consumer": consumer} if consumer is not None else {})), receipt)
                    process.assert_called_once()

    def test_selected_consumer_refuses_wrong_absent_malformed_or_substituted_runtime_pins(self):
        failures = (
            "wrong97", "different-release", "missing-version", "null-version", "nonstring-version",
            "malformed-version", "missing-identity", "malformed-identity", "missing-consumer",
            "bad-consumer-version", "bad-consumer-hash", "absent-consumer-hash",
            "cli-hash", "sdk-hash", "cli-path", "sdk-path", "connection-path",
            "missing-cli-path", "missing-sdk-path", "missing-connection-path",
            "missing-file", "relative-file", "aliased-file", "legacy103",
        )
        for failure in failures:
            with self.subTest(failure=failure):
                config, receipt, consumer = self.runtime_receipt_fixture("setup", failure)
                runtime = receipt["runtime_identity"]
                if failure == "wrong97":
                    runtime["version"] = "1.0.97"
                elif failure == "different-release":
                    runtime["version"] = "1.0.1031"
                elif failure == "missing-version":
                    del runtime["version"]
                elif failure in ("null-version", "nonstring-version", "malformed-version"):
                    runtime["version"] = {"null-version": None, "nonstring-version": 103,
                                          "malformed-version": "GitHub Copilot CLI 1.0.103."}[failure]
                elif failure == "missing-identity":
                    del receipt["runtime_identity"]
                elif failure == "malformed-identity":
                    receipt["runtime_identity"] = None
                elif failure == "missing-consumer":
                    consumer = {}
                elif failure == "bad-consumer-version":
                    consumer["cli_version"] = "unrecognized 1.0.103"
                elif failure == "bad-consumer-hash":
                    consumer["cli_sha256"] = None
                elif failure == "absent-consumer-hash":
                    del consumer["sdk_sha256"]
                elif failure in ("cli-hash", "sdk-hash"):
                    consumer[f"{failure.split('-')[0]}_sha256"] = "0" * 64
                elif failure in ("cli-path", "sdk-path"):
                    receipt[failure.split("-")[0]] += "-different"
                elif failure == "connection-path":
                    receipt["connection"]["path"] += "-different"
                elif failure in ("missing-cli-path", "missing-sdk-path"):
                    del receipt[failure.split("-")[1]]
                elif failure == "missing-connection-path":
                    receipt["connection"] = {}
                elif failure in ("missing-file", "relative-file", "aliased-file"):
                    path = self.root / "absent"
                    if failure == "relative-file":
                        path = Path("relative-copilot")
                    if failure == "aliased-file":
                        path = self.root / "aliased-copilot"
                        path.symlink_to(self.cli)
                    config["cli"] = receipt["cli"] = receipt["connection"]["path"] = str(path)
                elif failure == "legacy103":
                    consumer = None
                def execute(command, **kwargs):
                    Path(config["output"]).write_text(json.dumps(receipt))
                    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
                with (
                    mock.patch("skill_eval.subprocess.run", side_effect=execute),
                    mock.patch("skill_eval.personal_instruction_environment", return_value={}),
                ):
                    with self.assertRaisesRegex(ValueError, "consumer|pinned runtime"):
                        skill_eval._native_workflow_probe("setup", config, consumer=consumer)

    def candidate_double(self, config, **kwargs):
        self.order.append("preflight")
        self.assertTrue(kwargs["preflight_only"])
        self.assertEqual(Path(config["prompt_path"]).read_text(), self.recorded["trigger"]["content"])
        return {"status": "PREFLIGHT_OBSERVED", "model_send_calls": 0}

    def test_recorded_path_preserves_population_fields_and_defers_trigger_after_empty_import(self):
        from contextlib import ExitStack
        original = self.canonical.read_bytes()
        with ExitStack() as stack:
            self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "CONTEXT_SETUP_OBSERVED", result["firsterror"])
        self.assertEqual(self.order, ["import-exit", "setup", "preflight", "observe", "cleanup"])
        locator = result["locator"]
        self.assertEqual(len(locator["root_skills"]), 22)
        events = [json.loads(line) for line in self.journal.read_text().splitlines()]
        self.assertFalse(any(event["type"] == "session.compaction_complete" for event in events))
        self.assertEqual([event["data"]["content"] for event in events if event["type"] == "user.message"], [""])
        assistant = next(event["data"] for event in events if event["type"] == "assistant.message")
        self.assertEqual(assistant["providerId"], "synthetic-provider")
        self.assertEqual(assistant["encryptedContent"], "synthetic encrypted")
        self.assertEqual(assistant["reasoningBlocks"], [{"type": "synthetic"}])
        self.assertEqual(assistant["toolRequests"][0]["arguments"], '{ "path": "synthetic.txt" }')
        self.assertEqual(assistant["toolRequests"][1]["type"], "custom")
        source_indices = [item["index"] for item in locator["correspondence"] if item["collection"] == "chat_messages"]
        self.assertEqual(source_indices, list(range(6)))
        deferred = json.loads(Path(locator["trigger_file"]).read_text())
        self.assertEqual(deferred["event_id"], self.trigger_id)
        self.assertEqual(deferred["recorded_message"], self.context["chat_messages"][-1])
        self.assertEqual(deferred["source_event_path"], "source-trigger-event.jsonl")
        self.assertEqual(digest(self.run / "owner" / deferred["source_event_path"]),
                         deferred["source_line_sha256"])
        self.assertEqual(original, self.canonical.read_bytes())
        self.assertTrue(any("approval indices" in item for item in locator["limitations"]))

    def test_recorded_trigger_refuses_changed_raw_or_transformed_source_bindings(self):
        canonical_bytes = self.canonical.read_bytes()
        for fault in ("hash", "fixture-content", "id", "timestamp", "content", "type",
                      "transformed", "null-transformed", "absent-transformed", "canonical-transformed"):
            with self.subTest(fault=fault):
                fixture = json.loads(json.dumps(self.recorded))
                event = json.loads(json.dumps(self.source_event))
                context = json.loads(json.dumps(self.context))
                if fault == "fixture-content":
                    fixture["trigger"]["content"] = "synthetic mismatch diagnostic only"
                elif fault == "id":
                    event["id"] = str(uuid.uuid4())
                elif fault == "timestamp":
                    event["timestamp"] = "2026-01-02T00:00:00Z"
                elif fault == "content":
                    event["data"]["content"] = "Changed synthetic raw content"
                elif fault == "type":
                    event["type"] = "assistant.message"
                elif fault == "transformed":
                    event["data"]["transformedContent"] = "Changed synthetic transformed content"
                elif fault == "null-transformed":
                    event["data"]["transformedContent"] = None
                elif fault == "absent-transformed":
                    del event["data"]["transformedContent"]
                elif fault == "canonical-transformed":
                    context["chat_messages"][-1]["content"] = "Changed synthetic canonical trigger"
                self.source_event_path.write_text(json.dumps(event) + "\n")
                fixture["trigger"]["source_line_sha256"] = (
                    "0" * 64 if fault == "hash" else digest(self.source_event_path))
                self.canonical.write_bytes(
                    json.dumps(context).encode() if fault == "canonical-transformed" else canonical_bytes)
                fixture["recorded_context"]["sha256"] = digest(self.canonical)
                with self.assertRaisesRegex(ValueError, "Original trigger"):
                    skill_eval._validate_historical_context_fixture(fixture, root=self.root)

    def test_recorded_trigger_falls_back_to_raw_content_only_when_transform_is_absent(self):
        del self.source_event["data"]["transformedContent"]
        self.context["chat_messages"][-1]["content"] = self.source_event["data"]["content"]
        self.source_event_path.write_text(json.dumps(self.source_event) + "\n")
        self.canonical.write_text(json.dumps(self.context))
        self.recorded["trigger"]["source_line_sha256"] = digest(self.source_event_path)
        self.recorded["recorded_context"]["sha256"] = digest(self.canonical)
        validated = skill_eval._validate_historical_context_fixture(self.recorded, root=self.root)
        self.assertEqual(validated["trigger_source_bytes"], self.source_event_path.read_bytes())

    def test_recorded_trigger_preserves_owner_file_defenses(self):
        for fault in ("missing-path", "absolute", "traversal", "mode", "symlink", "hardlink"):
            with self.subTest(fault=fault):
                fixture = json.loads(json.dumps(self.recorded))
                alias = self.root / f"{fault}.jsonl"
                if fault == "missing-path":
                    del fixture["trigger"]["source_event_path"]
                elif fault == "absolute":
                    fixture["trigger"]["source_event_path"] = str(self.source_event_path)
                elif fault == "traversal":
                    fixture["trigger"]["source_event_path"] = "../trigger.jsonl"
                elif fault == "mode":
                    self.source_event_path.chmod(0o644)
                else:
                    if fault == "symlink":
                        alias.symlink_to(self.source_event_path)
                    else:
                        alias.hardlink_to(self.source_event_path)
                    fixture["trigger"]["source_event_path"] = alias.name
                try:
                    with self.assertRaises(ValueError):
                        skill_eval._validate_historical_context_fixture(fixture, root=self.root)
                finally:
                    self.source_event_path.chmod(0o600)
                    if alias.exists():
                        alias.unlink()

    def test_unmapped_provider_field_refuses_before_import_without_discarding_it(self):
        from contextlib import ExitStack
        self.context["chat_messages"][2]["unmapped_provider_state"] = "synthetic"
        self.canonical.write_text(json.dumps(self.context))
        self.recorded["recorded_context"]["sha256"] = digest(self.canonical)
        self.fixture.write_text(json.dumps(self.recorded))
        with ExitStack() as stack:
            self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("assistant fields", result["firsterror"])
        self.assertEqual(self.order, [])
        self.assertFalse(self.run.exists())

    def test_changed_artifact_or_cutoff_binding_refuses_before_import(self):
        from contextlib import ExitStack
        import copy
        for key, value in (("sha256", "f" * 64), ("cutoff_offset", 101)):
            with self.subTest(key=key), ExitStack() as stack:
                fixture = copy.deepcopy(self.recorded)
                fixture["recorded_context"][key] = value
                self.fixture.write_text(json.dumps(fixture))
                self.patches(stack)
                result = skill_eval._run_native_context_calibration(**self.arguments())
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(self.order, [])
                self.assertFalse(self.run.exists())

    def test_schema_without_provider_field_cannot_mutate_imported_journal(self):
        from contextlib import ExitStack
        schema = self.sdk.parent / "generated/session-events.d.ts"
        schema.write_text(schema.read_text().replace("providerId?: unknown;\n", ""))
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["setup_error_code"], "NATIVE_CONTEXT_SETUP_UNSUPPORTED")
        self.assertEqual(self.order, ["import-exit"])
        self.assertEqual(len(self.journal.read_text().splitlines()), 1)
        native.assert_not_called()
        candidate.assert_not_called()

    def test_accepted_named_import_without_journal_preserves_bootstrap_failure(self):
        from contextlib import ExitStack

        def accepted_without_journal(restoration, history, **kwargs):
            self.order.append("import-exit")
            skill_eval.write_json(kwargs["receipt_path"], {
                "status": "PASS", "session_id": self.session_id, "exit_code": 0,
                "history_sha256": digest(history)})
            return self.session_id

        self.import_double = accepted_without_journal
        with ExitStack() as stack:
            native, candidate = self.patches(stack)
            result = skill_eval._run_native_context_calibration(**self.arguments())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["setup_error_code"], "NATIVE_CONTEXT_SETUP_UNSUPPORTED")
        self.assertEqual(result["firsterror"], "Native journal is not an owned unaliased single-link file")
        self.assertEqual(self.order, ["import-exit"])
        self.assertFalse((self.run / "owner/journal-staged.jsonl").exists())
        native.assert_not_called()
        candidate.assert_not_called()


class NativeRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.packet = self.root / "packet"
        (self.packet / "candidate").mkdir(parents=True)
        (self.packet / "candidate" / "code.py").write_text("source\n")
        self.session_id = str(uuid.uuid4())
        self.model = "gpt-example"

    def tearDown(self):
        self.temp.cleanup()

    def events(self):
        return [
            {"type": "session.start", "data": {
                "sessionId": self.session_id, "selectedModel": self.model}},
            {"type": "tool.execution_start", "data": {
                "toolName": "view", "toolCallId": "read", "arguments": {"path": "candidate/code.py"}}},
            {"type": "tool.execution_complete", "data": {
                "toolCallId": "read", "success": True, "result": {"content": "source payload"}}},
            {"type": "assistant.message", "data": {"model": self.model, "content": "answer"}},
            {"type": "session.shutdown", "data": {}},
        ]

    def encoded(self, events):
        return ("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n").encode()

    def parse(self, content):
        return parse_native_run(
            content, session_id=self.session_id, expected_model=self.model, cwd=self.packet)

    def test_native_answer_models_views_and_byte_marker_without_result_event(self):
        events = self.events()
        events.insert(1, {"type": "assistant.message", "data": {
            "model": self.model, "content": "", "toolRequests": [{"toolCallId": "read"}]}})
        events.insert(-1, {"type": "session.usage_checkpoint", "data": {"totalNanoAiu": 1}})
        # A Unicode line separator inside source text is not a JSONL record boundary.
        events[3]["data"]["result"]["content"] = "source\u2028payload"
        content = self.encoded(events)
        parsed = self.parse(content)
        self.assertEqual(parsed["answer"], "answer")
        self.assertEqual(parsed["models"], [self.model])
        self.assertEqual(parsed["viewed_paths"], ["candidate/code.py"])
        self.assertEqual(parsed["tool_calls"], 1)
        self.assertEqual(parsed["event_count"], len(events))
        self.assertEqual(parsed["event_sha256"], hashlib.sha256(content).hexdigest())
        self.assertNotIn("source", json.dumps(parsed))
        self.assertNotIn("result_exit_code", parsed)
        self.assertEqual(self.parse(content[:-1])["answer"], "answer")

    def test_large_native_reader_keeps_original_digest_and_strict_terminal_checks(self):
        events = self.events()
        path = self.root / "large-native.jsonl"
        with path.open("wb") as stream:
            stream.write(self.encoded(events[:1]))
            for index in range(2):
                start = {**events[1], "data": {**events[1]["data"], "toolCallId": str(index)}}
                complete = {**events[2], "data": {
                    **events[2]["data"], "toolCallId": str(index),
                    "result": {"content": "x" * (17 * 1024 * 1024)},
                }}
                stream.write(self.encoded([start, complete]))
            stream.write(self.encoded(events[3:]).replace(b"\n", b"\r\n").rstrip(b"\r\n"))
        self.assertGreater(path.stat().st_size, measurement.MAX_EVENT_BYTES)
        expected = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                expected.update(chunk)
        with path.open("rb") as stream:
            parsed = self.parse(stream)
        self.assertEqual(parsed["event_sha256"], expected.hexdigest())
        self.assertEqual(parsed["event_count"], 7)
        self.assertEqual(parsed["answer"], "answer")
        self.assertEqual(parsed["tool_calls"], 2)
        self.assertEqual(parsed["viewed_paths"], ["candidate/code.py"] * 2)
        self.assertNotIn("content", parsed)
        with path.open("ab") as stream:
            stream.write(b'\n{"type":"session.usage_checkpoint","data":{}}\n')
        with path.open("rb") as stream, self.assertRaisesRegex(ValueError, "after session shutdown"):
            self.parse(stream)

    def test_native_reader_bound_is_raw_bytes_and_never_an_unbounded_read(self):
        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if not 0 < size <= 65536:
                    raise AssertionError("unbounded native read")
                return super().read(size)

        content = self.encoded(self.events())
        self.assertEqual(self.parse(BoundedReader(content))["event_sha256"], hashlib.sha256(content).hexdigest())
        events = self.events()
        events[2]["data"]["result"]["content"] = "\u00e9" * 200
        record = self.encoded(events[2:3])
        with mock.patch.object(measurement, "MAX_EVENT_BYTES", len(record.decode())), self.assertRaisesRegex(
            ValueError, "record exceeds byte limit",
        ):
            self.parse(BoundedReader(self.encoded(events)))

    def test_missing_corrupt_and_malformed_records_are_refused(self):
        valid = self.encoded(self.events())
        for content in (
            None, b"", b"invalid", b"\xff", b"[]\n", b"null\n", b"1\n", b"{}\n",
            b'{"type":[],"data":{}}\n', b'{"type":"","data":{}}\n',
            b'{"type":"system.message","data":[]}\n',
            b'{"type":"system.message"}\n',
            b'{"type":"system.message","data":{},"data":{}}\n',
            b'{"type":"system.message","data":{"value":NaN}}\n',
            b'{"type":"system.message","data":{"value":Infinity}}\n',
            b"[" * 2000 + b"]" * 2000,
            valid + b"\n", valid + b"invalid", b"\n" + valid,
        ):
            with self.subTest(content=repr(content)[:80]), self.assertRaises(ValueError):
                self.parse(content)
        for data in (None, [], "", 1):
            events = self.events()
            events.insert(1, {"type": "system.message", "data": data})
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.parse(self.encoded(events))

    def test_lifecycle_and_owned_session_refusals(self):
        valid = self.events()
        cases = [
            valid[1:], valid[:-1], [valid[0], *valid], [*valid, valid[-1]],
            [valid[0], valid[-1], *valid[1:-1]], [valid[0], valid[-1]],
            [valid[3], *valid], [*valid, {"type": "user.message", "data": {}}],
            [*valid, {"type": "session.usage_checkpoint", "data": {}}],
            [valid[0], {"type": "session.resume", "data": {}}, *valid[1:]],
            [valid[0], {"type": "result", "data": {}, "exitCode": 0}, *valid[1:]],
        ]
        for index, events in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.parse(self.encoded(events))
        for session in (str(uuid.uuid4()), None, "", [], 1):
            events = self.events()
            events[0]["data"]["sessionId"] = session
            with self.subTest(session=session), self.assertRaisesRegex(ValueError, "identity"):
                self.parse(self.encoded(events))

    def test_selected_model_is_not_actual_assistant_model_evidence(self):
        for index, field in ((0, "selectedModel"), (3, "model")):
            for value in ("other-model", None, [], 1):
                events = self.events()
                events[index]["data"][field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "model"):
                    self.parse(self.encoded(events))
            events = self.events()
            del events[index]["data"][field]
            with self.subTest(missing=field), self.assertRaisesRegex(ValueError, "model"):
                self.parse(self.encoded(events))
        events = self.events()
        events.insert(1, {"type": "assistant.message", "data": {"model": "other-model", "content": ""}})
        with self.assertRaisesRegex(ValueError, "model"):
            self.parse(self.encoded(events))
        with self.assertRaisesRegex(ValueError, "final assistant"):
            self.parse(self.encoded([self.events()[0], self.events()[-1]]))

    def test_tool_pairing_and_success_flags_are_strict(self):
        valid = self.events()
        for events in (
            [valid[0], *valid[2:]], [*valid[:2], *valid[3:]],
            [*valid[:2], valid[1], *valid[2:]],
            [*valid[:3], valid[2], *valid[3:]],
            [*valid[:3], valid[1], valid[2], *valid[3:]],
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                self.parse(self.encoded(events))
        for index, field, values in (
            (1, "toolCallId", (None, "", " ", 1, [])),
            (2, "toolCallId", (None, "", "orphan", 1, [])),
            (2, "success", (None, 0, 1, "true", [])),
            (2, "toolName", ("bash", [], None)),
        ):
            for value in values:
                events = self.events()
                events[index]["data"][field] = value
                with self.subTest(index=index, field=field, value=value), self.assertRaises(ValueError):
                    self.parse(self.encoded(events))
        for index, field in ((1, "toolCallId"), (2, "toolCallId"), (2, "success")):
            events = self.events()
            del events[index]["data"][field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.parse(self.encoded(events))

    def test_successful_views_must_have_resolvable_packet_paths(self):
        for arguments in (None, [], "{}", {}, {"path": None}, {"path": []},
                          {"path": ""}, {"path": " "}, {"path": "missing.py"},
                          {"path": "candidate/\x00"}):
            events = self.events()
            events[1]["data"]["arguments"] = arguments
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.parse(self.encoded(events))
        for requested in ("candidate", str(self.packet / "candidate/code.py"), "candidate/../candidate/code.py"):
            events = self.events()
            events[1]["data"]["arguments"]["path"] = requested
            parsed = self.parse(self.encoded(events))
            self.assertEqual(parsed["viewed_paths"], [
                "candidate" if requested == "candidate" else "candidate/code.py"])

    def test_failed_invalid_views_are_counted_but_never_successful_reads(self):
        for arguments in ({}, None, [], {"path": []}, {"path": "../outside"}, {"path": "\x00"}):
            events = self.events()
            events[1:1] = [
                {"type": "tool.execution_start", "data": {
                    "toolName": "view", "toolCallId": "failed", "arguments": arguments}},
                {"type": "tool.execution_complete", "data": {"toolCallId": "failed", "success": False}},
            ]
            with self.subTest(arguments=arguments):
                parsed = self.parse(self.encoded(events))
                self.assertEqual(parsed["tool_calls"], 2)
                self.assertEqual(parsed["viewed_paths"], ["candidate/code.py"])
                del events[3:5]
                parsed = self.parse(self.encoded(events))
                self.assertEqual(parsed["tool_calls"], 1)
                self.assertEqual(parsed["viewed_paths"], [])

    def test_final_answer_must_follow_tools_and_be_nonempty(self):
        for content in ("", " \n", None, [], 1):
            events = self.events()
            events[3]["data"]["content"] = content
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.parse(self.encoded(events))
        valid = self.events()
        for events in (
            [valid[0], valid[3], *valid[1:3], valid[-1]],
            [valid[0], valid[1], valid[3], valid[2], valid[-1]],
            [*valid[:-1], {"type": "assistant.message", "data": {"model": self.model, "content": ""}},
             valid[-1]],
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                self.parse(self.encoded(events))
        for requests in ([{"toolCallId": "unstarted"}], {}, None):
            events = self.events()
            events[3]["data"]["toolRequests"] = requests
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                self.parse(self.encoded(events))

    def test_new_activity_cannot_reuse_an_earlier_final_answer(self):
        for kind in ("user.message", "assistant.turn_start"):
            events = self.events()
            events.insert(-1, {"type": kind, "data": {}})
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "final assistant"):
                self.parse(self.encoded(events))
            events.insert(-1, {"type": "assistant.message", "data": {
                "model": self.model, "content": "new answer"}})
            self.assertEqual(self.parse(self.encoded(events))["answer"], "new answer")

    def test_stdout_and_native_share_quality_tool_and_escape_refusals(self):
        outside = self.root / "outside"
        outside.write_text("outside source\n")
        (self.packet / "escape").symlink_to(outside)
        for name, arguments in (
            ("bash", {"command": "true"}), ("skill", {"skill": "example-skill"}),
            (None, {}), ([], {}), ("view", {"path": "../outside"}),
            ("view", {"path": str(outside)}), ("view", {"path": "escape"}),
        ):
            events = self.events()
            events[1]["data"].update(toolName=name, arguments=arguments)
            stdout = self.root / "stdout.jsonl"
            stdout.write_bytes(self.encoded([*events[1:-1], {"type": "result", "exitCode": 0}]))
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaises(ValueError):
                    self.parse(self.encoded(events))
                with self.assertRaises(ValueError):
                    parse_run(stdout, skill="example-skill", expected_model=self.model,
                              cwd=self.packet, require_skill=False, allowed_tools={"view"})

    def test_stdout_still_requires_result_and_its_own_model_evidence(self):
        stdout = self.root / "stdout.jsonl"
        for events in (
            self.events(),
            [{"type": "assistant.message", "data": {"content": "answer", "model": self.model}},
             {"type": "result", "exitCode": 1}],
            [{"type": "session.start", "data": {"selectedModel": self.model}},
             {"type": "assistant.message", "data": {"content": "answer"}},
             {"type": "result", "exitCode": 0}],
        ):
            stdout.write_bytes(self.encoded(events))
            with self.subTest(events=events), self.assertRaises(ValueError):
                parse_run(stdout, skill="example-skill", expected_model=self.model,
                          cwd=self.packet, require_skill=False, allowed_tools={"view"})

    def test_stdout_reader_bounds_records_without_materializing_the_complete_log(self):
        stdout = self.root / "large-stdout.jsonl"
        events = [
            {"type": "system.message", "data": {"ignored": "x" * 40000}},
            {"type": "system.message", "data": {"ignored": "y" * 40000}},
            {"type": "assistant.message", "data": {"content": "answer", "model": self.model}},
            {"type": "result", "exitCode": 0},
        ]
        stdout.write_bytes(self.encoded(events))
        with mock.patch.object(measurement, "MAX_EVENT_BYTES", 50000), mock.patch.object(
            Path, "read_text", side_effect=AssertionError("stdout parser materialized the complete log"),
        ):
            parsed = parse_run(
                stdout, skill="example-skill", expected_model=self.model,
                cwd=self.packet, require_skill=False, allowed_tools={"view"},
            )
        self.assertEqual(parsed["answer"], "answer")
        self.assertEqual(parsed["models"], [self.model])


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

    def make_treatment(self, entry_skill: str = "alternate-skill") -> Path:
        path = Path(self.temp.name) / "treatment.json"
        write = {
            "schema_version": 1,
            "id": "alternate-workflow",
            "source": {
                "repository": "https://example.invalid/workflow",
                "revision": "a" * 40,
                "license": "MIT",
                "retrieved_at": "2026-09-16T00:00:00Z",
            },
            "runner": {"kind": "direct-copilot"},
            "compatibility": {
                "language": ["python"],
                "preapproved_plan": True,
            },
            "entry_skill": entry_skill,
            "intervention_policy": "approved-plan-v1",
            "adapter": {"digest": "0" * 64, "description": "No upstream changes."},
        }
        path.write_text(json.dumps(write, indent=2) + "\n")
        return path

    def restoration_case(self):
        case_dir = self.make_case()
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        restoration = {
            "history_file": "history.jsonl",
            "source_session_id": "original-session",
            "cutoff_event_id": "trigger-event",
            "skill_context": "before-target-load",
            "limitations": [],
        }
        definition["phases"][0]["session_restore"] = restoration
        definition_path.write_text(json.dumps(definition))
        history = case_dir / "evidence/candidate-pass-1/history.jsonl"
        records = [
            {"type": "session", "version": 1, "externalId": "original-session",
             "createdAt": "2026-01-01T00:00:00Z"},
            {"type": "message", "id": "earlier-user", "role": "user",
             "timestamp": "2026-01-01T00:00:00Z",
             "content": [{"type": "text", "text": "Original earlier request."}]},
        ]
        history.write_text("".join(json.dumps(record) + "\n" for record in records))
        return case_dir, definition, history

    def test_personal_instruction_carrier_validation_in_mutable_and_frozen_packets(self):
        from session_restore import validate_restoration
        case_dir, definition, history = self.restoration_case()
        restoration = definition["phases"][0]["session_restore"]
        carrier = history.with_name("personal.md")
        carrier.write_bytes(b"Synthetic instruction.\r\n")
        restoration["personal_instructions_file"] = carrier.name
        (case_dir / "case.json").write_text(json.dumps(definition))
        frozen = freeze_case(self.root, "example-case", replace=False)
        verify_case(self.root, "example-case")
        for root, is_frozen, source in (
            (case_dir, False, carrier),
            (frozen, True, frozen / "candidate-pass-1/personal.md"),
        ):
            for value in ("missing.md", str(carrier.resolve()), "../personal.md",
                          "./personal.md", "", None, 1):
                with self.subTest(frozen=is_frozen, value=value):
                    restoration["personal_instructions_file"] = value
                    with self.assertRaises(ValueError):
                        validate_restoration(definition, root, frozen=is_frozen)
            restoration["personal_instructions_file"] = "personal.md"
            source.unlink()
            source.symlink_to(history)
            with self.subTest(frozen=is_frozen, symlink=True), self.assertRaises(ValueError):
                validate_restoration(definition, root, frozen=is_frozen)
            source.unlink()
            source.write_bytes(b"Synthetic instruction.\r\n")
        definition["case_type"] = "repository-task"
        with self.assertRaisesRegex(ValueError, "read-only"):
            validate_restoration(definition, case_dir)
        definition.pop("case_type")
        restoration["unknown_setup"] = "not supported"
        with self.assertRaises(ValueError):
            validate_restoration(definition, case_dir)

    def personal_instruction_run_fixture(self):
        case_dir, definition, history = self.restoration_case()
        definition["phases"][0]["session_restore"]["personal_instructions_file"] = "personal.md"
        definition["phases"][1]["evidence_dir"] = definition["phases"][0]["evidence_dir"]
        (case_dir / "case.json").write_text(json.dumps(definition))
        body = b"Synthetic personal instruction.\r\nKeep these exact bytes.\n"
        history.with_name("personal.md").write_bytes(body)
        (history.parent / ".github").mkdir()
        (history.parent / ".github/copilot-instructions.md").write_bytes(body)
        freeze_case(self.root, "example-case", replace=False)
        plugin = Path(self.temp.name) / "fixture-plugin"
        skill = plugin / "skills/example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\ndescription: Synthetic skill.\n---\nInspect the source.\n")
        copilot = Path(self.temp.name) / "fixture-cli"
        imported_id = str(uuid.uuid4())
        copilot.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "if '-C' in args: os.chdir(args[args.index('-C') + 1])\n"
            "if '--version' in args: print('fixture-cli'); sys.exit()\n"
            "if 'instruction' in args:\n"
            " print(json.dumps([{'id':'home-copilot','location':'user','type':'home',"
            "'sourcePath':str(Path(os.environ['COPILOT_HOME'])/'copilot-instructions.md'),"
            "'defaultDisabled':False}]))\n"
            " print('synthetic discovery diagnostic', file=sys.stderr)\n"
            "elif 'import' in args:\n"
            f" print(json.dumps({{'ok':True,'code':'session_imported','sessionId':{imported_id!r}}}))\n"
            "elif '--available-tools=view' in args:\n"
            " assert '--no-custom-instructions' in args\n"
            " logs = list(Path.cwd().glob('*-raw.jsonl'))\n"
            " assert len(logs) == 2\n"
            " for log in logs:\n"
            "  call, result = [json.loads(line) for line in log.read_text().splitlines()][:2]\n"
            "  assert call['data']['toolCallId'] == result['data']['toolCallId']\n"
            "  assert result['data']['success'] is True\n"
            "  assert result['data']['result']['content'] == 'product evidence\\n'\n"
            "  receipt = json.loads(log.with_name(log.name.replace('-raw.jsonl','-receipt.json')).read_text())\n"
            "  assert receipt['raw_log_sha256'] == __import__('hashlib').sha256(log.read_bytes()).hexdigest()\n"
            " assert Path('judge-reference/gold.md').is_file()\n"
            " judgment = {'verdict':'PASS','confidence':'HIGH','matched':['read source'],"
            "'missed':[],'overcorrections':[],'generalized_skill_defect':None}\n"
            " print(json.dumps({'type':'assistant.message','data':"
            "{'content':json.dumps(judgment),'model':args[args.index('--model')+1]}}))\n"
            " print(json.dumps({'type':'result','exitCode':0}))\n"
            "else:\n"
            " print(json.dumps({'type':'tool.execution_start','data':{'toolName':'view',"
            "'toolCallId':'source-read','arguments':{'path':'product.md'}}}))\n"
            " print(json.dumps({'type':'tool.execution_complete','data':{'toolCallId':'source-read',"
            "'success':True,'result':{'content':Path('product.md').read_text()}}}))\n"
            " print(json.dumps({'type':'assistant.message','data':"
            "{'content':'candidate-result','model':'fixture-model'}}))\n"
            " print(json.dumps({'type':'result','exitCode':0}))\n"
        )
        copilot.chmod(0o755)
        return plugin, copilot, body

    def test_personal_instruction_run_keeps_isolation_and_raw_read_evidence_across_phases(self):
        plugin, copilot, body = self.personal_instruction_run_fixture()
        original_run = subprocess.run
        invocations = []

        def execute(command, **kwargs):
            if "--available-tools=view" in command:
                self.assertIn("--no-custom-instructions", command)
                self.assertFalse((Path(kwargs["env"]["COPILOT_HOME"]) / "copilot-instructions.md").exists())
                return original_run(command, **kwargs)
            if "--version" not in command:
                env = kwargs["env"]
                self.assertNotIn("COPILOT_CUSTOM_INSTRUCTIONS_DIRS", env)
                self.assertEqual((Path(env["COPILOT_HOME"]) / "copilot-instructions.md").read_bytes(),
                                 body)
                self.assertEqual(list(Path(env["HOME"]).iterdir()), [])
                cwd = Path(kwargs.get("cwd") or command[command.index("-C") + 1])
                self.assertFalse((cwd / "personal.md").exists())
                self.assertFalse((cwd / "history.jsonl").exists())
                self.assertFalse((cwd / "gold.md").exists())
                self.assertTrue((cwd / ".github/copilot-instructions.md").is_file())
                invocations.append((command, env["HOME"], env["COPILOT_HOME"], cwd))
            return original_run(command, **kwargs)

        with (
            mock.patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "synthetic-token",
                                        "COPILOT_CUSTOM_INSTRUCTIONS_DIRS": "/synthetic/ambient"}),
            mock.patch("skill_eval.subprocess.run", side_effect=execute),
            mock.patch("skill_eval.measurement.collect"),
        ):
            run = run_case(self.root, "example-case", plugin, copilot,
                           "fixture-model", "high", "isolated", 60)
        self.assertEqual(len({(home, copilot_home) for _, home, copilot_home, _ in invocations}), 1)
        self.assertEqual(
            ["discovery" if "instruction" in command else "import" if "import" in command else "candidate"
             for command, *_ in invocations],
            ["discovery", "import", "discovery", "candidate", "discovery", "candidate"],
        )
        for command, _, _, cwd in invocations:
            self.assertIn("--plugin-dir", command)
            if "instruction" in command or "-p" in command:
                self.assertEqual(Path(command[command.index("-C") + 1]), cwd)
                self.assertIn("--plugin-dir", command)
                self.assertNotIn("--no-custom-instructions", command)
        receipts = list(run.glob("*-instruction-*-receipt.json"))
        self.assertEqual(len(receipts), 3)
        for path in receipts:
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["source_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(receipt["installed_sha256"], receipt["source_sha256"])
            self.assertEqual(digest(Path(receipt["stdout_path"])), receipt["stdout_sha256"])
            self.assertIn("synthetic discovery diagnostic", Path(receipt["stderr_path"]).read_text())
        for phase in ("candidate-pass-1", "candidate-pass-2"):
            receipt = json.loads((run / f"{phase}-receipt.json").read_text())
            self.assertEqual(receipt["instruction_mode"], "personal-only")
        for path in run.glob("judgment-*.json"):
            self.assertEqual(json.loads(path.read_text())["verdict"], "PASS")

    def test_personal_instruction_discovery_failure_stops_before_import_or_candidate(self):
        plugin, copilot, _ = self.personal_instruction_run_fixture()
        original_run = subprocess.run
        personal = {"id": "home-copilot", "location": "user", "type": "home",
                    "sourcePath": "", "defaultDisabled": False}
        project = {"id": "repo-copilot", "location": "repository", "type": "repo",
                   "sourcePath": "/synthetic/project/.github/copilot-instructions.md",
                   "defaultDisabled": False}
        cases = [
            ("extra", [personal, project], 0), ("missing", [], 0),
            ("disabled", [{**personal, "defaultDisabled": True}], 0),
            ("malformed", {"sources": [personal]}, 0), ("failed", [personal], 1),
            ("bad-json", "not-json", 0), ("bad-encoding", b"\xff", 0),
            ("unknown-enabled-state", [{**personal, "defaultDisabled": None}], 0),
        ]
        for label, sources, exit_code in cases:
            def execute(command, **kwargs):
                if "--version" in command:
                    return original_run(command, **kwargs)
                self.assertIn("instruction", command, "import/model must not execute after failed discovery")
                if isinstance(sources, list):
                    for source in sources:
                        if source.get("id") == "home-copilot":
                            source["sourcePath"] = str(Path(kwargs["env"]["COPILOT_HOME"]) / "copilot-instructions.md")
                stdout = sources if isinstance(sources, (str, bytes)) else json.dumps(sources)
                return subprocess.CompletedProcess(command, exit_code, stdout=stdout, stderr="diagnostic\n")

            with (
                self.subTest(label=label),
                mock.patch("skill_eval.subprocess.run", side_effect=execute),
                mock.patch("skill_eval.run_copilot") as candidate,
                mock.patch("session_restore.import_session") as imported,
                mock.patch("skill_eval.run_judges") as judges,
                self.assertRaisesRegex(ValueError, "instruction discovery"),
            ):
                run_case(self.root, "example-case", plugin, copilot,
                         "fixture-model", "high", "isolated", 60)
            candidate.assert_not_called()
            imported.assert_not_called()
            judges.assert_not_called()
        failures = list((self.root / "runs").rglob("*-instruction-import-receipt.json"))
        self.assertEqual(len(failures), len(cases))
        for path in failures:
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt["status"], "FAIL")
            self.assertTrue(Path(receipt["stdout_path"]).exists())
            self.assertEqual(Path(receipt["stderr_path"]).read_text(), "diagnostic\n")
            self.assertTrue(path.with_name("candidate-pass-1-failure-receipt.json").is_file())

    def test_personal_instruction_later_discovery_failure_preserves_first_phase(self):
        plugin, copilot, _ = self.personal_instruction_run_fixture()
        original_run = subprocess.run
        discovery_count = 0
        candidate_count = 0

        def execute(command, **kwargs):
            nonlocal discovery_count, candidate_count
            if "instruction" in command:
                discovery_count += 1
                if discovery_count == 3:
                    return subprocess.CompletedProcess(command, 0, stdout=b"[]", stderr=b"later diagnostic")
            if "-p" in command:
                candidate_count += 1
            return original_run(command, **kwargs)

        with (
            mock.patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "synthetic-token"}),
            mock.patch("skill_eval.subprocess.run", side_effect=execute),
            mock.patch("skill_eval.measurement.collect"),
            mock.patch("skill_eval.run_judges") as judges,
            self.assertRaisesRegex(ValueError, "instruction discovery"),
        ):
            run_case(self.root, "example-case", plugin, copilot,
                     "fixture-model", "high", "isolated", 60)
        self.assertEqual(candidate_count, 1)
        judges.assert_not_called()
        failure, = (self.root / "runs").rglob("candidate-pass-2-instruction-candidate-receipt.json")
        run = failure.parent
        self.assertEqual(json.loads(failure.read_text())["status"], "FAIL")
        self.assertTrue((run / "candidate-pass-1-receipt.json").is_file())
        self.assertTrue((run / "candidate-pass-1-raw.jsonl").is_file())
        self.assertFalse((run / "candidate-pass-2-raw.jsonl").exists())

    def test_restoration_history_is_frozen_but_not_staged(self):
        from skill_eval import copy_packet
        case_dir, definition, history = self.restoration_case()
        frozen = freeze_case(self.root, "example-case", replace=False)
        verify_case(self.root, "example-case")
        destination = Path(self.temp.name) / "restored-workspace"
        manifest = copy_packet(
            frozen / "candidate-pass-1", destination,
            excluded={definition["phases"][0]["session_restore"]["history_file"]},
        )
        self.assertTrue((destination / "product.md").is_file())
        self.assertFalse((destination / "history.jsonl").exists())
        self.assertIn("history.jsonl", [record["path"] for record in manifest["files"]])
        self.assertEqual((frozen / "candidate-pass-1/history.jsonl").read_bytes(),
                         history.read_bytes())

    def test_restoration_rejects_later_phase_and_target_context(self):
        case_dir, definition, history = self.restoration_case()
        cases = [
            ("target", {"type": "tool-call", "id": "old-load",
                        "name": "skill", "arguments": {"skill": "example-skill"}}),
            ("cutoff", {"type": "message", "id": "trigger-event", "role": "user"}),
        ]
        original = history.read_text()
        for label, record in cases:
            with self.subTest(label=label):
                history.write_text(original + json.dumps(record) + "\n")
                with self.assertRaises(ValueError):
                    freeze_case(self.root, "example-case", replace=True)
        history.write_text(original)
        definition["phases"][1]["session_restore"] = definition["phases"][0].pop("session_restore")
        (case_dir / "case.json").write_text(json.dumps(definition))
        with self.assertRaisesRegex(ValueError, "first phase"):
            freeze_case(self.root, "example-case", replace=True)

    def test_restoration_skill_context_policy_preserves_or_rejects_old_text(self):
        case_dir, definition, history = self.restoration_case()
        original = history.read_text()
        for record, reason in [
            ({"type": "tool-call", "id": "old-load", "name": "skill",
              "arguments": {"skill": "example-skill"}}, "target-skill invocation"),
            ({"type": "message", "id": "old-context", "role": "user",
              "content": [{"type": "text",
                           "text": '<skill-context name="example-skill">Original body</skill-context>'}]},
             "old target-skill context"),
        ]:
            history.write_text(original + json.dumps(record) + "\n")
            for policy in ("before-target-load", "recorded-target-context", "unknown", []):
                with self.subTest(record=record["id"], policy=policy):
                    definition["phases"][0]["session_restore"]["skill_context"] = policy
                    (case_dir / "case.json").write_text(json.dumps(definition))
                    if policy == "recorded-target-context":
                        frozen = freeze_case(self.root, "example-case", replace=True)
                        verify_case(self.root, "example-case")
                        self.assertEqual((frozen / "candidate-pass-1/history.jsonl").read_bytes(),
                                         history.read_bytes())
                    else:
                        expected = reason if policy == "before-target-load" else "skill context"
                        with self.assertRaisesRegex(ValueError, expected):
                            freeze_case(self.root, "example-case", replace=True)

    def test_restored_run_resumes_imported_id_with_unmodified_prompts(self):
        case_dir, definition, history = self.restoration_case()
        definition["phases"][0]["session_restore"]["skill_context"] = "recorded-target-context"
        with history.open("a") as stream:
            stream.write(json.dumps({
                "type": "message", "id": "old-context", "role": "user",
                "content": [{"type": "text",
                             "text": '<skill-context name="example-skill">Old instructions</skill-context>'}],
            }) + "\n")
        definition["phases"][1]["evidence_dir"] = definition["phases"][0]["evidence_dir"]
        (case_dir / "case.json").write_text(json.dumps(definition))
        history.with_name("archived-context.txt").write_bytes(history.read_bytes())
        history.with_name("target-plugin").write_text("Original candidate evidence.\n")
        freeze_case(self.root, "example-case", replace=False)
        plugin = Path(self.temp.name) / "restored-plugin"
        skill = plugin / "skills/example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\ndescription: Example test skill.\n---\nInspect the task.\n")
        (skill / "references").mkdir()
        (skill / "references/checklist.md").write_text("Inspect the current evidence.\n")
        copilot = Path(self.temp.name) / "identity-cli"
        copilot.write_text("#!/usr/bin/env python3\nprint('fixture-cli')\n")
        copilot.chmod(0o755)
        imported_id = str(uuid.uuid4())
        prompts = [(case_dir / phase["prompt_file"]).read_text()
                   for phase in definition["phases"]]

        def import_history(restoration, frozen_history, **kwargs):
            self.assertEqual(frozen_history.read_bytes(), history.read_bytes())
            self.assertFalse((Path(kwargs["workdir"]) / restoration["history_file"]).exists())
            return imported_id

        def continue_candidate(**kwargs):
            self.assertEqual(kwargs["session_id"], imported_id)
            self.assertTrue(kwargs["resume"])
            self.assertEqual(kwargs["home_mode"], "isolated")
            self.assertEqual(kwargs["prompt"], prompts.pop(0))
            self.assertTrue((kwargs["cwd"] / "product.md").is_file())
            self.assertFalse((kwargs["cwd"] / "history.jsonl").exists())
            self.assertFalse((kwargs["cwd"] / "archived-context.txt").exists())
            self.assertEqual((kwargs["cwd"] / "target-plugin").read_text(),
                             "Original candidate evidence.\n")
            reference = kwargs["plugin_dir"] / "skills/example-skill/references/checklist.md"
            self.assertEqual(reference.read_text(), "Inspect the current evidence.\n")
            kwargs["log"].write_text(
                json.dumps({"type": "tool.execution_start", "data": {
                    "toolName": "view", "toolCallId": "reference",
                    "arguments": {"path": str(reference)}}}) + "\n"
                + json.dumps({"type": "tool.execution_complete", "data": {
                    "toolCallId": "reference", "success": True}}) + "\n"
                + json.dumps({"type": "assistant.message", "data": {
                    "content": "candidate-result", "model": "fixture-model"}}) + "\n"
                + json.dumps({"type": "result", "exitCode": 0}) + "\n")
            return [str(copilot), "--resume", imported_id, "-p", kwargs["prompt"]]

        with (
            mock.patch("session_restore.import_session", side_effect=import_history) as imported,
            mock.patch("skill_eval.run_copilot", side_effect=continue_candidate),
            mock.patch("skill_eval.run_judges", return_value=[
                {"model": "claude-opus-5", "verdict": "PASS"},
                {"model": "gpt-5.3-codex", "verdict": "PASS"},
            ]),
        ):
            run = run_case(self.root, "example-case", plugin, copilot,
                           "fixture-model", "high", "isolated", 60)
        imported.assert_called_once()
        self.assertEqual(prompts, [])
        report = (run / "REPORT.md").read_text()
        self.assertIn("**Result: PASS**", report)
        self.assertIn("Historical behavior/mechanism validation only", report)
        self.assertIn("not that historical text", report)
        self.assertIn("does not isolate a skill change", report)

    def test_native_import_failure_retains_receipt_and_does_not_resume(self):
        from session_restore import import_session
        case_dir, definition, history = self.restoration_case()
        receipt = Path(self.temp.name) / "restoration-receipt.json"
        execute = mock.Mock(return_value=(1, '{"ok":false,"code":"invalid_history"}'))
        with self.assertRaisesRegex(ValueError, "native session import"):
            import_session(
                definition["phases"][0]["session_restore"], history,
                copilot="copilot", workdir="/workspace/repo",
                execute=execute, receipt_path=receipt, cli_identity={"version": "test"},
            )
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(json.loads(receipt.read_text())["status"], "FAIL")

    def test_native_import_uses_only_a_validated_new_session_id(self):
        from session_restore import import_session
        _, definition, history = self.restoration_case()
        receipt = Path(self.temp.name) / "restoration-receipt.json"
        session_id = str(uuid.uuid4())
        native = {"ok": True, "code": "session_imported", "sessionId": session_id}
        execute = mock.Mock(return_value=(0, json.dumps(native)))
        actual = import_session(
            definition["phases"][0]["session_restore"], history,
            copilot="copilot", workdir="/workspace/repo",
            execute=execute, receipt_path=receipt, cli_identity={"version": "test"},
        )
        self.assertEqual(actual, session_id)
        self.assertEqual(json.loads(receipt.read_text())["history_sha256"], digest(history))
        for result in ("not-json", "[]", json.dumps({**native, "sessionId": "../../other"})):
            with self.subTest(result=result), self.assertRaises(ValueError):
                import_session(
                    definition["phases"][0]["session_restore"], history,
                    copilot="copilot", workdir="/workspace/repo",
                    execute=lambda command: (0, result), receipt_path=receipt,
                    cli_identity={"version": "test"},
                )
            self.assertEqual(json.loads(receipt.read_text())["status"], "FAIL")

    def test_treatment_descriptor_is_strict_and_compatibility_is_explicit(self) -> None:
        path = self.make_treatment()
        treatment = load_treatment(path)
        admitted = compatibility_result(
            {"compatibility": {"language": "python", "preapproved_plan": True}},
            treatment,
        )
        self.assertEqual(admitted["status"], "ADMITTED")
        blocked = compatibility_result(
            {"compatibility": {"language": "typescript", "preapproved_plan": True}},
            treatment,
        )
        self.assertEqual(blocked["status"], "BLOCKED")
        value = json.loads(path.read_text())
        value["unexpected"] = True
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_treatment(path)

    def test_treatment_source_rejects_moving_revisions_and_versions(self) -> None:
        path = self.make_treatment()
        value = json.loads(path.read_text())
        value["source"]["revision"] = "main"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "immutable commit digest"):
            load_treatment(path)
        value["source"].pop("revision")
        value["source"]["version"] = "latest"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "exact semantic version"):
            load_treatment(path)

    def test_custom_judge_prompt_receives_required_json_contract(self) -> None:
        from skill_eval import JUDGE_OUTPUT_CONTRACT, JUDGE_RUNTIME_CONTRACT

        custom = "Judge the behavior and return PASS, FAIL, or UNANSWERABLE."
        if JUDGE_RUNTIME_CONTRACT not in custom:
            custom = f"{custom.rstrip()}\n\n{JUDGE_RUNTIME_CONTRACT}"
        if JUDGE_OUTPUT_CONTRACT not in custom:
            custom = f"{custom.rstrip()}\n\n{JUDGE_OUTPUT_CONTRACT}"

        self.assertIn('"verdict": "PASS | FAIL | UNANSWERABLE"', custom)
        self.assertIn('"confidence": "LOW | MEDIUM | HIGH"', custom)

    def test_sandcastle_descriptor_accepts_only_frozen_runner(self) -> None:
        adapter = Path(self.temp.name) / "sandcastle-adapter"
        adapter.mkdir()
        (adapter / "main.mjs").write_text("// frozen adapter\n")
        (adapter / "__pycache__").mkdir()
        (adapter / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
        (adapter / ".git").mkdir()
        (adapter / ".git" / "config").write_text("ignored\n")
        treatment_dir = Path(self.temp.name) / "sandcastle-treatment"
        treatment_dir.mkdir()
        path = treatment_dir / "treatment.json"
        value = {
            "schema_version": 1,
            "id": "sandcastle-sequential-reviewer-copilot-outer-isolated",
            "source": {
                "package": "@ai-hero/sandcastle",
                "revision": "e99f832f26dc9d245c019a9ddd19fa5dee792427",
                "version": "0.12.0",
                "license": "MIT",
                "retrieved_at": "2026-09-16T00:00:00Z",
            },
            "runner": {
                "kind": "sandcastle-sequential-reviewer-copilot-outer-isolated",
                "command": ["node", "/treatment-adapter/main.mjs"],
                "model": "gpt-5.6-sol-fast",
                "session_subroles": ["candidate_implementer", "candidate_reviewer"],
            },
            "compatibility": {
                "language": ["typescript"],
                "package_system": ["npm"],
                "remote_side_effects_allowed": False,
            },
            "entry_skill": None,
            "intervention_policy": "fixture-local-one-issue",
            "adapter": {
                "digest": directory_identity(adapter)["sha256"],
                "description": "Copilot provider, outer isolation, one issue.",
            },
        }
        path.write_text(json.dumps(value, indent=2) + "\n")
        treatment = load_treatment(path, sandcastle=True, adapter_dir=adapter)
        self.assertEqual(treatment["descriptor"]["runner"]["command"],
                         ["node", "/treatment-adapter/main.mjs"])
        value["runner"]["command"] = ["node", "/treatment-adapter/other.mjs"]
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "frozen command"):
            load_treatment(path, sandcastle=True, adapter_dir=adapter)

    def test_treatment_admission_binding_is_required_and_artifact_checked(self) -> None:
        binding = {"treatment_fingerprint": "f" * 64}
        run = self.root / "treatment-admission-runs" / "admission" / "example-case"
        run.mkdir(parents=True)
        receipt_path = run / "treatment-admission-receipt.json"
        receipt_path.write_text(json.dumps({
            "schema_version": 1, "status": "PASS", "binding": binding, "artifacts": [],
        }))
        with self.assertRaisesRegex(ValueError, "matching successful"):
            require_treatment_admission(self.root, binding)
        names = {
            "treatment-identity.json": {},
            "skill-identity.json": {},
            "plugin-identity.json": {},
            "harness-identity.json": {},
            "compatibility.json": {},
            "execution-result.json": {"execution_status": "PASS"},
            "repository-result.json": {"behavioral_verdict": "PASS"},
        }
        for name, value in names.items():
            (run / name).write_text(json.dumps(value) + "\n")
        (run / "candidate.patch").write_text("patch\n")
        artifacts = [
            {"path": path.name, "sha256": digest(path)}
            for path in sorted(run.iterdir())
            if path != receipt_path
        ]
        receipt_path.write_text(json.dumps({
            "schema_version": 1,
            "status": "PASS",
            "binding": binding,
            "artifacts": artifacts,
        }))
        self.assertEqual(require_treatment_admission(self.root, binding), receipt_path)
        (run / "treatment-identity.json").write_text('{"changed":true}\n')
        with self.assertRaisesRegex(ValueError, "artifact digest mismatch"):
            require_treatment_admission(self.root, binding)
        (run / "treatment-identity.json").unlink()
        (run / "treatment-identity.json").symlink_to(run / "skill-identity.json")
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            require_treatment_admission(self.root, binding)

    def test_treatment_admission_binds_complete_plugin_snapshot(self) -> None:
        common = {
            "case_revision": "case",
            "treatment": {
                "fingerprint": "f" * 64,
                "source_identity": None,
                "adapter_identity": None,
                "descriptor": {"runner": {"kind": "direct-copilot"}},
            },
            "skill": {"name": "entry", "files": []},
            "harness": {"modules": []},
            "model": "model",
            "effort": "high",
        }
        first = treatment_admission_binding(
            **common, plugin={"sha256": "a" * 64}
        )
        second = treatment_admission_binding(
            **common, plugin={"sha256": "b" * 64}
        )
        self.assertNotEqual(first, second)

    def test_direct_treatment_entry_skill_overrides_case_target(self) -> None:
        case_dir = self.make_case()
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        definition["compatibility"] = {"language": "python", "preapproved_plan": True}
        for phase in definition["phases"]:
            phase["must_include"] = ["candidate-result"]
        definition_path.write_text(json.dumps(definition, indent=2) + "\n")
        freeze_case(self.root, "example-case", replace=False)

        plugin = Path(self.temp.name) / "entry-plugin"
        for name in ("example-skill", "alternate-skill"):
            skill = plugin / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"# {name}\n")
        fake = Path(self.temp.name) / "entry-copilot"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "if '--version' in sys.argv:\n print('fake-copilot 1.0'); raise SystemExit(0)\n"
            "prompt=sys.argv[sys.argv.index('-p')+1]\n"
            "model=sys.argv[sys.argv.index('--model')+1]\n"
            "if 'independent behavioral judge' in prompt:\n"
            " out=json.dumps({'verdict':'PASS','confidence':'HIGH','matched':['claim'],"
            "'missed':[],'overcorrections':[],'generalized_skill_defect':None})\n"
            "else:\n"
            " print(json.dumps({'type':'tool.execution_start','data':{'toolName':'skill',"
            "'toolCallId':'skill-load','arguments':{'skill':'alternate-skill'},'model':model}}))\n"
            " print(json.dumps({'type':'tool.execution_complete','data':"
            "{'toolCallId':'skill-load','success':True}}))\n"
            " out='candidate-result'\n"
            "print(json.dumps({'type':'assistant.message','data':{'content':out,'model':model}}))\n"
            "print(json.dumps({'type':'result','exitCode':0}))\n"
        )
        os.chmod(fake, 0o755)
        dashboard_root = self.root / "dashboard-state"
        from dashboard_state import create_campaign, event_records
        from dashboard_projection import campaign_projection

        registration = create_campaign(dashboard_root, self.root)
        with mock.patch.dict(
            os.environ,
            {"SKILL_EVAL_DASHBOARD_STATE_ROOT": str(dashboard_root)},
        ):
            run = run_case(
                self.root,
                "example-case",
                plugin,
                fake,
                "fake-model",
                "high",
                "existing",
                60,
                treatment_file=self.make_treatment(),
            )
        receipt = json.loads((run / "candidate-pass-1-receipt.json").read_text())
        self.assertTrue(receipt["skill_invoked"])
        self.assertEqual(
            json.loads((run / "skill-identity.json").read_text())["name"],
            "alternate-skill",
        )
        plugin_identity = json.loads((run / "plugin-identity.json").read_text())
        self.assertEqual(plugin_identity["sha256"], directory_identity(plugin)["sha256"])
        self.assertEqual(
            json.loads((run / "compatibility.json").read_text())["status"],
            "ADMITTED",
        )
        events, conflicts = event_records(self.root)
        self.assertEqual(conflicts, [])
        self.assertEqual(events[0]["event_type"], "attempt_planned")
        self.assertEqual(events[1]["event_type"], "attempt_started")
        self.assertIn(
            "attempt_artifact_available",
            {item["event_type"] for item in events},
        )
        attempt = json.loads((run / "attempt.json").read_text())
        self.assertEqual(
            events[0]["writer"]["id"],
            attempt["dashboard_writer_id"],
        )
        projected = campaign_projection(
            dashboard_root,
            registration["campaign_id"],
        )
        self.assertEqual(projected["live_attempts"][0]["state"], "superseded")
        self.assertEqual(
            projected["live_attempts"][0]["authority"],
            "immutable-artifact",
        )
        self.assertEqual(
            projected["live_attempts"][0]["skill_identity"],
            projected["attempts"][0]["population"]["skill_identity"],
        )
        self.assertEqual(projected["live_attempts"][0]["location"], "local")

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

    def test_skill_loading_requires_matching_successful_completion(self) -> None:
        log = Path(self.temp.name) / "skill-completions.jsonl"
        for boundary in ("prose", "repository"):
            for outcomes in ((False,), (None,), (True,), (False, True), (True, False)):
                events = []
                for index, success in enumerate(outcomes):
                    call_id = f"skill-{index}"
                    events.append({
                        "type": "tool.execution_start",
                        "data": {
                            "toolCallId": call_id, "toolName": "skill",
                            "arguments": {"skill": "example-skill"},
                        },
                    })
                    if success is not None:
                        events.append({
                            "type": "tool.execution_complete",
                            "data": {"toolCallId": call_id, "success": success},
                        })
                events.extend([
                    {"type": "assistant.message",
                     "data": {"content": "answer", "model": "fake-model"}},
                    {"type": "result", "exitCode": 0},
                ])
                log.write_text("".join(json.dumps(event) + "\n" for event in events))
                for required in (True, False):
                    with self.subTest(
                        boundary=boundary, outcomes=outcomes, required=required,
                    ):
                        arguments = {
                            "skill": "example-skill", "expected_model": "fake-model",
                            "cwd": Path(self.temp.name), "require_skill": required,
                            "boundary": boundary,
                        }
                        if required and True in outcomes:
                            self.assertTrue(parse_run(log, **arguments)["skill_loaded"])
                        else:
                            with self.assertRaisesRegex(
                                ValueError, "must.*invoke|baseline must not attempt",
                            ):
                                parse_run(log, **arguments)

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

    def test_receipt_records_every_successfully_invoked_skill(self) -> None:
        log = Path(self.temp.name) / "invoked-skills.jsonl"
        events = []
        for call_id, skill_name, success in (
            ("target", "example-skill", True),
            ("gate", "constraint-challenge", True),
            ("failed", "unused-skill", False),
        ):
            events.extend([
                {
                    "type": "tool.execution_start",
                    "data": {
                        "toolCallId": call_id,
                        "toolName": "skill",
                        "arguments": {"skill": skill_name},
                    },
                },
                {
                    "type": "tool.execution_complete",
                    "data": {"toolCallId": call_id, "success": success},
                },
            ])
        events.extend([
            {
                "type": "assistant.message",
                "data": {"content": "answer", "model": "fake-model"},
            },
            {"type": "result", "exitCode": 0},
        ])
        log.write_text("".join(json.dumps(event) + "\n" for event in events))

        result = parse_run(
            log,
            skill="example-skill",
            expected_model="fake-model",
            cwd=Path(self.temp.name),
            require_skill=True,
        )

        self.assertEqual(
            result["invoked_skills"],
            ["example-skill", "constraint-challenge"],
        )

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

    def test_additional_judgment_fields_are_rejected(self) -> None:
        judgment = {
            "verdict": "PASS", "confidence": "HIGH", "matched": ["criterion"],
            "missed": [], "overcorrections": [], "generalized_skill_defect": None,
            "additional_assessment": "An otherwise valid observation",
        }
        with self.assertRaisesRegex(ValueError, "invalid judge fields"):
            validate_judgment(judgment, "claude-opus-5")

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

    def test_scaffolded_judge_prompt_has_one_json_contract(self) -> None:
        case_dir = self.make_case()
        prompt = (case_dir / "prompts" / "judge.md").read_text()
        self.assertEqual(prompt.count("Return only JSON with:"), 1)
        self.assertIn("Return exactly the six fields", prompt)
        self.assertIn("Put every observation and qualification in the existing fields", prompt)

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
            "{'toolName':'skill','toolCallId':'skill-load','arguments':{'skill':'example-skill'},"
            "'model':model}}))\n"
            "print(json.dumps({'type':'tool.execution_complete','data':"
            "{'toolCallId':'skill-load','success':True}}))\n"
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
        run = receipts[0].parent
        timing = json.loads((run / "timing.json").read_text())
        self.assertEqual(timing["status"], "failed")
        self.assertEqual(timing["stages"][-1]["name"], "cleanup")
        accounting = json.loads((run / "accounting.json").read_text())
        self.assertEqual(accounting["candidate"]["sessions"], 1)
        self.assertIsNone(accounting["candidate"]["credits"])

    def test_run_with_fake_copilot(self) -> None:
        case_dir = self.make_case()
        (case_dir / "prompts" / "judge.md").write_text(
            "Act as an independent behavioral judge for the `example-skill` skill.\n"
            "Preserve this custom prose criterion.\n",
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
            " if 'Return only JSON with:' in prompt:\n"
            "  out=json.dumps({'verdict':'PASS','confidence':'HIGH',"
            "  'matched':['claim'],'missed':[],'overcorrections':[],"
            "  'generalized_skill_defect':None})\n"
            " else:\n"
            "  out='PASS\\nThe custom criterion was met.'\n"
            "else:\n"
            " print(json.dumps({'type':'tool.execution_start','data':"
            "{'toolName':'skill','toolCallId':'skill-load','arguments':{'skill':'example-skill'},"
            "'model':model}}))\n"
            " print(json.dumps({'type':'tool.execution_complete','data':"
            "{'toolCallId':'skill-load','success':True}}))\n"
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
        judge_prompt = (run / "judge-claude-opus-5-prompt.md").read_text()
        self.assertIn("Preserve this custom prose criterion.", judge_prompt)
        self.assertEqual(judge_prompt.count("Return only JSON with:"), 1)
        self.assertFalse((run / "criteria.md").exists())
        identity = json.loads((run / "skill-identity.json").read_text())
        self.assertIn("target-plugin", identity["plugin_dir"])
        accounting = json.loads((run / "accounting.json").read_text())
        self.assertEqual(accounting["candidate"]["sessions"], 1)
        self.assertEqual(accounting["evaluation"]["sessions"], 2)
        self.assertEqual(len(list((run / "measurements").glob("*.json"))), 4)
        timing = json.loads((run / "timing.json").read_text())
        self.assertEqual(timing["status"], "completed")
        self.assertIn("behavioral_judging", {stage["name"] for stage in timing["stages"]})
        self.assertTrue((run / "reporting-timing.json").is_file())

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
            "{'toolName':'skill','toolCallId':'skill-load','arguments':{'skill':'example-skill'},"
            "'model':model}}))\n"
            " print(json.dumps({'type':'tool.execution_complete','data':"
            "{'toolCallId':'skill-load','success':True}}))\n"
            " out='candidate-result'\n"
            "print(json.dumps({'type':'assistant.message','data':"
            "{'content':out,'model':model}}))\n"
            "print(json.dumps({'type':'result','exitCode':0}))\n",
            encoding="utf-8",
        )
        os.chmod(fake, 0o755)
        from dashboard_state import capture_skill_snapshot, create_campaign
        dashboard_state_root = Path(self.temp.name) / "dashboard-state"
        registration = create_campaign(dashboard_state_root, self.root)
        snapshot = capture_skill_snapshot(
            self.root,
            plugin,
            ["example-skill"],
        )

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
                dashboard_snapshot_id=snapshot["snapshot_id"],
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
        self.assertEqual(
            result["lineage_identity"]["snapshot_id"],
            snapshot["snapshot_id"],
        )
        suite_lineage = json.loads(
            (suite_root / "lineage-identity.json").read_text()
        )
        self.assertEqual(suite_lineage, result["lineage_identity"])
        harnesses = [
            json.loads((self.root / item["run_path"] / "harness-identity.json").read_text())
            for item in result["cases"]
        ]
        self.assertEqual(len({item["sha256"] for item in harnesses}), 1)
        self.assertEqual(
            Path(harnesses[0]["path"]).parent.resolve(),
            suite_root.resolve(),
        )
        for case in result["cases"]:
            run_lineage = json.loads(
                (self.root / case["run_path"] / "lineage-identity.json").read_text()
            )
            self.assertEqual(run_lineage, suite_lineage)
            for prompt_path in (self.root / case["run_path"]).glob("judge-*-prompt.md"):
                self.assertEqual(
                    prompt_path.read_text().count("Return only JSON with:"),
                    1,
                )
        import evaluation_history
        historical = evaluation_history.history(self.root)
        self.assertEqual(
            historical["lineage_suites"][0]["lineage_identity"],
            suite_lineage,
        )
        self.assertEqual(
            {
                row["population"]["lineage_snapshot_id"]
                for row in historical["attempts"]
            },
            {snapshot["snapshot_id"]},
        )
        first_run = self.root / result["cases"][0]["run_path"]
        lineage_path = first_run / "lineage-identity.json"
        original_lineage = lineage_path.read_text(encoding="utf-8")
        tampered = json.loads(original_lineage)
        tampered["plugin_identity"] = "f" * 64
        lineage_path.write_text(json.dumps(tampered, indent=2) + "\n")
        with self.assertRaisesRegex(
            ValueError,
            "lineage and plugin identity disagree",
        ):
            evaluation_history.history(self.root)
        lineage_path.write_text(original_lineage, encoding="utf-8")
        from dashboard_projection import campaign_projection
        projected = campaign_projection(
            dashboard_state_root,
            registration["campaign_id"],
        )
        self.assertEqual(
            projected["lineage"]["roles"]["passing"],
            {
                "status": "available",
                "snapshot_id": snapshot["snapshot_id"],
                "authority": "immutable-suite",
            },
        )
        first_attempt_path = first_run / "attempt.json"
        original_attempt = first_attempt_path.read_text(encoding="utf-8")
        attempt_value = json.loads(original_attempt)
        attempt_value.pop("suite_owner")
        first_attempt_path.write_text(
            json.dumps(attempt_value, indent=2) + "\n",
            encoding="utf-8",
        )
        historical = evaluation_history.history(self.root)
        self.assertEqual(historical["lineage_suites"], [])
        self.assertEqual(
            historical["invalid_lineage_suites"],
            [{
                "source": str(suite_root.relative_to(self.root)),
                "reason": "lineage_suite_invalid",
            }],
        )
        from dashboard_projection import campaign_projection
        projected = campaign_projection(
            dashboard_state_root,
            json.loads(
                (
                    self.root
                    / ".skill-evaluation-ui"
                    / "campaign.json"
                ).read_text()
            )["campaign_id"],
        )
        self.assertEqual(
            projected["lineage"]["roles"]["passing"]["status"],
            "unavailable",
        )
        self.assertIn(
            {
                "source": str(suite_root.relative_to(self.root)),
                "reason": "lineage_suite_invalid",
            },
            projected["lineage"]["invalid"],
        )
        first_attempt_path.write_text(original_attempt, encoding="utf-8")

        suite_result_path = suite_root / "suite-result.json"
        suite_value = json.loads(suite_result_path.read_text())
        first_case = next(
            item for item in suite_value["cases"]
            if item["case_id"] == result["cases"][0]["case_id"]
        )
        first_claim = first_case["attempts"][0]
        first_claim["result"] = "ERROR"
        first_claim.pop("execution_status", None)
        first_claim.pop("behavioral_verdict", None)
        first_case["result"] = "FAIL"
        first_case["run_path"] = None
        first_case["behavioral_verdict"] = None
        first_case["passed_after_retry"] = False
        suite_value["result"] = "FAIL"
        suite_result_path.write_text(
            json.dumps(suite_value, indent=2) + "\n",
            encoding="utf-8",
        )
        timing_path = first_run / "timing.json"
        timing_value = json.loads(timing_path.read_text())
        timing_value["status"] = "failed"
        timing_path.write_text(
            json.dumps(timing_value, indent=2) + "\n",
            encoding="utf-8",
        )
        historical = evaluation_history.history(self.root)
        self.assertEqual(historical["invalid_lineage_suites"], [])
        self.assertEqual(historical["lineage_suites"][0]["result"], "FAIL")
        suite_value["lineage_identity"]["plugin_identity"] = "e" * 64
        suite_result_path.write_text(
            json.dumps(suite_value, indent=2) + "\n",
            encoding="utf-8",
        )
        historical = evaluation_history.history(self.root)
        self.assertEqual(historical["lineage_suites"], [])
        self.assertEqual(
            historical["invalid_lineage_suites"],
            [{
                "source": str(suite_root.relative_to(self.root)),
                "reason": "lineage_suite_invalid",
            }],
        )
        self.assertEqual(len(historical["attempts"]), 2)

    def test_lineage_suite_summary_cannot_manufacture_pass(self) -> None:
        case_dir = self.make_case("failing-case")
        definition_path = case_dir / "case.json"
        definition = json.loads(definition_path.read_text())
        for phase in definition["phases"]:
            phase["must_include"] = ["required-result"]
        definition_path.write_text(json.dumps(definition, indent=2) + "\n")
        freeze_case(self.root, "failing-case", replace=False)

        plugin = Path(self.temp.name) / "failing-suite-plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n"
            "description: Test examples. Use when evaluating an example.\n---\n"
            "# example-skill\n",
            encoding="utf-8",
        )
        fake = Path(self.temp.name) / "failing-suite-copilot"
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
            "{'toolName':'skill','toolCallId':'skill-load','arguments':{'skill':'example-skill'},"
            "'model':model}}))\n"
            " print(json.dumps({'type':'tool.execution_complete','data':"
            "{'toolCallId':'skill-load','success':True}}))\n"
            " out='wrong-result'\n"
            "print(json.dumps({'type':'assistant.message','data':"
            "{'content':out,'model':model}}))\n"
            "print(json.dumps({'type':'result','exitCode':0}))\n",
            encoding="utf-8",
        )
        os.chmod(fake, 0o755)
        from dashboard_state import capture_skill_snapshot, create_campaign
        dashboard_state_root = Path(self.temp.name) / "dashboard-failing-state"
        create_campaign(dashboard_state_root, self.root)
        snapshot = capture_skill_snapshot(
            self.root,
            plugin,
            ["example-skill"],
        )
        with mock.patch(
            "skill_eval.copilot_identity",
            return_value={"version": "fake-copilot 1.0"},
        ):
            suite_root, passed = run_suite(
                self.root,
                plugin,
                fake,
                "fake-model",
                "high",
                "existing",
                60,
                workers=1,
                dashboard_snapshot_id=snapshot["snapshot_id"],
            )
        self.assertFalse(passed)
        result_path = suite_root / "suite-result.json"
        result = json.loads(result_path.read_text())
        self.assertEqual(result["result"], "FAIL")
        result["result"] = "PASS"
        result["cases"][0]["result"] = "PASS"
        result["failures"] = []
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        import evaluation_history
        historical = evaluation_history.history(self.root)
        self.assertEqual(historical["lineage_suites"], [])
        self.assertEqual(
            historical["invalid_lineage_suites"],
            [{
                "source": str(suite_root.relative_to(self.root)),
                "reason": "lineage_suite_invalid",
            }],
        )

    def test_lineage_suite_rejects_default_treatment_pooling(self) -> None:
        import evaluation_history
        suite_path = "suite-runs/example"
        modules = []
        suite = {
            "result": "PASS",
            "model": "model",
            "effort": "high",
            "arm": "skill",
            "treatment": None,
            "quality_review": False,
            "timeout_seconds": 60,
            "harness_identity": {"modules": modules},
            "case_revisions": {"first": "a" * 64, "second": "b" * 64},
            "failures": [],
            "cases": [
                {
                    "case_id": case_id,
                    "result": "PASS",
                    "run_path": f"runs/{case_id}/run",
                    "behavioral_verdict": None,
                    "passed_after_retry": False,
                    "attempt_count": 1,
                    "attempts": [{
                        "attempt": 1,
                        "result": "PASS",
                        "run_path": f"runs/{case_id}/run",
                    }],
                }
                for case_id in ("first", "second")
            ],
        }
        rows = []
        for case_id, revision, treatment_id, treatment_identity in (
            ("first", "a" * 64, "legacy-skill", "1" * 64),
            ("second", "b" * 64, "alternate-workflow", "2" * 64),
        ):
            rows.append({
                "suite_path": suite_path,
                "attempt": 1,
                "run_path": f"runs/{case_id}/run",
                "correctness": "PASS",
                "suite_result": "PASS",
                "behavioral_verdict": "PASS",
                "population": {
                    "case_id": case_id,
                    "case_revision": revision,
                    "case_type": "prose",
                    "model": "model",
                    "effort": "high",
                    "arm": "skill",
                    "quality_review": False,
                    "timeout_seconds": 60,
                    "harness_identity": evaluation_history.fingerprint(modules),
                    "treatment_id": treatment_id,
                    "treatment_identity": treatment_identity,
                    "runner_kind": "direct-copilot",
                    "intervention_policy": "legacy-case-contract",
                    "adapter_digest": None,
                },
            })
        with self.assertRaisesRegex(
            ValueError,
            "default treatment_id disagrees",
        ):
            evaluation_history.validated_lineage_suite(
                suite_path,
                suite,
                {"snapshot_id": "3" * 64},
                rows,
            )

    def test_dashboard_snapshot_binding_rejects_mutated_source_before_execution(self):
        case_dir = self.make_case("lineage-case")
        freeze_case(self.root, "lineage-case", replace=False)
        plugin = Path(self.temp.name) / "lineage-plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Original\n", encoding="utf-8")
        from dashboard_state import capture_skill_snapshot, create_campaign
        create_campaign(Path(self.temp.name) / "dashboard-state", self.root)
        snapshot = capture_skill_snapshot(
            self.root,
            plugin,
            ["example-skill"],
        )
        (skill / "SKILL.md").write_text("# Changed\n", encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError,
            "pinned plugin does not match dashboard snapshot skill",
        ):
            run_suite(
                self.root,
                plugin,
                Path(self.temp.name) / "copilot-not-needed",
                "fake-model",
                "high",
                "existing",
                60,
                workers=1,
                dashboard_snapshot_id=snapshot["snapshot_id"],
            )
        self.assertFalse(list((self.root / "runs").glob("*/*")))

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
