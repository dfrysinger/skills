import hashlib
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("distributed_campaign.py")
SPEC = importlib.util.spec_from_file_location("distributed_campaign", SCRIPT)
matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matrix)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FullProductMatrixTests(unittest.TestCase):
    def test_candidate_patch_path_is_resolved_before_workspace_chdir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
            (workspace / "value.txt").write_text("before\n")
            patch = root / "candidate.patch"
            patch.write_text(
                "diff --git a/value.txt b/value.txt\n"
                "index 9d55d72..0881f92 100644\n"
                "--- a/value.txt\n"
                "+++ b/value.txt\n"
                "@@ -1 +1 @@\n"
                "-before\n"
                "+after\n"
            )
            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                self.assertTrue(
                    matrix.apply_candidate_patch(
                        Path("workspace"), Path("candidate.patch")
                    )
                )
            finally:
                os.chdir(old_cwd)
            self.assertEqual((workspace / "value.txt").read_text(), "after\n")

    def test_candidate_auth_ignores_enterprise_gh_host_only_in_copilot_child(self):
        class Runner:
            def run_command(self, command, **kwargs):
                return {
                    "command": command,
                    "ghHost": kwargs["environment"].get("GH_HOST"),
                }

            def run_candidate(self, **_kwargs):
                return {
                    "processGhHost": os.environ.get("GH_HOST"),
                    "copilot": self.run_command(
                        ["copilot"], environment=os.environ.copy()
                    ),
                    "git": self.run_command(["git"], environment=os.environ.copy()),
                }

        runner = Runner()
        original_run_command = runner.run_command
        with mock.patch.dict("os.environ", {"GH_HOST": "github.example.com"}, clear=True):
            self.assertEqual(
                matrix.run_candidate_with_public_github(runner),
                {
                    "processGhHost": "github.example.com",
                    "copilot": {"command": ["copilot"], "ghHost": None},
                    "git": {"command": ["git"], "ghHost": "github.example.com"},
                },
            )
            self.assertEqual(os.environ["GH_HOST"], "github.example.com")
        self.assertEqual(runner.run_command, original_run_command)

    def test_candidate_auth_restores_runner_command_after_failure(self):
        class Runner:
            def run_command(self, command, **kwargs):
                return {"command": command, **kwargs}

            def run_candidate(self, **_kwargs):
                raise RuntimeError("candidate failed")

        runner = Runner()
        original_run_command = runner.run_command
        with self.assertRaisesRegex(RuntimeError, "candidate failed"):
            matrix.run_candidate_with_public_github(runner)
        self.assertEqual(runner.run_command, original_run_command)

    def test_candidate_boundary_is_retired_before_copilot_starts(self):
        events = []

        class Runner:
            def run_command(self, command, **kwargs):
                events.append(("command", command[0]))
                return {"command": command, **kwargs}

            def run_candidate(self, **_kwargs):
                return self.run_command(
                    ["copilot"], environment=os.environ.copy()
                )

        matrix.run_candidate_with_public_github(
            Runner(),
            before_copilot=lambda: events.append(("boundary", "retired")),
        )
        self.assertEqual(
            events,
            [("boundary", "retired"), ("command", "copilot")],
        )

    def test_only_split_macos_candidate_stage_retires_package(self):
        hosted = inspect.getsource(matrix.run_hosted)
        macos_candidate = inspect.getsource(matrix.run_macos_candidate_stage)
        macos_product = inspect.getsource(matrix.run_macos_product_stage)
        self.assertNotIn("before_copilot", hosted)
        self.assertIn("before_copilot", macos_candidate)
        self.assertIn("candidate_package_archive_sha256", macos_candidate)
        self.assertIn("prepare_case_python_dependencies", macos_candidate)
        self.assertIn("runtimeDependencies", macos_candidate)
        self.assertIn("pythonpath_environment(python_paths)", macos_product)
        self.assertIn("with dependency_environment(", macos_product)
        self.assertIn("trusted-candidate", macos_product)
        self.assertIn("cargo_fetch_workspace", macos_product)

    def test_pythonpath_environment_restores_prior_value(self):
        with tempfile.TemporaryDirectory() as directory:
            dependency = Path(directory) / "python"
            dependency.mkdir()
            with mock.patch.dict("os.environ", {"PYTHONPATH": "existing"}, clear=True):
                with matrix.pythonpath_environment([dependency]):
                    self.assertEqual(
                        os.environ["PYTHONPATH"],
                        f"{dependency}{os.pathsep}existing",
                    )
                self.assertEqual(os.environ["PYTHONPATH"], "existing")

    def test_empty_dependencies_do_not_read_hidden_scaffold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                matrix.prepare_case_python_dependencies(
                    {},
                    root / "run",
                    {"grading": {"scaffold": {"path": "hidden/missing.tar.gz"}}},
                    root / "candidate-safe-case",
                ),
                [],
            )

    def test_container_workspace_is_writable_without_changing_execute_bits(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate"
            workspace = candidate / "workspaces/repository"
            nested = workspace / "nested"
            nested.mkdir(parents=True)
            file_path = nested / "file.txt"
            file_path.write_text("content")
            workspace.chmod(0o555)
            nested.chmod(0o555)
            file_path.chmod(0o444)
            matrix.make_container_workspace_writable(candidate)
            self.assertEqual(workspace.stat().st_mode & 0o777, 0o777)
            self.assertEqual(nested.stat().st_mode & 0o777, 0o777)
            self.assertEqual(file_path.stat().st_mode & 0o777, 0o666)

    def test_container_workspace_does_not_follow_dependency_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "candidate/workspaces/repository"
            dependency = root / "dependency"
            workspace.mkdir(parents=True)
            dependency.mkdir()
            dependency_file = dependency / "package.json"
            dependency_file.write_text("{}")
            dependency.chmod(0o555)
            dependency_file.chmod(0o444)
            (workspace / "node_modules").symlink_to(dependency, target_is_directory=True)
            matrix.make_container_workspace_writable(root / "candidate")
            self.assertEqual(dependency.stat().st_mode & 0o777, 0o555)
            self.assertEqual(dependency_file.stat().st_mode & 0o777, 0o444)

    def test_grading_git_identity_tracks_exact_captured_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate"
            workspace = candidate / "workspaces/repository"
            workspace.mkdir(parents=True)
            subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
            (workspace / ".gitignore").write_text("cache/\n")
            (workspace / "tracked.txt").write_text("baseline\n")
            subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Matrix Test",
                    "-c",
                    "user.email=matrix@invalid",
                    "commit",
                    "-qm",
                    "baseline",
                ],
                cwd=workspace,
                check=True,
            )
            (workspace / "tracked.txt").write_text("candidate\n")
            (workspace / "new.txt").write_text("new\n")
            (workspace / "cache").mkdir()
            (workspace / "cache/dependency.bin").write_text("ignored\n")
            subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
            expected = subprocess.check_output(
                ["git", "write-tree"], cwd=workspace, text=True
            ).strip()
            subprocess.run(["git", "reset", "-q"], cwd=workspace, check=True)
            receipt = matrix.synchronize_grading_git_identity(
                candidate,
                [{"workspace": "repository", "resultTree": expected}],
            )
            self.assertEqual(receipt[0]["trackedFiles"], 3)
            self.assertEqual(receipt[0]["tree"], expected)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "write-tree"], cwd=workspace, text=True
                ).strip(),
                expected,
            )

    def test_product_stage_rejects_candidate_tree_changed_after_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate"
            workspace = candidate / "workspaces/repository"
            workspace.mkdir(parents=True)
            subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
            (workspace / "value.txt").write_text("captured\n")
            subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
            expected = subprocess.check_output(
                ["git", "write-tree"], cwd=workspace, text=True
            ).strip()
            (workspace / "value.txt").write_text("changed later\n")
            with self.assertRaisesRegex(
                ValueError, "candidate tree changed after candidate capture"
            ):
                matrix.verify_candidate_trees(
                    candidate,
                    [{"workspace": "repository", "resultTree": expected}],
                )

    def test_container_scaffold_is_writable_for_grading(self):
        class Runner:
            @staticmethod
            def sha256(path):
                return digest(path)

            @staticmethod
            def detach_cache_symlinks(_candidate):
                return []

            @staticmethod
            def extract_archive_with_modes(archive, destination):
                matrix.tarfile.TarFile.extractall(archive, destination, filter="data")
                for member in archive.getmembers():
                    target = destination / member.name
                    if target.exists() and not member.issym() and not member.islnk():
                        target.chmod(member.mode)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            workspace = candidate / "workspaces/repository"
            workspace.mkdir(parents=True)
            source = root / "config.toml"
            source.write_text("[net]\noffline = true\n")
            source.chmod(0o644)
            archive = root / "scaffold.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                stream.add(source, arcname="workspace-a/.cargo/config.toml")
            case = {
                "grading": {
                    "scaffold": {
                        "path": archive.name,
                        "sha256": digest(archive),
                    }
                }
            }
            matrix.prepare_container_grading_tree(
                Runner(), case, root, candidate
            )
            protected = (
                candidate
                / "workspaces/workspace-a/.cargo/config.toml"
            )
            workspace = candidate / "workspaces/workspace-a"
            self.assertEqual(workspace.stat().st_mode & 0o777, 0o777)
            self.assertEqual(protected.stat().st_mode & 0o777, 0o666)

    def test_dependency_environment_provisions_exact_cargo_home(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dependency"
            cargo_home = source / "cargo-home"
            cargo_home.mkdir(parents=True)
            with mock.patch.dict(os.environ, {"CARGO_HOME": "preexisting"}, clear=False):
                with matrix.dependency_environment({"runtime": source}):
                    self.assertEqual(os.environ["CARGO_HOME"], str(cargo_home.resolve()))
                self.assertEqual(os.environ["CARGO_HOME"], "preexisting")

    def test_dependency_environment_uses_scaffolded_cargo_home(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate"
            cargo_home = candidate / "workspaces/workspace-a/.cargo-home"
            cargo_home.mkdir(parents=True)
            with mock.patch.dict(os.environ, {}, clear=True):
                with matrix.dependency_environment({}, candidate):
                    self.assertEqual(os.environ["CARGO_HOME"], str(cargo_home.resolve()))
                self.assertNotIn("CARGO_HOME", os.environ)

    def test_dependency_environment_overlays_sealed_git_and_ambient_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            git_cache = candidate / "workspaces/runtime-repo/.cargo-git"
            (git_cache / "db/repository").mkdir(parents=True)
            (git_cache / "db/repository/HEAD").write_text("ref: refs/heads/main\n")
            home = root / "home"
            registry = home / ".cargo/registry"
            registry.mkdir(parents=True)
            run_root = root / "run"
            with mock.patch.dict(os.environ, {"HOME": str(home)}, clear=True):
                with matrix.dependency_environment({}, candidate, run_root):
                    overlay = run_root / "dependency-runtime/cargo-home"
                    self.assertEqual(os.environ["CARGO_HOME"], str(overlay.resolve()))
                    self.assertEqual(
                        (overlay / "git/db/repository/HEAD").read_text(),
                        "ref: refs/heads/main\n",
                    )
                    self.assertEqual((overlay / "registry").resolve(), registry.resolve())
                self.assertNotIn("CARGO_HOME", os.environ)

    def test_dependency_environment_fetches_locked_registry_without_ambient_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            candidate_workspace = candidate / "workspaces/runtime-repo"
            (candidate_workspace / ".cargo-git/db/repository").mkdir(parents=True)
            (candidate_workspace / ".cargo/config.toml").parent.mkdir(exist_ok=True)
            (candidate_workspace / ".cargo/config.toml").write_text(
                "[net]\ngit-fetch-with-cli = true\n"
            )
            workspace = root / "trusted/runtime-repo"
            git_cache = workspace / ".cargo-git"
            (git_cache / "db/repository").mkdir(parents=True)
            (git_cache / "db/repository/HEAD").write_text("ref: refs/heads/main\n")
            (workspace / "Cargo.toml").write_text("[workspace]\n")
            (workspace / "Cargo.lock").write_text("# lock\n")
            home = root / "home"
            home.mkdir()
            rustup_home = home / ".rustup"
            rustup_home.mkdir()
            (rustup_home / "settings.toml").write_text(
                'default_toolchain = "stable-aarch64-apple-darwin"\n'
            )
            run_root = root / "run"
            captured = {}

            def fetch(command, **kwargs):
                captured["command"] = command
                captured["environment"] = kwargs["env"]
                captured["cwd"] = kwargs["cwd"]
                kwargs["stdout"].write(b"fetched\n")
                (run_root / "dependency-runtime/cargo-home/registry").mkdir()
                return mock.Mock(returncode=0)

            with mock.patch.dict(
                os.environ,
                {"HOME": str(home), "ACTIONS_RUNTIME_TOKEN": "secret"},
                clear=True,
            ):
                with mock.patch.object(matrix.subprocess, "run", side_effect=fetch):
                    with matrix.dependency_environment(
                        {}, candidate, run_root, workspace
                    ):
                        self.assertEqual(
                            os.environ["CARGO_HOME"],
                            str((run_root / "dependency-runtime/cargo-home").resolve()),
                        )
            self.assertEqual(captured["command"], ["cargo", "fetch", "--locked"])
            self.assertNotIn("ACTIONS_RUNTIME_TOKEN", captured["environment"])
            self.assertNotIn("SSH_AUTH_SOCK", captured["environment"])
            self.assertEqual(captured["environment"]["HOME"], str(
                run_root / "dependency-runtime/cargo-fetch-home"
            ))
            self.assertEqual(
                captured["environment"]["RUSTUP_HOME"],
                str(rustup_home.resolve()),
            )
            self.assertEqual(
                captured["environment"]["RUSTUP_TOOLCHAIN"],
                "stable-aarch64-apple-darwin",
            )
            self.assertEqual(captured["cwd"], workspace.resolve())
            self.assertTrue((run_root / "dependency-logs/cargo-fetch.json").is_file())

    def test_dependency_environment_rejects_ancestor_cargo_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            (candidate / "workspaces/runtime-repo/.cargo-git").mkdir(parents=True)
            workspace = root / "trusted/runtime-repo"
            (workspace / ".cargo-git").mkdir(parents=True)
            (workspace / "Cargo.toml").write_text("[workspace]\n")
            (workspace / "Cargo.lock").write_text("# lock\n")
            ancestor_config = root / "trusted/.cargo/config.toml"
            ancestor_config.parent.mkdir()
            ancestor_config.write_text("[source.crates-io]\nreplace-with = 'candidate'\n")
            home = root / "home"
            home.mkdir()
            with mock.patch.dict(os.environ, {"HOME": str(home)}, clear=True):
                with self.assertRaisesRegex(
                    ValueError, "Cargo fetch ancestor config is not allowed"
                ):
                    with matrix.dependency_environment(
                        {}, candidate, root / "run", workspace
                    ):
                        pass

    def test_hosted_container_case_removes_only_redundant_root_chown(self):
        command = (
            "mkdir -p /workspace/capture/tmp /workspace/capture/home && "
            + matrix.HOSTED_REDUNDANT_ROOT_CHOWN
            + "git init -q"
        )
        case = {
            "grading": {
                "execution": "container",
                "candidateSetup": [
                    {"argv": ["sh", "-c", command], "timeoutSeconds": 60}
                ],
                "setup": [
                    {"argv": ["python3", "/grader/setup.py"], "timeoutSeconds": 60}
                ],
            }
        }
        with mock.patch.object(matrix.platform, "system", return_value="Linux"):
            adapted, adaptations = matrix.adapt_hosted_container_case(case)
        self.assertEqual(case["grading"]["candidateSetup"][0]["argv"][2], command)
        self.assertEqual(
            adapted["grading"]["candidateSetup"][0]["argv"][2],
            "mkdir -p /workspace/capture/tmp /workspace/capture/home && "
            'mkdir -p "$HOME" && '
            "git config --file /workspace/capture/home/.gitconfig "
            "--add safe.directory /workspace/repo && git init -q",
        )
        self.assertEqual(
            adapted["grading"]["setup"][0]["argv"],
            ["python3", "/grader/setup.py"],
        )
        self.assertEqual(
            adaptations,
            [
                {
                    "phase": "candidateSetup",
                    "index": 0,
                    "reason": (
                        "The hosted container user namespace rejects recursive chown "
                        "on the bind-mounted workspace; host write permissions satisfy "
                        "the setup contract and Git is scoped to the exact mounted repo."
                    ),
                }
            ],
        )

    def test_runtime_dependency_clone_is_writable_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sealed"
            cache = source / "node_modules"
            cache.mkdir(parents=True)
            lock = source / "bun.lock"
            package = cache / "package.json"
            lock.write_text("lock")
            package.write_text("{}")
            source.chmod(0o555)
            cache.chmod(0o555)
            lock.chmod(0o444)
            package.chmod(0o444)
            runtime_sources, receipts = matrix.prepare_writable_dependency_sources(
                {"application": source},
                root / "run",
            )
            runtime = runtime_sources["application"]
            self.assertNotEqual(runtime, source)
            self.assertEqual((runtime / "bun.lock").read_text(), "lock")
            self.assertEqual((runtime / "node_modules/package.json").read_text(), "{}")
            (runtime / "node_modules/.vite-temp").mkdir()
            self.assertFalse((source / "node_modules/.vite-temp").exists())
            self.assertEqual(source.stat().st_mode & 0o777, 0o555)
            self.assertEqual(package.stat().st_mode & 0o777, 0o444)
            self.assertEqual(receipts[0]["writableCaches"], ["node_modules"])
            self.assertEqual(
                receipts[0]["sourcePathMetadataSha256"],
                receipts[0]["runtimePathMetadataSha256"],
            )
            self.assertEqual(receipts[0]["sourceVerification"], "pending")
            matrix.verify_dependency_sources_unchanged(receipts)
            self.assertEqual(receipts[0]["sourceVerification"], "unchanged")
            self.assertEqual(
                receipts[0]["sourceMetadataSha256Before"],
                receipts[0]["sourceMetadataSha256After"],
            )
            self.assertEqual(
                receipts[0]["sourceContentSha256Before"],
                receipts[0]["sourceContentSha256After"],
            )

    def test_dependency_runtime_receipt_accepts_empty_array(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dependency-runtime.json"
            matrix.write_json(path, [])
            self.assertEqual(matrix.read_json_list(path), [])

    def test_recovers_split_stage_receipt_after_product_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            candidate_stage = {
                "attemptId": "attempt-1",
                "caseId": "case-1",
                "caseRevision": "revision-1",
                "treatmentId": "treatment-1",
                "repetition": 1,
                "route": "macos-candidate-stage",
                "candidatePackageArchiveSha256": "candidate-package",
                "candidate": {"boundaryAudit": {"passed": True}},
                "sources": [{"workspace": "runtime"}],
                "gradingGitIdentity": {"name": "Evaluator"},
                "deterministicExecution": "container",
            }
            product = {
                "schemaVersion": 1,
                "passed": False,
                "records": [{"exitCode": 1}],
                "evidenceFiles": [],
            }
            matrix.write_json(
                run_root / "macos-candidate-stage-receipt.json",
                candidate_stage,
            )
            matrix.write_json(run_root / "dependency-runtime.json", [])
            matrix.write_json(run_root / "product/receipt.json", product)

            receipt = matrix.load_or_recover_macos_stage_receipt(run_root)

            self.assertEqual(receipt["route"], "macos-native-stage")
            self.assertEqual(receipt["product"], product)
            self.assertFalse(receipt["candidateRerunRequired"])
            self.assertEqual(
                matrix.read_json(run_root / "macos-stage-receipt.json"),
                receipt,
            )

    def test_dependency_identity_ignores_directory_allocation_size(self):
        source = inspect.getsource(matrix.dependency_metadata)
        path_source = inspect.getsource(matrix.dependency_path_metadata)
        self.assertIn('stat.st_size if kind == "file" else None', source)
        self.assertIn('stat.st_size if kind == "file" else None', path_source)

    def test_runtime_dependency_clone_allows_mode_changes_before_writable_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sealed"
            cache = source / "node_modules"
            cache.mkdir(parents=True)
            package = cache / "package.json"
            package.write_text("{}")
            package.chmod(0o444)
            real_run = subprocess.run

            def copy_with_changed_mode(command, **kwargs):
                if command[:2] == ["cp", "-cR"]:
                    shutil.copytree(command[2], command[3], symlinks=True)
                    (Path(command[3]) / "node_modules/package.json").chmod(0o644)
                    return subprocess.CompletedProcess(command, 0)
                return real_run(command, **kwargs)

            with mock.patch.object(
                matrix.subprocess, "run", side_effect=copy_with_changed_mode
            ):
                runtime_sources, receipts = matrix.prepare_writable_dependency_sources(
                    {"application": source},
                    root / "run",
                )

            runtime = runtime_sources["application"]
            self.assertEqual((runtime / "node_modules/package.json").read_text(), "{}")
            self.assertEqual(package.stat().st_mode & 0o777, 0o444)
            self.assertEqual(
                receipts[0]["sourcePathMetadataSha256"],
                receipts[0]["runtimePathMetadataSha256"],
            )
            self.assertEqual(
                receipts[0]["sourceContentSha256Before"],
                receipts[0]["runtimeContentSha256"],
            )

    def test_runtime_dependency_verification_rejects_source_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sealed"
            source.mkdir()
            file_path = source / "file"
            file_path.write_text("alpha")
            receipts = [
                {
                    "workspace": "application",
                    "source": str(source),
                    "sourceMetadataSha256Before": matrix.dependency_metadata(source),
                    "sourceContentSha256Before": matrix.dependency_content_sha256(source),
                }
            ]
            file_path.write_text("omega")
            with self.assertRaisesRegex(
                ValueError,
                "Sealed dependency source content changed during execution",
            ):
                matrix.verify_dependency_sources_unchanged(receipts)

    def test_python_only_dependency_source_stays_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sealed"
            (source / "wheels").mkdir(parents=True)
            runtime_sources, receipts = matrix.prepare_writable_dependency_sources(
                {"service": source},
                root / "run",
            )
            self.assertEqual(runtime_sources, {"service": source.resolve()})
            self.assertEqual(receipts, [])

    def test_git_tree_is_stable_across_synthetic_commit_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repositories = []
            for index in range(2):
                repository = root / str(index)
                repository.mkdir()
                subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
                subprocess.run(
                    ["git", "config", "user.name", "Matrix Test"],
                    cwd=repository,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", "matrix-test@invalid"],
                    cwd=repository,
                    check=True,
                )
                (repository / "file.txt").write_text("same tree\n")
                subprocess.run(["git", "add", "file.txt"], cwd=repository, check=True)
                subprocess.run(
                    ["git", "commit", "--quiet", "-m", f"synthetic {index}"],
                    cwd=repository,
                    check=True,
                )
                repositories.append(repository)
            commits = [
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=repository, text=True
                ).strip()
                for repository in repositories
            ]
            self.assertNotEqual(commits[0], commits[1])
            self.assertEqual(
                matrix.git_tree(repositories[0]),
                matrix.git_tree(repositories[1]),
            )

    def test_empty_candidate_patch_is_a_valid_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patch = root / "candidate.patch"
            patch.write_bytes(b"")
            with mock.patch.object(matrix.subprocess, "run") as run:
                self.assertFalse(matrix.apply_candidate_patch(root, patch))
            run.assert_not_called()

    def make_package(self, root):
        cases = []
        attempts = []
        definitions = (
            ("linux-case", "1" * 64, "linux", "container", "sha256:" + "a" * 64),
            ("mac-case", "2" * 64, "macos", "host", None),
        )
        for index, (case_id, revision, os_name, execution, image) in enumerate(definitions, 1):
            case_root = root / "cases" / case_id / revision
            case_root.mkdir(parents=True)
            case = {
                "caseId": case_id,
                "caseRevision": revision,
                "runtime": {"platform": {"architecture": "arm64", "os": os_name}},
                "grading": {"execution": execution},
            }
            if image:
                case["grading"]["image"] = image
            manifest_path = case_root / "case-manifest.json"
            manifest_path.write_text(json.dumps(case))
            cases.append(
                {
                    "caseId": case_id,
                    "caseRevision": revision,
                    "manifest": manifest_path.relative_to(root).as_posix(),
                    "manifestSha256": digest(manifest_path),
                }
            )
            attempts.append(
                {
                    "attemptId": f"attempt-{index}",
                    "caseId": case_id,
                    "caseRevision": revision,
                    "treatmentId": "legacy-baseline",
                    "repetition": 1,
                    "candidateTimeoutSeconds": 7200,
                }
            )
        package = {
            "schemaVersion": 1,
            "campaignId": matrix.CAMPAIGN_ID,
            "cases": cases,
        }
        package_path = root / "package-manifest.json"
        package_path.write_text(json.dumps(package))
        (root / "execution-matrix.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "campaignId": matrix.CAMPAIGN_ID,
                    "attempts": attempts,
                }
            )
        )
        return attempts, digest(package_path)

    def write_controls(self, root, attempts):
        completion = {
            "schemaVersion": 1,
            "campaignId": matrix.CAMPAIGN_ID,
            "packageArchiveSha256": matrix.PACKAGE_ARCHIVE_SHA256,
            "packageManifestSha256": matrix.PACKAGE_MANIFEST_SHA256,
            "completedAttempts": [
                {
                    **matrix.attempt_identity(attempts[0]),
                    "outcome": "PASS",
                    "retainedEvidenceSha256": "c" * 64,
                }
            ],
            "excludedAttempts": [],
        }
        completion_path = root / "completion.json"
        completion_path.write_text(json.dumps(completion))
        images = {
            "schemaVersion": 1,
            "assets": [
                {
                    "imageId": "sha256:" + "a" * 64,
                    "release": "images-r1",
                    "asset": "image.tar",
                    "sha256": "b" * 64,
                    "bytes": 123,
                }
            ],
        }
        image_path = root / "images.json"
        image_path.write_text(json.dumps(images))
        dependency_path = root / "dependencies.json"
        dependency_path.write_text(json.dumps({"schemaVersion": 1, "dependencies": []}))
        return completion_path, image_path, dependency_path

    def test_plan_excludes_completed_and_routes_remaining_mac(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            plan = matrix.build_plan(
                root,
                completion,
                images,
                dependencies,
                expected_manifest_sha256=package_sha,
            )
            self.assertEqual(plan["excludedCount"], 1)
            self.assertEqual(plan["remainingCount"], 1)
            self.assertEqual(plan["macosCount"], 1)
            self.assertEqual(plan["linuxCount"], 0)
            job = plan["matrix"]["include"][0]
            self.assertEqual(job["attemptId"], "attempt-2")
            self.assertEqual(job["route"], "macos-native-stage")
            self.assertEqual(job["gradingRoute"], "macos-host-final")
            self.assertEqual(job["imageAsset"], "")

    def test_plan_routes_linux_full_and_binds_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            value = json.loads(completion.read_text())
            value["completedAttempts"] = []
            value["excludedAttempts"] = [
                {**matrix.attempt_identity(attempts[1]), "reason": "reserved locally"}
            ]
            completion.write_text(json.dumps(value))
            plan = matrix.build_plan(
                root,
                completion,
                images,
                dependencies,
                expected_manifest_sha256=package_sha,
            )
            job = plan["matrix"]["include"][0]
            self.assertEqual(job["route"], "full-linux")
            self.assertEqual(job["gradingRoute"], "hosted-final")
            self.assertEqual(job["imageId"], "sha256:" + "a" * 64)
            self.assertEqual(job["imageAsset"], "image.tar")
            self.assertEqual(plan["linuxCount"], 1)
            self.assertEqual(plan["macosCount"], 0)

    def test_split_plan_rejects_linux_candidate_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            value = json.loads(completion.read_text())
            value["completedAttempts"] = []
            value["excludedAttempts"] = [
                {**matrix.attempt_identity(attempts[1]), "reason": "macOS reserved"}
            ]
            value["candidatePackageArchiveSha256"] = "f" * 64
            completion.write_text(json.dumps(value))
            with mock.patch.object(
                matrix, "CANDIDATE_PACKAGE_ARCHIVE_SHA256", "f" * 64
            ):
                with self.assertRaisesRegex(
                    ValueError, "support only macOS attempts"
                ):
                    matrix.build_plan(
                        root,
                        completion,
                        images,
                        dependencies,
                        expected_manifest_sha256=package_sha,
                    )

    def test_split_plan_rejects_external_dependency_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            completion_value = json.loads(completion.read_text())
            completion_value["candidatePackageArchiveSha256"] = "f" * 64
            completion.write_text(json.dumps(completion_value))
            dependencies.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "dependencies": [
                            {
                                "workspace": "workspace-a",
                                "status": "READY",
                                "archiveRoot": ".",
                                "locks": [
                                    {"path": "Cargo.lock", "sha256": "a" * 64}
                                ],
                                "cachePaths": [".cargo"],
                                "cases": ["mac-case"],
                                "release": "dependencies-r1",
                                "asset": "workspace-a.tar.gz",
                                "sha256": "b" * 64,
                                "bytes": 123,
                            }
                        ],
                    }
                )
            )
            with mock.patch.object(
                matrix, "CANDIDATE_PACKAGE_ARCHIVE_SHA256", "f" * 64
            ):
                with self.assertRaisesRegex(
                    ValueError, "do not yet support external dependency archives"
                ):
                    matrix.build_plan(
                        root,
                        completion,
                        images,
                        dependencies,
                        expected_manifest_sha256=package_sha,
                    )

    def test_completion_rejects_duplicate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            value = json.loads(completion.read_text())
            value["excludedAttempts"] = [
                {**matrix.attempt_identity(attempts[0]), "reason": "also reserved"}
            ]
            completion.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "Duplicate completion/exclusion"):
                matrix.build_plan(
                    root,
                    completion,
                    images,
                    dependencies,
                    expected_manifest_sha256=package_sha,
                )

    def test_completion_rejects_mismatched_attempt_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            value = json.loads(completion.read_text())
            value["completedAttempts"][0]["caseRevision"] = "f" * 64
            completion.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "Attempt identity mismatch"):
                matrix.build_plan(
                    root,
                    completion,
                    images,
                    dependencies,
                    expected_manifest_sha256=package_sha,
                )

    def test_plan_fails_closed_when_required_image_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            json_images = json.loads(images.read_text())
            json_images["assets"] = []
            images.write_text(json.dumps(json_images))
            value = json.loads(completion.read_text())
            value["completedAttempts"] = []
            completion.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "No release asset for grading image"):
                matrix.build_plan(
                    root,
                    completion,
                    images,
                    dependencies,
                    expected_manifest_sha256=package_sha,
                )

    def test_select_attempt_rejects_dispatch_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            original = matrix.PACKAGE_MANIFEST_SHA256
            matrix.PACKAGE_MANIFEST_SHA256 = package_sha
            try:
                supplied = matrix.attempt_identity(attempts[0])
                supplied["treatmentId"] = "wrong-treatment"
                with self.assertRaisesRegex(ValueError, "Dispatched attempt identity mismatch"):
                    matrix.select_attempt(root, attempts[0]["attemptId"], supplied)
            finally:
                matrix.PACKAGE_MANIFEST_SHA256 = original

    def test_artifact_name_is_attempt_and_run_unique(self):
        self.assertEqual(
            matrix.artifact_name("campaign-a-case-1-treatment-1", "123", "1"),
            "distributed-eval-final-campaign-a-case-1-treatment-1-123-1",
        )
        with self.assertRaises(ValueError):
            matrix.artifact_name("../attempt", "123", "1")

    def test_retained_checksum_is_bound_to_archive_name_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "retained.tar.gz"
            archive.write_bytes(b"artifact")
            checksum = root / "retained.tar.gz.sha256"
            checksum.write_text(f"{digest(archive)}  retained.tar.gz\n")
            self.assertEqual(
                matrix.retained_archive_sha256(archive, checksum),
                digest(archive),
            )
            checksum.write_text(f"{digest(archive)}  other.tar.gz\n")
            with self.assertRaisesRegex(ValueError, "checksum record"):
                matrix.retained_archive_sha256(archive, checksum)

    def test_freeze_completion_binds_terminal_and_active_ledger_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            ledger = root / "ledger.json"
            ledger.write_text(
                json.dumps(
                    {
                        attempts[0]["attemptId"]: {
                            **matrix.attempt_identity(attempts[0]),
                            "state": "COMPLETE",
                            "outcome": "FAIL",
                            "packageManifestSha256": package_sha,
                            "retainedEvidence": {"sha256": "d" * 64},
                        },
                        attempts[1]["attemptId"]: {
                            **matrix.attempt_identity(attempts[1]),
                            "state": "RUNNING",
                            "packageManifestSha256": package_sha,
                        },
                    }
                )
            )
            original = matrix.PACKAGE_MANIFEST_SHA256
            matrix.PACKAGE_MANIFEST_SHA256 = package_sha
            try:
                value = matrix.freeze_completion(
                    root, ledger, root / "completion.json", {"RUNNING"}
                )
            finally:
                matrix.PACKAGE_MANIFEST_SHA256 = original
            self.assertEqual(
                [item["attemptId"] for item in value["completedAttempts"]],
                ["attempt-1"],
            )
            self.assertEqual(
                [item["attemptId"] for item in value["excludedAttempts"]],
                ["attempt-2"],
            )

    def test_safe_extract_rejects_escaping_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "inputs.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                member = tarfile.TarInfo("root/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                output.addfile(member, io.BytesIO())
            with self.assertRaisesRegex(ValueError, "Unsafe archive link target"):
                matrix.safe_extract(archive, root / "inputs", digest(archive))

    def test_safe_extract_accepts_direct_in_tree_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "inputs.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                target = tarfile.TarInfo("node_modules/pkg/.bin/tool")
                target.size = 4
                output.addfile(target, io.BytesIO(b"tool"))
                member = tarfile.TarInfo("node_modules/pkg/tool")
                member.type = tarfile.SYMTYPE
                member.linkname = ".bin/tool"
                output.addfile(member)
            destination = root / "inputs"
            matrix.safe_extract(archive, destination, digest(archive))
            self.assertEqual(
                (destination / "node_modules/pkg/tool").resolve(),
                (destination / "node_modules/pkg/.bin/tool").resolve(),
            )

    def test_safe_extract_rejects_chained_link_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "inputs.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                first = tarfile.TarInfo("root/first")
                first.type = tarfile.SYMTYPE
                first.linkname = "second"
                output.addfile(first)
                second = tarfile.TarInfo("root/second")
                second.type = tarfile.SYMTYPE
                second.linkname = "../../outside"
                output.addfile(second)
            with self.assertRaisesRegex(ValueError, "Unsafe archive link target"):
                matrix.safe_extract(archive, root / "inputs", digest(archive))

    def test_release_download_retries_transient_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "asset.tar.gz"
            results = [mock.Mock(returncode=1), mock.Mock(returncode=0)]

            def download(command, **_kwargs):
                result = results.pop(0)
                if result.returncode == 0:
                    output = Path(command[command.index("--dir") + 1])
                    (output / "asset.tar.gz").write_bytes(b"asset")
                return result

            with mock.patch.object(matrix.subprocess, "run", side_effect=download) as run:
                with mock.patch.object(matrix.time, "sleep") as sleep:
                    matrix.download_release_asset(
                        "owner/repository",
                        "release-1",
                        "asset.tar.gz",
                        destination,
                        attempts=3,
                    )
            self.assertEqual(destination.read_bytes(), b"asset")
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(2)

    def test_release_download_rejects_more_than_five_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "asset.tar.gz"
            with mock.patch.object(matrix.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                    matrix.download_release_asset(
                        "owner/repository",
                        "release-1",
                        "asset.tar.gz",
                        destination,
                        attempts=6,
                    )
            run.assert_not_called()

    def test_release_download_retries_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "asset.tar.gz"
            payloads = [b"partial-http-error", b"complete-asset"]

            def download(command, **_kwargs):
                output = Path(command[command.index("--dir") + 1])
                (output / "asset.tar.gz").write_bytes(payloads.pop(0))
                return mock.Mock(returncode=0)

            with mock.patch.object(matrix.subprocess, "run", side_effect=download) as run:
                with mock.patch.object(matrix.time, "sleep") as sleep:
                    matrix.download_release_asset(
                        "owner/repository",
                        "release-1",
                        "asset.tar.gz",
                        destination,
                        attempts=3,
                        expected_sha256=hashlib.sha256(b"complete-asset").hexdigest(),
                    )
            self.assertEqual(destination.read_bytes(), b"complete-asset")
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(2)

    def test_retention_excludes_reconstructible_candidate_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "run-root"
            evidence = root / "evidence"
            (run_root / "candidate").mkdir(parents=True)
            (run_root / "candidate" / "secret-build-output").write_text("discard")
            (run_root / "candidate-source").mkdir()
            (run_root / "candidate-source" / "repo.patch").write_text("patch")
            evidence.mkdir()
            (evidence / "status.json").write_text("{}")
            output = root / "retained.tar.gz"
            matrix.create_retained_archive(run_root, evidence, output)
            with tarfile.open(output, "r:gz") as archive:
                names = archive.getnames()
            self.assertIn("run-root/candidate-source/repo.patch", names)
            self.assertIn("evidence/status.json", names)
            self.assertNotIn("run-root/candidate/secret-build-output", names)

    def test_finalizer_rejects_changed_host_grading_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "hosted-deterministic"
            evidence.mkdir()
            log = evidence / "target.log"
            log.write_text("original")
            receipt = {
                "schemaVersion": 1,
                "results": [{"log": "target.log", "logSha256": digest(log)}],
            }
            (evidence / "receipt.json").write_text(json.dumps(receipt))
            matrix.validate_hosted_deterministic_directory(evidence, receipt)
            log.write_text("changed")
            with self.assertRaisesRegex(ValueError, "log digest mismatch"):
                matrix.validate_hosted_deterministic_directory(evidence, receipt)

    def test_judge_process_strips_unrelated_credentials_and_marks_model_token(self):
        class Runner:
            environment = None
            command = None

            @staticmethod
            def load_copilot_model_token():
                return "model-token"

            @classmethod
            def run_command(cls, command, **kwargs):
                cls.environment = kwargs["environment"]
                cls.command = command
                kwargs["log"].write_text(
                    json.dumps(
                        {
                            "verdict": "FAIL",
                            "confidence": "HIGH",
                            "matched": ["one"],
                            "missed": ["two"],
                            "overcorrections": [],
                            "generalized_skill_defect": None,
                        }
                    )
                )
                return {
                    "argv": command,
                    "cwd": str(kwargs["cwd"]),
                    "exitCode": 0,
                    "timedOut": False,
                    "elapsedSeconds": 0.1,
                    "log": kwargs["log"].name,
                    "logSha256": digest(kwargs["log"]),
                }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            candidate_root = root / "candidate"
            run_root = root / "run"
            (case_root / "hidden/authority/prompts").mkdir(parents=True)
            (case_root / "hidden/authority/criteria.md").write_text("criteria")
            (case_root / "hidden/authority/prompts/judge.md").write_text("judge")
            candidate_root.mkdir()
            (candidate_root / "task.md").write_text("task")
            run_root.mkdir()
            with mock.patch.dict(
                "os.environ",
                {
                    "ACTIONS_RUNTIME_TOKEN": "runtime-token",
                    "GH_HOST": "github.example.com",
                    "SAFE_VALUE": "safe",
                },
                clear=True,
            ):
                result = matrix.secure_run_judge(
                    Runner(),
                    case_root=case_root,
                    candidate_root=candidate_root,
                    run_root=run_root,
                    model="judge-model",
                    timeout=30,
                )
            self.assertNotIn("ACTIONS_RUNTIME_TOKEN", Runner.environment)
            self.assertNotIn("GH_HOST", Runner.environment)
            self.assertEqual(Runner.environment["COPILOT_GITHUB_TOKEN"], "model-token")
            secret_index = Runner.command.index("--secret-env-vars") + 1
            self.assertIn("COPILOT_GITHUB_TOKEN", Runner.command[secret_index])
            self.assertNotIn("environment", result)
            self.assertNotIn("model-token", json.dumps(result))
            self.assertEqual(result["judgment"]["verdict"], "FAIL")

    def test_judge_retries_one_contract_format_failure(self):
        class Runner:
            calls = 0

            @staticmethod
            def load_copilot_model_token():
                return "model-token"

            @classmethod
            def run_command(cls, command, **kwargs):
                cls.calls += 1
                if cls.calls == 1:
                    kwargs["log"].write_text("## Verdict: FAIL\n")
                else:
                    kwargs["log"].write_text(
                        json.dumps(
                            {
                                "verdict": "FAIL",
                                "confidence": "HIGH",
                                "matched": ["one"],
                                "missed": ["two"],
                                "overcorrections": [],
                                "generalized_skill_defect": None,
                            }
                        )
                    )
                return {
                    "argv": command,
                    "cwd": str(kwargs["cwd"]),
                    "exitCode": 0,
                    "timedOut": False,
                    "elapsedSeconds": 0.1,
                    "log": kwargs["log"].name,
                    "logSha256": digest(kwargs["log"]),
                }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            candidate_root = root / "candidate"
            run_root = root / "run"
            (case_root / "hidden/authority/prompts").mkdir(parents=True)
            (case_root / "hidden/authority/criteria.md").write_text("criteria")
            (case_root / "hidden/authority/prompts/judge.md").write_text("judge")
            candidate_root.mkdir()
            (candidate_root / "task.md").write_text("task")
            run_root.mkdir()
            result = matrix.secure_run_judge(
                Runner(),
                case_root=case_root,
                candidate_root=candidate_root,
                run_root=run_root,
                model="judge-model",
                timeout=30,
            )
            judge_root = run_root / "judge/judge-model"
            self.assertEqual(result["formatAttempts"], 2)
            self.assertEqual(
                result["priorFormatErrors"],
                ["Judge output must contain exactly one contract JSON object"],
            )
            self.assertEqual(
                (judge_root / "judgment.attempt-1.raw.txt").read_text(),
                "## Verdict: FAIL\n",
            )
            self.assertTrue((judge_root / "judgment.attempt-1.error.txt").is_file())
            self.assertEqual(result["judgment"]["verdict"], "FAIL")
            retry_prompt = result["argv"][result["argv"].index("-p") + 1]
            self.assertIn("exactly PASS, FAIL, or UNANSWERABLE", retry_prompt)
            self.assertIn("exactly LOW, MEDIUM, or HIGH", retry_prompt)

    def test_judge_output_accepts_one_fenced_json_object_after_preamble(self):
        value = matrix.parse_judge_output(
            "I inspected the evidence — including non-ASCII prose.\n\n```json\n"
            + json.dumps(
                {
                    "verdict": "FAIL",
                    "confidence": "HIGH",
                    "matched": ["one"],
                    "missed": ["two"],
                    "overcorrections": [],
                    "generalized_skill_defect": "three",
                }
            )
            + "\n```\n"
        )
        self.assertEqual(value["verdict"], "FAIL")
        self.assertEqual(value["generalized_skill_defect"], "three")

    def test_judge_output_accepts_one_inline_json_object_after_preamble(self):
        judgment = {
            "verdict": "FAIL",
            "confidence": "HIGH",
            "matched": ["one"],
            "missed": ["two"],
            "overcorrections": [],
            "generalized_skill_defect": None,
        }
        value = matrix.parse_judge_output(
            "I inspected the evidence first.\n\n" + json.dumps(judgment)
        )
        self.assertEqual(value, judgment)

    def test_judge_output_accepts_repeated_identical_contract(self):
        judgment = {
            "verdict": "FAIL",
            "confidence": "HIGH",
            "matched": ["one"],
            "missed": ["two"],
            "overcorrections": [],
            "generalized_skill_defect": None,
        }
        self.assertEqual(
            matrix.parse_judge_output(
                json.dumps(judgment) + "\n" + json.dumps(judgment)
            ),
            judgment,
        )

    def test_judge_output_rejects_conflicting_contracts(self):
        first = {
            "verdict": "FAIL",
            "confidence": "HIGH",
            "matched": ["one"],
            "missed": ["two"],
            "overcorrections": [],
            "generalized_skill_defect": None,
        }
        second = {**first, "verdict": "PASS"}
        with self.assertRaisesRegex(ValueError, "conflicting contract JSON objects"):
            matrix.parse_judge_output(
                json.dumps(first) + "\n" + json.dumps(second)
            )

    def test_judge_output_rejects_invalid_contract(self):
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            matrix.parse_judge_output('{"verdict":"PASS"}')

    def test_reused_stage_dispatch_accepts_pinned_source_run(self):
        attempt = {
            "attemptId": "fp-r1-c01-t01-baseline",
            "caseId": "case",
            "caseRevision": "a" * 64,
            "treatmentId": "baseline",
            "repetition": 1,
        }
        source_sha = "1" * 40
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence"
            evidence.mkdir()
            (evidence / "workflow.yml").write_text("source workflow")
            (evidence / "distributed_campaign.py").write_text("source runner")
            matrix.write_json(
                evidence / "dispatch.json",
                {
                    "schemaVersion": 1,
                    "attempt": attempt,
                    "github": {
                        "GITHUB_SERVER_URL": "https://github.example.com",
                        "GITHUB_REPOSITORY": "example/evaluations",
                        "GITHUB_RUN_ID": "26011576",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SHA": source_sha,
                        "GITHUB_WORKFLOW_SHA": source_sha,
                    },
                },
            )
            with mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_RUN_ID": "26099999",
                    "GITHUB_SHA": "2" * 40,
                    "GITHUB_WORKFLOW_SHA": "2" * 40,
                    "GITHUB_SERVER_URL": "https://github.example.com",
                    "GITHUB_REPOSITORY": "example/evaluations",
                },
                clear=True,
            ):
                result = matrix.validate_stage_dispatch(
                    evidence / "dispatch.json",
                    attempt,
                    "26011576",
                    source_sha,
                )
        self.assertEqual(result["github"]["GITHUB_RUN_ID"], "26011576")

    def test_dependency_manifest_blocks_selected_pending_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            dependencies.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "dependencies": [
                            {
                                "workspace": "repo",
                                "cases": ["mac-case"],
                                "status": "PENDING",
                                "reason": "archive is still building",
                                "release": None,
                                "asset": None,
                                "sha256": None,
                                "bytes": None,
                                "archiveRoot": ".",
                                "cachePaths": ["node_modules"],
                                "locks": [{"path": "lock", "sha256": "e" * 64}],
                            }
                        ],
                    }
                )
            )
            value = json.loads(completion.read_text())
            value["completedAttempts"] = []
            completion.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "archive is still building"):
                matrix.build_plan(
                    root,
                    completion,
                    images,
                    dependencies,
                    expected_manifest_sha256=package_sha,
                    selected_attempt_id="attempt-2",
                )

    def test_plan_rejects_dependency_archive_for_linux_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts, package_sha = self.make_package(root)
            completion, images, dependencies = self.write_controls(root, attempts)
            value = json.loads(completion.read_text())
            value["completedAttempts"] = []
            completion.write_text(json.dumps(value))
            dependencies.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "dependencies": [
                            {
                                "workspace": "repo",
                                "cases": ["linux-case"],
                                "status": "READY",
                                "release": "deps-r1",
                                "asset": "deps.tar.gz",
                                "sha256": "e" * 64,
                                "bytes": 123,
                                "archiveRoot": ".",
                                "cachePaths": ["node_modules"],
                                "locks": [{"path": "lock", "sha256": "f" * 64}],
                            }
                        ],
                    }
                )
            )
            with self.assertRaisesRegex(
                ValueError, "Linux dependency archives are not supported"
            ):
                matrix.build_plan(
                    root,
                    completion,
                    images,
                    dependencies,
                    expected_manifest_sha256=package_sha,
                    selected_attempt_id="attempt-1",
                )

    def test_dependency_acl_commands_do_not_use_chmod_mode_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested/file").write_text("content")
            commands = matrix.dependency_acl_commands(root)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][0:3], ["chmod", "-R", "+a"])
            self.assertIn("everyone deny", commands[0][3])

    def test_dependency_archive_verifies_size_hash_lock_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            (payload / "node_modules").mkdir(parents=True)
            (payload / "node_modules/package.txt").write_text("dependency")
            (payload / "lock").write_text("locked")
            archive = root / "deps.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                for path in sorted(payload.rglob("*")):
                    output.add(path, arcname=path.relative_to(payload), recursive=False)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "dependencies": [
                            {
                                "workspace": "repo",
                                "cases": ["case"],
                                "status": "READY",
                                "release": "deps-r1",
                                "asset": "deps.tar.gz",
                                "sha256": digest(archive),
                                "bytes": archive.stat().st_size,
                                "archiveRoot": ".",
                                "cachePaths": ["node_modules"],
                                "locks": [
                                    {"path": "lock", "sha256": digest(payload / "lock")}
                                ],
                            }
                        ],
                    }
                )
            )
            with mock.patch.object(matrix.platform, "system", return_value="Darwin"), \
                    mock.patch.object(matrix, "dependency_acl_commands", return_value=[]):
                receipt = matrix.unpack_dependency(
                    manifest,
                    "repo",
                    "deps-r1",
                    archive,
                    root / "extracted",
                    root / "receipt.json",
                )
            self.assertEqual(receipt["archive"]["sha256"], digest(archive))
            self.assertFalse(receipt["bytesChanged"])
            self.assertFalse(receipt["posixModesChanged"])

    def test_runtime_dependency_contract_rejects_unlisted_target_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            (payload / "node_modules").mkdir(parents=True)
            (payload / "target").mkdir()
            (payload / "pnpm-lock.yaml").write_text("pnpm")
            archive = root / "runtime-deps.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                for path in sorted(payload.rglob("*")):
                    output.add(path, arcname=path.relative_to(payload), recursive=False)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "dependencies": [
                            {
                                "workspace": "runtime-repo",
                                "cases": ["case"],
                                "status": "READY",
                                "release": "deps-r1",
                                "asset": archive.name,
                                "sha256": digest(archive),
                                "bytes": archive.stat().st_size,
                                "archiveRoot": ".",
                                "cachePaths": ["node_modules"],
                                "locks": [
                                    {
                                        "path": "pnpm-lock.yaml",
                                        "sha256": digest(payload / "pnpm-lock.yaml"),
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
            with mock.patch.object(matrix.platform, "system", return_value="Darwin"):
                with self.assertRaisesRegex(ValueError, "Unexpected dependency cache.*target"):
                    matrix.unpack_dependency(
                        manifest,
                        "runtime-repo",
                        "deps-r1",
                        archive,
                        root / "extracted",
                        root / "receipt.json",
                    )

    def test_python_dependencies_install_offline_outside_sealed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sealed"
            wheels = source / "wheels"
            wheels.mkdir(parents=True)
            (source / "requirements.lock.txt").write_text("PyJWT==2.13.0\n")
            run_root = root / "run"
            run_root.mkdir()
            completed = mock.Mock(returncode=0)
            def install(command, **_kwargs):
                target = Path(command[command.index("--target") + 1])
                metadata = target / "PyJWT-2.13.0.dist-info"
                metadata.mkdir()
                (metadata / "METADATA").write_text("Name: PyJWT\nVersion: 2.13.0\n")
                return completed

            with mock.patch.object(matrix.subprocess, "run", side_effect=install) as run:
                targets = matrix.prepare_python_dependencies(
                    {"service": source},
                    run_root,
                    {"pyjwt": "2.13.0"},
                )
            self.assertEqual(targets, [run_root / "dependency-runtime/service/python"])
            command = run.call_args.args[0]
            self.assertIn("--no-index", command)
            self.assertEqual(command[command.index("--find-links") + 1], str(wheels))
            self.assertEqual(
                command[command.index("--target") + 1],
                str(run_root / "dependency-runtime/service/python"),
            )
            self.assertTrue((run_root / "python-dependencies.json").is_file())
            retained = matrix.retained_files(run_root, root / "evidence")
            retained_names = {name for _, name in retained}
            self.assertNotIn(
                "run-root/dependency-runtime/service/python/PyJWT-2.13.0.dist-info/METADATA",
                retained_names,
            )
            self.assertIn("run-root/dependency-logs/service-pip-install.log", retained_names)

    def test_scaffold_python_versions_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "scaffold.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                for name in (
                    "service/vendor/python/PyJWT-2.13.0.dist-info/",
                    "service/vendor/python/cryptography-49.0.0.dist-info/",
                ):
                    member = tarfile.TarInfo(name)
                    member.type = tarfile.DIRTYPE
                    output.addfile(member)
            case = {"grading": {"scaffold": {"path": archive.name}}}
            self.assertEqual(
                matrix.scaffold_python_distributions(case, root),
                {"cryptography": "49.0.0", "pyjwt": "2.13.0"},
            )

    def test_linux_finalization_source_never_calls_candidate_runner(self):
        source = inspect.getsource(matrix.finalize_linux)
        self.assertNotIn("run_candidate", source)
        self.assertIn("restore_candidate_sources", source)
        self.assertIn('"candidatePackageArchiveSha256"', source)
        self.assertIn('"packageArchiveSha256"', source)

    def test_linux_resume_source_never_calls_candidate_or_product_runner(self):
        source = inspect.getsource(matrix.resume_hosted_linux)
        self.assertNotIn("run_candidate", source)
        self.assertNotIn("run_product", source)
        self.assertIn("recover_retained_candidate_sources", source)
        self.assertIn('"candidateRerun": False', source)

    def test_linux_resume_plan_requires_exact_single_attempt_identity(self):
        attempt = {
            "attemptId": "attempt-1",
            "caseId": "case-1",
            "caseRevision": "a" * 64,
            "treatmentId": "treatment-1",
            "repetition": 2,
        }
        source_attempt = {
            **attempt,
            "route": "full-linux",
        }
        plan = {
            "schemaVersion": 1,
            "campaignId": matrix.CAMPAIGN_ID,
            "packageArchiveSha256": matrix.PACKAGE_ARCHIVE_SHA256,
            "packageManifestSha256": matrix.PACKAGE_MANIFEST_SHA256,
            "remainingCount": 1,
            "macosCount": 0,
            "linuxCount": 1,
            "linuxMatrix": {"include": [source_attempt]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dispatch-plan.json"
            path.write_text(json.dumps(plan))
            self.assertEqual(matrix.validate_linux_resume_plan(path, attempt), plan)
            plan["linuxMatrix"]["include"][0]["attemptId"] = "different"
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "attempt identity mismatch"):
                matrix.validate_linux_resume_plan(path, attempt)

    def test_linux_resume_failure_requires_exact_attempt_and_boundary(self):
        attempt = {
            "attemptId": "attempt-1",
            "caseId": "case-1",
            "caseRevision": "a" * 64,
            "treatmentId": "treatment-1",
            "repetition": 2,
        }
        error = {
            "schemaVersion": 1,
            **attempt,
            "errorType": "PackageInfrastructureError",
            "message": "candidate setup failed",
            "resumableBoundary": "candidate-setup",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hosted-stage-error.json"
            path.write_text(json.dumps(error))
            self.assertEqual(
                matrix.validate_linux_resume_failure(path, attempt),
                error,
            )
            error["treatmentId"] = "different"
            path.write_text(json.dumps(error))
            with self.assertRaisesRegex(ValueError, "attempt identity mismatch"):
                matrix.validate_linux_resume_failure(path, attempt)

    def test_linux_resume_accepts_git_sha_not_sha256(self):
        source = inspect.getsource(matrix.resume_hosted_linux)
        self.assertIn(r're.fullmatch(r"[0-9a-f]{40}", source_sha)', source)
        self.assertNotIn('check_sha256(source_sha, "source workflow SHA")', source)

    def test_actions_use_the_token_name_loaded_by_the_sealed_runner(self):
        workflow = (
            SCRIPT.parent.parent / "templates/distributed-campaign.yml"
        ).read_text()
        self.assertEqual(
            workflow.count(
                "COPILOT_EVAL_MODEL_TOKEN: ${{ secrets.COPILOT_GITHUB_TOKEN }}"
            ),
            4,
        )
        self.assertNotIn(
            "COPILOT_GITHUB_TOKEN: ${{ secrets.COPILOT_GITHUB_TOKEN }}",
            workflow,
        )
        self.assertIn(
            "if: inputs.macos_source_run_id == '' && inputs.linux_source_run_id == '' && "
            "needs.plan.outputs.linux_count != '0'",
            workflow,
        )
        self.assertIn("resume-hosted-linux", workflow)
        self.assertIn("inputs.linux_source_run_id != ''", workflow)
        self.assertIn(
            "macOS stage reuse cannot dispatch Linux-native candidates",
            workflow,
        )

    def test_dispatch_inputs_reach_shell_only_through_environment(self):
        workflow = (
            SCRIPT.parent.parent / "templates/distributed-campaign.yml"
        ).read_text()
        lines = workflow.splitlines()
        run_bodies = []
        for index, line in enumerate(lines):
            if line.lstrip() != "run: |":
                continue
            indent = len(line) - len(line.lstrip())
            body = []
            for candidate in lines[index + 1:]:
                if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= indent:
                    break
                body.append(candidate)
            run_bodies.append("\n".join(body))
        self.assertTrue(run_bodies)
        self.assertTrue(all("${{ inputs." not in body for body in run_bodies))
        self.assertNotIn('"${dependency[@]}"', workflow)
        self.assertIn(
            """$(printf '%s\\n' 'bun-darwin-aarch64/' 'bun-darwin-aarch64/bun')""",
            workflow,
        )
        self.assertNotIn("bun-darwin-aarch64/\\\\nbun-darwin-aarch64/bun", workflow)
        self.assertIn("hidden-package-seal.json", workflow)
        self.assertIn('"CANDIDATE_PACKAGE_SHA256"', workflow)
        self.assertIn("distributed-eval-candidate-${{ matrix.attemptId }}", workflow)
        self.assertIn("Run native product stage on reconstructed candidate", workflow)
        self.assertIn("test ! -e run-root/candidate", workflow)
        self.assertIn("COMPLETION_RELEASE: ${{ inputs.completion_release }}", workflow)

    def test_stage_dispatch_binds_populated_controls(self):
        attempt = {
            "attemptId": "attempt-1",
            "caseId": "case-1",
            "caseRevision": "1" * 64,
            "treatmentId": "baseline",
            "repetition": 1,
        }
        controls = {
            "PACKAGE_RELEASE": "package-release",
            "PACKAGE_ASSET": "package.tar.gz",
            "COMPLETION_RELEASE": "completion-release",
            "COMPLETION_ASSET": "completion.json",
            "COMPLETION_SHA256": "a" * 64,
            "CANDIDATE_PACKAGE_RELEASE": "candidate-release",
            "CANDIDATE_PACKAGE_ASSET": "candidate.tar.gz",
            "CANDIDATE_PACKAGE_SHA256": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            workflow = SCRIPT.parent.parent / "templates/distributed-campaign.yml"
            (evidence / "workflow.yml").write_bytes(workflow.read_bytes())
            (evidence / "distributed_campaign.py").write_bytes(SCRIPT.read_bytes())
            matrix.write_json(
                evidence / "dispatch.json",
                {
                    "schemaVersion": 1,
                    "attempt": attempt,
                    "controls": controls,
                    "github": {
                        "GITHUB_RUN_ID": "10",
                        "GITHUB_SHA": "b" * 40,
                        "GITHUB_WORKFLOW_SHA": "a" * 40,
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SERVER_URL": "https://github.example.com",
                        "GITHUB_REPOSITORY": "example/evaluations",
                    },
                },
            )
            environment = {
                **controls,
                "GITHUB_RUN_ID": "10",
                "GITHUB_SHA": "b" * 40,
                "GITHUB_WORKFLOW_SHA": "a" * 40,
                "GITHUB_SERVER_URL": "https://github.example.com",
                "GITHUB_REPOSITORY": "example/evaluations",
                "DISTRIBUTED_EVAL_WORKFLOW_PATH": str(workflow),
            }
            with mock.patch.dict("os.environ", environment, clear=True):
                matrix.validate_stage_dispatch(evidence / "dispatch.json", attempt)
            environment["CANDIDATE_PACKAGE_SHA256"] = "c" * 64
            with mock.patch.dict(
                "os.environ", environment, clear=True
            ), self.assertRaisesRegex(ValueError, "dispatch controls mismatch"):
                matrix.validate_stage_dispatch(evidence / "dispatch.json", attempt)

    def test_completion_manifest_binds_candidate_archive(self):
        completion = {
            "schemaVersion": 1,
            "campaignId": matrix.CAMPAIGN_ID,
            "packageArchiveSha256": matrix.PACKAGE_ARCHIVE_SHA256,
            "candidatePackageArchiveSha256": "f" * 64,
            "packageManifestSha256": matrix.PACKAGE_MANIFEST_SHA256,
            "completedAttempts": [],
            "excludedAttempts": [],
        }
        with self.assertRaisesRegex(
            ValueError, "candidate package archive identity mismatch"
        ):
            matrix.validate_completion_manifest_from_value(completion, {})

    def test_stage_dispatch_requires_same_run_and_workflow_identity(self):
        attempt = {
            "attemptId": "attempt-1",
            "caseId": "case-1",
            "caseRevision": "1" * 64,
            "treatmentId": "baseline",
            "repetition": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            path = evidence / "dispatch.json"
            repository_root = SCRIPT.parent.parent
            workflow = repository_root / "templates/distributed-campaign.yml"
            (evidence / "workflow.yml").write_bytes(
                workflow.read_bytes()
            )
            (evidence / "distributed_campaign.py").write_bytes(SCRIPT.read_bytes())
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "attempt": attempt,
                        "github": {
                            "GITHUB_RUN_ID": "10",
                            "GITHUB_SHA": "b" * 40,
                            "GITHUB_WORKFLOW_SHA": "a" * 40,
                            "GITHUB_SERVER_URL": "https://github.example.com",
                            "GITHUB_REPOSITORY": "example/evaluations",
                            "GITHUB_RUN_ATTEMPT": "1",
                        },
                    }
                )
            )
            with mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_RUN_ID": "10",
                    "GITHUB_SHA": "b" * 40,
                    "GITHUB_WORKFLOW_SHA": "a" * 40,
                    "GITHUB_SERVER_URL": "https://github.example.com",
                    "GITHUB_REPOSITORY": "example/evaluations",
                    "DISTRIBUTED_EVAL_WORKFLOW_PATH": str(workflow),
                },
                clear=True,
            ):
                matrix.validate_stage_dispatch(path, attempt)
            with mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_RUN_ID": "11",
                    "GITHUB_SHA": "b" * 40,
                    "GITHUB_WORKFLOW_SHA": "a" * 40,
                    "GITHUB_SERVER_URL": "https://github.example.com",
                    "GITHUB_REPOSITORY": "example/evaluations",
                    "DISTRIBUTED_EVAL_WORKFLOW_PATH": str(workflow),
                },
                clear=True,
            ), self.assertRaisesRegex(ValueError, "another workflow run"):
                matrix.validate_stage_dispatch(path, attempt)


if __name__ == "__main__":
    unittest.main()
