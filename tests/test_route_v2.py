from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.support import ROOT, write_json

from maestro.cli import main, parser
from maestro.execution_contracts import normalize_execution_contract
from maestro.model_policy import LEGACY_MODEL_ROUTE_FIELDS
from maestro.planning import (
    KIND_EXECUTOR,
    LIMIT_FIELDS,
    MODEL_ROUTE_FIELDS,
    ROUTE_V1,
    ROUTE_V2,
    SOURCE_ROUTE_FIELDS,
    TASK_CONTRACT_FIELDS,
    route_goal_v2,
    validate_route_v2,
)
from maestro.registry import load_registry, route_goal
from maestro.util import canonical_json, sha256_text


def rehash(plan: dict[str, object]) -> None:
    payload = copy.deepcopy(plan)
    payload.pop("plan_id", None)
    plan["plan_id"] = sha256_text(canonical_json(payload))


def rehash_source_and_plan(plan: dict[str, object]) -> None:
    source = {
        key: copy.deepcopy(plan[key])
        for key in sorted(SOURCE_ROUTE_FIELDS)
        if key in plan
    }
    source["schema_version"] = ROUTE_V1
    plan["source_route_digest"] = sha256_text(canonical_json(source))
    rehash(plan)


class RouteV2ContractTests(unittest.TestCase):
    def test_v2_is_an_additive_projection_and_v1_remains_default(self) -> None:
        arguments = parser().parse_args(
            ["route", "--goal", "Review the API contract"]
        )
        self.assertEqual("v1", arguments.route_version)

        v1 = route_goal(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        v2 = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )

        self.assertEqual(ROUTE_V1, v1["schema_version"])
        self.assertEqual(ROUTE_V2, v2["schema_version"])
        for key, value in v1.items():
            if key != "schema_version":
                self.assertEqual(value, v2[key], key)
        self.assertEqual(ROUTE_V1, v2["source_route_version"])
        self.assertEqual(64, len(v2["source_route_digest"]))
        self.assertEqual(64, len(v2["plan_id"]))
        self.assertEqual("PASS", validate_route_v2(v2)["status"])

        skill = (ROOT / "skills/maestro/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--route-version v2", skill)
        self.assertIn("maestro validate-plan", skill)
        self.assertNotIn("validation bypass", skill.casefold())

    def test_assignments_select_models_by_explicit_stage(self) -> None:
        plan = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        routes = {
            assignment["assignment_id"]: assignment["model_route"]
            for assignment in plan["assignments"]
        }

        self.assertEqual("semantic-review", routes["review"]["stage_kind"])
        self.assertEqual("implementation", routes["implementation"]["stage_kind"])
        self.assertEqual(
            "semantic-verification",
            routes["verification"]["stage_kind"],
        )
        self.assertTrue(
            all(
                route["selected_model"] == "gpt-5.6-terra"
                for route in routes.values()
            )
        )
        self.assertTrue(
            all(
                route["reasoning_effort"] == "high"
                for route in routes.values()
            )
        )
        self.assertEqual(
            len(routes),
            len({route["model_route_id"] for route in routes.values()}),
        )

    def test_high_risk_writer_can_reach_sol_without_keyword_guessing(self) -> None:
        plan = route_goal_v2(
            "Implement the approved API behavior",
            "high",
            ["contract"],
            intent="implementation",
        )

        writer = next(
            assignment
            for assignment in plan["assignments"]
            if assignment["kind"] == "implementation"
        )
        self.assertEqual("gpt-5.6-sol", writer["model_route"]["selected_model"])

    def test_explicitly_difficult_medium_risk_writer_can_reach_sol(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Implement a difficult algorithm across multiple compiler passes",
            "medium",
            intent="implementation",
        )
        writer = next(
            assignment
            for assignment in plan["assignments"]
            if assignment["kind"] == "implementation"
        )

        self.assertEqual(
            "complex-implementation",
            writer["model_route"]["task_class"],
        )
        self.assertEqual(
            "gpt-5.6-sol",
            writer["model_route"]["selected_model"],
        )
        self.assertEqual("high", writer["model_route"]["reasoning_effort"])

        varied_wording = route_goal_v2(
            (
                "Implement a difficult compiler optimizer rewrite with "
                "subtle semantic invariants"
            ),
            "medium",
            intent="implementation",
        )
        varied_writer = next(
            assignment
            for assignment in varied_wording["assignments"]
            if assignment["kind"] == "implementation"
        )
        self.assertEqual(
            "complex-implementation",
            varied_writer["model_route"]["task_class"],
        )
        self.assertEqual(
            "gpt-5.6-sol",
            varied_writer["model_route"]["selected_model"],
        )

        ordinary = route_goal_v2(
            "Implement CRUD within the existing architecture",
            "medium",
            intent="implementation",
        )
        ordinary_writer = next(
            assignment
            for assignment in ordinary["assignments"]
            if assignment["kind"] == "implementation"
        )
        self.assertEqual(
            "gpt-5.6-terra",
            ordinary_writer["model_route"]["selected_model"],
        )
        architecture = route_goal_v2(
            "Implement the approved architecture decision for service boundaries",
            "medium",
            intent="implementation",
        )
        architecture_writer = next(
            assignment
            for assignment in architecture["assignments"]
            if assignment["kind"] == "implementation"
        )
        self.assertEqual(
            "gpt-5.6-sol",
            architecture_writer["model_route"]["selected_model"],
        )

    def test_explicitly_difficult_semantic_stage_can_reach_sol(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Research a complex causal interaction and synthesize the evidence",
            "medium",
            intent="research",
        )
        researcher = next(
            assignment
            for assignment in plan["assignments"]
            if assignment["kind"] == "research"
        )

        self.assertEqual(
            "complex-semantic-judgment",
            researcher["model_route"]["task_class"],
        )
        self.assertEqual(
            "gpt-5.6-sol",
            researcher["model_route"]["selected_model"],
        )
        self.assertEqual("high", researcher["model_route"]["reasoning_effort"])

    def test_legacy_model_routes_remain_readable_but_not_executable(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Implement a CRUD endpoint",
            "medium",
            intent="implementation",
        )
        for model_route in [
            plan["model_route"],
            *(
                assignment["model_route"]
                for assignment in plan["assignments"]
            ),
        ]:
            for field in list(model_route):
                if field not in LEGACY_MODEL_ROUTE_FIELDS:
                    model_route.pop(field)
            model_route["reasoning_effort"] = "medium"
        rehash_source_and_plan(plan)

        validation = validate_route_v2(plan)
        self.assertEqual("PASS", validation["status"])
        self.assertEqual(
            "UPGRADE_REQUIRED",
            validation["execution_status"],
        )
        execution = normalize_execution_contract(plan)
        self.assertEqual("FAIL", execution["status"])
        self.assertEqual(
            "EXECUTION_MODEL_ROUTE_UPGRADE_REQUIRED",
            execution["issues"][0]["code"],
        )

    def test_legacy_top_route_cannot_report_ready_with_typed_assignments(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Implement a CRUD endpoint",
            "medium",
            intent="implementation",
        )
        for field in list(plan["model_route"]):
            if field not in LEGACY_MODEL_ROUTE_FIELDS:
                plan["model_route"].pop(field)
        rehash_source_and_plan(plan)

        validation = validate_route_v2(plan)
        self.assertEqual("PASS", validation["status"])
        self.assertEqual(
            "UPGRADE_REQUIRED",
            validation["execution_status"],
        )
        execution = normalize_execution_contract(plan)
        self.assertEqual("PASS", execution["status"])
        self.assertEqual(
            "UPGRADE_REQUIRED",
            execution["execution_status"],
        )

    def test_frozen_route_cases_produce_valid_bounded_plans(self) -> None:
        cases = json.loads(
            (ROOT / "tests/fixtures/route-v2-cases.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(20, len(cases))

        for case in cases:
            with self.subTest(case=case["case_id"]):
                plan = route_goal_v2(
                    case["goal"],
                    case["risk"],
                    case.get("explicit_lenses"),
                    intent=case["intent"],
                )
                self.assertEqual(case["expected_depth"], plan["depth"])
                self.assertEqual(case["expected_lenses"], plan["selected_lenses"])
                self.assertEqual(
                    case["expected_assignments"],
                    [item["assignment_id"] for item in plan["assignments"]],
                )
                self.assertLessEqual(len(plan["assignments"]), 5)
                self.assertEqual("PASS", validate_route_v2(plan)["status"])
                covered_lenses = []
                for assignment in plan["assignments"]:
                    self.assertEqual(
                        KIND_EXECUTOR[assignment["kind"]],
                        assignment["executor_id"],
                    )
                    covered_lenses.extend(assignment["lens_ids"])
                    if assignment["kind"] == "implementation":
                        self.assertFalse(assignment["read_only"])
                        self.assertTrue(assignment["mutation_owner"])
                    else:
                        self.assertTrue(assignment["read_only"])
                        self.assertFalse(assignment["mutation_owner"])
                self.assertEqual(
                    sorted(case["expected_lenses"]),
                    sorted(covered_lenses),
                )
                if case.get("expected_warning"):
                    self.assertIn(
                        case["expected_warning"],
                        [item["code"] for item in plan["warnings"]],
                    )

    def test_assignments_bind_registered_contracts_and_one_writer(self) -> None:
        plan = route_goal_v2(
            "Change authorization, transaction, and rollback behavior",
            "high",
            [
                "auth-boundary",
                "transaction-concurrency",
                "rollback-observability",
            ],
            intent="implementation",
        )
        registry = load_registry()
        executors = {
            item["executor_id"]: item
            for item in registry["executors"]
        }

        writers = []
        for assignment in plan["assignments"]:
            executor = executors[assignment["executor_id"]]
            self.assertEqual(set(executor["accepts"]), set(assignment["input_packets"]))
            self.assertIn(assignment["output_packet"], executor["returns"])
            self.assertEqual(
                assignment["executor_id"],
                assignment["model_route"]["executor"],
            )
            if assignment["mutation_owner"]:
                writers.append(assignment["assignment_id"])

        self.assertEqual(["implementation"], writers)
        self.assertEqual("implementation", plan["mutation_owner_assignment_id"])
        self.assertEqual(["verification"], plan["terminal_assignments"])

    def test_unknown_references_and_contract_mismatches_are_rejected(self) -> None:
        plan = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        invalid = copy.deepcopy(plan)
        invalid["assignments"][0]["executor_id"] = "missing-executor"
        invalid["assignments"][0]["lens_ids"] = ["missing-lens"]
        invalid["assignments"][1]["depends_on"] = ["missing-assignment"]
        invalid["assignments"][2]["input_packets"] = ["CompletionContract"]

        codes = {
            issue["code"]
            for issue in validate_route_v2(invalid)["issues"]
        }
        self.assertIn("ADAG_EXECUTOR_UNKNOWN", codes)
        self.assertIn("ADAG_LENS_UNKNOWN", codes)
        self.assertIn("ADAG_UNKNOWN_REFERENCE", codes)
        self.assertIn("ADAG_EXECUTOR_CONTRACT_MISMATCH", codes)
        self.assertIn("ADAG_CONTRACT_MISMATCH", codes)

    def test_cycle_duplicate_edge_and_terminal_drift_are_rejected(self) -> None:
        plan = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        invalid = copy.deepcopy(plan)
        invalid["assignments"][0]["depends_on"] = [
            "verification",
            "verification",
        ]
        invalid["terminal_assignments"] = ["implementation"]

        codes = {
            issue["code"]
            for issue in validate_route_v2(invalid)["issues"]
        }
        self.assertIn("ADAG_CYCLE", codes)
        self.assertIn("ADAG_DUPLICATE_EDGE", codes)
        self.assertIn("ADAG_UNDECLARED_LEAF", codes)

    def test_multiple_writers_and_reviewer_mutation_are_rejected(self) -> None:
        plan = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        invalid = copy.deepcopy(plan)
        reviewer = invalid["assignments"][0]
        reviewer["read_only"] = False
        reviewer["mutation_owner"] = True
        reviewer["allowed_side_effects"] = ["repository_write"]

        codes = {
            issue["code"]
            for issue in validate_route_v2(invalid)["issues"]
        }
        self.assertIn("ADAG_MULTIPLE_MUTATION_OWNERS", codes)
        self.assertIn("ADAG_REVIEWER_WRITE_FORBIDDEN", codes)

    def test_plan_digest_detects_tampering(self) -> None:
        plan = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
        )
        plan["goal"] = "Changed after validation"

        codes = {
            issue["code"]
            for issue in validate_route_v2(plan)["issues"]
        }
        self.assertIn("ADAG_PLAN_ID_MISMATCH", codes)

    def test_source_digest_binds_preserved_v1_projection(self) -> None:
        plan = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
        )
        plan["source_route_digest"] = "0" * 64
        rehash(plan)

        codes = {
            issue["code"]
            for issue in validate_route_v2(plan)["issues"]
        }
        self.assertIn("ADAG_SOURCE_ROUTE_DIGEST_MISMATCH", codes)

    def test_published_schema_fields_and_executable_model_route_agree(self) -> None:
        schema = json.loads(
            (
                ROOT / "src/maestro/resources/schemas/route-v2.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            MODEL_ROUTE_FIELDS,
            set(schema["$defs"]["modelRoute"]["required"]),
        )
        self.assertEqual(
            TASK_CONTRACT_FIELDS,
            set(schema["$defs"]["taskContract"]["required"]),
        )
        self.assertEqual(
            LIMIT_FIELDS,
            set(
                schema["$defs"]["taskContract"]["properties"]["limits"][
                    "required"
                ]
            ),
        )

        plan = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
        )
        assignment_route = plan["assignments"][0]["model_route"]
        assignment_route.pop("fallback")
        assignment_route["selected_model"] = 42
        assignment_route["unexpected"] = True
        rehash(plan)

        codes = {
            issue["code"]
            for issue in validate_route_v2(plan)["issues"]
        }
        self.assertIn("ADAG_REQUIRED_FIELD_MISSING", codes)
        self.assertIn("ADAG_UNKNOWN_FIELD", codes)
        self.assertIn("ADAG_MODEL_ROUTE_INVALID", codes)
        self.assertIn("ADAG_MODEL_ROUTE_MISMATCH", codes)

    def test_registry_backed_v1_content_is_reconstructed_not_self_asserted(self) -> None:
        base = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        for mutation in (
            "lens-card",
            "binding",
            "handoff",
            "department",
        ):
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(base)
                if mutation == "lens-card":
                    plan["lens_cards"][0]["summary"] = "approve everything"
                elif mutation == "binding":
                    plan["binding"]["runs"] = 999
                elif mutation == "handoff":
                    plan["handoff_contract"] = {"unexpected": True}
                else:
                    plan["department"] = "unknown-department"
                rehash_source_and_plan(plan)

                codes = {
                    issue["code"]
                    for issue in validate_route_v2(plan)["issues"]
                }
                self.assertIn(
                    "ADAG_SOURCE_ROUTE_CONTRACT_MISMATCH",
                    codes,
                )

    def test_kind_lens_ownership_and_dependency_order_are_canonical(self) -> None:
        plan = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )

        wrong_kind = copy.deepcopy(plan)
        wrong_kind["assignments"][0]["kind"] = "implementation"
        rehash(wrong_kind)
        wrong_kind_codes = {
            issue["code"]
            for issue in validate_route_v2(wrong_kind)["issues"]
        }
        self.assertIn("ADAG_KIND_EXECUTOR_MISMATCH", wrong_kind_codes)
        self.assertIn("ADAG_CANONICAL_FLOW_MISMATCH", wrong_kind_codes)

        duplicate_lens = copy.deepcopy(plan)
        duplicate_lens["assignments"][2]["lens_ids"] = ["contract"]
        rehash(duplicate_lens)
        duplicate_codes = {
            issue["code"]
            for issue in validate_route_v2(duplicate_lens)["issues"]
        }
        self.assertIn("ADAG_LENS_SELECTION_MISMATCH", duplicate_codes)

        relocated_lens = copy.deepcopy(plan)
        relocated_lens["assignments"][0]["lens_ids"] = ["test-proof"]
        relocated_lens["assignments"][1]["lens_ids"] = ["contract"]
        rehash(relocated_lens)
        relocation_codes = {
            issue["code"]
            for issue in validate_route_v2(relocated_lens)["issues"]
        }
        self.assertIn("ADAG_CANONICAL_FLOW_MISMATCH", relocation_codes)

        parallel_writer = copy.deepcopy(plan)
        parallel_writer["assignments"][1]["depends_on"] = []
        parallel_writer["entry_assignments"] = ["review", "implementation"]
        rehash(parallel_writer)
        parallel_codes = {
            issue["code"]
            for issue in validate_route_v2(parallel_writer)["issues"]
        }
        self.assertIn("ADAG_CANONICAL_FLOW_MISMATCH", parallel_codes)

    def test_depth_and_rebuttal_budgets_cannot_be_raised_or_rewritten(self) -> None:
        plan = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        plan["task_contract"]["limits"]["max_lenses"] = 3
        plan["task_contract"]["limits"]["max_rebuttal_rounds"] = 0
        rehash(plan)

        codes = {
            issue["code"]
            for issue in validate_route_v2(plan)["issues"]
        }
        self.assertIn("ADAG_BOUND_EXCEEDED", codes)

    def test_malformed_external_plan_returns_diagnostics_instead_of_crashing(self) -> None:
        plan = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
        )
        plan["selected_lenses"] = [{"not": "an id"}]
        plan["lens_cards"] = [None]
        plan["entry_assignments"] = [1]
        plan["terminal_assignments"] = [{"bad": "leaf"}]
        plan["model_route"] = []
        plan["assignments"][0]["input_packets"] = [{"bad": "packet"}]
        plan["assignments"][0]["read_only"] = "yes"

        result = validate_route_v2(plan)

        self.assertEqual("FAIL", result["status"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("ADAG_LENSES_INVALID", codes)
        self.assertIn("ADAG_LENS_CARD_MISMATCH", codes)
        self.assertIn("ADAG_PACKET_CONTRACT_INVALID", codes)
        self.assertIn("ADAG_ASSIGNMENT_ACCESS_INVALID", codes)
        self.assertIn("ADAG_MODEL_ROUTE_MISMATCH", codes)

    def test_unhashable_executor_ids_return_cli_diagnostics(self) -> None:
        for malformed in (None, 7, ["verifier"], {"id": "verifier"}):
            with self.subTest(malformed=malformed):
                plan = route_goal_v2(
                    "Review the API contract",
                    "medium",
                    intent="review",
                )
                plan["assignments"][0]["executor_id"] = malformed
                rehash(plan)
                with tempfile.TemporaryDirectory() as temporary:
                    plan_path = Path(temporary) / "plan.json"
                    write_json(plan_path, plan)
                    output = StringIO()
                    with redirect_stdout(output):
                        exit_code = main(
                            [
                                "validate-plan",
                                "--plan",
                                str(plan_path),
                                "--json",
                            ]
                        )
                result = json.loads(output.getvalue())
                self.assertEqual(2, exit_code)
                self.assertEqual("FAIL", result["status"])
                self.assertIn(
                    "ADAG_EXECUTOR_UNKNOWN",
                    {issue["code"] for issue in result["issues"]},
                )

    def test_unhashable_enum_values_never_escape_as_internal_errors(self) -> None:
        for mutation in (
            "intent",
            "intent-source",
            "risk",
            "depth",
            "top-model-risk",
            "assignment-model-risk",
            "assignment-kind",
            "rebuttal-limit",
        ):
            with self.subTest(mutation=mutation):
                plan = route_goal_v2(
                    "Review the API contract",
                    "medium",
                    intent="review",
                )
                if mutation == "intent":
                    plan["intent"] = {}
                elif mutation == "intent-source":
                    plan["intent_source"] = {}
                elif mutation == "risk":
                    plan["risk"] = {}
                elif mutation == "depth":
                    plan["depth"] = {}
                elif mutation == "top-model-risk":
                    plan["model_route"]["risk"] = {}
                elif mutation == "assignment-model-risk":
                    plan["assignments"][0]["model_route"]["risk"] = {}
                elif mutation == "assignment-kind":
                    plan["assignments"][0]["kind"] = {}
                else:
                    plan["task_contract"]["limits"]["max_rebuttal_rounds"] = []
                rehash_source_and_plan(plan)
                with tempfile.TemporaryDirectory() as temporary:
                    plan_path = Path(temporary) / "plan.json"
                    write_json(plan_path, plan)
                    output = StringIO()
                    with redirect_stdout(output):
                        exit_code = main(
                            [
                                "validate-plan",
                                "--plan",
                                str(plan_path),
                                "--json",
                            ]
                        )
                result = json.loads(output.getvalue())
                self.assertEqual(2, exit_code)
                self.assertEqual("FAIL", result["status"])

    def test_validate_plan_cli_is_read_only_and_has_stable_status(self) -> None:
        plan = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
        )
        with tempfile.TemporaryDirectory() as temporary:
            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "validate-plan",
                        "--plan",
                        str(plan_path),
                        "--json",
                    ]
                )

        result = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("PASS", result["status"])
        self.assertEqual([], result["issues"])
        self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
