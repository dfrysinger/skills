#!/usr/bin/env python3
"""List every class and function span in explicitly selected Python source files."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
import tokenize


def render_index(root: Path, files: list[Path]) -> str:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source root must be a directory")
    sources = {}
    for name in files:
        path = (root / name).resolve(strict=True)
        relative = path.relative_to(root).as_posix()
        sources[relative] = path
    lines = []
    for relative, path in sorted(sources.items()):
        with tokenize.open(path) as stream:
            tree = ast.parse(stream.read(), filename=relative)
        symbols = []
        pending = [(tree, ())]
        while pending:
            node, parents = pending.pop()
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                parents = (*parents, node.name)
                start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
                symbols.append((start, node.end_lineno, ".".join(parents)))
            pending.extend((child, parents) for child in ast.iter_child_nodes(node))
        label = (
            json.dumps(relative, ensure_ascii=True)
            if any(c.isspace() or c in ':"\\' or not c.isprintable() for c in relative)
            else relative
        )
        lines.extend(
            f"{label}:{start}-{end} {name}\n"
            for start, end, name in sorted(symbols)
        )
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("files", nargs="+", type=Path, help="source paths within source_root")
    parser.add_argument("--output", type=Path, help="write a new file instead of stdout")
    args = parser.parse_args()
    try:
        text = render_index(args.source_root, args.files)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        else:
            sys.stdout.write(text)
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
