#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fully decode a walkthrough movie and emit its media receipt."
    )
    parser.add_argument("movie", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    movie = args.movie.expanduser().resolve()
    if not movie.is_file() or movie.stat().st_size == 0:
        raise SystemExit(f"movie is missing or empty: {movie}")

    for command in ("ffprobe", "ffmpeg"):
        if shutil.which(command) is None:
            raise SystemExit(f"{command} is required")

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(movie),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    streams = metadata.get("streams", [])
    if len(streams) != 1:
        raise SystemExit("movie must contain one readable primary video stream")

    stream = streams[0]
    media_format = metadata.get("format", {})
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    duration = float(media_format.get("duration", 0))
    size = movie.stat().st_size
    codec = stream.get("codec_name")
    if width <= 0 or height <= 0 or duration <= 0 or size <= 0 or not codec:
        raise SystemExit("movie has invalid codec, dimensions, duration, or size")

    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(movie),
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
        ],
        check=True,
    )

    receipt = {
        "schemaVersion": 1,
        "path": str(movie),
        "sha256": file_sha256(movie),
        "codec": codec,
        "width": width,
        "height": height,
        "durationSeconds": duration,
        "sizeBytes": size,
        "fullDecode": "PASS",
    }
    serialized = json.dumps(receipt, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
