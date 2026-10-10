#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import signal
import socket
import threading
import tempfile
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from dashboard_cli import (
    ensure_dashboard,
    open_dashboard,
    service_status,
    stop_service,
)
from dashboard_projection import campaign_projection
from dashboard_server import DashboardHTTPServer
from dashboard_state import (
    campaign_registration,
    create_campaign,
    validate_campaign_id,
)
import evaluation_history
from skill_eval import add_case, init_corpus, successful_view_path
import test_measurement


class DashboardHiddenBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"
        self.corpus = self.root / "corpus"
        init_corpus(self.corpus)
        add_case(
            self.corpus,
            "example-case",
            "example-skill",
            ["candidate"],
        )
        self.hidden_marker = "HIDDEN-DASHBOARD-MARKER"
        case = self.corpus / "cases" / "example-case"
        (case / "criteria.md").write_text(self.hidden_marker, encoding="utf-8")
        (case / "judge-reference" / "gold.md").write_text(
            self.hidden_marker,
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_projection_exposes_only_typed_case_and_history_fields(self):
        registration = create_campaign(self.state_root, self.corpus)
        projection = campaign_projection(self.state_root, registration["campaign_id"])

        encoded = json.dumps(projection, sort_keys=True)
        self.assertNotIn(self.hidden_marker, encoded)
        self.assertEqual(projection["campaign"]["campaign_id"], registration["campaign_id"])
        self.assertEqual(
            projection["cases"],
            [{
                "case_id": "example-case",
                "case_type": "prose",
                "target_skill": "example-skill",
                "status": "not_run",
                "outcomes": None,
                "source": {
                    "authority": "immutable-artifact",
                    "id": "cases/example-case/case.json",
                },
            }],
        )
        self.assertEqual(projection["attempts"], [])
        self.assertEqual(projection["populations"], [])
        self.assertEqual(projection["availability"]["live_sessions"], "unavailable")

    def test_campaign_identifier_and_registration_paths_fail_closed(self):
        for value in ("../escape", "UPPER", "", "a/b", "." * 64):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_campaign_id(value)

        registration = create_campaign(self.state_root, self.corpus)
        path = self.state_root / "campaigns" / f"{registration['campaign_id']}.json"
        path.unlink()
        path.symlink_to(self.corpus / "corpus.json")
        with self.assertRaises(ValueError):
            campaign_registration(self.state_root, registration["campaign_id"])

    def test_campaign_identity_is_create_once(self):
        first = create_campaign(self.state_root, self.corpus)
        second = create_campaign(self.state_root, self.corpus)
        self.assertEqual(second, first)

        other = self.root / "other"
        init_corpus(other)
        local = self.corpus / ".skill-evaluation-ui" / "campaign.json"
        value = json.loads(local.read_text(encoding="utf-8"))
        value["corpus_root"] = str(other)
        local.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            create_campaign(self.state_root, self.corpus)

    def test_concurrent_campaign_creation_joins_published_identity(self):
        barrier = threading.Barrier(2)
        calls = 0
        calls_lock = threading.Lock()
        from dashboard_state import corpus_identity

        def synchronized_identity(*args):
            nonlocal calls
            with calls_lock:
                calls += 1
                synchronize = calls <= 2
            if synchronize:
                barrier.wait(timeout=2)
            return corpus_identity(*args)

        with mock.patch(
            "dashboard_state.corpus_identity",
            side_effect=synchronized_identity,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda _: create_campaign(self.state_root, self.corpus),
                        range(2),
                    )
                )

        self.assertEqual(results[0], results[1])
        self.assertEqual(
            campaign_registration(
                self.state_root,
                results[0]["campaign_id"],
            ),
            results[0],
        )


class DashboardServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"
        self.corpus = self.root / "corpus"
        init_corpus(self.corpus)
        add_case(self.corpus, "example-case", "example-skill", ["candidate"])
        case = self.corpus / "cases" / "example-case"
        (case / "criteria.md").write_text("SERVER-HIDDEN-MARKER", encoding="utf-8")
        self.registration = create_campaign(self.state_root, self.corpus)
        self.generation = "a" * 32
        self.secret = "root-secret-for-tests-with-enough-entropy"
        self.server = DashboardHTTPServer(
            ("127.0.0.1", 0),
            self.state_root,
            self.generation,
            self.secret,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.temp.cleanup()

    def request(self, path, *, authorization=None, method="GET", payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers, error.read()

    def mint(self):
        status, _, body = self.request(
            "/_control/open",
            authorization=f"Root {self.secret}",
            method="POST",
            payload={"campaign_id": self.registration["campaign_id"]},
        )
        self.assertEqual(status, 200)
        return json.loads(body)["capability"]

    def test_control_and_browser_authority_are_separate(self):
        status, _, body = self.request("/_control/health")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body), {"error": "root_auth_required"})

        status, _, body = self.request(
            "/_control/health",
            authorization=f"Root {self.secret}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["generation"], self.generation)

        capability = self.mint()
        campaign_path = f"/api/campaign/{self.registration['campaign_id']}"
        status, _, body = self.request(
            campaign_path,
            authorization=f"Root {self.secret}",
        )
        self.assertEqual(status, 401)
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", body)

        status, _, body = self.request(
            campaign_path,
            authorization=f"Bearer {capability}",
        )
        self.assertEqual(status, 200)
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", body)
        self.assertEqual(
            json.loads(body)["campaign"]["campaign_id"],
            self.registration["campaign_id"],
        )

        status, _, _ = self.request(
            "/api/index",
            authorization=f"Bearer {capability}",
        )
        self.assertEqual(status, 403)

    def test_stale_generation_and_untyped_paths_return_no_data(self):
        status, _, body = self.request(
            f"/api/campaign/{self.registration['campaign_id']}",
            authorization=f"Bearer {'b' * 32}.old",
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body), {"error": "generation_replaced"})

        for path in (
            "/api/campaign/../root-secret",
            "/api/campaign/%2e%2e/root-secret",
            "/api/campaign/not-an-id",
            "/api/index?path=/tmp",
            "/_control/stop",
        ):
            with self.subTest(path=path):
                status, _, body = self.request(
                    path,
                    authorization=f"Root {self.secret}",
                )
                self.assertGreaterEqual(status, 400)
                self.assertNotIn(b"SERVER-HIDDEN-MARKER", body)

    def test_static_shell_contains_no_evaluation_data_and_sets_policy(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", body)
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])


class DashboardLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"
        self.corpus = self.root / "corpus"
        init_corpus(self.corpus)
        add_case(self.corpus, "example-case", "example-skill", ["candidate"])

    def tearDown(self):
        try:
            stop_service(self.state_root)
        except (OSError, ValueError):
            pass
        self.temp.cleanup()

    def test_ensure_open_status_and_stop_without_printing_capability(self):
        first = ensure_dashboard(self.corpus, self.state_root)
        second = ensure_dashboard(self.corpus, self.state_root)
        self.assertTrue(first["service_started"])
        self.assertFalse(second["service_started"])
        self.assertEqual(first["campaign_id"], second["campaign_id"])
        self.assertEqual(service_status(self.state_root)["status"], "running")

        opened_urls = []
        opened = open_dashboard(
            self.corpus,
            self.state_root,
            browser_open=lambda url: opened_urls.append(url) or True,
        )
        self.assertTrue(opened["opened"])
        self.assertNotIn("#cap=", json.dumps(opened))
        self.assertEqual(len(opened_urls), 1)
        self.assertIn("#cap=", opened_urls[0])

        stopped = stop_service(self.state_root)
        self.assertTrue(stopped["stopped"])
        self.assertEqual(service_status(self.state_root)["status"], "stopped")
        self.assertFalse((self.state_root / "root-secret").exists())

    def test_dashboard_state_view_violation_rotates_generation(self):
        with mock.patch.dict(
            os.environ,
            {"SKILL_EVAL_DASHBOARD_STATE_ROOT": str(self.state_root)},
        ):
            ensure_dashboard(self.corpus, self.state_root)
            original = service_status(self.state_root)["service"]["generation"]
            secret = self.state_root / "root-secret"
            with self.assertRaisesRegex(
                ValueError,
                "view escaped evaluation workdir",
            ):
                successful_view_path(
                    (str(secret), str(secret), False),
                    self.corpus,
                    "prose",
                )
            self.assertEqual(service_status(self.state_root)["status"], "stopped")
            ensure_dashboard(self.corpus, self.state_root)
            replacement = service_status(self.state_root)["service"]["generation"]
            self.assertNotEqual(replacement, original)

    def test_crash_replacement_reuses_port_and_refuses_old_capability(self):
        ensure_dashboard(self.corpus, self.state_root)
        original = service_status(self.state_root)["service"]
        secret = (self.state_root / "root-secret").read_text().strip()
        from dashboard_cli import control_request, STARTED_PROCESSES
        opened = control_request(
            original,
            secret,
            "/_control/open",
            method="POST",
            payload={"campaign_id": None},
        )
        os.kill(original["pid"], signal.SIGTERM)
        STARTED_PROCESSES.pop(original["pid"]).wait(timeout=5)

        ensure_dashboard(self.corpus, self.state_root)
        replacement = service_status(self.state_root)["service"]
        self.assertEqual(replacement["port"], original["port"])
        request = urllib.request.Request(
            f"http://127.0.0.1:{replacement['port']}/api/index",
            headers={"Authorization": f"Bearer {opened['capability']}"},
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=2)
        with context.exception as error:
            self.assertEqual(error.code, 401)
            self.assertEqual(
                json.load(error),
                {"error": "generation_replaced"},
            )

    def test_replacement_does_not_displace_unrelated_port_owner(self):
        ensure_dashboard(self.corpus, self.state_root)
        original = service_status(self.state_root)["service"]
        from dashboard_cli import STARTED_PROCESSES
        os.kill(original["pid"], signal.SIGTERM)
        STARTED_PROCESSES.pop(original["pid"]).wait(timeout=5)
        with socket.socket() as owner:
            owner.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            owner.bind(("0.0.0.0", original["port"]))
            owner.listen()
            ensure_dashboard(self.corpus, self.state_root)
        replacement = service_status(self.state_root)["service"]
        self.assertNotEqual(replacement["port"], original["port"])


class DashboardHistoryParityTests(unittest.TestCase):
    def setUp(self):
        self.history_fixture = test_measurement.HistoryTests(methodName="runTest")
        self.history_fixture.setUp()
        self.root = self.history_fixture.root
        self.state_root = self.root / "dashboard-state"

    def tearDown(self):
        self.history_fixture.tearDown()

    def test_projection_preserves_history_outcomes_coverage_and_cost_units(self):
        self.history_fixture.run_fixture("pass", "PASS", 2)
        self.history_fixture.run_fixture("fail", "FAIL", 3)
        self.history_fixture.run_fixture("invalid", "INVALID", 1, complete=False)
        self.history_fixture.run_fixture("legacy", "FAIL", old=True)
        registration = create_campaign(self.state_root, self.root)

        raw = evaluation_history.history(self.root)
        projected = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )

        self.assertEqual(
            [item["correctness"] for item in projected["attempts"]],
            [item["correctness"] for item in raw["attempts"]],
        )
        self.assertEqual(
            projected["populations"][0]["pass_at_1"],
            raw["populations"][0]["pass_at_1"],
        )
        self.assertEqual(
            projected["populations"][0]["execution_coverage"],
            raw["populations"][0]["execution_coverage"],
        )
        for field in (
            "total_spend",
            "invalid_spend",
            "unsuccessful_spend",
            "retry_spend",
        ):
            self.assertEqual(
                projected["populations"][0][field],
                raw["populations"][0][field],
            )
        self.assertIsNone(
            projected["populations"][0]["total_spend"]["credits"]
        )
        self.assertEqual(
            projected["populations"][0]["total_spend"][
                "observed_premium_requests"
            ],
            raw["populations"][0]["total_spend"][
                "observed_premium_requests"
            ],
        )
        encoded = json.dumps(projected)
        self.assertNotIn("session_id", encoded)
        self.assertNotIn("observations", encoded)

    def test_projection_propagates_malformed_history(self):
        path = self.history_fixture.run_fixture("broken", "PASS", 1)
        execution = json.loads(
            (path / "execution-result.json").read_text(encoding="utf-8")
        )
        execution["execution_status"] = "SUCCESS"
        (path / "execution-result.json").write_text(
            json.dumps(execution),
            encoding="utf-8",
        )
        registration = create_campaign(self.state_root, self.root)
        with self.assertRaisesRegex(ValueError, "invalid execution status"):
            campaign_projection(self.state_root, registration["campaign_id"])


if __name__ == "__main__":
    unittest.main()
