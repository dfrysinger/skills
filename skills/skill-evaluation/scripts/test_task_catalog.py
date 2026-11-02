import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import skill_eval as native
import measurement
import task_catalog as catalog
import test_skill_eval as fixtures


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "corpus"
        native.init_corpus(self.root)
        fixtures.SkillEvalTests.make_case(self)
        self.frozen = native.freeze_case(self.root, "example-case", False)
        self.revision = self.frozen.name
        self.catalog = self.base / "catalog"
        self.call("init")

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, command, *args, failure=None, root=None):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = native.main(["catalog", command, str(root or self.catalog), *map(str, args)])
        if failure is not None:
            self.assertEqual(status, 1, output.getvalue())
            self.assertIn(failure, error.getvalue())
            return None
        self.assertEqual(status, 0, error.getvalue())
        return json.loads(output.getvalue())

    def register(self, *, family="incident", title="Example", revision=None, root=None,
                 failure=None, history=False):
        return self.call(
            "import", "--corpus", self.root, "--namespace", "sample",
            "--case", "example-case", "--family", family, "--title", title,
            "--summary", "Synthetic continuation behavior", "--behavior", "continuation",
            *(["--revision", revision] if revision else []),
            *(["--include-history"] if history else []), root=root, failure=failure,
        )

    def plan(self, role="regression", revision=None, failure=None, root=None):
        return self.call(
            "plan", "--member", f"sample:example-case@{revision or self.revision}",
            "--lineage", "example-skill", "--role", role, failure=failure, root=root,
        )

    def expose(self, kind):
        return self.call("expose", "--family", "incident", "--lineage", "example-skill",
                         "--kind", kind, "--note", "Synthetic operator attestation")

    def test_exact_revision_and_native_verifier_after_pointer_moves(self):
        self.register()
        plan = self.plan()
        self.call("bind", "--namespace", "sample", "--corpus", self.root)
        case = self.root / "cases/example-case"
        (case / "evidence/candidate-pass-1/product.md").write_text("new revision\n")
        newer = native.freeze_case(self.root, "example-case", True).name
        self.assertNotEqual(newer, self.revision)
        pointer = (self.root / "frozen/example-case/current.json").read_bytes()
        output = self.base / "replay"
        self.call("materialize", "--suite", plan["suite"], "--output", output)
        self.assertEqual(native.frozen_case_path(output / "sample", "example-case").name, self.revision)
        self.assertGreater(native.verify_case(output / "sample", "example-case"), 0)
        self.assertEqual((self.root / "frozen/example-case/current.json").read_bytes(), pointer)
        self.assertEqual(native.load_corpus(output / "sample")["cases"], ["example-case"])

    def test_unbound_clone_searches_but_cannot_materialize(self):
        self.register()
        plan = self.plan()
        self.call("bind", "--namespace", "sample", "--corpus", self.root)
        clone = self.base / "clone"
        shutil.copytree(self.catalog, clone, ignore=shutil.ignore_patterns(".local"))
        for folder in catalog.KINDS:
            if not any((clone / folder).iterdir()):
                (clone / folder).rmdir()
        found = self.call("search", "--skill", "example-skill", root=clone)
        self.assertEqual(found["tasks"][0]["binding"], "unbound")
        output = self.base / "unbound-output"
        self.call("materialize", "--suite", plan["suite"], "--output", output,
                  failure="No such file", root=clone)
        self.assertFalse(output.exists())
        shared = json.dumps(catalog.load(clone))
        self.assertNotIn(str(self.root), shared)
        self.assertNotIn("hidden correction", shared)

    def test_unknown_holdout_and_later_exposure_rechecks_old_plan(self):
        self.register()
        self.plan("holdout", failure="unknown or contaminated")
        self.expose("unexposed")
        plan = self.plan("holdout")
        self.assertEqual(plan["limitation"], catalog.LIMITATION)
        before = plan["exposure_snapshot"]
        self.call("bind", "--namespace", "sample", "--corpus", self.root)
        self.call("materialize", "--suite", plan["suite"], "--output", self.base / "clean")
        self.expose("feedback")
        self.assertNotEqual(catalog.snapshot(catalog.load(self.catalog)), before)
        self.expose("unexposed")
        self.plan("holdout", failure="unknown or contaminated")
        self.call("materialize", "--suite", plan["suite"], "--output", self.base / "dirty",
                  failure="unknown or contaminated")
        self.assertFalse((self.base / "dirty").exists())

    def test_explicit_unknown_cannot_be_erased(self):
        self.register()
        self.expose("unknown")
        self.expose("unexposed")
        self.plan("holdout", failure="unknown or contaminated")

    def test_sibling_revision_cannot_change_family_or_launder_exposure(self):
        self.register()
        self.plan()
        (self.root / "cases/example-case/evidence/candidate-pass-1/product.md").write_text("revision B")
        newer = native.freeze_case(self.root, "example-case", True).name
        self.register(family="different-incident", failure="conflicting family")
        self.register()
        self.expose("unexposed")
        self.plan("holdout", revision=newer, failure="unknown or contaminated")
        self.plan("holdout", revision=self.revision, failure="unknown or contaminated")

    def test_idempotence_and_merged_conflicts_refuse_every_reader(self):
        other = self.base / "other"
        self.call("init", root=other)
        self.register()
        before = sorted(path.name for path in (self.catalog / "tasks").iterdir())
        self.register()
        self.assertEqual(sorted(path.name for path in (self.catalog / "tasks").iterdir()), before)
        self.register(title="Conflicting title", root=other)
        for path in (other / "tasks").iterdir():
            shutil.copyfile(path, self.catalog / "tasks" / path.name)
        for command in ("search", "history"):
            self.call(command, failure="conflicting metadata")
        self.plan(failure="conflicting metadata")
        self.call("materialize", "--suite", "a" * 64, "--output", self.base / "x",
                  failure="conflicting metadata")

    def test_corruption_and_symlinks_leave_no_partial_output(self):
        self.register()
        plan = self.plan()
        self.call("bind", "--namespace", "sample", "--corpus", self.root)
        packet = self.frozen / "candidate-pass-1/product.md"
        original = packet.read_bytes()
        packet.write_text("corrupt")
        output = self.base / "corrupt"
        self.call("materialize", "--suite", plan["suite"], "--output", output,
                  failure="digest mismatch")
        self.assertFalse(output.exists())
        packet.write_bytes(original)
        packet.unlink()
        packet.symlink_to(self.base / "outside")
        self.call("materialize", "--suite", plan["suite"], "--output", output,
                  failure="symlink")
        self.assertFalse(output.exists())
        self.assertFalse(list(self.base.glob(".catalog-stage-*")))

    def test_record_schemas_hashes_and_symlink_boundaries(self):
        self.register()
        path = next((self.catalog / "tasks").iterdir())
        original = path.read_bytes()
        path.write_text("{}")
        self.call("search", failure="content hash mismatch")
        path.write_bytes(original)
        outside = self.base / "external"
        path.rename(outside)
        path.symlink_to(outside)
        self.call("search", failure="symlink")
        path.unlink()
        path.write_bytes(original)
        task = json.loads(original)
        task["answer"] = "must not be accepted"
        path.unlink()
        bad = self.catalog / "tasks" / f"{catalog.identity(task)}.json"
        bad.write_bytes(catalog.encoded(task))
        self.call("search", failure="record schema")

    def test_unsafe_output_and_traversal_refused(self):
        self.register()
        plan = self.plan()
        self.call("bind", "--namespace", "sample", "--corpus", self.root)
        for output in (self.catalog / "packet", self.root / "packet"):
            self.call("materialize", "--suite", plan["suite"], "--output", output,
                      failure="cannot")
            self.assertFalse(output.exists())
        self.call("bind", "--namespace", "../escape", "--corpus", self.root,
                  failure="invalid namespace")
        self.call("plan", "--member", "../escape:example-case@" + self.revision,
                  "--lineage", "example-skill", "--role", "regression",
                  failure="member must")
        self.call("materialize", "--suite", "../escape", "--output", self.base / "x",
                  failure="invalid suite")

    def test_public_cli_dispatch_and_legacy_verify(self):
        self.register()
        script = Path(native.__file__)
        command = subprocess.run(
            [sys.executable, str(script), "catalog", "search", str(self.catalog)],
            text=True, capture_output=True,
        )
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(json.loads(command.stdout)["tasks"][0]["revision"], self.revision)
        command = subprocess.run([sys.executable, str(script), "verify", str(self.root)],
                                 text=True, capture_output=True)
        self.assertEqual(command.returncode, 0, command.stderr)

    def test_native_history_keeps_first_failure_later_pass_and_unknown_measurement(self):
        for name, status in (("first", "FAIL"), ("later", "PASS")):
            path = self.root / "runs" / name / "example-case"
            path.mkdir(parents=True)
            native.write_json(path / "execution-result.json", {
                "schema_version": 1, "case_id": "example-case", "case_type": "prose",
                "case_revision": self.revision, "execution_status": status,
                "behavioral_verdict": None, "model": "gpt-example", "effort": "high",
                "timeout_seconds": 10, "elapsed_seconds": 2,
            })
            native.write_json(path / "skill-identity.json",
                              {"name": "example-skill", "files": []})
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.register(history=True)
        self.register(history=True)
        rows = self.call("history")["runs"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["correctness"] for row in rows}, {"FAIL", "PASS"})
        self.assertEqual(len({row["run_key"] for row in rows}), 2)
        self.assertTrue(all(row["elapsed_seconds"] is None and row["credits"] is None for row in rows))
        self.assertTrue(all(row["legacy_execution_elapsed_seconds"] == 2 for row in rows))
        self.assertNotIn(str(self.root), json.dumps(rows))
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_native_clock_and_unanswerable_prose_history_are_preserved(self):
        path = self.root / "runs" / "unanswerable" / "example-case"
        path.mkdir(parents=True)
        native.write_json(path / "judgment-example.json", {"verdict": "UNANSWERABLE"})
        timing = measurement.Timeline().finish("completed")
        native.write_json(path / "timing.json", timing)
        self.register(history=True)
        row = self.call("history")["runs"][0]
        self.assertEqual(row["correctness"], "UNANSWERABLE")
        self.assertEqual(row["suite_result"], "UNANSWERABLE")
        self.assertEqual(row["clock_implementation"], timing["clock_implementation"])
        self.assertEqual(row["elapsed_seconds"], timing["elapsed_seconds"])

    def test_missing_native_run_artifacts_remain_distinct_unknown_observations(self):
        native.write_json(self.root / "suite-runs" / "early-errors" / "suite-result.json", {
            "schema_version": 1, "max_attempts": 2, "model": "gpt-example",
            "case_revisions": {"example-case": self.revision},
            "cases": [{"case_id": "example-case", "attempts": [
                {"attempt": 1, "result": "ERROR"},
                {"attempt": 2, "result": "ERROR"},
            ]}],
        })
        self.register(history=True)
        rows = self.call("history")["runs"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["attempt"] for row in rows}, {1, 2})
        self.assertEqual(len({row["run_key"] for row in rows}), 2)
        self.assertTrue(all(row["correctness"] == "ERROR" for row in rows))
        self.assertTrue(all(row["clock_implementation"] is None and
                            row["suspend_inclusive"] is None for row in rows))


if __name__ == "__main__":
    unittest.main()
