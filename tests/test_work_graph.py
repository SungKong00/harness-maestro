from __future__ import annotations

import json
import unittest

from maestro.errors import MaestroError
from maestro.work import (
    append_work_span,
    build_work_graph,
    complete_work_span,
    finish_work_span,
    new_work_span,
    project_observed_work,
    validate_work_span,
    validate_work_spans,
)
from tests.support import ROOT


def _span(
    work_id: str,
    *,
    parent_work_id: str | None = None,
    assignment_id: str | None = None,
    kind: str = "delegation",
    followup_of_work_id: str | None = None,
    joins_work_ids: list[str] | None = None,
    expertise_pack_ids: list[str] | None = None,
) -> dict[str, object]:
    return new_work_span(
        work_id=work_id,
        parent_work_id=parent_work_id,
        assignment_id=assignment_id,
        kind=kind,
        role="검토 담당",
        executor_id="lens-reviewer",
        task_summary=f"{work_id}의 경계를 검토합니다.",
        read_only=True,
        source="current_host",
        started_at="2026-07-28T01:00:00Z",
        timing_evidence="current_host_clock",
        followup_of_work_id=followup_of_work_id,
        joins_work_ids=joins_work_ids,
        requested_model="gpt-5.6-terra",
        requested_reasoning_effort="medium",
        model_evidence="host_request",
        lens_ids=["data-integrity"],
        expertise_pack_ids=expertise_pack_ids,
        expertise_evidence="selection_only",
    )


def _terminal_complete_stream(
    work_id: str,
    *,
    started_at: str,
    ended_at: str,
    duration_ms: int,
    schema_digest: str = "a" * 64,
    reroutes: list[dict[str, str]] | None = None,
    joins_work_ids: list[str] | None = None,
    outcome: dict[str, object] | None = None,
) -> dict[str, object]:
    requested = "gpt-5.6-terra"
    reroute_values = list(reroutes or [])
    applied = (
        reroute_values[-1]["to_model"]
        if reroute_values
        else requested
    )
    running = new_work_span(
        work_id=work_id,
        kind="delegation",
        role="실행 담당",
        executor_id="codex",
        task_summary=f"{work_id} 작업",
        read_only=True,
        source="codex_app_server",
        started_at=started_at,
        timing_evidence="host_event",
        joins_work_ids=joins_work_ids,
        requested_model=requested,
        requested_reasoning_effort="medium",
        model_evidence="host_request",
        source_binding={
            "interface": "codex_app_server",
            "version": "codex-cli 0.144.1",
            "schema_digest": schema_digest,
            "capability": "full_stream",
            "correlation_id": f"source-{work_id}",
            "event_coverage": "partial_stream",
        },
    )
    return complete_work_span(
        running,
        status="completed",
        result_summary=f"{work_id} 완료",
        ended_at=ended_at,
        duration_ms=duration_ms,
        evidence_refs=[f"fixture:{work_id}"],
        applied_model=applied,
        model_evidence="complete",
        source_binding={
            **running["source_binding"],
            "event_coverage": "complete_stream",
        },
        model_observation={
            "observed_model": None,
            "coverage": "complete_stream",
            "reroutes": reroute_values,
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
        outcome=outcome,
    )


class WorkContractTests(unittest.TestCase):
    def test_event_and_receipt_publish_the_same_v2_work_span_schema(
        self,
    ) -> None:
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
            schemas[0]["$defs"]["workSpan"],
            schemas[1]["$defs"]["workSpan"],
        )
        properties = schemas[0]["$defs"]["workSpan"]["properties"]
        for field in (
            "source_binding",
            "model_observation",
            "usage",
            "outcome",
            "diagnostics",
        ):
            self.assertFalse(properties[field]["additionalProperties"])

    def test_running_and_terminal_spans_preserve_evidence_boundaries(self) -> None:
        running = _span("domain-review", assignment_id="implementation")
        self.assertTrue(validate_work_spans([running]))
        self.assertIsNone(running["applied_model"])
        completed = complete_work_span(
            running,
            status="completed",
            result_summary="계획 단계와 실제 위임은 별도 객체입니다.",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
            evidence_refs=["src/maestro/observations.py::_plan_summary"],
        )
        self.assertTrue(validate_work_spans([completed]))
        self.assertEqual("host_request", completed["model_evidence"])
        self.assertIsNone(completed["applied_model"])

    def test_work_span_cannot_self_attest_an_applied_model(self) -> None:
        with self.assertRaises(MaestroError) as raised:
            complete_work_span(
                _span("untrusted-model"),
                status="completed",
                result_summary="실제 모델이라고 자체 주장합니다.",
                ended_at="2026-07-28T01:00:03Z",
                duration_ms=3000,
                evidence_refs=["untrusted:host-event"],
                applied_model="gpt-5.6-terra",
                model_evidence="complete",
            )
        self.assertEqual("WORK_SPAN_INVALID", raised.exception.code)

    def test_applied_expertise_requires_binding_and_result_evidence(self) -> None:
        with self.assertRaises(MaestroError) as missing_binding:
            finish_work_span(
                [_span("unbound-expertise")],
                work_id="unbound-expertise",
                status="completed",
                result_summary="전문 기준을 반영했습니다.",
                ended_at="2026-07-28T01:00:03Z",
                duration_ms=3000,
                evidence_refs=["tests/test_work_graph.py"],
                expertise_evidence="application_observed",
            )
        self.assertEqual(
            "WORK_EXPERTISE_EVIDENCE_INVALID",
            missing_binding.exception.code,
        )

        running = _span(
            "applied-expertise",
            expertise_pack_ids=["product-design"],
        )
        with self.assertRaises(MaestroError) as missing_evidence:
            finish_work_span(
                [running],
                work_id="applied-expertise",
                status="completed",
                result_summary="전문 기준을 반영했습니다.",
                ended_at="2026-07-28T01:00:03Z",
                duration_ms=3000,
                evidence_refs=[],
                expertise_evidence="application_observed",
            )
        self.assertEqual(
            "WORK_EXPERTISE_EVIDENCE_INVALID",
            missing_evidence.exception.code,
        )

        completed, changed = finish_work_span(
            [running],
            work_id="applied-expertise",
            status="completed",
            result_summary="전문 기준을 반영했습니다.",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
            evidence_refs=["tests/test_work_graph.py"],
            expertise_evidence="application_observed",
        )
        self.assertTrue(changed)
        self.assertEqual(
            "application_observed",
            completed[0]["expertise_evidence"],
        )

    def test_terminal_span_requires_a_result_and_duration(self) -> None:
        with self.assertRaises(MaestroError):
            complete_work_span(
                _span("invalid-result"),
                status="completed",
                result_summary="",
                ended_at="2026-07-28T01:00:03Z",
                duration_ms=3000,
                evidence_refs=[],
            )

    def test_relations_must_reference_known_work(self) -> None:
        self.assertFalse(validate_work_spans([_span("child", parent_work_id="missing")]))

    def test_legacy_v1_remains_readable_but_cannot_carry_v2_fields(self) -> None:
        legacy = _span("legacy")
        legacy["schema_version"] = "maestro_work_span_v1"
        for field in (
            "source_binding",
            "model_observation",
            "usage",
            "outcome",
            "diagnostics",
        ):
            legacy.pop(field)
        self.assertTrue(validate_work_spans([legacy]))
        legacy["usage"] = {}
        self.assertFalse(validate_work_spans([legacy]))

    def test_ordering_relations_must_form_a_dag(self) -> None:
        left = _span("left")
        right = _span("right")
        left["depends_on_work_ids"] = ["right"]
        right["depends_on_work_ids"] = ["left"]
        self.assertFalse(validate_work_spans([left, right]))

    def test_complete_model_stream_preserves_reroute_and_token_scopes(self) -> None:
        direct = _terminal_complete_stream(
            "direct",
            started_at="2026-07-28T01:00:00Z",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
        )
        rerouted = _terminal_complete_stream(
            "rerouted",
            started_at="2026-07-28T01:00:04Z",
            ended_at="2026-07-28T01:00:08Z",
            duration_ms=4000,
            reroutes=[
                {
                    "from_model": "gpt-5.6-terra",
                    "to_model": "gpt-5.6-sol",
                    "reason": "capacity",
                }
            ],
        )
        self.assertTrue(validate_work_spans([direct, rerouted]))
        self.assertEqual(
            "gpt-5.6-sol",
            rerouted["applied_model"],
        )
        self.assertEqual(20, rerouted["usage"]["last"]["total"])
        self.assertEqual(200, rerouted["usage"]["total"]["total"])

    def test_complete_claims_require_one_full_stream_source_binding(self) -> None:
        complete = _terminal_complete_stream(
            "complete",
            started_at="2026-07-28T01:00:00Z",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
        )
        unavailable = {
            **complete,
            "source_binding": {
                **complete["source_binding"],
                "version": None,
                "schema_digest": None,
                "capability": "unavailable",
                "correlation_id": None,
                "event_coverage": "unavailable",
            },
        }
        self.assertFalse(validate_work_span(unavailable))

        partial_direct_usage = {
            **complete,
            "model_evidence": "host_request",
            "applied_model": None,
            "model_observation": {
                "observed_model": None,
                "coverage": "request_only",
                "reroutes": [],
            },
            "source_binding": {
                **complete["source_binding"],
                "event_coverage": "partial_stream",
            },
            "usage": {
                **complete["usage"],
                "timing_coverage": "partial",
            },
        }
        self.assertFalse(validate_work_span(partial_direct_usage))

        unavailable_host_clock = {
            **complete,
            "model_evidence": "host_request",
            "applied_model": None,
            "model_observation": {
                "observed_model": None,
                "coverage": "request_only",
                "reroutes": [],
            },
            "usage": {
                **complete["usage"],
                "last": None,
                "total": None,
                "scope": "unavailable",
                "attribution": "unavailable",
                "timing_coverage": "unavailable",
            },
            "source_binding": {
                **complete["source_binding"],
                "version": None,
                "schema_digest": None,
                "capability": "unavailable",
                "correlation_id": None,
                "event_coverage": "unavailable",
            },
        }
        self.assertFalse(validate_work_span(unavailable_host_clock))

    def test_hook_point_is_not_promoted_to_an_applied_model(self) -> None:
        running = new_work_span(
            work_id="hook",
            kind="delegation",
            role="Hook 관찰",
            executor_id="hook",
            task_summary="Hook 시점 값을 관찰합니다.",
            read_only=True,
            source="host_adapter",
            started_at="2026-07-28T01:00:00Z",
            timing_evidence="host_event",
            model_evidence="hook_point",
            source_binding={
                "interface": "host_adapter",
                "version": "1.0",
                "schema_digest": None,
                "capability": "lifecycle_only",
                "correlation_id": "hook-1",
                "event_coverage": "hook_lifecycle",
            },
            model_observation={
                "observed_model": "gpt-5.6-terra",
                "coverage": "hook_point",
                "reroutes": [],
            },
        )
        self.assertIsNone(running["applied_model"])
        self.assertEqual(
            "hook_point",
            running["model_observation"]["coverage"],
        )

    def test_interrupt_request_and_error_diagnostics_are_not_terminal_statuses(
        self,
    ) -> None:
        running = new_work_span(
            work_id="diagnostic",
            kind="delegation",
            role="진단 대상",
            executor_id="codex",
            task_summary="중단 요청과 오류를 분리합니다.",
            read_only=True,
            source="current_host",
            started_at="2026-07-28T01:00:00Z",
            timing_evidence="current_host_clock",
            diagnostics={
                "interrupt_requested": True,
                "error_count": 1,
                "last_error": "일시적인 stream 오류",
                "followup_reason": None,
            },
        )
        self.assertEqual("running", running["status"])
        self.assertTrue(running["diagnostics"]["interrupt_requested"])

    def test_lifecycle_is_idempotent_and_rejects_conflicts(self) -> None:
        running = _span("review")
        spans, changed = append_work_span([], running)
        self.assertTrue(changed)
        repeated, changed = append_work_span(spans, running)
        self.assertFalse(changed)
        self.assertEqual(spans, repeated)

        completed, changed = finish_work_span(
            spans,
            work_id="review",
            status="completed",
            result_summary="검토가 끝났습니다.",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
            evidence_refs=["tests/test_work_graph.py"],
        )
        self.assertTrue(changed)
        repeated, changed = finish_work_span(
            completed,
            work_id="review",
            status="completed",
            result_summary="검토가 끝났습니다.",
            ended_at="2026-07-28T01:00:04Z",
            duration_ms=4000,
            evidence_refs=["tests/test_work_graph.py"],
        )
        self.assertFalse(changed)
        self.assertEqual(completed, repeated)
        with self.assertRaises(MaestroError):
            finish_work_span(
                completed,
                work_id="review",
                status="failed",
                result_summary="다른 결과입니다.",
                ended_at="2026-07-28T01:00:04Z",
                duration_ms=4000,
                evidence_refs=["tests/test_work_graph.py"],
            )


class WorkGraphTests(unittest.TestCase):
    def test_plan_and_execution_graphs_keep_distinct_edge_semantics(self) -> None:
        root = _span(
            "orchestrator",
            assignment_id="implementation",
            kind="orchestration",
        )
        child = complete_work_span(
            _span("domain-review", parent_work_id="orchestrator"),
            status="completed",
            result_summary="도메인 경계를 검토했습니다.",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
            evidence_refs=["src/maestro/observations.py::_plan_summary"],
        )
        synthesis = _span(
            "synthesis",
            parent_work_id="orchestrator",
            kind="synthesis",
            joins_work_ids=["domain-review"],
        )
        graph = build_work_graph(
            [
                {
                    "assignment_id": "implementation",
                    "depends_on": [],
                },
                {
                    "assignment_id": "verification",
                    "depends_on": ["implementation"],
                },
            ],
            [root, child, synthesis],
        )

        self.assertEqual(
            [
                {
                    "from": "implementation",
                    "to": "verification",
                    "type": "depends_on",
                    "provenance": "plan",
                    "source": "route_plan",
                    "coverage": "declared",
                }
            ],
            graph["plan"]["edges"],
        )
        actual_types = {
            edge["type"]
            for edge in graph["execution"]["edges"]
        }
        self.assertEqual(
            {"delegates_to", "reports_to", "joins_into"},
            actual_types,
        )
        self.assertEqual(
            "partial",
            graph["execution"]["completeness"],
        )
        self.assertEqual(
            "unavailable",
            graph["execution"]["actual_concurrency"],
        )

    def test_followup_attempt_is_a_separate_node(self) -> None:
        original = complete_work_span(
            _span("review-1"),
            status="failed",
            result_summary="계약 충돌을 발견했습니다.",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
            evidence_refs=["tests/test_work_graph.py"],
        )
        followup = _span(
            "review-2",
            followup_of_work_id="review-1",
        )
        followup["attempt"] = 2
        graph = build_work_graph([], [original, followup])
        self.assertIn(
            {
                "from": "review-1",
                "to": "review-2",
                "type": "followup_of",
                "provenance": "observed_work",
                "source": "current_host",
                "coverage": "unavailable",
            },
            graph["execution"]["edges"],
        )

    def test_projection_exposes_responsibility_and_expertise_without_claiming_use(
        self,
    ) -> None:
        child = complete_work_span(
            _span("domain-review"),
            status="completed",
            result_summary="데이터 경계를 확인했습니다.",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
            evidence_refs=["src/maestro/observations.py"],
        )
        projection = project_observed_work(
            [child],
            [{"assignment_id": "implementation", "kind": "implementation"}],
        )
        card = projection["cards"][0]
        self.assertEqual("검토 담당", card["role"])
        self.assertEqual(["data-integrity"], card["expertise"]["lens_ids"])
        self.assertEqual(
            "selection_only",
            card["expertise"]["evidence"],
        )
        self.assertIsNone(card["models"]["applied"])
        self.assertEqual("host_request", card["models"]["evidence"])

    def test_actual_concurrency_requires_same_complete_clock_domain(self) -> None:
        first = _terminal_complete_stream(
            "first",
            started_at="2026-07-28T01:00:00Z",
            ended_at="2026-07-28T01:00:05Z",
            duration_ms=5000,
        )
        second = _terminal_complete_stream(
            "second",
            started_at="2026-07-28T01:00:02Z",
            ended_at="2026-07-28T01:00:06Z",
            duration_ms=4000,
        )
        observed = build_work_graph([], [first, second])["execution"]
        self.assertEqual("observed", observed["actual_concurrency"])
        self.assertEqual(
            [["first", "second"]],
            observed["concurrent_work_pairs"],
        )

        incompatible = _terminal_complete_stream(
            "incompatible",
            started_at="2026-07-28T01:00:02Z",
            ended_at="2026-07-28T01:00:06Z",
            duration_ms=4000,
            schema_digest="b" * 64,
        )
        unavailable = build_work_graph(
            [],
            [first, incompatible],
        )["execution"]
        self.assertEqual(
            "unavailable",
            unavailable["actual_concurrency"],
        )

    def test_projection_keeps_structured_decision_separate_from_summary(
        self,
    ) -> None:
        worker = _terminal_complete_stream(
            "worker",
            started_at="2026-07-28T01:00:00Z",
            ended_at="2026-07-28T01:00:03Z",
            duration_ms=3000,
        )
        decision = _terminal_complete_stream(
            "decision",
            started_at="2026-07-28T01:00:04Z",
            ended_at="2026-07-28T01:00:05Z",
            duration_ms=1000,
            joins_work_ids=["worker"],
            outcome={
                "finding_summary": "계약 공백을 확인했습니다.",
                "conclusion": "v2 계약이 필요합니다.",
                "decision": "검증 단계로 진행합니다.",
                "next_action": "verify",
                "consumed_work_ids": ["worker"],
                "handoff": {
                    "purpose": "계약과 UI를 함께 검증합니다.",
                    "completion_criteria": "fixture와 접근성 검증이 통과합니다.",
                },
                "artifacts": [],
                "verification": None,
            },
        )
        projection = project_observed_work([worker, decision], [])
        card = next(
            item
            for item in projection["cards"]
            if item["work_id"] == "decision"
        )
        self.assertEqual(
            "검증 단계로 진행합니다.",
            card["summary"]["decision"],
        )
        self.assertEqual("verify", card["detail"]["next_action"])
        self.assertEqual(
            ["worker"],
            card["outcome"]["consumed_work_ids"],
        )


if __name__ == "__main__":
    unittest.main()
