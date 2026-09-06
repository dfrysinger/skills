"""Synthetic measurement fixtures; no models, Docker, or private cases."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import evaluation_history
import measurement as m
import quality_review
import skill_eval
import test_repository_task


def events(nano=1_000_000_000, kind="session.shutdown", **extra):
    return (json.dumps({"type": kind, "data": {
        "totalNanoAiu": nano, "totalPremiumRequests": 0.33, **extra,
    }}) + "\n").encode()


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = str(uuid.uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def record(self, name="candidate", content=None, stdout=None, **kwargs):
        log = self.root / f"{name}.jsonl"
        if stdout is not None:
            log.write_bytes(stdout)
        return m.collect(
            destination=self.root / f"{name}.measurement.json", session_id=kwargs.pop("session_id", self.session),
            role=kwargs.pop("role", "candidate"), phase=name, model="gpt-example", effort="high",
            cli_version="test-cli", log=log, capture=lambda: content, source="container_eventfile",
            started_at=kwargs.pop("started_at", "2026-01-01T00:00:00+00:00"),
            started_clock=time.monotonic(), outcome=kwargs.pop("outcome", "completed"), **kwargs,
        )

    def home_file(self):
        home = self.root / "home"
        path = home / "session-state" / self.session / "events.jsonl"
        path.parent.mkdir(parents=True)
        return home, path

    def archive(self, entries):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            for name, kind, data in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(data) if kind == tarfile.REGTYPE else 0
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = "/outside/secret"
                archive.addfile(info, io.BytesIO(data) if info.size else None)
        return output.getvalue()

    def test_known_mapping_breakdowns_and_identity_are_not_additive(self):
        content = events(
            session_id="forged", role="external", case_id="forged", secret="must-not-persist",
            modelMetrics={"gpt-example": {"totalNanoAiu": 1_000_000_000,
                                          "usage": {"inputTokens": 2, "secret": "excluded"}}},
            agentMetrics={"child": {"totalNanoAiu": 900_000_000}},
        )
        record = self.record(content=content, stdout=events(800_000_000, "session.usage_checkpoint"))
        self.assertEqual(record["credits"], 1)
        self.assertEqual(record["mapping"], m.MAPPING)
        self.assertEqual(record["session_id"], self.session)
        self.assertEqual(record["role"], "candidate")
        self.assertEqual(record["cli_version"], "test-cli")
        self.assertEqual(record["completeness"], "complete")
        self.assertNotIn("secret", json.dumps(record))
        self.assertNotIn("forged", json.dumps(record))
        self.assertEqual(m.accounting([record])["candidate"]["credits"], 1)

    def test_premium_only_unknown_and_partial(self):
        premium = self.record(name="premium", stdout=b'{"type":"result","usage":{"premiumRequests":0.5}}\n')
        self.assertIsNone(premium["credits"])
        self.assertEqual(premium["premium_requests"], 0.5)
        self.assertEqual(premium["completeness"], "partial")
        unknown = self.record(name="unknown")
        self.assertEqual(unknown["completeness"], "unknown")
        self.assertIsNone(unknown["credits"])
        self.assertIsNone(unknown["premium_requests"])
        partial = self.record(name="timeout", content=events(250_000_000, "session.usage_checkpoint"),
                              outcome="timed_out")
        self.assertEqual(partial["credits"], 0.25)
        total = m.accounting([partial])["total"]
        self.assertEqual(total["observed_credits"], 0.25)
        self.assertIsNone(total["credits"])
        self.assertFalse(total["complete"])
        unmapped = self.record(name="unmapped", stdout=(
            b'{"type":"result","usage":{"cost":19,"unit":"unrecognized"}}\n'))
        self.assertIsNone(unmapped["credits"])
        self.assertIn("unrecognized", (self.root / "unmapped.jsonl").read_text())
        terminal_premium = self.record(name="terminal-premium", content=events(None))
        self.assertEqual(m.accounting([terminal_premium])["total"]["premium_requests"], 0.33)
        self.assertIsNone(m.accounting([terminal_premium])["total"]["credits"])

    def test_invalid_numeric_and_structural_usage_is_error_not_zero(self):
        for index, value in enumerate((-1, True, "2", float("nan"), float("inf"), {}, 10 ** 400)):
            with self.subTest(value=type(value).__name__, index=index):
                result = self.record(name=f"bad-{index}", content=events(value))
                self.assertEqual(result["completeness"], "error")
                self.assertIsNone(result["credits"])
                self.assertTrue(result["errors"])
        for index, value in enumerate((b"invalid", b"[]\n", b'{"type":[]}\n',
                                       b'{"type":"session.shutdown","data":[]}\n',
                                       events(agentMetrics=[]), b"[" * 2000 + b"]" * 2000)):
            result = self.record(name=f"structure-{index}", content=value)
            self.assertEqual(result["completeness"], "error")

    def test_selected_observation_never_mixes_alternative_counters(self):
        record = self.record(content=events(None), stdout=events(5_000_000_000))
        self.assertIsNone(record["credits"])
        self.assertEqual(record["selected_observation"], 0)

    def test_two_sessions_failed_judges_and_resumed_totals(self):
        first = self.record(content=events(1_000_000_000))
        second = self.record(name="resume", content=events(3_000_000_000),
                             started_at="2026-01-01T00:01:00+00:00")
        judge = self.record(name="judge", content=events(2_000_000_000),
                            session_id=str(uuid.uuid4()), role="behavioral_judge", outcome="failed")
        summary = m.accounting([second, judge, first])
        self.assertEqual(summary["candidate"]["credits"], 3)
        self.assertEqual(summary["evaluation"]["credits"], 2)
        self.assertEqual(summary["total"]["credits"], 5)
        self.assertEqual(len(summary["sessions"]), 2)
        later = self.record(name="empty-resume", started_at="2026-01-01T00:02:00+00:00")
        provisional = m.accounting([first, second, later])["candidate"]
        self.assertEqual(provisional["observed_credits"], 3)
        self.assertIsNone(provisional["credits"])
        with self.assertRaisesRegex(m.MeasurementError, "multiple spending roles"):
            m.accounting([first, {**second, "role": "quality_judge"}])
        decreased = self.record(name="decreased", content=events(1_000_000_000),
                                started_at="2026-01-01T00:03:00+00:00")
        with self.assertRaisesRegex(m.MeasurementError, "decreased"):
            m.accounting([second, decreased])

    def test_old_shutdown_before_new_activity_is_not_terminal(self):
        content = events() + b'{"type":"user.message","data":{}}\n' + events(
            2_000_000_000, "session.usage_checkpoint")
        record = self.record(content=content)
        self.assertEqual(record["credits"], 2)
        self.assertEqual(record["completeness"], "partial")

    def test_host_exact_owned_file_and_unrelated_session_excluded(self):
        home, path = self.home_file()
        path.write_bytes(events())
        unrelated = home / "session-state" / str(uuid.uuid4()) / "events.jsonl"
        unrelated.parent.mkdir()
        unrelated.write_bytes(b"unrelated secret")
        self.assertEqual(m.host_events(home, self.session), events())
        path.unlink()
        self.assertIsNone(m.host_events(home, self.session))
        with self.assertRaises(m.MeasurementError):
            m.host_events(home, "../outside")

    def test_host_symlink_directory_fifo_hardlink_and_oversize_rejected(self):
        home, path = self.home_file()
        outside = self.root / "outside"
        outside.write_bytes(b"secret")
        path.symlink_to(outside)
        with self.assertRaises(m.MeasurementError):
            m.host_events(home, self.session)
        path.unlink()
        path.mkdir()
        with self.assertRaises(m.MeasurementError):
            m.host_events(home, self.session)
        path.rmdir()
        os.mkfifo(path)
        with self.assertRaises(m.MeasurementError):
            m.host_events(home, self.session)
        path.unlink()
        os.link(outside, path)
        with self.assertRaises(m.MeasurementError):
            m.host_events(home, self.session)
        path.unlink()
        path.write_bytes(b"x" * 20)
        with mock.patch.object(m, "MAX_EVENT_BYTES", 10), self.assertRaises(m.MeasurementError):
            m.host_events(home, self.session)
        path.unlink()
        path.parent.rmdir()
        path.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(m.MeasurementError):
            m.host_events(home, self.session)
        home_alias = self.root / "home-alias"
        home_alias.symlink_to(home, target_is_directory=True)
        with self.assertRaises(m.MeasurementError):
            m.host_events(home_alias, self.session)

    def test_archive_single_regular_only_and_no_extraction(self):
        data = events()
        regular = ("events.jsonl", tarfile.REGTYPE, data)
        self.assertEqual(m.archive_events(self.archive([regular])), data)
        for entries in (
            [regular, regular],
            [("events.jsonl", tarfile.SYMTYPE, b"")],
            [("events.jsonl", tarfile.LNKTYPE, b"")],
            [("events.jsonl", tarfile.DIRTYPE, b"")],
            [("events.jsonl", tarfile.CHRTYPE, b"")],
            [("../events.jsonl", tarfile.REGTYPE, data)],
            [("/events.jsonl", tarfile.REGTYPE, data)],
        ):
            with self.subTest(entries=entries), self.assertRaises(m.MeasurementError):
                m.archive_events(self.archive(entries))
        with mock.patch.object(m, "MAX_EVENT_BYTES", 1), self.assertRaises(m.MeasurementError):
            m.archive_events(self.archive([regular]))
        with self.assertRaises(m.MeasurementError):
            m.archive_events(self.archive([regular]) + self.archive([regular]))
        self.assertFalse((self.root / "events.jsonl").exists())

    def test_container_exact_path_stopped_guard_absence_and_capture_error(self):
        with mock.patch.object(m, "bounded_command", return_value=(
            0, self.archive([("events.jsonl", tarfile.REGTYPE, events())]), b"",
        )) as command:
            self.assertEqual(m.container_events("owned", self.session, stopped=True), events())
            self.assertEqual(command.call_args.args[0], [
                "docker", "cp", f"owned:/tmp/eval-home/session-state/{self.session}/events.jsonl", "-"])
            with self.assertRaises(m.MeasurementError):
                m.container_events("owned", self.session, stopped=False)
        message = f"Could not find the file /tmp/eval-home/session-state/{self.session}/events.jsonl in container owned"
        with mock.patch.object(m, "bounded_command", return_value=(1, b"", message.encode())):
            self.assertIsNone(m.container_events("owned", self.session, stopped=True))
        with mock.patch.object(m, "bounded_command", return_value=(1, b"", b"daemon broken")):
            with self.assertRaises(m.MeasurementError):
                m.container_events("owned", self.session, stopped=True)

    def test_bounded_collection_limits_pipes_before_allocation(self):
        with mock.patch.object(m, "MAX_ARCHIVE_BYTES", 1024):
            with self.assertRaisesRegex(m.MeasurementError, "byte limit"):
                m.bounded_command([sys.executable, "-c", "import os; os.write(1, b'x' * 100000)"])
        with self.assertRaisesRegex(m.MeasurementError, "timed out"):
            m.bounded_command([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.05)

    def test_read_failure_only_persists_filtered_error(self):
        destination = self.root / "failed.measurement.json"
        with mock.patch.object(m, "host_events", side_effect=m.MeasurementError("telemetry type rejected")):
            record = m.collect(
                destination=destination, session_id=self.session, role="candidate", phase="candidate",
                model="gpt-example", effort="high", cli_version="test", log=self.root / "absent",
                capture=lambda: m.host_events(self.root, self.session), source="host_eventfile",
                started_at=m.instant(), started_clock=time.monotonic(), outcome="failed")
        self.assertEqual(record["completeness"], "error")
        self.assertIsNone(record["credits"])

    def test_timeline_outer_interval_does_not_sum_parallel_work(self):
        clock = [0.0]
        with mock.patch.object(m.time, "monotonic", side_effect=lambda: clock[0]):
            timer = m.Timeline()
            clock[0] = 2
            timer.switch("candidate")
            clock[0] = 5
            timer.switch("behavioral_judging")
            clock[0] = 8
            timer.switch("quality_review")
            clock[0] = 10
            timer.switch("cleanup")
            clock[0] = 12
            result = timer.finish("completed")
        self.assertEqual(result["elapsed_seconds"], 12)
        self.assertEqual([stage["elapsed_seconds"] for stage in result["stages"]], [2, 3, 3, 2, 2])

    def test_host_transport_timeout_and_nonzero_keep_usage(self):
        for index, failure in enumerate((
            subprocess.TimeoutExpired(["fake"], 1, output=events(500_000_000, "session.usage_checkpoint")),
            subprocess.CompletedProcess(["fake"], 1, stdout=events(500_000_000, "session.usage_checkpoint").decode()),
        )):
            log = self.root / f"transport-{index}.log"
            destination = self.root / f"transport-{index}.measurement.json"
            kwargs = dict(copilot=Path("/fake"), plugin_dir=self.root, cwd=self.root, prompt="public",
                          model="gpt-example", effort="high", log=log, session_id=str(uuid.uuid4()),
                          resume=False, home_mode="existing", run_home=self.root, timeout_seconds=1,
                          allow_skill=False, measurement_path=destination, role="quality_judge")
            with mock.patch.object(skill_eval.subprocess, "run") as run, mock.patch.object(
                m, "host_events", return_value=None,
            ):
                if isinstance(failure, Exception):
                    run.side_effect = failure
                else:
                    run.return_value = failure
                with self.assertRaises(ValueError):
                    skill_eval.run_copilot(**kwargs)
            record = skill_eval.read_json(destination)
            self.assertEqual(record["credits"], 0.5)
            self.assertEqual(record["role"], "quality_judge")
            self.assertEqual(record["completeness"], "partial")

    def test_resumed_transport_does_not_reuse_prior_shutdown(self):
        home, path = self.home_file()
        path.write_bytes(events())
        log = self.root / "resumed.log"
        destination = self.root / "resumed.measurement.json"
        with mock.patch.dict(os.environ, {"COPILOT_HOME": str(home)}), mock.patch.object(
            skill_eval.subprocess, "run", side_effect=subprocess.TimeoutExpired(["fake"], 1, output=b""),
        ):
            with self.assertRaises(ValueError):
                skill_eval.run_copilot(
                    copilot=Path("/fake"), plugin_dir=self.root, cwd=self.root, prompt="public",
                    model="gpt-example", effort="high", log=log, session_id=self.session,
                    resume=True, home_mode="existing", run_home=self.root, timeout_seconds=1,
                    allow_skill=True, measurement_path=destination,
                )
        record = skill_eval.read_json(destination)
        self.assertEqual(record["completeness"], "unknown")
        self.assertIsNone(record["credits"])


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_repository_task.RepositoryTaskTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.frozen = self.fixture.freeze()
        self.definition = skill_eval.read_json(self.frozen / "case.json")
        self.run = self.root / "runs" / "review" / "example"
        self.run.mkdir(parents=True)
        (self.run / "candidate.patch").write_bytes(
            (self.frozen / "judge-reference" / "reference.patch").read_bytes())
        skill_eval.write_json(self.run / "copilot-identity.json", {"version": "fake"})

    def tearDown(self):
        self.fixture.tearDown()

    def review(self):
        return {
            "judgment": "needs_revision", "summary": "A source-linked concern.",
            "findings": [{"path": "candidate/code.py", "start_line": 1, "end_line": 1,
                          "quotation": "return a + b", "severity": "medium",
                          "trigger": "A concrete input", "explanation": "A concrete risk"}],
        }

    def test_packet_contains_only_source_and_public_requirements(self):
        packet = self.run / "packet"
        manifest = quality_review.prepare_packet(
            self.frozen, self.definition, self.run / "candidate.patch", packet)
        self.assertEqual({Path(item["path"]).parts[0] for item in manifest},
                         {"baseline", "candidate", "requirements"})
        self.assertTrue(all((packet / item["path"]).stat().st_mode & 0o222 == 0 for item in manifest))
        content = "\n".join(path.read_text() for path in packet.rglob("*") if path.is_file())
        self.assertIn("return a - b", content)
        self.assertIn("return a + b", content)
        self.assertIn("Fix addition", content)
        for value in ("TARGET_CHECKS_PASSED", "REGRESSION_CHECKS_PASSED", "synthetic-v1",
                      "example-skill", "trajectory", "premiumRequests", "reference.patch"):
            self.assertNotIn(value, content)
        quality_review.validate_review(self.review(), packet)
        for change in (
            {"path": "../outside"}, {"path": str(packet / "candidate/code.py")},
            {"path": "candidate/missing.py"}, {"path": "requirements/evidence/task.md"},
            {"start_line": 0}, {"end_line": 100}, {"start_line": True},
            {"quotation": "not present"}, {"quotation": ""}, {"trigger": ""},
            {"severity": "5"}, {"severity": []},
        ):
            value = self.review()
            value["findings"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                quality_review.validate_review(value, packet)
        invalid = self.review()
        invalid["judgment"] = []
        with self.assertRaises(ValueError):
            quality_review.validate_review(invalid, packet)

    def test_one_failed_reviewer_keeps_other_and_refuses_reassessment(self):
        calls = []

        def transport(**kwargs):
            calls.append(kwargs)
            self.assertFalse(kwargs["allow_skill"])
            plugin = skill_eval.read_json(kwargs["plugin_dir"] / "plugin.json")
            self.assertEqual(plugin["skills"], [])
            self.assertEqual(kwargs["role"], "quality_judge")
            answer = json.dumps(self.review()) if len(calls) == 1 else "not-json"
            kwargs["log"].write_text("\n".join(json.dumps(event) for event in (
                {"type": "assistant.message", "data": {"content": answer, "model": kwargs["model"]}},
                {"type": "result", "exitCode": 0},
            )))
            m.collect(
                destination=kwargs["measurement_path"], session_id=kwargs["session_id"],
                role=kwargs["role"], phase=kwargs["phase"], model=kwargs["model"],
                effort=kwargs["effort"], cli_version="fake", log=kwargs["log"],
                capture=lambda: events(), source="host_eventfile",
                started_at=m.instant(), started_clock=time.monotonic(), outcome="completed")

        with mock.patch.object(quality_review, "run_copilot", side_effect=transport):
            assessment = quality_review.review_repository(
                frozen=self.frozen, run_root=self.run, definition=self.definition,
                copilot=Path("/fake"), timeout_seconds=1)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["session_id"], calls[1]["session_id"])
        self.assertFalse(assessment["complete"])
        self.assertEqual(assessment["reviewers"][0]["judgment"], "needs_revision")
        self.assertEqual(assessment["reviewers"][1]["status"], "failed")
        self.assertEqual(assessment["patch_sha256"], skill_eval.digest(self.run / "candidate.patch"))
        records = [skill_eval.read_json(path) for path in (self.run / "measurements").glob("*.json")]
        self.assertEqual(m.accounting(records)["evaluation"]["credits"], 2)
        path = self.run / "quality" / "assessment.json"
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            quality_review.review_repository(
                frozen=self.frozen, run_root=self.run, definition=self.definition,
                copilot=Path("/fake"), timeout_seconds=1)
        self.assertEqual(path.read_bytes(), original)

    def test_missing_source_is_incomplete_without_invocations(self):
        (self.run / "candidate.patch").unlink()
        with mock.patch.object(quality_review, "run_copilot") as transport:
            result = quality_review.review_repository(
                frozen=self.frozen, run_root=self.run, definition=self.definition,
                copilot=Path("/fake"), timeout_seconds=1)
        transport.assert_not_called()
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["reviewers"]), 2)

    def test_complete_independent_reviews_keep_disagreement(self):
        count = 0

        def transport(**kwargs):
            nonlocal count
            count += 1
            value = self.review() if count == 1 else {
                "judgment": "acceptable", "summary": "Source meets the requirement.", "findings": []}
            kwargs["log"].write_text("\n".join(json.dumps(event) for event in (
                {"type": "assistant.message", "data": {
                    "content": json.dumps(value), "model": kwargs["model"]}},
                {"type": "result", "exitCode": 0},
            )))

        with mock.patch.object(quality_review, "run_copilot", side_effect=transport):
            result = quality_review.review_repository(
                frozen=self.frozen, run_root=self.run, definition=self.definition,
                copilot=Path("/fake"), timeout_seconds=1)
        self.assertTrue(result["complete"])
        self.assertTrue(result["disagreement"])
        self.assertEqual(len(result["reviewers"][0]["findings"]), 1)
        self.assertEqual(result["reviewers"][1]["findings"], [])

    def test_review_audit_rejects_execution_and_outside_reads(self):
        packet = self.run / "packet"
        packet.mkdir()
        log = self.run / "raw.log"
        for name, arguments in (("bash", {"command": "true"}), ("view", {"path": "../outside"})):
            log.write_text("\n".join(json.dumps(event) for event in (
                {"type": "tool.execution_start", "data": {
                    "toolCallId": "read", "toolName": name, "arguments": arguments}},
                {"type": "tool.execution_complete", "data": {"toolCallId": "read", "success": True}},
                {"type": "assistant.message", "data": {"model": "gpt-example", "content": "{}"}},
                {"type": "result", "exitCode": 0},
            )))
            with self.assertRaises(ValueError):
                skill_eval.parse_run(log, skill="example-skill", expected_model="gpt-example",
                                     cwd=packet, require_skill=False, allowed_tools={"view"})


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        skill_eval.init_corpus(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def run_fixture(self, name, status, credits=None, *, complete=True, old=False, owner=None):
        path = self.root / "runs" / name / "example"
        path.mkdir(parents=True)
        skill_eval.write_json(path / "execution-result.json", {
            "schema_version": 1, "case_id": "example", "case_type": "repository-task",
            "case_revision": "fixed", "execution_status": status, "behavioral_verdict": None,
            "arm": "skill", "model": "gpt-example", "effort": "high",
            "timeout_seconds": 10, "elapsed_seconds": 2,
        })
        skill_eval.write_json(path / "skill-identity.json", {"name": "example", "files": []})
        if not old:
            skill_eval.write_json(path / "attempt.json", {
                "schema_version": 1, "case_id": "example", "suite_owner": owner,
                "quality_review": False,
            })
            log = path / "log.jsonl"
            log.write_text("")
            m.collect(
                destination=path / "measurements" / "candidate.json",
                session_id=str(uuid.uuid4()), role="candidate", phase="candidate",
                model="gpt-example", effort="high", cli_version="fake", log=log,
                capture=lambda: events(credits * 1_000_000_000,
                                       "session.shutdown" if complete else "session.usage_checkpoint")
                                if credits is not None else None,
                source="container_eventfile", started_at=m.instant(),
                started_clock=time.monotonic(), outcome="completed")
            records = [skill_eval.read_json(path / "measurements" / "candidate.json")]
            skill_eval.write_json(path / "accounting.json", m.accounting(records))
        return path

    def test_stable_history_keeps_old_unknowns_invalid_and_failed_spending(self):
        self.run_fixture("pass", "PASS", 2)
        self.run_fixture("fail", "FAIL", 3)
        self.run_fixture("invalid", "INVALID", 1)
        self.run_fixture("old", "FAIL", old=True)
        first = evaluation_history.history(self.root)
        second = evaluation_history.history(self.root)
        self.assertEqual(first, second)
        self.assertEqual(len(first["attempts"]), 4)
        self.assertEqual(len(first["populations"]), 1)
        summary = first["populations"][0]
        self.assertIsNone(summary["credits_per_successful_first_attempt"])
        self.assertEqual(summary["total_spend"]["observed_credits"], 6)
        self.assertEqual(summary["invalid_spend"]["credits"], 1)
        self.assertEqual(summary["unsuccessful_spend"]["observed_credits"], 4)
        old = next(row for row in first["attempts"] if row["run_path"] == "runs/old/example")
        self.assertIsNone(old["elapsed_seconds"])
        self.assertEqual(old["legacy_execution_elapsed_seconds"], 2)
        self.assertFalse(old["accounting_available"])
        text = evaluation_history.markdown(first)
        self.assertIn("unknown", text)
        self.assertIn("invalid_spend", text)

    def test_suite_owned_runs_count_once_and_retry_excluded_from_first_ratio(self):
        cases = []
        for suite_id, values in (("one", [("FAIL", 3), ("PASS", 4)]),
                                 ("two", [("PASS", 2)]), ("three", [("INVALID", 1)])):
            attempts = []
            for ordinal, (status, credits) in enumerate(values, 1):
                owner = {"suite_path": f"suite-runs/{suite_id}", "case_id": "example",
                         "attempt": ordinal, "max_attempts": 2}
                path = self.run_fixture(f"{suite_id}-{ordinal}", status, credits, owner=owner)
                attempts.append({"attempt": ordinal, "result": status,
                                 "run_path": path.relative_to(self.root).as_posix()})
            cases.append(attempts)
            skill_eval.write_json(self.root / "suite-runs" / suite_id / "suite-result.json", {
                "schema_version": 1, "max_attempts": 2, "cases": [{"case_id": "example", "attempts": attempts}],
            })
        history = evaluation_history.history(self.root)
        self.assertEqual(len(history["attempts"]), 4)
        self.assertEqual(len(history["populations"]), 1)
        summary = history["populations"][0]
        self.assertEqual(summary["first_attempt_spend"]["credits"], 6)
        self.assertEqual(summary["credits_per_successful_first_attempt"], 6)
        self.assertEqual(summary["retry_spend"]["credits"], 4)
        self.assertEqual(summary["eventual_executable_passes"], 2)
        self.assertEqual(summary["retry_assisted_executable_passes"], 1)
        self.assertEqual(evaluation_history.history(self.root), history)

    def test_partial_credits_zero_success_and_population_changes_have_no_false_ratio(self):
        first = self.run_fixture("partial", "PASS", 2, complete=False)
        second = self.run_fixture("fail", "FAIL", 1)
        result = skill_eval.read_json(second / "execution-result.json")
        result["case_revision"] = "different"
        skill_eval.write_json(second / "execution-result.json", result)
        report = evaluation_history.history(self.root)
        self.assertEqual(len(report["populations"]), 2)
        self.assertTrue(all(item["credits_per_successful_first_attempt"] is None for item in report["populations"]))
        self.assertEqual(len(evaluation_history.history(self.root, model="other")["attempts"]), 0)
        corrupted = skill_eval.read_json(first / "accounting.json")
        corrupted["total"]["observed_credits"] = 100
        skill_eval.write_json(first / "accounting.json", corrupted)
        with self.assertRaisesRegex(ValueError, "does not match"):
            evaluation_history.history(self.root)

    def test_failed_suite_path_is_recovered_from_owned_attempt_without_duplicate(self):
        owner = {"suite_path": "suite-runs/failed", "case_id": "example",
                 "attempt": 1, "max_attempts": 1}
        self.run_fixture("failed", "INVALID", 2, owner=owner)
        skill_eval.write_json(self.root / "suite-runs/failed/suite-result.json", {
            "max_attempts": 1, "cases": [{"case_id": "example",
                                       "attempts": [{"attempt": 1, "result": "ERROR"}]}],
        })
        result = evaluation_history.history(self.root)
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["populations"][0]["invalid_spend"]["credits"], 2)

    def test_corrupt_attempt_and_duplicate_suite_ownership_fail_visibly(self):
        path = self.run_fixture("valid", "PASS", 1)
        (path / "execution-result.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "must be an object"):
            evaluation_history.history(self.root)
        (path / "execution-result.json").write_text('{"execution_status":"invented"}')
        with self.assertRaisesRegex(ValueError, "invalid execution"):
            evaluation_history.history(self.root)
        for name in ("a", "b"):
            skill_eval.write_json(self.root / "suite-runs" / name / "suite-result.json", {
                "cases": [{"case_id": "example", "attempts": [
                    {"attempt": 1, "result": "PASS", "run_path": path.relative_to(self.root).as_posix()}]}],
            })
        with self.assertRaisesRegex(ValueError, "multiple suite"):
            evaluation_history.history(self.root)

    def test_one_session_cannot_be_counted_as_two_attempts(self):
        first = self.run_fixture("first", "PASS", 1)
        second = self.run_fixture("second", "PASS", 1)
        record = skill_eval.read_json(first / "measurements/candidate.json")
        skill_eval.write_json(second / "measurements/candidate.json", record)
        skill_eval.write_json(second / "accounting.json", m.accounting([record]))
        with self.assertRaisesRegex(ValueError, "multiple attempts"):
            evaluation_history.history(self.root)

    def test_history_cli_formats_and_quality_options(self):
        self.run_fixture("cli", "PASS", 1)
        for format_name in ("json", "markdown"):
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                self.assertEqual(skill_eval.main([
                    "history", str(self.root), "--format", format_name, "--case", "example",
                ]), 0)
            if format_name == "json":
                self.assertEqual(len(json.loads(output.getvalue())["attempts"]), 1)
            else:
                self.assertIn("# Evaluation history", output.getvalue())
        for command in ("run", "run-suite"):
            arguments = [command, str(self.root), "--plugin-dir", "/plugin", "--quality-review"]
            if command == "run":
                arguments += ["--case", "example"]
            self.assertTrue(skill_eval.parser().parse_args(arguments).quality_review)


if __name__ == "__main__":
    unittest.main()
