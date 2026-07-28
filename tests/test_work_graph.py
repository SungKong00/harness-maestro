from __future__ import annotations

import unittest

from maestro.errors import MaestroError
from maestro.work import (
    build_work_graph,
    complete_work_span,
    new_work_span,
    validate_work_spans,
)


def _span(
    work_id: str,
    *,
    parent_work_id: str | None = None,
    assignment_id: str | None = None,
    kind: str = "delegation",
    followup_of_work_id: str | None = None,
    joins_work_ids: list[str] | None = None,
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
        expertise_evidence="selection_only",
    )


class WorkContractTests(unittest.TestCase):
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
            },
            graph["execution"]["edges"],
        )


if __name__ == "__main__":
    unittest.main()
