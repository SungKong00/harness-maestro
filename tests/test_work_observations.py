from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.support import (
    ROOT,
    apply_fresh_init,
    record_managed_completion_graph,
    write_json,
)

from maestro.errors import MaestroError
from maestro.expertise_routing import normalize_route_hints
from maestro.governance import finalize_run
from maestro.observations import (
    observation_receipt_fields,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.snapshot import snapshot_report


class WorkObservationTests(unittest.TestCase):
    def _repo_and_plan(
        self,
        root: Path,
    ) -> tuple[Path, dict[str, object], Path]:
        repo = root / "repo"
        repo.mkdir()
        apply_fresh_init(repo)
        plan = route_goal_v2(
            "실제 위임 작업을 관찰한다",
            "medium",
            intent="implementation",
            repo_path=repo,
        )
        plan_path = root / "plan.json"
        write_json(plan_path, plan)
        return repo, plan, plan_path

    def test_work_attempts_flow_from_observation_into_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="observed-work",
                task_label="실제 위임 관찰",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "The test exercises current-Host work observations.",
                },
            )
            observation_id = started["observation_id"]
            implementation = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["kind"] == "implementation"
            )

            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="orchestrator",
                assignment_id=implementation["assignment_id"],
                kind="orchestration",
                role="메인 오케스트레이터",
                executor_id=implementation["executor_id"],
                task_summary="작업을 분해하고 위임 결과를 합성합니다.",
                read_only=False,
                lens_ids=["data-integrity"],
                expertise_evidence="selection_only",
            )
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="domain-review",
                parent_work_id="orchestrator",
                kind="review",
                role="도메인 검토 담당",
                executor_id="lens-reviewer",
                task_summary="계획과 실제 실행의 데이터 경계를 검토합니다.",
                read_only=True,
                requested_model="gpt-5.6-terra",
                requested_reasoning_effort="medium",
                model_evidence="host_request",
                lens_ids=["data-integrity"],
                expertise_evidence="selection_only",
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="domain-review",
                status="completed",
                result_summary="계획 Assignment와 실제 위임을 분리해야 합니다.",
                evidence_refs=["src/maestro/observations.py::_plan_summary"],
            )
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="synthesis",
                parent_work_id="orchestrator",
                kind="synthesis",
                role="결과 합성 담당",
                executor_id=implementation["executor_id"],
                task_summary="위임 결과를 구현 경계로 합성합니다.",
                read_only=False,
                joins_work_ids=["domain-review"],
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="synthesis",
                status="completed",
                result_summary="독립 실행 span과 계획 binding을 채택했습니다.",
                evidence_refs=["tests/test_work_observations.py"],
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="orchestrator",
                status="completed",
                result_summary="위임 결과를 합성하고 구현을 완료했습니다.",
                evidence_refs=["tests/test_work_observations.py"],
            )
            observed = observation_receipt_fields(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
            )
            self.assertEqual(3, len(observed["work_spans"]))
            self.assertEqual(
                {
                    "schema_version": "maestro_expertise_routing_summary_v1",
                    "selection_state": "not_selected",
                    "selection_source": "none",
                    "route_attempt": 1,
                    "conflict_warning_codes": [],
                },
                observed["plan_summary"]["expertise_routing"],
            )
            self.assertIsNone(
                observed["work_spans"][1]["applied_model"],
            )

            for assignment in plan["assignments"]:
                record_stage_observation(
                    repo,
                    observation_id=observation_id,
                    run_id="observed-work",
                    assignment_id=assignment["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=[
                        f"tests:stage:{assignment['assignment_id']}"
                    ],
                )
            verification = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["kind"] == "verification"
            )
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="orchestrator-verification",
                assignment_id=verification["assignment_id"],
                kind="verification",
                role="오케스트레이터 결과 검증 담당",
                executor_id=verification["executor_id"],
                task_summary="관찰된 구현 오케스트레이션 결과를 검증합니다.",
                read_only=verification["read_only"],
                source="host_adapter",
                depends_on_work_ids=["orchestrator"],
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                work_id="orchestrator-verification",
                status="completed",
                result_summary="관찰된 구현 오케스트레이션 검증이 완료되었습니다.",
                evidence_refs=["tests:test_work_observations:verification"],
            )
            record_managed_completion_graph(
                repo,
                observation_id=observation_id,
                run_id="observed-work",
                plan=plan,
            )
            finalized = finalize_run(
                repo,
                run_id="observed-work",
                observation_id=observation_id,
                outcome="completed",
                evidence_refs=["tests:test_work_observations"],
                verifier_result="passed",
                command_artifact_ref="tests:test_work_observations",
            )
            event = json.loads(
                (repo / finalized["event_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                [
                    "orchestrator",
                    "domain-review",
                    "synthesis",
                    "orchestrator-verification",
                    "fixture-completion-implementation",
                    "fixture-completion-verification",
                    "fixture-completion-final",
                ],
                [span["work_id"] for span in event["work_spans"]],
            )
            work_detail = snapshot_report(repo)["runs"][0]["work_detail"]
            self.assertEqual(
                "maestro_work_detail_v2",
                work_detail["schema_version"],
            )
            self.assertEqual(
                "observed",
                work_detail["execution"]["mode"],
            )
            self.assertEqual(
                2,
                work_detail["execution"]["summary"]["report_count"],
            )
            orchestrator_card = next(
                card
                for card in work_detail["execution"]["cards"]
                if card["work_id"] == "orchestrator"
            )
            self.assertEqual(
                implementation["model_route"]["selected_model"],
                orchestrator_card["assignment"]["model_route"][
                    "route_recommended"
                ],
            )
            self.assertEqual(
                implementation["model_route"]["model_route_id"],
                orchestrator_card["assignment"]["model_route"][
                    "model_route_id"
                ],
            )
            self.assertEqual(
                "plan_summary",
                snapshot_report(repo)["runs"][0]["expertise"]["routing"][
                    "evidence"
                ],
            )

    def test_assignment_work_preserves_fallback_access_and_spawn_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="assignment-work-policy",
                task_label="Assignment 작업 권한",
                plan_path=plan_path,
            )
            implementation = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["kind"] == "implementation"
            )

            with self.assertRaises(MaestroError) as raised:
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="assignment-work-policy",
                    work_id="writer",
                    assignment_id=implementation["assignment_id"],
                    kind="orchestration",
                    role="writer",
                    executor_id=implementation["executor_id"],
                    task_summary="Execute the planned writer work.",
                    read_only=implementation["read_only"],
                )
            self.assertEqual(
                "RUN_EXECUTION_FALLBACK_REQUIRED",
                raised.exception.code,
            )

            observation = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="assignment-work-policy",
            )
            self.assertEqual([], observation["work_spans"])

            verification = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["kind"] == "verification"
            )
            with self.assertRaises(MaestroError) as raised:
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="assignment-work-policy",
                    work_id="wrong-access",
                    assignment_id=verification["assignment_id"],
                    kind="review",
                    role="reviewer",
                    executor_id=verification["executor_id"],
                    task_summary="Attempt mismatched write access.",
                    read_only=not verification["read_only"],
                    source="host_adapter",
                )
            self.assertEqual(
                "WORK_ASSIGNMENT_ACCESS_MISMATCH",
                raised.exception.code,
            )

            with self.assertRaises(MaestroError) as raised:
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="assignment-work-policy",
                    work_id="forbidden-child",
                    assignment_id=verification["assignment_id"],
                    kind="delegation",
                    role="child",
                    executor_id=verification["executor_id"],
                    task_summary="Attempt forbidden delegation.",
                    read_only=verification["read_only"],
                    source="host_adapter",
                )
            self.assertEqual(
                "WORK_DELEGATION_FORBIDDEN",
                raised.exception.code,
            )

    def test_successful_run_outcome_cannot_override_failed_stage_facts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="stage-outcome-conflict",
                task_label="단계 결과 우선",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "The test exercises terminal stage consistency.",
                },
            )
            for assignment in plan["assignments"]:
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="stage-outcome-conflict",
                    assignment_id=assignment["assignment_id"],
                    status=(
                        "failed"
                        if assignment["kind"] == "implementation"
                        else "skipped"
                    ),
                    evidence_source="current_host",
                    evidence_refs=[
                        f"tests:stage:{assignment['assignment_id']}"
                    ],
                )

            with self.assertRaises(MaestroError) as raised:
                finalize_run(
                    repo,
                    run_id="stage-outcome-conflict",
                    observation_id=started["observation_id"],
                    outcome="completed",
                    evidence_refs=["tests:stage-outcome-conflict"],
                    verifier_result="not_run",
                    command_artifact_ref="tests:stage-outcome-conflict",
                )
            self.assertEqual(
                "RUN_STAGE_OUTCOME_CONFLICT",
                raised.exception.code,
            )

    def test_corrected_routing_summary_flows_into_event_and_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "내부 경계를 정리한다"
            initial = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            corrected = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                route_hints=normalize_route_hints(
                    work_kinds=[
                        "software-structure",
                        "content-claim",
                    ],
                    route_attempt=2,
                    prior_plan_id=initial["plan_id"],
                    prior_source_route_digest=initial[
                        "source_route_digest"
                    ],
                ),
                prior_route_plan=initial,
            )
            plan_path = root / "corrected-plan.json"
            write_json(plan_path, corrected)
            started = start_run_observation(
                repo,
                run_id="corrected-routing",
                task_label="보정 라우팅 관찰",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "Fixture observes the current-Host route.",
                },
            )
            for assignment in corrected["assignments"]:
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="corrected-routing",
                    assignment_id=assignment["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=[
                        f"tests:stage:{assignment['assignment_id']}"
                    ],
                )
            record_managed_completion_graph(
                repo,
                observation_id=started["observation_id"],
                run_id="corrected-routing",
                plan=corrected,
            )
            finalized = finalize_run(
                repo,
                run_id="corrected-routing",
                observation_id=started["observation_id"],
                outcome="completed",
                evidence_refs=["tests:corrected-routing"],
                verifier_result="passed",
                command_artifact_ref="tests:corrected-routing",
            )
            event = json.loads(
                (repo / finalized["event_path"]).read_text(encoding="utf-8")
            )

            self.assertEqual(
                {
                    "schema_version": "maestro_expertise_routing_summary_v1",
                    "selection_state": "selected",
                    "selection_source": "work_kind",
                    "route_attempt": 2,
                    "conflict_warning_codes": [
                        "EXPERTISE_HINTS_AMBIGUOUS"
                    ],
                },
                event["plan_summary"]["expertise_routing"],
            )
            self.assertEqual(
                {
                    **event["plan_summary"]["expertise_routing"],
                    "evidence": "plan_summary",
                },
                snapshot_report(repo)["runs"][0]["expertise"]["routing"],
            )

    def test_work_binding_must_reference_attached_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="invalid-binding",
                task_label="잘못된 작업 연결",
                plan_path=plan_path,
            )
            with self.assertRaises(MaestroError) as raised:
                record_work_start(
                    repo,
                    observation_id=started["observation_id"],
                    run_id="invalid-binding",
                    work_id="unknown-work",
                    assignment_id="unknown-assignment",
                    kind="delegation",
                    role="검토 담당",
                    executor_id="lens-reviewer",
                    task_summary="존재하지 않는 계획 단계에 연결합니다.",
                    read_only=True,
                )
            self.assertEqual(
                "WORK_ASSIGNMENT_BINDING_INVALID",
                raised.exception.code,
            )

    def test_complete_stream_contract_flows_to_snapshot_card(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="complete-stream",
                task_label="완전한 작업 stream",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "Fixture supplies a bounded complete stream.",
                },
            )
            observation_id = started["observation_id"]
            assignment = next(
                item
                for item in plan["assignments"]
                if item["kind"] == "implementation"
            )
            partial_binding = {
                "interface": "codex_app_server",
                "version": "codex-cli 0.144.1",
                "schema_digest": "a" * 64,
                "capability": "full_stream",
                "correlation_id": "complete-stream-work",
                "event_coverage": "partial_stream",
            }
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="complete-stream",
                work_id="implementation-work",
                assignment_id=assignment["assignment_id"],
                kind="implementation",
                role="구현 담당",
                executor_id=assignment["executor_id"],
                task_summary="작업 카드의 검증된 정보를 구현합니다.",
                read_only=False,
                source="codex_app_server",
                requested_model="gpt-5.6-terra",
                requested_reasoning_effort="high",
                model_evidence="host_request",
                expertise_pack_ids=["product-design"],
                decision_guide_ids=["visual-hierarchy-layout"],
                lens_ids=["user-flow"],
                expertise_evidence="selection_only",
                source_binding=partial_binding,
                event_started_at="2026-07-28T01:00:00Z",
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="complete-stream",
                work_id="implementation-work",
                status="completed",
                result_summary="인라인 확장 카드 계약을 구현했습니다.",
                evidence_refs=["tests:test_complete_stream"],
                applied_model="gpt-5.6-sol",
                model_evidence="complete",
                expertise_evidence="application_observed",
                source_binding={
                    **partial_binding,
                    "event_coverage": "complete_stream",
                },
                model_observation={
                    "observed_model": None,
                    "coverage": "complete_stream",
                    "reroutes": [
                        {
                            "from_model": "gpt-5.6-terra",
                            "to_model": "gpt-5.6-sol",
                            "reason": "capacity",
                        }
                    ],
                },
                usage={
                    "last": {
                        "input": 10,
                        "output": 5,
                        "cached": 2,
                        "reasoning": 3,
                        "total": 20,
                    },
                    "total": {
                        "input": 100,
                        "output": 50,
                        "cached": 20,
                        "reasoning": 30,
                        "total": 200,
                    },
                    "scope": "work_turn",
                    "attribution": "direct",
                    "timing_coverage": "host_event",
                    "cost": None,
                },
                outcome={
                    "finding_summary": "오른쪽 상세 칸이 흐름을 분리했습니다.",
                    "conclusion": "상세은 카드 안에서 열어야 합니다.",
                    "decision": "인라인 확장 구조를 채택합니다.",
                    "next_action": "verify",
                    "consumed_work_ids": [],
                    "handoff": {
                        "purpose": "반응형과 접근성을 검증합니다.",
                        "completion_criteria": "fixture와 브라우저 검증이 통과합니다.",
                    },
                    "artifacts": [],
                    "verification": None,
                },
                event_ended_at="2026-07-28T01:00:03Z",
                event_duration_ms=3000,
            )
            for item in plan["assignments"]:
                record_stage_observation(
                    repo,
                    observation_id=observation_id,
                    run_id="complete-stream",
                    assignment_id=item["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=[
                        f"tests:stage:{item['assignment_id']}"
                    ],
                )
            verification = next(
                item
                for item in plan["assignments"]
                if item["kind"] == "verification"
            )
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="complete-stream",
                work_id="implementation-work-verification",
                assignment_id=verification["assignment_id"],
                kind="verification",
                role="완전한 stream 검증 담당",
                executor_id=verification["executor_id"],
                task_summary="완전한 implementation stream 결과를 검증합니다.",
                read_only=verification["read_only"],
                source="host_adapter",
                depends_on_work_ids=["implementation-work"],
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="complete-stream",
                work_id="implementation-work-verification",
                status="completed",
                result_summary="완전한 implementation stream 검증이 완료되었습니다.",
                evidence_refs=["tests:test_complete_stream:verification"],
            )
            record_managed_completion_graph(
                repo,
                observation_id=observation_id,
                run_id="complete-stream",
                plan=plan,
            )
            finalized = finalize_run(
                repo,
                run_id="complete-stream",
                observation_id=observation_id,
                outcome="completed",
                evidence_refs=["tests:test_complete_stream"],
                verifier_result="passed",
                command_artifact_ref="tests:test_complete_stream",
            )
            event = json.loads(
                (repo / finalized["event_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                "maestro_work_span_v2",
                event["work_spans"][0]["schema_version"],
            )
            self.assertEqual(
                ["gpt-5.6-sol"],
                event["execution_measurements"]["model"]["applied"],
            )
            self.assertEqual(
                200,
                event["execution_measurements"]["tokens"]["value"]["total"],
            )
            self.assertEqual(
                "direct_work_attempts",
                event["execution_measurements"]["tokens"]["source"],
            )
            sealed_measurements = observation_receipt_fields(
                repo,
                observation_id=observation_id,
                run_id="complete-stream",
            )["execution_measurements"]
            self.assertEqual(
                sealed_measurements,
                event["execution_measurements"],
            )
            self.assertTrue(
                any(
                    item["model"] == "complete"
                    and item["tokens"] == "complete"
                    for item in sealed_measurements["producer_coverage"]
                )
            )
            self.assertTrue(
                any(
                    item["model"] == "unavailable"
                    and item["tokens"] == "unavailable"
                    for item in sealed_measurements["producer_coverage"]
                )
            )
            card = snapshot_report(repo)["runs"][0]["work_detail"][
                "execution"
            ]["cards"][0]
            self.assertEqual(
                "인라인 확장 구조를 채택합니다.",
                card["summary"]["decision"],
            )
            self.assertEqual("actual", card["execution_facts"]["model"]["kind"])
            self.assertEqual(
                200,
                card["execution_facts"]["tokens"]["value"]["total"],
            )
            self.assertEqual(
                "application_observed",
                card["expertise"]["evidence"],
            )

    def test_viewer_prefers_observed_work_without_overclaiming_models(self) -> None:
        source = (
            ROOT / "src/maestro/resources/viewer/app.js"
        ).read_text(encoding="utf-8")
        self.assertIn("관계상 첫 단계부터 최종 결과까지", source)
        self.assertIn("buildObservedWorkCardDetail", source)
        self.assertIn("지시·보고·다음 판단", source)
        self.assertIn("담당 전문지식", source)
        self.assertIn("실제 모델 확인 불가", source)
        self.assertNotIn(
            "완전한 Host 실행 이벤트에서 확인했습니다.",
            source,
        )
        self.assertIn("work.execution?.mode === \"observed\"", source)


if __name__ == "__main__":
    unittest.main()
