from __future__ import annotations

import json
import unittest

from maestro.errors import MaestroError
from maestro.work.codex import CodexCollaborationTracker


def collab_params(
    *,
    item_id: str,
    tool: str,
    status: str,
    targets: list[str],
    states: dict[str, str],
    timestamp: int,
    prompt: str = "SECRET-PROMPT",
) -> dict[str, object]:
    return {
        "threadId": "parent-thread",
        "turnId": "parent-turn",
        "startedAtMs": timestamp,
        "completedAtMs": timestamp,
        "item": {
            "type": "collabAgentToolCall",
            "id": item_id,
            "senderThreadId": "parent-thread",
            "receiverThreadIds": targets,
            "tool": tool,
            "status": status,
            "model": "gpt-5.6-terra",
            "reasoningEffort": "medium",
            "prompt": prompt,
            "agentsStates": {
                thread_id: {
                    "status": state,
                    "message": "SECRET-AGENT-MESSAGE",
                }
                for thread_id, state in states.items()
            },
        },
    }


class CodexCollaborationTrackerTests(unittest.TestCase):
    def _tracker(self) -> CodexCollaborationTracker:
        return CodexCollaborationTracker(
            root_work_id="root",
            root_thread_id="parent-thread",
            assignment_id="implementation",
            read_only=False,
        )

    def test_spawn_lifecycle_uses_agent_state_and_redacts_content(self) -> None:
        tracker = self._tracker()
        started = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="spawn-1",
                tool="spawnAgent",
                status="inProgress",
                targets=["child-1"],
                states={"child-1": "running"},
                timestamp=1_785_217_057_000,
            ),
        )
        self.assertEqual(["start"], [item["action"] for item in started])
        self.assertEqual("host_request", started[0]["model_evidence"])

        duplicate = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="spawn-1",
                tool="spawnAgent",
                status="inProgress",
                targets=["child-1"],
                states={"child-1": "running"},
                timestamp=1_785_217_057_000,
            ),
        )
        self.assertEqual([], duplicate)

        rpc_completed = tracker.consume(
            method="item/completed",
            params=collab_params(
                item_id="spawn-1",
                tool="spawnAgent",
                status="completed",
                targets=["child-1"],
                states={"child-1": "running"},
                timestamp=1_785_217_057_500,
            ),
        )
        self.assertEqual([], rpc_completed)
        self.assertEqual(1, len(tracker.running_work_ids))

        child_completed = tracker.consume(
            method="item/completed",
            params=collab_params(
                item_id="wait-1",
                tool="wait",
                status="completed",
                targets=["child-1"],
                states={"child-1": "completed"},
                timestamp=1_785_217_058_000,
            ),
        )
        self.assertEqual(["finish"], [item["action"] for item in child_completed])
        self.assertEqual([], tracker.running_work_ids)
        serialized = json.dumps(
            [*started, *child_completed],
            ensure_ascii=False,
        )
        self.assertNotIn("SECRET-PROMPT", serialized)
        self.assertNotIn("SECRET-AGENT-MESSAGE", serialized)
        self.assertNotIn("child-1", serialized)

    def test_failed_spawn_is_terminal_and_replay_is_idempotent(self) -> None:
        tracker = self._tracker()
        params = collab_params(
            item_id="spawn-failed",
            tool="spawnAgent",
            status="failed",
            targets=[],
            states={},
            timestamp=1_785_217_057_000,
        )
        first = tracker.consume(method="item/completed", params=params)
        second = tracker.consume(method="item/completed", params=params)
        self.assertEqual(
            ["start", "finish"],
            [item["action"] for item in first],
        )
        self.assertEqual("failed", first[1]["status"])
        self.assertEqual([], second)

    def test_resume_creates_an_explicit_followup_attempt(self) -> None:
        tracker = self._tracker()
        spawn = tracker.consume(
            method="item/completed",
            params=collab_params(
                item_id="spawn-1",
                tool="spawnAgent",
                status="completed",
                targets=["child-1"],
                states={"child-1": "completed"},
                timestamp=1_785_217_057_000,
            ),
        )
        first_work_id = spawn[0]["work_id"]
        resumed = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="resume-1",
                tool="resumeAgent",
                status="inProgress",
                targets=["child-1"],
                states={"child-1": "running"},
                timestamp=1_785_217_058_000,
            ),
        )
        self.assertEqual(2, resumed[0]["attempt"])
        self.assertEqual(first_work_id, resumed[0]["followup_of_work_id"])

        interrupted = tracker.consume(
            method="item/completed",
            params=collab_params(
                item_id="wait-2",
                tool="wait",
                status="completed",
                targets=["child-1"],
                states={"child-1": "interrupted"},
                timestamp=1_785_217_059_000,
            ),
        )
        self.assertEqual("interrupted", interrupted[0]["status"])

    def test_invalid_or_foreign_events_do_not_cross_the_boundary(self) -> None:
        tracker = self._tracker()
        foreign = collab_params(
            item_id="spawn-foreign",
            tool="spawnAgent",
            status="inProgress",
            targets=["child-1"],
            states={"child-1": "running"},
            timestamp=1_785_217_057_000,
        )
        foreign["item"]["senderThreadId"] = "other-thread"
        self.assertEqual(
            [],
            tracker.consume(method="item/started", params=foreign),
        )

        invalid = collab_params(
            item_id="spawn-invalid",
            tool="spawnAgent",
            status="inProgress",
            targets=["child-1"],
            states={"child-1": "running"},
            timestamp=1_785_217_057_000,
        )
        invalid["item"]["agentsStates"]["child-1"]["status"] = "unknown"
        with self.assertRaises(MaestroError) as raised:
            tracker.consume(method="item/started", params=invalid)
        self.assertEqual("CODEX_WORK_EVENT_INVALID", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
