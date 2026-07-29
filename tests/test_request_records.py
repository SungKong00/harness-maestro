from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from tests.support import (
    apply_fresh_init,
    record_managed_completion_graph,
    write_json,
)

from maestro.governance import finalize_run
from maestro.observations import (
    record_execution_fallback,
    record_stage_observation,
    start_desktop_request_observation,
)
from maestro.planning import route_goal_v2
from maestro.request_records import project_request_records
from maestro.snapshot import snapshot_report
from maestro.snapshot_runs import _measurement_coverage


def _run(
    *,
    event_id: str,
    run_id: str,
    timestamp: str,
    outcome: str,
    work_id: str,
    correlation_id: str | None,
    model: str | None,
    tokens: dict[str, int] | None,
) -> dict[str, object]:
    host = (
        {
            "schema_version": "maestro_host_observation_v2",
            "source": "codex-desktop-request-meta",
            "quality": "host_reported",
            "correlation_id": correlation_id,
            "observed_at": timestamp,
        }
        if correlation_id is not None
        else None
    )
    model_values = [model] if model else []
    card = {
        "work_id": work_id,
        "rank": 0,
        "position": 0,
        "relationships": {
            "parent_work_id": None,
            "followup_of_work_id": None,
            "depends_on_work_ids": [],
            "joins_work_ids": [],
        },
        "execution_facts": {
            "model": {
                "kind": "actual" if model else "unavailable",
                "value": model,
                "coverage": "complete_stream" if model else "unavailable",
            },
            "tokens": {
                "value": tokens,
                "scope": "work_turn" if tokens else "unavailable",
                "attribution": "direct" if tokens else "unavailable",
            },
        },
    }
    return {
        "event_id": event_id,
        "run_id": run_id,
        "task_label": "요청 기록 개선",
        "timestamp": timestamp,
        "outcome": outcome,
        "verifier_result": "passed" if outcome == "completed" else "failed",
        "duration_ms": 100,
        "planning_duration_ms": 10,
        "tokens": tokens,
        "token_scope": "observed_stages" if tokens else "unavailable",
        "models": {
            "requested": ["gpt-requested"],
            "requested_reasoning_effort": ["high"],
            "applied": model_values,
            "route_recommended": ["gpt-recommended"],
            "route_recommended_reasoning_effort": ["medium"],
            "measurement_state": (
                "host_event_stream_complete"
                if model
                else "host_request_observed"
            ),
        },
        "measurement_provenance": {},
        "stage_coverage": {
            "available": True,
            "recorded": 1,
            "planned": 1,
            "complete": True,
        },
        "stage_telemetry": {
            "model_expected": 1,
            "model_measured": 1 if model else 0,
            "duration_measured": 1,
            "tokens_measured": 1 if tokens else 0,
            "complete": bool(model),
        },
        "host_observation": host,
        "correction_count": 0,
        "correction_summary": [],
        "expertise": {
            "packs": [],
            "guides": [],
        },
        "flow": [],
        "flow_graph": {"edges": []},
        "work_detail": {
            "header": {},
            "limitations": {},
            "execution": {
                "schema_version": "maestro_observed_work_projection_v2",
                "mode": "observed",
                "completeness": "complete",
                "cards": [card],
                "lanes": [
                    {
                        "lane_id": "orchestration",
                        "label": "오케스트레이션",
                        "work_ids": [work_id],
                    }
                ],
                "graph": {
                    "edges": [],
                    "entry_work_ids": [work_id],
                    "terminal_work_ids": [work_id],
                    "concurrent_work_pairs": [],
                },
                "bindings": [],
                "summary": {
                    "work_count": 1,
                    "delegation_count": 0,
                    "report_count": 0,
                    "join_count": 0,
                    "followup_count": 0,
                },
            },
        },
    }


class RequestRecordProjectionTests(unittest.TestCase):
    def test_same_desktop_request_becomes_one_record_with_ordered_attempts(
        self,
    ) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-1",
            model="gpt-5.6-terra",
            tokens={"input": 7, "total": 10},
        )
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-1",
            model="gpt-5.6-sol",
            tokens={"input": 13, "total": 20},
        )
        first["work_detail"]["execution"]["cards"][0]["assignment"] = {
            "assignment_id": "implementation",
            "model_route": {
                "route_recommended": "gpt-5.6-terra",
            },
        }
        second["work_detail"]["execution"]["cards"][0]["assignment"] = {
            "assignment_id": "implementation",
            "model_route": {
                "route_recommended": "gpt-5.6-sol",
            },
        }

        records = project_request_records([second, first])

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("trusted_desktop_thread_turn", record[
            "request_identity_evidence"
        ])
        self.assertEqual(["event-a", "event-b"], record["source_event_ids"])
        self.assertEqual(["run-a", "run-b"], record["source_run_ids"])
        self.assertEqual(2, record["attempt_count"])
        self.assertEqual(1, record["rework_count"])
        self.assertEqual("completed", record["outcome"])
        self.assertEqual({"input": 20, "total": 30}, record["tokens"])
        self.assertEqual(
            ["gpt-5.6-terra", "gpt-5.6-sol"],
            record["models"]["applied"],
        )
        self.assertEqual(
            "request_attempts_measured",
            record["models"]["measurement_state"],
        )
        execution = record["work_detail"]["execution"]
        self.assertEqual(
            ["attempt-1:work-a", "attempt-2:work-b"],
            [card["work_id"] for card in execution["cards"]],
        )
        self.assertEqual([0, 1], [
            card["rank"] for card in execution["cards"]
        ])
        self.assertEqual(
            {
                "from": "attempt-1:work-a",
                "to": "attempt-2:work-b",
                "type": "followup_of",
                "provenance": "request_record_projection",
                "source": "trusted_desktop_request_correlation",
                "coverage": "derived_attempt_order",
            },
            execution["graph"]["edges"][0],
        )
        self.assertEqual(
            "shared_trunk",
            execution["graph"]["display_edge_groups"][0]["routing"],
        )
        self.assertEqual(
            "unavailable",
            execution["graph"]["actual_concurrency"],
        )
        self.assertEqual(
            ["gpt-5.6-terra", "gpt-5.6-sol"],
            [
                card["assignment"]["model_route"]["route_recommended"]
                for card in execution["cards"]
            ],
        )

    def test_request_concurrency_preserves_source_measurement_coverage(
        self,
    ) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-concurrency",
            model="gpt-5.6-terra",
            tokens=None,
        )
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-concurrency",
            model="gpt-5.6-sol",
            tokens=None,
        )

        unavailable = project_request_records([first, second])[0]
        self.assertEqual(
            "unavailable",
            unavailable["work_detail"]["execution"]["graph"][
                "actual_concurrency"
            ],
        )

        for run in (first, second):
            run["work_detail"]["execution"]["graph"][
                "actual_concurrency"
            ] = "none_observed"
        measured = project_request_records([first, second])[0]
        self.assertEqual(
            "none_observed",
            measured["work_detail"]["execution"]["graph"][
                "actual_concurrency"
            ],
        )

    def test_request_preserves_mixed_definition_evidence_per_attempt(
        self,
    ) -> None:
        historical = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-definition-mixed",
            model=None,
            tokens=None,
        )
        historical["history_evidence"] = {
            "classification": "definition",
            "history_visibility": "visible",
            "governance_eligible": False,
            "definition_status": "historical",
            "reason": "definition_digest_mismatch",
        }
        current = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-definition-mixed",
            model=None,
            tokens=None,
        )
        current["history_evidence"] = {
            "classification": "eligible",
            "history_visibility": "visible",
            "governance_eligible": True,
            "definition_status": "current",
            "reason": None,
        }

        record = project_request_records([current, historical])[0]

        self.assertEqual(
            {
                "definition_status": "mixed",
                "governance_eligible": False,
                "governance_eligible_attempts": 1,
                "attempts_total": 2,
                "latest_attempt": current["history_evidence"],
            },
            record["history_evidence"],
        )
        self.assertEqual(
            [
                historical["history_evidence"],
                current["history_evidence"],
            ],
            [
                attempt["history_evidence"]
                for attempt in record["attempts"]
            ],
        )

    def test_merged_retry_cards_recover_only_their_source_stage_route(
        self,
    ) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-stage-route",
            model=None,
            tokens=None,
        )
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-stage-route",
            model=None,
            tokens=None,
        )
        for run, model in (
            (first, "gpt-5.6-terra"),
            (second, "gpt-5.6-sol"),
        ):
            run["work_detail"]["execution"]["cards"][0]["assignment"] = {
                "assignment_id": "implementation",
            }
            run["work_detail"]["stages"] = [
                {
                    "stage_id": "implementation",
                    "models": {
                        "route_recommended": model,
                        "route_recommended_reasoning_effort": "high",
                    },
                }
            ]

        record = project_request_records([second, first])[0]

        self.assertEqual(
            ["gpt-5.6-terra", "gpt-5.6-sol"],
            [
                card["assignment"]["model_route"]["route_recommended"]
                for card in record["work_detail"]["execution"]["cards"]
            ],
        )

    def test_untrusted_runs_are_never_grouped_by_label(self) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="completed",
            work_id="work-a",
            correlation_id=None,
            model=None,
            tokens=None,
        )
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id=None,
            model=None,
            tokens=None,
        )

        records = project_request_records([second, first])

        self.assertEqual(2, len(records))
        self.assertTrue(all(
            record["request_identity_evidence"] == "single_run_fallback"
            for record in records
        ))
        self.assertTrue(all(record["attempt_count"] == 1 for record in records))

    def test_one_request_preserves_all_internal_work_cards(self) -> None:
        attempts = []
        for attempt in range(3):
            run = _run(
                event_id=f"event-{attempt}",
                run_id=f"run-{attempt}",
                timestamp=f"2026-07-29T00:0{attempt}:00Z",
                outcome="completed",
                work_id=f"work-{attempt}-0",
                correlation_id="thread-1:turn-many-cards",
                model="gpt-5.6-sol",
                tokens={"total": 10},
            )
            execution = run["work_detail"]["execution"]
            template = execution["cards"][0]
            for card_index in range(1, 4):
                card = deepcopy(template)
                card["work_id"] = f"work-{attempt}-{card_index}"
                card["position"] = card_index
                execution["cards"].append(card)
                execution["lanes"][0]["work_ids"].append(card["work_id"])
            attempts.append(run)

        records = project_request_records(attempts)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(3, record["attempt_count"])
        self.assertEqual(12, len(record["work_detail"]["execution"]["cards"]))
        self.assertEqual(
            12,
            len({
                card["work_id"]
                for card in record["work_detail"]["execution"]["cards"]
            }),
        )

    def test_request_uses_direct_work_measurements_from_a_partial_run(
        self,
    ) -> None:
        run = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="completed",
            work_id="work-a",
            correlation_id="thread-1:turn-1",
            model="gpt-5.6-terra",
            tokens={"total": 42},
        )
        run["models"]["applied"] = []
        run["models"]["measurement_state"] = "host_request_observed"
        run["tokens"] = None

        record = project_request_records([run])[0]

        self.assertEqual(["gpt-5.6-terra"], record["models"]["applied"])
        self.assertEqual({"total": 42}, record["tokens"])
        self.assertEqual(1, record["request_measurement"][
            "model_measured_attempts"
        ])
        self.assertEqual(1, record["request_measurement"][
            "token_measured_attempts"
        ])

    def test_attempt_coverage_preserves_reasoning_duration_and_provenance(
        self,
    ) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-coverage",
            model="gpt-5.6-terra",
            tokens={"total": 21},
        )
        first["measurement_provenance"] = {
            "duration": "execution_ledger",
            "tokens": "execution_ledger",
        }
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-coverage",
            model=None,
            tokens=None,
        )
        second["duration_ms"] = None
        second["measurement_provenance"] = {}
        second["models"]["requested_reasoning_effort"] = []

        record = project_request_records([second, first])[0]

        measurement = record["request_measurement"]
        self.assertEqual(1, measurement["duration_measured_attempts"])
        self.assertEqual("partial", measurement["duration_coverage"])
        self.assertEqual(
            1,
            measurement["reasoning_request_observed_attempts"],
        )
        self.assertEqual(
            "partial",
            measurement["reasoning_request_coverage"],
        )
        self.assertEqual(
            ["medium"],
            record["models"]["route_recommended_reasoning_effort"],
        )
        self.assertEqual(
            {
                "duration_ms": 100,
                "duration_source": "execution_ledger",
                "tokens": {"total": 21},
                "token_scope": "observed_stages",
                "requested_models": ["gpt-requested"],
                "requested_reasoning_effort": ["high"],
                "route_recommended_models": ["gpt-recommended"],
                "route_recommended_reasoning_effort": ["medium"],
                "applied_models": ["gpt-5.6-terra"],
            },
            {
                key: record["attempts"][0][key]
                for key in (
                    "duration_ms",
                    "duration_source",
                    "tokens",
                    "token_scope",
                    "requested_models",
                    "requested_reasoning_effort",
                    "route_recommended_models",
                    "route_recommended_reasoning_effort",
                    "applied_models",
                )
            },
        )
        self.assertIsNone(record["attempts"][1]["duration_ms"])
        self.assertEqual(
            "unavailable",
            record["attempts"][1]["duration_source"],
        )
        self.assertIsNone(record["attempts"][1]["tokens"])
        self.assertEqual(
            [],
            record["attempts"][1]["requested_reasoning_effort"],
        )

    def test_mixed_token_scopes_are_not_summed_as_one_request_total(
        self,
    ) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:00:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-mixed-token-scope",
            model=None,
            tokens={"total": 100},
        )
        first["token_scope"] = "run"
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:01:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-mixed-token-scope",
            model=None,
            tokens={"total": 20},
        )
        second["token_scope"] = "observed_stages"

        record = project_request_records([first, second])[0]

        self.assertIsNone(record["tokens"])
        self.assertEqual("mixed_attempt_scopes", record["token_scope"])
        self.assertEqual(
            "incompatible_scopes",
            record["request_measurement"]["token_coverage"],
        )
        self.assertEqual(
            "not_aggregated_mixed_scopes",
            record["request_measurement"]["token_aggregation"],
        )
        self.assertEqual(
            ["run", "observed_stages"],
            record["request_measurement"]["token_scopes"],
        )
        self.assertEqual(
            [{"total": 100}, {"total": 20}],
            [attempt["tokens"] for attempt in record["attempts"]],
        )
        coverage = _measurement_coverage([record])
        self.assertEqual(1, coverage["tokens"]["measured_requests"])
        self.assertEqual(0, coverage["token_aggregate"]["measured_requests"])

    def test_attempt_order_uses_request_intake_not_receipt_write_time(
        self,
    ) -> None:
        first = _run(
            event_id="event-a",
            run_id="run-a",
            timestamp="2026-07-29T00:03:00Z",
            outcome="failed",
            work_id="work-a",
            correlation_id="thread-1:turn-1",
            model=None,
            tokens=None,
        )
        first["host_observation"]["observed_at"] = (
            "2026-07-29T00:00:00Z"
        )
        second = _run(
            event_id="event-b",
            run_id="run-b",
            timestamp="2026-07-29T00:02:00Z",
            outcome="completed",
            work_id="work-b",
            correlation_id="thread-1:turn-1",
            model=None,
            tokens=None,
        )
        second["host_observation"]["observed_at"] = (
            "2026-07-29T00:01:00Z"
        )

        record = project_request_records([first, second])[0]

        self.assertEqual(["run-a", "run-b"], record["source_run_ids"])
        self.assertEqual("completed", record["outcome"])
        self.assertEqual(
            ["attempt-1:work-a", "attempt-2:work-b"],
            [
                card["work_id"]
                for card in record["work_detail"]["execution"]["cards"]
            ],
        )

    def test_snapshot_keeps_runs_but_exposes_one_request_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            plan = route_goal_v2(
                "같은 사용자 요청의 재시도를 한 기록으로 보여 준다",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)

            for attempt, outcome in ((1, "failed"), (2, "completed")):
                run_id = f"request-attempt-{attempt}"
                started = start_desktop_request_observation(
                    repo,
                    run_id=run_id,
                    task_label="요청 단위 투영",
                    thread_id="thread-1",
                    turn_id="turn-1",
                    requested_model="gpt-5.6-sol",
                    requested_reasoning_effort="high",
                    plan_path=plan_path,
                )
                record_execution_fallback(
                    repo,
                    observation_id=started["observation_id"],
                    run_id=run_id,
                    reason="capability_unavailable",
                    evidence="The fixture exercises request grouping.",
                )
                for assignment in plan["assignments"]:
                    record_stage_observation(
                        repo,
                        observation_id=started["observation_id"],
                        run_id=run_id,
                        assignment_id=assignment["assignment_id"],
                        status=(
                            "failed"
                            if outcome == "failed"
                            and assignment
                            is plan["assignments"][-1]
                            else "completed"
                        ),
                        evidence_source="current_host",
                        evidence_refs=[
                            f"tests:{run_id}:{assignment['assignment_id']}"
                        ],
                    )
                record_managed_completion_graph(
                    repo,
                    observation_id=started["observation_id"],
                    run_id=run_id,
                    plan=plan,
                    prefix=f"completion-{run_id}",
                )
                finalize_run(
                    repo,
                    run_id=run_id,
                    observation_id=started["observation_id"],
                    outcome=outcome,
                    evidence_refs=[f"tests:{run_id}"],
                    verifier_result=(
                        "failed" if outcome == "failed" else "passed"
                    ),
                    command_artifact_ref=f"tests:{run_id}",
                )

            snapshot = snapshot_report(repo)

            self.assertEqual(2, len(snapshot["runs"]))
            self.assertEqual(1, len(snapshot["request_records"]))
            record = snapshot["request_records"][0]
            self.assertEqual(2, record["attempt_count"])
            self.assertEqual(
                ["request-attempt-1", "request-attempt-2"],
                record["source_run_ids"],
            )
            self.assertEqual(1, snapshot["overview"]["requests"])
            self.assertEqual(
                1,
                snapshot["measurement_coverage"]["duration"][
                    "total_requests"
                ],
            )
            self.assertEqual(
                "request_records",
                snapshot["measurement_coverage"]["duration"]["scope"],
            )


if __name__ == "__main__":
    unittest.main()
