"""Local source-node diagnostics; no containers, models, or private fixtures."""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import stat
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import quality_review
import repository_task as repository
import skill_eval as evaluator
from test_repository_task import RepositoryTaskTests


class SourceNodeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RepositoryTaskTests()
        self.fixture.setUp()
        self.temporary_parent = Path(self.fixture.temp.name).parent
        self.root = self.fixture.root
        self.frozen = self.fixture.freeze()
        self.definition = evaluator.read_json(self.frozen / "case.json")
        self.candidate = self.root / "source"
        evaluator.copy_packet(self.frozen / "repository", self.candidate)
        self.patch = self.root / "candidate.patch"
        self.sentinel = self.root / "sentinel"
        self.sentinel_bytes = b"HOST REFERENT MUST NOT ENTER SOURCE EVIDENCE\n"
        self.sentinel.write_bytes(self.sentinel_bytes)
        self.sentinel.chmod(0o640)
        self.sentinel_mode = self.sentinel.stat().st_mode
        self.outside_directory = self.root / "outside-directory"
        self.outside_directory.mkdir()
        (self.outside_directory / "hidden").write_bytes(self.sentinel_bytes)

    def tearDown(self):
        self.fixture.tearDown()

    def add_links(self):
        (self.candidate / "directory").mkdir()
        (self.candidate / "directory" / "child.py").write_bytes(b"ordinary child\n")
        targets = {
            "relative": b"code.py",
            "broken": b"does-not-exist",
            "directory-link": b"directory",
            "outward": b"../sentinel",
            "absolute": os.fsencode(self.sentinel),
            "outward-directory": b"../outside-directory",
            "lexical": b"directory//../code.py",
            "nontextual": b"missing-\xff",
            "multiline": b"missing\nanother-target",
            "source-nodes.json": b"../sentinel",
        }
        for name, target in targets.items():
            os.symlink(target, os.fsencode(self.candidate / name))
        (self.candidate / "code.py").write_bytes(b"def add(a, b): return a + b\n")
        return targets

    @contextmanager
    def guard_host_referents(self):
        original_stat = Path.stat
        original_chmod = Path.chmod
        original_scandir = os.scandir
        original_open = builtins.open
        original_io_open = io.open

        def no_link_or_sentinel(path):
            if isinstance(path, int):
                return
            path = Path(os.fsdecode(path))
            self.assertNotEqual(path, self.sentinel, "host sentinel accessed")
            self.assertFalse(path.is_relative_to(self.outside_directory), "outside directory accessed")
            for ancestor in (path, *path.parents):
                # Platform temp-directory aliases are outside the synthetic source boundary.
                if ancestor == self.temporary_parent:
                    break
                try:
                    mode = original_stat(ancestor, follow_symlinks=False).st_mode
                except FileNotFoundError:
                    continue
                self.assertFalse(stat.S_ISLNK(mode), f"following operation on {path}")

        def guarded_stat(path, *, follow_symlinks=True):
            if follow_symlinks:
                no_link_or_sentinel(path)
            return original_stat(path, follow_symlinks=follow_symlinks)

        def guarded_chmod(path, mode, **kwargs):
            no_link_or_sentinel(path)
            return original_chmod(path, mode, **kwargs)

        def guarded_scandir(path):
            no_link_or_sentinel(path)
            return original_scandir(path)

        def guarded_open(path, *args, **kwargs):
            no_link_or_sentinel(path)
            return original_open(path, *args, **kwargs)

        def guarded_io_open(path, *args, **kwargs):
            no_link_or_sentinel(path)
            return original_io_open(path, *args, **kwargs)

        with (
            mock.patch.object(Path, "stat", guarded_stat),
            mock.patch.object(Path, "chmod", guarded_chmod),
            mock.patch.object(os, "scandir", guarded_scandir),
            mock.patch.object(builtins, "open", guarded_open),
            mock.patch.object(io, "open", guarded_io_open),
        ):
            yield

    def assert_sentinel_unchanged(self):
        self.assertEqual(self.sentinel.read_bytes(), self.sentinel_bytes)
        self.assertEqual(self.sentinel.stat().st_mode, self.sentinel_mode)
        self.assertEqual((self.outside_directory / "hidden").read_bytes(), self.sentinel_bytes)

    def test_export_and_trusted_apply_preserve_raw_nodes_without_following(self):
        targets = self.add_links()
        fresh = self.root / "fresh"
        evaluator.copy_packet(self.frozen / "repository", fresh)
        with self.guard_host_referents():
            repository.export_patch(self.frozen, self.candidate, self.patch)
            repository.apply_patch(fresh, self.patch)
            paths = {
                path.relative_to(fresh).as_posix()
                for path in repository.ordinary_files(fresh, allow_source_links=True)
            }
            for name, target in targets.items():
                self.assertTrue(stat.S_ISLNK((fresh / name).lstat().st_mode))
                self.assertEqual(os.readlink(os.fsencode(fresh / name)), target)
            self.assertIn("directory/child.py", paths)
            self.assertIn("directory-link", paths)
            self.assertNotIn("directory-link/child.py", paths)
        content = self.patch.read_bytes()
        self.assertEqual(content.count(b"new file mode 120000"), len(targets))
        self.assertIn(b"+def add(a, b): return a + b", content)
        self.assertNotIn(self.sentinel_bytes, content)
        self.assertEqual((fresh / "code.py").read_bytes(), (self.candidate / "code.py").read_bytes())
        self.assert_sentinel_unchanged()

    def test_replacing_source_file_and_adding_nested_link_preserves_node_types(self):
        (self.candidate / "code.py").unlink()
        (self.candidate / "code.py").symlink_to("remove.txt")
        (self.candidate / "nested").mkdir()
        (self.candidate / "nested" / "link").symlink_to("../remove.txt")
        repository.export_patch(self.frozen, self.candidate, self.patch)
        fresh = self.root / "fresh"
        evaluator.copy_packet(self.frozen / "repository", fresh)
        repository.apply_patch(fresh, self.patch)
        self.assertEqual(os.readlink(fresh / "code.py"), "remove.txt")
        self.assertEqual(os.readlink(fresh / "nested" / "link"), "../remove.txt")
        packet = self.root / "packet"
        quality_review.prepare_packet(self.frozen, self.definition, self.patch, packet)
        self.assertEqual((packet / "candidate" / "code.py").read_bytes(), b"remove.txt")
        self.assertEqual((packet / "candidate" / "nested" / "link").read_bytes(), b"../remove.txt")
        self.assertEqual(
            (packet / "baseline" / "code.py").read_bytes(),
            (self.frozen / "repository" / "code.py").read_bytes())

    def test_new_link_is_exported_beside_unchanged_recorded_setup_link(self):
        (self.candidate / "runtime-link").symlink_to("runtime-target")
        links = repository.observe_setup_links(self.frozen, self.candidate)
        (self.candidate / "new-link").symlink_to("runtime-target")
        repository.export_patch(self.frozen, self.candidate, self.patch, links)
        fresh = self.root / "fresh"
        evaluator.copy_packet(self.frozen / "repository", fresh)
        repository.apply_patch(fresh, self.patch)
        self.assertEqual(os.readlink(fresh / "new-link"), "runtime-target")
        self.assertFalse((fresh / "runtime-link").is_symlink())
        self.assertNotIn(b"runtime-link", self.patch.read_bytes())

    def test_strict_traversal_and_special_and_git_refusals_remain(self):
        link = self.candidate / "link"
        link.symlink_to(self.sentinel)
        with self.guard_host_referents(), self.assertRaisesRegex(ValueError, "unsupported"):
            repository.ordinary_files(self.candidate)
        link.unlink()
        fifo = self.candidate / "fifo"
        os.mkfifo(fifo)
        for allow in (False, True):
            with self.subTest(allow=allow), self.assertRaisesRegex(ValueError, "unsupported"):
                repository.ordinary_files(self.candidate, allow_source_links=allow)
        fifo.unlink()
        metadata = self.candidate / ".git"
        metadata.symlink_to(self.sentinel)
        for allow in (False, True):
            with self.subTest(allow=allow), self.assertRaisesRegex(ValueError, "Git metadata"):
                repository.ordinary_files(self.candidate, allow_source_links=allow)
        with self.guard_host_referents():
            repository.export_patch(self.frozen, self.candidate, self.patch)
        self.assertEqual(self.patch.read_bytes(), b"")
        self.assert_sentinel_unchanged()

    def test_export_disables_candidate_and_ambient_git_configuration(self):
        self.add_links()
        metadata = self.candidate / ".git"
        metadata.mkdir()
        marker = self.root / "configuration-was-executed"
        driver = f"touch {marker}"
        (metadata / "config").write_text(
            f'[filter "candidate"]\nclean = {driver}\nrequired = true\n'
            f'[diff]\nexternal = {driver}\n')
        (self.candidate / ".gitattributes").write_text("* filter=candidate diff=candidate\n")
        config = self.root / "global-config"
        config.write_text(
            f'[filter "candidate"]\nclean = {driver}\nrequired = true\n'
            '[core]\nsymlinks = false\n')
        with mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.symlinks",
            "GIT_CONFIG_VALUE_0": "false",
        }):
            repository.export_patch(self.frozen, self.candidate, self.patch)
            fresh = self.root / "fresh"
            evaluator.copy_packet(self.frozen / "repository", fresh)
            repository.apply_patch(fresh, self.patch)
        self.assertFalse(marker.exists())
        self.assertTrue((fresh / "relative").is_symlink())
        self.assertIn(b"new file mode 120000", self.patch.read_bytes())
        self.assertNotIn(b"configuration-was-executed", self.patch.read_bytes())

    def test_trusted_apply_refuses_paths_through_symlink_and_git_metadata(self):
        for name, target in (("link-parent", "../"), (".git", "irrelevant")):
            with self.subTest(name=name):
                fresh = self.root / f"fresh-{name}"
                evaluator.copy_packet(self.frozen / "repository", fresh)
                (fresh / name).symlink_to(target)
                self.patch.write_text(
                    f"diff --git a/{name}/sentinel b/{name}/sentinel\n"
                    f"--- a/{name}/sentinel\n+++ b/{name}/sentinel\n"
                    "@@ -1 +1 @@\n-HOST REFERENT MUST NOT ENTER SOURCE EVIDENCE\n+changed\n")
                with self.assertRaisesRegex(ValueError, "trusted Git operation failed"):
                    repository.apply_patch(fresh, self.patch)
        self.assert_sentinel_unchanged()

    def test_review_projection_correspondence_and_no_referent_access(self):
        targets = self.add_links()
        repository.export_patch(self.frozen, self.candidate, self.patch)
        original_patch = self.patch.read_bytes()
        packet = self.root / "packet"
        original_digest = quality_review.digest

        def digest_after_projection(path):
            if Path(path).is_relative_to(packet):
                self.assertFalse(any(
                    stat.S_ISLNK(node.lstat().st_mode)
                    for node in repository.ordinary_files(packet, allow_source_links=True)
                ))
            return original_digest(path)

        with self.guard_host_referents(), mock.patch.object(
            quality_review, "digest", side_effect=digest_after_projection,
        ):
            manifest = quality_review.prepare_packet(
                self.frozen, self.definition, self.patch, packet)
            metadata = evaluator.read_json(packet / "source-nodes.json")
            self.assertEqual(metadata["schema_version"], 1)
            self.assertEqual(metadata["representation"], "symlink-target-bytes")
            nodes = {node["path"]: node for node in metadata["nodes"]}
            self.assertEqual(set(nodes), {f"candidate/{name}" for name in targets})
            for name, target in targets.items():
                relative = f"candidate/{name}"
                projected = packet / relative
                self.assertTrue(stat.S_ISREG(projected.lstat().st_mode))
                self.assertEqual(projected.read_bytes(), target)
                self.assertEqual(nodes[relative], {
                    "path": relative, "kind": "symlink", "git_mode": "120000",
                    "raw_target_sha256": hashlib.sha256(target).hexdigest(),
                    "projection_sha256": evaluator.digest(projected),
                })
            self.assertIn("source-nodes.json", {item["path"] for item in manifest})
            for item in manifest:
                path = packet / item["path"]
                self.assertEqual(evaluator.digest(path), item["sha256"])
                self.assertTrue(stat.S_ISREG(path.lstat().st_mode))
                self.assertEqual(path.stat().st_mode & 0o222, 0)
                self.assertNotIn(self.sentinel_bytes, path.read_bytes())
            self.assertEqual(
                (packet / "baseline" / "code.py").read_bytes(),
                (self.frozen / "repository" / "code.py").read_bytes())
            self.assertEqual(
                (packet / "candidate" / "code.py").read_bytes(),
                (self.candidate / "code.py").read_bytes())
        self.assertEqual(self.patch.read_bytes(), original_patch)
        self.assertTrue((self.candidate / "absolute").is_symlink())
        self.assert_sentinel_unchanged()

    def test_ordinary_manifest_is_preserved_with_empty_node_metadata(self):
        self.patch.write_bytes((self.frozen / "judge-reference" / "reference.patch").read_bytes())
        packet = self.root / "packet"
        manifest = quality_review.prepare_packet(
            self.frozen, self.definition, self.patch, packet)
        expected = {}
        for prefix in ("baseline", "candidate"):
            for item in evaluator.read_json(self.frozen / "repository" / "bundle-manifest.json")["files"]:
                expected[f"{prefix}/{item['path']}"] = item["sha256"]
        expected["candidate/code.py"] = hashlib.sha256(b"def add(a, b): return a + b\n").hexdigest()
        actual = {item["path"]: item["sha256"] for item in manifest
                  if item["path"].startswith(("baseline/", "candidate/"))}
        self.assertEqual(actual, expected)
        self.assertEqual(evaluator.read_json(packet / "source-nodes.json")["nodes"], [])

    def test_link_findings_use_exact_text_and_nontextual_evidence_is_not_invented(self):
        self.add_links()
        repository.export_patch(self.frozen, self.candidate, self.patch)
        packet = self.root / "packet"
        quality_review.prepare_packet(self.frozen, self.definition, self.patch, packet)
        finding = {
            "path": "candidate/multiline", "start_line": 2, "end_line": 2,
            "quotation": "another-target", "severity": "medium",
            "trigger": "A consumer uses this link", "explanation": "The target includes a newline",
        }
        value = {"judgment": "needs_revision", "summary": "Literal link evidence", "findings": [finding]}
        quality_review.validate_review(value, packet)
        finding["quotation"] = "invented referent source"
        with self.assertRaisesRegex(ValueError, "quotation"):
            quality_review.validate_review(value, packet)
        finding.update(path="candidate/nontextual", start_line=1, end_line=1, quotation="missing")
        with self.assertRaisesRegex(ValueError, "textual source"):
            quality_review.validate_review(value, packet)
        quality_review.validate_review({
            "judgment": "unassessable", "summary": "Non-textual decisive link evidence", "findings": [],
        }, packet)
        self.assertEqual(quality_review.PROMPT_VERSION, "source-quality-v3")
        for disclosure in ("source-nodes.json", "raw link-target bytes", "not the",
                           "Never resolve or follow", "non-textual decisive link evidence requires"):
            self.assertIn(disclosure, quality_review.PROMPT)

    def test_partial_projection_never_hashes_chmods_or_launches_reviewer(self):
        self.add_links()
        repository.export_patch(self.frozen, self.candidate, self.patch)
        run = self.root / "run"
        run.mkdir()
        (run / "candidate.patch").write_bytes(self.patch.read_bytes())
        packet = run / "quality" / "packet"
        original_write = Path.write_bytes
        original_chmod = Path.chmod
        original_digest = quality_review.digest
        projected = []

        def fail_second_projection(path, data):
            if path.parent == packet / "candidate" and path.name in {"absolute", "broken"}:
                projected.append(path.name)
                if len(projected) == 2:
                    raise OSError("synthetic projection write failure")
            return original_write(path, data)

        def no_packet_digest(path):
            self.assertFalse(Path(path).is_relative_to(packet))
            return original_digest(path)

        def no_projected_chmod(path, mode, **kwargs):
            self.assertFalse(projected, "chmod after incomplete projection")
            return original_chmod(path, mode, **kwargs)

        with (
            self.guard_host_referents(),
            mock.patch.object(Path, "write_bytes", fail_second_projection),
            mock.patch.object(Path, "chmod", no_projected_chmod),
            mock.patch.object(quality_review, "digest", side_effect=no_packet_digest),
            mock.patch.object(quality_review, "run_copilot") as transport,
        ):
            result = quality_review.review_repository(
                frozen=self.frozen, run_root=run, definition=self.definition,
                copilot=Path("/unused"), timeout_seconds=1)
        transport.assert_not_called()
        self.assertEqual(projected, ["absolute", "broken"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["error"]["message"], "synthetic projection write failure")
        self.assertTrue(all(reviewer["status"] == "not_run" for reviewer in result["reviewers"]))
        self.assertEqual(result["patch_sha256"], evaluator.digest(self.patch))
        self.assertEqual(evaluator.read_json(run / "quality" / "assessment.json"), result)
        self.assertTrue((packet / "candidate" / "relative").is_symlink())
        self.assert_sentinel_unchanged()


if __name__ == "__main__":
    unittest.main()
