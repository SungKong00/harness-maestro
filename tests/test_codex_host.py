from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.support import apply_fresh_init, write_json

from maestro.cli import main, parser
from maestro.codex_host import run_codex_host
from maestro.errors import MaestroError
from maestro.planning import route_goal_v2
from maestro.util import safe_target


FAKE_APP_SERVER = r"""
import json
import sys
import time

mode = sys.argv[1]
thread_model = "gpt-default"
thread_effort = "medium"


def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        emit({"jsonrpc": "2.0", "id": message["id"], "result": {}})
    elif method == "initialized":
        continue
    elif method == "thread/start":
        params = message["params"]
        assert params["approvalPolicy"] == "never"
        assert params["ephemeral"] is True
        assert params["sandbox"] in {"read-only", "workspace-write"}
        thread_model = params.get("model") or thread_model
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "thread": {"id": "thread-1"},
                    "model": thread_model,
                    "reasoningEffort": thread_effort,
                },
            }
        )
    elif method == "turn/start":
        params = message["params"]
        assert params["approvalPolicy"] == "never"
        policy = params["sandboxPolicy"]
        if policy["type"] == "readOnly":
            assert policy["networkAccess"] is False
        else:
            assert policy["type"] == "workspaceWrite"
            assert policy["networkAccess"] is False
            assert len(policy["writableRoots"]) == 1
        assert params["input"][0]["type"] == "text"
        assert params["input"][0]["text"].strip()
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"turn": {"id": "turn-1"}},
            }
        )
        if mode == "incomplete":
            sys.exit(0)
        if mode == "interactive":
            emit(
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "item/tool/requestUserInput",
                    "params": {},
                }
            )
            sys.exit(0)
        if mode != "terminal-message":
            emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "completedAtMs": 1,
                        "item": {
                            "id": "message-1",
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": "fake final answer",
                        },
                    },
                }
            )
        if thread_model == "gpt-5.6-sol":
            emit(
                {
                    "jsonrpc": "2.0",
                    "method": "model/rerouted",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "fromModel": "gpt-5.6-sol",
                        "toModel": "gpt-5.6-terra",
                        "reason": "highRiskCyberActivity",
                    },
                }
            )
        emit(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "durationMs": (
                            "invalid" if mode == "bad-duration" else 321
                        ),
                        "items": (
                            [
                                {
                                    "id": "message-2",
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": "terminal fallback answer",
                                }
                            ]
                            if mode == "terminal-message"
                            else []
                        ),
                    },
                },
            }
        )
        time.sleep(0.03)
        emit(
            {
                "jsonrpc": "2.0",
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 30,
                            "outputTokens": 12,
                            "cachedInputTokens": 5,
                            "reasoningOutputTokens": 3,
                            "totalTokens": 42,
                        },
                        "total": {
                            "inputTokens": 30,
                            "outputTokens": 12,
                            "cachedInputTokens": 5,
                            "reasoningOutputTokens": 3,
                            "totalTokens": 42,
                        },
                    },
                },
            }
        )
"""


class CodexHostTests(unittest.TestCase):
    def _project(self, root: Path) -> tuple[Path, Path, Path]:
        repo = root / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Test\n", encoding="utf-8")
        apply_fresh_init(repo)
        prompt = root / "prompt.txt"
        prompt.write_text(
            "SENSITIVE-PROMPT-MUST-NOT-BE-PERSISTED",
            encoding="utf-8",
        )
        server = root / "fake_app_server.py"
        server.write_text(FAKE_APP_SERVER, encoding="utf-8")
        return repo, prompt, server

    def test_owned_turn_records_complete_model_reroute_effort_and_tokens(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)

            result = run_codex_host(
                repo,
                run_id="owned-turn",
                task_label="공식 이벤트 관측 테스트",
                prompt_file=prompt,
                sandbox="read-only",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                timeout_seconds=5,
                command=[sys.executable, str(server), "success"],
            )

            self.assertEqual("completed", result["status"])
            self.assertEqual("read-only", result["sandbox"])
            self.assertEqual("gpt-5.6-sol", result["requested_model"])
            self.assertEqual("high", result["requested_reasoning_effort"])
            self.assertEqual("gpt-5.6-terra", result["applied_model"])
            self.assertEqual(42, result["tokens"]["total"])
            self.assertEqual("host_event", result["token_measurement"])
            self.assertEqual("fake final answer", result["final_message"])
            observation = json.loads(
                safe_target(
                    repo,
                    (
                        ".maestro/state/inflight/"
                        f"{result['observation_id']}.json"
                    ),
                ).read_text(encoding="utf-8")
            )
            serialized = json.dumps(observation, ensure_ascii=False)
            self.assertNotIn("SENSITIVE-PROMPT", serialized)
            self.assertNotIn("fake final answer", serialized)
            self.assertEqual(321, observation["duration_ms"])
            self.assertEqual(
                "complete",
                observation["host_observation"]["model_event_evidence"],
            )
            self.assertEqual(
                42,
                observation["host_observation"]["tokens"]["total"],
            )

    def test_assignment_derives_bounded_writer_sandbox_and_model_route(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            plan = route_goal_v2(
                "Implement one local CLI behavior",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            assignment = next(
                item
                for item in plan["assignments"]
                if item["assignment_id"] == "implementation"
            )

            result = run_codex_host(
                repo,
                run_id="assignment-turn",
                task_label="Assignment 기반 실행",
                prompt_file=prompt,
                plan_path=plan_path,
                assignment_id="implementation",
                timeout_seconds=5,
                command=[sys.executable, str(server), "success"],
            )

            self.assertEqual("workspace-write", result["sandbox"])
            self.assertEqual(
                assignment["model_route"]["selected_model"],
                result["requested_model"],
            )
            self.assertEqual(
                assignment["model_route"]["reasoning_effort"],
                result["requested_reasoning_effort"],
            )

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="sandbox-conflict",
                    task_label="충돌",
                    prompt_file=prompt,
                    plan_path=plan_path,
                    assignment_id="implementation",
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_SANDBOX_CONFLICT",
                raised.exception.code,
            )

    def test_terminal_turn_items_supply_final_message_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            result = run_codex_host(
                repo,
                run_id="terminal-message",
                task_label="terminal fallback",
                prompt_file=prompt,
                sandbox="read-only",
                timeout_seconds=5,
                command=[sys.executable, str(server), "terminal-message"],
            )
            self.assertEqual(
                "terminal fallback answer",
                result["final_message"],
            )

    def test_incomplete_or_interactive_stream_never_claims_applied_model(
        self,
    ) -> None:
        for mode, code in (
            ("incomplete", "CODEX_HOST_EXITED"),
            ("interactive", "CODEX_HOST_INTERACTION_UNSUPPORTED"),
            ("bad-duration", "CODEX_HOST_PROTOCOL_INVALID"),
        ):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    repo, prompt, server = self._project(root)
                    with self.assertRaises(MaestroError) as raised:
                        run_codex_host(
                            repo,
                            run_id=f"{mode}-turn",
                            task_label=f"{mode} 실패",
                            prompt_file=prompt,
                            sandbox="read-only",
                            model="gpt-5.6-sol",
                            timeout_seconds=5,
                            command=[sys.executable, str(server), mode],
                        )
                    self.assertEqual(code, raised.exception.code)
                    observations = list(
                        safe_target(
                            repo,
                            ".maestro/state/inflight",
                        ).glob("*.json")
                    )
                    self.assertEqual(1, len(observations))
                    value = json.loads(
                        observations[0].read_text(encoding="utf-8")
                    )
                    self.assertNotIn("host_observation", value)
                    self.assertNotIn("completed_at", value)

    def test_cli_contract_is_explicit_and_terminal_failure_exits_four(
        self,
    ) -> None:
        args = parser().parse_args(
            [
                "host",
                "codex",
                "--run-id",
                "run",
                "--task-label",
                "label",
                "--prompt-file",
                "prompt.txt",
                "--sandbox",
                "read-only",
                "--reasoning-effort",
                "xhigh",
                "--json",
            ]
        )
        self.assertEqual("codex", args.host_command)
        self.assertEqual("read-only", args.sandbox)
        self.assertEqual("xhigh", args.reasoning_effort)

        with patch(
            "maestro.cli.run_codex_host",
            return_value={
                "schema_version": "maestro_codex_host_run_v1",
                "status": "failed",
            },
        ):
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    4,
                    main(
                        [
                            "host",
                            "codex",
                            "--run-id",
                            "run",
                            "--task-label",
                            "label",
                            "--prompt-file",
                            "prompt.txt",
                            "--sandbox",
                            "read-only",
                            "--json",
                        ]
                    ),
                )


if __name__ == "__main__":
    unittest.main()
