"""Read-only, bounded GitHub Actions metadata snapshots for exact run bindings."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


BINDINGS = ("id", "workflow_id", "head_sha", "head_branch", "run_attempt", "event")
FIELDS = (*BINDINGS, "path", "status", "conclusion", "repository")
STATUSES = {"queued", "in_progress", "completed", "waiting", "requested", "pending"}
ROW_PROJECTION = (
    "{id,workflow_id,path,event,head_sha,head_branch,run_attempt,status,conclusion,"
    "repository:{id:.repository.id,full_name:.repository.full_name,private:.repository.private}}"
)
LIST_PROJECTION = "{total_count,workflow_runs:[.workflow_runs[]|" + ROW_PROJECTION + "]}"
JOB_FIELDS = (
    "id", "name", "status", "conclusion", "run_id", "run_attempt", "head_sha",
    "started_at", "completed_at",
)
JOB_PROJECTION = (
    "{id,name,status,conclusion,run_id,run_attempt,head_sha,started_at,completed_at}"
)
JOBS_LIST_PROJECTION = "{total_count,jobs:[.jobs[]|" + JOB_PROJECTION + "]}"


class ObservationError(ValueError):
    """The requested snapshot cannot be established."""


def integer(value: object, name: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ObservationError(f"{name} must be an integer >= {minimum}")
    return value


def text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ObservationError(f"{name} must be nonempty text without control characters")
    return value


def repository_record(value: object, repository: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"id", "full_name", "private"}:
        raise ObservationError("repository requires id, full_name and private")
    integer(value["id"], "repository.id")
    if value["full_name"] != repository or type(value["private"]) is not bool:
        raise ObservationError("repository identity or private flag is invalid")
    return value


def binding(row: object, repository: str) -> dict:
    if not isinstance(row, dict):
        raise ObservationError("run must be an object")
    for field in BINDINGS:
        if field not in row:
            raise ObservationError(f"run is missing {field}")
    for field in ("id", "workflow_id", "run_attempt"):
        integer(row[field], field)
    if not isinstance(row["head_sha"], str) or not re.fullmatch(r"[0-9a-fA-F]{40}", row["head_sha"]):
        raise ObservationError("head_sha must be 40 hexadecimal characters")
    for field in ("head_branch", "event"):
        text(row[field], field)
    repository_record(row.get("repository"), repository)
    return row


def workflow_path(value: object, name: str = "path") -> str:
    path = text(value, name)
    if (path.startswith("/") or "\\" in path or ":" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        raise ObservationError("workflow path must be a safe relative path")
    return path


def job_name(value: object) -> str:
    name = text(value, "job name")
    if name != name.strip() or len(name) > 256:
        raise ObservationError("job name must be trimmed and at most 256 characters")
    return name


def job_record(row: object, expected: dict) -> dict:
    if not isinstance(row, dict) or set(row) != set(JOB_FIELDS):
        raise ObservationError("job metadata has missing or unexpected fields")
    integer(row["id"], "job id")
    job_name(row["name"])
    for field in ("run_id", "run_attempt"):
        integer(row[field], f"job {field}")
    if row["run_id"] != expected["id"] or row["run_attempt"] != expected["run_attempt"]:
        raise ObservationError("job belongs to a different run or run attempt")
    if row["head_sha"] != expected["head_sha"]:
        raise ObservationError("job head SHA does not match requested run")
    if row["status"] not in STATUSES:
        raise ObservationError("unknown job status")
    if row["status"] == "completed":
        text(row["conclusion"], "completed job conclusion")
    elif row["conclusion"] is not None:
        raise ObservationError("nonterminal job must have a null conclusion")
    for field in ("started_at", "completed_at"):
        if row[field] is not None:
            text(row[field], f"job {field}")
    return row


def run_record(row: object, repository: str) -> dict:
    binding(row, repository)
    if set(row) != set(FIELDS):
        raise ObservationError("run metadata has missing or unexpected fields")
    workflow_path(row["path"])
    if not isinstance(row["status"], str) or row["status"] not in STATUSES:
        raise ObservationError("unknown run status")
    if row["status"] == "completed":
        text(row["conclusion"], "completed conclusion")
    elif row["conclusion"] is not None:
        raise ObservationError("nonterminal run must have a null conclusion")
    return row


def read_json(raw: str | bytes) -> object:
    def reject_constant(value):
        raise ObservationError("nonfinite JSON number")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ObservationError("duplicate JSON object key")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except (ValueError, UnicodeError) as error:
        raise ObservationError("invalid JSON") from error


def validate_options(args: argparse.Namespace) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", args.repository):
        raise ObservationError("repository must be OWNER/REPO, not a URL or path")
    if (len(args.host) > 253 or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in args.host.split("."))):
        raise ObservationError("host must be a DNS hostname without scheme, port or path")
    for field, maximum in (("max_pages", 1000), ("max_calls", 10000), ("timeout", 300)):
        integer(getattr(args, field), field)
        if getattr(args, field) > maximum:
            raise ObservationError(f"{field} exceeds {maximum}")
    if args.output.exists() or args.output.is_symlink():
        raise ObservationError("output already exists")
    if not args.output.parent.is_dir():
        raise ObservationError("output parent directory does not exist")
    try:
        rows = read_json(args.runs.read_bytes())
    except OSError as error:
        raise ObservationError("cannot read runs input") from error
    if not isinstance(rows, list) or not rows:
        raise ObservationError("runs must be a nonempty JSON array")
    seen = set()
    input_fields = set(BINDINGS) | {"repository"}
    direct = args.direct_known_runs or args.direct_known_jobs
    if direct:
        input_fields.add("workflow_path")
    if args.direct_known_jobs:
        input_fields.add("expected_jobs")
    for row in rows:
        binding(row, args.repository)
        if set(row) != input_fields:
            raise ObservationError("input run has unexpected fields")
        if direct:
            workflow_path(row["workflow_path"], "workflow_path")
        if args.direct_known_jobs:
            if row["run_attempt"] != 1:
                raise ObservationError("exact job observation requires first run attempt")
            names = row["expected_jobs"]
            if not isinstance(names, list) or not names:
                raise ObservationError("expected_jobs must be a nonempty array")
            validated = [job_name(name) for name in names]
            if len(set(validated)) != len(validated):
                raise ObservationError("expected_jobs contains duplicate names")
        if row["id"] in seen:
            raise ObservationError("duplicate requested run id")
        seen.add(row["id"])
        if row["repository"] != rows[0]["repository"]:
            raise ObservationError("inconsistent requested repository records")
    calls_per_run = 2 if args.direct_known_jobs else 1
    if direct and len(rows) * calls_per_run > args.max_calls:
        raise ObservationError("requested runs exceed call budget; observation is UNKNOWN")
    return rows


class Reader:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.calls: list[dict] = []

    def get(self, endpoint: str, projection: str, source: str) -> object:
        if len(self.calls) >= self.args.max_calls:
            raise ObservationError("call budget exhausted; observation is UNKNOWN")
        started = time.monotonic()
        try:
            response = subprocess.run(
                ["gh", "api", "--hostname", self.args.host, "--method", "GET",
                 endpoint, "--jq", projection],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.args.timeout, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ObservationError("gh GET timed out; observation is UNKNOWN") from error
        except OSError as error:
            raise ObservationError("gh GET unavailable; observation is UNKNOWN") from error
        if response.returncode:
            # Do not relay gh output, which may contain authentication details.
            raise ObservationError("gh GET failed; observation is UNKNOWN")
        self.calls.append({
            "source": source, "endpoint": endpoint,
            "projected_response_bytes": len(response.stdout),
            "client_wall_seconds": time.monotonic() - started,
        })
        return read_json(response.stdout)


def observe(args: argparse.Namespace, requested: list[dict]) -> dict:
    started = time.monotonic()
    reader = Reader(args)
    wanted = {row["id"]: row for row in requested}
    observed = {}
    seen = set()
    total = None
    expected_repository = requested[0]["repository"]

    def verify(row: dict) -> None:
        if row["repository"] != expected_repository:
            raise ObservationError("repository record does not match requested binding")
        expected = wanted.get(row["id"])
        if expected is not None and any(row[key] != expected[key] for key in BINDINGS):
            raise ObservationError("requested run binding mismatch; reruns cannot replace originals")
        if (direct and expected is not None
                and row["path"] != expected["workflow_path"]):
            raise ObservationError("requested workflow path mismatch; observation is UNKNOWN")

    direct = args.direct_known_runs or args.direct_known_jobs
    if not direct:
        for page in range(1, args.max_pages + 1):
            endpoint = f"repos/{args.repository}/actions/runs?per_page=100&page={page}"
            response = reader.get(endpoint, LIST_PROJECTION, "list")
            if not isinstance(response, dict) or set(response) != {"total_count", "workflow_runs"}:
                raise ObservationError("list response requires total_count and workflow_runs")
            count = integer(response["total_count"], "total_count", 0)
            if total is None:
                total = count
                if total > args.max_pages * 100:
                    raise ObservationError("listing incomplete within max-pages; observation is UNKNOWN")
            elif count != total:
                raise ObservationError("listing total_count drift; observation is UNKNOWN")
            rows = response["workflow_runs"]
            if not isinstance(rows, list) or len(rows) != min(100, total - len(seen)):
                raise ObservationError("list page length does not match declared membership")
            for row in rows:
                run_record(row, args.repository)
                if row["id"] in seen:
                    raise ObservationError("duplicate listed run id")
                seen.add(row["id"])
                verify(row)
                if row["id"] in wanted:
                    observed[row["id"]] = {
                        "run": row, "provenance": {"source": "list", "page": page, "call": len(reader.calls)}
                    }
            if len(seen) == total:
                break
        else:
            raise ObservationError("listing incomplete; observation is UNKNOWN")

    for expected in requested:
        if expected["id"] in observed:
            continue
        endpoint = f"repos/{args.repository}/actions/runs/{expected['id']}"
        row = reader.get(endpoint, ROW_PROJECTION, "direct")
        run_record(row, args.repository)
        if row["id"] != expected["id"]:
            raise ObservationError("direct response has a different run id")
        verify(row)
        observed[row["id"]] = {
            "run": row, "provenance": {"source": "direct", "call": len(reader.calls)}
        }
        if args.direct_known_jobs:
            expected_names = set(expected["expected_jobs"])
            jobs = []
            seen_ids = set()
            seen_names = set()
            total_jobs = None
            first_job_call = len(reader.calls) + 1
            for page in range(1, args.max_pages + 1):
                endpoint = (
                    f"repos/{args.repository}/actions/runs/{expected['id']}"
                    f"/jobs?per_page=100&page={page}"
                )
                response = reader.get(endpoint, JOBS_LIST_PROJECTION, "jobs")
                if not isinstance(response, dict) or set(response) != {"total_count", "jobs"}:
                    raise ObservationError("jobs response requires total_count and jobs")
                count = integer(response["total_count"], "job total_count", 0)
                if total_jobs is None:
                    total_jobs = count
                    if total_jobs > args.max_pages * 100:
                        raise ObservationError(
                            "jobs listing incomplete within max-pages; observation is UNKNOWN"
                        )
                elif count != total_jobs:
                    raise ObservationError("jobs total_count drift; observation is UNKNOWN")
                rows = response["jobs"]
                if not isinstance(rows, list) or len(rows) != min(
                    100, total_jobs - len(seen_ids)
                ):
                    raise ObservationError(
                        "jobs page length does not match declared membership"
                    )
                for job in rows:
                    job_record(job, expected)
                    if job["id"] in seen_ids or job["name"] in seen_names:
                        raise ObservationError("duplicate job id or name")
                    seen_ids.add(job["id"])
                    seen_names.add(job["name"])
                    jobs.append(job)
                if len(seen_ids) == total_jobs:
                    break
            else:
                raise ObservationError("jobs listing incomplete; observation is UNKNOWN")
            if seen_names != expected_names:
                raise ObservationError("observed job-name set differs from dispatch binding")
            observed[row["id"]]["jobs"] = jobs
            observed[row["id"]]["jobs_provenance"] = {
                "source": "jobs",
                "calls": list(range(first_job_call, len(reader.calls) + 1)),
            }
    result = {
        "schema_version": 3 if args.direct_known_jobs else 2 if direct else 1,
        "repository": args.repository, "host": args.host,
        "non_atomic": True,
        "observations": [observed[row["id"]] for row in requested],
        "calls": reader.calls, "call_count": len(reader.calls),
        "projected_response_bytes": sum(call["projected_response_bytes"] for call in reader.calls),
        "client_wall_seconds": time.monotonic() - started,
    }
    if direct:
        result["coverage"] = {
            "scope": (
                "requested-runs-and-exact-jobs-only"
                if args.direct_known_jobs
                else "requested-runs-only"
            ),
            "repository_enumerated": False,
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--host", default="github.com")
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-calls", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=30, help="seconds per gh GET (1-300)")
    parser.add_argument("--direct-known-runs", action="store_true",
                        help="read only exact known IDs; requires workflow_path on each input")
    parser.add_argument("--direct-known-jobs", action="store_true",
                        help="read exact known IDs and exact expected job-name sets")
    args = parser.parse_args(argv)
    try:
        if args.direct_known_runs and args.direct_known_jobs:
            raise ObservationError("choose one direct observation mode")
        requested = validate_options(args)
        result = observe(args, requested)
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    except (ObservationError, OSError) as error:
        message = str(error) if isinstance(error, ObservationError) else "cannot create exclusive output"
        print(f"observation refused: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
