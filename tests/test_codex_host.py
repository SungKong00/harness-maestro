from __future__ import annotations

import copy
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
from maestro.assignment_contracts import project_assignment_input
from maestro.codex_host import _host_assignment_lease, run_codex_host
from maestro.errors import MaestroError
from maestro.governance import finalize_run
from maestro.observations import (
    record_stage_observation,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.snapshot import snapshot_report
from maestro.util import safe_target
from tests.test_assignment_contracts import (
    baseline_for,
    completed_terminal_packet,
    finding_packet,
)


FAKE_APP_SERVER = r"""
import json
import sys
import time

mode = sys.argv[1]
packet_path = sys.argv[2] if len(sys.argv) > 2 else None
thread_model = "gpt-default"
thread_effort = "medium"


def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        opt_out = message["params"]["capabilities"][
            "optOutNotificationMethods"
        ]
        assert "item/agentMessage/delta" in opt_out
        assert "item/reasoning/textDelta" in opt_out
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
        prompt_text = params["input"][0]["text"]
        assert prompt_text.strip()
        assignment_prompt = "Validated AssignmentInput:" in prompt_text
        if assignment_prompt:
            output_schema = params["outputSchema"]
            assert output_schema["additionalProperties"] is False
            assert output_schema["properties"]["plan_id"]["enum"]
            assert output_schema["properties"]["assignment_id"]["enum"]
            assert "Final-answer JSON Schema:" in prompt_text
            assert json.dumps(
                output_schema,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ) in prompt_text
            if packet_path is not None:
                with open(packet_path, encoding="utf-8") as packet_file:
                    expected_packet = json.load(packet_file)
                properties = output_schema["properties"]
                assert (
                    properties["schema_version"]["enum"]
                    == [expected_packet["schema_version"]]
                )
                assert (
                    properties["plan_id"]["enum"]
                    == [expected_packet["plan_id"]]
                )
                assert (
                    properties["assignment_id"]["enum"]
                    == [expected_packet["assignment_id"]]
                )
                if "packet_type" in expected_packet:
                    assert (
                        properties["packet_type"]["enum"]
                        == [expected_packet["packet_type"]]
                    )
        else:
            assert "outputSchema" not in params
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
        if mode == "noisy":
            for index in range(20_050):
                emit(
                    {
                        "jsonrpc": "2.0",
                        "method": "warning",
                        "params": {
                            "threadId": "thread-1",
                            "message": f"noise-{index}",
                        },
                    }
                )
        if mode != "terminal-message":
            final_text = (
                open(packet_path, encoding="utf-8").read()
                if packet_path is not None
                else "fake final answer"
            )
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
                            "text": final_text,
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
        time.sleep(0.6 if mode == "late-token" else 0.03)
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
                            "inputTokens": 60,
                            "outputTokens": 24,
                            "cachedInputTokens": 10,
                            "reasoningOutputTokens": 6,
                            "totalTokens": 84,
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
        for relative in ("docs/project.md", "docs/architecture.md"):
            path = repo / relative
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "status: draft",
                    "status: active",
                    1,
                ),
                encoding="utf-8",
            )
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
                command=[sys.executable, str(server), "late-token"],
            )

            self.assertEqual("completed", result["status"])
            self.assertEqual("read-only", result["sandbox"])
            self.assertEqual("gpt-5.6-sol", result["requested_model"])
            self.assertEqual("high", result["requested_reasoning_effort"])
            self.assertEqual("gpt-5.6-terra", result["applied_model"])
            self.assertEqual(84, result["tokens"]["total"])
            self.assertEqual("host_event", result["token_measurement"])
            self.assertFalse(result["output_schema_applied"])
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
                84,
                observation["host_observation"]["tokens"]["total"],
            )
            self.assertEqual(
                {
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "maestro_owned_codex_app_server",
                },
                observation["execution_binding"],
            )
            root_work = next(
                span
                for span in observation["work_spans"]
                if span["kind"] == "orchestration"
            )
            self.assertEqual(
                "lifecycle_only",
                root_work["source_binding"]["capability"],
            )
            self.assertEqual("unavailable", root_work["usage"]["attribution"])
            self.assertIsNone(root_work["usage"]["total"])

    def test_assignment_lease_blocks_concurrent_launch_and_recovers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            with _host_assignment_lease(
                repo,
                run_id="lease-run",
                assignment_id="implementation",
            ):
                with self.assertRaises(MaestroError) as raised:
                    run_codex_host(
                        repo,
                        run_id="lease-run",
                        task_label="동시 실행 금지",
                        prompt_file=prompt,
                        assignment_id="implementation",
                        sandbox="workspace-write",
                        timeout_seconds=5,
                        command=[
                            sys.executable,
                            str(server),
                            "success",
                        ],
                    )
                self.assertEqual(
                    "CODEX_HOST_ASSIGNMENT_BUSY",
                    raised.exception.code,
                )

            with _host_assignment_lease(
                repo,
                run_id="lease-run",
                assignment_id="implementation",
            ):
                pass

    def test_missing_platform_lease_is_typed_without_breaking_cli_import(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            with (
                patch("maestro.codex_host.fcntl", None),
                self.assertRaises(MaestroError) as raised,
            ):
                run_codex_host(
                    repo,
                    run_id="lease-unavailable",
                    task_label="lease unavailable",
                    prompt_file=prompt,
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_LEASE_UNAVAILABLE",
                raised.exception.code,
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
            baseline_path = root / "baseline.json"
            baseline = baseline_for(plan)
            write_json(baseline_path, baseline)
            projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
            )
            self.assertEqual("PASS", projection["status"])
            projection_path = root / "projection.json"
            write_json(projection_path, projection)
            packet_path = root / "packet.json"
            write_json(
                packet_path,
                completed_terminal_packet(
                    plan,
                    "implementation",
                    projection,
                ),
            )
            assignment = next(
                item
                for item in plan["assignments"]
                if item["assignment_id"] == "implementation"
            )
            parent = start_run_observation(
                repo,
                run_id="assignment-turn",
                task_label="Assignment 기반 실행",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "interactive_required",
                    "evidence": "The parent test represents a Desktop orchestrator.",
                },
            )

            result = run_codex_host(
                repo,
                run_id="assignment-turn",
                task_label="Assignment 기반 실행",
                plan_path=plan_path,
                assignment_id="implementation",
                projection_path=projection_path,
                baseline_path=baseline_path,
                observation_id=parent["observation_id"],
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "success",
                    str(packet_path),
                ],
            )

            self.assertEqual("completed", result["status"])
            self.assertIsNotNone(result["packet_digest"])
            self.assertEqual("PASS", result["packet_validation"]["status"])
            self.assertTrue(result["output_schema_applied"])
            self.assertEqual("workspace-write", result["sandbox"])
            self.assertEqual(
                assignment["model_route"]["selected_model"],
                result["requested_model"],
            )
            self.assertEqual(
                assignment["model_route"]["reasoning_effort"],
                result["requested_reasoning_effort"],
            )
            observation = json.loads(
                (
                    repo
                    / ".maestro/state/inflight"
                    / f"{parent['observation_id']}.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(1, len(observation["stage_results"]))
            self.assertEqual(
                "codex_app_server",
                observation["stage_results"][0]["evidence_source"],
            )
            self.assertEqual(
                "gpt-5.6-terra",
                observation["stage_results"][0]["actual_model"],
            )
            self.assertEqual(
                "explicit_fallback",
                observation["execution_binding"]["mode"],
            )
            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="assignment-turn",
                    task_label="중복 실행 금지",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    observation_id=parent["observation_id"],
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "success",
                        str(packet_path),
                    ],
                )
            self.assertEqual(
                "CODEX_HOST_ASSIGNMENT_ALREADY_TERMINAL",
                raised.exception.code,
            )
            self.assertEqual(2, len(plan["assignments"]))
            record_stage_observation(
                repo,
                observation_id=parent["observation_id"],
                run_id="assignment-turn",
                assignment_id="verification",
                status="completed",
                evidence_source="deterministic_command",
                evidence_refs=["tests:codex-host-verification"],
            )
            finalize_run(
                repo,
                run_id="assignment-turn",
                observation_id=parent["observation_id"],
                outcome="completed",
                evidence_refs=["tests:codex-host-stage"],
                verifier_result="not_run",
                command_artifact_ref="tests:codex-host-stage",
            )
            recorded = snapshot_report(repo)["runs"][0]
            self.assertEqual(
                "observed_stages",
                recorded["token_scope"],
            )
            self.assertEqual(84, recorded["tokens"]["total"])
            self.assertEqual(
                ["gpt-5.6-terra"],
                recorded["models"]["applied"],
            )
            self.assertTrue(recorded["stage_coverage"]["complete"])
            self.assertTrue(recorded["stage_telemetry"]["complete"])
            self.assertEqual(
                1,
                recorded["stage_telemetry"]["model_measured"],
            )

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="sandbox-conflict",
                    task_label="충돌",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "success",
                        str(packet_path),
                    ],
                )
            self.assertEqual(
                "CODEX_HOST_SANDBOX_CONFLICT",
                raised.exception.code,
            )

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="prompt-conflict",
                    task_label="프롬프트 우회 금지",
                    prompt_file=prompt,
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "success",
                        str(packet_path),
                    ],
                )
            self.assertEqual(
                "CODEX_HOST_PROMPT_CONFLICT",
                raised.exception.code,
            )

            tampered = copy.deepcopy(projection)
            tampered["input"]["research_context"] = {"forged": True}
            tampered_path = root / "tampered-projection.json"
            write_json(tampered_path, tampered)
            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="projection-conflict",
                    task_label="투영 변조 금지",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=tampered_path,
                    baseline_path=baseline_path,
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "success",
                        str(packet_path),
                    ],
                )
            self.assertEqual(
                "CODEX_HOST_ASSIGNMENT_INPUT_MISMATCH",
                raised.exception.code,
            )

    def test_assignment_completion_requires_a_validated_output_packet(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _, server = self._project(root)
            plan = route_goal_v2(
                "Implement one local CLI behavior",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            baseline_path = root / "baseline.json"
            projection_path = root / "projection.json"
            write_json(plan_path, plan)
            baseline = baseline_for(plan)
            write_json(baseline_path, baseline)
            projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
            )
            self.assertEqual("PASS", projection["status"])
            write_json(projection_path, projection)

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="invalid-assignment-packet",
                    task_label="완료 패킷 검증",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_PACKET_INVALID",
                raised.exception.code,
            )
            observation_files = list(
                safe_target(repo, ".maestro/state/inflight").glob("*.json")
            )
            self.assertEqual(1, len(observation_files))
            observation = json.loads(
                observation_files[0].read_text(encoding="utf-8")
            )
            self.assertEqual(1, len(observation["stage_results"]))
            self.assertEqual(
                "failed",
                observation["stage_results"][0]["status"],
            )
            with self.assertRaises(MaestroError) as duplicate:
                run_codex_host(
                    repo,
                    run_id="invalid-assignment-packet",
                    task_label="완료 패킷 검증",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    observation_id=observation["observation_id"],
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_ASSIGNMENT_ALREADY_TERMINAL",
                duplicate.exception.code,
            )

    def test_dependent_assignment_requires_completed_parent_stage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _, server = self._project(root)
            plan = route_goal_v2(
                "Implement README contract behavior and verification",
                "medium",
                ["contract"],
                intent="implementation",
                repo_path=repo,
            )
            baseline = baseline_for(plan)
            review_projection = project_assignment_input(
                repo,
                plan,
                "review",
                baseline,
            )
            self.assertEqual("PASS", review_projection["status"])
            review_packet = finding_packet(plan, "review")
            implementation_projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
                dependency_packets=[review_packet],
                dependency_projections=[review_projection],
            )
            self.assertEqual("PASS", implementation_projection["status"])

            plan_path = root / "dependent-plan.json"
            baseline_path = root / "dependent-baseline.json"
            review_projection_path = root / "review-projection.json"
            review_packet_path = root / "review-packet.json"
            implementation_projection_path = (
                root / "implementation-projection.json"
            )
            write_json(plan_path, plan)
            write_json(baseline_path, baseline)
            write_json(review_projection_path, review_projection)
            write_json(review_packet_path, review_packet)
            write_json(
                implementation_projection_path,
                implementation_projection,
            )

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="dependency-order",
                    task_label="선행 단계 확인",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=implementation_projection_path,
                    baseline_path=baseline_path,
                    dependency_packet_paths=[review_packet_path],
                    dependency_projection_paths=[review_projection_path],
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_DEPENDENCIES_UNSATISFIED",
                raised.exception.code,
            )

            parent = start_run_observation(
                repo,
                run_id="dependency-evidence",
                task_label="dependency packet 결합",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "interactive_required",
                    "evidence": "The review stage was executed by the test host.",
                },
            )
            record_stage_observation(
                repo,
                observation_id=parent["observation_id"],
                run_id="dependency-evidence",
                assignment_id="review",
                status="completed",
                evidence_source="current_host",
                evidence_refs=["assignment-packet:" + "0" * 64],
            )
            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="dependency-evidence",
                    task_label="dependency packet 결합",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=implementation_projection_path,
                    baseline_path=baseline_path,
                    dependency_packet_paths=[review_packet_path],
                    dependency_projection_paths=[review_projection_path],
                    observation_id=parent["observation_id"],
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_DEPENDENCY_EVIDENCE_MISMATCH",
                raised.exception.code,
            )

    def test_open_research_gate_is_rejected_before_host_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            plan = route_goal_v2(
                "Find current references for a modern landing page design",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "open-plan.json"
            write_json(plan_path, plan)

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="open-research-gate",
                    task_label="리서치 전 실행 금지",
                    prompt_file=prompt,
                    plan_path=plan_path,
                    assignment_id=plan["assignments"][0]["assignment_id"],
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )

            self.assertEqual(
                "CODEX_HOST_PLAN_NOT_READY",
                raised.exception.code,
            )

    def test_plan_cannot_be_attached_to_arbitrary_standalone_prompt(
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

            with self.assertRaises(MaestroError) as raised:
                run_codex_host(
                    repo,
                    run_id="standalone-plan-bypass",
                    task_label="plan 우회 금지",
                    prompt_file=prompt,
                    plan_path=plan_path,
                    sandbox="workspace-write",
                    timeout_seconds=5,
                    command=[sys.executable, str(server), "success"],
                )
            self.assertEqual(
                "CODEX_HOST_ASSIGNMENT_REQUIRED",
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

    def test_unrelated_notifications_do_not_consume_the_semantic_run_budget(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            result = run_codex_host(
                repo,
                run_id="noisy-stream",
                task_label="노이즈가 많은 이벤트 스트림",
                prompt_file=prompt,
                sandbox="read-only",
                timeout_seconds=10,
                command=[sys.executable, str(server), "noisy"],
            )

            self.assertEqual("completed", result["status"])
            self.assertGreaterEqual(result["filtered_notifications"], 20_050)
            self.assertGreater(result["protocol_messages_seen"], 20_000)

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
        assignment_args = parser().parse_args(
            [
                "host",
                "codex",
                "--run-id",
                "run",
                "--task-label",
                "label",
                "--plan",
                "plan.json",
                "--assignment",
                "implementation",
                "--projection",
                "projection.json",
                "--baseline",
                "baseline.json",
                "--research-evidence",
                "research.json",
            ]
        )
        self.assertIsNone(assignment_args.prompt_file)
        self.assertEqual("projection.json", assignment_args.projection)
        self.assertEqual("baseline.json", assignment_args.baseline)

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
