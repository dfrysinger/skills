#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from validate_skill import validate


class ValidateSkillTests(unittest.TestCase):
    def make_skill(
        self,
        root: Path,
        name: str = "example-skill",
        description: str = "Create examples. Use when a user requests an example.",
    ) -> Path:
        skill_dir = root / name
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n"
            f"# {name}\n\nDo the work.\n",
            encoding="utf-8",
        )
        return skill_md

    def test_valid_skill_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(validate(self.make_skill(Path(directory))), [])

    def test_user_invoked_description_needs_no_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_md = self.make_skill(Path(directory), description="Create examples.")
            text = skill_md.read_text()
            skill_md.write_text(
                text.replace(
                    "description: Create examples.\n",
                    "description: Create examples.\ndisable-model-invocation: true\n",
                )
            )
            self.assertEqual(validate(skill_md), [])

    def test_name_must_match_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_md = self.make_skill(Path(directory))
            skill_md.write_text(skill_md.read_text().replace("name: example-skill", "name: other"))
            self.assertTrue(any("must match directory" in error for error in validate(skill_md)))

    def test_model_invoked_description_requires_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_md = self.make_skill(Path(directory), description="Create examples.")
            self.assertTrue(any("Use when" in error for error in validate(skill_md)))

    def test_missing_relative_link_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_md = self.make_skill(Path(directory))
            skill_md.write_text(skill_md.read_text() + "\n[Missing](references/missing.md)\n")
            self.assertTrue(any("does not exist" in error for error in validate(skill_md)))

    def test_sibling_skill_link_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sibling = self.make_skill(root, name="sibling-skill")
            skill_md = self.make_skill(root)
            skill_md.write_text(
                skill_md.read_text() + "\n[Sibling](../sibling-skill/SKILL.md)\n"
            )
            self.assertEqual(validate(skill_md), [])
            self.assertTrue(sibling.exists())

    def test_link_above_skill_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_md = self.make_skill(Path(directory))
            skill_md.write_text(skill_md.read_text() + "\n[Outside](../../outside.md)\n")
            self.assertTrue(any("escapes the skill root" in error for error in validate(skill_md)))

    def test_stray_root_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_md = self.make_skill(Path(directory))
            (skill_md.parent / "notes.txt").write_text("stray")
            self.assertTrue(any("unexpected root file" in error for error in validate(skill_md)))


if __name__ == "__main__":
    unittest.main()
