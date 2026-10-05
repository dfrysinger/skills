#!/usr/bin/env python3
"""Create deterministic full and candidate-safe archives for a distributed evaluation."""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def inventory(root: Path) -> list[dict]:
    return [
        {
            "bytes": path.stat().st_size,
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "package-inventory.json"
    ]


def tree_sha256(root: Path) -> str:
    records = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append(
                {
                    "kind": "symlink",
                    "mode": path.lstat().st_mode & 0o777,
                    "path": relative,
                    "sha256": hashlib.sha256(os.readlink(path).encode()).hexdigest(),
                }
            )
        elif path.is_file():
            records.append(
                {
                    "kind": "file",
                    "mode": path.lstat().st_mode & 0o777,
                    "path": relative,
                    "sha256": sha256(path),
                }
            )
    payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def add_tar_member(stream: tarfile.TarFile, root: Path, path: Path) -> None:
    relative = path.relative_to(root).as_posix()
    info = tarfile.TarInfo(relative + ("/" if path.is_dir() else ""))
    info.mode = stat.S_IMODE(path.lstat().st_mode)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    if path.is_symlink():
        info.type = tarfile.SYMTYPE
        info.linkname = os.readlink(path)
        stream.addfile(info)
    elif path.is_dir():
        info.type = tarfile.DIRTYPE
        stream.addfile(info)
    elif path.is_file():
        info.size = path.stat().st_size
        with path.open("rb") as source:
            stream.addfile(info, source)


def write_archive(root: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
            ) as stream:
                for path in sorted(root.rglob("*")):
                    add_tar_member(stream, root, path)


def remove_matches(root: Path, patterns: list[str]) -> list[str]:
    removed = []
    for path in sorted(root.rglob("*"), reverse=True):
        relative = path.relative_to(root).as_posix()
        if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            continue
        removed.append(relative)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    return sorted(removed)


def package_campaign(
    source: Path,
    full_root: Path,
    candidate_root: Path,
    full_archive: Path,
    candidate_archive: Path,
    receipt_path: Path,
    completion_path: Path,
    hidden_patterns: list[str],
) -> dict:
    source = source.resolve()
    outputs = (
        full_root,
        candidate_root,
        full_archive,
        candidate_archive,
        receipt_path,
        completion_path,
    )
    if not (source / "package-manifest.json").is_file():
        raise ValueError("source package must contain package-manifest.json")
    if any(path.exists() for path in outputs):
        raise ValueError("refusing to replace an existing output")
    if not hidden_patterns:
        raise ValueError("at least one hidden-path pattern is required")

    shutil.copytree(source, full_root, symlinks=True)
    for cache in full_root.rglob("__pycache__"):
        shutil.rmtree(cache)
    write_json(full_root / "package-inventory.json", inventory(full_root))
    write_archive(full_root, full_archive)

    shutil.copytree(full_root, candidate_root, symlinks=True)
    removed = remove_matches(candidate_root, hidden_patterns)
    if not removed:
        raise ValueError("hidden-path patterns removed no files or directories")
    write_json(candidate_root / "package-inventory.json", inventory(candidate_root))
    write_archive(candidate_root, candidate_archive)

    manifest_sha = sha256(full_root / "package-manifest.json")
    if sha256(candidate_root / "package-manifest.json") != manifest_sha:
        raise ValueError("candidate and full package manifests differ")
    receipt = {
        "schemaVersion": 1,
        "source": str(source),
        "hiddenPatterns": hidden_patterns,
        "removedPaths": removed,
        "packageManifestSha256": manifest_sha,
        "full": {
            "archive": str(full_archive),
            "archiveSha256": sha256(full_archive),
            "inventorySha256": sha256(full_root / "package-inventory.json"),
            "treeSha256": tree_sha256(full_root),
        },
        "candidate": {
            "archive": str(candidate_archive),
            "archiveSha256": sha256(candidate_archive),
            "inventorySha256": sha256(candidate_root / "package-inventory.json"),
            "treeSha256": tree_sha256(candidate_root),
        },
    }
    write_json(receipt_path, receipt)
    write_json(
        completion_path,
        {
            "schemaVersion": 1,
            "campaignId": json.loads(
                (full_root / "package-manifest.json").read_text()
            )["campaignId"],
            "packageArchiveSha256": receipt["full"]["archiveSha256"],
            "candidatePackageArchiveSha256": receipt["candidate"]["archiveSha256"],
            "packageManifestSha256": manifest_sha,
            "completedAttempts": [],
            "excludedAttempts": [],
        },
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--full-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--full-archive", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--completion", type=Path, required=True)
    parser.add_argument(
        "--hidden-pattern",
        action="append",
        default=[],
        help="Package-relative glob removed from the candidate archive; repeatable.",
    )
    args = parser.parse_args()
    receipt = package_campaign(
        args.source,
        args.full_root,
        args.candidate_root,
        args.full_archive,
        args.candidate_archive,
        args.receipt,
        args.completion,
        args.hidden_pattern,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
