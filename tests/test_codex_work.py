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
    sender: str = "parent-thread",
    event_thread: str = "parent-thread",
    turn_id: str = "parent-turn",
    prompt: str = "SECRET-PROMPT",
) -> dict[str, object]:
    return {
        "threadId": event_thread,
        "turnId": turn_id,
        "startedAtMs": timestamp,
        "completedAtMs": timestamp,
        "item": {
            "type": "collabAgentToolCall",
            "id": item_id,
            "senderThreadId": sender,
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
            root_turn_id="parent-turn",
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
        self.assertEqual(
            ["finish", "start"],
            [item["action"] for item in started],
        )
        child_start = started[1]
        self.assertEqual("host_request", child_start["model_evidence"])

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

    def test_forbidden_spawn_is_rejected_before_tracker_state_changes(
        self,
    ) -> None:
        tracker = CodexCollaborationTracker(
            root_work_id="root",
            root_thread_id="parent-thread",
            root_turn_id="parent-turn",
            assignment_id="verification",
            read_only=True,
            may_spawn=False,
            max_children=0,
        )

        with self.assertRaises(MaestroError) as raised:
            tracker.consume(
                method="item/started",
                params=collab_params(
                    item_id="spawn-forbidden",
                    tool="spawnAgent",
                    status="inProgress",
                    targets=["child-1"],
                    states={"child-1": "running"},
                    timestamp=1_785_217_057_000,
                ),
            )

        self.assertEqual(
            "CODEX_WORK_DELEGATION_FORBIDDEN",
            raised.exception.code,
        )
        self.assertEqual(0, tracker.observed_work_count)
        self.assertEqual(0, tracker.decision_work_count)
        self.assertEqual([], tracker.running_work_ids)
        self.assertFalse(tracker.root_terminal)

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
            ["finish", "start", "finish"],
            [item["action"] for item in first],
        )
        self.assertEqual("failed", first[2]["status"])
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
        first_work_id = next(
            item["work_id"]
            for item in spawn
            if item["action"] == "start"
        )
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
        followup = next(
            item
            for item in resumed
            if item["action"] == "start"
            and item["kind"] == "delegation"
        )
        self.assertEqual(2, followup["attempt"])
        self.assertEqual(
            first_work_id,
            followup["followup_of_work_id"],
        )

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

    def test_wait_alone_does_not_create_a_synthesis_decision(self) -> None:
        tracker = self._tracker()
        tracker.consume(
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
        waited = tracker.consume(
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
        self.assertEqual(["finish"], [item["action"] for item in waited])
        self.assertEqual(0, tracker.decision_work_count)

    def test_report_consumption_creates_decision_before_redelegation(
        self,
    ) -> None:
        tracker = self._tracker()
        first = tracker.consume(
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
        first_work_id = next(
            item["work_id"]
            for item in first
            if item["action"] == "start"
        )
        tracker.consume(
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
        redelegated = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="spawn-2",
                tool="spawnAgent",
                status="inProgress",
                targets=["child-2"],
                states={"child-2": "running"},
                timestamp=1_785_217_059_000,
            ),
        )
        synthesis_start = redelegated[0]
        synthesis_finish = redelegated[1]
        next_start = redelegated[2]
        self.assertEqual("synthesis", synthesis_start["kind"])
        self.assertEqual(
            [first_work_id],
            synthesis_start["joins_work_ids"],
        )
        self.assertEqual(
            synthesis_start["work_id"],
            next_start["parent_work_id"],
        )
        self.assertEqual("finish", synthesis_finish["action"])

    def test_nested_delegation_keeps_the_child_as_its_parent(self) -> None:
        tracker = self._tracker()
        root_actions = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="spawn-parent",
                tool="spawnAgent",
                status="inProgress",
                targets=["child-1"],
                states={"child-1": "running"},
                timestamp=1_785_217_057_000,
            ),
        )
        parent_work_id = next(
            item["work_id"]
            for item in root_actions
            if item["action"] == "start"
        )
        nested = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="spawn-nested",
                tool="spawnAgent",
                status="inProgress",
                targets=["grandchild-1"],
                states={"grandchild-1": "running"},
                timestamp=1_785_217_057_500,
                sender="child-1",
                event_thread="child-1",
                turn_id="child-turn",
            ),
        )
        self.assertEqual("start", nested[0]["action"])
        self.assertEqual(parent_work_id, nested[0]["parent_work_id"])

    def test_terminal_decision_preserves_failure_and_interrupt_status(
        self,
    ) -> None:
        for agent_status, turn_status, expected in (
            ("errored", "failed", "failed"),
            ("interrupted", "interrupted", "interrupted"),
        ):
            with self.subTest(agent_status=agent_status):
                tracker = self._tracker()
                tracker.consume(
                    method="item/started",
                    params=collab_params(
                        item_id=f"spawn-{agent_status}",
                        tool="spawnAgent",
                        status="inProgress",
                        targets=["child-1"],
                        states={"child-1": "running"},
                        timestamp=1_785_217_057_000,
                    ),
                )
                tracker.consume(
                    method="item/completed",
                    params=collab_params(
                        item_id=f"wait-{agent_status}",
                        tool="wait",
                        status="completed",
                        targets=["child-1"],
                        states={"child-1": agent_status},
                        timestamp=1_785_217_058_000,
                    ),
                )
                final = tracker.finish_turn(
                    status=turn_status,
                    observed_at="2026-07-28T01:00:03Z",
                    duration_ms=3_000,
                    evidence_identity=(
                        "parent-thread",
                        "parent-turn",
                        f"terminal-{agent_status}",
                    ),
                )
                self.assertEqual("synthesis", final[0]["kind"])
                self.assertEqual(expected, final[1]["status"])

    def test_resume_is_parented_by_the_consuming_decision(self) -> None:
        tracker = self._tracker()
        spawned = tracker.consume(
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
        first_work_id = next(
            item["work_id"]
            for item in spawned
            if item["action"] == "start"
        )
        tracker.consume(
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
        resumed = tracker.consume(
            method="item/started",
            params=collab_params(
                item_id="resume-1",
                tool="resumeAgent",
                status="inProgress",
                targets=["child-1"],
                states={"child-1": "running"},
                timestamp=1_785_217_059_000,
            ),
        )
        decision = resumed[0]
        followup = resumed[2]
        self.assertEqual(decision["work_id"], followup["parent_work_id"])
        self.assertEqual(
            first_work_id,
            followup["followup_of_work_id"],
        )
        self.assertEqual(2, followup["attempt"])


if __name__ == "__main__":
    unittest.main()
