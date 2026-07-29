from __future__ import annotations

import copy
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
from maestro.governance import finalize_run
from maestro.observations import (
    inflight_observations,
    observation_receipt_fields,
    record_host_observation,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.util import read_json
from maestro.work import (
    commit_execution_transition,
    ensure_execution_ledger,
    producer_binding,
    validate_execution_ledger,
    validate_execution_measurements,
)


class ExecutionLedgerTests(unittest.TestCase):
    def _repo_and_plan(
        self,
        root: Path,
    ) -> tuple[Path, dict[str, object], Path]:
        repo = root / "repo"
        repo.mkdir()
        apply_fresh_init(repo)
        plan = route_goal_v2(
            "실행 원장을 구조적으로 검증한다",
            "medium",
            intent="implementation",
            repo_path=repo,
        )
        plan_path = root / "plan.json"
        write_json(plan_path, plan)
        return repo, plan, plan_path

    def _observation_path(
        self,
        repo: Path,
        observation_id: str,
    ) -> Path:
        return (
            repo
            / ".maestro"
            / "state"
            / "inflight"
            / f"{observation_id}.json"
        )

    def test_desktop_request_preserves_requested_values_and_typed_gaps(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="desktop-measurement-gap",
                task_label="Desktop 요청 계측",
                plan_path=plan_path,
            )
            record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="desktop-measurement-gap",
                source="codex-desktop-request-meta",
                quality="host_reported",
                correlation_id="thread-1:turn-1",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="xhigh",
            )

            observed = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="desktop-measurement-gap",
            )
            measurements = observed["execution_measurements"]
            self.assertTrue(validate_execution_measurements(measurements))
            self.assertEqual(
                ["gpt-5.6-sol"],
                measurements["model"]["requested"],
            )
            self.assertEqual("request_only", measurements["model"]["coverage"])
            self.assertEqual(
                ["xhigh"],
                measurements["reasoning_effort"]["requested"],
            )
            self.assertIsNone(measurements["tokens"]["value"])
            self.assertEqual(
                "request_metadata_only",
                measurements["tokens"]["missing_reason"],
            )
            self.assertEqual(
                "collector_clock",
                measurements["duration"]["coverage"],
            )

    def test_assignment_terminals_do_not_seal_before_late_work(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="late-work-after-stages",
                task_label="단계 뒤 작업 기록",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "Fixture exercises a current-Host late work event.",
                },
            )
            observation_id = started["observation_id"]
            for assignment in plan["assignments"]:
                recorded = record_stage_observation(
                    repo,
                    observation_id=observation_id,
                    run_id="late-work-after-stages",
                    assignment_id=assignment["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=[
                        f"tests:stage:{assignment['assignment_id']}"
                    ],
                )
            self.assertTrue(recorded["assignments_terminal"])
            self.assertFalse(recorded["run_terminal"])
            raw = read_json(self._observation_path(repo, observation_id))
            self.assertNotIn("completed_at", raw)
            self.assertNotEqual(
                "execution_sealed",
                raw["execution_ledger"]["events"][-1]["event_type"],
            )

            implementation = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["kind"] == "implementation"
            )
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="late-work-after-stages",
                work_id="late-synthesis",
                assignment_id=implementation["assignment_id"],
                kind="synthesis",
                role="결과 합성 담당",
                executor_id=implementation["executor_id"],
                task_summary="단계 결과 뒤에 도착한 종합 판단을 기록합니다.",
                read_only=False,
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="high",
                model_evidence="host_request",
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="late-work-after-stages",
                work_id="late-synthesis",
                status="completed",
                result_summary="종합 판단이 실행 원장에 남았습니다.",
                evidence_refs=["tests:test_execution_ledger"],
            )
            verification = next(
                assignment
                for assignment in plan["assignments"]
                if assignment["kind"] == "verification"
            )
            record_work_start(
                repo,
                observation_id=observation_id,
                run_id="late-work-after-stages",
                work_id="late-verification-followup",
                assignment_id=verification["assignment_id"],
                kind="verification",
                role="늦은 구현 결과 검증 담당",
                executor_id=verification["executor_id"],
                task_summary="늦게 도착한 구현 결과를 검증합니다.",
                read_only=verification["read_only"],
                source="host_adapter",
                depends_on_work_ids=["late-synthesis"],
            )
            record_work_finish(
                repo,
                observation_id=observation_id,
                run_id="late-work-after-stages",
                work_id="late-verification-followup",
                status="completed",
                result_summary="늦은 구현 결과 검증이 완료되었습니다.",
                evidence_refs=["tests:test_execution_ledger:late-verification"],
            )
            record_managed_completion_graph(
                repo,
                observation_id=observation_id,
                run_id="late-work-after-stages",
                plan=plan,
            )
            finalized = finalize_run(
                repo,
                run_id="late-work-after-stages",
                observation_id=observation_id,
                outcome="completed",
                evidence_refs=["tests:test_execution_ledger"],
                verifier_result="passed",
                command_artifact_ref="tests:test_execution_ledger",
            )
            self.assertEqual("recorded", finalized["status"])
            sealed = read_json(self._observation_path(repo, observation_id))
            self.assertEqual(
                "execution_sealed",
                sealed["execution_ledger"]["events"][-1]["event_type"],
            )

    def test_stale_observation_writer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="stale-writer",
                task_label="동시 기록 충돌",
                plan_path=plan_path,
            )
            target = self._observation_path(repo, started["observation_id"])
            stale = read_json(target)
            first_after = copy.deepcopy(stale)
            first_after["fallback_recorded_at"] = stale["started_at"]
            producer = producer_binding(
                "maestro_core",
                capability="lifecycle_only",
                event_coverage="partial_stream",
            )
            commit_execution_transition(
                target,
                before=stale,
                after=first_after,
                event_type="execution_binding_changed",
                idempotency_key="test:first-writer",
                producer=producer,
                payload={"writer": "first"},
                measurement=None,
                recorded_at=stale["started_at"],
            )
            with self.assertRaises(MaestroError) as raised:
                commit_execution_transition(
                    target,
                    before=stale,
                    after=stale,
                    event_type="execution_binding_changed",
                    idempotency_key="test:stale-writer",
                    producer=producer,
                    payload={"writer": "stale"},
                    measurement=None,
                    recorded_at=stale["started_at"],
                )
            self.assertEqual(
                "RUN_OBSERVATION_STALE_REVISION",
                raised.exception.code,
            )

    def test_legacy_observation_is_projected_without_rewriting_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="legacy-projection",
                task_label="기존 관측 호환",
                plan_path=plan_path,
            )
            target = self._observation_path(repo, started["observation_id"])
            legacy = read_json(target)
            legacy.pop("execution_ledger")
            write_json(target, legacy)

            projected = ensure_execution_ledger(read_json(target))
            self.assertEqual("legacy_import", projected["origin"])
            self.assertTrue(validate_execution_ledger(projected))
            self.assertNotIn("execution_ledger", read_json(target))
            measured = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="legacy-projection",
            )["execution_measurements"]
            self.assertTrue(validate_execution_measurements(measured))
            self.assertEqual("unavailable", measured["model"]["coverage"])

    def test_public_receipt_schemas_publish_the_same_measurement_contract(
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
            schemas[0]["$defs"]["executionMeasurements"],
            schemas[1]["$defs"]["executionMeasurements"],
        )
        measurements = schemas[0]["$defs"]["executionMeasurements"]
        for field in ("ledger_revision", "ledger_event_count"):
            self.assertEqual(
                {"type": "integer", "minimum": 1, "maximum": 256},
                measurements["properties"][field],
            )
        self.assertEqual(
            "^[a-f0-9]{64}$",
            measurements["properties"]["ledger_digest"]["pattern"],
        )
        self.assertEqual(
            "^[a-f0-9]{64}$",
            schemas[0]["$defs"]["producerMeasurementCoverage"][
                "properties"
            ]["event_id"]["pattern"],
        )
        self.assertEqual(
            {"$ref": "#/$defs/executionMeasurements"},
            schemas[0]["properties"]["execution_measurements"],
        )
        for definition in (
            "modelMeasurementSummary",
            "reasoningMeasurementSummary",
            "tokenMeasurementSummary",
            "durationMeasurementSummary",
        ):
            self.assertEqual(
                schemas[0]["$defs"][definition],
                schemas[1]["$defs"][definition],
            )
            self.assertTrue(
                schemas[0]["$defs"][definition]["allOf"],
                definition,
            )

    def test_measurement_value_or_typed_missing_cross_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _plan, plan_path = self._repo_and_plan(root)
            started = start_run_observation(
                repo,
                run_id="measurement-cross-fields",
                task_label="측정 교차 필드",
                plan_path=plan_path,
            )
            record_host_observation(
                repo,
                observation_id=started["observation_id"],
                run_id="measurement-cross-fields",
                source="codex-desktop-request-meta",
                quality="host_reported",
                correlation_id="thread-2:turn-2",
                requested_model="gpt-5.6-sol",
                requested_reasoning_effort="high",
            )
            valid = observation_receipt_fields(
                repo,
                observation_id=started["observation_id"],
                run_id="measurement-cross-fields",
            )["execution_measurements"]
            self.assertTrue(validate_execution_measurements(valid))

            mutations = []
            missing_token_reason = copy.deepcopy(valid)
            missing_token_reason["tokens"]["missing_reason"] = None
            mutations.append(missing_token_reason)
            false_token_value = copy.deepcopy(valid)
            false_token_value["tokens"].update(
                {
                    "value": {"total": 1},
                    "coverage": "unavailable",
                    "scope": "unavailable",
                    "attribution": "unavailable",
                    "source": "unavailable",
                    "missing_reason": "request_metadata_only",
                }
            )
            mutations.append(false_token_value)
            request_without_model = copy.deepcopy(valid)
            request_without_model["model"]["requested"] = []
            mutations.append(request_without_model)
            requested_reason_without_gap = copy.deepcopy(valid)
            requested_reason_without_gap["reasoning_effort"][
                "missing_reason"
            ] = None
            mutations.append(requested_reason_without_gap)
            unavailable_duration_with_value = copy.deepcopy(valid)
            unavailable_duration_with_value["duration"].update(
                {
                    "value_ms": 1.0,
                    "coverage": "unavailable",
                    "attribution": "unavailable",
                    "missing_reason": "producer_did_not_expose",
                }
            )
            mutations.append(unavailable_duration_with_value)
            zero_revision = copy.deepcopy(valid)
            zero_revision["ledger_revision"] = 0
            zero_revision["ledger_event_count"] = 0
            mutations.append(zero_revision)
            excessive_revision = copy.deepcopy(valid)
            excessive_revision["ledger_revision"] = 257
            excessive_revision["ledger_event_count"] = 257
            mutations.append(excessive_revision)
            mismatched_event_count = copy.deepcopy(valid)
            mismatched_event_count["ledger_event_count"] -= 1
            mutations.append(mismatched_event_count)
            non_hex_ledger_digest = copy.deepcopy(valid)
            non_hex_ledger_digest["ledger_digest"] = "z" * 64
            mutations.append(non_hex_ledger_digest)
            short_producer_event_id = copy.deepcopy(valid)
            short_producer_event_id["producer_coverage"][0][
                "event_id"
            ] = "abcd"
            mutations.append(short_producer_event_id)
            non_hex_producer_event_id = copy.deepcopy(valid)
            non_hex_producer_event_id["producer_coverage"][0][
                "event_id"
            ] = "z" * 64
            mutations.append(non_hex_producer_event_id)
            excessive_producer_coverage = copy.deepcopy(valid)
            producer = excessive_producer_coverage[
                "producer_coverage"
            ][0]
            excessive_producer_coverage["producer_coverage"] = [
                {
                    **copy.deepcopy(producer),
                    "event_id": f"{index:064x}",
                }
                for index in range(valid["ledger_event_count"] + 1)
            ]
            mutations.append(excessive_producer_coverage)
            for non_finite in (float("inf"), float("nan")):
                non_finite_duration = copy.deepcopy(valid)
                non_finite_duration["duration"]["value_ms"] = non_finite
                mutations.append(non_finite_duration)

            for index, invalid in enumerate(mutations):
                with self.subTest(index=index):
                    self.assertFalse(
                        validate_execution_measurements(invalid)
                    )

    def test_non_observation_json_in_inflight_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _plan, _plan_path = self._repo_and_plan(root)
            write_json(
                repo / ".maestro/state/inflight/unrelated.json",
                {"schema_version": "unrelated_state_v1"},
            )

            self.assertEqual([], inflight_observations(repo))


if __name__ == "__main__":
    unittest.main()
