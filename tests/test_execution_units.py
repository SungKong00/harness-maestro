from __future__ import annotations

import copy
import json
import unittest

from tests.support import ROOT

from maestro.execution_units import (
    ATTEMPT_FIELDS,
    EXECUTION_UNIT_FIELDS,
    RECEIPT_FIELDS,
    build_execution_attempt,
    build_execution_unit_receipt,
    project_route_execution_units,
    validate_execution_receipt_bundle,
    validate_execution_unit,
    validate_execution_unit_receipt,
    validate_plan_execution_units,
    validate_stage_execution_receipts,
)
from maestro.observations import _assignment_plan_summary
from maestro.planning import route_goal_v2
from maestro.util import canonical_json, sha256_text


def _rehash(value: dict[str, object], field: str) -> None:
    payload = copy.deepcopy(value)
    payload[field] = ""
    value[field] = sha256_text(canonical_json(payload))


class ExecutionUnitContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        self.units = project_route_execution_units(self.route)
        self.by_id = {
            unit["local_unit_id"]: unit for unit in self.units
        }

    def _attempt(
        self,
        unit: dict[str, object],
        *,
        applied_model: str | None = None,
        provider_reroutes: list[dict[str, str]] | None = None,
        writes_observed: bool = False,
    ) -> dict[str, object]:
        route = unit["model_route"]
        assert isinstance(route, dict)
        return build_execution_attempt(
            attempt=1,
            followup_of_attempt=None,
            route_kind="primary",
            requested_class=route["selected_class"],
            requested_model=route["selected_model"],
            requested_reasoning_effort=route["reasoning_effort"],
            applied_model=applied_model or route["selected_model"],
            applied_reasoning_effort=None,
            reasoning_effort_evidence="requested-only",
            status="completed",
            transition_trigger=None,
            provider_reroutes=provider_reroutes or [],
            thread_id="thread-one",
            turn_id="turn-one",
            duration_ms=25,
            tokens={
                "input": 10,
                "output": 5,
                "cached": 0,
                "reasoning": 2,
                "total": 17,
            },
            writes_observed=writes_observed,
        )

    def _receipt(
        self,
        unit: dict[str, object],
        attempt: dict[str, object],
        *,
        framework_version: str = "0.2.0",
    ) -> dict[str, object]:
        return build_execution_unit_receipt(
            unit=unit,
            input_digest=sha256_text("input"),
            attempts=[attempt],
            output_packet_digest=sha256_text("output"),
            terminal_work_id="work-one",
            terminal_status="completed",
            effect_state="no-writes",
            producer={
                "interface": "codex_app_server",
                "framework_version": framework_version,
                "runtime_schema_digest": None,
                "run_id": "run-one",
                "observation_id": "observation-one",
            },
            issued_at="2026-07-30T00:00:00Z",
        )

    def _plan_summary(self) -> dict[str, object]:
        return {
            "schema_version": "maestro_plan_summary_v1",
            "plan_id": self.route["plan_id"],
            "execution_contract": {
                "kind": "direct-route",
                "execution_plan_id": None,
                "decision_plan_id": None,
                "decision_bundle_digest": None,
            },
            "risk": self.route["risk"],
            "execution_receipts_required": True,
            "assignments": [
                _assignment_plan_summary(
                    assignment,
                    execution_unit=self.by_id[
                        assignment["assignment_id"]
                    ],
                )
                for assignment in self.route["assignments"]
            ],
        }

    def _stage_fixture(
        self,
        *,
        framework_version: str = "0.2.0",
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        list[dict[str, object]],
    ]:
        plan = self._plan_summary()
        assignment = next(
            item
            for item in plan["assignments"]
            if not item["depends_on"]
        )
        unit = assignment["execution_unit"]
        attempt = self._attempt(unit)
        receipt = self._receipt(
            unit,
            attempt,
            framework_version=framework_version,
        )
        stage = {
            "assignment_id": assignment["assignment_id"],
            "status": "completed",
            "model_route_id": assignment["model_route_id"],
            "execution_unit_id": assignment["execution_unit_id"],
            "requested_model": attempt["requested_model"],
            "requested_reasoning_effort": attempt[
                "requested_reasoning_effort"
            ],
            "actual_model": attempt["applied_model"],
            "model_evidence": "complete",
            "reroutes": [],
            "duration_ms": attempt["duration_ms"],
            "tokens": attempt["tokens"],
            "evidence_refs": [
                "assignment-input:" + receipt["input_digest"],
                "codex-app-server:thread-one:turn-one",
                "assignment-packet:"
                + receipt["output_packet_digest"],
            ],
            "evidence_source": "codex_app_server",
            "execution_unit_receipt": receipt,
        }
        work_spans = [
            {
                "work_id": "work-one",
                "assignment_id": assignment["assignment_id"],
                "source": "codex_app_server",
                "status": "completed",
                "kind": "orchestration",
                "source_binding": {"schema_digest": None},
            }
        ]
        return plan, stage, work_spans

    def test_route_projection_is_stable_and_tamper_evident(self) -> None:
        repeated = project_route_execution_units(self.route)
        self.assertEqual(self.units, repeated)
        self.assertTrue(all(validate_execution_unit(unit) for unit in self.units))
        self.assertTrue(all(unit["host_executable"] for unit in self.units))

        tampered = copy.deepcopy(self.units[0])
        tampered["executor_id"] = "different-executor"
        self.assertFalse(validate_execution_unit(tampered))

    def test_plan_summary_binds_every_exact_execution_unit(self) -> None:
        plan_summary = {
            "schema_version": "maestro_plan_summary_v1",
            "plan_id": self.route["plan_id"],
            "execution_contract": {
                "kind": "direct-route",
                "execution_plan_id": None,
                "decision_plan_id": None,
                "decision_bundle_digest": None,
            },
            "risk": self.route["risk"],
            "assignments": [
                _assignment_plan_summary(
                    assignment,
                    execution_unit=self.by_id[assignment["assignment_id"]],
                )
                for assignment in self.route["assignments"]
            ],
        }
        self.assertTrue(validate_plan_execution_units(plan_summary))

        changed = copy.deepcopy(plan_summary)
        changed["assignments"][0]["task_class"] = "different-task"
        self.assertFalse(validate_plan_execution_units(changed))

        stripped = copy.deepcopy(plan_summary)
        stripped["execution_receipts_required"] = True
        for assignment in stripped["assignments"]:
            assignment.pop("execution_unit")
        self.assertFalse(validate_plan_execution_units(stripped))

        legacy = copy.deepcopy(stripped)
        legacy.pop("execution_receipts_required")
        self.assertTrue(validate_plan_execution_units(legacy))

    def test_primary_receipt_and_typed_provider_fallback_validate(self) -> None:
        review = self.by_id["review"]
        primary = self._receipt(review, self._attempt(review))
        self.assertEqual(
            "PASS",
            validate_execution_unit_receipt(primary, unit=review)["status"],
        )

        route = review["model_route"]
        fallback = route["fallback_route"]
        fallback_attempt = self._attempt(
            review,
            applied_model=fallback["selected_model"],
            provider_reroutes=[
                {
                    "from_model": route["selected_model"],
                    "to_model": fallback["selected_model"],
                    "reason": "selected model unavailable",
                }
            ],
        )
        fallback_receipt = self._receipt(review, fallback_attempt)
        self.assertEqual(
            "PASS",
            validate_execution_unit_receipt(
                fallback_receipt,
                unit=review,
            )["status"],
        )

    def test_receipt_rejects_tamper_and_read_only_writes(self) -> None:
        review = self.by_id["review"]
        receipt = self._receipt(review, self._attempt(review))
        tampered = copy.deepcopy(receipt)
        tampered["output_packet_digest"] = sha256_text("different")
        self.assertEqual(
            "FAIL",
            validate_execution_unit_receipt(tampered, unit=review)["status"],
        )

        write_claim = copy.deepcopy(receipt)
        write_claim["attempts"][0]["writes_observed"] = True
        _rehash(write_claim["attempts"][0], "attempt_id")
        write_claim["effect_state"] = "verified-writes"
        _rehash(write_claim, "receipt_id")
        result = validate_execution_unit_receipt(write_claim, unit=review)
        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "EXECUTION_UNIT_READ_ONLY_EFFECT_INVALID",
            {issue["code"] for issue in result["issues"]},
        )

    def test_receipt_bundle_requires_exact_host_coverage(self) -> None:
        review = self.by_id["review"]
        receipt = self._receipt(review, self._attempt(review))
        self.assertEqual(
            "FAIL",
            validate_execution_receipt_bundle(
                self.units,
                [receipt],
                require_all_host_units=True,
            )["status"],
        )
        self.assertEqual(
            "PASS",
            validate_execution_receipt_bundle(
                self.units,
                [receipt],
                require_all_host_units=False,
            )["status"],
        )

    def test_stage_receipts_use_projected_ownership_not_claimed_source(
        self,
    ) -> None:
        plan, stage, _ = self._stage_fixture()
        source_claim = copy.deepcopy(stage)
        source_claim["evidence_source"] = "deterministic_command"
        source_claim.pop("execution_unit_receipt")
        result = validate_stage_execution_receipts(
            plan_summary=plan,
            stage_results=[source_claim],
            work_spans=[],
            expected_framework_version="0.2.0",
        )
        self.assertEqual("FAIL", result["status"])
        self.assertTrue(
            {
                "EXECUTION_UNIT_EVIDENCE_SOURCE_MISMATCH",
                "EXECUTION_UNIT_RECEIPT_REQUIRED",
            }.issubset(
                {issue["code"] for issue in result["issues"]}
            )
        )

    def test_receipt_is_rejected_when_owned_receipts_are_disabled(
        self,
    ) -> None:
        plan, stage, work_spans = self._stage_fixture()
        plan["execution_receipts_required"] = False
        result = validate_stage_execution_receipts(
            plan_summary=plan,
            stage_results=[stage],
            work_spans=work_spans,
            expected_framework_version="0.2.0",
        )
        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "EXECUTION_UNIT_RECEIPT_CONTEXT_INVALID",
            {issue["code"] for issue in result["issues"]},
        )

    def test_stage_receipt_framework_is_caller_bound_and_historical(
        self,
    ) -> None:
        plan, stage, work_spans = self._stage_fixture(
            framework_version="0.2.0",
        )
        exact = validate_stage_execution_receipts(
            plan_summary=plan,
            stage_results=[stage],
            run_id="run-one",
            observation_id="observation-one",
            work_spans=work_spans,
            expected_framework_version="0.2.0",
        )
        self.assertEqual("PASS", exact["status"])
        current_mismatch = validate_stage_execution_receipts(
            plan_summary=plan,
            stage_results=[stage],
            run_id="run-one",
            observation_id="observation-one",
            work_spans=work_spans,
            expected_framework_version="0.3.0",
        )
        self.assertEqual("FAIL", current_mismatch["status"])

    def test_malformed_stage_receipt_inputs_fail_without_exceptions(
        self,
    ) -> None:
        plan, stage, work_spans = self._stage_fixture()
        malformed_attempt = copy.deepcopy(stage)
        malformed_attempt["execution_unit_receipt"]["attempts"] = [None]
        _rehash(
            malformed_attempt["execution_unit_receipt"],
            "receipt_id",
        )
        fixtures = [
            ([malformed_attempt], work_spans),
            ([stage], [None]),
            (
                [
                    {
                        **stage,
                        "evidence_refs": [
                            stage["evidence_refs"][0],
                            stage["evidence_refs"][0],
                        ],
                    }
                ],
                work_spans,
            ),
        ]
        for stage_results, spans in fixtures:
            with self.subTest(stage_results=stage_results, spans=spans):
                result = validate_stage_execution_receipts(
                    plan_summary=plan,
                    stage_results=stage_results,
                    work_spans=spans,
                    expected_framework_version="0.2.0",
                )
                self.assertEqual("FAIL", result["status"])

    def test_public_schema_required_fields_match_runtime_contracts(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/execution-unit.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            EXECUTION_UNIT_FIELDS,
            set(schema["$defs"]["executionUnit"]["required"]),
        )
        self.assertEqual(
            ATTEMPT_FIELDS,
            set(schema["$defs"]["executionAttempt"]["required"]),
        )
        self.assertEqual(
            RECEIPT_FIELDS,
            set(schema["$defs"]["executionUnitReceipt"]["required"]),
        )
        self.assertEqual(
            "route-v2.schema.json#/$defs/modelRoute",
            schema["$defs"]["executionUnit"]["properties"]["model_route"][
                "$ref"
            ],
        )

    def test_public_event_and_receipt_schemas_share_new_boundaries(self) -> None:
        schemas = ROOT / "src/maestro/resources/schemas"
        event_schema = json.loads(
            (schemas / "event.schema.json").read_text(encoding="utf-8")
        )
        receipt_schema = json.loads(
            (schemas / "run-receipt.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for definition in ("planSummary", "stageResult"):
            self.assertEqual(
                event_schema["$defs"][definition],
                receipt_schema["$defs"][definition],
            )
        plan = event_schema["$defs"]["planSummary"]["properties"]
        assignment = plan["assignments"]["items"]["properties"]
        stage = event_schema["$defs"]["stageResult"]["properties"]
        self.assertEqual({"const": True}, plan["execution_receipts_required"])
        self.assertEqual(
            "execution-unit.schema.json#/$defs/executionUnit",
            assignment["execution_unit"]["$ref"],
        )
        self.assertIn("task_class", assignment)
        self.assertEqual(
            "execution-unit.schema.json#/$defs/executionUnitReceipt",
            stage["execution_unit_receipt"]["$ref"],
        )
        self.assertEqual(
            "model-feedback.schema.json#/$defs/verificationAssessment",
            stage["verification_assessment"]["$ref"],
        )

        route_schema = json.loads(
            (schemas / "route-v2.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "model-feedback.schema.json#/$defs/modelPolicyOverlay",
            route_schema["properties"]["model_policy_overlays"]["items"][
                "$ref"
            ],
        )
        decision_schema = json.loads(
            (schemas / "decision-workflow.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "route-v2.schema.json",
            decision_schema["$defs"]["executionPlan"]["properties"][
                "route_plan"
            ]["$ref"],
        )

    def test_new_public_schema_references_resolve_to_real_definitions(
        self,
    ) -> None:
        schema_root = ROOT / "src/maestro/resources/schemas"
        names = {
            "execution-unit.schema.json",
            "assignment-contracts.schema.json",
            "model-feedback.schema.json",
            "event.schema.json",
            "run-receipt.schema.json",
            "route-v2.schema.json",
            "decision-workflow.schema.json",
        }

        def references(value: object) -> list[str]:
            if isinstance(value, dict):
                found = (
                    [value["$ref"]]
                    if isinstance(value.get("$ref"), str)
                    else []
                )
                return found + [
                    reference
                    for item in value.values()
                    for reference in references(item)
                ]
            if isinstance(value, list):
                return [
                    reference
                    for item in value
                    for reference in references(item)
                ]
            return []

        for name in names:
            schema = json.loads(
                (schema_root / name).read_text(encoding="utf-8")
            )
            for reference in references(schema):
                if "://" in reference:
                    continue
                target_name, _, fragment = reference.partition("#")
                if target_name:
                    target_path = schema_root / target_name
                    self.assertTrue(target_path.is_file(), reference)
                    target: object = json.loads(
                        target_path.read_text(encoding="utf-8")
                    )
                else:
                    target = schema
                if not fragment:
                    continue
                self.assertTrue(fragment.startswith("/"), reference)
                for part in fragment.removeprefix("/").split("/"):
                    part = part.replace("~1", "/").replace("~0", "~")
                    self.assertIsInstance(target, dict, reference)
                    target = target[part]


if __name__ == "__main__":
    unittest.main()
