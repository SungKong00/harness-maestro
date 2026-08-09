from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maestro.codex_host import (
    _capture_child_runtime_event,
    _enrich_child_finish_action,
    run_codex_host,
)
from maestro.errors import MaestroError
from maestro.util import safe_target
from maestro.work import project_observed_work
from maestro.work.codex import CodexCollaborationTracker
from tests.test_codex_host import CodexHostTests, FAKE_APP_SERVER


COLLAB_EVENTS = r'''
        if mode in {
            "collab",
            "collab-error",
            "collab-incomplete",
            "collab-measured",
        }:
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
            if mode == "collab-error":
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": "error",
                        "params": {
                            "threadId": "thread-1",
                            "turnId": "turn-1",
                            "error": {
                                "code": "transient",
                                "message": "SECRET-ERROR-MESSAGE",
                            },
                            "willRetry": True,
                        },
                    }
                )
            if mode == "collab-measured":
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/started",
                        "params": {
                            "threadId": "child-thread-1",
                            "turn": {
                                "id": "child-turn-1",
                                "status": "inProgress",
                            },
                        },
                    }
                )
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": "model/rerouted",
                        "params": {
                            "threadId": "child-thread-1",
                            "turnId": "child-turn-1",
                            "fromModel": "gpt-5.6-terra",
                            "toModel": "gpt-5.6-sol",
                            "reason": "capacity",
                        },
                    }
                )
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "child-thread-1",
                            "turn": {
                                "id": "child-turn-1",
                                "status": "completed",
                                "completedAt": 1785217058,
                                "durationMs": 600,
                            },
                        },
                    }
                )
            if mode in {"collab", "collab-error", "collab-measured"}:
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
        if mode == "collab-wave":
            def emit_collab(item_id, tool, targets, states, timestamp):
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": (
                            "item/started"
                            if tool == "spawnAgent"
                            else "item/completed"
                        ),
                        "params": {
                            "threadId": "thread-1",
                            "turnId": "turn-1",
                            (
                                "startedAtMs"
                                if tool == "spawnAgent"
                                else "completedAtMs"
                            ): timestamp,
                            "item": {
                                "id": item_id,
                                "type": "collabAgentToolCall",
                                "tool": tool,
                                "status": (
                                    "inProgress"
                                    if tool == "spawnAgent"
                                    else "completed"
                                ),
                                "senderThreadId": "thread-1",
                                "receiverThreadIds": targets,
                                "model": "gpt-5.6-terra",
                                "reasoningEffort": "medium",
                                "agentsStates": {
                                    target: {"status": states[target]}
                                    for target in targets
                                },
                            },
                        },
                    }
                )

            emit_collab(
                "spawn-a",
                "spawnAgent",
                ["child-a"],
                {"child-a": "running"},
                1785217057000,
            )
            emit_collab(
                "spawn-a",
                "spawnAgent",
                ["child-a"],
                {"child-a": "running"},
                1785217057000,
            )
            emit_collab(
                "spawn-b",
                "spawnAgent",
                ["child-b"],
                {"child-b": "running"},
                1785217057100,
            )
            emit_collab(
                "spawn-c",
                "spawnAgent",
                ["child-c"],
                {"child-c": "running"},
                1785217057200,
            )
            emit_collab(
                "wait-abc",
                "wait",
                ["child-a", "child-b", "child-c"],
                {
                    "child-a": "completed",
                    "child-b": "completed",
                    "child-c": "completed",
                },
                1785217058000,
            )
            emit_collab(
                "spawn-d",
                "spawnAgent",
                ["child-d"],
                {"child-d": "running"},
                1785217059000,
            )
            emit_collab(
                "spawn-e",
                "spawnAgent",
                ["child-e"],
                {"child-e": "running"},
                1785217059100,
            )
            emit_collab(
                "wait-de",
                "wait",
                ["child-d", "child-e"],
                {
                    "child-d": "completed",
                    "child-e": "completed",
                },
                1785217060000,
            )
            emit_collab(
                "spawn-verification",
                "spawnAgent",
                ["child-verification"],
                {"child-verification": "running"},
                1785217061000,
            )
            emit_collab(
                "wait-verification",
                "wait",
                ["child-verification"],
                {"child-verification": "completed"},
                1785217062000,
            )
'''

COLLAB_LATE_EVENTS = r'''
        if mode == "collab-measured":
            emit(
                {
                    "jsonrpc": "2.0",
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "child-thread-1",
                        "turnId": "child-turn-1",
                        "tokenUsage": {
                            "last": {
                                "inputTokens": 12,
                                "outputTokens": 6,
                                "cachedInputTokens": 4,
                                "reasoningOutputTokens": 3,
                                "totalTokens": 25,
                            },
                            "total": {
                                "inputTokens": 80,
                                "outputTokens": 20,
                                "cachedInputTokens": 5,
                                "reasoningOutputTokens": 4,
                                "totalTokens": 109,
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
    late_marker = (
        '        time.sleep(0.6 if mode == "late-token" else 0.03)\n'
    )
    if late_marker not in FAKE_APP_SERVER:
        raise AssertionError("fake App Server late-event point changed")
    with_collaboration = FAKE_APP_SERVER.replace(
        marker,
        COLLAB_EVENTS + marker,
        1,
    )
    return with_collaboration.replace(
        late_marker,
        COLLAB_LATE_EVENTS + late_marker,
        1,
    )


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
                    "decision_count": 1,
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
            self.assertEqual(3, len(observation["work_spans"]))
            root_span, child_span, decision_span = observation["work_spans"]
            self.assertEqual("orchestration", root_span["kind"])
            self.assertEqual("completed", root_span["status"])
            self.assertEqual(root_span["work_id"], child_span["parent_work_id"])
            self.assertEqual("delegation", child_span["kind"])
            self.assertEqual("completed", child_span["status"])
            self.assertEqual("host_event", child_span["timing_evidence"])
            self.assertEqual(1_000, child_span["duration_ms"])
            self.assertEqual("gpt-5.6-terra", child_span["requested_model"])
            self.assertIsNone(child_span["applied_model"])
            self.assertEqual("unavailable", child_span["usage"]["scope"])
            self.assertIsNone(child_span["usage"]["total"])
            self.assertEqual(
                "partial_stream",
                child_span["source_binding"]["event_coverage"],
            )
            self.assertIsNone(child_span["source_binding"]["version"])
            self.assertEqual("synthesis", decision_span["kind"])
            self.assertEqual(
                [child_span["work_id"]],
                decision_span["joins_work_ids"],
            )
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
            self.assertEqual(3, len(work["cards"]))
            self.assertEqual(
                {"delegates_to", "reports_to", "joins_into", "depends_on"},
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

    def test_complete_child_turn_records_direct_model_tokens_and_time(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            with patch(
                "maestro.codex_host._codex_runtime_binding",
                return_value={
                    "version": "codex-cli 0.144.1",
                    "schema_digest": "a" * 64,
                    "capability": "full_stream",
                    "experimental_api": False,
                    "runtime_workspace_roots": False,
                },
            ):
                result = run_codex_host(
                    repo,
                    run_id="collab-measured",
                    task_label="하위 Codex 실행 계측",
                    prompt_file=prompt,
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "collab-measured",
                    ],
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
            child = next(
                span
                for span in observation["work_spans"]
                if span["kind"] == "delegation"
            )
            self.assertEqual("gpt-5.6-sol", child["applied_model"])
            self.assertEqual("complete", child["model_evidence"])
            self.assertEqual(
                "complete_stream",
                child["source_binding"]["event_coverage"],
            )
            self.assertEqual("work_turn", child["usage"]["scope"])
            self.assertEqual("direct", child["usage"]["attribution"])
            self.assertEqual(25, child["usage"]["last"]["total"])
            self.assertEqual(109, child["usage"]["total"]["total"])
            self.assertEqual(600, child["duration_ms"])

    def test_child_without_terminal_stream_never_uses_requested_as_actual(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            with patch(
                "maestro.codex_host._codex_runtime_binding",
                return_value={
                    "version": "codex-cli 0.144.1",
                    "schema_digest": "b" * 64,
                    "capability": "full_stream",
                    "experimental_api": False,
                    "runtime_workspace_roots": False,
                },
            ):
                result = run_codex_host(
                    repo,
                    run_id="collab-unmeasured-child",
                    task_label="불완전 하위 실행 계측",
                    prompt_file=prompt,
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "collab"],
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
            child = next(
                span
                for span in observation["work_spans"]
                if span["kind"] == "delegation"
            )
            self.assertIsNone(child["applied_model"])
            self.assertEqual("host_request", child["model_evidence"])
            self.assertEqual(
                "partial_stream",
                child["source_binding"]["event_coverage"],
            )
            self.assertEqual("unavailable", child["usage"]["scope"])

    def test_resumed_child_uses_stable_delta_and_rejects_late_baseline(
        self,
    ) -> None:
        def measured_resume(*, late_prior_token: bool) -> dict[str, object]:
            tracker = CodexCollaborationTracker(
                root_work_id="root-work",
                root_thread_id="root-thread",
                root_turn_id="root-turn",
                assignment_id=None,
                read_only=True,
                source_version="codex-cli 0.144.1",
                schema_digest="c" * 64,
                source_capability="full_stream",
            )
            runtime_state = {
                "child_work_starts": {},
                "child_work_runtime": {},
                "child_thread_totals": {},
            }

            def collab(
                *,
                item_id: str,
                tool: str,
                status: str,
                child_status: str,
                timestamp: int,
            ) -> list[dict[str, object]]:
                return tracker.consume(
                    method=(
                        "item/started"
                        if status == "inProgress"
                        else "item/completed"
                    ),
                    params={
                        "threadId": "root-thread",
                        "turnId": "root-turn",
                        (
                            "startedAtMs"
                            if status == "inProgress"
                            else "completedAtMs"
                        ): timestamp,
                        "item": {
                            "id": item_id,
                            "type": "collabAgentToolCall",
                            "tool": tool,
                            "status": status,
                            "senderThreadId": "root-thread",
                            "receiverThreadIds": ["child-thread"],
                            "model": "gpt-5.6-terra",
                            "reasoningEffort": "medium",
                            "agentsStates": {
                                "child-thread": {"status": child_status}
                            },
                        },
                    },
                )

            first_actions = collab(
                item_id="spawn-1",
                tool="spawnAgent",
                status="inProgress",
                child_status="running",
                timestamp=1785217057000,
            )
            first_start = next(
                action
                for action in first_actions
                if action["action"] == "start"
                and action["kind"] == "delegation"
            )
            runtime_state["child_work_starts"][
                first_start["work_id"]
            ] = first_start
            _capture_child_runtime_event(
                method="turn/started",
                params={
                    "threadId": "child-thread",
                    "turn": {"id": "child-turn-1"},
                },
                state=runtime_state,
                tracker=tracker,
            )
            _capture_child_runtime_event(
                method="thread/tokenUsage/updated",
                params={
                    "threadId": "child-thread",
                    "turnId": "child-turn-1",
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 12,
                            "outputTokens": 6,
                            "cachedInputTokens": 4,
                            "reasoningOutputTokens": 3,
                            "totalTokens": 25,
                        },
                        "total": {
                            "inputTokens": 80,
                            "outputTokens": 20,
                            "cachedInputTokens": 5,
                            "reasoningOutputTokens": 4,
                            "totalTokens": 109,
                        },
                    },
                },
                state=runtime_state,
                tracker=tracker,
            )
            _capture_child_runtime_event(
                method="turn/completed",
                params={
                    "threadId": "child-thread",
                    "turn": {
                        "id": "child-turn-1",
                        "status": "completed",
                        "durationMs": 600,
                    },
                },
                state=runtime_state,
                tracker=tracker,
            )
            first_finish = next(
                action
                for action in collab(
                    item_id="wait-1",
                    tool="wait",
                    status="completed",
                    child_status="completed",
                    timestamp=1785217058000,
                )
                if action["action"] == "finish"
            )
            first_enriched = _enrich_child_finish_action(
                first_finish,
                start_action=first_start,
                runtime=runtime_state["child_work_runtime"][
                    first_start["work_id"]
                ],
            )
            self.assertEqual(
                109,
                first_enriched["usage"]["total"]["total"],
            )

            resumed_actions = collab(
                item_id="resume-2",
                tool="resumeAgent",
                status="inProgress",
                child_status="running",
                timestamp=1785217059000,
            )
            second_start = next(
                action
                for action in resumed_actions
                if action["action"] == "start"
                and action["kind"] == "delegation"
            )
            runtime_state["child_work_starts"][
                second_start["work_id"]
            ] = second_start
            _capture_child_runtime_event(
                method="turn/started",
                params={
                    "threadId": "child-thread",
                    "turn": {"id": "child-turn-2"},
                },
                state=runtime_state,
                tracker=tracker,
            )
            if late_prior_token:
                _capture_child_runtime_event(
                    method="thread/tokenUsage/updated",
                    params={
                        "threadId": "child-thread",
                        "turnId": "child-turn-1",
                        "tokenUsage": {
                            "last": {
                                "inputTokens": 2,
                                "outputTokens": 1,
                                "cachedInputTokens": 0,
                                "reasoningOutputTokens": 0,
                                "totalTokens": 3,
                            },
                            "total": {
                                "inputTokens": 82,
                                "outputTokens": 21,
                                "cachedInputTokens": 5,
                                "reasoningOutputTokens": 4,
                                "totalTokens": 112,
                            },
                        },
                    },
                    state=runtime_state,
                    tracker=tracker,
                )
            _capture_child_runtime_event(
                method="thread/tokenUsage/updated",
                params={
                    "threadId": "child-thread",
                    "turnId": "child-turn-2",
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 8,
                            "outputTokens": 4,
                            "cachedInputTokens": 2,
                            "reasoningOutputTokens": 1,
                            "totalTokens": 15,
                        },
                        "total": {
                            "inputTokens": 88,
                            "outputTokens": 24,
                            "cachedInputTokens": 7,
                            "reasoningOutputTokens": 5,
                            "totalTokens": 124,
                        },
                    },
                },
                state=runtime_state,
                tracker=tracker,
            )
            _capture_child_runtime_event(
                method="turn/completed",
                params={
                    "threadId": "child-thread",
                    "turn": {
                        "id": "child-turn-2",
                        "status": "completed",
                        "durationMs": 400,
                    },
                },
                state=runtime_state,
                tracker=tracker,
            )
            second_finish = next(
                action
                for action in collab(
                    item_id="wait-2",
                    tool="wait",
                    status="completed",
                    child_status="completed",
                    timestamp=1785217060000,
                )
                if action["action"] == "finish"
            )
            return _enrich_child_finish_action(
                second_finish,
                start_action=second_start,
                runtime=runtime_state["child_work_runtime"][
                    second_start["work_id"]
                ],
            )

        stable = measured_resume(late_prior_token=False)
        self.assertEqual("direct", stable["usage"]["attribution"])
        self.assertEqual(15, stable["usage"]["total"]["total"])
        invalidated = measured_resume(late_prior_token=True)
        self.assertEqual(
            "unavailable",
            invalidated["usage"]["attribution"],
        )
        self.assertIsNone(invalidated["usage"]["total"])

    def test_first_observed_resume_never_uses_zero_token_baseline(
        self,
    ) -> None:
        tracker = CodexCollaborationTracker(
            root_work_id="root-work",
            root_thread_id="root-thread",
            root_turn_id="root-turn",
            assignment_id=None,
            read_only=True,
            source_version="codex-cli 0.144.1",
            schema_digest="d" * 64,
            source_capability="full_stream",
        )
        actions = tracker.consume(
            method="item/started",
            params={
                "threadId": "root-thread",
                "turnId": "root-turn",
                "startedAtMs": 1785217057000,
                "item": {
                    "id": "resume-existing",
                    "type": "collabAgentToolCall",
                    "tool": "resumeAgent",
                    "status": "inProgress",
                    "senderThreadId": "root-thread",
                    "receiverThreadIds": ["existing-child-thread"],
                    "model": "gpt-5.6-terra",
                    "reasoningEffort": "medium",
                    "agentsStates": {
                        "existing-child-thread": {"status": "running"}
                    },
                },
            },
        )
        start = next(
            action
            for action in actions
            if action["action"] == "start"
            and action["kind"] == "delegation"
        )
        runtime_state = {
            "child_work_starts": {start["work_id"]: start},
            "child_work_runtime": {},
            "child_thread_totals": {},
        }
        _capture_child_runtime_event(
            method="turn/started",
            params={
                "threadId": "existing-child-thread",
                "turn": {"id": "resumed-turn"},
            },
            state=runtime_state,
            tracker=tracker,
        )
        _capture_child_runtime_event(
            method="thread/tokenUsage/updated",
            params={
                "threadId": "existing-child-thread",
                "turnId": "resumed-turn",
                "tokenUsage": {
                    "last": {
                        "inputTokens": 4,
                        "outputTokens": 2,
                        "cachedInputTokens": 0,
                        "reasoningOutputTokens": 1,
                        "totalTokens": 7,
                    },
                    "total": {
                        "inputTokens": 104,
                        "outputTokens": 42,
                        "cachedInputTokens": 10,
                        "reasoningOutputTokens": 9,
                        "totalTokens": 165,
                    },
                },
            },
            state=runtime_state,
            tracker=tracker,
        )
        _capture_child_runtime_event(
            method="turn/completed",
            params={
                "threadId": "existing-child-thread",
                "turn": {
                    "id": "resumed-turn",
                    "status": "completed",
                    "durationMs": 500,
                },
            },
            state=runtime_state,
            tracker=tracker,
        )
        enriched = _enrich_child_finish_action(
            {
                "action": "finish",
                "work_id": start["work_id"],
                "status": "completed",
                "result_summary": "재개 작업 완료",
                "ended_at": "2026-07-28T01:00:00Z",
                "duration_ms": 500,
                "evidence_refs": ["fixture:first-resume"],
            },
            start_action=start,
            runtime=runtime_state["child_work_runtime"][
                start["work_id"]
            ],
        )
        self.assertEqual("complete", enriched["model_evidence"])
        self.assertEqual("unavailable", enriched["usage"]["attribution"])
        self.assertIsNone(enriched["usage"]["total"])

    def test_full_wave_fixture_projects_join_and_redelegation_ranks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            result = run_codex_host(
                repo,
                run_id="collab-wave",
                task_label="결과 종합과 재위임 파동",
                prompt_file=prompt,
                sandbox="read-only",
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "collab-wave",
                ],
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
            work = project_observed_work(
                observation["work_spans"],
                [],
            )
            cards = work["cards"]
            by_rank: dict[int, list[dict[str, object]]] = {}
            for card in cards:
                by_rank.setdefault(card["rank"], []).append(card)

            self.assertEqual(10, len(cards))
            self.assertEqual(
                [1, 3, 1, 2, 1, 1, 1],
                [len(by_rank[rank]) for rank in range(7)],
            )
            self.assertTrue(
                all(
                    card["kind"] == "delegation"
                    for card in by_rank[1]
                )
            )
            self.assertTrue(
                all(
                    card["kind"] == "delegation"
                    for card in by_rank[3]
                )
            )
            self.assertEqual(
                ["synthesis"],
                [card["kind"] for card in by_rank[2]],
            )
            self.assertEqual(
                ["synthesis"],
                [card["kind"] for card in by_rank[4]],
            )
            self.assertEqual(
                ["synthesis"],
                [card["kind"] for card in by_rank[6]],
            )
            self.assertEqual(6, work["summary"]["join_count"])
            self.assertEqual(6, work["summary"]["delegation_count"])
            self.assertEqual(6, work["summary"]["report_count"])
            self.assertEqual(
                "unavailable",
                work["graph"]["actual_concurrency"],
            )
            self.assertEqual(3, result["work_capture"]["decision_count"])

    def test_mid_turn_error_is_diagnostic_until_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            result = run_codex_host(
                repo,
                run_id="collab-error",
                task_label="중간 오류 진단",
                prompt_file=prompt,
                sandbox="read-only",
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "collab-error",
                ],
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
            diagnostic_span = next(
                span
                for span in reversed(observation["work_spans"])
                if span["diagnostics"]["error_count"]
            )
            self.assertEqual("completed", diagnostic_span["status"])
            self.assertEqual(
                1,
                diagnostic_span["diagnostics"]["error_count"],
            )
            self.assertEqual(
                "Codex App Server error (transient)",
                diagnostic_span["diagnostics"]["last_error"],
            )
            self.assertNotIn(
                "SECRET-ERROR-MESSAGE",
                json.dumps(observation, ensure_ascii=False),
            )


if __name__ == "__main__":
    unittest.main()
