from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from maestro.cli import parser
from maestro.dashboard import (
    create_dashboard_server,
    prepare_dashboard_project_catalog,
)
from maestro.documents import select_documents
from maestro.errors import MaestroError
from maestro.expertise_health import expertise_component_health
from maestro.expertise_lifecycle import expertise_inventory
from maestro.governance import (
    expertise_management_signals,
    finalize_run,
    record_run,
)
from maestro.history import (
    apply_history_bundle_plan,
    build_history_bundle_plan,
    history_inventory,
    set_run_display_label,
)
from maestro.observations import (
    attach_run_plan,
    import_codex_app_server_trace,
    record_execution_fallback,
    record_host_observation,
    record_stage_observation,
    start_desktop_request_observation,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.snapshot import _expertise_review_attention, snapshot_report
from maestro.snapshot_runs import (
    _aggregate_stage_tokens,
    _flow_graph,
    _graph_ranks,
    _receipt_projection,
    _run_card,
    _run_flow,
    _work_detail_projection,
)
from maestro.verification import (
    apply_verification_approval_plan,
    build_verification_approval_plan,
    verification_inventory,
)
from tests.support import (
    ROOT,
    application_work_span,
    apply_fresh_init,
    write_json,
)


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
        "tokens": None,
        "correction_count": 0,
        "agent_calls": len(assignments),
        "verifier_result": (
            "passed" if "verifier" in executor_ids else "not_run"
        ),
        "command_artifact_ref": "tests:operations-viewer",
    }


def _observe_plan_stages(
    repo: Path,
    observation_id: str,
    run_id: str,
    plan: dict[str, object],
) -> None:
    observation = json.loads(
        (
            repo
            / ".maestro/state/inflight"
            / f"{observation_id}.json"
        ).read_text(encoding="utf-8")
    )
    if observation.get("execution_binding", {}).get("mode") != "explicit_fallback":
        record_execution_fallback(
            repo,
            observation_id=observation_id,
            run_id=run_id,
            reason="capability_unavailable",
            evidence="The test intentionally exercises the current-Host fallback path.",
        )
    for index, assignment in enumerate(plan["assignments"]):
        record_stage_observation(
            repo,
            observation_id=observation_id,
            run_id=run_id,
            assignment_id=assignment["assignment_id"],
            status="completed",
            evidence_source="current_host",
            evidence_refs=[f"tests:stage:{assignment['assignment_id']}"],
            duration_ms=10 + index,
        )


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

    def test_dashboard_cli_accepts_repeated_additional_projects(self) -> None:
        arguments = parser().parse_args(
            [
                "dashboard",
                "--repo",
                "/project/primary",
                "--project",
                "/project/second",
                "--project",
                "/project/third",
            ]
        )
        self.assertEqual(
            ["/project/second", "/project/third"],
            arguments.project,
        )
        self.assertFalse(arguments.no_saved_projects)

    def test_dashboard_catalog_restores_projects_without_scanning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first = self._initialized_repo(first_root)
            second = self._initialized_repo(second_root)
            catalog_path = root / "state" / "dashboard-projects.json"

            registered = prepare_dashboard_project_catalog(
                first,
                project_paths=[second],
                catalog_path=catalog_path,
            )
            restored = prepare_dashboard_project_catalog(
                first,
                catalog_path=catalog_path,
            )

            self.assertEqual(2, registered["project_count"])
            self.assertEqual(0, registered["restored_count"])
            self.assertEqual(2, restored["project_count"])
            self.assertEqual(1, restored["restored_count"])
            self.assertEqual(
                {first.resolve(), second.resolve()},
                set(restored["project_paths"]),
            )
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(
                "maestro_dashboard_project_catalog_v1",
                catalog["schema_version"],
            )
            self.assertEqual(0o600, catalog_path.stat().st_mode & 0o777)

    def test_dashboard_catalog_prunes_missing_or_reidentified_projects(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first = self._initialized_repo(first_root)
            second = self._initialized_repo(second_root)
            catalog_path = root / "dashboard-projects.json"
            prepare_dashboard_project_catalog(
                first,
                project_paths=[second],
                catalog_path=catalog_path,
            )
            second_manifest_path = second / ".maestro/project.json"
            second_manifest = json.loads(
                second_manifest_path.read_text(encoding="utf-8")
            )
            second_manifest["project_id"] = "changed-project-id"
            write_json(second_manifest_path, second_manifest)

            restored = prepare_dashboard_project_catalog(
                first,
                catalog_path=catalog_path,
            )

            self.assertEqual([first.resolve()], restored["project_paths"])
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(1, len(catalog["projects"]))

    def test_dashboard_catalog_recovers_from_invalid_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            catalog_path = root / "dashboard-projects.json"
            write_json(catalog_path, {"unexpected": True})

            restored = prepare_dashboard_project_catalog(
                repo,
                catalog_path=catalog_path,
            )

            self.assertEqual("recreated", restored["status"])
            self.assertEqual([repo.resolve()], restored["project_paths"])
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(
                "maestro_dashboard_project_catalog_v1",
                catalog["schema_version"],
            )

    def test_isolated_dashboard_does_not_read_or_replace_saved_catalog(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first = self._initialized_repo(first_root)
            second = self._initialized_repo(second_root)
            catalog_path = root / "dashboard-projects.json"
            prepare_dashboard_project_catalog(
                first,
                project_paths=[second],
                catalog_path=catalog_path,
            )
            before = catalog_path.read_bytes()

            isolated = prepare_dashboard_project_catalog(
                first,
                catalog_path=catalog_path,
                include_saved=False,
            )

            self.assertEqual("session_only", isolated["status"])
            self.assertEqual([first.resolve()], isolated["project_paths"])
            self.assertFalse(isolated["writes_performed"])
            self.assertEqual(before, catalog_path.read_bytes())

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
            self.assertEqual(
                "desktop_request",
                repeated["execution_binding"]["mode"],
            )
            fallback = record_execution_fallback(
                repo,
                observation_id=first["observation_id"],
                run_id="desktop-request",
                reason="interactive_required",
                evidence="The test now requires the open Desktop surface.",
            )
            after_fallback = start_desktop_request_observation(
                repo,
                run_id="desktop-request",
                task_label="Desktop 요청 설정 연결",
                thread_id="thread-1",
                turn_id="turn-1",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="xhigh",
            )
            self.assertEqual("attached", fallback["status"])
            self.assertEqual(
                "explicit_fallback",
                after_fallback["execution_binding"]["mode"],
            )

    def test_request_plan_stages_and_finalize_form_one_observed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "계획과 실행 기록을 연결한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_desktop_request_observation(
                repo,
                run_id="observed-pipeline",
                task_label="계획·실행 기록 연결",
                thread_id="thread-pipeline",
                turn_id="turn-pipeline",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="xhigh",
            )

            attached = attach_run_plan(
                repo,
                observation_id=started["observation_id"],
                run_id="observed-pipeline",
                plan_path=plan_path,
            )
            before = snapshot_report(repo)["inflight"][0]
            self.assertEqual("attached", attached["status"])
            self.assertEqual("attached", before["planning_status"])
            self.assertEqual(0, before["recorded_stage_count"])
            self.assertEqual(
                len(plan["assignments"]),
                before["planned_stage_count"],
            )

            _observe_plan_stages(
                repo,
                started["observation_id"],
                "observed-pipeline",
                plan,
            )
            pending = snapshot_report(repo)["inflight"][0]
            self.assertEqual("receipt_pending", pending["status"])
            self.assertEqual(
                pending["planned_stage_count"],
                pending["recorded_stage_count"],
            )

            finalized = finalize_run(
                repo,
                run_id="observed-pipeline",
                observation_id=started["observation_id"],
                outcome="completed",
                evidence_refs=["tests:observed-pipeline"],
                verifier_result="passed",
                command_artifact_ref="tests:observed-pipeline",
            )
            snapshot = snapshot_report(repo)
            run = snapshot["runs"][0]
            self.assertEqual("recorded", finalized["status"])
            self.assertEqual([], snapshot["inflight"])
            self.assertTrue(run["stage_coverage"]["complete"])
            self.assertFalse(run["stage_telemetry"]["complete"])
            self.assertEqual(
                0,
                run["stage_telemetry"]["model_measured"],
            )
            self.assertEqual(
                "explicit_fallback",
                run["execution_binding"]["mode"],
            )
            self.assertEqual(
                len(plan["assignments"]),
                run["stage_coverage"]["recorded"],
            )
            self.assertEqual(["gpt-5.6-sol"], run["models"]["requested"])
            self.assertEqual([], run["models"]["applied"])
            self.assertIsNone(run["tokens"])
            self.assertEqual(
                {
                    "plan_id": plan["plan_id"],
                    "intent": plan["intent"],
                    "department": plan["department"],
                    "risk": plan["risk"],
                    "depth": plan["depth"],
                    "source": "plan_summary",
                },
                run["plan"],
            )
            flow_by_id = {
                stage["assignment_id"]: stage
                for stage in run["flow"]
            }
            for assignment in plan["assignments"]:
                projected = flow_by_id[assignment["assignment_id"]]
                self.assertEqual(
                    assignment["lens_ids"],
                    projected["lens_ids"],
                )
                self.assertEqual(
                    assignment["mutation_owner"],
                    projected["mutation_owner"],
                )
                self.assertEqual(
                    assignment["read_only"],
                    projected["read_only"],
                )
            self.assertEqual(
                sorted(
                    (
                        {
                            "from": dependency,
                            "to": assignment["assignment_id"],
                            "source": "plan_summary",
                        }
                        for assignment in plan["assignments"]
                        for dependency in assignment["depends_on"]
                    ),
                    key=lambda edge: (edge["from"], edge["to"]),
                ),
                sorted(
                    run["flow_graph"]["edges"],
                    key=lambda edge: (edge["from"], edge["to"]),
                ),
            )
            self.assertEqual(
                "planned_dependency",
                run["flow_graph"]["ordering_semantics"],
            )
            assignment_ids = {
                assignment["assignment_id"]
                for assignment in plan["assignments"]
            }
            dependency_ids = {
                dependency
                for assignment in plan["assignments"]
                for dependency in assignment["depends_on"]
            }
            expected_entries = sorted(
                assignment["assignment_id"]
                for assignment in plan["assignments"]
                if not assignment["depends_on"]
            )
            expected_terminals = sorted(
                assignment_ids - dependency_ids
            )
            self.assertEqual(
                expected_entries,
                run["flow_graph"]["entry_assignment_ids"],
            )
            self.assertEqual(
                expected_terminals,
                run["flow_graph"]["terminal_assignment_ids"],
            )
            self.assertEqual(
                "unavailable",
                run["flow_graph"]["actual_order"],
            )
            self.assertEqual(
                "unavailable",
                run["flow_graph"]["actual_concurrency"],
            )
            work_detail = run["work_detail"]
            self.assertEqual(
                "maestro_work_detail_v2",
                work_detail["schema_version"],
            )
            self.assertEqual(
                run["flow_graph"]["edges"],
                work_detail["graph"]["edges"],
            )
            self.assertEqual(
                "planned_dependency",
                work_detail["graph"]["ordering_semantics"],
            )
            self.assertEqual(
                "unavailable",
                work_detail["graph"]["actual_concurrency"],
            )
            self.assertEqual(
                {item["assignment_id"] for item in plan["assignments"]},
                {
                    stage["stage_id"]
                    for stage in work_detail["stages"]
                },
            )
            self.assertTrue(
                all(
                    lane["basis"] == "assignment_kind"
                    for lane in work_detail["lanes"]
                )
            )
            self.assertEqual(
                "unavailable",
                work_detail["limitations"]["stage_findings"],
            )
            self.assertEqual(
                "unavailable",
                work_detail["limitations"]["guide_application"],
            )
            self.assertEqual("run_summary", run["receipt"]["kind"])
            self.assertEqual(
                "tests:observed-pipeline",
                run["receipt"]["command_artifact_ref"],
            )
            self.assertIsNone(
                run["receipt"]["project_convention_evidence"]
            )
            self.assertEqual(
                {
                    "result": "passed",
                    "command_artifact_ref": "tests:observed-pipeline",
                    "evidence_refs": ["tests:observed-pipeline"],
                    "source": "run_receipt",
                    "criteria": "unavailable",
                    "artifact_integrity": "unavailable",
                    "interpretation": (
                        "The RunReceipt reports the verifier result and "
                        "references. It does not define the verifier criteria "
                        "or prove artifact integrity."
                    ),
                },
                run["verification"],
            )

    def test_run_projection_preserves_graph_and_measurement_boundaries(
        self,
    ) -> None:
        flow = [
            {"assignment_id": "verify", "depends_on": ["write", "review"]},
            {"assignment_id": "root", "depends_on": []},
            {"assignment_id": "review", "depends_on": ["root"]},
            {"assignment_id": "write", "depends_on": ["root"]},
        ]

        graph = _flow_graph(flow, "assignment_observation")

        self.assertEqual(["root"], graph["entry_assignment_ids"])
        self.assertEqual(["verify"], graph["terminal_assignment_ids"])
        self.assertEqual(
            [
                {"from": "review", "to": "verify", "source": "plan_summary"},
                {"from": "root", "to": "review", "source": "plan_summary"},
                {"from": "root", "to": "write", "source": "plan_summary"},
                {"from": "write", "to": "verify", "source": "plan_summary"},
            ],
            graph["edges"],
        )
        self.assertEqual("unavailable", graph["actual_order"])
        self.assertEqual("unavailable", graph["actual_concurrency"])
        self.assertEqual(
            {"root": 0, "review": 1, "write": 1, "verify": 2},
            _graph_ranks(flow),
        )
        self.assertEqual(
            {
                "edges": [],
                "entry_assignment_ids": [],
                "terminal_assignment_ids": [],
                "ordering_semantics": "summary_only",
                "actual_order": "unavailable",
                "actual_concurrency": "unavailable",
            },
            _flow_graph(flow, "summary_only"),
        )
        self.assertIsNone(
            _aggregate_stage_tokens([{"tokens": {}}, {"tokens": None}])
        )
        self.assertEqual(
            {"input": 3, "total": 7},
            _aggregate_stage_tokens(
                [
                    {"tokens": {"input": 3, "total": 3}},
                    {"tokens": {"total": 4}},
                ]
            ),
        )
        historical = _work_detail_projection(
            {
                "flow": [],
                "flow_graph": _flow_graph([], "summary_only"),
                "models": {},
                "plan": {},
                "receipt": {},
                "verification": {},
                "measurement_provenance": {},
            }
        )
        self.assertEqual([], historical["lanes"])
        self.assertEqual([], historical["stages"])
        self.assertEqual(
            "summary_only",
            historical["graph"]["ordering_semantics"],
        )
        self.assertEqual(
            "unavailable",
            historical["limitations"]["actual_order"],
        )

    def test_receipt_projection_keeps_convention_decision_evidence(
        self,
    ) -> None:
        evidence = {
            "kind": "owner_decision",
            "assurance": "owner_attested",
            "decision_summary": "프로젝트 소유자가 채택을 승인했다.",
            "convention_sha256": "a" * 64,
            "artifact": {
                "path": "docs/decisions/convention.txt",
                "sha256": "b" * 64,
            },
        }

        receipt = _receipt_projection(
            {
                "project_convention_action": "created",
                "project_convention_basis": "owner_decision",
                "project_convention_path": "docs/conventions/example.md",
                "project_convention_evidence": evidence,
            }
        )

        self.assertEqual(evidence, receipt["project_convention_evidence"])

    def test_source_less_stage_model_remains_legacy_reported(self) -> None:
        flow, evidence = _run_flow(
            {
                "plan_summary": {
                    "assignments": [
                        {
                            "assignment_id": "implementation",
                            "kind": "implementation",
                            "executor_id": "implementation-engineer",
                            "depends_on": [],
                            "lens_ids": [],
                            "mutation_owner": "implementation-engineer",
                            "read_only": False,
                            "planned_model": "gpt-planned",
                            "reasoning_effort": "medium",
                            "expertise_pack_ids": [],
                            "decision_guide_ids": [],
                        }
                    ]
                },
                "stage_results": [
                    {
                        "assignment_id": "implementation",
                        "actual_model": "gpt-legacy-reported",
                        "model_evidence": "complete",
                    }
                ],
            }
        )

        self.assertEqual("assignment_observation", evidence)
        self.assertIsNone(flow[0]["applied_model"])
        self.assertEqual(
            "gpt-legacy-reported",
            flow[0]["legacy_reported_model"],
        )
        self.assertEqual("unavailable", flow[0]["model_evidence"])
        self.assertEqual("complete", flow[0]["reported_model_evidence"])

    def test_partial_stage_models_do_not_become_run_actual_model(
        self,
    ) -> None:
        event = {
            "event_id": "event-partial-model",
            "run_id": "partial-model",
            "timestamp": "2026-07-28T00:00:00Z",
            "risk": "medium",
            "route_depth": "standard",
            "outcome": "completed",
            "verifier_result": "not_run",
            "plan_summary": {
                "plan_id": "plan-partial-model",
                "intent": "implementation",
                "department": "software-development",
                "risk": "medium",
                "depth": "standard",
                "assignments": [
                    {
                        "assignment_id": assignment_id,
                        "kind": "implementation",
                        "executor_id": "implementation-engineer",
                        "depends_on": [],
                        "lens_ids": [],
                        "mutation_owner": "implementation-engineer",
                        "read_only": False,
                        "planned_model": "gpt-planned",
                        "reasoning_effort": "medium",
                        "expertise_pack_ids": [],
                        "decision_guide_ids": [],
                    }
                    for assignment_id in ("first", "second")
                ],
            },
            "stage_results": [
                {
                    "assignment_id": "first",
                    "actual_model": "gpt-observed",
                    "model_evidence": "complete",
                    "evidence_source": "codex_app_server",
                }
            ],
        }

        run = _run_card(event)

        self.assertEqual([], run["models"]["applied"])
        self.assertEqual("partial", run["models"]["model_event_evidence"])
        self.assertEqual(
            "partial",
            run["models"]["applied_model_provenance"]["observed_stages"],
        )
        self.assertEqual(
            "host_not_connected",
            run["models"]["measurement_state"],
        )
        self.assertEqual("gpt-observed", run["flow"][0]["applied_model"])
        self.assertIsNone(run["flow"][1]["applied_model"])
        self.assertFalse(run["stage_telemetry"]["complete"])

    def test_run_card_distinguishes_new_no_selection_from_legacy(
        self,
    ) -> None:
        event = {
            "event_id": "event-routing-summary",
            "run_id": "routing-summary",
            "timestamp": "2026-07-28T00:00:00Z",
            "risk": "low",
            "route_depth": "fast",
            "outcome": "completed",
            "verifier_result": "not_run",
            "plan_summary": {
                "expertise_routing": {
                    "schema_version": (
                        "maestro_expertise_routing_summary_v1"
                    ),
                    "selection_state": "not_selected",
                    "selection_source": "none",
                    "route_attempt": 1,
                    "conflict_warning_codes": [],
                },
            },
        }

        current = _run_card(event)["expertise"]["routing"]
        legacy = _run_card(
            {
                **event,
                "event_id": "event-routing-legacy",
                "plan_summary": {},
            }
        )["expertise"]["routing"]

        self.assertEqual("plan_summary", current["evidence"])
        self.assertEqual("not_selected", current["selection_state"])
        self.assertEqual("none", current["selection_source"])
        self.assertEqual("unavailable", legacy["evidence"])
        self.assertEqual("unavailable", legacy["selection_state"])
        self.assertIsNone(legacy["route_attempt"])

    def test_public_schemas_share_the_routing_summary_contract(self) -> None:
        schemas = [
            json.loads(
                (
                    ROOT
                    / "src/maestro/resources/schemas"
                    / filename
                ).read_text(encoding="utf-8")
            )
            for filename in (
                "event.schema.json",
                "run-receipt.schema.json",
            )
        ]

        self.assertEqual(
            schemas[0]["$defs"]["planSummary"],
            schemas[1]["$defs"]["planSummary"],
        )
        self.assertEqual(
            schemas[0]["$defs"]["expertiseRoutingSummary"],
            schemas[1]["$defs"]["expertiseRoutingSummary"],
        )

    def test_finalize_rejects_an_unrecorded_planned_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "여러 실행 단계를 검증한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="incomplete-stages",
                task_label="누락 단계 검증",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "The test intentionally leaves one stage unfinished.",
                },
            )
            first = plan["assignments"][0]
            record_stage_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="incomplete-stages",
                assignment_id=first["assignment_id"],
                status="completed",
                evidence_source="current_host",
                evidence_refs=["tests:first-stage"],
            )

            with self.assertRaises(MaestroError) as raised:
                finalize_run(
                    repo,
                    run_id="incomplete-stages",
                    observation_id=started["observation_id"],
                    outcome="completed",
                    evidence_refs=["tests:incomplete"],
                    verifier_result="passed",
                    command_artifact_ref="tests:incomplete",
                )

            self.assertEqual(
                "RUN_STAGE_EVIDENCE_REQUIRED",
                raised.exception.code,
            )

    def test_current_host_stage_cannot_claim_model_or_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "현재 Host 근거 경계를 검증한다",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="current-host-boundary",
                task_label="현재 Host 근거 경계",
                plan_path=plan_path,
            )
            with self.assertRaises(MaestroError) as unbound:
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="current-host-boundary",
                    assignment_id=plan["assignments"][0]["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=["tests:current-host"],
                )
            self.assertEqual(
                "RUN_EXECUTION_FALLBACK_REQUIRED",
                unbound.exception.code,
            )
            record_execution_fallback(
                repo,
                observation_id=started["observation_id"],
                run_id="current-host-boundary",
                reason="capability_unavailable",
                evidence="The test intentionally exercises the fallback boundary.",
            )

            with self.assertRaises(MaestroError) as raised:
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="current-host-boundary",
                    assignment_id=plan["assignments"][0]["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=["tests:current-host"],
                    requested_model="gpt-5.6-sol",
                    actual_model="gpt-5.6-sol",
                    model_evidence="complete",
                    tokens={"total": 10},
                )

            self.assertEqual(
                "RUN_STAGE_OBSERVATION_INVALID",
                raised.exception.code,
            )

    def test_stage_result_must_follow_plan_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "실행 순서를 검증한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            dependent = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["depends_on"]
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="stage-order",
                task_label="실행 단계 순서",
                plan_path=plan_path,
            )
            record_execution_fallback(
                repo,
                observation_id=started["observation_id"],
                run_id="stage-order",
                reason="capability_unavailable",
                evidence="The test intentionally exercises dependency ordering.",
            )

            with self.assertRaises(MaestroError) as raised:
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="stage-order",
                    assignment_id=dependent["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=["tests:out-of-order"],
                )

            self.assertEqual("RUN_STAGE_ORDER_INVALID", raised.exception.code)

    def test_cli_exposes_plan_stage_and_finalize_lifecycle(self) -> None:
        attached = parser().parse_args(
            [
                "observe",
                "plan",
                "--observation",
                "observation-1",
                "--run-id",
                "run-1",
                "--plan",
                "/tmp/plan.json",
            ]
        )
        stage = parser().parse_args(
            [
                "observe",
                "stage",
                "--observation",
                "observation-1",
                "--run-id",
                "run-1",
                "--assignment",
                "implementation",
                "--status",
                "completed",
                "--evidence-source",
                "current_host",
                "--evidence",
                "diff:reviewed",
            ]
        )
        finalized = parser().parse_args(
            [
                "finalize",
                "--run-id",
                "run-1",
                "--outcome",
                "completed",
                "--evidence",
                "tests:passed",
                "--verifier-result",
                "passed",
            ]
        )

        self.assertEqual("plan", attached.observe_command)
        self.assertEqual("stage", stage.observe_command)
        self.assertEqual("finalize", finalized.command)

    def test_desktop_fallback_cli_requires_typed_reason_and_evidence(self) -> None:
        with self.assertRaises(SystemExit):
            parser().parse_args(
                [
                    "observe",
                    "fallback",
                    "--observation",
                    "0" * 32,
                    "--run-id",
                    "desktop-request",
                ]
            )

    def test_existing_observation_can_attach_one_explicit_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "대시보드 상호작용을 검증한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="late-fallback-run",
                task_label="브라우저 상호작용 검증",
                plan_path=plan_path,
            )
            attached = start_run_observation(
                repo,
                run_id="late-fallback-run",
                task_label="브라우저 상호작용 검증",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "interactive_required",
                    "evidence": (
                        "The task requires interaction with the open dashboard."
                    ),
                },
            )
            _observe_plan_stages(
                repo,
                started["observation_id"],
                "late-fallback-run",
                plan,
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "late-fallback-run"
            receipt_path = root / "receipt.json"
            write_json(receipt_path, receipt)

            recorded = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )

            self.assertEqual("fallback_attached", attached["status"])
            self.assertTrue(attached["writes_performed"])
            self.assertEqual("recorded", recorded["status"])

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
            started = start_desktop_request_observation(
                repo,
                run_id="viewer-run-1",
                task_label="통합 운영 뷰어 구현",
                thread_id="thread-fallback",
                turn_id="turn-fallback",
                requested_model="gpt-5.6-sol",
                plan_path=plan_path,
            )
            receipt_path = root / "receipt.json"
            _observe_plan_stages(
                repo,
                started["observation_id"],
                "viewer-run-1",
                plan,
            )
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
                {
                    "schema_version": (
                        "maestro_expertise_routing_summary_v1"
                    ),
                    "selection_state": "not_selected",
                    "selection_source": "none",
                    "route_attempt": 1,
                    "conflict_warning_codes": [],
                    "evidence": "plan_summary",
                },
                snapshot["runs"][0]["expertise"]["routing"],
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
            self.assertIsNone(snapshot["runs"][0]["tokens"])
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

    def test_definition_drift_does_not_reopen_a_recorded_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "운영 화면 상태를 정리한다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="definition-drift-run",
                task_label="정의 변경 전 완료한 작업",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": (
                        "The test does not run through a Codex App Server."
                    ),
                },
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "definition-drift-run"
            _observe_plan_stages(
                repo,
                started["observation_id"],
                "definition-drift-run",
                plan,
            )
            receipt_path = root / "receipt.json"
            write_json(receipt_path, receipt)
            recorded = record_run(
                repo,
                receipt_path,
                observation_id=started["observation_id"],
            )
            event_path = repo / recorded["event_path"]
            event = json.loads(event_path.read_text(encoding="utf-8"))
            executor_id = next(iter(event["executor_definition_digests"]))
            event["executor_definition_digests"][executor_id] = "0" * 64
            event_path.write_text(
                json.dumps(event, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            snapshot = snapshot_report(repo)

            self.assertEqual([], snapshot["runs"])
            self.assertEqual([], snapshot["inflight"])

    def test_completed_observation_becomes_receipt_stale_from_completion_time(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            started = start_run_observation(
                repo,
                run_id="receipt-stale-run",
                task_label="완료 후 기록이 누락된 작업",
            )
            observation_path = repo / started["observation_path"]
            observation = json.loads(
                observation_path.read_text(encoding="utf-8")
            )
            observation["started_at"] = "2020-01-01T00:00:00Z"
            observation["completed_at"] = "2020-01-02T00:00:00Z"
            observation["duration_ms"] = 24 * 60 * 60 * 1000
            write_json(observation_path, observation)

            snapshot = snapshot_report(repo)

            self.assertEqual("receipt_stale", snapshot["inflight"][0]["status"])
            self.assertEqual(
                observation["completed_at"],
                snapshot["inflight"][0]["completed_at"],
            )
            self.assertGreater(
                snapshot["inflight"][0]["status_elapsed_ms"],
                24 * 60 * 60 * 1000,
            )
            self.assertEqual(0, snapshot["overview"]["execution_stale"])
            self.assertEqual(0, snapshot["overview"]["receipt_pending"])
            self.assertEqual(1, snapshot["overview"]["receipt_stale"])
            self.assertEqual(1, snapshot["overview"]["stale_observations"])
            stale_attention = [
                item
                for item in snapshot["attention"]
                if item["id"] == "review_stale_run"
            ]
            self.assertEqual(1, len(stale_attention))
            self.assertEqual(
                "receipt_stale",
                stale_attention[0]["observation_status"],
            )

    def test_completed_implementation_plan_cannot_silently_skip_execution_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "CLI 동작을 구현한다",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            receipt_path = root / "receipt.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="missing-execution-evidence",
                task_label="실행 근거 누락",
                plan_path=plan_path,
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "missing-execution-evidence"
            receipt["execution_binding"] = {
                "schema_version": "maestro_execution_binding_v1",
                "mode": "explicit_fallback",
                "reason": "capability_unavailable",
                "evidence": "A receipt must not be able to self-attest execution.",
            }
            write_json(receipt_path, receipt)

            with self.assertRaises(MaestroError) as raised:
                record_run(
                    repo,
                    receipt_path,
                    observation_id=started["observation_id"],
                )

            self.assertEqual(
                "RUN_STAGE_EVIDENCE_REQUIRED",
                raised.exception.code,
            )

    def test_failed_receipt_cannot_self_attest_execution_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._initialized_repo(root)
            plan = route_goal_v2(
                "CLI 동작을 구현한다",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = root / "plan.json"
            receipt_path = root / "receipt.json"
            write_json(plan_path, plan)
            started = start_run_observation(
                repo,
                run_id="failed-self-attested-execution",
                task_label="실패 실행 근거 자체 주장",
                plan_path=plan_path,
            )
            receipt = _receipt_from_plan(plan)
            receipt["run_id"] = "failed-self-attested-execution"
            receipt["outcome"] = "failed"
            receipt["execution_binding"] = {
                "schema_version": "maestro_execution_binding_v1",
                "mode": "explicit_fallback",
                "reason": "capability_unavailable",
                "evidence": "A failed receipt must not self-attest execution.",
            }
            write_json(receipt_path, receipt)

            with self.assertRaises(MaestroError) as raised:
                record_run(
                    repo,
                    receipt_path,
                    observation_id=started["observation_id"],
                )

            self.assertEqual(
                "RUN_STAGE_EVIDENCE_REQUIRED",
                raised.exception.code,
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
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "The public host adapter cannot own this turn.",
                },
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
            _observe_plan_stages(
                repo,
                started["observation_id"],
                "host-observed-run",
                plan,
            )
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
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "The public host adapter cannot own this turn.",
                },
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
            _observe_plan_stages(
                repo,
                started["observation_id"],
                "requested-only-run",
                plan,
            )
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
                                "inputTokens": 100,
                                "outputTokens": 40,
                                "cachedInputTokens": 20,
                                "reasoningOutputTokens": 10,
                                "totalTokens": 140,
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
            self.assertEqual(140, imported["telemetry"]["tokens"]["total"])
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
                    "duration_ms": None,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 1,
                    "verifier_result": "not_run",
                    "command_artifact_ref": "tests:app-server",
                    "stage_results": [],
                },
            )
            record_run(repo, receipt_path)
            run = snapshot_report(repo)["runs"][0]
            self.assertEqual(2500, run["duration_ms"])
            self.assertEqual(140, run["tokens"]["total"])
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

    def test_run_details_use_a_routed_accessible_work_workspace(
        self,
    ) -> None:
        viewer_root = ROOT / "src/maestro/resources/viewer"
        viewer_source = (viewer_root / "app.js").read_text(encoding="utf-8")
        viewer_markup = (viewer_root / "index.html").read_text(encoding="utf-8")
        viewer_styles = (viewer_root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="run-list-view"', viewer_markup)
        self.assertIn('id="run-workspace"', viewer_markup)
        self.assertIn("function workLocation(", viewer_source)
        self.assertIn("function workSelectionFromLocation(", viewer_source)
        self.assertIn("toggle.href = workLocation(run.event_id)", viewer_source)
        self.assertIn("state.selectedRun = run.event_id", viewer_source)
        self.assertIn('text: "작업 열기"', viewer_source)
        self.assertIn("renderRunWorkspace(snapshot", viewer_source)
        self.assertIn("buildStageMap(", viewer_source)
        self.assertIn("buildStageInspector(", viewer_source)
        self.assertIn("drawWorkEdges(", viewer_source)
        self.assertIn('button.setAttribute("aria-expanded"', viewer_source)
        self.assertIn('className: "work-card-toggle"', viewer_source)
        self.assertIn("workExecutionFooterFromProjection(", viewer_source)
        self.assertIn("workPackDisclosure(", viewer_source)
        self.assertIn("workInfoDisclosure(", viewer_source)
        self.assertIn(
            "if (state.selectedStage === stageId)",
            viewer_source,
        )
        self.assertIn(
            'event.key === "Escape"',
            viewer_source,
        )
        self.assertIn(
            "containMobileNavigationFocus(event)",
            viewer_source,
        )
        self.assertIn('className: "run-flow-preview"', viewer_source)
        self.assertNotIn('id="run-detail"', viewer_markup)
        self.assertIn(
            "담당 영역별 단계·의존 관계·근거",
            viewer_markup,
        )
        self.assertIn('checkbox.type = "checkbox"', viewer_source)
        self.assertIn('id="history-bundles"', viewer_markup)
        self.assertIn(".run-flow-preview", viewer_styles)
        self.assertIn(".work-detail-layout", viewer_styles)
        self.assertIn(".work-stage-card.expanded", viewer_styles)
        self.assertIn(".work-card-detail", viewer_styles)
        self.assertIn("관계상 독립 가능", viewer_source)
        self.assertIn("실제 병렬 실행", viewer_source)
        self.assertIn("구조화된 문제와 결론 기록 없음", viewer_source)
        self.assertIn("선택·전달 기록이며", viewer_source)
        self.assertIn("실제 모델 확인 불가", viewer_source)
        self.assertIn('"완료 상태"', viewer_source)
        self.assertIn('"기록된 수정"', viewer_source)
        self.assertIn('text: "계획 단계"', viewer_source)
        self.assertIn("pendingWorkFocusRestore", viewer_source)
        self.assertIn(
            'input[name="run_display_name"]',
            viewer_source,
        )
        self.assertIn(
            'selectionStatus.id = "work-selection-status"',
            viewer_source,
        )
        self.assertNotIn(
            'inspector.setAttribute("aria-live"',
            viewer_source,
        )
        self.assertNotIn(
            'textContent = snapshot.repo_root',
            viewer_source,
        )
        self.assertIn("target.append(layout);", viewer_source)
        header_start = viewer_source.index("function buildWorkHeader(")
        header_end = viewer_source.index(
            "function buildWorkTelemetryNotice(",
            header_start,
        )
        header_source = viewer_source[header_start:header_end]
        workspace_start = viewer_source.index(
            "function renderRunWorkspace(",
        )
        workspace_end = viewer_source.index(
            "function reviewReasonText(",
            workspace_start,
        )
        workspace_source = viewer_source[workspace_start:workspace_end]
        self.assertIn("expertiseRoutingText(run)", header_source)
        self.assertIn('"work-routing-summary"', header_source)
        self.assertIn("buildWorkHeader(run, work)", workspace_source)

    def test_expertise_routing_text_distinguishes_recorded_states(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the viewer helper test")
        viewer_source = (
            ROOT / "src/maestro/resources/viewer/app.js"
        ).read_text(encoding="utf-8")
        helper_start = viewer_source.index("function routingSourceLabel(")
        helper_end = viewer_source.index("function element(", helper_start)
        script = (
            'const assert = require("node:assert/strict");\n'
            + viewer_source[helper_start:helper_end]
            + r"""
const selected = {
  expertise: {
    routing: {
      evidence: "plan_summary",
      selection_source: "work_kind",
      route_attempt: 2,
      conflict_warning_codes: ["EXPERTISE_HINTS_AMBIGUOUS"],
    },
  },
};
const notSelected = {
  expertise: {
    routing: {
      evidence: "plan_summary",
      selection_source: "none",
      route_attempt: 1,
      conflict_warning_codes: [],
    },
  },
};
const legacy = {
  expertise: {
    routing: {
      evidence: "unavailable",
      selection_source: null,
      route_attempt: null,
      conflict_warning_codes: [],
    },
  },
};
assert.equal(
  expertiseRoutingText(selected),
  "작업 종류로 선택 · 1회 보정 · 충돌: 작업 종류 간 충돌",
);
assert.equal(
  expertiseRoutingText(notSelected),
  "라우터 확인 결과 선택 없음 · 최초 선택 · 충돌 없음",
);
assert.equal(expertiseRoutingText(legacy), "선택 방식 기록 없음");
"""
        )
        completed = subprocess.run(
            [node, "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + completed.stderr,
        )

    def test_status_matrix_keeps_run_and_stage_scopes_distinct(self) -> None:
        stage_statuses = [
            "completed",
            "failed",
            "blocked",
            "skipped",
            "interrupted",
        ]
        event = {
            "event_id": "status-matrix",
            "run_id": "status-matrix",
            "task_label": "상태 매트릭스",
            "timestamp": "2026-07-28T01:00:00Z",
            "risk": "high",
            "route_depth": "deep",
            "selected_lenses": ["test-proof"],
            "selected_expertise_packs": ["software-qa"],
            "selected_decision_guides": ["qa-test-design"],
            "executor_runs": 1,
            "primary_executor_id": "lens-reviewer",
            "executor_ids": ["lens-reviewer"],
            "outcome": "corrected",
            "evidence_refs": ["tests:status-matrix"],
            "duration_ms": 100,
            "tokens": None,
            "correction_count": 1,
            "agent_calls": 5,
            "verifier_result": "passed",
            "command_artifact_ref": "tests:status-matrix",
            "plan_summary": {
                "assignments": [
                    {
                        "assignment_id": f"stage-{status}",
                        "kind": "review",
                        "executor_id": "lens-reviewer",
                        "depends_on": [],
                        "lens_ids": ["test-proof"],
                        "mutation_owner": False,
                        "read_only": True,
                        "planned_model": "gpt-5.6-terra",
                        "reasoning_effort": "medium",
                        "expertise_pack_ids": ["software-qa"],
                        "decision_guide_ids": ["qa-test-design"],
                    }
                    for status in stage_statuses
                ],
            },
            "stage_results": [
                {
                    "assignment_id": f"stage-{status}",
                    "status": status,
                    "evidence_source": "current_host",
                    "observed_at": "2026-07-28T01:00:01Z",
                    "duration_ms": 10,
                    "tokens": None,
                    "evidence_refs": [f"tests:{status}"],
                }
                for status in stage_statuses
            ],
        }

        flow, evidence = _run_flow(event)
        self.assertEqual("assignment_observation", evidence)
        self.assertEqual(
            stage_statuses,
            [stage["status"] for stage in flow],
        )
        self.assertEqual("corrected", _run_card(event)["outcome"])
        for run_outcome in (
            "completed",
            "corrected",
            "failed",
            "blocked",
            "no_change",
        ):
            self.assertEqual(
                run_outcome,
                _run_card({**event, "outcome": run_outcome})["outcome"],
            )

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
        self.assertTrue(
            signals[0]["automatic_candidate_authoring_allowed"]
        )
        self.assertFalse(signals[0]["automatic_change_allowed"])

    def test_explicit_clear_missing_expertise_can_author_one_candidate(
        self,
    ) -> None:
        events = [
            {
                "run_id": "clear-missing-expertise",
                "timestamp": "2026-07-28T00:00:00Z",
                "expertise_observations": [
                    {
                        "kind": "missing_guide",
                        "domain": "frontend page composition",
                        "pack_id": None,
                        "guide_id": None,
                        "severity": "high",
                        "reusable": True,
                        "resolution": "author_candidate",
                        "evidence_ref": "tests:composition-gap",
                    }
                ],
            }
        ]

        signals = expertise_management_signals(events)

        self.assertEqual(1, len(signals))
        self.assertEqual(
            "explicit_clear_missing_expertise",
            signals[0]["admission_basis"],
        )
        self.assertTrue(
            signals[0]["automatic_candidate_authoring_allowed"]
        )
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
                    "work_spans": [
                        application_work_span(
                            "product-design",
                            ["typography-korean"],
                            work_id=f"design-{index}",
                        )
                    ],
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
                "application_observed",
                guide["load_evidence"],
            )
            self.assertFalse(report["automatic_mutation_allowed"])
            self.assertIn("not causal proof", report["interpretation"])

    def test_pack_observations_do_not_mark_every_guide_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            events = [
                {
                    "run_id": f"design-pack-{index}",
                    "timestamp": f"2026-07-{20 + index:02d}T00:00:00Z",
                    "selected_expertise_packs": ["product-design"],
                    "selected_decision_guides": [],
                    "work_spans": [
                        application_work_span(
                            "product-design",
                            [],
                            work_id=f"design-pack-{index}",
                        )
                    ],
                    "verifier_result": "passed",
                    "correction_count": 0,
                    "expertise_observations": [
                        {
                            "kind": "trigger_miss",
                            "pack_id": "product-design",
                            "guide_id": None,
                            "severity": "high",
                        }
                    ],
                }
                for index in range(1, 4)
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
            review_items = [
                item
                for item in report["review_items"]
                if item["pack_id"] == "product-design"
            ]

            self.assertEqual("review_required", pack["utility_verdict"])
            self.assertEqual(1, len(review_items))
            self.assertIsNone(review_items[0]["guide_id"])
            self.assertTrue(all(
                guide["utility_verdict"] == "awaiting_usage"
                for guide in pack["guides"]
            ))

    def test_expertise_attention_is_grouped_by_one_owner_action(self) -> None:
        attention = _expertise_review_attention(
            [
                {
                    "pack_id": "product-design",
                    "guide_id": "design-brief",
                    "utility_verdict": "review_due",
                    "usage_count": 5,
                    "reasons": ["5 observed applications reached the review interval"],
                },
                {
                    "pack_id": "product-design",
                    "guide_id": "visual-hierarchy-layout",
                    "utility_verdict": "review_required",
                    "usage_count": 3,
                    "reasons": ["3 component observations"],
                },
            ],
            excluded_candidate_ids=set(),
        )

        self.assertEqual(1, len(attention))
        self.assertEqual("high", attention[0]["severity"])
        self.assertEqual(
            ["design-brief", "visual-hierarchy-layout"],
            attention[0]["guide_ids"],
        )

    def test_viewer_separates_expertise_lifecycle_freshness_and_evidence(
        self,
    ) -> None:
        viewer_root = ROOT / "src/maestro/resources/viewer"
        viewer_source = (viewer_root / "app.js").read_text(encoding="utf-8")
        viewer_markup = (viewer_root / "index.html").read_text(encoding="utf-8")
        viewer_styles = (viewer_root / "styles.css").read_text(
            encoding="utf-8",
        )

        self.assertIn('href="?view=overview"', viewer_markup)
        self.assertIn('href="?view=work"', viewer_markup)
        self.assertIn('href="?view=expertise"', viewer_markup)
        self.assertIn('href="?view=management"', viewer_markup)
        self.assertIn('class="destination-link"', viewer_markup)
        self.assertIn('aria-current="page"', viewer_markup)
        self.assertNotIn('role="tablist"', viewer_markup)
        self.assertNotIn('role="tabpanel"', viewer_markup)
        self.assertIn('id="pipeline-summary"', viewer_markup)
        self.assertIn('href="#main-content"', viewer_markup)
        self.assertIn('const VIEW_NAMES = new Set(["overview", "work", "expertise", "management"])', viewer_source)
        self.assertIn('function viewFromLocation()', viewer_source)
        self.assertIn(
            'function restoreViewFromLocation(options = {})',
            viewer_source,
        )
        self.assertIn("function expertiseRoutingText(run)", viewer_source)
        self.assertIn("선택 방식 기록 없음", viewer_source)
        self.assertIn("라우터 확인 결과 선택 없음", viewer_source)
        self.assertIn('"전문성 라우팅"', viewer_source)
        self.assertIn('url.searchParams.set("view", viewName)', viewer_source)
        self.assertIn('`${url.pathname}${url.search}${url.hash}`', viewer_source)
        self.assertIn('window.addEventListener("popstate"', viewer_source)
        self.assertIn('!VIEW_NAMES.has(view)', viewer_source)
        self.assertIn('id="navigation-toggle"', viewer_markup)
        self.assertIn('aria-expanded="false"', viewer_markup)
        self.assertIn('aria-controls="primary-navigation"', viewer_markup)
        self.assertIn('id="navigation-scrim"', viewer_markup)
        self.assertIn('event.key === "Escape" && navigationIsOpen()', viewer_source)
        self.assertIn('closeMobileNavigation({ returnFocus: true })', viewer_source)
        self.assertIn('mobileNavigation.addEventListener("change"', viewer_source)
        self.assertIn('duration.dataset.label = "걸린 시간"', viewer_source)
        self.assertIn("@media (prefers-reduced-motion: reduce)", viewer_styles)
        self.assertIn("전문 지식 묶음의 사용 단계", viewer_markup)
        self.assertIn('evidence_gathering: "사용 결과 수집 중"', viewer_source)
        self.assertIn('stable: "변경이 드문 기준"', viewer_source)
        self.assertIn(
            "현재 사용 가능 · 프로젝트에 미확정",
            viewer_source,
        )
        self.assertIn("후보 파일은 자동 삭제되지 않으며", viewer_source)
        self.assertIn("프로젝트에 확정", viewer_source)
        self.assertIn('"기본 Pack 반영 가능"', viewer_source)
        self.assertIn('"기본 Pack 반영됨"', viewer_source)
        self.assertIn('"기본 Pack으로 올리기"', viewer_source)
        self.assertIn('action: "promote_global"', viewer_source)
        self.assertIn(
            "이 프로젝트에 확정된 스냅샷을 Harness 기본 Pack 소스에",
            viewer_source,
        )
        self.assertIn(
            "검증된 후보나 프로젝트 확정본을 한 번의 확인",
            viewer_markup,
        )
        self.assertIn(
            'export: "내부 기여 묶음 만들기"',
            viewer_source,
        )
        self.assertIn("promotion.owner_prompt_due", viewer_source)
        self.assertNotIn("const exportButton", viewer_source)
        self.assertIn(
            "기본 Pack 반영 여부 확인",
            viewer_source,
        )
        self.assertIn(
            "변경안 전체를 프로젝트에 확정",
            viewer_source,
        )
        self.assertIn('action: "approve_change_set"', viewer_source)
        self.assertIn(
            "이번 후보는 기본 Pack으로 올리지 않음",
            viewer_source,
        )
        self.assertIn('action: "decline_promotion"', viewer_source)
        self.assertIn(
            "사용 기한 종료 · 기준 다시 확인 필요",
            viewer_source,
        )
        self.assertIn(
            "같은 파일의 검증 명령만 다시 실행하는 뜻은 아닙니다",
            viewer_source,
        )
        self.assertIn('className: "candidate-action-bar"', viewer_source)
        self.assertLess(
            viewer_source.index('className: "candidate-action-bar"'),
            viewer_source.index('className: "candidate-runtime-summary"'),
        )
        self.assertIn("최근 반영 확인 작업", viewer_source)
        self.assertIn("후보 Pack 내용", viewer_source)
        self.assertIn("판단 체크리스트", viewer_source)
        self.assertIn("연결된 평가 사례", viewer_source)
        self.assertIn("details.candidate-detail", viewer_source)
        self.assertIn("Guide를 누르면 기준·출처·평가가 펼쳐집니다", viewer_source)
        self.assertIn(
            "내부 기여 묶음은 저장소 간 전달에만 사용",
            viewer_markup,
        )
        self.assertIn('id="project-select"', viewer_markup)
        self.assertIn('id="project-rename-form"', viewer_markup)
        self.assertIn("프로젝트 ID는 바뀌지 않으며", viewer_markup)
        self.assertIn('"X-Maestro-Project"', viewer_source)
        self.assertIn('fetch("/api/projects"', viewer_source)
        self.assertIn("프로젝트 ${state.projects.length}개 기억됨", viewer_source)
        self.assertIn('id="project-catalog-state"', viewer_markup)
        self.assertIn('"/api/project-labels/apply"', viewer_source)
        self.assertIn(
            "function renderProjectLoadFailure(reason, projectId",
            viewer_source,
        )
        self.assertIn(
            "선택한 프로젝트의 데이터를 불러오지 못했습니다",
            viewer_source,
        )
        self.assertIn("후보에서 선택할 수 있는 두 경로", viewer_markup)
        self.assertIn("후보 자동 사용 종료일", viewer_markup)
        self.assertIn("프로젝트에 확정", viewer_markup)
        self.assertIn("기본 Pack으로 올리기", viewer_markup)
        self.assertIn("서로 다른 작업에서 적용이 5회 확인", viewer_markup)
        self.assertIn(
            "변경 내용 확인 → Harness 소스 반영",
            viewer_markup,
        )
        self.assertIn(
            "Codex가 기본 Pack 반영 여부를 사용자에게 확인",
            viewer_markup,
        )
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
        self.assertIn('<details class="meaning-guide">', viewer_markup)
        self.assertNotIn('<details class="meaning-guide" open>', viewer_markup)
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
        self.assertIn(
            'PROJECT_STATE_STALE: "프로젝트 상태 갱신 필요"',
            viewer_source,
        )
        self.assertIn(
            '"로컬 데이터 연결됨 · 기준선 갱신 필요"',
            viewer_source,
        )
        self.assertIn(
            'stale_registry: "기준선 갱신 전 · 기록 판단 보류"',
            viewer_source,
        )
        self.assertIn("function responseError", viewer_source)
        self.assertIn(
            'PROJECT_EXPERTISE_INVALID: "전문 지식 활성 항목 충돌"',
            viewer_source,
        )
        self.assertIn(
            "같은 ID의 전역 Pack과 프로젝트 Pack이 서로 다른 내용으로",
            viewer_source,
        )
        self.assertNotIn("로컬 데이터 연결 오류", viewer_source)
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
                        "운영 대시보드",
                        response.read().decode("utf-8"),
                    )
                with urllib.request.urlopen(
                    f"{base}/assets/project-switch.js",
                    timeout=5,
                ) as response:
                    self.assertEqual(200, response.status)
                    self.assertIn(
                        "createProjectSnapshotLoader",
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

    def test_project_snapshot_loader_uses_the_latest_selection(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the browser state test")
        loader_path = (
            ROOT
            / "src/maestro/resources/viewer/project-switch.js"
        )
        script = r"""
const assert = require("node:assert/strict");
const {
  createProjectSnapshotLoader,
} = require(process.argv[1]);

const pending = new Map();
const events = [];
const loader = createProjectSnapshotLoader({
  loadSnapshot(projectId, signal) {
    return new Promise((resolve, reject) => {
      pending.set(projectId, { resolve, reject });
      signal.addEventListener("abort", () => {
        const reason = new Error("superseded");
        reason.name = "AbortError";
        reject(reason);
      }, { once: true });
    });
  },
  onStart(projectId) {
    events.push(`start:${projectId}`);
  },
  onSuccess(_snapshot, projectId) {
    events.push(`success:${projectId}`);
  },
  onFailure(_reason, projectId) {
    events.push(`failure:${projectId}`);
  },
  onSettled(projectId) {
    events.push(`settled:${projectId}`);
  },
});

(async () => {
  const first = loader.load("project-1");
  const second = loader.load("project-2");
  pending.get("project-2").resolve({ project: "project-2" });
  const [firstResult, secondResult] = await Promise.all([first, second]);

  assert.equal(firstResult.status, "superseded");
  assert.equal(secondResult.status, "loaded");
  assert.deepEqual(events, [
    "start:project-1",
    "start:project-2",
    "success:project-2",
    "settled:project-2",
  ]);

  const third = loader.load("project-3");
  pending.get("project-3").reject(new Error("snapshot failed"));
  const thirdResult = await third;
  assert.equal(thirdResult.status, "failed");
  assert.deepEqual(events.slice(-3), [
    "start:project-3",
    "failure:project-3",
    "settled:project-3",
  ]);
})().catch((reason) => {
  console.error(reason);
  process.exitCode = 1;
});
"""
        completed = subprocess.run(
            [node, "-e", script, str(loader_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + completed.stderr,
        )

        viewer_source = (
            ROOT / "src/maestro/resources/viewer/app.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("event.target.disabled = true", viewer_source)
        self.assertIn(
            "await refresh(state.selectedProject)",
            viewer_source,
        )

    def test_dashboard_switches_only_allowlisted_projects_without_path_leak(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first = self._initialized_repo(first_root)
            second = self._initialized_repo(second_root)
            for repo, project_id in (
                (first, "first-project"),
                (second, "second-project"),
            ):
                project_path = repo / ".maestro/project.json"
                project = json.loads(project_path.read_text(encoding="utf-8"))
                project["project_id"] = project_id
                write_json(project_path, project)

            server, token, url = create_dashboard_server(
                first,
                project_paths=[second, first],
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]

            def get(path: str, **headers: str) -> dict[str, object]:
                request = urllib.request.Request(
                    f"{base}{path}",
                    headers={"X-Maestro-Token": token, **headers},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            try:
                inventory = get("/api/projects")
                self.assertEqual(2, len(inventory["projects"]))
                self.assertEqual(
                    "project-1",
                    inventory["default_project_id"],
                )
                encoded_inventory = json.dumps(inventory)
                self.assertNotIn(str(first.resolve()), encoded_inventory)
                self.assertNotIn(str(second.resolve()), encoded_inventory)

                first_snapshot = get(
                    "/api/snapshot",
                    **{"X-Maestro-Project": "project-1"},
                )
                second_snapshot = get(
                    "/api/snapshot",
                    **{"X-Maestro-Project": "project-2"},
                )
                self.assertEqual(
                    str(first.resolve()),
                    first_snapshot["repo_root"],
                )
                self.assertEqual(
                    str(second.resolve()),
                    second_snapshot["repo_root"],
                )

                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    get(
                        "/api/snapshot",
                        **{"X-Maestro-Project": "project-999"},
                    )
                self.assertEqual(409, rejected.exception.code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_dashboard_reads_stale_registry_project_without_mutating_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            lock_path = repo / ".maestro/lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["registry"]["sha256"] = "0" * 64
            write_json(lock_path, lock)

            before = lock_path.read_bytes()
            server, token, url = create_dashboard_server(repo, window=20)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]
            try:
                request = urllib.request.Request(
                    f"{base}/api/snapshot",
                    headers={"X-Maestro-Token": token},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read())
                    self.assertEqual(200, response.status)

                self.assertEqual(
                    "stale_registry",
                    payload["governance"]["evidence_status"],
                )
                self.assertEqual(
                    "PROJECT_STATE_STALE",
                    payload["governance"]["error"]["code"],
                )
                self.assertEqual(
                    "PROJECT_STATE_STALE",
                    payload["status"]["governance"]["error"]["code"],
                )
                self.assertEqual(before, lock_path.read_bytes())
                self.assertFalse(payload["writes_performed"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_dashboard_preview_cannot_be_applied_to_another_project(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first = self._initialized_repo(first_root)
            second = self._initialized_repo(second_root)
            self._add_verification_candidate(first)
            self._add_verification_candidate(second)
            candidate = verification_inventory(first)["candidates"][0]
            server, token, url = create_dashboard_server(
                first,
                project_paths=[second],
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]

            def post(
                path: str,
                payload: dict[str, object],
                project_id: str,
            ) -> dict[str, object]:
                request = urllib.request.Request(
                    f"{base}{path}",
                    method="POST",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                        "X-Maestro-Project": project_id,
                        "Origin": base,
                    },
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            try:
                preview = post(
                    "/api/verification-approvals/preview",
                    {"candidate_id": candidate["candidate_id"]},
                    "project-1",
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    post(
                        "/api/verification-approvals/apply",
                        {
                            "plan_id": preview["plan_id"],
                            "plan_digest": preview["plan_digest"],
                        },
                        "project-2",
                    )
                self.assertEqual(409, rejected.exception.code)
                self.assertEqual(
                    [],
                    json.loads(
                        (second / ".maestro/project.json").read_text(
                            encoding="utf-8"
                        )
                    )["verification_commands"],
                )

                applied = post(
                    "/api/verification-approvals/apply",
                    {
                        "plan_id": preview["plan_id"],
                        "plan_digest": preview["plan_digest"],
                    },
                    "project-1",
                )
                self.assertEqual("approved", applied["status"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_dashboard_project_display_label_is_local_bounded_and_persistent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._initialized_repo(Path(temporary))
            project_path = repo / ".maestro/project.json"
            original_project_id = json.loads(
                project_path.read_text(encoding="utf-8")
            )["project_id"]
            server, token, url = create_dashboard_server(repo)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = url.split("/#token=", 1)[0]

            def post(label: str) -> dict[str, object]:
                request = urllib.request.Request(
                    f"{base}/api/project-labels/apply",
                    method="POST",
                    data=json.dumps({"label": label}).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                        "X-Maestro-Project": "project-1",
                        "Origin": base,
                    },
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            try:
                renamed = post("마에스트로 개발")
                repeated = post("마에스트로 개발")
                inventory_request = urllib.request.Request(
                    f"{base}/api/projects",
                    headers={"X-Maestro-Token": token},
                )
                with urllib.request.urlopen(
                    inventory_request,
                    timeout=5,
                ) as response:
                    inventory = json.loads(response.read())

                self.assertEqual("set", renamed["status"])
                self.assertTrue(renamed["writes_performed"])
                self.assertEqual("already_set", repeated["status"])
                self.assertFalse(repeated["writes_performed"])
                self.assertEqual(
                    "마에스트로 개발",
                    inventory["projects"][0]["label"],
                )
                self.assertEqual(
                    original_project_id,
                    json.loads(
                        project_path.read_text(encoding="utf-8")
                    )["project_id"],
                )
                preferences_path = (
                    repo
                    / ".maestro/state/dashboard/preferences.json"
                )
                preferences = json.loads(
                    preferences_path.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    "maestro_dashboard_preferences_v1",
                    preferences["schema_version"],
                )
                self.assertEqual(
                    "마에스트로 개발",
                    preferences["display_label"],
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    post("잘못된\n이름")
                self.assertEqual(409, rejected.exception.code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            restarted, _token, _url = create_dashboard_server(repo)
            try:
                self.assertEqual(
                    "마에스트로 개발",
                    restarted.project_inventory()["projects"][0]["label"],
                )
            finally:
                restarted.server_close()

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
            ("technical-seo", "maestro-technical-seo"),
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
        self.assertIn("--color-canvas: #f6f7f9", self.theme)
        self.assertIn("--color-blue: #0969da", self.theme)
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
