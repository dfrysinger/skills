#!/usr/bin/env python3
"""Validate the portable file contract for one agent skill."""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ALLOWED_DIRECTORIES = {"assets", "references", "scripts", "templates"}
ALLOWED_ROOT_FILES = {
    "SKILL.md",
    "LICENSE",
    "NOTICE",
    "NOTICE.md",
    "README.md",
}


def frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return None
    values: dict[str, str] = {}
    for line in lines[1:closing]:
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("\"'")
    return values, "\n".join(lines[closing + 1 :])


def validate(skill_md: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_md.expanduser().resolve()
    if not skill_md.is_file():
        return [f"SKILL.md not found: {skill_md}"]

    skill_dir = skill_md.parent
    name = skill_dir.name
    text = skill_md.read_text(encoding="utf-8")
    encoded_size = len(text.encode())

    if not NAME_RE.fullmatch(name) or len(name) > 64:
        errors.append(f"directory name must match {NAME_RE.pattern} and be at most 64 characters")
    if encoded_size > 100_000:
        errors.append(f"SKILL.md is {encoded_size} bytes; maximum is 100000")

    parsed = frontmatter(text)
    if parsed is None:
        errors.append("SKILL.md must start with closed YAML frontmatter")
    else:
        values, body = parsed
        declared_name = values.get("name", "")
        description = values.get("description", "")
        if declared_name != name:
            errors.append(f"frontmatter name {declared_name!r} must match directory {name!r}")
        if not description:
            errors.append("frontmatter description is required")
        elif len(description) > 1024:
            errors.append("frontmatter description exceeds 1024 characters")
        elif (
            values.get("disable-model-invocation", "").lower() != "true"
            and "use when" not in description.lower()
        ):
            errors.append("model-invoked description must include 'Use when'")

        first_body_line = next((line for line in body.splitlines() if line.strip()), "")
        if first_body_line != f"# {name}":
            errors.append(f"first body heading must be '# {name}'")

    for path in skill_dir.rglob("*"):
        if path.is_symlink():
            errors.append(f"symlink is not portable: {path.relative_to(skill_dir)}")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir)
        if len(path.read_bytes()) > 1_048_576:
            errors.append(f"{relative} exceeds 1 MiB")
        if len(relative.parts) == 1:
            if relative.name not in ALLOWED_ROOT_FILES:
                errors.append(f"unexpected root file: {relative}")
        elif relative.parts[0] not in ALLOWED_DIRECTORIES:
            errors.append(f"support file must live under {sorted(ALLOWED_DIRECTORIES)}: {relative}")

    skills_root = skill_dir.parent
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        relative_target = target.split("#", 1)[0]
        if not relative_target:
            continue
        resolved = (skill_dir / relative_target).resolve()
        try:
            resolved.relative_to(skills_root)
        except ValueError:
            errors.append(f"relative link escapes the skill root: {target}")
            continue
        if not resolved.exists():
            errors.append(f"relative link target does not exist: {target}")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} /path/to/SKILL.md", file=sys.stderr)
        return 2
    skill_md = Path(sys.argv[1])
    errors = validate(skill_md)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {skill_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
