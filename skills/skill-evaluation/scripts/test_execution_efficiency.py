"""Synthetic projections exercised through the owning distributed CLI."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import execution_efficiency as efficiency


SCRIPT = Path(__file__).with_name("distributed_campaign.py")
FLOW = Path(__file__).with_name("fixtures") / "efficiency-event-flow.json"


def view(scope="synthetic-current", overhead=20, *, mode="fresh_window"):
    return {
        "schema_version": 1, "scope_id": scope, "source_fingerprint": "synthetic-source-v1",
        "comparison_contract": {
            "comparison_mode": mode, "population": {"synthetic-case": 2},
            "model": "synthetic-model", "effort": "high", "timeout_seconds": 10,
            "check": "synthetic-check-v1", "threshold": 1, "repetitions": 2,
            "retry": 0, "verification": "synthetic-verification-v1",
        },
        "expected_decision_ids": ["synthetic-pass", "synthetic-fail", "synthetic-audit"],
        "decisions": [
            {"id": name, "class": kind, "status": status,
             "provenance": {"reference": "opaque:synthetic-result", "digest": name,
                            "trust": "coordinator_projection"}}
            for name, kind, status in (("synthetic-pass", "product", "PASS"),
                                       ("synthetic-fail", "product", "FAIL"),
                                       ("synthetic-audit", "audit", "FAIL"))
        ],
        "expected_work_ids": ["synthetic-parent", "synthetic-overhead", "synthetic-execution",
                              "synthetic-investment"],
        "work": [
            {"id": name, "owner": owner, "parent_id": parent, "category": category,
             "seconds": seconds, "source_reference": "opaque:synthetic-work",
             "inclusion": inclusion, "purpose": purpose}
            for name, owner, parent, category, seconds, inclusion, purpose in (
                ("synthetic-parent", "owner-a", None, "coordination", 999, "aggregate", "recurring"),
                ("synthetic-overhead", "owner-a", "synthetic-parent", "coordination", overhead, "leaf", "recurring"),
                ("synthetic-execution", "owner-b", None, "execution", 80, "leaf", "recurring"),
                ("synthetic-investment", "owner-c", None, "reporting", 0, "leaf", "repair_investment"),
            )
        ],
        "outer_timing": {"clock": "monotonic", "clock_implementation": "synthetic-sleep-inclusive",
                         "suspend_inclusive": True, "elapsed_seconds": 100, "stages": [
            {"category": "coordination", "start_seconds": 0, "end_seconds": 20},
            {"category": "execution", "start_seconds": 20, "end_seconds": 100},
        ]},
        "control": {"scope_hold": False, "open_repair": False},
    }


def regression(overhead=26):
    current = view(overhead=overhead)
    current["control"]["consecutive_windows"] = [
        view("synthetic-window-1", overhead), view("synthetic-window-2", overhead)]
    return current


class EfficiencyCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-efficiency-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, current, baseline=None, policy=None, *, raw=None, raw_policy=None):
        path = self.root / "view.json"
        path.write_text(raw if raw is not None else json.dumps(current))
        command = [sys.executable, "-B", str(SCRIPT), "audit-efficiency", str(path)]
        for name, value in (("baseline", baseline), ("policy", policy)):
            if value is not None:
                target = self.root / f"{name}.json"
                target.write_text(json.dumps(value))
                command.extend([f"--{name}", str(target)])
        if raw_policy is not None:
            target = self.root / "policy.json"
            target.write_text(raw_policy)
            command.extend(["--policy", str(target)])
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, report["exit_code"], result.stderr)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertEqual(result.stderr, "")
        self.assertTrue(report["drain_allowed"])
        self.assertEqual(report["authority"], "advisory_only")
        return report

    def test_command_exit_states_and_priority(self):
        current = view()
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["coverage"]["useful_product_ids"], ["synthetic-fail", "synthetic-pass"])
        self.assertEqual(report["coverage"]["audit_ids"], ["synthetic-audit"])
        self.assertEqual(report["metrics"]["overhead_work_per_decision"]["value"], 10)
        self.assertEqual(report["metrics"]["total_work_per_decision"]["value"], 50)
        self.assertEqual(report["metrics"]["overhead_wall_fraction"]["value"], 0.2)
        self.assertEqual(report["comparison"]["reasons"], ["baseline_missing"])
        current["work"][1]["seconds"] = None
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 3)
        self.assertFalse(report["reconciliation_ready"])
        current["control"]["recurrence_signatures"] = ["synthetic-recurrence"]
        current["outer_timing"] = None
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(report["state"], "PAUSE_NEW_WORK")
        self.assertFalse(report["reconciliation_ready"])
        self.assertIn("overhead_work_per_decision", report["missing_decisive_measurement"])

    def test_invalid_work_category_names_record_and_choices(self):
        current = view()
        current["work"][2]["category"] = "result_consumption"
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(report["state"], "ERROR")
        self.assertFalse(report["reconciliation_ready"])
        self.assertIn("synthetic-execution", report["error"])
        self.assertIn("result_consumption", report["error"])
        for category in ("coordination", "execution", "infrastructure", "reporting"):
            self.assertIn(category, report["error"])

    def test_malformed_json_numeric_policy_and_id_refusals(self):
        for raw in ('{"schema_version":1,"schema_version":1}', "{", '{"value":NaN}',
                    '{"value":Infinity}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.invoke(None, raw=raw)["exit_code"], 1)
                self.assertEqual(self.invoke(view(), raw_policy=raw)["exit_code"], 1)
        for value in (True, -1, float("inf"), float("nan"), "5", 2 ** 1024):
            current = view()
            current["work"][1]["seconds"] = value
            with self.subTest(value=str(value)):
                self.assertEqual(self.invoke(current)["exit_code"], 1)
        for override in (
            {"consecutive_complete_windows": 0}, {"unproductive_same_operation_cycles": True},
            {"required_metrics": ["unknown"]}, {"require_baseline": "false"},
            {"regression_multiplier": None}, {"improvement_fraction": 1},
            {"policy_id": ""}, {"candidate_policy": {}}, {"routine_copies_target": -1},
        ):
            with self.subTest(policy=override):
                self.assertEqual(self.invoke(view(), policy=override)["exit_code"], 1)
        current = view()
        current["decisions"].append(copy.deepcopy(current["decisions"][0]))
        self.assertEqual(self.invoke(current)["exit_code"], 0)
        current["decisions"][-1]["status"] = "FAIL"
        self.assertEqual(self.invoke(current)["exit_code"], 1)
        for field in ("expected_work_ids", "expected_decision_ids"):
            current = view()
            current[field].append(current[field][0])
            self.assertEqual(self.invoke(current)["exit_code"], 1)
        current = view()
        current["work"][1]["parent_id"] = "absent"
        self.assertEqual(self.invoke(current)["exit_code"], 1)
        current = view()
        current["work"][0]["parent_id"] = "synthetic-parent"
        self.assertEqual(self.invoke(current)["exit_code"], 1)
        current = view()
        current["work"].append(dict(current["work"][1], seconds=True))
        self.assertEqual(self.invoke(current)["exit_code"], 1)
        for section, index, field in (("decisions", 0, "status"), ("work", 1, "category"),
                                      ("work", 1, "purpose")):
            current = view()
            current[section][index][field] = []
            self.assertEqual(self.invoke(current)["exit_code"], 1)
        for field in ("outer_timing", "control", "source_fingerprint"):
            current = view()
            current.pop(field)
            self.assertEqual(self.invoke(current)["exit_code"], 1)
        current = view()
        current["decisions"].append(dict(current["decisions"][0], id="synthetic-unexpected"))
        self.assertEqual(self.invoke(current)["exit_code"], 1)

    def test_coverage_candidate_provenance_zero_and_opaque_references(self):
        for status in ("PENDING", "INVALID", "UNKNOWN"):
            current = view()
            current["decisions"][0]["status"] = status
            report = self.invoke(current)
            self.assertEqual(report["exit_code"], 3)
            self.assertIsNone(report["metrics"]["outer_wall_per_decision"]["value"])
        current = view()
        current["decisions"][0]["provenance"]["trust"] = "candidate_reported"
        current["decisions"][0]["provenance"]["reference"] = "/must/not/read/or/execute"
        current["control"]["candidate_policy"] = {"require_baseline": False}
        self.assertEqual(self.invoke(current)["exit_code"], 3)
        current = view(overhead=0)
        self.assertEqual(self.invoke(current)["metrics"]["overhead_work_per_decision"]["value"], 0)
        self.assertFalse(self.invoke(current, view(overhead=0))["comparison"]["eligible"])
        current["decisions"] = current["decisions"][2:]
        self.assertEqual(self.invoke(current)["exit_code"], 3)
        current = view()
        current["work"].pop()
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 3)
        self.assertIn("synthetic-investment", report["coverage"]["unknown_work_ids"])

    def test_overlap_gap_clock_unknown_and_parallel_work_are_not_wall(self):
        for mutate in (
            lambda timing: timing["stages"][1].update(start_seconds=19),
            lambda timing: timing["stages"][1].update(start_seconds=21),
            lambda timing: timing.update(clock="utc"),
            lambda timing: timing["stages"][0].update(clock="utc"),
            lambda timing: timing["stages"][0].pop("category"),
            lambda timing: timing["stages"][0].pop("start_seconds"),
            lambda timing: timing.update(scope_id="foreign-scope"),
            lambda timing: timing["stages"][0].update(elapsed_seconds=99),
        ):
            current = view()
            mutate(current["outer_timing"])
            report = self.invoke(current)
            self.assertIsNone(report["metrics"]["overhead_wall_fraction"]["value"])
            self.assertTrue(report["metrics"]["overhead_wall_fraction"]["reasons"])
        current = view(overhead=200)
        report = self.invoke(current)
        self.assertEqual(report["metrics"]["outer_wall_seconds"]["value"], 100)
        self.assertEqual(report["metrics"]["overhead_work_per_decision"]["value"], 100)
        self.assertEqual(report["metrics"]["overhead_wall_fraction"]["value"], 0.2)

    def test_foreign_outer_scope_cannot_satisfy_required_wall_metric(self):
        current = view()
        current["outer_timing"]["scope_id"] = "different-decision-window"
        report = self.invoke(current, policy={"required_metrics": ["outer_wall_per_decision"]})
        self.assertEqual(report["exit_code"], 3)
        self.assertFalse(report["reconciliation_ready"])
        self.assertIsNone(report["metrics"]["outer_wall_per_decision"]["value"])
        self.assertIn("foreign_outer_scope", report["metrics"]["outer_wall_per_decision"]["reasons"])

    def test_unestablished_sleep_coverage_cannot_satisfy_required_wall(self):
        for coverage in ("absent", None, False):
            with self.subTest(coverage=coverage):
                current = view()
                if coverage == "absent":
                    current["outer_timing"].pop("clock_implementation")
                    current["outer_timing"].pop("suspend_inclusive")
                else:
                    current["outer_timing"]["suspend_inclusive"] = coverage
                report = self.invoke(
                    current, policy={"required_metrics": ["outer_wall_per_decision"]})
                self.assertEqual(report["exit_code"], 3)
                self.assertFalse(report["reconciliation_ready"])
                self.assertIsNone(report["metrics"]["outer_wall_seconds"]["value"])
                self.assertIsNone(report["metrics"]["overhead_wall_fraction"]["value"])
                self.assertEqual(report["metrics"]["overhead_work_per_decision"]["value"], 10)

    def test_malformed_clock_coverage_is_an_explicit_input_error(self):
        for metadata in (
            {"suspend_inclusive": 1},
            {"suspend_inclusive": "true"},
            {"clock_implementation": ""},
            {"clock_implementation": None},
        ):
            with self.subTest(metadata=metadata):
                current = view()
                current["outer_timing"].update(metadata)
                report = self.invoke(current)
                self.assertEqual(report["exit_code"], 1)
                self.assertEqual(report["state"], "ERROR")
                self.assertIn("clock", report["error"])

    def test_regression_only_boundary_and_intervening_ineligible_window(self):
        baseline = view("synthetic-baseline")
        report = self.invoke(regression(), baseline)
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual([key for key, value in report["triggers"].items() if value],
                         ["quantified_regression"])
        self.assertFalse(report["reconciliation_ready"])
        self.assertEqual(self.invoke(regression(25), baseline)["exit_code"], 0)
        current = regression()
        current["control"]["consecutive_windows"][1]["decisions"][0]["status"] = "INVALID"
        report = self.invoke(current, baseline)
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["comparison"]["consecutive_regression_windows"], 1)
        current["control"]["consecutive_windows"][1]["work"][1]["seconds"] = None
        self.assertEqual(self.invoke(current, baseline)["exit_code"], 0)

    def test_copy_only_cycle_only_and_reset(self):
        current = view()
        event = {"operation_id": "synthetic-operation", "operation_digest": "synthetic-digest",
                 "implementation_changed": False, "new_executable_copies": 1}
        current["control"]["operation_materializations"] = [event]
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual([key for key, value in report["triggers"].items() if value], ["duplicate_copy"])
        event["implementation_changed"] = True
        self.assertEqual(self.invoke(current)["exit_code"], 0)
        current = view()
        cycle = {"operation_id": "synthetic-operation", "operation_digest": "synthetic-digest",
                 "new_decision_evidence": False, "evidence_reference": "opaque:synthetic-evidence"}
        current["control"]["same_operation_cycles"] = [cycle, copy.deepcopy(cycle)]
        report = self.invoke(current)
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual([key for key, value in report["triggers"].items() if value], ["unproductive_cycle"])
        for last in (dict(cycle, operation_digest="synthetic-new-digest"),
                     dict(cycle, new_decision_evidence=True),
                     dict(cycle, operation_id="synthetic-new-operation")):
            current["control"]["same_operation_cycles"].append(last)
            self.assertEqual(self.invoke(current)["exit_code"], 0)
            current["control"]["same_operation_cycles"].pop()

    def test_held_windows_preserve_a_persistent_regression(self):
        current = regression()
        for window in [*current["control"]["consecutive_windows"], current]:
            window["control"].update(scope_hold=True, open_repair=True)
        report = self.invoke(current, view("synthetic-baseline"))
        self.assertEqual(report["exit_code"], 2)
        self.assertTrue(report["triggers"]["quantified_regression"])
        self.assertEqual(report["comparison"]["consecutive_regression_windows"], 3)
        self.assertFalse(report["reconciliation_ready"])

    def test_present_trusted_retained_status_mutations_are_integrity_errors(self):
        baseline = view("synthetic-baseline", mode="retained_replay")
        for index in (1, 2):
            for status in ("INVALID", "PENDING", "UNKNOWN"):
                current = view(mode="retained_replay")
                current["decisions"][index]["status"] = status
                with self.subTest(index=index, status=status):
                    report = self.invoke(current, baseline)
                    self.assertEqual(report["exit_code"], 2)
                    self.assertTrue(report["triggers"]["integrity"])
                    self.assertFalse(report["reconciliation_ready"])

    def test_retained_fresh_contract_and_total_investment(self):
        baseline = view("synthetic-baseline", mode="retained_replay")
        current = view(mode="retained_replay", overhead=10)
        current["source_fingerprint"] = "synthetic-source-v2"
        report = self.invoke(current, baseline)
        self.assertTrue(report["comparison"]["target_met"] is False)
        self.assertTrue(report["comparison"]["eligible"])
        current["decisions"][0]["provenance"]["digest"] = "synthetic-mutated-result"
        self.assertEqual(self.invoke(current, baseline)["exit_code"], 2)
        current = view(mode="retained_replay")
        current["decisions"].pop(0)
        report = self.invoke(current, baseline)
        self.assertEqual(report["exit_code"], 3)
        self.assertFalse(report["triggers"]["integrity"])
        current = view(mode="retained_replay")
        current["decisions"][0]["provenance"].update(trust="candidate_reported", digest="unverified")
        report = self.invoke(current, baseline)
        self.assertEqual(report["exit_code"], 3)
        self.assertFalse(report["triggers"]["integrity"])
        baseline = view("synthetic-baseline")
        current = view(overhead=0)
        current["decisions"][0].update(id="synthetic-fresh-attempt", status="FAIL")
        current["expected_decision_ids"][0] = "synthetic-fresh-attempt"
        current["decisions"][0]["provenance"]["digest"] = "synthetic-fresh-outcome"
        self.assertTrue(self.invoke(current, baseline)["comparison"]["target_met"])
        current["work"][-1]["seconds"] = 1000
        report = self.invoke(current, baseline)
        self.assertEqual(report["metrics"]["overhead_work_per_decision"]["value"], 0)
        self.assertFalse(report["comparison"]["target_met"])
        self.assertLess(report["comparison"]["total_improvement_fraction"], 0)
        current["work"][-1]["seconds"] = None
        self.assertIsNone(self.invoke(current, baseline)["comparison"]["total_improvement_fraction"])
        current = view()
        current["comparison_contract"]["model"] = "different-synthetic-model"
        report = self.invoke(current, baseline)
        self.assertEqual(report["exit_code"], 0)
        self.assertFalse(report["comparison"]["eligible"])
        self.assertEqual(self.invoke(current, baseline, {"require_baseline": True})["exit_code"], 3)
        current = view()
        current["comparison_contract"]["threshold"] = True
        self.assertFalse(self.invoke(current, baseline)["comparison"]["eligible"])

    def test_control_and_window_refusals(self):
        for field, value in (
            ("scope_hold", 1), ("open_repair", None), ("integrity_violation", "false"),
            ("quality_regressions", -1), ("recurrence_signatures", [False]),
            ("operation_materializations", [{"operation_id": "synthetic", "operation_digest": "digest",
                                             "implementation_changed": False, "new_executable_copies": True}]),
            ("same_operation_cycles", [{"operation_id": "synthetic", "operation_digest": "digest",
                                       "new_decision_evidence": 0, "evidence_reference": "opaque:synthetic"}]),
        ):
            current = view()
            current["control"][field] = value
            self.assertEqual(self.invoke(current)["exit_code"], 1)
        for field, value in (("integrity_violation", True), ("quality_regressions", 1),
                             ("open_repair", True), ("scope_hold", True)):
            current = view()
            current["control"][field] = value
            self.assertEqual(self.invoke(current)["exit_code"], 2)
        current = regression()
        current["control"]["consecutive_windows"][0]["scope_id"] = current["scope_id"]
        self.assertEqual(self.invoke(current, view("synthetic-baseline"))["exit_code"], 1)
        current = regression()
        current["control"]["consecutive_windows"][0]["control"]["consecutive_windows"] = [view()]
        self.assertEqual(self.invoke(current, view("synthetic-baseline"))["exit_code"], 1)
        current = view()
        current["outer_timing"]["stages"][0]["start_seconds"] = True
        self.assertEqual(self.invoke(current)["exit_code"], 1)

    def test_synthetic_owner_event_flow_drain_gap_reconcile_then_clear(self):
        fixture = json.loads(FLOW.read_text())
        self.assertTrue(fixture["synthetic"])
        events = {event["event"]: event for event in fixture["events"]}
        baseline = view("synthetic-baseline")
        report = self.invoke(regression(), baseline)
        self.assertEqual(report["exit_code"], events["regression"]["exit_code"])
        self.assertTrue(report["drain_allowed"])
        self.assertEqual(events["measurement_attempt"]["attempts"], 1)
        self.assertEqual(events["measurement_attempt"]["outcome"], "inconclusive")
        held = view()
        held["control"].update(scope_hold=True, open_repair=True)
        held["work"][1]["seconds"] = None
        report = self.invoke(held, baseline)
        self.assertEqual(report["exit_code"], events["missing_evidence"]["exit_code"])
        self.assertFalse(report["reconciliation_ready"])
        held["work"][1]["seconds"] = 10
        report = self.invoke(held, baseline)
        self.assertEqual(report["exit_code"], events["held_audit"]["exit_code"])
        self.assertTrue(report["reconciliation_ready"])
        self.assertTrue(held["control"]["scope_hold"])
        proof = events["corrected_proof"]
        self.assertEqual(proof["proof_status"], "accepted")
        self.assertTrue(proof["proof_reference"] and proof["applicability_reference"])
        self.assertLess([event["event"] for event in fixture["events"]].index("explicit_reconcile"),
                        [event["event"] for event in fixture["events"]].index("final_audit"))
        held["control"].update(scope_hold=False, open_repair=False)
        report = self.invoke(held, baseline)
        self.assertEqual(report["exit_code"], events["final_audit"]["exit_code"])
        self.assertTrue(report["reconciliation_ready"])
        self.assertEqual([record["status"] for record in fixture["learning"]], ["inconclusive", "validated"])


if __name__ == "__main__":
    unittest.main()
