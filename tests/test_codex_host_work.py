from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from maestro.codex_host import run_codex_host
from maestro.errors import MaestroError
from maestro.util import safe_target
from maestro.work import project_observed_work
from tests.test_codex_host import CodexHostTests, FAKE_APP_SERVER


COLLAB_EVENTS = r'''
        if mode in {"collab", "collab-incomplete"}:
            spawn = {
                "id": "spawn-1",
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "status": "inProgress",
                "senderThreadId": "thread-1",
                "receiverThreadIds": ["child-thread-1"],
                "model": "gpt-5.6-terra",
                "reasoningEffort": "medium",
                "prompt": "SECRET-DELEGATION-PROMPT",
                "agentsStates": {
                    "child-thread-1": {
                        "status": "running",
                        "message": "SECRET-CHILD-MESSAGE",
                    }
                },
            }
            started = {
                "jsonrpc": "2.0",
                "method": "item/started",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "startedAtMs": 1785217057000,
                    "item": spawn,
                },
            }
            emit(started)
            emit(started)
            completed_spawn = dict(spawn)
            completed_spawn["status"] = "completed"
            emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "completedAtMs": 1785217057500,
                        "item": completed_spawn,
                    },
                }
            )
            if mode == "collab":
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turnId": "turn-1",
                            "completedAtMs": 1785217058000,
                            "item": {
                                "id": "wait-1",
                                "type": "collabAgentToolCall",
                                "tool": "wait",
                                "status": "completed",
                                "senderThreadId": "thread-1",
                                "receiverThreadIds": ["child-thread-1"],
                                "agentsStates": {
                                    "child-thread-1": {
                                        "status": "completed",
                                        "message": "SECRET-CHILD-RESULT",
                                    }
                                },
                            },
                        },
                    }
                )
'''


def collab_app_server() -> str:
    marker = '        if mode != "terminal-message":\n'
    if marker not in FAKE_APP_SERVER:
        raise AssertionError("fake App Server insertion point changed")
    return FAKE_APP_SERVER.replace(marker, COLLAB_EVENTS + marker, 1)


class CodexHostWorkTests(unittest.TestCase):
    def _project(self, root: Path) -> tuple[Path, Path, Path]:
        repo, prompt, server = CodexHostTests()._project(root)
        server.write_text(collab_app_server(), encoding="utf-8")
        return repo, prompt, server

    def test_owned_host_projects_delegation_cards_without_raw_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            result = run_codex_host(
                repo,
                run_id="collab-work",
                task_label="Codex 위임 수집",
                prompt_file=prompt,
                sandbox="read-only",
                timeout_seconds=5,
                command=[sys.executable, str(server), "collab"],
            )
            self.assertEqual(
                {
                    "root_work_id": result["work_capture"]["root_work_id"],
                    "delegation_count": 1,
                    "terminal_delegation_count": 1,
                    "incomplete_delegation_count": 0,
                },
                result["work_capture"],
            )
            observation = json.loads(
                safe_target(
                    repo,
                    (
                        ".maestro/state/inflight/"
                        f"{result['observation_id']}.json"
                    ),
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(2, len(observation["work_spans"]))
            root_span, child_span = observation["work_spans"]
            self.assertEqual("orchestration", root_span["kind"])
            self.assertEqual("completed", root_span["status"])
            self.assertEqual(root_span["work_id"], child_span["parent_work_id"])
            self.assertEqual("delegation", child_span["kind"])
            self.assertEqual("completed", child_span["status"])
            self.assertEqual("host_event", child_span["timing_evidence"])
            self.assertEqual(1_000, child_span["duration_ms"])
            self.assertEqual("gpt-5.6-terra", child_span["requested_model"])
            self.assertIsNone(child_span["applied_model"])
            serialized = json.dumps(observation, ensure_ascii=False)
            self.assertNotIn("SECRET-DELEGATION-PROMPT", serialized)
            self.assertNotIn("SECRET-CHILD-MESSAGE", serialized)
            self.assertNotIn("SECRET-CHILD-RESULT", serialized)
            self.assertNotIn("child-thread-1", serialized)
            work = project_observed_work(
                observation["work_spans"],
                [],
            )
            self.assertEqual("observed", work["mode"])
            self.assertEqual(2, len(work["cards"]))
            self.assertEqual(
                {"delegates_to", "reports_to"},
                {edge["type"] for edge in work["graph"]["edges"]},
            )

    def test_unresolved_child_keeps_the_observation_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="collab-incomplete",
                    task_label="미완료 Codex 위임 수집",
                    prompt_file=prompt,
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "collab-incomplete",
                    ],
                )
            self.assertEqual(
                "CODEX_HOST_WORK_INCOMPLETE",
                raised.exception.code,
            )
            paths = list(
                safe_target(repo, ".maestro/state/inflight").glob("*.json")
            )
            self.assertEqual(1, len(paths))
            observation = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertNotIn("completed_at", observation)
            self.assertEqual(
                ["completed", "running"],
                [item["status"] for item in observation["work_spans"]],
            )


if __name__ == "__main__":
    unittest.main()
