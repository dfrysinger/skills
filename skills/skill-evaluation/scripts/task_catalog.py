"""Git-shareable evaluation metadata; private packets stay in local corpora."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import skill_eval as native


KINDS = ("tasks", "runs", "exposures", "suites")
USED = {"unknown", "development", "regression", "feedback"}
LIMITATION = "Snapshot-only exposure evidence; not globally verified fresh."


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def identity(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def slug(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def text(value):
    return isinstance(value, str) and bool(value.strip())


def label(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", value) is not None


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def maybe(check):
    return lambda value: value is None or check(value)


def sequence(check):
    return lambda value: isinstance(value, list) and all(check(item) for item in value)


def choices(*values):
    return lambda value: value in values


def fields(value, schema):
    return (isinstance(value, dict) and value.keys() == schema.keys()
            and all(check(value[key]) for key, check in schema.items()))


POPULATION = {
    **{key: maybe(sha) for key in (
        "treatment_identity", "adapter_digest", "skill_identity", "plugin_identity", "harness_identity")},
    **{key: maybe(label) for key in (
        "case_type", "arm", "treatment_id", "runner_kind", "entry_skill", "model", "effort")},
    "timeout_seconds": maybe(number),
    "max_attempts": maybe(number),
    "evaluator_models": sequence(label),
}
MEMBER = {"namespace": slug, "case_id": slug, "revision": sha}
SCHEMAS = {
    "tasks": {
        **MEMBER, "family": slug, "entry_skill": slug,
        "related_skills": sequence(slug), "title": text, "summary": text,
        "tags": sequence(slug), "behavior": slug,
        "case_type": choices("prose", "repository-task"),
    },
    "runs": {
        "namespace": slug, "case_id": slug, "revision": maybe(sha),
        "run_key": sha, "experiment_key": maybe(sha), "suite_key": maybe(sha),
        "population_identity": sha,
        "attempt": lambda value: type(value) is int and value >= 1,
        "population": lambda value: fields(value, POPULATION),
        "correctness": maybe(choices("PASS", "FAIL", "ERROR", "INVALID", "BLOCKED", "UNANSWERABLE")),
        "behavioral_verdict": maybe(choices("PASS", "FAIL", "UNANSWERABLE")),
        "suite_result": maybe(choices("PASS", "FAIL", "ERROR", "INVALID", "BLOCKED", "UNANSWERABLE")),
        "elapsed_seconds": maybe(number), "credits": maybe(number),
        "observed_credits": maybe(number),
        "credits_complete": lambda value: type(value) is bool,
        "accounting_available": lambda value: type(value) is bool,
        "clock_implementation": maybe(text),
        "suspend_inclusive": maybe(lambda value: type(value) is bool),
        "timing_status": label,
        "legacy_execution_elapsed_seconds": maybe(number),
        "started_at": maybe(text),
    },
    "exposures": {
        "family": slug, "lineages": sequence(slug),
        "exposure": choices("unknown", "unexposed", "development", "regression", "feedback"),
        "note": text,
    },
    "suites": {
        "members": sequence(lambda value: fields(value, MEMBER)),
        "lineages": sequence(slug), "role": choices("development", "regression", "holdout"),
        "exposure_snapshot": sha, "limitation": lambda value: value == LIMITATION,
    },
}


def record(kind, **values):
    return {"schema_version": 1, **values}


def validate_record(kind, value):
    schema = {"schema_version": lambda item: type(item) is int and item == 1, **SCHEMAS[kind]}
    if not fields(value, schema):
        raise ValueError(f"invalid {kind} record schema")
    if kind in {"exposures", "suites"} and (
        not value["lineages"] or len(set(value["lineages"])) != len(value["lineages"])
    ):
        raise ValueError("provide unique stable skill lineages")
    if kind == "suites":
        keys = [(item["namespace"], item["case_id"]) for item in value["members"]]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("suite needs unique cases, one revision per namespace/case")


def key(value):
    return value["namespace"], value["case_id"], value["revision"]


def bounded(root, path):
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink is not allowed: {current}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escaped selected root")
    return path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_set(data):
    tasks, families = {}, {}
    for kind in KINDS:
        for value in data[kind]:
            validate_record(kind, value)
    for task in data["tasks"]:
        task_key = key(task)
        if task_key in tasks and tasks[task_key] != task:
            raise ValueError("conflicting metadata for task revision")
        stable_key = task_key[:2]
        if stable_key in families and families[stable_key] != task["family"]:
            raise ValueError("conflicting family across task revisions")
        tasks[task_key], families[stable_key] = task, task["family"]
    for suite in data["suites"]:
        if any(key(member) not in tasks for member in suite["members"]):
            raise ValueError("suite references an unregistered revision")
    return tasks


def load(root):
    marker = bounded(root, root / "catalog.json")
    if read(marker) != {"schema_version": 1}:
        raise ValueError("unsupported catalog schema")
    data = {}
    for kind in KINDS:
        folder = bounded(root, root / kind)
        data[kind] = []
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            bounded(root, path)
            if not path.is_file() or not sha(path.stem) or path.suffix != ".json":
                raise ValueError(f"invalid catalog record filename: {path.name}")
            value = read(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != path.stem:
                raise ValueError("catalog record content hash mismatch")
            data[kind].append(value)
    validate_set(data)
    return data


def atomic_write(root, path, value, *, replace=False):
    bounded(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".catalog-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != encoded(value):
                    raise ValueError("existing immutable record differs")
    finally:
        Path(temporary).unlink(missing_ok=True)


def store(root, data, additions):
    combined = {kind: data[kind] + additions.get(kind, []) for kind in KINDS}
    validate_set(combined)
    for kind, values in additions.items():
        for value in values:
            atomic_write(root, root / kind / f"{identity(value)}.json", value)


def initialize(root):
    root.mkdir(parents=True, exist_ok=True)
    if (root / "catalog.json").exists():
        load(root)
        return
    if any((root / kind).exists() for kind in KINDS):
        raise ValueError("refusing existing non-catalog record directories")
    ignore = bounded(root, root / ".gitignore")
    previous = ignore.read_text() if ignore.exists() else ""
    if ".local/" not in previous.splitlines():
        ignore.write_text(previous.rstrip("\n") + "\n.local/\n", encoding="utf-8")
    for kind in KINDS:
        (root / kind).mkdir()
    atomic_write(root, root / "catalog.json", {"schema_version": 1})


def revision_source(corpus, case_id, revision=None):
    if not slug(case_id):
        raise ValueError("invalid case ID")
    case = bounded(corpus, corpus / "frozen" / case_id)
    if revision is None:
        pointer = read(bounded(corpus, case / "current.json"))
        if not isinstance(pointer, dict):
            raise ValueError("invalid native current pointer")
        revision = pointer.get("revision")
        if pointer.get("case_id") != case_id or pointer.get("case_manifest_sha256") != revision:
            raise ValueError("invalid native current pointer")
    if not sha(revision):
        raise ValueError("invalid case revision")
    source = bounded(corpus, case / "revisions" / revision)
    native.list_files(source)
    if native.digest(source / "case-manifest.json") != revision:
        raise ValueError("native revision manifest digest mismatch")
    return source, revision


def copy_case(corpus, output, case_id, revision):
    source, _ = revision_source(corpus, case_id, revision)
    destination = output / "frozen" / case_id
    shutil.copytree(source, destination / "revisions" / revision)
    native.write_json(destination / "current.json", {
        "schema_version": 1, "case_id": case_id,
        "revision": revision, "case_manifest_sha256": revision,
    })
    try:
        native.verify_case(output, case_id)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid native frozen case schema") from error


def project_run(namespace, row):
    from evaluation_history import fingerprint
    population = row["population"]
    total = row["accounting"].get("total", {})
    return record(
        "runs", namespace=namespace, case_id=population["case_id"],
        revision=population["case_revision"],
        run_key=identity(row["run_path"] if row["run_path"] else {
            "experiment_id": row["experiment_id"], "attempt": row["attempt"]}),
        experiment_key=identity(row["experiment_id"]) if row.get("experiment_id") else None,
        suite_key=identity(row["suite_path"]) if row.get("suite_path") else None,
        attempt=row["attempt"],
        population_identity=fingerprint(population),
        population={name: population.get(name, [] if name == "evaluator_models" else None)
                    for name in POPULATION},
        correctness=row["correctness"], behavioral_verdict=row["behavioral_verdict"],
        suite_result=row["suite_result"], elapsed_seconds=row["elapsed_seconds"],
        started_at=row["started_at"], credits=total.get("credits"),
        observed_credits=total.get("observed_credits"),
        credits_complete=total.get("complete", False),
        accounting_available=row["accounting_available"],
        clock_implementation=row.get("clock_implementation"),
        suspend_inclusive=row.get("suspend_inclusive"), timing_status=row["timing_status"],
        legacy_execution_elapsed_seconds=row["legacy_execution_elapsed_seconds"],
    )


def import_case(root, data, args):
    corpus = args.corpus.expanduser().resolve()
    source, revision = revision_source(corpus, args.case, args.revision)
    with tempfile.TemporaryDirectory(prefix="catalog-verify-") as directory:
        copy_case(corpus, Path(directory), args.case, revision)
    definition = read(source / "case.json")
    task = record(
        "tasks", namespace=args.namespace, case_id=args.case, revision=revision,
        family=args.family, entry_skill=definition["target_skill"],
        related_skills=sorted(set(args.related_skill)), title=args.title,
        summary=args.summary, tags=sorted(set(args.tag)), behavior=args.behavior,
        case_type=definition.get("case_type", "prose"),
    )
    additions = {"tasks": [task]}
    if args.include_history:
        from evaluation_history import history
        for folder in ("runs", "suite-runs"):
            path = bounded(corpus, corpus / folder)
            if path.exists():
                native.list_files(path)
        additions["runs"] = [
            project_run(args.namespace, row)
            for row in history(corpus, case_id=args.case)["attempts"]
        ]
    store(root, data, additions)
    return {"task": task, "runs_imported": len(additions.get("runs", []))}


def binding(root, namespace):
    if not slug(namespace):
        raise ValueError("invalid namespace")
    return bounded(root, root / ".local" / f"{namespace}.json")


def snapshot(data):
    return identity(sorted(identity(item) for item in data["exposures"]))


def eligible(data, family, lineages):
    for lineage in lineages:
        kinds = {item["exposure"] for item in data["exposures"]
                 if item["family"] == family and lineage in item["lineages"]}
        if kinds & USED or "unexposed" not in kinds:
            return False
    return True


def member(value):
    match = re.fullmatch(r"([^/:]+):([^/@]+)@([0-9a-f]{64})", value)
    if not match:
        raise ValueError("member must be namespace:case-id@64-hex-revision")
    result = dict(zip(MEMBER, match.groups()))
    if not fields(result, MEMBER):
        raise ValueError("invalid suite member")
    return result


def check_holdout(data, suite, tasks):
    if suite["role"] == "holdout" and any(
        not eligible(data, tasks[key(item)]["family"], suite["lineages"])
        for item in suite["members"]
    ):
        raise ValueError("holdout exposure is unknown or contaminated in current snapshot")


def plan(root, data, args):
    members = sorted((member(item) for item in args.member), key=key)
    suite = record(
        "suites", members=members, lineages=sorted(set(args.lineage)),
        role=args.role, exposure_snapshot=snapshot(data), limitation=LIMITATION,
    )
    validate_record("suites", suite)
    tasks = validate_set(data)
    if any(key(item) not in tasks for item in members):
        raise ValueError("suite references an unregistered revision")
    check_holdout(data, suite, tasks)
    if args.role != "holdout":
        exposures = [record(
            "exposures", family=family, lineages=suite["lineages"],
            exposure=args.role, note="Suite selection",
        ) for family in sorted({tasks[key(item)]["family"] for item in members})]
        store(root, data, {"exposures": exposures})
        data = load(root)
        suite["exposure_snapshot"] = snapshot(data)
    store(root, data, {"suites": [suite]})
    return {"suite": identity(suite), **suite}


def materialize(root, data, args):
    if not sha(args.suite):
        raise ValueError("invalid suite identity")
    suites = {identity(item): item for item in data["suites"]}
    if args.suite not in suites:
        raise ValueError("unknown suite")
    suite = suites[args.suite]
    tasks = validate_set(data)
    check_holdout(data, suite, tasks)
    output = args.output.expanduser().absolute()
    if output.is_symlink() or output.exists():
        raise ValueError("materialization needs a new output directory")
    resolved = output.resolve()
    if resolved.is_relative_to(root) or root.is_relative_to(resolved):
        raise ValueError("packet output cannot contain or be inside the catalog")
    sources = {}
    for item in suite["members"]:
        source = read(binding(root, item["namespace"]))
        if not fields(source, {"schema_version": lambda value: value == 1, "corpus": text}):
            raise ValueError("invalid local binding")
        corpus = Path(source["corpus"]).resolve()
        if resolved.is_relative_to(corpus) or corpus.is_relative_to(resolved):
            raise ValueError("packet output cannot overlap a source corpus")
        revision_source(corpus, item["case_id"], item["revision"])
        sources[item["namespace"]] = corpus
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".catalog-stage-", dir=output.parent))
    try:
        for namespace in sorted(sources):
            corpus = stage / namespace
            native.init_corpus(corpus)
            members = [item for item in suite["members"] if item["namespace"] == namespace]
            for item in members:
                copy_case(sources[namespace], corpus, item["case_id"], item["revision"])
            native.write_json(corpus / "corpus.json", {
                "schema_version": 1, "cases": sorted(item["case_id"] for item in members),
            })
        manifest = {
            "schema_version": 1, "suite": args.suite, "members": suite["members"],
            "exposure_snapshot": snapshot(data), "limitation": LIMITATION,
        }
        native.write_json(stage / "catalog-suite.json", manifest)
        if output.exists() or output.is_symlink():
            raise ValueError("output appeared during materialization")
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {"output": str(output), **manifest}


def configure_parser(sub):
    parser = sub.add_parser("catalog", help=__doc__)
    commands = parser.add_subparsers(dest="catalog_command", required=True)
    for name in ("init", "import", "bind", "search", "history", "expose", "plan", "materialize"):
        command = commands.add_parser(name)
        command.add_argument("catalog", type=Path)
        if name == "import":
            command.add_argument("--corpus", type=Path, required=True)
            command.add_argument("--namespace", required=True)
            command.add_argument("--case", required=True)
            command.add_argument("--revision")
            for field in ("family", "title", "summary", "behavior"):
                command.add_argument(f"--{field}", required=True)
            command.add_argument("--related-skill", action="append", default=[])
            command.add_argument("--tag", action="append", default=[])
            command.add_argument("--include-history", action="store_true")
        elif name == "bind":
            command.add_argument("--namespace", required=True)
            command.add_argument("--corpus", type=Path, required=True)
        elif name in {"search", "history"}:
            command.add_argument("--namespace")
            command.add_argument("--case")
            command.add_argument("--skill")
            command.add_argument("--text", default="")
            command.add_argument("--lineage", action="append", default=[])
        elif name == "expose":
            command.add_argument("--family", required=True)
            command.add_argument("--lineage", action="append", required=True)
            command.add_argument("--kind", choices=("unknown", "unexposed", "development", "regression", "feedback"), required=True)
            command.add_argument("--note", required=True)
        elif name == "plan":
            command.add_argument("--member", action="append", required=True)
            command.add_argument("--lineage", action="append", required=True)
            command.add_argument("--role", choices=("development", "regression", "holdout"), required=True)
        elif name == "materialize":
            command.add_argument("--suite", required=True)
            command.add_argument("--output", type=Path, required=True)


def dispatch(args):
    root = args.catalog.expanduser().resolve()
    command = args.catalog_command
    if command == "init":
        initialize(root)
        return {"schema_version": 1}
    data = load(root)
    if command == "import":
        return import_case(root, data, args)
    if command == "bind":
        corpus = args.corpus.expanduser().resolve()
        native.load_corpus(corpus)
        atomic_write(root, binding(root, args.namespace), {
            "schema_version": 1, "corpus": str(corpus),
        }, replace=True)
        return {"namespace": args.namespace, "binding": "bound-but-not-verified"}
    if command == "expose":
        if args.family not in {item["family"] for item in data["tasks"]}:
            raise ValueError("unknown task family")
        value = record(
            "exposures", family=args.family, lineages=sorted(set(args.lineage)),
            exposure=args.kind, note=args.note,
        )
        store(root, data, {"exposures": [value]})
        return value
    if command == "plan":
        return plan(root, data, args)
    if command == "materialize":
        return materialize(root, data, args)
    tasks = [item for item in data["tasks"]
             if (not args.namespace or item["namespace"] == args.namespace)
             and (not args.case or item["case_id"] == args.case)
             and (not args.skill or args.skill in [item["entry_skill"], *item["related_skills"]])
             and args.text.casefold() in " ".join(
                 [item["title"], item["summary"], item["behavior"], *item["tags"]]).casefold()]
    if command == "history":
        selected = {(item["namespace"], item["case_id"]) for item in tasks}
        return {"runs": [item for item in data["runs"]
                         if (item["namespace"], item["case_id"]) in selected],
                "interpretation": "Separate native observations; no pooled qualification."}
    return {"tasks": [
        {**item, "binding": "bound-but-not-verified" if binding(root, item["namespace"]).exists() else "unbound",
         "holdout_evidence": "recorded-unexposed-in-snapshot" if args.lineage and
         eligible(data, item["family"], args.lineage) else "unknown-or-exposed"}
        for item in tasks], "exposure_snapshot": snapshot(data), "limitation": LIMITATION}
