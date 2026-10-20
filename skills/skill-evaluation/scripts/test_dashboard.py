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
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from dashboard_cli import (
    ensure_dashboard,
    lineage_snapshot_dashboard,
    open_dashboard,
    register_dashboard,
    service_status,
    stop_service,
    task_progress_dashboard,
)
from dashboard_projection import (
    campaign_index_projection,
    campaign_projection,
    session_projection,
    terminal_run,
)
from dashboard_server import DashboardHTTPServer
from dashboard_state import (
    capture_skill_snapshot,
    campaign_registration,
    create_campaign,
    enable_live_state,
    emit_event,
    emit_lineage_event,
    emit_task_progress_event,
    event_records,
    extension_records,
    read_skill_snapshot,
    read_session,
    register_session,
    session_event,
    update_session,
    validate_campaign_id,
)
import evaluation_history
from skill_eval import (
    add_case,
    digest,
    directory_identity,
    freeze_case,
    frozen_case_path,
    init_corpus,
    json_fingerprint,
    successful_view_path,
)
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

    def test_campaign_target_skills_grow_after_initial_registration(self):
        empty = self.root / "empty-corpus"
        init_corpus(empty)
        first = create_campaign(self.state_root, empty)
        self.assertEqual(first["target_skills"], [])

        add_case(empty, "later-case", "later-skill", ["candidate"])
        second = create_campaign(self.state_root, empty)
        self.assertEqual(second["campaign_id"], first["campaign_id"])
        self.assertEqual(second["target_skills"], ["later-skill"])
        self.assertEqual(
            campaign_registration(self.state_root, first["campaign_id"]),
            second,
        )

    def test_live_contract_is_unavailable_until_a_writer_registers(self):
        registration = create_campaign(self.state_root, self.corpus)
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(projection["availability"]["live_sessions"], "unavailable")
        self.assertEqual(projection["sessions"], [])

        session_id = str(uuid.uuid4())
        register_session(self.state_root, self.corpus, session_id)
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(projection["availability"]["live_sessions"], "available")
        self.assertEqual(projection["sessions"][0]["session_id"], session_id)

    def test_global_live_availability_is_unavailable_for_legacy_only_corpora(self):
        create_campaign(self.state_root, self.corpus)
        projection = campaign_index_projection(self.state_root)
        self.assertEqual(
            projection["availability"]["live_sessions"],
            "unavailable",
        )

    def test_session_events_serialize_and_duplicate_events_conflict(self):
        registration = create_campaign(self.state_root, self.corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            self.corpus,
            session_id,
        )
        case_revision = "a" * 64

        def publish(index):
            return session_event(
                self.corpus,
                session_id,
                session["writer_generation"],
                event_type="assignment_started",
                case_id="example-case",
                case_revision=case_revision,
                skill_identity=None,
                summary=f"working {index}",
                event_id=f"{index:032x}",
                emitted_at=f"2026-01-01T00:00:{index:02d}+00:00",
                recorded_at=f"2026-01-01T00:00:{index:02d}+00:00",
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            published = list(pool.map(publish, range(1, 17)))
        events, conflicts = event_records(self.corpus)
        self.assertEqual(len(events), 16)
        self.assertEqual(conflicts, [])
        self.assertIn(
            read_session(self.corpus, session_id)["last_event_id"],
            {item["event_id"] for item in published},
        )

        writer = {
            "kind": "evaluator",
            "id": "b" * 32,
            "generation": "c" * 32,
        }
        kwargs = {
            "campaign_id": registration["campaign_id"],
            "writer": writer,
            "event_type": "attempt_planned",
            "case_id": "example-case",
            "case_revision": case_revision,
            "event_id": "d" * 32,
            "emitted_at": "2026-01-01T00:01:00+00:00",
            "recorded_at": "2026-01-01T00:01:00+00:00",
        }
        payload = {
            "model": "gpt-example",
            "effort": "high",
            "arm": "skill",
            "treatment_identity": "treatment",
            "suite_id": None,
        }
        first = emit_event(self.corpus, payload=payload, **kwargs)
        self.assertEqual(emit_event(self.corpus, payload=payload, **kwargs), first)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            emit_event(
                self.corpus,
                payload={**payload, "model": "gpt-other"},
                **kwargs,
            )
        _, conflicts = event_records(self.corpus)
        self.assertEqual(conflicts[0]["event_id"], "d" * 32)

    def test_event_publication_is_atomic_and_retries_same_id(self):
        registration = create_campaign(self.state_root, self.corpus)
        enable_live_state(self.corpus)
        writer = {
            "kind": "evaluator",
            "id": "1" * 32,
            "generation": "2" * 32,
        }
        kwargs = {
            "campaign_id": registration["campaign_id"],
            "writer": writer,
            "event_type": "attempt_planned",
            "case_id": "example-case",
            "case_revision": "a" * 64,
            "event_id": "3" * 32,
            "payload": {
                "model": "gpt-example",
                "effort": "high",
                "arm": "skill",
                "treatment_identity": "treatment",
                "suite_id": None,
            },
        }
        with mock.patch(
            "dashboard_state.os.link",
            side_effect=OSError("interrupted publish"),
        ):
            with self.assertRaisesRegex(OSError, "interrupted publish"):
                emit_event(self.corpus, **kwargs)
        self.assertEqual(event_records(self.corpus), ([], []))

        published = emit_event(self.corpus, **kwargs)
        self.assertEqual(published["event_id"], "3" * 32)
        events, conflicts = event_records(self.corpus)
        self.assertEqual(len(events), 1)
        self.assertEqual(conflicts, [])

    def test_skill_snapshot_is_bounded_immutable_and_evaluator_compatible(self):
        registration = create_campaign(self.state_root, self.corpus)
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        (skill / "references" / "guide.md").write_text("guide\n", encoding="utf-8")
        (skill / "z-last.md").write_text("last\n", encoding="utf-8")
        (skill / ".DS_Store").write_bytes(b"ignored")
        (skill / "__pycache__").mkdir()
        (skill / "__pycache__" / "cache.pyc").write_bytes(b"ignored")
        sibling = plugin / "skills" / "other-skill"
        sibling.mkdir(parents=True)
        (sibling / "SKILL.md").write_text("secret sibling\n", encoding="utf-8")

        snapshot = capture_skill_snapshot(
            self.corpus,
            plugin,
            ["example-skill"],
        )
        self.assertEqual(snapshot["campaign_id"], registration["campaign_id"])
        self.assertEqual([item["name"] for item in snapshot["skills"]], ["example-skill"])
        files = snapshot["skills"][0]["files"]
        self.assertEqual(
            [item["path"] for item in files],
            ["SKILL.md", "references/guide.md", "z-last.md"],
        )
        plugin_identity = directory_identity(plugin)
        evaluator_files = [
            {
                "path": item["path"].removeprefix("skills/example-skill/"),
                "sha256": item["sha256"],
            }
            for item in plugin_identity["files"]
            if item["path"].startswith("skills/example-skill/")
        ]
        evaluator_files.sort(key=lambda item: item["path"])
        self.assertEqual(
            snapshot["skills"][0]["evaluator_skill_identity"],
            json_fingerprint({
                "name": "example-skill",
                "files": evaluator_files,
            }),
        )
        self.assertEqual(
            snapshot["skills"][0]["evaluator_skill_identity"],
            json_fingerprint({
                "name": "example-skill",
                "files": [
                    {"path": item["path"], "sha256": item["sha256"]}
                    for item in files
                ],
            }),
        )
        snapshot_root = (
            self.corpus
            / ".skill-evaluation-ui"
            / "snapshots"
            / snapshot["snapshot_id"]
        )
        self.assertFalse((snapshot_root / "files" / "other-skill").exists())

        (skill / "SKILL.md").write_text("# Mutated\n", encoding="utf-8")
        reread = read_skill_snapshot(self.corpus, snapshot["snapshot_id"])
        self.assertEqual(reread, snapshot)
        self.assertEqual(
            (snapshot_root / "files" / "example-skill" / "SKILL.md").read_text(
                encoding="utf-8"
            ),
            "# Example\n",
        )

    def test_skill_snapshot_refuses_symlinks_and_atomic_publish_failure(self):
        create_campaign(self.state_root, self.corpus)
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        (skill / "escape").symlink_to(self.root / "outside")
        with self.assertRaisesRegex(ValueError, "symlink"):
            capture_skill_snapshot(self.corpus, plugin, ["example-skill"])

        (skill / "escape").unlink()
        with mock.patch(
            "dashboard_state.os.rename",
            side_effect=OSError("interrupted snapshot publish"),
        ):
            with self.assertRaisesRegex(OSError, "interrupted snapshot publish"):
                capture_skill_snapshot(self.corpus, plugin, ["example-skill"])
        snapshots = self.corpus / ".skill-evaluation-ui" / "snapshots"
        self.assertEqual(list(snapshots.iterdir()), [])

        with mock.patch(
            "dashboard_state.validate_skill_snapshot",
            side_effect=ValueError("invalid manifest"),
        ), mock.patch("dashboard_state.os.rename") as rename:
            with self.assertRaisesRegex(ValueError, "invalid manifest"):
                capture_skill_snapshot(self.corpus, plugin, ["example-skill"])
        rename.assert_not_called()
        self.assertEqual(list(snapshots.iterdir()), [])

    def test_skill_snapshot_does_not_follow_file_replaced_during_capture(self):
        create_campaign(self.state_root, self.corpus)
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        payload = skill / "payload.txt"
        payload.write_text("bounded\n", encoding="utf-8")
        outside = self.root / "outside.txt"
        outside.write_text("must not be captured\n", encoding="utf-8")
        real_open = os.open
        replaced = False

        def replace_before_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if path == "payload.txt" and dir_fd is not None and not replaced:
                replaced = True
                payload.unlink()
                payload.symlink_to(outside)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch("dashboard_state.os.open", side_effect=replace_before_open):
            with self.assertRaises(OSError):
                capture_skill_snapshot(self.corpus, plugin, ["example-skill"])
        self.assertTrue(replaced)
        snapshots = self.corpus / ".skill-evaluation-ui" / "snapshots"
        self.assertTrue(
            not snapshots.exists() or list(snapshots.iterdir()) == []
        )

    def test_invalid_snapshot_projection_uses_path_safe_reason(self):
        registration = create_campaign(self.state_root, self.corpus)
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        snapshot = capture_skill_snapshot(
            self.corpus,
            plugin,
            ["example-skill"],
        )
        stored = (
            self.corpus
            / ".skill-evaluation-ui"
            / "snapshots"
            / snapshot["snapshot_id"]
            / "files"
            / "example-skill"
            / "SKILL.md"
        )
        stored.unlink()
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(
            projection["lineage"]["invalid"][0]["reason"],
            "snapshot_invalid",
        )
        serialized = json.dumps(projection)
        for path in (self.corpus, plugin, self.state_root, stored.parent):
            self.assertNotIn(str(path), serialized)

    def test_lineage_extension_reuses_writer_conflicts_and_old_readers_ignore_it(self):
        registration = create_campaign(self.state_root, self.corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            self.corpus,
            session_id,
        )
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        snapshot = capture_skill_snapshot(
            self.corpus,
            plugin,
            ["example-skill"],
        )
        writer = {
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        }
        kwargs = {
            "campaign_id": registration["campaign_id"],
            "writer": writer,
            "snapshot_id": snapshot["snapshot_id"],
            "roles": ["experimental"],
            "parents": [],
            "summary": "First bounded snapshot",
            "event_id": "9" * 32,
            "observed_at": "2026-01-01T00:00:00+00:00",
            "recorded_at": "2026-01-01T00:00:01+00:00",
        }
        first = emit_lineage_event(self.corpus, **kwargs)
        self.assertEqual(emit_lineage_event(self.corpus, **kwargs), first)
        self.assertEqual(event_records(self.corpus), ([], []))

        records, conflicts, invalid = extension_records(self.corpus)
        self.assertEqual([item["event_id"] for item in records], ["9" * 32])
        self.assertEqual(conflicts, [])
        self.assertEqual(invalid, [])

        with self.assertRaisesRegex(ValueError, "conflicts"):
            emit_lineage_event(
                self.corpus,
                **{**kwargs, "summary": "Conflicting declaration"},
            )
        records, conflicts, invalid = extension_records(self.corpus)
        self.assertEqual(len(records), 1)
        self.assertEqual(conflicts[0]["event_id"], "9" * 32)
        self.assertEqual(invalid, [])

        extension_root = next(
            (
                self.corpus
                / ".skill-evaluation-ui"
                / "events"
            ).iterdir()
        ) / "extensions" / "skill-lineage-v1"
        (extension_root / f"{'8' * 32}.json").write_text(
            '{"schema_version": 1, "broken": true}\n',
            encoding="utf-8",
        )
        records, conflicts, invalid = extension_records(self.corpus)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["reason"], "extension_event_invalid")
        leaked = extension_root / f"{'7' * 32}.json"
        leaked.symlink_to(self.root / "outside.json")
        _, _, invalid = extension_records(self.corpus)
        self.assertEqual(
            {item["reason"] for item in invalid},
            {"extension_event_invalid"},
        )
        self.assertNotIn(str(self.root), json.dumps(invalid))
        leaked.unlink()
        self.assertEqual(event_records(self.corpus), ([], []))

        progress = emit_task_progress_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=snapshot["snapshot_id"],
            case_id="example-case",
            case_revision="a" * 64,
            frontier="behavioral",
            classification="skill_defect",
            movement="Strict improvement",
            summary="Executable checks pass; behavior remains incomplete",
            uptake=[{
                "rule_id": "preserve-authority",
                "status": "OBSERVED",
                "summary": "The candidate retained immutable outcome authority",
            }],
            blocker="Behavioral judgment still fails",
            next_action="Refine the general instruction",
            sources=[{"kind": "attempt", "id": "attempt-1"}],
            event_id="7" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
            recorded_at="2026-01-01T00:02:01+00:00",
        )
        self.assertEqual(progress["event_type"], "task_progress_recorded")
        records, _, invalid = extension_records(self.corpus)
        self.assertEqual(
            [item["event_type"] for item in records],
            ["lineage_declared", "task_progress_recorded"],
        )
        self.assertEqual(len(invalid), 1)
        self.assertEqual(event_records(self.corpus), ([], []))

        with self.assertRaisesRegex(ValueError, "classification"):
            emit_task_progress_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer=writer,
                snapshot_id=snapshot["snapshot_id"],
                case_id="example-case",
                case_revision="a" * 64,
                frontier="behavioral",
                classification="invented",
                movement="Strict improvement",
                summary="Invalid classification",
            )

    def test_campaign_projects_lineage_diff_task_progress_and_attention(self):
        definition_path = (
            self.corpus / "cases" / "example-case" / "case.json"
        )
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition["behavioral_claim"] = "The skill preserves evaluator authority."
        definition["authority_kind"] = "synthetic"
        definition_path.write_text(
            json.dumps(definition, indent=2) + "\n",
            encoding="utf-8",
        )
        (
            self.corpus
            / "cases"
            / "example-case"
            / "evidence"
            / "candidate"
            / "input.md"
        ).write_text("candidate evidence\n", encoding="utf-8")
        freeze_case(self.corpus, "example-case", replace=False)
        registration = create_campaign(self.state_root, self.corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            self.corpus,
            session_id,
        )
        writer = {
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        }
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Original\n", encoding="utf-8")
        original = capture_skill_snapshot(
            self.corpus,
            plugin,
            ["example-skill"],
        )
        (skill / "SKILL.md").write_text("# Integrated\n", encoding="utf-8")
        integrated = capture_skill_snapshot(
            self.corpus,
            plugin,
            ["example-skill"],
        )
        emit_lineage_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=original["snapshot_id"],
            roles=["original", "published"],
            parents=[],
            summary="Published baseline",
            event_id="1" * 32,
            observed_at="2026-01-01T00:00:00+00:00",
            recorded_at="2026-01-01T00:00:01+00:00",
        )
        emit_lineage_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=integrated["snapshot_id"],
            roles=["integrated"],
            parents=[{
                "snapshot_id": original["snapshot_id"],
                "relation": "derived_from",
            }],
            summary="Integrated the general fix",
            event_id="2" * 32,
            observed_at="2026-01-01T00:01:00+00:00",
            recorded_at="2026-01-01T00:01:01+00:00",
        )
        case_revision = digest(
            frozen_case_path(self.corpus, "example-case")
            / "case-manifest.json"
        )
        emit_task_progress_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=integrated["snapshot_id"],
            comparison_snapshot_id=original["snapshot_id"],
            case_id="example-case",
            case_revision=case_revision,
            frontier="behavioral",
            classification="skill_defect",
            movement="Strict improvement",
            summary="The known defect moved to behavioral review",
            uptake=[{
                "rule_id": "preserve-authority",
                "status": "OBSERVED",
                "summary": "The candidate preserved immutable authority",
            }],
            blocker="One behavioral criterion still fails",
            next_action="Refine the general rule",
            sources=[{"kind": "review_receipt", "id": "review-1"}],
            event_id="3" * 32,
            observed_at="2026-01-01T00:02:00+00:00",
            recorded_at="2026-01-01T00:02:01+00:00",
        )

        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(projection["availability"]["lineage"], "available")
        self.assertEqual(
            projection["lineage"]["roles"]["integrated"]["snapshot_id"],
            integrated["snapshot_id"],
        )
        self.assertEqual(
            projection["lineage"]["roles"]["passing"]["status"],
            "unavailable",
        )
        comparison = projection["lineage"]["comparisons"][0]
        self.assertEqual(comparison["from_snapshot_id"], original["snapshot_id"])
        self.assertEqual(comparison["to_snapshot_id"], integrated["snapshot_id"])
        self.assertEqual(comparison["summary"]["modified_files"], 1)
        self.assertIn("-# Original", comparison["files"][0]["diff"])
        self.assertIn("+# Integrated", comparison["files"][0]["diff"])

        detail = projection["task_details"][0]
        self.assertEqual(detail["case_id"], "example-case")
        self.assertEqual(
            detail["associated_snapshot_id"],
            integrated["snapshot_id"],
        )
        self.assertEqual(detail["progress"]["frontier"], "behavioral")
        self.assertEqual(detail["progress"]["classification"], "skill_defect")
        self.assertEqual(detail["progress"]["movement"], "Strict improvement")
        self.assertEqual(detail["progress"]["status"], "available")
        self.assertEqual(
            projection["attention"][0]["kind"],
            "blocked",
        )
        self.assertNotIn(self.hidden_marker, json.dumps(projection))

    def test_lineage_cycles_and_equal_time_progress_conflicts_fail_visible(self):
        definition_path = (
            self.corpus / "cases" / "example-case" / "case.json"
        )
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition["behavioral_claim"] = "The skill preserves evaluator authority."
        definition["authority_kind"] = "synthetic"
        definition_path.write_text(
            json.dumps(definition, indent=2) + "\n",
            encoding="utf-8",
        )
        (
            self.corpus
            / "cases"
            / "example-case"
            / "evidence"
            / "candidate"
            / "input.md"
        ).write_text("candidate evidence\n", encoding="utf-8")
        freeze_case(self.corpus, "example-case", replace=False)
        registration = create_campaign(self.state_root, self.corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            self.corpus,
            session_id,
        )
        writer = {
            "kind": "session",
            "id": session_id,
            "generation": session["writer_generation"],
        }
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# One\n", encoding="utf-8")
        first = capture_skill_snapshot(self.corpus, plugin, ["example-skill"])
        (skill / "SKILL.md").write_text("# Two\n", encoding="utf-8")
        second = capture_skill_snapshot(self.corpus, plugin, ["example-skill"])
        emit_lineage_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=first["snapshot_id"],
            roles=["integrated"],
            parents=[{
                "snapshot_id": second["snapshot_id"],
                "relation": "derived_from",
            }],
            summary="First side of cycle",
            event_id="4" * 32,
        )
        emit_lineage_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=second["snapshot_id"],
            roles=["integrated"],
            parents=[{
                "snapshot_id": first["snapshot_id"],
                "relation": "derived_from",
            }],
            summary="Second side of cycle",
            event_id="5" * 32,
        )
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(
            projection["lineage"]["roles"]["integrated"]["status"],
            "unavailable",
        )
        self.assertEqual(
            sum(
                item["reason"] == "lineage declaration participates in a cycle"
                for item in projection["lineage"]["invalid"]
            ),
            2,
        )

        # Publish a valid tip, then two incompatible observations at one instant.
        emit_lineage_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=second["snapshot_id"],
            roles=["integrated"],
            parents=[],
            summary="Recovered tip",
            event_id="6" * 32,
            observed_at="2026-01-02T00:00:00+00:00",
        )
        revision = digest(
            frozen_case_path(self.corpus, "example-case") / "case-manifest.json"
        )
        for event_id, movement, observed_at in (
            ("a" * 32, "Mixed", "2026-01-02T00:01:00+00:00"),
            ("b" * 32, "Regression", "2026-01-01T19:01:00-05:00"),
        ):
            emit_task_progress_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer=writer,
                snapshot_id=second["snapshot_id"],
                case_id="example-case",
                case_revision=revision,
                frontier="behavioral",
                classification="skill_defect",
                movement=movement,
                summary=f"Observation {movement}",
                event_id=event_id,
                observed_at=observed_at,
            )
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(
            projection["task_details"][0]["progress"]["status"],
            "conflicted",
        )
        self.assertEqual(projection["attention"][0]["kind"], "conflicted")

        emit_task_progress_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            snapshot_id=second["snapshot_id"],
            case_id="example-case",
            case_revision=revision,
            frontier="release",
            classification="skill_defect",
            movement="Strict improvement",
            summary="A later absolute instant resolves the conflict",
            event_id="c" * 32,
            observed_at="2026-01-01T20:00:00-05:00",
        )
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(
            projection["task_details"][0]["progress"]["status"],
            "available",
        )
        self.assertEqual(
            projection["task_details"][0]["progress"]["movement"],
            "Strict improvement",
        )

    def test_lineage_and_progress_cli_producers_bind_registered_session(self):
        definition_path = (
            self.corpus / "cases" / "example-case" / "case.json"
        )
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition["behavioral_claim"] = "The skill preserves evaluator authority."
        definition["authority_kind"] = "synthetic"
        definition_path.write_text(
            json.dumps(definition, indent=2) + "\n",
            encoding="utf-8",
        )
        (
            self.corpus
            / "cases"
            / "example-case"
            / "evidence"
            / "candidate"
            / "input.md"
        ).write_text("candidate evidence\n", encoding="utf-8")
        freeze_case(self.corpus, "example-case", replace=False)
        session_id = str(uuid.uuid4())
        register_session(self.state_root, self.corpus, session_id)
        plugin = self.root / "plugin"
        skill = plugin / "skills" / "example-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Integrated\n", encoding="utf-8")

        lineage = lineage_snapshot_dashboard(
            self.corpus,
            session_id,
            plugin,
            ["example-skill"],
            ["integrated"],
            "Integrated candidate",
            root=self.state_root,
        )
        progress = task_progress_dashboard(
            self.corpus,
            session_id,
            "example-case",
            lineage["snapshot_id"],
            "behavioral",
            "skill_defect",
            "Strict improvement",
            "Behavior moved later",
            blocker="One criterion remains",
            root=self.state_root,
        )
        self.assertEqual(progress["snapshot_id"], lineage["snapshot_id"])
        projection = campaign_projection(
            self.state_root,
            lineage["campaign_id"],
        )
        self.assertEqual(
            projection["task_details"][0]["progress"]["status"],
            "available",
        )

    def test_event_writer_rejects_symlinked_events_ancestor(self):
        registration = create_campaign(self.state_root, self.corpus)
        external = self.root / "external-events"
        external.mkdir()
        events = self.corpus / ".skill-evaluation-ui" / "events"
        events.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "events path is invalid"):
            emit_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer={
                    "kind": "evaluator",
                    "id": "1" * 32,
                    "generation": "2" * 32,
                },
                event_type="attempt_planned",
                case_id="example-case",
                case_revision="a" * 64,
                payload={
                    "model": "gpt-example",
                    "effort": "high",
                    "arm": "skill",
                    "treatment_identity": "treatment",
                    "suite_id": None,
                },
            )
        self.assertEqual(list(external.iterdir()), [])

    def test_plan_ids_are_scoped_to_writer_identity(self):
        registration = create_campaign(self.state_root, self.corpus)
        shared_id = "4" * 32
        for index in range(2):
            writer = {
                "kind": "evaluator",
                "id": f"{index + 5:032x}",
                "generation": f"{index + 7:032x}",
            }
            planned = emit_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer=writer,
                event_type="attempt_planned",
                event_id=shared_id,
                case_id="example-case",
                case_revision="a" * 64,
                payload={
                    "model": "gpt-example",
                    "effort": "high",
                    "arm": "skill",
                    "treatment_identity": f"treatment-{index}",
                    "suite_id": None,
                },
            )
            emit_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer=writer,
                event_type="attempt_started",
                case_id="example-case",
                case_revision="a" * 64,
                payload={
                    "planned_event_id": planned["event_id"],
                    "run_path": f"runs/live-{index}/example-case",
                },
            )
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(len(projection["live_attempts"]), 2)

    def test_stale_blocked_and_reconciled_attempt_views(self):
        registration = create_campaign(self.state_root, self.corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            self.corpus,
            session_id,
            now="2020-01-01T00:00:00+00:00",
        )
        update_session(
            self.corpus,
            session_id,
            session["writer_generation"],
            state="blocked",
            heartbeat_at="2020-01-01T00:00:00+00:00",
            summary="waiting for local resource",
        )
        writer = {
            "kind": "evaluator",
            "id": "e" * 32,
            "generation": "f" * 32,
        }
        planned = emit_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            event_type="attempt_planned",
            case_id="example-case",
            case_revision="a" * 64,
            payload={
                "model": "gpt-example",
                "effort": "high",
                "arm": "skill",
                "treatment_identity": "treatment",
                "suite_id": None,
            },
        )
        emit_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            event_type="attempt_started",
            case_id="example-case",
            case_revision="a" * 64,
            payload={
                "planned_event_id": planned["event_id"],
                "run_path": "runs/live/example-case",
            },
        )
        projection = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(projection["sessions"][0]["state"], "stale")
        self.assertEqual(projection["live_attempts"][0]["state"], "active")

        completed = projection["live_attempts"][0]
        from dashboard_projection import live_projection
        reconciled = live_projection(
            self.corpus,
            registration["campaign_id"],
            [{"source": {"id": completed["run_path"]}}],
        )
        self.assertEqual(reconciled["live_attempts"][0]["state"], "superseded")
        self.assertEqual(
            reconciled["live_attempts"][0]["authority"],
            "immutable-artifact",
        )

    def test_terminal_detection_waits_for_report_and_covers_admission_runs(self):
        partial = self.corpus / "runs" / "partial" / "example-case"
        partial.mkdir(parents=True)
        (partial / "attempt.json").write_text("{}")
        (partial / "judgment-claude.json").write_text("{}")
        self.assertFalse(
            terminal_run(self.corpus, "runs/partial/example-case")
        )
        (partial / "judge-claude-failure-receipt.json").write_text("{}")
        self.assertFalse(
            terminal_run(self.corpus, "runs/partial/example-case")
        )
        (partial / "REPORT.md").write_text("complete")
        self.assertTrue(
            terminal_run(self.corpus, "runs/partial/example-case")
        )

        failed = self.corpus / "runs" / "failed" / "example-case"
        failed.mkdir(parents=True)
        (failed / "attempt.json").write_text("{}")
        (failed / "attempt-failure-receipt.json").write_text("{}")
        self.assertTrue(
            terminal_run(self.corpus, "runs/failed/example-case")
        )

        admission = (
            self.corpus
            / "treatment-admission-runs"
            / "admitted"
            / "example-case"
        )
        admission.mkdir(parents=True)
        (admission / "execution-result.json").write_text("{}")
        self.assertFalse(
            terminal_run(
                self.corpus,
                "treatment-admission-runs/admitted/example-case",
            )
        )
        (admission / "REPORT.md").write_text("complete")
        self.assertTrue(
            terminal_run(
                self.corpus,
                "treatment-admission-runs/admitted/example-case",
            )
        )
        registration = create_campaign(self.state_root, self.corpus)
        writer = {
            "kind": "evaluator",
            "id": "c" * 32,
            "generation": "d" * 32,
        }
        planned = emit_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            event_type="attempt_planned",
            case_id="example-case",
            case_revision="a" * 64,
            payload={
                "model": "gpt-example",
                "effort": "high",
                "arm": "skill",
                "treatment_identity": "treatment",
                "suite_id": None,
            },
        )
        emit_event(
            self.corpus,
            campaign_id=registration["campaign_id"],
            writer=writer,
            event_type="attempt_started",
            case_id="example-case",
            case_revision="a" * 64,
            payload={
                "planned_event_id": planned["event_id"],
                "run_path": (
                    "treatment-admission-runs/admitted/example-case"
                ),
            },
        )
        from dashboard_projection import live_projection
        projection = live_projection(
            self.corpus,
            registration["campaign_id"],
            [],
        )
        self.assertEqual(
            projection["live_attempts"][0]["state"],
            "superseded",
        )

    def test_session_related_attempts_match_case_revision(self):
        registration = create_campaign(self.state_root, self.corpus)
        session_id = str(uuid.uuid4())
        session, _ = register_session(
            self.state_root,
            self.corpus,
            session_id,
        )
        update_session(
            self.corpus,
            session_id,
            session["writer_generation"],
            case_id="example-case",
            case_revision="a" * 64,
            summary="working exact revision",
        )
        for index, revision in enumerate(("a" * 64, "b" * 64)):
            writer = {
                "kind": "evaluator",
                "id": f"{index + 9:032x}",
                "generation": f"{index + 11:032x}",
            }
            planned = emit_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer=writer,
                event_type="attempt_planned",
                case_id="example-case",
                case_revision=revision,
                payload={
                    "model": "gpt-example",
                    "effort": "high",
                    "arm": "skill",
                    "treatment_identity": f"treatment-{index}",
                    "suite_id": None,
                },
            )
            emit_event(
                self.corpus,
                campaign_id=registration["campaign_id"],
                writer=writer,
                event_type="attempt_started",
                case_id="example-case",
                case_revision=revision,
                payload={
                    "planned_event_id": planned["event_id"],
                    "run_path": f"runs/revision-{index}/example-case",
                },
            )
        detail = session_projection(
            self.state_root,
            registration["campaign_id"],
            session_id,
        )
        self.assertEqual(len(detail["attempts"]), 1)
        self.assertEqual(detail["attempts"][0]["case_revision"], "a" * 64)


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

    def test_campaign_capability_reads_session_route_within_scope(self):
        session_id = str(uuid.uuid4())
        register_session(self.state_root, self.corpus, session_id)
        capability = self.mint()
        status, _, body = self.request(
            (
                f"/api/campaign/{self.registration['campaign_id']}"
                f"/session/{session_id}"
            ),
            authorization=f"Bearer {capability}",
        )
        self.assertEqual(status, 200)
        projection = json.loads(body)
        self.assertEqual(projection["session"]["session_id"], session_id)
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", body)

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

    def test_task_route_uses_static_shell_without_embedding_data(self):
        campaign_id = self.registration["campaign_id"]
        status, headers, body = self.request(
            f"/campaign/{campaign_id}/task/example-case"
        )
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", body)

    def test_static_assets_include_lineage_and_task_surfaces_without_data(self):
        status, _, javascript = self.request("/dashboard.js")
        self.assertEqual(status, 200)
        self.assertIn(b"Skill lineage", javascript)
        self.assertIn(b"Relevant skill change", javascript)
        self.assertIn(b"Needs attention", javascript)
        self.assertIn(b"Experiment attention", javascript)
        self.assertIn(b"Distributed activity", javascript)
        self.assertIn(b"observed as of", javascript)
        self.assertIn(b"non-atomic snapshot", javascript)
        self.assertIn(b"Experiment attempts", javascript)
        self.assertIn(b"Incompatible current workflow records", javascript)
        self.assertIn(b"Get a passing evaluator result for every task", javascript)
        self.assertIn(b"What is being tested", javascript)
        self.assertIn(b"Running now", javascript)
        self.assertIn(b"Nothing is running right now", javascript)
        self.assertIn(b"Live run status is not available", javascript)
        self.assertIn(b"REFRESH_INTERVAL_MS = 5000", javascript)
        self.assertIn(b'addEventListener("visibilitychange"', javascript)
        self.assertIn(b"session.last_event_id", javascript)
        self.assertIn(b'state = activityState === "active" ? "running"', javascript)
        self.assertIn(b"Related retries and treatments are not grouped", javascript)
        self.assertIn(b"Campaign data unavailable", javascript)
        self.assertIn(b"/task/", javascript)
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", javascript)

        status, _, stylesheet = self.request("/dashboard.css")
        self.assertEqual(status, 200)
        self.assertIn(b".lineage-strip", stylesheet)
        self.assertIn(b".diff-code", stylesheet)
        self.assertIn(b".experiment-summary-strip", stylesheet)
        self.assertIn(b".treatment-grid", stylesheet)
        self.assertIn(b".distributed-table", stylesheet)
        self.assertIn(b".campaign-brief", stylesheet)
        self.assertIn(b".task-list-simple", stylesheet)
        self.assertIn(b".run-card", stylesheet)
        self.assertNotIn(b"SERVER-HIDDEN-MARKER", stylesheet)


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

    def test_unassigned_session_registration_does_not_auto_open(self):
        session_id = str(uuid.uuid4())
        urls = []
        first = register_dashboard(
            self.corpus,
            session_id,
            self.state_root,
            browser_open=lambda url: urls.append(url) or True,
        )
        second = register_dashboard(
            self.corpus,
            session_id,
            self.state_root,
            browser_open=lambda url: urls.append(url) or True,
        )
        self.assertTrue(first["session_created"])
        self.assertFalse(first["opened"])
        self.assertFalse(second["session_created"])
        self.assertFalse(second["opened"])
        self.assertEqual(len(urls), 0)
        self.assertNotIn("#cap=", json.dumps(first))

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

    def test_custom_state_root_view_violation_rotates_without_environment(self):
        ensure_dashboard(self.corpus, self.state_root)
        original = service_status(self.state_root)["service"]["generation"]
        secret = self.state_root / "root-secret"
        with mock.patch.dict(
            os.environ,
            {"SKILL_EVAL_DASHBOARD_STATE_ROOT": str(self.root / "unused")},
        ):
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
        self.assertNotEqual(
            service_status(self.state_root)["service"]["generation"],
            original,
        )

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
        for path in (
            self.history_fixture.run_fixture("pass", "PASS", 2),
            self.history_fixture.run_fixture("fail", "FAIL", 3),
            self.history_fixture.run_fixture(
                "invalid",
                "INVALID",
                1,
                complete=False,
            ),
        ):
            (path / "REPORT.md").write_text("complete")
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
        (path / "REPORT.md").write_text("complete")
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

    def test_attempt_metadata_does_not_supersede_live_attempt(self):
        path = self.history_fixture.run_fixture("running", "PASS", 1)
        execution = json.loads(
            (path / "execution-result.json").read_text(encoding="utf-8")
        )
        for artifact in ("execution-result.json", "repository-result.json"):
            (path / artifact).unlink(missing_ok=True)
        for receipt in path.glob("*-receipt.json"):
            receipt.unlink()
        attempt = json.loads((path / "attempt.json").read_text(encoding="utf-8"))
        registration = create_campaign(self.state_root, self.root)
        writer = {
            "kind": "evaluator",
            "id": "e" * 32,
            "generation": "f" * 32,
        }
        planned = emit_event(
            self.root,
            campaign_id=registration["campaign_id"],
            writer=writer,
            event_type="attempt_planned",
            case_id=attempt["case_id"],
            case_revision="a" * 64,
            payload={
                "model": execution["model"],
                "effort": execution["effort"],
                "arm": execution["arm"],
                "treatment_identity": "test-treatment",
                "suite_id": None,
            },
        )
        emit_event(
            self.root,
            campaign_id=registration["campaign_id"],
            writer=writer,
            event_type="attempt_started",
            case_id=attempt["case_id"],
            case_revision="a" * 64,
            payload={
                "planned_event_id": planned["event_id"],
                "run_path": path.relative_to(self.root).as_posix(),
            },
        )

        projected = campaign_projection(
            self.state_root,
            registration["campaign_id"],
        )
        self.assertEqual(projected["attempts"], [])
        self.assertEqual(projected["populations"], [])
        self.assertEqual(projected["live_attempts"][0]["state"], "active")
        self.assertEqual(
            projected["live_attempts"][0]["authority"],
            "live-event",
        )


if __name__ == "__main__":
    unittest.main()
