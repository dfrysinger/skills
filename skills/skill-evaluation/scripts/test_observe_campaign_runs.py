"""Caller-level metadata observer tests using only a local gh executable."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import observe_campaign_runs as observer


REPOSITORY = "example/evaluation"


def run(run_id=1, **updates):
    value = {
        "id": run_id, "workflow_id": 8, "head_sha": "a" * 40,
        "head_branch": "main", "run_attempt": 1, "event": "workflow_dispatch",
        "path": ".github/workflows/evaluation.yml", "status": "completed",
        "conclusion": "success",
        "repository": {"id": 9, "full_name": REPOSITORY, "private": False},
    }
    value.update(updates)
    return value


def requested(*rows):
    return [{key: row[key] for key in (*observer.BINDINGS, "repository")} for row in rows]


def page(*rows, total=None):
    return {"total_count": len(rows) if total is None else total, "workflow_runs": list(rows)}


GH_SUBSTITUTE = """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

root = Path(os.environ["OBSERVER_TEST_ROOT"])
log = root / "calls.jsonl"
index = len(log.read_text().splitlines()) if log.exists() else 0
with log.open("a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
fixtures = json.loads((root / "responses.json").read_text())
if index >= len(fixtures):
    print("unexpected call", file=sys.stderr)
    sys.exit(99)
fixture = fixtures[index]
if fixture.get("create_output"):
    (root / "result.json").write_text("racing creator")
time.sleep(fixture.get("sleep", 0))
if fixture.get("error"):
    print("not-a-real-secret", file=sys.stderr)
    sys.exit(1)
if "raw" in fixture:
    sys.stdout.write(fixture["raw"])
else:
    print(json.dumps(fixture["body"]))
"""


class ObserverCLITests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / (".observer-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(GH_SUBSTITUTE)
        gh.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.root)

    def invoke(self, inputs, responses, *options, raw_input=None, existing_output=None, read_output=True):
        for name in ("calls.jsonl", "result.json"):
            (self.root / name).unlink(missing_ok=True)
        (self.root / "runs.json").write_text(
            json.dumps(inputs) if raw_input is None else raw_input)
        (self.root / "responses.json").write_text(json.dumps(responses))
        output = self.root / "result.json"
        if existing_output is not None:
            output.write_text(existing_output)
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
                   OBSERVER_TEST_ROOT=str(self.root), GH_HOST="ignored.example")
        result = subprocess.run(
            [sys.executable, str(Path(observer.__file__).resolve()),
             "--repository", REPOSITORY, "--runs", str(self.root / "runs.json"),
             "--output", str(output), *options],
            capture_output=True, text=True, timeout=10, env=env,
        )
        log = self.root / "calls.jsonl"
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        value = json.loads(output.read_text()) if output.exists() and existing_output is None and read_output else None
        return result, calls, value

    def refuse(self, inputs, responses, *options, expected_calls=None, raw_input=None):
        result, calls, output = self.invoke(inputs, responses, *options, raw_input=raw_input)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("observation refused", result.stderr)
        self.assertIsNone(output)
        self.assertFalse((self.root / "result.json").exists())
        if expected_calls is not None:
            self.assertEqual(len(calls), expected_calls)
        return result, calls

    def test_batched_cli_snapshot_and_get_only_projection(self):
        rows = [run(1), run(2, status="queued", conclusion=None), run(3)]
        result, calls, output = self.invoke(requested(rows[1], rows[0]), [{"body": page(*rows)}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [[
            "api", "--hostname", "github.com", "--method", "GET",
            f"repos/{REPOSITORY}/actions/runs?per_page=100&page=1",
            "--jq", observer.LIST_PROJECTION,
        ]])
        self.assertNotIn("actor", calls[0][-1])
        self.assertNotIn("avatar", calls[0][-1])
        self.assertEqual([entry["run"]["id"] for entry in output["observations"]], [2, 1])
        self.assertEqual(output["observations"][0]["run"]["status"], "queued")
        self.assertEqual(output["observations"][0]["provenance"], {"source": "list", "page": 1, "call": 1})
        self.assertTrue(output["non_atomic"])
        self.assertEqual(output["call_count"], 1)
        self.assertEqual(output["projected_response_bytes"], output["calls"][0]["projected_response_bytes"])
        self.assertEqual(output["projected_response_bytes"], len((json.dumps(page(*rows)) + "\n").encode()))
        self.assertGreaterEqual(output["client_wall_seconds"], output["calls"][0]["client_wall_seconds"])
        self.assertNotIn("PASS", json.dumps(output))

    def test_complete_two_page_enumeration_even_when_requested_found_early(self):
        rows = [run(i) for i in range(1, 102)]
        result, calls, output = self.invoke(requested(rows[0]), [
            {"body": page(*rows[:100], total=101)}, {"body": page(rows[100], total=101)},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertIn("page=2", calls[1][5])
        self.assertEqual(output["call_count"], 2)

    def test_missing_original_uses_exact_direct_get_not_similar_run(self):
        original = run(1)
        result, calls, output = self.invoke(requested(original), [
            {"body": page(run(2, run_attempt=2))}, {"body": original},
        ], "--host", "api.example.org")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1], [
            "api", "--hostname", "api.example.org", "--method", "GET",
            f"repos/{REPOSITORY}/actions/runs/1", "--jq", observer.ROW_PROJECTION,
        ])
        self.assertEqual(output["observations"][0]["provenance"], {"source": "direct", "call": 2})
        self.assertEqual(output["observations"][0]["run"]["id"], 1)

    def test_private_repository_record_is_supported_without_requiring_private(self):
        row = run(repository={"id": 9, "full_name": REPOSITORY, "private": True})
        result, _, output = self.invoke(requested(row), [{"body": page(row)}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output["observations"][0]["run"]["repository"]["private"])

    def test_all_input_validation_precedes_network(self):
        good = requested(run())
        invalid = [[], {}, [True], good * 2]
        for field, values in {
            "id": [True, 0, -1, 1.0, "1"],
            "workflow_id": [False, 0], "run_attempt": [True, 0],
            "head_sha": ["a" * 39, "z" * 40, None],
            "head_branch": ["", " ", "main\n"], "event": ["", None],
            "repository": [None, {"full_name": REPOSITORY, "private": False},
                           {"id": 9, "full_name": "other/repository", "private": False},
                           {"id": 9, "full_name": REPOSITORY, "private": 0}],
        }.items():
            for value in values:
                item = copy.deepcopy(good)
                item[0][field] = value
                invalid.append(item)
        missing = copy.deepcopy(good)
        del missing[0]["event"]
        invalid.append(missing)
        extra = copy.deepcopy(good)
        extra[0]["path"] = "../unexpected"
        invalid.append(extra)
        inconsistent = requested(run(), run(2, repository={"id": 10, "full_name": REPOSITORY, "private": False}))
        invalid.append(inconsistent)
        for inputs in invalid:
            with self.subTest(inputs=inputs):
                self.refuse(inputs, [], expected_calls=0)
        for raw in ('[{"id":1,"id":2}]', '[NaN]', '{'):
            with self.subTest(raw=raw):
                self.refuse(good, [], raw_input=raw, expected_calls=0)

    def test_cli_target_injection_and_bounds_refused_before_network(self):
        for name, values in {
            "--repository": ["../repo", "owner/repo/extra", "https://example/repo", "-x/repo"],
            "--host": ["https://github.com", "github.com/path", "github.com:443", "--host", "a..b", "a\nb"],
            "--max-pages": ["0", "-1", "1001"],
            "--max-calls": ["0", "-1", "10001"],
            "--timeout": ["0", "-1", "301"],
        }.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    result, calls, output = self.invoke(requested(run()), [], f"{name}={value}")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(calls, [])
                    self.assertIsNone(output)

    def test_existing_output_untouched_and_no_calls(self):
        result, calls, _ = self.invoke(requested(run()), [], existing_output="preserved")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertEqual((self.root / "result.json").read_text(), "preserved")

    def test_racing_output_creator_is_never_overwritten(self):
        result, calls, _ = self.invoke(
            requested(run()), [{"body": page(run()), "create_output": True}],
            read_output=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "result.json").read_text(), "racing creator")
        self.assertEqual(len(calls), 1)

    def test_malformed_list_membership_refused(self):
        missing = run()
        del missing["path"]
        responses = [
            {}, {"total_count": True, "workflow_runs": []},
            {"total_count": -1, "workflow_runs": []},
            {"total_count": 1.0, "workflow_runs": []},
            {"total_count": 1, "workflow_runs": {}},
            page(run(), total=2), page(run(), total=0),
            page(run(), run()), page(run(id=True)), page(missing),
            page(run(repository={"id": 9, "full_name": REPOSITORY})),
            page(run(repository={"id": 9, "full_name": REPOSITORY, "private": 0})),
        ]
        for response in responses:
            with self.subTest(response=response):
                self.refuse(requested(run()), [{"body": response}], expected_calls=1)
        self.refuse(requested(run()), [{"raw": '{"total_count":0,"total_count":1,"workflow_runs":[]}'}],
                    expected_calls=1)
        self.refuse(requested(run()), [{"raw": "not json"}], expected_calls=1)

    def test_page_count_drift_duplicate_and_short_page(self):
        first = page(*(run(i) for i in range(1, 101)), total=101)
        for second in (page(run(101), total=102), page(run(1), total=101), page(total=101)):
            with self.subTest(second=second):
                self.refuse(requested(run()), [{"body": first}, {"body": second}], expected_calls=2)

    def test_page_limit_and_call_budget_do_not_return_partial_success(self):
        self.refuse(requested(run()), [{"body": page(*(run(i) for i in range(1, 101)), total=101)}],
                    "--max-pages", "1", expected_calls=1)
        self.refuse(requested(run()), [{"body": page(*(run(i) for i in range(1, 101)), total=101)}],
                    "--max-calls", "1", expected_calls=1)
        self.refuse(requested(run(), run(2)), [{"body": page()}, {"body": run()}],
                    "--max-calls", "2", expected_calls=2)

    def test_each_binding_mismatch_in_list_or_direct_refuses(self):
        for field, value in {
            "workflow_id": 99, "head_sha": "b" * 40, "head_branch": "other",
            "run_attempt": 2, "event": "push",
            "repository": {"id": 10, "full_name": REPOSITORY, "private": False},
        }.items():
            for direct in (False, True):
                with self.subTest(field=field, direct=direct):
                    mismatched = run(**{field: value})
                    responses = [{"body": page()}, {"body": mismatched}] if direct else [{"body": page(mismatched)}]
                    self.refuse(requested(run()), responses, expected_calls=2 if direct else 1)
        self.refuse(requested(run()), [{"body": page()}, {"body": run(2)}], expected_calls=2)

    def test_unrelated_row_is_also_validated(self):
        self.refuse(requested(run()), [{"body": page(run(), run(2, repository={
            "id": 9, "full_name": "other/repository", "private": False,
        }))}], expected_calls=1)

    def test_nonterminal_statuses_remain_observations_not_completion(self):
        for status in observer.STATUSES - {"completed"}:
            with self.subTest(status=status):
                row = run(status=status, conclusion=None)
                result, _, output = self.invoke(requested(row), [{"body": page(row)}])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output["observations"][0]["run"]["status"], status)
                self.assertIsNone(output["observations"][0]["run"]["conclusion"])

    def test_inconsistent_status_conclusion_and_unsafe_paths_refuse(self):
        for updates in (
            {"status": "unknown"}, {"status": True},
            {"conclusion": None}, {"conclusion": ""}, {"conclusion": 7},
            {"status": "queued", "conclusion": "success"},
            {"status": "queued", "conclusion": ""},
            {"path": "../workflow.yml"}, {"path": "/workflow.yml"},
            {"path": "https://example/workflow.yml"}, {"path": "folder\\workflow.yml"},
        ):
            with self.subTest(updates=updates):
                self.refuse(requested(run()), [{"body": page(run(**updates))}], expected_calls=1)

    def test_get_errors_timeout_and_missing_original_never_complete_or_retry(self):
        for failed in ({"error": True}, {"sleep": 2, "body": run()}, {"body": None}):
            with self.subTest(failed=failed):
                result, calls = self.refuse(
                    requested(run()), [{"body": page()}, failed], "--timeout", "1", expected_calls=2)
                self.assertNotIn("not-a-real-secret", result.stderr)
                self.assertEqual(len(calls), 2)
        self.refuse(requested(run()), [{"error": True}], expected_calls=1)

    def test_completed_failure_is_metadata_not_skill_result(self):
        row = run(conclusion="failure")
        result, _, output = self.invoke(requested(row), [{"body": page(row)}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["observations"][0]["run"]["conclusion"], "failure")


class ObserverUnitTests(unittest.TestCase):
    def test_missing_gh_is_unknown(self):
        args = mock.Mock(max_calls=1, host="github.com", timeout=1)
        with mock.patch.object(observer.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(observer.ObservationError, "UNKNOWN"):
                observer.Reader(args).get("repos/example/evaluation/actions/runs", "{}", "list")

    def test_boolean_is_not_integer(self):
        with self.assertRaises(observer.ObservationError):
            observer.integer(True, "id")


if __name__ == "__main__":
    unittest.main()
