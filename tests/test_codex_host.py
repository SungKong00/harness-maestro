from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.support import (
    ROOT,
    apply_fresh_init,
    record_managed_completion_graph,
    write_json,
)

from maestro.cli import main, parser
from maestro.assignment_contracts import (
    VERIFICATION_VERDICT_VERSION,
    project_assignment_input,
)
from maestro.codex_host import (
    _AppServer,
    _assert_scoped_repository_changes,
    _codex_error_identifier,
    _codex_runtime_binding,
    _host_assignment_lease,
    _host_contract,
    _quiesce_background_terminals,
    _record_dependency_handoff,
    _repository_change_snapshot,
    _same_runtime_workspace_roots,
    _shutdown_and_audit_scoped_host,
    _supports_scoped_enactment,
    _terminate_and_audit_scoped_server,
    _validate_managed_model_reroutes,
    run_codex_host,
)
from maestro.decisions import build_decision_plan, build_execution_plan
from maestro.errors import MaestroError
from maestro.evaluation_attestation import projected_evaluation_evidence_refs
from maestro.governance import _app_server_binding_error, finalize_run
from maestro.observations import (
    observation_receipt_fields,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.snapshot import snapshot_report
from maestro.util import canonical_json, safe_target, sha256_text
from maestro.work import build_work_graph
from tests.test_assignment_contracts import (
    baseline_for,
    completed_terminal_packet,
    finding_packet,
)
from tests.test_decision_workflow import _bundle, _packets


def expertise_dispositions(
    projection: dict[str, object],
    *,
    disposition: str,
    evidence_refs: list[str],
) -> list[dict[str, object]]:
    projected = projection["input"]
    return [
        {
            "expertise_pack_id": pack["expertise_pack_id"],
            "definition_digest": pack["definition_digest"],
            "guide_id": guide["guide_id"],
            "skill_definition_digest": guide[
                "skill_definition_digest"
            ],
            "disposition": disposition,
            "reason": "Used the exact projected Guide for this Assignment.",
            "evidence_refs": evidence_refs,
        }
        for pack in projected["expertise_load"]["packs"]
        for guide in pack["guides"]
    ]


FAKE_APP_SERVER = r"""
import json
import sys
import time

mode = sys.argv[1]
packet_path = (
    sys.argv[2]
    if len(sys.argv) > 2 and sys.argv[2] != "-"
    else None
)
cleanup_marker = sys.argv[3] if len(sys.argv) > 3 else None
thread_model = "gpt-default"
thread_effort = "medium"
background_terminal_active = mode == "scoped-cleanup"


def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        if mode in {"experimental", "scoped-cleanup"}:
            assert message["params"]["capabilities"]["experimentalApi"] is True
        opt_out = message["params"]["capabilities"][
            "optOutNotificationMethods"
        ]
        assert "item/agentMessage/delta" in opt_out
        assert "item/reasoning/textDelta" in opt_out
        emit({"jsonrpc": "2.0", "id": message["id"], "result": {}})
    elif method == "initialized":
        continue
    elif method == "thread/backgroundTerminals/list":
        assert message["params"]["threadId"] == "thread-1"
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "data": (
                        [
                            {
                                "itemId": "item-1",
                                "processId": "42",
                                "command": "background fixture",
                                "cwd": "/tmp",
                            }
                        ]
                        if background_terminal_active
                        else []
                    ),
                    "nextCursor": None,
                },
            }
        )
    elif method == "thread/backgroundTerminals/terminate":
        assert message["params"] == {
            "threadId": "thread-1",
            "processId": "42",
        }
        background_terminal_active = False
        if cleanup_marker is not None:
            with open(cleanup_marker, "w", encoding="utf-8") as marker:
                marker.write("thread-1:42")
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"terminated": True},
            }
        )
    elif method == "thread/start":
        params = message["params"]
        assert params["approvalPolicy"] == "never"
        assert params["ephemeral"] is True
        assert params["sandbox"] in {"read-only", "workspace-write"}
        assert params["runtimeWorkspaceRoots"]
        assert all(
            root.startswith("/")
            for root in params["runtimeWorkspaceRoots"]
        )
        thread_model = params.get("model") or thread_model
        thread_result = {
            "thread": {"id": "thread-1"},
            "reasoningEffort": thread_effort,
            "runtimeWorkspaceRoots": params[
                "runtimeWorkspaceRoots"
            ],
        }
        if mode != "no-response-model":
            thread_result["model"] = thread_model
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": thread_result,
            }
        )
    elif method == "turn/start":
        params = message["params"]
        assert params["approvalPolicy"] == "never"
        policy = params["sandboxPolicy"]
        assert params["runtimeWorkspaceRoots"]
        if policy["type"] == "readOnly":
            assert policy["networkAccess"] is False
        else:
            assert policy["type"] == "workspaceWrite"
            assert policy["networkAccess"] is False
            assert len(policy["writableRoots"]) == 1
            assert (
                policy["writableRoots"]
                == params["runtimeWorkspaceRoots"]
            )
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
    def test_evaluation_refs_only_come_from_completion_evidence(self) -> None:
        accepted = f"candidate-subject:{'a' * 64}"
        ignored = f"candidate-cases:{'b' * 64}"
        projection = {
            "task_contract": {"objective": ignored},
            "engineering_baseline": [
                {
                    "check_id": "behavior-contract",
                    "note": ignored,
                },
                {
                    "check_id": "completion-evidence",
                    "note": f"Bind {accepted}.",
                },
            ],
        }
        self.assertEqual(
            [accepted],
            projected_evaluation_evidence_refs(projection),
        )

    def test_codex_error_identifier_prefers_stable_host_metadata(self) -> None:
        self.assertEqual(
            "usageLimitExceeded",
            _codex_error_identifier(
                {
                    "message": "Account-specific detail must not be persisted.",
                    "codexErrorInfo": "usageLimitExceeded",
                }
            ),
        )
        self.assertEqual(
            "-32000",
            _codex_error_identifier({"code": -32000}),
        )
        self.assertEqual(
            "legacy-error",
            _codex_error_identifier("legacy-error"),
        )
        self.assertEqual(
            "unclassified",
            _codex_error_identifier({"message": "message only"}),
        )

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

    @staticmethod
    def _typed_model_contract() -> dict:
        return {
            "schema_version": "maestro_model_execution_contract_v1",
            "assignment_id": "implementation",
            "model_route_id": "a" * 64,
            "execution_unit_id": "implementation",
            "stage_kind": "implementation",
            "enforcement": "typed-quality-floor",
            "selected_class": "economy",
            "selected_model": "gpt-5.6-luna",
            "reasoning_effort": "high",
            "quality_floor": {
                "acceptable_routes": [
                    {
                        "selected_class": "economy",
                        "reasoning_effort": "high",
                    },
                    {
                        "selected_class": "balanced",
                        "reasoning_effort": "medium",
                    },
                ],
                "failure_action": "reject-or-reroute",
            },
            "fallback_route": {
                "selected_class": "balanced",
                "selected_model": "gpt-5.6-terra",
                "reasoning_effort": "medium",
                "trigger": "selected-model-unavailable",
            },
        }

    def test_typed_model_contract_accepts_only_its_explicit_fallback(
        self,
    ) -> None:
        applied = _validate_managed_model_reroutes(
            self._typed_model_contract(),
            requested_model="gpt-5.6-luna",
            provider_reported_model="gpt-5.6-luna",
            reroutes=[
                {
                    "from_model": "gpt-5.6-luna",
                    "to_model": "gpt-5.6-terra",
                    "reason": "capacity",
                }
            ],
        )

        self.assertEqual("gpt-5.6-terra", applied)

    def test_typed_model_contract_rejects_quality_floor_downgrade(
        self,
    ) -> None:
        with self.assertRaises(MaestroError) as raised:
            _validate_managed_model_reroutes(
                self._typed_model_contract(),
                requested_model="gpt-5.6-luna",
                provider_reported_model="gpt-5.6-luna",
                reroutes=[
                    {
                        "from_model": "gpt-5.6-luna",
                        "to_model": "gpt-5.6-nano",
                        "reason": "capacity",
                    }
                ],
            )

        self.assertEqual(
            "CODEX_HOST_QUALITY_FLOOR_VIOLATION",
            raised.exception.code,
        )

    def test_quality_escalation_cannot_masquerade_as_operational_fallback(
        self,
    ) -> None:
        contract = self._typed_model_contract()
        with self.assertRaises(MaestroError) as raised:
            _validate_managed_model_reroutes(
                contract,
                requested_model="gpt-5.6-luna",
                provider_reported_model="gpt-5.6-luna",
                reroutes=[
                    {
                        "from_model": "gpt-5.6-luna",
                        "to_model": "gpt-5.6-terra",
                        "reason": "quality_escalation",
                    }
                ],
            )

        self.assertEqual(
            "CODEX_HOST_MODEL_TRANSITION_KIND_CONFLICT",
            raised.exception.code,
        )

    def test_legacy_model_contract_preserves_reroute_compatibility(
        self,
    ) -> None:
        applied = _validate_managed_model_reroutes(
            {
                "schema_version": "maestro_model_execution_contract_v1",
                "enforcement": "legacy-exact-request",
            },
            requested_model="gpt-5.6-sol",
            provider_reported_model="gpt-5.6-sol",
            reroutes=[
                {
                    "from_model": "gpt-5.6-sol",
                    "to_model": "gpt-5.6-terra",
                    "reason": "legacy-host-policy",
                }
            ],
        )

        self.assertEqual("gpt-5.6-terra", applied)

    def test_runtime_binding_loads_the_experimental_scope_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "codex"
            executable.write_text(
                """#!/usr/bin/env python3
import pathlib
import sys

if sys.argv[1:] == ["--version"]:
    print("codex-cli test")
    raise SystemExit(0)
if "--experimental" not in sys.argv:
    raise SystemExit(7)
output = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
files = {
    "v1/InitializeParams.json": '"experimentalApi"',
    "v2/ThreadStartParams.json": '"runtimeWorkspaceRoots"',
    "v2/ThreadStartResponse.json": '"runtimeWorkspaceRoots"',
    "v2/TurnStartParams.json": '"runtimeWorkspaceRoots"',
    "ClientRequest.json": (
        '"thread/backgroundTerminals/clean"'
        '"thread/backgroundTerminals/list"'
        '"thread/backgroundTerminals/terminate"'
        '"turn/interrupt"'
    ),
    "v2/ThreadBackgroundTerminalsCleanParams.json": '"threadId"',
    "v2/ThreadBackgroundTerminalsCleanResponse.json": '{}',
    "v2/ThreadBackgroundTerminalsListParams.json": (
        '"threadId""cursor""limit"'
    ),
    "v2/ThreadBackgroundTerminalsListResponse.json": (
        '"data""processId""nextCursor"'
    ),
    "v2/ThreadBackgroundTerminalsTerminateParams.json": (
        '"threadId""processId"'
    ),
    "v2/ThreadBackgroundTerminalsTerminateResponse.json": '"terminated"',
    "v2/TurnInterruptParams.json": '"threadId""turnId"',
    "v2/TurnInterruptResponse.json": '{}',
}
for relative, content in files.items():
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
""",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            _codex_runtime_binding.cache_clear()
            try:
                binding = _codex_runtime_binding(str(executable))
            finally:
                _codex_runtime_binding.cache_clear()
        self.assertTrue(binding["experimental_api"])
        self.assertTrue(binding["runtime_workspace_roots"])
        self.assertTrue(binding["background_terminal_control"])
        self.assertTrue(binding["turn_interrupt"])

    def test_runtime_workspace_root_confirmation_rejects_broader_scope(
        self,
    ) -> None:
        expected = ["/repo/src", "/repo/tests"]
        self.assertTrue(
            _same_runtime_workspace_roots(
                ["/repo/tests", "/repo/src"],
                expected,
            )
        )
        self.assertFalse(
            _same_runtime_workspace_roots(
                ["/repo", "/repo/src", "/repo/tests"],
                expected,
            )
        )

    def test_scoped_enactment_requires_process_group_quiescence(
        self,
    ) -> None:
        binding = {
            "experimental_api": True,
            "runtime_workspace_roots": True,
            "background_terminal_control": True,
            "turn_interrupt": True,
        }
        with patch(
            "maestro.codex_host._scoped_process_quiescence_supported",
            return_value=False,
        ):
            self.assertFalse(_supports_scoped_enactment(binding))

    def test_experimental_workspace_roots_are_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, prompt, server = self._project(Path(temporary))
            with patch(
                "maestro.codex_host._codex_runtime_binding",
                return_value={
                    "version": "codex-cli test",
                    "schema_digest": "a" * 64,
                    "capability": "full_stream",
                    "experimental_api": True,
                    "runtime_workspace_roots": True,
                },
            ):
                result = run_codex_host(
                    repo,
                    run_id="experimental-roots",
                    task_label="experimental roots",
                    prompt_file=prompt,
                    sandbox="read-only",
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "experimental",
                    ],
                )
        self.assertEqual("completed", result["status"])

    def test_scoped_host_cleans_the_exact_returned_thread_before_audit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)
            allowed = repo / "allowed"
            allowed.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Maestro Test",
                    "-c",
                    "user.email=maestro@example.invalid",
                    "commit",
                    "-qm",
                    "baseline",
                ],
                check=True,
            )
            contract = _host_contract(
                repo,
                plan_path=None,
                assignment_id=None,
                projection_path=None,
                baseline_path=None,
                document_paths=(),
                dependency_packet_paths=(),
                dependency_projection_paths=(),
                research_evidence_path=None,
                coverage_path=None,
                coverage_admission_path=None,
                coverage_projection_path=None,
                expertise_work_plan_path=None,
                expertise_closure_path=None,
                sandbox="workspace-write",
                model=None,
                reasoning_effort=None,
            )
            contract["scoped_write_roots"] = True
            contract["runtime_workspace_roots"] = [
                str(allowed.resolve())
            ]
            contract["sandbox_policy"]["writableRoots"] = [
                str(allowed.resolve())
            ]
            cleanup_marker = root / "cleanup-marker.txt"
            with (
                patch(
                    "maestro.codex_host._host_contract",
                    return_value=contract,
                ),
                patch(
                    "maestro.codex_host._codex_runtime_binding",
                    return_value={
                        "version": "codex-cli test",
                        "schema_digest": "a" * 64,
                        "capability": "full_stream",
                        "experimental_api": True,
                        "runtime_workspace_roots": True,
                        "background_terminal_control": True,
                        "turn_interrupt": True,
                    },
                ),
            ):
                result = run_codex_host(
                    repo,
                    run_id="scoped-thread-cleanup",
                    task_label="scoped cleanup",
                    prompt_file=prompt,
                    sandbox="workspace-write",
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "scoped-cleanup",
                        "-",
                        str(cleanup_marker),
                    ],
                )
            cleanup_evidence = cleanup_marker.read_text(encoding="utf-8")
        self.assertEqual("completed", result["status"])
        self.assertEqual("thread-1:42", cleanup_evidence)

    def test_decision_host_contract_uses_exact_runtime_workspace_roots(
        self,
    ) -> None:
        goal = "Implement one local CLI behavior"
        plan = build_decision_plan(ROOT, goal, "medium")
        packets = _packets(plan)
        execution = build_execution_plan(
            ROOT,
            plan,
            _bundle(plan, packets),
            packets,
            authorization_source="prior_explicit_request",
        )
        assignment_id = execution["route_plan"][
            "mutation_owner_assignment_id"
        ]
        baseline = baseline_for(execution["route_plan"])
        projection = project_assignment_input(
            ROOT,
            execution,
            assignment_id,
            baseline,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "execution.json"
            projection_path = root / "projection.json"
            baseline_path = root / "baseline.json"
            write_json(plan_path, execution)
            write_json(projection_path, projection)
            write_json(baseline_path, baseline)

            contract = _host_contract(
                ROOT,
                plan_path=plan_path,
                assignment_id=assignment_id,
                projection_path=projection_path,
                baseline_path=baseline_path,
                document_paths=(),
                dependency_packet_paths=(),
                dependency_projection_paths=(),
                research_evidence_path=None,
                coverage_path=None,
                coverage_admission_path=None,
                coverage_projection_path=None,
                expertise_work_plan_path=None,
                expertise_closure_path=None,
                sandbox=None,
                model=None,
                reasoning_effort=None,
            )

        self.assertTrue(contract["scoped_write_roots"])
        self.assertEqual(
            [str((ROOT / "src").resolve()), str((ROOT / "tests").resolve())],
            contract["runtime_workspace_roots"],
        )
        self.assertEqual(
            contract["runtime_workspace_roots"],
            contract["sandbox_policy"]["writableRoots"],
        )

    def test_scoped_change_audit_rejects_sibling_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "allowed").mkdir()
            (repo / "sibling").mkdir()
            (repo / "allowed" / "file.txt").write_text(
                "before\n",
                encoding="utf-8",
            )
            (repo / "sibling" / "file.txt").write_text(
                "before\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Maestro Test",
                    "-c",
                    "user.email=maestro@example.invalid",
                    "commit",
                    "-qm",
                    "baseline",
                ],
                check=True,
            )
            before = _repository_change_snapshot(repo)
            (repo / "allowed" / "file.txt").write_text(
                "allowed change\n",
                encoding="utf-8",
            )
            _assert_scoped_repository_changes(
                repo,
                before=before,
                allowed_roots=[str((repo / "allowed").resolve())],
            )
            (repo / "allowed" / "file.txt").write_text(
                "before\n",
                encoding="utf-8",
            )
            before = _repository_change_snapshot(repo)
            (repo / "sibling" / "file.txt").write_text(
                "unauthorized change\n",
                encoding="utf-8",
            )
            with self.assertRaises(MaestroError) as raised:
                _assert_scoped_repository_changes(
                    repo,
                    before=before,
                    allowed_roots=[str((repo / "allowed").resolve())],
                )
            self.assertEqual(
                "CODEX_HOST_SCOPE_VIOLATION",
                raised.exception.code,
            )

    def test_scoped_change_audit_rejects_a_committed_head_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "allowed").mkdir()
            (repo / "sibling").mkdir()
            (repo / "sibling" / "file.txt").write_text(
                "before\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
            )
            identity = [
                "-c",
                "user.name=Maestro Test",
                "-c",
                "user.email=maestro@example.invalid",
            ]
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    *identity,
                    "commit",
                    "-qm",
                    "baseline",
                ],
                check=True,
            )
            before = _repository_change_snapshot(repo)
            (repo / "sibling" / "file.txt").write_text(
                "committed sibling change\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    *identity,
                    "commit",
                    "-qm",
                    "unauthorized",
                ],
                check=True,
            )
            with self.assertRaises(MaestroError) as raised:
                _assert_scoped_repository_changes(
                    repo,
                    before=before,
                    allowed_roots=[str((repo / "allowed").resolve())],
                )
            self.assertEqual(
                "CODEX_HOST_SCOPE_VIOLATION",
                raised.exception.code,
            )

    def test_scope_audit_runs_only_after_server_termination(self) -> None:
        events: list[str] = []

        class Server:
            deadline = time.monotonic() + 5

            def close(self) -> bool:
                events.append("close")
                return True

        with (
            patch(
                "maestro.codex_host._quiesce_background_terminals",
                side_effect=lambda *args, **kwargs: events.append(
                    "background-terminals"
                ),
            ),
            patch(
                "maestro.codex_host._assert_scoped_repository_changes",
                side_effect=lambda *args, **kwargs: events.append("audit"),
            ),
        ):
            _terminate_and_audit_scoped_server(
                Server(),
                ROOT,
                before={"head": "a" * 40, "paths": {}},
                allowed_roots=[str((ROOT / "src").resolve())],
                thread_ids=["thread-1", "child-thread-1"],
            )
        self.assertEqual(
            [
                "background-terminals",
                "background-terminals",
                "close",
                "audit",
            ],
            events,
        )

    def test_scope_shutdown_interrupts_an_active_turn_before_cleanup(
        self,
    ) -> None:
        events: list[str] = []

        class Server:
            deadline = time.monotonic() + 5

            def __init__(self) -> None:
                self.notifications: list[dict[str, object]] = []

            def send(self, request: dict[str, object]) -> None:
                events.append(request["method"])

            def response(self, request_id: int) -> dict[str, object]:
                self.notifications.append(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {
                                "id": "turn-1",
                                "status": "interrupted",
                            },
                        },
                    }
                )
                return {}

            def close(self) -> bool:
                events.append("close")
                return True

        with (
            patch(
                "maestro.codex_host._quiesce_background_terminals",
                side_effect=lambda *args, **kwargs: events.append(
                    "background-terminals"
                ),
            ),
            patch(
                "maestro.codex_host._assert_scoped_repository_changes",
                side_effect=lambda *args, **kwargs: events.append("audit"),
            ),
        ):
            _terminate_and_audit_scoped_server(
                Server(),
                ROOT,
                before={"head": "a" * 40, "paths": {}},
                allowed_roots=[str((ROOT / "src").resolve())],
                thread_ids=["thread-1"],
                active_turn=("thread-1", "turn-1"),
            )
        self.assertEqual(
            [
                "turn/interrupt",
                "background-terminals",
                "close",
                "audit",
            ],
            events,
        )

    def test_scope_shutdown_fails_closed_without_terminal_interrupt(
        self,
    ) -> None:
        events: list[str] = []

        class Server:
            deadline = time.monotonic() + 5
            notifications: list[dict[str, object]] = []

            def send(self, request: dict[str, object]) -> None:
                events.append(request["method"])

            def response(self, request_id: int) -> dict[str, object]:
                return {}

            def next_message(self, **kwargs: object) -> None:
                return None

            def close(self) -> bool:
                events.append("close")
                return True

        with (
            patch(
                "maestro.codex_host._quiesce_background_terminals",
                side_effect=lambda *args, **kwargs: events.append(
                    "background-terminals"
                ),
            ),
            patch(
                "maestro.codex_host._assert_scoped_repository_changes",
                side_effect=lambda *args, **kwargs: events.append("audit"),
            ),
            self.assertRaises(MaestroError) as raised,
        ):
            _terminate_and_audit_scoped_server(
                Server(),
                ROOT,
                before={"head": "a" * 40, "paths": {}},
                allowed_roots=[str((ROOT / "src").resolve())],
                thread_ids=["thread-1"],
                active_turn=("thread-1", "turn-1"),
            )
        self.assertEqual(
            "CODEX_HOST_BACKGROUND_TERMINALS_UNQUIESCED",
            raised.exception.code,
        )
        self.assertEqual(["turn/interrupt", "close"], events)

    def test_unconfirmed_turn_start_never_reaches_scope_audit(
        self,
    ) -> None:
        events: list[str] = []

        class Server:
            deadline = time.monotonic() - 1

            def close(self) -> bool:
                events.append("close")
                return True

        state = {
            "thread_id": "thread-1",
            "turn_id": None,
            "turn_start_requested": True,
            "completion": None,
            "child_work_runtime": {},
        }
        with (
            patch(
                "maestro.codex_host._terminate_and_audit_scoped_server",
                side_effect=lambda *args, **kwargs: events.append("audit"),
            ),
            self.assertRaises(MaestroError) as raised,
        ):
            _shutdown_and_audit_scoped_host(
                Server(),
                ROOT,
                state=state,
                before={"head": "a" * 40, "paths": {}},
                allowed_roots=[str((ROOT / "src").resolve())],
            )
        self.assertEqual(
            "CODEX_HOST_BACKGROUND_TERMINALS_UNQUIESCED",
            raised.exception.code,
        )
        self.assertEqual(["close"], events)

    @unittest.skipUnless(
        sys.platform != "win32",
        "POSIX process-group termination is required.",
    )
    def test_app_server_close_terminates_background_children(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            late_file = root / "late-write.txt"
            parent = root / "parent.py"
            parent.write_text(
                """import subprocess
import sys

subprocess.Popen(
    [
        sys.executable,
        "-c",
        (
            "import pathlib,sys,time;"
            "time.sleep(0.3);"
            "pathlib.Path(sys.argv[1]).write_text('late', encoding='utf-8')"
        ),
        sys.argv[1],
    ]
)
""",
                encoding="utf-8",
            )
            server = _AppServer(
                [sys.executable, str(parent), str(late_file)],
                cwd=root,
                deadline=time.monotonic() + 5,
            )
            time.sleep(0.05)
            self.assertTrue(server.close())
            time.sleep(0.4)
            self.assertFalse(late_file.exists())

    @unittest.skipUnless(
        sys.platform != "win32",
        "POSIX detached-process termination is required.",
    )
    def test_background_terminal_control_stops_detached_children(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            late_file = root / "detached-late-write.txt"
            app_server = root / "detached_app_server.py"
            app_server.write_text(
                """import json
import os
import signal
import subprocess
import sys

late_file = sys.argv[1]
child = subprocess.Popen(
    [
        sys.executable,
        "-c",
        (
            "import pathlib,sys,time;"
            "time.sleep(0.4);"
            "pathlib.Path(sys.argv[1]).write_text('late', encoding='utf-8')"
        ),
        late_file,
    ],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)


def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "thread/backgroundTerminals/list":
        running = child is not None and child.poll() is None
        data = (
            [
                {
                    "itemId": "item-1",
                    "processId": "42",
                    "command": "late writer",
                    "cwd": os.getcwd(),
                }
            ]
            if running
            else []
        )
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"data": data, "nextCursor": None},
            }
        )
    elif method == "thread/backgroundTerminals/terminate":
        assert message["params"] == {
            "threadId": "thread-1",
            "processId": "42",
        }
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=2)
        child = None
        emit(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"terminated": True},
            }
        )
""",
                encoding="utf-8",
            )
            server = _AppServer(
                [
                    sys.executable,
                    str(app_server),
                    str(late_file),
                ],
                cwd=root,
                deadline=time.monotonic() + 5,
            )
            server.deadline = time.monotonic() - 1
            with patch(
                "maestro.codex_host._assert_scoped_repository_changes"
            ):
                _terminate_and_audit_scoped_server(
                    server,
                    root,
                    before={"head": None, "paths": {}},
                    allowed_roots=[str(root.resolve())],
                    thread_ids=["thread-1"],
                )
            time.sleep(0.5)
            self.assertFalse(late_file.exists())

    def test_background_terminal_cleanup_handles_exit_race_and_new_process(
        self,
    ) -> None:
        class Server:
            def __init__(self) -> None:
                self.requests: dict[int, dict[str, object]] = {}
                self.list_calls = 0
                self.terminated: list[str] = []

            def send(self, request: dict[str, object]) -> None:
                self.requests[request["id"]] = request

            def response(self, request_id: int) -> dict[str, object]:
                request = self.requests[request_id]
                if request["method"] == (
                    "thread/backgroundTerminals/list"
                ):
                    pages = [
                        [{"processId": "natural-exit"}],
                        [{"processId": "new-process"}],
                        [],
                    ]
                    data = pages[self.list_calls]
                    self.list_calls += 1
                    return {"data": data, "nextCursor": None}
                params = request["params"]
                process_id = params["processId"]
                self.terminated.append(process_id)
                return {"terminated": process_id == "new-process"}

        server = Server()
        self.assertEqual(
            2,
            _quiesce_background_terminals(server, "thread-1"),
        )
        self.assertEqual(
            ["natural-exit", "new-process"],
            server.terminated,
        )

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

    def test_owned_turn_does_not_copy_request_into_missing_applied_model(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, prompt, server = self._project(root)

            result = run_codex_host(
                repo,
                run_id="request-only-model",
                task_label="적용 모델 누락 보존",
                prompt_file=prompt,
                sandbox="read-only",
                model="gpt-5.6-terra",
                reasoning_effort="high",
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "no-response-model",
                ],
            )

            self.assertEqual("gpt-5.6-terra", result["requested_model"])
            self.assertEqual("high", result["requested_reasoning_effort"])
            self.assertIsNone(result["applied_model"])
            self.assertNotIn("applied_reasoning_effort", result)
            self.assertEqual(
                "request_only",
                result["host_observation"]["model_event_evidence"],
            )
            self.assertIsNone(
                result["host_observation"]["applied_model"]
            )

    def test_successful_app_server_binding_accepts_only_bounded_request_only(
        self,
    ) -> None:
        binding = {
            "schema_version": "maestro_execution_binding_v1",
            "mode": "maestro_owned_codex_app_server",
        }
        request_only = {
            "evidence_source": "codex_app_server",
            "model_evidence": "request_only",
        }
        unavailable = {
            "evidence_source": "codex_app_server",
            "model_evidence": "unavailable",
        }

        self.assertIsNone(
            _app_server_binding_error(
                binding,
                [request_only],
                outcome="completed",
            )
        )
        self.assertIsNotNone(
            _app_server_binding_error(
                binding,
                [unavailable],
                outcome="completed",
            )
        )

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
            verification_projection = project_assignment_input(
                repo,
                plan,
                "verification",
                baseline,
                dependency_packets=[
                    json.loads(packet_path.read_text(encoding="utf-8"))
                ],
                dependency_projections=[projection],
            )
            self.assertEqual("PASS", verification_projection["status"])
            verification_projection_path = (
                root / "verification-projection.json"
            )
            verification_packet_path = root / "verification-packet.json"
            write_json(
                verification_projection_path,
                verification_projection,
            )
            verification_target = verification_projection["input"][
                "verification_target"
            ]
            write_json(
                verification_packet_path,
                {
                    "schema_version": VERIFICATION_VERDICT_VERSION,
                    "plan_id": plan["plan_id"],
                    "assignment_id": "verification",
                    "packet_type": "VerificationVerdict",
                    "target_assignment_id": verification_target[
                        "assignment_id"
                    ],
                    "target_execution_unit_id": verification_target[
                        "execution_unit_id"
                    ],
                    "target_model_route_id": verification_target[
                        "model_route_id"
                    ],
                    "verdict": "passed",
                    "failure_cause": "none",
                    "failure_categories": [],
                    "evidence_refs": ["readme"],
                    "summary": "The implementation passed verification.",
                    "writes_performed": False,
                },
            )
            assignment = next(
                item
                for item in plan["assignments"]
                if item["assignment_id"] == "implementation"
            )
            parent = start_run_observation(
                repo,
                run_id="assignment-turn",
                request_key="assignment-turn",
                task_label="Assignment 기반 실행",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "desktop_request",
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
            self.assertEqual(
                assignment["model_route"].get("model_route_id"),
                result["model_route_id"],
            )
            self.assertEqual(
                assignment["model_route"].get("execution_unit_id"),
                result["execution_unit_id"],
            )
            self.assertNotIn("applied_reasoning_effort", result)
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
            if assignment["model_route"].get("model_route_id") is not None:
                self.assertEqual(
                    assignment["model_route"]["model_route_id"],
                    observation["stage_results"][0]["model_route_id"],
                )
                self.assertEqual(
                    assignment["model_route"]["execution_unit_id"],
                    observation["stage_results"][0][
                        "execution_unit_id"
                    ],
                )
            self.assertNotIn(
                "applied_reasoning_effort",
                observation["stage_results"][0],
            )
            self.assertEqual(
                "maestro_owned_codex_app_server",
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
            verification_result = run_codex_host(
                repo,
                run_id="assignment-turn",
                task_label="Assignment 검증 실행",
                plan_path=plan_path,
                assignment_id="verification",
                projection_path=verification_projection_path,
                baseline_path=baseline_path,
                dependency_packet_paths=[packet_path],
                dependency_projection_paths=[projection_path],
                observation_id=parent["observation_id"],
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "success",
                    str(verification_packet_path),
                ],
            )
            self.assertEqual("completed", verification_result["status"])
            self.assertIsNotNone(
                verification_result["execution_unit_receipt"]
            )
            record_managed_completion_graph(
                repo,
                observation_id=parent["observation_id"],
                run_id="assignment-turn",
                plan=plan,
            )
            finalize_run(
                repo,
                run_id="assignment-turn",
                observation_id=parent["observation_id"],
                outcome="completed",
                evidence_refs=["tests:codex-host-stage"],
                verifier_result="passed",
                command_artifact_ref="tests:codex-host-stage",
            )
            recorded = snapshot_report(repo)["runs"][0]
            self.assertEqual(
                "observed_stages",
                recorded["token_scope"],
            )
            self.assertEqual(168, recorded["tokens"]["total"])
            self.assertEqual(
                ["gpt-5.6-terra"],
                recorded["models"]["applied"],
            )
            self.assertTrue(recorded["stage_coverage"]["complete"])
            self.assertTrue(recorded["stage_telemetry"]["complete"])
            self.assertEqual(
                2,
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

    def test_read_only_evaluation_binds_projected_lifecycle_refs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _, server = self._project(root)
            plan = route_goal_v2(
                "Review the README contract",
                "medium",
                ["contract"],
                intent="review",
                repo_path=repo,
            )
            plan_path = root / "evaluation-plan.json"
            write_json(plan_path, plan)
            baseline = baseline_for(plan)
            expected_refs = [
                f"candidate-subject:{'a' * 64}",
                f"candidate-cases:{'b' * 64}",
                f"candidate-quality:{'c' * 64}",
            ]
            completion_check = next(
                check
                for check in baseline["checks"]
                if check["check_id"] == "completion-evidence"
            )
            completion_check["note"] = (
                "Bind the exact frozen evaluation inputs and result: "
                + ", ".join(expected_refs)
            )
            baseline_path = root / "evaluation-baseline.json"
            write_json(baseline_path, baseline)
            projection = project_assignment_input(
                repo,
                plan,
                "review",
                baseline,
            )
            self.assertEqual("PASS", projection["status"])
            projection_path = root / "evaluation-projection.json"
            write_json(projection_path, projection)
            packet_path = root / "evaluation-packet.json"
            write_json(packet_path, finding_packet(plan, "review"))
            parent = start_run_observation(
                repo,
                run_id="detached-evaluation",
                request_key="detached-evaluation",
                task_label="Frozen candidate evaluation",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "desktop_request",
                },
            )

            result = run_codex_host(
                repo,
                run_id="detached-evaluation",
                task_label="Frozen candidate evaluation",
                plan_path=plan_path,
                assignment_id="review",
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
            observation = observation_receipt_fields(
                repo,
                observation_id=parent["observation_id"],
                run_id="detached-evaluation",
            )
            recorded_refs = observation["stage_results"][0][
                "evidence_refs"
            ]
            self.assertEqual(6, len(recorded_refs))
            self.assertTrue(recorded_refs[0].startswith("codex-app-server:"))
            self.assertTrue(recorded_refs[1].startswith("assignment-input:"))
            self.assertTrue(recorded_refs[2].startswith("assignment-packet:"))
            self.assertEqual(expected_refs, recorded_refs[3:])
            self.assertEqual(
                "codex_app_server",
                observation["stage_results"][0]["evidence_source"],
            )

    def test_assignment_rejects_model_and_reasoning_request_conflicts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _, _ = self._project(root)
            plan = route_goal_v2(
                "Implement one local CLI behavior",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            assignment = next(
                item
                for item in plan["assignments"]
                if item["assignment_id"] == "implementation"
            )
            baseline = baseline_for(plan)
            projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
            )
            plan_path = root / "plan.json"
            baseline_path = root / "baseline.json"
            projection_path = root / "projection.json"
            write_json(plan_path, plan)
            write_json(baseline_path, baseline)
            write_json(projection_path, projection)
            arguments = {
                "plan_path": plan_path,
                "assignment_id": "implementation",
                "projection_path": projection_path,
                "baseline_path": baseline_path,
                "document_paths": (),
                "dependency_packet_paths": (),
                "dependency_projection_paths": (),
                "research_evidence_path": None,
                "coverage_path": None,
                "coverage_admission_path": None,
                "coverage_projection_path": None,
                "expertise_work_plan_path": None,
                "expertise_closure_path": None,
                "sandbox": None,
            }
            selected_model = assignment["model_route"]["selected_model"]
            conflicting_model = (
                "gpt-5.6-sol"
                if selected_model != "gpt-5.6-sol"
                else "gpt-5.6-luna"
            )
            with self.assertRaises(MaestroError) as model_error:
                _host_contract(
                    repo,
                    **arguments,
                    model=conflicting_model,
                    reasoning_effort=None,
                )
            self.assertEqual(
                "CODEX_HOST_MODEL_CONFLICT",
                model_error.exception.code,
            )

            selected_effort = assignment["model_route"][
                "reasoning_effort"
            ]
            conflicting_effort = (
                "low" if selected_effort != "low" else "high"
            )
            with self.assertRaises(MaestroError) as effort_error:
                _host_contract(
                    repo,
                    **arguments,
                    model=None,
                    reasoning_effort=conflicting_effort,
                )
            self.assertEqual(
                "CODEX_HOST_REASONING_CONFLICT",
                effort_error.exception.code,
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
            self.assertIn(
                "effect-state:unknown",
                observation["stage_results"][0]["evidence_refs"],
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

    def test_assignment_stream_crash_freezes_unknown_effect_terminal(
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
                    run_id="crashed-assignment",
                    task_label="중단된 writer 증거",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "incomplete",
                    ],
                )
            self.assertEqual("CODEX_HOST_EXITED", raised.exception.code)

            observation_files = list(
                safe_target(repo, ".maestro/state/inflight").glob("*.json")
            )
            self.assertEqual(1, len(observation_files))
            observation = json.loads(
                observation_files[0].read_text(encoding="utf-8")
            )
            stage = observation["stage_results"][0]
            self.assertEqual("failed", stage["status"])
            self.assertEqual("unavailable", stage["model_evidence"])
            self.assertIn("effect-state:unknown", stage["evidence_refs"])

            with self.assertRaises(MaestroError) as duplicate:
                run_codex_host(
                    repo,
                    run_id="crashed-assignment",
                    task_label="중단된 writer 재실행 금지",
                    plan_path=plan_path,
                    assignment_id="implementation",
                    projection_path=projection_path,
                    baseline_path=baseline_path,
                    observation_id=observation["observation_id"],
                    timeout_seconds=5,
                    command=[
                        sys.executable,
                        str(server),
                        "success",
                    ],
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
            review_packet["expertise_dispositions"] = (
                expertise_dispositions(
                    review_projection,
                    disposition="consulted",
                    evidence_refs=["readme"],
                )
            )
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
                request_key="dependency-evidence",
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
                "RUN_EXECUTION_BINDING_CONFLICT",
                raised.exception.code,
            )

    def test_dependency_handoff_retry_finishes_matching_running_work(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _, _server = self._project(root)
            plan = route_goal_v2(
                "Recover one deterministic dependency handoff",
                "medium",
                ["contract"],
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "handoff-recovery-plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="handoff-recovery",
                request_key="handoff-recovery",
                task_label="dependency handoff 복구",
                plan_path=plan_path,
            )
            dependency = plan["assignments"][0]
            record_work_start(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
                work_id="dependency-terminal",
                assignment_id=dependency["assignment_id"],
                kind=dependency["kind"],
                role="dependency fixture",
                executor_id=dependency["executor_id"],
                task_summary="Produce dependency evidence.",
                read_only=dependency["read_only"],
                source="host_adapter",
            )
            record_work_finish(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
                work_id="dependency-terminal",
                status="completed",
                result_summary="Dependency evidence completed.",
                evidence_refs=["tests:handoff-recovery"],
            )
            record_work_start(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
                work_id="dependency-terminal-two",
                assignment_id=dependency["assignment_id"],
                kind=dependency["kind"],
                role="parallel dependency fixture",
                executor_id=dependency["executor_id"],
                task_summary="Produce a second dependency result.",
                read_only=dependency["read_only"],
                source="host_adapter",
            )
            record_work_finish(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
                work_id="dependency-terminal-two",
                status="completed",
                result_summary="Second dependency result completed.",
                evidence_refs=["tests:handoff-recovery-two"],
            )
            observed = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
            )
            arguments = {
                "observation": observed,
                "run_id": "handoff-recovery",
                "downstream_assignment_id": "downstream",
                "dependency_assignment_ids": [dependency["assignment_id"]],
                "dependency_packet_digests": {
                    dependency["assignment_id"]: "a" * 64,
                },
            }
            with patch(
                "maestro.codex_host.record_work_finish",
                side_effect=OSError("simulated handoff crash"),
            ):
                with self.assertRaises(OSError):
                    _record_dependency_handoff(repo, **arguments)

            crashed = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
            )
            running = next(
                span
                for span in crashed["work_spans"]
                if span["kind"] == "synthesis"
                and span["assignment_id"] is None
            )
            self.assertEqual("running", running["status"])

            recovered_id = _record_dependency_handoff(
                repo,
                **{**arguments, "observation": crashed},
            )
            recovered = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="handoff-recovery",
            )
            handoff = next(
                span
                for span in recovered["work_spans"]
                if span["work_id"] == recovered_id
            )
            self.assertEqual("completed", handoff["status"])
            self.assertEqual(
                [
                    "dependency-terminal",
                    "dependency-terminal-two",
                ],
                handoff["joins_work_ids"],
            )
            self.assertEqual(
                [
                    "dependency-terminal",
                    "dependency-terminal-two",
                ],
                handoff["outcome"]["consumed_work_ids"],
            )

    def test_dependent_assignment_records_handoff_and_raw_causal_edges(
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
            review_packet = finding_packet(plan, "review")
            review_packet["expertise_dispositions"] = (
                expertise_dispositions(
                    review_projection,
                    disposition="consulted",
                    evidence_refs=["readme"],
                )
            )
            implementation_projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
                dependency_packets=[review_packet],
                dependency_projections=[review_projection],
            )
            implementation_packet = completed_terminal_packet(
                plan,
                "implementation",
                implementation_projection,
            )
            implementation_packet["expertise_dispositions"] = (
                expertise_dispositions(
                    implementation_projection,
                    disposition="applied",
                    evidence_refs=implementation_packet[
                        "evidence_refs"
                    ],
                )
            )
            plan_path = root / "handoff-plan.json"
            baseline_path = root / "handoff-baseline.json"
            review_projection_path = root / "handoff-review-projection.json"
            review_packet_path = root / "handoff-review-packet.json"
            implementation_projection_path = (
                root / "handoff-implementation-projection.json"
            )
            implementation_packet_path = root / "handoff-implementation-packet.json"
            for path, value in (
                (plan_path, plan),
                (baseline_path, baseline),
                (review_projection_path, review_projection),
                (review_packet_path, review_packet),
                (implementation_projection_path, implementation_projection),
                (implementation_packet_path, implementation_packet),
            ):
                write_json(path, value)

            parent = start_run_observation(
                repo,
                run_id="dependency-handoff",
                request_key="dependency-handoff",
                task_label="dependency handoff 기록",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "desktop_request",
                },
            )
            review_result = run_codex_host(
                repo,
                run_id="dependency-handoff",
                task_label="dependency review 기록",
                plan_path=plan_path,
                assignment_id="review",
                projection_path=review_projection_path,
                baseline_path=baseline_path,
                observation_id=parent["observation_id"],
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "success",
                    str(review_packet_path),
                ],
            )
            self.assertEqual("completed", review_result["status"])

            result = run_codex_host(
                repo,
                run_id="dependency-handoff",
                task_label="dependency handoff 기록",
                plan_path=plan_path,
                assignment_id="implementation",
                projection_path=implementation_projection_path,
                baseline_path=baseline_path,
                dependency_packet_paths=[review_packet_path],
                dependency_projection_paths=[review_projection_path],
                observation_id=parent["observation_id"],
                timeout_seconds=5,
                command=[
                    sys.executable,
                    str(server),
                    "success",
                    str(implementation_packet_path),
                ],
            )
            self.assertEqual("completed", result["status"])
            observed = observation_receipt_fields(
                repo,
                observation_id=parent["observation_id"],
                run_id="dependency-handoff",
            )
            handoff = next(
                span
                for span in observed["work_spans"]
                if span["kind"] == "synthesis"
                and span["assignment_id"] is None
            )
            root = next(
                span
                for span in observed["work_spans"]
                if span["work_id"] == result["work_capture"]["root_work_id"]
            )
            self.assertEqual(
                [review_result["work_capture"]["root_work_id"]],
                handoff["joins_work_ids"],
            )
            self.assertEqual(
                [handoff["work_id"]],
                root["depends_on_work_ids"],
            )
            self.assertEqual(
                "observed",
                root["allocation"]["status"],
            )
            self.assertEqual(
                "route_plan",
                root["allocation"]["source"],
            )
            self.assertEqual(
                "host_loaded",
                root["expertise_observation"]["load"]["status"],
            )
            self.assertEqual(
                "observed",
                root["expertise_observation"]["application"]["status"],
            )
            self.assertEqual(
                "application_observed",
                root["expertise_evidence"],
            )
            self.assertEqual(
                implementation_packet["summary"],
                root["outcome"]["conclusion"],
            )
            self.assertIsNone(handoff["requested_model"])
            self.assertIsNone(handoff["applied_model"])
            edges = build_work_graph(
                plan["assignments"],
                observed["work_spans"],
            )["execution"]["edges"]
            self.assertIn(
                {
                    "from": review_result["work_capture"][
                        "root_work_id"
                    ],
                    "to": handoff["work_id"],
                    "type": "joins_into",
                    "provenance": "observed_work",
                    "source": "current_host",
                    "coverage": "unavailable",
                },
                edges,
            )
            self.assertIn(
                {
                    "from": handoff["work_id"],
                    "to": root["work_id"],
                    "type": "depends_on",
                    "provenance": "observed_work",
                    "source": "codex_app_server",
                    "coverage": "partial_stream",
                },
                edges,
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
