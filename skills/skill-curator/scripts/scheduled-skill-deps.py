#!/usr/bin/env python3
"""Enumerate durable skill dependencies reachable from installed LaunchAgents."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

BUILTIN_SLASH_COMMANDS = {
    "allow-all",
    "autopilot",
    "clear",
    "compact",
    "context",
    "every",
    "exit",
    "help",
    "login",
    "logout",
    "model",
    "new",
    "permissions",
    "plugin",
    "plugins",
    "restart",
    "skills",
    "status",
}
NAME_RE = r"[a-z0-9][a-z0-9._-]*"
SLASH_RE = re.compile(
    rf"(?<![\w:/])/(?:(dfrysinger-skills):)?({NAME_RE})(?=[\s`'\",.)\]]|$)"
)
BACKTICK_RE = re.compile(rf"`({NAME_RE})`")
RELATIVE_FILE_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:references|scripts)/[A-Za-z0-9._/-]+)"
)
ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_:/])(/[A-Za-z0-9._~@%+=,/-]+)"
)


class DependencyError(ValueError):
    pass


def roots() -> tuple[Path, Path]:
    public = Path(os.environ.get("SKILLS_REPO_ROOT", Path.home() / "code/skills")).resolve()
    local = Path(os.environ.get("SKILLS_LOCAL_ROOT", Path.home() / ".copilot/skills")).resolve()
    return public / "skills", local


def live_skills(public: Path, local: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for root in (public, local):
        if not root.is_dir():
            continue
        for skill_md in root.glob("*/SKILL.md"):
            name = skill_md.parent.name
            if name in result:
                raise DependencyError(f"ambiguous live skill name: {name}")
            result[name] = skill_md.parent.resolve()
    return result


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def skill_for_path(path: Path, skills: dict[str, Path]) -> str | None:
    resolved = path.resolve()
    for name, directory in skills.items():
        if within(resolved, directory):
            return name
    return None


def add_dependency(
    dependencies: dict[str, set[str]],
    name: str,
    source: str,
    skills: dict[str, Path],
    strict: bool = True,
) -> None:
    if name not in skills:
        if strict:
            raise DependencyError(f"{source}: referenced skill does not exist: {name}")
        return
    dependencies.setdefault(name, set()).add(source)


def path_patterns(public: Path, local: Path) -> list[tuple[re.Pattern[str], Path]]:
    patterns: list[tuple[re.Pattern[str], Path]] = []
    for prefix, root in (
        (r"\$(?:REPO|SKILLS_REPO_ROOT)/skills/", public),
        (r"(?:~|\$HOME)/code/skills/skills/", public),
        (r"(?:~|\$HOME)/\.copilot/skills/", local),
    ):
        patterns.append(
            (
                re.compile(
                    prefix
                    + rf"(?P<name>{NAME_RE})(?:/(?P<rest>[A-Za-z0-9._/-]+))?"
                ),
                root,
            )
        )
    return patterns


def add_path_reference(
    raw: str,
    source: str,
    skills: dict[str, Path],
    dependencies: dict[str, set[str]],
    queue: deque[Path],
    public: Path,
    local: Path,
) -> bool:
    target = Path(os.path.expanduser(raw.rstrip(".,;:)"))).resolve(strict=False)
    root = next((item for item in (public, local) if within(target, item)), None)
    if root is None:
        return False
    relative = target.relative_to(root)
    if not relative.parts:
        return True
    name = relative.parts[0]
    add_dependency(dependencies, name, source, skills)
    if len(relative.parts) == 1:
        return True
    if not within(target, skills[name]):
        raise DependencyError(f"{source}: referenced path escapes {name}: {raw}")
    if not target.exists():
        raise DependencyError(f"{source}: referenced path is missing: {target}")
    if not target.is_file():
        raise DependencyError(f"{source}: referenced path is not a file: {target}")
    queue.append(target)
    return True


def scan_file(
    path: Path,
    skills: dict[str, Path],
    dependencies: dict[str, set[str]],
    queue: deque[Path],
    public: Path,
    local: Path,
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DependencyError(f"cannot read durable dependency file {path}: {exc}") from exc
    source = str(path)
    current_skill = skill_for_path(path, skills)
    if current_skill:
        add_dependency(dependencies, current_skill, source, skills)

    for match in ABSOLUTE_PATH_RE.finditer(text):
        add_path_reference(
            match.group(1),
            source,
            skills,
            dependencies,
            queue,
            public,
            local,
        )

    for pattern, root in path_patterns(public, local):
        for match in pattern.finditer(text):
            name = match.group("name")
            add_dependency(dependencies, name, source, skills)
            rest = match.group("rest")
            if rest:
                rest = rest.rstrip(".,;:)")
                target = (root / name / rest).resolve()
                if not within(target, skills[name]):
                    raise DependencyError(f"{source}: referenced path escapes {name}: {rest}")
                if not target.exists():
                    raise DependencyError(f"{source}: referenced path is missing: {target}")
                if target.is_file():
                    queue.append(target)

    if current_skill:
        skill_root = skills[current_skill]
        for match in RELATIVE_FILE_RE.finditer(text):
            relative = match.group(1).rstrip(".,;:)")
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start : line_end if line_end >= 0 else len(text)]
            foreign_context = any(
                candidate.group("name") != current_skill
                for pattern, _ in path_patterns(public, local)
                for candidate in pattern.finditer(line)
            )
            if foreign_context:
                continue
            target = (skill_root / relative).resolve()
            if not within(target, skill_root):
                raise DependencyError(f"{source}: relative reference escapes skill root")
            if not target.exists() and path.name != "SKILL.md":
                raise DependencyError(f"{source}: relative reference is missing: {target}")
            if target.is_file():
                queue.append(target)

    for match in SLASH_RE.finditer(text):
        explicit_plugin = bool(match.group(1))
        name = match.group(2)
        if name in BUILTIN_SLASH_COMMANDS:
            continue
        add_dependency(dependencies, name, source, skills, strict=explicit_plugin)
    for match in BACKTICK_RE.finditer(text):
        add_dependency(dependencies, match.group(1), source, skills, strict=False)


def enumerate_dependencies(launch_agents: Path) -> dict[str, Any]:
    public, local = roots()
    skills = live_skills(public, local)
    dependencies: dict[str, set[str]] = {}
    queue: deque[Path] = deque()
    if not launch_agents.is_dir():
        raise DependencyError(f"LaunchAgents directory does not exist: {launch_agents}")
    prefix = os.environ.get(
        "SKILLS_LAUNCHD_PREFIX",
        f"com.{os.environ.get('USER') or Path.home().name}.skills",
    )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", prefix):
        raise DependencyError(f"invalid launchd prefix: {prefix}")
    plists = sorted(launch_agents.glob(f"{prefix}*.plist"))
    allow_empty = os.environ.get("SKILLS_ALLOW_NO_SCHEDULED_JOBS") == "1"
    if not plists and not allow_empty:
        raise DependencyError(f"no managed LaunchAgents found for prefix {prefix}")
    managed_programs = 0
    for plist_path in plists:
        try:
            data = plistlib.loads(plist_path.read_bytes())
        except Exception as exc:
            raise DependencyError(f"cannot parse {plist_path}: {exc}") from exc
        arguments = data.get("ProgramArguments")
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise DependencyError(f"{plist_path}: ProgramArguments must be a string array")
        for raw in arguments:
            candidate = Path(os.path.expanduser(raw))
            if not candidate.is_absolute():
                continue
            if add_path_reference(
                raw,
                str(plist_path),
                skills,
                dependencies,
                queue,
                public,
                local,
            ):
                managed_programs += 1
    if plists and managed_programs == 0 and not allow_empty:
        raise DependencyError("managed LaunchAgents contain no managed program paths")

    visited: set[Path] = set()
    while queue:
        path = queue.popleft().resolve()
        if path in visited:
            continue
        visited.add(path)
        scan_file(path, skills, dependencies, queue, public, local)

    return {
        "schema_version": 1,
        "complete": True,
        "launch_agents_dir": str(launch_agents.resolve()),
        "launch_agents": [str(path.resolve()) for path in plists],
        "dependencies": [
            {
                "skill": name,
                "path": str(skills[name]),
                "sources": sorted(sources),
            }
            for name, sources in sorted(dependencies.items())
        ],
        "scanned_files": [str(path) for path in sorted(visited)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--launch-agents-dir",
        default=os.environ.get(
            "SKILLS_LAUNCH_AGENTS_DIR",
            str(Path.home() / "Library/LaunchAgents"),
        ),
    )
    parser.add_argument("--check")
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args()
    try:
        result = enumerate_dependencies(Path(args.launch_agents_dir))
        names = {item["skill"] for item in result["dependencies"]}
        if args.check and args.check in names:
            sources = next(
                item["sources"]
                for item in result["dependencies"]
                if item["skill"] == args.check
            )
            raise DependencyError(
                f"{args.check} is an implicit pin from durable config: {', '.join(sources)}"
            )
        if args.inventory:
            public, local = roots()
            skills = live_skills(public, local)
            dependency_sources = {
                item["skill"]: item["sources"] for item in result["dependencies"]
            }
            result["skills"] = [
                {
                    "name": name,
                    "root": "public" if within(path, public) else "local",
                    "path": str(path),
                    "pinned": (path / ".pinned").is_file(),
                    "implicit_pin": name in dependency_sources,
                    "implicit_pin_sources": dependency_sources.get(name, []),
                }
                for name, path in sorted(skills.items())
            ]
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except DependencyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
