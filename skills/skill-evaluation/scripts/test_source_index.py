"""Deterministic source navigation; no imports of indexed code or model calls."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import source_index


class SourceIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(Path(source_index.__file__).resolve()),
             str(self.root), *map(str, args)],
            capture_output=True, text=True, timeout=10,
        )

    def test_complete_nested_names_and_spans_without_execution(self):
        (self.root / "sample.py").write_text(
            "raise RuntimeError('must not execute')\n"
            "class Outer:\n"
            "    @staticmethod\n"
            "    async def run():\n"
            "        if True:\n"
            "            def inner():\n"
            "                pass\n"
            "        return inner\n"
            "if True:\n"
            "    def final():\n"
            "        pass\n"
        )
        result = self.run_cli("sample.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (
            "sample.py:2-8 Outer\n"
            "sample.py:3-8 Outer.run\n"
            "sample.py:6-7 Outer.run.inner\n"
            "sample.py:10-11 final\n"
        ))

    def test_sorted_deduplicated_sources_and_declared_python_encoding(self):
        (self.root / "z.py").write_bytes(
            b"# coding: latin-1\n# caf\xe9\ndef last(): pass\n"
        )
        (self.root / "a.py").write_text("def first(): pass\n")
        (self.root / "empty.py").write_text("VALUE = 3\n")
        self.assertEqual(
            source_index.render_index(self.root, [
                Path("z.py"), Path("a.py"), Path("./a.py"), Path("empty.py"),
            ]),
            "a.py:1-1 first\nz.py:3-3 last\n",
        )

    def test_long_expression_preserves_complete_symbol_coverage(self):
        (self.root / "long.py").write_text(
            "def total():\n    return " + "+".join(["1"] * 1100)
            + "\ndef after(): pass\n"
        )
        result = self.run_cli("long.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "long.py:1-2 total\nlong.py:3-3 after\n")

    def test_unusual_filenames_cannot_add_index_rows(self):
        name = 'two\nrows.py'
        (self.root / name).write_text("def only(): pass\n")
        result = self.run_cli(name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '"two\\nrows.py":1-1 only\n')

    def test_invalid_or_missing_source_never_emits_partial_index(self):
        (self.root / "a.py").write_text("def valid(): pass\n")
        (self.root / "z.py").write_text("def invalid(:\n")
        for invalid in ("z.py", "missing.py"):
            with self.subTest(invalid=invalid):
                result = self.run_cli("a.py", invalid)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn(invalid, result.stderr)

    def test_parent_and_outward_symlink_paths_are_not_indexed(self):
        outside = self.root / "outside.py"
        outside.write_text("def outside(): pass\n")
        source = self.root / "source"
        source.mkdir()
        (source / "link.py").symlink_to(outside)
        for name in ("../outside.py", "link.py", str(outside)):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    source_index.render_index(source, [Path(name)])

    def test_output_file_is_complete_and_existing_file_is_unchanged(self):
        (self.root / "sample.py").write_text("def only(): pass\n")
        output = self.root / "index.txt"
        result = self.run_cli("sample.py", "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(output.read_text(), "sample.py:1-1 only\n")
        result = self.run_cli("sample.py", "--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(output.read_text(), "sample.py:1-1 only\n")


if __name__ == "__main__":
    unittest.main()
