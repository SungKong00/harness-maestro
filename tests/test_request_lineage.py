from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests.support import apply_fresh_init

from maestro.errors import MaestroError
from maestro.observations import (
    start_child_run_observation,
    start_desktop_request_observation,
    start_run_observation,
)
from maestro.project import checkout_id
from maestro.request_lineage import (
    REQUEST_ALIAS_PATH,
    load_request_alias_bindings,
    write_legacy_request_alias,
)
from maestro.util import read_json


class RequestLineageContractTests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        apply_fresh_init(repo)
        return repo

    def test_root_child_and_retry_inherit_one_immutable_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            root = start_run_observation(
                repo,
                run_id="root-run",
                task_label="하나의 사용자 요청",
                request_key="thread-1:turn-1",
            )
            child = start_child_run_observation(
                repo,
                run_id="verifier-run",
                task_label="분리 검증",
                parent_observation_id=root["observation_id"],
                parent_run_id="root-run",
                relation="child",
            )
            retry = start_child_run_observation(
                repo,
                run_id="retry-run",
                task_label="수정 재시도",
                parent_observation_id=child["observation_id"],
                parent_run_id="verifier-run",
                relation="retry",
            )

            root_lineage = root["request_lineage"]
            child_lineage = child["request_lineage"]
            retry_lineage = retry["request_lineage"]
            self.assertEqual(
                root_lineage["root_request_id"],
                child_lineage["root_request_id"],
            )
            self.assertEqual(
                root_lineage["root_request_id"],
                retry_lineage["root_request_id"],
            )
            self.assertEqual("root-run", child_lineage["root_run_id"])
            self.assertEqual("root-run", retry_lineage["root_run_id"])
            self.assertEqual("child", child_lineage["relation"])
            self.assertEqual("retry", retry_lineage["relation"])
            self.assertEqual(
                child["observation_id"],
                retry_lineage["parent_observation_id"],
            )

            repeated = start_run_observation(
                repo,
                run_id="root-run",
                task_label="하나의 사용자 요청",
                request_key="thread-1:turn-1",
            )
            self.assertEqual("already_started", repeated["status"])
            self.assertFalse(repeated["writes_performed"])

    def test_conflicting_roots_and_run_replay_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            with self.assertRaises(MaestroError) as missing_intake:
                start_run_observation(
                    repo,
                    run_id="implicit-root",
                    task_label="요청 식별자 없는 시작",
                )
            self.assertEqual(
                "REQUEST_LINEAGE_UNAVAILABLE",
                missing_intake.exception.code,
            )

            start_run_observation(
                repo,
                run_id="root-run",
                task_label="원 요청",
                request_key="request-key",
            )

            with self.assertRaises(MaestroError) as duplicate_root:
                start_run_observation(
                    repo,
                    run_id="second-root",
                    task_label="잘못 분리된 요청",
                    request_key="request-key",
                )
            self.assertEqual(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                duplicate_root.exception.code,
            )

            with self.assertRaises(MaestroError) as conflicting_replay:
                start_run_observation(
                    repo,
                    run_id="root-run",
                    task_label="원 요청",
                    request_key="different-request-key",
                )
            self.assertEqual(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                conflicting_replay.exception.code,
            )

    def test_desktop_identity_exists_before_optional_host_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            started = start_desktop_request_observation(
                repo,
                run_id="desktop-root",
                task_label="Desktop 요청",
                thread_id="thread-1",
                turn_id="turn-1",
                requested_model="gpt-5.6-sol",
            )
            observation = read_json(repo / started["observation_path"])

            self.assertEqual(
                started["request_lineage"],
                observation["request_lineage"],
            )
            self.assertEqual(
                "desktop_thread_turn",
                observation["request_lineage"]["identity_source"],
            )
            self.assertEqual("root", observation["request_lineage"]["relation"])

            with self.assertRaises(MaestroError) as duplicate:
                start_desktop_request_observation(
                    repo,
                    run_id="desktop-second-root",
                    task_label="잘못 분리된 Desktop 요청",
                    thread_id="thread-1",
                    turn_id="turn-1",
                    requested_model="gpt-5.6-sol",
                )
            self.assertEqual(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                duplicate.exception.code,
            )

    def test_legacy_alias_is_content_addressed_and_never_rewrites_events(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            project = read_json(repo / ".maestro/project.json")
            current_checkout = checkout_id(repo)
            events = [
                {
                    "event_id": f"event-{name}",
                    "project_id": project["project_id"],
                    "checkout_id": current_checkout,
                    "run_id": f"run-{name}",
                    "payload": {"name": name},
                }
                for name in ("root", "child", "retry", "other")
            ]
            raw_event_path = repo / ".maestro/state/events/legacy.jsonl"
            raw_event_path.parent.mkdir(parents=True, exist_ok=True)
            raw_event_path.write_text(
                "\n".join(
                    json.dumps(event, sort_keys=True)
                    for event in events
                )
                + "\n",
                encoding="utf-8",
            )
            before = raw_event_path.read_bytes()

            linked = write_legacy_request_alias(
                repo,
                events=events,
                root_run_id="run-root",
                member_run_ids=[
                    "run-root",
                    "run-child",
                    "run-retry",
                ],
                retry_run_ids=["run-retry"],
            )
            self.assertEqual("linked", linked["status"])
            self.assertEqual(before, raw_event_path.read_bytes())
            self.assertTrue((repo / REQUEST_ALIAS_PATH).is_file())

            bindings = load_request_alias_bindings(repo, events)
            self.assertEqual("root", bindings["run-root"]["relation"])
            self.assertEqual("child", bindings["run-child"]["relation"])
            self.assertEqual("retry", bindings["run-retry"]["relation"])
            self.assertEqual(
                bindings["run-root"]["root_request_id"],
                bindings["run-retry"]["root_request_id"],
            )
            repeated = write_legacy_request_alias(
                repo,
                events=events,
                root_run_id="run-root",
                member_run_ids=[
                    "run-root",
                    "run-child",
                    "run-retry",
                ],
                retry_run_ids=["run-retry"],
            )
            self.assertEqual("already_linked", repeated["status"])
            self.assertFalse(repeated["writes_performed"])

            tampered = copy.deepcopy(events)
            tampered[1]["payload"]["name"] = "changed"
            with self.assertRaises(MaestroError) as stale:
                load_request_alias_bindings(repo, tampered)
            self.assertEqual(
                "REQUEST_LINEAGE_ALIAS_STALE",
                stale.exception.code,
            )

            with self.assertRaises(MaestroError) as duplicate_owner:
                write_legacy_request_alias(
                    repo,
                    events=events,
                    root_run_id="run-other",
                    member_run_ids=["run-other", "run-child"],
                )
            self.assertEqual(
                "REQUEST_LINEAGE_ALIAS_CONFLICT",
                duplicate_owner.exception.code,
            )

            alias_path = repo / REQUEST_ALIAS_PATH
            original_alias = read_json(alias_path)
            forged_root = copy.deepcopy(original_alias)
            forged_root["groups"][0]["root_request_id"] = (
                "request-00000000000000000000"
            )
            alias_path.write_text(
                json.dumps(forged_root, sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaises(MaestroError) as forged:
                load_request_alias_bindings(repo, events)
            self.assertEqual(
                "REQUEST_LINEAGE_ALIAS_INVALID",
                forged.exception.code,
            )

            cyclic = copy.deepcopy(original_alias)
            group = cyclic["groups"][0]
            child = next(
                member
                for member in group["members"]
                if member["run_id"] == "run-child"
            )
            retry = next(
                member
                for member in group["members"]
                if member["run_id"] == "run-retry"
            )
            child["parent_run_id"] = "run-retry"
            retry["parent_run_id"] = "run-child"
            alias_path.write_text(
                json.dumps(cyclic, sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaises(MaestroError) as cycle:
                load_request_alias_bindings(repo, events)
            self.assertEqual(
                "REQUEST_LINEAGE_ALIAS_INVALID",
                cycle.exception.code,
            )


if __name__ == "__main__":
    unittest.main()
