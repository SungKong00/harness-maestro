from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from maestro.dashboard import create_dashboard_server
from maestro.documents import select_documents
from maestro.errors import MaestroError
from maestro.expertise_health import expertise_component_health
from maestro.expertise_lifecycle import expertise_inventory
from maestro.governance import (
    expertise_management_signals,
    record_run,
)
from maestro.history import (
    apply_history_bundle_plan,
    build_history_bundle_plan,
    history_inventory,
    set_run_display_label,
)
from maestro.observations import (
    import_codex_app_server_trace,
    record_host_observation,
    start_desktop_request_observation,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.snapshot import snapshot_report
from maestro.verification import (
    apply_verification_approval_plan,
    build_verification_approval_plan,
    verification_inventory,
)
from tests.support import ROOT, apply_fresh_init, write_json


def _receipt_from_plan(plan: dict[str, object]) -> dict[str, object]:
    assignments = plan["assignments"]
    expertise = plan.get("expertise") or {}
    research = expertise.get(
        "research_requirement",
        {"mode": "reuse", "gate": "not-required"},
    )
    executor_ids = list(
        dict.fromkeys(item["executor_id"] for item in assignments)
    )
    return {
        "run_id": "viewer-run-1",
        "risk": plan["risk"],
        "route_depth": plan["depth"],
        "selected_lenses": plan["selected_lenses"],
        "selected_expertise_packs": expertise.get("selected_pack_ids", []),
        "selected_decision_guides": expertise.get("selected_guide_ids", []),
        "expertise_research_mode": research["mode"],
        "expertise_research_gate": research["gate"],
        "executor_runs": len(executor_ids),
        "primary_executor_id": assignments[0]["executor_id"],
        "executor_ids": executor_ids,
        "outcome": "completed",
        "evidence_refs": ["tests:operations-viewer"],
        "duration_ms": None,
        "tokens": {"input": 80, "output": 20, "total": 100},
        "correction_count": 0,
        "agent_calls": len(assignments),
        "verifier_result": (
            "passed" if "verifier" in executor_ids else "not_run"
        ),
        "command_artifact_ref": "tests:operations-viewer",
        "stage_results": [
            {
                "assignment_id": item["assignment_id"],
                "status": "completed",
                "actual_model": item["model_route"]["selected_model"],
                "duration_ms": 10 + index,
                "tokens": {
                    "total": 50,
                },
                "evidence_refs": ["tests:operations-viewer"],
            }
            for index, item in enumerate(assignments)
        ],
    }


class OperationsViewerTests(unittest.TestCase):
    def _initialized_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        apply_fresh_init(repo)
        return repo

    def _add_verification_candidate(self, repo: Path) -> None:
        project_path = repo / ".maestro/project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["commands"] = [
            {
                "name": "test",
                "command": "python3 -m unittest discover -s tests -v",
                "status": "candidate",
            }
        ]
        write_json(project_path, project)

    def test_desktop_observation_starts_and_attaches_request_settings_once(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))

            first = start_desktop_request_observation(
                repo,
                run_id="desktop-request",
                task_label="Desktop 요청 설정 연결",
                thread_id="thread-1",
                turn_id="turn-1",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="xhigh",
            )
            repeated = start_desktop_request_observation(
                repo,
                run_id="desktop-request",
                task_label="Desktop 요청 설정 연결",
                thread_id="thread-1",
                turn_id="turn-1",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="xhigh",
            )

            self.assertEqual("observe-desktop", first["command"])
            self.assertEqual("started", first["status"])
            self.assertTrue(first["writes_performed"])
            self.assertEqual("already_started", repeated["status"])
            self.assertFalse(repeated["writes_performed"])
            telemetry = repeated["telemetry"]
            self.assertEqual(
                "codex-desktop-request-meta",
                telemetry["source"],
            )
            self.assertEqual("gpt-5.6-sol", telemetry["requested_model"])
            self.assertEqual(
                "xhigh",
                telemetry["requested_reasoning_effort"],
            )
            self.assertEqual("unavailable", telemetry["model_event_evidence"])
            self.assertIsNone(telemetry["applied_model"])
            self.assertIsNone(telemetry["tokens"])

    def test_observation_enriches_one_idempotent_run_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "CLI에 읽기 전용 상태 출력을 추가한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="viewer-run-1",
                task_label="통합 운영 뷰어 구현",
                plan_path=plan_path,
            )
            receipt_path = root / "receipt.json"
            write_json(receipt_path, _receipt_from_plan(plan))

            first = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            repeated = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            snapshot = snapshot_report(repo, window=20)
            smallest_snapshot = snapshot_report(repo, window=1)

            self.assertEqual("recorded", first["status"])
            self.assertEqual("already_recorded", repeated["status"])
            self.assertFalse(first["management_check"]["automatic_mutation_allowed"])
            self.assertEqual("통합 운영 뷰어 구현", snapshot["runs"][0]["task_label"])
            self.assertEqual(
                "assignment_observation",
                snapshot["runs"][0]["flow_evidence"],
            )
            self.assertEqual(
                "not_selected",
                snapshot["runs"][0]["expertise"]["evidence"]["selection"],
            )
            self.assertEqual(
                "unavailable",
                snapshot["runs"][0]["expertise"]["evidence"][
                    "assignment_attachment"
                ],
            )
            self.assertEqual(
                "unavailable",
                snapshot["runs"][0]["expertise"]["evidence"]["host_load"],
            )
            self.assertEqual(
                "unavailable",
                snapshot["runs"][0]["expertise"]["evidence"]["application"],
            )
            self.assertEqual(100, snapshot["runs"][0]["tokens"]["total"])
            self.assertEqual([], snapshot["runs"][0]["models"]["applied"])
            self.assertTrue(
                snapshot["runs"][0]["models"]["route_recommended"]
            )
            self.assertEqual([], snapshot["inflight"])
            self.assertEqual(1, smallest_snapshot["window"])
            self.assertEqual(3, smallest_snapshot["governance"]["window"])
            self.assertIn(
                "decision_guide_usage",
                snapshot["governance"],
            )

    def test_host_observation_supplies_applied_model_and_tokens_without_estimation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "운영 기록에 실제 Host 측정값을 연결한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="host-observed-run",
                task_label="Host 측정값 연결",
                plan_path=plan_path,
            )
            first = record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="host-observed-run",
                source="codex-app-server",
                quality="host_reported",
                correlation_id="thread-1:turn-2",
                requested_model="gpt-host-observed",
                requested_reasoning_effort="medium",
                applied_model="gpt-host-observed",
                model_event_evidence="complete",
                tokens={"input": 70, "output": 30, "total": 100},
            )
            repeated = record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="host-observed-run",
                source="codex-app-server",
                quality="host_reported",
                correlation_id="thread-1:turn-2",
                requested_model="gpt-host-observed",
                requested_reasoning_effort="medium",
                applied_model="gpt-host-observed",
                model_event_evidence="complete",
                tokens={"input": 70, "output": 30, "total": 100},
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "host-observed-run"
            receipt["tokens"] = None
            receipt.pop("stage_results")
            receipt_path = root / "receipt.json"
            write_json(receipt_path, receipt)

            recorded = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            snapshot = snapshot_report(repo)

            self.assertEqual("recorded", first["status"])
            self.assertEqual("already_recorded", repeated["status"])
            self.assertEqual("recorded", recorded["status"])
            self.assertEqual(100, snapshot["runs"][0]["tokens"]["total"])
            self.assertEqual(
                ["gpt-host-observed"],
                snapshot["runs"][0]["models"]["requested"],
            )
            self.assertEqual(
                ["gpt-host-observed"],
                snapshot["runs"][0]["models"]["applied"],
            )
            self.assertEqual(
                ["medium"],
                snapshot["runs"][0]["models"][
                    "requested_reasoning_effort"
                ],
            )
            self.assertEqual(
                "host_event_stream_complete",
                snapshot["runs"][0]["models"]["measurement_state"],
            )
            self.assertEqual(
                "host_reported",
                snapshot["runs"][0]["host_observation"]["quality"],
            )
            viewer_source = (
                ROOT / "src/maestro/resources/viewer/app.js"
            ).read_text(encoding="utf-8")
            self.assertIn("run.host_observation.source", viewer_source)
            self.assertIn("run.host_observation.quality", viewer_source)
            self.assertIn("run.host_observation.correlation_id", viewer_source)
            self.assertIn(
                "snapshot.governance.decision_guide_usage",
                viewer_source,
            )
            self.assertIn("usage.last_used_timestamp", viewer_source)
            self.assertIn("usage.recent_run_ids", viewer_source)
            self.assertIn(
                "usage.failed_verification_run_count",
                viewer_source,
            )
            self.assertIn("usage.corrected_run_count", viewer_source)

    def test_requested_and_route_models_never_fill_unmeasured_applied_model(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "일반 기능을 구현한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="requested-only-run",
                task_label="요청 모델만 관측",
                plan_path=plan_path,
            )
            record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="requested-only-run",
                source="codex-app-server",
                quality="host_reported",
                correlation_id="thread-1:turn-3",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="xhigh",
            )
            inflight = snapshot_report(repo)["inflight"][0]
            self.assertEqual(
                "host_request_observed",
                inflight["host_state"],
            )
            self.assertEqual(
                "xhigh",
                inflight["requested_reasoning_effort"],
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "requested-only-run"
            receipt["tokens"] = None
            receipt_path = root / "receipt.json"
            write_json(receipt_path, receipt)
            record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )

            run = snapshot_report(repo)["runs"][0]
            self.assertEqual(["gpt-5.6-sol"], run["models"]["requested"])
            self.assertEqual([], run["models"]["applied"])
            self.assertEqual(
                ["xhigh"],
                run["models"]["requested_reasoning_effort"],
            )
            self.assertEqual(
                "host_request_observed",
                run["models"]["measurement_state"],
            )
            self.assertEqual(
                [
                    assignment["model_route"]["selected_model"]
                    for assignment in plan["assignments"]
                ][:1],
                run["models"]["route_recommended"],
            )
            self.assertEqual(
                "unavailable",
                run["models"]["model_event_evidence"],
            )

            viewer_source = (
                ROOT / "src/maestro/resources/viewer/app.js"
            ).read_text(encoding="utf-8")
            self.assertIn('"Maestro 권장"', viewer_source)
            self.assertIn("run.models.requested", viewer_source)
            self.assertIn("run.models.applied", viewer_source)
            self.assertNotIn(
                "run.models.actual[0] || run.models.planned[0]",
                viewer_source,
            )

    def test_legacy_reported_model_is_not_treated_as_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "기존 운영 기록을 읽는다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "legacy-host-run"
            receipt["host_observation"] = {
                "schema_version": "maestro_host_observation_v1",
                "source": "legacy-host",
                "quality": "host_reported",
                "correlation_id": "legacy-thread:legacy-turn",
                "actual_model": "gpt-legacy-reported",
                "tokens": {"total": 100},
                "observed_at": "2026-07-27T00:00:00Z",
            }
            receipt_path = root / "receipt.json"
            write_json(receipt_path, receipt)
            record_run(repo, receipt_path)

            run = snapshot_report(repo)["runs"][0]
            self.assertEqual([], run["models"]["requested"])
            self.assertEqual([], run["models"]["applied"])
            self.assertEqual(
                ["gpt-legacy-reported"],
                run["models"]["legacy_reported"],
            )
            self.assertEqual(
                "unavailable",
                run["models"]["model_event_evidence"],
            )

    def test_applied_model_requires_complete_host_event_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            started = start_run_observation(
                repo,
                run_id="model-evidence-run",
                task_label="모델 이벤트 근거 검사",
            )
            with self.assertRaises(MaestroError) as rejected:
                record_host_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="model-evidence-run",
                    source="codex-app-server",
                    quality="host_reported",
                    correlation_id="thread-2:turn-1",
                    requested_model="gpt-5.6-sol",
                    applied_model="gpt-5.6-terra",
                )
            self.assertEqual(
                "HOST_OBSERVATION_INVALID",
                rejected.exception.code,
            )

            recorded = record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="model-evidence-run",
                source="codex-app-server",
                quality="host_reported",
                correlation_id="thread-2:turn-1",
                requested_model="gpt-5.6-sol",
                applied_model="gpt-5.6-terra",
                model_event_evidence="complete",
                reroutes=[
                    {
                        "from_model": "gpt-5.6-sol",
                        "to_model": "gpt-5.6-terra",
                        "reason": "service reroute",
                    }
                ],
            )
            self.assertEqual(
                "gpt-5.6-terra",
                recorded["telemetry"]["applied_model"],
            )
            self.assertEqual(1, len(recorded["telemetry"]["reroutes"]))

    def test_codex_app_server_trace_imports_requested_applied_and_turn_tokens(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            started = start_run_observation(
                repo,
                run_id="app-server-run",
                task_label="App Server 실측 수집",
            )
            trace = root / "app-server.jsonl"
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "thread/start",
                    "params": {"model": "gpt-5.6-sol"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "thread": {"id": "thread-1"},
                        "reasoningEffort": "high",
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "turn/start",
                    "params": {
                        "threadId": "thread-1",
                        "input": [],
                        "model": None,
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "turn": {
                            "id": "turn-1",
                            "items": [],
                            "status": "inProgress",
                        }
                    },
                },
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
                },
                {
                    "jsonrpc": "2.0",
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "tokenUsage": {
                            "last": {
                                "inputTokens": 70,
                                "outputTokens": 20,
                                "cachedInputTokens": 10,
                                "reasoningOutputTokens": 5,
                                "totalTokens": 90,
                            },
                            "total": {
                                "inputTokens": 70,
                                "outputTokens": 20,
                                "cachedInputTokens": 10,
                                "reasoningOutputTokens": 5,
                                "totalTokens": 90,
                            },
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {
                            "id": "turn-1",
                            "items": [],
                            "status": "completed",
                            "durationMs": 2500,
                        },
                    },
                },
            ]
            trace.write_text(
                "".join(
                    json.dumps(message, ensure_ascii=False) + "\n"
                    for message in messages
                ),
                encoding="utf-8",
            )

            imported = import_codex_app_server_trace(
                repo,
                observation_id=started["observation_id"],
                run_id="app-server-run",
                trace_path=trace,
            )

            self.assertEqual("observe-import-codex", imported["command"])
            self.assertEqual(
                "gpt-5.6-sol",
                imported["telemetry"]["requested_model"],
            )
            self.assertEqual(
                "gpt-5.6-terra",
                imported["telemetry"]["applied_model"],
            )
            self.assertEqual(
                "high",
                imported["telemetry"]["requested_reasoning_effort"],
            )
            self.assertEqual(90, imported["telemetry"]["tokens"]["total"])
            self.assertEqual(2500, imported["turn_duration_ms"])
            receipt_path = root / "app-server-receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "app-server-run",
                    "risk": "low",
                    "route_depth": "fast",
                    "selected_lenses": [],
                    "selected_expertise_packs": [],
                    "selected_decision_guides": [],
                    "expertise_research_mode": "reuse",
                    "expertise_research_gate": "not-required",
                    "executor_runs": 1,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer"],
                    "outcome": "completed",
                    "evidence_refs": ["tests:app-server"],
                    "duration_ms": 2500,
                    "tokens": {
                        "input": 70,
                        "output": 20,
                        "cached": 10,
                        "reasoning": 5,
                        "total": 90,
                    },
                    "correction_count": 0,
                    "agent_calls": 1,
                    "verifier_result": "not_run",
                    "command_artifact_ref": "tests:app-server",
                    "stage_results": [],
                },
            )
            record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            run = snapshot_report(repo)["runs"][0]
            self.assertEqual(["gpt-5.6-sol"], run["models"]["requested"])
            self.assertEqual(["gpt-5.6-terra"], run["models"]["applied"])
            self.assertEqual(
                "host_event_stream_complete",
                run["models"]["measurement_state"],
            )
            self.assertEqual(
                ["high"],
                run["models"]["requested_reasoning_effort"],
            )

    def test_run_details_use_one_inline_accessible_disclosure(self) -> None:
        viewer_root = ROOT / "src/maestro/resources/viewer"
        viewer_source = (viewer_root / "app.js").read_text(encoding="utf-8")
        viewer_markup = (viewer_root / "index.html").read_text(encoding="utf-8")
        viewer_styles = (viewer_root / "styles.css").read_text(encoding="utf-8")

        self.assertIn(
            'state.selectedRun = expanded ? null : run.run_id',
            viewer_source,
        )
        self.assertIn('toggle.setAttribute("aria-expanded"', viewer_source)
        self.assertIn('toggle.setAttribute("aria-controls"', viewer_source)
        self.assertIn('detail.setAttribute("aria-labelledby"', viewer_source)
        self.assertIn('className: "run-detail-row"', viewer_source)
        self.assertIn("target.append(detailRow)", viewer_source)
        self.assertNotIn('id="run-detail"', viewer_markup)
        self.assertIn(
            "제목을 누르면 작업 기준, 결과, 모델·토큰 기록",
            viewer_markup,
        )
        self.assertIn('checkbox.type = "checkbox"', viewer_source)
        self.assertIn('id="history-bundles"', viewer_markup)
        self.assertIn(".run-detail-row", viewer_styles)

    def test_history_bundle_hides_selected_runs_without_deleting_receipts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            receipt_path = root / "receipt.json"
            receipt = {
                "run_id": "history-run-1",
                "risk": "low",
                "route_depth": "fast",
                "selected_lenses": [],
                "selected_expertise_packs": [],
                "selected_decision_guides": [],
                "expertise_research_mode": "reuse",
                "expertise_research_gate": "not-required",
                "executor_runs": 1,
                "primary_executor_id": "implementation-engineer",
                "executor_ids": ["implementation-engineer"],
                "outcome": "completed",
                "evidence_refs": ["tests:history"],
                "duration_ms": 100,
                "tokens": {"input": 10, "output": 5, "total": 15},
                "correction_count": 0,
                "agent_calls": 1,
                "verifier_result": "not_run",
                "command_artifact_ref": "tests:history",
                "stage_results": [],
            }
            started = start_run_observation(
                repo,
                run_id="history-run-1",
                task_label="History run",
            )
            write_json(receipt_path, receipt)
            record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            before = snapshot_report(repo)
            event_id = before["runs"][0]["event_id"]
            set_run_display_label(
                repo,
                event_id=event_id,
                label="결제 안정화 작업",
            )
            renamed = snapshot_report(repo)
            self.assertEqual(
                "결제 안정화 작업",
                renamed["runs"][0]["task_label"],
            )

            plan = build_history_bundle_plan(
                repo,
                label="결제 안정화 1차",
                event_ids=[event_id],
            )
            self.assertFalse(plan["writes_performed"])
            applied = apply_history_bundle_plan(plan, repo)
            after = snapshot_report(repo)

            self.assertEqual("applied", applied["status"])
            self.assertEqual([], after["runs"])
            self.assertEqual(1, after["overview"]["history_bundles"])
            self.assertEqual(
                "결제 안정화 1차",
                after["history_bundles"][0]["label"],
            )
            self.assertEqual(
                [event_id],
                history_inventory(repo)["bundled_event_ids"],
            )
            self.assertTrue(
                any(
                    (repo / ".maestro/state/events").glob("*.jsonl")
                )
            )

    def test_expertise_signal_requires_repeated_reusable_evidence(self) -> None:
        events = [
            {
                "run_id": f"run-{index}",
                "timestamp": f"2026-07-2{index}T00:00:00Z",
                "expertise_observations": [
                    {
                        "kind": "missing_guide",
                        "domain": "database transactions",
                        "pack_id": None,
                        "guide_id": None,
                        "severity": "high",
                        "reusable": True,
                        "resolution": "research",
                        "evidence_ref": f"tests:run-{index}",
                    }
                ],
            }
            for index in range(1, 4)
        ]

        self.assertEqual([], expertise_management_signals(events[:2]))
        signals = expertise_management_signals(events)
        self.assertEqual(1, len(signals))
        self.assertEqual(3, signals[0]["occurrences"])
        self.assertEqual("review_recommended", signals[0]["status"])
        self.assertFalse(signals[0]["automatic_change_allowed"])

    def test_expertise_health_uses_actionable_states_not_not_observed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            snapshot = snapshot_report(repo)
            health = snapshot["expertise"]["component_health"]

            self.assertTrue(health["packs"])
            self.assertTrue(all(
                pack["utility_verdict"] == "awaiting_usage"
                for pack in health["packs"]
            ))
            self.assertTrue(all(
                guide["load_evidence"]
                == "host_attestation_unavailable"
                for pack in health["packs"]
                for guide in pack["guides"]
            ))
            self.assertNotIn(
                '"not_observed"',
                json.dumps(health, sort_keys=True),
            )

    def test_component_health_reports_guide_review_without_claiming_causality(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            events = [
                {
                    "run_id": f"design-{index}",
                    "timestamp": f"2026-07-{20 + index:02d}T00:00:00Z",
                    "selected_expertise_packs": ["product-design"],
                    "selected_decision_guides": ["typography-korean"],
                    "verifier_result": "passed",
                    "correction_count": 0,
                    "expertise_observations": [],
                }
                for index in range(1, 6)
            ]
            report = expertise_component_health(
                expertise_inventory(repo),
                events,
            )
            pack = next(
                item
                for item in report["packs"]
                if item["pack_id"] == "product-design"
            )
            guide = next(
                item
                for item in pack["guides"]
                if item["guide_id"] == "typography-korean"
            )

            self.assertEqual("review_due", guide["utility_verdict"])
            self.assertEqual(5, guide["usage_count"])
            self.assertEqual(5, guide["selection_count"])
            self.assertEqual(
                "host_attestation_unavailable",
                guide["load_evidence"],
            )
            self.assertFalse(report["automatic_mutation_allowed"])
            self.assertIn("not causal proof", report["interpretation"])

    def test_viewer_separates_expertise_lifecycle_freshness_and_evidence(
        self,
    ) -> None:
        viewer_root = ROOT / "src/maestro/resources/viewer"
        viewer_source = (viewer_root / "app.js").read_text(encoding="utf-8")
        viewer_markup = (viewer_root / "index.html").read_text(encoding="utf-8")

        self.assertIn('data-view-target="overview"', viewer_markup)
        self.assertIn('data-view-target="work"', viewer_markup)
        self.assertIn('data-view-target="expertise"', viewer_markup)
        self.assertIn('data-view-target="management"', viewer_markup)
        self.assertIn("전문 지식 묶음의 사용 단계", viewer_markup)
        self.assertIn('evidence_gathering: "사용 결과 수집 중"', viewer_source)
        self.assertIn('stable: "변경이 드문 기준"', viewer_source)
        self.assertIn("후보 · 즉시 사용 가능", viewer_source)
        self.assertIn("최근 선택된 작업", viewer_source)
        self.assertIn("게시 전에도 관련 작업에 즉시 사용", viewer_markup)
        self.assertIn('"3 · 본문 불러오기"', viewer_source)
        self.assertIn('"4 · 결과에 적용"', viewer_source)
        self.assertNotIn("최근 사용 ${usage}", viewer_source)

    def test_viewer_uses_clear_axis_specific_status_language(self) -> None:
        viewer_root = ROOT / "src/maestro/resources/viewer"
        viewer_source = (viewer_root / "app.js").read_text(encoding="utf-8")
        viewer_markup = (viewer_root / "index.html").read_text(
            encoding="utf-8",
        )

        self.assertIn("실행 정보가 기록된 작업 비율", viewer_markup)
        self.assertIn("0%는 작업 실패가 아니라", viewer_markup)
        self.assertIn('<details class="meaning-guide" open>', viewer_markup)
        self.assertIn('host_not_connected: "모델·토큰 기록 없음"', viewer_source)
        self.assertIn(
            'host_request_observed: "채팅에서 선택한 설정만 기록됨"',
            viewer_source,
        )
        self.assertIn(
            'host_event_stream_complete: "실제 실행 모델 기록됨"',
            viewer_source,
        )
        self.assertIn('"작업 기준"', viewer_source)
        self.assertIn('"작업 결과"', viewer_source)
        self.assertIn('"모델과 사용량 기록"', viewer_source)
        self.assertIn('"기술 기록 보기"', viewer_source)
        self.assertIn("0토큰이라는 뜻이 아닙니다", viewer_source)
        self.assertNotIn("작업 요약", viewer_source + viewer_markup)
        self.assertNotIn("토큰 미측정", viewer_source + viewer_markup)
        self.assertNotIn("요청 설정 확인", viewer_source + viewer_markup)
        self.assertIn('active: "정식 사용"', viewer_source)
        self.assertIn('deprecated: "교체 예정"', viewer_source)
        self.assertIn("function lifecycleTone", viewer_source)
        self.assertIn("function displayReasoningEffort", viewer_source)
        self.assertIn('"보통 (medium)"', viewer_source)
        self.assertIn('"매우 높음 (xhigh)"', viewer_source)
        self.assertNotIn("실행 이벤트 미연결", viewer_source + viewer_markup)
        self.assertNotIn("Host 정보 없음", viewer_source + viewer_markup)

    def test_dashboard_is_local_read_only_and_token_gated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            server, token, url = create_dashboard_server(repo, window=20)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]
            try:
                with urllib.request.urlopen(f"{base}/", timeout=5) as response:
                    self.assertEqual(200, response.status)
                    self.assertIn(
                        "프로젝트 운영 뷰어",
                        response.read().decode("utf-8"),
                    )
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(
                        f"{base}/api/snapshot",
                        timeout=5,
                    )
                self.assertEqual(403, denied.exception.code)

                request = urllib.request.Request(
                    f"{base}/api/snapshot",
                    headers={"X-Maestro-Token": token},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read())
                self.assertEqual("maestro_snapshot_v1", payload["schema_version"])
                self.assertFalse(payload["writes_performed"])

                post = urllib.request.Request(
                    f"{base}/api/snapshot",
                    method="POST",
                    data=b"{}",
                    headers={"X-Maestro-Token": token},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(post, timeout=5)
                self.assertEqual(405, rejected.exception.code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_verification_approval_is_exact_preview_apply_and_never_executes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            self._add_verification_candidate(repo)
            inventory = verification_inventory(repo)
            candidate = inventory["candidates"][0]
            plan = build_verification_approval_plan(
                repo,
                candidate_id=candidate["candidate_id"],
            )

            self.assertFalse(plan["writes_performed"])
            self.assertFalse(plan["executes_command"])
            self.assertEqual(
                [],
                json.loads(
                    (repo / ".maestro/project.json").read_text(encoding="utf-8")
                )["verification_commands"],
            )

            applied = apply_verification_approval_plan(plan, repo)
            repeated = apply_verification_approval_plan(plan, repo)
            approved = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )["verification_commands"]

            self.assertEqual("approved", applied["status"])
            self.assertEqual("already_approved", repeated["status"])
            self.assertFalse(applied["executes_command"])
            self.assertEqual(
                [{"name": candidate["name"], "command": candidate["command"]}],
                approved,
            )

    def test_dashboard_verification_action_requires_origin_token_and_preview(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            self._add_verification_candidate(repo)
            candidate = verification_inventory(repo)["candidates"][0]
            server, token, url = create_dashboard_server(repo)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]
            origin = base

            def post(path: str, payload: dict[str, object], **headers: str):
                body = json.dumps(payload).encode("utf-8")
                request = urllib.request.Request(
                    f"{base}{path}",
                    method="POST",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                        "Origin": origin,
                        **headers,
                    },
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            try:
                denied = urllib.request.Request(
                    f"{base}/api/verification-approvals/preview",
                    method="POST",
                    data=json.dumps(
                        {"candidate_id": candidate["candidate_id"]}
                    ).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                    },
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(denied, timeout=5)
                self.assertEqual(403, rejected.exception.code)

                preview = post(
                    "/api/verification-approvals/preview",
                    {"candidate_id": candidate["candidate_id"]},
                )
                self.assertFalse(preview["writes_performed"])
                self.assertFalse(preview["executes_command"])
                self.assertEqual(
                    [],
                    json.loads(
                        (repo / ".maestro/project.json").read_text(
                            encoding="utf-8"
                        )
                    )["verification_commands"],
                )
                with self.assertRaises(urllib.error.HTTPError) as tampered:
                    post(
                        "/api/verification-approvals/apply",
                        {
                            "plan_id": preview["plan_id"],
                            "plan_digest": "0" * 64,
                        },
                    )
                self.assertEqual(409, tampered.exception.code)

                applied = post(
                    "/api/verification-approvals/apply",
                    {
                        "plan_id": preview["plan_id"],
                        "plan_digest": preview["plan_digest"],
                    },
                )
                self.assertEqual("approved", applied["status"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_operations_document_is_selected_for_viewer_paths(self) -> None:
        selection = select_documents(
            ROOT,
            "HTML 운영 뷰어 포함 전체 연결 점검",
            [],
            [
                "src/maestro/dashboard.py",
                "src/maestro/observations.py",
                "src/maestro/resources/viewer/app.js",
            ],
        )
        paths = {
            item["path"]
            for item in selection["required_documents"]
        }
        self.assertIn("docs/architecture/operations-viewer.md", paths)

    def test_packaged_source_manifests_match_bundled_skill_evidence(self) -> None:
        for pack_id, skill_id in (
            ("marketing", "maestro-marketing"),
            ("product-design", "maestro-product-design"),
            ("software-qa", "maestro-software-qa"),
        ):
            packaged = (
                ROOT
                / "src"
                / "maestro"
                / "resources"
                / "expertise-sources"
                / f"{pack_id}.json"
            )
            source = (
                ROOT
                / "skills"
                / skill_id
                / "evidence"
                / "sources.json"
            )
            self.assertEqual(
                json.loads(source.read_text(encoding="utf-8")),
                json.loads(packaged.read_text(encoding="utf-8")),
            )


class OperationsViewerVisualThemeContractTests(unittest.TestCase):
    """Isolated contract for the final visual-system layer."""

    def setUp(self) -> None:
        self.viewer_root = ROOT / "src/maestro/resources/viewer"
        self.styles = (self.viewer_root / "styles.css").read_text(
            encoding="utf-8"
        )
        marker = "/* Trustworthy operations console:"
        self.theme = self.styles[self.styles.index(marker):]

    def test_theme_layer_follows_structural_styles(self) -> None:
        structural = self.styles.index(":root")
        theme = self.styles.index("/* Trustworthy operations console:")
        self.assertLess(structural, theme)

    def test_theme_uses_semantic_tokens_and_neutral_trust_palette(self) -> None:
        for token in (
            "--color-canvas",
            "--color-surface",
            "--color-surface-raised",
            "--color-ink",
            "--color-blue",
            "--color-success",
            "--color-warning",
            "--color-danger",
            "--space-",
            "--radius-",
            "--shadow-",
            "--type-",
        ):
            self.assertIn(token, self.theme)
        self.assertIn("--color-canvas: #eef3f8", self.theme)
        self.assertIn("--color-blue: #1769c2", self.theme)
        for legacy_purple in ("#4f46e5", "#3730a3", "#eeedff", "#deddff"):
            self.assertNotIn(legacy_purple, self.theme)

    def test_theme_preserves_visual_state_and_accessibility_contracts(self) -> None:
        for contract in (
            ":focus-visible",
            ":hover",
            ":disabled",
            '[aria-current="page"]',
            ".selected",
            ".empty-state",
            ".error-banner",
            ".pill.good",
            ".pill.warn",
            ".pill.bad",
            "--shadow-overlay",
            "@media (max-width: 640px)",
            "@media (prefers-reduced-motion: reduce)",
            '[aria-busy="true"]',
        ):
            self.assertIn(contract, self.theme)
        self.assertNotIn("gradient(", self.theme.lower())
        self.assertNotIn("display: none !important", self.theme)


if __name__ == "__main__":
    unittest.main()
